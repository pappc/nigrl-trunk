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

from combat import deal_damage as _deal_damage


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
    is_curse: bool = False         # If True, this is a curse (debuff replaces existing curse on target)
    max_range: float = 0.0         # 0.0 = unlimited; Manhattan tile distance from player
    aoe_radius: float = 0.0        # For AOE_CIRCLE target type (future use)
    execute_at: Callable = field(default=None, repr=False)  # (engine, tx, ty) -> bool; True = fired (consume charge)
    validate: Callable = field(default=None, repr=False)    # (engine, tx, ty) -> str|None; None = ok, str = error msg
    get_affected_tiles: Callable = field(default=None, repr=False)  # (engine, tx, ty) -> list[tuple[int,int]]; None = single-target default
    rad_cost: int = 0              # Radiation consumed on cast. 0 = no rad cost.


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

    def consume(self, engine=None):
        """Spend one charge.  Charge-preservation sources stack additively
        (muffin buff 50%, blue spray-paint tile 25%, etc.) and roll once.
        Returns True if a charge was actually consumed, False if preserved."""
        import random as _rng
        has_charges = self.charges_remaining > 0 or self.floor_charges_remaining > 0
        if has_charges and engine is not None:
            preserve_chance = 0.0
            # Muffin Magic buff: +50%
            has_muffin = any(
                getattr(e, 'id', '') == 'muffin_buff' and not e.expired
                for e in engine.player.status_effects
            )
            if has_muffin:
                preserve_chance += 0.50
            # Blue spray-paint tile: +25%
            spray = engine.dungeon.spray_paint.get(
                (engine.player.x, engine.player.y)
            )
            if spray == "blue":
                preserve_chance += 0.25
            if preserve_chance > 0 and _rng.random() < preserve_chance:
                parts = []
                if has_muffin and spray == "blue":
                    parts.append(("Muffin Magic + Blue Paint! ", (130, 180, 255)))
                elif has_muffin:
                    parts.append(("Muffin Magic! ", (255, 220, 130)))
                else:
                    parts.append(("Blue Paint! ", (80, 140, 255)))
                parts.append(("Charge preserved!", (200, 255, 200)))
                engine.messages.append(parts)
                return False
        consumed = False
        if self.charges_remaining > 0:
            self.charges_remaining -= 1
            consumed = True
        if self.floor_charges_remaining > 0:
            self.floor_charges_remaining -= 1
            consumed = True
        return consumed

    def refund_charge(self, defn: AbilityDef):
        """Restore one charge (e.g., free cast from high radiation)."""
        if defn.charge_type in (ChargeType.PER_FLOOR, ChargeType.FLOOR_ONLY):
            self.floor_charges_remaining += 1
        elif defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
            self.charges_remaining += 1

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
            return str(self.floor_charges_remaining)
        if defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
            return str(self.charges_remaining)
        if defn.charge_type == ChargeType.FLOOR_ONLY:
            return str(self.floor_charges_remaining)
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


def _execute_curse_of_ham(engine) -> bool:
    """Enter cone targeting mode for Curse of Ham."""
    engine._enter_spell_targeting({"type": "curse_of_ham"})
    return False


def _execute_curse_of_dot(engine) -> bool:
    """Enter targeting mode for Curse of DOT."""
    engine._enter_spell_targeting({"type": "curse_of_dot"})
    return False


def _execute_curse_of_covid(engine) -> bool:
    """Enter targeting mode for Curse of COVID."""
    engine._enter_spell_targeting({"type": "curse_of_covid"})
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


def _execute_at_curse_of_ham(engine, tx: int, ty: int) -> bool:
    return engine._spell_curse_of_ham(tx, ty)


def _execute_at_curse_of_dot(engine, tx: int, ty: int) -> bool:
    return engine._spell_curse_of_dot(tx, ty)


