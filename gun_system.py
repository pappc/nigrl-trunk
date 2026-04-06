"""
Gun system: targeting, firing, reloading, and ammo management.

All functions are module-level and take `engine` (GameEngine instance) as first parameter.
"""

import math
import random

import combat
from combat import _apply_toxic_frenzy
from config import DUNGEON_WIDTH, DUNGEON_HEIGHT, MIN_DAMAGE
from effects import notify_gun_kill, dead_shot_gun_bonus, dead_shot_ammo_recovery, hollow_points_modify_damage, unstable_gun_bonus, unstable_gun_irradiate
from items import get_item_def
from menu_state import MenuState

# Colors for segmented log messages (mirrored from engine.py)
_C_MSG_NEUTRAL = (200, 200, 100)

# Gun skill XP per ammo type: light=20, medium=50, heavy=100
_GUN_AMMO_XP = {"light": 20, "medium": 50, "heavy": 100}


def _sts_gun_bonus(engine):
    """Street Smarts gun damage bonus: +1 per 5 effective STS."""
    return engine.player_stats.effective_street_smarts // 5


def _cw_damage_bonus(engine, gun_defn) -> int:
    """Chemical Warfare scaling bonus for guns with cw_damage_bonus field."""
    per_level = gun_defn.get("cw_damage_bonus", 0)
    if per_level <= 0:
        return 0
    cw_level = engine.skills.get("Chemical Warfare").level
    return per_level * cw_level


def _award_gun_skill_xp(engine, gun_defn, num_shots):
    """Award Gunplay XP based on ammo consumed."""
    ammo_type = gun_defn.get("ammo_type", "light")
    xp_per_shot = _GUN_AMMO_XP.get(ammo_type, 20)
    xp = xp_per_shot * num_shots
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Gunplay", xp, bksmt)


def _award_drive_by_xp(engine, gun_defn, num_shots):
    """Award Drive-By XP when using gun abilities (double tap, burst, spray)."""
    ammo_type = gun_defn.get("ammo_type", "light")
    xp_per_shot = _GUN_AMMO_XP.get(ammo_type, 20)
    xp = xp_per_shot * num_shots
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Drive-By", xp, bksmt)


def _gun_crit_unlocked(engine):
    """Gun crits require Gunplay level 5+."""
    return engine.skills.get("Gunplay").level >= 5


def _get_calculated_aim(engine):
    """Return the active CalculatedAimEffect on the player, or None."""
    return next(
        (e for e in engine.player.status_effects
         if getattr(e, 'id', '') == 'calculated_aim'),
        None,
    )




def _apply_sideways(engine, base_hit, energy_cost):
    """Gunplay L3 'Doin' It Sideways': -10% accuracy, -10 energy cost."""
    if engine.skills.get("Gunplay").level >= 3:
        base_hit = max(5, base_hit - 10)
        energy_cost = max(10, energy_cost - 10)
    return base_hit, energy_cost


def _notify_ammo_spent(engine, gun, num_rounds):
    """Handle auto-reload from Calculated Aim buff after ammo is spent."""
    aim = _get_calculated_aim(engine)
    if aim is None:
        return
    # Auto-reload: if gun is empty and buff has auto_reload
    if aim.auto_reload and gun.current_ammo <= 0:
        gun_defn = get_item_def(gun.item_id)
        ammo_type = gun_defn.get("ammo_type") if gun_defn else None
        if ammo_type:
            ammo_item = next(
                (it for it in engine.player.inventory
                 if getattr(it, 'item_id', '') == ammo_type),
                None,
            )
            if ammo_item:
                needed = gun.mag_size - gun.current_ammo
                loaded = min(needed, ammo_item.quantity)
                gun.current_ammo += loaded
                ammo_item.quantity -= loaded
                if ammo_item.quantity <= 0:
                    engine.player.inventory.remove(ammo_item)
                engine.messages.append([
                    ("Auto-reload! ", (100, 255, 100)),
                    (f"({gun.current_ammo}/{gun.mag_size})", (200, 200, 200)),
                ])


def _get_primary_gun(engine):
    """Return the Entity in the primary gun slot, or None."""
    if engine.primary_gun is None:
        return None
    return engine.equipment.get(engine.primary_gun)


def _find_nearest_visible_enemy(engine, max_range):
    """Return the nearest alive, visible monster within Chebyshev distance, or None."""
    best = None
    best_dist = max_range + 1
    for entity in engine.dungeon.get_monsters():
        if not entity.alive:
            continue
        if not engine.dungeon.visible[entity.y, entity.x]:
            continue
        dist = max(abs(entity.x - engine.player.x), abs(entity.y - engine.player.y))
        if dist <= max_range and dist < best_dist:
            best = entity
            best_dist = dist
    return best


def _enter_gun_ability_targeting(engine, spec: dict) -> bool:
    """Enter gun targeting mode for a gun ability. spec contains ability stats.
    Returns False (no turn consumed yet — turn consumed on confirm)."""
    gun = _get_primary_gun(engine)
    if gun is None:
        engine.messages.append("No gun equipped.")
        return False
    if engine.gun_jammed:
        engine.messages.append("Gun is jammed! Reload (Shift+R) to clear it.")
        return False
    gun_defn = get_item_def(gun.item_id)
    if gun_defn is None:
        return False
    num_shots = spec.get("num_shots", 2)
    if gun.current_ammo < num_shots:
        if gun.current_ammo <= 0:
            engine.messages.append("Click! Empty magazine. Reload with Shift+R.")
        else:
            engine.messages.append(f"Need {num_shots} rounds to fire. Reload with Shift+R.")
        return False

    # Cursor start: last targeted enemy > nearest visible > player pos
    last = engine.last_targeted_enemy
    ability_range = spec.get("range", 4)
    if (last is not None and getattr(last, 'alive', False)
            and engine.dungeon.visible[last.y, last.x]):
        engine.gun_targeting_cursor = [last.x, last.y]
    else:
        nearest = _find_nearest_visible_enemy(engine, ability_range)
        if nearest:
            engine.gun_targeting_cursor = [nearest.x, nearest.y]
        else:
            engine.gun_targeting_cursor = [engine.player.x, engine.player.y]

    engine.gun_ability_active = spec
    engine.menu_state = MenuState.GUN_TARGETING
    return False


