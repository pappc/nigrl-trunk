"""Zone-based loot generation system.

generate_floor_loot(zone, floor_num, player_skills) returns a flat list of
(item_id, strain_or_None) tuples for one dungeon floor.

Adding a new zone:
1. Add ZONE_LOOT_CONFIG["new_zone"] block
2. Add ZONE_STRAIN_WEIGHTS["new_zone"] if cannabis items are present
3. Add ZONE_CONSUMABLE/MATERIAL/TOOL/FOOD/EQUIPMENT table entries for new_zone
4. Tag new items with "zones": ["new_zone"] in items.py/foods.py
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
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": {          # TODO: tune budgets for meth lab zone
        "consumable": {"per_floor": (4, 8)},
        "material":   {"per_floor": (6, 12)},
        "tool":       {"per_floor": (0, 1)},
        "equipment":  {"per_floor": (1, 3)},
    },
    "casino_botanical": {  # TODO: tune budgets for casino + botanical garden zone
        "consumable": {"per_floor": (4, 8)},
        "material":   {"per_floor": (6, 12)},
        "tool":       {"per_floor": (0, 1)},
        "equipment":  {"per_floor": (1, 3)},
    },
    "the_underprison": {   # TODO: tune budgets for The Underprison zone
        "consumable": {"per_floor": (4, 8)},
        "material":   {"per_floor": (6, 12)},
        "tool":       {"per_floor": (0, 1)},
        "equipment":  {"per_floor": (1, 3)},
    },
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
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         {},   # TODO: define strain weights for meth lab
    "casino_botanical": {},   # TODO: define strain weights for casino + botanical
    "the_underprison":  {},   # TODO: define strain weights for The Underprison
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
        ("alcohol_drink", 1.5),
        ("food", 1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         [],   # TODO
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
}

# Secondary alcohol drink table — rolled when alcohol_drink is selected
ALCOHOL_DRINK_SUBTABLE = [
    ("40oz", 1),
    ("fireball_shooter", 1),
    ("malt_liquor", 1),
    ("wizard_mind_bomb", 1),
    ("homemade_hennessy", 1),
    ("steel_reserve", 1),
]

ZONE_MATERIAL_TABLES = {
    "crack_den": [
        ("rolling_paper", 6),   # 3× more likely than nugs
        ("kush",          2),   # 2× more likely than nugs
        ("weed_nug",      1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         [],   # TODO
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
}

ZONE_TOOL_TABLES = {
    "crack_den": [
        ("grinder",   1),
        ("fry_daddy", 1),
        ("bic_torch", 1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         [],   # TODO
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
}

ZONE_FOOD_TABLES = {
    "crack_den": [
        ("chicken", 1),
        ("instant_ramen", 1),
        ("hot_cheetos", 1),
        ("cornbread", 1),
        ("corn_dog", 1),
        ("lightskin_beans", 1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         [],   # TODO
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
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
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": {          # TODO
        "type_weights":      [("weapon", 1), ("ring", 2), ("neck", 1), ("feet", 1)],
        "ring_tier_weights": [("minor", 6), ("greater", 2)],
    },
    "casino_botanical": {  # TODO
        "type_weights":      [("weapon", 1), ("ring", 2), ("neck", 1), ("feet", 1)],
        "ring_tier_weights": [("minor", 4), ("greater", 3)],
    },
    "the_underprison": {   # TODO
        "type_weights":      [("weapon", 1), ("ring", 2), ("neck", 1), ("feet", 1)],
        "ring_tier_weights": [("minor", 2), ("greater", 4)],
    },
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

    For items with only primary_skill:
        effective_weight = base_weight * (level + 1)

    For items with secondary_skill (and optional tertiary_skill):
        effective_weight = base_weight * (1.0 + primary_level * 1.0 + secondary_level * 0.5 + tertiary_level * 0.33)
    """
    item_ids = [t[0] for t in table]
    weights  = []
    for item_id, base_w in table:
        if not use_skill_weighting or not player_skills:
            weights.append(base_w)
            continue

        primary_skill = ITEM_DEFS.get(item_id, {}).get("primary_skill")
        secondary_skill = ITEM_DEFS.get(item_id, {}).get("secondary_skill")
        tertiary_skill = ITEM_DEFS.get(item_id, {}).get("tertiary_skill")

        try:
            primary_level = player_skills.get(primary_skill).level if primary_skill else 0
        except (KeyError, AttributeError):
            primary_level = 0

        if secondary_skill:
            # Multi-skill scaling formula
            try:
                secondary_level = player_skills.get(secondary_skill).level
            except (KeyError, AttributeError):
                secondary_level = 0

            tertiary_level = 0
            if tertiary_skill:
                try:
                    tertiary_level = player_skills.get(tertiary_skill).level
                except (KeyError, AttributeError):
                    tertiary_level = 0

            weight = base_w * (1.0 + primary_level * 1.0 + secondary_level * 0.5 + tertiary_level * 0.33)
            weights.append(weight)
        else:
            # Single skill: original formula
            weights.append(base_w * (primary_level + 1))

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

def pick_strain(zone: str):
    """Pick a strain using zone-weighted distribution. Returns None if zone has no strains."""
    return _pick_strain(zone)


def pick_random_consumable(zone: str) -> tuple:
    """Pick one random consumable (item_id, strain_or_None) from the zone's consumable table.

    Resolves alcohol_drink and food sub-tables. No skill weighting applied.
    Falls back to ('joint', None) if the zone has no consumable table.
    """
    table = ZONE_CONSUMABLE_TABLES.get(zone, [])
    if not table:
        return ("joint", None)

    item_id = _weighted_pick(table, None, use_skill_weighting=False)

    if item_id == "alcohol_drink":
        item_id = _weighted_pick(ALCOHOL_DRINK_SUBTABLE, None, use_skill_weighting=False)
    elif item_id == "food":
        food_table = ZONE_FOOD_TABLES.get(zone, [])
        if food_table:
            item_id = _weighted_pick(food_table, None, use_skill_weighting=False)

    strain = _pick_strain(zone) if item_id in _STRAIN_ITEMS else None
    return (item_id, strain)


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

                # Special case: alcohol_drink picks a specific drink from subtable
                if item_id == "alcohol_drink":
                    item_id = _weighted_pick(ALCOHOL_DRINK_SUBTABLE, player_skills, use_skill_weighting=True)
                # Special case: food picks a specific food from zone table
                elif item_id == "food":
                    food_table = ZONE_FOOD_TABLES.get(zone, [])
                    if food_table:
                        item_id = _weighted_pick(food_table, player_skills, use_skill_weighting=True)

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
