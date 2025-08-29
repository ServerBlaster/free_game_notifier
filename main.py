import requests, json, os
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
import feedparser

# === CONFIG ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PLACEHOLDER_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "PLACEHOLDER_CHANNEL_ID")
DASHBOARD_TEMPLATE = "dashboard/template_dashboard.html"
DASHBOARD_FILE = "dashboard/dashboard.html"
DATA_FILE = "game_data.json"
DROPS_FILE = "drops.json"
ARCHIVE_FILE = "monthly_archive.json"
SUMMARY_FILE = "drop_summary.txt"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.reddit.com/",
    "Connection": "keep-alive",
}
INDIAN_TZ = pytz.timezone("Asia/Kolkata")
DASHBOARD_LINK = os.getenv("DASHBOARD_LINK", "https://yourusername.github.io/free_game_notifier/dashboard/dashboard.html")

def now_str() -> str:
    return datetime.now(INDIAN_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

# ------------------ SCRAPERS ------------------

def get_egs_free():
    try:
        url = (
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
            "?locale=en-US&country=IN&allowCountries=IN"
        )
        r = requests.get(url, headers=HEADERS, timeout=20).json()
        elems = r.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        res = []
        for g in elems:
            price = g.get("price", {}).get("totalPrice", {}).get("discountPrice", 1)
            if price == 0:
                title_raw = g.get("title") or g.get("productSlug") or "Unknown"
                title = str(title_raw) if title_raw else ""
                banner = ""
                if g.get("keyImages"):
                    banner = str(g["keyImages"][0].get("url", "")) if g["keyImages"][0].get("url") else ""
                res.append({"platform": "EGS", "title": title, "status": "Fresh Drop", "banner": banner})
        return res
    except Exception as e:
        print("EGS error:", e)
        return []

def get_gog_free():
    try:
        html = requests.get("https://www.gog.com/games?price=free", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a.product-tile")
        out = []
        for c in cards[:8]:
            title_val = c.get("title")
            title_tag = str(title_val) if isinstance(title_val, str) else ""
            if not title_tag:
                pt_elem = c.select_one(".product-title")
                title_tag = pt_elem.get_text(strip=True) if pt_elem else ""
            img = c.select_one("img")
            banner = img.get("src", "") if img and img.has_attr("src") else ""
            if title_tag:
                out.append({"platform": "GOG", "title": title_tag, "status": "Fresh Drop", "banner": str(banner)})
        return out
    except Exception as e:
        print("GOG error:", e)
        return []

def get_steam_free():
    try:
        html = requests.get("https://steamdb.info/sales/?min_discount=100", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.table-products tbody tr")[:6]
        out = []
        for r in rows:
            name_tag = r.select_one("td:nth-child(2)")
            title = name_tag.get_text(strip=True) if name_tag else ""
            if title:
                out.append({"platform": "Steam", "title": title, "status": "Fresh Drop", "banner": ""})
        return out
    except Exception as e:
        print("Steam error:", e)
        return []

def get_humble_free():
    results = []
    try:
        url = "https://www.humblebundle.com/store/search?sort=discount&filter=onsale"
        html = requests.get(url, headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")

        for card in soup.select(".entity-block-container"):
            discount_elem = card.select_one(".discount-amount")
            discount_text = discount_elem.get_text(strip=True) if discount_elem else ""
            
            if discount_text != "-100%":
                continue

            title_elem = card.select_one(".entity-title")
            title = title_elem.get_text(strip=True) if title_elem else ""

            img_elem = card.select_one("img")
            banner = img_elem.get("src") if img_elem and img_elem.has_attr("src") else ""

            expiry_elem = card.select_one(".promo-timer, .countdown")
            expiry = expiry_elem.get_text(strip=True) if expiry_elem else None

            if title:
                status = "Fresh Drop"
                if expiry:
                    status += f" (Expires {expiry})"
                results.append({
                    "platform": "Humble",
                    "title": title,
                    "status": status,
                    "banner": banner
                })

    except Exception as e:
        print("Humble scrape error:", e)
    return results

def get_ubisoft():
    try:
        html = requests.get("https://store.ubisoft.com/us/free-games/", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        titles = [t.get_text(strip=True) for t in soup.select(".product-tile-title") if t]
        return [{"platform": "Ubisoft", "title": str(t), "status": "Fresh Drop", "banner": ""} for t in titles[:6]]
    except Exception as e:
        print("Ubisoft error:", e)
        return []


def get_prime_free():
    results = []
    try:
        url = "https://gaming.amazon.com/home"
        html = requests.get(url, headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")

        offer_cards = soup.select(".item-card, .offer, .item-content")

        for card in offer_cards:
            title_elem = card.select_one("h3, .item-title, span")
            title = title_elem.get_text(strip=True) if title_elem else ""

            img_elem = card.select_one("img")
            banner = img_elem.get("src") if img_elem and img_elem.has_attr("src") else ""

            if title:
                results.append({
                    "platform": "Prime",
                    "title": title,
                    "status": "Fresh Drop",
                    "banner": banner
                })
    except Exception as e:
        print("Prime Gaming scrape error:", e)

    # Deduplicate
    unique_titles = set()
    unique_results = []
    for item in results:
        if item["title"].lower() not in unique_titles:
            unique_titles.add(item["title"].lower())
            unique_results.append(item)

    return unique_results

# ------------------ UTILITIES ------------------

def load_json(path: str, default):
    try:
        if os.path.exists(path):
            return json.load(open(path, "r", encoding="utf-8"))
    except Exception as e:
        print(f"load_json error for {path}:", e)
    return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def compare_and_build(old: dict, new: dict):
    changes = []
    monthly = load_json(ARCHIVE_FILE, {})
    cur_month = datetime.now(INDIAN_TZ).strftime("%Y-%m")
    if cur_month not in monthly:
        monthly[cur_month] = []
    for src, items in new.items():
        old_set = set([i["title"] for i in old.get(src, [])])
        new_set = set([i["title"] for i in items])
        expired = old_set - new_set
        fresh = new_set - old_set
        for g in expired:
            changes.append(f"🔻 Expired: `{src}` – {g}")
        for g in fresh:
            changes.append(f"🟢 New Freebie: `{src}` – {g}")
            if g not in monthly[cur_month]:
                monthly[cur_month].append(g)
    save_json(ARCHIVE_FILE, monthly)
    return changes

def build_dashboard(all_drops: dict):
    now = datetime.now(INDIAN_TZ).strftime("%Y-%m-%d %H:%M %Z")
    blocks = ""
    for src, items in all_drops.items():
        blocks += f"<h2>{src}</h2><ul>"
        for it in items:
            img = f"<img src='{it.get('banner','')}' alt='' style='max-width:220px'/>" if it.get("banner") else ""
            blocks += f"<li>{img}<strong>{it.get('title')}</strong> — {it.get('status')}</li>"
        blocks += "</ul>"
    if os.path.exists(DASHBOARD_TEMPLATE):
        tpl = open(DASHBOARD_TEMPLATE, "r", encoding="utf-8").read()
        tpl = tpl.replace("{{TIMESTAMP}}", now).replace("{{GAME_BLOCKS}}", blocks)
        os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
        open(DASHBOARD_FILE, "w", encoding="utf-8").write(tpl)
    else:
        open(DASHBOARD_FILE, "w", encoding="utf-8").write(
            f"<html><body><h1>Free Game Tracker</h1><p>{now}</p>{blocks}</body></html>"
        )

def send_telegram(msg: str):
    if BOT_TOKEN.startswith("PLACEHOLDER"):
        print("Telegram not configured. Skipping send.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

# ------------------ MAIN ------------------

def main():
    old = load_json(DATA_FILE, {})
    new = {
        "EGS": get_egs_free(),
        "GOG": get_gog_free(),
        "Steam": get_steam_free(),
        "Humble": get_humble_free(),
        "Ubisoft": get_ubisoft(),
        "Prime": get_prime_free()
    }
    save_json(DROPS_FILE, [item for lst in new.values() for item in lst])
    changes = compare_and_build(old, new)
    build_dashboard(new)
    if changes:
        msg = "🗞 *Free Game Update* 🗞\n\n" + "\n".join(changes) + f"\n\n🌐 Dashboard: {DASHBOARD_LINK}"
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
        send_telegram(msg)
        save_json(DATA_FILE, new)
    else:
        print("No changes at", now_str())

if __name__ == "__main__":
    main()