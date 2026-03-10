"""
Item definitions, crafting recipes, and helper functions.

All item metadata lives here to keep Entity lean.
Entity objects link to definitions via their `item_id` field.
"""

import math as _math
from foods import FOOD_DEFS, get_food_prefix_def

# ---------------------------------------------------------------------------
# Marijuana strains
# ---------------------------------------------------------------------------

STRAINS = [
    "OG Kush",
    "Columbian Gold",
    "Jungle Boyz",
    "Agent Orange",
    "Blue Lobster",
    "Dosidos",
]

# Smoking skill XP values per strain
# Higher complexity/power strains = more XP
STRAIN_SMOKING_XP = {
    "OG Kush": 50,           # Simple healing strain
    "Agent Orange": 75,      # Debuff effects
    "Columbian Gold": 100,   # Power-based buff with DoT
    "Blue Lobster": 125,     # Complex damage/defense mechanic
    "Jungle Boyz": 150,      # Multiple attack-based effects
    "Dosidos": 175,          # Complex spellcasting effects
}

# Rolling skill XP values per strain
# Grinding and rolling give similar XP per strain complexity
STRAIN_ROLLING_XP = {
    "OG Kush": 50,           # Simple healing strain
    "Agent Orange": 75,      # Debuff effects
    "Columbian Gold": 100,   # Power-based buff with DoT
    "Blue Lobster": 125,     # Complex damage/defense mechanic
    "Jungle Boyz": 150,      # Multiple attack-based effects
    "Dosidos": 175,          # Complex spellcasting effects
}

# Munching skill XP values per food
# Eating food grants XP based on food type and effects
# ---------------------------------------------------------------------------
# Tolerance bonus-roll thresholds per strain
#
# first_bonus_roll: minimum Tolerance to gain 1 extra roll (take best)
# add_bonus_roll:   each additional N Tolerance beyond first grants another roll
# ---------------------------------------------------------------------------
STRAIN_TOLERANCE_THRESHOLDS = {
    "OG Kush":       {"first_bonus_roll": 8,  "add_bonus_roll": 5},
    "Columbian Gold": {"first_bonus_roll": 8,  "add_bonus_roll": 5},
    "Agent Orange":  {"first_bonus_roll": 9,  "add_bonus_roll": 6},
    "Jungle Boyz":   {"first_bonus_roll": 10, "add_bonus_roll": 6},
    "Blue Lobster":  {"first_bonus_roll": 10, "add_bonus_roll": 7},
    "Dosidos":       {"first_bonus_roll": 9,  "add_bonus_roll": 6},
}


