"""
Spell and ability system functions extracted from engine.py.

All functions take `engine` as their first parameter (replacing `self`).
"""

import math
import random

from combat import deal_damage as _deal_damage
from config import (
    DUNGEON_WIDTH, DUNGEON_HEIGHT, ENERGY_THRESHOLD,
)
from items import get_item_def
from menu_state import MenuState
from abilities import ABILITY_REGISTRY, AbilityInstance, ChargeType, TargetType
import effects


# ======================================================================
# Entity targeting
# ======================================================================

def _get_weapon_reach(engine) -> int:
    """Return the reach of the equipped weapon (1 = adjacent, 2+ = extended)."""
    weapon = engine.equipment.get("weapon")
    if weapon:
        defn = get_item_def(weapon.item_id)
        return defn.get("reach", 1)
    return 1


def _build_entity_target_list(engine, reach: int) -> list:
    """Return visible living monsters within Chebyshev reach, sorted closest-first."""
    targets = []
    for entity in engine.dungeon.get_monsters():
        if not entity.alive:
            continue
        dx = abs(entity.x - engine.player.x)
        dy = abs(entity.y - engine.player.y)
        dist = max(dx, dy)  # Chebyshev distance
        if dist <= reach and engine.dungeon.visible[entity.y, entity.x]:
            targets.append((dist, entity.x, entity))
    targets.sort(key=lambda t: (t[0], t[1]))
    return [e for _, _, e in targets]


def _action_start_entity_targeting(engine, _action):
    """Enter entity targeting mode if there are valid targets in weapon range."""
    reach = _get_weapon_reach(engine)
    if reach < 1:
        engine.messages.append("Your weapon cannot be used at range.")
        return False
    target_list = _build_entity_target_list(engine, reach)
    if not target_list:
        engine.messages.append("No targets in range.")
        return False
    engine.entity_target_list = target_list
    engine.entity_target_index = 0
    engine.menu_state = MenuState.ENTITY_TARGETING
    return False


def _handle_entity_targeting_input(engine, action):
    """Left/right cycle targets; Enter attacks/fires ability; Esc cancels."""
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.entity_target_list = []
        engine.targeting_ability_index = None
        return False

    if action_type == "move":
        dx = action.get("dx", 0)
        if dx != 0 and engine.entity_target_list:
            n = len(engine.entity_target_list)
            engine.entity_target_index = (engine.entity_target_index + dx) % n
        return False

    if action_type == "confirm_target":
        if not engine.entity_target_list:
            engine.menu_state = MenuState.NONE
            engine.targeting_ability_index = None
            return False
        target = engine.entity_target_list[engine.entity_target_index]
        engine.last_targeted_enemy = target
        engine.entity_target_list = []
        engine.menu_state = MenuState.NONE

        # Ability adjacent targeting: fire the ability instead of a weapon attack
        if engine.targeting_ability_index is not None:
            if target.alive:
                result = _fire_adjacent_ability(engine, target.x, target.y)
                if result and engine.running and engine.player.alive:
                    engine.player.energy -= ENERGY_THRESHOLD
                    engine._run_energy_loop()
                return result
            engine.targeting_ability_index = None
            return False

        if target.alive:
            engine.handle_attack(engine.player, target)
            if engine.running and engine.player.alive:
                engine.player.energy -= ENERGY_THRESHOLD
                engine._run_energy_loop()
        return True

    return False


# ======================================================================
# Item throw targeting
# ======================================================================

_C_MSG_NEUTRAL = (200, 200, 100)

_WASTE_MESSAGES = [
    "The joint bounces off the floor and smolders away. You just wasted primo weed.",
    "Nothing there. Great job, you killed perfectly good chronic.",
    "You hucked a whole joint at an empty tile. Your dealer disowns you.",
    "The joint lands in the corner and burns up. What a tragic loss.",
    "Wasted. You threw good herb at absolutely nothing. Smooth move.",
    "That was GOOD weed, man. What are you doing?",
]


def _enter_targeting(engine, item_index):
    """Enter targeting mode for a throw action. Cursor starts on last/nearest enemy."""
    engine.targeting_item_index = item_index
    engine.targeting_cursor = engine._get_smart_targeting_cursor()
    engine.selected_item_index = None
    engine.menu_state = MenuState.TARGETING


def _handle_targeting_input(engine, action):
    """Handle input while in targeting mode. Arrow keys move cursor; Enter throws/casts; Esc cancels."""
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.targeting_item_index = None
        engine.targeting_spell = None
        engine.targeting_ability_index = None
        return False

    if action_type == "move":
        nx = engine.targeting_cursor[0] + action["dx"]
        ny = engine.targeting_cursor[1] + action["dy"]
        if 0 <= nx < DUNGEON_WIDTH and 0 <= ny < DUNGEON_HEIGHT:
            engine.targeting_cursor = [nx, ny]
        return False

    if action_type == "confirm_target":
        tx, ty = engine.targeting_cursor
        engine._record_targeted_enemy_at(tx, ty)
        if engine.targeting_spell is not None:
            if not _is_targeting_in_range(engine, tx, ty):
                engine.messages.append("Out of range!")
                return False
            return _execute_spell_at(engine, tx, ty)
        return _throw_item(engine, engine.targeting_item_index, tx, ty)

    return False


