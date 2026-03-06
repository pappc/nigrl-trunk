"""
Test the Niglet enemy implementation.
"""

from engine import GameEngine
from enemies import create_enemy


def test_niglet_spawn():
    """Test that niglet can be spawned."""
    niglet = create_enemy('niglet', 5, 5)
    assert niglet.name == "Niglet"
    assert niglet.char == "n"
    assert 10 <= niglet.hp <= 20
    assert 1 <= niglet.power <= 2, f"Niglet power should be 1-2, got {niglet.power}"
    assert niglet.ai_type == "hit_and_run"
    print("[OK] Niglet spawn")


def test_niglet_special_attack():
    """Test that niglet has Pickpocket special attack."""
    niglet = create_enemy('niglet', 5, 5)
    assert len(niglet.special_attacks) == 1
    assert niglet.special_attacks[0]["name"] == "Pickpocket"
    assert niglet.special_attacks[0]["chance"] == 0.85
    assert niglet.special_attacks[0]["damage_mult"] == 0.0
    print("[OK] Niglet special attack")


def test_niglet_pickpocket_mechanic():
    """Test that Pickpocket steals cash from the player."""
    engine = GameEngine()
    engine.cash = 50  # Give player starting cash

    niglet = create_enemy('niglet', engine.player.x + 1, engine.player.y)
    engine.dungeon.entities.append(niglet)

    initial_cash = engine.cash
    initial_niglet_attacked = getattr(niglet, 'has_attacked_player', False)

    # Simulate niglet attacking player
    # Force the Pickpocket special attack to trigger
    niglet.special_attacks[0]["chance"] = 1.0  # Always hit
    engine.handle_monster_attack(niglet)

    # Check that cash was stolen and has_attacked_player flag is set
    assert engine.cash < initial_cash, f"Cash should be stolen (was {initial_cash}, now {engine.cash})"
    assert niglet.has_attacked_player == True, "has_attacked_player should be True"
    stolen = initial_cash - engine.cash
    assert 1 <= stolen <= 30, f"Stolen amount should be 1-30, got {stolen}"
    print(f"[OK] Pickpocket mechanic (stole ${stolen})")


def test_niglet_damage_ignores_defense():
    """Test that niglet's normal damage ignores player defense."""
    engine = GameEngine()
    niglet = create_enemy('niglet', engine.player.x + 1, engine.player.y)
    engine.dungeon.entities.append(niglet)

    initial_hp = engine.player.hp
    niglet.special_attacks[0]["chance"] = 0.0  # Disable Pickpocket to test normal attack
    niglet_damage = niglet.power

    engine.handle_monster_attack(niglet)

    damage_taken = initial_hp - engine.player.hp
    assert damage_taken == niglet_damage, f"Niglet should deal {niglet_damage} damage, dealt {damage_taken}"
    print(f"[OK] Niglet damage ignores defense ({niglet_damage} damage dealt)")


def test_niglet_ai_behavior():
    """Test that niglet uses hit_and_run AI."""
    from ai import get_initial_state, BEHAVIORS

    assert "hit_and_run" in BEHAVIORS
    behavior = BEHAVIORS["hit_and_run"]

    # Verify behavior structure
    assert "initial_state" in behavior
    assert "transitions" in behavior
    assert "actions" in behavior

    niglet = create_enemy('niglet', 5, 5)
    initial_state = get_initial_state(niglet.ai_type)
    assert initial_state.value == "wandering"
    print("[OK] Niglet AI behavior")


if __name__ == "__main__":
    try:
        test_niglet_spawn()
        test_niglet_special_attack()
        test_niglet_ai_behavior()
        test_niglet_damage_ignores_defense()
        test_niglet_pickpocket_mechanic()
        print("\nAll niglet tests passed!")
    except AssertionError as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
