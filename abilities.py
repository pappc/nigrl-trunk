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
    AOE_CIRCLE = "aoe_circle"       # Circular AoE around a target tile.
    ADJACENT = "adjacent"           # Quick-select an adjacent enemy (auto if only 1).
    ADJACENT_TILE = "adjacent_tile" # Press a directional key to target an adjacent tile (any non-wall).


class ChargeType(Enum):
    """How usage of an ability is limited."""
    INFINITE = "infinite"    # Unlimited uses.
    PER_FLOOR = "per_floor"  # max_charges uses per floor; resets on floor change.
    TOTAL = "total"          # max_charges uses total; permanently consumed.
    ONCE = "once"            # Exactly 1 use ever (shorthand for TOTAL + max_charges=1).
    FLOOR_ONLY = "floor_only" # max_charges uses per floor; resets to 0 on floor change (consumed permanently).


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
    is_spell: bool = False         # If True, this is a magic spell (affected by Wizard Mind-Bomb bonus)
    max_range: float = 0.0         # 0.0 = unlimited; Manhattan tile distance from player
    aoe_radius: float = 0.0        # For AOE_CIRCLE target type (future use)
    execute_at: Callable = field(default=None, repr=False)  # (engine, tx, ty) -> bool; True = fired (consume charge)
    validate: Callable = field(default=None, repr=False)    # (engine, tx, ty) -> str|None; None = ok, str = error msg
    get_affected_tiles: Callable = field(default=None, repr=False)  # (engine, tx, ty) -> list[tuple[int,int]]; None = single-target default


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
        elif defn.charge_type == ChargeType.FLOOR_ONLY:
            self.charges_remaining = -1
            self.floor_charges_remaining = defn.max_charges

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
        elif defn.charge_type == ChargeType.FLOOR_ONLY:
            self.floor_charges_remaining = 0  # Consumed permanently, resets to 0

    def charge_display(self, defn: AbilityDef) -> str:
        """Human-readable charge string for the UI."""
        if defn.charge_type == ChargeType.INFINITE:
            return "inf"
        if defn.charge_type == ChargeType.PER_FLOOR:
            return f"{self.floor_charges_remaining}/{defn.max_charges} /fl"
        if defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
            return f"{self.charges_remaining} left"
        if defn.charge_type == ChargeType.FLOOR_ONLY:
            return f"{self.floor_charges_remaining} /fl"
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
    engine._compute_fov()
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


def _execute_breath_fire(engine) -> bool:
    """Enter cone targeting mode for breath fire spell."""
    engine._enter_spell_targeting({"type": "breath_fire", "damage": 20})
    return False


# ---------------------------------------------------------------------------
# Per-ability execute_at functions (called when player confirms target)
# Each takes (engine, tx, ty) and returns True if the spell fired (charge consumed),
# False if it failed validation or needs to stay in targeting mode.
# ---------------------------------------------------------------------------

def _execute_at_dimension_door(engine, tx: int, ty: int) -> bool:
    return engine._spell_dimension_door(tx, ty)


def _execute_at_chain_lightning(engine, tx: int, ty: int) -> bool:
    return engine._spell_chain_lightning(tx, ty, total_hits=4)


def _execute_at_ray_of_frost(engine, tx: int, ty: int) -> bool:
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        engine.messages.append("Ray of Frost: aim your cursor away from yourself!")
        return False
    unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
    unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0
    engine._spell_ray_of_frost(unit_dx, unit_dy)
    return True


def _execute_at_firebolt(engine, tx: int, ty: int) -> bool:
    return engine._spell_firebolt(tx, ty)


def _execute_at_arcane_missile(engine, tx: int, ty: int) -> bool:
    return engine._spell_arcane_missile(tx, ty)


def _execute_at_breath_fire(engine, tx: int, ty: int) -> bool:
    return engine._spell_breath_fire(tx, ty)


def _execute_zap(engine) -> bool:
    engine._enter_spell_targeting({"type": "zap"})
    return False


def _execute_at_zap(engine, tx: int, ty: int) -> bool:
    return engine._spell_zap(tx, ty)


def _execute_corn_dog(engine) -> bool:
    engine._enter_spell_targeting({"type": "corn_dog"})
    return False