def _throw_item(engine, item_index, tx, ty):
    """Throw item at target tile. Apply throw_effect to monster if present, else waste it."""
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("You can't throw there \u2014 it's not in your line of sight.")
        engine.menu_state = MenuState.NONE
        engine.targeting_item_index = None
        return False

    item = engine.player.inventory[item_index]
    defn = get_item_def(item.item_id)
    throw_effect = defn.get("throw_effect")
    item_name = item.name
    item_color = item.color

    target_monster = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )

    # Consume one from the stack
    item.quantity -= 1
    if item.quantity <= 0:
        engine.player.inventory.pop(item_index)

    engine.menu_state = MenuState.NONE
    engine.targeting_item_index = None

    if target_monster is not None and throw_effect:
        engine.messages.append([
            ("You threw ", _C_MSG_NEUTRAL),
            (item_name, item_color),
            (f" at {target_monster.name}!", _C_MSG_NEUTRAL),
        ])
        if throw_effect.get("type") == "strain_roll":
            roll = random.randint(1, 100)
            # Contact High (Smoking level 5): roll twice, take worst for monster
            if engine.skills.get("Smoking").level >= 5:
                roll2 = random.randint(1, 100)
                roll = min(roll, roll2)
            engine._apply_strain_effect(target_monster, item.strain, roll, "monster")
        else:
            engine._apply_item_effect_to_entity(throw_effect, target_monster)
        return True

    # No monster — wasted
    engine.messages.append(random.choice(_WASTE_MESSAGES))
    return True


# ======================================================================
# Spell targeting helpers
# ======================================================================

def _get_targeting_ability_def(engine):
    """Return the AbilityDef for the ability currently being targeted, or None."""
    if engine.targeting_ability_index is not None:
        if 0 <= engine.targeting_ability_index < len(engine.player_abilities):
            inst = engine.player_abilities[engine.targeting_ability_index]
            return ABILITY_REGISTRY.get(inst.ability_id)
    return None


def _is_targeting_in_range(engine, tx: int, ty: int) -> bool:
    """Return True if (tx, ty) is within the current ability's max_range (0.0 = unlimited, Manhattan distance)."""
    defn = _get_targeting_ability_def(engine)
    if defn is None or defn.max_range == 0.0:
        return True
    dist = abs(tx - engine.player.x) + abs(ty - engine.player.y)
    return dist <= defn.max_range


def _enter_spell_targeting(engine, spell_dict: dict) -> None:
    """Enter cursor targeting mode for a Dosidos spell cast."""
    engine.targeting_spell = dict(spell_dict)
    engine.targeting_item_index = None
    engine.targeting_cursor = engine._get_smart_targeting_cursor()
    engine.menu_state = MenuState.TARGETING


# ======================================================================
# Spell execution and dispatch
# ======================================================================

def _execute_spell_at(engine, tx: int, ty: int) -> bool:
    """Dispatch spell execution at (tx, ty).
    If the current ability has an execute_at, call it and handle charge/menu cleanup.
    Otherwise fall back to _execute_dosidos_spell_at for item-triggered spells."""
    defn = _get_targeting_ability_def(engine)
    if defn is not None and defn.execute_at is not None:
        fired = defn.execute_at(engine, tx, ty)
        if fired:
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            engine.menu_state = MenuState.NONE
            engine.targeting_spell = None
        return fired
    return _execute_dosidos_spell_at(engine, tx, ty)


def _execute_dosidos_spell_at(engine, tx: int, ty: int) -> bool:
    """Execute an item-triggered (Dosidos) spell at (tx, ty).
    Returns True to close targeting (final cast done), False to keep it open."""
    spell = engine.targeting_spell
    spell_type = spell["type"]

    if spell_type == "dimension_door":
        if _spell_dimension_door(engine, tx, ty):
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            engine.menu_state = MenuState.NONE
            engine.targeting_spell = None
        return False

    elif spell_type == "chain_lightning":
        if _spell_chain_lightning(engine, tx, ty, spell.get("total_hits", 4)):
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            engine.menu_state = MenuState.NONE
            engine.targeting_spell = None
        return False

    elif spell_type == "ray_of_frost":
        dx = tx - engine.player.x
        dy = ty - engine.player.y
        if dx == 0 and dy == 0:
            engine.messages.append("Ray of Frost: aim your cursor away from yourself!")
            return False
        unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
        unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0
        _spell_ray_of_frost(engine, unit_dx, unit_dy)
        ability_id = _consume_ability_charge(engine)
        if ability_id:
            engine._gain_spell_xp(ability_id)
        count = spell.get("count", 1) - 1
        if count > 0:
            spell["count"] = count
            engine.targeting_cursor = engine._get_smart_targeting_cursor()
            engine.messages.append(f"Ray of Frost! {count} shot(s) remaining \u2014 aim again.")
        else:
            engine.menu_state = MenuState.NONE
            engine.targeting_spell = None
        return False

    elif spell_type == "firebolt":
        if _spell_firebolt(engine, tx, ty):
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            count = spell.get("count", 1) - 1
            if count > 0:
                spell["count"] = count
                engine.targeting_cursor = engine._get_smart_targeting_cursor()
                engine.messages.append(f"Firebolt! {count} shot(s) remaining \u2014 pick next target.")
            else:
                engine.menu_state = MenuState.NONE
                engine.targeting_spell = None
        return False

    elif spell_type == "arcane_missile":
        if _spell_arcane_missile(engine, tx, ty):
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            count = spell.get("count", 1) - 1
            if count > 0:
                spell["count"] = count
                engine.targeting_cursor = engine._get_smart_targeting_cursor()
                engine.messages.append(f"Magic Missile! {count} shot(s) remaining \u2014 pick next target.")
            else:
                engine.menu_state = MenuState.NONE
                engine.targeting_spell = None
        return False

    elif spell_type == "breath_fire":
        if _spell_breath_fire(engine, tx, ty):
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            engine.menu_state = MenuState.NONE
            engine.targeting_spell = None
        return False

    engine.menu_state = MenuState.NONE
    engine.targeting_spell = None
    return False


# ======================================================================
# Dosidos spell implementations
# ======================================================================

def _dist_sq(x0: int, y0: int, x1: int, y1: int) -> int:
    return (x0 - x1) ** 2 + (y0 - y1) ** 2


def _ray_tiles(engine, start_x: int, start_y: int, dx: int, dy: int, max_dist: int = 10):
    """Yield (x, y) tiles along a ray starting one step from origin, stopping before walls."""
    tiles = []
    x, y = start_x + dx, start_y + dy
    for _ in range(max_dist):
        if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
            break
        if engine.dungeon.is_terrain_blocked(x, y):
            break
        tiles.append((x, y))
        x += dx
        y += dy
    return tiles


