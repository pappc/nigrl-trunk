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
    """Return the reach of the equipped weapon (1 = adjacent, 2+ = extended).
    Includes bonus reach from equipment (e.g. Cuban Link neck item)."""
    weapon = engine.equipment.get("weapon")
    base = 1
    if weapon:
        defn = get_item_def(weapon.item_id)
        base = defn.get("reach", 1)
    # Bonus reach from neck/feet/hat/rings
    bonus = 0
    if engine.neck:
        ndefn = get_item_def(engine.neck.item_id)
        if ndefn:
            bonus += ndefn.get("reach_bonus", 0)
    return base + bonus


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
                return result
            engine.targeting_ability_index = None
            return False

        if target.alive:
            engine.handle_attack(engine.player, target)
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
            if engine.targeting_spell.get("type") == "graffiti_gun_fire":
                return _execute_graffiti_gun_fire(engine, tx, ty)
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
    """Return True if (tx, ty) is within the current ability's max_range (0.0 = unlimited, Chebyshev distance).
    If the ability has a validate callable, use that instead."""
    # Graffiti gun: Chebyshev distance 6
    if engine.targeting_spell and engine.targeting_spell.get("type") == "graffiti_gun_fire":
        dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
        return 0 < dist <= 6
    defn = _get_targeting_ability_def(engine)
    if defn is None:
        return True
    # Ability-specific validate: None return = valid, string = invalid
    if defn.validate is not None:
        return defn.validate(engine, tx, ty) is None
    if defn.max_range == 0.0:
        return True
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    return dist <= defn.max_range


def _enter_spell_targeting(engine, spell_dict: dict) -> None:
    """Enter cursor targeting mode for a Dosidos spell cast."""
    engine.targeting_spell = dict(spell_dict)
    engine.targeting_item_index = None
    engine.targeting_cursor = engine._get_smart_targeting_cursor()
    engine.menu_state = MenuState.TARGETING


# ======================================================================
# Spell Echo (Smartsness L4)
# ======================================================================

def _try_spell_echo_targeted(engine, defn, tx, ty):
    """Spell Echo: 15% chance for targeted spell to fire again at 50% damage.
    Echo can chain. Retargets to random nearby enemy if target is dead.
    Skips channeled spells."""
    import random as _rng
    if engine.skills.get("Smartsness").level < 4:
        return
    if not defn.is_spell:
        return
    # Skip channeled spells
    if engine._channel is not None:
        return

    while _rng.random() < 0.15:
        # Find target — retarget if dead
        target = engine.dungeon.get_blocking_entity_at(tx, ty)
        if target is None or not getattr(target, 'alive', False) or target is engine.player:
            # Retarget: random living monster within 3 tiles of original target
            candidates = [
                m for m in engine.dungeon.get_monsters()
                if m.alive and max(abs(m.x - tx), abs(m.y - ty)) <= 3
            ]
            if not candidates:
                engine.messages.append([
                    ("Spell Echo fizzles! ", (180, 140, 255)),
                    ("No targets nearby.", (150, 150, 180)),
                ])
                return
            new_target = _rng.choice(candidates)
            tx, ty = new_target.x, new_target.y

        # Store and halve spell damage for the echo
        old_spell_dmg = engine.player_stats.total_spell_damage
        engine._spell_echo_half_damage = True
        defn.execute_at(engine, tx, ty)
        engine._spell_echo_half_damage = False

        engine.messages.append([
            ("Spell Echo! ", (180, 140, 255)),
            ("The spell fires again!", (220, 200, 255)),
        ])
        if engine.sdl_overlay:
            engine.sdl_overlay.add_tile_flash_ripple(
                [(tx, ty)], tx, ty,
                color=(180, 140, 255), duration=0.5,
            )


def _try_spell_echo_self(engine, defn):
    """Spell Echo for self-cast spells. Same 15% chain, no retargeting needed."""
    import random as _rng
    if engine.skills.get("Smartsness").level < 4:
        return
    if not defn.is_spell:
        return
    if engine._channel is not None:
        return

    while _rng.random() < 0.15:
        engine._spell_echo_half_damage = True
        defn.execute(engine)
        engine._spell_echo_half_damage = False
        engine.messages.append([
            ("Spell Echo! ", (180, 140, 255)),
            ("The spell fires again!", (220, 200, 255)),
        ])


