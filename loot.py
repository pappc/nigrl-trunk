"""Zone-based loot generation system.

generate_floor_loot(zone, floor_num, player_skills) returns a flat list of
(item_id, strain_or_None) tuples for one dungeon floor.

Adding a new zone:
1. Add ZONE_LOOT_CONFIG["new_zone"] block
2. Add ZONE_STRAIN_WEIGHTS["new_zone"] if cannabis items are present
3. Add ZONE_CONSUMABLE/MATERIAL/TOOL/EQUIPMENT table entries for new_zone
4. Tag new items with "zones": ["new_zone"] in items.py
5. For chains: add entry to CHAIN_ZONE_CONFIGS in items.py
"""

import random
from items import ITEM_DEFS, get_random_chain


# ---------------------------------------------------------------------------
# Zone floor budgets
# ---------------------------------------------------------------------------

ZONE_LOOT_CONFIG = {
    "crack_den": {
        "consumable": {"per_floor": (4, 8)},    # target 20-30 over 4 floors
        "material":   {"per_floor": (6, 12)},   # target 35-45
        "tool":       {"per_floor": (0, 1)},    # target 2-3
        "equipment":  {"per_floor": (1, 3)},    # target 6-10
    }
}


# ---------------------------------------------------------------------------
# Zone strain weights
# ---------------------------------------------------------------------------

ZONE_STRAIN_WEIGHTS = {
    "crack_den": {
        "OG Kush":       10,
        "Columbian Gold":  8,
        "Agent Orange":    5,
        "Jungle Boyz":     3,
        "Blue Lobster":    2,
        "Dosidos":         3,
    }
}


# ---------------------------------------------------------------------------
# Item tables per category
#
# Each entry: (item_id, base_weight)
# Skill weighting multiplies base_weight by (skill_level + 1) for consumables
# and materials. Tools and equipment are always picked uniformly.
# ---------------------------------------------------------------------------

ZONE_CONSUMABLE_TABLES = {
    "crack_den": [
        ("joint", 1),
    ],
}

ZONE_MATERIAL_TABLES = {
    "crack_den": [
        ("rolling_paper", 6),   # 3× more likely than nugs
        ("kush",          2),   # 2× more likely than nugs
        ("weed_nug",      1),
    ],
}

ZONE_TOOL_TABLES = {
    "crack_den": [
        ("grinder", 1),
    ],
}


# ---------------------------------------------------------------------------
# Equipment config per zone
# ---------------------------------------------------------------------------

ZONE_EQUIPMENT_CONFIG = {
    "crack_den": {
        # ring is 2× as common as each other equipment type
        "type_weights":      [("weapon", 1), ("ring", 2), ("neck", 1), ("feet", 1)],
        # minor ring 8× as likely as greater; divine/advanced excluded via zones tag
        "ring_tier_weights": [("minor", 8), ("greater", 1)],
    }
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_STRAIN_ITEMS = frozenset(("joint", "kush", "weed_nug"))


def _pick_strain(zone):
    """Pick a strain using zone-weighted distribution."""
    weights = ZONE_STRAIN_WEIGHTS.get(zone)
    if not weights:
        return None
    keys = list(weights.keys())
    vals = list(weights.values())
    return random.choices(keys, weights=vals, k=1)[0]


def _weighted_pick(table, player_skills, use_skill_weighting=True):
    """Pick one item_id from a table, applying skill multipliers when requested.

    effective_weight = base_weight * (skill_level + 1)
    Level 0 → 1× (unchanged), level 1 → 2×, level 2 → 3×, etc.
    """
    item_ids = [t[0] for t in table]
    weights  = []
    for item_id, base_w in table:
        level = 0
        if use_skill_weighting and player_skills:
            primary_skill = ITEM_DEFS.get(item_id, {}).get("primary_skill")
            if primary_skill:
                try:
                    level = player_skills.get(primary_skill).level
                except (KeyError, AttributeError):
                    level = 0
        weights.append(base_w * (level + 1))
    return random.choices(item_ids, weights=weights, k=1)[0]


def _resolve_equipment(zone):
    """Pick one equipment item_id for the given zone, or None on failure."""
    config   = ZONE_EQUIPMENT_CONFIG[zone]
    eq_types = [t[0] for t in config["type_weights"]]
    eq_wts   = [t[1] for t in config["type_weights"]]
    eq_type  = random.choices(eq_types, weights=eq_wts, k=1)[0]

    if eq_type == "weapon":
        candidates = [
            iid for iid, defn in ITEM_DEFS.items()
            if defn.get("subcategory") == "weapon"
            and zone in defn.get("zones", [])
        ]
        return random.choice(candidates) if candidates else None

    elif eq_type == "ring":
        tier_types = [t[0] for t in config["ring_tier_weights"]]
        tier_wts   = [t[1] for t in config["ring_tier_weights"]]
        tier       = random.choices(tier_types, weights=tier_wts, k=1)[0]
        candidates = [
            iid for iid, defn in ITEM_DEFS.items()
            if tier in defn.get("tags", [])
            and zone in defn.get("zones", [])
        ]
        return random.choice(candidates) if candidates else None

    elif eq_type == "neck":
        return get_random_chain(zone)

    elif eq_type == "feet":
        candidates = [
            iid for iid, defn in ITEM_DEFS.items()
            if "jordans" in defn.get("tags", [])
            and zone in defn.get("zones", [])
        ]
        return random.choice(candidates) if candidates else None

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_floor_loot(zone, floor_num, player_skills=None):
    """Generate a flat list of (item_id, strain_or_None) for one floor.

    zone         : zone key, e.g. "crack_den"
    floor_num    : 0-based floor index (reserved for future floor-scaling)
    player_skills: Skills object or None
    """
    config = ZONE_LOOT_CONFIG.get(zone, {})
    result = []

    # Consumables — skill-weighted
    if "consumable" in config:
        lo, hi = config["consumable"]["per_floor"]
        table  = ZONE_CONSUMABLE_TABLES.get(zone, [])
        if table:
            for _ in range(random.randint(lo, hi)):
                item_id = _weighted_pick(table, player_skills, use_skill_weighting=True)
                strain  = _pick_strain(zone) if item_id in _STRAIN_ITEMS else None
                result.append((item_id, strain))

    # Materials — skill-weighted
    if "material" in config:
        lo, hi = config["material"]["per_floor"]
        table  = ZONE_MATERIAL_TABLES.get(zone, [])
        if table:
            for _ in range(random.randint(lo, hi)):
                item_id = _weighted_pick(table, player_skills, use_skill_weighting=True)
                strain  = _pick_strain(zone) if item_id in _STRAIN_ITEMS else None
                result.append((item_id, strain))

    # Tools — no skill weighting
    if "tool" in config:
        lo, hi = config["tool"]["per_floor"]
        table  = ZONE_TOOL_TABLES.get(zone, [])
        if table:
            for _ in range(random.randint(lo, hi)):
                item_id = _weighted_pick(table, player_skills, use_skill_weighting=False)
                result.append((item_id, None))

    # Equipment — type/tier weighted, no skill weighting
    if "equipment" in config:
        lo, hi = config["equipment"]["per_floor"]
        for _ in range(random.randint(lo, hi)):
            item_id = _resolve_equipment(zone)
            if item_id:
                result.append((item_id, None))

    return result
