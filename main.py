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

# Importy bibliotek PDF (wymagają pypdf i reportlab)
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, white

# --- SYSTEM UTRZYMANIA BOTA (KEEP ALIVE DLA RENDER) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is running!"
def run_flask(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run_flask).start()

# --- KONFIGURACJA ---
load_dotenv()
TOKEN = os.getenv('TOKEN') # Pobiera token ze zmiennych środowiskowych Render

AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_FORUM_ID = 1452784717802766397
VACATION_LOG_CHANNEL_ID = 1462908198074974433

WATERMARK_URL = "https://discord.gg/TESTYPL"
WATERMARK_TEXT_DISPLAY = "DISCORD.GG/TESTYPL"
DISCORD_USERNAME = "manager3194"
DISCORD_USERNAME_2 = "duns0649"

# --- LOGIKA GENEROWANIA PDF (WERSJA PREMIUM 2026) ---
def add_watermark(original_pdf_bytes: bytes) -> bytes:
    try:
        reader = PdfReader(io.BytesIO(original_pdf_bytes))
        first_page = reader.pages[0]
        PAGE_WIDTH = float(first_page.mediabox.width)
        PAGE_HEIGHT = float(first_page.mediabox.height)

        watermark_buffer = io.BytesIO()
        c = canvas.Canvas(watermark_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        
        # --- RAMKI (KOLOR PREMIUM BŁĘKIT) ---
        c.saveState()
        c.setFillColorRGB(0.9, 0.95, 1.0) 
        c.rect(0, 0, PAGE_WIDTH, 50, fill=1)
        c.rect(0, PAGE_HEIGHT - 20, PAGE_WIDTH, 20, fill=1)
        c.rect(PAGE_WIDTH - 18, 0, 18, PAGE_HEIGHT, fill=1)
        c.rect(0, 0, 15, PAGE_HEIGHT, fill=1)
        c.restoreState()

        c.linkURL(WATERMARK_URL, rect=(0, 0, PAGE_WIDTH, PAGE_HEIGHT), thickness=0)

        # --- ŚRODKOWE ZNAKI WODNE (PRZEZROCZYSTE) ---
        c.setFillColor(Color(0, 0, 0, alpha=0.07))
        c.setFont("Helvetica-Bold", 35)
        for i in range(1, 6):
            c.saveState()
            side_offset = -30 if i % 2 == 0 else 30
            c.translate(PAGE_WIDTH/2 + side_offset, (PAGE_HEIGHT/6) * i)
            c.rotate(15 if i % 2 == 0 else -15)
            c.drawCentredString(0, 0, WATERMARK_TEXT_DISPLAY)
            c.restoreState()
            
        # --- MAŁE MAILE W ŚRODKU ---
        c.setFont("Helvetica-Bold", 10)
        central_emails = ["nize@int.pl", "nizekontakt@int.pl"]
        for mail in central_emails:
            rand_x = random.uniform(PAGE_WIDTH*0.25, PAGE_WIDTH*0.75)
            rand_y = random.uniform(PAGE_HEIGHT*0.25, PAGE_HEIGHT*0.75)
            c.saveState()
            c.translate(rand_x, rand_y)
            c.rotate(random.choice([25, -25, 35, -35]))
            c.drawCentredString(0, 0, mail)
            c.restoreState()

        # --- TEKSTY NA KRAWĘDZIACH ---
        txt_side_right = f"DISCORD: {DISCORD_USERNAME} | {DISCORD_USERNAME_2} | ZAKUP: {WATERMARK_TEXT_DISPLAY} | EMAIL: nizekontakt@int.pl"
        txt_side_left = f"DISCORD: {DISCORD_USERNAME} | {DISCORD_USERNAME_2} | ZAKUP: {WATERMARK_TEXT_DISPLAY} | EMAIL: nize@int.pl"
        txt_contact_bottom = f"KONTAKT: {DISCORD_USERNAME} | {DISCORD_USERNAME_2} | nizekontakt@int.pl | nize@int.pl" 
        txt_purchase_bottom = f"W CELU ZAKUPU LUB PYTAN: {WATERMARK_TEXT_DISPLAY}"
        txt_top = f"DOKUMENT WYGENEROWANY DLA: {WATERMARK_TEXT_DISPLAY}"
        
        current_time = datetime.datetime.now().strftime("%Y%m%d/%H:%M")

        # --- GÓRA I DÓŁ ---
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 13, txt_top)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(PAGE_WIDTH / 2, 35, txt_contact_bottom)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(PAGE_WIDTH / 2, 23, txt_purchase_bottom)

        # --- SPECJALNA LINIA Z WIĘKSZYM © ---
        poczatek = "NIZE "
        koniec = f" 2026 - Wszelkie prawa zastrzezone | DATA: {current_time}"
        
        c.setFont("Helvetica", 6.5)
        w_poczatek = c.stringWidth(poczatek, "Helvetica", 6.5)
        c.setFont("Helvetica-Bold", 12)
        w_symbol = c.stringWidth("©", "Helvetica-Bold", 12)
        c.setFont("Helvetica", 6.5)
        w_koniec = c.stringWidth(koniec, "Helvetica", 6.5)
        
        total_w = w_poczatek + w_symbol + w_koniec
        start_x = (PAGE_WIDTH - total_w) / 2
        
        c.setFont("Helvetica", 6.5)
        c.drawString(start_x, 11, poczatek)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(start_x + w_poczatek, 10, "©") 
        c.setFont("Helvetica", 6.5)
        c.drawString(start_x + w_poczatek + w_symbol, 11, koniec)
        
        # --- NAPISY BOCZNE (PIONOWE) ---
        c.setFont("Helvetica-Bold", 9) 
        c.saveState() 
        c.translate(PAGE_WIDTH - 8, PAGE_HEIGHT / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, txt_side_right)
        c.restoreState()
        c.saveState() 
        c.translate(8, PAGE_HEIGHT / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, txt_side_left)
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
    print(f"✅ Bot {bot.user} Online. System NIZE gotowy.")

