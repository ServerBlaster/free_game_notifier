// dashboard.js - front-end to show drops.json and handle subscription
document.addEventListener("DOMContentLoaded", () => {
  const content = document.getElementById("content");

  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, s => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    }[s]));
  }

  fetch("../drops.json")
    .then(r => r.json())
    .then(drops => {
      if (!Array.isArray(drops) || drops.length === 0) {
        content.innerHTML = "<p>No drops found.</p>";
        return;
      }

      // Group by platform
      const byPlatform = {};
      drops.forEach(d => {
        const p = d.platform || "Other";
        byPlatform[p] = byPlatform[p] || [];
        byPlatform[p].push(d);
      });

      let html = "";
      Object.keys(byPlatform).sort().forEach(platform => {
        html += `<section class="platform"><h2>${escapeHtml(platform)}</h2><div class="cards">`;

        byPlatform[platform].forEach(item => {
          const title = escapeHtml(item.title);
          const status = escapeHtml(item.status || "");
          const banner = item.banner ? `<img src="${escapeHtml(item.banner)}" alt="" />` : "";
          const link = (item.link || "").trim();
          const hasLink = /^https?:\/\//i.test(link);
          const cta = escapeHtml(item.cta || `Claim directly on the ${platform} website`);

          // If link is real, make the entire card clickable; else disable click
          if (hasLink) {
            html += `
              <a class="card" href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">
                ${banner}
                <h4>${title}</h4>
                <p>${status}</p>
              </a>
            `;
          } else {
            html += `
              <div class="card disabled" tabindex="0" aria-disabled="true">
                ${banner}
                <h4>${title}</h4>
                <p>${status}</p>
                <div class="cta">
                  <span class="badge">🔒 Claim unavailable</span>
                  <span class="cta-text">${cta}</span>
                </div>
              </div>
            `;
          }
        });

        html += "</div></section>";
      });

      content.innerHTML = html;
    })
    .catch(() => {
      content.innerText = "Failed to load drops.json";
    });

  // Simple subscribe handler (adjust to your deploy)
  const form = document.getElementById("subscribe-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("emailInput").value.trim();
      const status = document.getElementById("statusMsg");
      status.innerText = "Subscribing…";
      try {
        const res = await fetch("https://freegamenotifier.vercel.app/api/subscribe", {
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
  }
});