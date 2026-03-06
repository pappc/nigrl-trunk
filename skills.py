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
    "Munching",
    "Dismantling",
    "Abandoning",
    "Crack-Head",
]

DEFAULT_EXP_CURVE = [200, 400, 600, 800, 2000, 6000, 15000, 25000, 100000, 500000]
MAX_LEVEL = 10

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
