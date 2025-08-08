const dropContainer = document.getElementById("drop-container");
const slider = document.getElementById("theme-slider");
const toggle = document.getElementById("dark-toggle");
const email = new URLSearchParams(window.location.search).get("email");
const unsub = new URLSearchParams(window.location.search).get("unsubscribe");

fetch("../drops.json")
  .then(res => res.json())
  .then(drops => {
    dropContainer.innerHTML = drops.map(d => `
      <div class="card">
        <img src="${d.banner}" />
        <h3>${d.platform}</h3>
        <p>${d.title}</p>
      </div>
    `).join('');
  });

// THEMING
function applyTheme(index) {
  document.body.className = `theme${index}`;
}
slider.addEventListener("input", () => applyTheme(slider.value));
toggle.addEventListener("change", () => document.body.classList.toggle("dark", toggle.checked));

// EMAIL SUB/UNSUB
const form = document.getElementById("subscribe-form");
const status = document.getElementById("status");

if (unsub && email) {
  fetch("../subscribers.json")
    .then(res => res.json())
    .then(data => {
      const updated = data.filter(e => e !== email);
      return fetch("/save_subs", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      });
    })
    .then(() => status.textContent = "Unsubscribed successfully!")
    .catch(() => status.textContent = "Unsubscribe failed.");
}

form.addEventListener("submit", e => {
  e.preventDefault();
  const val = document.getElementById("email").value;
  fetch("../subscribers.json")
    .then(res => res.json())
    .then(data => {
      if (data.includes(val)) {
        status.textContent = "Already subscribed.";
        return;
      }
      if (data.length >= 300) {
        status.textContent = "Mailing list full.";
        return;
      }
      data.push(val);
      return fetch("/save_subs", {
        method: "POST",
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      }).then(() => status.textContent = "Subscribed!");
    });
});