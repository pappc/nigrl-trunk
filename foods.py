"""
Food item definitions and helper functions.

Foods are consumables that require the player to sit and eat before effects apply.
All foods follow a declarative structure with flexible effect support.
"""

# ---------------------------------------------------------------------------
# Food definitions
# ---------------------------------------------------------------------------
#
# Each food item:
#   eat_length      : turns to spend eating
#   eating_effect_name : display name during eating (e.g. "Eating Chicken")
#   well_fed_effect_name : default effect name when eating completes (can be overridden per-effect)
#   effects         : list of effect dicts that apply when eating finishes
#                     each effect dict has "type" and type-specific fields
#   char            : single character for display
#   color           : (r, g, b) tuple
#   zones           : list of zone names where this food spawns
#   weight          : spawn weight relative to other items in loot tables
#
# Effect types:
#   "heal"          : immediate healing on eating completion
#       amount      : [min, max] tuple or single value
#
#   "hot"           : heal-over-time effect after eating
#       stat_formula: "constitution / 5" (uses Fractional arithmetic, rounded up on apply)
#       duration    : number of turns
#
#   "speed_boost"   : temporary speed buff (adds energy per tick)
#       amount      : energy gained per tick
#       duration    : number of turns
#
#   "hot_cheetos"   : fiery buff (grants +2 all stats, 50% melee ignite, ignites on expire)
#       duration    : number of turns
#
#   "radiation"     : adds radiation to the player (goes through rad resistance)
#       amount      : radiation to add
#
#   "remove_radiation" : removes radiation from the player
#       amount      : radiation to remove
#
#   "toxicity"      : adds toxicity to the player (goes through tox resistance)
#       amount      : toxicity to add
#
#   "remove_toxicity" : removes toxicity from the player
#       amount      : toxicity to remove
# ---------------------------------------------------------------------------

FOOD_DEFS = {
    "chicken": {
        "name": "Chicken",
        "eat_length": 10,
        "eating_effect_name": "Eating Chicken",
        "well_fed_effect_name": "Well Fed",
        "char": "f",
        "color": (200, 180, 140),
        "zones": ["crack_den"],

        "effects": [
            {
                "type": "heal",
                "amount": 50,
            },
            {
                "type": "hot",
                "stat_formula": "constitution / 5",  # rounded up on apply
                "duration": 30,
            },
        ],
    },
    "instant_ramen": {
        "name": "Instant Ramen",
        "eat_length": 4,
        "eating_effect_name": "Eating Instant Ramen",
        "well_fed_effect_name": "Hyped Up",
        "char": "f",
        "color": (255, 200, 100),
        "zones": ["crack_den", "meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {
                "type": "speed_boost",
                "amount": 50,
                "duration": 20,
            },
        ],
    },
    "hot_cheetos": {
        "name": "Hot Cheetos",
        "eat_length": 5,
        "eating_effect_name": "Eating Hot Cheetos",
        "well_fed_effect_name": "Spicy Vibes",
        "char": "f",
        "color": (255, 140, 40),
        "zones": ["crack_den", "meth_lab"],

        "effects": [
            {"type": "heal", "amount": 50},
            {
                "type": "hot_cheetos",
                "duration": 30,
            },
        ],
    },
    "cornbread": {
        "name": "Cornbread",
        "eat_length": 5,
        "eating_effect_name": "Eating Cornbread",
        "well_fed_effect_name": "Cornbread High",
        "char": "f",
        "color": (220, 180, 80),
        "zones": ["crack_den", "meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "cornbread_buff", "duration": 30},
            {"type": "grant_ability_charges", "ability_id": "zap", "charges": 10},
        ],
    },
    "corn_dog": {
        "name": "Corn Dog",
        "eat_length": 3,
        "eating_effect_name": "Eating Corn Dog",
        "well_fed_effect_name": "Corn Dogged Up",
        "char": "f",
        "color": (220, 160, 60),
        "zones": ["crack_den", "meth_lab"],

        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "grant_ability_charges", "ability_id": "corn_dog", "charges": 3},
        ],
    },
    "leftovers": {
        "name": "Leftovers",
        "eat_length": 3,
        "eating_effect_name": "Eating Leftovers",
        "well_fed_effect_name": "Well Fed",
        "char": "f",
        "color": (180, 140, 100),
        "zones": [],

        "effects": [
            {"type": "heal", "amount": 10},
            {"type": "leftovers_well_fed", "duration": 10},
        ],
    },
    "jell_o": {
        "name": "Jell-O",
        "eat_length": 10,
        "eating_effect_name": "Eating Jell-O",
        "well_fed_effect_name": "Jiggly",
        "char": "f",
        "color": (255, 100, 120),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "heal", "amount": 58},
            {"type": "grant_ability_charges", "ability_id": "mirror_entity", "charges": [1, 3]},
        ],
    },
    "meatball_sub": {
        "name": "Meatball Sub",
        "eat_length": 10,
        "eating_effect_name": "Eating Meatball Sub",
        "well_fed_effect_name": "Meat Sweats",
        "char": "f",
        "color": (180, 80, 40),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "grant_ability_charges", "ability_id": "fire_meatball", "charges": [2, 5]},
        ],
    },
    "heinz_baked_beans": {
        "name": "Heinz Baked Beans",
        "eat_length": 10,
        "eating_effect_name": "Eating Heinz Baked Beans",
        "well_fed_effect_name": "Gassed Up",
        "char": "f",
        "color": (180, 100, 50),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "grant_ability_charges", "ability_id": "gas_attack", "charges": [2, 5]},
        ],
    },
    "altoid": {
        "name": "Altoid",
        "eat_length": 3,
        "eating_effect_name": "Eating Altoid",
        "well_fed_effect_name": "Minty Fresh",
        "char": "f",
        "color": (200, 240, 240),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "remove_toxicity", "amount": 20},
        ],
    },
    "asbestos": {
        "name": "Asbestos",
        "eat_length": 3,
        "eating_effect_name": "Eating Asbestos",
        "well_fed_effect_name": "Toxic",
        "char": "f",
        "color": (180, 180, 160),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "toxicity", "amount": 20},
        ],
    },
    "rad_away": {
        "name": "Rad Away",
        "eat_length": 3,
        "eating_effect_name": "Drinking Rad Away",
        "well_fed_effect_name": "Cleansed",
        "char": "f",
        "color": (100, 200, 255),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "remove_radiation", "amount": 20},
        ],
    },
    "radbar": {
        "name": "RadBar",
        "eat_length": 3,
        "eating_effect_name": "Eating RadBar",
        "well_fed_effect_name": "Irradiated",
        "char": "f",
        "color": (100, 220, 50),
        "zones": ["meth_lab"],


        "effects": [
            {"type": "radiation", "amount": 20},
        ],
    },
    "lightskin_beans": {
        "name": "Lightskin Beans",
        "eat_length": 10,
        "eating_effect_name": "Eating Lightskin Beans",
        "well_fed_effect_name": "Gassed Up",
        "char": "f",
        "color": (160, 200, 120),
        "zones": ["crack_den", "meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "grant_ability_charges", "ability_id": "lesser_cloudkill", "charges": 5},
        ],
    },
    "muffin": {
        "name": "Muffin",
        "eat_length": 10,
        "eating_effect_name": "Eating Muffin",
        "well_fed_effect_name": "Muffin Magic",
        "char": "f",
        "color": (255, 220, 130),
        "zones": ["crack_den", "meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "muffin_buff"},
        ],
    },
    "protein_powder": {
        "name": "Protein Powder",
        "eat_length": 10,
        "eating_effect_name": "Chugging Protein Powder",
        "well_fed_effect_name": "Swole",
        "char": "f",
        "color": (220, 180, 255),
        "zones": ["crack_den", "meth_lab"],


        "effects": [
            {"type": "heal", "amount": 50},
            {"type": "protein_powder"},
        ],
    },
}


