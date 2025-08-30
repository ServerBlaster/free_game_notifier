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
    Only cares about new and expired titles.
    Ignores status changes because dashboard only tracks fresh drops.
    """
    changes = []
    monthly = load_json(ARCHIVE_FILE, {})
    cur_month = datetime.now(INDIAN_TZ).strftime("%Y-%m")
    if cur_month not in monthly:
        monthly[cur_month] = []

    for src, new_items in new.items():
        old_items = old.get(src, [])

        old_titles = {i["title"] for i in old_items}
        new_titles = {i["title"] for i in new_items}

        # Titles completely gone → mark as expired
        expired_titles = old_titles - new_titles
        for g in expired_titles:
            changes.append(f"🔻 Expired: <b>{src}</b> – {g}")

        # New titles → mark as fresh drop
        fresh_titles = new_titles - old_titles
        for g in fresh_titles:
            changes.append(f"🟢 New Freebie: <b>{src}</b> – {g}")
            if g not in monthly[cur_month]:
                monthly[cur_month].append(g)

        # Common titles → ignore status flips

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
                    cta = it.get("cta") or f"Claim on the {src} website"
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

# In main.py, replace the old get_egs_free function

def get_egs_free():
    """
    Epic Games Store free weekly games via official API.
    UPDATED to be more robust at finding the product slug.
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
            # We only care about currently free games
            if price != 0:
                continue

            title = g.get("title", "Unknown Game")
            banner = ""
            if g.get("keyImages"):
                # Find the 'OfferImageWide' for a better banner if available
                for img in g["keyImages"]:
                    if img.get("type") == "OfferImageWide":
                        banner = img.get("url", "")
                        break
                if not banner:
                    banner = g["keyImages"][0].get("url", "")

            # --- NEW ROBUST SLUG FINDING LOGIC ---
            slug = g.get("productSlug") or g.get("urlSlug")
            
            # Fallback 1: Check for a slug in offerMappings
            if not slug and g.get("offerMappings"):
                for mapping in g["offerMappings"]:
                    if mapping.get("pageSlug"):
                        slug = mapping["pageSlug"]
                        break
            
            # Fallback 2: Check for a slug in catalogNs.mappings (less common)
            if not slug and g.get("catalogNs", {}).get("mappings"):
                 for mapping in g["catalogNs"]["mappings"]:
                    if mapping.get("pageSlug"):
                        slug = mapping["pageSlug"]
                        break

            # Clean the final slug and build the link
            slug = (slug or "").strip().replace("/home", "")
            link = f"https://store.epicgames.com/p/{slug}" if slug else ""
            
            item = {
                "platform": "Epic Games Store",
                "title": title,
                "status": "Fresh Drop",
                "banner": banner,
                "link": link
            }
            out.append(ensure_link_and_cta(item, "Claim on Epic Games Store"))

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

# In main.py, replace the old get_steam_free function

# In main.py, replace the existing get_steam_free function