def _trace_projectile(engine, x0: int, y0: int, tx: int, ty: int):
    """Trace a projectile from (x0,y0) toward (tx,ty) via linear interpolation.
    Returns the first alive monster Entity hit, or None if blocked by wall first."""
    dx = tx - x0
    dy = ty - y0
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return None
    for step in range(1, steps + 1):
        x = round(x0 + dx * step / steps)
        y = round(y0 + dy * step / steps)
        if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
            return None
        if engine.dungeon.is_terrain_blocked(x, y):
            return None
        for entity in engine.dungeon.get_entities_at(x, y):
            if entity.entity_type == "monster" and entity.alive:
                return entity
    return None


def _spell_dimension_door(engine, tx: int, ty: int) -> bool:
    """Teleport to target explored tile. Returns True on success."""
    if not engine.dungeon.explored[ty, tx]:
        engine.messages.append("Dimension Door: you haven't explored that tile yet.")
        return False
    if engine.dungeon.is_terrain_blocked(tx, ty):
        engine.messages.append("Dimension Door: that tile is blocked by a wall.")
        return False
    blocker = engine.dungeon.get_blocking_entity_at(tx, ty)
    if blocker is not None and blocker is not engine.player:
        engine.messages.append(f"Dimension Door: {blocker.name} is in the way!")
        return False
    engine.dungeon.move_entity(engine.player, tx, ty)
    engine._compute_fov()
    engine.messages.append(f"Dimension Door! You blink to ({tx}, {ty}).")
    engine._pickup_items_at(tx, ty)
    return True


def _spell_chain_lightning(engine, tx: int, ty: int, total_hits: int) -> bool:
    """Chain lightning hitting total_hits times, bouncing to the nearest monster each time.
    Returns True if the spell fired, False if the target was invalid."""
    stsmt = engine.player_stats.effective_street_smarts
    tlr   = engine.player_stats.effective_tolerance
    damage = 5 + stsmt + tlr + _get_wizard_bomb_bonus(engine)

    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Chain Lightning: no enemy at that tile!")
        return False
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Chain Lightning: target not in line of sight!")
        return False

    engine.messages.append(f"Chain Lightning! ({total_hits} hits, {damage} dmg each)")
    for i in range(total_hits):
        if target is None:
            break
        last_x, last_y = target.x, target.y
        _deal_damage(engine, damage, target)
        hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
        engine.messages.append(f"  Lightning hits {target.name} for {damage} ({hp_disp})")
        if not target.alive:
            engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
        if i < total_hits - 1:
            living = [e for e in engine.dungeon.get_monsters() if e.alive]
            if not living:
                break
            BOUNCE_DIST_SQ = 4  # 2-tile Euclidean radius (2^2 = 4)
            candidates = [e for e in living
                          if _dist_sq(last_x, last_y, e.x, e.y) <= BOUNCE_DIST_SQ]
            if not candidates:
                engine.messages.append("  Lightning fizzles \u2014 no target in range to chain!")
                break
            min_d = min(_dist_sq(last_x, last_y, e.x, e.y) for e in candidates)
            nearest = [e for e in candidates
                       if _dist_sq(last_x, last_y, e.x, e.y) == min_d]
            target = random.choice(nearest)
    return True


def _spell_ray_of_frost(engine, dx: int, dy: int) -> None:
    """Fire a Ray of Frost in direction (dx, dy). Deals 12+BKSMT damage to all monsters
    in a 10-tile line; stops at walls."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = 12 + bksmt + _get_wizard_bomb_bonus(engine)
    tiles  = _ray_tiles(engine, engine.player.x, engine.player.y, dx, dy, max_dist=10)
    hit_count = 0
    for x, y in tiles:
        for entity in list(engine.dungeon.get_entities_at(x, y)):
            if entity.entity_type == "monster" and entity.alive:
                _deal_damage(engine, damage, entity)
                hp_disp = f"{entity.hp}/{entity.max_hp}" if entity.alive else "dead"
                engine.messages.append(
                    f"Ray of Frost hits {entity.name} for {damage} dmg! ({hp_disp})"
                )
                hit_count += 1
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)
    if hit_count == 0:
        engine.messages.append("Ray of Frost \u2014 no targets in that direction.")


def _spell_warp(engine) -> None:
    """Teleport to a random passable, unoccupied floor tile."""
    candidates = []
    for room in engine.dungeon.rooms:
        for rx, ry in room.floor_tiles(engine.dungeon):
            if engine.dungeon.is_terrain_blocked(rx, ry):
                continue
            blocker = engine.dungeon.get_blocking_entity_at(rx, ry)
            if blocker is None or blocker is engine.player:
                if not (rx == engine.player.x and ry == engine.player.y):
                    candidates.append((rx, ry))
    if not candidates:
        engine.messages.append("Warp: nowhere to go!")
        return
    tx, ty = random.choice(candidates)
    engine.dungeon.move_entity(engine.player, tx, ty)
    engine._compute_fov()
    engine.messages.append("Warp! You vanish and reappear elsewhere on the floor.")
    engine._pickup_items_at(tx, ty)


def _player_ignite_duration(engine) -> int:
    """Base ignite duration the player applies. +5 with Neva Burn Out (Pyromania lv4)."""
    base = 5
    pyro = engine.skills.get("Pyromania")
    if pyro and pyro.level >= 4:
        base += 5
    return base


def _spell_firebolt(engine, tx: int, ty: int) -> bool:
    """Fire a Firebolt toward (tx, ty). Blocked by walls and entities. Returns True on hit."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = 10 + bksmt + _get_wizard_bomb_bonus(engine)
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Firebolt: no line of sight to that tile.")
        return False
    hit = _trace_projectile(engine, engine.player.x, engine.player.y, tx, ty)
    if hit is None:
        engine.messages.append("Firebolt fizzles \u2014 no target in path!")
        return False
    _deal_damage(engine, damage, hit)
    ignite_eff = effects.apply_effect(hit, engine, "ignite", duration=_player_ignite_duration(engine), stacks=1, silent=True)
    stacks = ignite_eff.stacks if ignite_eff else 1
    hp_disp = f"{hit.hp}/{hit.max_hp}" if hit.alive else "dead"
    engine.messages.append(
        f"Firebolt! {hit.name} takes {damage} dmg and ignites (x{stacks})! ({hp_disp})"
    )
    if not hit.alive:
        engine.event_bus.emit("entity_died", entity=hit, killer=engine.player)
    return True


