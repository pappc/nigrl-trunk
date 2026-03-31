"""
Item effect functions extracted from engine.py.

Each function takes `engine` as its first parameter (replacing `self`).
"""

import math
import random

import effects
from entity import Entity
from items import (
    is_stackable, build_inventory_display_name, get_strain_effect,
    ITEM_DEFS, get_random_ring_by_tags, get_random_chain, STRAINS,
)

# Colors for segmented log messages (mirror engine.py constants)
_C_MSG_NEUTRAL = (200, 200, 100)
_C_MSG_PICKUP  = (255, 200, 100)


def _pickup_items_at(engine, x: int, y: int):
    """Pick up all items and cash at (x, y). Used by abilities that teleport the player."""
    for entity in list(engine.dungeon.get_entities_at(x, y)):
        if entity == engine.player:
            continue
        if entity.entity_type == "item":
            engine.dungeon.remove_entity(entity)
            # Check if this item instance has been looted before (prevent drop/pickup abuse)
            is_first_pickup = entity.instance_id not in engine.picked_up_items
            if is_first_pickup:
                engine.picked_up_items.add(entity.instance_id)
                engine._gain_item_skill_xp("Stealing", entity.item_id)
                engine._sticky_fingers_check(entity.item_id)
                engine._gain_ammo_rat_xp(entity.item_id)
                # Ammo Rat L1 "Scrounger": 50% chance for +1 bonus round on ammo pickup
                item_defn = ITEM_DEFS.get(entity.item_id)
                if (item_defn and item_defn.get("category") == "ammo"
                        and engine.skills.get("Ammo Rat").level >= 1
                        and random.random() < 0.50):
                    entity.quantity += 1
                    engine.messages.append([
                        ("Scrounger! ", (220, 200, 120)),
                        ("+1 bonus round", (180, 255, 150)),
                    ])
                # Ammo Rat L3 "Rat Race": 20% chance for +10 speed (stacks, refreshes)
                if (item_defn and item_defn.get("category") == "ammo"
                        and engine.skills.get("Ammo Rat").level >= 3
                        and random.random() < 0.20):
                    import effects as _eff
                    applied = _eff.apply_effect(engine.player, engine, "rat_race", stacks=1, silent=True)
                    if applied:
                        engine.messages.append([
                            ("Rat Race! ", (220, 200, 120)),
                            ("+10 speed for 20 turns", (180, 255, 150)),
                        ])
            # Skip charged items from stacking — each is unique
            if is_stackable(entity.item_id) and getattr(entity, "charges", None) is None:
                existing = next(
                    (i for i in engine.player.inventory
                     if i.item_id == entity.item_id and i.strain == entity.strain
                     and getattr(i, "charges", None) is None),
                    None,
                )
                if existing:
                    existing.quantity += entity.quantity
                    display = build_inventory_display_name(
                        existing.item_id, existing.strain, existing.quantity
                    )
                    engine.messages.append([
                        ("Picked up ", _C_MSG_PICKUP),
                        (entity.name, entity.color),
                        (f" ({display})", _C_MSG_NEUTRAL),
                    ])
                    continue
            engine.player.inventory.append(entity)
            engine._sort_inventory()
            engine.messages.append([
                ("Picked up ", _C_MSG_PICKUP),
                (entity.name, entity.color),
            ])
        elif entity.entity_type == "cash":
            engine.dungeon.remove_entity(entity)
            engine.cash += entity.cash_amount
            engine.messages.append(f"Picked up ${entity.cash_amount}!")


def _apply_item_effect_to_entity(engine, effect_def, entity):
    """Apply an item throw_effect dict to any entity via the unified effects system."""
    effect_id = effect_def.get("effect_id") or effect_def.get("type", "stat_mod")
    duration = effect_def.get("duration", 10)
    amount = effect_def.get("amount", 0)
    stat = effect_def.get("stat")
    effects.apply_effect(entity, engine, effect_id,
                         duration=duration, amount=amount, stat=stat)


_contact_high_spreading = False  # recursion guard for Contact High spread