def calc_tolerance_rolls(strain: str, tolerance: int) -> tuple[int, int]:
    """Return (num_rolls, roll_floor) based on tolerance and strain thresholds.

    num_rolls: how many d100 to roll (take best). Minimum 1.
    roll_floor: minimum value each roll can produce.
    """
    thresholds = STRAIN_TOLERANCE_THRESHOLDS.get(strain)
    if not thresholds:
        return 1, 0

    first = thresholds["first_bonus_roll"]
    add = thresholds["add_bonus_roll"]

    if tolerance >= first:
        bonus = 1 + (tolerance - first) // add
    else:
        bonus = 0
    num_rolls = 1 + bonus

    # Roll floor: max(0, (tolerance - 12) // 2)
    roll_floor = max(0, (tolerance - 12) // 2)

    return num_rolls, roll_floor


FOOD_MUNCHING_XP = {
    "chicken": 50,           # Simple healing food
    "instant_ramen": 60,     # Speed boost (value 30 × 2)
    "hot_cheetos": 110,      # Complex buff (stats + melee effect + expire effect)
    "cornbread": 50,         # Moderate: stat buff + spell charges
    "corn_dog": 40,          # Quick eat, melee charges
    "lightskin_beans": 70,   # Long eat, powerful AoE spell
    "leftovers": 25,         # Proc'd from Better Later perk
}

# Deep-Frying skill XP values per food
# Frying food grants XP equal to the material's value × 2
ITEM_DEEP_FRYING_XP = {
    "chicken": 50,           # value 25 × 2
    "instant_ramen": 60,     # value 30 × 2
    "hot_cheetos": 80,       # value 40 × 2
}


# ---------------------------------------------------------------------------
# Strain effect tables
#
# Each entry: (low, high, player_effect, monster_effect)
#   monster_effect=None means same as player_effect
# Effect dict types:
#   {"type": "heal_percent",  "amount": float}  — heal X% of max HP
#   {"type": "heal_flat",     "amount": int}    — heal N HP
#   {"type": "damage_percent","amount": float}  — deal X% of max HP as damage
#   {"type": "none"}                             — no effect
# ---------------------------------------------------------------------------

STRAIN_TABLES = {
    "Agent Orange": [
        (90, 100, {"type": "remove_debuffs_zoned_out"},                                          None),
        (50,  89, {"type": "remove_debuffs"},                                                    None),
        (30,  49, {"type": "random_dot_debuff", "duration_mode": "tlr"},                        None),
        (11,  29, {"type": "random_dot_debuff", "duration": 20},                                None),
        ( 1,  10, {"type": "agent_orange_debuff", "duration": 10},                              None),
    ],
    "Blue Lobster": [
        (90, 100, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        (83,  89, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        (60,  82, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        (45,  59, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        (20,  44, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        ( 5,  19, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
        ( 1,   4, {"type": "blue_lobster"},                                                      {"type": "blue_lobster"}),
    ],
    "Columbian Gold": [
        (99, 100, {"type": "invulnerable",   "duration": 10},                        None),
        (91,  98, {"type": "cg_buff_debuff", "duration": 10},                        None),
        (66,  90, {"type": "damage_flat",    "amount": 10},                          None),
        (31,  65, {"type": "damage_stsmt",   "base": 20, "min": 10},                 None),
        (11,  30, {"type": "damage_stsmt",   "base": 30, "min": 10},                 None),
        ( 1,  10, {"type": "damage_percent", "amount": 0.5},                         None),
    ],
    "Jungle Boyz": [
        (81, 100, {"type": "jb_glory_fists",      "duration": 20}, {"type": "jb_soul_pair"}),
        (61,  80, {"type": "jb_lifesteal",         "duration":  8}, {"type": "jb_heal_damage"}),
        (41,  60, {"type": "jb_crippling_attacks", "duration": 10}, {"type": "jb_crippled"}),
        (21,  40, {"type": "jb_fiery_fists",       "duration": 10}, {"type": "jb_monster_ignite"}),
        ( 1,  20, {"type": "jb_self_reflection",   "duration": 10}, {"type": "none"}),
    ],
    "OG Kush": [
        (95, 100, {"type": "heal_percent",    "amount": 1.0},  None),
        (90,  94, {"type": "heal_percent",    "amount": 0.75}, None),
        (80,  89, {"type": "heal_flat",       "amount": 100},  None),
        (66,  79, {"type": "heal_flat",       "amount": 70},   None),
        (40,  65, {"type": "heal_flat",       "amount": 50},   None),
        (20,  39, {"type": "heal_flat",       "amount": 20},   None),
        (10,  19, {"type": "none"},                            None),
        ( 1,   9, {"type": "damage_percent",  "amount": 0.1},  None),
    ],
    "Dosidos": [
        (87, 100, {"type": "dosidos_dimension_door"},                   {"type": "dosidos_bksmt_buff", "amount": 10}),
        (79,  86, {"type": "dosidos_chain_lightning", "total_hits": 4}, {"type": "dosidos_bksmt_buff", "amount":  9}),
        (60,  78, {"type": "dosidos_chain_lightning", "total_hits": 2}, {"type": "dosidos_bksmt_buff", "amount":  8}),
        (45,  59, {"type": "dosidos_ray_of_frost",    "count": 3},      {"type": "dosidos_bksmt_buff", "amount":  7}),
        (35,  44, {"type": "dosidos_warp"},                              {"type": "dosidos_bksmt_buff", "amount":  5}),
        (20,  34, {"type": "dosidos_firebolt",        "count": 2},      {"type": "dosidos_bksmt_buff", "amount":  4}),
        ( 1,  19, {"type": "dosidos_arcane_missile",  "count": 3},      {"type": "dosidos_bksmt_buff", "amount":  2}),
    ],
}


def get_strain_effect(strain, roll, target="player"):
    """Return the effect dict for a strain given a 1-100 roll and target.

    target: "player" or "monster"
    Returns an effect dict, or None if the strain has no table entry.
    When monster_effect is None the player_effect is used for both.
    """
    table = STRAIN_TABLES.get(strain)
    if not table:
        return None
    for low, high, player_eff, monster_eff in table:
        if low <= roll <= high:
            if target == "monster":
                return monster_eff if monster_eff is not None else player_eff
            return player_eff
    return None


# ---------------------------------------------------------------------------
# Strain metadata: abbreviations and colors
# ---------------------------------------------------------------------------

def abbreviate_strain(strain_name):
    """Create a short abbreviation for a strain name to fit in inventory.
    Examples: "OG Kush" -> "OGK", "Columbian Gold" -> "CG", "Dosidos" -> "SD"
    """
    words = strain_name.split()
    if len(words) == 1:
        # Single word: take first 3 chars
        return words[0][:3].upper()
    else:
        # Multiple words: take first letter of each word
        return "".join(w[0] for w in words).upper()


def get_strain_color(strain_name):
    """Generate a unique, deterministic color for a strain based on its name.
    Each strain gets its own distinct, bright color.
    """
    # Hardcoded colors per strain for guaranteed uniqueness and thematic fit
    strain_colors = {
        "OG Kush": (150, 200, 100),         # Deep green
        "Columbian Gold": (220, 150, 50),   # Gold/Orange
        "Jungle Boyz": (100, 200, 100),     # Bright green
        "Agent Orange": (220, 120, 50),     # Orange
        "Blue Lobster": (100, 150, 220),    # Blue
        "Dosidos": (200, 180, 50),      # Yellow-Gold
    }

    return strain_colors.get(strain_name, (150, 150, 150))  # Fallback gray

# ---------------------------------------------------------------------------
# Item definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Ring definitions
#
# Each ring has:
#   tags        : list of classification strings (e.g. ["minor"]) used by
#                 get_random_ring_by_tags() to filter candidates.
#   stat_bonus  : dict mapping a PlayerStats attribute name to the bonus value.
#                 Applied additively to the player's stats while the ring is equipped.
# ---------------------------------------------------------------------------

_RING_STAT_DEFS = [
    # (stat_attr,       id_key,   short_label, base_color)
    ("constitution",  "con",   "CON",   (180, 80,  80)),
    ("strength",      "str",   "STR",   (200, 120, 60)),
    ("book_smarts",   "bksmt", "BKSMT", (100, 160, 220)),
    ("street_smarts", "stsmt", "STSMT", (80,  200, 150)),
    ("tolerance",     "tol",   "TOL",   (160, 100, 200)),
    ("swagger",       "swag",  "SWAG",  (220, 200, 80)),
]

def _build_minor_rings():
    """Generate the 18 minor ring item definitions (6 stats × +1/+2/+3)."""
    rings = {}
    for stat_attr, id_key, label, (r, g, b) in _RING_STAT_DEFS:
        for bonus in (1, 2, 3):
            item_id = f"ring_minor_{id_key}_{bonus}"
            # Brighten color slightly per tier
            rings[item_id] = {
                "name": f"+{bonus} ring of {id_key}",
                "char": "o",
                "color": (
                    min(255, r + (bonus - 1) * 15),
                    min(255, g + (bonus - 1) * 15),
                    min(255, b + (bonus - 1) * 15),
                ),
                "category": "equipment",
                "subcategory": "ring",
                "equip_slot": "ring",
                "power_bonus": 0,
                "defense_bonus": 0,
                "stat_bonus": {stat_attr: bonus},
                "value": 20 + bonus * 20,
                "tags": ["minor"],
                "zones": ["crack_den"],
                "use_verb": None,
                "use_effect": None,
            }
    return rings

_MINOR_RINGS = _build_minor_rings()


def _build_greater_rings():
    """Generate the 18 greater ring item definitions (6 stats × +4/+5/+6)."""
    rings = {}
    for stat_attr, id_key, label, (r, g, b) in _RING_STAT_DEFS:
        for bonus in (4, 5, 6):
            item_id = f"ring_greater_{id_key}_{bonus}"
            # Brighten color more aggressively for higher tiers
            rings[item_id] = {
                "name": f"+{bonus} ring of {id_key}",
                "char": "o",
                "color": (
                    min(255, r + (bonus - 1) * 12),
                    min(255, g + (bonus - 1) * 12),
                    min(255, b + (bonus - 1) * 12),
                ),
                "category": "equipment",
                "subcategory": "ring",
                "equip_slot": "ring",
                "power_bonus": 0,
                "defense_bonus": 0,
                "stat_bonus": {stat_attr: bonus},
                "value": 20 + bonus * 20,
                "tags": ["greater"],
                "zones": ["crack_den"],
                "use_verb": None,
                "use_effect": None,
            }
    return rings

_GREATER_RINGS = _build_greater_rings()


def _build_divine_rings():
    """Generate the 18 divine ring item definitions (6 stats × +7/+8/+9)."""
    rings = {}
    for stat_attr, id_key, label, (r, g, b) in _RING_STAT_DEFS:
        for bonus in (7, 8, 9):
            item_id = f"ring_divine_{id_key}_{bonus}"
            # Brighten color even more for divine rings
            rings[item_id] = {
                "name": f"+{bonus} ring of {id_key}",
                "char": "o",
                "color": (
                    min(255, r + (bonus - 1) * 10),
                    min(255, g + (bonus - 1) * 10),
                    min(255, b + (bonus - 1) * 10),
                ),
                "category": "equipment",
                "subcategory": "ring",
                "equip_slot": "ring",
                "power_bonus": 0,
                "defense_bonus": 0,
                "stat_bonus": {stat_attr: bonus},
                "value": 20 + bonus * 20,
                "tags": ["divine"],
                "zones": [],
                "use_verb": None,
                "use_effect": None,
            }
    return rings

_DIVINE_RINGS = _build_divine_rings()


def _build_advanced_rings():
    """Generate the 45 advanced ring item definitions (15 stat pairs × +3/+4/+5).

    Each stat pair gets 3 bonus values, both stats receive the same bonus.
    Example: +3 ring of str and con, +4 ring of str and con, +5 ring of str and con
    """
    from itertools import combinations

    rings = {}

    # Get all pairs of stats (order: str < con < bksmt < stsmt < tol < swag)
    stat_indices = list(range(len(_RING_STAT_DEFS)))
    stat_pairs = list(combinations(stat_indices, 2))

    for idx1, idx2 in stat_pairs:
        stat_attr_1, id_key_1, label_1, (r1, g1, b1) = _RING_STAT_DEFS[idx1]
        stat_attr_2, id_key_2, label_2, (r2, g2, b2) = _RING_STAT_DEFS[idx2]

        for bonus in (3, 4, 5):
            item_id = f"ring_advanced_{id_key_1}_{id_key_2}_{bonus}"
            # Average colors from both stats, brighten for divine-tier
            avg_r = (r1 + r2) // 2
            avg_g = (g1 + g2) // 2
            avg_b = (b1 + b2) // 2

            rings[item_id] = {
                "name": f"+{bonus} ring of {id_key_1} and {id_key_2}",
                "char": "o",
                "color": (
                    min(255, avg_r + (bonus - 1) * 10),
                    min(255, avg_g + (bonus - 1) * 10),
                    min(255, avg_b + (bonus - 1) * 10),
                ),
                "category": "equipment",
                "subcategory": "ring",
                "equip_slot": "ring",
                "power_bonus": 0,
                "defense_bonus": 0,
                "stat_bonus": {stat_attr_1: bonus, stat_attr_2: bonus},
                "value": 20 + bonus * 2 * 20,
                "tags": ["advanced"],
                "zones": [],
                "use_verb": None,
                "use_effect": None,
            }
    return rings

_ADVANCED_RINGS = _build_advanced_rings()


# ---------------------------------------------------------------------------
# Chain definitions
# ---------------------------------------------------------------------------
#
# Architecture:
#   _CHAIN_MATERIALS / _CHAIN_BRANDS / _CHAIN_STYLES  — master attribute tables.
#       Changing a value here updates EVERY chain that uses that attribute.
#
#   CHAIN_ZONE_CONFIGS  — per-zone spawn weights referencing master table keys.
#       To make chains spawn in a new area: add an entry here only.
#       To retune spawn rates in an existing zone: edit that zone's weights only.
#
#   _build_chains()  — generates all combinations at import time; merged into ITEM_DEFS.
#   get_random_chain(zone)  — three independent weighted picks using the zone config.
# ---------------------------------------------------------------------------

_CHAIN_BASE_ARMOR = 15

# Master attribute tables — single source of truth.
# Change armor_mod for a material here to affect every chain using that material.
_CHAIN_MATERIALS = {
    "Bronze": {"armor_mod": -5,  "color": (205, 127,  50)},
    "Brass":  {"armor_mod": -1,  "color": (181, 166,  66)},
    "Steel":  {"armor_mod":  2,  "color": (160, 174, 192)},
    "Silver": {"armor_mod": 10,  "color": (192, 192, 192)},
}

# None key = no brand label in the name.
_CHAIN_BRANDS = {
    None:       {"multiplier": 1.0},
    "Fake":     {"multiplier": 0.6},
    "Designer": {"multiplier": 1.6},
}

# None key = no style label in the name.
_CHAIN_STYLES = {
    None:       {"multiplier": 1.0},
    "Bummy":    {"multiplier": 0.5},
    "Ghetto":   {"multiplier": 0.75},
    "Raw":      {"multiplier": 1.35},
    "Iced-Out": {"multiplier": 2.0},
}

# Per-zone spawn weight configs.  Each axis is weighted independently.
# To add a new zone: add a new key with its own weight dicts.
# To change a zone's rates: edit only that zone's entry.
CHAIN_ZONE_CONFIGS = {
    "crack_den": {
        "material_weights": {"Bronze": 1, "Brass": 3, "Steel": 5, "Silver": 2},
        "brand_weights":    {None: 10, "Fake": 3, "Designer": 2},
        "style_weights":    {None: 10, "Bummy": 1, "Ghetto": 4, "Raw": 4, "Iced-Out": 1},
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    # TODO: tune per zone as content is built out
    "meth_lab": {
        "material_weights": {"Bronze": 1, "Brass": 2, "Steel": 6, "Silver": 1},
        "brand_weights":    {None: 8, "Fake": 4, "Designer": 1},
        "style_weights":    {None: 8, "Bummy": 3, "Ghetto": 5, "Raw": 3, "Iced-Out": 1},
    },
    "casino_botanical": {
        "material_weights": {"Bronze": 1, "Brass": 2, "Steel": 4, "Silver": 4},
        "brand_weights":    {None: 6, "Fake": 2, "Designer": 5},
        "style_weights":    {None: 6, "Bummy": 1, "Ghetto": 2, "Raw": 4, "Iced-Out": 4},
    },
    "the_underprison": {
        "material_weights": {"Bronze": 4, "Brass": 4, "Steel": 2, "Silver": 1},
        "brand_weights":    {None: 12, "Fake": 5, "Designer": 1},
        "style_weights":    {None: 12, "Bummy": 5, "Ghetto": 5, "Raw": 3, "Iced-Out": 1},
    },
}


def _chain_key(name):
    """Convert a display name (or None) to a safe identifier fragment."""
    if name is None:
        return "none"
    return name.lower().replace("-", "_").replace(" ", "_")


def _chain_item_id(material, brand, style):
    return f"chain_{_chain_key(material)}_{_chain_key(brand)}_{_chain_key(style)}"


def _chain_display_name(material, brand, style):
    """Format: (Material) (Style) (Brand) Chain — omit None parts."""
    parts = [material]
    if style is not None:
        parts.append(style)
    if brand is not None:
        parts.append(brand)
    parts.append("Chain")
    return " ".join(parts)


def _chain_armor(material, brand, style):
    """Compute clamped armor value from master tables."""
    armor_mod    = _CHAIN_MATERIALS[material]["armor_mod"]
    brand_multi  = _CHAIN_BRANDS[brand]["multiplier"]
    style_multi  = _CHAIN_STYLES[style]["multiplier"]
    return max(10, min(60, _math.ceil((_CHAIN_BASE_ARMOR + armor_mod) * brand_multi * style_multi)))


def _build_chains():
    """Generate every (material × brand × style) combination from the master tables."""
    chains = {}
    for material, mat_data in _CHAIN_MATERIALS.items():
        for brand in _CHAIN_BRANDS:
            for style in _CHAIN_STYLES:
                item_id = _chain_item_id(material, brand, style)
                armor = _chain_armor(material, brand, style)
                chains[item_id] = {
                    "name":          _chain_display_name(material, brand, style),
                    "char":          '"',
                    "color":         mat_data["color"],
                    "category":      "equipment",
                    "subcategory":   "neck",
                    "equip_slot":    "neck",
                    "power_bonus":   0,
                    "defense_bonus": 0,
                    "armor_bonus":   armor,
                    "value":         round(50 + (armor - 10) * 3),
                    "stat_bonus":    {},
                    "tags":          ["chain"],
                    "zones":         ["crack_den"],
                    "use_verb":      None,
                    "use_effect":    None,
                }
    return chains

_CHAINS = _build_chains()


# ---------------------------------------------------------------------------
# Scuffed Jordans definitions
#
# Each pair rolls 1–15 for armor and gets +1 to one of 6 stats.
# 90 total combinations (6 stats × 15 armor values), pre-generated at import.
# Item IDs: "jordans_{stat_key}_{armor}" e.g. "jordans_constitution_7"
# Names include stat and armor so the player can distinguish pairs in inventory.
# ---------------------------------------------------------------------------

def _build_jordans():
    """Generate all 90 Scuffed Jordans item definitions (6 stats × armor 1–15)."""
    jordans = {}
    for stat_attr, id_key, label, (r, g, b) in _RING_STAT_DEFS:
        for armor in range(1, 16):
            item_id = f"jordans_{id_key}_{armor}"
            # Slightly worn/scuffed color: darken the stat color
            color = (max(0, r - 40), max(0, g - 40), max(0, b - 40))
            jordans[item_id] = {
                "name":          f"Scuffed Jordans (+1 {label}, {armor}AR)",
                "char":          "s",
                "color":         color,
                "category":      "equipment",
                "subcategory":   "feet",
                "equip_slot":    "feet",
                "power_bonus":   0,
                "defense_bonus": 0,
                "armor_bonus":   armor,
                "value":         round(15 + (armor - 1) * (60 / 14)),
                "stat_bonus":    {stat_attr: 1},
                "tags":          ["jordans"],
                "zones":         ["crack_den"],
                "use_verb":      None,
                "use_effect":    None,
            }
    return jordans

_JORDANS = _build_jordans()


def get_random_jordans():
    """Return a random jordans item_id (uniform pick across all 90 combinations)."""
    import random as _random
    return _random.choice(list(_JORDANS.keys()))


def get_random_chain(zone="crack_den"):
    """Return a random chain item_id using per-axis weighted selection for the given zone.

    Each axis (material, brand, style) is picked independently from its weight table,
    so changing one material's weight never affects other axes.
    """
    import random as _random
    config = CHAIN_ZONE_CONFIGS[zone]

    def _wpick(weights_dict):
        keys    = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return _random.choices(keys, weights=weights, k=1)[0]

    material = _wpick(config["material_weights"])
    brand    = _wpick(config["brand_weights"])
    style    = _wpick(config["style_weights"])
    return _chain_item_id(material, brand, style)


ITEM_DEFS = {
    **_MINOR_RINGS,
    **_GREATER_RINGS,
    **_DIVINE_RINGS,
    **_ADVANCED_RINGS,
    **_CHAINS,
    **_JORDANS,
    "knife": {
        "name": "Knife",
        "char": "/",
        "color": (200, 200, 220),
        "category": "equipment",       # tool | equipment | material | consumable
        "subcategory": "weapon",       # weapon | ring  (None for non-equipment)
        "equip_slot": "weapon",        # equipment slot (None if not equippable)
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 6,              # base damage when equipped (overrides player base power)
        "str_req": 1,                  # minimum STR to equip
        "reach": 1,                    # melee reach in Chebyshev tiles (1 = adjacent)
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above str_req
        "weapon_type": "stabbing",
        "value": 35,
        "zones": ["crack_den"],
        "use_verb": None,              # action label shown in menu (None = no direct use)
        "use_effect": None,            # effect dict applied on use (None = no effect)
    },
    "sharp_pole": {
        "name": "Sharp Pole",
        "char": "/",
        "color": (170, 140, 90),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "str_req": 7,
        "reach": 2,
        "str_scaling": {"type": "tiered", "divisor": 1},  # +1 dmg per STR above 7
        "weapon_type": "stabbing",
        "value": 50,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "bottle_tipped_spear": {
        "name": "Bottle Tipped Spear",
        "char": "/",
        "color": (180, 220, 160),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 6,
        "str_req": 5,
        "reach": 2,
        # +1 dmg per 1 STR for first 2 pts over req, then +1 per 2 for next 4,
        # +1 per 3 for next 6, continuing with increasing divisors, capping at +1 per 8 STR
        "str_scaling": {"type": "diminishing_tiered"},
        "weapon_type": "stabbing",
        "value": 40,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "kids_basketball_pole": {
        "name": "Kids Basketball Pole",
        "char": "/",
        "color": (220, 90, 30),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 9,
        "str_req": 12,
        "reach": 3,
        "stat_scaling": {"type": "threshold", "stat": "street_smarts", "threshold": 7},  # +1 dmg per STSMT above 7
        "weapon_type": "blunt",
        "value": 55,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "broken_bong": {
        "name": "Broken Bong",
        "char": "/",
        "color": (80, 200, 180),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 4,
        "str_req": 1,
        "reach": 1,
        "on_hit_effect": {"type": "glass_shards", "stacks": 1, "duration": 5},
        "weapon_type": "stabbing",
        "value": 40,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "broken_crack_pipe": {
        "name": "Broken Crack Pipe",
        "char": "/",
        "color": (200, 175, 145),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 6,
        "str_req": 1,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 1
        "on_hit_skill_xp": {"skill": "Meth-Head", "amount": 1},
        "weapon_type": "stabbing",
        "value": 45,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "crowbar": {
        "name": "Crowbar",
        "char": "/",
        "color": (160, 160, 160),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 5,
        "str_req": 8,
        "reach": 1,
        "weapon_type": "blunt",
        "str_scaling": {"type": "tiered", "divisor": 1},  # +1 per STR above req
        "grants_ability": "pry",
        "value": 50,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "two_by_four": {
        "name": "2x4",
        "char": "/",
        "color": (180, 140, 90),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 2,
        "str_req": 8,
        "reach": 1,
        "weapon_type": "blunt",
        "stat_scaling": {"type": "swagger_linear", "divisor": 2},
        "value": 40,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "crooked_baseball_bat": {
        "name": "Crooked Baseball Bat",
        "char": "/",
        "color": (200, 160, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 12,
        "str_req": 5,
        "reach": 1,
        "weapon_type": "blunt",
        "break_chance": 0.075,
        "value": 60,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "blackjack": {
        "name": "Blackjack",
        "char": "/",
        "color": (80, 80, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 4,
        "str_req": 6,
        "reach": 1,
        "weapon_type": "blunt",
        "str_scaling": {"type": "ratio", "numerator": 2, "denominator": 3},  # +2/3 per STR above req
        "on_hit_stun_chance": 0.10,
        "stun_duration": 3,
        "value": 55,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "bone_club": {
        "name": "Bone Club",
        "char": "/",
        "color": (220, 205, 175),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 5,
        "reach": 1,
        "weapon_type": "blunt",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 5
        "vampiric": 0.30,                                  # heal 30% of damage dealt (after defense)
        "value": 55,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "monkey_wrench": {
        "name": "Monkey Wrench",
        "char": "/",
        "color": (160, 130, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 7,
        "str_req": 7,
        "reach": 1,
        "weapon_type": "blunt",
        "stat_scaling": {"type": "threshold", "stat": "street_smarts", "threshold": 5},  # +1 per STSMT above 5
        "on_hit_disarm_chance": 0.20,
        "disarm_duration": 3,
        "value": 52,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "masonry_hammer": {
        "name": "Masonry Hammer",
        "char": "/",
        "color": (170, 100, 60),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "str_req": 9,
        "reach": 1,
        "weapon_type": "blunt",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 9
        "on_hit_sunder": 1,                                # permanently reduce defender.defense by 1 per hit
        "value": 58,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "extension_cord": {
        "name": "Extension Cord",
        "char": "/",
        "color": (220, 100, 30),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 4,
        "str_req": 3,
        "reach": 2,
        "weapon_type": "blunt",
        "stat_scaling": {"type": "swagger_linear", "divisor": 2},  # +1 per 2 SWAGGER
        "on_hit_bounce": {"chance": 0.25, "damage_pct": 0.50},     # 25% chance to arc to nearest adj enemy
        "value": 42,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "weed_nug": {
        "name": "1g nug",  # strain appended in brackets via build_item_name
        "char": "*",
        "color": (50, 180, 50),
        "category": "material",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 15,
        "primary_skill": "Smoking",
        "use_verb": None,
        "use_effect": None,
    },
    "kush": {
        "name": "Kush",  # strain appended in brackets via build_item_name
        "char": "%",
        "color": (80, 220, 80),
        "category": "material",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 15,
        "primary_skill": "Grinding",
        "use_verb": None,
        "use_effect": None,
    },
    "grinder": {
        "name": "Grinder",
        "char": "o",
        "color": (160, 160, 160),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "fry_daddy": {
        "name": "Fry Daddy",
        "char": "Θ",
        "color": (200, 140, 60),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "rolling_paper": {
        "name": "Rolling Paper",
        "char": "~",
        "color": (240, 230, 200),
        "category": "material",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 9,
        "primary_skill": "Rolling",
        "use_verb": None,
        "use_effect": None,
    },
    "spectral_paper": {
        "name": "Spectral Paper",
        "char": "~",
        "color": (180, 180, 255),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 0,
        "primary_skill": "Rolling",
        "use_verb": None,
        "use_effect": None,
    },
    "bic_torch": {
        "name": "BIC Torch",
        "char": "t",
        "color": (255, 165, 0),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 25,
        "primary_skill": "Pyromania",
        "use_verb": "Burn",
        "use_effect": {"type": "torch_burn"},
    },
    "joint": {
        "name": "Joint",  # strain appended in brackets via build_item_name
        "char": "j",
        "color": (255, 255, 150),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 15,
        "primary_skill": "Smoking",
        "use_verb": "Smoke",
        "use_effect": {"type": "strain_roll"},
        "throw_verb": "Throw",
        "throw_effect": {"type": "strain_roll"},
    },
    # Alcohol consumables
    "40oz": {
        "name": "40oz bottle",
        "char": "!",
        "color": (210, 180, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "40oz"},
    },
    "fireball_shooter": {
        "name": "Fireball Shooter",
        "char": "!",
        "color": (255, 80, 30),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "fireball_shooter"},
    },
    "malt_liquor": {
        "name": "Malt Liquor can",
        "char": "!",
        "color": (200, 200, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "malt_liquor"},
    },
    "wizard_mind_bomb": {
        "name": "Wizard Mind Bomb bottle",
        "char": "!",
        "color": (120, 80, 220),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": "Blackkk Magic",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "wizard_mind_bomb"},
    },
    "homemade_hennessy": {
        "name": "Homemade Hennessy bottle",
        "char": "!",
        "color": (200, 150, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": "Smoking",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "homemade_hennessy"},
    },
    "steel_reserve": {
        "name": "Steel Reserve can",
        "char": "!",
        "color": (160, 160, 160),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Alcoholism",
        "secondary_skill": "Drinking",
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "steel_reserve"},
    },
    "chicken": {
        "name": "Chicken",
        "char": "f",
        "color": (200, 180, 140),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 25,
        "primary_skill": "Cooking",
        "secondary_skill": "Eating",
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "chicken"},
    },
    "instant_ramen": {
        "name": "Instant Ramen",
        "char": "f",
        "color": (255, 200, 100),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "instant_ramen"},
    },
    "hot_cheetos": {
        "name": "Hot Cheetos",
        "char": "f",
        "color": (255, 140, 40),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "hot_cheetos"},
    },
    "cornbread": {
        "name": "Cornbread",
        "char": "f",
        "color": (220, 180, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 25,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "cornbread"},
    },
    "corn_dog": {
        "name": "Corn Dog",
        "char": "f",
        "color": (220, 160, 60),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 20,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "corn_dog"},
    },
    "lightskin_beans": {
        "name": "Lightskin Beans",
        "char": "f",
        "color": (160, 200, 120),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 35,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "lightskin_beans"},
    },
    "leftovers": {
        "name": "Leftovers",
        "char": "f",
        "color": (180, 140, 100),
        "category": "food",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 5,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "leftovers"},
    },
    "big_niggas_key": {
        "name": "Big Nigga's Key",
        "char": "~",
        "color": (220, 180, 60),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 0,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
}


# ---------------------------------------------------------------------------
# Item value and skill XP
# ---------------------------------------------------------------------------

# Per-skill multiplier applied to item value to get skill XP.
# Add a new skill here when it needs item-value-based XP gain.
SKILL_VALUE_MULTIPLIERS = {
    "Dismantling": 1.0,
    "Stealing":    0.5,
    "Abandoning":  1.0,
}


def get_item_value(item_id: str) -> int:
    """Return the base value of an item.

    Reads the 'value' field from ITEM_DEFS. Falls back to 10 for unknown items.
    """
    item_def = ITEM_DEFS.get(item_id)
    if item_def is None:
        return 10
    return item_def.get("value", 10)


def get_skill_xp(item_id: str, skill_name: str) -> int:
    """Return the base XP gain for a skill interaction with an item.

    XP = item_value * SKILL_VALUE_MULTIPLIERS[skill_name]
    Falls back to a multiplier of 1.0 for unregistered skills.
    """
    multiplier = SKILL_VALUE_MULTIPLIERS.get(skill_name, 1.0)
    return round(get_item_value(item_id) * multiplier)


def get_deep_frying_xp(food_item_id: str) -> int:
    """Return the base XP gain for deep-frying a food item.

    Returns the XP value from ITEM_DEEP_FRYING_XP dict, or 0 if unknown.
    """
    return ITEM_DEEP_FRYING_XP.get(food_item_id, 0)


# Ring tag helpers
# ---------------------------------------------------------------------------

def get_ring_ids_by_tags(tags):
    """Return all ring item_ids whose tags contain ALL of the specified tags.

    Example: get_ring_ids_by_tags(["minor"])  → all 18 minor ring ids
    """
    tag_set = set(tags)
    return [
        item_id
        for item_id, defn in ITEM_DEFS.items()
        if tag_set.issubset(set(defn.get("tags", [])))
    ]


def get_random_ring_by_tags(tags):
    """Return a random item_id for a ring matching ALL given tags, or None.

    Example: get_random_ring_by_tags(["minor"])  → e.g. "ring_minor_str_2"
    """
    import random as _random
    candidates = get_ring_ids_by_tags(tags)
    return _random.choice(candidates) if candidates else None


# ---------------------------------------------------------------------------
# Crafting recipes
#
# Key: (item_id_a, item_id_b)  — order-independent (both orderings checked)
# Value: {"result": item_id, "consumed": [item_ids that are removed]}
# ---------------------------------------------------------------------------

# Maps prefix-tool item_id -> prefix name it applies
PREFIX_TOOL_ITEMS: dict[str, str] = {
    "fry_daddy": "greasy",
}


RECIPES = {
    ("weed_nug", "grinder"): {
        "result": "kush",
        "consumed": ["weed_nug"],           # grinder is a reusable tool
    },
    ("kush", "rolling_paper"): {
        "result": "joint",
        "consumed": ["kush", "rolling_paper"],
    },
    ("kush", "spectral_paper"): {
        "result": "joint",
        "consumed": ["kush"],               # spectral paper is a reusable tool
    },
}


# ---------------------------------------------------------------------------
# Environment interactions
#
# Key: (item_id, env_feature)  — e.g. ("raw_meat", "fire")
# Value: {"result": item_id or None, "consumed": [item_ids removed],
#         "message": str}
# ---------------------------------------------------------------------------

ENV_INTERACTIONS = {
    # placeholder entries — expand as environment features are added
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def build_item_name(item_id, strain=None):
    """Build the full item name, including strain name if applicable.
    For cannabis items: "1g nug OG Kush", "Joint Dosidos", etc.
    For other items: just returns the base name."""
    defn = ITEM_DEFS.get(item_id)
    if not defn:
        return "Unknown"

    base_name = defn["name"]

    # Cannabis items with strain names
    if item_id in ("weed_nug", "kush", "joint") and strain:
        return f"{base_name} {strain}"

    return base_name


def build_inventory_display_name(item_id, strain, quantity, prefix=None, charges=None, max_charges=None):
    """Build the inventory panel display name for an item, respecting gram-based naming.

    weed_nug: "1g nug OG Kush" / "3g nugs OG Kush"
    kush:     "1g OG Kush"     / "3g OG Kush"
    prefixed food: "Greasy Chicken (2/2)"
    others:   base name + " x{n}" suffix when quantity > 1
    """
    qty = quantity or 1
    strain_part = f" {strain}" if strain else ""

    if item_id == "weed_nug":
        noun = "Nugs" if qty > 1 else "Nug"
        return f"{qty}g {noun}{strain_part}"

    if item_id == "kush":
        return f"{qty}g{strain_part}"

    base = build_item_name(item_id, strain)

    if prefix is not None and charges is not None and max_charges is not None:
        pdef = get_food_prefix_def(prefix)
        adj = pdef["display_adjective"] if pdef else prefix.title()
        return f"{adj} {base} ({charges}/{max_charges})"

    if qty > 1:
        return f"{base} x{qty}"
    return base


def get_item_def(item_id):
    """Return the definition dict for an item_id, or None."""
    return ITEM_DEFS.get(item_id)


_STACKABLE_CATEGORIES = {"material", "consumable"}

def is_stackable(item_id):
    """Return True if this item's category allows stacking (material or consumable)."""
    defn = ITEM_DEFS.get(item_id)
    return bool(defn and defn.get("category") in _STACKABLE_CATEGORIES)


def find_recipe(item_id_a, item_id_b):
    """Look up a recipe by two item_ids (order-independent).
    Returns recipe dict or None."""
    return RECIPES.get((item_id_a, item_id_b)) or RECIPES.get((item_id_b, item_id_a))


def get_craft_result_strain(item_a, item_b):
    """Determine the strain for a crafting result based on inputs.
    Returns the strain from the appropriate input item, or None.
    - weed_nug + grinder -> kush: preserve nug's strain
    - kush + rolling_paper -> joint: preserve kush's strain
    """
    if item_a.item_id == "weed_nug" and item_b.item_id == "grinder":
        return item_a.strain
    elif item_a.item_id == "grinder" and item_b.item_id == "weed_nug":
        return item_b.strain
    elif item_a.item_id == "kush" and item_b.item_id in ("rolling_paper", "spectral_paper"):
        return item_a.strain
    elif item_a.item_id in ("rolling_paper", "spectral_paper") and item_b.item_id == "kush":
        return item_b.strain

    return None


def can_combine(item_id):
    """Return True if item_id can participate in any combine (recipe or prefix-tool)."""
    for a, b in RECIPES:
        if item_id == a or item_id == b:
            return True
    if item_id in PREFIX_TOOL_ITEMS:
        return True
    if item_id in FOOD_DEFS:
        return True
    return False


def get_actions(item_id):
    """Return list of action label strings available for this item."""
    defn = ITEM_DEFS[item_id]
    actions = []

    if defn["equip_slot"] is not None:
        actions.append("Equip")

    if defn.get("use_verb"):
        actions.append(defn["use_verb"])

    if defn.get("throw_verb"):
        actions.append(defn["throw_verb"])

    if can_combine(item_id):
        actions.append("Use on...")

    actions.append("Examine")
    actions.append("Drop")
    actions.append("Destroy")
    return actions


def get_combine_targets(item_id, inventory_item_ids):
    """Given a source item_id and a list of other inventory item_ids,
    return the indices of items that form a valid recipe or prefix-tool combine with item_id."""
    targets = []
    for i, other_id in enumerate(inventory_item_ids):
        if find_recipe(item_id, other_id):
            targets.append(i)
            continue
        if item_id in PREFIX_TOOL_ITEMS and other_id in FOOD_DEFS:
            targets.append(i)
            continue
        if item_id in FOOD_DEFS and other_id in PREFIX_TOOL_ITEMS:
            targets.append(i)
    return targets


def find_env_interaction(item_id, env_feature):
    """Look up an environment interaction by item_id and feature name.
    Returns interaction dict or None."""
    return ENV_INTERACTIONS.get((item_id, env_feature))


def generate_examine_lines(item_id, engine=None):
    """Generate a list of text lines describing an item for the Examine overlay.

    Each line is either a plain string or a (text, (r,g,b)) tuple for coloring.
    Returns a list of lists, where each inner list is one visual line
    (each element is a (text, color) tuple).
    """
    defn = ITEM_DEFS.get(item_id)
    if not defn:
        return [[("Unknown item.", (200, 200, 200))]]

    lines = []
    C_LABEL = (180, 180, 220)
    C_VALUE = (255, 255, 200)
    C_GOOD  = (100, 220, 100)
    C_BAD   = (255, 100, 100)
    C_INFO  = (200, 200, 200)
    C_HINT  = (150, 150, 180)

    category = defn.get("category", "")
    subcategory = defn.get("subcategory")

    # --- Category header ---
    cat_display = category.title()
    if subcategory:
        cat_display += f" ({subcategory.title()})"
    lines.append([(cat_display, C_HINT)])

    # --- WEAPONS ---
    if subcategory == "weapon":
        wtype = defn.get("weapon_type", "melee")
        lines.append([("Type: ", C_LABEL), (wtype.title(), C_VALUE)])

        base_dmg = defn.get("base_damage", 0)
        lines.append([("Base Damage: ", C_LABEL), (str(base_dmg), C_VALUE)])

        # STR scaling description
        scaling = defn.get("str_scaling")
        stat_scaling = defn.get("stat_scaling")
        req = defn.get("str_req", 1)

        if scaling:
            stype = scaling["type"]
            if stype == "tiered":
                div = scaling.get("divisor", 2)
                if div == 1:
                    desc = f"+1 per STR above {req}"
                else:
                    desc = f"+1 per {div} STR above {req}"
            elif stype == "linear":
                base = scaling.get("base", 5)
                desc = f"+1 per STR above {base}"
            elif stype == "diminishing_tiered":
                desc = f"Diminishing per STR above {req}"
            elif stype == "ratio":
                n = scaling.get("numerator", 1)
                d = scaling.get("denominator", 1)
                desc = f"+{n}/{d} per STR above {req}"
            else:
                desc = "STR scaling"
            lines.append([("Scaling: ", C_LABEL), (desc, C_INFO)])
        elif stat_scaling:
            stype = stat_scaling["type"]
            if stype == "threshold":
                stat = stat_scaling["stat"].replace("_", " ").title()
                thresh = stat_scaling["threshold"]
                desc = f"+1 per {stat} above {thresh}"
            elif stype == "swagger_linear":
                div = stat_scaling.get("divisor", 2)
                desc = f"+1 per {div} Swagger"
            else:
                desc = "Special scaling"
            lines.append([("Scaling: ", C_LABEL), (desc, C_INFO)])

        # Current total damage
        if engine:
            weapon = engine.equipment.get("weapon")
            if weapon and weapon.item_id == item_id:
                total = engine._compute_player_attack_power()
                lines.append([("Current Damage: ", C_LABEL), (str(total), C_GOOD)])
            else:
                # Compute what damage would be if equipped
                # Manually compute for this weapon
                _str = engine.player_stats.effective_strength
                bonus = 0
                if scaling:
                    stype = scaling["type"]
                    if stype == "tiered":
                        bonus = max(0, (_str - req) // scaling.get("divisor", 2))
                    elif stype == "linear":
                        bonus = max(0, _str - scaling.get("base", 5))
                    elif stype == "diminishing_tiered":
                        excess = max(0, _str - req)
                        divisor = 1
                        tier_size = 2
                        remaining = excess
                        while remaining > 0:
                            if divisor >= 8:
                                bonus += remaining // 8
                                break
                            chunk = min(remaining, tier_size)
                            bonus += chunk // divisor
                            remaining -= chunk
                            divisor += 1
                            tier_size += 2
                    elif stype == "ratio":
                        n = scaling.get("numerator", 1)
                        d = scaling.get("denominator", 1)
                        bonus = max(0, (_str - req) * n // d)
                elif stat_scaling:
                    if stat_scaling["type"] == "threshold":
                        stat_val = getattr(engine.player_stats, f"effective_{stat_scaling['stat']}", 0)
                        bonus = max(0, stat_val - stat_scaling["threshold"])
                    elif stat_scaling["type"] == "swagger_linear":
                        div = stat_scaling.get("divisor", 2)
                        bonus = getattr(engine.player_stats, "effective_swagger", 0) // div
                total = base_dmg + bonus
                lines.append([("Damage if equipped: ", C_LABEL), (str(total), C_VALUE)])

        lines.append([("STR Required: ", C_LABEL), (str(req), C_VALUE)])

        reach = defn.get("reach", 1)
        if reach > 1:
            lines.append([("Reach: ", C_LABEL), (f"{reach} tiles", C_VALUE)])

        # Special weapon properties
        if defn.get("on_hit_effect"):
            eff = defn["on_hit_effect"]
            eff_name = eff.get("type", "").replace("_", " ").title()
            lines.append([("On Hit: ", C_LABEL), (f"{eff_name}", C_GOOD)])
        if defn.get("on_hit_stun_chance"):
            chance = int(defn["on_hit_stun_chance"] * 100)
            dur = defn.get("stun_duration", 1)
            lines.append([("On Hit: ", C_LABEL), (f"{chance}% stun ({dur} turns)", C_GOOD)])
        if defn.get("vampiric"):
            pct = int(defn["vampiric"] * 100)
            lines.append([("Vampiric: ", C_LABEL), (f"Heal {pct}% of damage", C_GOOD)])
        if defn.get("on_hit_sunder"):
            amt = defn["on_hit_sunder"]
            lines.append([("Sunder: ", C_LABEL), (f"-{amt} defense per hit", C_GOOD)])
        if defn.get("on_hit_disarm_chance"):
            chance = int(defn["on_hit_disarm_chance"] * 100)
            dur = defn.get("disarm_duration", 1)
            lines.append([("On Hit: ", C_LABEL), (f"{chance}% disarm ({dur} turns)", C_GOOD)])
        if defn.get("on_hit_bounce"):
            b = defn["on_hit_bounce"]
            chance = int(b.get("chance", 0) * 100)
            pct = int(b.get("damage_pct", 0) * 100)
            lines.append([("Chain Hit: ", C_LABEL), (f"{chance}% at {pct}% damage", C_GOOD)])
        if defn.get("break_chance"):
            chance = round(defn["break_chance"] * 100, 1)
            lines.append([("Break Chance: ", C_LABEL), (f"{chance}% per hit", C_BAD)])
        if defn.get("on_hit_skill_xp"):
            sk = defn["on_hit_skill_xp"]
            lines.append([("Trains: ", C_LABEL), (f"{sk['skill']} (+{sk['amount']} XP/hit)", C_INFO)])
        if defn.get("grants_ability"):
            lines.append([("Grants: ", C_LABEL), (defn["grants_ability"].replace("_", " ").title(), C_GOOD)])

    # --- NECK EQUIPMENT (chains) ---
    elif subcategory == "neck":
        armor = defn.get("armor_bonus", 0)
        lines.append([("Armor: ", C_LABEL), (f"+{armor}", C_GOOD)])
        sb = defn.get("stat_bonus", {})
        for stat, val in sb.items():
            stat_display = stat.replace("_", " ").title()
            lines.append([(f"{stat_display}: ", C_LABEL), (f"+{val}", C_GOOD)])

    # --- FEET EQUIPMENT (jordans) ---
    elif subcategory == "feet":
        armor = defn.get("armor_bonus", 0)
        lines.append([("Armor: ", C_LABEL), (f"+{armor}", C_GOOD)])
        sb = defn.get("stat_bonus", {})
        for stat, val in sb.items():
            stat_display = stat.replace("_", " ").title()
            lines.append([(f"{stat_display}: ", C_LABEL), (f"+{val}", C_GOOD)])

    # --- RINGS ---
    elif subcategory == "ring":
        sb = defn.get("stat_bonus", {})
        for stat, val in sb.items():
            stat_display = stat.replace("_", " ").title()
            sign = "+" if val > 0 else ""
            color = C_GOOD if val > 0 else C_BAD
            lines.append([(f"{stat_display}: ", C_LABEL), (f"{sign}{val}", color)])
        pb = defn.get("power_bonus", 0)
        if pb:
            lines.append([("Power: ", C_LABEL), (f"+{pb}", C_GOOD)])
        db = defn.get("defense_bonus", 0)
        if db:
            lines.append([("Defense: ", C_LABEL), (f"+{db}", C_GOOD)])

    # --- CONSUMABLES ---
    elif category == "consumable":
        use_eff = defn.get("use_effect")
        if use_eff:
            etype = use_eff.get("type")

            if etype == "strain_roll":
                lines.append([("Smoke to trigger a random strain", C_INFO)])
                lines.append([("effect (roll 1-100).", C_INFO)])
                skill = defn.get("primary_skill")
                if skill:
                    lines.append([("Trains: ", C_LABEL), (skill, C_VALUE)])

            elif etype == "alcohol":
                drink_id = use_eff.get("drink_id", "")
                _drink_descs = {
                    "40oz": [
                        "Restores 50% armor.",
                        "+5 Swagger for 50 turns.",
                        "+1 hangover stack.",
                    ],
                    "fireball_shooter": [
                        "Grants 3 Breath Fire charges.",
                        "+2 hangover stacks.",
                    ],
                    "malt_liquor": [
                        "+8 STR, -2 CON, +20 armor",
                        "for 50 turns.",
                        "+1 hangover stack.",
                    ],
                    "wizard_mind_bomb": [
                        "Grants 3 Breath Fire charges.",
                        "+2 charges to all active spells.",
                        "+5 Book Smarts for 50 turns.",
                        "+1 hangover stack.",
                    ],
                    "homemade_hennessy": [
                        "-2 STR, +5 Tolerance for",
                        "50 turns. Enables double smoke.",
                        "+1 hangover stack.",
                    ],
                    "steel_reserve": [
                        "Heals 50% max HP.",
                        "+3 permanent armor.",
                        "+1 hangover stack.",
                    ],
                }
                desc_lines = _drink_descs.get(drink_id, ["Alcohol effect."])
                for dl in desc_lines:
                    lines.append([(dl, C_INFO)])

            elif etype == "food":
                food_id = use_eff.get("food_id", "")
                from foods import FOOD_DEFS
                fdef = FOOD_DEFS.get(food_id)
                if fdef:
                    eat_len = fdef.get("eat_length", 0)
                    lines.append([("Eat Time: ", C_LABEL), (f"{eat_len} turns", C_VALUE)])
                    for eff in fdef.get("effects", []):
                        ft = eff.get("type")
                        if ft == "heal":
                            amt = eff["amount"]
                            if isinstance(amt, list):
                                lines.append([("Heals: ", C_LABEL), (f"{amt[0]}-{amt[1]} HP", C_GOOD)])
                            else:
                                lines.append([("Heals: ", C_LABEL), (f"{amt} HP", C_GOOD)])
                        elif ft == "hot":
                            formula = eff.get("stat_formula", "?")
                            dur = eff.get("duration", 0)
                            lines.append([("Heals: ", C_LABEL), (f"{formula} HP/turn for {dur} turns", C_GOOD)])
                        elif ft == "speed_boost":
                            amt = eff.get("amount", 0)
                            dur = eff.get("duration", 0)
                            lines.append([("Speed Boost: ", C_LABEL), (f"+{amt} energy/tick, {dur} turns", C_GOOD)])
                        elif ft == "hot_cheetos":
                            dur = eff.get("duration", 0)
                            lines.append([("+2 all stats for ", C_GOOD), (f"{dur} turns.", C_GOOD)])
                            lines.append([("50% melee ignite chance.", C_GOOD)])
                            lines.append([("Ignites you when it expires.", C_BAD)])
                        elif ft == "grant_ability_charges":
                            aid = eff.get("ability_id", "?").replace("_", " ").title()
                            charges = eff.get("charges", 0)
                            lines.append([("Grants: ", C_LABEL), (f"{charges}x {aid}", C_GOOD)])
                        elif ft == "cornbread_buff":
                            dur = eff.get("duration", 0)
                            lines.append([("Cornbread buff for ", C_INFO), (f"{dur} turns.", C_INFO)])
                        elif ft == "leftovers_well_fed":
                            dur = eff.get("duration", 0)
                            lines.append([("Well Fed for ", C_INFO), (f"{dur} turns.", C_INFO)])

            elif etype == "torch_burn":
                lines.append([("Burns an item when used on it.", C_INFO)])

        # Throw info
        if defn.get("throw_verb"):
            lines.append([("Can be thrown at enemies.", C_INFO)])

        # Skills trained
        skill = defn.get("primary_skill")
        if skill and (not use_eff or use_eff.get("type") not in ("strain_roll",)):
            lines.append([("Trains: ", C_LABEL), (skill, C_VALUE)])

    # --- MATERIALS ---
    elif category == "material":
        # Show what recipes this participates in
        recipes_found = []
        for (a, b), recipe in RECIPES.items():
            result_name = ITEM_DEFS.get(recipe["result"], {}).get("name", recipe["result"])
            if a == item_id:
                other_name = ITEM_DEFS.get(b, {}).get("name", b)
                recipes_found.append((other_name, result_name))
            elif b == item_id:
                other_name = ITEM_DEFS.get(a, {}).get("name", a)
                recipes_found.append((other_name, result_name))
        if recipes_found:
            lines.append([("Recipes:", C_LABEL)])
            for other, result in recipes_found:
                lines.append([("  + ", C_HINT), (other, C_VALUE), (" = ", C_HINT), (result, C_GOOD)])

        # Check if it can be prefix-tooled (e.g., food + fry daddy)
        for tool_id, prefix in PREFIX_TOOL_ITEMS.items():
            tool_name = ITEM_DEFS.get(tool_id, {}).get("name", tool_id)
            lines.append([("  + ", C_HINT), (tool_name, C_VALUE), (" = ", C_HINT), (f"{prefix.title()} version", C_GOOD)])

        skill = defn.get("primary_skill")
        if skill:
            lines.append([("Trains: ", C_LABEL), (skill, C_VALUE)])

    # --- TOOLS ---
    elif category == "tool":
        # Show what this tool is used for
        recipes_found = []
        for (a, b), recipe in RECIPES.items():
            result_name = ITEM_DEFS.get(recipe["result"], {}).get("name", recipe["result"])
            consumed = recipe.get("consumed", [])
            reusable = item_id not in consumed
            if a == item_id:
                other_name = ITEM_DEFS.get(b, {}).get("name", b)
                recipes_found.append((other_name, result_name, reusable))
            elif b == item_id:
                other_name = ITEM_DEFS.get(a, {}).get("name", a)
                recipes_found.append((other_name, result_name, reusable))

        # Check prefix tool
        if item_id in PREFIX_TOOL_ITEMS:
            prefix = PREFIX_TOOL_ITEMS[item_id]
            lines.append([("Applies '", C_INFO), (prefix.title(), C_GOOD), ("' prefix to food.", C_INFO)])

        if recipes_found:
            lines.append([("Recipes:", C_LABEL)])
            for other, result, reusable in recipes_found:
                tag = " (reusable)" if reusable else ""
                lines.append([("  + ", C_HINT), (other, C_VALUE), (" = ", C_HINT), (result, C_GOOD), (tag, C_HINT)])
        elif not item_id in PREFIX_TOOL_ITEMS:
            if defn.get("use_effect"):
                etype = defn["use_effect"].get("type")
                if etype == "torch_burn":
                    lines.append([("Use on items to burn them", C_INFO)])
                    lines.append([("together.", C_INFO)])

        skill = defn.get("primary_skill")
        if skill:
            lines.append([("Trains: ", C_LABEL), (skill, C_VALUE)])

    # --- Value ---
    val = defn.get("value", 0)
    if val > 0:
        lines.append([("Value: ", C_LABEL), (f"${val}", C_VALUE)])

    return lines


def create_item_entity(item_id, x, y, strain=None):
    """Build an Entity kwargs dict for the given item_id and optional strain.
    Returns a dict — caller does Entity(**kwargs).
    This avoids importing Entity here (no circular import)."""
    defn = ITEM_DEFS[item_id]

    # For cannabis items with strains, use the strain's unique color
    item_color = defn["color"]
    if item_id in ("weed_nug", "kush", "joint") and strain:
        item_color = get_strain_color(strain)

    return {
        "x": x,
        "y": y,
        "char": defn["char"],
        "color": item_color,
        "name": build_item_name(item_id, strain),
        "entity_type": "item",
        "blocks_movement": False,
        "item_id": item_id,
        "strain": strain,
    }
