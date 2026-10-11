"""
Embed the CSV data (and, optionally, local image paths) into osrs_equipment_viewer.html.

Run this after you re-scrape the wiki or download images:
    python build_viewer.py
    python build_viewer.py my.csv my_viewer.html --manifest image_manifest.csv

If image_manifest.csv exists (created by download_images.py) each item is linked
to its local image file; otherwise the page falls back to wiki URLs / placeholders.

If data_meta.json exists (created by update_data.py) its "last updated" date is
embedded and shown at the top of the page.

Requires: pandas
"""
import argparse
import json
import os
import re

import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("csv", nargs="?", default="osrs_equipment_all_slots.csv")
ap.add_argument("html", nargs="?", default="osrs_equipment_viewer.html")
ap.add_argument("--manifest", default="image_manifest.csv")
ap.add_argument("--meta", default="data_meta.json")
args = ap.parse_args()

df = pd.read_csv(args.csv)

# Magic_Damage is stored like "+10%" -> 10.0
df["Magic_Damage"] = (
    df["Magic_Damage"].astype(str).str.replace("%", "", regex=False).str.replace("+", "", regex=False).astype(float)
)
df = df.drop_duplicates().reset_index(drop=True)  # exact duplicate rows from the wiki

# Optional: local image paths from download_images.py
if os.path.exists(args.manifest):
    man = pd.read_csv(args.manifest, keep_default_na=False)
    lookup = {(r.Slot, r.Name): r.Image for r in man.itertuples(index=False) if r.Image}
    df["Image"] = [lookup.get((s, n)) for s, n in zip(df["Slot"], df["Name"])]
    print(f"Linked {df['Image'].notna().sum()} of {len(df)} items to local images ({args.manifest})")
else:
    print(f"No {args.manifest} found: skipping local images (run download_images.py first)")

columns = list(df.columns)
rows = []
for rec in df.itertuples(index=False):
    row = []
    for val in rec:
        if pd.isna(val):
            row.append(None)
        elif isinstance(val, float) and val.is_integer() and columns[len(row)] != "Weight":
            row.append(int(val))
        elif hasattr(val, "item"):
            row.append(val.item())
        else:
            row.append(val)
    rows.append(row)

payload = json.dumps({"columns": columns, "rows": rows}, separators=(",", ":"), ensure_ascii=False)

with open(args.html, encoding="utf-8") as f:
    html = f.read()

pattern = re.compile(r"/\*DATA_START\*/.*?/\*DATA_END\*/", re.DOTALL)
if not pattern.search(html):
    raise SystemExit("Could not find the DATA_START / DATA_END markers in the HTML file.")
html = pattern.sub(lambda m: "/*DATA_START*/" + payload + "/*DATA_END*/", html, count=1)

# Optional: "last updated" info for the page header
meta_pattern = re.compile(r"/\*META_START\*/.*?/\*META_END\*/", re.DOTALL)
if os.path.exists(args.meta):
    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)
    keep = ("last_updated", "item_count", "added_count", "removed_count", "modified_count", "added_sample")
    meta_payload = json.dumps({k: meta[k] for k in keep if k in meta}, separators=(",", ":"), ensure_ascii=False)
    if meta_pattern.search(html):
        html = meta_pattern.sub(lambda m: "/*META_START*/" + meta_payload + "/*META_END*/", html, count=1)
        print(f"Embedded last-updated info ({meta.get('last_updated')}) from {args.meta}")
    else:
        print("Warning: no META_START / META_END markers in the HTML, so the last-updated date was not embedded")
else:
    print(f"No {args.meta} found: the page will not show a last-updated date (run update_data.py)")

with open(args.html, "w", encoding="utf-8") as f:
    f.write(html)
print(f"Embedded {len(rows)} items into {args.html}")