def _get_equipped_staff(engine):
    """Return (weapon_entity, item_defn) if weapon slot holds a staff, else (None, None)."""
    weapon = engine.equipment.get("weapon")
    if weapon is None:
        return None, None
    defn = get_item_def(weapon.item_id)
    if defn is None or "staff_element" not in defn:
        return None, None
    return weapon, defn


def _action_fire_gun(engine, _action):
    """Enter gun targeting mode if the player has a loaded primary gun (or staff)."""
    gun = _get_primary_gun(engine)
    if gun is None:
        # No gun — check for an equipped staff
        staff, staff_defn = _get_equipped_staff(engine)
        if staff is not None:
            return _action_fire_staff(engine, staff, staff_defn)
        engine.messages.append("No gun equipped.")
        return False
    if engine.gun_jammed:
        engine.messages.append("Gun is jammed! Reload (Shift+R) to clear it.")
        return False
    gun_defn = get_item_def(gun.item_id)
    if gun_defn is None:
        return False
    # Check minimum ammo requirement (cone guns need multiple rounds)
    ammo_per_shot = gun_defn.get("ammo_per_shot")
    min_ammo = ammo_per_shot[0] if isinstance(ammo_per_shot, (list, tuple)) else 1
    if gun.current_ammo < min_ammo:
        if gun.current_ammo <= 0:
            engine.messages.append("Click! Empty magazine. Reload with Shift+R.")
        else:
            engine.messages.append(f"Need at least {min_ammo} rounds to fire. Reload with Shift+R.")
        return False

    gun_range = gun_defn.get("gun_range", 4)
    # Cursor start: last targeted enemy > nearest visible > player pos
    last = engine.last_targeted_enemy
    if (last is not None and getattr(last, 'alive', False)
            and engine.dungeon.visible[last.y, last.x]):
        engine.gun_targeting_cursor = [last.x, last.y]
    else:
        nearest = _find_nearest_visible_enemy(engine, gun_range)
        if nearest:
            engine.gun_targeting_cursor = [nearest.x, nearest.y]
        else:
            engine.gun_targeting_cursor = [engine.player.x, engine.player.y]

    engine.menu_state = MenuState.GUN_TARGETING
    return False


# ---- Staff fire (elementalist staves) ----

_STAFF_RANGE = 4

_STAFF_ELEMENT_DEBUFF = {
    "fire": "ignite",
    "lightning": "shocked",
    "cold": "chill",
}

_STAFF_ELEMENT_COLOR = {
    "fire": (255, 100, 30),
    "lightning": (255, 255, 80),
    "cold": (100, 200, 255),
}


def _action_fire_staff(engine, staff, staff_defn):
    """Enter targeting mode for a staff ranged attack."""
    if getattr(staff, 'charges', 0) <= 0:
        engine.messages.append("The staff has no charges left.")
        return False
    last = engine.last_targeted_enemy
    if (last is not None and getattr(last, 'alive', False)
            and engine.dungeon.visible[last.y, last.x]):
        engine.gun_targeting_cursor = [last.x, last.y]
    else:
        nearest = _find_nearest_visible_enemy(engine, _STAFF_RANGE)
        if nearest:
            engine.gun_targeting_cursor = [nearest.x, nearest.y]
        else:
            engine.gun_targeting_cursor = [engine.player.x, engine.player.y]

    # Store staff info for the confirm handler
    engine.staff_firing = {
        "element": staff_defn["staff_element"],
        "item_id": staff.item_id,
    }
    engine.menu_state = MenuState.GUN_TARGETING
    return False


def _resolve_staff_shot(engine, tx, ty):
    """Fire a staff bolt at (tx, ty). Range 4, dmg = 5 + bksmt//3, apply 1 debuff stack."""
    import effects
    from spells import _trace_projectile

    info = engine.staff_firing
    element = info["element"]
    engine.staff_firing = None
    engine.menu_state = MenuState.NONE

    px, py = engine.player.x, engine.player.y
    dist = max(abs(tx - px), abs(ty - py))
    if dist == 0:
        engine.messages.append("Can't target yourself!")
        return
    if dist > _STAFF_RANGE:
        engine.messages.append("Out of range!")
        return
    if not engine.dungeon.visible[ty, tx]:
        engine.messages.append("Can't see that tile.")
        return

    # Consume a staff charge
    weapon = engine.equipment.get("weapon")
    if weapon and getattr(weapon, 'charges', None) is not None:
        weapon.charges = max(0, weapon.charges - 1)

    hit = _trace_projectile(engine, px, py, tx, ty)
    if hit is None:
        engine.messages.append("Staff bolt fizzles — no target in path!")
        return

    bksmt = engine.player_stats.effective_book_smarts
    damage = 5 + bksmt // 3

    combat.deal_damage(engine, damage, hit)

    # Elementalist XP (cross-element check before applying debuff)
    from xp_progression import _gain_elementalist_xp
    _gain_elementalist_xp(engine, hit, damage, element)

    debuff_id = _STAFF_ELEMENT_DEBUFF[element]
    effects.apply_effect(hit, engine, debuff_id, duration=10, stacks=1, silent=True)

    color = _STAFF_ELEMENT_COLOR[element]
    hp_disp = f"{hit.hp}/{hit.max_hp}" if hit.alive else "dead"
    debuff_name = debuff_id.capitalize()
    engine.messages.append([
        ("Staff bolt hits ", color),
        (f"{hit.name} for {damage} dmg! +1 {debuff_name} ({hp_disp})", (255, 255, 255)),
    ])

    if engine.sdl_overlay:
        engine.sdl_overlay.add_tile_flash_ripple(
            [(hit.x, hit.y)], px, py, color=color, duration=0.4, ripple_speed=0.02,
        )

    if not hit.alive:
        engine.event_bus.emit("entity_died", entity=hit, killer=engine.player)