def _apply_strain_effect(engine, entity, strain, roll, target="player"):
    """Resolve a strain table roll and apply the resulting effect to entity."""
    global _contact_high_spreading
    eff = get_strain_effect(strain, roll, target)
    if eff is None:
        engine.messages.append("Nothing happens.")
        return

    is_player = entity == engine.player
    eff_type = eff.get("type")

    if eff_type == "heal_percent":
        amount = int(entity.max_hp * eff["amount"])
        entity.heal(amount)
        if is_player:
            engine.messages.append(
                f"You feel much better! Healed {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
            )
        else:
            engine.messages.append(
                f"{entity.name} recovers {amount} HP! ({entity.hp}/{entity.max_hp} HP)"
            )

    elif eff_type == "heal_flat":
        amount = eff["amount"]
        entity.heal(amount)
        if is_player:
            engine.messages.append(
                f"You feel better! Healed {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
            )
        else:
            engine.messages.append(
                f"{entity.name} recovers {amount} HP! ({entity.hp}/{entity.max_hp} HP)"
            )

    elif eff_type == "damage_percent":
        amount = max(1, int(entity.max_hp * eff["amount"]))
        entity.take_damage(amount)
        if is_player:
            engine.messages.append(
                f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            engine.messages.append(
                f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)

    elif eff_type == "invulnerable":
        duration = eff.get("duration", 10)
        effects.apply_effect(entity, engine, "invulnerable", duration=duration)
        if is_player:
            engine.messages.append(
                f"You feel untouchable! ({duration} turns)"
            )
        else:
            engine.messages.append(
                f"{entity.name} looks untouchable! ({duration} turns)"
            )

    elif eff_type == "cg_buff_debuff":
        duration = eff.get("duration", 10)
        effects.apply_effect(entity, engine, "columbian_gold", duration=duration, silent=True)
        if is_player:
            engine.messages.append([
                ("You smoke the rush — stronger but ", (220, 220, 220)),
                ("burning", (220, 100, 50)),
                (" inside! (", (220, 220, 220)),
                (str(duration), (220, 150, 50)),
                (" turns)", (220, 220, 220)),
            ])
        else:
            engine.messages.append(
                f"{entity.name} looks stronger but pained! ({duration} turns)"
            )

    elif eff_type == "damage_flat":
        amount = eff["amount"]
        entity.take_damage(amount)
        if is_player:
            engine.messages.append(
                f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            engine.messages.append(
                f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)

    elif eff_type == "damage_stsmt":
        base = eff["base"]
        minimum = eff.get("min", 10)
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
        else:
            stsmt = entity.base_stats.get("street_smarts", 1)
        amount = max(minimum, base - stsmt)
        entity.take_damage(amount)
        if is_player:
            engine.messages.append(
                f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            engine.messages.append(
                f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)

    elif eff_type == "remove_debuffs":
        removed = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') == 'debuff']
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') != 'debuff']
        for eff_obj in removed:
            eff_obj.expire(entity, engine)
        if is_player:
            if removed:
                engine.messages.append("The smoke clears your head — all debuffs removed!")
            else:
                engine.messages.append("The smoke clears your head.")

    elif eff_type == "remove_debuffs_zoned_out":
        removed = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') == 'debuff']
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') != 'debuff']
        for eff_obj in removed:
            eff_obj.expire(entity, engine)
        effects.apply_effect(entity, engine, "zoned_out", duration=10, silent=True)
        if is_player:
            engine.messages.append("You seem out of it! (10 turns)")
        else:
            engine.messages.append(f"{entity.name} seems out of it!")

    elif eff_type == "random_dot_debuff":
        duration_mode = eff.get("duration_mode")
        if duration_mode == "tlr":
            if is_player:
                tlr = engine.player_stats.effective_tolerance
            else:
                bs = getattr(entity, 'base_stats', {})
                tlr = bs.get("tolerance", 7) if isinstance(bs, dict) else 7
            duration = max(5, math.ceil(20 - tlr / 2))
        else:
            duration = eff.get("duration", 20)
        debuff_id = random.choice(["ignite", "chill", "shocked"])
        effects.apply_effect(entity, engine, debuff_id, duration=duration, silent=True)
        _DOT_NAMES = {"ignite": ("Ignite", (255, 120, 40)),
                      "chill":  ("Chill",  (100, 180, 255)),
                      "shocked":("Shocked",(255, 220, 50))}
        dname, dcolor = _DOT_NAMES[debuff_id]
        if is_player:
            engine.messages.append([
                ("The smoke hits wrong — ", (220, 220, 220)),
                (dname, dcolor),
                (f" for {duration} turns!", (220, 220, 220)),
            ])
        else:
            engine.messages.append(f"{entity.name} is afflicted with {dname}!")

    elif eff_type == "agent_orange_debuff":
        duration = eff.get("duration", 10)
        if is_player:
            if engine.player_stats.effective_tolerance >= 12:
                engine.messages.append("The Agent Orange rolls right off you. (Tolerance max)")
            else:
                effects.apply_effect(entity, engine, "agent_orange", duration=duration, silent=True)
                engine.messages.append([
                    ("Agent Orange kicks in — ", (220, 120, 50)),
                    ("melee disabled", (255, 80, 20)),
                    (f" for {duration} turns!", (220, 120, 50)),
                ])
        else:
            effects.apply_effect(entity, engine, "agent_orange", duration=duration, silent=True)
            engine.messages.append(f"{entity.name} is debilitated by Agent Orange!")

    # ── Jungle Boyz effects ──────────────────────────────────────────────
    elif eff_type == "jb_self_reflection":
        duration = eff.get("duration", 10)
        effects.apply_effect(entity, engine, "minor_self_reflection", duration=duration, silent=True)
        engine.messages.append([
            ("Jungle Boyz hits — ", (100, 200, 100)),
            ("Minor Self Reflection", (200, 100, 100)),
            (f" for {duration} turns!", (100, 200, 100)),
        ])

    elif eff_type == "jb_fiery_fists":
        duration = eff.get("duration", 10)
        effects.apply_effect(entity, engine, "fiery_fists", duration=duration, silent=True)
        engine.messages.append([
            ("Jungle Boyz burns — ", (100, 200, 100)),
            ("Fiery Fists", (255, 120, 40)),
            (f" for {duration} turns!", (100, 200, 100)),
        ])

    elif eff_type == "jb_monster_ignite":
        # 5 stacks of Ignite applied to monster
        ignite_eff = effects.apply_effect(entity, engine, "ignite", duration=5, stacks=5, silent=True)
        stacks = ignite_eff.stacks if ignite_eff else 5
        engine.messages.append(f"{entity.name} erupts in flames! (Ignite x{stacks})")

    elif eff_type == "jb_crippling_attacks":
        duration = eff.get("duration", 10)
        effects.apply_effect(entity, engine, "crippling_attacks", duration=duration, silent=True)
        engine.messages.append([
            ("Jungle Boyz crips — ", (100, 200, 100)),
            ("Crippling Attacks", (200, 220, 80)),
            (f" for {duration} turns!", (100, 200, 100)),
        ])

    elif eff_type == "jb_crippled":
        duration = eff.get("duration", 8)
        effects.apply_effect(entity, engine, "crippled", duration=duration, silent=True)
        engine.messages.append(f"{entity.name} is crippled! (deals half damage for {duration} turns)")

    elif eff_type == "jb_lifesteal":
        duration = eff.get("duration", 8)
        effects.apply_effect(entity, engine, "lifesteal", duration=duration, silent=True)
        engine.messages.append([
            ("Jungle Boyz flows — ", (100, 200, 100)),
            ("Lifesteal", (200, 80, 80)),
            (f" for {duration} turns!", (100, 200, 100)),
        ])

    elif eff_type == "jb_heal_damage":
        # Monster takes 20 damage, player heals 20
        entity.take_damage(20)
        engine.player.heal(20)
        engine.messages.append(
            f"{entity.name} takes 20 damage! You heal 20 HP. "
            f"({engine.player.hp}/{engine.player.max_hp} HP)"
        )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)

    elif eff_type == "jb_glory_fists":
        duration = eff.get("duration", 20)
        effects.apply_effect(entity, engine, "glory_fists", duration=duration, silent=True)
        engine.messages.append([
            ("Jungle Boyz blesses — ", (100, 200, 100)),
            ("Glory Fists", (220, 180, 255)),
            (f" for {duration} turns!", (100, 200, 100)),
        ])

    elif eff_type == "jb_soul_pair":
        effects.apply_effect(entity, engine, "soul_pair", duration=9999, silent=True)
        engine.messages.append([
            ("The smoke links your souls — ", (100, 200, 100)),
            ("Soul-Pair", (180, 100, 220)),
            (f" applied to {entity.name}!", (100, 200, 100)),
        ])

    elif eff_type == "blue_lobster":
        _apply_blue_lobster_effect(engine, entity, roll, is_player)

    elif eff_type == "none":
        if is_player:
            engine.messages.append("You feel nothing.")
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    # ── Spell effects — grant ability charges for later use ──────────────
    elif eff_type == "dosidos_dimension_door":
        if is_player:
            charges = random.randint(eff.get("min_count", 1), eff.get("max_count", 1))
            engine.grant_ability_charges("dimension_door", charges)
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    elif eff_type == "dosidos_chain_lightning":
        if is_player:
            charges = random.randint(eff.get("min_count", 2), eff.get("max_count", 2))
            engine.grant_ability_charges("chain_lightning", charges)
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    elif eff_type == "dosidos_ray_of_frost":
        if is_player:
            charges = random.randint(eff.get("min_count", 3), eff.get("max_count", 3))
            engine.grant_ability_charges("ray_of_frost", charges)
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    elif eff_type == "dosidos_warp":
        if is_player:
            charges = random.randint(eff.get("min_count", 1), eff.get("max_count", 1))
            engine.grant_ability_charges("warp", charges)
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    elif eff_type == "dosidos_firebolt":
        if is_player:
            engine.grant_ability_charges("firebolt", eff.get("count", 1))
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    elif eff_type == "dosidos_arcane_missile":
        if is_player:
            engine.grant_ability_charges("arcane_missile", eff.get("count", 1))
        else:
            engine.messages.append(f"{entity.name} flickers briefly.")

    # ── Iron Lung (CON-based tox removal tank strain) ───────────────────
    elif eff_type == "iron_lung_full":
        # Remove ALL tox; heal = tox_removed + CON*2 (floor 20); excess → armor
        # Gain defense = tox_removed/20 (floor 1) for 50 turns
        tox = getattr(entity, "toxicity", 0)
        entity.toxicity = 0
        con = engine.player_stats.effective_constitution if is_player else 10
        heal_amount = max(20, tox + con * 2)
        hp_before = entity.hp
        entity.heal(heal_amount)
        healed = entity.hp - hp_before
        excess = heal_amount - healed
        if excess > 0:
            entity.armor += excess
        def_bonus = max(1, tox // 20)
        effects.apply_effect(entity, engine, "iron_lung_defense", duration=50, defense_amount=def_bonus, silent=True)
        if is_player:
            parts = [f"Iron Lung purges all toxicity! Healed {healed} HP"]
            if excess > 0:
                parts.append(f", +{excess} armor")
            parts.append(f", +{def_bonus} DEF (50t)")
            if tox > 0:
                parts.append(f" [{tox} tox removed]")
            engine.messages.append("".join(parts))
        else:
            engine.messages.append(f"{entity.name} purges toxicity and toughens up!")

    elif eff_type == "iron_lung_half":
        # Remove up to 50 tox; heal = removed*2 + CON*2, excess → armor
        # If 25+ tox removed: +2 DEF for 50 turns
        tox = getattr(entity, "toxicity", 0)
        removed = min(50, tox)
        entity.toxicity = tox - removed
        con = engine.player_stats.effective_constitution if is_player else 10
        heal_amount = removed * 2 + con * 2
        hp_before = entity.hp
        entity.heal(heal_amount)
        healed = entity.hp - hp_before
        excess = heal_amount - healed
        if excess > 0:
            entity.armor += excess
        if is_player:
            parts = [f"Iron Lung cleanses! Healed {healed} HP"]
            if excess > 0:
                parts.append(f", +{excess} armor")
        if removed >= 25:
            effects.apply_effect(entity, engine, "iron_lung_defense", duration=50, defense_amount=2, silent=True)
            if is_player:
                parts.append(", +2 DEF (50t)")
        if is_player:
            if removed > 0:
                parts.append(f" [{removed} tox removed]")
            engine.messages.append("".join(parts))
        else:
            engine.messages.append(f"{entity.name} cleanses toxicity and heals!")

    elif eff_type == "iron_lung_half_weak":
        # Same as iron_lung_half but also -25% melee damage dealt for 50 turns
        tox = getattr(entity, "toxicity", 0)
        removed = min(50, tox)
        entity.toxicity = tox - removed
        con = engine.player_stats.effective_constitution if is_player else 10
        heal_amount = removed * 2 + con * 2
        hp_before = entity.hp
        entity.heal(heal_amount)
        healed = entity.hp - hp_before
        excess = heal_amount - healed
        if excess > 0:
            entity.armor += excess
        if is_player:
            parts = [f"Iron Lung cleanses! Healed {healed} HP"]
            if excess > 0:
                parts.append(f", +{excess} armor")
        if removed >= 25:
            effects.apply_effect(entity, engine, "iron_lung_defense", duration=50, defense_amount=2, silent=True)
            if is_player:
                parts.append(", +2 DEF (50t)")
        effects.apply_effect(entity, engine, "iron_lung_dmg_reduction", duration=50, silent=True)
        if is_player:
            if removed > 0:
                parts.append(f" [{removed} tox removed]")
            parts.append(" (-25% dmg dealt 50t)")
            engine.messages.append("".join(parts))
        else:
            engine.messages.append(f"{entity.name} cleanses toxicity but feels sluggish!")

    elif eff_type == "iron_lung_minor":
        # Gain 50 tox, heal 50 HP
        from combat import add_toxicity
        add_toxicity(engine, entity, 50)
        entity.heal(50)
        if is_player:
            engine.messages.append(f"Iron Lung: +50 toxicity, healed 50 HP. ({entity.hp}/{entity.max_hp} HP)")
        else:
            engine.messages.append(f"{entity.name} gains toxicity but heals!")

    elif eff_type == "iron_lung_bad":
        # Gain 100 tox
        from combat import add_toxicity
        add_toxicity(engine, entity, 100)
        if is_player:
            engine.messages.append("Iron Lung hits wrong. +100 toxicity!")
        else:
            engine.messages.append(f"{entity.name} chokes on the smoke! (+100 toxicity)")

    # ── Skywalker OG (STR-based rad synergy strain) ─────────────────────
    elif eff_type == "skywalker_lightsaber":
        # Roll 100: Green Lightsaber + Force Sensitive III
        if is_player:
            from items import create_item_entity
            saber = create_item_entity("green_lightsaber", 0, 0)
            entity.inventory.append(saber)
            engine.messages.append([
                ("A ", (255, 255, 255)),
                ("Green Lightsaber", (50, 255, 50)),
                (" materializes in your hands!", (255, 255, 255)),
            ])
            str_val = engine.player_stats.effective_strength
            duration = 50 + str_val * 5
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, tier=3, silent=True)
            from combat import add_radiation
            add_radiation(engine, entity, 40)
            engine.messages.append(f"Force Sensitive III! ({duration} turns, +1 STR per 10 rad gained, +40 rad)")
        else:
            engine.messages.append(f"{entity.name} glows with an eerie green light!")

    elif eff_type == "skywalker_iii":
        # Force Sensitive III: 50 + STR*5 turns, +30 starting rad
        if is_player:
            str_val = engine.player_stats.effective_strength
            duration = 50 + str_val * 5
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, tier=3, silent=True)
            from combat import add_radiation
            add_radiation(engine, entity, 30)
            engine.messages.append(f"Force Sensitive III! ({duration} turns, +1 STR per 10 rad gained, +30 rad)")
        else:
            engine.messages.append(f"{entity.name} surges with power!")

    elif eff_type == "skywalker_ii":
        # Force Sensitive II: 40 + STR*4 turns, +20 starting rad
        if is_player:
            str_val = engine.player_stats.effective_strength
            duration = 40 + str_val * 4
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, tier=2, silent=True)
            from combat import add_radiation
            add_radiation(engine, entity, 20)
            engine.messages.append(f"Force Sensitive II! ({duration} turns, +1 STR per 10 rad gained, +20 rad)")
        else:
            engine.messages.append(f"{entity.name} surges with power!")

    elif eff_type == "skywalker_i":
        # Force Sensitive I: 30 + STR*3 turns, no starting rad
        if is_player:
            str_val = engine.player_stats.effective_strength
            duration = 30 + str_val * 3
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, tier=1, silent=True)
            engine.messages.append(f"Force Sensitive I! ({duration} turns, +1 STR per 10 rad gained)")
        else:
            engine.messages.append(f"{entity.name} surges with power!")

    elif eff_type == "skywalker_rad_gain":
        # Gain 40 rad, no buff
        from combat import add_radiation
        add_radiation(engine, entity, 40)
        if is_player:
            engine.messages.append("Skywalker OG irradiates you. +40 rad.")
        else:
            engine.messages.append(f"{entity.name} gets irradiated!")

    elif eff_type == "skywalker_rad_loss":
        # Lose 30 rad
        old_rad = getattr(entity, "radiation", 0)
        entity.radiation = max(0, old_rad - 30)
        lost = old_rad - entity.radiation
        if is_player:
            engine.messages.append(f"Skywalker OG fizzles. Lost {lost} rad.")
        else:
            engine.messages.append(f"{entity.name} loses some radiation.")

    # ── Street Scholar (STSMT-based gun strain) ─────────────────────────
    elif eff_type == "calculated_aim_iii":
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 30 + stsmt * 3
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, tier=3, bksmt_chance=0.15, silent=True)
            engine.messages.append(
                f"Calculated Aim III! ({duration}t, 15% BKSMT/kill, 100% accuracy, auto-reload, +1x crit mult)"
            )
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "calculated_aim_ii":
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 30 + stsmt * 3
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, tier=2, bksmt_chance=0.10, silent=True)
            engine.messages.append(
                f"Calculated Aim II! ({duration}t, 10% BKSMT/kill, auto-reload, +1x crit mult)"
            )
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "calculated_aim_i":
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 30 + stsmt * 3
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, tier=1, bksmt_chance=0.05, silent=True)
            engine.messages.append(
                f"Calculated Aim I! ({duration}t, 5% BKSMT/kill, +1x crit mult)"
            )
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "street_scholar_jam":
        # Jam all equipped guns
        if is_player:
            engine.gun_jammed = True
            engine.messages.append("Your guns jam up from the smoke!")
        else:
            engine.messages.append(f"{entity.name} coughs violently!")

    elif eff_type == "street_scholar_misfire":
        # Dump all ammo from equipped guns
        if is_player:
            dumped = False
            for slot in ["weapon", "sidearm"]:
                gun = engine.equipment.get(slot)
                if gun and hasattr(gun, 'current_ammo') and gun.current_ammo > 0:
                    engine.messages.append(
                        f"Misfire! {gun.name} dumps {gun.current_ammo} rounds!"
                    )
                    gun.current_ammo = 0
                    dumped = True
            if not dumped:
                engine.messages.append("Misfire! ...but no guns were loaded.")
        else:
            engine.messages.append(f"{entity.name} fumbles around!")

    # ── Kushenheimer strain ──────────────────────────────────────────────────
    elif eff_type in ("rad_nova_1", "rad_nova_2", "rad_nova_3", "rad_nova_4", "rad_nova_5"):
        import random as _rn
        from combat import add_radiation
        tier = int(eff_type[-1])  # 1-5
        # Each tier gains random radiation — lower tiers gain more
        rad_ranges = {1: (30, 40), 2: (25, 35), 3: (20, 30), 4: (15, 25), 5: (10, 20)}
        rad_lo, rad_hi = rad_ranges[tier]
        rad_gain = _rn.randint(rad_lo, rad_hi)
        add_radiation(engine, entity, rad_gain)
        if is_player:
            if tier >= 2:
                # Tiers 2-5: flat temporary spell damage, duration scales with BKS
                bksmt = engine.player_stats.effective_book_smarts
                spell_dmg = {2: 5, 3: 7, 4: 10, 5: 12}[tier]
                duration = 20 + bksmt * 2
                effects.apply_effect(entity, engine, "rad_nova_spell_buff",
                                     duration=duration, amount=spell_dmg, silent=True)
                engine.messages.append(
                    f"Kushenheimer tier {tier}! +{rad_gain} rad, +{spell_dmg} spell dmg ({duration}t)"
                )
            else:
                engine.messages.append(f"Kushenheimer tier 1! +{rad_gain} rad.")
            # Tiers 3-5: grant Radiation Nova charges
            if tier >= 3:
                bksmt = engine.player_stats.effective_book_smarts
                base_charges = {3: 2, 4: 3, 5: 3}[tier]
                bonus = bksmt // 5 if tier == 5 else 0
                charges = base_charges + bonus
                engine.grant_ability_charges("radiation_nova", charges)
            if tier == 5:
                # +1 permanent Book Smarts
                engine.player_stats.modify_base_stat("book_smarts", 1)
                engine.messages.append([
                    ("Kushenheimer: +1 permanent Book Smarts!", (160, 220, 100)),
                ])
        else:
            engine.messages.append(f"{entity.name} glows with nuclear energy!")

    # ── Nigle Fart strain (TOL-based toxicity spillover) ────────────────
    elif eff_type in ("nigle_fart_1", "nigle_fart_2", "nigle_fart_3", "nigle_fart_4", "nigle_fart_5"):
        from combat import add_toxicity
        tier = int(eff_type[-1])  # 1-5
        tox_amounts = {1: 100, 2: 70, 3: 50, 4: 40, 5: 30}
        tox_gain = tox_amounts[tier]
        add_toxicity(engine, entity, tox_gain)
        if is_player:
            # All tiers grant Pandemic charges
            charges = {1: 1, 2: 2, 3: 3, 4: 3, 5: 4}[tier]
            engine.grant_ability_charges("pandemic", charges)
            # Tiers 3-5: grant spillover aura
            if tier >= 3:
                tol = engine.player_stats.effective_tolerance
                spillover_pct = {3: 50, 4: 75, 5: 100}[tier]
                duration = 20 + tol * 2
                effects.apply_effect(entity, engine, "tox_spillover_aura",
                                     duration=duration, spillover_pct=spillover_pct, silent=True)
                engine.messages.append(
                    f"Nigle Fart tier {tier}! +{tox_gain} tox, {spillover_pct}% spillover aura ({duration}t), +{charges} Pandemic"
                )
            else:
                engine.messages.append(
                    f"Nigle Fart tier {tier}! +{tox_gain} tox, +{charges} Pandemic"
                )
        else:
            engine.messages.append(f"{entity.name} releases a toxic cloud!")

    # ── Purple Halt strain (SWG-based mutation control) ──────────────────
    elif eff_type in ("purple_halt_glory", "purple_halt_strong",
                       "purple_halt_weak", "purple_halt_bad"):
        if is_player:
            if eff_type == "purple_halt_glory":
                # Force a mutation at a random eligible tier, NO rad cost
                _purple_halt_force_mutation(engine, spend_rad=False)
            elif eff_type == "purple_halt_strong":
                # Force a mutation at a random eligible tier, rad consumed
                _purple_halt_force_mutation(engine, spend_rad=True)
            elif eff_type == "purple_halt_weak":
                # -15 rad (whiff)
                old_rad = entity.radiation
                entity.radiation = max(0, old_rad - 15)
                lost = old_rad - entity.radiation
                engine.messages.append(f"Purple Halt fizzles. -{lost} rad.")
            elif eff_type == "purple_halt_bad":
                # -40 rad (worst — drains mutation buildup), +1 temp SWG consolation
                old_rad = entity.radiation
                entity.radiation = max(0, old_rad - 40)
                lost = old_rad - entity.radiation
                effects.apply_effect(entity, engine, "purple_halt_swagger",
                                     duration=15, amount=1, silent=True)
                engine.messages.append(
                    f"Purple Halt drains your radiation. -{lost} rad. +1 SWG (15t)."
                )
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    # ── Snickelfritz strain (very negative, TBD) ─────────────────────────
    elif eff_type == "snickelfritz":
        if is_player:
            engine.messages.append([
                ("You smoke the Snickelfritz. ", (150, 120, 60)),
                ("It tastes like regret.", (200, 200, 200)),
            ])
            # TBD: very negative effects go here

    # ── Dosidos monster buff ─────────────────────────────────────────────
    elif eff_type == "dosidos_bksmt_buff":
        amount = eff.get("amount", 5)
        effects.apply_effect(entity, engine, "bksmt_buff", amount=amount, duration=9999, silent=True)
        engine.messages.append(
            f"{entity.name} gains +{amount} Book-Smarts from the Dosidos smoke!"
        )

    # ── Contact High (Smoking L5): spread strain effect to enemies within 3 tiles ──
    if not is_player and not _contact_high_spreading and engine.skills.get("Smoking").level >= 5:
        _contact_high_spreading = True
        spread_count = 0
        for mon in engine.dungeon.get_monsters():
            if mon is entity or not mon.alive:
                continue
            dx = abs(mon.x - entity.x)
            dy = abs(mon.y - entity.y)
            if max(dx, dy) <= 3:
                _apply_strain_effect(engine, mon, strain, roll, "monster")
                spread_count += 1
        _contact_high_spreading = False
        if spread_count > 0:
            engine.messages.append([
                ("Contact High! ", (200, 150, 255)),
                (f"Effect spreads to {spread_count} nearby enemies!",
                 (200, 200, 200)),
            ])


