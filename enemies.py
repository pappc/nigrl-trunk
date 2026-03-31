"""
Enemy definitions, spawn tables, and factory system for NIGRL.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO ADD A NEW ENEMY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. Add a MonsterTemplate(...) entry to MONSTER_REGISTRY with a unique
     snake_case key. All field docs live on the dataclasses themselves —
     see MonsterTemplate, SpecialAttack, OnHitEffect, SpawnEscort below.

  2. Add the key + weight to ZONE_SPAWN_TABLES for every zone it appears in.

  3. Run validate_registry() at startup (or your test suite) to catch
     typos, missing references, and bad ranges instantly.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BLANK TEMPLATE  (copy, fill in, drop into MONSTER_REGISTRY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "enemy_key": MonsterTemplate(
        name         = "",
        char         = "",
        color        = (255, 255, 255),
        constitution  = (1, 1),
        strength      = (1, 1),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp      = 0,
        base_damage  = (0, 0),
        defense      = 0,
        male_chance  = 0.5,
        spawn_min    = 1,
        spawn_max    = 2,
        spawn_with   = [],
        ai           = AIType.MEANDER,
        sight_radius = 6,
        speed        = 100,
        special_attacks = [],
        on_hit_effects  = [],
        cash_drop    = (0, 5),
    ),

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VARIANT SHORTHAND  (inherit from an existing enemy, override a few fields)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    "elite_tweaker": variant("tweaker",
        name        = "Elite Tweaker",
        color       = (200, 160, 130),
        base_hp     = 5,
        constitution = (3, 5),
        strength    = (4, 7),
        defense     = 1,
    ),
"""

from __future__ import annotations

import copy
import dataclasses
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
#  ENUMS — central source of truth for AI modes and effect categories
# ══════════════════════════════════════════════════════════════════════════════

class AIType(Enum):
    """
    Every AI behavior mode the engine supports.
    Adding a new pattern = add an entry here + implement its tick handler.
    """
    MEANDER           = "meander"            # Drifts toward player, attacks adjacent
    WANDER_AMBUSH     = "wander_ambush"      # Wanders until player enters sight_radius, then chases
    PASSIVE_UNTIL_HIT = "passive_until_hit"  # Ignores player until damaged, then chases
    ROOM_GUARD        = "room_guard"         # Wanders in spawn room; chases permanently once player enters
    ALARM_CHASER      = "alarm_chaser"       # Wanders normally; chases everywhere after first floor kill
    ESCORT            = "escort"             # Follows a leader around the room; chases when player enters
    HIT_AND_RUN       = "hit_and_run"        # Ambushes from a distance, attacks once, then flees
    FEMALE_ALARM      = "female_alarm"       # Wanders passively; chases everywhere when any female dies on the floor
    STATIONARY_GUARD  = "stationary_guard"   # Stands completely still until damaged, then chases permanently
    JEROME_GUARD      = "jerome_guard"       # Jerome-specific: stationary until any damage, then chases; faster action rate
    PROXIMITY_ALARM   = "proximity_alarm"    # Meanders until any monster within 10 tiles is attacked, then chases permanently
    CARTEL_UNIT       = "cartel_unit"        # Stationary; aggro depends on faction reputation
    FALCON_ALERT      = "falcon_alert"       # Run to ally, alert 9x9, then chase
    CARTEL_RANGED     = "cartel_ranged"      # Ranged cartel unit; maintain distance, shoot, blink
    RANGED_ROOM_GUARD = "ranged_room_guard"  # Room guard that kites at exact range
    ROOM_COMBAT       = "room_combat"        # Wanders passively; chases permanently when player attacks in same room
    STATIONARY_SPAWNER = "stationary_spawner"  # Stationary mid-combat spawner (never moves)
    SUICIDE_BOMBER     = "suicide_bomber"      # Wanders, chases on sight, explodes when adjacent
    CHEMIST_RANGED     = "chemist_ranged"      # Stationary ranged vial thrower
    PIPE_SPIDER_PACK   = "pipe_spider_pack"    # Slow wander; pack-aggro on sight/room hit
    SAC_SPIDER         = "sac_spider"          # Room guard; shoots web at range, melee when target webbed
    WOLF_SPIDER        = "wolf_spider"         # Fast wander_ambush predator
    BLACK_WIDOW        = "black_widow"         # Mini-boss; room guard, neuro venom stacker
    ZOMBIE_PACK        = "zombie_pack"         # Wander; 10-tile LOS aggro; room pack-aggro
    OCCULTIST_RANGED   = "occultist_ranged"    # Room aggro; ranged hex, prioritize attack


class EffectKind(Enum):
    """
    Status-effect categories.  The combat system dispatches on these.
    """
    DOT           = "dot"            # X damage per turn for N turns
    FEAR          = "fear"           # Forced flee from source, 50% break on damage
    STUN          = "stun"           # Target skips actions
    CHILD_SUPPORT = "child_support"  # Drains $1 per player move for N turns
    MOGGED        = "mogged"         # Stacking debuff that reduces swagger
    WELL_FED      = "well_fed"       # Buff that increases damage and defense
    RAD_BURST     = "rad_burst"      # Instant radiation on hit
    TOX_BURST     = "tox_burst"      # Instant toxicity on hit
    DEPORT        = "deport"         # Teleport player to random tile + stun
    RAD_POISON    = "rad_poison"     # Radiation DOT (rad per turn)
    CONVERSION    = "conversion"     # Converts higher tox/rad to lower 2:1
    RABIES        = "rabies"         # -1 all stats debuff
    BUFF_PURGE    = "buff_purge"     # Remove random buff, gain tox = duration
    INFECTION     = "infection"      # Instant infection on hit
    STAT_DRAIN    = "stat_drain"    # Permanently reduce a random player stat by 1


# ══════════════════════════════════════════════════════════════════════════════
#  COMPONENT DATACLASSES — validated building blocks for monster templates
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OnHitEffect:
    """
    A status effect that can proc when a monster lands a hit.

    Fields
    ------
    name     : Display name shown in the message log.
    kind     : EffectKind enum (or its string value — auto-coerced).
    amount   : Per-turn payload (damage for DOT, 0 for flag-only effects).
    duration : How many turns the effect lasts.
    chance   : Probability this fires per qualifying hit.
               Defaults to 1.0 so effects nested inside a SpecialAttack
               always apply when that attack fires.
    """
    name:     str
    kind:     EffectKind
    amount:   int
    duration: int
    chance:   float = 1.0

    def __post_init__(self):
        if isinstance(self.kind, str):
            try:
                self.kind = EffectKind(self.kind)
            except ValueError:
                valid = ", ".join(e.value for e in EffectKind)
                raise ValueError(
                    f"Effect '{self.name}': unknown kind '{self.kind}'. Valid: {valid}"
                )
        if not 0.0 <= self.chance <= 1.0:
            raise ValueError(f"Effect '{self.name}': chance {self.chance} not in 0.0–1.0")
        if self.duration <= 0:
            raise ValueError(f"Effect '{self.name}': duration must be > 0, got {self.duration}")


@dataclass
class SpecialAttack:
    """
    A special attack checked before every normal attack.
    First entry whose chance roll succeeds fires; normal attack is skipped.

    Fields
    ------
    name         : Name shown in the message log.
    chance       : 0.0–1.0 probability this replaces the normal attack.
    damage_mult  : Multiplier on base damage.  None → randomized 2.0–3.0 at spawn.
    on_hit_effect: Optional status effect applied on hit (always procs if attack fires).
    """
    name:          str
    chance:        float
    damage_mult:   Optional[float] = None
    on_hit_effect: Optional[OnHitEffect] = None

    def __post_init__(self):
        if not 0.0 <= self.chance <= 1.0:
            raise ValueError(f"Attack '{self.name}': chance {self.chance} not in 0.0–1.0")
        if isinstance(self.on_hit_effect, dict):
            self.on_hit_effect = OnHitEffect(**self.on_hit_effect)


@dataclass
class SpawnEscort:
    """
    An enemy type that spawns alongside the parent monster.

    Fields
    ------
    type  : Registry key of the escort enemy.
    count : (min, max) — rolled randomly per spawn event.
    """
    type:  str
    count: tuple[int, int]

    def __post_init__(self):
        if isinstance(self.count, list):
            self.count = tuple(self.count)
        if self.count[0] > self.count[1]:
            raise ValueError(
                f"Escort '{self.type}': count min ({self.count[0]}) > max ({self.count[1]})"
            )


