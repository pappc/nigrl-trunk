"""
Inventory and equipment management functions extracted from engine.py.

Each function takes `engine` as its first parameter (replacing `self`).
"""

import random

import effects
from config import RING_SLOTS
from entity import Entity
from foods import FOOD_DEFS, get_food_def, get_food_prefix_def
from items import (
    PREFIX_TOOL_ITEMS,
    build_inventory_display_name,
    create_item_entity,
    find_recipe,
    get_actions,
    get_craft_result_strain,
    get_item_def,
    get_item_value,
    is_stackable,
    calc_tolerance_rolls,
)

# Colors for segmented log messages
_C_MSG_NEUTRAL = (200, 200, 100)   # default yellow
_C_MSG_PICKUP  = (255, 200, 100)   # orange  (matches get_message_color "picked up")
_C_MSG_USE     = (100, 255, 100)   # green   (matches get_message_color "used")

# Inventory sort order: tool → equipment → material → consumable
_INV_CATEGORY_ORDER = {
    "tool": 0,
    "equipment": 1,
    "material": 2,
    "consumable": 3,
    "ammo": 4,
}

_INV_SUBCATEGORY_ORDER = {
    "weapon": 0,
    "ring": 1,
    "gun": 2,
}


# ------------------------------------------------------------------
# Phat Cloud (shared between Smoking L3 and Rolling L5)
# ------------------------------------------------------------------
def _trigger_phat_cloud(engine):
    """Deal 10 + tolerance//2 dmg to nearest visible enemy."""
    tlr = engine.player_stats.effective_tolerance
    cloud_dmg = 10 + tlr // 2
    best = None
    best_dist = float("inf")
    for mon in engine.dungeon.get_monsters():
        if not mon.alive:
            continue
        if not engine.dungeon.visible[mon.y, mon.x]:
            continue
        d = engine._dist_sq(engine.player.x, engine.player.y, mon.x, mon.y)
        if d < best_dist:
            best_dist = d
            best = mon
    if best is not None:
        best.take_damage(cloud_dmg)
        hp_disp = f"{best.hp}/{best.max_hp}" if best.alive else "dead"
        engine.messages.append([
            ("Phat Cloud! ", (150, 255, 150)),
            (f"Hit {best.name} for {cloud_dmg} dmg! ({hp_disp})", _C_MSG_USE),
        ])
        if not best.alive:
            engine.event_bus.emit("entity_died", entity=best, killer=engine.player)


# ------------------------------------------------------------------
# Deep Fryer
# ------------------------------------------------------------------

def _open_deep_fryer(engine):
    """Open the deep-fryer menu showing fryable food items."""
    from foods import FOOD_DEFS
    from menu_state import MenuState
    fryable = [
        (i, item) for i, item in enumerate(engine.player.inventory)
        if item.item_id in FOOD_DEFS and getattr(item, "prefix", None) is None
    ]
    if not fryable:
        engine.messages.append("You don't have any food to deep-fry.")
        return
    engine.menu_state = MenuState.DEEP_FRYER
    engine.deep_fryer_cursor = 0
    engine.deep_fryer_items = fryable  # list of (inv_index, item)


def _deep_fry_selected(engine):
    """Apply upgraded greasy prefix to the selected food item via the deep-fryer."""
    from foods import FOOD_DEFS, get_food_prefix_def
    from menu_state import MenuState
    if not hasattr(engine, "deep_fryer_items") or not engine.deep_fryer_items:
        return
    if engine.deep_fryer_cursor < 0 or engine.deep_fryer_cursor >= len(engine.deep_fryer_items):
        return

    _inv_idx, food_item = engine.deep_fryer_items[engine.deep_fryer_cursor]

    # Split stack: only fry one unit
    if food_item.quantity > 1:
        food_item.quantity -= 1
        kwargs = create_item_entity(food_item.item_id, engine.player.x, engine.player.y, strain=food_item.strain)
        new_ent = Entity(**kwargs)
        engine.player.inventory.append(new_ent)
        food_item = new_ent

    # Apply upgraded greasy prefix: 3 charges, 3 stacks per charge
    pdef = get_food_prefix_def("greasy")
    food_item.prefix = "greasy"
    food_item.charges = 3
    food_item.max_charges = 3
    # Store upgraded stacks-per-charge on the item so effect system can read it
    food_item.greasy_stacks_per_charge = 3
    adj = pdef["display_adjective"]
    base_name = get_item_def(food_item.item_id)["name"]
    food_item.name = f"{adj} {base_name}"
    c = food_item.charges
    engine.messages.append([
        ("The Deep Fryer sizzles! ", (255, 200, 100)),
        (f"{food_item.name}", (200, 140, 60)),
        (f" ({c}/{c}) — extra greasy!", (255, 200, 100)),
    ])

    # Award deep-frying XP
    engine._gain_deep_frying_xp(food_item.item_id)

    _sort_inventory(engine)
    engine.menu_state = MenuState.NONE


# ------------------------------------------------------------------
# Item menu
# ------------------------------------------------------------------

def _open_item_menu(engine, index):
    from menu_state import MenuState
    item = engine.player.inventory[index]
    engine.selected_item_index = index
    engine.selected_item_actions = get_actions(item.item_id)
    # Auto-position cursor on the use_verb if available
    defn = get_item_def(item.item_id)
    use_verb = defn.get("use_verb") if defn else None
    if use_verb and use_verb in engine.selected_item_actions:
        engine.item_menu_cursor = engine.selected_item_actions.index(use_verb)
    else:
        engine.item_menu_cursor = 0
    engine.menu_state = MenuState.ITEM_MENU


def _handle_item_menu_input(engine, action):
    from menu_state import MenuState
    action_type = action.get("type")
    actions = engine.selected_item_actions
    item = engine.player.inventory[engine.selected_item_index]
    defn = get_item_def(item.item_id)

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        return False

    # Up/Down — scroll through valid inventory items (those with a use_verb)
    if action_type == "move":
        dy = action.get("dy", 0)
        if dy != 0:
            valid_indices = [
                i for i, it in enumerate(engine.player.inventory)
                if it.item_id and get_item_def(it.item_id) and get_item_def(it.item_id).get("use_verb")
            ]
            if len(valid_indices) > 1 and engine.selected_item_index in valid_indices:
                cur_pos = valid_indices.index(engine.selected_item_index)
                new_idx = valid_indices[(cur_pos + dy) % len(valid_indices)]
                _open_item_menu(engine, new_idx)
                # Position cursor on the use_verb row
                new_verb = get_item_def(engine.player.inventory[new_idx].item_id).get("use_verb")
                if new_verb in engine.selected_item_actions:
                    engine.item_menu_cursor = engine.selected_item_actions.index(new_verb)
        return False

    # Enter — execute action at cursor
    if action_type == "confirm_target":
        return _execute_item_action(engine, actions[engine.item_menu_cursor])

    # Number keys — still work as direct selection
    if action_type == "select_action":
        idx = action["index"]
        if 0 <= idx < len(actions):
            return _execute_item_action(engine, actions[idx])
        return False

    # Spacebar — execute the use verb / "Use on..." / Equip (first actionable verb)
    if action_type == "item_use":
        use_verb = defn.get("use_verb")
        throw_verb = defn.get("throw_verb")
        for act in actions:
            if act == use_verb or act == throw_verb or act == "Use on..." or act == "Equip":
                return _execute_item_action(engine, act)
        return False

    # E — examine
    if action_type == "open_equipment":
        if "Examine" in actions:
            return _execute_item_action(engine, "Examine")
        return False

    # D — drop
    if action_type == "drop_item":
        if "Drop" in actions:
            return _execute_item_action(engine, "Drop")
        return False

    # Shift+D — destroy
    if action_type == "destroy_item":
        if "Destroy" in actions:
            return _execute_item_action(engine, "Destroy")
        return False

    return False


