import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import re
import os
import io
import random
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Importy bibliotek PDF
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color

# --- KONFIGURACJA ---
load_dotenv()
TOKEN = os.getenv('TOKEN')

AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_FORUM_ID = 1452784717802766397
VACATION_LOG_CHANNEL_ID = 1462908198074974433

WATERMARK_URL = "https://discord.gg/TESTYPL"
WATERMARK_TEXT_DISPLAY = "DISCORD.GG/TESTYPL"

# --- SYSTEM KEEP ALIVE ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run_flask).start()

# --- BAZA DANYCH (ZACHOWUJE ISTNIEJĄCE DANE) ---
def setup_db():
    # Połączenie z plikiem bazy danych - jeśli plik istnieje, dane zostaną zachowane
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # IF NOT EXISTS gwarantuje, że nie usuniemy starych urlopów
    c.execute('CREATE TABLE IF NOT EXISTS warns (user_id TEXT, reason TEXT, timestamp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS vacations (user_id TEXT, end_date TEXT, reason TEXT, active INTEGER)')
    conn.commit()
    conn.close()

setup_db()

# --- LOGIKA PDF ---
def add_watermark(original_pdf_bytes: bytes) -> bytes:
    try:
        reader = PdfReader(io.BytesIO(original_pdf_bytes))
        first_page = reader.pages[0]
        PAGE_WIDTH = float(first_page.mediabox.width)
        PAGE_HEIGHT = float(first_page.mediabox.height)
        
        watermark_buffer = io.BytesIO()
        c = canvas.Canvas(watermark_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        
        # Obramowanie
        c.saveState()
        c.setFillColorRGB(0.9, 0.95, 1.0) 
        c.rect(0, 0, PAGE_WIDTH, 50, fill=1)
        c.rect(0, PAGE_HEIGHT - 20, PAGE_WIDTH, 20, fill=1)
        c.restoreState()

        c.linkURL(WATERMARK_URL, rect=(0, 0, PAGE_WIDTH, PAGE_HEIGHT), thickness=0)

        c.setFillColor(Color(0, 0, 0, alpha=0.07))
        c.setFont("Helvetica-Bold", 35)
        for i in range(1, 6):
            c.saveState()
            side_offset = -30 if i % 2 == 0 else 30
            c.translate(PAGE_WIDTH/2 + side_offset, (PAGE_HEIGHT/6) * i)
            c.rotate(15 if i % 2 == 0 else -15)
            c.drawCentredString(0, 0, WATERMARK_TEXT_DISPLAY)
            c.restoreState()

        c.save()
        watermark_buffer.seek(0)
        water_page = PdfReader(watermark_buffer).pages[0]
        writer = PdfWriter()
        for page in reader.pages:
            page.merge_page(water_page)
            writer.add_page(page)
        
        writer.encrypt(user_password='', owner_password="SecretPassword", permissions_flag=-4092)
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
    except Exception as e:
        print(f"Błąd PDF: {e}")
        return original_pdf_bytes

async def process_attachments(attachments):
    files_data = []
    for att in attachments:
        if att:
            data = await att.read()
            # Zabezpieczenie PDF znakiem wodnym
            if att.filename.lower().endswith(".pdf"):
                data = add_watermark(data)
                files_data.append({"data": data, "name": f"NIZE_{att.filename}"})
            else:
                files_data.append({"data": data, "name": att.filename})
    return files_data

# --- BOT SETUP ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not check_vacations.is_running(): check_vacations.start()
    print(f"✅ Bot {bot.user} Online. Dane z bazy zostały wczytane.")

# --- KOMENDY SLASH (Z OBSŁUGĄ 4 PLIKÓW) ---

@bot.tree.command(name="pv", description="Wysyła wiadomość do wielu osób (do 4 plików)")
async def pv(interaction: discord.Interaction, osoby: str, temat: str, wiadomosc: str, 
             pokaz_autora: bool = True, 
             plik1: discord.Attachment = None, plik2: discord.Attachment = None,
             plik3: discord.Attachment = None, plik4: discord.Attachment = None):
    
    if not any(r.id == AUTHORIZED_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    user_ids = list(set(re.findall(r'\d+', osoby)))
    processed_files = await process_attachments([plik1, plik2, plik3, plik4])
    
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    if pokaz_autora:
        embed.set_footer(text=f"Autor: {interaction.user.display_name}")

    success, failed = [], []
    for u_id in user_ids:
        try:
            user = await bot.fetch_user(int(u_id))
            # Tworzenie listy obiektów discord.File dla każdego odbiorcy
            files_to_send = [discord.File(io.BytesIO(f["data"]), filename=f["name"]) for f in processed_files]
            await user.send(embed=embed, files=files_to_send)
            success.append(user.name)
        except: failed.append(u_id)

    await interaction.followup.send(f"✅ Wysłano: {len(success)} | ❌ Błąd: {len(failed)}")

@bot.tree.command(name="mess", description="Wysyła wiadomość na kanał (do 4 plików)")
async def mess(interaction: discord.Interaction, kanal: discord.TextChannel, temat: str, wiadomosc: str, 
               pokaz_autora: bool = True, 
               plik1: discord.Attachment = None, plik2: discord.Attachment = None,
               plik3: discord.Attachment = None, plik4: discord.Attachment = None):
    
    if not any(r.id == AUTHORIZED_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    processed_files = await process_attachments([plik1, plik2, plik3, plik4])
    
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    if pokaz_autora:
        embed.set_footer(text=f"Autor: {interaction.user.display_name}")

    files_to_send = [discord.File(io.BytesIO(f["data"]), filename=f["name"]) for f in processed_files]
    await kanal.send(embed=embed, files=files_to_send)
    await interaction.followup.send(f"✅ Wysłano na {kanal.mention}")

# --- SYSTEM URLOPÓW ---

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def dodajurlop(ctx, user_id: str, data_koniec: str, *, powod: str):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO vacations (user_id, end_date, reason, active) VALUES (?, ?, ?, 1)", 
              (user_id, data_koniec, powod))
    conn.commit()
    conn.close()
    await ctx.send(f"✅ Dodano urlop dla <@{user_id}> do {data_koniec}.")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def usunurl(ctx, user_id: str):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    await ctx.send(f"✅ Usunięto urlop użytkownikowi <@{user_id}>.")

@bot.command()
async def urlopy(ctx):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id, end_date, reason FROM vacations WHERE active = 1")
    rows = c.fetchall()
    conn.close()
    
    if not rows: return await ctx.send("Aktualnie nikt nie ma urlopu.")
    
    txt = "**LISTA AKTYWNYCH URLOPÓW (ZACHOWANE DANE):**\n"
    for r in rows:
        txt += f"• <@{r[0]}> - do {r[1]} (Powód: {r[2]})\n"
    await ctx.send(txt)

@bot.event
async def on_thread_create(thread):
    if thread.parent_id == VACATION_FORUM_ID:
        embed = discord.Embed(
            title="✨ ZGŁOSZENIE URLOPU ✨",
            description=(
                f"**Uwaga!** {thread.owner.mention}, Twój urlop został zarejestrowany.\n\n"
                "Zostanie on aktywowany w bazie danych po zaakceptowaniu przez Opiekuna reakcją ✅."
            ),
            color=discord.Color.orange()
        )
        await thread.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name == "✅" and payload.user_id != bot.user.id:
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        
        if any(r.id == AUTHORIZED_ROLE_ID for r in member.roles):
            channel = bot.get_channel(payload.channel_id)
            if isinstance(channel, discord.Thread) and channel.parent_id == VACATION_FORUM_ID:
                async for message in channel.history(limit=1, oldest_first=True):
                    content = message.content
                    try:
                        data_match = re.search(r'(\d{2}\.\d{2}\.\d{4})', content)
                        powod_match = content.split("Z powodu")[-1].strip() if "Z powodu" in content else "Nie podano"
                        
                        if not data_match:
                            await channel.send(f"⚠️ Błąd daty u <@{message.author.id}>.")
                            return

                        data_koniec = data_match.group(1)
                        user_urlop = message.author

                        conn = sqlite3.connect('bot_data.db')
                        c = conn.cursor()
                        c.execute("INSERT INTO vacations VALUES (?, ?, ?, 1)", 
                                  (str(user_urlop.id), data_koniec, powod_match))
                        conn.commit()
                        conn.close()

                        await channel.send(f"✅ Urlop zaakceptowany dla {user_urlop.mention} do {data_koniec}.")
                    except:
                        await channel.send("❌ Błąd przetwarzania danych.")

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == TIKTOK_CHANNEL_ID:
        if "tiktok.com" not in message.content:
            await message.delete()
            return
    await bot.process_commands(message)

@tasks.loop(hours=12)
async def check_vacations():
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM vacations WHERE end_date = ? AND active = 1", (today,))
    expired = c.fetchall()
    
    log_chan = bot.get_channel(VACATION_LOG_CHANNEL_ID)
    
    for row in expired:
        u_id = int(row[0])
        msg = f"🔔 Koniec urlopu dla <@{u_id}>!"
        if log_chan: await log_chan.send(msg)
        c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (str(u_id),))
    
    conn.commit()
    conn.close()

# --- START ---
keep_alive()
bot.run(TOKEN)
