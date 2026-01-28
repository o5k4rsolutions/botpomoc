require('dotenv').config();
const { 
    Client, GatewayIntentBits, Partials, EmbedBuilder, 
    AttachmentBuilder, Events, REST, Routes 
} = require('discord.js');
const { PDFDocument, rgb, degrees } = require('pdf-lib');
const fontkit = require('@pdf-lib/fontkit');
const Database = require('better-sqlite3');
const express = require('express');
const cron = require('node-cron');
const fs = require('fs');

// --- KONFIGURACJA ---
const TOKEN = process.env.TOKEN;
const AUTHORIZED_ROLE_ID = '1437194858375680102';
const TIKTOK_CHANNEL_ID = '1437380571180306534';
const VACATION_FORUM_ID = '1452784717802766397';
const VACATION_LOG_CHANNEL_ID = '1462908198074974433';
const WATERMARK_TEXT = "DISCORD.GG/TESTYPL";

// --- BAZA DANYCH ---
const db = new Database('bot_data.db');
db.prepare('CREATE TABLE IF NOT EXISTS warns (user_id TEXT, reason TEXT, timestamp TEXT)').run();
db.prepare('CREATE TABLE IF NOT EXISTS vacations (user_id TEXT, end_date TEXT, reason TEXT, active INTEGER)').run();
db.prepare('CREATE TABLE IF NOT EXISTS message_logs (channel_name TEXT, author TEXT, content TEXT, timestamp TEXT)').run();

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildMessageReactions,
        GatewayIntentBits.GuildMembers
    ],
    partials: [Partials.Message, Partials.Channel, Partials.Reaction]
});

// --- KEEP ALIVE ---
const app = express();
app.get('/', (req, res) => res.send('Bot is running!'));
const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`✅ Serwer HTTP aktywny na porcie ${PORT}`));

// --- LOGIKA PDF (Błękitne ramki i znaki wodne) ---
async function processPDF(buffer) {
    try {
        const pdfDoc = await PDFDocument.load(buffer);
        pdfDoc.registerFontkit(fontkit);

        const fontRegular = await pdfDoc.embedFont(fs.readFileSync('./Helvetica.ttf'));
        const fontBold = await pdfDoc.embedFont(fs.readFileSync('./Helvetica-Bold.ttf'));

        const pages = pdfDoc.getPages();
        const currentTime = new Date().toLocaleString('pl-PL').replace(',', '');

        for (const page of pages) {
            const { width, height } = page.getSize();

            const blueFill = rgb(0.9, 0.95, 1.0);
            page.drawRectangle({ x: 0, y: 0, width: width, height: 50, color: blueFill });
            page.drawRectangle({ x: 0, y: height - 20, width: width, height: 20, color: blueFill });
            page.drawRectangle({ x: width - 18, y: 0, width: 18, height: height, color: blueFill });
            page.drawRectangle({ x: 0, y: 0, width: 15, height: height, color: blueFill });

            for (let i = 1; i <= 5; i++) {
                page.drawText(WATERMARK_TEXT, {
                    x: width / 2 - 120, y: (height / 6) * i,
                    size: 35, font: fontBold, color: rgb(0, 0, 0), opacity: 0.07,
                    rotate: degrees(i % 2 === 0 ? 15 : -15),
                });
            }

            const drawCenter = (text, y, size, fontType) => {
                const textWidth = fontType.widthOfTextAtSize(text, size);
                page.drawText(text, { x: (width - textWidth) / 2, y, size, font: fontType, color: rgb(0, 0, 0) });
            };

            drawCenter(`DOKUMENT WYGENEROWANY DLA: ${WATERMARK_TEXT}`, height - 13, 8, fontBold);
            drawCenter(`KONTAKT: manager3194 | duns0649 | nizekontakt@int.pl | nize@int.pl`, 35, 10, fontBold);
            drawCenter(`W CELU ZAKUPU LUB PYTAŃ: ${WATERMARK_TEXT}`, 23, 8, fontBold);
            drawCenter(`NIZE © 2026 - Wszelkie Prawa Zastrzeżone | DATA: ${currentTime}`, 10, 7, fontRegular);

            const sideTxt = `DISCORD: manager3194 | duns0649 | ZAKUP: ${WATERMARK_TEXT} | EMAIL: nize@int.pl`;
            const sideOptions = { size: 9, font: fontBold, rotate: degrees(90) };
            page.drawText(sideTxt, { x: width - 6, y: height / 2 - 150, ...sideOptions });
            page.drawText(sideTxt, { x: 10, y: height / 2 - 150, ...sideOptions });
        }
        return await pdfDoc.save();
    } catch (e) {
        console.error("Błąd PDF:", e);
        return buffer;
    }
}

