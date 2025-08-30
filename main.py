import os
import json
import requests
from datetime import datetime
import pytz
from bs4 import BeautifulSoup

# NEW: Playwright-based Prime scraper (integrated from fgntest.py)
from playwright.sync_api import sync_playwright

# === CONFIG ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "PLACEHOLDER_BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "PLACEHOLDER_CHANNEL_ID")
DASHBOARD_TEMPLATE = "dashboard/template_dashboard.html"
DASHBOARD_FILE = "dashboard/dashboard.html"
DATA_FILE = "game_data.json"          # grouped by platform (dict)
DROPS_FILE = "drops.json"             # flat list of all items
ARCHIVE_FILE = "monthly_archive.json"
SUMMARY_FILE = "drop_summary.txt"

PRIME_WITH_LINK = "prime_gaming.json"
PRIME_SKIPPED = "prime_gaming_skipped.json"

INDIAN_TZ = pytz.timezone("Asia/Kolkata")
DASHBOARD_LINK = os.getenv("DASHBOARD_LINK", "https://yourusername.github.io/free_game_notifier/dashboard/dashboard.html")

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

def now_str() -> str:
    return datetime.now(INDIAN_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

# ------------------ UTILITIES ------------------

def load_json(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"load_json error for {path}:", e)
    return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def ensure_link_and_cta(item, default_cta=None):
    """
    Guarantees the object has 'link' and optionally a 'cta'.
    If link is not a usable URL, set it to "" and keep/display cta text.
    """
    link = (item.get("link") or "").strip()
    if link.startswith("http://") or link.startswith("https://"):
        item["link"] = link
    else:
        item["link"] = ""
        if default_cta and not item.get("cta"):
            item["cta"] = default_cta
    return item

def compare_and_build(old: dict, new: dict):
    """
    Build human-readable change log & maintain monthly archive.
    Now detects Expired status changes as well.
    """
    changes = []
    monthly = load_json(ARCHIVE_FILE, {})
    cur_month = datetime.now(INDIAN_TZ).strftime("%Y-%m")
    if cur_month not in monthly:
        monthly[cur_month] = []

    for src, new_items in new.items():
        old_items = old.get(src, [])

        # Map by title for easy lookups
        old_map = {i["title"]: i for i in old_items}
        new_map = {i["title"]: i for i in new_items}

        old_titles = set(old_map.keys())
        new_titles = set(new_map.keys())

        # Titles completely gone
        expired_titles = old_titles - new_titles
        for g in expired_titles:
            changes.append(f"🔻 Expired: <b>{src}</b> – {g}")

        # New titles
        fresh_titles = new_titles - old_titles
        for g in fresh_titles:
            changes.append(f"🟢 New Freebie: <b>{src}</b> – {g}")
            if g not in monthly[cur_month]:
                monthly[cur_month].append(g)

        # Titles that still exist but changed status (e.g. Fresh → Expired)
        common_titles = old_titles & new_titles
        for g in common_titles:
            old_status = old_map[g].get("status", "")
            new_status = new_map[g].get("status", "")
            if old_status != new_status:
                changes.append(f"🔄 Status change: <b>{src}</b> – {g} ({old_status} → {new_status})")

    save_json(ARCHIVE_FILE, monthly)
    return changes

def build_dashboard(grouped: dict):
    now = datetime.now(INDIAN_TZ).strftime("%Y-%m-%d %H:%M %Z")

    # Simple fallback HTML if template missing
    if not os.path.exists(DASHBOARD_TEMPLATE):
        blocks = ""
        for src, items in grouped.items():
            blocks += f"<h2>{src}</h2><ul>"
            for it in items:
                img = f"<img src='{it.get('banner','')}' alt='' style='max-width:220px'/>" if it.get("banner") else ""
                link = it.get("link") or ""
                title = it.get("title", "")
                status = it.get("status", "")
                if link:
                    blocks += f"<li>{img}<a href='{link}' target='_blank'><strong>{title}</strong></a> — {status}</li>"
                else:
                    cta = it.get("cta") or f"Claim directly on the {src} website"
                    blocks += f"<li>{img}<strong>{title}</strong> — {status} <em>({cta})</em></li>"
            blocks += "</ul>"
        with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
            f.write(f"<html><body><h1>Free Game Tracker</h1><p>{now}</p>{blocks}</body></html>")
        return

    tpl = open(DASHBOARD_TEMPLATE, "r", encoding="utf-8").read()
    # The new dashboard front-end (dashboard.js) will actually consume drops.json,
    # but we still stamp an updated time in the static HTML.
    html = tpl.replace("{{TIMESTAMP}}", now).replace("{{GAME_BLOCKS}}", "")
    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)