def _handle_gun_targeting_input(engine, action):
    """Handle input while in gun targeting mode."""
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.gun_ability_active = None
        engine.staff_firing = None
        return False

    if action_type == "move":
        dx = action.get("dx", 0)
        dy = action.get("dy", 0)
        nx = max(0, min(DUNGEON_WIDTH - 1, engine.gun_targeting_cursor[0] + dx))
        ny = max(0, min(DUNGEON_HEIGHT - 1, engine.gun_targeting_cursor[1] + dy))
        engine.gun_targeting_cursor = [nx, ny]
        return False

    if action_type == "confirm_target":
        tx, ty = engine.gun_targeting_cursor
        engine._record_targeted_enemy_at(tx, ty)

        # Staff shot — resolve and return (energy handled internally)
        if getattr(engine, 'staff_firing', None):
            _resolve_staff_shot(engine, tx, ty)
            return False

        gun = _get_primary_gun(engine)
        if gun is None:
            engine.menu_state = MenuState.NONE
            return False
        gun_defn = get_item_def(gun.item_id)

        # Gun ability active — use ability's range, not gun's
        if engine.gun_ability_active is not None:
            ability_range = engine.gun_ability_active.get("range", 4)
            if not engine.dungeon.visible[ty, tx]:
                engine.messages.append("Can't see that tile.")
                return False
            dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
            if dist > ability_range:
                engine.messages.append("Out of range!")
                return False
            if dist == 0:
                engine.messages.append("Can't shoot yourself!")
                return False
            _resolve_gun_ability_shot(engine, tx, ty)
            return False

        gun_range = gun_defn.get("gun_range", 4)

        # Validate visible and in range
        if not engine.dungeon.visible[ty, tx]:
            engine.messages.append("Can't see that tile.")
            return False
        dist = max(abs(tx - engine.player.x), abs(ty - engine.player.y))
        if dist > gun_range:
            engine.messages.append("Out of range!")
            return False
        if dist == 0:
            engine.messages.append("Can't shoot yourself!")
            return False

        aoe_type = gun_defn.get("aoe_type", "target")
        if aoe_type == "cone":
            _resolve_cone_shot(engine, tx, ty)
        elif aoe_type == "circle":
            _resolve_circle_shot(engine, tx, ty)
        else:
            _resolve_gun_shot(engine, tx, ty)
        return False

    return False


def _get_gun_cone_tiles(engine, tx, ty):
    """Return list of (x, y) tiles in the primary gun's cone toward (tx, ty).

    Uses corner-inclusive angle check: a tile is in the cone if ANY of its four
    corners falls within the cone angle.  Tiles blocked by walls (no LOS from
    player) are excluded.
    """
    from ai import _has_los
    gun = _get_primary_gun(engine)
    if gun is None:
        return []
    gun_defn = get_item_def(gun.item_id)
    gun_range = gun_defn.get("gun_range", 5)
    cone_angle = gun_defn.get("cone_angle", 30)
    px, py = engine.player.x, engine.player.y
    angle_to_target = math.atan2(ty - py, tx - px)
    half_angle = math.radians(cone_angle / 2)
    # Corner offsets — check all four corners of each tile
    corners = [(-0.4, -0.4), (-0.4, 0.4), (0.4, -0.4), (0.4, 0.4)]
    tiles = []
    for y in range(py - gun_range, py + gun_range + 1):
        for x in range(px - gun_range, px + gun_range + 1):
            if x == px and y == py:
                continue
            dist = max(abs(x - px), abs(y - py))
            if dist > gun_range or dist == 0:
                continue
            # Check if any corner of the tile falls within the cone
            in_cone = False
            for cx, cy in corners:
                angle = math.atan2((y + cy) - py, (x + cx) - px)
                diff = abs(angle - angle_to_target)
                if diff > math.pi:
                    diff = 2 * math.pi - diff
                if diff <= half_angle:
                    in_cone = True
                    break
            if not in_cone:
                continue
            # Skip tiles behind walls
            if not _has_los(engine.dungeon, px, py, x, y):
                continue
            tiles.append((x, y))
    return tiles


def _get_gun_line_tiles(engine, tx, ty, max_range):
    """Return list of (x, y) tiles in a line from player toward (tx, ty), up to max_range tiles."""
    px, py = engine.player.x, engine.player.y
    dx = tx - px
    dy = ty - py
    if dx == 0 and dy == 0:
        return []
    # Normalize to unit direction (cardinal/diagonal)
    unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
    unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0
    tiles = []
    cx, cy = px + unit_dx, py + unit_dy
    for _ in range(max_range):
        if cx < 0 or cx >= DUNGEON_WIDTH or cy < 0 or cy >= DUNGEON_HEIGHT:
            break
        if engine.dungeon.is_terrain_blocked(cx, cy):
            break
        tiles.append((cx, cy))
        cx += unit_dx
        cy += unit_dy
    return tiles