# --- KOMENDY SLASH (PV / MESS) ---

@bot.tree.command(name="pv", description="Wysyła wiadomość do wielu osób z wieloma plikami")
@app_commands.describe(osoby="Wspomnij osoby lub wklej ID", temat="Temat wiadomości", wiadomosc="Treść")
async def pv(interaction: discord.Interaction, osoby: str, temat: str, wiadomosc: str, 
             plik1: discord.Attachment = None, plik2: discord.Attachment = None, plik3: discord.Attachment = None):
    
    if not any(r.id == AUTHORIZED_ROLE_ID for r in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    user_ids = list(set(re.findall(r'\d+', osoby))) # Wyciąga wszystkie ID z tekstu
    
    if not user_ids:
        return await interaction.followup.send("❌ Nie wykryto żadnych osób (użyj wzmianek lub wklej ID).")

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
        except Exception as e:
            failed.append(u_id)

    res = f"✅ Wysłano do: {', '.join(success)}" if success else "❌ Nie wysłano do nikogo."
    if failed: res += f"\n⚠️ Błąd u {len(failed)} osób (zablokowane PV)."
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

# --- SYSTEM MODERACJI I URLOPÓW ---

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def ban(ctx, member: discord.Member, *, reason="Brak powodu"):
    await member.ban(reason=reason)
    await ctx.send(f"✅ Zbanowano {member.mention}.")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def warn(ctx, member: discord.Member, *, reason):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO warns VALUES (?, ?, ?)", (str(member.id), reason, str(datetime.datetime.now())))
    conn.commit()
    conn.close()
    await ctx.send(f"⚠️ Warn dla {member.mention}. Powód: {reason}")

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

@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == TIKTOK_CHANNEL_ID and "tiktok.com" not in message.content:
        await message.delete()
        return
    await bot.process_commands(message)

# --- START ---
keep_alive()
bot.run(TOKEN)
