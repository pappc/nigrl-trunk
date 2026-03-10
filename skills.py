"""
Skill definitions and progression system.

Levels: 0 - 10
XP thresholds per level (DEFAULT_EXP_CURVE):
  0 ->  1:    200
  1 ->  2:    400
  2 ->  3:    600
  3 ->  4:    800
  4 ->  5:  2,000
  5 ->  6:  6,000
  6 ->  7: 15,000
  7 ->  8: 25,000
  8 ->  9: 100,000
  9 -> 10: 500,000
  Total to max: 649,000

Potential exp is earned passively by doing actions.
Real exp is earned by spending skill_points to convert potential -> real.
Skill_points are gained as a fraction of potential_exp (scaled by book_smarts).
"""

SKILL_NAMES = [
    "Smoking",
    "Rolling",
    "Pyromania",
    "Negromancy",
    "Blackkk Magic",
    "Stabbing",
    "Beating",
    "Smacking",
    "Stealing",
    "Jaywalking",
    "Deep-Frying",
    "Drinking",
    "Alcoholism",
    "Munching",
    "Dismantling",
    "Abandoning",
    "Meth-Head",
]

DEFAULT_EXP_CURVE = [200, 400, 600, 800, 2000, 6000, 15000, 25000, 100000, 500000]
MAX_LEVEL = 10

# Placeholder perk data for all 17 skills × 10 levels.
# Each entry: {"name": str, "perk_type": str, "effect": dict | None}
# perk_type: "none" (placeholder), "stat", "passive", "activated"
_PLACEHOLDER = {"name": "Placeholder", "perk_type": "none", "effect": None}

SKILL_PERKS: dict[str, list[dict]] = {
    skill_name: [_PLACEHOLDER] * 10
    for skill_name in [
        "Smoking", "Rolling", "Pyromania", "Negromancy", "Blackkk Magic",
        "Stabbing", "Beating", "Smacking", "Stealing", "Jaywalking",
        "Deep-Frying", "Drinking", "Alcoholism", "Munching", "Dismantling",
        "Abandoning", "Meth-Head",
    ]
}

SKILL_PERKS["Deep-Frying"] = [
    {"name": "Fry Shot",     "perk_type": "activated", "effect": {"ability": "fry_shot"},    "desc": "Hurl a ball of scorching hot oil that deals burn damage in a small area."},   # level 1
    {"name": "Extra Greasy", "perk_type": "passive",   "effect": None,                       "desc": "Your fried food items restore +20% HP when eaten."},                         # level 2
    {"name": "Double Batch", "perk_type": "passive",   "effect": None,                       "desc": "20% chance a food item is not consumed when you eat it."},                   # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                # levels 4-10
]

SKILL_PERKS["Dismantling"] = [
    {"name": "+2 BKS, +2 CON",    "perk_type": "stat",    "effect": {"book_smarts": 2, "constitution": 2}, "desc": "+2 Book Smarts, +2 Constitution. You learn from taking things apart."},  # level 1
    {"name": "Chop Shop",   "perk_type": "passive", "effect": None,                                  "desc": "Destroying an item grants +5 armor and +$20 cash from salvaged parts."},   # level 2
    {"name": "Nigga Armor", "perk_type": "passive", "effect": None,                                  "desc": "Gain a stack of Nigga Armor whenever you destroy an item."},               # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 4-10
]

SKILL_PERKS["Abandoning"] = [
    {"name": "+1 All Stats", "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 to all stats. Leaving things behind builds character."},  # level 1
    {"name": "+1 All Stats", "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 to all stats. And it keeps building."},                   # level 2
    {"name": "Anotha Motha", "perk_type": "passive", "effect": None, "desc": "Receive 5 extra item drops when descending to the next floor."},                                                                                         # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                          # levels 4-10
]