def _get_gun_circle_tiles(engine, cx, cy, radius):
    """Return list of (x, y) tiles in a circle (Chebyshev distance) around (cx, cy)."""
    tiles = []
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if x < 0 or x >= DUNGEON_WIDTH or y < 0 or y >= DUNGEON_HEIGHT:
                continue
            if engine.dungeon.is_terrain_blocked(x, y):
                continue
            tiles.append((x, y))
    return tiles


def _resolve_gun_ability_shot(engine, tx, ty):
    """Resolve firing a gun ability (double_tap, burst, spray) toward target tile."""
    spec = engine.gun_ability_active
    if spec is None:
        return
    gun = _get_primary_gun(engine)
    gun_defn = get_item_def(gun.item_id)

    ability_name = spec["name"]
    num_shots = spec["num_shots"]
    min_dmg, max_dmg = spec["damage"]
    accuracy = spec["accuracy"]
    energy_cost = spec["energy"]
    aoe_type = spec.get("aoe_type", "line")
    ability_range = spec.get("range", 4)
    ability_id = spec.get("ability_id")

    # Check ammo
    if gun.current_ammo < num_shots:
        engine.messages.append(f"Need {num_shots} rounds loaded. Reload with Shift+R.")
        return

    # Consume ammo
    gun.current_ammo = max(0, gun.current_ammo - num_shots)
    _award_drive_by_xp(engine, gun_defn, num_shots)
    _notify_ammo_spent(engine, gun, num_shots)
    dead_shot_ammo_recovery(engine, num_shots, gun_defn.get("ammo_type", "light"))

    # Exit targeting
    engine.menu_state = MenuState.NONE
    engine.gun_ability_active = None

    # Find targets in the AOE
    if aoe_type == "line":
        aoe_tiles = set(_get_gun_line_tiles(engine, tx, ty, ability_range))
    elif aoe_type == "cone":
        aoe_tiles = set(_get_gun_cone_tiles(engine, tx, ty))
    else:
        aoe_tiles = {(tx, ty)}

    targets = []
    for entity in engine.dungeon.get_monsters():
        if entity.alive and (entity.x, entity.y) in aoe_tiles:
            if engine.dungeon.visible[entity.y, entity.x]:
                targets.append(entity)

    if not targets:
        engine.messages.append(f"{ability_name}! {num_shots} rounds into empty space!")
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Distribute shots: max ceil(num_shots / 2) per target
    max_per_target = math.ceil(num_shots / 2)
    hit_counts = {}
    assignments = []
    for _ in range(num_shots):
        eligible = [t for t in targets
                    if hit_counts.get(t.instance_id, 0) < max_per_target]
        if not eligible:
            break
        target = random.choice(eligible)
        assignments.append(target)
        hit_counts[target.instance_id] = hit_counts.get(target.instance_id, 0) + 1

    # Resolve each shot (with per-shot jam checks if ability specifies)
    total_hits = 0
    shots_fired = 0
    kills = []
    ability_jam_chance = spec.get("jam_chance", 0)
    jammed = False
    for target in assignments:
        if not target.alive:
            shots_fired += 1
            continue
        # Per-shot jam check (e.g. Spray & Pray)
        if ability_jam_chance and random.randint(1, 100) <= ability_jam_chance:
            jammed = True
            # Refund unspent rounds
            refund = num_shots - shots_fired - 1
            if refund > 0:
                gun.current_ammo = min(gun.mag_size, gun.current_ammo + refund)
            break
        shots_fired += 1
        # Accuracy roll
        if random.randint(1, 100) > accuracy:
            continue
        # Dodge roll
        if random.random() * 100 < target.dodge_chance:
            continue
        # Damage
        damage = random.randint(min_dmg, max_dmg) + _sts_gun_bonus(engine) + dead_shot_gun_bonus(engine) + unstable_gun_bonus(engine)
        is_crit = _gun_crit_unlocked(engine) and random.random() < engine.player_stats.crit_chance
        if is_crit:
            damage *= engine.crit_multiplier
        damage = max(MIN_DAMAGE, damage - target.defense)
        mult = engine.player_stats.outgoing_damage_mult
        if mult != 1.0:
            damage = int(damage * mult)
        damage = _apply_toxic_frenzy(engine, damage)
        damage = engine._apply_damage_modifiers(damage, target)
        damage = engine._apply_toxicity(damage, target)
        damage = hollow_points_modify_damage(engine, damage)
        killed = combat.deal_damage(engine, damage, target)
        engine._apply_virulent_vodka(target, damage)
        engine._check_decontamination_proc(target)
        if target.alive:
            unstable_gun_irradiate(engine, target)
        # On-hit toxicity from ability spec or gun definition
        ability_tox = spec.get("on_hit_tox", 0) or gun_defn.get("on_hit_tox", 0)
        if ability_tox and target.alive:
            combat.add_toxicity(engine, target, ability_tox, from_player=True)
        total_hits += 1
        if killed and target not in kills:
            kills.append(target)

    if jammed:
        engine.gun_jammed = True
        engine.messages.append([
            (f"{ability_name}! ", (200, 150, 80)),
            (f"{shots_fired} of {num_shots} rounds fired, {total_hits} hit{'s' if total_hits != 1 else ''} — ", (200, 200, 200)),
            ("JAM!", (255, 80, 80)),
        ])
    else:
        engine.messages.append(
            f"{ability_name}! {num_shots} rounds fired, {total_hits} hit{'s' if total_hits != 1 else ''}."
        )
    for killed_target in kills:
        engine.event_bus.emit("entity_died", entity=killed_target, killer=engine.player)
        notify_gun_kill(engine)

    # Consume ability cooldown if specified
    cooldown = spec.get("cooldown", 0)
    if cooldown > 0 and ability_id:
        engine.ability_cooldowns[ability_id] = cooldown

    engine.player.energy -= energy_cost
    if engine.running and engine.player.alive:
        engine._run_energy_loop()