def _purple_halt_force_mutation(engine, spend_rad: bool) -> None:
    """Force an immediate mutation at a random eligible tier.

    Picks uniformly from all tiers the player qualifies for based on
    current radiation. If rad < 50, defaults to weak.
    If spend_rad is False, radiation is NOT deducted.
    """
    from mutations import (
        RAD_THRESHOLDS, RAD_COSTS, BAD_CHANCE, MUTATION_TABLES,
        _COLOR_GOOD, _COLOR_BAD,
    )
    rad = engine.player.radiation

    # Collect eligible tiers
    eligible = []
    if rad >= RAD_THRESHOLDS["huge"]:
        eligible.append("huge")
    if rad >= RAD_THRESHOLDS["strong"]:
        eligible.append("strong")
    if rad >= RAD_THRESHOLDS["weak"]:
        eligible.append("weak")
    if not eligible:
        eligible.append("weak")  # sub-50 rad: still force weak

    tier = random.choice(eligible)

    # Deduct rad if applicable
    if spend_rad:
        cost = RAD_COSTS[tier]
        engine.player.radiation = max(0, rad - cost)

    # Pick polarity and mutation
    polarity = "bad" if random.random() < BAD_CHANCE else "good"
    table = MUTATION_TABLES[(tier, polarity)]
    desc, apply_fn = random.choice(table)

    # Refresh Force Sensitive buff if present
    for eff in engine.player.status_effects:
        if getattr(eff, 'id', '') == 'force_sensitive':
            eff.refresh(engine.player, engine)
            break

    # Apply mutation
    suffix = apply_fn(engine) or ""

    # Award Mutation XP
    _MUTATION_XP = {"weak": 100, "strong": 250, "huge": 500}
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Mutation", _MUTATION_XP[tier], bksmt)

    # Build messages
    color = _COLOR_GOOD if polarity == "good" else _COLOR_BAD
    if spend_rad:
        cost_spent = rad - engine.player.radiation
        engine.messages.append(
            f"Purple Halt forces a mutation! (-{cost_spent} rad)"
        )
    else:
        engine.messages.append("PURPLE HALT — free mutation! Radiation unchanged.")
    engine.messages.append([(f"You mutate! [{tier.capitalize()}] {desc}{suffix}", color)])
    engine.mutation_log.append({
        "tier": tier, "polarity": polarity,
        "description": desc, "suffix": suffix,
    })


