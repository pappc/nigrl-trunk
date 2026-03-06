"""
Test game logic without tcod rendering.
"""

from engine import GameEngine
from entity import Entity


def test_game_initialization():
    """Test that game initializes correctly."""
    engine = GameEngine()
    assert engine.player is not None
    assert engine.dungeon is not None
    assert len(engine.dungeon.rooms) > 0
    assert len(engine.dungeon.entities) > 0
    print("[OK] Game initialization")


def test_player_movement():
    """Test player movement and collision."""
    engine = GameEngine()
    initial_pos = (engine.player.x, engine.player.y)

    # Move right
    engine.process_action({"type": "move", "dx": 1, "dy": 0})
    assert engine.player.x == initial_pos[0] + 1 or engine.dungeon.is_blocked(
        initial_pos[0] + 1, initial_pos[1]
    )
    print("[OK] Player movement and collision")


def test_combat():
    """Test combat system."""
    player = Entity(0, 0, "@", (255, 255, 255), name="player", blocks_movement=True, hp=30)
    monster = Entity(1, 1, "M", (150, 0, 0), name="monster", entity_type="monster", blocks_movement=True, hp=15)

    # Player attacks monster
    damage = player.attack(monster)
    assert damage > 0
    assert monster.hp < 15
    print("[OK] Combat system")


def test_item_pickup():
    """Test item pickup mechanics."""
    engine = GameEngine()
    # Create an item at player location
    item = Entity(
        engine.player.x,
        engine.player.y + 1,
        "!",
        (0, 200, 0),
        name="test_item",
        entity_type="item",
    )
    engine.dungeon.entities.append(item)

    # Move to item
    engine.process_action({"type": "move", "dx": 0, "dy": 1})
    # Item should be removed
    assert item not in engine.dungeon.entities
    print("[OK] Item pickup mechanics")


def test_permadeath():
    """Test permadeath system."""
    engine = GameEngine()
    # Create a very strong monster and have it kill the player
    monster = engine.dungeon.entities[1]  # Get first monster
    monster.power = 100  # Make it very strong

    # Have the player attack the monster until the player dies
    for _ in range(10):
        if engine.player.alive:
            # Monster attacks player
            engine.handle_attack(monster, engine.player)
        else:
            break

    assert not engine.player.alive
    assert engine.game_over
    print("[OK] Permadeath system")


if __name__ == "__main__":
    try:
        test_game_initialization()
        test_player_movement()
        test_combat()
        test_item_pickup()
        test_permadeath()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
