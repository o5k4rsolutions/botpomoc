import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import re
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- SYSTEM UTRZYMANIA BOTA (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    # Port 8080 jest standardem dla usług typu Replit/render
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- KONFIGURACJA BOTA ---
load_dotenv()
TOKEN = os.getenv('TOKEN')

# ID z Twojej specyfikacji
AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_FORUM_ID = 1452784717802766397
VACATION_LOG_CHANNEL_ID = 1462908198074974433

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# --- BAZA DANYCH SQLITE ---
def setup_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS warns (user_id TEXT, reason TEXT, timestamp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS vacations (user_id TEXT, end_date TEXT, reason TEXT, active INTEGER)')
    conn.commit()
    conn.close()

setup_db()

# --- KOMENDY MODERACYJNE ---

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason="Brak powodu"):
    try:
        await member.send(f"Zostałeś zbanowany na serwerze {ctx.guild.name}. Powód: {reason}")
    except:
        pass
    await member.ban(reason=reason)
    await ctx.send(f"✅ Zbanowano {member.mention}. Powód: {reason}")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def warn(ctx, member: discord.Member, *, reason):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO warns VALUES (?, ?, ?)", (str(member.id), reason, str(datetime.datetime.now())))
    conn.commit()
    conn.close()
    await ctx.send(f"⚠️ Nadano ostrzeżenie dla {member.mention}. Powód: {reason}")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def unwarn(ctx, member: discord.Member):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT rowid, reason FROM warns WHERE user_id = ?", (str(member.id),))
    warns = c.fetchall()
    
    if not warns:
        return await ctx.send("Ta osoba nie ma ostrzeżeń.")

    class WarnView(discord.ui.View):
        def __init__(self):
            super().__init__()
            for rowid, reason in warns:
                btn = discord.ui.Button(label=f"Usuń: {reason[:20]}", style=discord.ButtonStyle.danger, custom_id=str(rowid))
                btn.callback = self.callback
                self.add_item(btn)

        async def callback(self, interaction: discord.Interaction):
            conn_int = sqlite3.connect('bot_data.db')
            c_int = conn_int.cursor()
            c_int.execute("DELETE FROM warns WHERE rowid = ?", (interaction.data['custom_id'],))
            conn_int.commit()
            conn_int.close()
            await interaction.response.send_message("Ostrzeżenie usunięte!", ephemeral=True)
            self.stop()

    await ctx.send(f"Wybierz ostrzeżenie do usunięcia dla {member.name}:", view=WarnView())

# --- KOMENDY SLASH (PV / MESS) ---

@bot.tree.command(name="pv", description="Wysyła wiadomość prywatną z embedem")
async def pv(interaction: discord.Interaction, osoba: discord.User, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if interaction.user.get_role(AUTHORIZED_ROLE_ID) is None:
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    if not bezautora:
        embed.set_footer(text=f"Autor: {interaction.user.display_name}")
    
    file = await plik.to_file() if plik else None
    try:
        await osoba.send(embed=embed, file=file)
        await interaction.response.send_message(f"Wysłano PV do {osoba.name}", ephemeral=True)
    except:
        await interaction.response.send_message("Błąd: PV zablokowane.", ephemeral=True)

@bot.tree.command(name="mess", description="Wysyła wiadomość na kanał")
async def mess(interaction: discord.Interaction, kanal: discord.TextChannel, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if interaction.user.get_role(AUTHORIZED_ROLE_ID) is None:
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    if not bezautora:
        embed.set_footer(text=f"Autor: {interaction.user.display_name}")
    
    file = await plik.to_file() if plik else None
    await kanal.send(embed=embed, file=file)
    await interaction.response.send_message(f"Wysłano na {kanal.mention}", ephemeral=True)

# --- SYSTEM URLOPÓW ---

@bot.event
async def on_thread_create(thread):
    if thread.parent_id == VACATION_FORUM_ID:
        embed = discord.Embed(
            title="Wniosek o urlop",
            description="Uwaga! Twój urlop został zapisany ale nie nadany. Otrzymasz informację gdy któryś z opiekunów nada urlop. Do tego momentu twój urlop nie jest aktywny.",
            color=discord.Color.orange()
        )
        await thread.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name == "✅":
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if member is None or member.bot: return
        
        if member.get_role(AUTHORIZED_ROLE_ID):
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            # Pobieranie daty i powodu
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", message.content)
            reason_match = re.search(r"[Zz] powodu\s+(.*)", message.content)
            
            if not date_match:
                await channel.send(f"UWAGA! {message.author.mention},\nUrlop nie zostanie dodany do bazy z powodu błędu w wzorze (brak daty).")
                return

            end_date = date_match.group(1)
            reason = reason_match.group(1).strip() if reason_match else "Brak powodu"
            
            conn = sqlite3.connect('bot_data.db')
            c = conn.cursor()
            c.execute("INSERT INTO vacations VALUES (?, ?, ?, 1)", (str(message.author.id), end_date, reason))
            conn.commit()
            conn.close()

            confirm = (f"Cześć {message.author.mention},\nOpiekun {member.display_name} nadał twój urlop. "
                       f"Dane zapisano w bazie NIZE PL. Kończy się: {end_date}. Powód: {reason}.")
            
            await channel.send(confirm)
            try: await message.author.send(confirm)
            except: pass

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def usunurl(ctx, member: discord.Member):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (str(member.id),))
    conn.commit()
    conn.close()
    await ctx.send(f"Usunięto urlop dla {member.mention}.")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def urlopy(ctx):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id, end_date, reason FROM vacations WHERE active = 1")
    rows = c.fetchall()
    if not rows: return await ctx.send("Brak aktywnych urlopów.")
    
    desc = "\n".join([f"<@{r[0]}> - do {r[1]} ({r[2]})" for r in rows])
    await ctx.send(embed=discord.Embed(title="Aktywne urlopy", description=desc))

# --- FILTR TIKTOKA I PĘTLE ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == TIKTOK_CHANNEL_ID:
        if "tiktok.com" not in message.content:
            await message.delete()
            return
    await bot.process_commands(message)

@tasks.loop(hours=24)
async def check_vacations():
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM vacations WHERE end_date = ? AND active = 1", (today,))
    expired = c.fetchall()
    
    log_chan = bot.get_channel(VACATION_LOG_CHANNEL_ID)
    for row in expired:
        user = bot.get_user(int(row[0]))
        msg = f"🔔 {user.mention if user else row[0]}, Twój urlop minął!"
        if log_chan: await log_chan.send(msg)
        if user:
            try: await user.send(msg)
            except: pass
        c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (row[0],))
    
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not check_vacations.is_running():
        check_vacations.start()
    print(f"Bot Online: {bot.user}")

# --- START BOTA ---
keep_alive() # Uruchamia serwer Flask w tle
bot.run(TOKEN)