def _apply_blue_lobster_effect(engine, entity, roll, is_player):
    """Apply Blue Lobster strain effect based on roll (1-100).

    Player effects: gain items, lose items
    Monster effects: drop cash, gain Acid Armor
    """
    if is_player:
        # Player effects
        if 90 <= roll <= 100:
            # Add random tool
            current_zone = engine._get_zone_info()[0]
            candidates = [iid for iid, defn in ITEM_DEFS.items()
                         if defn.get("category") == "tool" and current_zone in defn.get("zones", [])]
            if candidates:
                tool_id = random.choice(candidates)
                engine._add_item_to_inventory(tool_id, strain=None)
                engine.messages.append(f"Blue Lobster grants: {ITEM_DEFS[tool_id]['name']}!")
            else:
                engine.messages.append("The Blue Lobster would grant a tool, but found none!")

        elif 83 <= roll <= 89:
            # Add 1-3 random joints
            num_joints = random.randint(1, 3)
            strain = random.choice(STRAINS)
            for _ in range(num_joints):
                engine._add_item_to_inventory("joint", strain=strain)
            engine.messages.append(f"Blue Lobster grants {num_joints} {strain} joint{'s' if num_joints > 1 else ''}!")

        elif 60 <= roll <= 82:
            # Add random ring (80% minor, 10% greater, 5% divine, 5% advanced)
            roll_ring = random.randint(1, 100)
            if roll_ring <= 80:
                tags = ["minor"]
            elif roll_ring <= 90:
                tags = ["greater"]
            elif roll_ring <= 95:
                tags = ["divine"]
            else:
                tags = ["advanced"]
            ring_id = get_random_ring_by_tags(tags)
            if ring_id:
                engine._add_item_to_inventory(ring_id, strain=None)
                engine.messages.append(f"Blue Lobster grants: {ITEM_DEFS[ring_id]['name']}!")
            else:
                engine.messages.append("The Blue Lobster would grant a ring, but found none!")

        elif 45 <= roll <= 59:
            # Add random neck (chain) directly
            neck_id = get_random_chain(engine._get_zone_info()[0])
            if neck_id:
                engine._add_item_to_inventory(neck_id, strain=None)
                engine.messages.append(f"Blue Lobster grants: {ITEM_DEFS[neck_id]['name']}!")
            else:
                engine.messages.append("The Blue Lobster would grant a neck, but found none!")

        elif 20 <= roll <= 44:
            # Add random weapon directly
            candidates = [
                iid for iid, defn in ITEM_DEFS.items()
                if defn.get("subcategory") == "weapon"
                and engine._get_zone_info()[0] in defn.get("zones", [])
            ]
            if candidates:
                weapon_id = random.choice(candidates)
                engine._add_item_to_inventory(weapon_id, strain=None)
                engine.messages.append(f"Blue Lobster grants: {ITEM_DEFS[weapon_id]['name']}!")
            else:
                engine.messages.append("The Blue Lobster would grant a weapon, but found none!")

        elif 5 <= roll <= 19:
            # Delete random item from inventory
            if engine.player.inventory:
                idx = random.randint(0, len(engine.player.inventory) - 1)
                deleted = engine.player.inventory.pop(idx)
                engine.messages.append(f"Blue Lobster curse: {deleted.name} deleted!")
            else:
                engine.messages.append("The Blue Lobster would curse an item, but you have none!")

        elif 1 <= roll <= 4:
            # Delete random equipped item
            equipped_items = []
            if engine.equipment.get("weapon"):
                equipped_items.append(("weapon", engine.equipment["weapon"]))
            if engine.equipment.get("neck"):
                equipped_items.append(("neck", engine.equipment["neck"]))
            for i, ring in enumerate(engine.rings):
                if ring:
                    equipped_items.append((f"ring_{i}", ring))
            if engine.equipment.get("feet"):
                equipped_items.append(("feet", engine.equipment["feet"]))

            if equipped_items:
                slot, item = random.choice(equipped_items)
                # Unequip the item
                if slot == "weapon":
                    engine.equipment["weapon"] = None
                elif slot == "neck":
                    engine.equipment["neck"] = None
                elif slot == "feet":
                    engine.equipment["feet"] = None
                elif slot.startswith("ring_"):
                    idx = int(slot.split("_")[1])
                    engine.rings[idx] = None
                engine.messages.append(f"Blue Lobster curse: {item.name} unequipped!")
            else:
                engine.messages.append("The Blue Lobster would curse equipped items, but you have none!")

    else:
        # Monster effects
        if 90 <= roll <= 100:
            # Drop 100-50 cash
            cash = random.randint(50, 100)
            cash_entity = Entity(
                x=entity.x, y=entity.y,
                char="$", color=(255, 215, 0),
                name=f"${cash}",
                entity_type="cash",
                blocks_movement=False,
                cash_amount=cash,
            )
            engine.dungeon.add_entity(cash_entity)
            engine.messages.append(f"Blue Lobster grants ${cash}!")

        elif 83 <= roll <= 89:
            # Drop 75-50 cash
            cash = random.randint(50, 75)
            cash_entity = Entity(
                x=entity.x, y=entity.y,
                char="$", color=(255, 215, 0),
                name=f"${cash}",
                entity_type="cash",
                blocks_movement=False,
                cash_amount=cash,
            )
            engine.dungeon.add_entity(cash_entity)
            engine.messages.append(f"Blue Lobster grants ${cash}!")

        elif 60 <= roll <= 82:
            # Drop 60-30 cash
            cash = random.randint(30, 60)
            cash_entity = Entity(
                x=entity.x, y=entity.y,
                char="$", color=(255, 215, 0),
                name=f"${cash}",
                entity_type="cash",
                blocks_movement=False,
                cash_amount=cash,
            )
            engine.dungeon.add_entity(cash_entity)
            engine.messages.append(f"Blue Lobster grants ${cash}!")

        elif 45 <= roll <= 59:
            # Nothing
            engine.messages.append(f"{entity.name} seems unaffected by the Blue Lobster.")

        elif 20 <= roll <= 44:
            # Nothing
            engine.messages.append(f"{entity.name} seems unaffected by the Blue Lobster.")

        elif 5 <= roll <= 19:
            # Gain Acid Armor (5% break chance, 10 turns)
            effects.apply_effect(entity, engine, "acid_armor", duration=10, break_chance=0.05, silent=True)
            engine.messages.append(f"{entity.name} gains Acid Armor!")

        elif 1 <= roll <= 4:
            # Gain Acid Armor (10% break chance, 20 turns)
            effects.apply_effect(entity, engine, "acid_armor", duration=20, break_chance=0.10, silent=True)
            engine.messages.append(f"{entity.name} gains Acid Armor!")