# ======================================================================
# Spellweaver (Smartsness L5)
# ======================================================================

def _spellweaver_before(engine, defn):
    """Check and activate Spellweaver +30% damage bonus before a spell fires."""
    engine._spellweaver_active = False
    if engine.skills.get("Smartsness").level < 5:
        return
    if not defn.is_spell:
        return
    ability_id = defn.ability_id
    last = engine._spellweaver_last_spell
    last_turn = engine._spellweaver_last_turn
    if last is not None and last != ability_id and (engine.turn - last_turn) <= 5:
        engine._spellweaver_active = True


def _spellweaver_after(engine, defn):
    """Record spell cast for Spellweaver tracking. Show message if bonus was active."""
    if not defn.is_spell:
        return
    if getattr(engine, '_spellweaver_active', False):
        engine.messages.append([
            ("Spellweaver! ", (200, 180, 255)),
            ("+30% damage!", (255, 220, 255)),
        ])
        engine._spellweaver_active = False
    engine._spellweaver_last_spell = defn.ability_id
    engine._spellweaver_last_turn = engine.turn


# ======================================================================
# Spell execution and dispatch
# ======================================================================

def _execute_spell_at(engine, tx: int, ty: int) -> bool:
    """Dispatch spell execution at (tx, ty).
    If the current ability has an execute_at, call it and handle charge/menu cleanup.
    Otherwise fall back to _execute_dosidos_spell_at for item-triggered spells."""
    defn = _get_targeting_ability_def(engine)
    if defn is not None and defn.execute_at is not None:
        _spellweaver_before(engine, defn)
        fired = defn.execute_at(engine, tx, ty)
        if fired:
            _spellweaver_after(engine, defn)
            ability_id = _consume_ability_charge(engine)
            if ability_id:
                engine._gain_spell_xp(ability_id)
            _try_spell_echo_targeted(engine, defn, tx, ty)
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

    elif spell_type == "fireball":
        if _spell_fireball(engine, tx, ty):
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
    bksmt = engine.player_stats.effective_book_smarts
    damage = 5 + bksmt + engine.player_stats.total_spell_damage

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
    hit_entities = set()
    for i in range(total_hits):
        if target is None:
            break
        if id(target) in hit_entities:
            break
        hit_entities.add(id(target))
        last_x, last_y = target.x, target.y
        _deal_damage(engine, damage, target)
        from xp_progression import _gain_elementalist_xp
        _gain_elementalist_xp(engine, target, damage, "lightning")
        hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
        engine.messages.append(f"  Lightning hits {target.name} for {damage} ({hp_disp})")
        from xp_progression import _gain_elemental_spell_xp
        _gain_elemental_spell_xp(engine, "chain_lightning", damage)
        if not target.alive:
            engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
        if i < total_hits - 1:
            living = [e for e in engine.dungeon.get_monsters()
                      if e.alive and id(e) not in hit_entities]
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
    """Fire a Ray of Frost beam in direction (dx, dy). Channeled: fires immediately,
    then up to 2 more times if the player presses Wait.
    Dmg per beam: random(6,12) + BKS/2 + Wizard Mind-Bomb bonus."""
    _ray_of_frost_beam(engine, dx, dy)
    # Start channel for 2 more ticks (3 total beams including this one)
    engine.start_channel("ray_of_frost", 2, {"dx": dx, "dy": dy})


