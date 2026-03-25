"""
Combat-related functions extracted from engine.py.

All methods that were originally on GameEngine are now module-level functions
that take ``engine`` as their first parameter.
"""

import math
import random

from config import (
    MIN_DAMAGE, UNARMED_STR_BASE,
)
from items import get_item_def
import effects


MEGA_CRIT_MULTIPLIER = 4


def check_mega_crit(engine) -> bool:
    """Sniping L3: if you crit, roll again — second crit = mega crit (4x).
    Only works with melee weapons or guns in accurate mode."""
    if engine.skills.get("Sniping").level < 3:
        return False
    return random.random() < engine.player_stats.crit_chance


# ------------------------------------------------------------------
# Toxicity multipliers (module-level helpers, no engine needed)
# ------------------------------------------------------------------

def _player_toxicity_multiplier(toxicity: int) -> float:
    """Damage-taken 'more' multiplier for the player.
    200 tox = 2x, 1000 tox ≈ 3.4x. Formula: 1 + (tox/200)^0.6"""
    if toxicity <= 0:
        return 1.0
    return 1.0 + (toxicity / 200) ** 0.6


def _monster_toxicity_multiplier(toxicity: int) -> float:
    """Damage-taken 'more' multiplier for monsters (more sensitive than player).
    50 tox = 2x, 500 tox ≈ 5x. Formula: 1 + (tox/50)^0.6"""
    if toxicity <= 0:
        return 1.0
    return 1.0 + (toxicity / 50) ** 0.6


# ------------------------------------------------------------------
# Death behaviors (split, creep)
# ------------------------------------------------------------------

def _spawn_death_split(engine, entity):
    """Spawn child monsters at adjacent free tiles when entity dies."""
    from enemies import create_enemy as _create_enemy
    from ai import get_initial_state as _get_initial_state
    split_type = entity.death_split_type
    count = entity.death_split_count
    # Find adjacent free tiles
    free_tiles = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            nx, ny = entity.x + dx, entity.y + dy
            if not engine.dungeon.is_blocked(nx, ny):
                free_tiles.append((nx, ny))
    random.shuffle(free_tiles)
    spawned = 0
    for tx, ty in free_tiles:
        if spawned >= count:
            break
        child = _create_enemy(split_type, tx, ty)
        child.ai_state = _get_initial_state(child.ai_type)
        engine.dungeon.add_entity(child)
        spawned += 1
    if spawned > 0:
        engine.messages.append(
            f"{entity.name} splits into {spawned} creatures!"
        )


def _spawn_death_creep(engine, entity):
    """Spawn toxic creep tiles in a diamond pattern around entity's death position."""
    from hazards import create_toxic_creep
    radius = entity.death_creep_radius
    duration = entity.death_creep_duration
    tox = entity.death_creep_tox
    ex, ey = entity.x, entity.y
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if abs(dx) + abs(dy) > radius:
                continue
            nx, ny = ex + dx, ey + dy
            if engine.dungeon.is_terrain_blocked(nx, ny):
                continue
            # Don't double-stack toxic creep
            has_creep = any(
                getattr(e, "hazard_type", None) == "toxic_creep"
                for e in engine.dungeon.get_entities_at(nx, ny)
            )
            if not has_creep:
                creep = create_toxic_creep(nx, ny, duration=duration, tox_per_turn=tox)
                engine.dungeon.add_entity(creep)
    engine.messages.append(f"{entity.name} dissolves into a toxic puddle!")


def spawn_trail_creep(engine, x, y, trail_info):
    """Spawn a toxic creep tile at (x, y) from a trail-leaving monster."""
    from hazards import create_toxic_creep
    # Don't double-stack
    has_creep = any(
        getattr(e, "hazard_type", None) == "toxic_creep"
        for e in engine.dungeon.get_entities_at(x, y)
    )
    if not has_creep:
        creep = create_toxic_creep(
            x, y,
            duration=trail_info.get("duration", 10),
            tox_per_turn=trail_info.get("tox", 5),
        )
        engine.dungeon.add_entity(creep)


# ------------------------------------------------------------------
# Suicide / Chemist attack handlers
# ------------------------------------------------------------------

def handle_suicide_explosion(engine, monster):
    """Handle a suicide bomber exploding adjacent to the player."""
    damage = random.randint(10, 15)
    # Unblockable — no defense subtraction
    damage = _apply_toxicity(engine, damage, engine.player)
    damage = _armor_up_check(engine, damage)
    engine.player.take_damage(damage)
    engine._gain_catchin_fades_xp(damage)
    engine._graffiti_proc_green()
    engine._smoking_proc_on_hit()
    tox = random.randint(20, 30)
    add_toxicity(engine, engine.player, tox)
    engine.messages.append(
        f"{monster.name} explodes! {damage} damage + {tox} toxicity!"
    )
    monster.alive = False
    engine.event_bus.emit("entity_died", entity=monster, killer=engine.player)
    if not engine.player.alive:
        engine.event_bus.emit("entity_died", entity=engine.player, killer=monster)


def handle_chemist_vial(engine, monster):
    """Handle a chemist throwing a toxic vial at the player's position."""
    from ai import _has_los
    from hazards import create_toxic_creep
    mx, my = monster.x, monster.y
    px, py = engine.player.x, engine.player.y
    dist = max(abs(mx - px), abs(my - py))
    if dist > 5 or not _has_los(engine.dungeon, mx, my, px, py):
        return
    # Only create if no existing toxic_creep at target tile
    has_creep = any(
        getattr(e, "hazard_type", None) == "toxic_creep"
        for e in engine.dungeon.get_entities_at(px, py)
    )
    if not has_creep:
        creep = create_toxic_creep(px, py, duration=10, tox_per_turn=5)
        engine.dungeon.add_entity(creep)
    engine.messages.append(f"{monster.name} hurls a toxic vial at you!")


# ------------------------------------------------------------------
# Stat computation helpers
# ------------------------------------------------------------------

