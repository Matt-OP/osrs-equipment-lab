"""
Scrape every equipment-slot stats table from the OSRS Wiki into ONE CSV,
with a "Slot" column and a "Members" column (F2P / Members).

Uses the MediaWiki API (action=parse) to get each "<Slot> slot table" page,
then parses the wikitables with BeautifulSoup's built-in html.parser
(no lxml / html5lib needed).

Requirements:
    pip install requests pandas beautifulsoup4
"""

import os
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup

API_URL = "https://oldschool.runescape.wiki/api.php"
# The OSRS Wiki blocks generic user agents, so identify yourself.
# Set the OSRS_WIKI_CONTACT environment variable (email or URL), or edit the default below.
CONTACT = os.environ.get("OSRS_WIKI_CONTACT", "your_email@example.com")
HEADERS = {"User-Agent": f"osrs-equipment-table-scraper/1.0 (contact: {CONTACT})"}

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

OUTPUT_CSV = "osrs_equipment_all_slots.csv"

# Final CSV columns (fixed)
COLUMNS = ["Slot", "Name", "Stab_Attack", "Slash_Attack", "Crush_Attack", "Magic_Attack", "Ranged_Attack",
           "Stab_Defence", "Slash_Defence", "Crush_Defence", "Magic_Defence", "Ranged_Defence", "Strength",
           "Ranged_Strength", "Magic_Damage", "Prayer", "Weight", "Speed", "Members"]

# Wiki table layout after the item-icon column is dropped:
#   Name | members/F2P icon | 15 stat columns (Stab_Attack ... Weight) | Speed (weapon tables only)
STAT_COLS = COLUMNS[2:17]  # Stab_Attack ... Weight

# Alt text of the icon in the wiki's members column -> value for our CSV
MEMBERS_ICON_ALT = {"Members": "Members", "Free-to-play": "F2P"}


def fetch_page_html(title: str, retries: int = 3) -> str:
    params = {
        "action": "parse",
        "page": title,
        "prop": "text",
        "format": "json",
        "formatversion": 2,
        "redirects": 1,
    }
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"API error for '{title}': {data['error'].get('info')}")
            return data["parse"]["text"]
        except (requests.RequestException, RuntimeError):
            if attempt == retries:
                raise
            time.sleep(3 * attempt)


def cell_text(cell) -> str:
    """Cell text; for the members/F2P icon cell (image only) use the image's alt text."""
    text = cell.get_text(" ", strip=True)
    if not text:
        img = cell.find("img")
        if img is not None and img.get("alt") in MEMBERS_ICON_ALT:
            return img["alt"]
    return text


def table_to_grid(table):
    """
    Expand an HTML table into a list of rows (lists of strings), honouring
    rowspan/colspan. Also returns a parallel list saying whether each row is
    a header row (all <th>).
    """
    grid, is_header = [], []
    pending = {}  # (row, col) -> text carried down by a rowspan

    for r, tr in enumerate(table.find_all("tr")):
        cells = tr.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        row, col = [], 0

        def fill_pending():
            nonlocal col
            while (r, col) in pending:
                row.append(pending.pop((r, col)))
                col += 1

        for cell in cells:
            fill_pending()
            text = cell_text(cell)
            rs = int(cell.get("rowspan", 1) or 1)
            cs = int(cell.get("colspan", 1) or 1)
            for dc in range(cs):
                row.append(text)
                for dr in range(1, rs):
                    pending[(r + dr, col + dc)] = text
            col += cs
        fill_pending()

        grid.append(row)
        is_header.append(all(c.name == "th" for c in cells))

    return grid, is_header


def table_to_df(table) -> pd.DataFrame | None:
    grid, is_header = table_to_grid(table)
    data_rows = [g for g, h in zip(grid, is_header) if not h]
    if not data_rows:
        return None

    width = max(len(r) for r in data_rows)
    data_rows = [r + [""] * (width - len(r)) for r in data_rows]
    df = pd.DataFrame(data_rows)

    # Drop empty columns (the item icon column) and empty rows
    df = df.replace("", pd.NA).dropna(axis=1, how="all").dropna(axis=0, how="all")

    # Assign the predefined column names by position
    n = df.shape[1]
    if n == 2 + len(STAT_COLS):          # Name, Members, 15 stats  (no Speed)
        df.columns = ["Name", "Members"] + STAT_COLS
    elif n == 3 + len(STAT_COLS):        # ... plus Speed (weapon tables)
        df.columns = ["Name", "Members"] + STAT_COLS + ["Speed"]
    else:
        print(f"  !! unexpected column count ({n}); table skipped")
        return None

    df = df[df["Name"].notna()].copy()
    df["Members"] = df["Members"].map(MEMBERS_ICON_ALT)
    return df


def extract_tables(html: str) -> list[pd.DataFrame]:
    soup = BeautifulSoup(html, "html.parser")
    frames = []
    for table in soup.find_all("table", class_="wikitable"):
        df = table_to_df(table)
        if df is not None and not df.empty:
            frames.append(df)
    return frames


def scrape(strict: bool = False) -> pd.DataFrame:
    """
    Scrape every slot page and return one DataFrame with the fixed COLUMNS.
    strict=True raises if ANY slot page could not be read (used by update_data.py
    so a partial scrape never overwrites good data).
    """
    all_frames, failed = [], []
    for slot, title in SLOT_PAGES.items():
        print(f"Fetching {title} ...")
        try:
            html = fetch_page_html(title)
        except Exception as e:
            print(f"  !! skipped {title}: {e}")
            failed.append(slot)
            continue

        tables = extract_tables(html)
        if not tables:
            print(f"  !! no tables found on {title}")
            failed.append(slot)
            continue

        for df in tables:
            df.insert(0, "Slot", slot)
            all_frames.append(df)
        print(f"  {sum(len(t) for t in tables)} rows from {len(tables)} table(s)")
        time.sleep(1)

    if strict and failed:
        raise RuntimeError("Could not read slot page(s): " + ", ".join(failed))
    if not all_frames:
        raise RuntimeError("No data retrieved.")

    combined = pd.concat(all_frames, ignore_index=True, sort=False)
    if "Speed" not in combined.columns:
        combined["Speed"] = pd.NA
    return combined[COLUMNS]


def main() -> None:
    try:
        combined = scrape()
    except RuntimeError as e:
        raise SystemExit(str(e))

    missing = combined["Members"].isna().sum()
    if missing:
        print(f"Warning: {missing} rows had no Members/F2P icon (Members left blank)")

    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nSaved {len(combined)} rows x {len(combined.columns)} cols -> {OUTPUT_CSV}")
    print(combined["Members"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