def _resolve_cone_shot(engine, tx, ty):
    """Resolve firing a cone-type gun toward target tile (tx, ty)."""
    gun = _get_primary_gun(engine)
    gun_defn = get_item_def(gun.item_id)
    stats = gun_defn.get("gun_stats", {"hit": 50, "energy": 50})
    energy_cost = stats["energy"]
    if engine.action_cost_mult != 1.0:
        energy_cost = int(energy_cost * engine.action_cost_mult)
    base_hit = stats["hit"]
    min_dmg, max_dmg = gun_defn.get("base_damage", (1, 1))
    cw_bonus = _cw_damage_bonus(engine, gun_defn)
    min_dmg += cw_bonus
    max_dmg += cw_bonus
    _edb = getattr(gun, "enchant_damage_bonus", None)
    if _edb:
        min_dmg += _edb[0]
        max_dmg += _edb[1]

    # Determine ammo to use and projectile count
    ammo_per_shot = gun_defn.get("ammo_per_shot", (1, 1))
    if isinstance(ammo_per_shot, (list, tuple)):
        ammo_cost = min(random.randint(ammo_per_shot[0], ammo_per_shot[1]),
                        gun.current_ammo)
    else:
        ammo_cost = min(ammo_per_shot, gun.current_ammo)
    # Projectiles can differ from ammo consumed (e.g. shotguns: 1 shell = 5 pellets)
    num_shots = gun_defn.get("projectiles", ammo_cost)

    # Consume ammo
    gun.current_ammo = max(0, gun.current_ammo - ammo_cost)
    _award_gun_skill_xp(engine, gun_defn, num_shots)
    _notify_ammo_spent(engine, gun, num_shots)
    dead_shot_ammo_recovery(engine, num_shots, gun_defn.get("ammo_type", "light"))

    # Exit targeting
    engine.menu_state = MenuState.NONE

    # Find enemies in cone
    cone_tiles = set(_get_gun_cone_tiles(engine, tx, ty))
    targets = []
    for entity in engine.dungeon.get_monsters():
        if entity.alive and (entity.x, entity.y) in cone_tiles:
            if engine.dungeon.visible[entity.y, entity.x]:
                targets.append(entity)

    if not targets:
        engine.messages.append(f"You spray {num_shots} rounds into empty space!")
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Distribute shots: max ceil(num_shots / 2) hits per target
    max_per_target = math.ceil(num_shots / 2)
    hit_counts = {}
    assignments = []
    for _ in range(num_shots):
        eligible = [t for t in targets
                    if hit_counts.get(t.instance_id, 0) < max_per_target]
        if not eligible:
            break
        target = random.choice(eligible)
        assignments.append(target)
        hit_counts[target.instance_id] = hit_counts.get(target.instance_id, 0) + 1

    # Resolve each shot
    total_hits = 0
    kills = []
    for target in assignments:
        if not target.alive:
            continue
        # Accuracy roll
        if random.randint(1, 100) > base_hit:
            continue
        # Dodge roll
        defender_dodge = target.dodge_chance
        if random.random() * 100 < defender_dodge:
            continue

        # Damage
        damage = random.randint(min_dmg, max_dmg) + _sts_gun_bonus(engine) + dead_shot_gun_bonus(engine) + unstable_gun_bonus(engine)
        is_crit = _gun_crit_unlocked(engine) and random.random() < engine.player_stats.crit_chance
        if is_crit:
            damage *= engine.crit_multiplier
        damage = max(MIN_DAMAGE, damage - target.defense)
        mult = engine.player_stats.outgoing_damage_mult
        if mult != 1.0:
            damage = int(damage * mult)
        damage = _apply_toxic_frenzy(engine, damage)
        damage = engine._apply_damage_modifiers(damage, target)
        damage = engine._apply_toxicity(damage, target)
        damage = hollow_points_modify_damage(engine, damage)
        killed = combat.deal_damage(engine, damage, target)
        engine._apply_virulent_vodka(target, damage)
        engine._check_decontamination_proc(target)
        if target.alive:
            unstable_gun_irradiate(engine, target)
        # On-hit toxicity (e.g. Toxic Slingshot)
        on_hit_tox = gun_defn.get("on_hit_tox", 0)
        if on_hit_tox and target.alive:
            combat.add_toxicity(engine, target, on_hit_tox, from_player=True)
        total_hits += 1
        if killed and target not in kills:
            kills.append(target)

    engine.messages.append(
        f"You spray {num_shots} rounds! {total_hits} hit{'s' if total_hits != 1 else ''}."
    )
    for killed_target in kills:
        engine.event_bus.emit("entity_died", entity=killed_target, killer=engine.player)
        notify_gun_kill(engine)

    engine.player.energy -= energy_cost
    if engine.running and engine.player.alive:
        engine._run_energy_loop()


