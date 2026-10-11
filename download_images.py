"""
Download every image needed by the equipment viewer from the OSRS Wiki:

  images/items/   one icon per item in the CSV
  images/stats/   stat icons (attack/defence/strength/etc.), weight, speed, members/F2P icons
  images/slots/   equipment slot icons

It also writes  image_manifest.csv  (Slot, Name, Image) which build_viewer.py
uses to link each item to its local image file.

How item images are found
-------------------------
The script re-reads the same wiki slot-table pages used by the scraper (via the
MediaWiki API) and takes the exact icon file shown next to each item. That is
more reliable than guessing filenames from item names (variants like
"(p++)", "Charged", etc. have their own files). Any CSV item that cannot be
matched falls back to a guessed filename.

The script is resumable: files that already exist are skipped, so you can
safely re-run it.

Usage (run from the folder that holds the CSV and the HTML file):
    python download_images.py
    python download_images.py --csv osrs_equipment_all_slots.csv --out images --delay 0.25

Requirements:
    pip install requests pandas beautifulsoup4
"""

import argparse
import csv
import hashlib
import os
import re
import sys
import time
from urllib.parse import quote, unquote, urljoin, urlsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

SITE = "https://oldschool.runescape.wiki"
API_URL = SITE + "/api.php"
IMAGES_URL = SITE + "/images/"

# The OSRS Wiki blocks generic user agents, so identify yourself.
# Set the OSRS_WIKI_CONTACT environment variable (email or URL), or edit the default below.
CONTACT = os.environ.get("OSRS_WIKI_CONTACT", "your_email@example.com")
HEADERS = {"User-Agent": f"osrs-equipment-image-downloader/1.0 (contact: {CONTACT})"}

SLOT_PAGES = {
    "head": "Head slot table",
    "cape": "Cape slot table",
    "neck": "Neck slot table",
    "ammunition": "Ammunition slot table",
    "weapon": "One-handed slot table",
    "shield": "Shield slot table",
    "body": "Body slot table",
    "legs": "Legs slot table",
    "hands": "Hands slot table",
    "feet": "Feet slot table",
    "ring": "Ring slot table",
    "two-handed": "Two-handed slot table",
}

# Icons for the stat columns in the CSV, plus the extras the viewer uses.
STAT_ICONS = [
    "White_dagger.png",          # Stab_Attack / Stab_Defence
    "White_scimitar.png",        # Slash_Attack / Slash_Defence
    "White_warhammer.png",       # Crush_Attack / Crush_Defence
    "Magic_icon.png",            # Magic_Attack / Magic_Defence
    "Ranged_icon.png",           # Ranged_Attack / Ranged_Defence
    "Defence_icon.png",          # overlay on the defence icons
    "Strength_icon.png",         # Strength
    "Ranged_Strength_icon.png",  # Ranged_Strength
    "Magic_Damage_icon.png",     # Magic_Damage
    "Prayer_icon.png",           # Prayer
    "Weight_icon.png",           # Weight
    "Watch.png",                 # Speed
    "Member_icon.png",           # Members
    "Free-to-play_icon.png",     # F2P
]
SLOT_ICONS = [
    "Head_slot.png", "Cape_slot.png", "Neck_slot.png", "Ammo_slot.png", "Weapon_slot.png",
    "Body_slot.png", "Shield_slot.png", "Legs_slot.png", "Hands_slot.png", "Feet_slot.png",
    "Ring_slot.png", "2h_slot.png",
]


