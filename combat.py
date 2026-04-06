"""
Combat-related functions extracted from engine.py.

All methods that were originally on GameEngine are now module-level functions
that take ``engine`` as their first parameter.
"""

import math
import random

from config import (
    MIN_DAMAGE, UNARMED_STR_BASE, TILE_FLOOR,
    MAX_TOXICITY, MAX_RADIATION,
)
from items import get_item_def, weapon_matches_type
import effects


MEGA_CRIT_MULTIPLIER = 4


def _massive_blunt_smoke_proc(engine):
    """Massive Blunt on-hit: smoke a random joint from the current floor's strain table."""
    from loot import pick_strain
    from items import calc_tolerance_rolls, STRAIN_SMOKING_XP

    zone = engine.current_zone
    strain = pick_strain(zone, engine.player_stats)
    if not strain or strain == "Snickelfritz":
        return

    # Tolerance multi-roll (same as normal smoking)
    tlr = engine.player_stats.effective_tolerance
    num_rolls, roll_floor = calc_tolerance_rolls(strain, tlr)
    rolls = [max(roll_floor + 1, random.randint(1, 100)) for _ in range(num_rolls)]
    roll = max(rolls)

    # Apply the strain effect to the player
    engine._apply_strain_effect(engine.player, strain, roll, "player")

    # Award half Smoking XP
    base_xp = STRAIN_SMOKING_XP.get(strain, 5)
    half_xp = max(1, round(base_xp * 0.5 * engine.player_stats.xp_multiplier))
    engine.skills.gain_potential_exp(
        "Smoking", half_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness,
    )

    engine.messages.append([
        ("Massive Blunt procs! ", (80, 200, 60)),
        (f"Smoked {strain} (roll: {roll}). ", (150, 255, 150)),
        (f"+{half_xp} Smoking XP", (100, 200, 150)),
    ])


def _apply_toxic_frenzy(engine, damage: int) -> int:
    """Chemical Warfare L2: +1% damage per 10 toxicity, capped at 500 tox (+50%)."""
    if engine.skills.get("Chemical Warfare").level >= 2:
        capped_tox = min(engine.player.toxicity, 500)
        if capped_tox > 0:
            bonus = 1.0 + capped_tox / 1000.0  # +0.1% per tox, +1% per 10
            damage = int(damage * bonus)
    return damage


def _overkill_splash(engine, ox: int, oy: int, excess: int, depth: int = 0):
    """Beating L5: splash excess damage to enemies within radius 2. Chains on kill."""
    if excess <= 0 or depth > 20:  # safety cap
        return
    hit_any = False
    for m in list(engine.dungeon.get_monsters()):
        if not m.alive or m is engine.player:
            continue
        if max(abs(m.x - ox), abs(m.y - oy)) <= 2:
            hp_before = m.hp
            m.take_damage(excess)
            hit_any = True
            if not m.alive:
                chain_excess = abs(m.hp)
                engine.messages.append([
                    ("Overkill! ", (255, 100, 40)),
                    (f"{m.name} takes {excess} splash and dies!", (255, 160, 80)),
                ])
                engine.event_bus.emit("entity_died", entity=m, killer=engine.player)
                if chain_excess > 0:
                    _overkill_splash(engine, m.x, m.y, chain_excess, depth + 1)
            else:
                engine.messages.append([
                    ("Overkill! ", (255, 100, 40)),
                    (f"{m.name} takes {excess} splash ({m.hp}/{m.max_hp})", (255, 180, 100)),
                ])
    if hit_any and hasattr(engine, 'sdl_overlay') and engine.sdl_overlay:
        engine.sdl_overlay.add_floating_text(ox, oy, "OVERKILL", (255, 100, 40))


def check_mega_crit(engine) -> bool:
    """Gunplay L6: if you crit, roll again — second crit = mega crit (4x).
    Works with melee weapons and guns."""
    if engine.skills.get("Gunplay").level < 6:
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
    """Handle a chemist throwing a 3x3 toxic vial at the player's position."""
    from ai import _has_los
    from hazards import create_toxic_creep
    mx, my = monster.x, monster.y
    px, py = engine.player.x, engine.player.y
    dist = max(abs(mx - px), abs(my - py))
    if dist > 5 or not _has_los(engine.dungeon, mx, my, px, py):
        return
    # 3x3 AOE centered on player
    placed = 0
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            tx, ty = px + dx, py + dy
            if tx < 0 or tx >= engine.dungeon.width or ty < 0 or ty >= engine.dungeon.height:
                continue
            if engine.dungeon.tiles[ty][tx] != TILE_FLOOR:
                continue
            has_creep = any(
                getattr(e, "hazard_type", None) == "toxic_creep"
                for e in engine.dungeon.get_entities_at(tx, ty)
            )
            if not has_creep:
                creep = create_toxic_creep(tx, ty, duration=10, tox_per_turn=5)
                engine.dungeon.add_entity(creep)
                placed += 1
    engine.messages.append(f"{monster.name} hurls a toxic vial! (3x3 splash)")