SKILL_PERKS["Smoking"] = [
    {"name": "Phat Cloud",  "perk_type": "passive", "effect": None,                                    "desc": "Smoking produces a cloud of smoke that obscures enemy vision in the area."},  # level 1
    {"name": "+2 TOL, +2 CON",    "perk_type": "stat",    "effect": {"tolerance": 2, "constitution": 2},     "desc": "+2 Tolerance, +2 Constitution. Your body adapts to the abuse."},              # level 2
    {"name": "+2 TOL", "perk_type": "stat",    "effect": {"tolerance": 2},                        "desc": "+2 Tolerance. You smoke the roach. Every last bit."},                         # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 4-10
]

SKILL_PERKS["Pyromania"] = [
    {"name": "Fire!",         "perk_type": "activated", "effect": {"ability": "place_fire"},   "desc": "Place a fire tile on an adjacent square. Enemies that step on it take burn damage."},  # level 1
    {"name": "+3 CON",      "perk_type": "stat",      "effect": {"constitution": 3},          "desc": "+3 Constitution. Fire hardens the soul."},                                              # level 2
    {"name": "Ignite",        "perk_type": "activated", "effect": {"ability": "ignite_spell"}, "desc": "Targeted ignite spell — set a visible enemy ablaze from a distance."},                  # level 3
    {"name": "Neva Burn Out", "perk_type": "passive",   "effect": None,                        "desc": "You are completely immune to fire and burning damage."},                                 # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,        # levels 5-10
]

SKILL_PERKS["Rolling"] = [
    {"name": "+1 STR, +1 TOL",       "perk_type": "stat",    "effect": {"strength": 1, "tolerance": 1}, "desc": "+1 Strength, +1 Tolerance. Rolling builds hands and resistance."},  # level 1
    {"name": "Seeing Double",  "perk_type": "passive", "effect": None,                             "desc": "Chance to roll an extra blunt when you roll one up."},               # level 2
    {"name": "Spectral Paper", "perk_type": "passive", "effect": None,                             "desc": "20% chance rolling a blunt doesn't consume your papers."},           # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                      # levels 4-10
]

SKILL_PERKS["Alcoholism"] = [
    {"name": "Im Drinkin Here", "perk_type": "passive",   "effect": None,                           "desc": "Taking damage while drunk has a chance to not interrupt your drinking."},       # level 1
    {"name": "+2 TOL",        "perk_type": "stat",      "effect": {"tolerance": 2},               "desc": "+2 Tolerance. Your liver is basically pickled at this point."},                 # level 2
    {"name": "Throw Bottle",    "perk_type": "activated", "effect": {"ability": "throw_bottle"},    "desc": "Hurl a bottle at an enemy for damage with a chance to stun them."},            # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                       # levels 4-10
]

SKILL_PERKS["Drinking"] = [
    {"name": "Liquid Bandage",  "perk_type": "passive",   "effect": None,                             "desc": "Any drink heals +10% of your max HP on use, in addition to normal effects."},      # level 1
    {"name": "One More Sip",    "perk_type": "passive",   "effect": None,                             "desc": "20% chance a drink item is not consumed when used."},                              # level 2
    {"name": "Slow Metabolism", "perk_type": "activated", "effect": {"ability": "slow_metabolism"},   "desc": "Double the duration of all currently active drink buffs. 2 uses per floor."},      # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 4-10
]

SKILL_PERKS["Beating"] = [
    {"name": "+3 STR",  "perk_type": "stat",      "effect": {"strength": 3},         "desc": "+3 Strength. Beating people up makes you stronger. Simple as that."},    # level 1
    {"name": "Bash",      "perk_type": "activated",  "effect": {"ability": "bash"},    "desc": "Bash an adjacent enemy with full force, stunning them for 1 turn."},       # level 2
    {"name": "Crit+",     "perk_type": "passive",    "effect": None,                   "desc": "Increases your critical hit chance on all melee attacks."},                # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                          # levels 4-10
]

