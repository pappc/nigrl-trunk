"""
Skill definitions and progression system.

Levels: 0 - 5
XP thresholds per level:
  0 -> 1 :   25 xp
  1 -> 2 :  100 xp
  2 -> 3 :  200 xp
  3 -> 4 :  400 xp
  4 -> 5 :  800 xp
  Total to max: 1525 xp
"""

SKILL_NAMES = [
    "Smoking",
    "Rolling",
    "Grinding",
    "Pyromania",
    "Stabbing",
    "Beating",
    "Stealing",
    "Mugging",
    "Gangbanging",
    "Rizz",
    "Jaywalking",
    "Deep-Frying",
    "Drinking",
    "Munching",
]

# XP required to advance from each level to the next
XP_TO_NEXT = [25, 100, 200, 400, 800]
MAX_LEVEL = 5


class Skill:
    """A single skill with a level (0-5) and XP tracking."""

    def __init__(self, name):
        self.name = name
        self.level = 0
        self.xp = 0  # XP accumulated within the current level

    def xp_needed(self):
        """XP required to reach the next level. Returns 0 at max level."""
        if self.level >= MAX_LEVEL:
            return 0
        return XP_TO_NEXT[self.level]

    def add_xp(self, amount):
        """Add XP and level up if the threshold is crossed.
        Returns the number of levels gained."""
        if self.level >= MAX_LEVEL:
            return 0

        self.xp += amount
        gained = 0

        while self.level < MAX_LEVEL and self.xp >= XP_TO_NEXT[self.level]:
            self.xp -= XP_TO_NEXT[self.level]
            self.level += 1
            gained += 1

        return gained

    def is_maxed(self):
        return self.level >= MAX_LEVEL


class Skills:
    """Container for all player skills."""

    def __init__(self):
        self.skills = {name: Skill(name) for name in SKILL_NAMES}

    def get(self, name):
        """Get a skill by name."""
        return self.skills[name]

    def all(self):
        """Return all skills in definition order."""
        return [self.skills[name] for name in SKILL_NAMES]

    def add_xp(self, name, amount):
        """Add XP to a named skill. Returns levels gained."""
        return self.skills[name].add_xp(amount)
