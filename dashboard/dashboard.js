// dashboard.js - simple front-end to show drops.json and post subscription requests
document.addEventListener("DOMContentLoaded", () => {
  fetch("../drops.json").then(r => r.json()).then(drops => {
    const container = document.getElementById("content");
    if (!drops || !drops.length) {
      container.innerHTML = "<p>No drops found.</p>";
      return;
    }
    // build grouped view
    const byPlatform = {};
    drops.forEach(d => {
      byPlatform[d.platform] = byPlatform[d.platform] || [];
      byPlatform[d.platform].push(d);
    });
    let html = "";
    for (const p of Object.keys(byPlatform)) {
      html += `<section class="platform"><h2>${p}</h2><div class="cards">`;
      byPlatform[p].forEach(item => {
        html += `<div class="card">
                   ${item.banner ? `<img src="${item.banner}" alt="" />` : ""}
                   <h4>${item.title}</h4>
                   <p>${item.status}</p>
                 </div>`;
      });
      html += "</div></section>";
    }
    container.innerHTML = html;
  }).catch(() => { document.getElementById("content").innerText = "Failed to load drops.json"; });

  const form = document.getElementById("subscribe-form");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("emailInput").value.trim();
    const status = document.getElementById("statusMsg");
    status.innerText = "Subscribing…";
    // ======= Option A: serverless endpoint at /api/subscribe (see STEP 14) =======
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, action: "subscribe" })
      });
      const j = await res.json();
      status.innerText = j.message || "Subscribed (check email)";
    } catch (err) {
      status.innerText = "Subscribe failed (server not configured)";
    }
  });
});