def _resolve_circle_shot(engine, tx, ty):
    """Resolve firing a circle-AOE gun (e.g. RPG) at target tile (tx, ty)."""
    gun = _get_primary_gun(engine)
    gun_defn = get_item_def(gun.item_id)
    stats = gun_defn.get("gun_stats", {"hit": 50, "energy": 50})
    energy_cost = stats["energy"]
    if engine.action_cost_mult != 1.0:
        energy_cost = int(energy_cost * engine.action_cost_mult)
    base_hit = stats["hit"]
    min_dmg, max_dmg = gun_defn.get("base_damage", (1, 1))
    cw_bonus = _cw_damage_bonus(engine, gun_defn)
    min_dmg += cw_bonus
    max_dmg += cw_bonus
    _edb = getattr(gun, "enchant_damage_bonus", None)
    if _edb:
        min_dmg += _edb[0]
        max_dmg += _edb[1]
    aoe_radius = gun_defn.get("aoe_radius", 2)

    # Consume ammo
    gun.current_ammo = max(0, gun.current_ammo - 1)
    _award_gun_skill_xp(engine, gun_defn, 1)
    _notify_ammo_spent(engine, gun, 1)
    dead_shot_ammo_recovery(engine, 1, gun_defn.get("ammo_type", "light"))

    # Exit targeting
    engine.menu_state = MenuState.NONE

    # Accuracy roll — hit means explosion at target, miss means near player
    px, py = engine.player.x, engine.player.y
    if random.randint(1, 100) <= base_hit:
        # Direct hit
        ex, ey = tx, ty
        engine.messages.append("Direct hit! The rocket explodes!")
    else:
        # Miss — explosion at random walkable tile near player
        candidates = []
        for cy in range(py - 2, py + 3):
            for cx in range(px - 2, px + 3):
                if cx < 0 or cx >= DUNGEON_WIDTH or cy < 0 or cy >= DUNGEON_HEIGHT:
                    continue
                if not engine.dungeon.is_terrain_blocked(cx, cy):
                    candidates.append((cx, cy))
        if candidates:
            ex, ey = random.choice(candidates)
        else:
            ex, ey = px, py
        engine.messages.append(
            f"The rocket goes wide and explodes at ({ex},{ey})!"
        )

    # Get blast tiles and find targets
    blast_tiles = set(_get_gun_circle_tiles(engine, ex, ey, aoe_radius))

    # Animation: projectile trail + explosion ripple
    sdl = getattr(engine, "sdl_overlay", None)
    if sdl:
        # Build projectile path from player to explosion center
        trail = []
        dx_t, dy_t = ex - px, ey - py
        steps = max(abs(dx_t), abs(dy_t))
        if steps > 0:
            for s in range(1, steps + 1):
                trail.append((round(px + dx_t * s / steps), round(py + dy_t * s / steps)))
            sdl.add_tile_flash_trail(trail, color=(200, 200, 180), duration=0.25, trail_speed=0.02)
        # Explosion ripple over blast area
        sdl.add_tile_flash_ripple(
            list(blast_tiles), ex, ey,
            color=(255, 100, 20), duration=0.8, ripple_speed=0.05,
        )

    kills = []

    # Damage all alive monsters in blast radius
    for entity in engine.dungeon.get_monsters():
        if entity.alive and (entity.x, entity.y) in blast_tiles:
            damage = random.randint(min_dmg, max_dmg) + _sts_gun_bonus(engine) + dead_shot_gun_bonus(engine) + unstable_gun_bonus(engine)
            is_crit = _gun_crit_unlocked(engine) and random.random() < engine.player_stats.crit_chance
            if is_crit:
                damage *= engine.crit_multiplier
            damage = max(MIN_DAMAGE, damage - entity.defense)
            mult = engine.player_stats.outgoing_damage_mult
            if mult != 1.0:
                damage = int(damage * mult)
            damage = engine._apply_damage_modifiers(damage, entity)
            damage = engine._apply_toxicity(damage, entity)
            damage = hollow_points_modify_damage(engine, damage)
            killed = combat.deal_damage(engine, damage, entity)
            engine._apply_virulent_vodka(entity, damage)
            engine._check_decontamination_proc(entity)
            if entity.alive:
                unstable_gun_irradiate(engine, entity)
            # On-hit toxicity (e.g. Toxic Slingshot)
            on_hit_tox = gun_defn.get("on_hit_tox", 0)
            if on_hit_tox and entity.alive:
                combat.add_toxicity(engine, entity, on_hit_tox, from_player=True)
            if killed:
                kills.append(entity)

    # Check if player is in blast radius (self-damage)
    if (px, py) in blast_tiles:
        damage = random.randint(min_dmg, max_dmg)
        damage = max(MIN_DAMAGE, damage)
        engine.player.hp -= damage
        engine.messages.append(f"You're caught in the blast! ({damage} damage)")
        if engine.player.hp <= 0:
            engine.player.hp = 0
            engine.player.alive = False
            engine.game_over = True

    for killed_target in kills:
        engine.event_bus.emit("entity_died", entity=killed_target, killer=engine.player)
        notify_gun_kill(engine)

    engine.player.energy -= energy_cost
    if engine.running and engine.player.alive:
        engine._run_energy_loop()


