"""Test that Jerome's room spawns correctly: Jerome, door, and stairs all present,
Jerome and door are accessible from the player, and stairs are only reachable
through the locked door.
"""

import sys
sys.path.insert(0, ".")

import random
from config import TILE_FLOOR
from engine import GameEngine


def _flood_fill(dungeon, start_x, start_y, impassable=None):
    """BFS flood fill from (start_x, start_y) on floor tiles.
    impassable: optional set of (x,y) tiles to treat as walls.
    Returns set of reachable (x,y) tiles."""
    if impassable is None:
        impassable = set()
    visited = set()
    queue = [(start_x, start_y)]
    visited.add((start_x, start_y))
    while queue:
        cx, cy = queue.pop(0)
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in visited:
                continue
            if not (0 <= nx < dungeon.width and 0 <= ny < dungeon.height):
                continue
            if (nx, ny) in impassable:
                continue
            if dungeon.tiles[ny][nx] != TILE_FLOOR:
                continue
            visited.add((nx, ny))
            queue.append((nx, ny))
    return visited


def _make_floor4(seed):
    """Create a GameEngine and descend to floor 4 (Jerome's floor)."""
    random.seed(seed)
    game = GameEngine()
    for _ in range(3):
        game._descend()
    return game


def test_jerome_room_all_entities_spawn():
    """Jerome, the door, and the meth zone stairs must all spawn on every seed."""
    missing = []
    attempts = 50

    for seed in range(attempts):
        game = _make_floor4(seed)
        dungeon = game.dungeon

        jerome = next((e for e in dungeon.entities
                       if getattr(e, 'enemy_type', '') == 'big_nigga_jerome'), None)
        door = next((e for e in dungeon.entities
                     if getattr(e, 'hazard_type', None) == 'door'), None)
        stairs = next((e for e in dungeon.entities
                       if getattr(e, 'name', '') == 'meth_zone_stairs'), None)

        parts = []
        if jerome is None:
            parts.append("Jerome")
        if door is None:
            parts.append("door")
        if stairs is None:
            parts.append("stairs")
        if parts:
            missing.append(f"seed {seed}: missing {', '.join(parts)}")

    assert not missing, (
        f"Jerome room entities missing on {len(missing)}/{attempts} seeds:\n"
        + "\n".join(missing)
    )


def test_jerome_accessible_from_player():
    """The player must be able to walk to Jerome (he's in the main room)."""
    attempts = 50
    failures = []

    for seed in range(attempts):
        game = _make_floor4(seed)
        dungeon = game.dungeon

        jerome = next((e for e in dungeon.entities
                       if getattr(e, 'enemy_type', '') == 'big_nigga_jerome'), None)
        if jerome is None:
            failures.append(f"seed {seed}: Jerome missing")
            continue

        reachable = _flood_fill(dungeon, game.player.x, game.player.y)
        if (jerome.x, jerome.y) not in reachable:
            failures.append(f"seed {seed}: Jerome at ({jerome.x},{jerome.y}) not reachable")

    assert not failures, (
        f"Jerome not accessible on {len(failures)}/{attempts} seeds:\n"
        + "\n".join(failures)
    )


def test_door_accessible_from_player():
    """The player must be able to walk to the door tile."""
    attempts = 50
    failures = []

    for seed in range(attempts):
        game = _make_floor4(seed)
        dungeon = game.dungeon

        door = next((e for e in dungeon.entities
                     if getattr(e, 'hazard_type', None) == 'door'), None)
        if door is None:
            failures.append(f"seed {seed}: door missing")
            continue

        # Door blocks movement, so check adjacency — player can reach a tile
        # next to the door
        reachable = _flood_fill(dungeon, game.player.x, game.player.y)
        adjacent_to_door = any(
            (door.x + dx, door.y + dy) in reachable
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]
        )
        if not adjacent_to_door:
            failures.append(f"seed {seed}: door at ({door.x},{door.y}) not adjacent-reachable")

    assert not failures, (
        f"Door not accessible on {len(failures)}/{attempts} seeds:\n"
        + "\n".join(failures)
    )


def test_stairs_behind_door():
    """Stairs must NOT be reachable without going through the door."""
    attempts = 50
    failures = []

    for seed in range(attempts):
        game = _make_floor4(seed)
        dungeon = game.dungeon

        door = next((e for e in dungeon.entities
                     if getattr(e, 'hazard_type', None) == 'door'), None)
        stairs = next((e for e in dungeon.entities
                       if getattr(e, 'name', '') == 'meth_zone_stairs'), None)

        if door is None or stairs is None:
            failures.append(f"seed {seed}: door={door is not None}, stairs={stairs is not None}")
            continue

        # Flood fill treating door as impassable
        reachable = _flood_fill(dungeon, game.player.x, game.player.y,
                                impassable={(door.x, door.y)})

        if (stairs.x, stairs.y) in reachable:
            failures.append(
                f"seed {seed}: stairs ({stairs.x},{stairs.y}) reachable "
                f"without door ({door.x},{door.y})"
            )

    assert not failures, (
        f"Stairs reachable without door on {len(failures)}/{attempts} seeds:\n"
        + "\n".join(failures)
    )


def test_stairs_reachable_through_door():
    """Stairs must be reachable when the door is treated as passable floor."""
    attempts = 50
    failures = []

    for seed in range(attempts):
        game = _make_floor4(seed)
        dungeon = game.dungeon

        stairs = next((e for e in dungeon.entities
                       if getattr(e, 'name', '') == 'meth_zone_stairs'), None)

        if stairs is None:
            failures.append(f"seed {seed}: stairs missing")
            continue

        # Flood fill with no impassable set (door is treated as floor)
        reachable = _flood_fill(dungeon, game.player.x, game.player.y)

        if (stairs.x, stairs.y) not in reachable:
            failures.append(
                f"seed {seed}: stairs ({stairs.x},{stairs.y}) not reachable even through door"
            )

    assert not failures, (
        f"Stairs not reachable through door on {len(failures)}/{attempts} seeds:\n"
        + "\n".join(failures)
    )


if __name__ == "__main__":
    test_jerome_room_all_entities_spawn()
    print("[OK] All entities spawn")
    test_jerome_accessible_from_player()
    print("[OK] Jerome accessible")
    test_door_accessible_from_player()
    print("[OK] Door accessible")
    test_stairs_behind_door()
    print("[OK] Stairs behind door")
    test_stairs_reachable_through_door()
    print("[OK] Stairs reachable through door")
    print("\nAll tests passed!")