def _execute_item_action(engine, action_name):
    from menu_state import MenuState
    item = engine.player.inventory[engine.selected_item_index]
    defn = get_item_def(item.item_id)

    if action_name == "Equip":
        success = _equip_item(engine, engine.selected_item_index)
        if success:
            engine.menu_state = MenuState.NONE
            engine.selected_item_index = None
        return success

    elif action_name == "Drop":
        _drop_item(engine, engine.selected_item_index)
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        return False

    elif action_name == "Use on...":
        engine.menu_state = MenuState.COMBINE_SELECT
        _init_combine_cursor(engine)
        return False

    elif action_name == defn.get("use_verb"):
        engine._red_drank_free_action = False
        _use_item(engine, engine.selected_item_index)
        if engine.menu_state not in (MenuState.TARGETING, MenuState.COMBINE_SELECT):
            engine.selected_item_index = None
            engine.menu_state = MenuState.NONE
        if engine._red_drank_free_action:
            engine._red_drank_free_action = False
            return False
        return True

    elif action_name == defn.get("throw_verb"):
        engine._enter_targeting(engine.selected_item_index)
        return False

    elif action_name == "Examine":
        engine.menu_state = MenuState.EXAMINE
        return False

    elif action_name == "Destroy":
        engine.menu_state = MenuState.DESTROY_CONFIRM
        engine.destroy_confirm_cursor = 0  # default to No
        return False

    return False


# ------------------------------------------------------------------
# Equipment
# ------------------------------------------------------------------

def _equip_item(engine, index) -> bool:
    from menu_state import MenuState
    item = engine.player.inventory[index]
    defn = get_item_def(item.item_id)
    slot = defn["equip_slot"]
    if slot is None:
        return False

    str_req = defn.get("str_req")
    if str_req is not None and engine.player_stats.effective_strength < str_req:
        engine.messages.append(
            f"Need {str_req} STR to equip {item.name}! "
            f"(you have {engine.player_stats.effective_strength})"
        )
        return False

    # Gun class validation: small guns -> sidearm only, medium+ -> weapon only
    gun_class = defn.get("gun_class")
    if gun_class == "small" and slot != "sidearm":
        engine.messages.append("Small guns can only be equipped in the sidearm slot.")
        return False
    if gun_class and gun_class != "small" and slot != "weapon":
        engine.messages.append("This gun is too large for the sidearm slot.")
        return False

    if slot == "weapon":
        new_weapon = engine.player.inventory[index]
        old_weapon = engine.equipment["weapon"]
        if old_weapon is not None:
            engine.player.inventory.append(old_weapon)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (old_weapon.name, old_weapon.color)])
        engine.player.inventory.remove(new_weapon)
        engine.equipment["weapon"] = new_weapon

        # Revoke any ability granted by the old weapon
        if old_weapon:
            old_defn = get_item_def(old_weapon.item_id)
            revoked = old_defn.get("grants_ability") if old_defn else None
            if revoked:
                engine.revoke_ability(revoked)

        # Grant any ability given by the new weapon
        new_defn = get_item_def(engine.equipment["weapon"].item_id)
        granted = new_defn.get("grants_ability") if new_defn else None
        if granted:
            engine.grant_ability(granted)

        # Auto-set primary gun if this is a gun
        if defn.get("subcategory") == "gun":
            engine.primary_gun = "weapon"
    elif slot == "sidearm":
        new_sidearm = engine.player.inventory[index]
        old_sidearm = engine.equipment["sidearm"]
        if old_sidearm is not None:
            engine.player.inventory.append(old_sidearm)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (old_sidearm.name, old_sidearm.color)])
        engine.player.inventory.remove(new_sidearm)
        engine.equipment["sidearm"] = new_sidearm

        # Revoke any ability granted by the old sidearm
        if old_sidearm:
            old_defn = get_item_def(old_sidearm.item_id)
            revoked = old_defn.get("grants_ability") if old_defn else None
            if revoked:
                engine.revoke_ability(revoked)

        # Grant any ability given by the new sidearm
        new_defn = get_item_def(engine.equipment["sidearm"].item_id)
        granted = new_defn.get("grants_ability") if new_defn else None
        if granted:
            engine.grant_ability(granted)

        # Auto-set primary gun
        engine.primary_gun = "sidearm"
    elif slot == "neck":
        new_neck = engine.player.inventory[index]
        if engine.neck is not None:
            swapped = engine.neck
            engine.player.inventory.append(swapped)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
        engine.player.inventory.remove(new_neck)
        engine.neck = new_neck
    elif slot == "feet":
        new_feet = engine.player.inventory[index]
        if engine.feet is not None:
            swapped = engine.feet
            engine.player.inventory.append(swapped)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
        engine.player.inventory.remove(new_feet)
        engine.feet = new_feet
    elif slot == "hat":
        new_hat = engine.player.inventory[index]
        if engine.hat is not None:
            swapped = engine.hat
            engine.player.inventory.append(swapped)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
        engine.player.inventory.remove(new_hat)
        engine.hat = new_hat
    elif slot == "ring":
        empty = next((i for i, r in enumerate(engine.rings) if r is None), None)
        if empty is None:
            # All ring slots are full; open menu to select which ring to replace
            engine.pending_ring_item_index = index
            engine.ring_replace_cursor = 0
            engine.menu_state = MenuState.RING_REPLACE
            return False
        engine.rings[empty] = engine.player.inventory.pop(index)
    else:
        return False

    _refresh_ring_stat_bonuses(engine)
    engine.messages.append([("Equipped ", _C_MSG_NEUTRAL), (item.name, item.color)])
    return True