def send_telegram(msg_html: str):
    if BOT_TOKEN.startswith("PLACEHOLDER"):
        print("Telegram not configured. Skipping send.")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": msg_html,
        "parse_mode": "HTML",                 # ✅ switched to HTML
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

# ------------------ SCRAPERS ------------------

def get_egs_free():
    """
    Epic Games Store free weekly games via official API.
    Ensure link consistency: if productSlug present, link to store page.
    """
    out = []
    try:
        url = (
            "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
            "?locale=en-US&country=IN&allowCountries=IN"
        )
        r = requests.get(url, headers=HEADERS, timeout=20).json()
        elements = r.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        for g in elements:
            price = g.get("price", {}).get("totalPrice", {}).get("discountPrice", 1)
            if price == 0:
                title = (g.get("title") or g.get("productSlug") or "Unknown") or "Unknown"
                banner = ""
                if g.get("keyImages"):
                    banner = (g["keyImages"][0].get("url") or "").strip()
                slug = (g.get("productSlug") or "").strip().strip("/")
                link = f"https://store.epicgames.com/p/{slug}" if slug else ""
                item = {
                    "platform": "Epic Games Store",
                    "title": title,
                    "status": "Fresh Drop",
                    "banner": banner,
                    "link": link
                }
                out.append(ensure_link_and_cta(item, "Claim directly on the Epic Games Store"))
    except Exception as e:
        print("EGS error:", e)
    return out

