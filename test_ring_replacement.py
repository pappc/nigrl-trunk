#!/usr/bin/env python3
"""
Test ring replacement menu feature.
"""

from engine import GameEngine
from entity import Entity
from items import create_item_entity
from menu_state import MenuState


def test_ring_replacement_menu():
    """Test that ring replacement menu opens when all 5 ring slots are full."""
    engine = GameEngine()

    # Fill all 5 ring slots with rings
    ring_ids = [
        "ring_minor_con_1", "ring_minor_con_2", "ring_minor_con_3", "ring_minor_str_1",
        "ring_minor_str_2"
    ]
    for i, ring_id in enumerate(ring_ids):
        ring_dict = create_item_entity(ring_id, x=0, y=0)
        if ring_dict:
            engine.rings[i] = Entity(**ring_dict)

    # Verify all rings are equipped
    assert all(r is not None for r in engine.rings), "Not all ring slots are filled"
    print(f"[OK] Filled all 5 ring slots")

    # Create a new ring to try to equip
    new_ring_dict = create_item_entity("ring_minor_tol_1", x=0, y=0)
    if new_ring_dict:
        engine.player.inventory.append(Entity(**new_ring_dict))

    # Try to equip the new ring (should open the replacement menu)
    engine._equip_item(len(engine.player.inventory) - 1)

    # Verify the menu opened
    assert engine.menu_state == MenuState.RING_REPLACE, f"Menu state is {engine.menu_state}, expected RING_REPLACE"
    print(f"[OK] Ring replacement menu opened when all slots are full")

    # Verify pending ring is set
    assert engine.pending_ring_item_index is not None, "Pending ring index not set"
    print(f"[OK] Pending ring item index is set")

    # Simulate pressing key '4' to select ring slot 4
    action = {"type": "select_action", "index": 4}
    engine.process_action(action)

    # Verify the old ring is now in inventory
    # and the new ring is equipped at slot 4
    assert engine.rings[4].item_id == "ring_minor_tol_1", f"Ring at slot 4 is {engine.rings[4].item_id}, expected 'ring_minor_tol_1'"
    print(f"[OK] Ring at slot 4 is now equipped")

    # Verify the old ring is in inventory
    old_ring_found = any(r.item_id == "ring_minor_str_2" for r in engine.player.inventory)
    assert old_ring_found, "Old ring not found in inventory"
    print(f"[OK] Old ring is now in inventory")

    # Verify menu is closed
    assert engine.menu_state == MenuState.NONE, f"Menu state is {engine.menu_state}, expected NONE"
    print(f"[OK] Menu closed after selection")


def test_ring_replacement_with_arrow_keys():
    """Test navigating ring replacement menu with arrow keys."""
    engine = GameEngine()

    # Fill all 5 ring slots
    ring_ids = [
        "ring_minor_con_1", "ring_minor_con_2", "ring_minor_con_3", "ring_minor_str_1",
        "ring_minor_str_2"
    ]
    for i, ring_id in enumerate(ring_ids):
        ring_dict = create_item_entity(ring_id, x=0, y=0)
        if ring_dict:
            engine.rings[i] = Entity(**ring_dict)

    # Create a new ring
    new_ring_dict = create_item_entity("ring_minor_tol_1", x=0, y=0)
    if new_ring_dict:
        engine.player.inventory.append(Entity(**new_ring_dict))

    # Open the replacement menu
    engine._equip_item(len(engine.player.inventory) - 1)

    # Verify menu opened and cursor is at 0
    assert engine.menu_state == MenuState.RING_REPLACE
    assert engine.ring_replace_cursor == 0
    print(f"[OK] Ring replacement menu opened with cursor at 0")

    # Move cursor down 3 times
    for _ in range(3):
        action = {"type": "move", "dx": 0, "dy": 1}
        engine.process_action(action)

    # Verify cursor is now at 3
    assert engine.ring_replace_cursor == 3, f"Cursor is at {engine.ring_replace_cursor}, expected 3"
    print(f"[OK] Cursor moved down to position 3")

    # Confirm with Enter key (confirm_target)
    action = {"type": "confirm_target"}
    engine.process_action(action)

    # Verify ring was replaced at slot 3
    assert engine.rings[3].item_id == "ring_minor_tol_1", f"Ring at slot 3 is {engine.rings[3].item_id}, expected 'ring_minor_tol_1'"
    print(f"[OK] Ring replaced at slot 3 using Enter key")

    # Verify menu is closed
    assert engine.menu_state == MenuState.NONE
    print(f"[OK] Menu closed after Enter key confirmation")


if __name__ == "__main__":
    test_ring_replacement_menu()
    print()
    test_ring_replacement_with_arrow_keys()
    print("\nAll ring replacement tests passed!")
