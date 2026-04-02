"""
Zone generation and spawning registry.

Each zone provides generate() and spawn() callables. Dungeon delegates
to this registry instead of hardcoding zone-specific branches.
"""

import random
import numpy as np

from config import (
    DUNGEON_WIDTH,
    DUNGEON_HEIGHT,
    TILE_WALL,
    TILE_FLOOR,
    ROOM_MIN_SIZE,
    ROOM_MAX_SIZE,
    MAX_ROOMS,
    get_zone_gen_param,
)
from entity import Entity
from items import create_item_entity, STRAINS, build_item_name
from enemies import create_enemy, get_spawn_table, get_hallway_spawn_table, get_meth_lab_faction_table, MONSTER_REGISTRY  # noqa: F401 — get_hallway_spawn_table used by crack den
from loot import generate_floor_loot


# ===================================================================
# Crack Den
# ===================================================================

_CRACK_DEN_SHAPES = ["rect", "l", "u", "t", "hall", "oct", "cross", "diamond", "cavern", "pillar", "circle"]

# Floor-based generation profiles: ramp from clean/simple (floor 0) to chaotic/complex (floor 3)
_CRACK_DEN_FLOOR_PROFILES = {
    #                max_rooms  wide_chance  dogleg_chance  dressing_chance  shape_weights
    0: {"max_rooms": 18, "wide_chance": 0.00, "dogleg_chance": 0.05, "dressing_chance": 0.30,
        "shape_weights": [8, 3, 3, 2, 5, 2, 1, 1, 1, 1, 1]},
    1: {"max_rooms": 20, "wide_chance": 0.15, "dogleg_chance": 0.10, "dressing_chance": 0.40,
        "shape_weights": [6, 4, 4, 3, 5, 3, 2, 2, 2, 2, 1]},
    2: {"max_rooms": 22, "wide_chance": 0.20, "dogleg_chance": 0.15, "dressing_chance": 0.50,
        "shape_weights": [5, 4, 4, 3, 4, 3, 3, 3, 3, 2, 2]},
    3: {"max_rooms": 23, "wide_chance": 0.25, "dogleg_chance": 0.15, "dressing_chance": 0.60,
        "shape_weights": [4, 5, 5, 4, 3, 4, 3, 3, 4, 3, 2]},
}


def generate_crack_den(dungeon):
    """Place rooms randomly, then connect them all with MST corridors + extra connections."""
    from dungeon import build_mst

    profile = _CRACK_DEN_FLOOR_PROFILES.get(dungeon.floor_num, _CRACK_DEN_FLOOR_PROFILES[1])
    max_rooms = profile["max_rooms"]

    min_rooms = max(8, max_rooms * 2 // 3)  # floor for acceptable room count
    attempts = 0
    max_attempts = max_rooms * 15

    while len(dungeon.rooms) < max_rooms and attempts < max_attempts:
        attempts += 1
        room = _random_crack_den_room(dungeon, shape_weights=profile["shape_weights"])
        if room is None:
            continue
        # After hitting min_rooms, use tighter padding to pack more rooms in
        padding = 1 if len(dungeon.rooms) < min_rooms else 0
        if any(room.intersects(other, padding=padding) for other in dungeon.rooms):
            continue
        room.carve(dungeon)
        dungeon.rooms.append(room)

    # Carve MST corridors (guaranteed connectivity) with corridor variety
    wide_chance = profile["wide_chance"]
    dogleg_chance = profile["dogleg_chance"]

    def _carve_varied_corridor(pt_a, pt_b):
        r = random.random()
        if r < wide_chance:
            dungeon._carve_wide_corridor(pt_a, pt_b, width=2)
        elif r < wide_chance + dogleg_chance:
            dungeon._carve_dogleg_corridor(pt_a, pt_b)
        else:
            dungeon.carve_corridor(pt_a, pt_b)

    for i, j in build_mst(dungeon.rooms):
        _carve_varied_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center())

    # Add extra connections for more interconnected layout
    if len(dungeon.rooms) > 2:
        for _ in range(len(dungeon.rooms) // 3):
            i = random.randint(0, len(dungeon.rooms) - 1)
            j = random.randint(0, len(dungeon.rooms) - 1)
            if i != j:
                _carve_varied_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center())

    # Build room tile map after all corridors are carved
    dungeon._build_room_tile_map()

    # Dress rooms with interior wall features
    _dress_crack_den_rooms(dungeon, profile["dressing_chance"])

    # Sprout closet/alcove rooms off existing rooms
    _sprout_closets(dungeon)

    # Rebuild room tile map (closets added new rooms)
    dungeon._build_room_tile_map()