# ---------------------------------------------------------------------------
# Voodoo Doll curse detonation
# ---------------------------------------------------------------------------

_CURSE_IDS = frozenset({"curse_dot", "curse_covid", "curse_of_ham"})


def _voodoo_detonate(engine):
    """Detonate all curses on enemies within 8 tiles of the player."""
    player = engine.player
    targets = []  # [(monster, [curse_effects])]

    for m in engine.dungeon.get_monsters():
        if not m.alive:
            continue
        dist = max(abs(m.x - player.x), abs(m.y - player.y))
        if dist > 8:
            continue
        curses = [e for e in m.status_effects if getattr(e, 'id', '') in _CURSE_IDS]
        if curses:
            targets.append((m, curses))

    if not targets:
        engine.messages.append("The Voodoo Doll pulses... but finds no cursed enemies nearby.")
        return

    engine.messages.append([
        ("The Voodoo Doll pulses with dark energy!", (140, 60, 180)),
    ])

    detonation_count = 0
    for monster, curses in targets:
        for curse in curses:
            curse_id = curse.id
            stacks = getattr(curse, 'stacks', 0)
            # Remove curse (call expire for cleanup)
            monster.status_effects = [e for e in monster.status_effects if e is not curse]
            curse.expire(monster, engine)

            if curse_id == "curse_of_ham":
                _detonate_ham(engine, monster, stacks)
            elif curse_id == "curse_dot":
                _detonate_dot(engine, monster, stacks)
            elif curse_id == "curse_covid":
                _detonate_covid(engine, monster, stacks)
            detonation_count += 1

    if detonation_count > 0:
        bonus_xp = round(50 * detonation_count * engine.player_stats.xp_multiplier)
        engine.skills.gain_potential_exp(
            "Blackkk Magic", bonus_xp,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness,
        )
        engine.messages.append([
            (f"Detonated {detonation_count} curse(s)! ", (180, 80, 220)),
            (f"+{bonus_xp} Blackkk Magic XP", (200, 160, 255)),
        ])


