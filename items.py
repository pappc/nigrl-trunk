"""
Item definitions, crafting recipes, and helper functions.

All item metadata lives here to keep Entity lean.
Entity objects link to definitions via their `item_id` field.
"""

import math as _math
import random as _random
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
    "Iron Lung",
    "Skywalker OG",
    "Street Scholar",
    "Kushenheimer",
    "Nigle Fart",
    "Purple Halt",
    "Snickelfritz",
]

# Smoking skill XP values per strain
# Higher complexity/power strains = more XP
STRAIN_SMOKING_XP = {
    "OG Kush": 30,           # Simple healing strain
    "Agent Orange": 40,      # Debuff effects
    "Columbian Gold": 50,    # Power-based buff with DoT
    "Blue Lobster": 80,      # Complex damage/defense mechanic
    "Jungle Boyz": 60,       # Multiple attack-based effects
    "Dosidos": 70,           # Complex spellcasting effects
    "Blue Meth": 70,         # Meth meter smoking
    "Iron Lung": 125,        # CON-based tox removal tank strain
    "Skywalker OG": 125,     # STR-based rad synergy strain
    "Street Scholar": 125,   # STSMT-based gun strain
    "Kushenheimer": 125,         # BKSMT-based radiation spell strain
    "Nigle Fart": 125,           # TOL-based toxicity spillover strain
    "Purple Halt": 125,           # SWG-based mutation control strain
    "Snickelfritz": 30,           # Very negative trash strain (Rolling L4 proc)
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
    "Iron Lung": 125,        # CON-based tox removal tank strain
    "Skywalker OG": 125,     # STR-based rad synergy strain
    "Street Scholar": 125,   # STSMT-based gun strain
    "Kushenheimer": 125,         # BKSMT-based radiation spell strain
    "Nigle Fart": 125,           # TOL-based toxicity spillover strain
    "Purple Halt": 125,           # SWG-based mutation control strain
    "Snickelfritz": 30,           # Very negative trash strain (Rolling L4 proc)
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
    "Blue Meth":     {"first_bonus_roll": 8,  "add_bonus_roll": 8},
    "Iron Lung":     {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Skywalker OG":  {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Street Scholar": {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Kushenheimer":      {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Nigle Fart":        {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Purple Halt":       {"first_bonus_roll": 11, "add_bonus_roll": 6},
    "Snickelfritz":      {"first_bonus_roll": 99, "add_bonus_roll": 99},  # always 1 roll, always bad
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
    "chicken": 60,           # Simple healing food
    "instant_ramen": 70,     # Speed boost
    "hot_cheetos": 80,       # Complex buff (stats + melee effect + expire effect)
    "cornbread": 60,         # Moderate: stat buff + spell charges
    "corn_dog": 60,          # Quick eat, melee charges
    "lightskin_beans": 80,   # Long eat, powerful AoE spell
    "leftovers": 25,         # Proc'd from Better Later perk
    "protein_powder": 80,    # Floor-duration stat doubling buff
    "muffin": 80,            # Floor-duration charge preservation buff
    "jolly_rancher": 70,     # Phase walk through walls
    "yellowcake": 120,       # +100 rad, 10x mutation chance, no weak mutations
    "holy_wafer": 100,       # +5 Divine Shield stacks
    "mirror_cake": 70,       # +3 Mirror Entity charges
    "hard_boiled_egg": 100,  # Death save: revive at half HP
    "carrot_cake": 70,       # Unlimited FOV for floor
    "jell_o": 100,           # Meth Lab: mirror entity charges
    "meatball_sub": 100,     # Meth Lab: fire meatball charges
    "heinz_baked_beans": 100, # Meth Lab: gas attack charges
    "altoid": 25,            # Meth Lab: remove toxicity
    "asbestos": 25,          # Meth Lab: add toxicity
    "rad_away": 25,          # Meth Lab: remove radiation
    "radbar": 25,            # Meth Lab: add radiation
}

# Deep-Frying skill XP values per food
# Frying food grants XP equal to the material's value × 2
ITEM_DEEP_FRYING_XP = {
    "chicken": 50,           # value 25 × 2
    "instant_ramen": 60,     # value 30 × 2
    "hot_cheetos": 80,       # value 40 × 2
    "cornbread": 50,         # value 25 × 2
    "corn_dog": 40,          # value 20 × 2
    "lightskin_beans": 70,   # value 35 × 2
    "leftovers": 10,         # value 5 × 2
    "protein_powder": 80,    # value 40 × 2
    "muffin": 80,            # value 40 × 2
    "jell_o": 60,            # value 30 × 2
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
        (85, 100, {"type": "dosidos_dimension_door", "min_count": 1, "max_count": 2}, {"type": "dosidos_bksmt_buff", "amount": 10}),
        (72,  84, {"type": "dosidos_chain_lightning", "min_count": 2, "max_count": 5}, {"type": "dosidos_bksmt_buff", "amount":  8}),
        (50,  71, {"type": "dosidos_ray_of_frost",    "min_count": 3, "max_count": 5}, {"type": "dosidos_bksmt_buff", "amount":  6}),
        (22,  49, {"type": "dosidos_warp",            "min_count": 2, "max_count": 3}, {"type": "dosidos_bksmt_buff", "amount":  4}),
        ( 1,  21, {"type": "dosidos_warp",            "min_count": 1, "max_count": 1}, {"type": "dosidos_bksmt_buff", "amount":  2}),
    ],
    "Iron Lung": [
        (95, 100, {"type": "iron_lung_full"},       None),  # Remove all tox; heal tox+CON*2, half excess→temp HP; +tox/20 DEF (50t)
        (61,  94, {"type": "iron_lung_100"},        None),  # Remove 100 tox; heal removed*2+CON*2, half excess→temp HP; +1 DEF/10 removed (50t)
        (31,  60, {"type": "iron_lung_50"},         None),  # Remove 50 tox; heal removed*2+CON*2, half excess→temp HP; +1 DEF/10 removed (50t)
        ( 1,  30, {"type": "iron_lung_bad"},        None),  # Gain 100 tox
    ],
    "Skywalker OG": [
        (100, 100, {"type": "skywalker_lightsaber"},  None),  # Green Lightsaber + Force Sensitive + 100 rad
        (71,   99, {"type": "skywalker_force"},        None),  # Force Sensitive + 100 starting rad
        (50,   70, {"type": "skywalker_force_half"},   None),  # Force Sensitive + 50 starting rad
        ( 1,   49, {"type": "skywalker_rad_loss"},     None),  # Lose 50 rad
    ],
    "Street Scholar": [
        (75, 100, {"type": "calculated_aim_iii"},      None),  # Calc Aim III: 15% BKSMT/kill, 100% acc, auto-reload, +1x crit mult
        (45,  74, {"type": "calculated_aim_ii"},       None),  # Calc Aim II:  10% BKSMT/kill, auto-reload, +1x crit mult
        (25,  44, {"type": "calculated_aim_i"},        None),  # Calc Aim I:   5% BKSMT/kill, +1x crit mult
        (11,  24, {"type": "street_scholar_jam"},      None),  # Jam all equipped guns
        ( 1,  10, {"type": "street_scholar_misfire"},   None),  # Dump all gun ammo
    ],
    "Kushenheimer": [
        (80, 100, {"type": "rad_nova_5"},  None),  # Tier 5: +10-20 rad, +12 spell dmg, +3+BKS/5 Nova charges, +1 perm BKS
        (60,  79, {"type": "rad_nova_4"},  None),  # Tier 4: +15-25 rad, +10 spell dmg, +3 Nova charges
        (40,  59, {"type": "rad_nova_3"},  None),  # Tier 3: +20-30 rad, +7 spell dmg, +2 Nova charges
        (20,  39, {"type": "rad_nova_2"},  None),  # Tier 2: +25-35 rad, +5 spell dmg
        ( 1,  19, {"type": "rad_nova_1"},  None),  # Tier 1: +30-40 rad, no buff
    ],
    "Nigle Fart": [
        (80, 100, {"type": "nigle_fart_5"},  None),  # Tier 5: +30 tox, 100% spillover aura, +4 Pandemic, perm TOL chance
        (60,  79, {"type": "nigle_fart_4"},  None),  # Tier 4: +40 tox, 75% spillover aura, +3 Pandemic, perm TOL chance
        (40,  59, {"type": "nigle_fart_3"},  None),  # Tier 3: +50 tox, 50% spillover aura, +3 Pandemic, perm TOL chance
        (20,  39, {"type": "nigle_fart_2"},  None),  # Tier 2: +70 tox, +2 Pandemic
        ( 1,  19, {"type": "nigle_fart_1"},  None),  # Tier 1: +100 tox, +1 Pandemic
    ],
    "Purple Halt": [
        (90, 100, {"type": "purple_halt_glory"},   None),  # Glory: force random-tier mutation, NO rad cost
        (55,  89, {"type": "purple_halt_strong"},  None),  # Strong: force random-tier mutation, rad consumed
        (20,  54, {"type": "purple_halt_weak"},    None),  # Weak: -15 rad (whiff)
        ( 1,  19, {"type": "purple_halt_bad"},     None),  # Bad: -40 rad, +1 temp SWG (15t)
    ],
    "Snickelfritz": [
        ( 1, 100, {"type": "snickelfritz"},        None),  # TBD: very negative effects
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
        "Iron Lung": (160, 180, 180),    # Tarnished steel
        "Skywalker OG": (80, 200, 120),   # Force green
        "Street Scholar": (180, 160, 220), # Studious purple
        "Kushenheimer": (160, 220, 100),         # Sickly nuclear green
        "Nigle Fart": (200, 180, 60),            # Sickly amber
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
                "zones": ["crack_den", "meth_lab"],
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
                "zones": ["crack_den", "meth_lab"],
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
                "zones": ["meth_lab"],
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
                "zones": ["meth_lab"],
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

# Master attribute tables — single source of truth.
# Material sets base armor; brand applies a multiplier.
_CHAIN_MATERIALS = {
    "Bronze": {"base_armor": 20, "color": (205, 127,  50)},
    "Steel":  {"base_armor": 25, "color": (160, 174, 192)},
    "Silver": {"base_armor": 30, "color": (192, 192, 192)},
    "Gold":   {"base_armor": 35, "color": (255, 215,   0)},
}

# Brand multiplier applied to base armor. None = no brand label in name.
_CHAIN_BRANDS = {
    "Fake":     {"multiplier": 1.0},
    None:       {"multiplier": 1.5},
    "Designer": {"multiplier": 2.0},
}

# Per-zone spawn weight configs.  Each axis is weighted independently.
CHAIN_ZONE_CONFIGS = {
    "crack_den": {
        "material_weights": {"Bronze": 4, "Steel": 3, "Silver": 2, "Gold": 1},
        "brand_weights":    {"Fake": 4, None: 3, "Designer": 1},
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    # NOTE: meth_lab uses its own 4-axis chain system — see _METH_CHAIN_* tables.
    "casino_botanical": {
        "material_weights": {"Bronze": 1, "Steel": 3, "Silver": 3, "Gold": 3},
        "brand_weights":    {"Fake": 2, None: 3, "Designer": 3},
    },
    "the_underprison": {
        "material_weights": {"Bronze": 4, "Steel": 3, "Silver": 2, "Gold": 1},
        "brand_weights":    {"Fake": 5, None: 3, "Designer": 1},
    },
}


def _chain_key(name):
    """Convert a display name (or None) to a safe identifier fragment."""
    if name is None:
        return "none"
    return name.lower().replace("-", "_").replace(" ", "_")


def _chain_item_id(material, brand):
    return f"chain_{_chain_key(material)}_{_chain_key(brand)}"


def _chain_display_name(material, brand):
    """Format: (Brand) (Material) Chain — omit None brand."""
    parts = []
    if brand is not None:
        parts.append(brand)
    parts.append(material)
    parts.append("Chain")
    return " ".join(parts)


def _chain_armor(material, brand):
    """Compute armor value: base_armor * brand_multiplier."""
    base = _CHAIN_MATERIALS[material]["base_armor"]
    multi = _CHAIN_BRANDS[brand]["multiplier"]
    return _math.ceil(base * multi)


def _build_chains():
    """Generate every (material × brand) combination from the master tables."""
    chains = {}
    for material, mat_data in _CHAIN_MATERIALS.items():
        for brand in _CHAIN_BRANDS:
            item_id = _chain_item_id(material, brand)
            armor = _chain_armor(material, brand)
            chains[item_id] = {
                "name":          _chain_display_name(material, brand),
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
# Meth Lab Chain definitions
# ---------------------------------------------------------------------------
#
# Architecture: 4-axis combinatorial system (same pattern as crack den chains).
#   _METH_CHAIN_SMELLS / _METH_CHAIN_SIZES / _METH_CHAIN_MATERIALS / _METH_CHAIN_SUFFIXES
#   _build_meth_chains()  — generates all 480 combinations at import time.
#   get_random_meth_chain(zone) — four independent weighted picks.
#
# Name format: "[Smell] [Size] [Material] Chain [Suffix]"
# Example:     "Smelly Light Gold Chain of Swag"
# ---------------------------------------------------------------------------

# All meth lab chains inflict -20% tox resistance regardless of smell prefix.
_METH_CHAIN_SMELLS = {
    "Smelly": {"weight": 1},
    "Stinky": {"weight": 1},
    None:     {"weight": 2},
    "Clean":  {"weight": 1},
    "Pure":   {"weight": 1},
}

_METH_CHAIN_SIZES = {
    "Light":   {"defense_bonus": 0, "energy_per_tick":  10, "weight": 1},
    "Heavy":   {"defense_bonus": 1, "energy_per_tick":   0, "weight": 1},
    "Bulky":   {"defense_bonus": 2, "energy_per_tick":   0, "weight": 1},
    "Massive": {"defense_bonus": 3, "energy_per_tick": -10, "weight": 1},
}

_METH_CHAIN_MATERIALS = {
    "Silver":   {"armor": 35, "rad_resistance":   0, "color": (192, 192, 192), "weight": 3},
    "Gold":     {"armor": 40, "rad_resistance":   0, "color": (255, 215,   0), "weight": 3},
    "Platinum": {"armor": 50, "rad_resistance":   0, "color": (229, 228, 226), "weight": 2},
    "Uranium":  {"armor": 60, "rad_resistance": -20, "color": ( 57, 255,  20), "weight": 2},
}

_METH_CHAIN_SUFFIXES = {
    "of War":     {"stat_bonus": {"strength": 3, "constitution": 3},     "weight": 1},
    "of Health":  {"stat_bonus": {"constitution": 6},                    "weight": 1},
    "of Books":   {"stat_bonus": {"book_smarts": 3, "constitution": 3},  "weight": 1},
    "of Streets": {"stat_bonus": {"street_smarts": 3, "constitution": 3},"weight": 1},
    "of Drugs":   {"stat_bonus": {"tolerance": 3, "constitution": 3},    "weight": 1},
    "of Swag":    {"stat_bonus": {"swagger": 3, "constitution": 3},      "weight": 1},
}

METH_CHAIN_ZONE_CONFIGS = {
    "meth_lab": {
        "smell_weights":    {k: v["weight"] for k, v in _METH_CHAIN_SMELLS.items()},
        "size_weights":     {k: v["weight"] for k, v in _METH_CHAIN_SIZES.items()},
        "material_weights": {k: v["weight"] for k, v in _METH_CHAIN_MATERIALS.items()},
        "suffix_weights":   {k: v["weight"] for k, v in _METH_CHAIN_SUFFIXES.items()},
    },
}


def _meth_chain_key(name):
    """Convert a display name (or None) to a safe identifier fragment."""
    if name is None:
        return "none"
    return name.lower().replace("-", "_").replace(" ", "_")


def _meth_chain_item_id(smell, size, material, suffix):
    return f"mchain_{_meth_chain_key(smell)}_{_meth_chain_key(size)}_{_meth_chain_key(material)}_{_meth_chain_key(suffix)}"


def _meth_chain_display_name(smell, size, material, suffix):
    """Format: [Smell] [Size] [Material] Chain [Suffix] — omit None smell."""
    parts = []
    if smell is not None:
        parts.append(smell)
    parts.append(size)
    parts.append(material)
    parts.append("Chain")
    parts.append(suffix)
    return " ".join(parts)


def _build_meth_chains():
    """Generate every (smell × size × material × suffix) combination."""
    chains = {}
    for smell in _METH_CHAIN_SMELLS:
        for size, size_data in _METH_CHAIN_SIZES.items():
            for material, mat_data in _METH_CHAIN_MATERIALS.items():
                for suffix, suf_data in _METH_CHAIN_SUFFIXES.items():
                    item_id = _meth_chain_item_id(smell, size, material, suffix)
                    armor = mat_data["armor"]
                    defn = {
                        "name":            _meth_chain_display_name(smell, size, material, suffix),
                        "char":            '"',
                        "color":           mat_data["color"],
                        "category":        "equipment",
                        "subcategory":     "neck",
                        "equip_slot":      "neck",
                        "power_bonus":     0,
                        "defense_bonus":   size_data["defense_bonus"],
                        "armor_bonus":     armor,
                        "stat_bonus":      dict(suf_data["stat_bonus"]),
                        "tox_resistance":  -20,
                        "tags":            ["chain", "meth_chain"],
                        "zones":           ["meth_lab"],
                        "use_verb":        None,
                        "use_effect":      None,
                    }
                    # Uranium adds rad resistance penalty
                    if mat_data["rad_resistance"] != 0:
                        defn["rad_resistance"] = mat_data["rad_resistance"]
                    # Light/Massive modify energy per tick
                    if size_data["energy_per_tick"] != 0:
                        defn["energy_per_tick"] = size_data["energy_per_tick"]
                    # Value: armor + stat value + size value
                    stat_value = sum(suf_data["stat_bonus"].values()) * 5
                    defn["value"] = round(30 + armor + stat_value +
                                          size_data["defense_bonus"] * 10 +
                                          abs(size_data["energy_per_tick"]) * 2)
                    chains[item_id] = defn
    return chains


_METH_CHAINS = _build_meth_chains()


def get_random_meth_chain(zone="meth_lab"):
    """Return a random meth lab chain item_id using per-axis weighted selection."""
    import random as _random
    config = METH_CHAIN_ZONE_CONFIGS[zone]

    def _wpick(weights_dict):
        keys    = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return _random.choices(keys, weights=weights, k=1)[0]

    smell    = _wpick(config["smell_weights"])
    size     = _wpick(config["size_weights"])
    material = _wpick(config["material_weights"])
    suffix   = _wpick(config["suffix_weights"])
    return _meth_chain_item_id(smell, size, material, suffix)


# ---------------------------------------------------------------------------
# Scuffed Jordans definitions
#
# Each pair gets +3 to one of 6 stats and either 10 or 15 armor.
# 12 total combinations (6 stats × 2 armor tiers), pre-generated at import.
# Item IDs: "jordans_{stat_key}_{armor}" e.g. "jordans_constitution_10"
# Stats and armor only visible in the examine tooltip, not the item name.
# ---------------------------------------------------------------------------

def _build_jordans():
    """Generate all 12 Scuffed Jordans item definitions (6 stats × 2 armor tiers)."""
    jordans = {}
    for stat_attr, id_key, label, (r, g, b) in _RING_STAT_DEFS:
        for armor in (10, 15):
            item_id = f"jordans_{id_key}_{armor}"
            # Slightly worn/scuffed color: darken the stat color
            color = (max(0, r - 40), max(0, g - 40), max(0, b - 40))
            jordans[item_id] = {
                "name":          "Scuffed Jordans",
                "char":          "s",
                "color":         color,
                "category":      "equipment",
                "subcategory":   "feet",
                "equip_slot":    "feet",
                "power_bonus":   0,
                "defense_bonus": 0,
                "armor_bonus":   armor,
                "value":         45 if armor == 10 else 75,
                "stat_bonus":    {stat_attr: 3},
                "tags":          ["jordans"],
                "zones":         ["crack_den", "meth_lab"],
                "use_verb":      None,
                "use_effect":    None,
            }
    return jordans

_JORDANS = _build_jordans()


def get_random_jordans():
    """Return a random jordans item_id (uniform pick across all 90 combinations)."""
    import random as _random
    return _random.choice(list(_JORDANS.keys()))


# ---------------------------------------------------------------------------
# Hat definitions
# ---------------------------------------------------------------------------
#
# Architecture (same pattern as chains):
#   _HAT_TYPES / _HAT_PREFIXES / _HAT_SUFFIXES  — master attribute tables.
#   HAT_ZONE_CONFIGS  — per-zone spawn weights referencing master table keys.
#   _build_hats()  — generates all 105 combinations at import time; merged into ITEM_DEFS.
#   get_random_hat(zone)  — three independent weighted picks using the zone config.
# ---------------------------------------------------------------------------

_HAT_TYPES = {
    "Lead Hat":     {"resistance": "rad",  "color": (90,  95,  100)},
    "Plastic Mask": {"resistance": "tox",  "color": (200, 200, 210)},
    "Tinfoil Hat":  {"resistance": "both", "color": (180, 185, 195)},
}

_HAT_PREFIXES = {
    "Ripped":     {"res_percent": -50, "weight": 4},
    "Ghetto":     {"res_percent": -20, "weight": 4},
    "Fake":       {"res_percent":   0, "weight": 7},
    "Homemade":   {"res_percent":  10, "weight": 7},
    "Typical":    {"res_percent":  20, "weight": 5},
    "Protective": {"res_percent":  30, "weight": 4},
    "Excellent":  {"res_percent":  50, "weight": 2},
}

_HAT_SUFFIXES = {
    "Of Smart": {"stat_bonus": {"book_smarts": 3, "street_smarts": 3}, "weight": 2},
    "Of Drugs": {"stat_bonus": {"tolerance": 3, "swagger": 3},        "weight": 2},
    "Of Brick": {"armor_bonus": 30,                                    "weight": 2},
    "Of Crack": {"energy_per_tick": 10,                                "weight": 2},
    "Of Skill": {"briskness": 5,                                       "weight": 1},
}

HAT_ZONE_CONFIGS = {
    "crack_den": {
        "type_weights":   {"Lead Hat": 1, "Plastic Mask": 1, "Tinfoil Hat": 1},
        "prefix_weights": {"Ripped": 4, "Ghetto": 4, "Fake": 7, "Homemade": 7, "Typical": 5, "Protective": 4, "Excellent": 2},
        "suffix_weights": {"Of Smart": 2, "Of Drugs": 2, "Of Brick": 2, "Of Crack": 2, "Of Skill": 1},
    },
    "meth_lab": {
        "type_weights":   {"Lead Hat": 2, "Plastic Mask": 1, "Tinfoil Hat": 1},
        "prefix_weights": {"Ripped": 3, "Ghetto": 3, "Fake": 5, "Homemade": 7, "Typical": 6, "Protective": 5, "Excellent": 3},
        "suffix_weights": {"Of Smart": 2, "Of Drugs": 2, "Of Brick": 2, "Of Crack": 2, "Of Skill": 1},
    },
    "casino_botanical": {
        "type_weights":   {"Lead Hat": 1, "Plastic Mask": 1, "Tinfoil Hat": 2},
        "prefix_weights": {"Ripped": 2, "Ghetto": 3, "Fake": 5, "Homemade": 6, "Typical": 6, "Protective": 5, "Excellent": 4},
        "suffix_weights": {"Of Smart": 3, "Of Drugs": 2, "Of Brick": 2, "Of Crack": 2, "Of Skill": 2},
    },
    "the_underprison": {
        "type_weights":   {"Lead Hat": 2, "Plastic Mask": 2, "Tinfoil Hat": 1},
        "prefix_weights": {"Ripped": 5, "Ghetto": 5, "Fake": 6, "Homemade": 5, "Typical": 4, "Protective": 3, "Excellent": 1},
        "suffix_weights": {"Of Smart": 2, "Of Drugs": 3, "Of Brick": 2, "Of Crack": 2, "Of Skill": 1},
    },
}


def _hat_key(name):
    """Convert a display name to a safe identifier fragment."""
    return name.lower().replace(" ", "_").replace("-", "_")


def _hat_item_id(hat_type, prefix, suffix):
    return f"hat_{_hat_key(hat_type)}_{_hat_key(prefix)}_{_hat_key(suffix)}"


def _build_hats():
    """Generate every (type x prefix x suffix) combination from the master tables."""
    hats = {}
    for hat_type, type_data in _HAT_TYPES.items():
        for prefix, prefix_data in _HAT_PREFIXES.items():
            for suffix, suffix_data in _HAT_SUFFIXES.items():
                item_id = _hat_item_id(hat_type, prefix, suffix)
                res_pct = prefix_data["res_percent"]
                resistance = type_data["resistance"]

                # Build base item def
                defn = {
                    "name":          f"{prefix} {hat_type} {suffix}",
                    "char":          "^",
                    "color":         type_data["color"],
                    "category":      "equipment",
                    "subcategory":   "hat",
                    "equip_slot":    "hat",
                    "power_bonus":   0,
                    "defense_bonus": 0,
                    "armor_bonus":   0,
                    "stat_bonus":    {},
                    "tags":          ["hat"],
                    "zones":         ["crack_den", "meth_lab"],
                    "use_verb":      None,
                    "use_effect":    None,
                }

                # Apply resistance from type + prefix
                if resistance == "rad":
                    defn["rad_resistance"] = res_pct
                elif resistance == "tox":
                    defn["tox_resistance"] = res_pct
                else:  # both
                    defn["rad_resistance"] = res_pct
                    defn["tox_resistance"] = res_pct

                # Apply suffix bonuses
                if "stat_bonus" in suffix_data:
                    defn["stat_bonus"] = dict(suffix_data["stat_bonus"])
                if "armor_bonus" in suffix_data:
                    defn["armor_bonus"] = suffix_data["armor_bonus"]
                if "energy_per_tick" in suffix_data:
                    defn["energy_per_tick"] = suffix_data["energy_per_tick"]
                if "briskness" in suffix_data:
                    defn["briskness"] = suffix_data["briskness"]

                # Value: based on prefix quality + suffix value
                prefix_value = max(0, res_pct) * 2  # 0–100
                suffix_value = suffix_data.get("armor_bonus", 0) + \
                    sum(suffix_data.get("stat_bonus", {}).values()) * 5 + \
                    suffix_data.get("energy_per_tick", 0) * 3 + \
                    suffix_data.get("briskness", 0) * 4
                defn["value"] = round(20 + prefix_value + suffix_value)

                hats[item_id] = defn
    return hats


_HATS = _build_hats()

# Suffix-less hats — Tyrone's Penthouse exclusives
_HATS["hat_tinfoil_hat_ripped_plain"] = {
    "name":          "Ripped Tinfoil Hat",
    "char":          "^",
    "color":         (180, 185, 195),
    "category":      "equipment",
    "subcategory":   "hat",
    "equip_slot":    "hat",
    "power_bonus":   0,
    "defense_bonus": 0,
    "armor_bonus":   0,
    "stat_bonus":    {},
    "rad_resistance": -50,
    "tox_resistance": -50,
    "tags":          ["hat"],
    "zones":         [],
    "value":         100,
    "use_verb":      None,
    "use_effect":    None,
}

_HATS["hat_tinfoil_hat_excellent_plain"] = {
    "name":          "Excellent Tinfoil Hat",
    "char":          "^",
    "color":         (180, 185, 195),
    "category":      "equipment",
    "subcategory":   "hat",
    "equip_slot":    "hat",
    "power_bonus":   0,
    "defense_bonus": 0,
    "armor_bonus":   0,
    "stat_bonus":    {},
    "rad_resistance": 50,
    "tox_resistance": 50,
    "tags":          ["hat"],
    "zones":         [],
    "value":         300,
    "use_verb":      None,
    "use_effect":    None,
}


def get_random_hat(zone="crack_den"):
    """Return a random hat item_id using per-axis weighted selection for the given zone."""
    config = HAT_ZONE_CONFIGS[zone]

    def _wpick(weights_dict):
        keys    = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return _random.choices(keys, weights=weights, k=1)[0]

    hat_type = _wpick(config["type_weights"])
    prefix   = _wpick(config["prefix_weights"])
    suffix   = _wpick(config["suffix_weights"])
    return _hat_item_id(hat_type, prefix, suffix)


def get_random_chain(zone="crack_den"):
    """Return a random chain item_id using per-axis weighted selection for the given zone.

    Each axis (material, brand) is picked independently from its weight table.
    Meth lab zone uses its own 4-axis chain system.
    """
    if zone in METH_CHAIN_ZONE_CONFIGS:
        return get_random_meth_chain(zone)
    import random as _random
    config = CHAIN_ZONE_CONFIGS[zone]

    def _wpick(weights_dict):
        keys    = list(weights_dict.keys())
        weights = list(weights_dict.values())
        return _random.choices(keys, weights=weights, k=1)[0]

    material = _wpick(config["material_weights"])
    brand    = _wpick(config["brand_weights"])
    return _chain_item_id(material, brand)


ITEM_DEFS = {
    **_MINOR_RINGS,
    **_GREATER_RINGS,
    **_DIVINE_RINGS,
    **_ADVANCED_RINGS,
    **_CHAINS,
    **_METH_CHAINS,
    **_JORDANS,
    **_HATS,
    "knife": {
        "name": "Knife",
        "plural": "Knives",
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
        "weapon_type": "beating",
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
        "weapon_type": "beating",
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
        "weapon_type": "beating",
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
        "weapon_type": "beating",
        "break_hits": 3,
        "break_final_mult": 5,
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
        "weapon_type": "beating",
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
        "weapon_type": "beating",
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
        "weapon_type": "beating",
        "stat_scaling": {"type": "threshold", "stat": "street_smarts", "threshold": 5},  # +1 per STSMT above 5
        "on_hit_disarm_chance": 0.20,
        "disarm_duration": 3,
        "value": 52,
        "zones": ["meth_lab"],
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
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 9
        "on_hit_sunder": 1,                                # permanently reduce defender.defense by 1 per hit
        "value": 58,
        "zones": ["meth_lab"],
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
        "weapon_type": "beating",
        "stat_scaling": {"type": "swagger_linear", "divisor": 2},  # +1 per 2 SWAGGER
        "on_hit_bounce": {"chance": 0.25, "damage_pct": 0.50},     # 25% chance to arc to nearest adj enemy
        "value": 42,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "rusty_machete": {
        "name": "Rusty Machete",
        "char": "/",
        "color": (180, 100, 50),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "str_req": 10,
        "reach": 1,
        "weapon_type": "slashing",
        "dual_stat_scaling": {
            "stats": [
                {"stat": "strength", "threshold": 10},
                {"stat": "street_smarts", "threshold": 10},
            ],
            "divisor": 4,
        },
        "on_hit_tetanus_chance": 0.30,
        "value": 80,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "homemade_whip": {
        "name": "Homemade Whip",
        "char": "/",
        "color": (140, 90, 50),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 12,
        "str_req": 10,
        "reach": 2,
        "weapon_type": "slashing",
        "dual_stat_scaling": {
            "stats": [{"stat": "street_smarts", "threshold": 10}],
            "divisor": 2,
        },
        "value": 90,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "green_lightsaber": {
        "name": "Green Lightsaber",
        "char": "/",
        "color": (50, 255, 50),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 16,
        "str_req": 10,
        "reach": 2,
        "weapon_type": "beating",                          # counts as beating
        "weapon_type_alt": "stabbing",                     # ALSO counts as stabbing
        "str_scaling": {"type": "tiered", "divisor": 2},   # +1 per 2 STR above 10
        "value": 100,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "rolling_pin": {
        "name": "Rolling Pin",
        "char": "/",
        "color": (200, 170, 120),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 11,
        "str_req": 8,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 8
        "on_kill_skill_xp": {"skill": "Rolling", "amount": 15},
        "value": 55,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "metal_lunchbox": {
        "name": "Metal Lunchbox",
        "char": "/",
        "color": (180, 180, 200),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 5,
        "str_req": 4,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 4
        "on_hit_food_chance": 0.05,                        # 5% chance to find a random food
        "value": 50,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "war_maul": {
        "name": "War Maul",
        "char": "/",
        "color": (140, 100, 70),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 14,
        "str_req": 12,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 12
        "on_hit_knockback": {"chance": 0.30, "tiles": 3},  # 30% chance, 3 tiles, no collision dmg
        "value": 70,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "uranium_isotope": {
        "name": "Uranium Isotope",
        "char": "/",
        "color": (50, 255, 50),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 7,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 3},  # +1 per 3 STR above 7
        "on_hit_rad": {"enemy": 12, "self": 5},            # heavy rad to both
        "value": 60,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "dumpster_lid": {
        "name": "Dumpster Lid",
        "char": "/",
        "color": (100, 110, 90),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 1,
        "base_damage": 5,
        "str_req": 6,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 per 2 STR above 6
        "on_hit_tox": {"enemy": 8, "self": 0},             # 8 tox to enemy per hit
        "value": 45,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "deep_fryer_basket": {
        "name": "Deep Fryer Basket",
        "char": "/",
        "color": (180, 150, 60),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 6,
        "str_req": 5,
        "reach": 1,
        "weapon_type": "beating",
        "str_scaling": {"type": "tiered", "divisor": 3},  # +1 per 3 STR above 5
        "on_hit_grease_chance": 0.20,                      # 20% chance to apply greasy debuff
        "on_hit_ignite_if_greasy": 0.10,                   # 10% chance to ignite if target already greasy
        "on_kill_skill_xp": {"skill": "Deep-Frying", "amount": 15},
        "value": 48,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    # ── METH LAB WEAPONS ─────────────────────────────────────────────────────
    "uranium_tip_spear": {
        "name": "Uranium Tip Spear",
        "char": "/",
        "color": (80, 255, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 14,
        "str_req": 8,
        "reach": 2,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 8
        "weapon_type": "stabbing",
        "on_hit_rad": {"enemy": 5, "self": 2},            # irradiates both target and wielder
        "value": 75,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "syringe_lance": {
        "name": "Syringe Lance",
        "char": "/",
        "color": (180, 80, 255),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 12,
        "str_req": 10,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 1},  # +1 dmg per STR above 10
        "weapon_type": "stabbing",
        "on_hit_tox": {"enemy": 4},                        # injects toxicity into target
        "value": 70,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "tox_barbed_shiv": {
        "name": "Tox-Barbed Shiv",
        "char": "/",
        "color": (160, 200, 40),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "str_req": 6,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 6
        "weapon_type": "stabbing",
        "on_hit_tox": {"self": 3},                         # self-poison on attack
        "thorns": 3,                                        # reflect 3 dmg when hit by monster
        "value": 65,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "extra_sharp_hair_pick": {
        "name": "Extra Sharp Hair Pick",
        "char": "/",
        "color": (220, 220, 240),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 5,
        "str_req": 3,
        "reach": 1,
        "weapon_type": "stabbing",
        "stat_scaling": {"type": "swagger_linear", "divisor": 1, "multiplier": 2},  # +2 dmg per Swagger
        "value": 55,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "lethal_shiv": {
        "name": "Lethal Shiv",
        "char": "/",
        "color": (180, 40, 40),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 11,
        "str_req": 7,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 7
        "weapon_type": "stabbing",
        "execute": {"threshold": 0.30, "multiplier": 1.5},  # +50% dmg when target below 30% HP
        "value": 70,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "prison_shank": {
        "name": "Prison Shank",
        "char": "/",
        "color": (150, 150, 160),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 9,
        "str_req": 5,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 5
        "weapon_type": "stabbing",
        "bonus_crit_mult": 1,                               # +1x crit multiplier (2x -> 3x)
        "value": 60,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
    },
    "shard_of_meth": {
        "name": "Shard of Meth",
        "char": "/",
        "color": (100, 200, 255),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 6,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 6
        "weapon_type": "stabbing",
        "on_hit_meth": 5,                                   # gain 5 meth per hit
        "value": 65,
        "zones": ["meth_lab"],
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
    "nutrient_producer": {
        "name": "Nutrient Producer",
        "char": "Θ",
        "color": (120, 220, 80),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 80,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "pack_of_cones": {
        "name": "Pack of Cones",
        "char": "~",
        "color": (240, 230, 200),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "primary_skill": "Rolling",
        "zones": ["crack_den"],
        "tool_charges": 20,
        "tool_charges_min": 5,
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
    "red_spray_paint": {
        "name": "Red Spray Paint",
        "char": "!",
        "color": (255, 40, 40),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "tool_charges": 10,
        "use_verb": "Spray",
        "use_effect": {"type": "spray_paint", "spray_type": "red"},
    },
    "blue_spray_paint": {
        "name": "Blue Spray Paint",
        "char": "!",
        "color": (40, 100, 255),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "tool_charges": 10,
        "use_verb": "Spray",
        "use_effect": {"type": "spray_paint", "spray_type": "blue"},
    },
    "green_spray_paint": {
        "name": "Green Spray Paint",
        "char": "!",
        "color": (40, 200, 40),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "tool_charges": 10,
        "use_verb": "Spray",
        "use_effect": {"type": "spray_paint", "spray_type": "green"},
    },
    "orange_spray_paint": {
        "name": "Orange Spray Paint",
        "char": "!",
        "color": (255, 160, 40),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "tool_charges": 10,
        "use_verb": "Spray",
        "use_effect": {"type": "spray_paint", "spray_type": "orange"},
    },
    "silver_spray_paint": {
        "name": "Silver Spray Paint",
        "char": "!",
        "color": (200, 200, 210),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "tool_charges": 10,
        "use_verb": "Spray",
        "use_effect": {"type": "spray_paint", "spray_type": "silver"},
    },
    "graffiti_gun": {
        "name": "Graffiti Gun",
        "char": "G",
        "color": (180, 180, 180),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "tool_charges": None,
        "use_verb": None,
        "use_effect": None,
    },
    "ag_sword": {
        "name": "AG Sword",
        "char": chr(0xE006),
        "color": (255, 215, 0),
        "color_pulse": [(180, 150, 0), (255, 230, 50)],
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 15,
        "str_req": 15,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "slashing",
        "value": 400,
        "tags": ["ag_sword", "spec_weapon", "unique"],
        "name_alternating": [(255, 215, 0), (200, 170, 0)],
        "grants_ability": "ags_charge",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "really_old_maul": {
        "name": "Really Old Maul",
        "char": chr(0xE010),
        "color": (255, 140, 40),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 15,
        "str_req": 14,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "beating",
        "value": 300,
        "tags": ["really_old_maul", "spec_weapon", "unique"],
        "name_alternating": [(255, 140, 40), (40, 40, 40)],
        "grants_ability": "polarize",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "dragon_dagger": {
        "name": "Dragon Dagger",
        "char": "/",
        "color": (220, 80, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "str_req": 8,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "stabbing",
        "value": 250,
        "tags": ["dragon_dagger", "spec_weapon", "unique"],
        "name_gradient": [(180, 40, 40), (255, 140, 60)],
        "grants_ability": "ddd_puncture",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "yinyang_ichimonji": {
        "name": "Yinyang Ichimonji",
        "char": chr(0xE006),
        "color": (200, 200, 200),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 10,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "slashing",
        "value": 200,
        "tags": ["ramp_damage", "unique"],
        "name_gradient": [(30, 30, 30), (255, 255, 255)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "sleeper_agent": {
        "name": "Sleeper Agent",
        "char": chr(0xE007),
        "color": (140, 170, 140),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 6,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 3},
        "weapon_type": "stabbing",
        "value": 200,
        "tags": ["sleeper_agent", "unique"],
        "name_alternating": [(100, 255, 100), (180, 80, 255)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "rune_scraper": {
        "name": "Rune Scraper",
        "char": chr(0xE007),
        "color": (160, 60, 220),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 15,
        "bks_req": 10,
        "reach": 1,
        "bks_scaling": {"divisor": 2},
        "weapon_type": "stabbing",
        "value": 250,
        "tags": ["rune_scraper", "unique"],
        "name_gradient": [(160, 60, 220), (30, 10, 40)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "whirlwind_axe": {
        "name": "Whirlwind Axe",
        "char": chr(0xE00E),
        "color": (200, 80, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 15,
        "str_req": 14,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "slashing",
        "value": 250,
        "tags": ["whirlwind_axe", "unique"],
        "name_gradient": [(220, 60, 60), (140, 140, 140)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "massive_blunt": {
        "name": "Massive Blunt",
        "char": chr(0xE008),
        "color": (80, 200, 60),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 12,
        "str_req": 12,
        "tol_req": 12,
        "reach": 1,
        "str_scaling": {"type": "none"},
        "tol_scaling": {"divisor": 2},
        "weapon_type": "beating",
        "value": 250,
        "tags": ["massive_blunt", "unique"],
        "name_gradient": [(139, 90, 43), (50, 255, 50)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "double_edged_sword": {
        "name": "Double Edged Sword",
        "char": chr(0xE006),
        "color": (180, 180, 180),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 20,
        "str_req": 10,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},
        "weapon_type": "slashing",
        "value": 120,
        "tags": ["double_edged"],
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "mithril_axe": {
        "name": "Mithril Axe",
        "char": "/",
        "color": (160, 200, 230),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 8,
        "str_req": 8,
        "reach": 1,
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above 8
        "weapon_type": "slashing",
        "skill_scaling": {"skill": "Slashing", "bonus_per_level": 2},  # +2 dmg per Slashing level
        "value": 100,
        "zones": ["crack_den"],
        "use_verb": None,
        "use_effect": None,
    },
    "staff_of_fire": {
        "name": "Staff of Fire",
        "char": "/",
        "color": (255, 100, 30),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "stat_reqs": {"book_smarts": 12},
        "reach": 1,
        "weapon_type": "beating",
        "staff_element": "fire",
        "staff_charges": 5,
        "value": 150,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "staff_of_lightning": {
        "name": "Staff of Lightning",
        "char": "/",
        "color": (255, 255, 80),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "stat_reqs": {"book_smarts": 12},
        "reach": 1,
        "weapon_type": "beating",
        "staff_element": "lightning",
        "staff_charges": 5,
        "value": 150,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "staff_of_ice": {
        "name": "Staff of Ice",
        "char": "/",
        "color": (100, 200, 255),
        "category": "equipment",
        "subcategory": "weapon",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "base_damage": 10,
        "stat_reqs": {"book_smarts": 12},
        "reach": 1,
        "weapon_type": "beating",
        "staff_element": "cold",
        "staff_charges": 5,
        "value": 150,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "rosary": {
        "name": "Rosary",
        "char": chr(0xE005),
        "color": (212, 175, 55),
        "category": "equipment",
        "subcategory": "neck",
        "equip_slot": "neck",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 10,
        "stat_bonus": {},
        "tags": ["rosary"],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "amulet_of_equivalent_exchange": {
        "name": "Amulet of Equivalent Exchange",
        "char": chr(0xE009),
        "color": (160, 120, 200),
        "category": "equipment",
        "subcategory": "neck",
        "equip_slot": "neck",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 20,
        "stat_bonus": {},
        "tags": ["amulet_ee", "unique"],
        "name_gradient": [(160, 160, 160), (160, 50, 220), (160, 160, 160)],
        "grants_abilities": ["soul_cleanse", "soul_mend", "soul_empower"],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "cuban_link": {
        "name": "Cuban Link",
        "char": "#",
        "color": (255, 220, 50),
        "category": "equipment",
        "subcategory": "neck",
        "equip_slot": "neck",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 50,
        "stat_bonus": {},
        "reach_bonus": 1,
        "tags": ["cuban_link", "unique"],
        "name_alternating": [(255, 255, 80), (160, 120, 40), (212, 175, 55)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "nine_ring": {
        "name": "The 9 Ring",
        "char": chr(0xE00A),
        "color": (255, 220, 50),
        "category": "equipment",
        "subcategory": "ring",
        "equip_slot": "ring",
        "power_bonus": 0,
        "defense_bonus": 0,
        "stat_bonus": {
            "constitution": 5,
            "strength": 5,
            "book_smarts": 5,
            "street_smarts": 5,
            "tolerance": 5,
            "swagger": 5,
        },
        "tags": ["nine_ring", "unique"],
        "name_gradient": [(180, 150, 0), (255, 255, 80)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "berserkers_ring": {
        "name": "Berserker's Ring",
        "char": chr(0xE00A),
        "color": (200, 200, 210),
        "category": "equipment",
        "subcategory": "ring",
        "equip_slot": "ring",
        "power_bonus": 0,
        "defense_bonus": 0,
        "stat_bonus": {"strength": 4},
        "tags": ["berserkers_ring", "unique"],
        "name_gradient": [(200, 200, 210), (255, 215, 0), (200, 200, 210)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "boots_of_blinding_speed": {
        "name": "Boots of Blinding Speed",
        "char": chr(0xE00B),
        "color": (100, 200, 255),
        "category": "equipment",
        "subcategory": "feet",
        "equip_slot": "feet",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {},
        "energy_per_tick": 50,
        "fov_penalty": 2,
        "tags": ["blinding_speed", "unique"],
        "name_gradient": [(80, 180, 255), (200, 240, 255), (255, 255, 255)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "boots_of_springing": {
        "name": "Boots of Springing",
        "char": chr(0xE00B),
        "color": (160, 120, 70),
        "category": "equipment",
        "subcategory": "feet",
        "equip_slot": "feet",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {},
        "energy_per_tick": 20,
        "fov_penalty": 0,
        "tags": ["springing_boots", "unique"],
        "name_gradient": [(160, 120, 70), (60, 40, 20)],
        "grants_ability": "spring",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "boots_of_striding": {
        "name": "Boots of Striding",
        "char": chr(0xE00B),
        "color": (120, 80, 40),
        "category": "equipment",
        "subcategory": "feet",
        "equip_slot": "feet",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {},
        "energy_per_tick": 20,
        "fov_penalty": 0,
        "tags": ["striding_boots", "unique"],
        "name_gradient": [(60, 40, 20), (160, 120, 70)],
        "grants_ability": "stride",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "titans_blood_ring": {
        "name": "Titan's Blood Ring",
        "char": chr(0xE00A),
        "color": (200, 30, 30),
        "category": "equipment",
        "subcategory": "ring",
        "equip_slot": "ring",
        "power_bonus": 0,
        "defense_bonus": 0,
        "stat_bonus": {},
        "tags": ["titan_blood", "unique"],
        "name_gradient": [(30, 10, 10), (200, 30, 30), (30, 10, 10)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "ring_of_intimidation": {
        "name": "Ring of Intimidation",
        "char": "o",
        "color": (200, 50, 50),
        "category": "equipment",
        "subcategory": "ring",
        "equip_slot": "ring",
        "power_bonus": 0,
        "defense_bonus": 0,
        "stat_bonus": {},
        "tags": ["intimidation_ring", "unique"],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "ring_of_sustenance": {
        "name": "Ring of Sustenance",
        "char": chr(0xE00A),
        "color": (240, 160, 40),
        "category": "equipment",
        "subcategory": "ring",
        "equip_slot": "ring",
        "power_bonus": 0,
        "defense_bonus": 0,
        "stat_bonus": {},
        "tags": ["sustenance_ring", "unique"],
        "name_gradient": [(240, 130, 30), (255, 240, 80)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "brainstorming_cap": {
        "name": "Brainstorming Cap",
        "char": chr(0xE00D),
        "color": (40, 60, 180),
        "category": "equipment",
        "subcategory": "hat",
        "equip_slot": "hat",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {"book_smarts": 5},
        "tags": ["brainstorming_cap", "unique"],
        "name_gradient": [(30, 40, 160), (220, 230, 255)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "thinking_cap": {
        "name": "Thinking Cap",
        "char": chr(0xE00D),
        "color": (40, 60, 180),
        "category": "equipment",
        "subcategory": "hat",
        "equip_slot": "hat",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {"book_smarts": 5},
        "tags": ["thinking_cap", "unique"],
        "name_gradient": [(30, 40, 160), (220, 230, 255)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "flagellants_mask": {
        "name": "Flagellant's Mask",
        "char": chr(0xE00D),
        "color": (180, 50, 50),
        "category": "equipment",
        "subcategory": "hat",
        "equip_slot": "hat",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 0,
        "stat_bonus": {},
        "tags": ["flagellant", "unique"],
        "name_gradient": [(180, 50, 50), (80, 20, 20)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "straw_hat": {
        "name": "Straw Hat",
        "char": chr(0xE00D),
        "color": (200, 180, 80),
        "category": "equipment",
        "subcategory": "hat",
        "equip_slot": "hat",
        "power_bonus": 0,
        "defense_bonus": 0,
        "armor_bonus": 20,
        "stat_bonus": {
            "constitution": 2,
            "strength": 2,
            "book_smarts": 2,
            "street_smarts": 2,
            "tolerance": 2,
            "swagger": 2,
        },
        "tags": ["straw_hat", "unique"],
        "name_gradient": [(30, 30, 30), (220, 200, 80)],
        "zones": [],
        "use_verb": None,
        "use_effect": None,
    },
    "voodoo_doll": {
        "name": "Voodoo Doll",
        "char": chr(0xE011),
        "color": (140, 60, 180),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 20,
        "use_verb": "Use",
        "use_effect": {
            "type": "voodoo_detonate",
            "skill_xp": {"Blackkk Magic": 100},
        },
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
    "xl_bic_torch": {
        "name": "XL BIC Torch",
        "char": "t",
        "color": (255, 200, 50),
        "category": "tool",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": "Pyromania",
        "zones": ["meth_lab"],
        "torch_xp_mult": 1.5,
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
    "blue_meth_joint": {
        "name": "Blue Meth Joint",
        "char": "j",
        "color": (0, 180, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "primary_skill": "Smoking",
        "secondary_skill": "Meth-Head",
        "use_verb": "Smoke",
        "use_effect": {"type": "blue_meth_smoke"},
    },
    # Alcohol consumables
    "40oz": {
        "name": "40oz Bottle",
        "char": "!",
        "color": (210, 180, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "Smacking",
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
        "value": 50,
        "skill": "Pyromania",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "fireball_shooter"},
    },
    "limoncello": {
        "name": "Limoncello",
        "char": "!",
        "color": (255, 240, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": "Electrodynamics",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "limoncello"},
    },
    "blue_lagoon": {
        "name": "Blue Lagoon",
        "char": "!",
        "color": (100, 200, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "Cryomancy",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "blue_lagoon"},
    },
    "natty_light": {
        "name": "Natty Light",
        "char": "!",
        "color": (180, 200, 230),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "skill": "Drinking",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "natty_light"},
        "spawn_quantity": 6,
    },
    "jagermeister": {
        "name": "Jagermeister",
        "char": "!",
        "color": (60, 80, 40),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": "Smacking",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "jagermeister"},
    },
    "butterbeer": {
        "name": "Butterbeer",
        "char": "!",
        "color": (230, 190, 100),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": "Drinking",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "butterbeer"},
    },
    "absinthe": {
        "name": "Absinthe",
        "char": "!",
        "color": (100, 220, 100),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": "Drinking",
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "absinthe"},
    },
    "malt_liquor": {
        "name": "Malt Liquor",
        "char": "!",
        "color": (200, 200, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": ["Beating", "Slashing", "Stabbing"],
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "malt_liquor"},
    },
    "wizard_mind_bomb": {
        "name": "Wizard Mind Bomb",
        "char": "!",
        "color": (120, 80, 220),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "Smartsness",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "wizard_mind_bomb"},
    },
    "homemade_hennessy": {
        "name": "Homemade Hennessy",
        "char": "!",
        "color": (200, 150, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "Smoking",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "homemade_hennessy"},
    },
    "steel_reserve": {
        "name": "Steel Reserve Can",
        "char": "!",
        "color": (160, 160, 160),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "L Farming",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "steel_reserve"},
    },
    "speedball": {
        "name": "Speedball",
        "char": "!",
        "color": (255, 80, 200),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": "Meth-Head",
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "speedball"},
    },
    # Meth Lab alcoholic drinks
    "mana_drink": {
        "name": "Mana Booze",
        "char": "!",
        "color": (0, 220, 220),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "Smartsness",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "mana_drink"},
    },
    "virulent_vodka": {
        "name": "Virulent Vodka",
        "char": "!",
        "color": (0, 200, 0),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "Chemical Warfare",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "virulent_vodka"},
    },
    "five_loco": {
        "name": "Five Loco",
        "char": "!",
        "color": (255, 100, 180),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "Mutation",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "five_loco"},
    },
    "white_gonster": {
        "name": "White Gonster",
        "char": "!",
        "color": (255, 255, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "White Power",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "white_gonster"},
    },
    "platinum_reserve": {
        "name": "Platinum Reserve",
        "char": "!",
        "color": (210, 210, 230),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "Decontamination",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "platinum_reserve"},
    },
    "dead_shot_daiquiri": {
        "name": "Dead Shot Daiquiri",
        "char": "!",
        "color": (255, 200, 100),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "Ammo Rat",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "dead_shot_daiquiri"},
    },
    "alco_seltzer": {
        "name": "Alco-Seltzer",
        "char": "!",
        "color": (200, 240, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": "White Power",
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "alco_seltzer"},
    },
    "rainbow_rotgut": {
        "name": "Rainbow Rotgut",
        "char": "!",
        "color": (255, 100, 200),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": ["Cryomancy", "Electrodynamics", "Pyromania"],
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "rainbow_rotgut"},
    },
    "root_beer": {
        "name": '"Root" Beer',
        "char": "!",
        "color": (140, 80, 40),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 60,
        "skill": ["Slashing", "Stabbing", "Beating"],
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "root_beer"},
    },
    "sangria_40": {
        "name": "Sangria 40",
        "char": "!",
        "color": (160, 30, 60),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 75,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "alcohol", "drink_id": "sangria_40"},
    },
    "midas_brew": {
        "name": "Midas' Brew",
        "char": "!",
        "color": (212, 175, 55),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "weight": 2,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "name_gradient": [(212, 175, 55), (255, 255, 100)],
        "use_effect": {"type": "midas_brew", "consumed": False},
    },
    # Nonalcoholic drinks (Dranks) — no skill weighting
    "purple_drank": {
        "name": "Purple Drank",
        "char": "!",
        "color": (180, 60, 220),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "purple_drank"},
    },
    "blue_drank": {
        "name": "Blue Drank",
        "char": "!",
        "color": (40, 150, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "blue_drank"},
    },
    "red_drank": {
        "name": "Red Drank",
        "char": "!",
        "color": (220, 40, 40),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "red_drank"},
    },
    "green_drank": {
        "name": "Green Drank",
        "char": "!",
        "color": (40, 200, 60),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "green_drank"},
    },
    "orange_drank": {
        "name": "Orange Drank",
        "char": "!",
        "color": (255, 150, 30),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 25,
        "skill": None,
        "zones": ["crack_den"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "orange_drank"},
    },
    # Kool-Aid — rare consumables, permanent +1 to a stat
    "red_kool_aid": {
        "name": "Red Kool-Aid",
        "char": "!",
        "color": (255, 50, 50),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "red_kool_aid"},
    },
    "blue_kool_aid": {
        "name": "Blue Kool-Aid",
        "char": "!",
        "color": (60, 130, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "blue_kool_aid"},
    },
    "purple_kool_aid": {
        "name": "Purple Kool-Aid",
        "char": "!",
        "color": (180, 60, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "purple_kool_aid"},
    },
    "green_kool_aid": {
        "name": "Green Kool-Aid",
        "char": "!",
        "color": (50, 220, 70),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "green_kool_aid"},
    },
    "orange_kool_aid": {
        "name": "Orange Kool-Aid",
        "char": "!",
        "color": (255, 165, 30),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "orange_kool_aid"},
    },
    "yellow_kool_aid": {
        "name": "Yellow Kool-Aid",
        "char": "!",
        "color": (255, 240, 60),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 125,
        "skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "yellow_kool_aid"},
    },
    "sparkling_water": {
        "name": "Sparkling Water",
        "char": "!",
        "color": (200, 230, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "skill": None,
        "zones": ["meth_lab"],
        "use_verb": "Drink",
        "use_effect": {"type": "soft_drink", "drink_id": "sparkling_water"},
    },
    # Meth Lab consumables
    "blue_meth": {
        "name": "Blue Meth",
        "char": "%",
        "color": (0, 180, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 50,
        "skill": "Meth-Head",
        "zones": ["meth_lab"],
        "use_verb": "Use",
        "use_effect": {"type": "meth", "amount": 30},
    },
    # Meth lab consumables — instant use, not food
    "altoid": {
        "name": "Altoid",
        "char": "%",
        "color": (200, 240, 240),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "skill": "White Power",
        "zones": ["meth_lab"],
        "use_verb": "Use",
        "use_effect": {"type": "remove_toxicity", "amount": 50},
    },
    "asbestos": {
        "name": "Asbestos",
        "char": "%",
        "color": (180, 180, 160),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "skill": "Chemical Warfare",
        "zones": ["meth_lab"],
        "use_verb": "Use",
        "use_effect": {"type": "add_toxicity", "amount": 50},
    },
    "rad_away": {
        "name": "Rad Away",
        "char": "%",
        "color": (100, 200, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "skill": "Decontamination",
        "zones": ["meth_lab"],
        "use_verb": "Use",
        "use_effect": {"type": "remove_radiation", "amount": 50},
    },
    "radbar": {
        "name": "RadBar",
        "char": "%",
        "color": (100, 220, 50),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "skill": "Nuclear Research",
        "zones": ["meth_lab"],
        "use_verb": "Use",
        "use_effect": {"type": "add_radiation", "amount": 50},
    },
    "scrap": {
        "name": "Scrap",
        "char": "*",
        "color": (160, 130, 80),
        "category": "material",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 25,
        "skill": "Dismantling",
        "zones": [],
        "use_verb": None,
        "use_effect": None,
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
        "category": "consumable",
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
    "muffin": {
        "name": "Muffin",
        "char": "f",
        "color": (255, 220, 130),
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
        "use_effect": {"type": "food", "food_id": "muffin"},
    },
    "protein_powder": {
        "name": "Protein Powder",
        "char": "f",
        "color": (220, 180, 255),
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
        "use_effect": {"type": "food", "food_id": "protein_powder"},
    },
    "jolly_rancher": {
        "name": "Jolly Rancher",
        "char": "f",
        "color": (255, 100, 200),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 70,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "jolly_rancher"},
    },
    "holy_wafer": {
        "name": "Holy Wafer",
        "char": "f",
        "color": (255, 255, 200),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "holy_wafer"},
    },
    "mirror_cake": {
        "name": "Mirror Cake",
        "char": "f",
        "color": (150, 200, 255),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 70,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "mirror_cake"},
    },
    "hard_boiled_egg": {
        "name": "Hard Boiled Egg",
        "char": "f",
        "color": (255, 255, 220),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 100,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "hard_boiled_egg"},
    },
    "carrot_cake": {
        "name": "Carrot Cake",
        "char": "f",
        "color": (255, 180, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 70,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["crack_den", "meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "carrot_cake"},
    },
    "yellowcake": {
        "name": "Yellowcake",
        "char": "f",
        "color": (255, 255, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 120,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "yellowcake"},
    },
    "jell_o": {
        "name": "Jell-O",
        "char": "f",
        "color": (255, 100, 120),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "jell_o"},
    },
    "meatball_sub": {
        "name": "Meatball Sub",
        "char": "f",
        "color": (180, 80, 40),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "meatball_sub"},
    },
    "heinz_baked_beans": {
        "name": "Heinz Baked Beans",
        "char": "f",
        "color": (180, 100, 50),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 30,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": "Eat",
        "use_effect": {"type": "food", "food_id": "heinz_baked_beans"},
    },
    "mature_spider_egg": {
        "name": "Mature Spider Egg",
        "char": "o",
        "color": (100, 180, 80),
        "category": "consumable",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 40,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": "Hatch",
        "use_effect": {"type": "spawn_spider_hatchling"},
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
    # --- Guns ----------------------------------------------------------------
    "decimator": {
        "name": "Decimator",
        "char": chr(0xE00C),
        "color": (255, 120, 40),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (0, 0),
        "gun_range": 6,
        "ammo_type": "heavy",
        "mag_size": 1,
        "reload_speed": 0,
        "gun_class": "small",
        "reload_per_floor": 1,
        "tags": ["decimator", "unique"],
        "name_gradient": [(255, 120, 40), (200, 30, 30)],
        "gun_stats": {"hit": 100, "energy": 50},
    },
    "thunder_gun": {
        "name": "Thunder Gun",
        "char": chr(0xE00F),
        "color": (255, 255, 80),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 350,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (1, 30),
        "gun_range": 6,
        "ammo_type": "medium",
        "mag_size": 10,
        "reload_speed": 100,
        "gun_class": "medium",
        "aoe_type": "target",
        "tags": ["thunder_gun", "unique"],
        "name_gradient": [(255, 255, 80), (80, 120, 255)],
        "gun_stats": {"hit": 80, "energy": 70},
    },
    "ruger_mark_v": {
        "name": "Ruger Mark V",
        "char": ")",
        "color": (180, 180, 200),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 80,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (6, 8),
        "gun_range": 4,
        "ammo_type": "light",
        "mag_size": 10,
        "reload_speed": 0,        # energy cost to reload (0 = free action)
        "gun_class": "small",     # small = sidearm slot, medium/large = weapon slot
        "gun_stats": {"hit": 80, "energy": 45},
    },
    "hv_express": {
        "name": "HV Express",
        "char": ")",
        "color": (140, 160, 190),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 200,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (6, 8),
        "gun_range": 8,
        "ammo_type": "light",
        "mag_size": 5,
        "reload_speed": 100,          # energy cost to reload
        "gun_class": "medium",        # medium = weapon slot only
        "aoe_type": "target",
        "consecutive_bonus": 2,       # +2 dmg per consecutive hit on same target (stacking)
        "gun_stats": {"hit": 80, "energy": 65},
    },
    "glizzy_19": {
        "name": "Glizzy-19",
        "char": ")",
        "color": (60, 60, 60),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (11, 15),
        "gun_range": 5,
        "ammo_type": "light",
        "mag_size": 15,               # default; overridden by mag_size_options on spawn
        "mag_size_options": [15, 17, 19, 24, 33],
        "reload_speed": 0,            # free action
        "gun_class": "small",         # small = sidearm slot only
        "aoe_type": "target",         # line AOE (first target only until piercing added)
        "grants_ability": "double_tap",
        "gun_stats": {"hit": 70, "energy": 60},
    },
    "uzi": {
        "name": "UZI",
        "char": ")",
        "color": (100, 100, 115),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 350,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (8, 10),
        "gun_range": 5,
        "ammo_type": "light",
        "mag_size": 32,               # drum mag
        "reload_speed": 80,           # energy cost to reload
        "gun_class": "small",         # small = sidearm slot only
        "aoe_type": "cone",
        "cone_angle": 30,             # degrees
        "ammo_per_shot": (3, 4),      # random 3-4 rounds per fire action
        "gun_stats": {"hit": 50, "energy": 45},
    },
    "ar_14": {
        "name": "AR-14",
        "char": ")",
        "color": (120, 130, 110),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (12, 32),
        "gun_range": 6,
        "ammo_type": "medium",
        "mag_size": 30,
        "reload_speed": 100,
        "gun_class": "medium",         # medium = weapon slot only
        "aoe_type": "line",
        "cone_angle": 30,             # used by Spray ability
        "grants_ability": "spray",
        "gun_stats": {"hit": 80, "energy": 55},
    },
    "sawed_off": {
        "name": "Sawed Off",
        "char": ")",
        "color": (160, 120, 80),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (10, 25),
        "gun_range": 4,
        "ammo_type": "medium",
        "mag_size": 2,
        "reload_speed": 50,
        "gun_class": "small",              # small = sidearm slot
        "aoe_type": "cone",
        "cone_angle": 90,
        "projectiles": 5,
        "gun_stats": {"hit": 55, "energy": 100},
    },
    "m16": {
        "name": "M16",
        "char": ")",
        "color": (130, 140, 110),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (15, 28),
        "gun_range": 6,
        "ammo_type": "medium",
        "mag_size": 30,
        "reload_speed": 100,
        "gun_class": "medium",              # medium = weapon slot only
        "aoe_type": "line",
        "grants_ability": "burst",
        "gun_stats": {"hit": 65, "energy": 60},
    },
    "tec_9": {
        "name": "Tec-9",
        "char": ")",
        "color": (90, 90, 95),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "sidearm",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 250,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (9, 14),
        "gun_range": 5,
        "ammo_type": "light",
        "mag_size": 20,
        "reload_speed": 60,
        "gun_class": "small",
        "aoe_type": "target",
        "jam_chance": 18,             # % chance to jam per shot
        "jam_clear_cost": 100,        # energy cost to clear jam (full turn)
        "grants_ability": "spray_and_pray",
        "gun_stats": {"hit": 60, "energy": 30},
    },
    "rpg": {
        "name": "RPG",
        "char": ")",
        "color": (100, 130, 80),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 400,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (40, 50),
        "gun_range": 10,
        "ammo_type": "heavy",
        "mag_size": 1,
        "reload_speed": 150,
        "gun_class": "large",
        "aoe_type": "circle",
        "aoe_radius": 2,
        "gun_stats": {"hit": 80, "energy": 90},
    },
    "cruiser_500": {
        "name": "Cruiser 500",
        "char": ")",
        "color": (140, 100, 60),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 400,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (18, 22),
        "gun_range": 5,
        "ammo_type": "medium",
        "mag_size": 8,
        "reload_speed": 200,
        "gun_class": "medium",              # medium = weapon slot only
        "aoe_type": "cone",
        "cone_angle": 90,
        "projectiles": 5,
        "gun_stats": {"hit": 70, "energy": 90},
    },
    "draco": {
        "name": "Draco",
        "char": ")",
        "color": (110, 90, 70),
        "category": "equipment",
        "subcategory": "gun",
        "equip_slot": "weapon",
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 300,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": ["meth_lab"],
        "use_verb": None,
        "use_effect": None,
        "base_damage": (15, 35),
        "gun_range": 6,
        "ammo_type": "medium",
        "mag_size": 30,
        "reload_speed": 60,
        "gun_class": "medium",              # medium = weapon slot only
        "aoe_type": "line",
        "gun_stats": {"hit": 50, "energy": 55},
    },
    # --- Ammo ----------------------------------------------------------------
    "light_rounds": {
        "name": "Light Rounds",
        "char": "=",
        "color": (200, 180, 100),
        "category": "ammo",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 5,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
        "ammo_type": "light",
    },
    "medium_rounds": {
        "name": "Medium Rounds",
        "char": "=",
        "color": (180, 160, 80),
        "category": "ammo",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 8,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
        "ammo_type": "medium",
    },
    "heavy_rounds": {
        "name": "Heavy Rounds",
        "char": "=",
        "color": (160, 130, 60),
        "category": "ammo",
        "subcategory": None,
        "equip_slot": None,
        "power_bonus": 0,
        "defense_bonus": 0,
        "value": 15,
        "primary_skill": None,
        "secondary_skill": None,
        "tertiary_skill": None,
        "zones": [],
        "use_verb": None,
        "use_effect": None,
        "ammo_type": "heavy",
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


_METH_LAB_STRAINS = frozenset({
    "Iron Lung", "Skywalker OG", "Street Scholar",
    "Kushenheimer", "Nigle Fart", "Purple Halt",
})


def get_item_value(item_id: str, strain: str = None) -> int:
    """Return the base value of an item.

    Reads the 'value' field from ITEM_DEFS. Falls back to 10 for unknown items.
    Joints with meth lab strains are valued higher.
    """
    item_def = ITEM_DEFS.get(item_id)
    if item_def is None:
        return 10
    base = item_def.get("value", 10)
    if item_id == "joint" and strain and strain in _METH_LAB_STRAINS:
        return 100
    return base


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
    ("kush", "pack_of_cones"): {
        "result": "joint",
        "consumed": ["kush"],               # pack_of_cones loses a charge
    },
    ("kush", "spectral_paper"): {
        "result": "joint",
        "consumed": ["kush"],               # spectral paper is a reusable tool
    },
    ("blue_meth", "pack_of_cones"): {
        "result": "blue_meth_joint",
        "consumed": ["blue_meth"],          # pack_of_cones loses a charge
    },
}


# ---------------------------------------------------------------------------
# Unique item tables
# ---------------------------------------------------------------------------

UNIQUE_TABLE_A = [
    "ag_sword",
    "really_old_maul",
    "dragon_dagger",
    "yinyang_ichimonji",
    "sleeper_agent",
    "rune_scraper",
    "whirlwind_axe",
    "massive_blunt",
    "amulet_of_equivalent_exchange",
    "cuban_link",
    "nine_ring",
    "berserkers_ring",
    "boots_of_blinding_speed",
    "boots_of_springing",
    "boots_of_striding",
    "titans_blood_ring",
    "ring_of_intimidation",
    "ring_of_sustenance",
    "brainstorming_cap",
    "thinking_cap",
    "flagellants_mask",
    "straw_hat",
    "decimator",
    "thunder_gun",
]


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


def _pluralize(name, item_id=None):
    """Pluralize an item name for inventory display.

    Checks for an explicit 'plural' override in ITEM_DEFS first,
    then applies standard English pluralization rules.
    """
    if item_id is not None:
        defn = ITEM_DEFS.get(item_id)
        if defn and "plural" in defn:
            return defn["plural"]

    if name.endswith(("s", "S", ")")):
        return name

    lower = name.lower()

    if lower.endswith(("ch", "sh", "x", "z")):
        return name + "es"

    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return name[:-1] + "ies"

    if lower.endswith("fe"):
        return name[:-2] + "ves"

    return name + "s"


def build_inventory_display_name(item_id, strain, quantity, prefix=None, charges=None, max_charges=None):
    """Build the inventory panel display name for an item, respecting gram-based naming.

    weed_nug: "1g nug OG Kush" / "3g nugs OG Kush"
    kush:     "1g OG Kush"     / "3g OG Kush"
    prefixed food: "Greasy Chicken (2/2)"
    others:   "1 Knife" / "3 Knives"
    """
    qty = quantity or 1
    strain_part = f" {strain}" if strain else ""

    if item_id == "weed_nug":
        noun = "Nugs" if qty > 1 else "Nug"
        return f"{qty}g {noun}{strain_part}"

    if item_id == "kush":
        return f"{qty}g{strain_part}"

    defn = ITEM_DEFS.get(item_id)
    base_name = defn["name"] if defn else "Unknown"

    if prefix is not None and charges is not None and max_charges is not None:
        pdef = get_food_prefix_def(prefix)
        adj = pdef["display_adjective"] if pdef else prefix.title()
        if qty > 1:
            return f"{qty} {adj} {_pluralize(base_name, item_id)}{strain_part} ({charges}/{max_charges})"
        return f"{adj} {base_name}{strain_part} ({charges}/{max_charges})"

    # Tools with limited charges (e.g. Pack of Cones)
    if defn and defn.get("tool_charges") and charges is not None and max_charges is not None:
        return f"{base_name} ({charges}/{max_charges})"

    if qty > 1:
        return f"{qty} {_pluralize(base_name, item_id)}{strain_part}"
    return f"1 {base_name}{strain_part}"


def get_item_def(item_id):
    """Return the definition dict for an item_id, or None."""
    return ITEM_DEFS.get(item_id)


def weapon_matches_type(wdefn, weapon_type):
    """Check if a weapon definition matches a weapon_type (primary or alt)."""
    if not wdefn:
        return False
    return wdefn.get("weapon_type") == weapon_type or wdefn.get("weapon_type_alt") == weapon_type


_STACKABLE_CATEGORIES = {"material", "consumable", "ammo"}

def is_stackable(item_id):
    """Return True if this item's category allows stacking (material or consumable)."""
    defn = ITEM_DEFS.get(item_id)
    if not defn or defn.get("category") not in _STACKABLE_CATEGORIES:
        return False
    return True


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
    elif item_a.item_id == "kush" and item_b.item_id in ("pack_of_cones", "spectral_paper"):
        return item_a.strain
    elif item_a.item_id in ("pack_of_cones", "spectral_paper") and item_b.item_id == "kush":
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
    if item_id == "nutrient_producer":
        return True
    # Consumable items can be combined with nutrient_producer
    defn = ITEM_DEFS.get(item_id)
    if defn and defn.get("category") == "consumable":
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

    if item_id == "graffiti_gun":
        actions.append("Fire")
        actions.append("Load")
        actions.append("Unload")

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


_ON_HIT_EFFECT_DESCS = {
    "glass_shards": "{stacks} stack, {duration} turns. 1 dmg/stack/turn.",
}


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

        # Skill scaling description
        sk_scaling = defn.get("skill_scaling")
        if sk_scaling:
            sk_name = sk_scaling["skill"]
            sk_bpl = sk_scaling.get("bonus_per_level", 1)
            sk_desc = f"+{sk_bpl} per {sk_name} level"
            lines.append([("Skill Scaling: ", C_LABEL), (sk_desc, C_INFO)])

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
                # Skill scaling bonus
                if sk_scaling:
                    sk_obj = engine.skills.skills.get(sk_scaling["skill"])
                    if sk_obj:
                        bonus += sk_obj.level * sk_scaling.get("bonus_per_level", 1)
                total = base_dmg + bonus
                lines.append([("Damage if equipped: ", C_LABEL), (str(total), C_VALUE)])

        lines.append([("STR Required: ", C_LABEL), (str(req), C_VALUE)])

        reach = defn.get("reach", 1)
        if reach > 1:
            lines.append([("Reach: ", C_LABEL), (f"{reach} tiles", C_VALUE)])

        # Special weapon properties
        if defn.get("on_hit_effect"):
            eff = defn["on_hit_effect"]
            eff_type = eff.get("type", "")
            eff_name = eff_type.replace("_", " ").title()
            # Add a description of what the effect does
            eff_desc = _ON_HIT_EFFECT_DESCS.get(eff_type)
            if eff_desc:
                dur = eff.get("duration", "")
                stacks = eff.get("stacks", 1)
                desc = eff_desc.format(duration=dur, stacks=stacks)
                lines.append([("On Hit: ", C_LABEL), (f"{eff_name}", C_GOOD)])
                lines.append([("  ", C_LABEL), (desc, C_INFO)])
            else:
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
        if defn.get("on_hit_meth"):
            lines.append([("On Hit: ", C_LABEL), (f"+{defn['on_hit_meth']} Meth", (100, 200, 255))])
        if defn.get("bonus_crit_mult"):
            lines.append([("Crit Bonus: ", C_LABEL), (f"+{defn['bonus_crit_mult']}x crit multiplier", C_GOOD)])
        if defn.get("execute"):
            ex = defn["execute"]
            pct_thresh = int(ex["threshold"] * 100)
            pct_bonus = int((ex["multiplier"] - 1) * 100)
            lines.append([("Execute: ", C_LABEL), (f"+{pct_bonus}% dmg below {pct_thresh}% HP", C_GOOD)])
        if defn.get("on_hit_rad"):
            r = defn["on_hit_rad"]
            lines.append([("On Hit: ", C_LABEL), (f"+{r['enemy']} rad (enemy), +{r['self']} rad (self)", (80, 255, 80))])
        if defn.get("on_hit_tox"):
            t = defn["on_hit_tox"]
            parts = []
            if t.get("enemy"):
                parts.append(f"+{t['enemy']} tox (enemy)")
            if t.get("self"):
                parts.append(f"+{t['self']} tox (self)")
            lines.append([("On Hit: ", C_LABEL), (", ".join(parts), (180, 80, 255))])
        if defn.get("thorns"):
            lines.append([("Thorns: ", C_LABEL), (f"{defn['thorns']} dmg when hit", C_GOOD)])
        if defn.get("grants_ability"):
            lines.append([("Grants: ", C_LABEL), (defn["grants_ability"].replace("_", " ").title(), C_GOOD)])

    # --- NECK EQUIPMENT (chains) ---
    elif subcategory == "neck":
        armor = defn.get("armor_bonus", 0)
        lines.append([("Armor: ", C_LABEL), (f"+{armor}", C_GOOD)])
        db = defn.get("defense_bonus", 0)
        if db:
            lines.append([("Defense: ", C_LABEL), (f"+{db}", C_GOOD)])
        ept = defn.get("energy_per_tick", 0)
        if ept:
            sign = "+" if ept > 0 else ""
            color = C_GOOD if ept > 0 else C_BAD
            lines.append([("Energy/Tick: ", C_LABEL), (f"{sign}{ept}", color)])
        tox_r = defn.get("tox_resistance", 0)
        if tox_r:
            sign = "+" if tox_r > 0 else ""
            color = C_GOOD if tox_r > 0 else C_BAD
            lines.append([("Tox Resist: ", C_LABEL), (f"{sign}{tox_r}%", color)])
        rad_r = defn.get("rad_resistance", 0)
        if rad_r:
            sign = "+" if rad_r > 0 else ""
            color = C_GOOD if rad_r > 0 else C_BAD
            lines.append([("Rad Resist: ", C_LABEL), (f"{sign}{rad_r}%", color)])
        sb = defn.get("stat_bonus", {})
        for stat, val in sb.items():
            stat_display = stat.replace("_", " ").title()
            lines.append([(f"{stat_display}: ", C_LABEL), (f"+{val}", C_GOOD)])

    # --- HAT EQUIPMENT ---
    elif subcategory == "hat":
        armor = defn.get("armor_bonus", 0)
        if armor:
            lines.append([("Armor: ", C_LABEL), (f"+{armor}", C_GOOD)])
        tox_r = defn.get("tox_resistance", 0)
        if tox_r:
            sign = "+" if tox_r > 0 else ""
            color = C_GOOD if tox_r > 0 else C_BAD
            lines.append([("Tox Resist: ", C_LABEL), (f"{sign}{tox_r}%", color)])
        rad_r = defn.get("rad_resistance", 0)
        if rad_r:
            sign = "+" if rad_r > 0 else ""
            color = C_GOOD if rad_r > 0 else C_BAD
            lines.append([("Rad Resist: ", C_LABEL), (f"{sign}{rad_r}%", color)])
        sb = defn.get("stat_bonus", {})
        for stat, val in sb.items():
            stat_display = stat.replace("_", " ").title()
            sign = "+" if val > 0 else ""
            color = C_GOOD if val > 0 else C_BAD
            lines.append([(f"{stat_display}: ", C_LABEL), (f"{sign}{val}", color)])
        ept = defn.get("energy_per_tick", 0)
        if ept:
            sign = "+" if ept > 0 else ""
            color = C_GOOD if ept > 0 else C_BAD
            lines.append([("Energy/Tick: ", C_LABEL), (f"{sign}{ept}", color)])
        brisk = defn.get("briskness", 0)
        if brisk:
            sign = "+" if brisk > 0 else ""
            color = C_GOOD if brisk > 0 else C_BAD
            lines.append([("Briskness: ", C_LABEL), (f"{sign}{brisk}", color)])

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
                # Strain-specific effect descriptions
                _strain_descs = {
                    "OG Kush": [
                        "Healing strain. Roll 1-100:",
                        "95+: Full heal. 66+: 50-100 HP.",
                        "20-39: 20 HP. 10-19: Nothing.",
                        "1-9: Lose 10% HP.",
                    ],
                    "Agent Orange": [
                        "Cleansing strain. Roll 1-100:",
                        "90+: Remove all debuffs + Zoned Out.",
                        "50+: Remove debuffs.",
                        "11-49: Random DoT debuff.",
                        "1-10: AO debuff (all DoTs at once).",
                    ],
                    "Columbian Gold": [
                        "Volatile strain. Roll 1-100:",
                        "99+: Invulnerable (10t).",
                        "91+: Power buff + self-dmg.",
                        "31-90: 10-20 flat self-dmg.",
                        "1-10: Lose 50% HP.",
                    ],
                    "Blue Lobster": [
                        "Chaotic strain. Roll 1-100:",
                        "Every tier does something random.",
                        "Effects vary wildly each smoke.",
                    ],
                    "Jungle Boyz": [
                        "Combat strain. Roll 1-100:",
                        "81+: Glory Fists (+5 STR, 5%/hit perm +1 stat).",
                        "61+: Lifesteal (8t).",
                        "41+: Crippling Attacks (10t).",
                        "21+: Fiery Fists (ignite, 10t).",
                        "1-20: Self Reflection (10t).",
                    ],
                    "Dosidos": [
                        "Arcane strain. Roll 1-100:",
                        "85+: Dimension Door charges.",
                        "72+: Chain Lightning charges.",
                        "50+: Ray of Frost charges.",
                        "1-49: Warp charges.",
                        "Thrown: +BKS buff on monsters.",
                    ],
                    "Iron Lung": [
                        "Tank strain (CON). Roll 1-100:",
                        "95+: Purge all tox, big heal,",
                        "  excess→temp HP, +tox/20 DEF.",
                        "61+: Remove 100 tox, heal,",
                        "  +1 DEF per 10 tox removed.",
                        "31+: Remove 50 tox, heal, +DEF.",
                        "1-30: +100 tox (bad hit).",
                    ],
                    "Skywalker OG": [
                        "Force strain (STR). Roll 1-100:",
                        "100: Green Lightsaber + Force",
                        "  Sensitive + 100 starting rad.",
                        "71+: Force Sensitive + 100 rad.",
                        "50+: Force Sensitive + 50 rad.",
                        "1-49: Lose 50 rad.",
                        "Force: +1 STR per 10 rad gained.",
                    ],
                    "Street Scholar": [
                        "Gun strain (STS). Roll 1-100:",
                        "75+: Calc Aim III (auto-reload,",
                        "  100% acc, +BKS on kill).",
                        "45+: Calc Aim II (auto-reload).",
                        "25+: Calc Aim I (+crit mult).",
                        "11-24: Jam guns. 1-10: Dump ammo.",
                    ],
                    "Kushenheimer": [
                        "Nuclear strain (BKS). Roll 1-100:",
                        "80+: Rad Nova charges, +12 spell",
                        "  dmg, +1 perm BKS.",
                        "60+: +10 spell dmg, +3 charges.",
                        "40+: +7 spell dmg, +2 charges.",
                        "1-39: +rad, minor or no buff.",
                    ],
                    "Nigle Fart": [
                        "Toxic strain (TOL). Roll 1-100:",
                        "80+: +30 tox, spillover aura,",
                        "  +4 Pandemic, perm TOL chance.",
                        "40+: +50 tox, aura, +3 Pandemic.",
                        "20+: +70 tox, +2 Pandemic.",
                        "1-19: +100 tox, +1 Pandemic.",
                    ],
                    "Purple Halt": [
                        "Mutation strain (SWG). Roll 1-100:",
                        "90+: Force mutation, NO rad cost.",
                        "55+: Force mutation, rad consumed.",
                        "20-54: -15 rad (whiff).",
                        "1-19: -40 rad, +1 SWG (15t).",
                    ],
                    "Snickelfritz": [
                        "Ditch weed. Don't smoke this.",
                    ],
                }
                # Find the strain from the item entity context
                strain_key = use_eff.get("strain")
                if not strain_key and engine:
                    # Try to get strain from the item being examined
                    try:
                        exam_item = engine.player.inventory[engine.selected_item_index]
                        strain_key = getattr(exam_item, "strain", None)
                    except (IndexError, AttributeError):
                        pass
                if strain_key and strain_key in _strain_descs:
                    for desc_line in _strain_descs[strain_key]:
                        lines.append([(desc_line, C_VALUE)])
                skill = defn.get("primary_skill")
                if skill:
                    lines.append([("Trains: ", C_LABEL), (skill, C_VALUE)])

            elif etype == "alcohol":
                drink_id = use_eff.get("drink_id", "")
                _drink_descs = {
                    "40oz": [
                        "Restores armor to full.",
                        "+5 Swagger for 50 turns.",
                        "+1 hangover stack.",
                    ],
                    "fireball_shooter": [
                        "Grants 3 Breath Fire charges.",
                        "Fireball Breath (100t): items",
                        "ignite nearest enemy on use.",
                        "+1 hangover stack.",
                    ],
                    "blue_lagoon": [
                        "Grants 3 Ice Nova charges.",
                        "Frozen Breath (100t): items",
                        "chill nearest enemy on use.",
                        "+1 hangover stack.",
                    ],
                    "natty_light": [
                        "6-pack. Crack one open.",
                        "+25 HP per beer.",
                        "+1 all stats (100t) per beer.",
                        "1/6 chance of +1 hangover per beer.",
                    ],
                    "jagermeister": [
                        "+2 STR for 15 turns.",
                        "Each melee hit: +2 more STR",
                        "for the rest of the buff.",
                        "+1 hangover stack.",
                    ],
                    "butterbeer": [
                        "+25% Briskness for 100 turns.",
                        "+1 hangover stack.",
                    ],
                    "absinthe": [
                        "Resets all visible monsters to passive.",
                        "3-turn grace period (enemies won't re-aggro).",
                        "+2 hangover stacks.",
                    ],
                    "malt_liquor": [
                        "+8 STR, -2 CON, +20 Temp HP",
                        "for 50 turns. Stacks.",
                        "+1 hangover stack.",
                    ],
                    "wizard_mind_bomb": [
                        "+2 charges to all active spells.",
                        "+5 Book Smarts for 50 turns.",
                        "Spell dmg + Book Smarts while active.",
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
                    "speedball": [
                        "+100 speed, +5 Swagger",
                        "for 50 turns.",
                        "20% chance to lose a turn.",
                        "+1 hangover stack.",
                    ],
                    "mana_drink": [
                        "100 turn buff. Abilities heal",
                        "15% of damage dealt. Stacks.",
                        "-1 tox or rad per heal trigger.",
                        "+1 hangover stack.",
                    ],
                    "virulent_vodka": [
                        "100 turn buff. Direct damage",
                        "applies max(dmg,10) tox. Stacks.",
                        "25% +1 CON on kill w/ 100+ tox.",
                        "+1 hangover stack.",
                    ],
                    "five_loco": [
                        "Lasts until floor change. Stacks.",
                        "2x radiation gain.",
                        "+25% good mutation chance.",
                        "+1 hangover stack.",
                    ],
                    "white_gonster": [
                        "50 turn buff. Stacks.",
                        "30%/turn: purge a random debuff.",
                        "Heal HP = debuff duration (max 50).",
                        "+5 Swagger. +1 hangover stack.",
                    ],
                    "platinum_reserve": [
                        "Heals 50% max HP. +5 perm armor.",
                        "100 turn buff: 3x max armor,",
                        "restored to full. Reverts on expire.",
                        "+1 hangover stack.",
                    ],
                    "dead_shot_daiquiri": [
                        "100 turn buff. Stacks.",
                        "+5 STS, +5 gun damage.",
                        "50%/bullet: ammo returned.",
                        "+1 hangover stack.",
                    ],
                    "alco_seltzer": [
                        "Remove 50 toxicity.",
                        "100% tox resist (rest of floor).",
                        "Debuff immunity for 50 turns.",
                        "+1 hangover stack.",
                    ],
                    "rainbow_rotgut": [
                        "50 turn buff. Melee hits apply",
                        "ignite, shocked, or chill (1/3 each).",
                        "+1 hangover stack.",
                    ],
                    "root_beer": [
                        "30 turn buff. Immobile.",
                        "-10 incoming damage (all sources).",
                        "+50 Temp HP (absorbs damage).",
                        "Breaks if spell shield is depleted.",
                        "+1 hangover stack.",
                    ],
                }
                desc_lines = _drink_descs.get(drink_id, ["Alcohol effect."])
                for dl in desc_lines:
                    lines.append([(dl, C_INFO)])

            elif etype == "soft_drink":
                drink_id = use_eff.get("drink_id", "")
                if drink_id == "purple_drank":
                    lines.append([("Replays last drink's effect.", C_INFO)])
                    lines.append([("Adds a copy of that drink", C_INFO)])
                    lines.append([("to your inventory.", C_INFO)])
                    lines.append([("Nonalcoholic. No hangover.", C_INFO)])
                elif drink_id == "blue_drank":
                    lines.append([("Doubles next drink's effect.", C_INFO)])
                    lines.append([("Suppresses all hangover stacks.", C_INFO)])
                    lines.append([("Stacks with itself (x4, x8...).", C_INFO)])
                elif drink_id == "red_drank":
                    lines.append([("200 turn buff. While active:", C_INFO)])
                    lines.append([("Drinks have doubled duration.", C_INFO)])
                    lines.append([("Drinks cost no action.", C_INFO)])
                    lines.append([("Drinks grant +100 energy.", C_INFO)])
                elif drink_id == "green_drank":
                    lines.append([("Lasts until floor change. Stacks.", C_INFO)])
                    lines.append([("Each drink: +20 HP, +20 armor,", C_INFO)])
                    lines.append([("-20 rad/tox, cleanse 1 debuff.", C_INFO)])
                    lines.append([("Prevents hangover from drinks.", C_GOOD)])
                elif drink_id in ("red_kool_aid", "blue_kool_aid", "purple_kool_aid",
                                  "green_kool_aid", "orange_kool_aid", "yellow_kool_aid"):
                    _kool_aid_desc = {
                        "red_kool_aid":    "Permanent +1 Strength.",
                        "blue_kool_aid":   "Permanent +1 Book-Smarts.",
                        "purple_kool_aid": "Permanent +1 Street-Smarts.",
                        "green_kool_aid":  "Permanent +1 Tolerance.",
                        "orange_kool_aid": "Permanent +1 Constitution.",
                        "yellow_kool_aid": "Permanent +1 Swagger.",
                    }
                    lines.append([(_kool_aid_desc[drink_id], C_GOOD)])
                    lines.append([("OH YEAH!", C_INFO)])
                elif drink_id == "sparkling_water":
                    lines.append([("Clears ALL toxicity and radiation.", C_GOOD)])
                    lines.append([("Nonalcoholic. No hangover.", C_INFO)])
                # Dranks have no skill tag — no "Trains:" line

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
                            lines.append([("+10 Firebolt charges.", C_GOOD)])
                            lines.append([("Ignites you when it expires.", C_BAD)])
                        elif ft == "grant_ability_charges":
                            aid = eff.get("ability_id", "?").replace("_", " ").title()
                            charges = eff.get("charges", 0)
                            lines.append([("Grants: ", C_LABEL), (f"{charges}x {aid}", C_GOOD)])
                        elif ft == "cornbread_buff":
                            dur = eff.get("duration", 0)
                            lines.append([("+5 Book Smarts for ", C_GOOD), (f"{dur} turns.", C_GOOD)])
                        elif ft == "leftovers_well_fed":
                            dur = eff.get("duration", 0)
                            lines.append([("+1 power, +1 spell dmg for ", C_GOOD), (f"{dur} turns.", C_GOOD)])
                        elif ft == "protein_powder":
                            lines.append([("Lasts until floor change.", C_GOOD)])
                            lines.append([("Permanent stat gains grant", C_GOOD)])
                            lines.append([("an extra random +1 stat.", C_GOOD)])
                        elif ft == "muffin_buff":
                            lines.append([("Lasts until floor change.", C_GOOD)])
                            lines.append([("50% chance to not consume", C_GOOD)])
                            lines.append([("a charge on ability use.", C_GOOD)])
                        elif ft == "phase_walk":
                            dur = eff.get("duration", 0)
                            lines.append([(f"Walk through walls for {dur} turns.", C_GOOD)])
                            lines.append([("Teleported to safety if inside", C_INFO)])
                            lines.append([("a wall when effect expires.", C_INFO)])
                        elif ft == "holy_wafer":
                            lines.append([("+5 Divine Shield stacks.", C_GOOD)])
                            lines.append([("Each absorbs one direct hit.", C_GOOD)])
                            lines.append([("Ranged: 50% miss w/o using stack.", C_INFO)])
                            lines.append([("Permanent until consumed.", C_GOOD)])
                        elif ft == "hard_boiled_egg":
                            lines.append([("Death save: revive at half HP.", C_GOOD)])
                            lines.append([("Lasts 100 turns. Stacks.", C_GOOD)])
                        elif ft == "eagle_eye":
                            lines.append([("Unlimited view distance.", C_GOOD)])
                            lines.append([("Lasts until floor change.", C_GOOD)])
                        elif ft == "yellowcake_buff":
                            lines.append([("Lasts until floor change.", C_GOOD)])
                            lines.append([("10x mutation chance.", C_GOOD)])
                            lines.append([("Weak mutations blocked.", C_GOOD)])
                            lines.append([("Only strong/huge mutations.", C_INFO)])
                        elif ft == "remove_toxicity":
                            amt = eff.get("amount", 0)
                            lines.append([("Removes: ", C_LABEL), (f"{amt} Toxicity", C_GOOD)])
                        elif ft == "toxicity":
                            amt = eff.get("amount", 0)
                            lines.append([("Adds: ", C_LABEL), (f"{amt} Toxicity", C_BAD)])
                        elif ft == "remove_radiation":
                            amt = eff.get("amount", 0)
                            lines.append([("Removes: ", C_LABEL), (f"{amt} Radiation", C_GOOD)])
                        elif ft == "radiation":
                            amt = eff.get("amount", 0)
                            lines.append([("Adds: ", C_LABEL), (f"{amt} Radiation", C_BAD)])

            elif etype == "meth":
                amt = use_eff.get("amount", 30)
                lines.append([(f"Restores Meth resource.", C_GOOD)])
                lines.append([(f"Amount scales with Tolerance.", C_INFO)])

            elif etype == "remove_toxicity":
                amt = use_eff.get("amount", 50)
                lines.append([(f"Removes {amt} Toxicity.", C_GOOD)])
                lines.append([("Instant use.", C_INFO)])

            elif etype == "add_toxicity":
                amt = use_eff.get("amount", 50)
                lines.append([(f"Adds {amt} Toxicity.", C_BAD)])
                lines.append([("Instant use.", C_INFO)])

            elif etype == "remove_radiation":
                amt = use_eff.get("amount", 50)
                lines.append([(f"Removes {amt} Radiation.", C_GOOD)])
                lines.append([("Instant use.", C_INFO)])

            elif etype == "add_radiation":
                amt = use_eff.get("amount", 50)
                lines.append([(f"Adds {amt} Radiation.", C_BAD)])
                lines.append([("Instant use.", C_INFO)])

            elif etype == "torch_burn":
                lines.append([("Burns an item when used on it.", C_INFO)])

        # Throw info
        if defn.get("throw_verb"):
            lines.append([("Can be thrown at enemies.", C_INFO)])

        # Skills trained — check new "skill" key first, then legacy "primary_skill"
        skill = defn.get("skill") or defn.get("primary_skill")
        if skill and (not use_eff or use_eff.get("type") not in ("strain_roll",)):
            if isinstance(skill, list):
                lines.append([("Trains: ", C_LABEL), ("Best of:", C_VALUE)])
                lines.append([("  " + ", ".join(skill), C_VALUE)])
            else:
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

        skill = defn.get("skill") or defn.get("primary_skill")
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

        # Tool-specific descriptions
        _tool_descs = {
            "pack_of_cones": [
                ("Rolling papers for joints.", C_INFO),
                ("Combine with a weed nug to roll", C_INFO),
                ("a joint. Each roll uses 1 charge.", C_INFO),
            ],
            "grinder": [
                ("Grinds weed nugs into kush.", C_INFO),
                ("Combine with a nug to grind it.", C_INFO),
            ],
            "fry_daddy": [
                ("Deep fryer for cooking food.", C_INFO),
                ("Combine with food to fry it.", C_INFO),
            ],
            "bic_torch": [
                ("A lighter. Combine items to", C_INFO),
                ("burn them together.", C_INFO),
            ],
            "xl_bic_torch": [
                ("A big lighter. Combine items to", C_INFO),
                ("burn them together.", C_INFO),
            ],
        }
        if item_id in _tool_descs:
            for text, color in _tool_descs[item_id]:
                lines.append([(text, color)])

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
                elif etype == "spray_paint":
                    spray_type = defn["use_effect"].get("spray_type", "")
                    _spray_descs = {
                        "red": [
                            ("Spray a tile red.", C_INFO),
                            ("Enemies on red tiles take", C_INFO),
                            ("+25% damage from all sources.", C_GOOD),
                        ],
                        "blue": [
                            ("Spray a tile blue.", C_INFO),
                            ("+5 Street-Smarts while", C_GOOD),
                            ("standing on it.", C_INFO),
                            ("25% chance to preserve", C_GOOD),
                            ("ability charges.", C_INFO),
                        ],
                        "green": [
                            ("Spray a tile green.", C_INFO),
                            ("+4 Defense while standing", C_GOOD),
                            ("on it.", C_INFO),
                        ],
                        "orange": [
                            ("Spray a tile orange.", C_INFO),
                            ("Entities on it take", C_INFO),
                            ("5 + 2x Graffiti Lvl damage", (255, 160, 40)),
                            ("per turn.", C_INFO),
                        ],
                        "silver": [
                            ("Spray a tile silver.", C_INFO),
                            ("Entities entering slip and", C_INFO),
                            ("must spend a turn standing.", (200, 200, 210)),
                            ("+50% melee damage taken", (255, 100, 100)),
                            ("while slipped.", C_INFO),
                        ],
                    }
                    for text, color in _spray_descs.get(spray_type, []):
                        lines.append([(text, color)])

        skill = defn.get("skill") or defn.get("primary_skill")
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

    kwargs = {
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

    # Guns start fully loaded
    if defn.get("subcategory") == "gun":
        mag_options = defn.get("mag_size_options")
        if mag_options:
            mag = _random.choice(mag_options)
        else:
            mag = defn.get("mag_size", 0)
        kwargs["mag_size"] = mag
        kwargs["current_ammo"] = mag

    # Staves start with staff_charges
    if defn.get("staff_charges"):
        kwargs["charges"] = defn["staff_charges"]
        kwargs["max_charges"] = 99

    # Tools with limited charges (e.g. Pack of Cones)
    if defn.get("tool_charges"):
        max_ch = defn["tool_charges"]
        min_ch = defn.get("tool_charges_min", max_ch)
        kwargs["charges"] = _random.randint(min_ch, max_ch)
        kwargs["max_charges"] = max_ch

    # Items that spawn with a specific quantity (e.g. Natty Light 6-pack)
    if defn.get("spawn_quantity"):
        kwargs["quantity"] = defn["spawn_quantity"]

    return kwargs
