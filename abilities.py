"""
Ability system — definitions, instances, and registry.

Design (scalable to 100+ abilities):
- AbilityDef: declarative, data-only record; all logic lives in the execute callable.
- AbilityInstance: mutable runtime state (charge tracking) bound to one player-owned ability.
- execute(engine) is called for SELF-target abilities.
- execute(engine, tx, ty) is called for targeted abilities.
- Adding a new ability: add an AbilityDef entry to ABILITY_REGISTRY; nothing else changes.

Abilities are NOT granted at spawn — the player starts with none.
Abilities are granted by items (via engine.grant_ability) or by skills.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class TargetType(Enum):
    """How an ability selects its target."""
    SELF = "self"                   # No targeting; fires immediately on the player tile.
    SINGLE_ENEMY_LOS = "single_los" # Aim cursor at one enemy in FOV; fires on confirm.
    LINE_FROM_PLAYER = "line"       # Fire in a direction; hits all enemies along the ray.


class ChargeType(Enum):
    """How usage of an ability is limited."""
    INFINITE = "infinite"    # Unlimited uses.
    PER_FLOOR = "per_floor"  # max_charges uses per floor; resets on floor change.
    TOTAL = "total"          # max_charges uses total; permanently consumed.
    ONCE = "once"            # Exactly 1 use ever (shorthand for TOTAL + max_charges=1).


@dataclass
class AbilityDef:
    """Immutable definition of an ability (lives in ABILITY_REGISTRY)."""
    ability_id: str
    name: str
    description: str
    char: str
    color: tuple
    target_type: TargetType
    charge_type: ChargeType
    max_charges: int = 0           # Used by PER_FLOOR / TOTAL. Ignored for INFINITE / ONCE.
    tags: frozenset[str] = field(default_factory=frozenset)
    execute: Callable = field(default=None, repr=False)


class AbilityInstance:
    """Mutable runtime state for one ability the player possesses."""

    def __init__(self, ability_id: str, defn: AbilityDef):
        self.ability_id = ability_id
        self._init_charges(defn)

    def _init_charges(self, defn: AbilityDef):
        if defn.charge_type == ChargeType.INFINITE:
            self.charges_remaining = -1        # -1 means unlimited
            self.floor_charges_remaining = -1
        elif defn.charge_type == ChargeType.PER_FLOOR:
            self.charges_remaining = -1
            self.floor_charges_remaining = defn.max_charges
        elif defn.charge_type == ChargeType.TOTAL:
            self.charges_remaining = defn.max_charges
            self.floor_charges_remaining = -1
        elif defn.charge_type == ChargeType.ONCE:
            self.charges_remaining = 1
            self.floor_charges_remaining = -1

    def can_use(self) -> bool:
        """True if at least one use remains."""
        if self.charges_remaining == 0:
            return False
        if self.floor_charges_remaining == 0:
            return False
        return True

    def consume(self):
        """Spend one charge."""
        if self.charges_remaining > 0:
            self.charges_remaining -= 1
        if self.floor_charges_remaining > 0:
            self.floor_charges_remaining -= 1

    def reset_floor(self, defn: AbilityDef):
        """Called when the player descends to a new floor."""
        if defn.charge_type == ChargeType.PER_FLOOR:
            self.floor_charges_remaining = defn.max_charges

    def charge_display(self, defn: AbilityDef) -> str:
        """Human-readable charge string for the UI."""
        if defn.charge_type == ChargeType.INFINITE:
            return "inf"
        if defn.charge_type == ChargeType.PER_FLOOR:
            return f"{self.floor_charges_remaining}/{defn.max_charges} /fl"
        if defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
            return f"{self.charges_remaining} left"
        return "?"


# ---------------------------------------------------------------------------
# Ability implementations
# ---------------------------------------------------------------------------

def _execute_warp(engine) -> bool:
    """
    Teleport the player to a random open, unoccupied floor tile on the current floor.
    The destination tile must not be a wall, a monster, or terrain-blocked.
    If the player lands on an item it is picked up automatically.
    """
    dungeon = engine.dungeon

    # Build set of tiles blocked by living monsters
    monster_tiles = {
        (e.x, e.y)
        for e in dungeon.entities
        if e.entity_type == "monster" and e.alive
    }

    candidates = []
    for y in range(dungeon.height):
        for x in range(dungeon.width):
            if dungeon.is_terrain_blocked(x, y):
                continue
            if (x, y) in monster_tiles:
                continue
            if (x, y) == (engine.player.x, engine.player.y):
                continue
            candidates.append((x, y))

    if not candidates:
        engine.messages.append("Nowhere to warp to!")
        return False

    tx, ty = random.choice(candidates)
    dungeon.move_entity(engine.player, tx, ty)
    dungeon.compute_fov(engine.player.x, engine.player.y, engine.fov_radius)
    engine.messages.append("Reality folds — you blink out and reappear elsewhere.")
    engine._pickup_items_at(tx, ty)
    return True


# ---------------------------------------------------------------------------
# Spell execute callables
# ---------------------------------------------------------------------------

def _execute_dimension_door(engine) -> bool:
    engine._enter_spell_targeting({"type": "dimension_door"})
    return False  # charge consumed when spell fires in _execute_spell_at


def _execute_chain_lightning(engine) -> bool:
    # Each charge always fires the full 4-bounce spec; charges stack from any source.
    engine._enter_spell_targeting({"type": "chain_lightning", "total_hits": 4})
    return False


def _execute_ray_of_frost(engine) -> bool:
    # count=1: one ray per charge
    engine._enter_spell_targeting({"type": "ray_of_frost", "count": 1})
    return False


def _execute_firebolt(engine) -> bool:
    engine._enter_spell_targeting({"type": "firebolt", "count": 1})
    return False


def _execute_arcane_missile(engine) -> bool:
    engine._enter_spell_targeting({"type": "arcane_missile", "count": 1})
    return False


# ---------------------------------------------------------------------------
# Registry — add new abilities here; nothing else in the codebase changes.
# ---------------------------------------------------------------------------

ABILITY_REGISTRY: dict[str, AbilityDef] = {
    "warp": AbilityDef(
        ability_id="warp",
        name="Warp",
        description="Teleport to a random open tile. Items at the landing spot are auto-picked up.",
        char="W",
        color=(100, 140, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "movement", "teleport", "self_cast", "active"}),
        execute=_execute_warp,
    ),
    "dimension_door": AbilityDef(
        ability_id="dimension_door",
        name="Dimension Door",
        description="Blink to any explored, unoccupied tile. Picks up items on landing.",
        char="D",
        color=(180, 130, 255),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "movement", "teleport", "targeted", "arcane", "active"}),
        execute=_execute_dimension_door,
    ),
    "chain_lightning": AbilityDef(
        ability_id="chain_lightning",
        name="Chain Lightning",
        description="Strikes target then bounces 3×. Dmg: 5 + Street-Smarts + Tolerance. Charges stack from any source.",
        char="L",
        color=(255, 240, 80),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "lightning", "damage", "chain", "targeted", "active"}),
        execute=_execute_chain_lightning,
    ),
    "ray_of_frost": AbilityDef(
        ability_id="ray_of_frost",
        name="Ray of Frost",
        description="Fire a 10-tile frost ray in aimed direction. Dmg: 12 + Book-Smarts.",
        char="R",
        color=(100, 200, 255),
        target_type=TargetType.LINE_FROM_PLAYER,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "frost", "cold", "damage", "line", "active"}),
        execute=_execute_ray_of_frost,
    ),
    "firebolt": AbilityDef(
        ability_id="firebolt",
        name="Firebolt",
        description="Projectile hits first enemy in path. Dmg: 10 + Book-Smarts + Ignite.",
        char="F",
        color=(255, 140, 40),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "fire", "damage", "targeted", "ignite", "active"}),
        execute=_execute_firebolt,
    ),
    "arcane_missile": AbilityDef(
        ability_id="arcane_missile",
        name="Arcane Missile",
        description="Hits any visible enemy. Dmg: ceil(8 + Book-Smarts / 2).",
        char="M",
        color=(200, 150, 255),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "arcane", "damage", "targeted", "active"}),
        execute=_execute_arcane_missile,
    ),
}


# ---------------------------------------------------------------------------
# Tag query utilities
# ---------------------------------------------------------------------------

def has_tag(ability_id: str, tag: str) -> bool:
    """Return True if the ability with the given ID has the specified tag."""
    defn = ABILITY_REGISTRY.get(ability_id)
    return defn is not None and tag in defn.tags


def abilities_with_tag(tag: str) -> list[AbilityDef]:
    """Return all AbilityDef entries that have the specified tag."""
    return [defn for defn in ABILITY_REGISTRY.values() if tag in defn.tags]