def _execute_at_curse_of_covid(engine, tx: int, ty: int) -> bool:
    return engine._spell_curse_of_covid(tx, ty)


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
    """Bash an adjacent enemy with a beating weapon. Always crits, knocks back 4 tiles.
    Collision with another monster: both take STR damage and knockback stops.
    Collision with wall: enemy takes STR damage.
    """
    from items import ITEM_DEFS as _ITEM_DEFS
    weapon = engine.equipment.get("weapon")
    if not weapon:
        engine.messages.append("Bash: you need a blunt weapon equipped!")
        return False
    from items import weapon_matches_type
    wdefn = _ITEM_DEFS.get(weapon.item_id, {})
    if not weapon_matches_type(wdefn, "beating"):
        engine.messages.append("Bash: you need a beating weapon equipped!")
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
    _deal_damage(engine, damage, target)
    # Beating XP: damage dealt
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Beating", damage, bksmt)
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
            # Wall or blocking hazard (table) collision
            if engine.dungeon.is_terrain_blocked(nx, ny) or any(
                e.blocks_movement and e.entity_type == "hazard"
                for e in engine.dungeon.get_entities_at(nx, ny)
            ):
                _deal_damage(engine, str_dmg, target)
                hp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
                engine.messages.append(
                    f"{target.name} slams into an obstacle! -{str_dmg} dmg ({hp})"
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
                _deal_damage(engine, str_dmg, target)
                _deal_damage(engine, str_dmg, blocker)
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
    Collisions with walls or the player deal 3 + BKS//2 damage to the pushed unit.
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
        # Wall or blocking hazard (table) collision
        if engine.dungeon.is_terrain_blocked(nx, ny) or any(
            e.blocks_movement and e.entity_type == "hazard"
            for e in engine.dungeon.get_entities_at(nx, ny)
        ):
            _deal_damage(engine, col_dmg, target)
            hp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
            engine.messages.append(f"{target.name} slams into an obstacle! -{col_dmg} dmg ({hp})")
            if not target.alive:
                engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
            break
        # Player blocker
        if (nx, ny) == (engine.player.x, engine.player.y):
            _deal_damage(engine, col_dmg, target)
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
            _deal_damage(engine, col_dmg, target)
            _deal_damage(engine, col_dmg, blocker)
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
    """Spawn a line of 4 fire tiles in a cardinal direction from the player."""
    from hazards import create_fire
    # Derive direction from the chosen adjacent tile
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    count = 0
    for i in range(1, 5):
        fx = engine.player.x + dx * i
        fy = engine.player.y + dy * i
        if engine.dungeon.is_terrain_blocked(fx, fy):
            break
        # Don't stack fires on existing fire tiles
        has_fire = any(
            getattr(h, 'hazard_type', None) == 'fire'
            for h in engine.dungeon.get_entities_at(fx, fy)
        )
        if not has_fire:
            engine.dungeon.add_entity(create_fire(fx, fy, duration=10))
            count += 1
    if count > 0:
        engine.messages.append(f"You strike your lighter — FOOM! A wall of fire erupts! ({count} tiles)")
    else:
        engine.messages.append("The fire fizzles — nowhere to spread!")
        return False
    return True


def _rad_bomb_execute(engine) -> bool:
    """Enter cursor targeting mode for Rad Bomb placement."""
    from menu_state import MenuState
    engine.targeting_cursor = engine._get_smart_targeting_cursor()
    engine.targeting_spell = {"type": "ability_cursor"}
    engine.menu_state = MenuState.TARGETING
    engine.messages.append("Rad Bomb: choose placement (range 2, Enter). [Esc] cancel.")
    return False


def _rad_bomb_execute_at(engine, tx: int, ty: int) -> bool:
    """Place a rad bomb crystal at (tx, ty) if within range 2 and not blocked."""
    from hazards import create_rad_bomb_crystal
    px, py = engine.player.x, engine.player.y
    dist = max(abs(tx - px), abs(ty - py))
    if dist < 1:
        engine.messages.append("Rad Bomb: can't place on yourself!")
        return False
    if dist > 2:
        engine.messages.append("Rad Bomb: out of range! (max 2 tiles)")
        return False
    if engine.dungeon.is_blocked(tx, ty):
        engine.messages.append("Rad Bomb: that tile is blocked!")
        return False
    bks = engine.player_stats.effective_book_smarts
    if engine.skills.get("Nuclear Research").level >= 4:
        damage = 20 + bks
    else:
        damage = 15 + bks // 2
    crystal = create_rad_bomb_crystal(tx, ty, damage=damage)
    engine.dungeon.add_entity(crystal)
    engine.messages.append([
        ("Rad Bomb placed! ", (120, 220, 80)),
        (f"Detonates in 3 turns ({damage} dmg)", (160, 255, 120)),
    ])
    return True


def _rad_bomb_validate(engine, tx: int, ty: int):
    """Validate Rad Bomb targeting."""
    px, py = engine.player.x, engine.player.y
    dist = max(abs(tx - px), abs(ty - py))
    if dist > 2:
        return "Out of range (max 2)"
    return None


def _dash_execute(engine) -> bool:
    """Enter cursor targeting mode for the Dash ability."""
    from menu_state import MenuState
    engine.targeting_cursor = engine._get_smart_targeting_cursor()
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
    """Bitch Slap an adjacent enemy. Requires unarmed. Dmg = STR; vs. females: 2 + 2*STR."""
    # Requires unarmed (no weapon equipped)
    if engine.equipment.get("weapon") is not None:
        engine.messages.append("Bitch Slap: you need to be unarmed!")
        return False

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
        damage = 2 + 2 * strength
    else:
        damage = max(1, strength - target.defense)

    _deal_damage(engine, damage, target)
    # Smacking XP: damage dealt
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Smacking", damage, bksmt)

    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    gender_str = " (FEMALE BONUS!)" if is_female else ""
    engine.messages.append(
        f"BITCH SLAP!{gender_str} {target.name} takes {damage} dmg! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)

    engine.ability_cooldowns["black_eye_slap"] = 25
    return True


def _execute_at_gouge(engine, tx: int, ty: int) -> bool:
    """Gouge an adjacent enemy. Requires stabbing weapon. Dmg = effective STS. Applies Gouge debuff."""
    from items import ITEM_DEFS as _ITEM_DEFS
    weapon = engine.equipment.get("weapon")
    if not weapon:
        engine.messages.append("Gouge: you need a stabbing weapon equipped!")
        return False
    from items import weapon_matches_type
    wdefn = _ITEM_DEFS.get(weapon.item_id, {})
    if not weapon_matches_type(wdefn, "stabbing"):
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
    _deal_damage(engine, damage, target)
    effects.apply_effect(target, engine, "gouge", duration=5, silent=True)
    # Stabbing XP: damage dealt
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Stabbing", damage, bksmt)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Gouge! {target.name} takes {damage} dmg and is gouged for 5 turns! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    engine.ability_cooldowns["gouge"] = 12
    return True


def _execute_at_pickpocket(engine, tx: int, ty: int) -> bool:
    """Pickpocket an adjacent enemy. Dmg = STS/2; player gains 1-10 + STS cash. 15-turn cooldown."""
    import random as _rng
    import effects
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
    _deal_damage(engine, damage, target)
    cash_stolen = _rng.randint(1, 10) + stsmt
    engine.cash += cash_stolen
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Pickpocket! {target.name} takes {damage} dmg. You snag ${cash_stolen}! ({hp_disp})"
    )
    # Sleight of Hand (Stealing L4): chance to distract the target
    if target.alive:
        stealing_skill = engine.skills.get("Stealing")
        if stealing_skill and stealing_skill.level >= 4:
            distract_chance = min(stsmt * 2, 60) / 100.0
            if _rng.random() < distract_chance:
                effects.apply_effect(target, engine, "distracted", silent=True)
                engine.messages.append([
                    ("Sleight of Hand! ", (255, 200, 50)),
                    (f"{target.name} is distracted.", (200, 200, 200)),
                ])
    # Stealing XP: damage dealt + half the cash stolen
    pickpocket_xp = damage + cash_stolen // 2
    adjusted_xp = round(pickpocket_xp * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Stealing", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness,
    )
    engine.messages.append([
        ("Stealing skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    engine.ability_cooldowns["pickpocket"] = 15
    return True


def _execute_milk_from_the_store(engine) -> bool:
    """Milk From The Store: double all stats for 10 turns."""
    import effects
    # Don't stack — block if already active
    if any(getattr(e, 'id', None) == 'milk_from_the_store' for e in engine.player.status_effects):
        engine.messages.append("Milk From The Store is already active!")
        return False
    effects.apply_effect(engine.player, engine, "milk_from_the_store", silent=True)
    engine.messages.append([
        ("Milk From The Store! ", (200, 255, 200)),
        ("All stats doubled for 10 turns!", (255, 255, 200)),
    ])
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
    _deal_damage(engine, damage, target)
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


def _execute_double_tap(engine) -> bool:
    """Enter gun targeting mode for Double Tap: 2 shots in a 4-tile line."""
    return engine._enter_gun_ability_targeting({
        "ability_id": "double_tap",
        "name": "Double Tap",
        "aoe_type": "line",
        "num_shots": 2,
        "damage": (6, 18),
        "accuracy": 50,
        "energy": 80,
        "range": 4,
        "cooldown": 0,
    })


def _execute_spray(engine) -> bool:
    """Enter gun targeting mode for Spray: 5-round cone burst."""
    return engine._enter_gun_ability_targeting({
        "ability_id": "spray",
        "name": "Spray",
        "aoe_type": "cone",
        "num_shots": 5,
        "damage": (12, 25),
        "accuracy": 50,
        "energy": 120,
        "range": 6,
        "cooldown": 0,
    })


def _execute_burst(engine) -> bool:
    """Enter gun targeting mode for Burst: 3-round line burst."""
    return engine._enter_gun_ability_targeting({
        "ability_id": "burst",
        "name": "Burst",
        "aoe_type": "line",
        "num_shots": 3,
        "damage": (12, 25),
        "accuracy": 60,
        "energy": 100,
        "range": 6,
        "cooldown": 0,
    })


def _execute_spray_and_pray(engine) -> bool:
    """Fire 4 rapid shots at a single target. Each rolls hit independently at -15%.
    Each shot has its own jam check. If a jam occurs, remaining shots are lost."""
    if engine.gun_jammed:
        engine.messages.append("Gun is jammed! Reload (Shift+R) to clear it.")
        return False
    return engine._enter_gun_ability_targeting({
        "ability_id": "spray_and_pray",
        "name": "Spray & Pray",
        "aoe_type": "target",
        "num_shots": 4,
        "damage": (9, 14),
        "accuracy": 55,           # base 70 accurate - 15 penalty
        "energy": 50,
        "range": 5,
        "cooldown": 0,
        "jam_chance": 18,         # per-shot jam check
    })


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


def _execute_quick_eat(engine) -> bool:
    """Grant 1 stack of the Quick Eat buff. Next food eaten is instant."""
    from effects import apply_effect
    # Check if already have the buff
    existing = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'quick_eat'), None)
    if existing:
        engine.messages.append("You already have Quick Eat active!")
        return False
    apply_effect(engine.player, engine, "quick_eat", duration=999, silent=True)
    engine.messages.append([
        ("Quick Eat! ", (255, 200, 50)),
        ("Your next food will be eaten instantly.", (200, 255, 200)),
    ])
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
    _deal_damage(engine, actual, target)
    engine.messages.append([
        ("You hurl a bottle at ", (200, 200, 200)),
        (target.name, target.color),
        (f" for {actual} damage!", (200, 200, 200)),
    ])
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    return True


def _execute_pandemic(engine) -> bool:
    """Pandemic: apply 100 toxicity to every monster on the floor."""
    from combat import add_toxicity
    monsters = [m for m in engine.dungeon.get_monsters() if m.alive]
    if not monsters:
        engine.messages.append("Pandemic: no enemies on the floor!")
        return False
    for m in monsters:
        add_toxicity(engine, m, 100)
    engine.messages.append([
        ("Pandemic! ", (200, 180, 60)),
        (f"100 toxicity applied to {len(monsters)} enemy(ies)!", (200, 255, 200)),
    ])
    return True


def _execute_radiation_nova(engine) -> bool:
    """Radiation Nova: AOE damage centered on player, radius 4.
    Damage scales off player's radiation (capped at 200) + total_spell_damage.
    Does NOT consume radiation."""
    from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
    rad = engine.player.radiation
    if rad <= 0:
        engine.messages.append("Radiation Nova: you have no radiation!")
        return False
    capped_rad = min(rad, 200)
    spell_dmg = engine.player_stats.total_spell_damage
    damage = capped_rad // 2 + spell_dmg
    px, py = engine.player.x, engine.player.y
    radius = 4
    hit_targets = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            x, y = px + dx, py + dy
            if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
                continue
            # Chebyshev distance
            if max(abs(dx), abs(dy)) > radius:
                continue
            for entity in engine.dungeon.get_entities_at(x, y):
                if entity.entity_type == "monster" and entity.alive:
                    actual = max(1, damage - entity.defense)
                    _deal_damage(engine, actual, entity)
                    hit_targets.append((entity, actual))
    if not hit_targets:
        engine.messages.append(f"Radiation Nova pulses... but no enemies in range! ({damage} dmg)")
        return True
    engine.messages.append([
        ("Radiation Nova! ", (160, 220, 100)),
        (f"{len(hit_targets)} enemy(ies) hit for {damage} dmg (rad={capped_rad}, spell={spell_dmg})", (200, 255, 200)),
    ])
    for entity, _ in hit_targets:
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)
    return True


def _execute_gas_attack(engine) -> bool:
    """Gas Attack: apply fear to all enemies within 4 tiles of the player."""
    from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
    from effects import apply_effect
    px, py = engine.player.x, engine.player.y
    radius = 4
    feared = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            x, y = px + dx, py + dy
            if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
                continue
            if max(abs(dx), abs(dy)) > radius:
                continue
            for entity in engine.dungeon.get_entities_at(x, y):
                if entity.entity_type == "monster" and entity.alive:
                    apply_effect(entity, engine, "fear", duration=10,
                                 source_x=px, source_y=py)
                    feared.append(entity)
    if feared:
        engine.messages.append([
            ("Gas Attack! ", (160, 200, 80)),
            (f"{len(feared)} enemy(ies) flee in terror!", (200, 255, 200)),
        ])
    else:
        engine.messages.append("Gas Attack! ...but no enemies were nearby.")
    return True


def _execute_mirror_entity(engine) -> bool:
    """Mirror Entity: create illusory copies that absorb melee hits."""
    import math
    from effects import apply_effect
    bks = engine.player_stats.effective_book_smarts
    stacks = _random.randint(2, 3) + bks // 5
    effect = apply_effect(engine.player, engine, "mirror_entity",
                          duration=100, stacks=stacks, silent=True)
    if effect:
        engine.messages.append([
            ("Mirror Entity! ", (150, 200, 255)),
            (f"{stacks} illusory copies surround you.", (200, 220, 255)),
        ])
    return True


def _execute_fire_meatball(engine) -> bool:
    """Fire Meatball: spawn 2 meatball summons adjacent to the player."""
    from entity import Entity
    from ai import get_initial_state
    px, py = engine.player.x, engine.player.y
    dungeon = engine.dungeon

    # Find up to 2 free adjacent tiles
    spawn_tiles = []
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
        tx, ty = px + dx, py + dy
        if not dungeon.is_blocked(tx, ty):
            spawn_tiles.append((tx, ty))
            if len(spawn_tiles) >= 2:
                break

    if not spawn_tiles:
        engine.messages.append("You try to summon meatballs but there's no room! What the fuck?")
        return False

    for sx, sy in spawn_tiles:
        meatball = Entity(
            x=sx, y=sy,
            char="o",
            color=(180, 80, 40),
            name="Meatball",
            entity_type="monster",
            hp=9999,
            power=0,
            defense=999,
            ai_type="meatball",
            speed=100,
            is_summon=True,
            summon_lifetime=20,
        )
        meatball.ai_state = get_initial_state("meatball")
        meatball.dev_invincible = True  # cannot be killed
        dungeon.add_entity(meatball)

    count = len(spawn_tiles)
    engine.messages.append([
        ("Fire Meatball! ", (255, 140, 40)),
        (f"{count} meatball{'s' if count > 1 else ''} launched!", (255, 200, 150)),
    ])
    return True


def _execute_acid_meltdown(engine) -> bool:
    """Activate the Acid Meltdown buff. Costs 25 toxicity."""
    from effects import apply_effect
    # Check if already active
    existing = next(
        (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'acid_meltdown'),
        None,
    )
    if existing:
        engine.messages.append("Acid Meltdown is already active!")
        return False
    # Check toxicity cost
    if engine.player.toxicity < 25:
        engine.messages.append("Not enough toxicity! (need 25)")
        return False
    engine.player.toxicity -= 25
    apply_effect(engine.player, engine, "acid_meltdown", duration=20)
    engine.messages.append([
        ("Acid Meltdown! ", (100, 255, 50)),
        ("Move faster. Kills explode into acid. (20 turns)", (160, 255, 120)),
    ])
    return True


def _execute_toxic_harvest(engine) -> bool:
    """Activate the Toxic Harvest buff for 10 turns."""
    from effects import apply_effect
    # Check if already active — don't waste the charge
    existing = next(
        (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'toxic_harvest'),
        None,
    )
    if existing:
        engine.messages.append("Toxic Harvest is already active!")
        return False
    apply_effect(engine.player, engine, "toxic_harvest", duration=10)
    engine.messages.append([
        ("Toxic Harvest! ", (80, 255, 80)),
        ("Kills now feed your toxicity for 10 turns.", (160, 255, 160)),
    ])
    return True


def _execute_white_out(engine) -> bool:
    """White Out: gain 25 toxicity, +8 swagger / -25% damage dealt for 50 turns."""
    from effects import apply_effect
    from combat import add_toxicity
    existing = next(
        (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'white_out'),
        None,
    )
    if existing:
        engine.messages.append("White Out is already active!")
        return False
    add_toxicity(engine, engine.player, 25, pierce_resistance=True)
    apply_effect(engine.player, engine, "white_out", duration=50)
    engine.messages.append([
        ("White Out! ", (240, 240, 255)),
        ("+25 toxicity. +8 Swagger, -25% damage dealt for 50 turns.", (200, 200, 240)),
    ])
    return True


def _execute_web_trail(engine) -> bool:
    """Activate Web Trail: for 5 turns, leave cobwebs on tiles you move off of."""
    import effects
    effects.apply_effect(engine.player, engine, "web_trail")
    engine.messages.append([
        ("Web Trail! ", (180, 180, 255)),
        ("You'll leave cobwebs behind for 5 turns.", (200, 200, 220)),
    ])
    return True


def _execute_purge(engine) -> bool:
    """Purge: remove 20 infection, gain 3-stack melee damage debuff."""
    if engine.player.infection <= 0:
        engine.messages.append("You have no infection to purge!")
        return False
    from combat import remove_infection
    import effects
    remove_infection(engine, engine.player, 20)
    effects.apply_effect(engine.player, engine, "purge_infection")
    engine.messages.append([
        ("Purge! ", (120, 200, 50)),
        ("-20 infection, but your next 3 melee hits deal half damage.", (180, 220, 120)),
    ])
    return True


def _execute_zombie_stare(engine) -> bool:
    """Enter targeting mode for Zombie Stare."""
    engine._enter_spell_targeting({"type": "zombie_stare"})
    return False


def _execute_at_zombie_stare(engine, tx: int, ty: int) -> bool:
    """Zombie Stare: stun target for 3 turns, then fear for 10 turns. +5 infection."""
    from effects import apply_effect
    from combat import add_infection
    target = None
    for ent in engine.dungeon.get_entities_at(tx, ty):
        if ent.entity_type == "monster" and ent.alive:
            target = ent
            break
    if target is None:
        engine.messages.append("No target there!")
        return False
    apply_effect(target, engine, "stun", duration=3)
    apply_effect(target, engine, "fear", duration=10,
                 source_x=engine.player.x, source_y=engine.player.y)
    add_infection(engine, engine.player, 5)
    engine.ability_cooldowns["zombie_stare"] = 15
    engine.messages.append([
        ("Zombie Stare! ", (100, 180, 50)),
        (f"{target.name} is paralyzed with fear! (+5 infection)", (160, 220, 100)),
    ])
    return True


def _execute_zombie_rage(engine) -> bool:
    """Activate Zombie Rage: +20% melee dmg, +20 energy/tick, +5 infection now. 10 turns."""
    import effects
    if any(getattr(e, 'id', '') == 'zombie_rage' for e in engine.player.status_effects):
        engine.messages.append("Zombie Rage is already active!")
        return False
    from combat import add_infection
    add_infection(engine, engine.player, 5)
    effects.apply_effect(engine.player, engine, "zombie_rage")
    engine.ability_cooldowns["zombie_rage"] = 40
    engine.messages.append([
        ("ZOMBIE RAGE! ", (180, 50, 50)),
        ("+20% melee damage, +20 energy/tick for 10 turns. (+5 infection)", (220, 120, 120)),
    ])
    return True


def _execute_at_summon_spiderling(engine, tx: int, ty: int) -> bool:
    """Summon a Spider Hatchling on the targeted adjacent tile."""
    from entity import Entity
    from ai import get_initial_state

    # Block if tile is a wall or occupied by a blocking entity
    if engine.dungeon.is_blocked(tx, ty):
        engine.messages.append("Can't summon there — tile is blocked!")
        return False

    hatchling = Entity(
        x=tx, y=ty,
        char=chr(0xE004),
        color=(255, 255, 255),
        name="Spider Hatchling",
        entity_type="monster",
        hp=8,
        power=2,
        defense=0,
        ai_type="spider_hatchling",
        speed=100,
        is_summon=True,
    )
    hatchling.ai_state = get_initial_state("spider_hatchling")
    engine.dungeon.add_entity(hatchling)

    engine.messages.append([
        ("Summon Spider! ", (180, 180, 255)),
        ("A spiderling hatches!", (200, 200, 220)),
    ])
    return True


def _execute_crack_hallucinations(engine) -> bool:
    """Set the crack hallucinations flag. Next consumable used grants meth equal to its value."""
    if getattr(engine, 'crack_hallucinations_active', False):
        engine.messages.append("Crack Hallucinations is already active!")
        return False
    engine.crack_hallucinations_active = True
    engine.messages.append([
        ("Crack Hallucinations! ", (180, 80, 255)),
        ("Your next consumable will fuel your meth meter.", (200, 160, 255)),
    ])
    return True


def _execute_emission(engine) -> bool:
    """Set all visible enemies' radiation to the player's current radiation level."""
    player_rad = engine.player.radiation
    if player_rad <= 0:
        engine.messages.append("You have no radiation to emit!")
        return False
    visible = engine.dungeon.visible
    monsters = [
        e for e in engine.dungeon.entities
        if e.entity_type == "monster" and e.alive
        and visible[e.y][e.x]
    ]
    if not monsters:
        engine.messages.append("No enemies in sight!")
        return False
    count = 0
    for m in monsters:
        old_rad = getattr(m, 'radiation', 0)
        if player_rad > old_rad:
            m.radiation = player_rad
            count += 1
    engine.messages.append([
        ("EMISSION! ", (120, 255, 80)),
        (f"{count} enem{'y' if count == 1 else 'ies'} irradiated to {player_rad} rad!", (160, 255, 120)),
    ])
    # Glow Up XP: 5 per enemy irradiated
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Glow Up", count * 5, bksmt)
    return True


def _snipers_mark_execute_at(engine, tx, ty) -> bool:
    """Apply Sniper's Mark debuff to a target monster."""
    from effects import apply_effect
    target = None
    for e in engine.dungeon.get_entities_at(tx, ty):
        if e.entity_type == "monster" and e.alive:
            target = e
            break
    if target is None:
        engine.messages.append("No target there!")
        return False
    # Check if already marked
    if any(getattr(eff, 'id', '') == 'snipers_mark' for eff in target.status_effects):
        engine.messages.append(f"{target.name} is already marked!")
        return False
    apply_effect(target, engine, "snipers_mark")
    engine.messages.append([
        ("Sniper's Mark! ", (255, 100, 100)),
        (f"{target.name} takes 10% more damage.", (200, 200, 200)),
    ])
    # Track marked target for charge refund on kill
    engine.snipers_mark_target_id = getattr(target, 'instance_id', id(target))
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
        description="Target a 3×3 area (cannot include yourself). Dmg: max(1, 25 - Swagger + BKS/2). Applies Lesser Cloudkill: 1 dmg/turn + all stats -1 for 10 turns.",
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
        description="Smash an adjacent enemy with a beating weapon. Always crits. Knocks back 4 tiles; wall hit = STR dmg, enemy collision = both take STR dmg. 10-turn cooldown.",
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
        description="Slap an adjacent enemy (unarmed only). Dmg: STR (vs females: 2 + 2×STR, ignores defense). 25-turn cooldown.",
        char="S",
        color=(255, 100, 150),
        target_type=TargetType.ADJACENT,
        charge_type=ChargeType.INFINITE,
        tags=frozenset({"attack", "melee", "damage", "targeted", "active"}),
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
        description="Strike an adjacent enemy. Dmg: STS/2. Snag 1-10 + STS cash. 15-turn cooldown.",
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
        description="Push an adjacent enemy 3 tiles in a straight line. Collisions: 3 + BKS/2 dmg. 2 uses/floor, 20-turn cooldown.",
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
        description="Strike your lighter to spawn a line of 4 fire tiles in a cardinal direction. Fires last 10 turns. 3/floor.",
        char="^",
        color=(255, 80, 0),
        target_type=TargetType.ADJACENT_TILE,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
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
    "rad_bomb": AbilityDef(
        ability_id="rad_bomb",
        name="Rad Bomb",
        description="Place a crystal within 2 tiles that detonates after 3 turns, dealing 15+BKS/2 damage in a 5x5 area (20+BKS at L4). 3 charges/floor. Each cast costs 25 radiation and grants 50 Nuclear Research XP. At 100+ rad, the charge is refunded (rad still spent).",
        char="*",
        color=(120, 220, 80),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
        rad_cost=25,
        tags=frozenset({"spell", "aoe", "damage", "radiation", "active", "placement"}),
        execute=_rad_bomb_execute,
        execute_at=_rad_bomb_execute_at,
        validate=_rad_bomb_validate,
        is_spell=True,
    ),
    "snipers_mark": AbilityDef(
        ability_id="snipers_mark",
        name="Sniper's Mark",
        description="Mark a visible enemy. It takes 10% more damage (rounds up). 1 charge/floor, refunded on marked target's death.",
        char="X",
        color=(255, 100, 100),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"debuff", "targeted", "active"}),
        execute_at=_snipers_mark_execute_at,
    ),
    "emission": AbilityDef(
        ability_id="emission",
        name="Emission",
        description="Set all visible enemies' radiation to your current radiation level. 1 use per floor.",
        char="E",
        color=(120, 255, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"radiation", "aoe", "active"}),
        execute=_execute_emission,
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
    "quick_eat": AbilityDef(
        ability_id="quick_eat",
        name="Quick Eat",
        description="Your next food is eaten instantly — no multi-turn wait. 1 use per floor.",
        char="Q",
        color=(255, 200, 50),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"food", "buff", "self_cast", "active"}),
        execute=_execute_quick_eat,
        is_spell=False,
    ),
    "double_tap": AbilityDef(
        ability_id="double_tap",
        name="Double Tap",
        description="Fire 2 rounds in a 4-tile line. Dmg: 6-18 per bullet. 50% accuracy. 80 energy. Requires 2+ rounds loaded.",
        char="T",
        color=(255, 200, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"gun", "active", "ranged"}),
        execute=_execute_double_tap,
        is_spell=False,
    ),
    "spray": AbilityDef(
        ability_id="spray",
        name="Spray",
        description="Fire 5 rounds in a 30-degree cone. Dmg: 12-25 per bullet. 50% accuracy. 120 energy. Requires 5+ rounds loaded.",
        char="S",
        color=(200, 100, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"gun", "active", "ranged"}),
        execute=_execute_spray,
        is_spell=False,
    ),
    "burst": AbilityDef(
        ability_id="burst",
        name="Burst",
        description="Fire 3 rounds in a 6-tile line. Dmg: 12-25 per bullet. 60% accuracy. 100 energy. Requires 3+ rounds loaded.",
        char="B",
        color=(180, 150, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"gun", "active", "ranged"}),
        execute=_execute_burst,
        is_spell=False,
    ),
    "spray_and_pray": AbilityDef(
        ability_id="spray_and_pray",
        name="Spray & Pray",
        description="Fire 4 rapid shots at one target. Dmg: 9-14 per bullet. 55% accuracy. 50 energy. Each shot may jam the gun.",
        char="P",
        color=(90, 90, 95),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"gun", "active", "ranged"}),
        execute=_execute_spray_and_pray,
        is_spell=False,
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
    "pandemic": AbilityDef(
        ability_id="pandemic",
        name="Pandemic",
        description="Release a toxic wave across the entire floor. Applies 100 toxicity to every monster.",
        char="P",
        color=(200, 180, 60),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "aoe", "damage", "self_cast", "active", "toxicity"}),
        execute=_execute_pandemic,
        is_spell=False,
    ),
    "gas_attack": AbilityDef(
        ability_id="gas_attack",
        name="Gas Attack",
        description="Release a noxious cloud. All enemies within 4 tiles flee in fear for 10 turns. 50% chance to break on damage.",
        char="G",
        color=(160, 200, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "aoe", "debuff", "self_cast", "active", "fear"}),
        execute=_execute_gas_attack,
        is_spell=False,
    ),
    "mirror_entity": AbilityDef(
        ability_id="mirror_entity",
        name="Mirror Entity",
        description="Create illusory copies of yourself. Each copy can absorb one melee hit. Stacks: 2-3 + BKS/5. Lasts 100 turns.",
        char="I",
        color=(150, 200, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "buff", "defensive", "self_cast", "active"}),
        execute=_execute_mirror_entity,
        is_spell=False,
    ),
    "fire_meatball": AbilityDef(
        ability_id="fire_meatball",
        name="Fire Meatball",
        description="Launch 2 meatball summons that chase the nearest enemy and explode on contact. 3x3 blast: 10 + BKS/2 dmg. Can hurt you!",
        char="M",
        color=(180, 80, 40),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "summon", "aoe", "damage", "self_cast", "active"}),
        execute=_execute_fire_meatball,
        is_spell=False,
    ),
    "radiation_nova": AbilityDef(
        ability_id="radiation_nova",
        name="Radiation Nova",
        description="Emit a burst of nuclear energy. Hits all enemies within 4 tiles. Dmg: min(rad,200)/2 + spell_dmg. Does not consume radiation.",
        char="N",
        color=(160, 220, 100),
        target_type=TargetType.SELF,
        charge_type=ChargeType.TOTAL,
        max_charges=0,
        tags=frozenset({"spell", "aoe", "damage", "self_cast", "active", "radiation"}),
        execute=_execute_radiation_nova,
        is_spell=True,
    ),
    "acid_meltdown": AbilityDef(
        ability_id="acid_meltdown",
        name="Acid Meltdown",
        description="Cost: 25 toxicity. For 20 turns, movement costs half energy and kills explode into 3x3 acid. 1/floor.",
        char="A",
        color=(100, 255, 50),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"toxicity", "buff", "self_cast", "active"}),
        execute=_execute_acid_meltdown,
        is_spell=False,
    ),
    "toxic_harvest": AbilityDef(
        ability_id="toxic_harvest",
        name="Toxic Harvest",
        description="Activate: for 10 turns, any monster kill grants +5 toxicity and refreshes this buff. 1/floor.",
        char="T",
        color=(80, 255, 80),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"toxicity", "buff", "self_cast", "active"}),
        execute=_execute_toxic_harvest,
        is_spell=False,
    ),
    "white_out": AbilityDef(
        ability_id="white_out",
        name="White Out",
        description="Gain 25 toxicity. +8 Swagger, -25% damage dealt for 50 turns.",
        char="W",
        color=(240, 240, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
        tags=frozenset({"toxicity", "buff", "self_cast", "active"}),
        execute=_execute_white_out,
        is_spell=False,
    ),
    "crack_hallucinations": AbilityDef(
        ability_id="crack_hallucinations",
        name="Crack Hallucinations",
        description="Your next consumable grants meth equal to its value, plus Meth-Head XP. 1 use per floor.",
        char="H",
        color=(180, 80, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=1,
        tags=frozenset({"meth", "buff", "self_cast", "active"}),
        execute=_execute_crack_hallucinations,
        is_spell=False,
    ),
    # ── Arachnigga ─────────────────────────────────────────────────────────
    "web_trail": AbilityDef(
        ability_id="web_trail",
        name="Web Trail",
        description="For 5 turns, every tile you move off of gets a cobweb that sticks enemies (and you). 3/floor.",
        char="w",
        color=(180, 180, 255),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
        tags=frozenset({"buff", "self_cast", "active", "web"}),
        execute=_execute_web_trail,
        is_spell=False,
    ),
    "summon_spiderling": AbilityDef(
        ability_id="summon_spiderling",
        name="Summon Spider",
        description="Summon a Spider Hatchling on an adjacent tile. It guards the spot until an enemy comes near, then chases and bites. 5/floor.",
        char="s",
        color=(180, 180, 255),
        target_type=TargetType.ADJACENT_TILE,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=5,
        tags=frozenset({"summon", "active", "web"}),
        execute=None,
        is_spell=False,
        max_range=1.5,
        execute_at=_execute_at_summon_spiderling,
    ),
    # ── Infected ───────────────────────────────────────────────────────────
    "purge": AbilityDef(
        ability_id="purge",
        name="Purge",
        description="Remove 20 infection. Your next 3 melee attacks deal 50% damage. Stacks if reused.",
        char="P",
        color=(120, 200, 50),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"self_cast", "active", "infection"}),
        execute=_execute_purge,
        is_spell=False,
    ),
    "zombie_stare": AbilityDef(
        ability_id="zombie_stare",
        name="Zombie Stare",
        description="Stare down a monster within 3 tiles. Stunned 3 turns, then feared 10 turns. +5 infection. 15t cooldown.",
        char="Z",
        color=(100, 180, 50),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"debuff", "active", "infection", "cc"}),
        execute=_execute_zombie_stare,
        is_spell=False,
        max_range=3.0,
        execute_at=_execute_at_zombie_stare,
    ),
    "zombie_rage": AbilityDef(
        ability_id="zombie_rage",
        name="Zombie Rage",
        description="+20% melee damage, +20 energy/tick for 10 turns. +5 infection on use and per melee kill. 40-turn cooldown.",
        char="Z",
        color=(180, 50, 50),
        target_type=TargetType.SELF,
        charge_type=ChargeType.INFINITE,
        max_charges=0,
        tags=frozenset({"self_cast", "active", "infection", "buff"}),
        execute=_execute_zombie_rage,
        is_spell=False,
    ),
    # ── Blackkk Magic curses ──────────────────────────────────────────────
    "curse_of_ham": AbilityDef(
        ability_id="curse_of_ham",
        name="Curse of Ham",
        description="Curse enemies in a cone (range 3, 60°). Cursed monsters attack slower (+50% energy cost) and deal 50% less damage. 3/floor.",
        char="H",
        color=(140, 60, 180),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
        tags=frozenset({"spell", "curse", "cone", "debuff", "active"}),
        execute=_execute_curse_of_ham,
        is_spell=True,
        is_curse=True,
        max_range=3.0,
        execute_at=_execute_at_curse_of_ham,
        get_affected_tiles=lambda engine, tx, ty: engine._get_curse_of_ham_affected_tiles(tx, ty),
    ),
    "curse_of_dot": AbilityDef(
        ability_id="curse_of_dot",
        name="Curse of DOT",
        description="Curse a single enemy. Each turn the curse gains a stack and deals 1-5 damage, hitting harder as stacks grow. Spreads on death.",
        char="D",
        color=(140, 60, 180),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.FLOOR_ONLY,
        max_charges=3,
        tags=frozenset({"spell", "curse", "dot", "debuff", "active"}),
        execute=_execute_curse_of_dot,
        is_spell=True,
        is_curse=True,
        max_range=8.0,
        execute_at=_execute_at_curse_of_dot,
    ),
    "curse_of_covid": AbilityDef(
        ability_id="curse_of_covid",
        name="Curse of COVID",
        description="Curse a single enemy. Each turn applies 20 rad or tox (capped at 150). 50% chance to gain stacks. 25% chance to spread to nearby enemies.",
        char="C",
        color=(140, 60, 180),
        target_type=TargetType.SINGLE_ENEMY_LOS,
        charge_type=ChargeType.FLOOR_ONLY,
        max_charges=3,
        tags=frozenset({"spell", "curse", "dot", "debuff", "active"}),
        execute=_execute_curse_of_covid,
        is_spell=True,
        is_curse=True,
        max_range=8.0,
        execute_at=_execute_at_curse_of_covid,
    ),
    "milk_from_the_store": AbilityDef(
        ability_id="milk_from_the_store",
        name="Milk From The Store",
        description="Double all stats for 10 turns. 3 charges/floor.",
        char="M",
        color=(200, 255, 200),
        target_type=TargetType.SELF,
        charge_type=ChargeType.PER_FLOOR,
        max_charges=3,
        tags=frozenset({"buff", "self", "active"}),
        execute=_execute_milk_from_the_store,
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