SKILL_PERKS["Stabbing"] = [
    {"name": "Gouge",     "perk_type": "activated", "effect": {"ability": "gouge"},        "desc": "Gouge a single target, dealing bonus damage and applying a bleed effect."},   # level 1
    {"name": "+2 STS",  "perk_type": "stat",      "effect": {"street_smarts": 2},        "desc": "+2 Street Smarts. You learn to read people by poking holes in them."},        # level 2
    {"name": "Windfury",  "perk_type": "passive",   "effect": None,                        "desc": "Chance to attack a second time immediately after each stab."},                # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                              # levels 4-10
]

SKILL_PERKS["Blackkk Magic"] = [
    {"name": "+2 BKS",            "perk_type": "stat",      "effect": {"book_smarts": 2},           "desc": "+2 Book Smarts. Forbidden knowledge has its perks."},                    # level 1
    {"name": "Force Be With You",   "perk_type": "activated", "effect": {"ability": "force_push"},    "desc": "Force push an enemy backwards several tiles. Works through walls?"},      # level 2
    {"name": "Arcane Intelligence", "perk_type": "passive",   "effect": None,                         "desc": "All spells and abilities cost significantly less energy to use."},        # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 4-10
]

SKILL_PERKS["Smacking"] = [
    {"name": "Bitch Slap",  "perk_type": "activated", "effect": {"ability": "black_eye_slap"},         "desc": "Slap an adjacent enemy. Dmg: STR (vs females: 10 + 2×STR). 25-turn cooldown."},  # level 1
    {"name": "+3 STR, +3 CON",    "perk_type": "stat",       "effect": {"strength": 3, "constitution": 3},   "desc": "+3 Strength, +3 Constitution. Slapping builds muscle."},                                        # level 2
    {"name": "Black Eye",   "perk_type": "passive",    "effect": None,                                  "desc": "Unarmed attacks have a 10% chance to cause Black Eye: stun 2 turns, then 10 turns of dazed wandering."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                           # levels 4-10
]

SKILL_PERKS["Munching"] = [
    {"name": "Fast Food",    "perk_type": "activated", "effect": {"constitution": 2, "ability": "quick_eat"}, "desc": "+2 Constitution. Grants Quick Eat ability: instantly eat your next food."},  # level 1
    {"name": "+2 CON",  "perk_type": "stat",    "effect": {"constitution": 2}, "desc": "+2 Constitution. You're a unit. No cap."},                     # level 2
    {"name": "Better Later", "perk_type": "passive", "effect": None,               "desc": "Food effects last 50% longer before wearing off."},            # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                      # levels 4-10
]

SKILL_PERKS["Jaywalking"] = [
    {"name": "Air Jordans",   "perk_type": "passive",   "effect": None,                    "desc": "Movement costs -5 energy. You move like you own these streets."},     # level 1
    {"name": "Dash",          "perk_type": "activated", "effect": {"ability": "dash"},     "desc": "Dash in a direction, instantly moving 3 tiles. Great for escaping."},  # level 2
    {"name": "Airer Jordans", "perk_type": "passive",   "effect": None,                    "desc": "+10 Speed. Even fresher kicks. Even faster feet."},                    # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                               # levels 4-10
]

SKILL_PERKS["Stealing"] = [
    {"name": "+3 STS",  "perk_type": "stat",      "effect": {"street_smarts": 3},         "desc": "+3 Street Smarts. You learn real quick who to trust and who to rob."},              # level 1
    {"name": "Pickpocket",      "perk_type": "activated", "effect": {"ability": "pickpocket"},    "desc": "Attempt to pickpocket an adjacent enemy, stealing cash or an item from them."},    # level 2
    {"name": "Sticky Fingers",  "perk_type": "passive",   "effect": None,                         "desc": "Chance to gain +1 Street Smarts on the first item pickup each floor."},            # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                      # levels 4-10
]


def get_perk(skill_name: str, level: int) -> dict | None:
    """Return perk dict for skill at given level (1-10), or None if invalid."""
    perks = SKILL_PERKS.get(skill_name)
    if not perks or level < 1 or level > 10:
        return None
    return perks[level - 1]

def bksmt_mod(bksmt: int) -> float:
    """Sqrt-based skill_point gain rate from book_smarts.

    Calibrated so bksmt=0 -> 0.1, bksmt=8 -> ~0.19, caps at 0.5.
    Approximate targets: bksmt=8 ~0.19, bksmt=12 ~0.22, bksmt=50 ~0.34.
    """
    import math
    return min(0.5, 0.1 + 0.3 * math.sqrt(bksmt / 80.0))


class Skill:
    """A single skill with a level (0-10) and dual exp tracking."""

    def __init__(self, name: str, skill_mod: float = 1.0):
        self.name = name
        self.level = 0
        self.real_exp: float = 0.0      # counts toward level-ups
        self.potential_exp: float = 0.0  # earned passively; converted via spending
        self.skill_mod = skill_mod

    def xp_needed(self, exp_curve=None) -> int:
        """XP required to reach the next level. Returns 0 at max level."""
        if self.level >= MAX_LEVEL:
            return 0
        curve = exp_curve if exp_curve is not None else DEFAULT_EXP_CURVE
        return curve[self.level]

    def add_real_exp(self, amount: float) -> int:
        """Add to real_exp and level up if threshold crossed. Returns levels gained."""
        if self.level >= MAX_LEVEL:
            return 0

        self.real_exp += amount
        gained = 0

        while self.level < MAX_LEVEL and self.real_exp >= DEFAULT_EXP_CURVE[self.level]:
            self.real_exp -= DEFAULT_EXP_CURVE[self.level]
            self.level += 1
            gained += 1

        return gained

    def add_potential_exp(self, amount: float) -> None:
        """Add to potential_exp (uncapped)."""
        self.potential_exp += amount

    def is_maxed(self) -> bool:
        return self.level >= MAX_LEVEL


class Skills:
    """Container for all player skills."""

    def __init__(self):
        self.skills = {name: Skill(name) for name in SKILL_NAMES}
        self.skill_points: float = 0.0

    def get(self, name: str) -> Skill:
        """Get a skill by name."""
        return self.skills[name]

    def all(self):
        """Return all skills in definition order."""
        return [self.skills[name] for name in SKILL_NAMES]

    def unlocked(self):
        """Return only unlocked skills (those with level > 0, real_exp > 0, or potential_exp > 0)."""
        return [skill for skill in self.all() if skill.level > 0 or skill.real_exp > 0 or skill.potential_exp > 0]

    def gain_potential_exp(self, skill_name: str, amount: float, bksmt: int,
                           skill_mod_override: float = None) -> None:
        """Award potential_exp to a skill and add scaled skill_points.

        skill_points gained = amount * bksmt_mod(bksmt) * skill.skill_mod
        """
        skill = self.skills[skill_name]
        smod = skill_mod_override if skill_mod_override is not None else skill.skill_mod
        sp_gained = amount * bksmt_mod(bksmt) * smod
        skill.add_potential_exp(amount)
        self.skill_points += sp_gained

    def spend_on_skill(self, skill_name: str, amount: int) -> int:
        """Convert potential_exp to real_exp for a skill by spending skill_points.

        Spends min(amount, potential_exp, skill_points) and returns levels gained.
        """
        skill = self.skills[skill_name]
        if skill.is_maxed():
            return 0
        spendable = min(amount, int(skill.potential_exp), int(self.skill_points))
        if spendable <= 0:
            return 0
        skill.potential_exp -= spendable
        self.skill_points -= spendable
        return skill.add_real_exp(spendable)

    def add_xp(self, name: str, amount: float) -> int:
        """Legacy: add directly to real_exp (used for backward compat). Returns levels gained."""
        return self.skills[name].add_real_exp(amount)
