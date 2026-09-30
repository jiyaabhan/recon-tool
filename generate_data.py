"""
Step 1: generate synthetic data with planted problems and an answer key.

Creates, in ./data:
  source_a.csv   - the "ERP export" (treated as system of record)
  source_b.csv   - the "legacy spreadsheet" (messy copy of the same items)
  answer_key.csv - for every row in source_b: the correct source_a item_code
                   (blank if the item does not really exist) and the planted issue
"""
import csv
import os
import random

random.seed(7)  # same data every run results are reproducible

OUT = "data"
os.makedirs(OUT, exist_ok=True)

# ---------- 1. Build the clean item master (source A) ----------
FAMILIES = [
    # (code prefix, base name, unit, cost range, work centre)
    ("POWDER", "Powder Coat", "kg", (8, 20), "Painting"),
    ("AL", "Aluminium Tube", "m", (3, 9), "Cutting"),
    ("STL", "Steel Frame", "pc", (25, 60), "Welding"),
    ("SLAT", "Teak Slat", "pc", (4, 12), "Assembly"),
    ("MESH", "Rope Mesh Panel", "pc", (15, 35), "Assembly"),
    ("SCR", "Stainless Screw", "box", (2, 6), "Assembly"),
    ("CUSH", "Outdoor Cushion", "pc", (18, 45), "Upholstery"),
    ("GLD", "Floor Glide", "pack", (1, 4), "Grinding"),
]
VARIANTS = ["Black", "White", "Grey", "Natural", "Charcoal", "Sand",
            "12mm", "20mm", "25mm", "32mm", "Large", "Small", "Standard"]

items = []
counter = {}
while len(items) < 100:
    prefix, base, unit, (lo, hi), wc = random.choice(FAMILIES)
    variant = random.choice(VARIANTS)
    name = f"{base} {variant}"
    if any(i["description"] == name for i in items):
        continue
    counter[prefix] = counter.get(prefix, 0) + 1
    items.append({
        "item_code": f"{prefix}-{counter[prefix]:04d}",
        "description": name,
        "uom": unit,
        "cost": round(random.uniform(lo, hi), 2),
        "work_center": wc,
    })

with open(f"{OUT}/source_a.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(items[0].keys()))
    w.writeheader()
    w.writerows(items)

# ---------- 2. Build the messy copy (source B) with planted issues ----------
ABBREV = {"Aluminium": "Alu", "Stainless": "SS", "Powder Coat": "Pwdr Coat",
          "Outdoor": "Outdr", "Floor Glide": "Glide", "Rope Mesh Panel": "Mesh Panel",
          "Steel Frame": "Frm Stl", "Teak Slat": "Slat Tk", "Cushion": "Cush",
          "Black": "Blk", "White": "Wht", "Grey": "Gry", "Natural": "Nat",
          "Charcoal": "Chrcl", "Standard": "Std", "Large": "Lg", "Small": "Sm"}

def abbreviate(name):
    for long, short in ABBREV.items():
        name = name.replace(long, short)
    return name.replace("mm", " mm")

b_rows, key = [], []

def add(row, true_code, issue):
    b_rows.append(row)
    key.append({"b_row": len(b_rows), "true_item_code": true_code, "planted_issue": issue})

shuffled = items[:]
random.shuffle(shuffled)
missing = shuffled[0]                  # issue: exists in A, missing from B
conflict_cost = shuffled[1:6]          # issue: cost disagrees
conflict_wc = shuffled[6:9]            # issue: work centre disagrees (welding vs grinding style)
prefix_variant = [i for i in shuffled[9:] if i["item_code"].startswith("POWDER")][:4]
abbreviated = shuffled[20:55]          # issue: abbreviated name
legacy_code = shuffled[36:76]          # issue: legacy system used its own code, so only the name can match
duplicated = shuffled[35]              # issue: row appears twice in B

# swapped-code trap: B row uses ANOTHER real item's code but describes this item
same_family = {}
for i in items:
    same_family.setdefault(i["item_code"].split("-")[0], []).append(i)
swap_target, swap_wrong_code = None, None
for fam in same_family.values():
    if len(fam) >= 2 and fam[0] not in (missing, duplicated):
        swap_target, swap_wrong_code = fam[0], fam[1]["item_code"]
        break

for it in items:
    if it is missing:
        continue
    row = {"code": it["item_code"], "item_name": it["description"], "unit": it["uom"],
           "std_cost": it["cost"], "bottleneck_wc": it["work_center"]}
    issue = "clean"
    if it in prefix_variant:
        row["code"] = it["item_code"].replace("POWDER-", "POW-")
        issue = "prefix_variant"
    if it in abbreviated:
        row["item_name"] = abbreviate(it["description"])
        issue = "abbreviated_name" if issue == "clean" else issue + "+abbreviated_name"
    if it in legacy_code and it is not duplicated:
        row["code"] = f"L{random.randint(1000, 9999)}"
        issue = "legacy_code" if issue == "clean" else issue + "+legacy_code"
    if it in conflict_cost:
        row["std_cost"] = round(it["cost"] * random.choice([0.8, 1.25]), 2)
        issue = "cost_conflict" if issue == "clean" else issue + "+cost_conflict"
    if it in conflict_wc:
        row["bottleneck_wc"] = "Grinding" if it["work_center"] != "Grinding" else "Welding"
        issue = "work_center_conflict" if issue == "clean" else issue + "+work_center_conflict"
    if it is swap_target:
        row["code"] = swap_wrong_code
        issue = "swapped_code"
    add(row, it["item_code"], issue)
    if it is duplicated:
        add(dict(row), it["item_code"], "duplicate_row")

# phantom item: in B but not a real item in A
add({"code": "MESH-0099", "item_name": "Mesh Insert Temp", "unit": "pc",
     "std_cost": 9.5, "bottleneck_wc": "Assembly"}, "", "phantom_item")

# shuffle B so row order gives nothing away, then renumber the key to match
order = list(range(len(b_rows)))
random.shuffle(order)
b_rows = [b_rows[i] for i in order]
key = [dict(key[i], b_row=n + 1) for n, i in enumerate(order)]

with open(f"{OUT}/source_b.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(b_rows[0].keys()))
    w.writeheader()
    w.writerows(b_rows)

with open(f"{OUT}/answer_key.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["b_row", "true_item_code", "planted_issue"])
    w.writeheader()
    w.writerows(key)

print(f"source_a: {len(items)} rows | source_b: {len(b_rows)} rows")
print(f"missing from B (should be flagged): {missing['item_code']}")
print("Planted issues:")
from collections import Counter
for issue, n in Counter(k["planted_issue"] for k in key).most_common():
    print(f"  {issue}: {n}")
