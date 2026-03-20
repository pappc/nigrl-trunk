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
from items import ITEM_DEFS, get_random_chain, get_random_hat
from foods import FOOD_DEFS


# ---------------------------------------------------------------------------
# Zone floor budgets
# ---------------------------------------------------------------------------

ZONE_LOOT_CONFIG = {
    "crack_den": {
        "consumable": {"per_floor": (8, 12)},
        "tool":       {"per_floor": (0, 2)},
        "equipment":  {"per_floor": (1, 3)},
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": {
        "consumable": {"per_floor": (16, 20)},
        "tool":       {"per_floor": (0, 2)},
        "equipment":  {"per_floor": (2, 4)},
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
    "meth_lab": {
        # OG strains (static weights)
        "OG Kush":         6,
        "Columbian Gold":  6,
        "Agent Orange":    5,
        "Jungle Boyz":     5,
        "Dosidos":         5,
        "Blue Lobster":    4,
        # Meth lab strains (dynamic — base weight, scaled by player stats)
        "Iron Lung":       5,
        "Skywalker OG":    5,
        "Street Scholar":  5,
        "Kushenheimer":    5,
        "Nigle Fart":      5,
        "Purple Halt":     5,
    },
    "casino": {},   # TODO: define strain weights for casino
    "the_underprison":  {},   # TODO: define strain weights for The Underprison
    "Botanical Weed Garden":  {},   # TODO
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
        ("weed_product", 1.5),
        ("drinks", 1),
        ("food", 1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": [
        ("weed_product", 1, ["Smoking", "Rolling"]),
        ("blue_meth", 0.5, "Meth-Head"),
        ("food", 1, "Munching"),
        ("meth_lab_drink", 1, ["Alcoholism", "Drinking"]),
    ],
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
}

# Secondary drinks table — rolled when drinks is selected
DRINKS_SUBTABLE = [
    ("40oz", 1),
    ("fireball_shooter", 1),
    ("malt_liquor", 1),
    ("wizard_mind_bomb", 1),
    ("homemade_hennessy", 1),
    ("steel_reserve", 1),
    ("speedball", 1),
    ("purple_drank", 0.5),
    ("blue_drank", 0.5),
    ("red_drank", 0.5),
    ("green_drank", 0.5),
]

# Secondary weed product table — rolled when weed_product is selected
WEED_PRODUCT_SUBTABLE = [
    ("joint",    2),
    ("weed_nug", 1),
    ("kush",     1),
]

# Secondary meth lab drink table — rolled when meth_lab_drink is selected
METH_LAB_DRINK_SUBTABLE = [
    # Meth lab unique drinks
    ("mana_drink", 2),
    ("virulent_vodka", 2),
    ("five_loco", 2),
    ("white_gonster", 2),
    ("alco_seltzer", 2),
    ("dead_shot_daiquiri", 2),
    ("platinum_reserve", 2),
    # Crack den drinks
    ("40oz", 10),
    ("fireball_shooter", 2),
    ("malt_liquor", 10),
    ("wizard_mind_bomb", 2),
    ("homemade_hennessy", 2),
    ("steel_reserve", 10),
    ("speedball", 2),
    # Dranks
    ("purple_drank", 1),
    ("blue_drank", 1),
    ("red_drank", 1),
    ("green_drank", 1),
]

ZONE_TOOL_TABLES = {
    "crack_den": [
        ("grinder",        1),
        ("fry_daddy",      1),
        ("bic_torch",      1),
        ("pack_of_cones",  1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab":         [("grinder", 1), ("fry_daddy", 1), ("xl_bic_torch", 1), ("pack_of_cones", 1)],
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
        ("protein_powder", 1),
        ("muffin", 1),
    ],
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": [
        ("instant_ramen", 2, "Meth-Head"),
        ("cornbread", 2, "Smartsness"),
        ("corn_dog", 2),
        ("hot_cheetos", 2),
        ("lightskin_beans", 2, "Smartsness"),
        ("muffin", 3, "Smartsness"),
        ("protein_powder", 3, "Smacking"),
        ("altoid", 5, "White Power"),
        ("asbestos", 5, "Chemical Warfare"),
        ("rad_away", 5, "Glow Up"),
        ("radbar", 5, "Nuclear Research"),
        ("jell_o", 3, "Smartsness"),
        ("meatball_sub", 3, "Smartsness"),
        ("heinz_baked_beans", 3, "Smartsness"),
    ],
    "casino_botanical": [],   # TODO
    "the_underprison":  [],   # TODO
}


# ---------------------------------------------------------------------------
# Equipment config per zone
# ---------------------------------------------------------------------------

ZONE_EQUIPMENT_CONFIG = {
    "crack_den": {
        "type_weights":      [("weapon", 3), ("ring", 4), ("neck", 3), ("feet", 2), ("hat", 1)],
        "weapon_type_weights": [("beating", 1, "Beating"), ("stabbing", 1, "Stabbing")],
        "ring_tier_weights": [("minor", 8), ("greater", 1)],
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    "meth_lab": {
        "type_weights":      [("weapon", 1), ("ring", 2), ("neck", 1), ("feet", 1), ("hat", 1), ("gun", 1)],
        "weapon_type_weights": [("beating", 1, "Beating"), ("stabbing", 1, "Stabbing")],
        "ring_tier_weights": [("minor", 3), ("greater", 8), ("divine", 1), ("advanced", 3)],
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

# Meth lab strains linked to player stats for dynamic weighting
_STRAIN_STAT_MAP = {
    "Iron Lung":      "effective_constitution",
    "Skywalker OG":   "effective_strength",
    "Street Scholar":  "effective_street_smarts",
    "Kushenheimer":   "effective_book_smarts",
    "Nigle Fart":     "effective_tolerance",
    "Purple Halt":    "effective_swagger",
}


def _pick_strain(zone, player_stats=None):
    """Pick a strain using zone-weighted distribution.

    For meth_lab zone, strains linked to player stats get dynamic weights:
    - Top stat tier (highest value) → 2x base weight
    - Bottom stat tier (lowest value) → 0.5x base weight
    - Middle → 1x base weight
    Ties are promoted: all stats sharing the top value get 2x, etc.
    If all stats are equal, everything stays at base weight.
    """
    weights = ZONE_STRAIN_WEIGHTS.get(zone)
    if not weights:
        return None

    keys = list(weights.keys())
    vals = list(weights.values())

    # Apply dynamic stat scaling for meth_lab strains
    if zone == "meth_lab" and player_stats:
        stat_values = {
            attr: getattr(player_stats, attr, 8)
            for attr in _STRAIN_STAT_MAP.values()
        }
        # Sort unique stat values descending to find tier boundaries
        unique_vals = sorted(set(stat_values.values()), reverse=True)

        if len(unique_vals) >= 3:
            # At least 3 distinct values: top tier = highest, bottom tier = lowest
            top_val = unique_vals[0]
            bot_val = unique_vals[-1]
            for i, strain in enumerate(keys):
                attr = _STRAIN_STAT_MAP.get(strain)
                if attr:
                    sv = stat_values[attr]
                    if sv == top_val:
                        vals[i] *= 2.0
                    elif sv == bot_val:
                        vals[i] *= 0.5
        elif len(unique_vals) == 2:
            # Two distinct values: higher group = top, lower group = bottom
            top_val = unique_vals[0]
            bot_val = unique_vals[1]
            for i, strain in enumerate(keys):
                attr = _STRAIN_STAT_MAP.get(strain)
                if attr:
                    sv = stat_values[attr]
                    if sv == top_val:
                        vals[i] *= 2.0
                    elif sv == bot_val:
                        vals[i] *= 0.5
        # len == 1: all stats equal, no scaling

    return random.choices(keys, weights=vals, k=1)[0]


def _get_skill_level(player_skills, skill_key):
    """Resolve a skill key to a level. skill_key is a string (single skill)
    or a list of strings (take the highest level among them)."""
    if isinstance(skill_key, list):
        best = 0
        for s in skill_key:
            try:
                best = max(best, player_skills.get(s).level)
            except (KeyError, AttributeError):
                pass
        return best
    try:
        return player_skills.get(skill_key).level
    except (KeyError, AttributeError):
        return 0


def _weighted_pick(table, player_skills, use_skill_weighting=True):
    """Pick one item_id from a table, applying skill multipliers when requested.

    Table entries can be 2-tuples (item_id, base_weight) or 3-tuples
    (item_id, base_weight, skill_key) where skill_key is a string or list
    of strings. For lists, the highest skill level is used.

    effective_weight = base_weight * (skill_level + 1)

    Falls back to ITEM_DEFS/FOOD_DEFS "skill" key if no inline skill_key.
    """
    item_ids = [t[0] for t in table]
    weights  = []
    for entry in table:
        item_id = entry[0]
        base_w  = entry[1]
        inline_skill = entry[2] if len(entry) > 2 else None

        if not use_skill_weighting or not player_skills:
            weights.append(base_w)
            continue

        # Inline skill from table entry takes priority
        if inline_skill is not None:
            level = _get_skill_level(player_skills, inline_skill)
            weights.append(base_w * (level + 1))
            continue

        defn = ITEM_DEFS.get(item_id) or FOOD_DEFS.get(item_id, {})

        # Single "skill" key from item/food definition
        skill = defn.get("skill")
        if skill is not None:
            level = _get_skill_level(player_skills, skill)
            weights.append(base_w * (level + 1))
            continue

        # Legacy: primary_skill / secondary_skill / tertiary_skill
        primary_skill = defn.get("primary_skill")
        secondary_skill = defn.get("secondary_skill")
        tertiary_skill = defn.get("tertiary_skill")

        try:
            primary_level = player_skills.get(primary_skill).level if primary_skill else 0
        except (KeyError, AttributeError):
            primary_level = 0

        if secondary_skill:
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
            weights.append(base_w * (primary_level + 1))

    return random.choices(item_ids, weights=weights, k=1)[0]


def _resolve_equipment(zone, player_skills=None):
    """Pick one equipment item_id for the given zone, or None on failure."""
    config   = ZONE_EQUIPMENT_CONFIG[zone]
    eq_types = [t[0] for t in config["type_weights"]]
    eq_wts   = [t[1] for t in config["type_weights"]]
    eq_type  = random.choices(eq_types, weights=eq_wts, k=1)[0]

    if eq_type == "weapon":
        # Roll weapon_type (beating vs stabbing) weighted by skill level
        weapon_type_table = config.get("weapon_type_weights")
        if weapon_type_table and player_skills:
            wt_types = []
            wt_wts = []
            for wtype, base_w, skill_key in weapon_type_table:
                level = _get_skill_level(player_skills, skill_key) if skill_key else 0
                wt_types.append(wtype)
                wt_wts.append(base_w * (level + 1))
            chosen_type = random.choices(wt_types, weights=wt_wts, k=1)[0]
            candidates = [
                iid for iid, defn in ITEM_DEFS.items()
                if defn.get("subcategory") == "weapon"
                and defn.get("weapon_type") == chosen_type
                and zone in defn.get("zones", [])
            ]
        else:
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

    elif eq_type == "hat":
        return get_random_hat(zone)

    elif eq_type == "gun":
        candidates = [
            iid for iid, defn in ITEM_DEFS.items()
            if defn.get("subcategory") == "gun"
            and zone in defn.get("zones", [])
        ]
        return random.choice(candidates) if candidates else None

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pick_strain(zone: str, player_stats=None):
    """Pick a strain using zone-weighted distribution. Returns None if zone has no strains."""
    return _pick_strain(zone, player_stats)


def pick_random_consumable(zone: str, player_stats=None) -> tuple:
    """Pick one random consumable (item_id, strain_or_None) from the zone's consumable table.

    Resolves drinks and food sub-tables. No skill weighting applied.
    Falls back to ('joint', None) if the zone has no consumable table.
    """
    table = ZONE_CONSUMABLE_TABLES.get(zone, [])
    if not table:
        return ("joint", None)

    item_id = _weighted_pick(table, None, use_skill_weighting=False)

    if item_id == "drinks":
        item_id = _weighted_pick(DRINKS_SUBTABLE, None, use_skill_weighting=False)
    elif item_id == "meth_lab_drink":
        item_id = _weighted_pick(METH_LAB_DRINK_SUBTABLE, None, use_skill_weighting=False)
    elif item_id == "food":
        food_table = ZONE_FOOD_TABLES.get(zone, [])
        if food_table:
            item_id = _weighted_pick(food_table, None, use_skill_weighting=False)
    elif item_id == "weed_product":
        item_id = _weighted_pick(WEED_PRODUCT_SUBTABLE, None, use_skill_weighting=False)

    strain = _pick_strain(zone, player_stats) if item_id in _STRAIN_ITEMS else None
    return (item_id, strain)


def generate_floor_loot(zone, floor_num, player_skills=None, player_stats=None):
    """Generate a flat list of (item_id, strain_or_None) for one floor.

    zone         : zone key, e.g. "crack_den"
    floor_num    : 0-based floor index (reserved for future floor-scaling)
    player_skills: Skills object or None
    player_stats : PlayerStats object or None (used for dynamic strain weighting)
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

                # Special case: drinks picks a specific drink from subtable
                if item_id == "drinks":
                    item_id = _weighted_pick(DRINKS_SUBTABLE, player_skills, use_skill_weighting=True)
                # Special case: meth_lab_drink picks from meth lab drink subtable
                elif item_id == "meth_lab_drink":
                    item_id = _weighted_pick(METH_LAB_DRINK_SUBTABLE, player_skills, use_skill_weighting=True)
                # Special case: food picks a specific food from zone table
                elif item_id == "food":
                    food_table = ZONE_FOOD_TABLES.get(zone, [])
                    if food_table:
                        item_id = _weighted_pick(food_table, player_skills, use_skill_weighting=True)
                # Special case: weed_product picks from weed subtable
                elif item_id == "weed_product":
                    item_id = _weighted_pick(WEED_PRODUCT_SUBTABLE, player_skills, use_skill_weighting=True)

                strain  = _pick_strain(zone, player_stats) if item_id in _STRAIN_ITEMS else None
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
            item_id = _resolve_equipment(zone, player_skills)
            if item_id:
                result.append((item_id, None))

    return result
