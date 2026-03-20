"""
Test food system: eating mechanics, buffs, and movement prevention.
"""

from engine import GameEngine
from items import create_item_entity
from entity import Entity
import math


def test_food_eating():
    """Test that eating food applies the eating effect."""
    engine = GameEngine()

    # Create a chicken item next to player
    chicken = Entity(
        engine.player.x + 1,
        engine.player.y,
        "f",
        (200, 180, 140),
        name="Chicken",
        entity_type="item",
        item_id="chicken",
        strain=None,
    )
    engine.dungeon.entities.append(chicken)

    # Move to chicken and pick it up
    initial_count = len(engine.player.inventory)
    engine.process_action({"type": "move", "dx": 1, "dy": 0})

    # Chicken should be picked up
    assert len(engine.player.inventory) > initial_count, "Chicken not picked up"
    assert engine.player.inventory[-1].item_id == "chicken"

    print("[OK] Chicken pickup")


def test_eating_effect_applied():
    """Test that using food applies the eating effect."""
    from menu_state import MenuState
    engine = GameEngine()

    # Add chicken to inventory directly
    chicken_entity = Entity(0, 0, "f", (200, 180, 140), name="Chicken", entity_type="item", item_id="chicken")
    engine.player.inventory.append(chicken_entity)

    # Execute the use action directly (simulating menu interaction)
    engine.selected_item_index = 0
    engine._execute_item_action("Eat")

    # Check that eating effect is applied
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    assert len(eating_effects) > 0, "Eating effect not applied"
    assert eating_effects[0].duration == 10, f"Expected duration 10, got {eating_effects[0].duration}"

    print("[OK] Eating effect applied")


def test_movement_prevents_eating():
    """Test that moving while eating wastes food."""
    engine = GameEngine()

    # Add chicken and apply eating effect manually
    chicken_entity = Entity(0, 0, "f", (200, 180, 140), name="Chicken", entity_type="item", item_id="chicken")
    engine.player.inventory.append(chicken_entity)

    # Apply eating effect
    engine.selected_item_index = 0
    engine._execute_item_action("Eat")

    # Verify eating effect exists
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    assert len(eating_effects) > 0
    initial_eating_duration = eating_effects[0].duration

    # First move attempt: warns but doesn't remove
    initial_pos = (engine.player.x, engine.player.y)
    engine.handle_move(1, 0)

    # Should still be at same position (move rejected)
    assert engine.player.x == initial_pos[0], "Player moved while eating!"

    # Eating effect still present after first attempt (warning only)
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    assert len(eating_effects) > 0, "Eating effect should persist after first move (warning)"

    # Second move attempt: wastes food and removes effect
    engine.handle_move(1, 0)

    # Eating effect should now be removed
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    assert len(eating_effects) == 0, "Eating effect should be removed after second move"

    print("[OK] Movement prevents eating")


def test_eating_applies_healing():
    """Test that eating applies healing effects on completion."""
    engine = GameEngine()

    # Damage the player
    engine.player.take_damage(20)
    initial_hp = engine.player.hp
    assert initial_hp < engine.player.max_hp

    # Add chicken and use it
    chicken_entity = Entity(0, 0, "f", (200, 180, 140), name="Chicken", entity_type="item", item_id="chicken")
    engine.player.inventory.append(chicken_entity)
    engine.selected_item_index = 0
    engine._execute_item_action("Eat")

    # Get eating effect
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    eating_effect = eating_effects[0]

    # Manually expire the effect (simulate 10 turns passing)
    eating_effect.duration = 0
    eating_effect.expire(engine.player, engine)

    # Should have healed
    assert engine.player.hp > initial_hp, "Player should have healed after eating"

    print("[OK] Eating applies healing")


def test_well_fed_effect():
    """Test that Well Fed effect is applied after eating."""
    engine = GameEngine()

    # Add chicken and use it
    chicken_entity = Entity(0, 0, "f", (200, 180, 140), name="Chicken", entity_type="item", item_id="chicken")
    engine.player.inventory.append(chicken_entity)
    engine.selected_item_index = 0
    engine._execute_item_action("Eat")

    # Get eating effect
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    eating_effect = eating_effects[0]

    # Expire the eating effect
    eating_effect.duration = 0
    eating_effect.expire(engine.player, engine)

    # Should now have Hot effect with custom display name
    hot_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'hot']
    assert len(hot_effects) > 0, "Hot effect should be applied after eating"

    # Check display name
    hot_effect = hot_effects[0]
    assert hot_effect.display_name == "Well Fed", f"Expected 'Well Fed', got '{hot_effect.display_name}'"

    # Check that it heals per turn
    assert hot_effect.amount > 0, "Hot effect should have positive healing amount"

    print("[OK] Well Fed effect applied with correct display name")


def test_healing_amount_calculation():
    """Test that per-turn healing is calculated correctly (con/5 rounded up)."""
    engine = GameEngine()

    # Get current constitution
    current_con = engine.player_stats.effective_constitution
    expected_heal = math.ceil(current_con / 5)

    # Add chicken and use it
    chicken_entity = Entity(0, 0, "f", (200, 180, 140), name="Chicken", entity_type="item", item_id="chicken")
    engine.player.inventory.append(chicken_entity)
    engine.selected_item_index = 0
    engine._execute_item_action("Eat")

    # Expire eating effect
    eating_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'eating_food']
    eating_effect = eating_effects[0]
    eating_effect.duration = 0
    eating_effect.expire(engine.player, engine)

    # Check hot effect healing amount
    hot_effects = [e for e in engine.player.status_effects if getattr(e, 'id', '') == 'hot']
    assert len(hot_effects) > 0
    hot_effect = hot_effects[0]

    assert hot_effect.amount == expected_heal, f"Expected {expected_heal} per-turn heal, got {hot_effect.amount}"

    print("[OK] Healing amount calculated correctly")


if __name__ == "__main__":
    try:
        test_food_eating()
        test_eating_effect_applied()
        test_movement_prevents_eating()
        test_eating_applies_healing()
        test_well_fed_effect()
        test_healing_amount_calculation()
        print("\n[PASS] All food system tests passed!")
    except AssertionError as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