FOOD_PREFIX_DEFS = {
    "greasy":     {"charges": 2, "display_adjective": "Greasy",    "effects": ["greasy_buff"]},
    "spicy":      {"charges": 2, "display_adjective": "Spicy",     "effects": []},
    "fried":      {"charges": 2, "display_adjective": "Fried",     "effects": []},
    "deep_fried": {"charges": 2, "display_adjective": "Deep-Fried","effects": []},
}


def get_food_prefix_def(prefix_name: str) -> dict | None:
    return FOOD_PREFIX_DEFS.get(prefix_name)


def get_food_def(food_id: str) -> dict | None:
    """Get the definition dict for a food by ID."""
    return FOOD_DEFS.get(food_id)


def validate_food_registry():
    """Validate all food definitions for required fields and consistency."""
    for food_id, defn in FOOD_DEFS.items():
        assert isinstance(defn, dict), f"Food {food_id} definition must be a dict"
        assert "name" in defn, f"Food {food_id} missing 'name'"
        assert "eat_length" in defn, f"Food {food_id} missing 'eat_length'"
        assert "effects" in defn, f"Food {food_id} missing 'effects'"
        assert isinstance(defn["effects"], list), f"Food {food_id} effects must be a list"
        assert len(defn["effects"]) > 0, f"Food {food_id} must have at least one effect"
        assert "char" in defn, f"Food {food_id} missing 'char'"
        assert "color" in defn, f"Food {food_id} missing 'color'"

        for i, effect in enumerate(defn["effects"]):
            effect_type = effect.get("type")
            assert effect_type, f"Food {food_id} effect {i} missing 'type'"

            if effect_type == "heal":
                assert "amount" in effect, f"Food {food_id} heal effect missing 'amount'"
            elif effect_type == "hot":
                assert "stat_formula" in effect, f"Food {food_id} hot effect missing 'stat_formula'"
                assert "duration" in effect, f"Food {food_id} hot effect missing 'duration'"
            elif effect_type == "speed_boost":
                assert "amount" in effect, f"Food {food_id} speed_boost effect missing 'amount'"
                assert "duration" in effect, f"Food {food_id} speed_boost effect missing 'duration'"
            elif effect_type == "hot_cheetos":
                assert "duration" in effect, f"Food {food_id} hot_cheetos effect missing 'duration'"
            elif effect_type == "radiation":
                assert "amount" in effect, f"Food {food_id} radiation effect missing 'amount'"
            elif effect_type == "remove_radiation":
                assert "amount" in effect, f"Food {food_id} remove_radiation effect missing 'amount'"
            elif effect_type == "toxicity":
                assert "amount" in effect, f"Food {food_id} toxicity effect missing 'amount'"
            elif effect_type == "remove_toxicity":
                assert "amount" in effect, f"Food {food_id} remove_toxicity effect missing 'amount'"
            elif effect_type in ("grant_ability_charges", "cornbread_buff", "leftovers_well_fed", "protein_powder", "muffin_buff"):
                pass  # No extra required fields beyond "type"
