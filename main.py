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

# Importy do obsługi PDF i Watermarka
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color, black, white

# --- SYSTEM UTRZYMANIA BOTA (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- KONFIGURACJA I ZMIENNE ---
load_dotenv()
TOKEN = os.getenv('TOKEN')

AUTHORIZED_ROLE_ID = 1437194858375680102
TIKTOK_CHANNEL_ID = 1437380571180306534
VACATION_FORUM_ID = 1452784717802766397
VACATION_LOG_CHANNEL_ID = 1462908198074974433

WATERMARK_URL = "https://discord.gg/TESTYPL"
WATERMARK_TEXT_DISPLAY = "DISCORD.GG/TESTYPL"
DISCORD_USERNAME = "manager3194"
DISCORD_USERNAME_2 = "duns0649"

# --- LOGIKA WATERMARKA ---
def apply_watermark_logic(original_pdf_bytes: bytes) -> bytes:
    try:
        reader = PdfReader(io.BytesIO(original_pdf_bytes))
        first_page = reader.pages[0]
        PAGE_WIDTH = float(first_page.mediabox.width)
        PAGE_HEIGHT = float(first_page.mediabox.height)

        watermark_buffer = io.BytesIO()
        c = canvas.Canvas(watermark_buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        
        # Tło marginesów
        c.saveState()
        c.setFillColor(white)
        c.rect(0, 0, PAGE_WIDTH, 50, fill=1)
        c.rect(0, PAGE_HEIGHT - 20, PAGE_WIDTH, 20, fill=1)
        c.rect(PAGE_WIDTH - 18, 0, 18, PAGE_HEIGHT, fill=1)
        c.rect(0, 0, 15, PAGE_HEIGHT, fill=1)
        c.restoreState()

        c.linkURL(WATERMARK_URL, rect=(0, 0, PAGE_WIDTH, PAGE_HEIGHT), thickness=0)

        # Znaki wodne na środku
        c.setFillColor(Color(0, 0, 0, alpha=0.07))
        c.setFont("Helvetica-Bold", 35) 
        for i in range(1, 8):
            c.saveState()
            c.translate(PAGE_WIDTH/2, (PAGE_HEIGHT/8) * i)
            c.rotate(15 if i % 2 == 0 else -15)
            c.drawCentredString(0, 0, WATERMARK_TEXT_DISPLAY)
            c.restoreState()
            
        # Teksty informacyjne
        txt_side_right = f"DISCORD: {DISCORD_USERNAME} | {DISCORD_USERNAME_2} | ZAKUP: {WATERMARK_TEXT_DISPLAY}"
        txt_contact_bottom = f"KONTAKT: {DISCORD_USERNAME} | {DISCORD_USERNAME_2} | nizekontakt@int.pl | nize@int.pl" 
        txt_purchase_bottom = f"W CELU ZAKUPU LUB PYTAN: {WATERMARK_TEXT_DISPLAY}"
        txt_top = f"DOKUMENT WYGENEROWANY DLA: {WATERMARK_TEXT_DISPLAY}"
        txt_gen = "NIZE © 2026 - Wszelkie prawa zastrzezone"

        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 13, txt_top)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(PAGE_WIDTH / 2, 35, txt_contact_bottom)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(PAGE_WIDTH / 2, 23, txt_purchase_bottom)
        c.setFont("Helvetica", 7) 
        c.drawCentredString(PAGE_WIDTH / 2, 11, txt_gen)
        
        # Prawy margines pionowy
        c.setFont("Helvetica-Bold", 9) 
        c.saveState()
        c.translate(PAGE_WIDTH - 8, PAGE_HEIGHT / 2)
        c.rotate(90)
        c.drawCentredString(0, 0, txt_side_right)
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

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def unwarn(ctx, member: discord.Member):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT rowid, reason FROM warns WHERE user_id = ?", (str(member.id),))
    warns = c.fetchall()
    if not warns: return await ctx.send("Ta osoba nie ma ostrzeżeń.")

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

# --- KOMENDY SLASH Z PRZETWARZANIEM PDF ---
@bot.tree.command(name="pv", description="Wysyła wiadomość prywatną z watermarkiem PDF")
async def pv(interaction: discord.Interaction, osoba: discord.User, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if not any(role.id == AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.blue())
    if not bezautora: embed.set_footer(text=f"Autor: {interaction.user.display_name}")
    
    file_to_send = None
    if plik:
        file_bytes = await plik.read()
        if plik.filename.lower().endswith(".pdf"):
            processed = apply_watermark_logic(file_bytes)
            file_to_send = discord.File(io.BytesIO(processed), filename=f"NIZE_{plik.filename}")
        else:
            file_to_send = discord.File(io.BytesIO(file_bytes), filename=plik.filename)

    try:
        await osoba.send(embed=embed, file=file_to_send)
        await interaction.followup.send(f"✅ Wysłano PV do {osoba.name}")
    except:
        await interaction.followup.send("❌ Błąd: PV zablokowane.")

@bot.tree.command(name="mess", description="Wysyła wiadomość na kanał z watermarkiem PDF")
async def mess(interaction: discord.Interaction, kanal: discord.TextChannel, temat: str, wiadomosc: str, bezautora: bool = False, plik: discord.Attachment = None):
    if not any(role.id == AUTHORIZED_ROLE_ID for role in interaction.user.roles):
        return await interaction.response.send_message("Brak uprawnień.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title=temat, description=wiadomosc, color=discord.Color.green())
    if not bezautora: embed.set_footer(text=f"Autor: {interaction.user.display_name}")
    
    file_to_send = None
    if plik:
        file_bytes = await plik.read()
        if plik.filename.lower().endswith(".pdf"):
            processed = apply_watermark_logic(file_bytes)
            file_to_send = discord.File(io.BytesIO(processed), filename=f"NIZE_{plik.filename}")
        else:
            file_to_send = discord.File(io.BytesIO(file_bytes), filename=plik.filename)

    await kanal.send(embed=embed, file=file_to_send)
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
        if any(role.id == AUTHORIZED_ROLE_ID for role in member.roles):
            channel = bot.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", message.content)
            reason_match = re.search(r"[Zz] powodu\s+(.*)", message.content)
            if not date_match: return
            end_date = date_match.group(1)
            reason = reason_match.group(1).strip() if reason_match else "Brak powodu"
            conn = sqlite3.connect('bot_data.db')
            c = conn.cursor()
            c.execute("INSERT INTO vacations VALUES (?, ?, ?, 1)", (str(message.author.id), end_date, reason))
            conn.commit()
            conn.close()
            await channel.send(f"✅ Urlop zatwierdzony dla {message.author.mention} do {end_date}.")

@bot.command()
@commands.has_role(AUTHORIZED_ROLE_ID)
async def usunurl(ctx, member: discord.Member):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (str(member.id),))
    conn.commit()
    conn.close()
    await ctx.send(f"Usunięto urlop dla {member.mention}.")

# --- FILTR I PĘTLE ---
@bot.event
async def on_message(message):
    if message.author.bot: return
    if message.channel.id == TIKTOK_CHANNEL_ID and "tiktok.com" not in message.content:
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
        if log_chan: await log_chan.send(f"🔔 Urlop użytkownika <@{row[0]}> wygasł.")
        c.execute("UPDATE vacations SET active = 0 WHERE user_id = ?", (row[0],))
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not check_vacations.is_running(): check_vacations.start()
    print(f"Bot Online: {bot.user}")

keep_alive()
bot.run(TOKEN)