def _execute_at_corn_dog(engine, tx: int, ty: int) -> bool:
    return engine._spell_corn_dog(tx, ty)


def _execute_lesser_cloudkill(engine) -> bool:
    engine._enter_spell_targeting({"type": "lesser_cloudkill"})
    return False


def _execute_at_lesser_cloudkill(engine, tx: int, ty: int) -> bool:
    return engine._spell_lesser_cloudkill(tx, ty)


def _execute_pry(engine) -> bool:
    engine._enter_spell_targeting({"type": "pry"})
    return False


def _execute_at_pry(engine, tx: int, ty: int) -> bool:
    return engine._spell_pry(tx, ty)


def _execute_at_bash(engine, tx: int, ty: int) -> bool:
    """Bash an adjacent enemy with a blunt weapon. Always crits, knocks back 4 tiles.
    Collision with another monster: both take STR damage and knockback stops.
    Collision with wall: enemy takes STR damage.
    """
    from items import ITEM_DEFS as _ITEM_DEFS
    weapon = engine.equipment.get("weapon")
    if not weapon:
        engine.messages.append("Bash: you need a blunt weapon equipped!")
        return False
    wdefn = _ITEM_DEFS.get(weapon.item_id, {})
    if wdefn.get("weapon_type") != "blunt":
        engine.messages.append("Bash: you need a blunt weapon equipped!")
        return False

    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Bash: no enemy there.")
        return False

    # Always-crit damage: weapon attack * crit_multiplier
    atk_power = engine._compute_player_attack_power()
    def_defense = target.defense
    damage = max(1, atk_power - def_defense) * engine.crit_multiplier
    target.take_damage(damage)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"BASH! CRITICAL! {target.name} takes {damage} dmg! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)

    if target.alive:
        # Knockback: direction straight away from player
        dx = tx - engine.player.x
        dy = ty - engine.player.y
        if dx != 0:
            dx = dx // abs(dx)
        if dy != 0:
            dy = dy // abs(dy)

        str_dmg = engine.player_stats.effective_strength
        cx, cy = tx, ty
        for _ in range(4):
            nx, ny = cx + dx, cy + dy
            # Wall collision
            if engine.dungeon.is_terrain_blocked(nx, ny):
                target.take_damage(str_dmg)
                hp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
                engine.messages.append(
                    f"{target.name} slams into a wall! -{str_dmg} dmg ({hp})"
                )
                if not target.alive:
                    engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
                break
            # Monster blocker — stop 1 tile before it
            blocker = next(
                (e for e in engine.dungeon.get_entities_at(nx, ny)
                 if e.entity_type == "monster" and e.alive),
                None,
            )
            if blocker:
                target.take_damage(str_dmg)
                blocker.take_damage(str_dmg)
                hp_t = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
                hp_b = f"{blocker.hp}/{blocker.max_hp}" if blocker.alive else "dead"
                engine.messages.append(
                    f"{target.name} crashes into {blocker.name}! Both take {str_dmg} dmg. "
                    f"({hp_t} / {hp_b})"
                )
                if not target.alive:
                    engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
                if not blocker.alive:
                    engine.event_bus.emit("entity_died", entity=blocker, killer=engine.player)
                break
            # Free tile — slide the target
            engine.dungeon.move_entity(target, nx, ny)
            cx, cy = nx, ny

    engine.ability_cooldowns["bash"] = 10
    return True