def _handle_equipment_input(engine, action):
    from menu_state import MenuState
    action_type = action.get("type")

    if action_type in ("close_menu", "open_equipment"):
        engine.menu_state = MenuState.NONE
        return False

    # Build flat ordered list of occupied slots: (slot_id, item)
    # slot_id is "weapon", "neck", "feet", or ("ring", index)
    def _occupied_slots():
        slots = []
        if engine.equipment["weapon"] is not None:
            slots.append(("weapon", engine.equipment["weapon"]))
        if engine.equipment.get("sidearm") is not None:
            slots.append(("sidearm", engine.equipment["sidearm"]))
        if engine.neck is not None:
            slots.append(("neck", engine.neck))
        if engine.feet is not None:
            slots.append(("feet", engine.feet))
        if engine.hat is not None:
            slots.append(("hat", engine.hat))
        for i, r in enumerate(engine.rings):
            if r is not None:
                slots.append((("ring", i), r))
        return slots

    # Cursor navigation (up/down arrows — intercepted here, not passed to move)
    if action_type == "move":
        dy = action.get("dy", 0)
        n = max(0, len(_occupied_slots()) - 1)
        engine.equipment_cursor = max(0, min(n, engine.equipment_cursor + dy))
        return False

    # Enter = unequip item at cursor
    if action_type == "confirm_target":
        occupied = _occupied_slots()
        did_unequip = False
        if engine.equipment_cursor < len(occupied):
            slot_id, item = occupied[engine.equipment_cursor]
            if slot_id == "weapon":
                engine.equipment["weapon"] = None
                old_defn = get_item_def(item.item_id)
                revoked = old_defn.get("grants_ability") if old_defn else None
                if revoked:
                    engine.revoke_ability(revoked)
                # Update primary gun if we unequipped the primary
                if engine.primary_gun == "weapon":
                    if engine.equipment.get("sidearm") and get_item_def(engine.equipment["sidearm"].item_id).get("subcategory") == "gun":
                        engine.primary_gun = "sidearm"
                    else:
                        engine.primary_gun = None
            elif slot_id == "sidearm":
                engine.equipment["sidearm"] = None
                old_defn = get_item_def(item.item_id)
                revoked = old_defn.get("grants_ability") if old_defn else None
                if revoked:
                    engine.revoke_ability(revoked)
                if engine.primary_gun == "sidearm":
                    if engine.equipment.get("weapon") and get_item_def(engine.equipment["weapon"].item_id).get("subcategory") == "gun":
                        engine.primary_gun = "weapon"
                    else:
                        engine.primary_gun = None
            elif slot_id == "neck":
                engine.neck = None
            elif slot_id == "feet":
                engine.feet = None
            elif slot_id == "hat":
                engine.hat = None
            else:
                _, ring_idx = slot_id
                engine.rings[ring_idx] = None
            engine.player.inventory.append(item)
            _sort_inventory(engine)
            engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (item.name, item.color)])
            # Clamp cursor to new list length
            n_remaining = max(0, len(occupied) - 2)
            engine.equipment_cursor = min(engine.equipment_cursor, n_remaining)
            did_unequip = True
        _refresh_ring_stat_bonuses(engine)
        return did_unequip

    return False


# ------------------------------------------------------------------
# Ring stat bonuses
# ------------------------------------------------------------------

