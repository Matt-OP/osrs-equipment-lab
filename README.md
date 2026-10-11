# [OSRS Equipment Lab](https://matt-op.github.io/osrs-equipment-lab/)

Scrape every equipment table from the [Old School RuneScape Wiki](https://oldschool.runescape.wiki/), then browse the items and test gear loadouts in a single self-contained web page.

- **Items tab:** search, filter and sort all ~1,950 pieces of equipment and view each item's full stat block.
- **Loadout tab:** equip items into the 11 worn-equipment slots, preview what any item would change before equipping it, and see your totals as bars and a radar chart.
- **Data pipeline:** Python scripts that pull the data and icons from the wiki and bake them into the page, plus an updater that only refreshes things when the wiki actually changed.

The finished page is one HTML file with the data embedded. It needs no server, no database and no internet connection once the images are downloaded.

---

## Contents

1. [Project layout](#project-layout)
2. [Requirements](#requirements)
3. [Quick start](#quick-start)
4. [Using the viewer](#using-the-viewer)
5. [Data reference](#data-reference)
6. [Images](#images)
7. [Keeping the data up to date](#keeping-the-data-up-to-date)
8. [Configuration](#configuration)
9. [Troubleshooting](#troubleshooting)
10. [Credits and legal](#credits-and-legal)

---

## Project layout

```
.
├── osrs_equip_slots.py            # 1. scrapes the wiki -> osrs_equipment_all_slots.csv
├── download_images.py             # 2. downloads icons    -> images/ + image_manifest.csv
├── build_viewer.py                # 3. embeds data into   -> osrs_equipment_viewer.html
├── update_data.py                 #    checks the wiki and runs the steps above only if needed
├── osrs_equipment_viewer.html     # the web page (open this)
├── index.html                     # tiny redirect to the viewer
├── requirements.txt
├── .github/workflows/site.yml     # optional scheduled automation (see "Keeping the data up to date")
│
│   Generated files:
├── osrs_equipment_all_slots.csv   # all equipment, one row per item
├── image_manifest.csv             # item -> local image path
├── data_meta.json                 # last-updated date and change summary
└── images/
    ├── items/                     # one icon per item
    ├── stats/                     # stat, weight, speed and members/F2P icons
    └── slots/                     # equipment slot icons
```

Run the three numbered scripts in order the first time. After that, `update_data.py` does everything for you.

## Requirements

- **Python 3.10 or newer**
- Three packages: `requests`, `pandas`, `beautifulsoup4`
- An internet connection for the scraping and image steps (not for viewing the finished page)

```bash
pip install -r requirements.txt
```

On Windows you can use `py -m pip install -r requirements.txt` if `pip` isn't on your PATH. No `lxml` or `html5lib` is needed.

## Quick start

All commands are run from the project folder.

### 1. Tell the wiki who you are

The OSRS Wiki blocks anonymous or generic scrapers. Give it an email address or a URL so it can contact you if your requests cause trouble.

```powershell
# Windows PowerShell
$env:OSRS_WIKI_CONTACT = "you@example.com"
```

```bash
# macOS / Linux
export OSRS_WIKI_CONTACT="you@example.com"
```

You can instead edit the `CONTACT` default near the top of `osrs_equip_slots.py` and `download_images.py`. The variable only lasts for the current terminal session.

### 2. Scrape the equipment tables

```bash
python osrs_equip_slots.py
```

This reads the 12 wiki slot-table pages (head, cape, neck, ammunition, one-handed weapons, shield, body, legs, hands, feet, ring, two-handed weapons) and writes **`osrs_equipment_all_slots.csv`**. It takes about 15 to 30 seconds. See [Data reference](#data-reference) for the columns.

### 3. Download the images

```bash
python download_images.py
```

This downloads the item icons, stat icons and slot icons into `images/` and writes `image_manifest.csv`, which links each item to its icon. Expect roughly 1,850 small files and a few minutes of run time, since it waits a fraction of a second between downloads to be polite to the wiki. The script is resumable: files that already exist are skipped, so it is safe to stop and re-run it.

Items that can't be matched to an icon are listed in `missing_images.csv`, and the viewer shows a placeholder box for them.

### 4. Build the page

```bash
python build_viewer.py
```

This embeds the CSV data and the image paths into **`osrs_equipment_viewer.html`**. Run it again any time the CSV or images change.

### 5. Open the viewer

Double-click `osrs_equipment_viewer.html`. Keep it in the same folder as `images/`, because the page loads icons using relative paths.

> Fonts load from Google Fonts. Offline, the page falls back to your system font and works the same.

## Using the viewer

### Items tab

- **Search** by name (variants like `Charged` or `(p++)` are part of the name).
- **Filter** by slot, and by F2P or Members.
- **Sort** by name, any single stat (highest first) or weight (lightest first).
- Each list row shows the item's three biggest stats. Click a row for the full breakdown: attack, defence and other bonuses, weight, attack speed and F2P/Members status.
- **Equip in loadout** sends the item to the Loadout tab.

### Loadout tab

- **Worn equipment:** click a slot to list the items that fit it, then click an item to equip it. Click an equipped item again, or the red **x** on the slot, to remove it. **Clear all** empties every slot. Your loadout is remembered in your browser.
- **Two-handed weapons** go in the weapon slot and automatically remove your shield. Equipping a shield while holding a two-handed weapon removes the weapon. The preview note tells you when this will happen.
- **Preview before you equip:** hover an item in the list to see what it would change. Green is gained and red is lost, shown next to each stat, on the radar, and for weight and attack speed. Each row also shows its biggest changes compared with what you're wearing now.
- **Loadout stats bars:** a full bar means the best item in every slot added together for that stat, so 100% is a theoretical best-in-slot set. The shaded strip at the left of each bar is for negative totals. Hover a bar for the exact figure and percentage.
- **Stat radar:** shows all 14 attack, defence and other bonuses at once, with each stat's icon and your current value around the rim. Rings mark 25, 50, 75 and 100% of the best possible total. **Zoom to fit** enlarges the shape so differences between loadouts are easier to see.

The 100% scale simply adds up each slot's single best item, so it ignores items that can't be worn together (for example, a two-handed weapon and a shield). Some stats' 100% therefore isn't reachable in practice. It is a fixed yardstick, not a recommendation.

## Data reference

`osrs_equipment_all_slots.csv` has one row per item and these columns:

| Column | Meaning |
| --- | --- |
| `Slot` | `head`, `cape`, `neck`, `ammunition`, `weapon` (one-handed), `shield`, `body`, `legs`, `hands`, `feet`, `ring` or `two-handed` |
| `Name` | Item name as shown on the wiki. Variants carry a suffix, e.g. `Ahrim's hood#Undamaged` |
| `Stab_Attack`, `Slash_Attack`, `Crush_Attack`, `Magic_Attack`, `Ranged_Attack` | Attack bonuses |
| `Stab_Defence`, `Slash_Defence`, `Crush_Defence`, `Magic_Defence`, `Ranged_Defence` | Defence bonuses |
| `Strength` | Melee strength bonus |
| `Ranged_Strength` | Ranged strength bonus |
| `Magic_Damage` | Magic damage bonus, stored as text such as `+10%` |
| `Prayer` | Prayer bonus |
| `Weight` | Weight in kg (can be negative) |
| `Speed` | Attack speed in game ticks (0.6 s each). Only weapon and two-handed rows have it; others are blank |
| `Members` | `F2P` or `Members`, read from the icon in the wiki table |

Notes:

- The wiki lists a few items more than once with identical stats; `build_viewer.py` drops exact duplicate rows (about four), so the viewer shows slightly fewer items than the CSV has rows.
- Columns are assigned by position, not by header text, so if the wiki ever changes its table layout the scraper prints "unexpected column count" and skips that table rather than guessing.

## Images

Everything the page shows as an image goes through one place: the `IMAGE_CONFIG` block near the top of the script in `osrs_equipment_viewer.html`.

For each image the page tries, in order:

1. the local copy in `images/`
2. the same image on the OSRS Wiki (a filename guess for items)
3. a dashed placeholder box with a short label

To use your own picture for a specific item, add it to `itemOverrides`:

```js
itemOverrides: { "Abyssal whip": "my_pics/whip.png" }
```

To turn images off entirely, set `enabled: false` and every image becomes a placeholder.

## Keeping the data up to date

`update_data.py` re-scrapes the wiki and compares the result with your existing CSV. **Only if something changed** does it write the new CSV, download new images, rebuild the page and stamp a new date. If nothing changed, it touches no files and the displayed date stays the same.

```bash
python update_data.py                # normal check
python update_data.py --count-only   # only react to a different total item count
python update_data.py --force        # rebuild even if nothing changed
python update_data.py --skip-images  # don't run download_images.py
```

- **What counts as a change:** by default, a different item count *or* any changed row, so balance changes to existing items are caught as well as new items. Use `--count-only` if you only care about new or removed items.
- **Last-updated date:** stored in `data_meta.json` and shown at the top of the page along with the item count. Hovering it shows a summary such as "1 new item". The date only moves when the data changes, not every time the script runs.
- **Safety checks:** if any slot page can't be read, or the item count suddenly drops by more than 10%, the script stops and keeps your existing data.
- **Exit codes:** 0 on success (whether or not anything changed), 1 if the scrape failed or a safety check tripped.

The repository also includes a GitHub Actions workflow (`.github/workflows/site.yml`) that runs this check on a schedule.

## Configuration

| Setting | Where | Default |
| --- | --- | --- |
| `OSRS_WIKI_CONTACT` | environment variable | `your_email@example.com` (set this) |
| `--csv`, `--out`, `--manifest`, `--delay` | `download_images.py` | `osrs_equipment_all_slots.csv`, `images`, `image_manifest.csv`, `0.2` |
| `--manifest`, `--meta` and positional `csv` / `html` | `build_viewer.py` | `image_manifest.csv`, `data_meta.json`, `osrs_equipment_all_slots.csv`, `osrs_equipment_viewer.html` |
| `--count-only`, `--force`, `--skip-images` | `update_data.py` | off |
| `IMAGE_CONFIG` | top of the HTML's script | local images with wiki fallback |

## Troubleshooting

**The scraper gets a 403 error or an empty response.** Set `OSRS_WIKI_CONTACT` (step 1). The wiki rejects requests that don't identify themselves.

**"unexpected column count (N); table skipped".** The wiki changed a table's layout. Open the page named in the output, compare it with the column list in `osrs_equip_slots.py`, and adjust `STAT_COLS` there.

**"No tables found" or "skipped" for a slot.** The page title may have changed. Check `SLOT_PAGES` in `osrs_equip_slots.py` against the wiki's current page names.

**Items show dashed boxes instead of icons.** Check that `images/` sits next to `osrs_equipment_viewer.html` and that you ran `build_viewer.py` after `download_images.py`. Items in `missing_images.csv` have no icon on the wiki and will always show a placeholder.

**The page shows no "last updated" date.** The date comes from `data_meta.json`. Run `python update_data.py` once to create it, then `python build_viewer.py` (the updater does this itself).

**Changes to the CSV don't appear in the page.** The data is embedded in the HTML, so re-run `python build_viewer.py` after any change to the CSV.

**`python` isn't found on Windows.** Try `py` instead (for example `py osrs_equip_slots.py`).

## Credits and legal

- Equipment data and images come from the [Old School RuneScape Wiki](https://oldschool.runescape.wiki/). Wiki text is published under a Creative Commons licence; see the wiki's own licensing page for the exact terms, and follow the wiki's rules for automated requests (a descriptive User-Agent and reasonable request rates).
- Old School RuneScape and its artwork are trademarks and property of Jagex Ltd. This project is a fan-made tool and is not affiliated with or endorsed by Jagex.
- Please scrape politely: keep the default delays, identify yourself with `OSRS_WIKI_CONTACT`, and avoid running the scripts in tight loops.
