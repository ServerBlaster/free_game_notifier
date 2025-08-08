import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import pytz
import logging
from telegram import Bot

# --- CONFIG ---
TELEGRAM_BOT_TOKEN = "PLACEHOLDER_BOT_TOKEN"
TELEGRAM_CHANNEL_ID = "PLACEHOLDER_CHANNEL_ID"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
INDIAN_TZ = pytz.timezone("Asia/Kolkata")

# --- HELPERS ---
def now_str():
    return datetime.now(INDIAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

def fetch_egs():
    url = "https://store.epicgames.com/en-US/free-games"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    cards = soup.select("a[data-component='CardGridDesktopBase']")
    drops = []
    for card in cards:
        title = card.select_one("span[data-testid='offer-title-info-title']").text.strip()
        image = card.select_one("img")["src"]
        drops.append({
            "platform": "EGS",
            "title": title,
            "status": "Fresh Drop",
            "banner": image
        })
    return drops

def fetch_gog():
    url = "https://www.gog.com/games?price=free"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    drops = []
    for card in soup.select("product-tile"):
        title = card.get("title") or "GOG Free Game"
        image = card.get("image") or "https://cdn.cloudflare.steamstatic.com/steam/apps/1888930/header.jpg"
        drops.append({
            "platform": "GOG",
            "title": title.strip(),
            "status": "Fresh Drop",
            "banner": image
        })
    return drops

def fetch_steam():
    url = "https://steamdb.info/upcoming/free/"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    drops = []
    for row in soup.select("tr.app"):
        cols = row.select("td")
        if not cols or len(cols) < 3:
            continue
        title = cols[2].text.strip()
        appid = row.get("data-appid", "").strip()
        if appid:
            banner = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"
            drops.append({
                "platform": "Steam",
                "title": title,
                "status": "Fresh Drop",
                "banner": banner
            })
    return drops

def fetch_humble_from_reddit():
    url = "https://www.reddit.com/r/GameDeals/new.json?limit=10"
    headers = {"User-agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers).json()
    drops = []
    for post in res["data"]["children"]:
        title = post["data"]["title"]
        if "humble" in title.lower() and "free" in title.lower():
            drops.append({
                "platform": "Humble",
                "title": title.strip(),
                "status": "Fresh Drop",
                "banner": "https://humblebundle.imgix.net/static/humble_freebies.jpg"
            })
    return drops

def fetch_ubisoft():
    url = "https://register.ubisoft.com"
    soup = BeautifulSoup(requests.get(url, headers=HEADERS).text, "html.parser")
    drops = []
    for btn in soup.select("div.cta a"):
        title = btn.text.strip()
        href = btn.get("href", "")
        if "register.ubisoft.com" in href:
            drops.append({
                "platform": "Ubisoft",
                "title": title or "Ubisoft Freebie",
                "status": "Fresh Drop",
                "banner": "https://upload.wikimedia.org/wikipedia/commons/5/58/Ubisoft_logo.svg"
            })
    return drops

def fetch_prime():
    try:
        res = requests.get("https://gaming.amazon.com/home", headers=HEADERS)
        if "Prime Gaming" in res.text:
            return [{
                "platform": "Prime Gaming",
                "title": "🔐 Login to view freebies",
                "status": "Fresh Drop",
                "banner": "https://m.media-amazon.com/images/G/01/gaming/primegaming/pg-logo._CB1560279399_.png"
            }]
    except Exception as e:
        print("Prime Gaming failed:", e)
    return []

def send_telegram(summary):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    msg = f"🎮 *Free Game Drops ({now_str()})*\n\n{summary}\n\n📊 [Dashboard](https://yourdashboard.com)"
    bot.send_message(chat_id=TELEGRAM_CHANNEL_ID, text=msg, parse_mode="Markdown", disable_web_page_preview=False)

def generate_summary(drops):
    lines = []
    for d in drops:
        symbol = "🟢" if d["status"].lower() == "fresh drop" else "⚫"
        lines.append(f"{symbol} {d['platform']} – {d['title']}")
    return "\n".join(lines)

# --- MAIN ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    all_drops = []

    try:
        all_drops += fetch_egs()
        all_drops += fetch_gog()
        all_drops += fetch_steam()
        all_drops += fetch_humble_from_reddit()
        all_drops += fetch_ubisoft()
        all_drops += fetch_prime()
    except Exception as e:
        logging.error(f"Error during fetching: {e}")

    # Save to JSON
    with open("drops.json", "w", encoding="utf-8") as f:
        json.dump(all_drops, f, indent=2)

    # Save plain text summary
    summary = generate_summary(all_drops)
    with open("drop_summary.txt", "w", encoding="utf-8") as f:
        f.write(summary)

    # Send Telegram notification (only if fresh drops)
    if any(d["status"] == "Fresh Drop" for d in all_drops):
        send_telegram(summary)