def _refresh_ring_stat_bonuses(engine):
    """Recompute ring/neck stat bonuses from all equipped rings and neck item and apply to player_stats.
    Also syncs player.max_hp (clamping hp to new max if it dropped) and max_armor."""
    totals: dict[str, int] = {}
    for ring in engine.rings:
        if ring is None:
            continue
        defn = get_item_def(ring.item_id)
        if defn:
            for stat, amount in defn.get("stat_bonus", {}).items():
                totals[stat] = totals.get(stat, 0) + amount
    if engine.neck is not None:
        defn = get_item_def(engine.neck.item_id)
        if defn:
            for stat, amount in defn.get("stat_bonus", {}).items():
                totals[stat] = totals.get(stat, 0) + amount
    if engine.feet is not None:
        defn = get_item_def(engine.feet.item_id)
        if defn:
            for stat, amount in defn.get("stat_bonus", {}).items():
                totals[stat] = totals.get(stat, 0) + amount
    if engine.hat is not None:
        defn = get_item_def(engine.hat.item_id)
        if defn:
            for stat, amount in defn.get("stat_bonus", {}).items():
                totals[stat] = totals.get(stat, 0) + amount
    engine.player_stats.set_ring_bonuses(totals)
    new_max = engine.player_stats.max_hp
    engine.player.max_hp = new_max
    if engine.player.hp > new_max:
        engine.player.hp = new_max

    # Update max_armor (clamp current armor to new max if needed)
    new_max_armor = engine._compute_player_max_armor()
    engine.player.max_armor = new_max_armor
    if engine.player.armor > new_max_armor:
        engine.player.armor = new_max_armor

    # Update tox resistance from equipment
    tox_res = 0
    for slot_item in [engine.neck, engine.feet, engine.hat]:
        if slot_item is not None:
            defn = get_item_def(slot_item.item_id)
            if defn:
                tox_res += defn.get("tox_resistance", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                tox_res += defn.get("tox_resistance", 0)
    engine.player_stats.tox_resistance = tox_res

    # Update rad resistance from equipment
    rad_res = 0
    for slot_item in [engine.neck, engine.feet, engine.hat]:
        if slot_item is not None:
            defn = get_item_def(slot_item.item_id)
            if defn:
                rad_res += defn.get("rad_resistance", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                rad_res += defn.get("rad_resistance", 0)
    engine.player_stats.rad_resistance = rad_res

    # Update briskness from equipment
    brisk = 0
    for slot_item in [engine.neck, engine.feet, engine.hat]:
        if slot_item is not None:
            defn = get_item_def(slot_item.item_id)
            if defn:
                brisk += defn.get("briskness", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                brisk += defn.get("briskness", 0)
    engine.player_stats.briskness = brisk

    # Update energy per tick from equipment
    ept = 0
    for slot_item in [engine.neck, engine.feet, engine.hat]:
        if slot_item is not None:
            defn = get_item_def(slot_item.item_id)
            if defn:
                ept += defn.get("energy_per_tick", 0)
    for ring in engine.rings:
        if ring is not None:
            defn = get_item_def(ring.item_id)
            if defn:
                ept += defn.get("energy_per_tick", 0)
    engine.player_stats.equipment_energy_per_tick = ept


def _sync_player_max_hp(engine):
    """Sync entity max_hp from player_stats.max_hp after constitution changes.
    Clamps current HP to the new max if it dropped."""
    new_max = engine.player_stats.max_hp
    engine.player.max_hp = new_max
    if engine.player.hp > new_max:
        engine.player.hp = new_max


# ------------------------------------------------------------------
# Inventory sort
# ------------------------------------------------------------------

def _sort_inventory(engine):
    """Sort player inventory: tools -> equipment (by subcategory) -> materials -> consumables."""
    def _key(item):
        defn = get_item_def(item.item_id)
        if defn:
            cat    = defn.get("category", "")
            subcat = defn.get("subcategory") or ""
        else:
            cat = subcat = ""
        return (
            _INV_CATEGORY_ORDER.get(cat, 99),
            _INV_SUBCATEGORY_ORDER.get(subcat, 99),
            item.name,
            item.strain or "",
        )
    engine.player.inventory.sort(key=_key)


def _add_item_to_inventory(engine, item_id, strain=None, quantity=1):
    """Create an item and add it to player inventory, stacking if possible."""
    for _ in range(quantity):
        # Try to stack with existing item (skip charged items — each is unique)
        if is_stackable(item_id):
            for existing in engine.player.inventory:
                if (existing.item_id == item_id and existing.strain == strain
                        and getattr(existing, "charges", None) is None):
                    existing.quantity += 1
                    return
        # Create new item
        kwargs = create_item_entity(item_id, engine.player.x, engine.player.y, strain=strain)
        new_item = Entity(**kwargs)
        engine.player.inventory.append(new_item)
    _sort_inventory(engine)


def _acid_armor_break_equipment(engine):
    """Break a random piece of equipped equipment from Acid Armor effect."""
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
        engine.messages.append(f"Acid Armor breaks your {item.name}!")
    else:
        engine.messages.append("Acid Armor attacks, but you have no equipped items!")


# ------------------------------------------------------------------
# Drop / Use
# ------------------------------------------------------------------

def _drop_item(engine, index):
    item = engine.player.inventory[index]
    if item.quantity > 1:
        item.quantity -= 1
        kwargs = create_item_entity(item.item_id, engine.player.x, engine.player.y, strain=item.strain)
        dropped = Entity(**kwargs)
        engine.dungeon.add_entity(dropped)
        engine.messages.append([("Dropped ", _C_MSG_NEUTRAL), (dropped.name, dropped.color)])
    else:
        engine.player.inventory.pop(index)
        item.x = engine.player.x
        item.y = engine.player.y
        engine.dungeon.add_entity(item)
        engine.messages.append([("Dropped ", _C_MSG_NEUTRAL), (item.name, item.color)])


def _use_item(engine, index):
    item = engine.player.inventory[index]
    defn = get_item_def(item.item_id)
    effect = defn.get("use_effect")

    if effect is None:
        return

    effect_type = effect.get("type")
    skip_consume = False

    if effect_type == "message":
        text = effect["text"].format(name=item.name)
        engine.messages.append(text)

    elif effect_type == "heal":
        base_amount = effect.get("amount", 5)
        amount = base_amount
        engine.player.heal(amount)
        engine.messages.append([
            ("Used ", _C_MSG_USE), (item.name, item.color),
            (f". Healed {amount} HP.", _C_MSG_USE),
        ])

    elif effect_type == "strain_roll":
        tlr = engine.player_stats.effective_tolerance
        num_rolls, roll_floor = calc_tolerance_rolls(item.strain, tlr)
        rolls = [max(roll_floor + 1, random.randint(1, 100))
                 for _ in range(num_rolls)]
        roll = max(rolls)
        if num_rolls > 1:
            engine.messages.append([
                ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                (f". Rolled {num_rolls}x: {rolls} -> {roll}", _C_MSG_USE),
            ])
        else:
            engine.messages.append([
                ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                (f". (Roll: {roll})", _C_MSG_USE),
            ])
        engine._apply_strain_effect(engine.player, item.strain, roll, "player")

        # Gain smoking skill XP based on strain
        engine._gain_smoking_xp(item.strain)

        # Check for double-smoking effects (e.g., Hennessy)
        # Any effect that grants double smoking has a 20% chance to trigger
        for effect_obj in engine.player.status_effects:
            if getattr(effect_obj, 'id', '') == 'hennessy':
                if random.random() < 0.20:
                    # Re-apply the same strain effect
                    engine.messages.append([
                        ("The Hennessy amplifies the high! ", (200, 100, 100)),
                    ])
                    henny_rolls = [max(roll_floor + 1, random.randint(1, 100))
                                   for _ in range(num_rolls)]
                    henny_roll = max(henny_rolls)
                    engine._apply_strain_effect(engine.player, item.strain, henny_roll, "player")
                    engine._gain_smoking_xp(item.strain)
                break

        # Phat Cloud (Smoking level 3): deal 10 + tolerance//2 dmg to nearest visible enemy
        smoking_level = engine.skills.get("Smoking").level
        if smoking_level >= 3:
            _trigger_phat_cloud(engine)

        # Roach Fiend (Smoking level 4): 30% chance joint is not consumed
        if smoking_level >= 4:
            if random.random() < 0.3:
                skip_consume = True
                engine.messages.append([
                    ("Roach Fiend! ", (200, 255, 100)),
                    ("The roach hangs on.", _C_MSG_USE),
                ])

    elif effect_type == "stat_boost" or "effect_id" in effect:
        amount = effect.get("amount", 0)
        stat = effect.get("stat")
        duration = effect.get("duration", 10)
        effect_id = effect.get("effect_id", "stat_mod")
        engine.messages.append([("Used ", _C_MSG_USE), (item.name, item.color), (".", _C_MSG_USE)])
        effects.apply_effect(engine.player, engine, effect_id,
                             duration=duration, amount=amount, stat=stat)

    elif effect_type == "alcohol":
        drink_id = effect.get("drink_id")
        # Red Drank: set duration multiplier while handling drink
        has_red = any(getattr(e, 'id', '') == 'red_drank' for e in engine.player.status_effects)
        if has_red:
            engine._drink_duration_multiplier = 2
        if engine.blue_drank_stacks > 0:
            multiplier = 2 ** engine.blue_drank_stacks
            engine.blue_drank_stacks = 0
            saved_hangover = engine.pending_hangover_stacks
            for _ in range(multiplier):
                engine._handle_alcohol(item, drink_id)
            engine.pending_hangover_stacks = saved_hangover
            engine.messages.append([
                ("Blue Drank! ", (40, 150, 255)),
                (f"Effect x{multiplier}, no hangover!", (100, 200, 255)),
            ])
        else:
            engine._handle_alcohol(item, drink_id)
        if has_red:
            engine._drink_duration_multiplier = 1
            engine.player.energy += 100
            engine._red_drank_free_action = True
            engine.messages.append([
                ("Red Drank! ", (220, 40, 40)),
                ("Free drink! +100 energy!", (255, 120, 120)),
            ])
        # Green Drank: trigger cleanse on drink
        green = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'green_drank'), None)
        if green:
            from xp_progression import _apply_green_drank_on_drink
            _apply_green_drank_on_drink(engine, green.stacks)
        # Drinking perk 2: 20% chance not consumed
        drink_level = engine.skills.get("Drinking").level
        if drink_level >= 2 and random.random() < 0.20:
            skip_consume = True
            engine.messages.append([
                ("One More Sip! ", (100, 200, 255)),
                ("The bottle's not empty yet.", (200, 200, 200)),
            ])

    elif effect_type == "soft_drink":
        drink_id = effect.get("drink_id")
        # Red Drank: set duration multiplier for non-red soft drinks
        has_red = any(getattr(e, 'id', '') == 'red_drank' for e in engine.player.status_effects)
        if has_red and drink_id != "red_drank":
            engine._drink_duration_multiplier = 2
        if drink_id == "red_drank":
            engine._handle_red_drank(item)
        elif drink_id == "green_drank":
            engine._handle_green_drank(item)
        elif drink_id == "blue_drank":
            engine._handle_blue_drank(item)
        elif drink_id == "purple_drank":
            if engine.blue_drank_stacks > 0:
                multiplier = 2 ** engine.blue_drank_stacks
                engine.blue_drank_stacks = 0
                for _ in range(multiplier):
                    engine._handle_purple_drank(item)
                engine.messages.append([
                    ("Blue Drank! ", (40, 150, 255)),
                    (f"Effect x{multiplier}!", (100, 200, 255)),
                ])
            else:
                engine._handle_purple_drank(item)
        if has_red and drink_id != "red_drank":
            engine._drink_duration_multiplier = 1
            engine.player.energy += 100
            engine._red_drank_free_action = True
            engine.messages.append([
                ("Red Drank! ", (220, 40, 40)),
                ("Free drink! +100 energy!", (255, 120, 120)),
            ])
        # Green Drank: trigger cleanse on non-green drinks
        if drink_id != "green_drank":
            green = next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'green_drank'), None)
            if green:
                from xp_progression import _apply_green_drank_on_drink
                _apply_green_drank_on_drink(engine, green.stacks)
        # Drinking perk 2: 20% chance not consumed
        drink_level = engine.skills.get("Drinking").level
        if drink_level >= 2 and random.random() < 0.20:
            skip_consume = True
            engine.messages.append([
                ("One More Sip! ", (100, 200, 255)),
                ("The bottle's not empty yet.", (200, 200, 200)),
            ])

    elif effect_type == "meth":
        tol = engine.player_stats.effective_tolerance
        meth_amount = int(100 * max(0.5, 1.5 - tol * 0.02))
        p = engine.player
        old_meth = p.meth
        p.meth = min(p.meth + meth_amount, p.max_meth)
        gained = p.meth - old_meth
        engine.messages.append([
            ("You use the ", _C_MSG_USE), (item.name, item.color),
            (f". +{gained} Meth.", (0, 180, 255)),
        ])
        # Grant 100 Meth-Head XP
        skill = engine.skills.get("Meth-Head")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0
        engine.skills.gain_potential_exp(
            "Meth-Head", 100,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness,
        )
        if was_locked:
            engine.messages.append([
                ("[NEW SKILL UNLOCKED] Meth-Head!", (255, 215, 0)),
            ])

    elif effect_type == "blue_meth_smoke":
        # Blue Meth Joint: d100 roll with tolerance multi-roll, 6-tier meth table
        BLUE_METH_TABLE = [
            (16,  -20, "Bad Batch"),
            (33,   30, "Weak Hit"),
            (50,   60, "Mild Hit"),
            (67,  100, "Solid Hit"),
            (84,  130, "Strong Hit"),
            (100, 180, "Crystal Cloud"),
        ]
        tlr = engine.player_stats.effective_tolerance
        num_rolls, roll_floor = calc_tolerance_rolls("Blue Meth", tlr)
        rolls = [max(roll_floor + 1, random.randint(1, 100))
                 for _ in range(num_rolls)]
        roll = max(rolls)
        # Find tier
        meth_amount = 0
        tier_name = ""
        for ceiling, amount, name in BLUE_METH_TABLE:
            if roll <= ceiling:
                meth_amount = amount
                tier_name = name
                break
        p = engine.player
        if meth_amount >= 0:
            old_meth = p.meth
            p.meth = min(p.meth + meth_amount, p.max_meth)
            gained = p.meth - old_meth
            meth_str = f"+{gained} Meth"
        else:
            lost = min(-meth_amount, p.meth)
            p.meth = max(0, p.meth + meth_amount)
            gained = -lost
            meth_str = f"-{lost} Meth"
        if num_rolls > 1:
            engine.messages.append([
                ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                (f". Rolled {num_rolls}x: {rolls} -> {roll}. ", _C_MSG_USE),
                (f"{tier_name}! {meth_str}.", (0, 180, 255)),
            ])
        else:
            engine.messages.append([
                ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                (f". (Roll: {roll}) ", _C_MSG_USE),
                (f"{tier_name}! {meth_str}.", (0, 180, 255)),
            ])
        # Smoking XP (same as Dosidos: 70)
        engine._gain_smoking_xp("Blue Meth")
        # Meth-Head XP
        engine.skills.gain_potential_exp(
            "Meth-Head", 100,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness,
        )

    elif effect_type == "food":
        food_id = effect.get("food_id")
        _use_food(engine, item, food_id)

    elif effect_type == "torch_burn":
        # Enter combine mode to select which item to burn
        from menu_state import MenuState
        engine.menu_state = MenuState.COMBINE_SELECT
        engine.selected_item_index = index
        _init_combine_cursor(engine)
        engine.messages.append([
            ("Select an item to burn with ", _C_MSG_USE), (item.name, item.color),
        ])
        return

    # Skill XP
    skill_xp = effect.get("skill_xp")
    if skill_xp:
        for skill_name, xp_amount in skill_xp.items():
            # Check if skill is newly unlocked (no XP before this call)
            skill = engine.skills.get(skill_name)
            was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

            adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)
            engine.skills.gain_potential_exp(
                skill_name, adjusted_xp,
                engine.player_stats.effective_book_smarts,
                briskness=engine.player_stats.total_briskness
            )
            # Add unlock notification if this is the first XP
            if was_locked:
                engine.messages.append([
                    (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
                ])

    # Crack Hallucinations (Meth-Head L2): next consumable grants meth = item value + Meth-Head XP
    if getattr(engine, 'crack_hallucinations_active', False):
        engine.crack_hallucinations_active = False
        item_value = get_item_value(item.item_id)
        if item_value > 0:
            p = engine.player
            old_meth = p.meth
            p.meth = min(p.meth + item_value, p.max_meth)
            gained = p.meth - old_meth
            if gained > 0:
                # Award Meth-Head XP equal to meth gained
                adjusted_xp = round(gained * engine.player_stats.xp_multiplier)
                engine.skills.gain_potential_exp(
                    "Meth-Head", adjusted_xp,
                    engine.player_stats.effective_book_smarts,
                    briskness=engine.player_stats.total_briskness
                )
                engine.messages.append([
                    ("Crack Hallucinations! ", (180, 80, 255)),
                    (f"+{gained} meth", (0, 140, 255)),
                    (f" (+{adjusted_xp} Meth-Head XP)", (200, 160, 255)),
                ])

    # Nuclear Research L4 "Isotope Junkie": using a consumable grants +5 radiation (pierces resistance)
    if engine.skills.get("Nuclear Research").level >= 4:
        from combat import add_radiation
        add_radiation(engine, engine.player, 5, pierce_resistance=True)
        engine.messages.append([
            ("Isotope Junkie! ", (120, 220, 80)),
            ("+5 radiation", (160, 255, 120)),
        ])

    if effect.get("consumed", True) and not skip_consume:
        # Use identity search instead of index — apply_effect may have mutated the inventory
        if getattr(item, "charges", None) is not None:
            item.charges -= 1
            if item.charges <= 0:
                for i, x in enumerate(engine.player.inventory):
                    if x is item:
                        engine.player.inventory.pop(i)
                        break
        else:
            item.quantity -= 1
            if item.quantity <= 0:
                for i, x in enumerate(engine.player.inventory):
                    if x is item:
                        engine.player.inventory.pop(i)
                        break


def _use_food(engine, item, food_id):
    """Apply a food item: consume immediately and apply eating effect."""
    food_defn = get_food_def(food_id)
    if not food_defn:
        engine.messages.append(f"Unknown food: {food_id}")
        return

    food_name = food_defn.get("name", "Food")
    eat_length = food_defn.get("eat_length", 10)
    eating_effect_name = food_defn.get("eating_effect_name", f"Eating {food_name}")
    well_fed_effect_name = food_defn.get("well_fed_effect_name", "Well Fed")
    food_effects = list(food_defn.get("effects", []))

    # Prepend prefix adjective to displayed food name and inject prefix effects
    item_prefix = getattr(item, "prefix", None)
    greasy_stacks_per_charge = getattr(item, "greasy_stacks_per_charge", 0)
    if item_prefix:
        pdef = get_food_prefix_def(item_prefix)
        adj = pdef["display_adjective"] if pdef else item_prefix.title()
        food_name = f"{adj} {food_name}"
        if pdef:
            for eff_type in pdef.get("effects", []):
                food_effects.append({"type": eff_type})

    # Check for Quick Eat buff — if active, consume food instantly
    quick_eat = next(
        (e for e in engine.player.status_effects if getattr(e, 'id', '') == 'quick_eat'),
        None,
    )
    if quick_eat:
        engine.player.status_effects.remove(quick_eat)
        engine.messages.append([
            ("[Quick Eat] ", (255, 200, 50)),
            ("You scarf down the ", (150, 200, 150)),
            (item.name, item.color),
            (" instantly!", (150, 200, 150)),
        ])
        # Apply food effects immediately by creating a temporary eating effect and expiring it
        eating = effects.EatingFoodEffect(
            duration=0,
            food_id=food_id,
            food_name=food_name,
            food_effects=food_effects,
            well_fed_effect_name=well_fed_effect_name,
            greasy_stacks_per_charge=greasy_stacks_per_charge,
        )
        eating.expire(engine.player, engine)
        return

    engine.messages.append([
        ("You start eating ", (150, 200, 150)),
        (item.name, item.color),
        ("...", (150, 200, 150)),
    ])

    effects.apply_effect(
        engine.player, engine, "eating_food",
        duration=eat_length,
        food_id=food_id,
        food_name=food_name,
        food_effects=food_effects,
        well_fed_effect_name=well_fed_effect_name,
        greasy_stacks_per_charge=greasy_stacks_per_charge,
        silent=True
    )


# ------------------------------------------------------------------
# Destroy
# ------------------------------------------------------------------

def _handle_examine_input(engine, action):
    from menu_state import MenuState
    action_type = action.get("type")
    if action_type == "close_menu":
        engine.menu_state = MenuState.ITEM_MENU
    return False


def _handle_destroy_confirm_input(engine, action):
    from menu_state import MenuState
    action_type = action.get("type")

    # Left/right arrows move cursor between No (0) and Yes (1)
    if action_type == "move":
        dx = action.get("dx", 0)
        if dx != 0:
            engine.destroy_confirm_cursor = 1 - engine.destroy_confirm_cursor
        return False

    # Y key (select_item index 17 in INVENTORY_KEYS) → confirm yes
    # N key (select_item index 8 in INVENTORY_KEYS) → confirm no
    if action_type == "select_item":
        idx = action.get("index")
        if idx == 17:    # 'y'
            action_type = "confirm_yes"
        elif idx == 8:   # 'n'
            action_type = "confirm_no"

    # Enter or Space confirms based on cursor position
    if action_type in ("confirm_target", "item_use"):
        action_type = "confirm_yes" if engine.destroy_confirm_cursor == 1 else "confirm_no"

    if action_type == "confirm_yes":
        _destroy_item(engine, engine.selected_item_index)
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        engine.destroy_confirm_cursor = 0
    elif action_type in ("confirm_no", "close_menu"):
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        engine.destroy_confirm_cursor = 0
    return False


def _handle_deep_fryer_input(engine, action):
    """Handle input for the deep-fryer food selection menu."""
    from menu_state import MenuState
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        return False

    if action_type == "move":
        dy = action.get("dy", 0)
        if dy != 0 and hasattr(engine, "deep_fryer_items"):
            engine.deep_fryer_cursor = (
                engine.deep_fryer_cursor + dy
            ) % len(engine.deep_fryer_items)
        return False

    if action_type in ("confirm_target", "item_use"):
        _deep_fry_selected(engine)
        return False

    return False


def _destroy_item(engine, index):
    item = engine.player.inventory[index]
    qty = getattr(item, "quantity", 1)
    engine._gain_item_skill_xp("Dismantling", item.item_id)
    engine.destroyed_items.append({"name": item.name, "quantity": qty})
    engine.player.inventory.pop(index)
    engine.messages.append([
        ("Destroyed ", (200, 80, 80)),
        (item.name, item.color),
        (".", (200, 80, 80)),
    ])
    # Dismantling L2: Chop Shop — bonus armor and cash on destroy
    dm_level = engine.skills.get("Dismantling").level
    if dm_level >= 2:
        gained = min(5, engine.player.max_armor - engine.player.armor)
        engine.player.armor += gained
        engine.cash += 20
        engine.messages.append(f"  [Chop Shop] +{gained} armor, +$20 from salvage!")
    # Dismantling L3: Nigga Armor — stack on destroy
    if dm_level >= 3:
        import effects as _eff
        _eff.apply_effect(engine.player, engine, "nigga_armor", stacks=1, silent=True)
        na = next((e for e in engine.player.status_effects if getattr(e, "id", "") == "nigga_armor"), None)
        count = len(na.timers) if na else 1
        engine.messages.append(f"  [Nigga Armor] x{count} (-{count} incoming dmg, 30t)")
    # Ammo Rat L3: Rat Race — dismantling yields ammo (5 light, 3 medium, 1 heavy)
    if engine.skills.get("Ammo Rat").level >= 3:
        _add_item_to_inventory(engine, "light_rounds", quantity=5)
        _add_item_to_inventory(engine, "medium_rounds", quantity=3)
        _add_item_to_inventory(engine, "heavy_rounds", quantity=1)
        engine.messages.append([
            ("Rat Race! ", (220, 200, 120)),
            ("+5 light, +3 medium, +1 heavy rounds", (180, 255, 150)),
        ])


# ------------------------------------------------------------------
# Ring Replacement
# ------------------------------------------------------------------

def _handle_ring_replace_input(engine, action):
    """Handle input for selecting which ring to replace."""
    from menu_state import MenuState
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.pending_ring_item_index = None
        return False

    if action_type == "move":
        # Up/down to move cursor through rings
        dy = action.get("dy", 0)
        engine.ring_replace_cursor = max(0, min(9, engine.ring_replace_cursor + dy))
        return False

    if action_type == "select_ring_slot":
        # Converted from select_action in process_action
        slot = action.get("slot")
        _replace_ring_at_slot(engine, slot)
        engine.menu_state = MenuState.NONE
        engine.pending_ring_item_index = None
        return True

    if action_type == "confirm_target":
        # Enter key to confirm selection
        _replace_ring_at_slot(engine, engine.ring_replace_cursor)
        engine.menu_state = MenuState.NONE
        engine.pending_ring_item_index = None
        return True

    return False


def _replace_ring_at_slot(engine, slot_index: int):
    """Replace the ring at the given slot with the pending ring item."""
    if not (0 <= slot_index < RING_SLOTS):
        return

    if engine.pending_ring_item_index is None:
        return

    # Get the new ring from inventory
    new_ring = engine.player.inventory[engine.pending_ring_item_index]

    # Get the old ring at this slot
    old_ring = engine.rings[slot_index]

    # Equip the new ring (pop from inventory first to avoid index issues after sorting)
    engine.rings[slot_index] = engine.player.inventory.pop(engine.pending_ring_item_index)

    # Return the old ring to inventory and sort
    if old_ring is not None:
        engine.player.inventory.append(old_ring)
        _sort_inventory(engine)
        engine.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (old_ring.name, old_ring.color)])

    _refresh_ring_stat_bonuses(engine)
    engine.messages.append([("Equipped ", _C_MSG_NEUTRAL), (new_ring.name, new_ring.color)])