def get_gog_free():
    out = []
    try:
        html = requests.get("https://www.gog.com/games?price=free", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("a.product-tile")
        for c in cards[:12]:
            title = (c.get("title") or "").strip()
            if not title:
                pt = c.select_one(".product-title")
                title = pt.get_text(strip=True) if pt else ""
            img = c.select_one("img")
            banner = (img.get("src") if img and img.has_attr("src") else "") or ""
            href = (c.get("href") or "").strip()
            link = f"https://www.gog.com{href}" if href and href.startswith("/") else href
            item = {
                "platform": "GOG",
                "title": title,
                "status": "Fresh Drop",
                "banner": banner,
                "link": link
            }
            if title:
                out.append(ensure_link_and_cta(item, "Claim directly on GOG"))
    except Exception as e:
        print("GOG error:", e)
    return out

def get_steam_free():
    """
    Steam free 100% off (SteamDB page). Often no direct claim link; keep card non-clickable.
    """
    out = []
    try:
        html = requests.get("https://steamdb.info/sales/?min_discount=100", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.table-products tbody tr")[:10]
        for r in rows:
            name_tag = r.select_one("td:nth-child(2)")
            title = name_tag.get_text(strip=True) if name_tag else ""
            item = {
                "platform": "Steam",
                "title": title,
                "status": "Fresh Drop",
                "banner": "",
                "link": ""  # keep non-clickable; CTA shown
            }
            if title:
                out.append(ensure_link_and_cta(item, "Claim directly on Steam"))
    except Exception as e:
        print("Steam error:", e)
    return out

def get_humble_free():
    out = []
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

            # Try to find a link
            a = card.select_one("a[href]")
            href = (a.get("href") if a else "") or ""
            if href and href.startswith("/"):
                link = f"https://www.humblebundle.com{href}"
            else:
                link = href

            # Expiry/status
            expiry_elem = card.select_one(".promo-timer, .countdown")
            expiry = expiry_elem.get_text(strip=True) if expiry_elem else None

            status = "Fresh Drop"
            if expiry:
                status += f" (Expires {expiry})"

            if title:
                item = {
                    "platform": "Humble",
                    "title": title,
                    "status": status,
                    "banner": banner,
                    "link": link
                }
                out.append(ensure_link_and_cta(item, "Claim directly on Humble"))
    except Exception as e:
        print("Humble scrape error:", e)
    return out

def get_ubisoft():
    out = []
    try:
        html = requests.get("https://store.ubisoft.com/us/free-games/", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        tiles = soup.select("a.product-tile, a[href*='/game/']")
        for t in tiles[:10]:
            title = t.get("title") or ""
            if not title:
                ttag = t.select_one(".product-tile-title")
                title = ttag.get_text(strip=True) if ttag else ""
            href = (t.get("href") or "").strip()
            if href and href.startswith("/"):
                link = f"https://store.ubisoft.com{href}"
            else:
                link = href
            item = {
                "platform": "Ubisoft",
                "title": title,
                "status": "Fresh Drop",
                "banner": "",
                "link": link
            }
            if title:
                out.append(ensure_link_and_cta(item, "Claim directly on Ubisoft Store"))
    except Exception as e:
        print("Ubisoft error:", e)
    return out

# ---------- PRIME GAMING (Playwright) ----------

def get_prime_free():
    """
    Playwright scraper for Prime Gaming.
    Returns (with_link_list, skipped_list).
    Keeps expired offers with status="Expired" so they can
    trigger Telegram 'Expired' messages on the next run.
    """
    results = []
    skipped_entries = []
    html = ""

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()
            page.goto("https://gaming.amazon.com/home", timeout=60000)
            page.wait_for_timeout(5000)  # let dynamic stuff load
            html = page.content()
            # Save raw for debugging
            with open("prime_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
                f.flush()
                os.fsync(f.fileno())
            browser.close()
    except Exception as e:
        print("Playwright Prime error:", e)

    if not html:
        # Fallback if playwright failed
        try:
            html = requests.get("https://gaming.amazon.com/home", headers=HEADERS, timeout=20).text
        except Exception as e:
            print("Prime fallback fetch error:", e)
            html = ""

    if html:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("div[data-a-target='item-card']")
        for card in cards:
            title_tag = card.select_one("h3")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)

            # Footer / expiry status
            footer_text = card.select_one(".item-card-details__footer")
            status = "Fresh Drop"
            expired_flag = False
            if footer_text:
                txt = footer_text.get_text(" ", strip=True)
                if "Ends" in txt:
                    status = txt
                if "Ended" in txt or "expired" in txt.lower():
                    status = "Expired"
                    expired_flag = True

            # Primary claim link
            claim_link_tag = card.select_one("a[data-a-target='FGWPOffer']")
            # Fallback "learn more" link
            fallback_link_tag = card.select_one("a[data-a-target='learn-more-card']")

            link = ""
            if claim_link_tag and claim_link_tag.get("href"):
                link = "https://gaming.amazon.com" + claim_link_tag["href"]
            elif fallback_link_tag and fallback_link_tag.get("href"):
                link = "https://gaming.amazon.com" + fallback_link_tag["href"]

            entry = {
                "platform": "Prime Gaming",
                "title": title,
                "link": link,
                "status": status,
                "banner": ""
            }

            if expired_flag:
                # Expired: keep, but non-clickable
                entry["link"] = ""
                entry = ensure_link_and_cta(entry, "Expired – no longer claimable")
                skipped_entries.append(entry)
            elif link:
                results.append(entry)
            else:
                # Active but no direct link
                entry = ensure_link_and_cta(entry, "Claim directly on the Prime Gaming website")
                skipped_entries.append(entry)

    # Deduplicate by title
    def dedupe(data):
        unique = {}
        for r in data:
            key = r["title"].lower()
            if key not in unique:
                unique[key] = r
        return list(unique.values())

    results = dedupe(results)
    skipped_entries = dedupe(skipped_entries)

    # Save the two explicit files
    save_json(PRIME_WITH_LINK, results)
    save_json(PRIME_SKIPPED, skipped_entries)

    print(
        f"Prime Gaming total={len(results)+len(skipped_entries)} "
        f"(with links={len(results)}, skipped={len(skipped_entries)})"
    )
    return results, skipped_entries

# ------------------ MAIN ------------------

def main():
    old_grouped = load_json(DATA_FILE, {})  # dict grouped by platform

    # Scrape all sources
    egs = get_egs_free()
    gog = get_gog_free()
    steam = get_steam_free()
    humble = get_humble_free()
    ubi = get_ubisoft()
    prime_with_link, prime_skipped = get_prime_free()

    # Group under platform names
    grouped = {}

    def add_items(items):
        for it in items:
            src = it.get("platform") or "Other"
            grouped.setdefault(src, []).append(it)

    add_items(egs)
    add_items(gog)
    add_items(steam)
    add_items(humble)
    add_items(ubi)
    add_items(prime_with_link)
    add_items(prime_skipped)

    # Flat list for drops.json
    flat = []
    for v in grouped.values():
        flat.extend(v)

    # Save both required outputs
    save_json(DROPS_FILE, flat)      # used by dashboard.js
    save_json(DATA_FILE, grouped)    # grouped snapshot

    # Build change summary (HTML)
    changes = compare_and_build(old_grouped, grouped)
    build_dashboard(grouped)

    if changes:
        # Compose HTML message for Telegram
        msg = (
            "🗞 <b>Free Game Update</b> 🗞<br/><br/>"
            + "<br/>".join(changes)
            + f"<br/><br/>🌐 <a href=\"{DASHBOARD_LINK}\">Dashboard</a>"
        )
        # Write a text summary too (we'll keep HTML tags; mailer can render HTML)
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
        send_telegram(msg)
    else:
        print("No changes at", now_str())

if __name__ == "__main__":
    main()