def _resolve_gun_shot(engine, tx, ty):
    """Resolve firing the primary gun at target tile (tx, ty)."""
    gun = _get_primary_gun(engine)
    gun_defn = get_item_def(gun.item_id)
    stats = gun_defn.get("gun_stats", {"hit": 75, "energy": 50})
    energy_cost = stats["energy"]
    base_hit = stats["hit"]
    base_hit, energy_cost = _apply_sideways(engine, base_hit, energy_cost)
    if engine.action_cost_mult != 1.0:
        energy_cost = int(energy_cost * engine.action_cost_mult)
    min_dmg, max_dmg = gun_defn.get("base_damage", (1, 1))
    cw_bonus = _cw_damage_bonus(engine, gun_defn)
    min_dmg += cw_bonus
    max_dmg += cw_bonus
    _edb = getattr(gun, "enchant_damage_bonus", None)
    if _edb:
        min_dmg += _edb[0]
        max_dmg += _edb[1]

    # Consume ammo
    gun.current_ammo = max(0, gun.current_ammo - 1)
    _award_gun_skill_xp(engine, gun_defn, 1)
    _notify_ammo_spent(engine, gun, 1)
    dead_shot_ammo_recovery(engine, 1, gun_defn.get("ammo_type", "light"))

    # Exit targeting
    engine.menu_state = MenuState.NONE

    # Jam check
    jam_chance = gun_defn.get("jam_chance", 0)
    if jam_chance and random.randint(1, 100) <= jam_chance:
        engine.gun_jammed = True
        jam_cost = gun_defn.get("jam_clear_cost", 100)
        engine.messages.append([
            ("JAM! ", (255, 80, 80)),
            ("Your gun jams! Reload (Shift+R) to clear it.", (200, 200, 200)),
        ])
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Find target monster
    target = None
    for e in engine.dungeon.get_entities_at(tx, ty):
        if e.entity_type == "monster" and e.alive:
            target = e
            break

    # Track consecutive target for bonus damage (e.g. HV Express)
    consecutive_bonus_per = gun_defn.get("consecutive_bonus", 0)
    if target is not None and consecutive_bonus_per:
        if engine.gun_consecutive_target_id != target.instance_id:
            # Fired at a different target: reset
            engine.gun_consecutive_target_id = target.instance_id
            engine.gun_consecutive_count = 0

    # Gunplay L1 "Locked In": track consecutive target
    gatting_active = engine.skills.get("Gunplay").level >= 1
    if target is not None and gatting_active:
        if engine.gatting_consecutive_target_id != target.instance_id:
            engine.gatting_consecutive_target_id = target.instance_id
            engine.gatting_consecutive_count = 0

    if target is None:
        engine.messages.append("The shot hits nothing.")
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Accuracy roll
    if random.randint(1, 100) > base_hit:
        engine.messages.append([
            ("You miss ", _C_MSG_NEUTRAL),
            (target.name, target.color),
            ("!", _C_MSG_NEUTRAL),
        ])
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Dodge roll
    defender_dodge = engine.player_stats.dodge_chance if target is engine.player else target.dodge_chance
    if random.random() * 100 < defender_dodge:
        engine.messages.append(f"{target.name} dodges the shot!")
        engine.player.energy -= energy_cost
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
        return

    # Damage calculation
    # Decimator: damage = player's missing HP
    if "decimator" in gun_defn.get("tags", []):
        damage = engine.player.max_hp - engine.player.hp
    else:
        damage = random.randint(min_dmg, max_dmg) + _sts_gun_bonus(engine) + dead_shot_gun_bonus(engine) + unstable_gun_bonus(engine)

    # Consecutive hit bonus (HV Express)
    bonus = 0
    if consecutive_bonus_per and engine.gun_consecutive_count > 0:
        bonus = consecutive_bonus_per * engine.gun_consecutive_count
        damage += bonus
    if consecutive_bonus_per:
        engine.gun_consecutive_count += 1

    # Gunplay L1 "Locked In" consecutive bonus (+1 per hit)
    gatting_bonus = 0
    if gatting_active and engine.gatting_consecutive_count > 0:
        gatting_bonus = engine.gatting_consecutive_count
        damage += gatting_bonus
    if gatting_active:
        engine.gatting_consecutive_count += 1

    # Crit check
    is_crit = _gun_crit_unlocked(engine) and random.random() < engine.player_stats.crit_chance
    is_mega_crit = False
    if is_crit:
        # Gunplay L6 mega crit
        if combat.check_mega_crit(engine):
            is_mega_crit = True
            damage *= combat.MEGA_CRIT_MULTIPLIER
        else:
            damage *= engine.crit_multiplier

    damage = max(MIN_DAMAGE, damage - target.defense)
    mult = engine.player_stats.outgoing_damage_mult
    if mult != 1.0:
        damage = int(damage * mult)
    damage = _apply_toxic_frenzy(engine, damage)
    damage = engine._apply_damage_modifiers(damage, target)
    damage = engine._apply_toxicity(damage, target)
    damage = hollow_points_modify_damage(engine, damage)

    killed = combat.deal_damage(engine, damage, target)
    engine._apply_virulent_vodka(target, damage)
    engine._check_decontamination_proc(target)
    if target.alive:
        unstable_gun_irradiate(engine, target)

    # On-hit toxicity (e.g. Toxic Slingshot)
    on_hit_tox = gun_defn.get("on_hit_tox", 0)
    if on_hit_tox and target.alive:
        combat.add_toxicity(engine, target, on_hit_tox, from_player=True)

    crit_tag = " MEGA CRIT!" if is_mega_crit else (" CRIT!" if is_crit else "")
    total_consec = bonus + gatting_bonus
    bonus_tag = f" (+{total_consec} locked in)" if total_consec > 0 else ""
    engine.messages.append([
        ("You shoot ", _C_MSG_NEUTRAL),
        (target.name, target.color),
        (f" for {damage} damage!{crit_tag}{bonus_tag}", _C_MSG_NEUTRAL),
    ])

    if killed:
        engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
        notify_gun_kill(engine)
        # Gunplay L4 "Dead Eye": gun kill = +1 swagger for the floor
        if engine.skills.get("Gunplay").level >= 4:
            engine.player_stats.swagger += 1
            engine.dead_eye_swagger_gained += 1
            engine.messages.append([
                ("Dead Eye! ", (255, 220, 100)),
                ("+1 Swagger", (200, 200, 200)),
            ])

    # Thunder Gun chain lightning: on hit, chain to 2 additional targets within 2 tiles
    if "thunder_gun" in gun_defn.get("tags", []):
        _thunder_gun_chain(engine, target, gun_defn)

    engine.player.energy -= energy_cost
    if engine.running and engine.player.alive:
        engine._run_energy_loop()


