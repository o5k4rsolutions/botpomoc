import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- SYSTEM UTRZYMANIA BOTA (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- KONFIGURACJA ---
load_dotenv()
TOKEN = os.getenv("TOKEN")
AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
LOG_CHANNEL_ID = 1462908198074974433
URLOP_POST_CHANNEL_ID = 1452784717802766397

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Bazy danych w pamięci
warns = {} # {user_id: [powody]}
vacations = {} # {user_id: {"reason": str, "end": datetime}}

# --- MODERACJA CHECK ---
def is_mod():
    async def predicate(ctx):
        role = ctx.guild.get_role(AUTHORIZED_ROLE_ID)
        return role in ctx.author.roles
    return commands.check(predicate)

# --- TASKS (URLOPY) ---
@tasks.loop(minutes=1)
async def check_vacations():
    now = datetime.datetime.now()
    expired = []
    for uid, data in vacations.items():
        if now >= data["end"]:
            user = bot.get_user(uid)
            log_chan = bot.get_channel(LOG_CHANNEL_ID)
            msg = f"🔔 <@{uid}>, Twój urlop dobiegł końca!"
            if log_chan: await log_chan.send(msg)
            try: await user.send(msg)
            except: pass
            expired.append(uid)
    for uid in expired: del vacations[uid]

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"Zalogowano jako {bot.user}")
    await bot.tree.sync()
    check_vacations.start()

@bot.event
async def on_thread_create(thread):
    # Obsługa postów na kanale urlopowym
    if thread.parent_id == URLOP_POST_CHANNEL_ID:
        await asyncio.sleep(2) # Chwila zwłoki na załadowanie wątku
        await thread.send("UWAGA! Urlop został przekazany do akceptacji opiekunów. Bez akceptacji nie masz urlopu. Dostaniesz informację gdy twój urlop zostanie dodany do bazy danych.")

@bot.event
async def on_message(message):
    if message.author.bot: return
    # Blokada TikToka
    if message.channel.id == TIKTOK_CHANNEL_ID and "tiktok.com" not in message.content:
        await message.delete()
    await bot.process_commands(message)

# --- KOMENDY SLASH (/) ---

@bot.tree.command(name="pv", description="Wysyła prywatną wiadomość do użytkownika")
async def pv(interaction: discord.Interaction, idosoby: str, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if not interaction.user.get_role(AUTHORIZED_ROLE_ID): return await interaction.response.send_message("Brak uprawnień", ephemeral=True)
    user = await bot.fetch_user(int(idosoby))
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    if not bezautora: embed.set_footer(text=f"Od: {interaction.user.name}")
    
    file_to_send = await plik.to_file() if plik else None
    await user.send(embed=embed, file=file_to_send)
    await interaction.response.send_message(f"Wysłano wiadomość do {user.name}", ephemeral=True)

@bot.tree.command(name="mess", description="Wysyła wiadomość Embed na wybrany kanał")
async def mess(interaction: discord.Interaction, idkanalu: str, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if not interaction.user.get_role(AUTHORIZED_ROLE_ID): return await interaction.response.send_message("Brak uprawnień", ephemeral=True)
    channel = bot.get_channel(int(idkanalu))
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    if not bezautora: embed.set_footer(text=f"Ogłoszenie od: {interaction.user.name}")
    
    file_to_send = await plik.to_file() if plik else None
    await channel.send(embed=embed, file=file_to_send)
    await interaction.response.send_message(f"Wysłano na <#{idkanalu}>", ephemeral=True)

# --- KOMENDY MODERATORSKIE (!) ---

@bot.command()
@is_mod()
async def clear(ctx, ilosc: int):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    deleted_messages = []
    async for message in ctx.channel.history(limit=ilosc):
        deleted_messages.append(message)
    
    deleted_messages.reverse()
    for msg in deleted_messages:
        if log_channel:
            files = [await a.to_file() for a in msg.attachments]
            embed = discord.Embed(title="🗑️ Usunięta wiadomość", description=msg.content or "*Tylko plik*", color=discord.Color.orange(), timestamp=msg.created_at)
            embed.set_author(name=f"{msg.author}", icon_url=msg.author.avatar.url if msg.author.avatar else None)
            await log_channel.send(embed=embed, files=files)

    await ctx.channel.purge(limit=ilosc + 1)
    await ctx.send(f"✅ Usunięto i zarchiwizowano {len(deleted_messages)} wiadomości.", delete_after=3)

@bot.command()
@is_mod()
async def dodajurlop(ctx, id_osoby: int, dni: int, *, powod: str):
    end_date = datetime.datetime.now() + datetime.timedelta(days=dni)
    vacations[id_osoby] = {"end": end_date, "reason": powod}
    await ctx.send(f"✅ Dodano urlop dla <@{id_osoby}> do {end_date.strftime('%d.%m.%Y')}. Powód: {powod}")

@bot.command()
@is_mod()
async def usunurl(ctx, id_osoby: int):
    if id_osoby in vacations:
        del vacations[id_osoby]
        await ctx.send(f"✅ Usunięto urlop dla <@{id_osoby}>.")
    else:
        await ctx.send("❌ Ta osoba nie ma aktywnego urlopu.")

@bot.command()
@is_mod()
async def warn(ctx, user: discord.Member, *, powod: str):
    if user.id not in warns: warns[user.id] = []
    warns[user.id].append(powod)
    await ctx.send(f"⚠️ {user.mention} ostrzeżony: {powod}. Suma: {len(warns[user.id])}")

@bot.command()
@is_mod()
async def unwarn(ctx, user: discord.Member):
    if user.id not in warns or not warns[user.id]:
        return await ctx.send("Ten użytkownik nie ma ostrzeżeń.")
    warns[user.id].pop()
    await ctx.send(f"✅ Usunięto ostatnie ostrzeżenie dla {user.mention}. Pozostało: {len(warns[user.id])}")

@bot.command()
@is_mod()
async def ban(ctx, user: discord.Member, *, powod: str):
    try:
        await user.send(f"Zostałeś zbanowany na serwerze za: {powod}")
    except: pass
    await user.ban(reason=powod)
    await ctx.send(f"🔨 Zbanowano {user.name} za: {powod}")

# --- URUCHOMIENIE ---
keep_alive()
bot.run(TOKEN)