def _ray_of_frost_beam(engine, dx: int, dy: int) -> None:
    """Fire a single Ray of Frost beam. Called on initial cast and each channel tick."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = random.randint(6, 12) + bksmt // 2 + engine.player_stats.total_spell_damage
    tiles  = _ray_tiles(engine, engine.player.x, engine.player.y, dx, dy, max_dist=10)
    hit_count = 0
    for x, y in tiles:
        for entity in list(engine.dungeon.get_entities_at(x, y)):
            if entity.entity_type == "monster" and entity.alive:
                _deal_damage(engine, damage, entity)
                from xp_progression import _gain_elementalist_xp
                _gain_elementalist_xp(engine, entity, damage, "cold")
                effects.apply_effect(entity, engine, "chill", duration=10, silent=True)
                hp_disp = f"{entity.hp}/{entity.max_hp}" if entity.alive else "dead"
                engine.messages.append(
                    f"Ray of Frost hits {entity.name} for {damage} dmg! +1 Chill ({hp_disp})"
                )
                hit_count += 1
                from xp_progression import _gain_elemental_spell_xp
                _gain_elemental_spell_xp(engine, "ray_of_frost", damage)
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
    """Base ignite duration the player applies. +5 with +3 CON perk (Pyromania lv4)."""
    base = 5
    pyro = engine.skills.get("Pyromania")
    if pyro and pyro.level >= 4:
        base += 5
    return base


def _spell_firebolt(engine, tx: int, ty: int) -> bool:
    """Fire a Firebolt toward (tx, ty). Blocked by walls and entities. Returns True on hit."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = 10 + bksmt + engine.player_stats.total_spell_damage
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Firebolt: no line of sight to that tile.")
        return False
    hit = _trace_projectile(engine, engine.player.x, engine.player.y, tx, ty)
    if hit is None:
        engine.messages.append("Firebolt fizzles \u2014 no target in path!")
        return False
    _deal_damage(engine, damage, hit)
    from xp_progression import _gain_elementalist_xp
    _gain_elementalist_xp(engine, hit, damage, "fire")
    ignite_eff = effects.apply_effect(hit, engine, "ignite", duration=_player_ignite_duration(engine), stacks=1, silent=True)
    stacks = ignite_eff.stacks if ignite_eff else 1
    hp_disp = f"{hit.hp}/{hit.max_hp}" if hit.alive else "dead"
    engine.messages.append(
        f"Firebolt! {hit.name} takes {damage} dmg and ignites (x{stacks})! ({hp_disp})"
    )
    from xp_progression import _gain_elemental_spell_xp
    _gain_elemental_spell_xp(engine, "firebolt", damage)
    if not hit.alive:
        engine.event_bus.emit("entity_died", entity=hit, killer=engine.player)
    return True


def _spell_arcane_missile(engine, tx: int, ty: int) -> bool:
    """Fire an Arcane Missile at a visible target at (tx, ty). Returns True on hit."""
    bksmt  = engine.player_stats.effective_book_smarts
    damage = math.ceil(8 + bksmt / 2 + engine.player_stats.total_spell_damage)
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
    damage = 10 + bksmt + engine.player_stats.total_spell_damage

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
                from xp_progression import _gain_elementalist_xp
                _gain_elementalist_xp(engine, entity, damage, "fire")
                effects.apply_effect(entity, engine, "ignite", duration=_player_ignite_duration(engine), stacks=3, silent=True)
                hit_targets.add(entity)

    if not hit_targets:
        engine.messages.append("Breath Fire: no enemies in range!")
        return True  # still fired (visual + charge consumed)

    engine.messages.append(f"You breathe a cone of fire! {len(hit_targets)} enemy(ies) engulfed.")
    from xp_progression import _gain_elemental_spell_xp
    _gain_elemental_spell_xp(engine, "breath_fire", damage * len(hit_targets))
    for entity in hit_targets:
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)

    return True


