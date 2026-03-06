"""
Stat systems for player and enemies.
"""

import random

_STAT_MIN = 5
_STAT_MAX = 12
_TOTAL_POINTS = 46   # 6 stats, sum = 46, each clamped to [5, 12]
_NUM_STATS = 6


class PlayerStats:
    """
    Randomly distributed RPG stats for the player character.

    40 points distributed across 5 stats, each clamped to [5, 10].

    Constitution  — determines max HP (base 30 + CON × 10)
    Strength      — weapon damage bonus; scaling varies per weapon
    Book-Smarts   — skill XP multiplier (1.0x – 1.7x)
    Street-Smarts — critical strike chance (SS × 3%, range 15%-36%)
    Tolerance     — drug effect multiplier; lower = stronger (1.0x – 1.7x)
    Swagger       — melee defence bonus; +1 defence per 2 points above 5 (SWG 5=0, 7=+1, 9=+2);
                    scales negatively below 5 (SWG 3=-1, 1=-2)
    """

    def __init__(self):
        self._roll()

    def _roll(self):
        """Distribute 40 points across 5 stats, each between 5 and 10."""
        values = [_STAT_MIN] * _NUM_STATS
        remaining = _TOTAL_POINTS - _STAT_MIN * _NUM_STATS  # 15 extra points
        while remaining > 0:
            candidates = [i for i in range(_NUM_STATS) if values[i] < _STAT_MAX]
            if not candidates:
                break
            values[random.choice(candidates)] += 1
            remaining -= 1
        (
            self.constitution,
            self.strength,
            self.book_smarts,
            self.street_smarts,
            self.tolerance,
            self.swagger,
        ) = values
        # Store originals for buff/debuff visual comparison
        self._base = {
            "constitution": self.constitution,
            "strength":     self.strength,
            "book_smarts":  self.book_smarts,
            "street_smarts": self.street_smarts,
            "tolerance":    self.tolerance,
            "swagger":      self.swagger,
        }
        # Additive bonuses from equipped rings; updated by the engine on equip/unequip
        self.ring_bonuses: dict[str, int] = {
            "constitution":  0,
            "strength":      0,
            "book_smarts":   0,
            "street_smarts": 0,
            "tolerance":     0,
            "swagger":       0,
        }
        # Temporary bonuses from status effects; not persistent across saves
        self.temporary_stat_bonuses: dict[str, int] = {
            "constitution":  0,
            "strength":      0,
            "book_smarts":   0,
            "street_smarts": 0,
            "tolerance":     0,
            "swagger":       0,
        }
        # Temporary armor bonus from effects
        self.temporary_armor_bonus: int = 0

    # --- Ring bonus application ---

    def set_ring_bonuses(self, bonuses: dict[str, int]):
        """Replace the current ring_bonuses with the given dict.
        Call this whenever rings are equipped or unequipped."""
        for key in self.ring_bonuses:
            self.ring_bonuses[key] = bonuses.get(key, 0)

    def _rb(self, stat: str) -> int:
        """Shorthand: ring bonus for a named stat."""
        return self.ring_bonuses.get(stat, 0)

    def set_temporary_stat_bonus(self, stat: str, amount: int):
        """Set temporary stat bonus for a given stat (e.g., from status effects)."""
        if stat in self.temporary_stat_bonuses:
            self.temporary_stat_bonuses[stat] = amount

    def add_temporary_stat_bonus(self, stat: str, amount: int):
        """Add to temporary stat bonus for a given stat."""
        if stat in self.temporary_stat_bonuses:
            self.temporary_stat_bonuses[stat] += amount

    def _tb(self, stat: str) -> int:
        """Shorthand: temporary bonus for a named stat."""
        return self.temporary_stat_bonuses.get(stat, 0)

    # --- Derived properties ---

    @property
    def effective_constitution(self) -> int:
        return self.constitution + self._rb("constitution") + self._tb("constitution")

    @property
    def effective_strength(self) -> int:
        return self.strength + self._rb("strength") + self._tb("strength")

    @property
    def effective_book_smarts(self) -> int:
        return self.book_smarts + self._rb("book_smarts") + self._tb("book_smarts")

    @property
    def effective_street_smarts(self) -> int:
        return self.street_smarts + self._rb("street_smarts") + self._tb("street_smarts")

    @property
    def effective_tolerance(self) -> int:
        return self.tolerance + self._rb("tolerance") + self._tb("tolerance")

    @property
    def effective_swagger(self) -> int:
        return self.swagger + self._rb("swagger") + self._tb("swagger")

    @property
    def max_hp(self):
        """Max HP from Constitution (including ring bonuses). 30 base + 10 per point."""
        return 30 + self.effective_constitution * 10

    @property
    def crit_chance(self):
        """Crit chance from Street-Smarts (including ring bonuses)."""
        return self.effective_street_smarts * 0.03

    @property
    def xp_multiplier(self):
        """Skill XP multiplier from Book-Smarts (including ring bonuses)."""
        return 1.0 + (self.effective_book_smarts - _STAT_MIN) * 0.1

    @property
    def drug_multiplier(self):
        """Drug potency multiplier — lower Tolerance = stronger effects (including ring bonuses)."""
        return 1.0 + (_STAT_MAX - self.effective_tolerance) * 0.1

    def stat_delta(self, stat_name: str) -> int:
        """current minus base for the named stat. Negative = debuffed, positive = buffed."""
        return getattr(self, stat_name) - self._base[stat_name]

    @property
    def swagger_defence(self) -> int:
        """Melee defence from Swagger (including ring bonuses). +1 per 2 points above 5."""
        return (self.effective_swagger - 5) // 2

    def as_list(self):
        """Return list of (label, value, description, attr_name) for the character sheet."""
        return [
            ("Constitution",  self.constitution,  "Affects total Health",                    "constitution"),
            ("Strength",      self.strength,      "Modifies weapon damage",                  "strength"),
            ("Book-Smarts",   self.book_smarts,   "Increases EXP gain",                      "book_smarts"),
            ("Street-Smarts", self.street_smarts, "Increases critical strike chance",        "street_smarts"),
            ("Tolerance",     self.tolerance,     "Changes how drugs affect you",            "tolerance"),
            ("Swagger",       self.swagger,       "Increases defence against melee attacks", "swagger"),
        ]


class EnemyStats:
    """
    Simple randomized stats for enemy entities.

    Constitution — determines enemy max HP
    Strength     — determines enemy power (attack damage)
    """

    def __init__(self):
        self.constitution = random.randint(3, 8)
        self.strength = random.randint(3, 8)

    @property
    def max_hp(self):
        """Enemy HP range: 27–47."""
        return 15 + self.constitution * 4

    @property
    def power(self):
        """Enemy attack power range: 3–8."""
        return self.strength
