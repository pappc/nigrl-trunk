"""
Stat systems for player and enemies.
"""

import random

_STAT_MIN = 6
_STAT_MAX = 12
_TOTAL_POINTS = 45   # 5 stats (excluding Swagger), sum = 45, each clamped to [6, 12]
_NUM_STATS = 5


class PlayerStats:
    """
    Randomly distributed RPG stats for the player character.

    45 points distributed across 5 stats, each clamped to [6, 12]. Swagger starts at 8.

    Constitution  — determines max HP (base 30 + CON × 10)
    Strength      — weapon damage bonus; scaling varies per weapon
    Book-Smarts   — skill point gain rate (higher = faster conversion)
    Street-Smarts — critical strike chance (SS × 3%, range 15%-36%)
    Tolerance     — drug effect multiplier; lower = stronger (1.0x – 1.7x)
    Swagger       — melee defence bonus; +1 defence per 2 points above 8 (starts at 8, not rolled)
    """

    def __init__(self):
        self._player = None  # set by engine after player creation
        self._roll()

    def _roll(self):
        """Distribute 45 points across 5 stats (each [6, 12]). Swagger starts at 8."""
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
        ) = values
        self.swagger = 8
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
        # Tile-based bonuses from spray paint etc.; updated by engine on player move
        self.tile_stat_bonuses: dict[str, int] = {
            "constitution":  0,
            "strength":      0,
            "book_smarts":   0,
            "street_smarts": 0,
            "tolerance":     0,
            "swagger":       0,
        }
        # Temporary armor bonus from effects
        self.temporary_armor_bonus: int = 0
        # Permanent armor bonus from items/effects (survives floor transitions)
        self.permanent_armor_bonus: int = 0
        # Tile-based defense bonus from spray paint; updated by engine on player move
        self.tile_defense_bonus: int = 0
        # Dodge chance — integer percentage (0-90); no base stat grants it
        self.dodge_chance: int = 0
        # Spell damage — flat bonus added to all spell formulas
        self.spell_damage: int = 0
        self.temporary_spell_damage: int = 0
        # Toxicity resistance — percentage; 100 = immune, negative = extra gain
        self.tox_resistance: int = 0
        self.temporary_tox_resistance: int = 0
        # Radiation resistance — percentage; 100 = immune, negative = extra gain
        self.rad_resistance: int = 0
        self.temporary_rad_resistance: int = 0
        # Briskness — percentage bonus to skill points from potential exp
        # Can be negative; no upper cap. Ex: 50 = +50% more skill points
        self.briskness: int = 0
        self.temporary_briskness: int = 0
        # Permanent damage reduction from mutations
        self.permanent_dr: int = 0
        # Good mutation chance: good_chance = (0.33 + base_bonus) * (1 + multiplier), capped at 1.0
        # base_bonus: flat additions (e.g., 0.10 → base becomes 0.43)
        # multiplier: multiplicative scaling (e.g., Five Loco adds 0.25 per stack)
        self.good_mutation_base_bonus: float = 0.0
        self.good_mutation_multiplier: float = 0.0
        # Radiation gain multiplier bonus — stacks additively. 1.0 = +100% (double).
        self.rad_gain_multiplier_bonus: float = 0.0
        # Outgoing damage multipliers (melee + guns, not spells).
        # Multiplicative stacking: two -25% entries → 0.75 * 0.75 = 0.5625x.
        # Effects append on apply, remove on expire.
        self.outgoing_damage_mults: list[float] = []
        # Energy per tick from equipment (hats with "Of Crack" suffix, etc.)
        self.equipment_energy_per_tick: int = 0
        self.equipment_spell_damage: int = 0
        # Faction reputation — raw integer values
        self.reputation: dict[str, int] = {"aldor": -1000, "scryer": -1000}
        # Callbacks fired when a permanent stat increase occurs (e.g. Protein Powder)
        self._on_stat_increase_callbacks: list = []

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

    def set_dodge_chance(self, amount: int):
        """Set dodge chance, clamping to [0, 90]."""
        self.dodge_chance = max(0, min(90, amount))

    def add_dodge_chance(self, amount: int):
        """Add to dodge chance, clamping to [0, 90]."""
        self.set_dodge_chance(self.dodge_chance + amount)

    def set_temporary_spell_damage(self, amount: int):
        """Set temporary spell damage bonus."""
        self.temporary_spell_damage = amount

    def add_temporary_spell_damage(self, amount: int):
        """Add to temporary spell damage bonus."""
        self.temporary_spell_damage += amount

    @property
    def total_spell_damage(self) -> int:
        """Total spell damage = permanent + temporary + equipment + active buff bonuses.
        Wizard Mind Bomb: adds effective_book_smarts while active."""
        base = self.spell_damage + self.temporary_spell_damage + self.equipment_spell_damage
        # Wizard Mind Bomb: add BKS while buff is active
        if self._player is not None:
            for eff in self._player.status_effects:
                if getattr(eff, 'id', '') == 'wizard_mind_bomb':
                    base += self.effective_book_smarts
                    break
        return base

    @property
    def total_tox_resistance(self) -> int:
        """Total tox resistance = permanent + temporary. No upper cap."""
        return self.tox_resistance + self.temporary_tox_resistance

    def set_temporary_tox_resistance(self, amount: int):
        """Set temporary tox resistance bonus."""
        self.temporary_tox_resistance = amount

    def add_temporary_tox_resistance(self, amount: int):
        """Add to temporary tox resistance bonus."""
        self.temporary_tox_resistance += amount

    @property
    def total_rad_resistance(self) -> int:
        """Total rad resistance = permanent + temporary. No upper cap."""
        return self.rad_resistance + self.temporary_rad_resistance

    def set_temporary_rad_resistance(self, amount: int):
        """Set temporary rad resistance bonus."""
        self.temporary_rad_resistance = amount

    def add_temporary_rad_resistance(self, amount: int):
        """Add to temporary rad resistance bonus."""
        self.temporary_rad_resistance += amount

    @property
    def outgoing_damage_mult(self) -> float:
        """Product of all outgoing damage multipliers. 1.0 = no change."""
        result = 1.0
        for m in self.outgoing_damage_mults:
            result *= m
        return result

    @property
    def total_briskness(self) -> int:
        """Total briskness = permanent + temporary. No cap."""
        return self.briskness + self.temporary_briskness

    def set_temporary_briskness(self, amount: int):
        """Set temporary briskness bonus."""
        self.temporary_briskness = amount

    def add_temporary_briskness(self, amount: int):
        """Add to temporary briskness bonus."""
        self.temporary_briskness += amount

    def _tb(self, stat: str) -> int:
        """Shorthand: temporary bonus for a named stat."""
        return self.temporary_stat_bonuses.get(stat, 0)

    def _tslb(self, stat: str) -> int:
        """Shorthand: tile-based bonus for a named stat (spray paint etc.)."""
        return self.tile_stat_bonuses.get(stat, 0)

    # --- Derived properties ---

    @property
    def effective_constitution(self) -> int:
        return self.constitution + self._rb("constitution") + self._tb("constitution") + self._tslb("constitution")

    @property
    def effective_strength(self) -> int:
        return self.strength + self._rb("strength") + self._tb("strength") + self._tslb("strength")

    @property
    def effective_book_smarts(self) -> int:
        return self.book_smarts + self._rb("book_smarts") + self._tb("book_smarts") + self._tslb("book_smarts")

    @property
    def effective_street_smarts(self) -> int:
        return self.street_smarts + self._rb("street_smarts") + self._tb("street_smarts") + self._tslb("street_smarts")

    @property
    def effective_tolerance(self) -> int:
        return self.tolerance + self._rb("tolerance") + self._tb("tolerance") + self._tslb("tolerance")

    @property
    def effective_swagger(self) -> int:
        return self.swagger + self._rb("swagger") + self._tb("swagger") + self._tslb("swagger")

    @property
    def max_hp(self):
        """Max HP from Constitution (including ring bonuses). 30 base + 10 per point."""
        return 30 + self.effective_constitution * 10

    @property
    def crit_chance(self):
        """Crit chance from Street-Smarts (including ring bonuses)."""
        return self.effective_street_smarts * 0.01

    @property
    def xp_multiplier(self):
        """Skill XP multiplier (always 1.0; Book-Smarts affects skill_point gain instead)."""
        return 1.0

    def modify_base_stat(self, stat: str, amount: int, _from_callback: bool = False) -> None:
        """Permanently modify a base stat and update _base. Floors at 1."""
        current = getattr(self, stat)
        new_val = max(1, current + amount)
        setattr(self, stat, new_val)
        self._base[stat] = new_val
        # Fire on-increase callbacks (e.g. Protein Powder buff)
        if amount > 0 and not _from_callback:
            for cb in list(self._on_stat_increase_callbacks):
                cb(stat, amount)

    def stat_delta(self, stat_name: str) -> int:
        """current minus base for the named stat. Negative = debuffed, positive = buffed."""
        return getattr(self, stat_name) - self._base[stat_name]

    @property
    def swagger_defence(self) -> int:
        """Melee defence from Swagger. +1 per 2 points above 8, truncates toward zero."""
        return int((self.effective_swagger - 8) / 2)

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


    # --- Faction reputation ---

    REPUTATION_TIERS = [
        (-16000, "Archenemy"),
        (-8000,  "Hated"),
        (-2000,  "Unfriendly"),
        (2000,   "Neutral"),
        (8000,   "Friendly"),
        (16000,  "Hombre"),
    ]
    REPUTATION_MAX_TITLE = "One of Their Own"

    REPUTATION_COLORS = {
        "Archenemy":       (200, 0, 0),
        "Hated":           (255, 80, 80),
        "Unfriendly":      (255, 160, 80),
        "Neutral":         (180, 180, 180),
        "Friendly":        (100, 200, 100),
        "Hombre":          (80, 180, 255),
        "One of Their Own": (255, 215, 0),
    }

    FACTION_DISPLAY_NAMES = {"aldor": "Aldor", "scryer": "Scryer"}

    def get_reputation_title(self, faction: str) -> str:
        """Return the reputation title for a faction based on current rep value."""
        val = self.reputation.get(faction, 0)
        for threshold, title in self.REPUTATION_TIERS:
            if val < threshold:
                return title
        return self.REPUTATION_MAX_TITLE

    def get_reputation_color(self, faction: str) -> tuple[int, int, int]:
        """Return the color for the current reputation tier."""
        title = self.get_reputation_title(faction)
        return self.REPUTATION_COLORS.get(title, (180, 180, 180))

    def modify_reputation(self, faction: str, amount: int):
        """Add or subtract reputation for a faction."""
        if faction in self.reputation:
            self.reputation[faction] += amount


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
