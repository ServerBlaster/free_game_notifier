// mailer.js
const fs = require("fs");
const path = require("path");
const nodemailer = require("nodemailer");

const FROM_NAME = process.env.FROM_NAME || "Free Game Bot";
const GMAIL_USER = process.env.GMAIL_USER;
const GMAIL_APP_PASSWORD = process.env.GMAIL_APP_PASSWORD;
const DASHBOARD_LINK = process.env.DASHBOARD_LINK || "https://yourusername.github.io/free_game_notifier/dashboard/dashboard.html";
const MAX_SUBS = parseInt(process.env.MAX_SUBS || "250", 10);

if (!GMAIL_USER || !GMAIL_APP_PASSWORD) {
  console.error("ERROR: Set GMAIL_USER and GMAIL_APP_PASSWORD in env.");
  process.exit(1);
}

const summaryPath = path.join(__dirname, "drop_summary.txt");
if (!fs.existsSync(summaryPath) || !fs.readFileSync(summaryPath, "utf-8").trim()) {
  console.log("No drop_summary.txt or it's empty. Nothing to send.");
  process.exit(0);
}
const summaryText = fs.readFileSync(summaryPath, "utf-8").trim();

let subs = [];
try {
  const subsRaw = JSON.parse(fs.readFileSync(path.join(__dirname, "subscribers.json"), "utf-8"));
  subs = Array.isArray(subsRaw.emails) ? subsRaw.emails : [];
} catch (e) {
  console.error("Error reading subscribers.json:", e.message);
  process.exit(1);
}

if (!subs.length) {
  console.log("No subscribers found in subscribers.json");
  process.exit(0);
}
if (subs.length > MAX_SUBS) {
  console.log(`Limiting recipients to MAX_SUBS=${MAX_SUBS}`);
  subs = subs.slice(0, MAX_SUBS);
}

const transporter = nodemailer.createTransport({
  host: "smtp.gmail.com",
  port: 587,
  secure: false,
  auth: { user: GMAIL_USER, pass: GMAIL_APP_PASSWORD }
});

async function sendAll() {
  for (const to of subs) {
    try {
      await transporter.sendMail({
        from: `"${FROM_NAME}" <${GMAIL_USER}>`,
        to,
        subject: process.env.EMAIL_SUBJECT || "🎁 New Free Games Alert!",
        text: summaryText.replace(/<br\/?>/g, "\n").replace(/<[^>]+>/g, "") + `\n\nView on dashboard: ${DASHBOARD_LINK}`,
        html: `<div style="font-family:Segoe UI,Arial;padding:8px">
                 ${summaryText}
                 <hr/>
                 <p><a href="${DASHBOARD_LINK}">View Dashboard</a></p>
               </div>`
      });
      console.log(`✅ Sent to ${to}`);
    } catch (err) {
      console.error(`❌ Failed ${to}:`, err.message);
    }
  }
  console.log("Done sending.");
}

sendAll().catch(e => console.error(e));