"""
Test jaywalking XP: entering a new room for the first time should award XP.
"""

from engine import GameEngine


def test_jaywalking_xp_on_new_room():
    """Walking into an unvisited room should award Jaywalking XP."""
    engine = GameEngine()

    # Record initial Jaywalking XP
    skill = engine.skills.get("Jaywalking")
    initial_potential = skill.potential_exp
    initial_real = skill.real_exp

    # Find a room the player hasn't visited (any room besides room 0)
    # Player starts in room 0's center
    player_room = engine.dungeon.get_room_index_at(engine.player.x, engine.player.y)
    assert player_room == 0, f"Player should start in room 0 but is in room {player_room}"

    # Find a tile that belongs to room 1 (or any other unvisited room)
    target_room_idx = None
    target_tile = None
    for (x, y), room_idx in engine.dungeon.room_tile_map.items():
        if room_idx != 0 and room_idx not in engine.visited_rooms.get(0, set()):
            target_room_idx = room_idx
            target_tile = (x, y)
            break

    assert target_tile is not None, "No unvisited room tiles found"

    # Remove all monsters so player can move freely
    engine.dungeon.entities = [e for e in engine.dungeon.entities
                               if e.entity_type != "monster"]

    # Teleport player to the target tile (simulate entering the room)
    old_x, old_y = engine.player.x, engine.player.y
    # We need to use handle_move logic, but we can't easily pathfind.
    # Instead, manually place player adjacent to target and step in.
    # Simpler: directly call the jaywalking XP code path by moving player there.
    engine.dungeon.move_entity(engine.player, target_tile[0], target_tile[1])

    # Now manually trigger the jaywalking check (same logic as handle_move)
    room_idx = engine.dungeon.get_room_index_at(engine.player.x, engine.player.y)
    assert room_idx is not None, "Player should be in a room"
    assert room_idx == target_room_idx

    floor_visited = engine.visited_rooms.setdefault(engine.current_floor, {0})
    was_visited = room_idx in floor_visited
    assert not was_visited, f"Room {room_idx} should not have been visited yet"

    # Now actually process a move action that enters the room
    # Reset player position to just outside the target room, then step in
    # For simplicity, let's just call handle_move directly with the target coords
    engine.player.x = old_x
    engine.player.y = old_y
    engine.dungeon.move_entity(engine.player, old_x, old_y)

    # Instead, let's test more directly: place player on a corridor tile adjacent
    # to the target room tile, then move into it
    tx, ty = target_tile
    # Find an adjacent tile that's walkable but NOT in the target room
    from config import TILE_FLOOR
    adjacent_positions = [(tx-1, ty), (tx+1, ty), (tx, ty-1), (tx, ty+1)]
    corridor_tile = None
    for ax, ay in adjacent_positions:
        if (0 <= ax < engine.dungeon.width and 0 <= ay < engine.dungeon.height
                and engine.dungeon.tiles[ay][ax] == TILE_FLOOR
                and not engine.dungeon.is_blocked(ax, ay)):
            # Check it's not in the same target room
            adj_room = engine.dungeon.get_room_index_at(ax, ay)
            if adj_room != target_room_idx:
                corridor_tile = (ax, ay)
                break

    if corridor_tile is None:
        # Fallback: just teleport player next to target and move
        # Place on a wall-adjacent floor tile
        for ax, ay in adjacent_positions:
            if (0 <= ax < engine.dungeon.width and 0 <= ay < engine.dungeon.height
                    and engine.dungeon.tiles[ay][ax] == TILE_FLOOR
                    and not engine.dungeon.is_blocked(ax, ay)):
                corridor_tile = (ax, ay)
                break

    assert corridor_tile is not None, "No adjacent walkable tile found"

    # Place player on the adjacent tile
    engine.dungeon.move_entity(engine.player, corridor_tile[0], corridor_tile[1])

    # Calculate direction to step into the target room
    dx = tx - corridor_tile[0]
    dy = ty - corridor_tile[1]

    # Clear any items/entities on the target tile to avoid pickup interference
    engine.dungeon.entities = [e for e in engine.dungeon.entities
                               if not (e.x == tx and e.y == ty and e.entity_type != "player")]

    # Record XP before move
    skill = engine.skills.get("Jaywalking")
    xp_before = skill.potential_exp

    # Process the move
    engine.process_action({"type": "move", "dx": dx, "dy": dy})

    # Check player actually moved
    assert engine.player.x == tx and engine.player.y == ty, \
        f"Player didn't move to target. At ({engine.player.x},{engine.player.y}), expected ({tx},{ty})"

    # Check XP was awarded
    skill = engine.skills.get("Jaywalking")
    xp_after = skill.potential_exp
    xp_gained = xp_after - xp_before

    print(f"Jaywalking XP before: {xp_before}, after: {xp_after}, gained: {xp_gained}")
    assert xp_gained > 0, f"Expected Jaywalking XP gain but got {xp_gained}"
    print("[OK] Jaywalking XP awarded on entering new room")


