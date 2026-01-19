import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import asyncio
import random
import os
from dotenv import load_dotenv

load_dotenv()

# --- KONFIGURACJA ---
TOKEN = os.getenv("TOKEN")
AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_LOG_CHANNEL_ID = 1462908198074974433

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Bazy danych w pamięci (dla hostingu 24/7 warto użyć SQLite/JSON)
warns = {} # {user_id: [warn1, warn2]}
vacations = {} # {user_id: {"reason": str, "end_date": datetime, "channel_id": int}}

# --- ZARTY (60 sztuk - przykładowa lista) ---
JOKES = [
    "Dlaczego nauczycielka nosi okulary przeciwsłoneczne? Bo ma tak błyskotliwych uczniów!",
    "Sprawdzian to nie wyścigi, ale i tak zawsze jestem ostatni.",
    "Nauczyciel: Dlaczego nie masz zadania? Uczeń: Bo dom jest do mieszkania, a nie do pracy.",
    # ... tutaj dodaj pozostałe 57 żartów ...
] + [f"Żart o szkole nr {i}" for i in range(4, 61)]

# --- NARZĘDZIA ---
def is_authorized():
    async def predicate(ctx):
        role = ctx.guild.get_role(AUTHORIZED_ROLE_ID)
        return role in ctx.author.roles
    return commands.check(predicate)

# --- TASKS ---
@tasks.loop(minutes=1)
async def check_vacations():
    now = datetime.datetime.now()
    to_remove = []
    for user_id, data in vacations.items():
        if now >= data["end_date"]:
            user = bot.get_user(user_id)
            guild_channel = bot.get_channel(data["channel_id"])
            log_channel = bot.get_channel(VACATION_LOG_CHANNEL_ID)
            
            msg = f"🔔 {user.mention}, Twój urlop właśnie się skończył!"
            
            if guild_channel: await guild_channel.send(msg)
            if log_channel: await log_channel.send(msg)
            try: await user.send(msg)
            except: pass
            to_remove.append(user_id)
            
    for uid in to_remove:
        del vacations[uid]

# --- EVENTS ---
@bot.event
async def on_ready():
    await bot.tree.sync()
    check_vacations.start()
    print(f"Zalogowano jako {bot.user}")

@bot.event
async def on_message(message):
    if message.author.bot: return
    
    # Blokada kanału TikTok
    if message.channel.id == TIKTOK_CHANNEL_ID:
        if "tiktok.com" not in message.content:
            await message.delete()
            return

    await bot.process_commands(message)

# --- SLASH COMMANDS ---

@bot.tree.command(name="pv", description="Wysyła wiadomość prywatną")
@app_commands.describe(osoba="ID osoby", temat="Temat embeda", wiadomosc="Treść", bezautora="Czy ukryć autora?", plik="Załącznik")
async def pv(interaction: discord.Interaction, osoba: str, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if interaction.user.get_role(AUTHORIZED_ROLE_ID) is None:
        return await interaction.response.send_message("Brak uprawnień!", ephemeral=True)
    
    user = await bot.fetch_user(int(osoba))
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    if not bezautora:
        embed.set_footer(text=f"Wysłano przez: {interaction.user}", icon_url=interaction.user.avatar.url)
    
    file = await plik.to_file() if plik else None
    
    try:
        await user.send(embed=embed, file=file)
        await interaction.response.send_message(f"Wysłano PV do {user.name}", ephemeral=True)
    except:
        await interaction.response.send_message("Nie udało się wysłać PV (zablokowane DM).", ephemeral=True)

@bot.tree.command(name="mess", description="Wysyła wiadomość na kanał")
async def mess(interaction: discord.Interaction, idkanalu: str, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if interaction.user.get_role(AUTHORIZED_ROLE_ID) is None:
        return await interaction.response.send_message("Brak uprawnień!", ephemeral=True)
    
    channel = bot.get_channel(int(idkanalu))
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    if not bezautora:
        embed.set_footer(text=f"Autor: {interaction.user}")
    
    file = await plik.to_file() if plik else None
    await channel.send(embed=embed, file=file)
    await interaction.response.send_message("Wysłano!", ephemeral=True)

@bot.tree.command(name="zart", description="Losowy żart o szkole")
async def zart(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(JOKES))

# --- TRADYCYJNE KOMENDY (!) ---

@bot.command()
@is_authorized()
async def ban(ctx, member: discord.Member, *, powod="Brak"):
    embed = discord.Embed(title="Zostałeś zbanowany!", description=f"Powód: {powod}", color=discord.Color.red())
    try: await member.send(embed=embed)
    except: pass
    await member.ban(reason=powod)
    await ctx.send(f"Zbanowano {member.mention}")

@bot.command()
@is_authorized()
async def warn(ctx, member: discord.Member, *, powod):
    if member.id not in warns: warns[member.id] = []
    warns[member.id].append(powod)
    await ctx.send(f"Warn dla {member.mention}. Powód: {powod} (Suma: {len(warns[member.id])})")

@bot.command()
@is_authorized()
async def unwarn(ctx, member: discord.Member):
    if member.id not in warns or not warns[member.id]:
        return await ctx.send("Ten użytkownik nie ma ostrzeżeń.")
    
    view = discord.ui.View()
    for i, w in enumerate(warns[member.id]):
        btn = discord.ui.Button(label=f"Usuń: {w[:20]}...", style=discord.ButtonStyle.danger, custom_id=f"{member.id}_{i}")
        
        async def callback(interaction, idx=i, uid=member.id):
            warns[uid].pop(idx)
            await interaction.response.send_message("Usunięto ostrzeżenie!")
            
        btn.callback = callback
        view.add_item(btn)
    
    await ctx.send("Wybierz ostrzeżenie do usunięcia:", view=view)

@bot.command()
async def dodajurlop(ctx, member: discord.Member, czas_dni: int, *, powod):
    end_date = datetime.datetime.now() + datetime.timedelta(days=czas_dni)
    vacations[member.id] = {"reason": powod, "end_date": end_date, "channel_id": ctx.channel.id}
    await ctx.send(f"Dodano urlop dla {member.mention} do {end_date.strftime('%Y-%m-%d %H:%M')}")

@bot.command()
async def usunurl(ctx, member: discord.Member):
    if member.id in vacations:
        del vacations[member.id]
        await ctx.send(f"Usunięto urlop użytkownikowi {member.mention}")
    else:
        await ctx.send("Ta osoba nie ma aktywnego urlopu.")

bot.run(TOKEN)
