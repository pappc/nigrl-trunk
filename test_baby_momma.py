"""Test baby momma collision and monster blocking mechanics."""

from dungeon import Dungeon
from engine import GameEngine
from enemies import create_enemy


def test_baby_momma_blocks_player():
    """Test that player cannot walk onto baby momma tile without attacking."""
    engine = GameEngine()
    dungeon = engine.dungeon

    # Place player at (5, 5)
    engine.player.x = 5
    engine.player.y = 5

    # Create a baby momma at (6, 5) - to the right of player
    baby_momma = create_enemy("baby_momma", 6, 5)
    dungeon.entities.append(baby_momma)

    assert baby_momma.alive, "Baby momma should start alive"
    assert baby_momma.blocks_movement, "Monster should block movement"
    assert dungeon.is_blocked(6, 5), "Tile with monster should be blocked"

    # Try to move player right onto the baby momma
    initial_hp = baby_momma.hp
    engine.handle_move(1, 0)  # Move right

    # Player should NOT have moved
    assert engine.player.x == 5, "Player should not move onto monster"
    assert engine.player.y == 5, "Player should not move onto monster"

    # Monster should have taken damage (attacked by player)
    assert baby_momma.hp < initial_hp, "Monster should take damage from collision"


def test_all_monsters_block_movement():
    """Test that all monster types have blocks_movement=True."""
    from enemies import MONSTER_REGISTRY

    for enemy_key, tmpl in MONSTER_REGISTRY.items():
        # Create an instance
        monster = create_enemy(enemy_key, 10, 10)
        assert monster.blocks_movement, f"{enemy_key} should have blocks_movement=True"
        assert monster.alive, f"{enemy_key} should start alive"


def test_dead_monster_does_not_block():
    """Test that dead monsters don't block player movement."""
    engine = GameEngine()
    dungeon = engine.dungeon

    # Place player at (5, 5)
    engine.player.x = 5
    engine.player.y = 5

    # Create a baby momma at (6, 5)
    baby_momma = create_enemy("baby_momma", 6, 5)
    dungeon.entities.append(baby_momma)

    # Kill the baby momma
    baby_momma.alive = False

    # Now the tile should not be blocked
    assert not dungeon.is_blocked(6, 5), "Dead monster should not block movement"

    # Player should be able to move through
    engine.handle_move(1, 0)  # Move right
    assert engine.player.x == 6, "Player should move through dead monster"
    assert engine.player.y == 5, "Player should move through dead monster"


if __name__ == "__main__":
    test_baby_momma_blocks_player()
    test_all_monsters_block_movement()
    test_dead_monster_does_not_block()
    print("All tests passed!")