def get_steam_free():
    """
    Steam free 100% off (SteamDB page).
    UPDATED to be more robust at finding the store page link.
    """
    out = []
    try:
        html = requests.get("https://steamdb.info/sales/?min_discount=100", headers=HEADERS, timeout=20).text
        soup = BeautifulSoup(html, "html.parser")
        # Select rows that are specifically for an app/game to avoid bundles
        rows = soup.select("tr.app[data-appid]")
        for r in rows[:10]:
            title_cell = r.select_one("td:nth-of-type(3)") # Title is usually the 3rd cell
            if not title_cell:
                continue

            title = title_cell.get_text(strip=True)
            link_tag = title_cell.find("a", href=True)
            link = ""

            # Ensure the link is a valid Steam store URL
            if link_tag and 'store.steampowered.com' in link_tag['href']:
                link = link_tag['href']

            if title:
                item = {
                    "platform": "Steam",
                    "title": title,
                    "status": "Fresh Drop",
                    "banner": "",
                    "link": link
                }
                # The ensure_link_and_cta will correctly handle if the link is empty
                out.append(ensure_link_and_cta(item, "Claim on Steam"))

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
    - with_link_list: claimable entries with working links
    - skipped_list: active entries without links (shown with CTA on dashboard)
    - expired entries are dropped completely (not returned, not saved)
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
            browser.close()
    except Exception as e:
        print("Playwright Prime error:", e)

    if not html:
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
            
            banner = ""
            img_tag = card.select_one("img.item-card-image__image")
            if img_tag and img_tag.has_attr("src"):
                banner = img_tag["src"]

            # Footer / expiry
            footer_text = card.select_one(".item-card-details__footer")
            status = "Fresh Drop"
            expired_flag = False
            if footer_text:
                txt = footer_text.get_text(" ", strip=True)
                if "Ends" in txt:
                    status = txt
                if "Ended" in txt or "expired" in txt.lower():
                    expired_flag = True

            if expired_flag:
                continue  # 🚫 drop expired completely

            # Primary claim link
            claim_link_tag = card.select_one("a[data-a-target='FGWPOffer']")
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
                "banner": banner
            }

            if link:
                results.append(entry)
            else:
                entry = ensure_link_and_cta(entry, "Claim directly on Prime Gaming website")
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

    # Save only active items (expired ones dropped)
    save_json(PRIME_WITH_LINK, results)
    save_json(PRIME_SKIPPED, skipped_entries)

    print(
        f"Prime Gaming active total={len(results)+len(skipped_entries)} "
        f"(with links={len(results)}, skipped={len(skipped_entries)})"
    )
    return results, skipped_entries

# ------------------ MAIN ------------------