def _random_crack_den_room(dungeon, shape_weights=None):
    """Pick a random room shape and position for crack den."""
    from dungeon import RectRoom, LRoom, URoom, TRoom, HallRoom, OctRoom, CrossRoom, DiamondRoom, CavernRoom, PillarRoom, CircleRoom

    if shape_weights is None:
        shape_weights = [6, 4, 4, 3, 5, 3, 2, 2, 2, 2, 1]

    shape = random.choices(_CRACK_DEN_SHAPES, weights=shape_weights)[0]

    lo = ROOM_MIN_SIZE
    hi = ROOM_MAX_SIZE

    if shape == "rect":
        w = random.randint(lo, hi)
        h = random.randint(lo, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return RectRoom(x, y, w, h)

    elif shape == "l":
        w = random.randint(lo, hi)
        h = random.randint(lo, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return LRoom(x, y, x + w, y + h)

    elif shape == "u":
        w = random.randint(lo, hi)
        h = random.randint(lo, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return URoom(x, y, x + w, y + h)

    elif shape == "t":
        w = random.randint(lo + 2, hi)
        h = random.randint(lo + 2, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return TRoom(x, y, x + w, y + h)

    elif shape == "hall":
        length = random.randint(18, 32)
        width  = random.randint(3, 5)
        horiz  = random.choice([True, False])
        if horiz:
            x = random.randint(1, dungeon.width - length - 2)
            y = random.randint(1, dungeon.height - width - 2)
        else:
            x = random.randint(1, dungeon.width - width - 2)
            y = random.randint(1, dungeon.height - length - 2)
        return HallRoom(x, y, length, width, horiz)

    elif shape == "oct":
        w = random.randint(lo, hi)
        h = random.randint(lo, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return OctRoom(x, y, w, h)

    elif shape == "cross":
        size = random.randint(lo // 2, hi // 2)
        cx = random.randint(size + 1, dungeon.width - size - 2)
        cy = random.randint(size + 1, dungeon.height - size - 2)
        return CrossRoom(cx, cy, size)

    elif shape == "diamond":
        radius = random.randint(lo // 2, hi // 2)
        cx = random.randint(radius + 1, dungeon.width - radius - 2)
        cy = random.randint(radius + 1, dungeon.height - radius - 2)
        return DiamondRoom(cx, cy, radius)

    elif shape == "cavern":
        size = random.randint(lo // 2, hi // 2)
        cx = random.randint(size + 1, dungeon.width - size - 2)
        cy = random.randint(size + 1, dungeon.height - size - 2)
        return CavernRoom(cx, cy, size)

    elif shape == "pillar":
        w = random.randint(lo + 2, hi)
        h = random.randint(lo + 2, hi)
        x = random.randint(1, dungeon.width - w - 2)
        y = random.randint(1, dungeon.height - h - 2)
        return PillarRoom(x, y, w, h)

    elif shape == "circle":
        radius = random.randint(lo // 2, hi // 2)
        cx = random.randint(radius + 1, dungeon.width - radius - 2)
        cy = random.randint(radius + 1, dungeon.height - radius - 2)
        return CircleRoom(cx, cy, radius)


def _safe_to_wall(dungeon, x, y):
    """Check if converting (x, y) to wall keeps all orthogonal neighbors connected.
    Returns True only if the tile has 3+ orthogonal floor neighbors after the change."""
    if dungeon.tiles[y][x] != TILE_FLOOR:
        return False
    floor_neighbors = 0
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < dungeon.width and 0 <= ny < dungeon.height:
            if dungeon.tiles[ny][nx] == TILE_FLOOR:
                floor_neighbors += 1
    return floor_neighbors >= 3


def _dress_crack_den_rooms(dungeon, dressing_chance):
    """Add interior wall features to Crack Den rooms for visual and tactical variety."""
    for room_idx, room in enumerate(dungeon.rooms):
        if room_idx == 0:
            continue  # skip spawn room
        floor_tiles = room.floor_tiles(dungeon)
        if len(floor_tiles) < 25:
            continue
        if random.random() > dressing_chance:
            continue

        rw = room.x2 - room.x1
        rh = room.y2 - room.y1

        dressing_type = random.choices(
            ["debris", "barricade", "columns", "center_pillar"],
            weights=[5, 4, 3, 2],
        )[0]

        if dressing_type == "debris":
            # 2-4 scattered wall tiles in the room interior
            n_debris = random.randint(2, 4)
            interior = [
                (x, y) for x, y in floor_tiles
                if room.x1 + 2 <= x <= room.x2 - 2 and room.y1 + 2 <= y <= room.y2 - 2
            ]
            random.shuffle(interior)
            placed = 0
            for x, y in interior:
                if placed >= n_debris:
                    break
                if _safe_to_wall(dungeon, x, y):
                    dungeon.tiles[y][x] = TILE_WALL
                    placed += 1

        elif dressing_type == "barricade":
            # L-shaped wall formation near one corner, 2 tiles in from walls
            corners = [
                (room.x1 + 2, room.y1 + 2, [(1, 0), (0, 1)]),   # top-left
                (room.x2 - 2, room.y1 + 2, [(-1, 0), (0, 1)]),  # top-right
                (room.x1 + 2, room.y2 - 2, [(1, 0), (0, -1)]),  # bottom-left
                (room.x2 - 2, room.y2 - 2, [(-1, 0), (0, -1)]), # bottom-right
            ]
            if rw >= 6 and rh >= 6:
                cx, cy, offsets = random.choice(corners)
                if _safe_to_wall(dungeon, cx, cy):
                    dungeon.tiles[cy][cx] = TILE_WALL
                for odx, ody in offsets:
                    nx, ny = cx + odx, cy + ody
                    if 0 <= nx < dungeon.width and 0 <= ny < dungeon.height:
                        if _safe_to_wall(dungeon, nx, ny):
                            dungeon.tiles[ny][nx] = TILE_WALL

        elif dressing_type == "columns":
            # 2-3 wall tiles along one wall, 1 tile out, evenly spaced
            if rw >= 8 and rh >= 6:
                side = random.choice(["top", "bottom", "left", "right"])
                n_cols = random.randint(2, 3)
                if side == "top":
                    step = max(1, (rw - 4) // (n_cols + 1))
                    for i in range(1, n_cols + 1):
                        px = room.x1 + 2 + i * step
                        py = room.y1 + 1
                        if room.x1 < px < room.x2 and _safe_to_wall(dungeon, px, py):
                            dungeon.tiles[py][px] = TILE_WALL
                elif side == "bottom":
                    step = max(1, (rw - 4) // (n_cols + 1))
                    for i in range(1, n_cols + 1):
                        px = room.x1 + 2 + i * step
                        py = room.y2 - 1
                        if room.x1 < px < room.x2 and _safe_to_wall(dungeon, px, py):
                            dungeon.tiles[py][px] = TILE_WALL
                elif side == "left":
                    step = max(1, (rh - 4) // (n_cols + 1))
                    for i in range(1, n_cols + 1):
                        px = room.x1 + 1
                        py = room.y1 + 2 + i * step
                        if room.y1 < py < room.y2 and _safe_to_wall(dungeon, px, py):
                            dungeon.tiles[py][px] = TILE_WALL
                else:  # right
                    step = max(1, (rh - 4) // (n_cols + 1))
                    for i in range(1, n_cols + 1):
                        px = room.x2 - 1
                        py = room.y1 + 2 + i * step
                        if room.y1 < py < room.y2 and _safe_to_wall(dungeon, px, py):
                            dungeon.tiles[py][px] = TILE_WALL

        elif dressing_type == "center_pillar":
            # 1-2 wall tiles near the room center
            cx, cy = room.center()
            if _safe_to_wall(dungeon, cx, cy):
                dungeon.tiles[cy][cx] = TILE_WALL
            if random.random() < 0.5:
                # Add a second pillar adjacent
                odx, ody = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                nx, ny = cx + odx, cy + ody
                if 0 <= nx < dungeon.width and 0 <= ny < dungeon.height:
                    if _safe_to_wall(dungeon, nx, ny):
                        dungeon.tiles[ny][nx] = TILE_WALL


def _sprout_closets(dungeon):
    """Bud small 3x3 or 4x3 closet rooms off existing room walls."""
    from dungeon import RectRoom

    floor_num = getattr(dungeon, "floor_num", 0)
    # Closet count scales with floor
    closet_targets = {0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (2, 4)}
    lo, hi = closet_targets.get(floor_num, (1, 2))
    target = random.randint(lo, hi)
    if target <= 0:
        return

    placed = 0
    candidate_rooms = [i for i in range(1, len(dungeon.rooms))]

    for _ in range(target * 10):  # max attempts
        if placed >= target or not candidate_rooms:
            break

        room_idx = random.choice(candidate_rooms)
        room = dungeon.rooms[room_idx]
        rw = room.x2 - room.x1
        rh = room.y2 - room.y1
        if rw < 5 or rh < 5:
            continue

        side = random.choice(["north", "south", "east", "west"])
        closet_w = random.randint(3, 4)
        closet_h = random.randint(3, 4)

        if side == "north":
            # Attach above the room
            cx = random.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - closet_w))
            cy = room.y1 - closet_h
            door_x = cx + closet_w // 2
            door_y = room.y1
        elif side == "south":
            cx = random.randint(room.x1 + 1, max(room.x1 + 1, room.x2 - closet_w))
            cy = room.y2
            door_x = cx + closet_w // 2
            door_y = room.y2 - 1
        elif side == "west":
            cx = room.x1 - closet_w
            cy = random.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - closet_h))
            door_x = room.x1
            door_y = cy + closet_h // 2
        else:  # east
            cx = room.x2
            cy = random.randint(room.y1 + 1, max(room.y1 + 1, room.y2 - closet_h))
            door_x = room.x2 - 1
            door_y = cy + closet_h // 2

        # Bounds check
        if cx < 1 or cy < 1 or cx + closet_w >= dungeon.width - 1 or cy + closet_h >= dungeon.height - 1:
            continue

        # Check that the closet area is all wall (uncarved space)
        all_wall = True
        for ty in range(cy, cy + closet_h):
            for tx in range(cx, cx + closet_w):
                if dungeon.tiles[ty][tx] != TILE_WALL:
                    all_wall = False
                    break
            if not all_wall:
                break
        if not all_wall:
            continue

        # Check overlap with existing rooms
        closet_room = RectRoom(cx, cy, closet_w, closet_h)
        if any(closet_room.intersects(other) for other in dungeon.rooms):
            continue

        # Carve the closet and its doorway
        closet_room.carve(dungeon)
        if 0 <= door_x < dungeon.width and 0 <= door_y < dungeon.height:
            dungeon.tiles[door_y][door_x] = TILE_FLOOR

        dungeon.rooms.append(closet_room)
        placed += 1


def _spawn_sublevel_stairs(dungeon, sublevel_key: str):
    """Spawn purple stairs leading to a sublevel. Avoids existing stair tiles."""
    stair_positions = frozenset(
        (e.x, e.y) for e in dungeon.entities if getattr(e, "entity_type", None) == "staircase"
    )
    eligible = dungeon.rooms[1:]
    random.shuffle(eligible)
    for room in eligible:
        tiles = room.floor_tiles(dungeon)
        free = [
            (x, y) for x, y in tiles
            if not dungeon.is_blocked(x, y) and (x, y) not in stair_positions
        ]
        if free:
            x, y = random.choice(free)
            stair = Entity(
                x=x, y=y,
                char=">",
                color=(180, 100, 255),
                name="Stairs Down (Haitian Daycare)",
                entity_type="staircase",
                blocks_movement=False,
                reveals_on_sight=True,
            )
            stair.sublevel = sublevel_key
            dungeon.entities.append(stair)
            return


# Per-floor monster target bands (min, max) for Crack Den
_MONSTER_TARGET = {0: (15, 22), 1: (18, 26), 2: (20, 30), 3: (22, 32)}


def spawn_crack_den(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned, floor_event=None):
    """Spawn monsters, items, and cash for the Crack Den zone."""
    dungeon.zone = zone
    dungeon.entities.append(player)

    is_zombie_floor = (floor_event == "stench_of_death")
    monster_min, monster_max = _MONSTER_TARGET.get(floor_num, (18, 26))
    if is_zombie_floor:
        monster_min = int(monster_min * 1.5)
        monster_max = int(monster_max * 1.5)
    floor_monster_count = 0

    # Roll for special rooms and claim rooms before normal spawning
    special_room_indices = set()
    if special_rooms_spawned is not None:
        special_room_indices = _roll_special_rooms(dungeon, floor_num, zone, special_rooms_spawned)

    zone_table = get_spawn_table(zone, floor_num)
    if not zone_table:
        zone_table = []
    enemy_types   = [t[0] for t in zone_table]
    enemy_weights = [t[1] for t in zone_table]

    for room_idx, room in enumerate(dungeon.rooms[1:], start=1):
        if room_idx in special_room_indices:
            continue  # special rooms handle their own spawns
        if floor_monster_count >= monster_max:
            break  # hit ceiling, stop spawning

        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue

        if zone_table:
            room_tile_set = frozenset(floor_tiles)

            # Dynamic monster count: size-scaling + floor bonus + populated/empty gate
            size_max = max(1, len(floor_tiles) // 10)
            floor_bonus = floor_num // 2
            room_max = size_max + floor_bonus

            # 60% populated, 40% empty — fewer but denser rooms
            if random.random() < 0.60 and room_max >= 2:
                options = list(range(2, room_max + 1))
                weights = [max(1, room_max + 1 - i) for i in range(len(options))]
                n_groups = random.choices(options, weights=weights, k=1)[0]
            elif random.random() < 0.60:
                n_groups = 1
            else:
                n_groups = 0

            # Clamp so we don't overshoot the floor ceiling
            n_groups = min(n_groups, monster_max - floor_monster_count)

            dealers_in_room = 0
            # Soft cap on dealers per room: 1 on floor 0, 2 on later floors
            max_dealers = 1 if floor_num == 0 else 2

            for _ in range(n_groups):
                if floor_monster_count >= monster_max:
                    break

                enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
                tmpl = MONSTER_REGISTRY[enemy_type]

                # Enforce dealer cap per room
                if enemy_type == "drug_dealer" and dealers_in_room >= max_dealers:
                    continue

                free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
                if not free:
                    continue
                x, y = random.choice(free)
                monster = create_enemy(enemy_type, x, y)
                monster.spawn_room_tiles = room_tile_set
                dungeon.entities.append(monster)
                floor_monster_count += 1

                if enemy_type == "drug_dealer":
                    dealers_in_room += 1

                # Spawn escorts defined in the template
                for escort_spec in tmpl.spawn_with:
                    escort_type  = escort_spec.type
                    escort_count = random.randint(*escort_spec.count)
                    for _ in range(escort_count):
                        if floor_monster_count >= monster_max:
                            break
                        nearby_free = [
                            (nx, ny) for nx, ny in floor_tiles
                            if abs(nx - x) <= 4 and abs(ny - y) <= 4
                            and not dungeon.is_blocked(nx, ny)
                        ]
                        if nearby_free:
                            ex, ey = random.choice(nearby_free)
                            escort = create_enemy(escort_type, ex, ey)
                            escort.spawn_room_tiles = room_tile_set
                            escort.leader = monster
                            escort.ai_type = "escort"
                            escort.ai_state = None
                            dungeon.entities.append(escort)
                            floor_monster_count += 1

    # ── Top-up: if below monster_min, spawn extras in random rooms ────
    if zone_table and floor_monster_count < monster_min:
        spawnable = [
            (i, r) for i, r in enumerate(dungeon.rooms[1:], start=1)
            if i not in special_room_indices
        ]
        random.shuffle(spawnable)
        for room_idx, room in spawnable:
            if floor_monster_count >= monster_min:
                break
            floor_tiles = room.floor_tiles(dungeon)
            free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
            if not free:
                continue
            x, y = random.choice(free)
            enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
            monster = create_enemy(enemy_type, x, y)
            monster.spawn_room_tiles = frozenset(floor_tiles)
            dungeon.entities.append(monster)
            floor_monster_count += 1

    # ── Stench of Death: guaranteed zombie injection ─────────────────
    if is_zombie_floor:
        zombie_count = random.randint(13, 17)
        spawnable_rooms = [r for r in dungeon.rooms[1:]]
        random.shuffle(spawnable_rooms)
        zombies_placed = 0
        for room in spawnable_rooms * 3:  # cycle rooms to fill quota
            if zombies_placed >= zombie_count:
                break
            tiles = room.floor_tiles(dungeon)
            free = [(tx, ty) for tx, ty in tiles if not dungeon.is_blocked(tx, ty)]
            if not free:
                continue
            x, y = random.choice(free)
            zombie = create_enemy("zombie", x, y)
            zombie.spawn_room_tiles = frozenset(tiles)
            dungeon.entities.append(zombie)
            zombies_placed += 1

    # ── Hallway spawning (zone-specific, respects floor ceiling) ────
    hallway_table = get_hallway_spawn_table(zone, floor_num)
    if hallway_table:
        hallway_tiles = dungeon.get_hallway_tiles()
        if hallway_tiles:
            h_types   = [t[0] for t in hallway_table]
            h_weights = [t[1] for t in hallway_table]

            n_hallway_monsters = max(1, min(8, len(hallway_tiles) // 15))
            n_hallway_monsters = min(n_hallway_monsters, monster_max - floor_monster_count)

            for _ in range(n_hallway_monsters):
                if floor_monster_count >= monster_max:
                    break
                free = [(hx, hy) for hx, hy in hallway_tiles
                        if not dungeon.is_blocked(hx, hy)]
                if not free:
                    break
                hx, hy = random.choice(free)
                h_enemy_type = random.choices(h_types, weights=h_weights, k=1)[0]
                h_monster = create_enemy(h_enemy_type, hx, hy)
                dungeon.entities.append(h_monster)
                floor_monster_count += 1

    # Spawn staircase
    dungeon._spawn_staircase_for_zone(zone, floor_num)

    # Occult event: spawn purple stairs to Haitian Daycare sublevel
    if floor_event == "occult_occupation":
        _spawn_sublevel_stairs(dungeon, "haitian_daycare")

    # Collect staircase positions to exclude from item/cash spawning
    stair_tiles = frozenset(
        (e.x, e.y) for e in dungeon.entities if getattr(e, "entity_type", None) == "staircase"
    )

    # Spawn floor loot via zone-based loot system (round-robin across rooms)
    floor_loot = generate_floor_loot(zone, floor_num, player_skills, player_stats)
    random.shuffle(floor_loot)
    spawnable_rooms = dungeon.rooms[1:]
    if spawnable_rooms:
        for i, (item_id, strain) in enumerate(floor_loot):
            room = spawnable_rooms[i % len(spawnable_rooms)]
            floor_tiles = room.floor_tiles(dungeon)
            if floor_tiles:
                x, y = random.choice(floor_tiles)
                if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles:
                    kwargs = create_item_entity(item_id, x, y, strain=strain)
                    dungeon.entities.append(Entity(**kwargs))

    # Spawn cash piles
    _CASH_AMOUNTS = list(range(1, 16))
    _CASH_WEIGHTS = list(range(15, 0, -1))
    cash_target = random.randint(7, 10)
    cash_total = 0

    for room in dungeon.rooms[1:]:
        if cash_total >= cash_target:
            break
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue
        remaining = cash_target - cash_total
        n_cash = random.randint(0, min(3, remaining))
        for _ in range(n_cash):
            x, y = random.choice(floor_tiles)
            if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles:
                amount = random.choices(_CASH_AMOUNTS, weights=_CASH_WEIGHTS, k=1)[0]
                dungeon.entities.append(Entity(
                    x=x, y=y,
                    char="$",
                    color=(255, 215, 0),
                    name=f"${amount}",
                    entity_type="cash",
                    blocks_movement=False,
                    cash_amount=amount,
                ))
                cash_total += 1

    # ── Vending Machine: one per floor in a random non-special room ──────
    from hazards import create_vending_machine
    from loot import pick_random_consumable
    non_special_rooms = [
        (i, r) for i, r in enumerate(dungeon.rooms[1:], start=1)
        if i not in special_room_indices
    ]
    if non_special_rooms:
        vm_idx, vm_room = random.choice(non_special_rooms)
        vm_tiles = vm_room.floor_tiles(dungeon)
        vm_free = [(x, y) for x, y in vm_tiles
                   if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles]
        if vm_free:
            vx, vy = random.choice(vm_free)
            n_stock = random.randint(5, 10)
            _vm_exclude = {"weed_nug", "kush"}
            stock = []
            attempts = 0
            while len(stock) < n_stock and attempts < n_stock * 3:
                item_id, strain = pick_random_consumable(zone, player_stats)
                attempts += 1
                if item_id in _vm_exclude:
                    continue
                stock.append((item_id, strain))
            vm = create_vending_machine(vx, vy, stock=stock)
            dungeon.entities.append(vm)

# Trap Kitchen bonus: scatter 3 pre-greased foods across non-special rooms
    if getattr(dungeon, "_trap_kitchen_bonus_food", False):
        from loot import ZONE_FOOD_TABLES, _weighted_pick
        from foods import get_food_prefix_def
        from items import get_item_def
        food_table = ZONE_FOOD_TABLES.get(zone, [])
        non_special = [r for i, r in enumerate(dungeon.rooms[1:], start=1)
                       if i not in special_room_indices]
        if food_table and non_special:
            for _ in range(3):
                room = random.choice(non_special)
                ft = room.floor_tiles(dungeon)
                if not ft:
                    continue
                x, y = random.choice(ft)
                if dungeon.is_blocked(x, y) or (x, y) in stair_tiles:
                    continue
                food_id = _weighted_pick(food_table, None, use_skill_weighting=False)
                kwargs = create_item_entity(food_id, x, y)
                ent = Entity(**kwargs)
                # Apply greasy prefix with upgraded stats (3 charges, 3 stacks)
                pdef = get_food_prefix_def("greasy")
                ent.prefix = "greasy"
                ent.charges = 3
                ent.max_charges = 3
                ent.greasy_stacks_per_charge = 3
                adj = pdef["display_adjective"]
                base_name = get_item_def(food_id)["name"]
                ent.name = f"{adj} {base_name}"
                dungeon.entities.append(ent)
        dungeon._trap_kitchen_bonus_food = False


# ------------------------------------------------------------------
# Crack Den special rooms
# ------------------------------------------------------------------

# Each entry: (room_key, eligible_floors, chance)
SPECIAL_ROOM_DEFS = [
    ("niglet_den",   {0, 1, 2}, 0.10),
    ("smoke_lounge", {1, 2, 3}, 0.10),
    ("dive_bar",     {1, 2, 3}, 0.10),
    ("trap_kitchen", {1, 2, 3}, 0.10),
    ("stash_house",  {0, 1, 2, 3}, 0.20),
    ("keisha_room",  {3},       1.00),
    ("jerome_room",  {3},       1.00),
]


def _roll_special_rooms(dungeon, floor_num, zone, special_rooms_spawned):
    """Roll for special rooms on this floor. Returns set of room indices claimed."""
    claimed = set()
    available_indices = [i for i in range(1, len(dungeon.rooms)) if i not in claimed]

    for room_key, eligible_floors, chance in SPECIAL_ROOM_DEFS:
        if room_key in special_rooms_spawned:
            continue
        if floor_num not in eligible_floors:
            continue
        if random.random() > chance:
            continue
        if not available_indices:
            break

        if room_key == "keisha_room":
            # Small-medium room (12–35 tiles) for a packed stripper encounter
            small = [i for i in available_indices
                     if 12 <= len(dungeon.rooms[i].floor_tiles(dungeon)) <= 35]
            if not small:
                small = [i for i in available_indices
                         if len(dungeon.rooms[i].floor_tiles(dungeon)) >= 12]
            if not small:
                continue
            room_idx = random.choice(small)
        elif room_key == "jerome_room":
            # Need >= 20 tiles AND enough vertical space below for door + 2×2 back room
            large = []
            for i in available_indices:
                tiles = dungeon.rooms[i].floor_tiles(dungeon)
                if len(tiles) < 20:
                    continue
                room_max_y = max(y for x, y in tiles)
                # door at max_y+1, back room at max_y+2 to max_y+3, walls at max_y+4
                if room_max_y + 4 >= dungeon.height - 1:
                    continue
                large.append(i)
            if not large:
                continue
            room_idx = max(large, key=lambda i: len(dungeon.rooms[i].floor_tiles(dungeon)))
        else:
            room_idx = random.choice(available_indices)

        room = dungeon.rooms[room_idx]
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles or len(floor_tiles) < 6:
            continue

        if room_key == "niglet_den":
            _spawn_niglet_den(dungeon, room, floor_tiles)
        elif room_key == "smoke_lounge":
            _spawn_smoke_lounge(dungeon, room, floor_tiles, zone)
        elif room_key == "dive_bar":
            _spawn_dive_bar(dungeon, room, floor_tiles, zone)
        elif room_key == "trap_kitchen":
            _spawn_trap_kitchen(dungeon, room, floor_tiles, zone)
        elif room_key == "stash_house":
            _spawn_stash_house(dungeon, room, floor_tiles, zone, floor_num)
        elif room_key == "keisha_room":
            _spawn_keisha_room(dungeon, room, floor_tiles)
        elif room_key == "jerome_room":
            _spawn_jerome_room(dungeon, room, floor_tiles)

        special_rooms_spawned.add(room_key)
        claimed.add(room_idx)
        available_indices = [i for i in available_indices if i not in claimed]

    return claimed


def _spawn_niglet_den(dungeon, room, floor_tiles):
    """Spawn a trap room packed with niglets. No loot — pure punishment."""
    room_tile_set = frozenset(floor_tiles)
    count = random.randint(5, 8)
    for _ in range(count):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        monster = create_enemy("niglet", x, y)
        monster.spawn_room_tiles = room_tile_set
        dungeon.entities.append(monster)


def _spawn_smoke_lounge(dungeon, room, floor_tiles, zone):
    """The Hotbox — 2 Drug Dealers with tweaker escorts + 2 proximity_alarm
    ugly strippers.  Huge weed loot payout."""
    room_tile_set = frozenset(floor_tiles)

    # 2 Drug Dealers, each with 2-3 tweaker escorts
    for _ in range(2):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        dealer = create_enemy("drug_dealer", x, y)
        dealer.spawn_room_tiles = room_tile_set
        dungeon.entities.append(dealer)

        tweaker_count = random.randint(2, 3)
        for _ in range(tweaker_count):
            nearby = [
                (nx, ny) for nx, ny in floor_tiles
                if abs(nx - x) <= 4 and abs(ny - y) <= 4
                and not dungeon.is_blocked(nx, ny)
            ]
            if not nearby:
                break
            ex, ey = random.choice(nearby)
            tweaker = create_enemy("tweaker", ex, ey)
            tweaker.spawn_room_tiles = room_tile_set
            tweaker.leader = dealer
            tweaker.ai_type = "escort"
            tweaker.ai_state = None
            dungeon.entities.append(tweaker)

    # 2 Ugly Strippers with room_combat AI
    for _ in range(2):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        stripper = create_enemy("ugly_stripper", x, y)
        stripper.ai_type = "room_combat"
        stripper.ai_state = None
        dungeon.entities.append(stripper)

    # Guaranteed loot: grinder + pack of cones + 7-8 random weed items
    loot_list = []
    loot_list.append(("grinder", None))
    loot_list.append(("pack_of_cones", None))
    weed_pool = ["kush", "joint", "weed_nug"]
    for _ in range(random.randint(7, 8)):
        weed_id = random.choice(weed_pool)
        loot_list.append((weed_id, random.choice(STRAINS)))

    for item_id, strain in loot_list:
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        kwargs = create_item_entity(item_id, x, y, strain=strain)
        dungeon.entities.append(Entity(**kwargs))


def _spawn_dive_bar(dungeon, room, floor_tiles, zone):
    """The Dive Bar — 5 thugs + 1 proximity_alarm ugly stripper.
    5-7 random alcohol drinks."""
    from loot import DRINKS_SUBTABLE, _weighted_pick
    room_tile_set = frozenset(floor_tiles)

    # 5 Thugs
    for _ in range(5):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        thug = create_enemy("thug", x, y)
        thug.spawn_room_tiles = room_tile_set
        dungeon.entities.append(thug)

    # 1 Ugly Stripper with room_combat AI
    free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
    if free:
        x, y = random.choice(free)
        stripper = create_enemy("ugly_stripper", x, y)
        stripper.ai_type = "room_combat"
        stripper.ai_state = None
        dungeon.entities.append(stripper)

    # 7-8 random drinks from the weighted table
    n_drinks = random.randint(7, 8)
    for _ in range(n_drinks):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        drink_id = _weighted_pick(DRINKS_SUBTABLE, None, use_skill_weighting=False)
        kwargs = create_item_entity(drink_id, x, y)
        dungeon.entities.append(Entity(**kwargs))


def _spawn_trap_kitchen(dungeon, room, floor_tiles, zone):
    """The Trap Kitchen — 6 crack addicts + deep-fryer appliance + 3 random foods.
    When this room spawns, also scatter 3 pre-greased foods across the floor."""
    from hazards import create_deep_fryer
    from loot import ZONE_FOOD_TABLES, _weighted_pick
    room_tile_set = frozenset(floor_tiles)

    # 6 Crack Addicts
    for _ in range(6):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        addict = create_enemy("crack_addict", x, y)
        addict.spawn_room_tiles = room_tile_set
        dungeon.entities.append(addict)

    # Deep-Fryer appliance (center-ish of room)
    free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
    if free:
        min_x = min(x for x, y in floor_tiles)
        max_x = max(x for x, y in floor_tiles)
        min_y = min(y for x, y in floor_tiles)
        max_y = max(y for x, y in floor_tiles)
        cx, cy = (min_x + max_x) // 2, (min_y + max_y) // 2
        free.sort(key=lambda t: abs(t[0] - cx) + abs(t[1] - cy))
        fx, fy = free[0]
        dungeon.entities.append(create_deep_fryer(fx, fy))

    # 3 random foods in the room
    food_table = ZONE_FOOD_TABLES.get(zone, [])
    if food_table:
        for _ in range(3):
            free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            food_id = _weighted_pick(food_table, None, use_skill_weighting=False)
            kwargs = create_item_entity(food_id, x, y)
            dungeon.entities.append(Entity(**kwargs))

    # Mark that greasy bonus food should be scattered across the floor
    dungeon._trap_kitchen_bonus_food = True


def _spawn_stash_house(dungeon, room, floor_tiles, zone, floor_num):
    """The Stash House — cramped room packed with 8-10 enemies guarding a random
    unique item from Unique Table A. High risk, high reward."""
    from items import UNIQUE_TABLE_A, create_item_entity
    room_tile_set = frozenset(floor_tiles)

    # 8-10 enemies from the floor's spawn table
    zone_table = get_spawn_table(zone, floor_num)
    if zone_table:
        enemy_types   = [t[0] for t in zone_table]
        enemy_weights = [t[1] for t in zone_table]
        n_enemies = random.randint(8, 10)
        for _ in range(n_enemies):
            free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
            monster = create_enemy(enemy_type, x, y)
            monster.spawn_room_tiles = room_tile_set
            dungeon.entities.append(monster)

    # One random unique item from Table A — placed at the far end from the entrance
    if UNIQUE_TABLE_A:
        item_id = random.choice(UNIQUE_TABLE_A)
        # Find entrance: room floor tile adjacent to a corridor (non-room floor tile)
        entrance = None
        for tx, ty in floor_tiles:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = tx + dx, ty + dy
                if (nx, ny) not in room_tile_set and 0 <= nx < dungeon.width and 0 <= ny < dungeon.height:
                    if dungeon.tiles[ny][nx] == TILE_FLOOR:
                        entrance = (tx, ty)
                        break
            if entrance:
                break
        # Place item at tile farthest from entrance
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if free:
            if entrance:
                ex, ey = entrance
                free.sort(key=lambda t: -(abs(t[0] - ex) + abs(t[1] - ey)))
            x, y = free[0]
            kwargs = create_item_entity(item_id, x, y)
            dungeon.entities.append(Entity(**kwargs))


def _spawn_keisha_room(dungeon, room, floor_tiles):
    """Spawn Keisha's room: 6 ugly strippers with Keisha in the back."""
    room_tile_set = frozenset(floor_tiles)

    max_y = max(y for x, y in floor_tiles)

    # Keisha in the back of the room (highest y rows)
    back_tiles = [(x, y) for x, y in floor_tiles if y >= max_y - 1]
    if not back_tiles:
        back_tiles = list(floor_tiles)

    free = [(x, y) for x, y in back_tiles if not dungeon.is_blocked(x, y)]
    if not free:
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
    if free:
        kx, ky = random.choice(free)
        keisha = create_enemy("keisha", kx, ky)
        keisha.spawn_room_tiles = room_tile_set
        dungeon.entities.append(keisha)

    # 6 ugly strippers filling the room
    for _ in range(6):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        stripper = create_enemy("ugly_stripper", x, y)
        stripper.spawn_room_tiles = room_tile_set
        dungeon.entities.append(stripper)


def _spawn_jerome_room(dungeon, room, floor_tiles):
    """Spawn Jerome's guarded chamber on floor 4."""
    room_tile_set = frozenset(floor_tiles)

    min_x = min(x for x, y in floor_tiles)
    max_x = max(x for x, y in floor_tiles)
    min_y = min(y for x, y in floor_tiles)
    max_y = max(y for x, y in floor_tiles)
    center_x = (min_x + max_x) // 2
    mid_y    = (min_y + max_y) // 2

    # ── Door entity + 2×2 back room ──────────────────────────────────
    # Door goes directly below a floor tile on the room's bottom row.
    # center_x may not be a floor tile on max_y for non-rectangular rooms,
    # so scan outward from center to find a valid position.
    door_x = center_x
    for candidate_x in [center_x, center_x - 1, center_x + 1,
                         center_x - 2, center_x + 2,
                         center_x - 3, center_x + 3]:
        if (candidate_x, max_y) in room_tile_set:
            door_x = candidate_x
            break
    door_y = max_y + 1

    if 0 < door_y < dungeon.height - 3:
        dungeon.tiles[door_y][door_x] = TILE_FLOOR
        door_entity = Entity(
            x=door_x, y=door_y,
            char='+',
            color=(139, 90, 43),
            name="Door",
            entity_type="hazard",
            hazard_type="door",
            blocks_movement=True,
            blocks_fov=True,
        )
        dungeon.entities.append(door_entity)

        room_left  = door_x - 1
        room_right = door_x
        room_top   = door_y + 1
        room_bot   = door_y + 2
        back_room_tiles = []

        # Wall off the border around the back room.  Skip the door tile
        # and the tile directly above it (the room-side entry point).
        above_door = (door_x, door_y - 1)
        for ry in range(room_top - 1, room_bot + 2):
            for rx in range(room_left - 1, room_right + 2):
                if (rx == door_x and ry == door_y):
                    continue  # don't overwrite the door tile
                if (rx, ry) == above_door:
                    continue  # preserve the room-side entry
                is_interior = (room_left <= rx <= room_right
                               and room_top <= ry <= room_bot)
                if not is_interior:
                    if 0 < rx < dungeon.width - 1 and 0 < ry < dungeon.height - 1:
                        dungeon.tiles[ry][rx] = TILE_WALL

        # Ensure the tile above the door is floor (room entry point)
        if 0 < above_door[0] < dungeon.width - 1 and 0 < above_door[1] < dungeon.height - 1:
            dungeon.tiles[above_door[1]][above_door[0]] = TILE_FLOOR

        for ry in range(room_top, room_bot + 1):
            for rx in range(room_left, room_right + 1):
                if 0 < rx < dungeon.width - 1 and 0 < ry < dungeon.height - 1:
                    dungeon.tiles[ry][rx] = TILE_FLOOR
                    back_room_tiles.append((rx, ry))

        if back_room_tiles:
            sx, sy = random.choice(back_room_tiles)
            stairs = Entity(
                x=sx, y=sy,
                char='>',
                color=(255, 255, 255),
                name="meth_zone_stairs",
                entity_type="staircase",
                blocks_movement=False,
                reveals_on_sight=True,
            )
            dungeon.entities.append(stairs)

        # Ensure the Jerome room is still connected to the rest of the map.
        # The back room walling can seal the only corridor into the room.
        # Fix: find the main connected component (from room 0) and if the
        # entry tile above the door is disconnected, carve an L-shaped
        # corridor from the entry to the nearest connected floor tile.
        # The corridor stays at or above door_y to avoid breaching the
        # sealed back room.
        entry_x, entry_y = door_x, door_y - 1
        r0 = dungeon.rooms[0]
        r0_tiles = r0.floor_tiles(dungeon)
        if r0_tiles:
            start = r0_tiles[0]
            connected = set()
            _q = [start]
            connected.add(start)
            while _q:
                _cx, _cy = _q.pop()
                for _dx, _dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    _nx, _ny = _cx + _dx, _cy + _dy
                    if (_nx, _ny) in connected:
                        continue
                    if not (0 <= _nx < dungeon.width and 0 <= _ny < dungeon.height):
                        continue
                    if dungeon.tiles[_ny][_nx] != TILE_FLOOR:
                        continue
                    connected.add((_nx, _ny))
                    _q.append((_nx, _ny))
            if (entry_x, entry_y) not in connected and connected:
                # Find nearest connected tile that is above or at door_y
                best_dist = 999
                best_conn = None
                for ct in connected:
                    if ct[1] > door_y:
                        continue  # skip tiles below door to avoid breaching back room
                    d = abs(entry_x - ct[0]) + abs(entry_y - ct[1])
                    if d < best_dist:
                        best_dist = d
                        best_conn = ct
                if best_conn is None:
                    # Fallback: use any connected tile
                    for ct in connected:
                        d = abs(entry_x - ct[0]) + abs(entry_y - ct[1])
                        if d < best_dist:
                            best_dist = d
                            best_conn = ct
                if best_conn:
                    # Carve L-shaped corridor: horizontal from entry, then vertical
                    cx, cy = best_conn
                    # Horizontal leg at entry_y
                    step_x = 1 if cx >= entry_x else -1
                    x = entry_x
                    while x != cx:
                        x += step_x
                        if 0 < x < dungeon.width - 1 and 0 < entry_y < dungeon.height - 1:
                            dungeon.tiles[entry_y][x] = TILE_FLOOR
                    # Vertical leg at cx
                    step_y = 1 if cy >= entry_y else -1
                    y = entry_y
                    while y != cy:
                        y += step_y
                        if 0 < cx < dungeon.width - 1 and 0 < y < dungeon.height - 1:
                            dungeon.tiles[y][cx] = TILE_FLOOR

    # ── Jerome: back row, directly above the door ────
    jerome_y = max_y
    jerome_x = door_x  # prefer door_x so he's on the connected path
    for candidate_x in [door_x, door_x - 1, door_x + 1,
                         center_x, center_x - 1, center_x + 1]:
        if (candidate_x, jerome_y) in room_tile_set and \
           not dungeon.is_blocked(candidate_x, jerome_y):
            jerome_x = candidate_x
            break
    jerome = create_enemy("big_nigga_jerome", jerome_x, jerome_y)
    jerome.spawn_room_tiles = room_tile_set
    dungeon.entities.append(jerome)

    # ── Front group: 2 thugs + 2 drug dealers (each with tweakers) ──
    front_tiles = [(x, y) for x, y in floor_tiles if y <= mid_y]
    if not front_tiles:
        front_tiles = floor_tiles

    for _ in range(2):
        free = [(x, y) for x, y in front_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        thug = create_enemy("thug", x, y)
        thug.spawn_room_tiles = room_tile_set
        dungeon.entities.append(thug)

    for _ in range(2):
        free = [(x, y) for x, y in front_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        dealer = create_enemy("drug_dealer", x, y)
        dealer.spawn_room_tiles = room_tile_set
        dungeon.entities.append(dealer)

        tweaker_count = random.randint(1, 3)
        for _ in range(tweaker_count):
            nearby = [
                (nx, ny) for nx, ny in floor_tiles
                if abs(nx - x) <= 4 and abs(ny - y) <= 4
                and not dungeon.is_blocked(nx, ny)
            ]
            if not nearby:
                break
            ex, ey = random.choice(nearby)
            tweaker = create_enemy("tweaker", ex, ey)
            tweaker.spawn_room_tiles = room_tile_set
            tweaker.leader   = dealer
            tweaker.ai_type  = "escort"
            tweaker.ai_state = None
            dungeon.entities.append(tweaker)


# ===================================================================
# Meth Lab
# ===================================================================

def generate_meth_lab(dungeon):
    """Generate a meth lab floor: center start room, 4 corner anchor rooms,
    remaining rooms fill the gaps.  All corridors are 2 tiles wide.
    Tables are placed inside rooms after carving."""
    from dungeon import build_mst, RectRoom

    # Pull generation params from config registry
    rm_min = get_zone_gen_param("meth_lab", "room_min")
    rm_max = get_zone_gen_param("meth_lab", "room_max")
    max_rooms = get_zone_gen_param("meth_lab", "max_rooms")
    corr_w = get_zone_gen_param("meth_lab", "corridor_width")

    margin = 2

    # --- 1. Center start room (room index 0 — player spawns here, small + safe) ---
    cx, cy = dungeon.width // 2, dungeon.height // 2
    w = random.randint(4, 6)
    h = random.randint(4, 6)
    x = cx - w // 2
    y = cy - h // 2
    center_room = RectRoom(x, y, w, h)
    center_room.carve(dungeon)
    dungeon.rooms.append(center_room)

    # --- 2. Four corner anchor rooms ---
    corner_zones = [
        (margin, dungeon.width // 3,              margin, dungeon.height // 3),
        (dungeon.width * 2 // 3, dungeon.width - margin, margin, dungeon.height // 3),
        (margin, dungeon.width // 3,              dungeon.height * 2 // 3, dungeon.height - margin),
        (dungeon.width * 2 // 3, dungeon.width - margin, dungeon.height * 2 // 3, dungeon.height - margin),
    ]

    for x_lo, x_hi, y_lo, y_hi in corner_zones:
        placed = False
        for _ in range(30):
            w = random.randint(rm_min, rm_max)
            h = random.randint(rm_min, rm_max)
            max_x = min(x_hi, dungeon.width - w - margin)
            max_y = min(y_hi, dungeon.height - h - margin)
            min_x = max(x_lo, margin)
            min_y = max(y_lo, margin)
            if min_x > max_x or min_y > max_y:
                continue
            rx = random.randint(min_x, max_x)
            ry = random.randint(min_y, max_y)
            room = RectRoom(rx, ry, w, h)
            if any(room.intersects(other) for other in dungeon.rooms):
                continue
            room.carve(dungeon)
            dungeon.rooms.append(room)
            placed = True
            break
        if not placed:
            w = rm_min
            h = rm_min
            max_x = min(x_hi, dungeon.width - w - margin)
            max_y = min(y_hi, dungeon.height - h - margin)
            min_x = max(x_lo, margin)
            min_y = max(y_lo, margin)
            if min_x <= max_x and min_y <= max_y:
                rx = random.randint(min_x, max_x)
                ry = random.randint(min_y, max_y)
                room = RectRoom(rx, ry, w, h)
                if not any(room.intersects(other) for other in dungeon.rooms):
                    room.carve(dungeon)
                    dungeon.rooms.append(room)

    # --- 3. Fill remaining rooms ---
    attempts = 0
    max_attempts = max_rooms * 6
    while len(dungeon.rooms) < max_rooms and attempts < max_attempts:
        attempts += 1
        w = random.randint(rm_min, rm_max)
        h = random.randint(rm_min, rm_max)
        rx = random.randint(margin, dungeon.width - w - margin)
        ry = random.randint(margin, dungeon.height - h - margin)
        room = RectRoom(rx, ry, w, h)
        if any(room.intersects(other) for other in dungeon.rooms):
            continue
        room.carve(dungeon)
        dungeon.rooms.append(room)

    # --- 4. Connect rooms with wide corridors ---
    for i, j in build_mst(dungeon.rooms):
        dungeon._carve_wide_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center(), corr_w)

    # Extra connections for loops
    if len(dungeon.rooms) > 2:
        for _ in range(len(dungeon.rooms) // 3):
            i = random.randint(0, len(dungeon.rooms) - 1)
            j = random.randint(0, len(dungeon.rooms) - 1)
            if i != j:
                dungeon._carve_wide_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center(), corr_w)

    # --- 5. Place tables inside rooms ---
    for room_idx, room in enumerate(dungeon.rooms):
        dungeon._place_tables(room)

    # Build room tile map
    dungeon._build_room_tile_map()


def spawn_meth_lab(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned, floor_event=None):
    """Spawn entities for a Meth Lab floor."""
    dungeon.zone = zone
    dungeon.entities.append(player)
    dungeon._spawn_staircase_for_zone(zone, floor_num)

    # Assign each room a faction
    dungeon.room_factions = {}
    dungeon.room_factions[0] = "start"  # Room 0 — no monsters
    for idx in range(1, len(dungeon.rooms)):
        dungeon.room_factions[idx] = random.choices(
            ["aldor", "scryer", "neutral"], weights=[1, 1, 2]
        )[0]

    # ── Room monster spawning ──────────────────────────────────────────
    for room_idx, room in enumerate(dungeon.rooms[1:], start=1):
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue

        faction = dungeon.room_factions[room_idx]
        room_tile_set = frozenset(floor_tiles)

        # Population roll: 70% high-pop, 30% low-pop
        if random.random() < 0.70:
            n_monsters = max(6, min(20, len(floor_tiles) // 15))
        else:
            n_monsters = random.randint(2, 5)

        for _ in range(n_monsters):
            # Pick spawn table: faction rooms 67% faction / 33% neutral
            if faction in ("scryer", "aldor"):
                if random.random() < 0.67:
                    table = get_meth_lab_faction_table(faction, floor_num)
                else:
                    table = get_meth_lab_faction_table("neutral", floor_num)
            else:
                table = get_meth_lab_faction_table("neutral", floor_num)

            if not table:
                continue

            enemy_types   = [t[0] for t in table]
            enemy_weights = [t[1] for t in table]
            enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
            tmpl = MONSTER_REGISTRY[enemy_type]

            free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
            if not free:
                break
            x, y = random.choice(free)
            monster = create_enemy(enemy_type, x, y)
            monster.spawn_room_tiles = room_tile_set
            dungeon.entities.append(monster)

            # Spawn escorts defined in the template
            for escort_spec in tmpl.spawn_with:
                escort_type  = escort_spec.type
                escort_count = random.randint(*escort_spec.count)
                for _ in range(escort_count):
                    nearby_free = [
                        (nx, ny) for nx, ny in floor_tiles
                        if abs(nx - x) <= 4 and abs(ny - y) <= 4
                        and not dungeon.is_blocked(nx, ny)
                    ]
                    if nearby_free:
                        ex, ey = random.choice(nearby_free)
                        escort = create_enemy(escort_type, ex, ey)
                        escort.spawn_room_tiles = room_tile_set
                        escort.leader = monster
                        escort.ai_type = "escort"
                        escort.ai_state = None
                        dungeon.entities.append(escort)

    # ── Falcon hallway spawning (only mobs in meth lab hallways) ─────
    _spawn_hallway_falcons(dungeon, floor_num)

    # Collect staircase positions to exclude from item/cash spawning
    stair_tiles = frozenset(
        (e.x, e.y) for e in dungeon.entities if getattr(e, "entity_type", None) == "staircase"
    )

    # Spawn floor loot via zone-based loot system (round-robin across rooms)
    floor_loot = generate_floor_loot(zone, floor_num, player_skills, player_stats)
    random.shuffle(floor_loot)
    spawnable_rooms = dungeon.rooms[1:]
    if spawnable_rooms:
        for i, (item_id, strain) in enumerate(floor_loot):
            room = spawnable_rooms[i % len(spawnable_rooms)]
            floor_tiles = room.floor_tiles(dungeon)
            if floor_tiles:
                x, y = random.choice(floor_tiles)
                if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles:
                    kwargs = create_item_entity(item_id, x, y, strain=strain)
                    dungeon.entities.append(Entity(**kwargs))

    # Spawn ammo piles (5 per floor, spread across rooms)
    _AMMO_TYPES = [
        ("light_rounds",  15, 30),
        ("medium_rounds", 10, 20),
        ("heavy_rounds",   3,  5),
    ]
    ammo_target = 5
    ammo_total = 0
    ammo_rooms = dungeon.rooms[1:]
    random.shuffle(ammo_rooms)
    for room in ammo_rooms:
        if ammo_total >= ammo_target:
            break
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue
        x, y = random.choice(floor_tiles)
        if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles:
            ammo_id, lo, hi = random.choice(_AMMO_TYPES)
            qty = random.randint(lo, hi)
            kwargs = create_item_entity(ammo_id, x, y)
            kwargs["quantity"] = qty
            dungeon.entities.append(Entity(**kwargs))
            ammo_total += 1

    # Spawn cash piles (4x bigger stacks than crack den)
    _CASH_AMOUNTS = list(range(4, 61))  # 4-60 per pile
    _CASH_WEIGHTS = list(range(len(_CASH_AMOUNTS), 0, -1))
    cash_target = random.randint(7, 10)
    cash_total = 0

    for room in dungeon.rooms[1:]:
        if cash_total >= cash_target:
            break
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue
        remaining = cash_target - cash_total
        n_cash = random.randint(0, min(3, remaining))
        for _ in range(n_cash):
            x, y = random.choice(floor_tiles)
            if not dungeon.is_blocked(x, y) and (x, y) not in stair_tiles:
                amount = random.choices(_CASH_AMOUNTS, weights=_CASH_WEIGHTS, k=1)[0]
                dungeon.entities.append(Entity(
                    x=x, y=y,
                    char="$",
                    color=(255, 215, 0),
                    name=f"${amount}",
                    entity_type="cash",
                    blocks_movement=False,
                    cash_amount=amount,
                ))
                cash_total += 1


def _spawn_hallway_falcons(dungeon, floor_num):
    """Spawn faction falcons in hallway segments adjacent to faction rooms.

    1. Flood-fill hallway tiles into connected segments
    2. For each segment, find adjacent rooms and their factions
    3. 50% chance to spawn a falcon with the appropriate faction
    """
    hallway_tiles = dungeon.get_hallway_tiles()
    if not hallway_tiles:
        return

    hallway_set = set(map(tuple, hallway_tiles))
    visited = set()
    segments = []

    # Flood-fill hallway tiles into connected segments
    for tile in hallway_tiles:
        tile = tuple(tile)
        if tile in visited:
            continue
        segment = []
        stack = [tile]
        while stack:
            t = stack.pop()
            if t in visited or t not in hallway_set:
                continue
            visited.add(t)
            segment.append(t)
            x, y = t
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                neighbor = (x + dx, y + dy)
                if neighbor in hallway_set and neighbor not in visited:
                    stack.append(neighbor)
        if segment:
            segments.append(segment)

    room_factions = getattr(dungeon, "room_factions", {})

    for segment in segments:
        # Find adjacent rooms by checking neighbors of each hallway tile
        adjacent_room_indices = set()
        for x, y in segment:
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                room_idx = dungeon.room_tile_map.get((x + dx, y + dy))
                if room_idx is not None:
                    adjacent_room_indices.add(room_idx)

        # Collect factions of adjacent rooms (only scryer/aldor, not start/neutral)
        adjacent_factions = set()
        for ri in adjacent_room_indices:
            f = room_factions.get(ri, "")
            if f in ("scryer", "aldor"):
                adjacent_factions.add(f)

        if not adjacent_factions:
            continue

        # 50% chance to spawn a falcon
        if random.random() > 0.50:
            continue

        # Pick faction: if both present, 50/50; if one, use that
        falcon_faction = random.choice(sorted(adjacent_factions))
        falcon_type = f"{falcon_faction}_falcon"

        free = [(fx, fy) for fx, fy in segment if not dungeon.is_blocked(fx, fy)]
        if free:
            fx, fy = random.choice(free)
            falcon = create_enemy(falcon_type, fx, fy)
            dungeon.entities.append(falcon)


# ===================================================================
# Tyrone's Penthouse
# ===================================================================

def generate_penthouse(dungeon):
    """Build the fixed Tyrone's Penthouse layout.

    39 wide x 14 tall room centered on the map with:
    - Counter nook built into north wall (box-drawing chars)
    - Small alcove at bottom-right for exit stairs
    - Large open floor area
    """
    from dungeon import RectRoom

    # --- room dimensions & origin ---
    rw, rh = 39, 14
    ox = (dungeon.width - rw) // 2
    oy = (dungeon.height - rh) // 2

    # Carve main room (interior: rows 1-12, cols 1-37)
    room = RectRoom(ox, oy, rw, rh)
    room.carve(dungeon)
    dungeon.rooms.append(room)

    # --- Carve alcove at bottom-right ---
    # Alcove interior: 5 wide x 3 tall, opening on the left side
    ax, ay = ox + 33, oy + 9   # alcove top-left (wall)
    aw, ah = 5, 3              # alcove interior size
    # Wall off the alcove top + right + bottom (already outer wall for right/bottom)
    # Top wall of alcove
    for x in range(ax, ax + aw + 1):
        if 0 <= x < dungeon.width and 0 <= ay < dungeon.height:
            dungeon.tiles[ay][x] = TILE_WALL
    # Left wall of alcove (with opening at middle row for access)
    for y in range(ay, ay + ah + 2):
        if y == ay + 2:
            continue  # leave opening for player to walk in
        if 0 <= ax < dungeon.width and 0 <= y < dungeon.height:
            dungeon.tiles[y][ax] = TILE_WALL

    dungeon._build_room_tile_map()


def spawn_penthouse(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned, floor_event=None):
    """Populate Tyrone's Penthouse: player, stairs, Tyrone NPC, counter, shop items."""
    from items import UNIQUE_TABLE_A, ITEM_DEFS, get_item_value, get_item_def

    dungeon.zone = zone

    rw, rh = 39, 14
    ox = (dungeon.width - rw) // 2
    oy = (dungeon.height - rh) // 2

    # --- Place player near entrance (row 4, a few tiles in from left) ---
    player.x = ox + 3
    player.y = oy + 4
    dungeon.entities.append(player)

    # --- Exit staircase (to Meth Lab) — bottom-right alcove ---
    dungeon.entities.append(Entity(
        x=ox + 35, y=oy + 11,
        char=">",
        color=(255, 220, 80),
        name="Stairs Down",
        entity_type="staircase",
        blocks_movement=False,
        reveals_on_sight=True,
    ))

    # --- Counter (box-drawing characters as blocking entities) ---
    # The counter is a U-shape that connects to the north wall.
    # Vertical sides run from row 1 (just inside north wall) down to row 3.
    # Horizontal front spans row 3 between the two sides.
    counter_color = (180, 140, 100)  # warm wood brown

    # Vertical sides: ║ at x=8 and x=26, rows 1-2 (connecting wall to counter front)
    for x in [ox + 8, ox + 26]:
        for y in range(oy + 1, oy + 3):
            dungeon.entities.append(Entity(
                x=x, y=y,
                char="║",
                color=counter_color,
                name="Counter",
                entity_type="hazard",
                hazard_type="counter",
                blocks_movement=True,
                blocks_fov=False,
            ))

    # Bottom corners where sides meet the front
    corners = [
        (ox + 8, oy + 3, "╚"),   # bottom-left
        (ox + 26, oy + 3, "╝"),  # bottom-right
    ]
    for cx, cy, ch in corners:
        dungeon.entities.append(Entity(
            x=cx, y=cy,
            char=ch,
            color=counter_color,
            name="Counter",
            entity_type="hazard",
            hazard_type="counter",
            blocks_movement=True,
            blocks_fov=False,
        ))

    # Front edge (row 3): ═ between items
    # 8 items: 5 uniques + 2 hats + 1 gun, spaced 2 apart
    item_xs = [ox + 9, ox + 11, ox + 13, ox + 15, ox + 17,
               ox + 19, ox + 21, ox + 23]
    for x in range(ox + 9, ox + 26):
        if x not in item_xs:
            dungeon.entities.append(Entity(
                x=x, y=oy + 3,
                char="═",
                color=counter_color,
                name="Counter",
                entity_type="hazard",
                hazard_type="counter",
                blocks_movement=True,
                blocks_fov=False,
            ))

    # --- Tyrone NPC (behind counter, row 2, centered) ---
    # Non-hostile NPC with npc_wander AI. Slowly roams behind the counter.
    tyrone = Entity(
        x=ox + 17, y=oy + 2,
        char="T",
        color=(255, 215, 0),  # gold
        name="Tyrone",
        entity_type="npc",
        blocks_movement=True,
        blocks_fov=False,
    )
    tyrone.ai_type = "npc_wander"
    tyrone.speed = 30               # slow wanderer
    tyrone.energy = 0
    tyrone.alive = True
    tyrone.hp = 9999
    tyrone.max_hp = 9999
    tyrone.status_effects = []
    tyrone.wander_idle_chance = 0.8  # mostly stands still
    dungeon.entities.append(tyrone)

    # --- Shop items (8 total on counter edge, row 3) ---
    # 5 seeded-random uniques (2x value)
    shop_entries = []  # list of (item_id, price)
    for uid in random.sample(UNIQUE_TABLE_A, 5):
        shop_entries.append((uid, get_item_value(uid) * 2))

    # 2 suffix-less tinfoil hats (fixed prices)
    shop_entries.append(("hat_tinfoil_hat_ripped_plain", 100))
    shop_entries.append(("hat_tinfoil_hat_excellent_plain", 300))

    # 1 random gun (1.5x value)
    all_guns = [k for k, v in ITEM_DEFS.items() if v.get("subcategory") == "gun"]
    gun_id = random.choice(all_guns)
    shop_entries.append((gun_id, round(get_item_value(gun_id) * 1.5)))

    for i, (item_id, price) in enumerate(shop_entries):
        defn = get_item_def(item_id) or {}
        item_entity = Entity(
            x=item_xs[i], y=oy + 3,
            char=defn.get("char", "?"),
            color=defn.get("color", (255, 255, 255)),
            name=defn.get("name", item_id),
            entity_type="hazard",
            hazard_type="shop_item",
            blocks_movement=True,
            blocks_fov=False,
        )
        item_entity.item_id = item_id
        item_entity.shop_price = price
        dungeon.entities.append(item_entity)


# ===================================================================
# Zone Generator Registry
# ===================================================================

# ===================================================================
# Event Generator: Spider Infestation
# ===================================================================

def generate_spider_infestation(dungeon):
    """Generate a spider infestation floor for the Crack Den.

    Layout:
    - Center: small 5x5 spawn room (room 0)
    - North: branching spider rooms → boss room (circular, radius 6) in top-left or top-right
    - South: normal Crack Den rooms with stairs down
    - Cobwebs in north-side hallways and room corners
    """
    from dungeon import build_mst, RectRoom, CircleRoom

    cx, cy = dungeon.width // 2, dungeon.height // 2

    # --- Room 0: spawn room (center, 5x5) ---
    spawn_room = RectRoom(cx - 2, cy - 2, 5, 5)
    spawn_room.carve(dungeon)
    dungeon.rooms.append(spawn_room)

    # --- Boss room: circular, radius 6, top-left or top-right ---
    boss_side = random.choice(["left", "right"])
    if boss_side == "left":
        boss_cx = dungeon.width // 4
    else:
        boss_cx = dungeon.width * 3 // 4
    boss_cy = 10
    boss_room = CircleRoom(boss_cx, boss_cy, 6)
    boss_room.carve(dungeon)
    dungeon.rooms.append(boss_room)  # room 1 = boss room

    # --- North spider rooms (between spawn and boss) ---
    north_rooms = []
    margin = 2
    for _ in range(random.randint(4, 6)):
        for _attempt in range(30):
            w = random.randint(5, 9)
            h = random.randint(5, 9)
            rx = random.randint(margin, dungeon.width - w - margin)
            ry = random.randint(margin, cy - 3)  # north half
            room = RectRoom(rx, ry, w, h)
            if any(room.intersects(other) for other in dungeon.rooms):
                continue
            room.carve(dungeon)
            dungeon.rooms.append(room)
            north_rooms.append(room)
            break

    # --- South normal rooms ---
    south_rooms = []
    for _ in range(random.randint(4, 7)):
        for _attempt in range(30):
            w = random.randint(5, 10)
            h = random.randint(5, 8)
            rx = random.randint(margin, dungeon.width - w - margin)
            ry = random.randint(cy + 4, dungeon.height - h - margin)  # south half
            room = RectRoom(rx, ry, w, h)
            if any(room.intersects(other) for other in dungeon.rooms):
                continue
            room.carve(dungeon)
            dungeon.rooms.append(room)
            south_rooms.append(room)
            break

    # --- Connect rooms with MST ---
    if len(dungeon.rooms) > 1:
        for i, j in build_mst(dungeon.rooms):
            dungeon._carve_wide_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center(), 2)

    # Extra connections for loops
    if len(dungeon.rooms) > 3:
        for _ in range(len(dungeon.rooms) // 4):
            i = random.randint(0, len(dungeon.rooms) - 1)
            j = random.randint(0, len(dungeon.rooms) - 1)
            if i != j:
                dungeon._carve_wide_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center(), 2)

    # Build room tile map
    dungeon._build_room_tile_map()

    # --- Place cobwebs in north-side hallways and room corners ---
    from hazards import create_web
    from config import TILE_FLOOR

    # Cobwebs in corridors north of center
    corridor_webs = 0
    for y in range(0, cy):
        for x in range(dungeon.width):
            if dungeon.tiles[y][x] != TILE_FLOOR:
                continue
            # Only in corridors (not in rooms)
            if dungeon.room_tile_map.get((x, y)) is not None:
                continue
            if random.random() < 0.15:  # 15% chance per corridor tile
                web = create_web(x, y)
                dungeon.entities.append(web)
                corridor_webs += 1

    # Cobwebs in corners of north rooms (including boss room)
    for room in [dungeon.rooms[1]] + north_rooms:  # boss room + spider rooms
        tiles = room.floor_tiles(dungeon)
        if not tiles:
            continue
        # Find corner-ish tiles (near room edges)
        x1, y1, x2, y2 = room.x1, room.y1, room.x2, room.y2
        for tx, ty in tiles:
            near_edge_x = (tx <= x1 + 1 or tx >= x2 - 1)
            near_edge_y = (ty <= y1 + 1 or ty >= y2 - 1)
            if near_edge_x and near_edge_y and random.random() < 0.5:
                if not any(e.x == tx and e.y == ty for e in dungeon.entities):
                    web = create_web(tx, ty)
                    dungeon.entities.append(web)

    # Mark which rooms are spider rooms vs normal
    dungeon.spider_rooms = [1] + [dungeon.rooms.index(r) for r in north_rooms if r in dungeon.rooms]
    dungeon.south_rooms = [dungeon.rooms.index(r) for r in south_rooms if r in dungeon.rooms]
    dungeon.boss_room_index = 1


def spawn_spider_infestation(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned):
    """Spawn entities for a spider infestation floor."""
    from items import create_item_entity
    from entity import Entity

    dungeon.zone = zone
    dungeon.entities.append(player)

    # Stairs in the southernmost room
    south_rooms = getattr(dungeon, 'south_rooms', [])
    if south_rooms:
        stair_room_idx = max(south_rooms, key=lambda idx: dungeon.rooms[idx].center()[1])
    else:
        stair_room_idx = len(dungeon.rooms) - 1
    stair_room = dungeon.rooms[stair_room_idx]
    sx, sy = stair_room.center()
    dungeon.entities.append(Entity(
        x=sx, y=sy,
        char=">",
        color=(255, 220, 80),
        name="Stairs Down",
        entity_type="staircase",
        blocks_movement=False,
        reveals_on_sight=True,
    ))

    # --- Spawn spiders in north rooms ---
    spider_rooms = getattr(dungeon, 'spider_rooms', [])
    boss_idx = getattr(dungeon, 'boss_room_index', 1)
    spider_table = [("pipe_spider", 50), ("sac_spider", 25), ("wolf_spider", 25)]

    for room_idx in spider_rooms:
        if room_idx == boss_idx:
            continue  # boss room handled separately
        room = dungeon.rooms[room_idx]
        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue

        room_tile_set = frozenset(floor_tiles)
        n_monsters = random.randint(3, 6)

        for _ in range(n_monsters):
            types = [t[0] for t in spider_table]
            weights = [t[1] for t in spider_table]
            enemy_type = random.choices(types, weights=weights, k=1)[0]

            free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
            if not free:
                break
            x, y = random.choice(free)
            monster = create_enemy(enemy_type, x, y)
            monster.spawn_room_tiles = room_tile_set
            dungeon.entities.append(monster)

    # --- Boss room: Black Widow + 3-5 mature spider eggs ---
    boss_room = dungeon.rooms[boss_idx]
    boss_tiles = boss_room.floor_tiles(dungeon)
    boss_tile_set = frozenset(boss_tiles)
    bx, by = boss_room.center()

    # Spawn Black Widow near center
    free = [(tx, ty) for tx, ty in boss_tiles if not dungeon.is_blocked(tx, ty)]
    if free:
        # Place boss near center
        boss_candidates = [(tx, ty) for tx, ty in free if abs(tx - bx) <= 2 and abs(ty - by) <= 2]
        if boss_candidates:
            wx, wy = random.choice(boss_candidates)
        else:
            wx, wy = random.choice(free)
        widow = create_enemy("black_widow", wx, wy)
        widow.spawn_room_tiles = boss_tile_set
        dungeon.entities.append(widow)

    # Place 3-5 mature spider eggs in the back (far from entrance)
    n_eggs = random.randint(3, 5)
    # "Back" = tiles farthest from center of dungeon
    egg_tiles = sorted(boss_tiles, key=lambda t: -abs(t[1] - dungeon.height // 2))
    eggs_placed = 0
    for tx, ty in egg_tiles:
        if eggs_placed >= n_eggs:
            break
        if dungeon.is_blocked(tx, ty):
            continue
        if any(e.x == tx and e.y == ty for e in dungeon.entities):
            continue
        egg_kwargs = create_item_entity("mature_spider_egg", tx, ty)
        dungeon.entities.append(Entity(**egg_kwargs))
        eggs_placed += 1

    # --- Spawn normal Crack Den enemies in south rooms ---
    zone_table = get_spawn_table(zone, floor_num)
    if zone_table:
        for room_idx in getattr(dungeon, 'south_rooms', []):
            room = dungeon.rooms[room_idx]
            floor_tiles = room.floor_tiles(dungeon)
            if not floor_tiles:
                continue
            room_tile_set = frozenset(floor_tiles)
            n_monsters = random.randint(2, 5)
            enemy_types = [t[0] for t in zone_table]
            enemy_weights = [t[1] for t in zone_table]
            for _ in range(n_monsters):
                enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
                free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
                if not free:
                    break
                x, y = random.choice(free)
                monster = create_enemy(enemy_type, x, y)
                monster.spawn_room_tiles = room_tile_set
                dungeon.entities.append(monster)

    # --- Spawn loot in south rooms ---
    _spawn_floor_loot_in_rooms(dungeon, dungeon.south_rooms, zone, floor_num, player_skills)

    # --- Extra consumables in spider rooms (reward for clearing the north) ---
    from loot import pick_random_consumable
    from items import create_item_entity as _cie
    spider_loot_rooms = [idx for idx in spider_rooms if idx != boss_idx]
    for _ in range(6):
        if not spider_loot_rooms:
            break
        room_idx = random.choice(spider_loot_rooms)
        room = dungeon.rooms[room_idx]
        free = [(tx, ty) for tx, ty in room.floor_tiles(dungeon) if not dungeon.is_blocked(tx, ty)]
        if not free:
            continue
        ix, iy = random.choice(free)
        item_id, strain = pick_random_consumable(zone)
        kwargs = _cie(item_id, ix, iy, strain=strain)
        dungeon.entities.append(Entity(**kwargs))


def _spawn_floor_loot_in_rooms(dungeon, room_indices, zone, floor_num, player_skills):
    """Spawn loot items in the given rooms using the zone's loot tables."""
    from loot import generate_floor_loot
    from items import create_item_entity
    from entity import Entity

    loot_list = generate_floor_loot(zone, floor_num, player_skills)
    for item_id, strain in loot_list:
        if not room_indices:
            break
        room_idx = random.choice(room_indices)
        room = dungeon.rooms[room_idx]
        floor_tiles = room.floor_tiles(dungeon)
        free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
        if free:
            ix, iy = random.choice(free)
            kwargs = create_item_entity(item_id, ix, iy, strain=strain)
            dungeon.entities.append(Entity(**kwargs))


# ===================================================================
# Sublevel: Haitian Daycare
# ===================================================================

def generate_haitian_daycare(dungeon):
    """Generate the Haitian Daycare sublevel.

    Compact cluster of square rooms connected by tiny 1-2 tile hallways.
    Does not fill the whole map — rooms packed into a ~35x25 area.
    """
    from dungeon import build_mst, RectRoom

    # Define the active area — compact cluster offset from top-left
    area_x, area_y = 10, 8
    area_w, area_h = 38, 28

    # Room size pools: small and large
    sizes = [
        (4, 4), (4, 5), (5, 4), (5, 5),   # small
        (6, 5), (5, 6), (6, 6),             # medium
        (7, 6), (6, 7), (8, 6), (7, 7),    # large
    ]

    target_rooms = random.randint(8, 12)
    attempts = 0
    max_attempts = target_rooms * 20

    while len(dungeon.rooms) < target_rooms and attempts < max_attempts:
        attempts += 1
        w, h = random.choice(sizes)
        # Place within the compact area with 1-2 tile gaps (padding=2 allows tiny hallways)
        x = random.randint(area_x, area_x + area_w - w - 1)
        y = random.randint(area_y, area_y + area_h - h - 1)
        room = RectRoom(x, y, w, h)

        # Check overlap — allow rooms within 2 tiles of each other (tiny hallways)
        # but not overlapping
        if any(room.intersects(other) for other in dungeon.rooms):
            continue

        # Reject rooms that are too far from any existing room (keep cluster tight)
        if dungeon.rooms:
            cx, cy = room.center()
            min_dist = min(
                max(abs(cx - ox), abs(cy - oy))
                for r in dungeon.rooms
                for ox, oy in [r.center()]
            )
            if min_dist > 14:  # reject outliers
                continue

        room.carve(dungeon)
        dungeon.rooms.append(room)

    # Connect rooms with MST — corridors will be short (1-2 tiles) due to tight packing
    if len(dungeon.rooms) >= 2:
        for i, j in build_mst(dungeon.rooms):
            dungeon.carve_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center())

    dungeon._build_room_tile_map()


def spawn_haitian_daycare(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned, floor_event=None):
    """Spawn entities for the Haitian Daycare sublevel."""
    dungeon.zone = "haitian_daycare"
    dungeon.entities.append(player)

    # Spawn upstairs in the first room (sends player back to the occult floor)
    if dungeon.rooms:
        room = dungeon.rooms[0]
        tiles = room.floor_tiles(dungeon)
        free = [(x, y) for x, y in tiles if not dungeon.is_blocked(x, y)]
        if free:
            x, y = random.choice(free)
            dungeon.entities.append(Entity(
                x=x, y=y,
                char="<",
                color=(180, 100, 255),
                name="Stairs Up",
                entity_type="staircase",
                blocks_movement=False,
                reveals_on_sight=True,
            ))

    # Spawn 1-3 enemies per room (50/50 ritualist/occultist), skip room 0 (spawn room)
    _DAYCARE_ENEMIES = ["ritualist", "occultist"]
    for room in dungeon.rooms[1:]:
        tiles = room.floor_tiles(dungeon)
        room_tile_set = frozenset(tiles)
        n_mobs = random.randint(1, 3)
        for _ in range(n_mobs):
            free = [(x, y) for x, y in tiles if not dungeon.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            enemy_type = random.choice(_DAYCARE_ENEMIES)
            monster = create_enemy(enemy_type, x, y)
            monster.spawn_room_tiles = room_tile_set
            dungeon.entities.append(monster)

    # Spawn 6 voodoo dolls spread across rooms
    spawnable = dungeon.rooms[1:]
    if spawnable:
        for i in range(6):
            room = spawnable[i % len(spawnable)]
            tiles = room.floor_tiles(dungeon)
            free = [(x, y) for x, y in tiles if not dungeon.is_blocked(x, y)]
            if free:
                x, y = random.choice(free)
                kwargs = create_item_entity("voodoo_doll", x, y)
                dungeon.entities.append(Entity(**kwargs))

    # Spawn 10 items from the Crack Den loot pool
    if spawnable and player_skills and player_stats:
        crack_den_loot = generate_floor_loot("crack_den", 1, player_skills, player_stats)
        random.shuffle(crack_den_loot)
        for i, (item_id, strain) in enumerate(crack_den_loot[:10]):
            room = spawnable[i % len(spawnable)]
            tiles = room.floor_tiles(dungeon)
            if tiles:
                x, y = random.choice(tiles)
                if not dungeon.is_blocked(x, y):
                    kwargs = create_item_entity(item_id, x, y, strain=strain)
                    dungeon.entities.append(Entity(**kwargs))


ZONE_GENERATORS = {
    "crack_den":         {"generate": generate_crack_den,  "spawn": spawn_crack_den},
    "meth_lab":          {"generate": generate_meth_lab,   "spawn": spawn_meth_lab},
    "tyrones_penthouse": {"generate": generate_penthouse,  "spawn": spawn_penthouse},
    "haitian_daycare":   {"generate": generate_haitian_daycare, "spawn": spawn_haitian_daycare},
}

EVENT_GENERATORS = {
    "spider_infestation": {"generate": generate_spider_infestation, "spawn": spawn_spider_infestation},
}
