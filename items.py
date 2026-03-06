"""
Item definitions, crafting recipes, and helper functions.

All item metadata lives here to keep Entity lean.
Entity objects link to definitions via their `item_id` field.
"""

import math as _math

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
                "tags": ["minor"],
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
                "tags": ["greater"],
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
                "tags": ["divine"],
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
                "tags": ["advanced"],
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
                chains[item_id] = {
                    "name":          _chain_display_name(material, brand, style),
                    "char":          '"',
                    "color":         mat_data["color"],
                    "category":      "equipment",
                    "subcategory":   "neck",
                    "equip_slot":    "neck",
                    "power_bonus":   0,
                    "defense_bonus": 0,
                    "armor_bonus":   _chain_armor(material, brand, style),
                    "stat_bonus":    {},
                    "tags":          ["chain"],
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
                "stat_bonus":    {stat_attr: 1},
                "tags":          ["jordans"],
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
        "str_scaling": {"type": "tiered", "divisor": 2},  # +1 dmg per 2 STR above str_req
        "use_verb": None,              # action label shown in menu (None = no direct use)
        "use_effect": None,            # effect dict applied on use (None = no effect)
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
        "use_verb": None,
        "use_effect": None,
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
        "use_verb": "Smoke",
        "use_effect": {"type": "strain_roll"},
        "throw_verb": "Throw",
        "throw_effect": {"type": "strain_roll"},
    },
}


# ---------------------------------------------------------------------------
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

RECIPES = {
    ("weed_nug", "grinder"): {
        "result": "kush",
        "consumed": ["weed_nug"],           # grinder is a reusable tool
    },
    ("kush", "rolling_paper"): {
        "result": "joint",
        "consumed": ["kush", "rolling_paper"],
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


def build_inventory_display_name(item_id, strain, quantity):
    """Build the inventory panel display name for an item, respecting gram-based naming.

    weed_nug: "1g nug OG Kush" / "3g nugs OG Kush"
    kush:     "1g OG Kush"     / "3g OG Kush"
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
    elif item_a.item_id == "kush" and item_b.item_id == "rolling_paper":
        return item_a.strain
    elif item_a.item_id == "rolling_paper" and item_b.item_id == "kush":
        return item_b.strain

    return None


def can_combine(item_id):
    """Return True if item_id appears as an ingredient in any recipe."""
    for a, b in RECIPES:
        if item_id == a or item_id == b:
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

    actions.append("Drop")
    actions.append("Destroy")
    return actions


def get_combine_targets(item_id, inventory_item_ids):
    """Given a source item_id and a list of other inventory item_ids,
    return the indices of items that form a valid recipe with item_id."""
    targets = []
    for i, other_id in enumerate(inventory_item_ids):
        if find_recipe(item_id, other_id):
            targets.append(i)
    return targets


def find_env_interaction(item_id, env_feature):
    """Look up an environment interaction by item_id and feature name.
    Returns interaction dict or None."""
    return ENV_INTERACTIONS.get((item_id, env_feature))


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