def _spell_fireball(engine, tx: int, ty: int) -> bool:
    """Fireball: projectile hits first enemy in path, then explodes in 2-tile radius AOE."""
    bksmt = engine.player_stats.effective_book_smarts
    damage = 15 + bksmt + engine.player_stats.total_spell_damage

    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Fireball: no line of sight to that tile.")
        return False

    # Trace projectile to find impact point and collect travel path
    x0, y0 = engine.player.x, engine.player.y
    dx_raw, dy_raw = tx - x0, ty - y0
    steps = max(abs(dx_raw), abs(dy_raw))
    travel_tiles = []
    hit = None
    impact_x, impact_y = tx, ty
    if steps > 0:
        for step in range(1, steps + 1):
            sx = round(x0 + dx_raw * step / steps)
            sy = round(y0 + dy_raw * step / steps)
            if not (0 <= sx < DUNGEON_WIDTH and 0 <= sy < DUNGEON_HEIGHT):
                break
            if engine.dungeon.is_terrain_blocked(sx, sy):
                break
            travel_tiles.append((sx, sy))
            for entity in engine.dungeon.get_entities_at(sx, sy):
                if entity.entity_type == "monster" and entity.alive:
                    hit = entity
                    impact_x, impact_y = sx, sy
                    break
            if hit:
                break
    if hit is None:
        impact_x, impact_y = tx, ty

    # Gather all tiles in 2-tile Chebyshev radius around impact
    aoe_tiles = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            ax, ay = impact_x + dx, impact_y + dy
            if max(abs(dx), abs(dy)) <= 2 and not engine.dungeon.is_terrain_blocked(ax, ay):
                aoe_tiles.append((ax, ay))

    # Visual: fire trail along projectile path + explosion ripple at impact
    if engine.sdl_overlay:
        # Trail: fast orange ripple along travel path
        if travel_tiles:
            engine.sdl_overlay.add_tile_flash_ripple(
                travel_tiles, x0, y0,
                color=(255, 120, 30), duration=0.5, ripple_speed=0.03,
            )
        # Explosion: slower red-orange burst at impact
        engine.sdl_overlay.add_tile_flash_ripple(
            aoe_tiles, impact_x, impact_y,
            color=(255, 80, 20), duration=1.0, ripple_speed=0.04,
        )

    # Deal damage + ignite to all enemies in AOE
    hit_targets = set()
    for ax, ay in aoe_tiles:
        for entity in engine.dungeon.get_entities_at(ax, ay):
            if entity.entity_type == "monster" and entity.alive and entity not in hit_targets:
                _deal_damage(engine, damage, entity)
                from xp_progression import _gain_elementalist_xp
                _gain_elementalist_xp(engine, entity, damage, "fire")
                effects.apply_effect(entity, engine, "ignite",
                                     duration=_player_ignite_duration(engine),
                                     stacks=3, silent=True)
                hit_targets.add(entity)

    total_damage = damage * len(hit_targets)
    if hit_targets:
        engine.messages.append(
            f"FIREBALL! Explosion hits {len(hit_targets)} enemy(ies) for {damage} each!"
        )
        from xp_progression import _gain_elemental_spell_xp
        _gain_elemental_spell_xp(engine, "fireball", total_damage)
        for entity in hit_targets:
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)
    else:
        engine.messages.append("FIREBALL! The explosion hits nothing but air!")

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
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist > 4:
        engine.messages.append("Zap: target out of range (max 4 tiles).")
        return False
    bksmt = engine.player_stats.effective_book_smarts
    damage = 5 + bksmt // 2 + engine.player_stats.total_spell_damage
    _deal_damage(engine, damage, target)
    from xp_progression import _gain_elementalist_xp
    _gain_elementalist_xp(engine, target, damage, "lightning")
    from xp_progression import _gain_elemental_spell_xp
    _gain_elemental_spell_xp(engine, "zap", damage)
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


def _spell_ags_charge(engine, tx: int, ty: int) -> bool:
    """AG Sword Charge: charge through a clear line to an enemy 2-5 tiles away.
    Player moves to the tile adjacent to the target, then attacks for 1.5x damage.
    If the target dies, restore 20 spec energy."""
    from abilities import _get_ags_charge_path
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Charge: no enemy there.")
        return False
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist < 2 or dist > 5:
        engine.messages.append("Charge: target must be 2-5 tiles away!")
        return False
    # Verify clear path
    path = _get_ags_charge_path(engine.player.x, engine.player.y, tx, ty)
    for cx, cy in path:
        if engine.dungeon.is_terrain_blocked(cx, cy):
            engine.messages.append("Charge: path is blocked!")
            return False
        if engine.dungeon.get_blocking_entity_at(cx, cy):
            engine.messages.append("Charge: path is blocked!")
            return False
    # Move player to tile adjacent to target (last tile in path)
    if path:
        land_x, land_y = path[-1]
    else:
        # Distance 2 with no intermediate — shouldn't happen, but fallback
        land_x, land_y = engine.player.x, engine.player.y
    engine.player.x = land_x
    engine.player.y = land_y
    # Attack with 1.5x damage
    import combat as _combat
    base_power = _combat._compute_player_attack_power(engine)
    boosted = int(base_power * 1.5)
    old_power = engine.player.power
    engine.player.power = boosted
    engine.messages.append([
        ("Charge! ", (255, 215, 0)),
        (f"You charge {dist} tiles for {boosted} damage!", (255, 230, 150)),
    ])
    _combat.handle_attack(engine, engine.player, target)
    engine.player.power = old_power
    if not target.alive:
        engine.spec_energy = min(100.0, engine.spec_energy + 20.0)
        engine.messages.append([
            ("Kill! ", (255, 50, 50)),
            ("+20 spec energy restored!", (255, 215, 0)),
        ])
    return True