def _spell_arcane_missile(engine, tx: int, ty: int) -> bool:
    """Fire an Arcane Missile at a visible target at (tx, ty). Returns True on hit."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = math.ceil(8 + bksmt / 2 + _get_wizard_bomb_bonus(engine))
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Arcane Missile: target not in view.")
        return False
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Arcane Missile: no visible enemy there.")
        return False
    _deal_damage(engine, damage, target)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(f"Arcane Missile! {target.name} takes {damage} dmg! ({hp_disp})")
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    return True


def _spell_breath_fire(engine, tx: int, ty: int) -> bool:
    """Breathe a cone of fire toward (tx, ty). Cone: 5-tile range, 90 deg spread.
    Affected by walls, passes through enemies."""
    bksmt = engine.player_stats.effective_book_smarts
    damage = 20 + bksmt + _get_wizard_bomb_bonus(engine)

    # Determine center direction toward target
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        engine.messages.append("Breath Fire: aim away from yourself!")
        return False

    # Normalize to unit vector
    dist = math.sqrt(dx*dx + dy*dy)
    center_dx = dx / dist
    center_dy = dy / dist

    # Get cone tiles (5-tile range, 90 deg spread)
    cone_tiles = _get_cone_tiles(engine, engine.player.x, engine.player.y, center_dx, center_dy, range_dist=5)

    if not cone_tiles:
        engine.messages.append("Breath Fire: no valid targets!")
        return False

    # Visual: fire ripple from player through cone
    if engine.sdl_overlay:
        engine.sdl_overlay.add_tile_flash_ripple(
            cone_tiles, engine.player.x, engine.player.y,
            color=(255, 120, 30), duration=0.8, ripple_speed=0.06,
        )

    # Apply damage to all enemies in cone
    hit_targets = set()
    for cx, cy in cone_tiles:
        for entity in engine.dungeon.get_entities_at(cx, cy):
            if entity.entity_type == "monster" and entity.alive and entity not in hit_targets:
                _deal_damage(engine, damage, entity)
                effects.apply_effect(entity, engine, "ignite", duration=_player_ignite_duration(engine), stacks=3, silent=True)
                hit_targets.add(entity)

    if not hit_targets:
        engine.messages.append("Breath Fire: no enemies in range!")
        return True  # still fired (visual + charge consumed)

    engine.messages.append(f"You breathe a cone of fire! {len(hit_targets)} enemy(ies) engulfed.")
    for entity in hit_targets:
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)

    return True


def _get_cone_tiles(engine, cx: int, cy: int, dir_x: float, dir_y: float,
                    range_dist: int = 5, half_angle_deg: float = 27,
                    min_spread: int = 1):
    """Get all tiles in a cone centered on *direction* from (cx, cy).

    Parameters
    ----------
    range_dist : how far the cone extends (in tiles).
    half_angle_deg : half the total cone angle (e.g. 30 → 60° cone).
    min_spread : minimum perpendicular spread at every distance
                 (1 = always at least 3 tiles wide; 0 = can be single-tile).

    Uses angle-based inclusion: for every tile within range, check if the
    angle from (cx,cy) to that tile falls within half_angle_deg of the
    direction vector.  This guarantees no gaps on diagonals.
    Blocked by walls, passes through enemies.
    """
    tiles = []
    half_rad = math.radians(half_angle_deg)
    cos_half = math.cos(half_rad)
    dir_len = math.sqrt(dir_x * dir_x + dir_y * dir_y)
    if dir_len == 0:
        return tiles
    ndx = dir_x / dir_len
    ndy = dir_y / dir_len

    for dy in range(-range_dist, range_dist + 1):
        for dx in range(-range_dist, range_dist + 1):
            if dx == 0 and dy == 0:
                continue
            tx, ty = cx + dx, cy + dy
            if not (0 <= tx < DUNGEON_WIDTH and 0 <= ty < DUNGEON_HEIGHT):
                continue
            # Chebyshev distance for range check
            dist = max(abs(dx), abs(dy))
            if dist > range_dist:
                continue
            # Angle check: dot product of normalized vectors
            tile_dist = math.sqrt(dx * dx + dy * dy)
            dot = (dx * ndx + dy * ndy) / tile_dist
            # Must be in the forward hemisphere
            if dot <= 0:
                continue
            # min_spread: always include tiles within 1 Chebyshev step of center line
            if dot < cos_half:
                # Check min_spread fallback: is this tile within min_spread
                # of the center line at this distance?
                if min_spread > 0:
                    # Project onto perpendicular axis
                    perp = abs(-ndy * dx + ndx * dy)
                    if perp > min_spread + 0.5:
                        continue
                else:
                    continue
            if engine.dungeon.is_terrain_blocked(tx, ty):
                continue
            tiles.append((tx, ty))

    return tiles


def _spell_zap(engine, tx: int, ty: int) -> bool:
    """Zap a target within 4 tiles. Dmg: 5 + Book-Smarts/2. Applies 1 Shocked stack."""
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Zap: no line of sight.")
        return False
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Zap: no enemy there.")
        return False
    dist = math.sqrt((tx - engine.player.x) ** 2 + (ty - engine.player.y) ** 2)
    if dist > 4.0:
        engine.messages.append("Zap: target out of range (max 4 tiles).")
        return False
    bksmt = engine.player_stats.effective_book_smarts
    damage = 5 + bksmt // 2
    _deal_damage(engine, damage, target)
    effects.apply_effect(target, engine, "shocked", duration=10, stacks=1, silent=True)
    shocked_eff = next(
        (e for e in target.status_effects if getattr(e, 'id', '') == 'shocked'), None
    )
    stacks = shocked_eff.stacks if shocked_eff else 1
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Zap! {target.name} takes {damage} dmg! Shocked x{stacks}. ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    return True


def _spell_corn_dog(engine, tx: int, ty: int) -> bool:
    """Corn Dog an adjacent enemy: 5 armor-piercing damage + stun 4 turns."""
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Corn Dog: no enemy there.")
        return False
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))  # Chebyshev
    if dist > 1:
        engine.messages.append("Corn Dog: must be adjacent to target.")
        return False
    _deal_damage(engine, 5, target)
    effects.apply_effect(target, engine, "stun", duration=4, silent=True)
    hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
    engine.messages.append(
        f"Corn Dog! {target.name} takes 5 dmg and is stunned for 4 turns! ({hp_disp})"
    )
    if not target.alive:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
    return True


def _spell_pry(engine, tx: int, ty: int) -> bool:
    """Pry an adjacent enemy: sets their defense to 0 for 10 turns."""
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Pry: no enemy there.")
        return False
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist > 1:
        engine.messages.append("Pry: must be adjacent to target.")
        return False
    effects.apply_effect(target, engine, "cripple_armor", duration=10)
    engine.messages.append(
        f"You pry open {target.name}'s defenses! Their armor is crippled for 10 turns!"
    )
    engine.ability_cooldowns["pry"] = 50
    return True


def _spell_lesser_cloudkill(engine, tx: int, ty: int) -> bool:
    """Lesser Cloudkill 3x3 AoE (cannot include player). Damage + debuff."""
    px, py = engine.player.x, engine.player.y
    if abs(tx - px) <= 1 and abs(ty - py) <= 1:
        engine.messages.append("Lesser Cloudkill: can't target an area that includes yourself!")
        return False
    bksmt = engine.player_stats.effective_book_smarts
    swag = engine.player_stats.effective_swagger
    damage = max(1, 25 - swag + bksmt // 2)
    tiles = _get_lesser_cloudkill_affected_tiles(engine, tx, ty)
    hit_count = 0
    hit_entities = []
    for x, y in tiles:
        for entity in engine.dungeon.get_entities_at(x, y):
            if entity.entity_type == "monster" and entity.alive and entity not in hit_entities:
                hit_entities.append(entity)
                _deal_damage(engine, damage, entity)
                effects.apply_effect(entity, engine, "lesser_cloudkill", duration=10, silent=True)
                hit_count += 1
    engine.messages.append(
        f"Lesser Cloudkill! {hit_count} enem{'y' if hit_count == 1 else 'ies'} hit "
        f"for {damage} dmg and are now Smelly."
    )
    for entity in hit_entities:
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)
    return True


def _get_lesser_cloudkill_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Return all non-terrain-blocked tiles in a 3x3 area centred on (tx, ty)."""
    tiles = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x, y = tx + dx, ty + dy
            if 0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT:
                if not engine.dungeon.is_terrain_blocked(x, y):
                    tiles.append((x, y))
    return tiles