# ------------------------------------------------------------------
# Crafting / Combine
# ------------------------------------------------------------------

def _is_valid_combine_target(engine, inv_idx):
    """Return True if the item at inv_idx is a valid combine target for selected_item."""
    if inv_idx == engine.selected_item_index:
        return False
    src = engine.player.inventory[engine.selected_item_index]
    cand = engine.player.inventory[inv_idx]
    if find_recipe(src.item_id, cand.item_id):
        return True
    if src.item_id in PREFIX_TOOL_ITEMS and cand.item_id in FOOD_DEFS:
        return getattr(cand, "prefix", None) is None
    if src.item_id in FOOD_DEFS and cand.item_id in PREFIX_TOOL_ITEMS:
        return getattr(src, "prefix", None) is None
    # Nutrient Producer: works on any consumable (category "consumable" or food item)
    if src.item_id == "nutrient_producer" and cand.item_id != "nutrient_producer":
        cand_def = get_item_def(cand.item_id)
        is_consumable = (cand_def and cand_def.get("category") == "consumable") or cand.item_id in FOOD_DEFS
        return is_consumable and cand.item_id != "radbar"
    if cand.item_id == "nutrient_producer" and src.item_id != "nutrient_producer":
        src_def_chk = get_item_def(src.item_id)
        is_consumable = (src_def_chk and src_def_chk.get("category") == "consumable") or src.item_id in FOOD_DEFS
        return is_consumable and src.item_id != "radbar"
    src_def = get_item_def(src.item_id)
    if src_def and (src_def.get("use_effect") or {}).get("type") == "torch_burn":
        return True
    return False


