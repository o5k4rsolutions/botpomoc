import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
import datetime
import re
import os
import io
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Importy bibliotek PDF (wymagają instalacji pypdf i reportlab)
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, white

# --- SYSTEM UTRZYMANIA BOTA (KEEP ALIVE) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run_flask).start()

# --- KONFIGURACJA ---
load_dotenv()
TOKEN = os.getenv('TOKEN')

AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_FORUM_ID = 1452784717802766397
VACATION_LOG_CHANNEL_ID = 1462908198074974433

WATERMARK_URL = "https://discord.gg/TESTYPL"
WATERMARK_TEXT = "DISCORD.GG/TESTYPL"
DISCORD_1 = "manager3194"
DISCORD_2 = "razler_87290"

# --- LOGIKA WATERMARKA (NIZE 2026) ---
def add_watermark(pdf_bytes):
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        first_page = reader.pages[0]
        W = float(first_page.mediabox.width)
        H = float(first_page.mediabox.height)

        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(W, H))
        
        # Marginesy
        can.saveState()
        can.setFillColor(white)
        can.rect(0, 0, W, 50, fill=1)
        can.rect(0, H - 20, W, 20, fill=1)
        can.rect(W - 18, 0, 18, H, fill=1)
        can.rect(0, 0, 15, H, fill=1)
        can.restoreState()

        can.linkURL(WATERMARK_URL, rect=(0, 0, W, H), thickness=0)

        # Znaki wodne w tle
        can.setFillColor(Color(0, 0, 0, alpha=0.07))
        can.setFont("Helvetica-Bold", 35)
        for i in range(1, 8):
            can.saveState()
            can.translate(W/2, (H/8)*i)
            can.rotate(15 if i%2==0 else -15)
            can.drawCentredString(0, 0, WATERMARK_TEXT)
            can.restoreState()

        # Napisy informacyjne
        can.setFillColor(black)
        can.setFont("Helvetica-Bold", 8)
        can.drawCentredString(W/2, H-13, f"DOKUMENT WYGENEROWANY DLA: {WATERMARK_TEXT}")
        can.drawCentredString(W/2, 23, f"W CELU ZAKUPU LUB PYTAN: {WATERMARK_TEXT}")
        can.setFont("Helvetica", 7)
        can.drawCentredString(W/2, 11, "NIZE © 2026 - Wszelkie prawa zastrzezone")

        # Pionowy napis
        can.setFont("Helvetica-Bold", 9)
        can.saveState()
        can.translate(W - 8, H / 2)
        can.rotate(90)
        can.drawCentredString(0, 0, f"DISCORD: {DISCORD_1} | {DISCORD_2} | ZAKUP: {WATERMARK_TEXT}")
        can.restoreState()

        can.save()
        packet.seek(0)
        new_pdf = PdfReader(packet)
        output = PdfWriter()

        for page in reader.pages:
            page.merge_page(new_pdf.pages[0])
            output.add_page(page)

        output.encrypt(user_password='', owner_password="SecretPassword", permissions_flag=-4092)
        res_bytes = io.BytesIO()
        output.write(res_bytes)
        return res_bytes.getvalue()
    except Exception as e:
        print(f"Błąd PDF: {e}")
        return pdf_bytes

# --- POMOCNICZA FUNKCJA DO PLIKÓW ---
async def process_attachments(attachments):
    files_data = []
    for att in attachments:
        if att:
            data = await att.read()
            if att.filename.lower().endswith(".pdf"):
                data = add_watermark(data)
                files_data.append({"data": data, "name": f"NIZE_{att.filename}"})
            else:
                files_data.append({"data": data, "name": att.filename})
    return files_data

# --- INICJALIZACJA BOTA ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

def setup_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS warns (user_id TEXT, reason TEXT, timestamp TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS vacations (user_id TEXT, end_date TEXT, reason TEXT, active INTEGER)')
    conn.commit()
    conn.close()

setup_db()

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not check_vacations.is_running(): check_vacations.start()
    print(f"✅ Bot Online: {bot.user}")

# --- KOMENDY MODERACYJNE ---

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason="Brak powodu"):
    try: await member.send(f"Zostałeś zbanowany na serwerze {ctx.guild.name}. Powód: {reason}")
    except: pass
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

