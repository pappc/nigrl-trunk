"""Test that Jerome's locked door cannot be bypassed.

The back room containing the meth zone stairs must be completely sealed
except through the door tile. No corridor or adjacent room should breach
the walls around the back room.
"""

import sys
sys.path.insert(0, ".")

from engine import GameEngine


def test_jerome_door_seals_back_room():
    """On crack den floor 4 (index 3), the meth zone stairs must only be
    reachable through the locked door tile. Verify by flood-filling from
    the player position and checking that the stairs tile is NOT reachable
    without passing through the door."""
    # Generate many maps to catch the intermittent bug
    failures = 0
    attempts = 50

    for seed in range(attempts):
        import random
        random.seed(seed)

        game = GameEngine()
        # Navigate to floor 4 (index 3) — the Jerome floor
        for _ in range(3):
            game._descend()

        dungeon = game.dungeon

        # Find the door entity
        door = None
        for e in dungeon.entities:
            if getattr(e, 'hazard_type', None) == 'door':
                door = e
                break

        # Find the meth zone stairs
        stairs = None
        for e in dungeon.entities:
            if getattr(e, 'name', '') == 'meth_zone_stairs':
                stairs = e
                break

        if door is None or stairs is None:
            # No door/stairs on this seed — skip
            continue

        # Flood fill from player position, treating the door as impassable
        visited = set()
        queue = [(game.player.x, game.player.y)]
        visited.add((game.player.x, game.player.y))

        while queue:
            cx, cy = queue.pop(0)
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in visited:
                    continue
                if not (0 <= nx < dungeon.width and 0 <= ny < dungeon.height):
                    continue
                # Treat door tile as impassable
                if nx == door.x and ny == door.y:
                    continue
                # Skip walls
                if dungeon.tiles[ny][nx] != 1:  # 1 = TILE_FLOOR
                    continue
                visited.add((nx, ny))
                queue.append((nx, ny))

        # The stairs should NOT be reachable without going through the door
        stairs_reachable = (stairs.x, stairs.y) in visited
        if stairs_reachable:
            failures += 1
            print(f"  FAIL seed={seed}: stairs at ({stairs.x},{stairs.y}) reachable "
                  f"without door at ({door.x},{door.y})")

    print(f"\nResults: {failures}/{attempts} maps had bypass bugs")
    assert failures == 0, (
        f"Jerome's back room was breachable in {failures}/{attempts} generated maps!"
    )


if __name__ == "__main__":
    test_jerome_door_seals_back_room()
    print("All tests passed!")
