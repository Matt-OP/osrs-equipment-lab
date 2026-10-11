"""
Check the OSRS Wiki for new or changed equipment and, only if something changed,
refresh the CSV, download any new images, rebuild the viewer and stamp a new
"last updated" date (data_meta.json -> shown at the top of the page).

Change detection
----------------
The fresh scrape is compared with the CSV you already have:

  * default      : the data counts as changed if the item count differs OR any
                   row differs (so balance changes to existing items are caught too)
  * --count-only : only a different total number of items counts as a change

If nothing changed, no file is touched and the displayed date stays the same.

Safety: if any slot page cannot be read, or the item count suddenly drops by
more than 10%, the script stops and keeps your existing data.

Usage:
    python update_data.py                 # normal run
    python update_data.py --count-only    # only react to item-count changes
    python update_data.py --force         # rebuild even if nothing changed
    python update_data.py --skip-images   # don't run download_images.py

Set OSRS_WIKI_CONTACT (email or URL) so the wiki can identify your requests.

Requirements:
    pip install requests pandas beautifulsoup4
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

import osrs_equip_slots as scraper

CSV_PATH = scraper.OUTPUT_CSV
META_PATH = "data_meta.json"
MAX_SHRINK = 0.10   # refuse to overwrite if the item count drops by more than this


def read_rows(path):
    """CSV -> set of row tuples (exact duplicate rows collapse, like build_viewer.py)."""
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        return {tuple(r) for r in reader if r}


def fingerprint(rows):
    blob = "\n".join("\x1f".join(r) for r in sorted(rows))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def item_keys(rows):
    return {(r[0], r[1]) for r in rows}  # (Slot, Name)


def set_github_output(**values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={str(v).lower()}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count-only", action="store_true", help="only a different item count counts as a change")
    ap.add_argument("--force", action="store_true", help="rebuild even if nothing changed; skip the shrink safety check")
    ap.add_argument("--skip-images", action="store_true", help="do not run download_images.py")
    args = ap.parse_args()

    today = dt.datetime.now(dt.timezone.utc).date().isoformat()

    # ---- 1. scrape (all-or-nothing) ------------------------------------------
    print("Checking the wiki for equipment changes ...\n")
    try:
        df = scraper.scrape(strict=True)
    except Exception as e:
        print(f"\nScrape failed, keeping existing data: {e}")
        set_github_output(changed=False)
        sys.exit(1)

    tmp_csv = CSV_PATH + ".new"
    df.to_csv(tmp_csv, index=False, encoding="utf-8-sig")
    new_rows = read_rows(tmp_csv)
    old_rows = read_rows(CSV_PATH)
    meta = None
    if os.path.exists(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            meta = json.load(f)

    new_count = len(new_rows)
    old_count = len(old_rows) if old_rows is not None else 0

    # ---- 2. decide whether anything changed ----------------------------------
    if old_rows is None:
        changed = True
        reason = "no previous CSV, creating it"
    elif args.count_only:
        changed = new_count != old_count
        reason = f"item count {old_count} -> {new_count}" if changed else f"item count unchanged ({new_count})"
    else:
        changed = fingerprint(new_rows) != fingerprint(old_rows)
        reason = f"item count {old_count} -> {new_count}, contents differ" if changed else f"no changes ({new_count} items)"

    if changed and old_count and new_count < old_count * (1 - MAX_SHRINK) and not args.force:
        os.remove(tmp_csv)
        print(f"\nItem count dropped from {old_count} to {new_count} (more than {MAX_SHRINK:.0%}). "
              "That looks like a bad scrape, so nothing was changed. Use --force to override.")
        set_github_output(changed=False)
        sys.exit(1)

    print(f"\nResult: {reason}")

    needs_build = changed or args.force or meta is None

    # ---- 3. write data + meta only when something changed --------------------
    if changed:
        old = old_rows or set()
        old_keys, new_keys = item_keys(old), item_keys(new_rows)
        added = sorted(new_keys - old_keys)
        removed = sorted(old_keys - new_keys)
        modified = {(r[0], r[1]) for r in (new_rows - old)} - set(added)
        os.replace(tmp_csv, CSV_PATH)
        meta = {
            "last_updated": today,
            "item_count": new_count,
            "content_hash": fingerprint(new_rows),
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "added_sample": [f"{name} ({slot})" for slot, name in added[:25]],
        }
        with open(META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Updated {CSV_PATH}: +{len(added)} new, -{len(removed)} removed, ~{len(modified)} changed. "
              f"Last-updated date set to {today}.")
    else:
        os.remove(tmp_csv)
        if meta is None:
            # first run with an existing CSV: record a baseline so the page can show a date
            meta = {"last_updated": today, "item_count": new_count, "content_hash": fingerprint(new_rows)}
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"No {META_PATH} yet, so a baseline was created with date {today}.")
        else:
            print(f"Keeping the last-updated date ({meta['last_updated']}).")

    # ---- 4. images + rebuild --------------------------------------------------
    if needs_build:
        if not args.skip_images:
            print("\nDownloading any new images ...")
            subprocess.run([sys.executable, "download_images.py"], check=True)
        print("\nRebuilding the viewer ...")
        subprocess.run([sys.executable, "build_viewer.py"], check=True)
    else:
        print("Nothing to rebuild.")

    set_github_output(changed=needs_build)


if __name__ == "__main__":
    main()
