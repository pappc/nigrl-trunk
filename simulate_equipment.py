#!/usr/bin/env python3
"""Simulate 100 equipment spawns in Crack Den to analyze distribution."""

from loot import _resolve_equipment
from items import ITEM_DEFS
from collections import defaultdict

# Run 100 equipment spawns
results = defaultdict(int)
for _ in range(100):
    item_id = _resolve_equipment("crack_den")
    if item_id:
        results[item_id] += 1

# Categorize results
equipment_by_type = defaultdict(list)
for item_id, count in sorted(results.items(), key=lambda x: x[1], reverse=True):
    defn = ITEM_DEFS.get(item_id, {})
    tags = defn.get("tags", [])

    # Determine type
    if defn.get("subcategory") == "weapon":
        eq_type = "WEAPON"
    elif "minor" in tags:
        eq_type = "RING (minor)"
    elif "greater" in tags:
        eq_type = "RING (greater)"
    elif "jordans" in tags:
        eq_type = "FEET (jordans)"
    elif "chain" in tags:
        eq_type = "NECK (chain)"
    else:
        eq_type = "OTHER"

    equipment_by_type[eq_type].append((item_id, count))

# Print results
print("=" * 80)
print("EQUIPMENT SPAWN SIMULATION: 100 spawns in Crack Den")
print("=" * 80)
print()

for eq_type in sorted(equipment_by_type.keys()):
    items = equipment_by_type[eq_type]
    type_count = sum(c for _, c in items)
    print(f"{eq_type}: {type_count} spawns ({type_count}%)")
    for item_id, count in sorted(items, key=lambda x: x[1], reverse=True):
        print(f"  {item_id:40} {count:3}x ({count}%)")
    print()

print("=" * 80)
print("SUMMARY BY CATEGORY")
print("=" * 80)

categories = {}
for eq_type, items in equipment_by_type.items():
    if "WEAPON" in eq_type:
        cat = "WEAPONS"
    elif "RING" in eq_type:
        cat = "RINGS"
    elif "NECK" in eq_type:
        cat = "NECK"
    elif "FEET" in eq_type:
        cat = "FEET"
    else:
        cat = "OTHER"

    count = sum(c for _, c in items)
    if cat not in categories:
        categories[cat] = 0
    categories[cat] += count

for cat in sorted(categories.keys()):
    print(f"{cat:15} {categories[cat]:3} spawns ({categories[cat]}%)")