# --- KOMENDY SLASH (PV / MESS) ---

@bot.tree.command(name="pv", description="PV do wielu osób i wiele plików")
@app_commands.describe(osoby="Wspomnij osoby lub wklej ID", temat="Temat wiadomości", wiadomosc="Treść wiadomości")
async def pv(interaction: discord.Interaction, osoby: str, temat: str, wiadomosc: str, 
             plik1: discord.Attachment = None, plik2: discord.Attachment = None, plik3: discord.Attachment = None):
    
    if not any(r.id == AUTHORIZED_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    user_ids = list(set(re.findall(r'\d+', osoby)))
    
    if not user_ids:
        return await interaction.followup.send("❌ Nie wykryto żadnych osób (użyj wzmianek lub ID).")

    processed_files = await process_attachments([plik1, plik2, plik3])
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    embed.set_footer(text=f"Autor: {interaction.user.display_name}")

    success, failed = [], []
    for u_id in user_ids:
        try:
            user = await bot.fetch_user(int(u_id))
            current_files = [discord.File(io.BytesIO(f["data"]), filename=f["name"]) for f in processed_files]
            await user.send(embed=embed, files=current_files)
            success.append(user.name)
        except:
            failed.append(u_id)

    res = f"✅ Wysłano do: {', '.join(success)}" if success else "❌ Nie wysłano do nikogo."
    if failed: res += f"\n⚠️ Nie udało się do (zablokowane PV): {len(failed)} osób."
    await interaction.followup.send(res)

@bot.tree.command(name="mess", description="Wiadomość na kanał z wieloma plikami")
async def mess(interaction: discord.Interaction, kanal: discord.TextChannel, temat: str, wiadomosc: str, 
               plik1: discord.Attachment = None, plik2: discord.Attachment = None, plik3: discord.Attachment = None):
    
    if not any(r.id == AUTHORIZED_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    processed_files = await process_attachments([plik1, plik2, plik3])
    discord_files = [discord.File(io.BytesIO(f["data"]), filename=f["name"]) for f in processed_files]
    
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    embed.set_footer(text=f"Autor: {interaction.user.display_name}")

    await kanal.send(embed=embed, files=discord_files)
    await interaction.followup.send(f"✅ Wysłano na {kanal.mention}")

# --- SYSTEM URLOPÓW ---

@bot.event
async def on_thread_create(thread):
    if thread.parent_id == VACATION_FORUM_ID:
        embed = discord.Embed(title="Wniosek o urlop", description="Twój urlop został zapisany. Czekaj na zatwierdzenie przez opiekuna.", color=discord.Color.orange())
        await thread.send(embed=embed)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name == "✅":
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if not member or member.bot: return
        if any(r.id == AUTHORIZED_ROLE_ID for r in member.roles):
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", message.content)
            if not date_match: return
            
            end_date = date_match.group(1)
            conn = sqlite3.connect('bot_data.db')
            c = conn.cursor()
            c.execute("INSERT INTO vacations VALUES (?, ?, ?, 1)", (str(message.author.id), end_date, "Zatwierdzony"))
            conn.commit()
            conn.close()
            await channel.send(f"✅ Urlop zatwierdzony dla {message.author.mention} do {end_date}.")

@tasks.loop(hours=24)
async def check_vacations():
    today = datetime.datetime.now().strftime("%d.%m.%Y")
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM vacations WHERE end_date = ? AND active = 1", (today,))
    expired = c.fetchall()
    log_chan = bot.get_channel(VACATION_LOG_CHANNEL_ID)
    for row in expired:
        if log_chan: await log_chan.send(f"🔔 Urlop <@{row[0]}> właśnie się zakończył.")
        c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (row[0],))
    conn.commit()
    conn.close()

# --- FILTR TIKTOKA ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == TIKTOK_CHANNEL_ID and "tiktok.com" not in message.content:
        await message.delete()
        return
    await bot.process_commands(message)

# START
keep_alive()
bot.run(TOKEN)