def _get_valid_combine_targets(engine):
    """Return list of inventory indices that are valid combine targets."""
    return [i for i in range(len(engine.player.inventory)) if _is_valid_combine_target(engine, i)]


def _init_combine_cursor(engine):
    """Set combine_target_cursor to the first valid target."""
    targets = _get_valid_combine_targets(engine)
    engine.combine_target_cursor = targets[0] if targets else None


def _handle_combine_input(engine, action):
    from menu_state import MenuState
    action_type = action.get("type")

    if action_type == "close_menu":
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        engine.combine_target_cursor = None
        return False

    # Up/Down — scroll through valid combine targets
    if action_type == "move":
        dy = action.get("dy", 0)
        if dy != 0:
            targets = _get_valid_combine_targets(engine)
            if targets and engine.combine_target_cursor is not None:
                cur_pos = targets.index(engine.combine_target_cursor) if engine.combine_target_cursor in targets else 0
                engine.combine_target_cursor = targets[(cur_pos + dy) % len(targets)]
        return False

    # Enter — confirm target at cursor
    if action_type == "confirm_target":
        if engine.combine_target_cursor is not None:
            result = bool(_try_combine(engine, engine.selected_item_index, engine.combine_target_cursor))
            engine.menu_state = MenuState.NONE
            engine.selected_item_index = None
            engine.combine_target_cursor = None
            return result
        return False

    # Letter keys — still work as direct selection
    if action_type == "select_item":
        target_index = action["index"]
        if target_index == engine.selected_item_index:
            return False
        result = False
        if 0 <= target_index < len(engine.player.inventory):
            result = bool(_try_combine(engine, engine.selected_item_index, target_index))
        engine.menu_state = MenuState.NONE
        engine.selected_item_index = None
        engine.combine_target_cursor = None
        return result

    return False