def main():
    # --- helpers ---
    def is_expired(status: str) -> bool:
        s = (status or "").strip().lower()
        # catch common variants Amazon uses
        return any(k in s for k in ["expired", "ended", "no longer", "unavailable"])

    def dedupe_by_title(items):
        seen = {}
        for it in items or []:
            title = (it.get("title") or "").strip().lower()
            if title and title not in seen:
                seen[title] = it
        return list(seen.values())

    # --- load previous snapshot for change detection ---
    old_grouped = load_json(DATA_FILE, {})  # dict grouped by platform

    # --- scrape all sources ---
    egs = get_egs_free()
    gog = get_gog_free()
    steam = get_steam_free()
    humble = get_humble_free()
    ubi = get_ubisoft()

    # Prime returns (but we will *not* trust these for saving to game_data.json)
    prime_with_link_return, prime_skipped_return = get_prime_free()

    # --- debug: raw scraper counts ---
    print(f"[SCRAPER] Epic Games: {len(egs)}")
    print(f"[SCRAPER] GOG: {len(gog)}")
    print(f"[SCRAPER] Steam: {len(steam)}")
    print(f"[SCRAPER] Humble: {len(humble)}")
    print(f"[SCRAPER] Ubisoft: {len(ubi)}")
    print(f"[SCRAPER] Prime (returned) with link: {len(prime_with_link_return)}")
    print(f"[SCRAPER] Prime (returned) skipped : {len(prime_skipped_return)}")

    # --- build grouped fresh (do NOT reuse old_grouped) ---
    grouped = {}
    expired_filtered = 0

    def add_items(items):
        nonlocal expired_filtered
        for it in items or []:
            if is_expired(it.get("status", "")):
                expired_filtered += 1
                continue
            src = it.get("platform") or "Other"
            grouped.setdefault(src, []).append(it)

    # Non-Prime platforms straight from scrapers
    add_items(egs)
    add_items(gog)
    add_items(steam)
    add_items(humble)
    add_items(ubi)

    # --- PRIME: enforce file-as-source-of-truth ---
    # Load what get_prime_free() saved to disk and use *only* that for game_data.json
    try:
        prime_with_link_file = load_json(PRIME_WITH_LINK, [])
    except Exception as e:
        print("[WARN] Failed to load PRIME_WITH_LINK file; using returned list. Err:", e)
        prime_with_link_file = prime_with_link_return

    try:
        prime_skipped_file = load_json(PRIME_SKIPPED, [])
    except Exception as e:
        print("[WARN] Failed to load PRIME_SKIPPED file; using returned list. Err:", e)
        prime_skipped_file = prime_skipped_return

    # Always ensure skipped file exists (even if empty)
    save_json(PRIME_SKIPPED, prime_skipped_file or [])

    # Dedupe both sets by title (defensive)
    prime_with_link_file = dedupe_by_title(prime_with_link_file)
    prime_skipped_file = dedupe_by_title(prime_skipped_file)

    # Debug: compare returned vs file to spot "leaks"
    def titles(items): return sorted((it.get("title") or "").strip() for it in items)

    ret_w, ret_s = set(titles(prime_with_link_return)), set(titles(prime_skipped_return))
    fil_w, fil_s = set(titles(prime_with_link_file)), set(titles(prime_skipped_file))

    if ret_w != fil_w or ret_s != fil_s:
        print("[DEBUG] PRIME mismatch between returned and file sets detected.")
        only_in_return_with = sorted(ret_w - fil_w)
        only_in_file_with = sorted(fil_w - ret_w)
        only_in_return_skip = sorted(ret_s - fil_s)
        only_in_file_skip = sorted(fil_s - ret_s)
        if only_in_return_with:
            print("  ↪ Only in RETURN (with-link):", only_in_return_with)
        if only_in_file_with:
            print("  ↪ Only in FILE   (with-link):", only_in_file_with)
        if only_in_return_skip:
            print("  ↪ Only in RETURN (skipped)  :", only_in_return_skip)
        if only_in_file_skip:
            print("  ↪ Only in FILE   (skipped)  :", only_in_file_skip)

    # Union for Prime (from FILES only)
    prime_union_file = prime_with_link_file + prime_skipped_file
    # Filter expired (defensive), then add to grouped
    prime_union_file_active = [it for it in prime_union_file if not is_expired(it.get("status", ""))]
    add_items(prime_union_file_active)

    # --- result debug ---
    print(f"[FILTER] Expired entries removed: {expired_filtered}")
    print(f"[RESULT] Platforms in grouped: {list(grouped.keys())}")
    for src, items in grouped.items():
        print(f"[RESULT] {src}: {len(items)} items")

    # Extra Prime integrity check
    prime_in_grouped = [it for it in grouped.get("Prime Gaming", [])]
    expected_prime_count = len(prime_union_file_active)
    if len(prime_in_grouped) != expected_prime_count:
        print(
            f"[ERROR] Prime count mismatch in grouped! grouped={len(prime_in_grouped)} "
            f"expected={expected_prime_count}"
        )
        # Debug titles diff
        grp_titles = set(titles(prime_in_grouped))
        exp_titles = set(titles(prime_union_file_active))
        print("  ↪ Only in grouped:", sorted(grp_titles - exp_titles))
        print("  ↪ Only in expected:", sorted(exp_titles - grp_titles))

    # --- prepare drops.json (flat list used by dashboard.js) ---
    flat = []
    for v in grouped.values():
        flat.extend(v)

    # --- save outputs ---
    save_json(DROPS_FILE, flat)      # dashboard.js reads this
    save_json(DATA_FILE, grouped)    # grouped snapshot for comparison
    # PRIME_SKIPPED already saved above; keep as always-present file

    # --- changes & dashboard ---
    changes = compare_and_build(old_grouped, grouped)
    build_dashboard(grouped)

    if changes:
        msg = (
            "🗞 <b>Free Game Update</b> 🗞<br/><br/>"
            + "<br/>".join(changes)
            + f"<br/><br/>🌐 <a href=\"{DASHBOARD_LINK}\">Dashboard</a>"
        )
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write(msg)
        send_telegram(msg)
        # Email handled by mailer.js
    else:
        print("[INFO] No changes at", now_str())

if __name__ == "__main__":
    main()