def _spell_polarize(engine, tx: int, ty: int) -> bool:
    """Really Old Maul Polarize: reduce adjacent enemy defense to 0 for 20 turns."""
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Polarize: no enemy there.")
        return False
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist > 1:
        engine.messages.append("Polarize: must be adjacent to target.")
        return False
    effects.apply_effect(target, engine, "cripple_armor", duration=20)
    engine.messages.append([
        ("Polarize! ", (255, 140, 40)),
        (f"{target.name}'s defenses are crushed for 20 turns!", (255, 200, 120)),
    ])
    return True


def _spell_ddd_puncture(engine, tx: int, ty: int) -> bool:
    """Dragon Dagger Puncture: 2 rapid melee hits on an adjacent enemy.
    Each hit resolves as a full normal attack (damage, on-hit effects, crits)."""
    target = next(
        (e for e in engine.dungeon.get_entities_at(tx, ty)
         if e.entity_type == "monster" and e.alive),
        None,
    )
    if target is None:
        engine.messages.append("Puncture: no enemy there.")
        return False
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist > 1:
        engine.messages.append("Puncture: must be adjacent to target.")
        return False
    engine.messages.append([
        ("Puncture! ", (220, 80, 80)),
        ("2 rapid strikes!", (255, 140, 100)),
    ])
    import combat as _combat
    # Hit 1: full normal attack
    _combat.handle_attack(engine, engine.player, target)
    # Hit 2: only if target survived the first hit
    if target.alive:
        _combat.handle_attack(engine, engine.player, target)
    return True


