"""XP progression functions extracted from GameEngine.

Each function takes `engine` as first parameter (the GameEngine instance)
and operates on its state. Function names match the original engine methods
so engine.py can forward calls directly.
"""

import random

import effects
from abilities import ABILITY_REGISTRY
from config import ZONE_SMARTSNESS_MULT, ZONE_DAMAGE_MULT


def _gain_smoking_xp(engine, strain):
    """Award smoking skill XP based on the strain smoked."""
    from items import STRAIN_SMOKING_XP

    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get("Smoking")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = STRAIN_SMOKING_XP.get(strain, 5)  # Default 5 XP for unknown strains
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Smoking", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    # Add unlock notification if this is the first XP
    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Smoking!", (255, 215, 0)),
        ])
    # Provide feedback to the player
    engine.messages.append([
        ("Smoking skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])


def _gain_rolling_xp(engine, strain, is_grinding=False):
    """Award rolling skill XP based on the strain rolled/ground."""
    from items import STRAIN_ROLLING_XP

    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get("Rolling")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = STRAIN_ROLLING_XP.get(strain, 5)  # Default 5 XP for unknown strains
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Rolling", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    # Add unlock notification if this is the first XP
    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Rolling!", (255, 215, 0)),
        ])
    # Provide feedback to the player
    action = "Grinding" if is_grinding else "Rolling"
    engine.messages.append([
        ("Rolling skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])


def _gain_munching_xp(engine, food_id):
    """Award munching skill XP based on food eaten."""
    from items import FOOD_MUNCHING_XP

    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get("Munching")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = FOOD_MUNCHING_XP.get(food_id, 5)  # Default 5 XP for unknown foods
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Munching", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    # Add unlock notification if this is the first XP
    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Munching!", (255, 215, 0)),
        ])
    # Provide feedback to the player
    engine.messages.append([
        ("Munching skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])


def _gain_deep_frying_xp(engine, food_item_id):
    """Award deep-frying skill XP based on food fried."""
    from items import get_deep_frying_xp

    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get("Deep-Frying")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = get_deep_frying_xp(food_item_id)
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Deep-Frying", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    # Add unlock notification if this is the first XP
    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Deep-Frying!", (255, 215, 0)),
        ])
    # Provide feedback to the player
    engine.messages.append([
        ("Deep-Frying skill: +", (255, 140, 0)),
        (str(adjusted_xp), (255, 180, 100)),
        (" potential XP", (255, 140, 0)),
    ])


def _gain_alcohol_xp(engine, drink_id: str):
    """Award alcoholism and drinking skill XP based on drink type."""
    from items import ITEM_DEFS

    # Get value from item definition (for consistency)
    base_xp = ITEM_DEFS.get(drink_id, {}).get("value", 20)
    adjusted = round(base_xp * 2 * engine.player_stats.xp_multiplier)
    bksmt = engine.player_stats.effective_book_smarts

    # Award primary skill (Alcoholism)
    engine.skills.gain_potential_exp("Alcoholism", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)
    # Award Drinking at equal rate
    engine.skills.gain_potential_exp("Drinking", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)

    # Feedback
    engine.messages.append([
        ("Alcoholism skill: +", (100, 150, 200)),
        (str(adjusted), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])
    engine.messages.append([
        ("Drinking skill: +", (100, 200, 150)),
        (str(adjusted), (150, 255, 200)),
        (" potential XP", (100, 200, 150)),
    ])


def _add_hangover_stacks(engine, stacks: int):
    """Add hangover stacks, with tolerance% chance per stack to resist."""
    tolerance = engine.player_stats.effective_tolerance
    added = 0
    for _ in range(stacks):
        if random.random() * 100 < tolerance:
            engine.messages.append([
                ("Tolerance! ", (100, 200, 100)),
                ("Hangover stack resisted.", (160, 160, 160)),
            ])
        else:
            engine.pending_hangover_stacks += 1
            added += 1
    return added


def _handle_alcohol(engine, item, drink_id: str):
    """Handle alcohol consumable effects."""
    from abilities import ABILITY_REGISTRY

    # Track last drink for Purple Drank
    engine.last_drink_id = drink_id

    # Gain skill XP first
    _gain_alcohol_xp(engine, drink_id)

    # Apply drink-specific effects
    if drink_id == "40oz":
        engine.player.armor = engine.player.max_armor
        effects.apply_effect(engine.player, engine, "forty_oz")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "fireball_shooter":
        engine.grant_ability_charges("breath_fire", 3)
        effects.apply_effect(engine.player, engine, "fireball_shooter_buff")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "blue_lagoon":
        engine.grant_ability_charges("ice_nova", 3)
        effects.apply_effect(engine.player, engine, "blue_lagoon_buff")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "limoncello":
        engine.grant_ability_charges("shocking_grasp", 5)
        effects.apply_effect(engine.player, engine, "limoncello_chain_shock")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "natty_light":
        import random as _rng
        engine.player.hp = min(engine.player.hp + 25, engine.player.max_hp)
        engine.messages.append(f"You crack a Natty Light. +25 HP ({engine.player.hp}/{engine.player.max_hp})")
        effects.apply_effect(engine.player, engine, "natty_light_buff")
        if _rng.randint(1, 6) == 1:
            _add_hangover_stacks(engine, 1)
            engine.messages.append([
                ("That one hit different... ", (200, 200, 100)),
                ("+1 hangover.", (255, 180, 80)),
            ])

    elif drink_id == "jagermeister":
        effects.apply_effect(engine.player, engine, "jagermeister_buff")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "butterbeer":
        effects.apply_effect(engine.player, engine, "butterbeer_buff")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "absinthe":
        from ai import get_initial_state, AIState
        reset_count = 0
        for mon in engine.dungeon.get_monsters():
            if not mon.alive:
                continue
            if not engine.dungeon.visible[mon.y, mon.x]:
                continue
            if getattr(mon, "ai_state", None) == AIState.CHASING:
                mon.ai_state = get_initial_state(mon.ai_type)
                mon.provoked = False
                mon.absinthe_grace = 3
                reset_count += 1
        if reset_count > 0:
            engine.messages.append([
                ("The Green Fairy whispers... ", (100, 220, 100)),
                (f"{reset_count} enemy(ies) lose interest.", (180, 255, 180)),
            ])
        else:
            engine.messages.append([
                ("The Green Fairy finds no one to calm.", (100, 220, 100)),
            ])
        _add_hangover_stacks(engine, 2)

    elif drink_id == "malt_liquor":
        effects.apply_effect(engine.player, engine, "malt_liquor")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "wizard_mind_bomb":
        # Add 2 charges to all active magic spells
        for inst in engine.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn and defn.is_spell and inst.can_use():
                inst.charges_remaining += 2
        effects.apply_effect(engine.player, engine, "wizard_mind_bomb")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "homemade_hennessy":
        effects.apply_effect(engine.player, engine, "hennessy")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "steel_reserve":
        heal = engine.player.max_hp // 2
        engine.player.heal(heal)
        engine.player_stats.permanent_armor_bonus += 3
        engine.player.max_armor = engine._compute_player_max_armor()
        engine.player.armor = min(engine.player.armor + 3, engine.player.max_armor)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "platinum_reserve":
        heal = engine.player.max_hp // 2
        engine.player.heal(heal)
        engine.player_stats.permanent_armor_bonus += 5
        effects.apply_effect(engine.player, engine, "platinum_reserve")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "mana_drink":
        effects.apply_effect(engine.player, engine, "mana_drink", stacks=1)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "virulent_vodka":
        effects.apply_effect(engine.player, engine, "virulent_vodka", stacks=1)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "five_loco":
        effects.apply_effect(engine.player, engine, "five_loco", stacks=1)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "white_gonster":
        effects.apply_effect(engine.player, engine, "white_gonster", stacks=1)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "dead_shot_daiquiri":
        effects.apply_effect(engine.player, engine, "dead_shot_daiquiri", stacks=1)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "alco_seltzer":
        # Remove 50 toxicity
        engine.player.toxicity = max(0, getattr(engine.player, 'toxicity', 0) - 50)
        # Floor-duration 100% tox resistance
        effects.apply_effect(engine.player, engine, "alco_seltzer_tox_resist")
        # 50-turn debuff immunity
        effects.apply_effect(engine.player, engine, "alco_seltzer_immunity")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "speedball":
        effects.apply_effect(engine.player, engine, "speedball")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "rainbow_rotgut":
        effects.apply_effect(engine.player, engine, "rainbow_rotgut")
        _add_hangover_stacks(engine, 1)

    elif drink_id == "root_beer":
        effects.apply_effect(engine.player, engine, "root_beer", duration=30)
        _add_hangover_stacks(engine, 1)

    elif drink_id == "sangria_40":
        effects.apply_effect(engine.player, engine, "sangria", duration=50, stacks=1)
        _add_hangover_stacks(engine, 1)

    engine.messages.append([
        ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
    ])

    # Alcoholism perks
    alc_level = engine.skills.get("Alcoholism").level
    if alc_level >= 1:
        effects.apply_effect(engine.player, engine, "peace_of_mind", duration=20, stacks=1, silent=True)
        engine.messages.append([("Peace of Mind (+1 STS)", (100, 200, 255))])
    if alc_level >= 3:
        engine.grant_ability_charges("throw_bottle", 1, silent=True)
        inst = next((a for a in engine.player_abilities if a.ability_id == "throw_bottle"), None)
        count = inst.charges_remaining if inst else 0
        engine.messages.append([("  +1 Throw Bottle charge", (180, 120, 60)), (f" ({count})", (150, 150, 150))])

    # Drinking perk 1: heal 10% max HP on any drink
    drink_level = engine.skills.get("Drinking").level
    if drink_level >= 1:
        heal_amt = max(1, engine.player.max_hp // 10)
        engine.player.heal(heal_amt)
        engine.messages.append([
            ("Liquid Bandage! ", (100, 200, 255)),
            (f"+{heal_amt} HP", (100, 255, 100)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])


def _handle_purple_drank(engine, item):
    """Handle Purple Drank: replay last drink effect, add copy of last drink to inventory, award 100 Drinking XP."""
    from items import ITEM_DEFS

    # Award flat 200 Drinking XP
    adjusted = round(200 * engine.player_stats.xp_multiplier)
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Drinking", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)
    engine.messages.append([
        ("Drinking skill: +", (100, 200, 150)),
        (str(adjusted), (150, 255, 200)),
        (" potential XP", (100, 200, 150)),
    ])

    engine.messages.append([
        ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
    ])

    last = engine.last_drink_id
    if last and last in ITEM_DEFS:
        # Replay the last drink's full effect (including its hangover, Alcoholism perks, and Drinking perk heal)
        last_defn = ITEM_DEFS[last]
        _handle_alcohol(engine, item, last)

        # Add a copy of the last drink to inventory
        engine._add_item_to_inventory(last)
        engine.messages.append([
            ("A ", (200, 200, 200)),
            (last_defn["name"], last_defn.get("color", (255, 255, 255))),
            (" appears in your inventory!", (200, 200, 200)),
        ])
    else:
        engine.messages.append([
            ("The drank fizzles... nothing to copy.", (150, 150, 150)),
        ])


def _handle_red_drank(engine, item):
    """Handle Red Drank: apply 200-turn buff that doubles drink durations, makes drinks free, and grants +100 energy."""
    # Award flat 200 Drinking XP
    adjusted = round(200 * engine.player_stats.xp_multiplier)
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Drinking", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)
    engine.messages.append([
        ("Drinking skill: +", (100, 200, 150)),
        (str(adjusted), (150, 255, 200)),
        (" potential XP", (100, 200, 150)),
    ])

    effects.apply_effect(engine.player, engine, "red_drank")
    engine.messages.append([
        ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
    ])
    engine.messages.append([
        ("Red Drank! ", (220, 40, 40)),
        ("Drinks are doubled, free, and give +100 energy!", (255, 120, 120)),
    ])

    # Drinking perk 1: heal 10% max HP on any drink
    drink_level = engine.skills.get("Drinking").level
    if drink_level >= 1:
        heal_amt = max(1, engine.player.max_hp // 10)
        engine.player.heal(heal_amt)
        engine.messages.append([
            ("Liquid Bandage! ", (100, 200, 255)),
            (f"+{heal_amt} HP", (100, 255, 100)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])


def _handle_green_drank(engine, item):
    """Handle Green Drank: apply stacking floor-duration buff. Each drink heals 20 HP/armor, removes 20 rad/tox, removes a random debuff per stack."""
    import random as _rng

    # Award flat 200 Drinking XP
    adjusted = round(200 * engine.player_stats.xp_multiplier)
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Drinking", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)
    engine.messages.append([
        ("Drinking skill: +", (100, 200, 150)),
        (str(adjusted), (150, 255, 200)),
        (" potential XP", (100, 200, 150)),
    ])

    effects.apply_effect(engine.player, engine, "green_drank", stacks=1)
    green = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'green_drank'), None)
    stacks = green.stacks if green else 1

    engine.messages.append([
        ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
    ])
    engine.messages.append([
        ("Green Drank! ", (40, 200, 60)),
        (f"Drinks now cleanse & heal (x{stacks})!", (100, 255, 120)),
    ])

    # Green Drank itself counts as a drink — trigger the cleanse
    _apply_green_drank_on_drink(engine, stacks)

    # Drinking perk 1: heal 10% max HP on any drink
    drink_level = engine.skills.get("Drinking").level
    if drink_level >= 1:
        heal_amt = max(1, engine.player.max_hp // 10)
        engine.player.heal(heal_amt)
        engine.messages.append([
            ("Liquid Bandage! ", (100, 200, 255)),
            (f"+{heal_amt} HP", (100, 255, 100)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])


def _apply_green_drank_on_drink(engine, stacks):
    """Apply Green Drank's per-drink cleanse: 20 HP, 20 armor, -20 rad/tox, remove random debuff, per stack."""
    import random as _rng
    p = engine.player

    # Heal 20 HP per stack
    heal = 20 * stacks
    old_hp = p.hp
    p.heal(heal)
    actual_heal = p.hp - old_hp

    # Restore 20 armor per stack
    armor_restore = 20 * stacks
    old_armor = p.armor
    p.armor = min(p.armor + armor_restore, p.max_armor)
    actual_armor = p.armor - old_armor

    # Remove 20 rad/tox per stack
    rad_remove = 20 * stacks
    tox_remove = 20 * stacks
    old_rad = getattr(p, 'radiation', 0)
    old_tox = getattr(p, 'toxicity', 0)
    if hasattr(p, 'radiation'):
        p.radiation = max(0, p.radiation - rad_remove)
    if hasattr(p, 'toxicity'):
        p.toxicity = max(0, p.toxicity - tox_remove)
    actual_rad = old_rad - getattr(p, 'radiation', 0)
    actual_tox = old_tox - getattr(p, 'toxicity', 0)

    # Remove random debuffs (1 per stack)
    debuffs_removed = []
    for _ in range(stacks):
        active_debuffs = [e for e in p.status_effects
                          if getattr(e, 'category', '') == 'debuff']
        if active_debuffs:
            chosen = _rng.choice(active_debuffs)
            chosen.expire(p, engine)
            p.status_effects.remove(chosen)
            debuffs_removed.append(getattr(chosen, 'display_name', chosen.id))

    # Build message
    parts = []
    if actual_heal > 0:
        parts.append(f"+{actual_heal} HP")
    if actual_armor > 0:
        parts.append(f"+{actual_armor} armor")
    if actual_rad > 0:
        parts.append(f"-{actual_rad} rad")
    if actual_tox > 0:
        parts.append(f"-{actual_tox} tox")
    if debuffs_removed:
        parts.append(f"cleansed {', '.join(debuffs_removed)}")

    if parts:
        engine.messages.append([
            ("Green Drank: ", (40, 200, 60)),
            (", ".join(parts), (100, 255, 120)),
        ])


def _handle_blue_drank(engine, item):
    """Handle Blue Drank: add a doubling stack, award 100 Drinking XP."""
    # Award flat 200 Drinking XP
    adjusted = round(200 * engine.player_stats.xp_multiplier)
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Drinking", adjusted, bksmt,
                                     briskness=engine.player_stats.total_briskness)
    engine.messages.append([
        ("Drinking skill: +", (100, 200, 150)),
        (str(adjusted), (150, 255, 200)),
        (" potential XP", (100, 200, 150)),
    ])

    engine.blue_drank_stacks += 1
    engine.messages.append([
        ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
    ])
    multiplier = 2 ** engine.blue_drank_stacks
    engine.messages.append([
        ("Blue Drank! ", (40, 150, 255)),
        (f"Next drink effect x{multiplier}!", (100, 200, 255)),
    ])

    # Drinking perk 1: heal 10% max HP on any drink
    drink_level = engine.skills.get("Drinking").level
    if drink_level >= 1:
        heal_amt = max(1, engine.player.max_hp // 10)
        engine.player.heal(heal_amt)
        engine.messages.append([
            ("Liquid Bandage! ", (100, 200, 255)),
            (f"+{heal_amt} HP", (100, 255, 100)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])


def _gain_item_skill_xp(engine, skill_name: str, item_id: str, silent: bool = False) -> None:
    """Award potential XP to a skill based on item value * skill multiplier."""
    from items import get_skill_xp

    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get(skill_name)
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = get_skill_xp(item_id, skill_name)
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        skill_name, adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    if not silent:
        # Add unlock notification if this is the first XP
        if was_locked:
            engine.messages.append([
                (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
            ])
        engine.messages.append([
            (f"{skill_name} skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])


def _sticky_fingers_check(engine, item_id: str) -> None:
    """Perk 2 of Stealing -- Sticky Fingers: chance to gain +1 STS on first pickup.

    Chance = item_value / 1000, capped at 50%.
    Only fires if the player has Stealing level >= 2.
    """
    stealing_skill = engine.skills.get("Stealing")
    if not stealing_skill or stealing_skill.level < 2:
        return
    import random as _random
    from items import get_item_value
    value = get_item_value(item_id)
    chance = min(0.5, value / 1000.0)
    if _random.random() < chance:
        ps = engine.player_stats
        ps.street_smarts += 1
        ps._base["street_smarts"] = ps.street_smarts
        engine.messages.append([
            ("Sticky Fingers! ", (255, 200, 50)),
            ("+1 Street Smarts", (200, 230, 255)),
            (f" (now {ps.street_smarts})", (150, 150, 150)),
        ])


def _gain_jaywalking_xp(engine) -> None:
    """Award Jaywalking XP when the player enters a room for the first time."""
    from config import ZONE_JAYWALK_MULT
    zone = engine._get_zone_info()[0]
    zone_mult = ZONE_JAYWALK_MULT.get(zone, 1.0)
    floor_mult = engine.current_floor + 1
    base_xp = 10 * zone_mult * floor_mult
    adjusted_xp = round(base_xp * engine.player_stats.xp_multiplier)

    skill = engine.skills.get("Jaywalking")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    engine.skills.gain_potential_exp(
        "Jaywalking", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )

    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Jaywalking!", (255, 215, 0)),
        ])
    engine.messages.append([
        ("Jaywalking skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])


def _gain_abandoning_xp(engine) -> None:
    """Award Abandoning XP for items and cash left on the current floor."""
    from items import get_skill_xp

    total_xp = 0
    item_count = 0
    for entity in engine.dungeon.entities:
        if entity.entity_type == "item":
            total_xp += get_skill_xp(entity.item_id, "Abandoning")
            item_count += 1
        elif entity.entity_type == "cash":
            total_xp += entity.cash_amount

    # Abandoning L3: Left Behind — gain +1 DR per item left on the floor
    skill = engine.skills.get("Abandoning")
    if item_count > 0 and skill and skill.level >= 3:
        import effects
        effects.apply_effect(engine.player, engine, "left_behind",
                             stacks=item_count, silent=True)
        engine.messages.append([
            ("Left Behind! ", (255, 200, 50)),
            (f"+{item_count} damage resistance until next floor.", (200, 200, 200)),
        ])

    if total_xp <= 0:
        return

    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    adjusted_xp = round(total_xp * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "Abandoning", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )

    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Abandoning!", (255, 215, 0)),
        ])
    engine.messages.append([
        ("Abandoning skill: +", (100, 150, 200)),
        (str(adjusted_xp), (150, 200, 255)),
        (" potential XP", (100, 150, 200)),
    ])


def _gain_melee_xp(engine, skill_name: str, damage: int) -> None:
    """Award melee skill potential XP equal to damage dealt. Shows unlock notification only."""
    # Check if skill is newly unlocked (no XP before this call)
    skill = engine.skills.get(skill_name)
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    zone = engine._get_zone_info()[0]
    zone_dmg_mult = ZONE_DAMAGE_MULT.get(zone, 1.0)
    adjusted_xp = round(damage * zone_dmg_mult * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        skill_name, adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )
    # Show unlock notification (no regular message for melee XP)
    if was_locked:
        engine.messages.append([
            (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
        ])


def _gain_spell_xp(engine, ability_id: str) -> None:
    """Award Smartsness XP when a spell is activated and its charge is consumed.

    XP calculation: 20 * floor_skill_mult * zone_skill_mult
    - floor_skill_mult: 1.0 + (current_floor * 0.5) [floors 1,2,3,4... get 1.0, 1.5, 2.0, 2.5...]
    - zone_skill_mult: From ZONE_SMARTSNESS_MULT (crack_den = 2.0)
    """
    # Check if this is a spell
    defn = ABILITY_REGISTRY.get(ability_id)
    if defn is None or not defn.is_spell:
        return

    # Calculate floor multiplier: 1.0 + (current_floor * 0.5)
    # current_floor is 0-indexed, so floor 0 (1st floor) -> 1.0, floor 1 (2nd floor) -> 1.5, etc.
    floor_mult = 1.0 + (engine.current_floor * 0.5)

    # Get zone multiplier
    zone = engine._get_zone_info()[0]
    zone_mult = ZONE_SMARTSNESS_MULT.get(zone, 1.0)

    # Calculate base XP: 20 * floor_skill_mult * zone_skill_mult
    base_xp = 20 * floor_mult * zone_mult
    adjusted_xp = round(base_xp * engine.player_stats.xp_multiplier)

    # Check if skill is newly unlocked
    skill = engine.skills.get("Smartsness")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    engine.skills.gain_potential_exp(
        "Smartsness", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )

    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Smartsness!", (255, 215, 0)),
        ])

    # Arcane Intelligence perk (Smartsness L3): 25% chance to gain 2 stacks
    if engine.skills.get("Smartsness").level >= 3 and random.random() < 0.25:
        effects.apply_effect(engine.player, engine, "arcane_intelligence", duration=20, stacks=2)
        ai_eff = next(
            (e for e in engine.player.status_effects if getattr(e, "id", "") == "arcane_intelligence"),
            None,
        )
        total_stacks = ai_eff.stacks if ai_eff else 2
        engine.messages.append(
            f"Arcane Intelligence! +2 spell dmg stacks ({total_stacks} total, "
            f"+{engine.player_stats.total_spell_damage} bonus spell dmg)"
        )


# Tag → skill name mapping for elemental spell XP.
# Add one entry per new elemental skill.
_ELEMENTAL_TAG_TO_SKILL: dict[str, str] = {
    "cold": "Cryomancy",
    "lightning": "Electrodynamics",
    "fire": "Pyromania",
}


def _gain_elemental_spell_xp(engine, ability_id: str, damage: int) -> None:
    """Award elemental skill XP when a tagged spell deals damage.

    Looks up the ability's tags, maps them to skills via _ELEMENTAL_TAG_TO_SKILL,
    and grants XP = damage dealt to each matching skill.
    """
    if damage <= 0:
        return
    defn = ABILITY_REGISTRY.get(ability_id)
    if defn is None:
        return
    bksmt = engine.player_stats.effective_book_smarts
    for tag, skill_name in _ELEMENTAL_TAG_TO_SKILL.items():
        if tag in defn.tags:
            engine.skills.gain_potential_exp(skill_name, damage, bksmt)


# Cross-element debuff mapping for Elementalist XP.
# Keys = spell element, values = debuff IDs from OTHER elements that qualify.
_CROSS_ELEMENT_DEBUFFS: dict[str, tuple[str, ...]] = {
    "fire":      ("chill", "shocked"),
    "cold":      ("ignite", "shocked"),
    "lightning": ("ignite", "chill"),
}


def _gain_elementalist_xp(engine, target, damage: int, spell_element: str) -> None:
    """Award Elementalist XP when an elemental spell hits a target with a cross-element debuff.

    XP = half damage dealt.  Silent (no per-hit message), only unlock notification.
    Must be called BEFORE apply_effect() for fire spells (ignite strips chill).
    """
    if damage <= 0 or target is None:
        return
    qualifying = _CROSS_ELEMENT_DEBUFFS.get(spell_element)
    if not qualifying:
        return
    has_cross = any(
        getattr(eff, 'id', '') in qualifying
        for eff in target.status_effects
    )
    if not has_cross:
        return

    skill = engine.skills.get("Elementalist")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp = max(1, round(damage * 0.5))
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Elementalist", xp, bksmt)

    if was_locked:
        engine.messages.append([
            (f"[NEW SKILL UNLOCKED] Elementalist!", (255, 215, 0)),
        ])


def _gain_catchin_fades_xp(engine, damage: int) -> None:
    """Award L Farming XP when the player takes damage.

    XP = damage * 0.5 (half a point per damage point).
    Silent — no per-hit message, only unlock notification.
    """
    if damage <= 0:
        return
    if not hasattr(engine, 'skills'):
        return

    skill = engine.skills.get("L Farming")
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    xp_amount = round(damage * 0.5)
    if xp_amount < 1:
        xp_amount = 1
    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
    engine.skills.gain_potential_exp(
        "L Farming", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )

    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] L Farming!", (255, 215, 0)),
        ])

    # L3 "Unfazed": 25% chance on taking damage to gain +1 Swagger for the floor
    if skill.level >= 3 and random.random() < 0.25:
        engine.player_stats.swagger += 1
        engine.unfazed_swagger_gained += 1
        engine.messages.append([
            ("Unfazed! ", (255, 220, 100)),
            ("+1 Swagger", (200, 200, 200)),
            (f" ({engine.unfazed_swagger_gained} this floor)", (150, 150, 150)),
        ])


def _gain_ammo_rat_xp(engine, item_id: str) -> None:
    """Award Ammo Rat XP when picking up ammo or a gun for the first time.

    XP = item value * 2 for guns, item value * 5 for ammo.
    """
    from items import ITEM_DEFS

    defn = ITEM_DEFS.get(item_id)
    if defn is None:
        return

    category = defn.get("category", "")
    subcategory = defn.get("subcategory", "")

    # Only award for ammo items or gun equipment
    is_ammo = category == "ammo"
    is_gun = subcategory == "gun"
    if not is_ammo and not is_gun:
        return

    base_value = defn.get("value", 10)
    # Ammo is common but cheap — multiply more; guns are rare but valuable
    xp_amount = base_value * 5 if is_ammo else base_value * 2

    adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)

    # Ammo Rat L2 "Ammo Nerd": 2x XP from ammo pickups
    skill = engine.skills.get("Ammo Rat")
    if is_ammo and skill.level >= 2:
        adjusted_xp *= 2
    was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

    engine.skills.gain_potential_exp(
        "Ammo Rat", adjusted_xp,
        engine.player_stats.effective_book_smarts,
        briskness=engine.player_stats.total_briskness
    )

    if was_locked:
        engine.messages.append([
            ("[NEW SKILL UNLOCKED] Ammo Rat!", (255, 215, 0)),
        ])
    engine.messages.append([
        ("Ammo Rat skill: +", (180, 160, 80)),
        (str(adjusted_xp), (220, 200, 120)),
        (" potential XP", (180, 160, 80)),
    ])