// --- GENEROWANIE TRANSKRYPTU ---
async function generateDailyTranscript() {
    try {
        const rows = db.prepare('SELECT * FROM message_logs').all();
        if (rows.length === 0) return;

        const pdfDoc = await PDFDocument.create();
        pdfDoc.registerFontkit(fontkit);
        const fontRegular = await pdfDoc.embedFont(fs.readFileSync('./Helvetica.ttf'));
        const fontBold = await pdfDoc.embedFont(fs.readFileSync('./Helvetica-Bold.ttf'));

        let page = pdfDoc.addPage();
        let { width, height } = page.getSize();
        let yCursor = height - 100;

        page.drawText(`RAPORT Z DNIA: ${new Date().toLocaleDateString('pl-PL')}`, { x: 50, y: height - 80, size: 18, font: fontBold });

        for (const row of rows) {
            if (yCursor < 80) { page = pdfDoc.addPage(); yCursor = height - 100; }
            const cleanContent = row.content.replace(/[\n\r]/g, ' ').substring(0, 90);
            page.drawText(`[#${row.channel_name}] ${row.author}: ${cleanContent}`, { x: 50, y: yCursor, size: 8, font: fontRegular });
            yCursor -= 14;
        }

        const rawPdf = await pdfDoc.save();
        const finalPdf = await processPDF(rawPdf);

        const logChan = client.channels.cache.get(VACATION_LOG_CHANNEL_ID);
        if (logChan) {
            const attachment = new AttachmentBuilder(Buffer.from(finalPdf), { name: `Raport_${new Date().toLocaleDateString()}.pdf` });
            await logChan.send({ content: "📊 **Automatyczny raport dzienny wszystkich wiadomości:**", files: [attachment] });
        }
        db.prepare('DELETE FROM message_logs').run();
    } catch (e) { console.error("Błąd raportu:", e); }
}

// --- SYSTEM WIADOMOŚCI I TIKTOK ---
client.on(Events.MessageCreate, async message => {
    if (message.author.bot) return;

    db.prepare('INSERT INTO message_logs (channel_name, author, content, timestamp) VALUES (?, ?, ?, ?)')
      .run(message.channel.name || "Prywatny", message.author.tag, message.content, new Date().toLocaleString());

    if (message.channelId === TIKTOK_CHANNEL_ID && !message.content.includes('tiktok.com')) {
        return message.delete().catch(() => {});
    }
});

// --- SYSTEM URLOPÓW (Oryginalne teksty) ---
client.on(Events.ThreadCreate, async thread => {
    if (thread.parentId === VACATION_FORUM_ID) {
        const embed = new EmbedBuilder()
            .setTitle("✨ ZGŁOSZENIE URLOPU ✨")
            .setDescription(`**Uwaga!** <@${thread.ownerId}>, Twój urlop został zapisany w systemie, **ale nie jest jeszcze nadany**.\n\nOtrzymasz informację, gdy któryś z opiekunów nada urlop poprzez reakcję ✅.\nDo tego momentu Twój urlop nie jest aktywny.`)
            .setColor(0xFFA500)
            .setFooter({ text: "System Zarządzania NIZE PL" });
        await thread.send({ embeds: [embed] });
    }
});