def _get_wizard_bomb_bonus(engine) -> int:
    """Return spell damage bonus from Wizard Mind-Bomb effect + total spell damage."""
    bonus = 0
    for effect in engine.player.status_effects:
        if getattr(effect, 'id', '') == 'wizard_mind_bomb':
            bonus += engine.player_stats.effective_book_smarts
    bonus += engine.player_stats.total_spell_damage
    return bonus


# ======================================================================
# Spell targeting visualization
# ======================================================================

def get_spell_affected_tiles(engine, spell_type: str, tx: int, ty: int) -> list[tuple[int, int]]:
    """Get list of tiles that will be affected by a spell at target location (tx, ty).
    Used for rendering visualization during targeting mode."""
    if spell_type == "breath_fire":
        return _get_breath_fire_affected_tiles(engine, tx, ty)
    elif spell_type == "ray_of_frost":
        return _get_ray_of_frost_affected_tiles(engine, tx, ty)
    elif spell_type == "chain_lightning":
        # Single target, but show it
        if any(e for e in engine.dungeon.get_entities_at(tx, ty) if e.entity_type == "monster" and e.alive):
            return [(tx, ty)]
        return []
    elif spell_type in ("firebolt", "arcane_missile", "dimension_door"):
        # Single target spells
        if any(e for e in engine.dungeon.get_entities_at(tx, ty) if e.entity_type == "monster" and e.alive):
            return [(tx, ty)]
        return []
    elif spell_type == "lesser_cloudkill":
        return _get_lesser_cloudkill_affected_tiles(engine, tx, ty)
    return []


def get_targeting_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Get affected tiles for the current targeting mode, delegating to the ability definition."""
    defn = _get_targeting_ability_def(engine)
    if defn is not None:
        if defn.get_affected_tiles is not None:
            return defn.get_affected_tiles(engine, tx, ty)
        # Single-target default: highlight tile if enemy is present
        if (engine.dungeon.visible[ty, tx] and
                any(e for e in engine.dungeon.get_entities_at(tx, ty)
                    if e.entity_type == "monster" and e.alive)):
            return [(tx, ty)]
        return []
    # Fallback: item-triggered spells (Dosidos), dispatch by spell type string
    spell_type = engine.targeting_spell.get("type", "") if engine.targeting_spell else ""
    return get_spell_affected_tiles(engine, spell_type, tx, ty)


def _get_breath_fire_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Get all tiles in the breath fire cone."""
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        return []

    dist = math.sqrt(dx*dx + dy*dy)
    center_dx = dx / dist
    center_dy = dy / dist

    return _get_cone_tiles(engine, engine.player.x, engine.player.y, center_dx, center_dy, range_dist=5)