def _spell_lesser_cloudkill(engine, tx: int, ty: int) -> bool:
    """Fart: 3x3 AoE (cannot include player). Damage + Stinky debuff."""
    px, py = engine.player.x, engine.player.y
    if abs(tx - px) <= 1 and abs(ty - py) <= 1:
        engine.messages.append("Fart: can't target an area that includes yourself!")
        return False
    tol = engine.player_stats.effective_tolerance
    swag = engine.player_stats.effective_swagger
    damage = max(1, 25 - swag + tol // 2)
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
        f"Fart! {hit_count} enem{'y' if hit_count == 1 else 'ies'} hit "
        f"for {damage} dmg and are now Stinky."
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


def _get_outbreak_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Return all non-terrain-blocked tiles in a 7x7 area centred on (tx, ty).
    Center must be within 3 tiles of the player."""
    px, py = engine.player.x, engine.player.y
    dist = math.sqrt((tx - px) ** 2 + (ty - py) ** 2)
    if dist > 3.5:
        return []
    tiles = []
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            x, y = tx + dx, ty + dy
            if 0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT:
                if not engine.dungeon.is_terrain_blocked(x, y):
                    tiles.append((x, y))
    return tiles


def _get_wizard_bomb_bonus(engine) -> int:
    """Deprecated — use engine.player_stats.total_spell_damage directly."""
    return engine.player_stats.total_spell_damage


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
    elif spell_type == "graffiti_gun_fire":
        return _get_graffiti_gun_affected_tiles(engine, tx, ty)
    elif spell_type == "outbreak":
        return _get_outbreak_affected_tiles(engine, tx, ty)
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
    # Cryomancy L4 (Glacier Mind): double charges for cold-tagged abilities
    if "cold" in defn.tags and engine.skills.get("Cryomancy").level >= 4:
        n *= 2
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
        if defn:
            _pay_spec_cost(engine, defn)
        if defn and _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        # Curse charge steal: when a curse charge is consumed, steal 1
        # charge from each other curse ability that has charges.
        if consumed and defn and defn.is_curse:
            _curse_charge_steal(engine, inst, defn)
        # Arcane Flux (Elementalist L3): charge preservation also negates cooldowns
        if ability_id and getattr(engine, 'arcane_flux_active', False):
            cd = engine.ability_cooldowns.get(ability_id, 0)
            if cd > 0:
                import random as _rng
                preserve_chance = 0.10  # Arcane Flux base
                if any(getattr(e, 'id', '') == 'muffin_buff' and not e.expired
                       for e in engine.player.status_effects):
                    preserve_chance += 0.50
                if engine.dungeon.spray_paint.get(
                        (engine.player.x, engine.player.y)) == "blue":
                    preserve_chance += 0.25
                if _rng.random() < preserve_chance:
                    engine.ability_cooldowns[ability_id] = 0
                    engine.messages.append([
                        ("Arcane Flux! ", (220, 180, 255)),
                        ("Cooldown negated!", (200, 255, 200)),
                    ])
    engine.targeting_ability_index = None
    # Gunplay L1: targeted ability use resets consecutive shot tracker
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
    from config import HOTBAR_KEYS
    action_type = action.get("type")

    if action_type in ("close_menu", "toggle_abilities"):
        engine.menu_state = MenuState.NONE
        engine.selected_ability_index = None
        return False

    usable_abilities = _get_usable_abilities(engine)
    n = len(usable_abilities)

    # --- Shift+Number: directly bind cursor-selected ability to hotbar slot ---
    if action_type == "hotbar_bind_slot" and n > 0:
        slot = action.get("index", -1)
        if 0 <= slot < len(engine.hotbar) and 0 <= engine.abilities_cursor < n:
            target = usable_abilities[engine.abilities_cursor]
            ability_id = target.ability_id
            defn = ABILITY_REGISTRY.get(ability_id)
            key_label = HOTBAR_KEYS[slot] if slot < len(HOTBAR_KEYS) else str(slot)
            name = defn.name if defn else ability_id

            if engine.hotbar[slot] == ability_id:
                # Already in this slot — unbind
                engine.hotbar[slot] = None
                engine.messages.append([
                    ("Unbound ", (200, 100, 100)),
                    (name, defn.color if defn else (200, 200, 200)),
                    (f" from [{key_label}].", (200, 100, 100)),
                ])
            else:
                # Clear any existing binding for this ability
                for i in range(len(engine.hotbar)):
                    if engine.hotbar[i] == ability_id:
                        engine.hotbar[i] = None
                engine.hotbar[slot] = ability_id
                engine.messages.append([
                    ("Bound ", (100, 255, 100)),
                    (name, defn.color if defn else (200, 200, 200)),
                    (f" to [{key_label}].", (100, 255, 100)),
                ])
        return False

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


def _check_spec_cost(engine, defn) -> bool:
    """Check if player can afford spec_cost. Returns True if ok, False if blocked."""
    cost = getattr(defn, 'spec_cost', 0)
    if cost <= 0:
        return True
    if engine.spec_energy < cost:
        engine.messages.append(f"{defn.name}: not enough spec energy ({int(engine.spec_energy)}/{cost})!")
        return False
    return True


def _pay_spec_cost(engine, defn) -> None:
    """Deduct spec_cost from engine.spec_energy."""
    cost = getattr(defn, 'spec_cost', 0)
    if cost <= 0:
        return
    engine.spec_energy = max(0.0, engine.spec_energy - cost)


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

    if not _check_spec_cost(engine, defn):
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

    _spellweaver_before(engine, defn)
    result = defn.execute(engine)
    if result:
        _spellweaver_after(engine, defn)
        inst.consume(engine)
        if _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        _try_spell_echo_self(engine, defn)
        # Arcane Flux (Elementalist L3): charge preservation also negates cooldowns
        if getattr(engine, 'arcane_flux_active', False):
            cd = engine.ability_cooldowns.get(inst.ability_id, 0)
            if cd > 0:
                import random as _rng
                preserve_chance = 0.10
                if any(getattr(e, 'id', '') == 'muffin_buff' and not e.expired
                       for e in engine.player.status_effects):
                    preserve_chance += 0.50
                if engine.dungeon.spray_paint.get(
                        (engine.player.x, engine.player.y)) == "blue":
                    preserve_chance += 0.25
                if _rng.random() < preserve_chance:
                    engine.ability_cooldowns[inst.ability_id] = 0
                    engine.messages.append([
                        ("Arcane Flux! ", (220, 180, 255)),
                        ("Cooldown negated!", (200, 255, 200)),
                    ])
        engine.targeting_ability_index = None
        # Gunplay L1: ability use resets consecutive shot tracker
        engine.gatting_consecutive_target_id = None
        engine.gatting_consecutive_count = 0
        # Grant Smartsness XP for spell abilities that executed immediately
        if defn.is_spell:
            engine._gain_spell_xp(inst.ability_id)
        else:
            engine._graffiti_proc_blue()
    # result == False means targeting mode was entered; charge consumed later in _execute_spell_at.
    # free_action tag: ability fires but doesn't consume a turn
    if result and "free_action" in defn.tags:
        return False
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
        _pay_spec_cost(engine, defn)
        inst.consume(engine)
        if _pay_rad_cost(engine, defn):
            inst.refund_charge(defn)
        engine.targeting_ability_index = None
        # Gunplay L1: adjacent ability use resets consecutive shot tracker
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
    egg_pending = getattr(engine, 'spider_egg_pending', None)

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.targeting_ability_index = None
        engine.spray_paint_pending = None
        engine.spider_egg_pending = None
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
            elif egg_pending:
                engine.messages.append("Can't hatch there — it's a wall!")
            else:
                engine.messages.append("Fire!: can't place fire on a wall.")
            return False

        # Spray paint item targeting
        if pending:
            engine.menu_state = MenuState.NONE
            _apply_spray_paint_tile(engine, tx, ty, pending)
            engine.spray_paint_pending = None
            return True

        # Spider egg hatching
        if egg_pending:
            engine.menu_state = MenuState.NONE
            hatched = _hatch_spider_egg(engine, tx, ty, egg_pending)
            engine.spider_egg_pending = None
            return hatched

        engine.menu_state = MenuState.NONE
        fired = _fire_adjacent_ability(engine, tx, ty)
        return fired

    return False


def _hatch_spider_egg(engine, tx: int, ty: int, pending: dict) -> bool:
    """Hatch a spider egg on the targeted adjacent tile. Consumes the egg item."""
    from entity import Entity
    from ai import get_initial_state

    # Block if tile is occupied by a blocking entity
    if engine.dungeon.is_blocked(tx, ty):
        engine.messages.append("Can't hatch there — tile is blocked!")
        return False

    item_index = pending["item_index"]
    spider = Entity(
        x=tx, y=ty,
        char=chr(0xE004),
        color=(255, 255, 255),
        name="Spider Hatchling",
        entity_type="monster",
        hp=10,
        power=2,
        defense=0,
        ai_type="spider_hatchling",
        speed=100,
        is_summon=True,
        summon_lifetime=0,
    )
    spider.ai_state = get_initial_state("spider_hatchling")
    engine.dungeon.add_entity(spider)
    engine.messages.append([
        ("A Spider Hatchling emerges from the egg!", (100, 180, 80)),
    ])

    # Consume the egg
    item = engine.player.inventory[item_index]
    qty = getattr(item, "quantity", 1)
    if qty > 1:
        item.quantity -= 1
    else:
        engine.player.inventory.pop(item_index)

    # Grant Arachnigga XP for hatching
    _arachni_xp = round(50 * engine.player_stats.xp_multiplier)
    _arachni_skill = engine.skills.get("Arachnigga")
    _was_locked = _arachni_skill.potential_exp == 0 and _arachni_skill.real_exp == 0 and _arachni_skill.level == 0
    engine.skills.gain_potential_exp(
        "Arachnigga", _arachni_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness,
    )
    if _was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Arachnigga!", (255, 215, 0)),
        ])
    engine.messages.append([
        ("Arachnigga skill: +", (100, 200, 150)),
        (f"{_arachni_xp} XP", (255, 255, 100)),
    ])
    return True


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

    _SPRAY_COLORS = {"red": (255, 40, 40), "blue": (80, 140, 255), "green": (80, 255, 80), "orange": (255, 160, 40), "silver": (200, 200, 210)}
    color = _SPRAY_COLORS.get(spray_type, (200, 200, 200))
    engine.messages.append([
        ("You spray the tile ", (200, 200, 200)),
        (spray_type, color),
        ("!", (200, 200, 200)),
    ])

    # Graffiti XP
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Graffiti", 20, bksmt)


def _get_graffiti_gun_affected_tiles(engine, tx: int, ty: int) -> list[tuple[int, int]]:
    """Return non-wall tiles in 3x3 area centered on (tx, ty)."""
    tiles = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            x, y = tx + dx, ty + dy
            if (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT
                    and not engine.dungeon.is_terrain_blocked(x, y)):
                tiles.append((x, y))
    return tiles


def _execute_graffiti_gun_fire(engine, tx: int, ty: int) -> bool:
    """Fire graffiti gun: spray 3x3 area around target tile."""
    # Range check: Chebyshev distance 6
    dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
    if dist > 6 or dist == 0:
        engine.messages.append("Out of range!")
        return False
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Can't see that tile!")
        return False

    spell = engine.targeting_spell
    item_index = spell["item_index"]
    if item_index >= len(engine.player.inventory):
        engine.menu_state = MenuState.NONE
        engine.targeting_spell = None
        return False

    gun = engine.player.inventory[item_index]
    loaded_id = getattr(gun, 'loaded_spray_id', None)
    if loaded_id is None:
        engine.messages.append("No spray loaded!")
        engine.menu_state = MenuState.NONE
        engine.targeting_spell = None
        return False

    from items import get_item_def
    spray_defn = get_item_def(loaded_id)
    spray_type = spray_defn["use_effect"]["spray_type"]

    # Apply spray to 3x3 area (skip walls)
    tiles_sprayed = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            sx, sy = tx + dx, ty + dy
            if (0 <= sx < DUNGEON_WIDTH and 0 <= sy < DUNGEON_HEIGHT
                    and not engine.dungeon.is_terrain_blocked(sx, sy)):
                engine.dungeon.spray_paint[(sx, sy)] = spray_type
                tiles_sprayed += 1

    # Decrement charge (Taggin' perk: Graffiti L1, 50% preserve)
    import random as _rng
    if engine.skills.get("Graffiti").level >= 1 and _rng.random() < 0.50:
        engine.messages.append([
            ("Taggin'! ", (255, 220, 80)),
            ("Spray charge preserved!", (200, 255, 200)),
        ])
    else:
        gun.loaded_spray_charges -= 1

    _SPRAY_COLORS = {"red": (255, 40, 40), "blue": (80, 140, 255), "green": (80, 255, 80), "orange": (255, 160, 40), "silver": (200, 200, 210)}
    color = _SPRAY_COLORS.get(spray_type, (200, 200, 200))
    engine.messages.append([
        ("Graffiti Gun sprays ", (200, 200, 200)),
        (spray_type, color),
        (f" across {tiles_sprayed} tiles!", (200, 200, 200)),
    ])

    # Graffiti XP
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Graffiti", 20, bksmt)

    # Auto-eject empty spray
    if gun.loaded_spray_charges <= 0:
        gun.loaded_spray_id = None
        gun.loaded_spray_charges = None
        gun.loaded_spray_max_charges = None
        gun_defn = get_item_def("graffiti_gun")
        gun.char = gun_defn["char"]
        gun.color = tuple(gun_defn["color"])
        engine.messages.append([
            ("The loaded spray can is empty!", (200, 100, 100)),
        ])

    engine.menu_state = MenuState.NONE
    engine.targeting_spell = None
    return True
