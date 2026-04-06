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
        # Remove ALL tox; heal = tox_removed + CON*2; half excess → temp HP
        # Gain defense = tox_removed/20 (floor 1) for 50 turns
        tox = getattr(entity, "toxicity", 0)
        entity.toxicity = 0
        con = engine.player_stats.effective_constitution if is_player else 10
        heal_amount = max(20, tox + con * 2)
        hp_before = entity.hp
        entity.heal(heal_amount)
        healed = entity.hp - hp_before
        excess = heal_amount - healed
        temp_hp_gained = excess // 2
        if temp_hp_gained > 0:
            entity.temp_hp = getattr(entity, "temp_hp", 0) + temp_hp_gained
        def_bonus = max(1, tox // 20)
        effects.apply_effect(entity, engine, "iron_lung_defense", duration=50, defense_amount=def_bonus, silent=True)
        if is_player:
            parts = [f"Iron Lung purges all toxicity! Healed {healed} HP"]
            if temp_hp_gained > 0:
                parts.append(f", +{temp_hp_gained} temp HP")
            parts.append(f", +{def_bonus} DEF (50t)")
            if tox > 0:
                parts.append(f" [{tox} tox removed]")
            engine.messages.append("".join(parts))
        else:
            engine.messages.append(f"{entity.name} purges toxicity and toughens up!")

    elif eff_type in ("iron_lung_100", "iron_lung_50"):
        # Remove up to 100 or 50 tox; heal = removed*2 + CON*2; half excess → temp HP
        # +1 DEF per 10 tox removed for 50 turns
        cap = 100 if eff_type == "iron_lung_100" else 50
        tox = getattr(entity, "toxicity", 0)
        removed = min(cap, tox)
        entity.toxicity = tox - removed
        con = engine.player_stats.effective_constitution if is_player else 10
        heal_amount = removed * 2 + con * 2
        hp_before = entity.hp
        entity.heal(heal_amount)
        healed = entity.hp - hp_before
        excess = heal_amount - healed
        temp_hp_gained = excess // 2
        if temp_hp_gained > 0:
            entity.temp_hp = getattr(entity, "temp_hp", 0) + temp_hp_gained
        def_bonus = removed // 10
        if def_bonus > 0:
            effects.apply_effect(entity, engine, "iron_lung_defense", duration=50, defense_amount=def_bonus, silent=True)
        if is_player:
            parts = [f"Iron Lung cleanses! Healed {healed} HP"]
            if temp_hp_gained > 0:
                parts.append(f", +{temp_hp_gained} temp HP")
            if def_bonus > 0:
                parts.append(f", +{def_bonus} DEF (50t)")
            if removed > 0:
                parts.append(f" [{removed} tox removed]")
            engine.messages.append("".join(parts))
        else:
            engine.messages.append(f"{entity.name} cleanses toxicity and heals!")

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
        # Roll 100: Lightsaber + Force Sensitive + -50 rad + 5 Rad Nova
        if is_player:
            from items import create_item_entity
            from entity import Entity
            saber = Entity(**create_item_entity("green_lightsaber", 0, 0))
            entity.inventory.append(saber)
            engine.messages.append([
                ("A ", (255, 255, 255)),
                ("Green Lightsaber", (50, 255, 50)),
                (" materializes in your hands!", (255, 255, 255)),
            ])
            str_val = engine.player_stats.effective_strength
            duration = 50 + str_val * 2
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, silent=True)
            from combat import remove_radiation
            remove_radiation(engine, entity, 50)
            engine.grant_ability_charges("radiation_nova", 5)
            engine.messages.append([
                ("Force Sensitive! ", (80, 200, 120)),
                (f"({duration}t, +2 STR per 25 rad lost) ", (160, 255, 180)),
                ("-50 rad, +5 Rad Nova", (120, 255, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} glows with an eerie green light!")

    elif eff_type == "skywalker_force_nova_3":
        # 90-99: Force Sensitive + -50 rad + 3 Rad Nova
        if is_player:
            str_val = engine.player_stats.effective_strength
            duration = 50 + str_val * 2
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, silent=True)
            from combat import remove_radiation
            remove_radiation(engine, entity, 50)
            engine.grant_ability_charges("radiation_nova", 3)
            engine.messages.append([
                ("Force Sensitive! ", (80, 200, 120)),
                (f"({duration}t, +2 STR per 25 rad lost) ", (160, 255, 180)),
                ("-50 rad, +3 Rad Nova", (120, 255, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} surges with power!")

    elif eff_type == "skywalker_force_nova_2":
        # 70-89: Force Sensitive + -30 rad + 2 Rad Nova
        if is_player:
            str_val = engine.player_stats.effective_strength
            duration = 50 + str_val * 2
            effects.apply_effect(entity, engine, "force_sensitive", duration=duration, silent=True)
            from combat import remove_radiation
            remove_radiation(engine, entity, 30)
            engine.grant_ability_charges("radiation_nova", 2)
            engine.messages.append([
                ("Force Sensitive! ", (80, 200, 120)),
                (f"({duration}t, +2 STR per 25 rad lost) ", (160, 255, 180)),
                ("-30 rad, +2 Rad Nova", (120, 255, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} surges with power!")

    elif eff_type == "skywalker_nova_2":
        # 49-69: -30 rad + 2 Rad Nova (no buff)
        if is_player:
            from combat import remove_radiation
            remove_radiation(engine, entity, 30)
            engine.grant_ability_charges("radiation_nova", 2)
            engine.messages.append([
                ("Skywalker OG: ", (80, 200, 120)),
                ("-30 rad, +2 Rad Nova", (120, 255, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} loses some radiation!")

    elif eff_type == "skywalker_rad_loss":
        # 1-48: -30 rad only
        if is_player:
            from combat import remove_radiation
            remove_radiation(engine, entity, 30)
            engine.messages.append("Skywalker OG: -30 rad.")
        else:
            engine.messages.append(f"{entity.name} loses some radiation.")

    # ── Street Scholar (STSMT-based gun strain) ─────────────────────────
    elif eff_type == "calculated_aim_hp_ammo":
        # 90-100: Calculated Aim (long) + 5 Hollow Points + 100 each ammo
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 30 + stsmt * 3
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, silent=True)
            effects.apply_effect(entity, engine, "hollow_points",
                                 charges=5, silent=True)
            from inventory_mgr import _add_item_to_inventory
            for ammo_id in ("light_rounds", "medium_rounds", "heavy_rounds"):
                _add_item_to_inventory(engine, ammo_id, quantity=100)
            engine.messages.append([
                ("Calculated Aim! ", (180, 160, 220)),
                (f"({duration}t, auto-reload, 10% STS/kill) ", (200, 180, 240)),
                ("+ 5 Hollow Points + 100 each ammo!", (255, 180, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "calculated_aim_hp":
        # 75-89: Calculated Aim + 5 Hollow Points
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 20 + stsmt * 2
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, silent=True)
            effects.apply_effect(entity, engine, "hollow_points",
                                 charges=5, silent=True)
            engine.messages.append([
                ("Calculated Aim! ", (180, 160, 220)),
                (f"({duration}t, auto-reload, 10% STS/kill) ", (200, 180, 240)),
                ("+ 5 Hollow Points!", (255, 180, 80)),
            ])
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "calculated_aim":
        # 40-74: Calculated Aim only
        if is_player:
            stsmt = engine.player_stats.effective_street_smarts
            duration = 20 + stsmt * 2
            effects.apply_effect(entity, engine, "calculated_aim",
                                 duration=duration, silent=True)
            engine.messages.append([
                ("Calculated Aim! ", (180, 160, 220)),
                (f"({duration}t, auto-reload, 10% STS/kill)", (200, 180, 240)),
            ])
        else:
            engine.messages.append(f"{entity.name} focuses intently!")

    elif eff_type == "street_scholar_misfire":
        # 1-39: Dump all ammo from equipped guns
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
    elif eff_type == "kush_best":
        # 90-100: +70-80 rad, +10 spell dmg, +5 Rad Vent, +1 perm BKS
        import random as _rn
        from combat import add_radiation
        rad_gain = _rn.randint(70, 80)
        add_radiation(engine, entity, rad_gain)
        if is_player:
            bksmt = engine.player_stats.effective_book_smarts
            duration = 20 + bksmt * 2
            effects.apply_effect(entity, engine, "rad_nova_spell_buff",
                                 duration=duration, amount=10, silent=True)
            engine.grant_ability_charges("radiation_vent", 5)
            engine.player_stats.modify_base_stat("book_smarts", 1)
            engine.messages.append([
                ("Kushenheimer! ", (160, 220, 100)),
                (f"+{rad_gain} rad, +10 spell dmg ({duration}t), +5 Rad Vent, ", (200, 255, 200)),
                ("+1 permanent Book Smarts!", (160, 220, 100)),
            ])
        else:
            engine.messages.append(f"{entity.name} glows with nuclear energy!")

    elif eff_type == "kush_good":
        # 65-89: +50-60 rad, +10 spell dmg, +4 Rad Vent
        import random as _rn
        from combat import add_radiation
        rad_gain = _rn.randint(50, 60)
        add_radiation(engine, entity, rad_gain)
        if is_player:
            bksmt = engine.player_stats.effective_book_smarts
            duration = 20 + bksmt * 2
            effects.apply_effect(entity, engine, "rad_nova_spell_buff",
                                 duration=duration, amount=10, silent=True)
            engine.grant_ability_charges("radiation_vent", 4)
            engine.messages.append([
                ("Kushenheimer! ", (160, 220, 100)),
                (f"+{rad_gain} rad, +10 spell dmg ({duration}t), +4 Rad Vent", (200, 255, 200)),
            ])
        else:
            engine.messages.append(f"{entity.name} glows with nuclear energy!")

    elif eff_type == "kush_mid":
        # 40-64: +30-40 rad, +3 Rad Vent
        import random as _rn
        from combat import add_radiation
        rad_gain = _rn.randint(30, 40)
        add_radiation(engine, entity, rad_gain)
        if is_player:
            engine.grant_ability_charges("radiation_vent", 3)
            engine.messages.append([
                ("Kushenheimer: ", (160, 220, 100)),
                (f"+{rad_gain} rad, +3 Rad Vent", (200, 255, 200)),
            ])
        else:
            engine.messages.append(f"{entity.name} glows with nuclear energy!")

    elif eff_type == "kush_bad":
        # 1-39: Lose 100 rad
        if is_player:
            from combat import remove_radiation
            remove_radiation(engine, entity, 100)
            engine.messages.append("Kushenheimer fizzles. Lost 100 rad.")
        else:
            engine.messages.append(f"{entity.name} loses some radiation.")

    # ── Swamp Gas strain (TOL-based toxicity spillover) ────────────────
    elif eff_type == "nf_best":
        # 90-100: +80-100 tox, 50% spillover (20+TOL*2 t), +3 Pandemic
        import random as _rn
        from combat import add_toxicity
        tox_gain = _rn.randint(80, 100)
        add_toxicity(engine, entity, tox_gain)
        if is_player:
            tol = engine.player_stats.effective_tolerance
            duration = 20 + tol * 2
            effects.apply_effect(entity, engine, "tox_spillover_aura",
                                 duration=duration, spillover_pct=50, silent=True)
            engine.grant_ability_charges("pandemic", 3)
            engine.messages.append([
                ("Swamp Gas! ", (200, 180, 60)),
                (f"+{tox_gain} tox, 50% spillover ({duration}t), +3 Pandemic", (200, 255, 200)),
            ])
        else:
            engine.messages.append(f"{entity.name} releases a toxic cloud!")

    elif eff_type == "nf_good":
        # 65-89: +50-70 tox, 50% spillover (20+TOL t), +2 Pandemic
        import random as _rn
        from combat import add_toxicity
        tox_gain = _rn.randint(50, 70)
        add_toxicity(engine, entity, tox_gain)
        if is_player:
            tol = engine.player_stats.effective_tolerance
            duration = 20 + tol
            effects.apply_effect(entity, engine, "tox_spillover_aura",
                                 duration=duration, spillover_pct=50, silent=True)
            engine.grant_ability_charges("pandemic", 2)
            engine.messages.append([
                ("Swamp Gas! ", (200, 180, 60)),
                (f"+{tox_gain} tox, 50% spillover ({duration}t), +2 Pandemic", (200, 255, 200)),
            ])
        else:
            engine.messages.append(f"{entity.name} releases a toxic cloud!")

    elif eff_type == "nf_mid":
        # 40-64: +30-40 tox, +1 Pandemic
        import random as _rn
        from combat import add_toxicity
        tox_gain = _rn.randint(30, 40)
        add_toxicity(engine, entity, tox_gain)
        if is_player:
            engine.grant_ability_charges("pandemic", 1)
            engine.messages.append([
                ("Swamp Gas: ", (200, 180, 60)),
                (f"+{tox_gain} tox, +1 Pandemic", (200, 255, 200)),
            ])
        else:
            engine.messages.append(f"{entity.name} releases a toxic cloud!")

    elif eff_type == "nf_bad":
        # 1-39: Lose 100 tox
        if is_player:
            from combat import remove_toxicity
            remove_toxicity(engine, entity, 100)
            engine.messages.append("Swamp Gas fizzles. Lost 100 tox.")
        else:
            engine.messages.append(f"{entity.name} loses some toxicity.")

    # ── Double Helix strain (SWG-based mutation control) ──────────────────
    elif eff_type == "dh_glory":
        # 90-100: Force mutation (no rad cost), heal 15 HP per mutation
        if is_player:
            _purple_halt_force_mutation(engine, spend_rad=False)
            mut_count = len(engine.mutation_log)
            heal = 15 * mut_count
            if heal > 0:
                entity.hp = min(entity.max_hp, entity.hp + heal)
                engine.messages.append([
                    ("Double Helix: ", (180, 100, 220)),
                    (f"Healed {heal} HP ({mut_count} mutations x 15)!", (100, 255, 100)),
                ])
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    elif eff_type == "dh_strong":
        # 55-89: Force mutation (rad consumed), heal 10 HP per mutation
        if is_player:
            _purple_halt_force_mutation(engine, spend_rad=True)
            mut_count = len(engine.mutation_log)
            heal = 10 * mut_count
            if heal > 0:
                entity.hp = min(entity.max_hp, entity.hp + heal)
                engine.messages.append([
                    ("Double Helix: ", (180, 100, 220)),
                    (f"Healed {heal} HP ({mut_count} mutations x 10)!", (100, 255, 100)),
                ])
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    elif eff_type == "dh_weak":
        # 20-54: Heal 5 HP per mutation (no mutation forced)
        if is_player:
            mut_count = len(engine.mutation_log)
            heal = 5 * mut_count
            if heal > 0:
                entity.hp = min(entity.max_hp, entity.hp + heal)
                engine.messages.append([
                    ("Double Helix: ", (180, 100, 220)),
                    (f"Healed {heal} HP ({mut_count} mutations x 5)!", (100, 255, 100)),
                ])
            else:
                engine.messages.append("Double Helix fizzles. No mutations to draw from.")
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    elif eff_type == "dh_bad":
        # 1-19: -40 rad, +1 temp SWG consolation
        if is_player:
            from combat import remove_radiation
            remove_radiation(engine, entity, 40)
            effects.apply_effect(entity, engine, "purple_halt_swagger",
                                 duration=15, amount=1, silent=True)
            engine.messages.append(
                f"Double Helix drains your radiation. -40 rad. +1 SWG (15t)."
            )
        else:
            engine.messages.append(f"{entity.name} seems unaffected.")

    # ── Snickelfritz strain (offensive throw strain) ──────────────────────
    elif eff_type in ("snick_best", "snick_good", "snick_mid", "snick_bad"):
        import random as _rn
        from combat import deal_damage
        if is_player:
            # Self-smoke: take half damage, no debuff
            if eff_type == "snick_best":
                dmg = 50
            elif eff_type == "snick_good":
                dmg = _rn.randint(30, 40)
            elif eff_type == "snick_mid":
                dmg = _rn.randint(15, 25)
            else:
                dmg = _rn.randint(5, 10)
            deal_damage(engine, dmg, entity)
            engine.messages.append([
                ("You smoke the Snickelfritz. ", (150, 120, 60)),
                (f"It burns! -{dmg} HP.", (255, 80, 80)),
            ])
        else:
            # Enemy target: full damage + debuffs
            if eff_type == "snick_best":
                dmg = 100
                actual = max(1, dmg - entity.defense)
                deal_damage(engine, actual, entity)
                effects.apply_effect(entity, engine, "stun", duration=2, silent=True)
                engine.messages.append([
                    ("Snickelfritz! ", (150, 120, 60)),
                    (f"{entity.name} takes {actual} dmg + Stunned!", (255, 200, 80)),
                ])
            elif eff_type == "snick_good":
                dmg = _rn.randint(60, 80)
                actual = max(1, dmg - entity.defense)
                deal_damage(engine, actual, entity)
                effects.apply_effect(entity, engine, "crippled", duration=5, silent=True)
                engine.messages.append([
                    ("Snickelfritz! ", (150, 120, 60)),
                    (f"{entity.name} takes {actual} dmg + Crippled!", (255, 200, 80)),
                ])
            elif eff_type == "snick_mid":
                dmg = _rn.randint(30, 50)
                actual = max(1, dmg - entity.defense)
                deal_damage(engine, actual, entity)
                effects.apply_effect(entity, engine, "slow", duration=5, silent=True)
                engine.messages.append([
                    ("Snickelfritz! ", (150, 120, 60)),
                    (f"{entity.name} takes {actual} dmg + Slowed!", (255, 200, 80)),
                ])
            else:
                dmg = _rn.randint(10, 20)
                actual = max(1, dmg - entity.defense)
                deal_damage(engine, actual, entity)
                engine.messages.append([
                    ("Snickelfritz! ", (150, 120, 60)),
                    (f"{entity.name} takes {actual} dmg.", (255, 200, 80)),
                ])

    # ── Dosidos monster buff ─────────────────────────────────────────────
    elif eff_type == "dosidos_bksmt_buff":
        amount = eff.get("amount", 5)
        effects.apply_effect(entity, engine, "bksmt_buff", amount=amount, duration=9999, silent=True)
        engine.messages.append(
            f"{entity.name} gains +{amount} Book-Smarts from the Dosidos smoke!"
        )

    # ── Contact High (Smoking L5): spread strain effect to enemies within 3 tiles ──
    # Snickelfritz is excluded — its damage is already applied directly
    if not is_player and not _contact_high_spreading and strain != "Snickelfritz" and engine.skills.get("Smoking").level >= 5:
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
        _COLOR_GOOD, _COLOR_BAD, apply_scarred_tissue,
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

    # Apply mutation
    suffix, reversal = apply_fn(engine)

    # Award Mutation XP
    _MUTATION_XP = {"weak": 100, "strong": 250, "huge": 500}
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Mutation", _MUTATION_XP[tier], bksmt)

    # Build messages
    color = _COLOR_GOOD if polarity == "good" else _COLOR_BAD
    if spend_rad:
        cost_spent = rad - engine.player.radiation
        engine.messages.append(
            f"Double Helix forces a mutation! (-{cost_spent} rad)"
        )
    else:
        engine.messages.append("PURPLE HALT — free mutation! Radiation unchanged.")
    engine.messages.append([(f"You mutate! [{tier.capitalize()}] {desc}{suffix}", color)])

    # Scarred Tissue: bad mutations grant +1 random stat
    if polarity == "bad":
        apply_scarred_tissue(engine)

    engine.mutation_log.append({
        "tier": tier, "polarity": polarity,
        "description": desc, "suffix": suffix,
        "reversal": reversal,
    })

    # Triple Helix (Mutation L5): 30% chance for a bonus mutation, same tier
    from mutations import _apply_and_log_mutation
    if engine.skills.get("Mutation").level >= 5 and random.random() < 0.30:
        engine.messages.append([(f"  [Triple Helix] Bonus mutation!", (200, 150, 255))])
        _apply_and_log_mutation(engine, tier)


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

    # Visual: dark pulse radiating from player to all cursed targets
    if engine.sdl_overlay:
        pulse_tiles = [(player.x, player.y)]
        for m, _ in targets:
            # Line of tiles from player to each cursed monster
            dx = m.x - player.x
            dy = m.y - player.y
            steps = max(abs(dx), abs(dy))
            if steps > 0:
                for s in range(1, steps + 1):
                    tx = player.x + round(dx * s / steps)
                    ty = player.y + round(dy * s / steps)
                    if (tx, ty) not in pulse_tiles:
                        pulse_tiles.append((tx, ty))
        engine.sdl_overlay.add_tile_flash_ripple(
            pulse_tiles, player.x, player.y,
            color=(140, 60, 180), duration=0.6, ripple_speed=0.03,
        )

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
        engine.sdl_overlay.add_floating_text(
            monster.x, monster.y, f"STUN {duration}t", (255, 200, 100),
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
                if engine.sdl_overlay:
                    engine.sdl_overlay.add_floating_text(
                        entity.x, entity.y, str(damage), (255, 100, 255),
                    )

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

    from config import MAX_TOXICITY, MAX_RADIATION
    monster.toxicity = min(old_tox * 2, MAX_TOXICITY)
    monster.radiation = min(old_rad * 2, MAX_RADIATION)

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