def _get_curse_of_ham_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Get all tiles in the Curse of Ham cone (range 3, 60° spread)."""
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        return []
    dist = math.sqrt(dx * dx + dy * dy)
    return _get_cone_tiles(
        engine, engine.player.x, engine.player.y,
        dx / dist, dy / dist,
        range_dist=3, half_angle_deg=30, min_spread=0,
    )


def _spell_curse_of_ham(engine, tx: int, ty: int) -> bool:
    """Apply Curse of Ham to all monsters in a cone (range 3, 60° spread)."""
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        engine.messages.append("Curse of Ham: aim away from yourself!")
        return False
    dist = math.sqrt(dx * dx + dy * dy)
    cone_tiles = _get_cone_tiles(
        engine, engine.player.x, engine.player.y,
        dx / dist, dy / dist,
        range_dist=3, half_angle_deg=30, min_spread=0,
    )
    if not cone_tiles:
        engine.messages.append("Curse of Ham: no valid tiles!")
        return False

    cursed = []
    for cx, cy in cone_tiles:
        for entity in engine.dungeon.get_entities_at(cx, cy):
            if entity.entity_type == "monster" and entity.alive and entity not in cursed:
                result = effects.apply_effect(entity, engine, "curse_of_ham", silent=True)
                if result is not None:
                    cursed.append(entity)
                    # +10 Blackkk Magic XP per cursed target
                    adjusted_xp = round(10 * engine.player_stats.xp_multiplier)
                    engine.skills.gain_potential_exp(
                        "Blackkk Magic", adjusted_xp,
                        engine.player_stats.effective_book_smarts,
                        briskness=engine.player_stats.total_briskness,
                    )

    if not cursed:
        engine.messages.append("Curse of Ham: no enemies cursed!")
        return False

    names = ", ".join(e.name for e in cursed)
    engine.messages.append([
        ("Curse of Ham! ", (140, 60, 180)),
        (f"{names} cursed!", (200, 160, 255)),
    ])
    return True


def _spell_curse_of_dot(engine, tx: int, ty: int) -> bool:
    """Apply Curse of DOT to a single monster at the target tile."""
    target = None
    for entity in engine.dungeon.get_entities_at(tx, ty):
        if entity.entity_type == "monster" and entity.alive and not getattr(entity, "is_summon", False):
            target = entity
            break
    if target is None:
        engine.messages.append("Curse of DOT: no valid target!")
        return False

    result = effects.apply_effect(target, engine, "curse_dot", stacks=0, silent=True)
    if result is None:
        engine.messages.append("Curse of DOT: target is already cursed!")
        return False

    # +20 Blackkk Magic XP on infliction
    adjusted_xp = round(20 * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Blackkk Magic", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness,
    )
    engine.messages.append([
        ("Curse of DOT! ", (120, 40, 160)),
        (f"{target.name} is cursed!", (180, 120, 220)),
    ])
    return True


def _spell_curse_of_covid(engine, tx: int, ty: int) -> bool:
    """Apply Curse of COVID to a single monster at the target tile."""
    target = None
    for entity in engine.dungeon.get_entities_at(tx, ty):
        if entity.entity_type == "monster" and entity.alive and not getattr(entity, "is_summon", False):
            target = entity
            break
    if target is None:
        engine.messages.append("Curse of COVID: no valid target!")
        return False

    result = effects.apply_effect(target, engine, "curse_covid", stacks=0, silent=True)
    if result is None:
        engine.messages.append("Curse of COVID: target is already cursed!")
        return False

    # +20 Blackkk Magic XP on infliction
    adjusted_xp = round(20 * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Blackkk Magic", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness,
    )
    engine.messages.append([
        ("Curse of COVID! ", (80, 180, 60)),
        (f"{target.name} is cursed!", (140, 220, 100)),
    ])
    return True


def _get_ray_of_frost_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Get all tiles in the ray of frost line."""
    dx = tx - engine.player.x
    dy = ty - engine.player.y
    if dx == 0 and dy == 0:
        return []

    steps = max(abs(dx), abs(dy))
    unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
    unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0

    return _ray_tiles(engine, engine.player.x, engine.player.y, unit_dx, unit_dy, max_dist=10)


# ======================================================================
# Ability system
# ======================================================================

def grant_ability(engine, ability_id: str):
    """Grant the player an ability by ID. Silently ignored if already owned."""
    if ability_id not in ABILITY_REGISTRY:
        return
    if any(a.ability_id == ability_id for a in engine.player_abilities):
        return
    defn = ABILITY_REGISTRY[ability_id]
    engine.player_abilities.append(AbilityInstance(ability_id, defn))
    engine.messages.append(f"Ability unlocked: {defn.name}!")


def revoke_ability(engine, ability_id: str):
    """Remove a granted ability. Does NOT reset its cooldown."""
    engine.player_abilities = [a for a in engine.player_abilities if a.ability_id != ability_id]


def grant_ability_charges(engine, ability_id: str, n: int, silent: bool = False) -> None:
    """Add n charges of a spell ability. Creates the ability slot if not yet owned."""
    defn = ABILITY_REGISTRY.get(ability_id)
    if defn is None:
        return
    inst = next((a for a in engine.player_abilities if a.ability_id == ability_id), None)
    if inst is None:
        inst = AbilityInstance(ability_id, defn)
        if defn.charge_type != ChargeType.FLOOR_ONLY:
            inst.charges_remaining = 0  # start at 0; we'll add n below
        engine.player_abilities.append(inst)
    if defn.charge_type == ChargeType.FLOOR_ONLY:
        inst.floor_charges_remaining += n
        display_count = inst.floor_charges_remaining
    else:
        inst.charges_remaining += n
        display_count = inst.charges_remaining
    if not silent:
        engine.messages.append(
            f"+{n}x {defn.name} added to abilities! ({display_count} charges)"
        )