def _compute_str_bonus(engine, weapon_item):
    """Return the stat damage bonus for the given weapon (or unarmed)."""
    strength = engine.player_stats.effective_strength
    if weapon_item is None:
        return strength - UNARMED_STR_BASE
    defn = get_item_def(weapon_item.item_id)
    # STR-based scaling
    scaling = defn.get("str_scaling")
    if scaling:
        if scaling["type"] == "tiered":
            req = defn.get("str_req", 1)
            divisor = scaling.get("divisor", 2)
            return max(0, (strength - req) // divisor)
        if scaling["type"] == "linear":
            base = scaling.get("base", UNARMED_STR_BASE)
            return max(0, strength - base)
        if scaling["type"] == "diminishing_tiered":
            req = defn.get("str_req", 1)
            excess = max(0, strength - req)
            bonus = 0
            divisor = 1
            tier_size = 2
            remaining = excess
            while remaining > 0:
                if divisor >= 8:
                    bonus += remaining // 8
                    break
                chunk = min(remaining, tier_size)
                bonus += chunk // divisor
                remaining -= chunk
                divisor += 1
                tier_size += 2
            return bonus
        if scaling["type"] == "ratio":
            req = defn.get("str_req", 1)
            numer = scaling.get("numerator", 1)
            denom = scaling.get("denominator", 1)
            return max(0, (strength - req) * numer // denom)
    # Arbitrary stat scaling (threshold or swagger_linear)
    stat_scaling = defn.get("stat_scaling")
    if stat_scaling:
        if stat_scaling["type"] == "threshold":
            stat_name = stat_scaling["stat"]
            threshold = stat_scaling["threshold"]
            stat_value = getattr(engine.player_stats, f"effective_{stat_name}", 0)
            return max(0, stat_value - threshold)
        if stat_scaling["type"] == "swagger_linear":
            divisor = stat_scaling.get("divisor", 2)
            multiplier = stat_scaling.get("multiplier", 1)
            swagger = getattr(engine.player_stats, "effective_swagger", 0)
            return (swagger * multiplier) // divisor
    return 0


def _compute_player_attack_power(engine):
    """Compute the player's total attack power including equipment and STR.

    If the weapon slot holds a gun (subcategory "gun"), melee does a flat
    gun-butt strike (3 damage + gun's melee_bonus if any) with no STR scaling.
    """
    weapon = engine.equipment["weapon"]
    weapon_defn = get_item_def(weapon.item_id) if weapon else None

    # Gun in weapon slot: flat gun-butt damage, no STR scaling
    is_gun = weapon_defn and weapon_defn.get("subcategory") == "gun"
    if is_gun:
        atk_power = 3 + weapon_defn.get("melee_bonus", 0)
    elif weapon and weapon_defn and isinstance(weapon_defn.get("base_damage"), int):
        atk_power = weapon_defn["base_damage"]
    else:
        atk_power = engine.player.power

    # Ring power bonuses
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                atk_power += defn.get("power_bonus", 0)

    # Neck power bonus
    if engine.neck is not None:
        defn = get_item_def(engine.neck.item_id)
        if defn:
            atk_power += defn.get("power_bonus", 0)

    # Feet power bonus
    if engine.feet is not None:
        defn = get_item_def(engine.feet.item_id)
        if defn:
            atk_power += defn.get("power_bonus", 0)

    # Hat power bonus
    if engine.hat is not None:
        defn = get_item_def(engine.hat.item_id)
        if defn:
            atk_power += defn.get("power_bonus", 0)

    if not is_gun:
        atk_power += _compute_str_bonus(engine, weapon)
    return atk_power


def _compute_player_defense(engine):
    """Compute the player's total melee defence including equipment and swagger."""
    defense = engine.player.defense
    weapon = engine.equipment["weapon"]
    if weapon is not None:
        defn = get_item_def(weapon.item_id)
        if defn:
            defense += defn.get("defense_bonus", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                defense += defn.get("defense_bonus", 0)
    if engine.neck is not None:
        defn = get_item_def(engine.neck.item_id)
        if defn:
            defense += defn.get("defense_bonus", 0)
    if engine.feet is not None:
        defn = get_item_def(engine.feet.item_id)
        if defn:
            defense += defn.get("defense_bonus", 0)
    if engine.hat is not None:
        defn = get_item_def(engine.hat.item_id)
        if defn:
            defense += defn.get("defense_bonus", 0)
    defense += engine.player_stats.swagger_defence
    defense += getattr(engine.player_stats, 'permanent_dr', 0)
    defense += getattr(engine.player_stats, 'tile_defense_bonus', 0)
    return defense


def _compute_player_max_armor(engine):
    """Compute the player's total max armor including equipment bonuses."""
    max_armor = 0
    weapon = engine.equipment["weapon"]
    if weapon is not None:
        defn = get_item_def(weapon.item_id)
        if defn:
            max_armor += defn.get("armor_bonus", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                max_armor += defn.get("armor_bonus", 0)
    if engine.neck is not None:
        defn = get_item_def(engine.neck.item_id)
        if defn:
            max_armor += defn.get("armor_bonus", 0)
    if engine.feet is not None:
        defn = get_item_def(engine.feet.item_id)
        if defn:
            max_armor += defn.get("armor_bonus", 0)
    if engine.hat is not None:
        defn = get_item_def(engine.hat.item_id)
        if defn:
            max_armor += defn.get("armor_bonus", 0)
    # Add permanent and temporary armor bonuses
    max_armor += getattr(engine.player_stats, 'permanent_armor_bonus', 0)
    max_armor += getattr(engine.player_stats, 'temporary_armor_bonus', 0)
    return max_armor


# ------------------------------------------------------------------
# Damage modifier helpers
# ------------------------------------------------------------------

def _apply_damage_modifiers(engine, damage: int, defender) -> int:
    """Apply modify_incoming_damage hooks from defender's status effects."""
    for eff in defender.status_effects:
        damage = eff.modify_incoming_damage(damage, defender)
    return damage


def _armor_up_check(engine, damage: int) -> int:
    """L Farming L4 'Armor Up': 35% chance to reduce damage to 1 if player has armor."""
    from skills import Skill
    skill = getattr(engine, 'skills', None)
    if skill is None:
        return damage
    cf = skill.get("L Farming")
    if not isinstance(cf, Skill) or cf.level < 4:
        return damage
    if engine.player.armor <= 0:
        return damage
    if random.random() < 0.35:
        engine.messages.append([
            ("Armor Up! ", (150, 200, 255)),
            ("Damage blocked to 1!", (200, 220, 255)),
        ])
        return 1
    return damage


def _apply_toxicity(engine, damage: int, defender) -> int:
    """Apply toxicity 'more' multiplier to incoming damage (multiplicative after all other mods)."""
    tox = getattr(defender, 'toxicity', 0)
    if tox <= 0:
        return damage
    if defender is engine.player:
        mult = _player_toxicity_multiplier(tox)
    else:
        mult = _monster_toxicity_multiplier(tox)
    return max(1, int(damage * mult))


def apply_tile_amps(engine, damage: int, defender) -> int:
    """Apply all tile-based damage amplifications to the defender.

    Checks the tile the defender is standing on and applies any active amps.
    Add new tile amp types (spray paint colours, etc.) as branches here.
    """
    spray = engine.dungeon.spray_paint.get((defender.x, defender.y))
    if spray == "red":
        damage = max(1, int(damage * 1.25))
    return damage


def deal_damage(engine, damage: int, target) -> bool:
    """Apply tile amps then deal damage to a target.  Returns True if killed.

    Use this for all direct damage (melee, guns, spells/abilities).
    DoTs and debuff ticks should call target.take_damage() directly
    so tile amps do not apply to them.
    """
    damage = apply_tile_amps(engine, damage, target)
    return target.take_damage(damage)


def add_toxicity(engine, entity, amount: int, from_player: bool = False,
                 pierce_resistance: bool = False):
    """Add toxicity to an entity, reduced by its tox resistance.

    Formula: actual = amount * (1 - resistance/100).
    At 100% resistance, gain is 0.  Negative resistance increases gain.
    from_player: set True when the player is the source (weapons, spells, consumables).
    pierce_resistance: if True, ignore resistance entirely (full amount applied, XP still granted).
    """
    if amount <= 0:
        return
    if pierce_resistance:
        gain = amount
        resisted = 0
    else:
        if entity is engine.player:
            res = engine.player_stats.total_tox_resistance
        else:
            res = getattr(entity, 'tox_resistance', 0)
        actual = amount * (1 - res / 100)
        gain = max(0, int(round(actual)))
        resisted = amount - gain
    if gain > 0:
        entity.toxicity += gain
    # Chemical Warfare XP: 2 per point of toxicity gained (player receives tox)
    if entity is engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Chemical Warfare", gain * 2, bksmt)
    # Chemical Warfare XP: half of toxicity spread to enemies by the player
    if from_player and entity is not engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Chemical Warfare", max(1, gain // 2), bksmt)
    # White Power XP: 1 per point of toxicity resisted (doubled by "Pure" perk at L2)
    if entity is engine.player and resisted > 0:
        bksmt = engine.player_stats.effective_book_smarts
        xp = resisted
        if engine.skills.get("White Power").level >= 3:
            xp *= 2
        engine.skills.gain_potential_exp("White Power", xp, bksmt)


def remove_toxicity(engine, entity, amount: int):
    """Remove toxicity from an entity. Clamps at 0.

    White Power XP: 2 per point of toxicity actually removed (player only).
    """
    if amount <= 0 or entity.toxicity <= 0:
        return
    removed = min(amount, entity.toxicity)
    entity.toxicity -= removed
    # White Power XP: 2 per point removed
    if entity is engine.player and removed > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("White Power", removed * 2, bksmt)


def add_radiation(engine, entity, amount: int, pierce_resistance: bool = False,
                  from_player: bool = False):
    """Add radiation to an entity, reduced by its rad resistance.

    Formula: actual = amount * (1 - resistance/100).
    At 100% resistance, gain is 0.  Negative resistance increases gain.
    pierce_resistance: if True, ignore resistance entirely (full amount applied, XP still granted).
    from_player: set True when the player is the source (curses, spells, consumables).
    """
    if amount <= 0:
        return
    if pierce_resistance:
        gain = amount
        resisted = 0
    else:
        if entity is engine.player:
            res = engine.player_stats.total_rad_resistance
        else:
            res = getattr(entity, 'rad_resistance', 0)
        actual = amount * (1 - res / 100)
        # Apply rad gain multiplier (e.g., Five Loco doubles rad gain)
        if entity is engine.player:
            actual *= (1.0 + engine.player_stats.rad_gain_multiplier_bonus)
        gain = max(0, int(round(actual)))
        resisted = amount - gain
    # Nuclear Research L1 "Irradiated Intellect": bonus rad = gain * (book_smarts / 100)
    if entity is engine.player and gain > 0 and engine.skills.get("Nuclear Research").level >= 1:
        bonus = round(gain * engine.player_stats.effective_book_smarts / 100)
        if bonus > 0:
            gain += bonus
    if gain > 0:
        entity.radiation += gain
    # Nuclear Research XP: 2 per point of radiation gained
    if entity is engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Nuclear Research", gain * 2, bksmt)
        # Force Sensitive: notify buff of rad gained
        for eff in entity.status_effects:
            if getattr(eff, 'id', '') == 'force_sensitive':
                eff.on_rad_gained(entity, engine, gain)
                break
    # Nuclear Research XP: half of radiation spread to enemies by the player
    if from_player and entity is not engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Nuclear Research", max(1, gain // 2), bksmt)
    # Glow Up XP: 1 per point of radiation resisted
    if entity is engine.player and resisted > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Glow Up", resisted, bksmt)


def remove_radiation(engine, entity, amount: int):
    """Remove radiation from an entity. Clamps at 0.

    Glow Up XP: 2 per point of radiation actually removed (player only).
    """
    if amount <= 0 or entity.radiation <= 0:
        return
    removed = min(amount, entity.radiation)
    entity.radiation -= removed
    # Glow Up XP: 2 per point removed
    if entity is engine.player and removed > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Glow Up", removed * 2, bksmt)


def add_infection(engine, entity, amount: int):
    """Add infection to an entity, capped at max_infection.

    Infected XP: 2.5 per point of infection gained (player only).
    """
    if amount <= 0:
        return
    max_inf = getattr(entity, 'max_infection', 100)
    old = entity.infection
    entity.infection = min(old + amount, max_inf)
    gained = entity.infection - old
    if entity is engine.player and gained > 0:
        bksmt = engine.player_stats.effective_book_smarts
        xp = round(gained * 2.5)
        engine.skills.gain_potential_exp("Infected", xp, bksmt)


def remove_infection(engine, entity, amount: int):
    """Remove infection from an entity. Clamps at 0."""
    if amount <= 0 or entity.infection <= 0:
        return
    entity.infection = max(0, entity.infection - amount)


def _player_meets_weapon_req(engine) -> bool:
    """Return True if the player meets all stat requirements for their equipped weapon.

    Checks both the legacy `str_req` shorthand and the general `stat_reqs` dict
    (e.g. {"street_smarts": 7, "strength": 5}) against effective stat values.
    """
    weapon = engine.equipment.get("weapon")
    if weapon is None:
        return True
    defn = get_item_def(weapon.item_id)
    if defn is None:
        return True

    # Legacy shorthand: str_req
    reqs = dict(defn.get("stat_reqs", {}))
    if "str_req" in defn:
        reqs.setdefault("strength", defn["str_req"])

    for stat, required in reqs.items():
        effective = getattr(engine.player_stats, f"effective_{stat}", None)
        if effective is None:
            continue
        if effective < required:
            return False
    return True


# ------------------------------------------------------------------
# Main melee attack
# ------------------------------------------------------------------

def handle_attack(engine, attacker, defender, _windfury_eligible=True, force_crit=False):
    """Handle melee attack with equipment bonuses and player stat effects."""
    # Agent Orange: attacker cannot deal melee damage
    if any(getattr(e, 'id', None) == 'agent_orange' for e in attacker.status_effects):
        if attacker == engine.player:
            engine.messages.append("Agent Orange — you can't deal melee damage!")
        return

    # Venom miss chance: effects with miss_chance cause attacks to whiff
    if attacker == engine.player:
        total_miss = sum(getattr(e, 'miss_chance', 0.0) for e in attacker.status_effects)
        if total_miss > 0 and random.random() < total_miss:
            engine.messages.append("Your attack misses! (venom)")
            return

    # Weapon stat requirement check: if player doesn't meet requirements, deal no damage
    # Gun-butt attacks always work (no stat requirement to pistol whip someone)
    _weapon_defn_check = get_item_def(engine.equipment.get("weapon").item_id) if engine.equipment.get("weapon") else None
    _is_gun_weapon = _weapon_defn_check and _weapon_defn_check.get("subcategory") == "gun"
    if attacker == engine.player and not _is_gun_weapon and not _player_meets_weapon_req(engine):
        weapon = engine.equipment.get("weapon")
        defn = get_item_def(weapon.item_id)
        wname = defn.get("name", weapon.name)
        reqs = dict(defn.get("stat_reqs", {}))
        if "str_req" in defn:
            reqs.setdefault("strength", defn["str_req"])
        unmet = [
            stat for stat, req in reqs.items()
            if getattr(engine.player_stats, f"effective_{stat}", req) < req
        ]
        req_strs = ", ".join(
            f"{stat.replace('_', ' ').title()} {reqs[stat]}" for stat in unmet
        )
        engine.messages.append([
            ("Your stats are too low to wield ", (200, 100, 100)),
            (wname, weapon.color),
            (f" (need {req_strs})!", (200, 100, 100)),
        ])
        return

    weapon = engine.equipment.get("weapon") if attacker == engine.player else None
    wdefn = get_item_def(weapon.item_id) if weapon else None
    is_gun_butt = bool(wdefn and wdefn.get("subcategory") == "gun")
    is_crit = force_crit

    if attacker == engine.player:
        atk_power = _compute_player_attack_power(engine)
        # Unstable buff: +2 melee damage
        if any(getattr(e, 'id', '') == 'unstable' for e in attacker.status_effects):
            atk_power += 2
        if not is_crit and random.random() < engine.player_stats.crit_chance:
            is_crit = True
    else:
        atk_power = attacker.power

    if defender == engine.player:
        def_defense = _compute_player_defense(engine)
    else:
        def_defense = defender.defense

    # Check dodge before applying damage
    defender_dodge_chance = engine.player_stats.dodge_chance if defender == engine.player else defender.dodge_chance
    if random.random() * 100 < defender_dodge_chance:
        msg = f"{defender.name} dodges the attack!"
        engine.messages.append(msg)
        return

    damage = max(MIN_DAMAGE, atk_power - def_defense)
    if is_crit:
        crit_mult = engine.crit_multiplier
        # Weapon bonus crit multiplier (e.g. Prison Shank: +1x)
        if attacker == engine.player and weapon and weapon.item_id:
            wdefn_crit = get_item_def(weapon.item_id)
            if wdefn_crit:
                crit_mult += wdefn_crit.get("bonus_crit_mult", 0)
        damage *= crit_mult
    # Outgoing damage multipliers (multiplicative stacking)
    if attacker == engine.player:
        mult = engine.player_stats.outgoing_damage_mult
        if mult != 1.0:
            damage = int(damage * mult)
        # Purge Infection debuff: -50% melee damage
        if any(getattr(e, 'id', '') == 'purge_infection' for e in attacker.status_effects):
            damage = max(MIN_DAMAGE, damage // 2)
    damage = _apply_damage_modifiers(engine, damage, defender)
    damage = _apply_toxicity(engine, damage, defender)

    # Execute bonus (e.g. Lethal Shiv): bonus damage when target is below HP threshold
    # Does not apply to gun-butt attacks
    if attacker == engine.player and weapon and weapon.item_id and not is_gun_butt:
        wdefn_exec = get_item_def(weapon.item_id)
        execute = wdefn_exec.get("execute") if wdefn_exec else None
        if execute and defender.max_hp > 0:
            if defender.hp / defender.max_hp <= execute["threshold"]:
                damage = int(damage * execute["multiplier"])

    deal_damage(engine, damage, defender)

    # On-hit effects: notify player's active buffs/debuffs
    if attacker == engine.player:
        # Gatting L1: melee resets consecutive shot tracker
        engine.gatting_consecutive_target_id = None
        engine.gatting_consecutive_count = 0
        engine._check_glow_up_proc(defender)
        engine._graffiti_proc_red(defender)
        for eff in list(engine.player.status_effects):
            eff.on_player_melee_hit(engine, defender, damage)

        # Meth-Head L1 "Sped": 20% on-hit chance, costs 10 meth, blocked if already active
        if (engine.skills.get("Meth-Head").level >= 1
                and engine.player.meth >= 10
                and not any(getattr(e, 'id', '') == 'sped' for e in engine.player.status_effects)
                and random.random() < 0.20):
            engine.player.meth -= 10
            effects.apply_effect(engine.player, engine, "sped")
            engine.messages.append([
                ("Sped! ", (0, 200, 255)),
                ("Melee attacks cost half energy for 5 turns. (-10 meth)", (150, 220, 255)),
            ])

        # Mutation L2 "Unstable": 20% on-hit chance, grants Unstable buff (20t)
        if (engine.skills.get("Mutation").level >= 2
                and random.random() < 0.20):
            effects.apply_effect(engine.player, engine, "unstable")
            engine.messages.append([
                ("Unstable! ", (100, 255, 100)),
                ("+5 rad, +2 melee dmg, hits irradiate enemies for 20 turns.", (160, 255, 160)),
            ])

    # Weapon on-hit effects (e.g. Glass Shards, Meth-Head XP)
    # Skipped for gun-butt attacks — gun on-hit effects only apply to shots
    if attacker == engine.player and not is_gun_butt:
        weapon = engine.equipment.get("weapon")
        if weapon:
            wdefn = get_item_def(weapon.item_id)
            if wdefn:
                # Vampiric (e.g. Bone Club): heal 30% of damage dealt after defense
                vampiric = wdefn.get("vampiric", 0)
                if vampiric and damage > 0:
                    heal_amt = max(1, int(damage * vampiric))
                    engine.player.heal(heal_amt)

                on_hit = wdefn.get("on_hit_effect")
                if on_hit:
                    effects.apply_effect(
                        defender, engine, on_hit["type"],
                        stacks=on_hit.get("stacks", 1),
                        duration=on_hit.get("duration", 5),
                        silent=True,
                    )
                skill_xp = wdefn.get("on_hit_skill_xp")
                if skill_xp:
                    # Check if skill is newly unlocked (no XP before this call)
                    skill = engine.skills.get(skill_xp["skill"])
                    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

                    xp_amount = round(skill_xp["amount"] * engine.player_stats.xp_multiplier)
                    engine.skills.gain_potential_exp(
                        skill_xp["skill"], xp_amount,
                        engine.player_stats.effective_book_smarts,
                        briskness=engine.player_stats.total_briskness
                    )
                    # Add unlock notification if this is the first XP
                    if was_locked:
                        engine.messages.append([
                            (f"[NEW SKILL UNLOCKED] {skill_xp['skill']}!", (255, 215, 0)),
                        ])
                # Stun on-hit chance (e.g. Blackjack)
                stun_chance = wdefn.get("on_hit_stun_chance", 0)
                if stun_chance and random.random() < stun_chance:
                    stun_dur = wdefn.get("stun_duration", 3)
                    effects.apply_effect(defender, engine, "stun", duration=stun_dur, silent=True)
                    engine.messages.append(f"{defender.name} is stunned!")

                # Disarm on-hit chance (e.g. Monkey Wrench)
                disarm_chance = wdefn.get("on_hit_disarm_chance", 0)
                if disarm_chance and random.random() < disarm_chance:
                    disarm_dur = wdefn.get("disarm_duration", 3)
                    effects.apply_effect(defender, engine, "disarmed", duration=disarm_dur, silent=True)
                    engine.messages.append(f"{defender.name} is disarmed!")

                # Sunder: permanently reduce defender defense by 1 (e.g. Masonry Hammer)
                sunder = wdefn.get("on_hit_sunder", 0)
                if sunder and defender.alive:
                    defender.defense -= sunder

                # Bounce chain (e.g. Extension Cord): arc to nearest adjacent enemy
                bounce = wdefn.get("on_hit_bounce")
                if bounce and defender.alive and random.random() < bounce["chance"]:
                    bounce_target = min(
                        (
                            m for m in engine.dungeon.get_monsters()
                            if m.alive and m is not defender
                            and max(abs(m.x - defender.x), abs(m.y - defender.y)) <= 1
                        ),
                        key=lambda m: max(abs(m.x - defender.x), abs(m.y - defender.y)),
                        default=None,
                    )
                    if bounce_target:
                        bounce_dmg = max(1, int(damage * bounce["damage_pct"]))
                        bounce_target.take_damage(bounce_dmg)
                        engine.messages.append(
                            f"The cord arcs to {bounce_target.name}! ({bounce_dmg} dmg)"
                        )
                        if not bounce_target.alive:
                            engine.event_bus.emit("entity_died", entity=bounce_target, killer=engine.player)

                # On-hit radiation (e.g. Uranium Tip Spear): rad to both defender and player
                on_hit_rad = wdefn.get("on_hit_rad")
                if on_hit_rad and defender.alive:
                    add_radiation(engine, defender, on_hit_rad["enemy"])
                    add_radiation(engine, engine.player, on_hit_rad["self"])

                # On-hit meth gain (e.g. Shard of Meth): player gains meth per hit
                on_hit_meth = wdefn.get("on_hit_meth", 0)
                if on_hit_meth:
                    p = engine.player
                    p.meth = min(p.meth + on_hit_meth, p.max_meth)

                # On-hit toxicity (e.g. Syringe Lance): tox to defender and/or self
                on_hit_tox = wdefn.get("on_hit_tox")
                if on_hit_tox:
                    if on_hit_tox.get("enemy") and defender.alive:
                        add_toxicity(engine, defender, on_hit_tox["enemy"], from_player=True)
                    if on_hit_tox.get("self"):
                        add_toxicity(engine, engine.player, on_hit_tox["self"])

                # Grease on-hit chance (e.g. Deep Fryer Basket)
                grease_chance = wdefn.get("on_hit_grease_chance", 0)
                if grease_chance and defender.alive and random.random() < grease_chance:
                    effects.apply_effect(defender, engine, "greasy", duration=20, stacks=1, silent=True)
                    engine.messages.append(f"{defender.name} is coated in grease!")

                # Ignite-if-greasy on-hit chance (e.g. Deep Fryer Basket)
                ignite_greasy_chance = wdefn.get("on_hit_ignite_if_greasy", 0)
                if ignite_greasy_chance and defender.alive and random.random() < ignite_greasy_chance:
                    has_greasy = any(getattr(e, 'id', '') == 'greasy' for e in defender.status_effects)
                    if has_greasy:
                        effects.apply_effect(defender, engine, "ignite", duration=3, silent=True)
                        engine.messages.append(f"{defender.name}'s grease ignites!")

                # Knockback on-hit chance (e.g. War Maul): push enemy back, no collision dmg
                kb = wdefn.get("on_hit_knockback")
                if kb and defender.alive and random.random() < kb["chance"]:
                    dx = defender.x - engine.player.x
                    dy = defender.y - engine.player.y
                    if dx != 0:
                        dx = dx // abs(dx)
                    if dy != 0:
                        dy = dy // abs(dy)
                    ox, oy = defender.x, defender.y
                    cx, cy = ox, oy
                    for _ in range(kb["tiles"]):
                        nx, ny = cx + dx, cy + dy
                        if engine.dungeon.is_blocked(nx, ny):
                            break
                        engine.dungeon.move_entity(defender, nx, ny)
                        cx, cy = nx, ny
                    if (cx, cy) != (ox, oy):
                        engine.messages.append(f"{defender.name} is knocked back!")

                # Food on-hit chance (e.g. Metal Lunchbox): add random food to inventory
                food_chance = wdefn.get("on_hit_food_chance", 0)
                if food_chance and random.random() < food_chance:
                    from loot import ZONE_FOOD_TABLES
                    from items import create_item_entity
                    zone_key = engine._get_zone_info()[0] if hasattr(engine, '_get_zone_info') else "crack_den"
                    food_table = ZONE_FOOD_TABLES.get(zone_key, []) or ZONE_FOOD_TABLES.get("crack_den", [])
                    if food_table:
                        food_id = random.choice([f[0] for f in food_table])
                        food_ent = create_item_entity(food_id, 0, 0)
                        engine.player.inventory.append(food_ent)
                        engine.messages.append(f"A {food_ent.name} tumbles out of the lunchbox!")

                # Weapon break chance (e.g. Crooked Baseball Bat)
                break_chance = wdefn.get("break_chance", 0)
                if break_chance and random.random() < break_chance:
                    engine.messages.append(f"Your {weapon.name} breaks!")
                    engine.equipment["weapon"] = None
                    # Revoke any ability the weapon granted
                    granted = wdefn.get("grants_ability")
                    if granted:
                        engine.revoke_ability(granted)

        # Melee skill XP: equal to damage dealt
        _WEAPON_TYPE_SKILL = {"stabbing": "Stabbing", "beating": "Beating"}
        if weapon and wdefn:
            melee_skill = _WEAPON_TYPE_SKILL.get(wdefn.get("weapon_type"))
            # Dual weapon type (e.g. Green Lightsaber): award XP to both skills
            alt_type = wdefn.get("weapon_type_alt")
            if alt_type:
                alt_skill = _WEAPON_TYPE_SKILL.get(alt_type)
                if alt_skill:
                    engine._gain_melee_xp(alt_skill, damage)
        else:
            melee_skill = "Smacking"
        if melee_skill:
            engine._gain_melee_xp(melee_skill, damage)

        # Smacking L3 passive: 10% chance to black eye on unarmed hits
        if (not weapon and attacker == engine.player and defender.alive
                and engine.skills.get("Smacking").level >= 3
                and random.random() < 0.10):
            effects.apply_effect(defender, engine, "black_eye", duration=2, silent=True)
            engine.messages.append(f"Black Eye! {defender.name} gets stunned for 2 turns then staggers!")

    # Acid Armor counterattack: when monster is hit, chance to break player's equipment
    if attacker == engine.player and defender != engine.player:
        acid_armor_effect = next(
            (e for e in defender.status_effects if getattr(e, 'id', '') == 'acid_armor'),
            None
        )
        if acid_armor_effect and random.random() < acid_armor_effect.break_chance:
            engine._acid_armor_break_equipment()

    # Mark the room where combat happened (for room_combat AI like strippers)
    if attacker == engine.player:
        room_idx = engine.dungeon.get_room_index_at(defender.x, defender.y)
        if room_idx is not None:
            engine.dungeon.rooms_with_combat.add(room_idx)

    # Passive monsters become provoked when hit
    if hasattr(defender, "provoked") and not defender.provoked:
        defender.provoked = True
        if getattr(defender, 'name', '') == "Big Nigga Jerome":
            engine.messages.append([
                ("Jerome: ", (220, 80, 50)),
                ("don't fuck with me nigga", (255, 50, 50)),
            ])

    crit_str = " CRITICAL!" if is_crit else ""
    gun_str = " (gun butt)" if is_gun_butt else ""
    msg = f"{attacker.name} deals {damage} damage to {defender.name}{crit_str}{gun_str}"

    if not defender.alive:
        msg += f" ({defender.name} dies)"
        engine.messages.append(msg)
        engine.event_bus.emit("entity_died", entity=defender, killer=attacker)

        # On-kill skill XP (e.g. Deep Fryer Basket)
        if attacker == engine.player and weapon and wdefn:
            kill_xp = wdefn.get("on_kill_skill_xp")
            if kill_xp:
                skill = engine.skills.get(kill_xp["skill"])
                was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0
                xp_amount = round(kill_xp["amount"] * engine.player_stats.xp_multiplier)
                engine.skills.gain_potential_exp(
                    kill_xp["skill"], xp_amount,
                    engine.player_stats.effective_book_smarts,
                    briskness=engine.player_stats.total_briskness
                )
                if was_locked:
                    engine.messages.append([
                        (f"[NEW SKILL UNLOCKED] {kill_xp['skill']}!", (255, 215, 0)),
                    ])
    else:
        engine.messages.append(msg)

    # Gouge break: player damage removes gouge stun from the defender
    if attacker == engine.player and defender.alive:
        gouge_eff = next(
            (e for e in defender.status_effects if getattr(e, 'id', '') == 'gouge'),
            None,
        )
        if gouge_eff:
            defender.status_effects.remove(gouge_eff)
            engine.messages.append(f"{defender.name}'s gouge stun is broken!")

    # Windfury: extra attack with stabbing weapon (Stabbing level 3+)
    if (attacker == engine.player and _windfury_eligible
            and defender.alive
            and engine.skills.get("Stabbing").level >= 3):
        weapon = engine.equipment.get("weapon")
        if weapon:
            wdefn = get_item_def(weapon.item_id)
            from items import weapon_matches_type
            if weapon_matches_type(wdefn, "stabbing"):
                stsmt = engine.player_stats.effective_street_smarts
                chance = min(30, stsmt) / 100.0
                if random.random() < chance:
                    engine.messages.append("Windfury! Your blade strikes again!")
                    handle_attack(engine, attacker, defender, _windfury_eligible=False)


# ------------------------------------------------------------------
# Monster attack handling
# ------------------------------------------------------------------

def handle_monster_attack(engine, monster):
    """Resolve a monster attacking the player."""
    # Distracted: monster's attack misses entirely, effect consumed
    distracted = next(
        (e for e in monster.status_effects if getattr(e, 'id', None) == 'distracted'),
        None,
    )
    if distracted:
        monster.status_effects.remove(distracted)
        engine.messages.append(
            f"{monster.name} is distracted and misses!"
        )
        return

    # Agent Orange: monster cannot deal melee damage
    if any(getattr(e, 'id', None) == 'agent_orange' for e in monster.status_effects):
        return

    player = engine.player
    def_defense = _compute_player_defense(engine)

    # Special attack check
    for sa in monster.special_attacks:
        if random.random() < sa["chance"]:
            # Mark monster as having attacked (for hit-and-run AI)
            monster.has_attacked_player = True

            # Handle Pickpocket (cash stealing) attacks
            if sa.get("name") == "Pickpocket":
                # Steal 1-30 cash (heavily skewed to lower values)
                # Roll 2d10 (lower values more common) with cap at 30
                stolen = min(random.randint(1, 10) + random.randint(1, 10), 30)
                stolen = min(stolen, engine.cash)  # Can't steal more than player has
                engine.cash -= stolen
                engine.messages.append(
                    f"{monster.name} pickpockets you for ${stolen}!"
                )
                return

            mult = sa.get("damage_mult", 1.0)
            # Jerome's and Rad Rat's damage penetrates defense
            # (Well Fed bonus is already baked into monster.power via WellFedEffect.apply)
            if monster.enemy_type in ("big_nigga_jerome", "rad_rat"):
                damage = int(monster.power * mult)
            else:
                damage = max(MIN_DAMAGE, int(monster.power * mult) - def_defense)
            # Monster crit check (special attack)
            is_monster_crit = random.random() * 100 < monster.crit_chance
            if is_monster_crit:
                damage *= 2
            damage = _apply_damage_modifiers(engine, damage, player)
            damage = _apply_toxicity(engine, damage, player)
            if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            if any(getattr(e, 'is_curse', False) and getattr(e, 'id', '') == 'curse_of_ham' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            damage = _armor_up_check(engine, damage)
            deal_damage(engine, damage, player)
            engine._gain_catchin_fades_xp(damage)
            engine._graffiti_proc_green()
            engine._smoking_proc_on_hit()
            crit_str = " CRITICAL!" if is_monster_crit else ""
            engine.messages.append(
                f"{monster.name} hits you with {sa['name']} for {damage} damage!{crit_str}"
            )
            if any(getattr(e, 'id', None) == 'soul_pair' for e in monster.status_effects):
                monster.take_damage(damage)
                engine.messages.append(
                    f"Soul-Pair: {monster.name} shares your pain! (-{damage} HP)"
                )
                if not monster.alive:
                    engine.event_bus.emit("entity_died", entity=monster, killer=player)

            # Handle Knockback Punch
            if sa.get("name") == "Knockback Punch":
                dx = 0 if monster.x == player.x else (1 if player.x > monster.x else -1)
                dy = 0 if monster.y == player.y else (1 if player.y > monster.y else -1)
                nx, ny = player.x + dx, player.y + dy
                if engine.dungeon.is_blocked(nx, ny):
                    engine.messages.append("You brace yourself against the knockback!")
                else:
                    player.x, player.y = nx, ny
                    engine.messages.append("You're knocked back 1 tile!")
                effects.apply_effect(player, engine, "stun", duration=2, silent=True)
                engine.messages.append("You're stunned!")

            hit_eff = sa.get("on_hit_effect")
            if hit_eff:
                _apply_monster_hit_effect(engine, hit_eff, monster=monster)
            if not player.alive:
                engine.event_bus.emit("entity_died", entity=player, killer=monster)
            return

    # Normal attack
    monster.has_attacked_player = True
    # Niglet, Jerome, and Rad Rat damage ignores defense
    # (Jerome's Well Fed bonus is already baked into monster.power via WellFedEffect.apply)
    if monster.enemy_type in ("niglet", "big_nigga_jerome", "rad_rat"):
        damage = monster.power
    else:
        damage = max(MIN_DAMAGE, monster.power - def_defense)
    # Monster crit check (normal attack)
    is_monster_crit = random.random() * 100 < monster.crit_chance
    if is_monster_crit:
        damage *= 2
    damage = _apply_damage_modifiers(engine, damage, player)
    damage = _apply_toxicity(engine, damage, player)
    if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    if any(getattr(e, 'is_curse', False) and getattr(e, 'id', '') == 'curse_of_ham' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    damage = _armor_up_check(engine, damage)
    deal_damage(engine, damage, player)
    engine._gain_catchin_fades_xp(damage)
    engine._graffiti_proc_green()
    engine._smoking_proc_on_hit()
    crit_str = " CRITICAL!" if is_monster_crit else ""
    engine.messages.append(f"{monster.name} hits you for {damage} damage!{crit_str}")

    # Thorns: reflect damage back to attacker from equipped weapon (e.g. Toxic Barb Shiv)
    weapon = engine.equipment.get("weapon")
    if weapon and monster.alive:
        wdefn = get_item_def(weapon.item_id)
        thorns_dmg = wdefn.get("thorns", 0) if wdefn else 0
        if thorns_dmg > 0:
            monster.take_damage(thorns_dmg)
            engine.messages.append(f"Thorns! {monster.name} takes {thorns_dmg} damage!")
            if not monster.alive:
                engine.event_bus.emit("entity_died", entity=monster, killer=player)

    if any(getattr(e, 'id', None) == 'soul_pair' for e in monster.status_effects):
        monster.take_damage(damage)
        engine.messages.append(
            f"Soul-Pair: {monster.name} shares your pain! (-{damage} HP)"
        )
        if not monster.alive:
            engine.event_bus.emit("entity_died", entity=monster, killer=player)

    for hit_eff in monster.on_hit_effects:
        if random.random() < hit_eff["chance"]:
            _apply_monster_hit_effect(engine, hit_eff, monster=monster)

    if not player.alive:
        engine.event_bus.emit("entity_died", entity=player, killer=monster)


def _apply_monster_hit_effect(engine, effect, monster=None):
    """Apply a status debuff from a monster hit to the player."""
    effect_id = effect["kind"]
    amount = effect.get("amount", 0)

    # Instant effects — no duration, applied immediately
    if effect_id == "rad_burst":
        add_radiation(engine, engine.player, amount)
        return
    if effect_id == "tox_burst":
        add_toxicity(engine, engine.player, amount)
        return
    if effect_id == "infection":
        add_infection(engine, engine.player, amount)
        engine.messages.append([
            ("Infected! ", (120, 200, 50)),
            (f"+{amount} infection!", (180, 255, 100)),
        ])
        return
    if effect_id == "stat_drain":
        _DRAIN_STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]
        _DRAIN_LABELS = {
            "constitution": "Constitution", "strength": "Strength",
            "book_smarts": "Book-Smarts", "street_smarts": "Street-Smarts",
            "tolerance": "Tolerance", "swagger": "Swagger",
        }
        stat = random.choice(_DRAIN_STATS)
        ps = engine.player_stats
        current = getattr(ps, stat)
        if current > 1:  # floor at 1
            setattr(ps, stat, current - 1)
            ps._base[stat] = getattr(ps, stat)
            if stat == "constitution":
                engine.player.max_hp = max(10, engine.player.max_hp - 5)
                engine.player.hp = min(engine.player.hp, engine.player.max_hp)
            engine.messages.append([
                ("Cursed! ", (140, 50, 180)),
                (f"{_DRAIN_LABELS[stat]} permanently -1!", (180, 100, 220)),
            ])
        return
    if effect_id == "deport":
        _deport_player(engine, effect["duration"])
        return
    if effect_id == "rad_poison":
        effects.apply_effect(engine.player, engine, "rad_poison",
                             duration=effect["duration"],
                             amount=effect.get("amount", 10))
        return
    if effect_id == "conversion":
        effects.apply_effect(engine.player, engine, "conversion",
                             duration=effect["duration"])
        return
    if effect_id == "rabies":
        effects.apply_effect(engine.player, engine, "rabies",
                             duration=effect["duration"])
        return
    if effect_id == "buff_purge":
        buffs = [e for e in engine.player.status_effects if getattr(e, 'category', '') == 'buff']
        if buffs:
            import random as _rng
            target_buff = _rng.choice(buffs)
            remaining = getattr(target_buff, 'duration', 0)
            target_buff.expire(engine.player, engine)
            engine.player.status_effects.remove(target_buff)
            add_toxicity(engine, engine.player, remaining)
            engine.messages.append(
                f"Your {target_buff.display_name} was purged! (+{remaining} toxicity)"
            )
        return

    # Map specific named effects to their custom effect IDs
    _NAMED_EFFECT_MAP = {
        "Bleeding": "bleeding",
        "pipe_venom": "pipe_venom",
        "wolf_spider_venom": "wolf_spider_venom",
        "neuro_venom": "neuro_venom",
    }
    mapped = _NAMED_EFFECT_MAP.get(effect.get("name"))
    if mapped:
        effect_id = mapped
    duration = effect["duration"]
    # Effects in _NAMED_EFFECT_MAP hardcode their own duration; don't pass it
    kwargs = dict(amount=amount) if mapped else dict(duration=duration, amount=amount)
    # Fear needs the source position so the player flees away from it
    if effect_id == "fear" and monster is not None:
        kwargs["source_x"] = monster.x
        kwargs["source_y"] = monster.y
    effects.apply_effect(engine.player, engine, effect_id, **kwargs)


def handle_monster_ranged_attack(engine, monster):
    """Resolve a monster's ranged attack against the player."""
    from ai import _has_los

    ra = monster.ranged_attack
    if ra is None:
        return

    player = engine.player
    dist = abs(monster.x - player.x) + abs(monster.y - player.y)  # use Chebyshev for range check
    dist = max(abs(monster.x - player.x), abs(monster.y - player.y))

    if dist > ra["range"]:
        return
    if not _has_los(engine.dungeon, monster.x, monster.y, player.x, player.y):
        return

    # Miss check
    if random.random() < ra["miss_chance"]:
        engine.messages.append(f"{monster.name} shoots at you but misses!")
        return

    # Dodge check
    if random.random() * 100 < engine.player_stats.dodge_chance:
        engine.messages.append(f"You dodge {monster.name}'s ranged attack!")
        return

    # Roll damage
    dmg_min, dmg_max = ra["damage"]
    damage = random.randint(dmg_min, dmg_max)
    if not ra.get("pierces_defense"):
        def_defense = _compute_player_defense(engine)
        damage = max(MIN_DAMAGE, damage - def_defense)
        damage = _apply_damage_modifiers(engine, damage, player)
        damage = _apply_toxicity(engine, damage, player)
        damage = _armor_up_check(engine, damage)

    attack_name = ra.get("name", "shoots")
    player.take_damage(damage)
    engine._gain_catchin_fades_xp(damage)
    engine._graffiti_proc_green()
    engine._smoking_proc_on_hit()
    engine.messages.append(f"{monster.name} {attack_name} you for {damage} damage!")

    # Ranged on-hit effect (e.g. hex slow)
    ranged_on_hit = ra.get("on_hit_effect")
    if ranged_on_hit and random.random() < ranged_on_hit.get("chance", 0):
        effect_id = ranged_on_hit["effect_id"]
        effects.apply_effect(engine.player, engine, effect_id, **ranged_on_hit.get("kwargs", {}))

    # Knockback
    knockback = ra.get("knockback", 0)
    knockback_chance = ra.get("knockback_chance", 1.0)
    if knockback > 0 and random.random() < knockback_chance:
        dx = 0 if monster.x == player.x else (1 if player.x > monster.x else -1)
        dy = 0 if monster.y == player.y else (1 if player.y > monster.y else -1)
        nx, ny = player.x + dx, player.y + dy
        if not engine.dungeon.is_blocked(nx, ny):
            player.x, player.y = nx, ny
            engine.messages.append("You're knocked back!")

    if not player.alive:
        engine.event_bus.emit("entity_died", entity=player, killer=monster)


def _deport_player(engine, stun_duration: int):
    """Teleport player to a random walkable tile on the floor and stun."""
    # Gather all walkable, unoccupied tiles
    candidates = []
    for y in range(engine.dungeon.height):
        for x in range(engine.dungeon.width):
            if not engine.dungeon.is_blocked(x, y) and (x, y) != (engine.player.x, engine.player.y):
                candidates.append((x, y))
    if not candidates:
        return
    nx, ny = random.choice(candidates)
    engine.player.x, engine.player.y = nx, ny
    engine._compute_fov()
    effects.apply_effect(engine.player, engine, "stun", duration=stun_duration, silent=True)
    engine.messages.append(f"You've been deported! Stunned for {stun_duration} turns!")


# ------------------------------------------------------------------
# Spawner mechanic
# ------------------------------------------------------------------

def spawn_child(engine, spawner, creature_positions=None):
    """Spawn a child entity adjacent to the spawner (or within 2 tiles)."""
    from enemies import create_enemy
    import ai as ai_module

    child_type = spawner.spawner_type
    if child_type is None:
        return

    # Find a free tile adjacent to spawner, then within 2 tiles
    sx, sy = spawner.x, spawner.y
    candidates = []
    for dist in (1, 2):
        for dx in range(-dist, dist + 1):
            for dy in range(-dist, dist + 1):
                if dx == 0 and dy == 0:
                    continue
                if max(abs(dx), abs(dy)) != dist:
                    continue
                nx, ny = sx + dx, sy + dy
                if engine.dungeon.is_terrain_blocked(nx, ny):
                    continue
                if engine.dungeon.is_blocked(nx, ny):
                    continue
                if creature_positions and (nx, ny) in creature_positions:
                    continue
                candidates.append((nx, ny))
        if candidates:
            break

    if not candidates:
        return

    nx, ny = random.choice(candidates)
    child = create_enemy(child_type, nx, ny)
    child.ai_state = ai_module.get_initial_state(child.ai_type)
    # Inherit spawn room from parent
    if hasattr(spawner, "spawn_room_tiles"):
        child.spawn_room_tiles = spawner.spawn_room_tiles
    engine.dungeon.entities.append(child)
    spawner.spawned_children.append(child)
    if creature_positions is not None:
        creature_positions.add((nx, ny))
    from enemies import MONSTER_REGISTRY
    tmpl = MONSTER_REGISTRY.get(child_type)
    child_name = tmpl.name if tmpl else child_type
    engine.messages.append(f"The {spawner.name} spawns a {child_name}!")
