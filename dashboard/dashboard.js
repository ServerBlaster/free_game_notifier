// dashboard.js

document.addEventListener("DOMContentLoaded", () => {
  const contentArea = document.getElementById("content");
  const updatedTimestamp = document.getElementById("updated");

  async function fetchAndRenderGames() {
    try {
      // Fetch the flat list of all games
      const response = await fetch("drops.json?cachebust=" + new Date().getTime());
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const allGames = await response.json();

      // Group games by platform
      const groupedByPlatform = allGames.reduce((acc, game) => {
        const platform = game.platform || "Other";
        if (!acc[platform]) {
          acc[platform] = [];
        }
        acc[platform].push(game);
        return acc;
      }, {});

      // Clear any old content
      contentArea.innerHTML = '<p>Loading latest free games...</p>';

      // Set a defined order for platforms
      const platformOrder = ["Epic Games Store", "Prime Gaming", "Steam", "GOG", "Humble", "Ubisoft"];
      const sortedPlatforms = Object.keys(groupedByPlatform).sort((a, b) => {
        const indexA = platformOrder.indexOf(a);
        const indexB = platformOrder.indexOf(b);
        if (indexA === -1) return 1; // Put unknown platforms at the end
        if (indexB === -1) return -1;
        return indexA - indexB;
      });

      if (sortedPlatforms.length === 0) {
        contentArea.innerHTML = '<p>No free games found at the moment. Check back later!</p>';
        return;
      }
      
      contentArea.innerHTML = ''; // Clear "Loading..." message

      // Build a section for each platform
      for (const platform of sortedPlatforms) {
        const games = groupedByPlatform[platform];
        
        const platformSection = document.createElement("section");
        platformSection.className = "platform";

        const title = document.createElement("h2");
        title.className = "platform-title";
        title.textContent = platform;
        platformSection.appendChild(title);

        const cardsContainer = document.createElement("div");
        cardsContainer.className = "cards";

        games.forEach(game => {
          const isClickable = game.link && game.link.startsWith('http');
          const cardTag = isClickable ? 'a' : 'div';
          const card = document.createElement(cardTag);
          card.className = 'card';
          if(isClickable) {
            card.href = game.link;
            card.target = '_blank';
            card.rel = 'noopener noreferrer';
          } else {
            card.classList.add('disabled');
          }

          card.innerHTML = `
            <img src="${game.banner || 'placeholder.png'}" alt="${game.title}" onerror="this.onerror=null;this.src='placeholder.png';">
            <div class="card-content">
              <h4>${game.title}</h4>
              <p>${game.status || 'Free Now'}</p>
              <div class="cta">
                <span class="badge">${isClickable ? 'Claim Now' : (game.cta || 'Unavailable')}</span>
              </div>
            </div>
          `;
          cardsContainer.appendChild(card);
        });

        platformSection.appendChild(cardsContainer);
        contentArea.appendChild(platformSection);
      }

    } catch (error) {
      console.error("Failed to fetch or render games:", error);
      contentArea.innerHTML = `<p style="color: #ff5555;">Could not load game data. Please try refreshing the page.</p>`;
    }
  }

  // Handle subscription form
  const form = document.getElementById("subscribe-form");
  const emailInput = document.getElementById("emailInput");
  const statusMsg = document.getElementById("statusMsg");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = emailInput.value;
    statusMsg.textContent = "Subscribing...";
    statusMsg.style.color = "var(--text-secondary)";

    try {
      // NOTE: Replace with your actual subscription endpoint (e.g., Netlify Function, Cloudflare Worker)
      const endpoint = "https://your-serverless-function-endpoint.netlify.app/subscribe";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email }),
      });

      if (response.ok) {
        statusMsg.textContent = "Success! Check your inbox to confirm.";
        statusMsg.style.color = "var(--glow-cyan)";
        emailInput.value = "";
      } else {
        const result = await response.json();
        throw new Error(result.error || "Subscription failed.");
      }
    } catch (error) {
      statusMsg.textContent = `Error: ${error.message}`;
      statusMsg.style.color = "#ff5555";
    }
  });

  fetchAndRenderGames();
});