def _detonate_ham(engine, monster, stacks):
    """Curse of Ham detonation: apply breakable stun with duration = stacks."""
    duration = max(1, stacks)
    effects.apply_effect(monster, engine, "voodoo_ham_stun",
                         duration=duration, silent=True)
    engine.messages.append([
        (f"{monster.name}: ", (200, 200, 200)),
        ("Curse of Ham detonates! ", (140, 60, 180)),
        (f"Stunned for {duration} turns!", (255, 200, 100)),
    ])
    if engine.sdl_overlay:
        engine.sdl_overlay.add_tile_flash_ripple(
            [(monster.x, monster.y)], monster.x, monster.y,
            color=(140, 60, 180), duration=0.8,
        )


def _detonate_dot(engine, monster, stacks):
    """Curse of DOT detonation: 2*stacks damage in a 5x5 area centered on monster."""
    damage = max(1, 2 * stacks)
    cx, cy = monster.x, monster.y

    # 5x5 AOE (2-tile Chebyshev radius)
    aoe_tiles = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            ax, ay = cx + dx, cy + dy
            if max(abs(dx), abs(dy)) <= 2 and not engine.dungeon.is_terrain_blocked(ax, ay):
                aoe_tiles.append((ax, ay))

    if engine.sdl_overlay:
        engine.sdl_overlay.add_tile_flash_ripple(
            aoe_tiles, cx, cy,
            color=(180, 40, 180), duration=1.0, ripple_speed=0.04,
        )

    hit_targets = set()
    for ax, ay in aoe_tiles:
        for entity in engine.dungeon.get_entities_at(ax, ay):
            if entity.entity_type == "monster" and entity.alive and entity not in hit_targets:
                entity.take_damage(damage)
                hit_targets.add(entity)

    engine.messages.append([
        (f"Curse of DOT detonates on {monster.name}! ", (140, 60, 180)),
        (f"{damage} damage to {len(hit_targets)} target(s)!", (255, 100, 100)),
    ])

    for entity in hit_targets:
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)