client.on(Events.MessageReactionAdd, async (reaction, user) => {
    if (user.bot || reaction.emoji.name !== '✅') return;
    const member = await reaction.message.guild.members.fetch(user.id);
    if (member.roles.cache.has(AUTHORIZED_ROLE_ID)) {
        const thread = reaction.message.channel;
        if (thread.isThread() && thread.parentId === VACATION_FORUM_ID) {
            const msgs = await thread.messages.fetch({ limit: 10, after: '0' });
            const first = msgs.last();
            const dateMatch = first.content.match(/(\d{2}\.\d{2}\.\d{4})/);
            const reasonMatch = first.content.split("Z powodu")[1]?.trim() || "Nie podano";

            if (dateMatch) {
                db.prepare('INSERT INTO vacations (user_id, end_date, reason, active) VALUES (?, ?, ?, 1)').run(first.author.id, dateMatch[0], reasonMatch);
                const msg_text = `Cześć <@${first.author.id}>,\nOpiekun **${user.username}** nadał Twój urlop.\n📅 Koniec: **${dateMatch[0]}**\n📝 Powód: *${reasonMatch}*\nMiłego wypoczynku!`;
                await thread.send(msg_text);
                first.author.send(msg_text).catch(() => {});
            }
        }
    }
});

// --- HARMONOGRAMY (Cron) ---
cron.schedule('59 23 * * *', () => generateDailyTranscript());

cron.schedule('0 */12 * * *', async () => {
    const today = new Date().toLocaleDateString('pl-PL', { day: '2-digit', month: '2-digit', year: 'numeric' });
    const expired = db.prepare('SELECT user_id FROM vacations WHERE end_date = ? AND active = 1').all(today);
    expired.forEach(async row => {
        const msg = `🔔 Urlop <@${row.user_id}> właśnie się zakończył!`;
        [VACATION_LOG_CHANNEL_ID, TIKTOK_CHANNEL_ID].forEach(id => {
            const ch = client.channels.cache.get(id);
            if (ch) ch.send(msg);
        });
        const user = await client.users.fetch(row.user_id).catch(() => null);
        if (user) user.send("Twój urlop w NIZE PL dobiegł końca.").catch(() => {});
        db.prepare('UPDATE vacations SET active = 0 WHERE user_id = ?').run(row.user_id);
    });
});

// --- START I KOMENDY SLASH ---
client.once(Events.ClientReady, async c => {
    console.log(`✅ Bot ${c.user.tag} Online`);
    const rest = new REST({ version: '10' }).setToken(TOKEN);
    await rest.put(Routes.applicationCommands(c.user.id), { body: [
        {
            name: 'pv',
            description: 'Wysyła wiadomość do wielu osób',
            options: [
                { name: 'osoby', type: 3, description: 'ID osób (po spacji)', required: true },
                { name: 'temat', type: 3, description: 'Temat', required: true },
                { name: 'wiadomosc', type: 3, description: 'Treść', required: true },
                { name: 'pokaz_autora', type: 5, description: 'Czy pokazać autora?' }
            ]
        },
        {
            name: 'mess',
            description: 'Wysyła wiadomość na kanał',
            options: [
                { name: 'kanal', type: 7, description: 'Kanał docelowy', required: true },
                { name: 'temat', type: 3, description: 'Temat', required: true },
                { name: 'wiadomosc', type: 3, description: 'Treść', required: true },
                { name: 'pokaz_autora', type: 5, description: 'Czy pokazać autora?' }
            ]
        }
    ]});
});

client.on(Events.InteractionCreate, async i => {
    if (!i.isChatInputCommand()) return;
    if (!i.member.roles.cache.has(AUTHORIZED_ROLE_ID)) return i.reply({ content: 'Brak uprawnień.', ephemeral: true });

    const temat = i.options.getString('temat');
    const wiadomosc = i.options.getString('wiadomosc');
    const embed = new EmbedBuilder().setTitle(temat).setDescription(wiadomosc).setColor(0x0099FF);
    if (i.options.getBoolean('pokaz_autora') !== false) embed.setFooter({ text: `Autor: ${i.user.displayName}` });

    if (i.commandName === 'pv') {
        await i.deferReply({ ephemeral: true });
        const ids = i.options.getString('osoby').match(/\d+/g) || [];
        let s = 0;
        for (const id of ids) {
            try { const u = await client.users.fetch(id); await u.send({ embeds: [embed] }); s++; } catch {}
        }
        await i.editReply(`Wysłano do ${s} osób.`);
    }

    if (i.commandName === 'mess') {
        const k = i.options.getChannel('kanal');
        await k.send({ embeds: [embed] });
        await i.reply({ content: `Wysłano na ${k}`, ephemeral: true });
    }
});

client.login(TOKEN);
