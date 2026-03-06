"""
Test Big Nigga Jerome boss monster.
"""

from engine import GameEngine
from enemies import create_enemy


def test_jerome_spawn():
    """Test that Jerome can be spawned."""
    jerome = create_enemy('big_nigga_jerome', 5, 5)
    assert jerome.name == "Big Nigga Jerome"
    assert jerome.char == "J"
    assert jerome.hp == 50
    assert jerome.power == 4
    assert jerome.defense == 2
    print("[OK] Jerome spawn")


def test_jerome_knockback_attack():
    """Test Jerome's knockback attack."""
    jerome = create_enemy('big_nigga_jerome', 5, 5)
    assert len(jerome.special_attacks) == 1
    assert jerome.special_attacks[0]["name"] == "Knockback Punch"
    assert jerome.special_attacks[0]["chance"] == 0.25
    assert jerome.special_attacks[0]["damage_mult"] == 1.0
    print("[OK] Jerome knockback attack configured")


def test_jerome_defense_penetration():
    """Test that Jerome's damage penetrates defense."""
    engine = GameEngine()
    jerome = create_enemy('big_nigga_jerome', engine.player.x + 1, engine.player.y)
    engine.dungeon.entities.append(jerome)

    initial_hp = engine.player.hp
    # Disable special attack to test normal attack
    jerome.special_attacks[0]["chance"] = 0.0
    jerome_damage = jerome.power

    engine.handle_monster_attack(jerome)

    damage_taken = initial_hp - engine.player.hp
    assert damage_taken == jerome_damage, f"Jerome should deal {jerome_damage} damage, dealt {damage_taken}"
    print(f"[OK] Jerome damage penetrates defense ({jerome_damage} damage dealt)")


def test_jerome_knockback_mechanics():
    """Test Jerome's knockback push."""
    engine = GameEngine()
    player_initial_x, player_initial_y = engine.player.x, engine.player.y

    # Place Jerome south of player (so knockback pushes north)
    jerome = create_enemy('big_nigga_jerome', player_initial_x, player_initial_y + 1)
    engine.dungeon.entities.append(jerome)

    # Force knockback attack to trigger
    jerome.special_attacks[0]["chance"] = 1.0

    engine.handle_monster_attack(jerome)

    # Player should be pushed one tile away (north in this case)
    assert engine.player.y < player_initial_y, "Player should be knocked back"
    print(f"[OK] Jerome knockback push works (player moved from ({player_initial_x}, {player_initial_y}) to ({engine.player.x}, {engine.player.y}))")


def test_jerome_high_cash_drop():
    """Test Jerome has high cash drop."""
    jerome = create_enemy('big_nigga_jerome', 5, 5)
    assert 20 <= jerome.cash_drop <= 50, f"Jerome cash should be 20-50, got {jerome.cash_drop}"
    print(f"[OK] Jerome high cash drop ({jerome.cash_drop})")


def test_jerome_eat_limit():
    """Test Jerome can only eat twice."""
    from ai import do_ai_turn, prepare_ai_tick

    engine = GameEngine()
    jerome = create_enemy('big_nigga_jerome', 5, 5)
    engine.dungeon.entities.append(jerome)

    # Manually reduce Jerome's HP below 25 to trigger eating
    jerome.hp = 20
    eaten_count = getattr(jerome, "eaten_count", 0)
    assert eaten_count == 0, "Jerome should start with eaten_count=0"

    # Trigger first meal via AI turn
    tick_data = prepare_ai_tick(engine.player, engine.dungeon, [jerome])
    do_ai_turn(jerome, engine.player, engine.dungeon, engine, **tick_data)

    eaten_after_first = getattr(jerome, "eaten_count", 0)
    assert eaten_after_first == 1, f"First meal: eaten_count should be 1, got {eaten_after_first}"

    # Trigger second meal
    jerome.hp = 20  # Reduce again
    do_ai_turn(jerome, engine.player, engine.dungeon, engine, **tick_data)

    eaten_after_second = getattr(jerome, "eaten_count", 0)
    assert eaten_after_second == 2, f"Second meal: eaten_count should be 2, got {eaten_after_second}"

    # Try to trigger third meal (should not increase count)
    jerome.hp = 20  # Reduce again
    do_ai_turn(jerome, engine.player, engine.dungeon, engine, **tick_data)

    eaten_after_third = getattr(jerome, "eaten_count", 0)
    assert eaten_after_third == 2, f"Third attempt: eaten_count should stay 2, got {eaten_after_third}"

    print("[OK] Jerome eat limit (max 2 meals)")


if __name__ == "__main__":
    try:
        test_jerome_spawn()
        test_jerome_knockback_attack()
        test_jerome_defense_penetration()
        test_jerome_knockback_mechanics()
        test_jerome_high_cash_drop()
        test_jerome_eat_limit()
        print("\nAll Jerome tests passed!")
    except AssertionError as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
