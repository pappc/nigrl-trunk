"""
Test the Thug enemy and Mogged debuff mechanic.
"""

from engine import GameEngine
from enemies import create_enemy


def test_thug_spawn():
    """Test that thug can be spawned."""
    thug = create_enemy('thug', 5, 5)
    assert thug.name == "Thug"
    assert thug.char == "T"
    assert 25 <= thug.hp <= 30
    assert thug.power == 5
    assert thug.defense == 1
    assert thug.sight_radius == 6
    print("[OK] Thug spawn")


def test_thug_mogged_effect():
    """Test that Mogged effect is defined correctly."""
    thug = create_enemy('thug', 5, 5)
    assert len(thug.on_hit_effects) == 1
    effect = thug.on_hit_effects[0]
    assert effect["name"] == "Mogged"
    assert effect["kind"] == "mogged"
    assert effect["chance"] == 0.50
    assert effect["duration"] == 10
    print("[OK] Mogged effect configured")


def test_mogged_stacking():
    """Test that Mogged debuff stacks correctly."""
    engine = GameEngine()
    thug = create_enemy('thug', engine.player.x + 1, engine.player.y)
    engine.dungeon.entities.append(thug)

    # First Mogged application
    thug.on_hit_effects[0]["chance"] = 1.0  # Force apply
    engine.handle_monster_attack(thug)

    mogged1 = next(
        (e for e in engine.player.status_effects if e.id == "mogged"),
        None,
    )
    assert mogged1 is not None, "First Mogged should be applied"
    assert mogged1.amount == 1, f"First Mogged stack should be 1, got {mogged1.amount}"
    print(f"[OK] First Mogged applied (stack: {mogged1.amount})")

    # Second Mogged application (should stack)
    engine.handle_monster_attack(thug)

    mogged2 = next(
        (e for e in engine.player.status_effects if e.id == "mogged"),
        None,
    )
    assert mogged2 is not None, "Mogged should still be present"
    assert mogged2.amount == 2, f"Second Mogged stack should be 2, got {mogged2.amount}"
    print(f"[OK] Second Mogged applied, stacked (stack: {mogged2.amount})")

    # Third stack
    engine.handle_monster_attack(thug)
    mogged3 = next(
        (e for e in engine.player.status_effects if e.id == "mogged"),
        None,
    )
    assert mogged3.amount == 3, f"Third Mogged stack should be 3, got {mogged3.amount}"
    print(f"[OK] Mogged can stack unlimited (stack: {mogged3.amount})")


def test_thug_ai_behavior():
    """Test that thug uses wander_ambush AI."""
    from ai import BEHAVIORS

    # Thug uses wander_ambush with 6 tile sight radius
    thug = create_enemy('thug', 5, 5)
    assert thug.ai_type == "wander_ambush"
    assert "wander_ambush" in BEHAVIORS
    print("[OK] Thug uses wander_ambush AI with 6 tile radius")


if __name__ == "__main__":
    try:
        test_thug_spawn()
        test_thug_mogged_effect()
        test_thug_ai_behavior()
        test_mogged_stacking()
        print("\nAll thug tests passed!")
    except AssertionError as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
