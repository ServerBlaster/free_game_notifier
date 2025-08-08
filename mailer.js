const fs = require("fs");
const nodemailer = require("nodemailer");

const isWeekly = process.argv.includes("--weekly");

const drops = JSON.parse(fs.readFileSync("drops.json"));
const subs = JSON.parse(fs.readFileSync("subscribers.json"));

if (!drops.length) {
  console.log("No new drops – skipping email.");
  process.exit();
}
if (!subs.length) {
  console.log("No subscribers – skipping email.");
  process.exit();
}

const transporter = nodemailer.createTransport({
  host: "smtp-relay.brevo.com",
  port: 587,
  auth: {
    user: "your_email@example.com", // Replace with your Brevo verified sender
    pass: process.env.BREVO_KEY,
  },
});

// Email content builder
const buildEmailHTML = (email) => {
  const freshDrops = drops.filter(d => d.status === "Fresh Drop");
  const expiredDrops = drops.filter(d => d.status === "Expired");

  const makeBlock = (title, items) => items.length ? `
    <h3>${title}</h3>
    ${items.map(d => `
      <div style="margin-bottom: 20px; font-family: Arial, sans-serif;">
        <strong style="font-size: 16px;">${d.platform}</strong> – <span style="font-size:15px">${d.title}</span><br/>
        <img src="${d.banner}" width="90%" style="border-radius: 12px; max-width: 500px;" />
      </div>
    `).join("")}
  ` : "";

  const style = `
    <style>
      body { font-family: 'Segoe UI', sans-serif; color: #333; }
      a.unsubscribe { font-size: 12px; color: #999; text-decoration: none; }
    </style>
  `;

  return `
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8">${style}</head>
    <body>
      <h2 style="color: #4CAF50;">🎮 ${isWeekly ? 'This Week\'s Game Recap' : 'Fresh Game Drops'}!</h2>
      ${makeBlock("🟢 Fresh Drops", freshDrops)}
      ${isWeekly ? makeBlock("⚫ Expired This Week", expiredDrops) : ""}
      <hr style="margin: 40px 0;">
      <p style="font-size: 13px;">You’re receiving this because you subscribed on our game alert dashboard.</p>
      <p><a class="unsubscribe" href="https://yourdashboard.vercel.app?email=${encodeURIComponent(email)}&unsubscribe=1">Unsubscribe</a></p>
    </body>
    </html>
  `;
};

// Send all emails
subs.forEach(email => {
  const html = buildEmailHTML(email);
  transporter.sendMail({
    from: '🎮 Game Drop Bot <your_email@example.com>',
    to: email,
    subject: isWeekly ? "🗓️ Weekly Game Drop Recap!" : "🎁 New Free Games Alert!",
    html: html,
  }, (err, info) => {
    if (err) console.error(`❌ ${email}:`, err.message);
    else console.log(`✅ Sent to ${email}`);
  });
});