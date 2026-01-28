require('dotenv').config();
const { 
    Client, GatewayIntentBits, Partials, EmbedBuilder, 
    AttachmentBuilder, Collection, Events, REST, Routes 
} = require('discord.js');
const { PDFDocument, rgb, degrees } = require('pdf-lib');
const Database = require('better-sqlite3');
const express = require('express');
const cron = require('node-cron');

// --- KONFIGURACJA ---
const TOKEN = process.env.TOKEN;
const AUTHORIZED_ROLE_ID = '1437194858375680102';
const TIKTOK_CHANNEL_ID = '1437380571180306534';
const VACATION_FORUM_ID = '1452784717802766397';
const VACATION_LOG_CHANNEL_ID = '1462908198074974433';
const WATERMARK_URL = "https://discord.gg/TESTYPL";
const WATERMARK_TEXT = "DISCORD.GG/TESTYPL";

const db = new Database('bot_data.db');
db.prepare('CREATE TABLE IF NOT EXISTS vacations (user_id TEXT, end_date TEXT, reason TEXT, active INTEGER)').run();

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.GuildMessageReactions
    ],
    partials: [Partials.Message, Partials.Channel, Partials.Reaction]
});

// --- KEEP ALIVE ---
const app = express();
app.get('/', (req, res) => res.send('Bot is running!'));
const PORT = process.env.PORT || 8080;
app.listen(PORT, () => console.log(`Serwer HTTP na porcie ${PORT}`));

// --- LOGIKA PDF ---
async function addWatermark(buffer) {
    try {
        const pdfDoc = await PDFDocument.load(buffer);
        const pages = pdfDoc.getPages();
        
        for (const page of pages) {
            const { width, height } = page.getSize();
            
            // Lekkie tło/ramka (uproszczone dla wydajności)
            page.drawRectangle({
                x: 0, y: 0, width: 15, height: height,
                color: rgb(0.9, 0.95, 1.0)
            });

            // Dodawanie znaków wodnych (5 rzędów)
            for (let i = 1; i <= 5; i++) {
                page.drawText(WATERMARK_TEXT, {
                    x: width / 2 - 100,
                    y: (height / 6) * i,
                    size: 35,
                    color: rgb(0, 0, 0),
                    opacity: 0.07,
                    rotate: degrees(i % 2 === 0 ? 15 : -15),
                });
            }
        }
        return await pdfDoc.save();
    } catch (e) {
        console.error("Błąd PDF:", e);
        return buffer;
    }
}

// --- KOMENDY SLASH (Rejestracja) ---
const commands = [
    {
        name: 'pv',
        description: 'Wysyła wiadomość do wielu osób',
        options: [
            { name: 'osoby', type: 3, description: 'ID osób (po spacji)', required: true },
            { name: 'temat', type: 3, description: 'Temat', required: true },
            { name: 'wiadomosc', type: 3, description: 'Treść', required: true },
            { name: 'pokaz_autora', type: 5, description: 'Czy pokazać autora?' }
        ]
    }
    // Tu dodaj resztę komend analogicznie...
];

client.on(Events.InteractionCreate, async interaction => {
    if (!interaction.isChatInputCommand()) return;

    if (!interaction.member.roles.cache.has(AUTHORIZED_ROLE_ID)) {
        return interaction.reply({ content: 'Brak uprawnień.', ephemeral: true });
    }

    if (interaction.commandName === 'pv') {
        await interaction.deferReply({ ephemeral: true });
        const osoby = interaction.options.getString('osoby');
        const temat = interaction.options.getString('temat');
        const wiadomosc = interaction.options.getString('wiadomosc');
        const ids = osoby.match(/\d+/g) || [];

        const embed = new EmbedBuilder()
            .setTitle(temat)
            .setDescription(wiadomosc)
            .setColor(0x0099FF);

        let success = 0;
        for (const id of ids) {
            try {
                const user = await client.users.fetch(id);
                await user.send({ embeds: [embed] });
                success++;
            } catch (e) { console.error(`Błąd wysyłki do ${id}`); }
        }
        await interaction.editReply(`Wysłano do ${success} osób.`);
    }
});

// --- SYSTEM URLOPÓW (Forum & Reakcje) ---
client.on(Events.ThreadCreate, async thread => {
    if (thread.parentId === VACATION_FORUM_ID) {
        const embed = new EmbedBuilder()
            .setTitle("✨ ZGŁOSZENIE URLOPU ✨")
            .setDescription(`Uwaga! Twój urlop został zapisany, ale nie jest aktywny dopóki opiekun nie kliknie ✅.`)
            .setColor(0xFFA500);
        await thread.send({ embeds: [embed] });
    }
});

client.on(Events.MessageReactionAdd, async (reaction, user) => {
    if (user.bot) return;
    if (reaction.emoji.name === '✅') {
        const member = await reaction.message.guild.members.fetch(user.id);
        if (member.roles.cache.has(AUTHORIZED_ROLE_ID)) {
            const thread = reaction.message.channel;
            if (thread.isThread() && thread.parentId === VACATION_FORUM_ID) {
                const messages = await thread.messages.fetch({ limit: 10, after: '0' });
                const firstMsg = messages.last(); 
                
                const dateMatch = firstMsg.content.match(/(\d{2}\.\d{2}\.\d{4})/);
                if (dateMatch) {
                    db.prepare('INSERT INTO vacations (user_id, end_date, reason, active) VALUES (?, ?, ?, 1)')
                      .run(firstMsg.author.id, dateMatch[0], "Zgłoszenie z forum");
                    
                    await thread.send(`✅ Urlop dla <@${firstMsg.author.id}> zatwierdzony do ${dateMatch[0]}!`);
                }
            }
        }
    }
});

// --- AUTOMATYCZNE SPRAWDZANIE (Cron) ---
cron.schedule('0 */12 * * *', () => {
    const today = new Date().toLocaleDateString('pl-PL');
    const expired = db.prepare('SELECT user_id FROM vacations WHERE end_date = ? AND active = 1').all(today);
    
    expired.forEach(async row => {
        const logChan = client.channels.cache.get(VACATION_LOG_CHANNEL_ID);
        if (logChan) logChan.send(`🔔 Koniec urlopu dla <@${row.user_id}>!`);
        db.prepare('UPDATE vacations SET active = 0 WHERE user_id = ?').run(row.user_id);
    });
});

client.once(Events.ClientReady, c => {
    console.log(`✅ Bot online jako ${c.user.tag}`);
    const rest = new REST({ version: '10' }).setToken(TOKEN);
    rest.put(Routes.applicationCommands(c.user.id), { body: commands });
});

client.login(TOKEN);