def _execute_at_force_push(engine, tx: int, ty: int) -> bool:
    """Push an adjacent enemy 3 tiles away from the player in a straight line.
    Collisions with walls or the player deal 3 + BkSmt//2 damage to the pushed unit.
    Collisions with another monster deal that damage to both.
    """
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Force Push: no enemy there.")
        return False

    bksmt = engine.player_stats.effective_book_smarts
    col_dmg = 3 + bksmt // 2

    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx != 0:
        dx = dx // abs(dx)
    if dy != 0:
        dy = dy // abs(dy)

    engine.messages.append(f"Force Push! {target.name} is flung backward!")
    pushed = 0
    cx, cy = tx, ty
    for _ in range(3):
        nx, ny = cx + dx, cy + dy
        # Wall collision
        if engine.dungeon.is_terrain_blocked(nx, ny):
            target.take_damage(col_dmg)
            hp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
            engine.messages.append(f"{target.name} slams into a wall! -{col_dmg} dmg ({hp})")
            if not target.alive:
                engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
            break
        # Player blocker
        if (nx, ny) == (engine.player.x, engine.player.y):
            target.take_damage(col_dmg)
            hp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
            engine.messages.append(f"{target.name} slams into you! -{col_dmg} dmg ({hp})")
            if not target.alive:
                engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
            break
        # Monster blocker
        blocker = next(
            (e for e in engine.dungeon.get_entities_at(nx, ny)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if blocker:
            target.take_damage(col_dmg)
            blocker.take_damage(col_dmg)
            hp_t = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
            hp_b = f"{blocker.hp}/{blocker.max_hp}" if blocker.alive else "dead"
            engine.messages.append(
                f"{target.name} crashes into {blocker.name}! Both take {col_dmg} dmg. "
                f"({hp_t} / {hp_b})"
            )
            if not target.alive:
                engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
            if not blocker.alive:
                engine.event_bus.emit("entity_died", entity=blocker, killer=engine.player)
            break
        # Free tile — slide the target
        engine.dungeon.move_entity(target, nx, ny)
        cx, cy = nx, ny
        pushed += 1

    engine.ability_cooldowns["force_push"] = 20
    return True


def _execute_at_place_fire(engine, tx: int, ty: int) -> bool:
    """Spawn a fire hazard at the chosen adjacent tile."""
    from hazards import create_fire
    fire = create_fire(tx, ty)
    engine.dungeon.add_entity(fire)
    engine.messages.append("You strike your lighter — FOOM! Fire erupts!")
    return True


def _dash_execute(engine) -> bool:
    """Enter cursor targeting mode for the Dash ability."""
    from menu_state import MenuState
    engine.targeting_cursor = [engine.player.x, engine.player.y]
    engine.targeting_spell = {"type": "ability_cursor"}
    engine.menu_state = MenuState.TARGETING
    engine.messages.append("Dash: choose destination (arrow keys, Enter). [Esc] cancel.")
    return False


def _dash_execute_at(engine, tx: int, ty: int) -> bool:
    """Teleport the player to (tx, ty) if within Chebyshev range 2 and passable."""
    px, py = engine.player.x, engine.player.y
    dist = max(abs(tx - px), abs(ty - py))
    if dist < 1:
        engine.messages.append("Dash: you're already there!")
        return False
    if dist > 2:
        engine.messages.append("Dash: too far! Max 2 tiles.")
        return False
    if engine.dungeon.is_blocked(tx, ty):
        engine.messages.append("Dash: that tile is blocked!")
        return False
    engine.dungeon.move_entity(engine.player, tx, ty)
    engine._compute_fov()
    engine.messages.append("You dash!")
    engine.ability_cooldowns["dash"] = 15
    return True


def _execute_at_ignite_spell(engine, tx: int, ty: int) -> bool:
    """Apply 2 ignite stacks to the enemy at (tx, ty)."""
    import effects as _effects
    target = engine.dungeon.get_blocking_entity_at(tx, ty)
    if target is None or not target.alive or target is engine.player:
        engine.messages.append("Ignite: no target there!")
        return False
    for _ in range(2):
        _effects.apply_effect(target, engine, "ignite", duration=engine._player_ignite_duration(), stacks=1, silent=True)
    ign_eff = next((e for e in target.status_effects if getattr(e, "id", "") == "ignite"), None)
    stacks = ign_eff.stacks if ign_eff else 2
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(f"You ignite {target.name}! (x{stacks}) ({hp_disp})")
    return True


def _execute_at_black_eye_slap(engine, tx: int, ty: int) -> bool:
    """Bitch Slap an adjacent enemy. Dmg = STR; vs. females: 10 + 2*STR. Applies Black Eye debuff."""
    import effects
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Bitch Slap: no enemy there.")
        return False

    strength = engine.player_stats.effective_strength
    is_female = getattr(target, "gender", None) == "female"
    if is_female:
        damage = 10 + 2 * strength
    else:
        damage = max(1, strength - target.defense)

    target.take_damage(damage)
    effects.apply_effect(target, engine, "black_eye", duration=2, silent=True)

    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    gender_str = " (FEMALE BONUS!)" if is_female else ""
    engine.messages.append(
        f"BITCH SLAP!{gender_str} {target.name} takes {damage} dmg and gets a black eye! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)

    engine.ability_cooldowns["black_eye_slap"] = 25
    return True


def _execute_at_gouge(engine, tx: int, ty: int) -> bool:
    """Gouge an adjacent enemy. Requires stabbing weapon. Dmg = effective StSmt. Applies Gouge debuff."""
    from items import ITEM_DEFS as _ITEM_DEFS
    weapon = engine.equipment.get("weapon")
    if not weapon:
        engine.messages.append("Gouge: you need a stabbing weapon equipped!")
        return False
    wdefn = _ITEM_DEFS.get(weapon.item_id, {})
    if wdefn.get("weapon_type") != "stabbing":
        engine.messages.append("Gouge: you need a stabbing weapon equipped!")
        return False
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Gouge: no enemy there.")
        return False
    import effects
    stsmt = engine.player_stats.effective_street_smarts
    damage = max(1, stsmt - target.defense)
    target.take_damage(damage)
    effects.apply_effect(target, engine, "gouge", duration=5, silent=True)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Gouge! {target.name} takes {damage} dmg and is gouged for 5 turns! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    engine.ability_cooldowns["gouge"] = 7
    return True


def _execute_at_pickpocket(engine, tx: int, ty: int) -> bool:
    """Pickpocket an adjacent enemy. Dmg = StSmt/2; player gains $25. 15-turn cooldown."""
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Pickpocket: no enemy there.")
        return False
    stsmt = engine.player_stats.effective_street_smarts
    damage = max(1, stsmt // 2 - target.defense)
    target.take_damage(damage)
    engine.cash += 25
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Pickpocket! {target.name} takes {damage} dmg. You snag $25! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    engine.ability_cooldowns["pickpocket"] = 15
    return True


def _execute_fry_shot(engine) -> bool:
    """Enter targeting mode for Fry Shot."""
    engine._enter_spell_targeting({"type": "fry_shot"})
    return False


def _execute_at_fry_shot(engine, tx: int, ty: int) -> bool:
    """Hurl hot grease at an enemy. Dmg: CON + 2 - DEF. Applies 3 Greasy stacks."""
    import effects
    target = engine.dungeon.get_blocking_entity_at(tx, ty)
    if target is None or not target.alive or target is engine.player:
        engine.messages.append("Fry Shot: no target there!")
        return False
    con = engine.player_stats.effective_constitution
    damage = max(1, con + 2 - target.defense)
    target.take_damage(damage)
    for _ in range(3):
        effects.apply_effect(target, engine, "greasy", duration=20, stacks=1, silent=True)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(f"Fry Shot! {target.name} takes {damage} dmg and is Greasy x3! ({hp_disp})")
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    engine.ability_cooldowns["fry_shot"] = 15
    return True


def _execute_throw_bottle(engine) -> bool:
    engine._enter_spell_targeting({"type": "throw_bottle"})
    return False


_DRINK_BUFF_IDS = frozenset({"forty_oz", "malt_liquor", "wizard_mind_bomb", "hennessy", "peace_of_mind"})


def _execute_slow_metabolism(engine) -> bool:
    """Double the duration of all currently active drink buffs on the player."""
    doubled = []
    for eff in engine.player.status_effects:
        if getattr(eff, 'id', '') in _DRINK_BUFF_IDS and eff.category == "buff":
            eff.duration *= 2
            doubled.append(eff.display_name)
    if doubled:
        engine.messages.append([
            ("Slow Metabolism! ", (100, 200, 255)),
            (f"Doubled: {', '.join(doubled)}", (200, 255, 200)),
        ])
    else:
        engine.messages.append("Slow Metabolism: no active drink buffs to extend.")
    return True


def _execute_at_throw_bottle(engine, tx: int, ty: int) -> bool:
    """Throw a bottle at a target. Damage = 3 * Alcoholism level + STR / 2."""
    dungeon = engine.dungeon
    target = dungeon.get_blocking_entity_at(tx, ty)
    if target is None or not target.alive or target.entity_type != "monster":
        engine.messages.append("No target there!")
        return False
    alc_level = engine.skills.get("Alcoholism").level
    strength = engine.player_stats.effective_strength
    damage = 3 * alc_level + strength // 2
    actual = max(1, damage - target.defense)
    target.take_damage(actual)
    engine.messages.append([
        ("You hurl a bottle at ", (200, 200, 200)),
        (target.name, target.color),
        (f" for {actual} damage!", (200, 200, 200)),
    ])
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    return True


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
        is_spell=True,
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
        is_spell=True,
        max_range=0.0,
        execute_at=_execute_at_dimension_door,
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
        is_spell=True,
        max_range=10.0,
        execute_at=_execute_at_chain_lightning,
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
        is_spell=True,
        max_range=0.0,
        execute_at=_execute_at_ray_of_frost,
        get_affected_tiles=lambda engine, tx, ty: engine._get_ray_of_frost_affected_tiles(tx, ty),
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
        is_spell=True,
        max_range=12.0,
        execute_at=_execute_at_firebolt,
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
        is_spell=True,
        max_range=0.0,
        execute_at=_execute_at_arcane_missile,
    ),
    "breath_fire": AbilityDef(
        ability_id="breath_fire",
        name="Breathe Fire",
        description="Breathe a cone of fire (5-tile range, 90° spread). Dmg: 20 + Book-Smarts. Charges lost at floor end.",
        char="f",
        color=(255, 100, 0),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.FLOOR_ONLY,
        max_charges=0,
        tags=frozenset({"spell", "fire", "damage", "cone", "active"}),
        execute=_execute_breath_fire,
        is_spell=True,
        max_range=5.0,
        execute_at=_execute_at_breath_fire,
        get_affected_tiles=lambda engine, tx, ty: engine._get_breath_fire_affected_tiles(tx, ty),
    ),
    "zap": AbilityDef(
        ability_id="zap",
        name="Zap!",
        description="Zap a target within 4 tiles. Dmg: 5 + Book-Smarts/2. Applies 1 Shocked stack (max 5, refreshes duration).",
        char="Z",
        color=(255, 255, 80),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "lightning", "damage", "targeted", "active"}),
        execute=_execute_zap,
        is_spell=True,
        max_range=4.0,
        execute_at=_execute_at_zap,
    ),
    "corn_dog": AbilityDef(
        ability_id="corn_dog",
        name="Corn Dog",
        description="Smash an adjacent enemy with a Corn Dog: 5 damage (bypasses defense) + stun for 4 turns.",
        char="C",
        color=(255, 200, 80),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"melee", "damage", "stun", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_corn_dog,
    ),
    "lesser_cloudkill": AbilityDef(
        ability_id="lesser_cloudkill",
        name="Lesser Cloudkill",
        description="Target a 3×3 area (cannot include yourself). Dmg: max(1, 25 - Swagger + BkSmt/2). Applies Lesser Cloudkill: 1 dmg/turn + all stats -1 for 10 turns.",
        char="K",
        color=(100, 200, 80),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "aoe", "damage", "debuff", "targeted", "active"}),
        execute=_execute_lesser_cloudkill,
        is_spell=True,
        max_range=2.0,
        execute_at=_execute_at_lesser_cloudkill,
        get_affected_tiles=lambda engine, tx, ty: engine._get_lesser_cloudkill_affected_tiles(tx, ty),
    ),
    "pry": AbilityDef(
        ability_id="pry",
        name="Pry",
        description="Cripple an adjacent enemy's armor: sets defense to 0 for 10 turns. 50-turn cooldown.",
        char="P",
        color=(180, 130, 80),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"melee", "debuff", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_pry,
    ),
    "throw_bottle": AbilityDef(
        ability_id="throw_bottle",
        name="Throw Bottle",
        description="Hurl a bottle at an enemy. Dmg: 3 * Alcoholism level + STR/2.",
        char="B",
        color=(180, 120, 60),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.TOTAL,
        max_charges=1,
        tags=frozenset({"physical", "damage", "targeted", "active"}),
        execute=_execute_throw_bottle,
        is_spell=False,
        max_range=4.0,
        execute_at=_execute_at_throw_bottle,
    ),
    "bash": AbilityDef(
        ability_id="bash",
        name="Bash",
        description="Smash an adjacent enemy with a blunt weapon. Always crits. Knocks back 4 tiles; wall hit = STR dmg, enemy collision = both take STR dmg. 10-turn cooldown.",
        char="B",
        color=(220, 120, 40),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"attack", "melee", "damage", "knockback", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_bash,
    ),
    "black_eye_slap": AbilityDef(
        ability_id="black_eye_slap",
        name="Bitch Slap",
        description="Slap an adjacent enemy. Dmg: STR (vs females: 10 + 2×STR). Applies Black Eye: stun 2t then wander 10t. 25-turn cooldown.",
        char="S",
        color=(255, 100, 150),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"attack", "melee", "damage", "debuff", "stun", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_black_eye_slap,
    ),
    "gouge": AbilityDef(
        ability_id="gouge",
        name="Gouge",
        description="Stab an adjacent enemy. Dmg: Street-Smarts. Stuns for 5 turns (broken if you attack the target). 7-turn cooldown.",
        char="G",
        color=(200, 60, 60),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"attack", "melee", "damage", "debuff", "stun", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_gouge,
    ),
    "pickpocket": AbilityDef(
        ability_id="pickpocket",
        name="Pickpocket",
        description="Strike an adjacent enemy. Dmg: StSmt/2. Snag $25 from the target. 15-turn cooldown.",
        char="P",
        color=(255, 200, 50),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"attack", "melee", "damage", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_pickpocket,
    ),
    "force_push": AbilityDef(
        ability_id="force_push",
        name="Force Push",
        description="Push an adjacent enemy 3 tiles in a straight line. Collisions: 3 + BkSmt/2 dmg. 2 uses/floor, 20-turn cooldown.",
        char="~",
        color=(150, 100, 255),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=2,
        tags=frozenset({"spell", "push", "targeted", "active"}),
        execute=None,
        is_spell=True,
        max_range=1.5,
        execute_at=_execute_at_force_push,
    ),
    "fry_shot": AbilityDef(
        ability_id="fry_shot",
        name="Fry Shot",
        description="Hurl hot grease at an enemy within 4 tiles. Dmg: CON + 2 - DEF. Applies 3 Greasy stacks. 15-turn cooldown.",
        char="F",
        color=(255, 165, 0),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"ranged", "damage", "debuff", "targeted", "active"}),
        execute=_execute_fry_shot,
        max_range=4.0,
        execute_at=_execute_at_fry_shot,
    ),
    "place_fire": AbilityDef(
        ability_id="place_fire",
        name="Fire!",
        description="Strike your lighter to spawn a fire on an adjacent tile. 1 use per floor.",
        char="^",
        color=(255, 80, 0),
        target_type=TargetType.ADJACENT_TILE,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"fire", "hazard", "active"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_place_fire,
    ),
    "dash": AbilityDef(
        ability_id="dash",
        name="Dash",
        description="Dash to any passable tile up to 2 tiles away (Chebyshev). No monsters, walls, or blocking hazards. 15-turn cooldown, unlimited uses.",
        char=">",
        color=(100, 220, 255),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.INFINITE,
        max_range=0.0,  # range enforced in execute_at (Chebyshev ≤ 2)
        tags=frozenset({"movement", "mobility", "active"}),
        execute=_dash_execute,
        execute_at=_dash_execute_at,
    ),
    "ignite_spell": AbilityDef(
        ability_id="ignite_spell",
        name="Ignite",
        description="Set one enemy within 5 tiles ablaze: applies 2 ignite stacks. 5 uses per floor.",
        char="I",
        color=(255, 100, 0),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=5,
        tags=frozenset({"fire", "ignite", "debuff", "targeted", "active"}),
        execute=None,
        is_spell=False,
        max_range=5.0,
        execute_at=_execute_at_ignite_spell,
    ),
    "slow_metabolism": AbilityDef(
        ability_id="slow_metabolism",
        name="Slow Metabolism",
        description="Double the duration of all drink buffs currently active on you. 2 uses per floor.",
        char="M",
        color=(100, 200, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=2,
        tags=frozenset({"drink", "buff", "self_cast", "active"}),
        execute=_execute_slow_metabolism,
        is_spell=False,
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