def _consume_ability_charge(engine) -> str | None:
    """Consume one charge from the ability that triggered the current targeting session.
    Returns the ability_id of the consumed ability, or None."""
    idx = engine.targeting_ability_index
    ability_id = None
    if idx is not None and 0 <= idx < len(engine.player_abilities):
        inst = engine.player_abilities[idx]
        ability_id = inst.ability_id
        consumed = inst.consume(engine)
        defn = ABILITY_REGISTRY.get(ability_id)
        if defn and _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        # Curse charge steal: when a curse charge is consumed, steal 1
        # charge from each other curse ability that has charges.
        if consumed and defn and defn.is_curse:
            _curse_charge_steal(engine, inst, defn)
    engine.targeting_ability_index = None
    # Gatting L1: targeted ability use resets consecutive shot tracker
    engine.gatting_consecutive_target_id = None
    engine.gatting_consecutive_count = 0
    return ability_id


def _curse_charge_steal(engine, caster_inst, caster_defn):
    """Steal 1 charge from each other curse ability and give them to the caster."""
    stolen = 0
    donor_names = []
    for other_inst in engine.player_abilities:
        if other_inst is caster_inst:
            continue
        other_defn = ABILITY_REGISTRY.get(other_inst.ability_id)
        if other_defn is None or not other_defn.is_curse:
            continue
        # Check if the donor has charges to steal
        has = other_inst.charges_remaining > 0 or other_inst.floor_charges_remaining > 0
        if not has:
            continue
        # Steal 1 charge from the donor
        if other_inst.floor_charges_remaining > 0:
            other_inst.floor_charges_remaining -= 1
        elif other_inst.charges_remaining > 0:
            other_inst.charges_remaining -= 1
        # Give 1 charge to the caster
        if caster_defn.charge_type in (ChargeType.PER_FLOOR, ChargeType.FLOOR_ONLY):
            caster_inst.floor_charges_remaining += 1
        elif caster_defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
            caster_inst.charges_remaining += 1
        stolen += 1
        donor_names.append(other_defn.name)
    if stolen > 0:
        names = ", ".join(donor_names)
        engine.messages.append([
            ("Curse Synergy! ", (160, 80, 220)),
            (f"+{stolen} charge stolen from {names}", (200, 160, 255)),
        ])


def _action_toggle_abilities(engine, _action):
    if engine.menu_state == MenuState.NONE:
        engine.menu_state = MenuState.ABILITIES
        engine.abilities_cursor = 0
    elif engine.menu_state == MenuState.ABILITIES:
        engine.menu_state = MenuState.NONE
        engine.selected_ability_index = None
    return False


def _get_usable_abilities(engine):
    """Build filtered list of usable abilities (same as render logic)."""
    usable = []
    for inst in engine.player_abilities:
        if inst.can_use():
            usable.append(inst)
    return usable


def _handle_abilities_menu_input(engine, action):
    """Handle input while the abilities menu is open."""
    action_type = action.get("type")

    if action_type in ("close_menu", "toggle_abilities"):
        engine.menu_state = MenuState.NONE
        engine.selected_ability_index = None
        return False

    usable_abilities = _get_usable_abilities(engine)
    n = len(usable_abilities)

    # Arrow key cursor navigation
    if action_type == "move" and n > 0:
        dy = action.get("dy", 0)
        if dy != 0:
            engine.abilities_cursor = (engine.abilities_cursor + dy) % n
        return False

    # Enter key activates cursor selection
    if action_type == "confirm_target" and n > 0:
        if 0 <= engine.abilities_cursor < n:
            target_ability = usable_abilities[engine.abilities_cursor]
            actual_index = engine.player_abilities.index(target_ability)
            return _execute_ability(engine, actual_index)
        return False

    # Number key shortcuts (existing behavior)
    if action_type == "select_action":
        idx = action["index"]
        if 0 <= idx < n:
            target_ability = usable_abilities[idx]
            actual_index = engine.player_abilities.index(target_ability)
            return _execute_ability(engine, actual_index)
        return False

    return False


def _check_rad_cost(engine, defn) -> bool:
    """Check if player can afford rad_cost. Returns True if ok, False if blocked."""
    cost = getattr(defn, 'rad_cost', 0)
    if cost <= 0:
        return True
    if engine.player.radiation < cost:
        engine.messages.append(f"{defn.name}: not enough radiation ({engine.player.radiation}/{cost})!")
        return False
    return True


def _pay_rad_cost(engine, defn) -> bool:
    """Deduct rad_cost from player. Returns True if charge should be preserved (free cast).

    Free cast: if player has 100+ rad and ability has rad_cost, the rad is still
    spent but the ability charge is NOT consumed.
    Grants Nuclear Research XP for radiation spent.
    """
    cost = getattr(defn, 'rad_cost', 0)
    if cost <= 0:
        return False
    free_charge = engine.player.radiation >= 100
    actual = min(cost, engine.player.radiation)
    engine.player.radiation = max(0, engine.player.radiation - cost)
    # Grant Nuclear Research XP: 2 per point of rad spent
    if actual > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Nuclear Research", actual * 2, bksmt)
    if free_charge:
        engine.messages.append([
            ("Overcharged! ", (120, 220, 80)),
            ("Charge preserved (100+ rad)", (160, 255, 120)),
        ])
    return free_charge