def handle_chemist_ranged(engine, monster):
    """Chemist flat damage ranged attack (used when vial is on cooldown)."""
    px, py = engine.player.x, engine.player.y
    damage = max(1, monster.power - _compute_player_defense(engine))
    deal_damage(engine, damage, engine.player)
    engine.messages.append(
        f"{monster.name} flings a shard at you for {damage} damage! "
        f"({engine.player.hp}/{engine.player.max_hp} HP)"
    )
    if not engine.player.alive:
        engine.event_bus.emit("entity_died", entity=engine.player, killer=monster)


# ------------------------------------------------------------------
# Stat computation helpers
# ------------------------------------------------------------------

def _compute_str_bonus(engine, weapon_item):
    """Return the stat damage bonus for the given weapon (or unarmed)."""
    strength = engine.player_stats.effective_strength
    if weapon_item is None:
        return strength - UNARMED_STR_BASE
    defn = get_item_def(weapon_item.item_id)
    # BKS-based scaling (e.g. Rune Scraper: melee scales off Book-Smarts)
    bks_scaling = defn.get("bks_scaling")
    if bks_scaling:
        bks = engine.player_stats.effective_book_smarts
        req = defn.get("bks_req", 1)
        divisor = bks_scaling.get("divisor", 2)
        return max(0, (bks - req) // divisor)
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
    # Dual stat scaling: sum excess from two stats above their thresholds, divide by divisor
    dual = defn.get("dual_stat_scaling")
    if dual:
        total_excess = 0
        for entry in dual["stats"]:
            stat_val = getattr(engine.player_stats, f"effective_{entry['stat']}", 0)
            total_excess += max(0, stat_val - entry["threshold"])
        return total_excess // dual.get("divisor", 4)
    # Arbitrary stat scaling (threshold or swagger_linear)
    stat_scaling = defn.get("stat_scaling")
    if stat_scaling:
        if stat_scaling["type"] == "threshold":
            stat_name = stat_scaling["stat"]
            threshold = stat_scaling["threshold"]
            divisor = stat_scaling.get("divisor", 1)
            stat_value = getattr(engine.player_stats, f"effective_{stat_name}", 0)
            return max(0, (stat_value - threshold) // divisor)
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

    # Enchantment power bonus (Soloman)
    if weapon:
        atk_power += getattr(weapon, "enchant_power_bonus", 0)

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
    # Ramp damage: bonus from weapons with "ramp_damage" tag
    if weapon and weapon_defn and "ramp_damage" in weapon_defn.get("tags", []):
        atk_power += getattr(weapon, "ramp_bonus", 0)
    # Sleeper Agent: bonus from stacks
    if weapon and weapon_defn and "sleeper_agent" in weapon_defn.get("tags", []):
        atk_power += getattr(weapon, "sleeper_stacks", 0)
    # Tolerance scaling: +1 per divisor TOL above tol_req
    tol_scaling = weapon_defn.get("tol_scaling") if weapon_defn else None
    if tol_scaling and not is_gun:
        tol_req = weapon_defn.get("tol_req", 0)
        tol = engine.player_stats.effective_tolerance
        if tol > tol_req:
            atk_power += (tol - tol_req) // tol_scaling["divisor"]
    # Skill scaling: +N damage per level in a specific skill
    sk_scaling = weapon_defn.get("skill_scaling") if weapon_defn else None
    if sk_scaling and not is_gun:
        skill_name = sk_scaling["skill"]
        bonus_per = sk_scaling.get("bonus_per_level", 1)
        skill_obj = engine.skills.skills.get(skill_name)
        if skill_obj:
            atk_power += skill_obj.level * bonus_per
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
        max_armor += getattr(engine.neck, "enchant_armor_bonus", 0)
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
    """Apply toxicity + shocked as an additive 'more' multiplier to incoming damage.
    Shocked adds +10% per stack, additive with the toxicity multiplier.
    Example: 50% tox mult + 30% shocked (3 stacks) = 1.0 + 0.5 + 0.3 = 1.8x total."""
    # Base toxicity bonus
    tox = getattr(defender, 'toxicity', 0)
    tox_bonus = 0.0
    if tox > 0:
        if defender is engine.player:
            tox_bonus = _player_toxicity_multiplier(tox) - 1.0
        else:
            tox_bonus = _monster_toxicity_multiplier(tox) - 1.0

    # Shocked bonus: +10% per stack (additive)
    shocked_bonus = 0.0
    shocked_eff = next((e for e in defender.status_effects
                        if getattr(e, 'id', '') == 'shocked'), None)
    if shocked_eff:
        shocked_bonus = 0.10 * shocked_eff.stacks

    total_mult = 1.0 + tox_bonus + shocked_bonus
    if total_mult <= 1.0:
        return damage
    return max(1, int(damage * total_mult))


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
    # Spell Echo: halve damage on echo casts
    if getattr(engine, '_spell_echo_half_damage', False):
        damage = max(1, damage // 2)
    # Spellweaver (Smartsness L5): +30% damage when alternating spells
    if getattr(engine, '_spellweaver_active', False):
        damage = int(damage * 1.30)
    damage = apply_tile_amps(engine, damage, target)
    # Slashing L3 "Execute": 2x damage to enemies below 25% HP
    if target is not engine.player and target.max_hp > 0:
        if engine.skills.get("Slashing").level >= 3 and target.hp / target.max_hp < 0.25:
            damage *= 2
    killed = target.take_damage(damage)
    # Channel interrupt: 25% chance when the player takes damage
    if target is engine.player and damage > 0:
        engine._channel_interrupt_on_damage()
    # Lifesteal on all player damage (melee/gun/spell)
    if target is not engine.player and damage > 0:
        sangria = next(
            (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'sangria'),
            None,
        )
        if sangria:
            heal = max(1, int(damage * 0.30 * sangria.stacks))
            engine.player.heal(heal)
            engine.messages.append([
                ("Sangria: ", (160, 30, 60)),
                (f"+{heal} HP", (100, 255, 100)),
                (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
            ])
        nine_ring = next(
            (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'nine_ring'),
            None,
        )
        if nine_ring:
            heal = max(1, int(damage * 0.25))
            engine.player.heal(heal)
            engine.messages.append([
                ("The 9 Ring: ", (255, 220, 50)),
                (f"+{heal} HP", (100, 255, 100)),
                (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
            ])
    return killed


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
        entity.toxicity = min(entity.toxicity + gain, MAX_TOXICITY)
    # Chemical Warfare XP: 2 per point of toxicity gained (player receives tox)
    if entity is engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Chemical Warfare", gain * 2, bksmt)
    # Chemical Warfare XP: half of toxicity applied to any enemy
    if entity is not engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Chemical Warfare", max(1, gain // 2), bksmt)
    # White Power XP: 1 per point of toxicity resisted (doubled by "Pure" perk at L2)
    if entity is engine.player and resisted > 0:
        bksmt = engine.player_stats.effective_book_smarts
        xp = resisted
        if engine.skills.get("White Power").level >= 3:
            xp *= 2
        engine.skills.gain_potential_exp("White Power", xp, bksmt)
    # Reject the Poison (WP L1): resisted tox → Purity stacks (min 1 if any resistance)
    if entity is engine.player and engine.skills.get("White Power").level >= 1:
        if not pierce_resistance and amount > 0:
            res = engine.player_stats.total_tox_resistance
            if res > 0:
                stacks_to_add = max(1, resisted)
                existing = next(
                    (e for e in entity.status_effects
                     if getattr(e, 'id', '') == 'purity_stacks'),
                    None,
                )
                if existing:
                    existing.add_stacks(stacks_to_add, engine=engine)
                else:
                    from effects import apply_effect
                    apply_effect(entity, engine, "purity_stacks",
                                 stacks=stacks_to_add, duration=20)
    # Absolution (WP L5): resisted tox deals damage to nearby enemies
    if entity is engine.player and resisted > 0:
        absolution = next(
            (e for e in entity.status_effects if getattr(e, 'id', '') == 'absolution'),
            None,
        )
        if absolution:
            from effects import absolution_on_tox_lost
            absolution_on_tox_lost(engine, resisted)


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
    # Absolution (WP L5): removed tox deals damage to nearby enemies
    if entity is engine.player and removed > 0:
        absolution = next(
            (e for e in entity.status_effects if getattr(e, 'id', '') == 'absolution'),
            None,
        )
        if absolution:
            from effects import absolution_on_tox_lost
            absolution_on_tox_lost(engine, removed)


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
        entity.radiation = min(entity.radiation + gain, MAX_RADIATION)
    # Nuclear Research XP: 2 per point of radiation gained
    if entity is engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Nuclear Research", gain * 2, bksmt)
    # Nuclear Research XP: half of radiation spread to enemies by the player
    if from_player and entity is not engine.player and gain > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Nuclear Research", max(1, gain // 2), bksmt)
    # Decontamination XP: 1 per point of radiation resisted (2x with Gamma Aura)
    if entity is engine.player and resisted > 0:
        bksmt = engine.player_stats.effective_book_smarts
        xp = resisted
        has_gamma = any(getattr(e, 'id', '') == 'gamma_aura'
                        for e in entity.status_effects)
        if has_gamma:
            xp *= 2
        engine.skills.gain_potential_exp("Decontamination", xp, bksmt)


def remove_radiation(engine, entity, amount: int):
    """Remove radiation from an entity. Clamps at 0.

    Decontamination XP: 2 per point of radiation actually removed (player only).
    """
    if amount <= 0 or entity.radiation <= 0:
        return
    removed = min(amount, entity.radiation)
    entity.radiation -= removed
    # Decontamination XP: 2 per point removed
    if entity is engine.player and removed > 0:
        bksmt = engine.player_stats.effective_book_smarts
        engine.skills.gain_potential_exp("Decontamination", removed * 2, bksmt)
        # Force Sensitive: notify buff of rad lost
        for eff in entity.status_effects:
            if getattr(eff, 'id', '') == 'force_sensitive':
                eff.on_rad_lost(entity, engine, removed)
                break


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

def handle_attack(engine, attacker, defender, _windfury_eligible=True, force_crit=False, _whirlwind_eligible=True):
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

    # Whirlwind Axe: 30% chance to replace attack with whirlwind (hits all adjacent)
    if (attacker == engine.player and _whirlwind_eligible
            and wdefn and "whirlwind_axe" in wdefn.get("tags", [])
            and random.random() < 0.30):
        px, py = attacker.x, attacker.y
        targets = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                for e in engine.dungeon.get_entities_at(px + dx, py + dy):
                    if e.entity_type == "monster" and e.alive:
                        targets.append(e)
        if targets:
            hit_count = len(targets)
            engine.messages.append([
                ("Whirlwind! ", (255, 100, 60)),
                (f"Cleaving {hit_count} {'enemy' if hit_count == 1 else 'enemies'}!", (255, 180, 140)),
            ])
            for t in targets:
                if t.alive:
                    handle_attack(engine, attacker, t, _whirlwind_eligible=False)
            return

    if attacker == engine.player:
        atk_power = _compute_player_attack_power(engine)
        # Unstable buff: +2 melee damage
        if any(getattr(e, 'id', '') == 'unstable' for e in attacker.status_effects):
            atk_power += 2
        # Swashbuckling: +1 per stack with slashing weapons
        if wdefn and weapon_matches_type(wdefn, "slashing"):
            swash = next((e for e in attacker.status_effects if getattr(e, 'id', '') == 'swashbuckling'), None)
            if swash:
                atk_power += swash.stacks
        # Bonus damage from target radiation (e.g. Uranium Isotope: +ceil(rad/20))
        rad_div = wdefn.get("bonus_dmg_from_target_rad") if wdefn else None
        if rad_div and hasattr(defender, 'radiation') and defender.radiation > 0:
            atk_power += math.ceil(defender.radiation / rad_div)
        # Liquid Courage (Drinking L4): +3% crit per active drink stack
        _lc_crit_bonus = 0
        if engine.skills.get("Drinking").level >= 4:
            from effects import _DRINK_BUFF_IDS
            for _eff in attacker.status_effects:
                if getattr(_eff, 'id', '') in _DRINK_BUFF_IDS:
                    _lc_crit_bonus += getattr(_eff, 'stack_count', 1) * 0.03
        if not is_crit and random.random() < engine.player_stats.crit_chance + _lc_crit_bonus:
            is_crit = True
        # Victory Rush: advantage on crit (roll twice)
        if not is_crit and any(getattr(e, 'id', '') == 'victory_rush' for e in attacker.status_effects):
            if random.random() < engine.player_stats.crit_chance + _lc_crit_bonus:
                is_crit = True
    else:
        atk_power = attacker.power

    if defender == engine.player:
        def_defense = _compute_player_defense(engine)
    else:
        def_defense = defender.defense

    # Check dodge before applying damage
    defender_dodge_chance = engine.player_stats.dodge_chance if defender == engine.player else defender.dodge_chance
    # Slashing L4: +15% dodge while wielding a slashing weapon
    if defender == engine.player and engine.skills.get("Slashing").level >= 4:
        w = engine.equipment.get("weapon")
        if w and weapon_matches_type(get_item_def(w.item_id) or {}, "slashing"):
            defender_dodge_chance += 15
    if random.random() * 100 < defender_dodge_chance:
        msg = f"{defender.name} dodges the attack!"
        engine.messages.append(msg)
        if engine.sdl_overlay:
            engine.sdl_overlay.add_floating_text(defender.x, defender.y, "DODGE", (200, 200, 255))
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
        # Chemical Warfare L2: Toxic Frenzy — +1% damage per 10 tox (cap 500)
        damage = _apply_toxic_frenzy(engine, damage)
        # Liquid Courage (Drinking L4): +10% melee damage while any drink buff active
        if engine.skills.get("Drinking").level >= 4:
            from effects import _DRINK_BUFF_IDS
            if any(getattr(e, 'id', '') in _DRINK_BUFF_IDS for e in attacker.status_effects):
                damage = int(damage * 1.10)
        # Purge Infection debuff: -50% melee damage
        if any(getattr(e, 'id', '') == 'purge_infection' for e in attacker.status_effects):
            damage = max(MIN_DAMAGE, damage // 2)
        # Purity + Zombie Rage: Purity caps melee damage to 1
        has_purity = any(getattr(e, 'id', '') == 'purity_stacks' for e in attacker.status_effects)
        has_zombie_rage = any(getattr(e, 'id', '') == 'zombie_rage' for e in attacker.status_effects)
        if has_purity and has_zombie_rage:
            damage = 1
    # Cryomancy L3 (Chill Out): chilled attackers deal 10% less melee damage per stack (cap 50%)
    if attacker != engine.player and defender == engine.player:
        if engine.skills.get("Cryomancy").level >= 3:
            chill_eff = next(
                (e for e in attacker.status_effects if getattr(e, 'id', '') == 'chill'),
                None,
            )
            if chill_eff:
                import math
                mult = max(0.5, 0.9 ** chill_eff.stacks)
                damage = max(MIN_DAMAGE, math.ceil(damage * mult))

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

    # Cap XP-eligible damage to defender's remaining HP (no overkill XP)
    xp_damage = min(damage, max(0, defender.hp))

    deal_damage(engine, damage, defender)

    # On-hit effects: notify player's active buffs/debuffs
    if attacker == engine.player:
        # Gunplay L1: melee resets consecutive shot tracker
        engine.gatting_consecutive_target_id = None
        engine.gatting_consecutive_count = 0
        engine._check_decontamination_proc(defender)
        engine._graffiti_proc_red(defender)
        for eff in list(engine.player.status_effects):
            eff.on_player_melee_hit(engine, defender, damage)

        # Momentum (Jaywalking L6): 40% on melee hit to gain a free move stack
        if engine.skills.get("Jaywalking").level >= 6 and random.random() < 0.40:
            effects.apply_effect(engine.player, engine, "momentum", stacks=1, silent=True)
            _mom = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'momentum'), None)
            _mom_stacks = _mom.stacks if _mom else 1
            engine.messages.append([
                ("Momentum! ", (100, 220, 255)),
                (f"+1 free move ({_mom_stacks} stored)", (180, 220, 255)),
            ])

        # Ramp damage: +2 per stack, resets after 10 hits
        if weapon and wdefn and "ramp_damage" in wdefn.get("tags", []):
            old_ramp = getattr(weapon, "ramp_bonus", 0)
            new_ramp = old_ramp + 2
            if new_ramp > 20:
                new_ramp = 0
                engine.messages.append([
                    ("Yinyang resets! ", (180, 180, 180)),
                    ("Ramp damage returns to +0.", (120, 120, 120)),
                ])
            else:
                engine.messages.append([
                    ("Yinyang ramps! ", (200, 200, 200)),
                    (f"+{new_ramp} bonus damage.", (255, 255, 255)),
                ])
            weapon.ramp_bonus = new_ramp

        # Massive Blunt: 10% on-hit chance to smoke a random joint from current floor
        if weapon and wdefn and "massive_blunt" in wdefn.get("tags", []):
            if random.random() < 0.10:
                _massive_blunt_smoke_proc(engine)

        # Double Edged Sword: deal 1-3 self-damage if player is above 50% HP
        if weapon and wdefn and "double_edged" in wdefn.get("tags", []):
            if engine.player.hp > engine.player.max_hp // 2:
                self_dmg = random.randint(1, 3)
                engine.player.hp -= self_dmg
                engine.messages.append([
                    ("Double edge! ", (200, 80, 80)),
                    (f"-{self_dmg} HP", (255, 100, 100)),
                    (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
                ])
                if engine.player.hp <= 0:
                    engine.player.alive = False
                    engine.event_bus.emit("entity_died", entity=engine.player, killer=None)

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

        # Slashing L1 "Swashbuckling": 20% on slash hit → +1 slash dmg, +1% dodge per stack
        if (engine.skills.get("Slashing").level >= 1
                and weapon and wdefn
                and weapon_matches_type(wdefn, "slashing")
                and random.random() < 0.20):
            effects.apply_effect(engine.player, engine, "swashbuckling")
            swash = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'swashbuckling'), None)
            stk = swash.stacks if swash else 1
            engine.messages.append([
                ("Swashbuckling! ", (255, 220, 100)),
                (f"+{stk} slash dmg, +{stk}% dodge ({stk} stacks, 20t)", (255, 240, 180)),
            ])

        # Beating L4 "Aftershock": crit with beating weapon → 3 empowered follow-up attacks
        if (is_crit
                and engine.skills.get("Beating").level >= 4
                and weapon and wdefn
                and weapon_matches_type(wdefn, "beating")):
            effects.apply_effect(engine.player, engine, "aftershock", duration=15, stacks=3, silent=True)
            engine.messages.append([
                ("Aftershock! ", (255, 160, 40)),
                ("Next 3 hits deal bonus damage and can stun. (15t)", (255, 200, 100)),
            ])

        # Slashing L5 "Crippling Strikes": 25% on slash hit → Hamstrung (-2 dmg/stack)
        if (engine.skills.get("Slashing").level >= 5
                and weapon and wdefn
                and weapon_matches_type(wdefn, "slashing")
                and defender.alive
                and random.random() < 0.50):
            effects.apply_effect(defender, engine, "hamstrung", stacks=1, silent=True)
            ham = next((e for e in defender.status_effects if getattr(e, 'id', '') == 'hamstrung'), None)
            stk = ham.stacks if ham else 1
            engine.messages.append([
                ("Hamstrung! ", (200, 120, 80)),
                (f"{defender.name} deals -{stk * 2} dmg (x{stk})", (220, 170, 130)),
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

                # Tetanus on-hit chance (e.g. Rusty Machete): -1 power/-1 defense per stack
                tetanus_chance = wdefn.get("on_hit_tetanus_chance", 0)
                if tetanus_chance and defender.alive and random.random() < tetanus_chance:
                    effects.apply_effect(defender, engine, "tetanus", duration=10, stacks=1, silent=True)
                    tet = next((e for e in defender.status_effects if getattr(e, 'id', '') == 'tetanus'), None)
                    stacks = tet.stacks if tet else 1
                    engine.messages.append(f"Tetanus! {defender.name} weakens. (-1 all stats, x{stacks})")

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

                # Weapon break chance (random per-hit)
                break_chance = wdefn.get("break_chance", 0)
                if break_chance and random.random() < break_chance:
                    engine.messages.append(f"Your {weapon.name} breaks!")
                    engine.equipment["weapon"] = None
                    granted = wdefn.get("grants_ability")
                    if granted:
                        engine.revoke_ability(granted)

                # Weapon durability break (fixed hit count, e.g. Crooked Baseball Bat)
                break_hits = wdefn.get("break_hits", 0) + getattr(weapon, "enchant_break_hits", 0)
                if break_hits > 0:
                    hits_used = getattr(weapon, '_break_hits_used', 0) + 1
                    weapon._break_hits_used = hits_used
                    remaining = break_hits - hits_used
                    if remaining == 1:
                        engine.messages.append([
                            ("Your ", (200, 200, 200)),
                            (weapon.name, weapon.color),
                            (" is about to break!", (255, 200, 80)),
                        ])
                    elif remaining <= 0:
                        # Final hit: deal bonus damage
                        mult = wdefn.get("break_final_mult", 1)
                        bonus = damage * (mult - 1)
                        if bonus > 0 and defender.alive:
                            defender.take_damage(bonus)
                            engine.messages.append([
                                ("CRACK! ", (255, 220, 80)),
                                (weapon.name, weapon.color),
                                (f" shatters for {damage + bonus} total damage!", (255, 160, 60)),
                            ])
                            if not defender.alive:
                                engine.event_bus.emit("entity_died", entity=defender, killer=engine.player)
                        else:
                            engine.messages.append([
                                ("Your ", (200, 200, 200)),
                                (weapon.name, weapon.color),
                                (" shatters!", (255, 160, 60)),
                            ])
                        engine.equipment["weapon"] = None
                        granted = wdefn.get("grants_ability")
                        if granted:
                            engine.revoke_ability(granted)

        # Melee skill XP: equal to damage dealt (capped to defender's remaining HP)
        _WEAPON_TYPE_SKILL = {"stabbing": "Stabbing", "beating": "Beating", "slashing": "Slashing"}
        if weapon and wdefn:
            melee_skill = _WEAPON_TYPE_SKILL.get(wdefn.get("weapon_type"))
            # Dual weapon type (e.g. Green Lightsaber): award XP to both skills
            alt_type = wdefn.get("weapon_type_alt")
            if alt_type:
                alt_skill = _WEAPON_TYPE_SKILL.get(alt_type)
                if alt_skill:
                    engine._gain_melee_xp(alt_skill, xp_damage)
        else:
            melee_skill = "Smacking"
        if melee_skill:
            engine._gain_melee_xp(melee_skill, xp_damage)

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

        # Beating L5 "Overkill": excess damage splashes to nearby enemies, chains on kill
        if (attacker == engine.player
                and engine.skills.get("Beating").level >= 5
                and weapon and wdefn
                and weapon_matches_type(wdefn, "beating")):
            excess = abs(defender.hp)
            if excess > 0:
                _overkill_splash(engine, defender.x, defender.y, excess)
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

    # Voodoo Ham Stun break: 20% chance on player hit
    if attacker == engine.player and defender.alive:
        voodoo_stun = next(
            (e for e in defender.status_effects if getattr(e, 'id', '') == 'voodoo_ham_stun'),
            None,
        )
        if voodoo_stun and random.random() < 0.20:
            defender.status_effects.remove(voodoo_stun)
            engine.messages.append(f"{defender.name} snaps out of the Voodoo Stun!")

    # Windfury: extra attack with stabbing weapon (Stabbing level 3+)
    if (attacker == engine.player and _windfury_eligible
            and defender.alive
            and engine.skills.get("Stabbing").level >= 3):
        weapon = engine.equipment.get("weapon")
        if weapon:
            wdefn = get_item_def(weapon.item_id)
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
            player._current_attacker = monster
            damage = _apply_damage_modifiers(engine, damage, player)
            player._current_attacker = None
            damage = _apply_toxicity(engine, damage, player)
            if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            if any(getattr(e, 'is_curse', False) and getattr(e, 'id', '') == 'curse_of_ham' for e in monster.status_effects):
                damage = max(MIN_DAMAGE, damage // 2)
            hamstrung = next((e for e in monster.status_effects if getattr(e, 'id', None) == 'hamstrung'), None)
            if hamstrung:
                damage = max(MIN_DAMAGE, damage - hamstrung.stacks * 2)
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
            # Immaculate (WP L6): melee hit while Bastion active → 3 Purity stacks
            _immaculate_on_melee_hit(engine)
            # Ironsoul Aura: visible enemy hit grants +10 rad
            _ironsoul_on_hit(engine, monster)
            # Retribution Aura: attacker takes true damage
            _retribution_on_hit(engine, monster)
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
    player._current_attacker = monster
    damage = _apply_damage_modifiers(engine, damage, player)
    player._current_attacker = None
    damage = _apply_toxicity(engine, damage, player)
    if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    if any(getattr(e, 'is_curse', False) and getattr(e, 'id', '') == 'curse_of_ham' for e in monster.status_effects):
        damage = max(MIN_DAMAGE, damage // 2)
    hamstrung = next((e for e in monster.status_effects if getattr(e, 'id', None) == 'hamstrung'), None)
    if hamstrung:
        damage = max(MIN_DAMAGE, damage - hamstrung.stacks * 2)
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

    # Colossus Fortress: 30% counter-attack for STR damage + 1-turn stun
    if monster.alive and any(getattr(e, 'id', '') == 'colossus_fortress' for e in player.status_effects):
        if random.random() < 0.30:
            counter_dmg = max(1, engine.player_stats.effective_strength)
            monster.take_damage(counter_dmg)
            if monster.alive:
                effects.apply_effect(monster, engine, "stun", duration=1, silent=True)
                engine.messages.append([
                    ("Counter! ", (100, 160, 255)),
                    (f"{monster.name} takes {counter_dmg} dmg — stunned!", (140, 200, 255)),
                ])
            else:
                engine.messages.append([
                    ("Counter! ", (100, 160, 255)),
                    (f"{monster.name} takes {counter_dmg} dmg and dies!", (140, 200, 255)),
                ])
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

    # Immaculate (WP L6): melee hit while Bastion active → 3 Purity stacks
    _immaculate_on_melee_hit(engine)
    # Ironsoul Aura: visible enemy hit grants +10 rad
    _ironsoul_on_hit(engine, monster)
    # Retribution Aura: attacker takes true damage
    _retribution_on_hit(engine, monster)

    if not player.alive:
        engine.event_bus.emit("entity_died", entity=player, killer=monster)


def _immaculate_on_melee_hit(engine):
    """Immaculate (WP L6): grant 3 Purity stacks when hit while Bastion is active."""
    if engine.skills.get("White Power").level < 6:
        return
    has_bastion = any(
        getattr(e, 'id', '') == 'bastion'
        for e in engine.player.status_effects
    )
    if not has_bastion:
        return
    existing = next(
        (e for e in engine.player.status_effects
         if getattr(e, 'id', '') == 'purity_stacks'),
        None,
    )
    if existing:
        existing.add_stacks(3, engine=engine)
    else:
        from effects import apply_effect
        apply_effect(engine.player, engine, "purity_stacks", stacks=3, duration=20)


def _ironsoul_on_hit(engine, monster):
    """Ironsoul Aura: hits from visible enemies grant +10 rad to player."""
    has_ironsoul = any(getattr(e, 'id', '') == 'ironsoul_aura'
                       for e in engine.player.status_effects)
    if not has_ironsoul:
        return
    if engine.dungeon.visible[monster.y][monster.x]:
        add_radiation(engine, engine.player, 10, pierce_resistance=True)


def _retribution_on_hit(engine, monster):
    """Retribution Aura: enemies that melee you take true damage, drain 5 rad."""
    has_retribution = any(getattr(e, 'id', '') == 'retribution_aura'
                          for e in engine.player.status_effects)
    if not has_retribution:
        return
    player = engine.player
    if player.radiation <= 0 or not monster.alive:
        return
    decon_level = engine.skills.get("Decontamination").level
    retrib_dmg = min(30, player.radiation // 20 + decon_level)
    if retrib_dmg <= 0:
        return
    monster.take_damage(retrib_dmg)
    remove_radiation(engine, player, 5)
    engine.messages.append([
        ("Retribution! ", (255, 220, 80)),
        (f"{monster.name} takes {retrib_dmg} true damage. (-5 rad)", (240, 200, 100)),
    ])
    if not monster.alive:
        engine.event_bus.emit("entity_died", entity=monster, killer=player)


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
    dodge = engine.player_stats.dodge_chance
    # Slashing L4: +15% dodge while wielding a slashing weapon
    if engine.skills.get("Slashing").level >= 4:
        w = engine.equipment.get("weapon")
        if w and weapon_matches_type(get_item_def(w.item_id) or {}, "slashing"):
            dodge += 15
    if random.random() * 100 < dodge:
        engine.messages.append(f"You dodge {monster.name}'s ranged attack!")
        if engine.sdl_overlay:
            engine.sdl_overlay.add_floating_text(engine.player.x, engine.player.y, "DODGE", (200, 200, 255))
        return

    # Roll damage
    dmg_min, dmg_max = ra["damage"]
    damage = random.randint(dmg_min, dmg_max)
    if not ra.get("pierces_defense"):
        def_defense = _compute_player_defense(engine)
        damage = max(MIN_DAMAGE, damage - def_defense)
        player._current_attacker = monster
        damage = _apply_damage_modifiers(engine, damage, player)
        player._current_attacker = None
        damage = _apply_toxicity(engine, damage, player)
        damage = _armor_up_check(engine, damage)
    hamstrung = next((e for e in monster.status_effects if getattr(e, 'id', None) == 'hamstrung'), None)
    if hamstrung:
        damage = max(MIN_DAMAGE, damage - hamstrung.stacks * 2)

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