def _thunder_gun_chain(engine, initial_target, gun_defn):
    """Chain lightning from Thunder Gun: hit up to 2 additional unique targets within 2 tiles."""
    hit_set = {initial_target.instance_id}
    current = initial_target
    for hop in range(2):
        candidates = []
        for ent in engine.dungeon.get_monsters():
            if not ent.alive or ent.instance_id in hit_set:
                continue
            dist = max(abs(ent.x - current.x), abs(ent.y - current.y))
            if dist <= 2:
                candidates.append(ent)
        if not candidates:
            break
        chain_target = random.choice(candidates)
        hit_set.add(chain_target.instance_id)
        chain_dmg = random.randint(1, 30)
        chain_dmg = max(MIN_DAMAGE, chain_dmg - chain_target.defense)
        mult = engine.player_stats.outgoing_damage_mult
        if mult != 1.0:
            chain_dmg = int(chain_dmg * mult)
        chain_dmg = _apply_toxic_frenzy(engine, chain_dmg)
        chain_killed = combat.deal_damage(engine, chain_dmg, chain_target)
        engine.messages.append([
            ("Chain! ", (255, 255, 80)),
            (f"Lightning arcs to {chain_target.name} for {chain_dmg} damage!", (200, 220, 255)),
        ])
        if chain_killed:
            engine.event_bus.emit("entity_died", entity=chain_target, killer=engine.player)
            notify_gun_kill(engine)
        current = chain_target


def _action_reload_gun(engine, _action):
    """Reload the primary gun from inventory ammo. Also clears jams."""
    gun = _get_primary_gun(engine)
    if gun is None:
        engine.messages.append("No gun equipped.")
        return False
    gun_defn = get_item_def(gun.item_id)
    if gun_defn is None:
        return False

    # Block reload for temporary guns (e.g. Toxic Slingshot)
    if gun_defn.get("no_reload"):
        engine.messages.append("This gun cannot be reloaded.")
        return False

    # Clear jam if jammed (costs energy, doesn't reload ammo)
    if engine.gun_jammed:
        engine.gun_jammed = False
        jam_cost = gun_defn.get("jam_clear_cost", 100)
        engine.messages.append([
            ("Cleared the jam! ", (100, 255, 100)),
            (f"({gun.current_ammo}/{gun.mag_size})", (200, 200, 200)),
        ])
        if jam_cost > 0:
            engine.player.energy -= jam_cost
            if engine.running and engine.player.alive:
                engine._run_energy_loop()
        return False

    if gun.current_ammo >= gun.mag_size:
        engine.messages.append("Magazine is already full.")
        return False

    # Reload-per-floor limit (e.g. Decimator: 1 reload per floor)
    reload_limit = gun_defn.get("reload_per_floor")
    if reload_limit is not None:
        used = getattr(gun, 'reloads_this_floor', 0)
        if used >= reload_limit:
            engine.messages.append([
                ("Cannot reload — ", (255, 100, 100)),
                (f"limited to {reload_limit} reload{'s' if reload_limit != 1 else ''} per floor.", (200, 200, 200)),
            ])
            return False

    ammo_type = gun_defn.get("ammo_type")
    # Find matching ammo in inventory
    ammo_item = None
    for inv_item in engine.player.inventory:
        if inv_item.item_id and inv_item.entity_type == "item":
            idef = get_item_def(inv_item.item_id)
            if idef and idef.get("ammo_type") == ammo_type and idef.get("category") == "ammo":
                ammo_item = inv_item
                break

    if ammo_item is None:
        engine.messages.append(f"No {ammo_type} ammo in inventory.")
        return False

    needed = gun.mag_size - gun.current_ammo
    loaded = min(needed, ammo_item.quantity)
    gun.current_ammo += loaded
    ammo_item.quantity -= loaded
    if ammo_item.quantity <= 0:
        engine.player.inventory.remove(ammo_item)

    engine.messages.append(f"Reloaded {loaded} rounds. ({gun.current_ammo}/{gun.mag_size})")

    # Track reload-per-floor usage
    if gun_defn.get("reload_per_floor") is not None:
        gun.reloads_this_floor = getattr(gun, 'reloads_this_floor', 0) + 1

    # Spend energy if reload has a cost
    reload_speed = gun_defn.get("reload_speed", 0)
    if reload_speed > 0:
        engine.player.energy -= reload_speed
        if engine.running and engine.player.alive:
            engine._run_energy_loop()
    return False  # energy handled internally (or free action)


def _action_swap_primary_gun(engine, _action):
    """Toggle the primary gun between weapon and sidearm slots."""
    weapon = engine.equipment.get("weapon")
    sidearm = engine.equipment.get("sidearm")
    weapon_is_gun = weapon is not None and get_item_def(weapon.item_id).get("subcategory") == "gun"
    sidearm_is_gun = sidearm is not None and get_item_def(sidearm.item_id).get("subcategory") == "gun"

    if weapon_is_gun and sidearm_is_gun:
        if engine.primary_gun == "weapon":
            engine.primary_gun = "sidearm"
            engine.messages.append(f"Switched to {sidearm.name}.")
        else:
            engine.primary_gun = "weapon"
            engine.messages.append(f"Switched to {weapon.name}.")
    elif weapon_is_gun:
        engine.primary_gun = "weapon"
        engine.messages.append("Only one gun equipped.")
    elif sidearm_is_gun:
        engine.primary_gun = "sidearm"
        engine.messages.append("Only one gun equipped.")
    else:
        engine.messages.append("No guns equipped.")
    return False