def _detonate_covid(engine, monster, stacks):
    """Curse of COVID detonation: double tox+rad, force mutations until rad depleted."""
    import mutations as _mut

    old_tox = getattr(monster, 'toxicity', 0)
    old_rad = getattr(monster, 'radiation', 0)

    monster.toxicity = old_tox * 2
    monster.radiation = old_rad * 2

    engine.messages.append([
        (f"{monster.name}: ", (200, 200, 200)),
        ("Curse of COVID detonates! ", (80, 180, 60)),
        (f"Tox {old_tox}\u2192{monster.toxicity}, Rad {old_rad}\u2192{monster.radiation}", (120, 220, 100)),
    ])

    mutation_count = 0
    max_mutations = 20
    while (monster.alive
           and getattr(monster, 'radiation', 0) >= _mut.MONSTER_RAD_THRESHOLD
           and mutation_count < max_mutations):
        _mut.force_monster_mutation(engine, monster)
        mutation_count += 1

    if mutation_count > 0:
        engine.messages.append([
            (f"{monster.name} undergoes {mutation_count} forced mutation(s)!", (180, 80, 220)),
        ])

    if engine.sdl_overlay:
        engine.sdl_overlay.add_tile_flash_ripple(
            [(monster.x, monster.y)], monster.x, monster.y,
            color=(80, 220, 60), duration=1.2,
        )