def _execute_ability(engine, index: int) -> bool:
    """Execute the ability at the given player_abilities index. Returns True if a turn is consumed."""
    if index < 0 or index >= len(engine.player_abilities):
        return False

    inst = engine.player_abilities[index]
    defn = ABILITY_REGISTRY.get(inst.ability_id)
    if defn is None:
        return False

    cd = engine.ability_cooldowns.get(inst.ability_id, 0)
    if cd > 0:
        engine.messages.append(f"{defn.name}: on cooldown ({cd} turns remaining)!")
        return False

    if not inst.can_use():
        engine.messages.append(f"{defn.name}: no charges remaining!")
        return False

    if not _check_rad_cost(engine, defn):
        return False

    engine.menu_state = MenuState.NONE
    engine.selected_ability_index = None
    # Track index so _execute_spell_at can consume the charge when the spell fires.
    engine.targeting_ability_index = index

    # ADJACENT targeting: quick-select from adjacent enemies
    if defn.target_type == TargetType.ADJACENT:
        return _enter_adjacent_ability_targeting(engine, index, defn)

    # ADJACENT_TILE targeting: press a directional key to pick an adjacent tile
    if defn.target_type == TargetType.ADJACENT_TILE:
        engine.menu_state = MenuState.ADJACENT_TILE_TARGETING
        engine.messages.append(f"{defn.name}: choose a direction (arrow keys / numpad). [Esc] cancel.")
        return False

    # SINGLE_ENEMY_LOS / LINE_FROM_PLAYER: enter cursor targeting mode
    if defn.target_type in (TargetType.SINGLE_ENEMY_LOS, TargetType.LINE_FROM_PLAYER):
        engine.targeting_spell = {"type": "ability_cursor"}
        engine.targeting_cursor = engine._get_smart_targeting_cursor()
        engine.menu_state = MenuState.TARGETING
        range_str = f" (range {int(defn.max_range)})" if defn.max_range else ""
        engine.messages.append(f"{defn.name}: aim with arrow keys, Enter to fire{range_str}. [Esc] cancel.")
        return False

    result = defn.execute(engine)
    if result:
        inst.consume(engine)
        if _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        engine.targeting_ability_index = None
        # Gatting L1: ability use resets consecutive shot tracker
        engine.gatting_consecutive_target_id = None
        engine.gatting_consecutive_count = 0
        # Grant Smartsness XP for spell abilities that executed immediately
        if defn.is_spell:
            engine._gain_spell_xp(inst.ability_id)
        else:
            engine._graffiti_proc_blue()
    # result == False means targeting mode was entered; charge consumed later in _execute_spell_at.
    return result


def _enter_adjacent_ability_targeting(engine, index: int, defn) -> bool:
    """Enter quick-select targeting for an ADJACENT ability.
    Auto-fires if exactly one adjacent enemy; otherwise enters entity targeting."""
    targets = _build_entity_target_list(engine, reach=1)
    if not targets:
        engine.messages.append(f"{defn.name}: no adjacent enemies!")
        engine.targeting_ability_index = None
        return False
    if len(targets) == 1:
        # Auto-target the single adjacent enemy
        target = targets[0]
        return _fire_adjacent_ability(engine, target.x, target.y)
    # Multiple targets: enter entity targeting quick-select
    engine.entity_target_list = targets
    engine.entity_target_index = 0
    engine.menu_state = MenuState.ENTITY_TARGETING
    return False


def _fire_adjacent_ability(engine, tx: int, ty: int) -> bool:
    """Execute the current adjacent ability at (tx, ty) and handle charge/cleanup."""
    index = engine.targeting_ability_index
    if index is None or index >= len(engine.player_abilities):
        return False
    inst = engine.player_abilities[index]
    defn = ABILITY_REGISTRY.get(inst.ability_id)
    if defn is None or defn.execute_at is None:
        engine.targeting_ability_index = None
        return False
    fired = defn.execute_at(engine, tx, ty)
    if fired:
        inst.consume(engine)
        if _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        engine.targeting_ability_index = None
        # Gatting L1: adjacent ability use resets consecutive shot tracker
        engine.gatting_consecutive_target_id = None
        engine.gatting_consecutive_count = 0
        if defn.is_spell:
            engine._gain_spell_xp(inst.ability_id)
        else:
            engine._graffiti_proc_blue()
        return True
    engine.targeting_ability_index = None
    return False


def _handle_adjacent_tile_targeting_input(engine, action) -> bool:
    """Handle input while in ADJACENT_TILE_TARGETING state.
    A directional key places the ability on the chosen adjacent tile; Esc cancels."""
    action_type = action.get("type")
    pending = getattr(engine, 'spray_paint_pending', None)

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.targeting_ability_index = None
        engine.spray_paint_pending = None
        return False

    if action_type == "move":
        dx = action.get("dx", 0)
        dy = action.get("dy", 0)
        if dx == 0 and dy == 0:
            return False
        tx = engine.player.x + dx
        ty = engine.player.y + dy
        # Validate: within bounds and not a wall
        if (tx < 0 or ty < 0 or tx >= engine.dungeon.width or ty >= engine.dungeon.height
                or engine.dungeon.is_terrain_blocked(tx, ty)):
            if pending:
                engine.messages.append("Can't spray on a wall.")
            else:
                engine.messages.append("Fire!: can't place fire on a wall.")
            return False

        # Spray paint item targeting
        if pending:
            engine.menu_state = MenuState.NONE
            _apply_spray_paint_tile(engine, tx, ty, pending)
            engine.spray_paint_pending = None
            engine.player.energy -= ENERGY_THRESHOLD
            engine._run_energy_loop()
            return True

        engine.menu_state = MenuState.NONE
        fired = _fire_adjacent_ability(engine, tx, ty)
        if fired and engine.running and engine.player.alive:
            engine.player.energy -= ENERGY_THRESHOLD
            engine._run_energy_loop()
        return fired

    return False


def _apply_spray_paint_tile(engine, tx: int, ty: int, pending: dict):
    """Apply spray paint to a tile and decrement item charges."""
    spray_type = pending["spray_type"]
    item_index = pending["item_index"]

    # Apply paint to dungeon tile (overrides any existing spray paint)
    engine.dungeon.spray_paint[(tx, ty)] = spray_type

    # Decrement charges on the item (Graffiti L1: 50% chance to preserve charge)
    item = engine.player.inventory[item_index]
    import random as _rng
    if engine.skills.get("Graffiti").level >= 1 and _rng.random() < 0.50:
        engine.messages.append([
            ("Taggin'! ", (255, 220, 80)),
            ("Spray charge preserved!", (200, 255, 200)),
        ])
    else:
        item.charges -= 1

    _SPRAY_COLORS = {"red": (255, 40, 40), "blue": (80, 140, 255), "green": (80, 255, 80)}
    color = _SPRAY_COLORS.get(spray_type, (200, 200, 200))
    engine.messages.append([
        ("You spray the tile ", (200, 200, 200)),
        (spray_type, color),
        ("!", (200, 200, 200)),
    ])

    # Graffiti XP
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Graffiti", 20, bksmt)
