"""Test BIC Torch Pyromania skill training."""

from entity import Entity
from items import create_item_entity, get_item_def, get_item_value
from engine import GameEngine
from dungeon import Dungeon
from stats import PlayerStats

def test_bic_torch_burn():
    """Test that BIC Torch burns items and grants Pyromania XP."""
    # Create game
    game = GameEngine()

    # Add BIC Torch to inventory
    torch = Entity(**create_item_entity("bic_torch", 0, 0))
    game.player.inventory.append(torch)

    # Add an item to burn (e.g., a joint worth 15 XP)
    joint = Entity(**create_item_entity("joint", 0, 0, strain="OG Kush"))
    game.player.inventory.append(joint)

    print(f"Initial Pyromania XP: {game.skills.get('Pyromania').potential_exp}")

    # Use BIC Torch (should enter COMBINE_SELECT mode)
    game._use_item(0)  # Index 0 is torch

    assert game.menu_state.name == "COMBINE_SELECT", "Should enter COMBINE_SELECT mode"
    assert game.selected_item_index == 0, "Should store torch index"

    print(f"Menu state: {game.menu_state.name}")
    print(f"Selected item index: {game.selected_item_index}")

    # Now simulate selecting the joint to burn
    game._try_combine(0, 1)  # Torch at index 0, joint at index 1

    # Check that Pyromania XP was gained (joint value is 15, so 30 XP expected at 2x)
    joint_value = get_item_value("joint")
    expected_xp = joint_value * 2 * game.player_stats.xp_multiplier

    print(f"Joint value: {joint_value}")
    print(f"Expected XP: {expected_xp}")
    print(f"Pyromania XP after burn: {game.skills.get('Pyromania').potential_exp}")

    assert game.skills.get("Pyromania").potential_exp > 0, "Should gain Pyromania XP"

    # Check that the joint was removed
    assert len(game.player.inventory) == 1, "Joint should be removed, only torch remains"
    assert game.player.inventory[0].item_id == "bic_torch", "Torch should still be in inventory"

    # Verify messages were added
    print(f"\nMessages ({len(game.messages)}):")
    for msg in game.messages:
        if isinstance(msg, list):
            print(f"  {' '.join([text for text, color in msg])}")
        else:
            print(f"  {msg}")

    print("[PASS] BIC Torch burn test passed!")

if __name__ == "__main__":
    test_bic_torch_burn()