# --------------------------------------------------------------------------
# networking
# --------------------------------------------------------------------------
def http_get(session, url, retries=4, **kwargs):
    """GET with retries/backoff. Returns a Response or None."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=60, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5 * attempt))
                print(f"  rate limited, waiting {wait}s ...")
                time.sleep(wait)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt == retries:
                print(f"  !! failed: {url} ({e})")
                return None
            time.sleep(2 * attempt)
    return None


def fetch_page_html(session, title):
    params = {
        "action": "parse", "page": title, "prop": "text",
        "format": "json", "formatversion": 2, "redirects": 1,
    }
    resp = http_get(session, API_URL, params=params)
    if resp is None:
        return None
    data = resp.json()
    if "error" in data:
        print(f"  !! API error for '{title}': {data['error'].get('info')}")
        return None
    return data["parse"]["text"]


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def clean_url(src):
    """Absolute URL without the cache-busting query string."""
    parts = urlsplit(urljoin(SITE, src))
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def collect_item_icons(html):
    """Return {item name: icon url} for every row in the slot tables of a page."""
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for table in soup.find_all("table", class_="wikitable"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 3:
                continue
            icon_td, name_td = tds[0], tds[1]
            img = icon_td.find("img")
            name = name_td.get_text(" ", strip=True)
            if img is not None and img.get("src") and name:
                found.setdefault(name, clean_url(img["src"]))
    return found


def guess_icon_url(name):
    base = name.split("#")[0]
    base = base[:1].upper() + base[1:]
    return IMAGES_URL + quote(base.replace(" ", "_"), safe="()'!,-._~") + ".png"


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------
UNSAFE = re.compile(r"[^A-Za-z0-9._()'\-]")


def safe_filename(url, used):
    """Windows-safe filename for a URL. `used` maps filename -> url to avoid collisions."""
    name = unquote(os.path.basename(urlsplit(url).path)) or "image.png"
    name = UNSAFE.sub("_", name)
    if used.get(name, url) != url:  # same sanitized name, different source file
        stem, ext = os.path.splitext(name)
        name = f"{stem}_{hashlib.md5(url.encode()).hexdigest()[:6]}{ext}"
    used[name] = url
    return name


def download(session, url, dest, delay):
    """Download url -> dest. Returns True if the file exists afterwards."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    resp = http_get(session, url)
    if resp is None or not resp.headers.get("Content-Type", "").startswith("image"):
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(resp.content)
    time.sleep(delay)
    return True


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="osrs_equipment_all_slots.csv")
    ap.add_argument("--out", default="images", help="output folder (default: images)")
    ap.add_argument("--manifest", default="image_manifest.csv")
    ap.add_argument("--delay", type=float, default=0.2, help="seconds to wait between downloads")
    args = ap.parse_args()

    if CONTACT == "your_email@example.com":
        print("Tip: set the OSRS_WIKI_CONTACT environment variable to your email or URL.\n")

    df = pd.read_csv(args.csv)
    session = requests.Session()
    session.headers.update(HEADERS)

    out = args.out.rstrip("/\\")
    items_dir = os.path.join(out, "items")
    stats_dir = os.path.join(out, "stats")
    slots_dir = os.path.join(out, "slots")

    # ---- 1. stat + slot icons ------------------------------------------------
    print("Downloading stat icons and slot icons ...")
    failed_static = []
    for folder, files in ((stats_dir, STAT_ICONS), (slots_dir, SLOT_ICONS)):
        for fn in files:
            if not download(session, IMAGES_URL + fn, os.path.join(folder, fn), args.delay):
                failed_static.append(fn)
    print(f"  done ({len(STAT_ICONS) + len(SLOT_ICONS) - len(failed_static)} ok, {len(failed_static)} failed)")

    # ---- 2. find the icon URL for every (slot, name) -------------------------
    slots_in_csv = [s for s in SLOT_PAGES if s in set(df["Slot"])]
    src_map = {}  # (slot, name) -> url
    for slot in slots_in_csv:
        title = SLOT_PAGES[slot]
        print(f"Reading icon list from '{title}' ...")
        html = fetch_page_html(session, title)
        if html is None:
            continue
        for name, url in collect_item_icons(html).items():
            src_map[(slot, name)] = url
        time.sleep(args.delay)

    # ---- 3. download unique item icons ---------------------------------------
    pairs = list(df[["Slot", "Name"]].itertuples(index=False, name=None))
    row_url, guessed = {}, 0
    for slot, name in pairs:
        url = src_map.get((slot, name))
        if url is None:
            url, guessed = guess_icon_url(name), guessed + 1
        row_url[(slot, name)] = url

    unique_urls = sorted(set(row_url.values()))
    print(f"\n{len(pairs)} items -> {len(unique_urls)} unique image files "
          f"({guessed} items had no icon on the wiki page and use a guessed filename)")

    used, url_to_file, failed_urls = {}, {}, set()
    for i, url in enumerate(unique_urls, 1):
        fname = safe_filename(url, used)
        if download(session, url, os.path.join(items_dir, fname), args.delay):
            url_to_file[url] = fname
        else:
            failed_urls.add(url)
        if i % 50 == 0 or i == len(unique_urls):
            print(f"  {i}/{len(unique_urls)}  (failed so far: {len(failed_urls)})")

    # ---- 4. manifest + report -------------------------------------------------
    rel_items = out.replace("\\", "/") + "/items/"
    missing = []
    with open(args.manifest, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Slot", "Name", "Image"])
        for slot, name in pairs:
            fname = url_to_file.get(row_url[(slot, name)])
            w.writerow([slot, name, rel_items + fname if fname else ""])
            if not fname:
                missing.append((slot, name, row_url[(slot, name)]))

    if missing:
        with open("missing_images.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Slot", "Name", "TriedUrl"])
            w.writerows(missing)

    print(f"\nItem images saved to: {items_dir}")
    print(f"Manifest written to:  {args.manifest}")
    if missing:
        print(f"{len(missing)} items have no image (see missing_images.csv). The viewer shows a placeholder for these.")
    if failed_static:
        print("Static icons that failed: " + ", ".join(failed_static))
    print("\nNext: python build_viewer.py   (embeds the image paths into the HTML)")


if __name__ == "__main__":
    sys.exit(main())