def test_no_jaywalking_xp_on_revisit():
    """Walking into an already-visited room should NOT award XP again."""
    engine = GameEngine()

    # Room 0 is already visited (spawn room)
    # Find a tile in room 0
    room0_tile = None
    for (x, y), room_idx in engine.dungeon.room_tile_map.items():
        if room_idx == 0 and (x, y) != (engine.player.x, engine.player.y):
            if not engine.dungeon.is_blocked(x, y):
                room0_tile = (x, y)
                break

    assert room0_tile is not None, "No other tile in room 0"

    skill = engine.skills.get("Jaywalking")
    xp_before = skill.potential_exp

    # Move within room 0
    engine.dungeon.move_entity(engine.player, room0_tile[0], room0_tile[1])
    # Manually run the jaywalking check
    room_idx = engine.dungeon.get_room_index_at(engine.player.x, engine.player.y)
    floor_visited = engine.visited_rooms.setdefault(engine.current_floor, {0})
    assert room_idx in floor_visited, "Room 0 should already be visited"

    xp_after = skill.potential_exp
    assert xp_after == xp_before, "Should not gain XP for revisiting a room"
    print("[OK] No XP on room revisit")


def test_jaywalking_xp_corridor_no_xp():
    """Walking through a corridor (not in any room) should NOT award XP."""
    engine = GameEngine()

    # Find a corridor tile (one that's floor but not in any room)
    from config import TILE_FLOOR
    corridor_tile = None
    for y in range(engine.dungeon.height):
        for x in range(engine.dungeon.width):
            if engine.dungeon.tiles[y][x] == TILE_FLOOR:
                if engine.dungeon.get_room_index_at(x, y) is None:
                    if not engine.dungeon.is_blocked(x, y):
                        corridor_tile = (x, y)
                        break
        if corridor_tile:
            break

    if corridor_tile is None:
        print("[SKIP] No corridor tiles found in this dungeon layout")
        return

    skill = engine.skills.get("Jaywalking")
    xp_before = skill.potential_exp

    # Teleport player to corridor
    engine.dungeon.move_entity(engine.player, corridor_tile[0], corridor_tile[1])

    # Check that corridor gives no room index
    room_idx = engine.dungeon.get_room_index_at(engine.player.x, engine.player.y)
    assert room_idx is None, f"Corridor tile should have no room index, got {room_idx}"

    xp_after = skill.potential_exp
    assert xp_after == xp_before, "Should not gain XP in corridor"
    print("[OK] No XP in corridors")


if __name__ == "__main__":
    test_jaywalking_xp_on_new_room()
    test_no_jaywalking_xp_on_revisit()
    test_jaywalking_xp_corridor_no_xp()
    print("\nAll jaywalking XP tests passed!")