def _try_combine(engine, index_a, index_b):
    item_a = engine.player.inventory[index_a]
    item_b = engine.player.inventory[index_b]

    # Torch burn path: any torch item + any item → destroy item, gain Pyromania XP
    _TORCH_ITEMS = frozenset(("bic_torch", "xl_bic_torch"))
    torch_item = target_item = None
    if item_a.item_id in _TORCH_ITEMS and item_b.item_id not in _TORCH_ITEMS:
        torch_item, target_item = item_a, item_b
        target_index = index_b
    elif item_b.item_id in _TORCH_ITEMS and item_a.item_id not in _TORCH_ITEMS:
        torch_item, target_item = item_b, item_a
        target_index = index_a

    if torch_item and target_item:
        # Gain Pyromania XP equal to 2x item value, scaled by torch multiplier
        torch_def = get_item_def(torch_item.item_id) or {}
        torch_mult = torch_def.get("torch_xp_mult", 1.0)
        xp_amount = round(get_item_value(target_item.item_id) * 2 * torch_mult)
        adjusted_xp = round(xp_amount * engine.player_stats.xp_multiplier)

        # Check if skill is newly unlocked
        skill = engine.skills.get("Pyromania")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        engine.skills.gain_potential_exp(
            "Pyromania", adjusted_xp,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness
        )

        # Remove the target item
        target_item.quantity -= 1
        if target_item.quantity <= 0:
            engine.player.inventory.pop(target_index)

        engine.messages.append([
            (f"Burned ", (255, 100, 0)), (target_item.name, target_item.color),
            (f" with ", (255, 100, 0)), (torch_item.name, torch_item.color),
            (f". Gained {adjusted_xp} Pyromania XP!", (255, 215, 0)),
        ])

        # Add unlock notification if this is the first XP
        if was_locked:
            engine.messages.append([
                (f"[NEW SKILL UNLOCKED] Pyromania!", (255, 215, 0)),
            ])
        return True

    # Prefix-tool path: fry_daddy (or other PREFIX_TOOL_ITEMS) + food → prefixed food
    tool_item = food_item = None
    if item_a.item_id in PREFIX_TOOL_ITEMS and item_b.item_id in FOOD_DEFS:
        tool_item, food_item = item_a, item_b
    elif item_b.item_id in PREFIX_TOOL_ITEMS and item_a.item_id in FOOD_DEFS:
        tool_item, food_item = item_b, item_a

    if tool_item and food_item:
        if getattr(food_item, "prefix", None) is not None:
            engine.messages.append(f"{food_item.name} already has the '{food_item.prefix}' prefix applied!")
            return
        # Split stack: only prefix one unit
        if food_item.quantity > 1:
            food_item.quantity -= 1
            kwargs = create_item_entity(food_item.item_id, engine.player.x, engine.player.y, strain=food_item.strain)
            new_ent = Entity(**kwargs)
            engine.player.inventory.append(new_ent)
            food_item = new_ent
        # Apply prefix
        prefix_name = PREFIX_TOOL_ITEMS[tool_item.item_id]
        pdef = get_food_prefix_def(prefix_name)
        food_item.prefix = prefix_name
        food_item.charges = pdef["charges"]
        food_item.max_charges = pdef["charges"]
        adj = pdef["display_adjective"]
        base_name = get_item_def(food_item.item_id)["name"]
        food_item.name = f"{adj} {base_name}"
        c = food_item.charges
        engine.messages.append(f"Applied '{prefix_name}' prefix to {food_item.name} ({c}/{c})!")
        # Gain deep-frying XP when a food is fried (greasy prefix from fry_daddy)
        if tool_item.item_id == "fry_daddy":
            engine._gain_deep_frying_xp(food_item.item_id)
        # Deep-Frying L3: Double Batch — 20% chance to keep the food item
        if tool_item.item_id == "fry_daddy" and engine.skills.get("Deep-Frying").level >= 3:
            if random.random() < 0.20:
                refund_kwargs = create_item_entity(food_item.item_id, engine.player.x, engine.player.y)
                refund = Entity(**refund_kwargs)
                engine.player.inventory.append(refund)
                engine.messages.append(f"  [Double Batch] Proc! You kept a {get_item_def(food_item.item_id)['name']}!")
        _sort_inventory(engine)
        return True

    # Nutrient Producer path: consumable → RadBar
    np_item = target_item = target_index = None
    if item_a.item_id == "nutrient_producer":
        np_item, target_item, target_index = item_a, item_b, index_b
    elif item_b.item_id == "nutrient_producer":
        np_item, target_item, target_index = item_b, item_a, index_a

    if np_item and target_item:
        old_name = target_item.name
        # Remove one unit of the consumable
        target_item.quantity -= 1
        if target_item.quantity <= 0:
            engine.player.inventory.pop(target_index)
        # Add a RadBar to inventory
        _add_item_to_inventory(engine, "radbar")
        engine.messages.append([
            ("Nutrient Producer converts ", (120, 220, 80)),
            (old_name, (200, 200, 200)),
            (" into a RadBar!", (120, 220, 80)),
        ])
        _sort_inventory(engine)
        return True

    recipe = find_recipe(item_a.item_id, item_b.item_id)

    if recipe is None:
        engine.messages.append(f"Can't combine {item_a.name} with {item_b.name}")
        return

    # Capture strain before any removals
    result_id = recipe["result"]
    result_strain = get_craft_result_strain(item_a, item_b)

    # Consume 1 from each consumed item's stack (remove when quantity hits 0)
    consumed_ids = recipe["consumed"]
    to_consume = []
    if item_a.item_id in consumed_ids:
        to_consume.append(index_a)
    if item_b.item_id in consumed_ids:
        to_consume.append(index_b)

    for idx in sorted(to_consume, reverse=True):
        item = engine.player.inventory[idx]
        item.quantity -= 1
        if item.quantity <= 0:
            engine.player.inventory.pop(idx)

    # Deduct a charge from pack_of_cones (tool with limited uses)
    for item in (item_a, item_b):
        if item.item_id == "pack_of_cones" and item in engine.player.inventory:
            item.charges = getattr(item, "charges", 0) - 1
            if item.charges <= 0:
                engine.player.inventory.remove(item)
                engine.messages.append("Pack of Cones is empty!")
            else:
                item.name = f"Pack of Cones ({item.charges})"
            break

    # Try to merge result into an existing stack (skip charged items — each is unique)
    if is_stackable(result_id):
        existing = next(
            (i for i in engine.player.inventory
             if i.item_id == result_id and i.strain == result_strain
             and getattr(i, "charges", None) is None),
            None,
        )
        if existing:
            existing.quantity += 1
            display = build_inventory_display_name(existing.item_id, existing.strain, existing.quantity)
            engine.messages.append([
                ("Combined into ", _C_MSG_NEUTRAL),
                (display, existing.color),
                ("!", _C_MSG_NEUTRAL),
            ])
            # Award rolling skill XP for grinding (nug -> kush) or rolling (kush -> joint)
            if result_strain and result_id in ("joint", "kush"):
                is_grinding = result_id == "kush"
                engine._gain_rolling_xp(result_strain, is_grinding=is_grinding)
            # Seeing Double (Rolling level 2): 50% chance to roll an extra joint
            if result_id == "joint" and engine.skills.get("Rolling").level >= 2:
                if random.random() < 0.5:
                    _add_item_to_inventory(engine, "joint", strain=result_strain)
                    engine.messages.append([
                        ("Seeing Double! ", (255, 220, 80)),
                        ("You rolled an extra joint.", _C_MSG_USE),
                    ])
            # Snickelfritz (Rolling level 4): 25% chance to gain a bonus Snickelfritz joint
            if result_id == "joint" and engine.skills.get("Rolling").level >= 4:
                if random.random() < 0.25:
                    _add_item_to_inventory(engine, "joint", strain="Snickelfritz")
                    engine.messages.append([
                        ("Snickelfritz! ", (150, 120, 60)),
                        ("A sketchy bonus joint appeared...", (200, 200, 200)),
                    ])
            # Rollin' Cloud (Rolling level 5): trigger Phat Cloud when rolling a joint
            if result_id == "joint" and engine.skills.get("Rolling").level >= 5:
                _trigger_phat_cloud(engine)
            return True

    kwargs = create_item_entity(result_id, 0, 0, strain=result_strain)
    result_item = Entity(**kwargs)
    engine.player.inventory.append(result_item)
    _sort_inventory(engine)
    engine.messages.append([
        ("Combined into ", _C_MSG_NEUTRAL),
        (result_item.name, result_item.color),
        ("!", _C_MSG_NEUTRAL),
    ])
    # Award rolling skill XP for grinding (nug -> kush) or rolling (kush -> joint)
    if result_strain and result_id in ("joint", "kush"):
        is_grinding = result_id == "kush"
        engine._gain_rolling_xp(result_strain, is_grinding=is_grinding)
    # Seeing Double (Rolling level 2): 50% chance to roll an extra joint
    if result_id == "joint" and engine.skills.get("Rolling").level >= 2:
        if random.random() < 0.5:
            _add_item_to_inventory(engine, "joint", strain=result_strain)
            engine.messages.append([
                ("Seeing Double! ", (255, 220, 80)),
                ("You rolled an extra joint.", _C_MSG_USE),
            ])
    # Snickelfritz (Rolling level 4): 25% chance to gain a bonus Snickelfritz joint
    if result_id == "joint" and engine.skills.get("Rolling").level >= 4:
        if random.random() < 0.25:
            _add_item_to_inventory(engine, "joint", strain="Snickelfritz")
            engine.messages.append([
                ("Snickelfritz! ", (150, 120, 60)),
                ("A sketchy bonus joint appeared...", (200, 200, 200)),
            ])
    # Rollin' Cloud (Rolling level 5): trigger Phat Cloud when rolling a joint
    if result_id == "joint" and engine.skills.get("Rolling").level >= 5:
        _trigger_phat_cloud(engine)
    return True