# ══════════════════════════════════════════════════════════════════════════════
#  MONSTER TEMPLATE
# ══════════════════════════════════════════════════════════════════════════════

# Fields that accept (min, max) tuples but might arrive as lists (future JSON/YAML)
_TUPLE_FIELDS = (
    "color", "constitution", "strength", "street_smarts", "book_smarts",
    "tolerance", "swagger", "base_damage", "cash_drop",
)


@dataclass
class MonsterTemplate:
    """
    Validated blueprint for a monster type.
    Individual monsters are rolled from these ranges at spawn time.

    IDENTITY
      name          Display name shown to the player.
      char          Single ASCII character for the map.
      color         (R, G, B) tuple, each 0–255.

    BASE STATS — RPG stats, each a (min, max) range rolled per individual.
      constitution  Drives HP: final HP = base_hp + con × 5
      strength      Drives melee damage: final power = base_damage + str
      street_smarts Drives crit chance: crit% = street_smarts × 3
      book_smarts   Stored as bonus_spell_damage (future use)
      tolerance     No combat derivation for monsters
      swagger       Grants +1 defence per 3 points (added to base defense)

    COMBAT — base values added to stat-derived amounts.
      base_hp       Fixed int: flat HP added before constitution scaling.
      base_damage   (min, max) flat damage added before strength scaling, stored as `power` on Entity.
      defense       Flat damage reduction per hit taken.
      dodge_chance  Integer percentage (0-90) chance to dodge melee attacks.

    GENDER
      male_chance   0.0–1.0 probability of being male.

    SPAWN
      spawn_min     Min individuals per spawn group.
      spawn_max     Max individuals per spawn group.
      spawn_with    List of SpawnEscort — other enemies that appear alongside.

    AI
      ai            AIType enum — selects behavior handler.
      sight_radius  Detection radius in tiles.
      speed         Energy gained per tick (100 = same as player; 200 = twice as fast).

    ABILITIES
      special_attacks  List of SpecialAttack.
      on_hit_effects   List of OnHitEffect (checked on every normal hit).

    DROPS
      cash_drop     (min, max) cash awarded on death.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    name:  str
    char:  str
    color: tuple[int, int, int]

    # ── Base stats (min, max) ─────────────────────────────────────────────
    constitution:  tuple[int, int]
    strength:      tuple[int, int]
    street_smarts: tuple[int, int]
    book_smarts:   tuple[int, int]
    tolerance:     tuple[int, int]
    swagger:       tuple[int, int]

    # ── Combat ────────────────────────────────────────────────────────────
    base_hp:       int
    base_damage:   tuple[int, int]
    defense:       int

    # ── Gender ────────────────────────────────────────────────────────────
    male_chance: float

    # ── Dodge ──────────────────────────────────────────────────────────────
    dodge_chance: int = 0

    # ── Spawn ─────────────────────────────────────────────────────────────
    spawn_min:  int                  = 1
    spawn_max:  int                  = 1
    spawn_with: list[SpawnEscort]    = field(default_factory=list)

    # ── AI ────────────────────────────────────────────────────────────────
    ai:            AIType            = AIType.MEANDER
    sight_radius:  int               = 6
    speed:         int               = 100
    move_cost:     int               = 0     # energy cost override for movement (0 = use ENERGY_THRESHOLD)
    attack_cost:   int               = 0     # energy cost override for attacks  (0 = use ENERGY_THRESHOLD)
    wander_idle_chance: float        = 0.0   # 0.0-1.0: chance to idle instead of wandering each turn

    # ── Abilities ─────────────────────────────────────────────────────────
    special_attacks: list[SpecialAttack] = field(default_factory=list)
    on_hit_effects:  list[OnHitEffect]   = field(default_factory=list)

    # ── Faction ──────────────────────────────────────────────────────────
    faction:        Optional[str]  = None   # "scryer" | "aldor" | None
    ranged_attack:  Optional[dict] = None   # {"range": int, "damage": (min,max), "miss_chance": float, "knockback": int}
    blink_charges:  int            = 0      # emergency teleport charges for specialists

    # ── Spawner ─────────────────────────────────────────────────────────
    spawner_type:   Optional[str] = None   # enemy_type key to spawn mid-combat (e.g. "rad_rat")
    max_spawned:    int            = 0     # max alive children at once

    # ── Death behaviors ────────────────────────────────────────────────
    death_split_type:    Optional[str] = None   # enemy_type to spawn on death
    death_split_count:   int           = 0      # number of children on death
    death_creep_radius:  int           = 0      # radius of toxic creep on death
    death_creep_duration: int          = 0      # duration of death creep
    death_creep_tox:     int           = 0      # tox/turn of death creep

    # ── Trail ──────────────────────────────────────────────────────────
    leaves_trail:   Optional[dict] = None  # {"duration": int, "tox": int}

    # ── Drops ─────────────────────────────────────────────────────────────
    cash_drop: tuple[int, int] = (0, 0)
    death_drop_chance: float     = 0.0    # probability (0.0–1.0) of dropping an item on death
    death_drop_table:  list[str] = field(default_factory=list)  # item_ids to pick from
    death_drop_quantity: tuple[int, int] | None = None  # (min, max) stack size for dropped item

    # ── Validation & coercion ─────────────────────────────────────────────

    def __post_init__(self):
        # Coerce lists → tuples for range / tuple fields
        for fname in _TUPLE_FIELDS:
            val = getattr(self, fname)
            if isinstance(val, list):
                setattr(self, fname, tuple(val))

        # Coerce string → AIType enum
        if isinstance(self.ai, str):
            try:
                self.ai = AIType(self.ai)
            except ValueError:
                valid = ", ".join(e.value for e in AIType)
                raise ValueError(
                    f"{self.name}: unknown ai '{self.ai}'. Valid: {valid}"
                )

        # Coerce nested raw dicts → typed dataclasses
        self.spawn_with = [
            SpawnEscort(**e) if isinstance(e, dict) else e
            for e in self.spawn_with
        ]
        self.special_attacks = [
            SpecialAttack(**a) if isinstance(a, dict) else a
            for a in self.special_attacks
        ]
        self.on_hit_effects = [
            OnHitEffect(**e) if isinstance(e, dict) else e
            for e in self.on_hit_effects
        ]

        # ── Hard validations ──
        if len(self.char) != 1:
            raise ValueError(
                f"{self.name}: char must be exactly 1 character, got '{self.char}'"
            )
        if not all(0 <= c <= 255 for c in self.color):
            raise ValueError(
                f"{self.name}: color values must be 0–255, got {self.color}"
            )
        if not 0.0 <= self.male_chance <= 1.0:
            raise ValueError(f"{self.name}: male_chance must be 0.0–1.0")
        if self.defense < 0:
            raise ValueError(f"{self.name}: defense cannot be negative")
        if self.spawn_min > self.spawn_max:
            raise ValueError(
                f"{self.name}: spawn_min ({self.spawn_min}) > spawn_max ({self.spawn_max})"
            )
        # Validate all (min, max) ranges
        for fname in ("constitution", "strength", "street_smarts", "book_smarts",
                       "tolerance", "swagger", "base_damage", "cash_drop"):
            lo, hi = getattr(self, fname)
            if lo > hi:
                raise ValueError(f"{self.name}: {fname} min ({lo}) > max ({hi})")


# ══════════════════════════════════════════════════════════════════════════════
#  VARIANT HELPER — create enemies that inherit from a base template
# ══════════════════════════════════════════════════════════════════════════════

def variant(base_key: str, **overrides) -> MonsterTemplate:
    """
    Create a MonsterTemplate that copies everything from an existing entry
    and overrides only the fields you specify.

    Mutable fields (spawn_with, special_attacks, on_hit_effects) are
    deep-copied so the new template doesn't share lists with the base.

    Usage:
        "elite_tweaker": variant("tweaker",
            name   = "Elite Tweaker",
            hp     = (20, 35),
            damage = (4, 7),
        ),
    """
    base = MONSTER_REGISTRY[base_key]
    fields = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}

    # Deep-copy mutable fields so variants don't share references
    for mutable in ("spawn_with", "special_attacks", "on_hit_effects"):
        fields[mutable] = copy.deepcopy(fields[mutable])

    fields.update(overrides)
    return MonsterTemplate(**fields)


# ══════════════════════════════════════════════════════════════════════════════
#  MONSTER REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

MONSTER_REGISTRY: dict[str, MonsterTemplate] = {

    # ── TWEAKER ──────────────────────────────────────────────────────────
    # The common grunt of the crack den.  Shambles toward the player slowly
    # and swings weakly when close.  Individually pathetic; dangerous in groups.
    "tweaker": MonsterTemplate(
        name          = "Tweaker",
        char          = "t",
        color         = (200, 50, 50),
        constitution  = (3, 5),
        strength      = (3, 5),
        street_smarts = (0, 0),
        book_smarts   = (1, 2),
        tolerance     = (6, 9),
        swagger       = (1, 3),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.6,
        spawn_min     = 1,
        spawn_max     = 3,
        ai            = AIType.ROOM_GUARD,
        sight_radius  = 6,
        speed         = 80,
        cash_drop     = (0, 3),
    ),

    # ── CRACK ADDICT ─────────────────────────────────────────────────────
    # Zones out wandering until you get too close — then sprints at you.
    "crack_addict": MonsterTemplate(
        name          = "Crack Addict",
        char          = "c",
        color         = (200, 50, 50),
        constitution  = (2, 4),
        strength      = (4, 8),
        street_smarts = (0, 0),
        book_smarts   = (1, 3),
        tolerance     = (7, 10),
        swagger       = (1, 3),
        base_hp       = 2,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.65,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 3,
        speed         = 100,
        cash_drop     = (0, 5),
    ),

    # ── DRUG DEALER ──────────────────────────────────────────────────────
    # Never shows up alone — always brings tweaker bodyguards.
    "drug_dealer": MonsterTemplate(
        name          = "Drug Dealer",
        char          = "D",
        color         = (200, 50, 50),
        constitution  = (3, 5),
        strength      = (3, 5),
        street_smarts = (0, 0),
        book_smarts   = (4, 7),
        tolerance     = (4, 7),
        swagger       = (5, 8),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.75,
        spawn_min     = 1,
        spawn_max     = 1,
        spawn_with    = [
            SpawnEscort(type="tweaker", count=(3, 5)),
        ],
        ai            = AIType.ROOM_GUARD,
        sight_radius  = 6,
        speed         = 100,
        cash_drop         = (5, 15),
        death_drop_chance = 0.75,
        death_drop_table  = ["kush"],
    ),

    # ── UGLY STRIPPER ────────────────────────────────────────────────────
    # Low HP but hits hard.  20% stiletto kick (bleed), 20% fear on normals.
    "ugly_stripper": MonsterTemplate(
        name          = "Ugly Stripper",
        char          = "S",
        color         = (200, 50, 50),
        constitution  = (4, 5),
        strength      = (5, 6),
        street_smarts = (0, 0),
        book_smarts   = (2, 4),
        tolerance     = (4, 7),
        swagger       = (5, 8),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.1,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.ROOM_COMBAT,
        sight_radius  = 6,
        speed         = 100,
        wander_idle_chance = 0.6,
        special_attacks = [
            SpecialAttack(
                name         = "High Heel Kick",
                chance       = 0.20,
                damage_mult  = None,            # randomized 2.0–3.0 at spawn
                on_hit_effect = OnHitEffect(
                    name     = "Bleeding",
                    kind     = EffectKind.DOT,
                    amount   = 1,
                    duration = 4,
                ),
            ),
        ],
        on_hit_effects = [
            OnHitEffect(
                name     = "Frightened",
                kind     = EffectKind.FEAR,
                chance   = 0.20,
                amount   = 0,
                duration = 10,
            ),
        ],
        cash_drop     = (0, 8),
    ),

    # ── BABY MOMMA ───────────────────────────────────────────────────────
    # Tough and passive until attacked.  Slaps you with child-support.
    "baby_momma": MonsterTemplate(
        name          = "Baby Momma",
        char          = "B",
        color         = (200, 50, 50),
        constitution  = (5, 9),
        strength      = (2, 4),
        street_smarts = (0, 0),
        book_smarts   = (3, 6),
        tolerance     = (4, 7),
        swagger       = (4, 7),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.0,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.PASSIVE_UNTIL_HIT,
        sight_radius  = 6,
        speed         = 100,
        wander_idle_chance = 0.6,
        on_hit_effects = [
            OnHitEffect(
                name     = "Child Support",
                kind     = EffectKind.CHILD_SUPPORT,
                chance   = 0.30,
                amount   = 0,
                duration = 20,
            ),
        ],
        cash_drop     = (0, 4),
    ),

    # ── NIGLET ───────────────────────────────────────────────────────────
    # Sneaky street urchin.  Attacks once from ambush to steal your cash,
    # then runs away.  Low HP, fast movement, but cowardly. Damage ignores defense.
    "niglet": MonsterTemplate(
        name          = "Niglet",
        char          = "n",
        color         = (200, 50, 50),
        constitution  = (1, 2),
        strength      = (6, 7),
        street_smarts = (0, 0),
        book_smarts   = (1, 2),
        tolerance     = (2, 4),
        swagger       = (2, 4),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        dodge_chance  = 10,
        male_chance   = 0.5,
        spawn_min     = 1,
        spawn_max     = 3,
        ai            = AIType.HIT_AND_RUN,
        sight_radius  = 4,
        speed         = 120,
        special_attacks = [
            SpecialAttack(
                name         = "Pickpocket",
                chance       = 0.85,  # 85% chance to steal instead of normal attack
                damage_mult  = 0.0,   # No physical damage, steals cash instead
            ),
        ],
        cash_drop     = (1, 3),
    ),

    # ── FAT GOONER ───────────────────────────────────────────────────────
    # Docile slob who wanders aimlessly — until a woman dies anywhere on the
    # floor.  Then he flies into a rage and chases the player permanently.
    # Tanky with high defense, slow and lethargic, but hits hard.
    "fat_gooner": MonsterTemplate(
        name          = "Fat Gooner",
        char          = "G",
        color         = (200, 50, 50),
        constitution  = (8, 10),
        strength      = (3, 3),
        street_smarts = (0, 0),
        book_smarts   = (2, 4),
        tolerance     = (2, 5),
        swagger       = (1, 3),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 3,
        male_chance   = 1.0,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.FEMALE_ALARM,
        sight_radius  = 8,
        speed         = 70,
        cash_drop     = (0, 5),
    ),

    # ── THUG ──────────────────────────────────────────────────────────────
    # Street punk who lurks and watches. Ambushes when player gets close,
    # then relentlessly chases. Applies stacking "Mogged" debuff to humiliate.
    "thug": MonsterTemplate(
        name          = "Thug",
        char          = "T",
        color         = (200, 50, 50),
        constitution  = (5, 6),
        strength      = (5, 5),
        street_smarts = (0, 0),
        book_smarts   = (2, 3),
        tolerance     = (3, 5),
        swagger       = (4, 7),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.8,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 6,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Mogged",
                kind     = EffectKind.MOGGED,
                chance   = 0.50,
                amount   = 1,
                duration = 10,
            ),
        ],
        cash_drop     = (5, 12),
    ),

    # ── BIG NIGGA JEROME ──────────────────────────────────────────────────
    # Boss monster at the bottom of the crack den.  Tough, aggressive, and
    # dangerous.  Defense penetrating damage, knockback attacks, and self-healing
    # when low on health.  Will be spawn-locked to a specific room.
    "big_nigga_jerome": MonsterTemplate(
        name          = "Big Nigga Jerome",
        char          = "J",
        color         = (200, 50, 50),
        constitution  = (10, 10),
        strength      = (4, 4),
        street_smarts = (3, 3),
        book_smarts   = (3, 5),
        tolerance     = (5, 7),
        swagger       = (15, 15),
        base_hp       = 25,
        base_damage   = (0, 0),
        defense       = 2,
        male_chance   = 1.0,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.JEROME_GUARD,
        sight_radius  = 8,
        speed         = 120,
        move_cost     = 40,
        attack_cost   = 100,
        special_attacks = [
            SpecialAttack(
                name         = "Knockback Punch",
                chance       = 0.25,
                damage_mult  = 1.0,
                on_hit_effect = OnHitEffect(
                    name     = "Knocked Back",
                    kind     = EffectKind.DOT,  # Marker (handled specially in engine)
                    amount   = 0,
                    duration = 1,
                ),
            ),
        ],
        cash_drop          = (20, 50),
        death_drop_chance  = 1.0,
        death_drop_table   = ["big_niggas_key"],
    ),
    # ══════════════════════════════════════════════════════════════════════════
    #  METH LAB — SCRYER FACTION  (orange: 255, 140, 30)
    # ══════════════════════════════════════════════════════════════════════════

    # ── SCRYER GRUNT ────────────────────────────────────────────────────
    # Fast-moving cartel foot soldier.  Passive until aggro'd, then chases.
    "scryer_grunt": MonsterTemplate(
        name          = "Scryer Grunt",
        char          = "G",
        color         = (255, 140, 30),
        constitution  = (6, 8),
        strength      = (3, 5),
        street_smarts = (1, 2),
        book_smarts   = (1, 2),
        tolerance     = (3, 5),
        swagger       = (2, 4),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.8,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.CARTEL_UNIT,
        sight_radius  = 6,
        speed         = 100,
        move_cost     = 60,
        cash_drop     = (3, 8),
        faction       = "scryer",
    ),

    # ── SCRYER FALCON ───────────────────────────────────────────────────
    # Hallway scout that runs to an ally and alerts a 9x9 area.
    "scryer_falcon": MonsterTemplate(
        name          = "Scryer Falcon",
        char          = "F",
        color         = (255, 140, 30),
        constitution  = (4, 6),
        strength      = (3, 4),
        street_smarts = (1, 2),
        book_smarts   = (1, 2),
        tolerance     = (3, 5),
        swagger       = (1, 3),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.7,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.FALCON_ALERT,
        sight_radius  = 6,
        speed         = 120,
        cash_drop     = (2, 6),
        faction       = "scryer",
    ),

    # ── SCRYER HITMAN ───────────────────────────────────────────────────
    # Dangerous melee fighter with DOT, radiation, and toxicity procs.
    "scryer_hitman": MonsterTemplate(
        name          = "Scryer Hitman",
        char          = "H",
        color         = (255, 140, 30),
        constitution  = (8, 10),
        strength      = (5, 7),
        street_smarts = (2, 3),
        book_smarts   = (2, 3),
        tolerance     = (3, 5),
        swagger       = (3, 5),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 2,
        male_chance   = 0.85,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.CARTEL_UNIT,
        sight_radius  = 6,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Poison",
                kind     = EffectKind.DOT,
                chance   = 0.25,
                amount   = 2,
                duration = 4,
            ),
            OnHitEffect(
                name     = "Rad Burst",
                kind     = EffectKind.RAD_BURST,
                chance   = 0.20,
                amount   = 5,
                duration = 1,
            ),
            OnHitEffect(
                name     = "Tox Burst",
                kind     = EffectKind.TOX_BURST,
                chance   = 0.20,
                amount   = 5,
                duration = 1,
            ),
        ],
        cash_drop     = (8, 15),
        death_drop_chance = 0.5,
        death_drop_table  = ["light_rounds", "medium_rounds"],
        death_drop_quantity = (5, 12),
        faction       = "scryer",
    ),

    # ── SCRYER SPECIALIST ───────────────────────────────────────────────
    # Ranged attacker with emergency blink.  Weak in melee.
    "scryer_specialist": MonsterTemplate(
        name          = "Scryer Specialist",
        char          = "S",
        color         = (255, 140, 30),
        constitution  = (5, 7),
        strength      = (2, 3),
        street_smarts = (2, 3),
        book_smarts   = (3, 5),
        tolerance     = (3, 5),
        swagger       = (2, 4),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.6,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.CARTEL_RANGED,
        sight_radius  = 6,
        speed         = 100,
        cash_drop     = (5, 12),
        death_drop_chance = 0.5,
        death_drop_table  = ["light_rounds", "medium_rounds"],
        death_drop_quantity = (5, 12),
        faction       = "scryer",
        ranged_attack = {"range": 4, "damage": (5, 8), "miss_chance": 0.25, "knockback": 0},
        blink_charges = 1,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    #  METH LAB — ALDOR FACTION  (purple-pink: 220, 50, 180)
    # ══════════════════════════════════════════════════════════════════════════

    # ── ALDOR GRUNT ─────────────────────────────────────────────────────
    "aldor_grunt": MonsterTemplate(
        name          = "Aldor Grunt",
        char          = "G",
        color         = (220, 50, 180),
        constitution  = (6, 8),
        strength      = (3, 5),
        street_smarts = (1, 2),
        book_smarts   = (1, 2),
        tolerance     = (3, 5),
        swagger       = (2, 4),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.8,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.CARTEL_UNIT,
        sight_radius  = 6,
        speed         = 100,
        move_cost     = 60,
        cash_drop     = (3, 8),
        faction       = "aldor",
    ),

    # ── ALDOR FALCON ────────────────────────────────────────────────────
    "aldor_falcon": MonsterTemplate(
        name          = "Aldor Falcon",
        char          = "F",
        color         = (220, 50, 180),
        constitution  = (4, 6),
        strength      = (3, 4),
        street_smarts = (1, 2),
        book_smarts   = (1, 2),
        tolerance     = (3, 5),
        swagger       = (1, 3),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.7,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.FALCON_ALERT,
        sight_radius  = 6,
        speed         = 120,
        cash_drop     = (2, 6),
        faction       = "aldor",
    ),

    # ── ALDOR HITMAN ────────────────────────────────────────────────────
    # Dangerous melee fighter with stun proc.
    "aldor_hitman": MonsterTemplate(
        name          = "Aldor Hitman",
        char          = "H",
        color         = (220, 50, 180),
        constitution  = (8, 10),
        strength      = (5, 7),
        street_smarts = (2, 3),
        book_smarts   = (2, 3),
        tolerance     = (3, 5),
        swagger       = (3, 5),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 2,
        male_chance   = 0.85,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.CARTEL_UNIT,
        sight_radius  = 6,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Stunned",
                kind     = EffectKind.STUN,
                chance   = 0.25,
                amount   = 0,
                duration = 3,
            ),
        ],
        cash_drop     = (8, 15),
        death_drop_chance = 0.5,
        death_drop_table  = ["light_rounds", "medium_rounds"],
        death_drop_quantity = (5, 12),
        faction       = "aldor",
    ),

    # ── ALDOR SPECIALIST ────────────────────────────────────────────────
    # Ranged attacker with knockback and emergency blink.
    "aldor_specialist": MonsterTemplate(
        name          = "Aldor Specialist",
        char          = "S",
        color         = (220, 50, 180),
        constitution  = (5, 7),
        strength      = (2, 3),
        street_smarts = (2, 3),
        book_smarts   = (3, 5),
        tolerance     = (3, 5),
        swagger       = (2, 4),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.6,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.CARTEL_RANGED,
        sight_radius  = 6,
        speed         = 100,
        cash_drop     = (5, 12),
        death_drop_chance = 0.5,
        death_drop_table  = ["light_rounds", "medium_rounds"],
        death_drop_quantity = (5, 12),
        faction       = "aldor",
        ranged_attack = {"range": 3, "damage": (3, 6), "miss_chance": 0.20, "knockback": 1, "knockback_chance": 0.50},
        blink_charges = 1,
    ),

    # ══════════════════════════════════════════════════════════════════════════
    #  METH LAB — LAW ENFORCEMENT  (later floors, no faction)
    # ══════════════════════════════════════════════════════════════════════════

    # ── ICE AGENT ───────────────────────────────────────────────────────
    # Tough melee unit.  Chance on hit to "deport" — teleports the player
    # to a random tile on the floor and stuns them for 6 turns.
    "ice_agent": MonsterTemplate(
        name          = "ICE Agent",
        char          = "I",
        color         = (200, 50, 50),
        constitution  = (8, 10),
        strength      = (5, 7),
        street_smarts = (2, 4),
        book_smarts   = (3, 5),
        tolerance     = (4, 6),
        swagger       = (4, 6),
        base_hp       = 5,
        base_damage   = (0, 0),
        defense       = 2,
        male_chance   = 0.75,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.ROOM_GUARD,
        sight_radius  = 7,
        speed         = 70,
        on_hit_effects = [
            OnHitEffect(
                name     = "Deported",
                kind     = EffectKind.DEPORT,
                chance   = 0.20,
                amount   = 0,
                duration = 6,
            ),
        ],
        cash_drop     = (10, 20),
        death_drop_chance = 0.6,
        death_drop_table  = ["light_rounds", "medium_rounds", "heavy_rounds"],
        death_drop_quantity = (8, 15),
    ),

    # ── DEA AGENT ───────────────────────────────────────────────────────
    # Ranged unit that kites at exactly range 3.  Low attack cost lets it
    # shoot and reposition in the same turn.
    "dea_agent": MonsterTemplate(
        name          = "DEA Agent",
        char          = "A",
        color         = (200, 50, 50),
        constitution  = (6, 8),
        strength      = (2, 3),
        street_smarts = (3, 5),
        book_smarts   = (4, 6),
        tolerance     = (3, 5),
        swagger       = (3, 5),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.7,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.RANGED_ROOM_GUARD,
        sight_radius  = 7,
        speed         = 100,
        attack_cost   = 40,
        cash_drop     = (8, 18),
        death_drop_chance = 0.6,
        death_drop_table  = ["light_rounds", "medium_rounds", "heavy_rounds"],
        death_drop_quantity = (8, 15),
        ranged_attack = {"range": 3, "damage": (4, 7), "miss_chance": 0.15, "knockback": 0},
    ),

    # ══════════════════════════════════════════════════════════════════════════
    #  METH LAB — RADIATION ENEMIES  (non-faction, red-colored)
    # ══════════════════════════════════════════════════════════════════════════

    # ── RAD RAT ──────────────────────────────────────────────────────────
    # Tiny, fast, 1 unblockable damage + 10 radiation per hit.  Spawns in
    # groups of 3.  Also spawned by Rad Rats Nest mid-combat.
    "rad_rat": MonsterTemplate(
        name          = "Rad Rat",
        char          = "r",
        color         = (200, 50, 50),
        constitution  = (1, 2),
        strength      = (1, 1),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 0,
        base_damage   = (1, 1),
        defense       = 0,
        male_chance   = 0.5,
        spawn_min     = 3,
        spawn_max     = 3,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 8,
        speed         = 140,
        move_cost     = 50,
        attack_cost   = 50,
        on_hit_effects = [
            OnHitEffect(
                name     = "Irradiate",
                kind     = EffectKind.RAD_BURST,
                chance   = 1.0,
                amount   = 10,
                duration = 1,
            ),
        ],
        cash_drop     = (0, 1),
    ),

    # ── RAD RATS NEST ────────────────────────────────────────────────────
    # Stationary spawner: sits in place, creates Rad Rats up to max 3 alive.
    "rad_rats_nest": MonsterTemplate(
        name          = "Rad Rats Nest",
        char          = "N",
        color         = (200, 50, 50),
        constitution  = (5, 7),
        strength      = (1, 1),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.5,
        spawn_min     = 1,
        spawn_max     = 1,
        ai            = AIType.STATIONARY_SPAWNER,
        sight_radius  = 8,
        speed         = 80,
        spawner_type  = "rad_rat",
        max_spawned   = 3,
        cash_drop     = (3, 8),
    ),

    # ── MUTATOR ──────────────────────────────────────────────────────────
    # 15% chance for 100-rad burst + always 15 rad per hit.
    "mutator": MonsterTemplate(
        name          = "Mutator",
        char          = "M",
        color         = (200, 50, 50),
        constitution  = (6, 8),
        strength      = (4, 6),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.5,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 8,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Rad Burst",
                kind     = EffectKind.RAD_BURST,
                chance   = 0.15,
                amount   = 100,
                duration = 1,
            ),
            OnHitEffect(
                name     = "Irradiate",
                kind     = EffectKind.RAD_BURST,
                chance   = 1.0,
                amount   = 15,
                duration = 1,
            ),
        ],
        cash_drop     = (3, 10),
    ),

    # ── CONVERTOR ────────────────────────────────────────────────────────
    # 40% on hit: debuff that converts higher tox/rad → lower at 2:1 for 20 turns.
    "convertor": MonsterTemplate(
        name          = "Convertor",
        char          = "C",
        color         = (200, 50, 50),
        constitution  = (6, 8),
        strength      = (3, 5),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 1,
        male_chance   = 0.5,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 8,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Conversion",
                kind     = EffectKind.CONVERSION,
                chance   = 0.40,
                amount   = 0,
                duration = 20,
            ),
        ],
        cash_drop     = (3, 10),
    ),

    # ── URANIUM BEETLE ───────────────────────────────────────────────────
    # High defense (5), 50% on hit: rad poison DOT (10 rad/turn for 5 turns).
    "uranium_beetle": MonsterTemplate(
        name          = "Uranium Beetle",
        char          = "U",
        color         = (200, 50, 50),
        constitution  = (2, 3),
        strength      = (4, 6),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 0,
        base_damage   = (0, 0),
        defense       = 5,
        male_chance   = 0.5,
        spawn_min     = 1,
        spawn_max     = 2,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 8,
        speed         = 90,
        on_hit_effects = [
            OnHitEffect(
                name     = "Rad Poison",
                kind     = EffectKind.RAD_POISON,
                chance   = 0.50,
                amount   = 10,
                duration = 5,
            ),
        ],
        cash_drop     = (2, 6),
    ),

    # ══════════════════════════════════════════════════════════════════════════
    # METH LAB ZONE — toxic enemies
    # ══════════════════════════════════════════════════════════════════════════

    # ── COVID-26 ──────────────────────────────────────────────────────────
    # Suicide bomber. Wanders until player spotted, then rushes in and explodes
    # for heavy unblockable damage + toxicity. Dies on detonation.
    "covid_26": MonsterTemplate(
        name          = "Covid-26",
        char          = "o",
        color         = (200, 50, 50),
        constitution  = (0, 1),
        strength      = (1, 1),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 5,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.5,
        spawn_min     = 2,
        spawn_max     = 4,
        ai            = AIType.SUICIDE_BOMBER,
        sight_radius  = 8,
        speed         = 100,
        cash_drop     = (0, 2),
    ),

    # ── PURGER ────────────────────────────────────────────────────────────
    # Medium fighter. 35% chance on hit to remove a random buff from the player
    # and convert its remaining duration into toxicity.
    "purger": MonsterTemplate(
        name          = "Purger",
        char          = "P",
        color         = (200, 50, 50),
        constitution  = (4, 6),
        strength      = (3, 5),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 15,
        base_damage   = (4, 7),
        defense       = 2,
        male_chance   = 0.5,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 6,
        speed         = 100,
        on_hit_effects = [
            OnHitEffect(
                name     = "Purge",
                kind     = EffectKind.BUFF_PURGE,
                chance   = 0.35,
                amount   = 0,
                duration = 1,
            ),
        ],
        cash_drop     = (1, 5),
    ),

    # ── TOXIC SLUG ────────────────────────────────────────────────────────
    # Slow creature that leaves toxic creep trails and explodes into creep on death.
    "toxic_slug": MonsterTemplate(
        name          = "Toxic Slug",
        char          = "s",
        color         = (200, 50, 50),
        constitution  = (5, 7),
        strength      = (2, 4),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 20,
        base_damage   = (3, 5),
        defense       = 1,
        male_chance   = 0.5,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 5,
        speed         = 60,
        on_hit_effects = [
            OnHitEffect(
                name     = "Toxic Slime",
                kind     = EffectKind.TOX_BURST,
                chance   = 1.0,
                amount   = 10,
                duration = 1,
            ),
        ],
        leaves_trail         = {"duration": 10, "tox": 5},
        death_creep_radius   = 2,
        death_creep_duration = 10,
        death_creep_tox      = 5,
        cash_drop     = (0, 3),
    ),

    # ── STRAY DOG ─────────────────────────────────────────────────────────
    # Fast, aggressive. Tox on hit + 25% chance to inflict rabies (-1 all stats).
    "stray_dog": MonsterTemplate(
        name          = "Stray Dog",
        char          = "d",
        color         = (200, 50, 50),
        constitution  = (4, 6),
        strength      = (1, 2),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 12,
        base_damage   = (2, 8),
        defense       = 1,
        male_chance   = 0.5,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 7,
        speed         = 130,
        on_hit_effects = [
            OnHitEffect(
                name     = "Toxic Bite",
                kind     = EffectKind.TOX_BURST,
                chance   = 1.0,
                amount   = 3,
                duration = 1,
            ),
            OnHitEffect(
                name     = "Rabies",
                kind     = EffectKind.RABIES,
                chance   = 0.25,
                amount   = 0,
                duration = 15,
            ),
        ],
        cash_drop     = (0, 2),
    ),

    # ── SLUDGE AMALGAM ────────────────────────────────────────────────────
    # Slow, tanky blob. Deals heavy tox. Splits into 2 Mini Sludges on death.
    "sludge_amalgam": MonsterTemplate(
        name          = "Sludge Amalgam",
        char          = "O",
        color         = (200, 50, 50),
        constitution  = (8, 12),
        strength      = (2, 3),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 30,
        base_damage   = (2, 4),
        defense       = 3,
        male_chance   = 0.5,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 5,
        speed         = 70,
        on_hit_effects = [
            OnHitEffect(
                name     = "Toxic Slam",
                kind     = EffectKind.TOX_BURST,
                chance   = 1.0,
                amount   = 20,
                duration = 1,
            ),
        ],
        death_split_type  = "mini_sludge",
        death_split_count = 2,
        cash_drop     = (2, 8),
    ),

    # ── MINI SLUDGE ───────────────────────────────────────────────────────
    # Small sludge spawned by Amalgam death. NOT in spawn tables.
    "mini_sludge": MonsterTemplate(
        name          = "Mini Sludge",
        char          = "m",
        color         = (200, 50, 50),
        constitution  = (3, 4),
        strength      = (2, 3),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 8,
        base_damage   = (2, 4),
        defense       = 1,
        male_chance   = 0.5,
        ai            = AIType.WANDER_AMBUSH,
        sight_radius  = 6,
        speed         = 110,
        on_hit_effects = [
            OnHitEffect(
                name     = "Toxic Touch",
                kind     = EffectKind.TOX_BURST,
                chance   = 1.0,
                amount   = 10,
                duration = 1,
            ),
        ],
        cash_drop     = (0, 2),
    ),

    # ── CHEMIST ───────────────────────────────────────────────────────────
    # Stationary ranged enemy. Throws toxic vials at player's position,
    # creating toxic creep tiles. Doesn't move when player is in LOS.
    "chemist": MonsterTemplate(
        name          = "Chemist",
        char          = "k",
        color         = (200, 50, 50),
        constitution  = (3, 5),
        strength      = (1, 2),
        street_smarts = (0, 0),
        book_smarts   = (0, 0),
        tolerance     = (0, 0),
        swagger       = (0, 0),
        base_hp       = 10,
        base_damage   = (2, 3),
        defense       = 1,
        male_chance   = 0.5,
        ai            = AIType.CHEMIST_RANGED,
        sight_radius  = 6,
        speed         = 100,
        cash_drop     = (1, 4),
    ),

    # ── Spider event enemies (not in spawn tables — spawned by floor events) ──

    "pipe_spider": MonsterTemplate(
        name          = "Pipe Spider",
        char          = "s",
        color         = (200, 50, 50),
        constitution  = (1, 2),
        strength      = (1, 2),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 5,
        base_damage   = (3, 3),
        defense       = 0,
        male_chance   = 0.5,
        ai            = AIType.PIPE_SPIDER_PACK,
        sight_radius  = 4,
        speed         = 100,
        spawn_min     = 2,
        spawn_max     = 4,
        cash_drop     = (0, 1),
        death_drop_chance = 0.05,
        death_drop_table  = ["mature_spider_egg"],
        on_hit_effects = [
            OnHitEffect("pipe_venom", EffectKind.DOT, amount=1, duration=10, chance=1.0),
        ],
    ),

    "sac_spider": MonsterTemplate(
        name          = "Sac Spider",
        char          = "S",
        color         = (200, 50, 50),
        constitution  = (1, 2),
        strength      = (1, 2),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 18,
        base_damage   = (5, 7),
        defense       = 0,
        male_chance   = 0.5,
        ai            = AIType.SAC_SPIDER,
        sight_radius  = 5,
        speed         = 100,
        spawn_min     = 1,
        spawn_max     = 2,
        cash_drop     = (1, 3),
        death_drop_chance = 0.10,
        death_drop_table  = ["mature_spider_egg"],
    ),

    "wolf_spider": MonsterTemplate(
        name          = "Wolf Spider",
        char          = "w",
        color         = (200, 50, 50),
        constitution  = (2, 3),
        strength      = (2, 4),
        street_smarts = (1, 2),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 15,
        base_damage   = (5, 7),
        defense       = 0,
        dodge_chance   = 20,
        male_chance   = 0.5,
        ai            = AIType.WOLF_SPIDER,
        sight_radius  = 5,
        speed         = 140,
        spawn_min     = 1,
        spawn_max     = 2,
        cash_drop     = (1, 4),
        death_drop_chance = 0.08,
        death_drop_table  = ["mature_spider_egg"],
        special_attacks = [
            SpecialAttack(name="Pounce", chance=0.30, damage_mult=1.5),
        ],
        on_hit_effects = [
            OnHitEffect("wolf_spider_venom", EffectKind.DOT, amount=1, duration=10, chance=1.0),
        ],
    ),

    "black_widow": MonsterTemplate(
        name          = "Black Widow",
        char          = "W",
        color         = (200, 50, 50),
        constitution  = (3, 5),
        strength      = (3, 5),
        street_smarts = (2, 3),
        book_smarts   = (1, 2),
        tolerance     = (2, 3),
        swagger       = (2, 3),
        base_hp       = 58,
        base_damage   = (7, 10),
        defense       = 2,
        male_chance   = 0.0,
        ai            = AIType.BLACK_WIDOW,
        sight_radius  = 6,
        speed         = 110,
        spawn_min     = 1,
        spawn_max     = 1,
        cash_drop     = (5, 15),
        death_split_type  = "pipe_spider",
        death_split_count = 4,
        death_drop_chance = 0.25,
        death_drop_table  = ["mature_spider_egg"],
        on_hit_effects = [
            OnHitEffect("neuro_venom", EffectKind.DOT, amount=1, duration=12, chance=0.50),
        ],
    ),

    # ── Zombie event enemies (not in spawn tables — spawned by events) ──

    "zombie": MonsterTemplate(
        name          = "Zombie",
        char          = "z",
        color         = (120, 200, 50),
        constitution  = (3, 5),
        strength      = (3, 5),
        street_smarts = (1, 1),
        book_smarts   = (1, 1),
        tolerance     = (1, 1),
        swagger       = (1, 1),
        base_hp       = 5,
        base_damage   = (2, 3),
        defense       = 0,
        male_chance   = 0.5,
        ai            = AIType.ZOMBIE_PACK,
        sight_radius  = 10,
        speed         = 120,
        spawn_min     = 3,
        spawn_max     = 5,
        cash_drop     = (0, 1),
        death_drop_chance = 0.02,
        death_drop_table  = [
            "ruger_mark_v", "hv_express", "glizzy_19", "uzi", "ar_14",
            "sawed_off", "m16", "tec_9", "rpg", "cruiser_500", "draco",
        ],
        on_hit_effects = [
            OnHitEffect("Infection", EffectKind.INFECTION, amount=5, duration=1, chance=0.50),
        ],
    ),

    # ── Haitian Daycare enemies (spawned in sublevel only) ──

    "ritualist": MonsterTemplate(
        name          = "Ritualist",
        char          = "r",
        color         = (200, 50, 50),
        constitution  = (4, 5),
        strength      = (2, 2),
        street_smarts = (2, 3),
        book_smarts   = (3, 5),
        tolerance     = (2, 3),
        swagger       = (2, 3),
        base_hp       = 12,
        base_damage   = (3, 3),
        defense       = 0,
        male_chance   = 0.5,
        ai            = AIType.ROOM_GUARD,
        sight_radius  = 7,
        speed         = 100,
        spawn_min     = 1,
        spawn_max     = 3,
        cash_drop     = (1, 5),
        on_hit_effects = [
            OnHitEffect("Stat Drain", EffectKind.STAT_DRAIN, amount=1, duration=1, chance=0.10),
        ],
    ),

    "occultist": MonsterTemplate(
        name          = "Occultist",
        char          = "o",
        color         = (200, 50, 50),
        constitution  = (4, 5),
        strength      = (1, 1),
        street_smarts = (2, 3),
        book_smarts   = (4, 6),
        tolerance     = (2, 3),
        swagger       = (2, 3),
        base_hp       = 5,
        base_damage   = (0, 0),
        defense       = 0,
        male_chance   = 0.5,
        ai            = AIType.OCCULTIST_RANGED,
        sight_radius  = 7,
        speed         = 90,
        spawn_min     = 1,
        spawn_max     = 3,
        cash_drop     = (2, 6),
        ranged_attack = {
            "damage": (1, 5),
            "range": 4,
            "miss_chance": 0.0,
            "pierces_defense": True,
            "name": "hexes",
            "on_hit_effect": {
                "chance": 0.20,
                "effect_id": "hex_slow",
                "kwargs": {"duration": 20, "stacks": 1},
            },
        },
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
#  ZONE SPAWN TABLES  — per-floor weighted tables within each zone
# ══════════════════════════════════════════════════════════════════════════════
#
#  Structure:  zone -> floor_num (0-indexed) -> [(enemy_key, weight), ...]
#  Lookup: get_spawn_table(zone, floor_num) returns the table for that floor,
#          falling back to the highest defined floor if floor_num exceeds it.

ZONE_SPAWN_TABLES: dict[str, dict[int, list[tuple[str, int]]]] = {
    "crack_den": {
        # Floor 1 — mostly fodder, occasional Stripper/Dealer surprise
        0: [
            ("tweaker",        40),
            ("niglet",         10),
            ("baby_momma",     15),
            ("crack_addict",   15),
            ("fat_gooner",      5),
            ("ugly_stripper",  15),
            ("thug",            3),
            ("drug_dealer",    12),
        ],
        # Floor 2 — balanced mix, Baby Momma + Crack Addict rise
        1: [
            ("tweaker",        30),
            ("niglet",         20),
            ("baby_momma",     20),
            ("crack_addict",   20),
            ("fat_gooner",     10),
            ("ugly_stripper",  18),
            ("thug",            8),
            ("drug_dealer",    15),
        ],
        # Floor 3 — everything common, Gooner + Stripper peak
        2: [
            ("tweaker",        20),
            ("niglet",         15),
            ("baby_momma",     15),
            ("crack_addict",   20),
            ("fat_gooner",     15),
            ("ugly_stripper",  18),
            ("thug",           15),
            ("drug_dealer",    15),
        ],
        # Floor 4 — Thug + Dealer dominated (Jerome's floor)
        3: [
            ("tweaker",        10),
            ("niglet",         10),
            ("baby_momma",     10),
            ("crack_addict",   15),
            ("fat_gooner",     15),
            ("ugly_stripper",  20),
            ("thug",           20),
            ("drug_dealer",    18),
        ],
    },
    # ── FUTURE ZONES ─────────────────────────────────────────────────────────
    # meth_lab uses faction tables instead of ZONE_SPAWN_TABLES (see below)
    "meth_lab":          {},
    "casino_botanical":  {},   # TODO: populate when casino + botanical garden zone is built
    "the_underprison":   {},   # TODO: populate when The Underprison zone is built
}


# ══════════════════════════════════════════════════════════════════════════════
#  HALLWAY SPAWN TABLES — monsters that spawn in corridors between rooms
# ══════════════════════════════════════════════════════════════════════════════
#  Same structure as ZONE_SPAWN_TABLES: zone -> floor_num -> [(enemy_key, weight)]
#  Only zones with entries here will have hallway spawning.
#  Crack Den has NO hallway spawns (empty / absent = no hallway monsters).

ZONE_HALLWAY_SPAWN_TABLES: dict[str, dict[int, list[tuple[str, int]]]] = {
    # "crack_den" intentionally absent — no hallway spawning in crack den
    # "meth_lab" — hallways are falcon-only (handled by _spawn_hallway_falcons)
}


# ══════════════════════════════════════════════════════════════════════════════
#  METH LAB FACTION SPAWN TABLES — per-faction, per-floor enemy weights
# ══════════════════════════════════════════════════════════════════════════════
#  Used by spawn_meth_lab() instead of ZONE_SPAWN_TABLES.
#  NO falcons in these tables — falcons spawn in hallways only.

METH_LAB_SCRYER_TABLES: dict[int, list[tuple[str, int]]] = {
    0: [("scryer_grunt", 50), ("scryer_hitman", 5),  ("scryer_specialist", 5)],
    1: [("scryer_grunt", 60), ("scryer_hitman", 10), ("scryer_specialist", 10)],
    2: [("scryer_grunt", 40), ("scryer_hitman", 10), ("scryer_specialist", 5)],
    3: [("scryer_grunt", 40), ("scryer_hitman", 15), ("scryer_specialist", 10)],
    4: [("scryer_grunt", 40), ("scryer_hitman", 20), ("scryer_specialist", 15)],
    5: [("scryer_grunt", 30), ("scryer_hitman", 15), ("scryer_specialist", 15)],
    6: [("scryer_grunt", 20), ("scryer_hitman", 15), ("scryer_specialist", 15)],
}

METH_LAB_ALDOR_TABLES: dict[int, list[tuple[str, int]]] = {
    0: [("aldor_grunt", 50), ("aldor_hitman", 5),  ("aldor_specialist", 5)],
    1: [("aldor_grunt", 60), ("aldor_hitman", 10), ("aldor_specialist", 10)],
    2: [("aldor_grunt", 40), ("aldor_hitman", 10), ("aldor_specialist", 5)],
    3: [("aldor_grunt", 40), ("aldor_hitman", 15), ("aldor_specialist", 10)],
    4: [("aldor_grunt", 40), ("aldor_hitman", 20), ("aldor_specialist", 15)],
    5: [("aldor_grunt", 30), ("aldor_hitman", 15), ("aldor_specialist", 15)],
    6: [("aldor_grunt", 20), ("aldor_hitman", 15), ("aldor_specialist", 15)],
}

METH_LAB_NEUTRAL_TABLES: dict[int, list[tuple[str, int]]] = {
    0: [
        ("rad_rat",         20),
        ("covid_26",        36),
        ("stray_dog",       18),
        ("toxic_slug",      12),
        ("chemist",          8),
        ("purger",           5),
        ("convertor",        3),
        ("mutator",          3),
        ("uranium_beetle",   3),
        ("dea_agent",        5),
    ],
    1: [
        ("rad_rat",         20),
        ("covid_26",        36),
        ("stray_dog",       18),
        ("toxic_slug",      12),
        ("chemist",          8),
        ("purger",           5),
        ("convertor",        3),
        ("mutator",          3),
        ("uranium_beetle",   3),
        ("dea_agent",        5),
    ],
    2: [
        ("rad_rat",         18),
        ("covid_26",        30),
        ("stray_dog",       15),
        ("toxic_slug",      10),
        ("chemist",         10),
        ("purger",           8),
        ("convertor",        6),
        ("mutator",          5),
        ("uranium_beetle",   5),
        ("sludge_amalgam",   2),
        ("rad_rats_nest",    2),
        ("ice_agent",        5),
        ("dea_agent",        8),
    ],
    3: [
        ("rad_rat",         18),
        ("covid_26",        30),
        ("stray_dog",       15),
        ("toxic_slug",      10),
        ("chemist",         10),
        ("purger",          10),
        ("convertor",        8),
        ("mutator",          5),
        ("uranium_beetle",   5),
        ("sludge_amalgam",   3),
        ("rad_rats_nest",    3),
        ("ice_agent",        5),
        ("dea_agent",       10),
    ],
    4: [
        ("rad_rat",         15),
        ("covid_26",        24),
        ("stray_dog",       12),
        ("toxic_slug",      10),
        ("chemist",         10),
        ("purger",          12),
        ("convertor",       10),
        ("mutator",          8),
        ("uranium_beetle",   8),
        ("sludge_amalgam",   5),
        ("rad_rats_nest",    5),
        ("ice_agent",        8),
        ("dea_agent",       10),
    ],
    5: [
        ("rad_rat",         12),
        ("covid_26",        24),
        ("stray_dog",       10),
        ("toxic_slug",      10),
        ("chemist",         10),
        ("purger",          12),
        ("convertor",       10),
        ("mutator",          8),
        ("uranium_beetle",   8),
        ("sludge_amalgam",   6),
        ("rad_rats_nest",    5),
        ("ice_agent",       10),
        ("dea_agent",       10),
    ],
    6: [
        ("rad_rat",         10),
        ("covid_26",        20),
        ("stray_dog",        8),
        ("toxic_slug",       8),
        ("chemist",         10),
        ("purger",          12),
        ("convertor",       10),
        ("mutator",         10),
        ("uranium_beetle",  10),
        ("sludge_amalgam",   8),
        ("rad_rats_nest",    5),
        ("ice_agent",       10),
        ("dea_agent",       15),
    ],
}

_METH_LAB_FACTION_TABLES = {
    "scryer":  METH_LAB_SCRYER_TABLES,
    "aldor":   METH_LAB_ALDOR_TABLES,
    "neutral": METH_LAB_NEUTRAL_TABLES,
}


def get_meth_lab_faction_table(faction: str, floor_num: int) -> list[tuple[str, int]]:
    """Return the meth lab spawn table for a faction + floor, with floor fallback."""
    tables = _METH_LAB_FACTION_TABLES.get(faction, {})
    if not tables:
        return []
    if floor_num in tables:
        return tables[floor_num]
    # Fall back to highest defined floor <= floor_num
    valid = [f for f in tables if f <= floor_num]
    if valid:
        return tables[max(valid)]
    return tables[min(tables.keys())]


def get_spawn_table(zone: str, floor_num: int) -> list[tuple[str, int]]:
    """Return the spawn table for a zone + floor, falling back to the highest defined floor."""
    zone_floors = ZONE_SPAWN_TABLES.get(zone, {})
    if not zone_floors:
        return []
    if floor_num in zone_floors:
        return zone_floors[floor_num]
    # Fall back to highest defined floor (future-proofs extra floors)
    return zone_floors[max(zone_floors.keys())]


def get_hallway_spawn_table(zone: str, floor_num: int) -> list[tuple[str, int]]:
    """Return the hallway spawn table for a zone + floor, falling back to the highest defined floor."""
    zone_floors = ZONE_HALLWAY_SPAWN_TABLES.get(zone, {})
    if not zone_floors:
        return []
    if floor_num in zone_floors:
        return zone_floors[floor_num]
    return zone_floors[max(zone_floors.keys())]


# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP VALIDATION — call once when the game boots
# ══════════════════════════════════════════════════════════════════════════════

def validate_registry() -> None:
    """
    Validates cross-references and invariants that can't be checked inside
    a single dataclass __post_init__ (because the full registry doesn't
    exist yet at that point).

    Call once at startup.  Raises ValueError with ALL problems collected
    so you can fix them in one pass instead of whack-a-mole.

    Checks performed
    ----------------
    - Every spawn_with escort type exists in MONSTER_REGISTRY.
    - Every enemy key in every zone table exists in MONSTER_REGISTRY.
    - Zone table weights are positive.
    - No duplicate enemy keys within a single zone table.
    """
    errors: list[str] = []

    # ── Escort references ──
    for key, tmpl in MONSTER_REGISTRY.items():
        for escort in tmpl.spawn_with:
            if escort.type not in MONSTER_REGISTRY:
                errors.append(
                    f"  [{key}] spawn_with references unknown type '{escort.type}'"
                )
        # ── Death split references ──
        if tmpl.death_split_type and tmpl.death_split_type not in MONSTER_REGISTRY:
            errors.append(
                f"  [{key}] death_split_type references unknown type '{tmpl.death_split_type}'"
            )

    # ── Zone table references (per-floor tables) ──
    for zone, floor_tables in ZONE_SPAWN_TABLES.items():
        for floor_num, table in floor_tables.items():
            seen_keys: set[str] = set()
            for enemy_key, weight in table:
                if enemy_key not in MONSTER_REGISTRY:
                    errors.append(
                        f"  zone '{zone}' floor {floor_num}: references unknown enemy '{enemy_key}'"
                    )
                if weight <= 0:
                    errors.append(
                        f"  zone '{zone}' floor {floor_num}: weight for '{enemy_key}' must be > 0, got {weight}"
                    )
                if enemy_key in seen_keys:
                    errors.append(
                        f"  zone '{zone}' floor {floor_num}: duplicate entry for '{enemy_key}'"
                    )
                seen_keys.add(enemy_key)

    # ── Meth Lab faction table references ──
    for label, faction_tables in _METH_LAB_FACTION_TABLES.items():
        for floor_num, table in faction_tables.items():
            seen_keys = set()
            for enemy_key, weight in table:
                if enemy_key not in MONSTER_REGISTRY:
                    errors.append(
                        f"  meth_lab faction '{label}' floor {floor_num}: references unknown enemy '{enemy_key}'"
                    )
                if weight <= 0:
                    errors.append(
                        f"  meth_lab faction '{label}' floor {floor_num}: weight for '{enemy_key}' must be > 0, got {weight}"
                    )
                if enemy_key in seen_keys:
                    errors.append(
                        f"  meth_lab faction '{label}' floor {floor_num}: duplicate entry for '{enemy_key}'"
                    )
                seen_keys.add(enemy_key)

    if errors:
        raise ValueError(
            "Enemy registry validation failed:\n" + "\n".join(errors)
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY — turns a template + coordinates into a live Entity
# ══════════════════════════════════════════════════════════════════════════════

def create_enemy(enemy_type: str, x: int, y: int):
    """
    Instantiate a fully-configured Entity from a registry template.

    Every individual is randomly rolled within its template's ranges so two
    monsters of the same type can have noticeably different stats.

    The Entity constructor interface is UNCHANGED — this function serializes
    dataclass fields back into the dicts/primitives Entity already expects.
    """
    from entity import Entity          # deferred to avoid circular import

    tmpl = MONSTER_REGISTRY[enemy_type]

    # ── Roll the six base stats ──
    base_stats = {
        "constitution":  random.randint(*tmpl.constitution),
        "strength":      random.randint(*tmpl.strength),
        "street_smarts": random.randint(*tmpl.street_smarts),
        "book_smarts":   random.randint(*tmpl.book_smarts),
        "tolerance":     random.randint(*tmpl.tolerance),
        "swagger":       random.randint(*tmpl.swagger),
    }

    # ── Derive combat stats from base stats ──
    rolled_con = base_stats["constitution"]
    rolled_str = base_stats["strength"]
    rolled_ss  = base_stats["street_smarts"]
    rolled_bs  = base_stats["book_smarts"]
    rolled_swg = base_stats["swagger"]

    hp     = tmpl.base_hp + rolled_con * 5
    damage = random.randint(*tmpl.base_damage) + rolled_str
    crit_chance        = rolled_ss * 3
    bonus_spell_damage = rolled_bs
    bonus_ranged_damage = rolled_swg
    swagger_defense    = int(rolled_swg / 3)

    gender = "male" if random.random() < tmpl.male_chance else "female"
    cash   = random.randint(*tmpl.cash_drop)

    # ── Serialize special attacks (dataclass → dict for Entity) ──
    special_attacks = []
    for sa in tmpl.special_attacks:
        sa_dict = {
            "name":        sa.name,
            "chance":      sa.chance,
            "damage_mult": sa.damage_mult,
        }
        # Randomize damage_mult marked None at spawn time
        if sa.damage_mult is None:
            sa_dict["damage_mult"] = round(random.uniform(2.0, 3.0), 2)
        # Serialize nested on-hit effect
        if sa.on_hit_effect is not None:
            sa_dict["on_hit_effect"] = {
                "name":     sa.on_hit_effect.name,
                "kind":     sa.on_hit_effect.kind.value,
                "amount":   sa.on_hit_effect.amount,
                "duration": sa.on_hit_effect.duration,
            }
        special_attacks.append(sa_dict)

    # ── Serialize on-hit effects (dataclass → dict for Entity) ──
    on_hit_effects = []
    for eff in tmpl.on_hit_effects:
        on_hit_effects.append({
            "name":     eff.name,
            "kind":     eff.kind.value,
            "chance":   eff.chance,
            "amount":   eff.amount,
            "duration": eff.duration,
        })

    entity = Entity(
        x=x,
        y=y,
        char=tmpl.char,
        color=tmpl.color,
        name=tmpl.name,
        entity_type="monster",
        blocks_movement=True,
        hp=hp,
        power=damage,
        defense=tmpl.defense + swagger_defense,
        enemy_type=enemy_type,
        gender=gender,
        base_stats=base_stats,
        ai_type=tmpl.ai.value,         # AIType enum → string for Entity
        sight_radius=tmpl.sight_radius,
        speed=tmpl.speed,
        is_chasing=False,
        special_attacks=special_attacks,
        on_hit_effects=on_hit_effects,
        cash_drop=cash,
        dodge_chance=tmpl.dodge_chance,
        crit_chance=crit_chance,
        bonus_spell_damage=bonus_spell_damage,
        bonus_ranged_damage=bonus_ranged_damage,
        move_cost=tmpl.move_cost,
        attack_cost=tmpl.attack_cost,
        death_drop_chance=tmpl.death_drop_chance,
        death_drop_table=list(tmpl.death_drop_table),
        death_drop_quantity=tmpl.death_drop_quantity,
        faction=tmpl.faction,
        blink_charges=tmpl.blink_charges,
        ranged_attack=dict(tmpl.ranged_attack) if tmpl.ranged_attack else None,
        spawner_type=tmpl.spawner_type,
        max_spawned=tmpl.max_spawned,
        death_split_type=tmpl.death_split_type,
        death_split_count=tmpl.death_split_count,
        death_creep_radius=tmpl.death_creep_radius,
        death_creep_duration=tmpl.death_creep_duration,
        death_creep_tox=tmpl.death_creep_tox,
        leaves_trail=dict(tmpl.leaves_trail) if tmpl.leaves_trail else None,
    )
    if tmpl.wander_idle_chance > 0:
        entity.wander_idle_chance = tmpl.wander_idle_chance
    return entity
