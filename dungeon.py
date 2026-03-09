"""
Dungeon generation and map management.
"""

import random
import numpy as np
import tcod
from config import (
    DUNGEON_WIDTH,
    DUNGEON_HEIGHT,
    TILE_WALL,
    TILE_FLOOR,
    ROOM_MIN_SIZE,
    ROOM_MAX_SIZE,
    MAX_ROOMS,
    MAX_MONSTERS_PER_ROOM,
    BASE_HP,
    BASE_POWER,
    BASE_DEFENSE,
)
from entity import Entity
from items import create_item_entity
from enemies import create_enemy, get_spawn_table, MONSTER_REGISTRY
from loot import generate_floor_loot
from items import STRAINS, build_item_name


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Room shapes
# ---------------------------------------------------------------------------

class Room:
    """Base class for all room shapes. Stores bounding box for intersection."""

    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def center(self):
        return ((self.x1 + self.x2) // 2, (self.y1 + self.y2) // 2)

    def intersects(self, other, padding=1):
        """Bounding-box check with a padding gap between rooms."""
        return (
            self.x1 - padding <= other.x2
            and self.x2 + padding >= other.x1
            and self.y1 - padding <= other.y2
            and self.y2 + padding >= other.y1
        )

    def _carve_rect(self, dungeon, x1, y1, x2, y2):
        """Carve a rectangle of floor tiles."""
        for y in range(y1, y2):
            for x in range(x1, x2):
                if 0 <= x < dungeon.width and 0 <= y < dungeon.height:
                    dungeon.tiles[y][x] = TILE_FLOOR

    def carve(self, dungeon):
        raise NotImplementedError

    def floor_tiles(self, dungeon):
        """Return all floor tile positions inside this room's bounding box."""
        tiles = []
        for y in range(self.y1, self.y2 + 1):
            for x in range(self.x1, self.x2 + 1):
                if 0 <= x < dungeon.width and 0 <= y < dungeon.height:
                    if dungeon.tiles[y][x] == TILE_FLOOR:
                        tiles.append((x, y))
        return tiles


class RectRoom(Room):
    """Classic rectangle — the most common room type."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, x + w, y + h)

    def carve(self, dungeon):
        self._carve_rect(dungeon, self.x1, self.y1, self.x2, self.y2)


class LRoom(Room):
    """L-shaped room: two rectangles sharing a corner.
    The corner parameter controls which quarter is removed (0-3 = TL,TR,BL,BR)."""

    def __init__(self, x1, y1, x2, y2, corner=None):
        super().__init__(x1, y1, x2, y2)
        if corner is None:
            corner = random.randint(0, 3)
        w = x2 - x1
        h = y2 - y1
        mx = x1 + w // 2
        my = y1 + h // 2

        # Full bounding box minus one quadrant = L shape
        if corner == 0:   # remove top-left quadrant
            self.rects = [(mx, y1, x2, my), (x1, my, x2, y2)]
        elif corner == 1: # remove top-right quadrant
            self.rects = [(x1, y1, mx, my), (x1, my, x2, y2)]
        elif corner == 2: # remove bottom-left quadrant
            self.rects = [(x1, y1, x2, my), (mx, my, x2, y2)]
        else:             # remove bottom-right quadrant
            self.rects = [(x1, y1, x2, my), (x1, my, mx, y2)]

    def carve(self, dungeon):
        for x1, y1, x2, y2 in self.rects:
            self._carve_rect(dungeon, x1, y1, x2, y2)


class TRoom(Room):
    """T-shaped room: a wide horizontal bar with a vertical stem."""

    def __init__(self, x1, y1, x2, y2):
        super().__init__(x1, y1, x2, y2)
        w = x2 - x1
        h = y2 - y1
        stem_w = max(3, w // 3)
        stem_x = x1 + (w - stem_w) // 2
        bar_h = max(3, h // 3)

        self.bar  = (x1, y1, x2, y1 + bar_h)
        self.stem = (stem_x, y1 + bar_h, stem_x + stem_w, y2)

    def carve(self, dungeon):
        for rect in [self.bar, self.stem]:
            self._carve_rect(dungeon, *rect)


class CrossRoom(Room):
    """Plus/cross shape: two bars intersecting at the center."""

    def __init__(self, cx, cy, size):
        super().__init__(cx - size, cy - size, cx + size, cy + size)
        self.cx = cx
        self.cy = cy
        self.size = size

    def carve(self, dungeon):
        arm = max(2, self.size // 3)
        # Horizontal bar
        self._carve_rect(dungeon, self.x1, self.cy - arm, self.x2, self.cy + arm)
        # Vertical bar
        self._carve_rect(dungeon, self.cx - arm, self.y1, self.cx + arm, self.y2)


class CircleRoom(Room):
    """Rare circular room — stands out as a special chamber."""

    def __init__(self, cx, cy, radius):
        super().__init__(cx - radius, cy - radius, cx + radius, cy + radius)
        self.cx = cx
        self.cy = cy
        self.radius = radius

    def carve(self, dungeon):
        r2 = self.radius * self.radius
        for y in range(self.y1, self.y2 + 1):
            for x in range(self.x1, self.x2 + 1):
                if (x - self.cx) ** 2 + (y - self.cy) ** 2 <= r2:
                    if 0 <= x < dungeon.width and 0 <= y < dungeon.height:
                        dungeon.tiles[y][x] = TILE_FLOOR


class URoom(Room):
    """U-shaped room: rectangle with a rectangular notch cut from one side."""

    def __init__(self, x1, y1, x2, y2, side=None):
        super().__init__(x1, y1, x2, y2)
        if side is None:
            side = random.randint(0, 3)
        w = x2 - x1
        h = y2 - y1
        nw = max(2, w // 3)
        nh = max(2, h // 3)
        nx = x1 + (w - nw) // 2
        ny = y1 + (h - nh) // 2

        if side == 0:   # notch at top
            self.rects = [(x1, y1 + nh, x2, y2), (x1, y1, nx, y1 + nh), (nx + nw, y1, x2, y1 + nh)]
        elif side == 1: # notch at right
            self.rects = [(x1, y1, x2 - nw, y2), (x2 - nw, y1, x2, ny), (x2 - nw, ny + nh, x2, y2)]
        elif side == 2: # notch at bottom
            self.rects = [(x1, y1, x2, y2 - nh), (x1, y2 - nh, nx, y2), (nx + nw, y2 - nh, x2, y2)]
        else:           # notch at left
            self.rects = [(x1 + nw, y1, x2, y2), (x1, y1, x1 + nw, ny), (x1, ny + nh, x1 + nw, y2)]

    def carve(self, dungeon):
        for rect in self.rects:
            self._carve_rect(dungeon, *rect)


class DiamondRoom(Room):
    """Diamond/rhombus shape using Manhattan distance — all right-angle edges."""

    def __init__(self, cx, cy, radius):
        super().__init__(cx - radius, cy - radius, cx + radius, cy + radius)
        self.cx = cx
        self.cy = cy
        self.radius = radius

    def carve(self, dungeon):
        for y in range(self.y1, self.y2 + 1):
            for x in range(self.x1, self.x2 + 1):
                if abs(x - self.cx) + abs(y - self.cy) <= self.radius:
                    if 0 <= x < dungeon.width and 0 <= y < dungeon.height:
                        dungeon.tiles[y][x] = TILE_FLOOR


class CavernRoom(Room):
    """Irregular blob room carved by a drunk walk — organic but still blocky."""

    def __init__(self, cx, cy, size):
        super().__init__(cx - size, cy - size, cx + size, cy + size)
        self.cx = cx
        self.cy = cy
        self.size = size

    def carve(self, dungeon):
        x, y = self.cx, self.cy
        steps = self.size * self.size * 3
        for _ in range(steps):
            if self.x1 < x < self.x2 and self.y1 < y < self.y2:
                if 0 <= x < dungeon.width and 0 <= y < dungeon.height:
                    dungeon.tiles[y][x] = TILE_FLOOR
            dx, dy = random.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
            nx, ny = x + dx, y + dy
            if self.x1 <= nx <= self.x2 and self.y1 <= ny <= self.y2:
                x, y = nx, ny


class HallRoom(Room):
    """Long narrow room — either horizontal or vertical.
    Acts as a wide corridor and creates natural chokepoints."""

    def __init__(self, x, y, length, width, horizontal=True):
        if horizontal:
            super().__init__(x, y, x + length, y + width)
        else:
            super().__init__(x, y, x + width, y + length)

    def carve(self, dungeon):
        self._carve_rect(dungeon, self.x1, self.y1, self.x2, self.y2)


class OctRoom(Room):
    """Octagonal room: rectangle with clipped corners (all right-angle cuts)."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, x + w, y + h)
        self.clip = min(w, h) // 4

    def carve(self, dungeon):
        clip = self.clip
        w = self.x2 - self.x1
        h = self.y2 - self.y1

        for y in range(self.y1, self.y2):
            for x in range(self.x1, self.x2):
                if not (0 <= x < dungeon.width and 0 <= y < dungeon.height):
                    continue
                lx = x - self.x1
                ly = y - self.y1
                # Skip the four diagonal corners
                if lx + ly < clip:
                    continue
                if (w - 1 - lx) + ly < clip:
                    continue
                if lx + (h - 1 - ly) < clip:
                    continue
                if (w - 1 - lx) + (h - 1 - ly) < clip:
                    continue
                dungeon.tiles[y][x] = TILE_FLOOR


class PillarRoom(Room):
    """Rectangle with internal wall pillars — classic vault feel."""

    def __init__(self, x, y, w, h):
        super().__init__(x, y, x + w, y + h)

    def carve(self, dungeon):
        # Carve full room first
        self._carve_rect(dungeon, self.x1, self.y1, self.x2, self.y2)
        # Place 1-tile pillars on a grid, keeping 2-tile margin from walls
        for py in range(self.y1 + 2, self.y2 - 2, 3):
            for px in range(self.x1 + 2, self.x2 - 2, 3):
                if 0 <= px < dungeon.width and 0 <= py < dungeon.height:
                    dungeon.tiles[py][px] = TILE_WALL


# ---------------------------------------------------------------------------
# MST connection — no duplicate corridors
# ---------------------------------------------------------------------------

def build_mst(rooms):
    """
    Prim's algorithm: grows a spanning tree one room at a time.
    Returns a list of (i, j) index pairs — one connection per pair, no duplicates.
    """
    if len(rooms) < 2:
        return []

    connected = {0}
    edges = []

    while len(connected) < len(rooms):
        best = None
        best_dist = float("inf")

        for i in connected:
            cx1, cy1 = rooms[i].center()
            for j in range(len(rooms)):
                if j in connected:
                    continue
                cx2, cy2 = rooms[j].center()
                dist = abs(cx1 - cx2) + abs(cy1 - cy2)
                if dist < best_dist:
                    best_dist = dist
                    best = (i, j)

        if best:
            edges.append(best)
            connected.add(best[1])

    return edges


# ---------------------------------------------------------------------------
# Dungeon
# ---------------------------------------------------------------------------

class Dungeon:
    """Represents a dungeon floor."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.tiles = [[TILE_WALL for _ in range(width)] for _ in range(height)]
        self.entities = []
        self.rooms = []

        self.visible = np.zeros((height, width), dtype=bool)
        self.explored = np.zeros((height, width), dtype=bool)

        # Entities revealed as landmarks this FOV update (cleared each compute_fov call).
        self.newly_revealed_landmarks: list = []

        # Set to True the first time any monster dies on this floor.
        # Used by the alarm_chaser AI (ugly strippers).
        self.first_kill_happened = False

        # Set to True the first time a female monster dies on this floor.
        # Used by the female_alarm AI (fat gooners).
        self.female_kill_happened = False

        self.room_tile_map: dict[tuple, int] = {}  # (x, y) -> room_index

        self.generate()

    def generate(self):
        """Place rooms randomly, then connect them all with MST corridors + extra connections."""
        attempts = 0
        max_attempts = MAX_ROOMS * 6

        while len(self.rooms) < MAX_ROOMS and attempts < max_attempts:
            attempts += 1
            room = self._random_room()
            if room is None:
                continue
            if any(room.intersects(other) for other in self.rooms):
                continue
            room.carve(self)
            self.rooms.append(room)

        # Carve MST corridors (guaranteed connectivity)
        for i, j in build_mst(self.rooms):
            self.carve_corridor(self.rooms[i].center(), self.rooms[j].center())

        # Add extra connections for more interconnected layout
        if len(self.rooms) > 2:
            for _ in range(len(self.rooms) // 3):  # ~1/3 of rooms get an extra connection
                i = random.randint(0, len(self.rooms) - 1)
                j = random.randint(0, len(self.rooms) - 1)
                if i != j:
                    self.carve_corridor(self.rooms[i].center(), self.rooms[j].center())

        # Build room tile map after all corridors are carved
        self._build_room_tile_map()

    def _random_room(self):
        """Pick a random room shape and position."""
        shape = random.choices(
            ["rect", "l", "u", "t", "hall", "oct", "cross", "diamond", "cavern", "pillar", "circle"],
            weights=[  6,   4,   4,   3,      5,      3,       2,          2,          2,       2,        1],
        )[0]

        lo = ROOM_MIN_SIZE
        hi = ROOM_MAX_SIZE

        if shape == "rect":
            w = random.randint(lo, hi)
            h = random.randint(lo, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return RectRoom(x, y, w, h)

        elif shape == "l":
            w = random.randint(lo, hi)
            h = random.randint(lo, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return LRoom(x, y, x + w, y + h)

        elif shape == "u":
            w = random.randint(lo, hi)
            h = random.randint(lo, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return URoom(x, y, x + w, y + h)

        elif shape == "t":
            w = random.randint(lo + 2, hi)
            h = random.randint(lo + 2, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return TRoom(x, y, x + w, y + h)

        elif shape == "hall":
            length = random.randint(18, 32)
            width  = random.randint(3, 5)
            horiz  = random.choice([True, False])
            if horiz:
                x = random.randint(1, self.width - length - 2)
                y = random.randint(1, self.height - width - 2)
            else:
                x = random.randint(1, self.width - width - 2)
                y = random.randint(1, self.height - length - 2)
            return HallRoom(x, y, length, width, horiz)

        elif shape == "oct":
            w = random.randint(lo, hi)
            h = random.randint(lo, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return OctRoom(x, y, w, h)

        elif shape == "cross":
            size = random.randint(lo // 2, hi // 2)
            cx = random.randint(size + 1, self.width - size - 2)
            cy = random.randint(size + 1, self.height - size - 2)
            return CrossRoom(cx, cy, size)

        elif shape == "diamond":
            radius = random.randint(lo // 2, hi // 2)
            cx = random.randint(radius + 1, self.width - radius - 2)
            cy = random.randint(radius + 1, self.height - radius - 2)
            return DiamondRoom(cx, cy, radius)

        elif shape == "cavern":
            size = random.randint(lo // 2, hi // 2)
            cx = random.randint(size + 1, self.width - size - 2)
            cy = random.randint(size + 1, self.height - size - 2)
            return CavernRoom(cx, cy, size)

        elif shape == "pillar":
            w = random.randint(lo + 2, hi)
            h = random.randint(lo + 2, hi)
            x = random.randint(1, self.width - w - 2)
            y = random.randint(1, self.height - h - 2)
            return PillarRoom(x, y, w, h)

        elif shape == "circle":
            radius = random.randint(lo // 2, hi // 2)
            cx = random.randint(radius + 1, self.width - radius - 2)
            cy = random.randint(radius + 1, self.height - radius - 2)
            return CircleRoom(cx, cy, radius)

    def carve_corridor(self, from_point, to_point):
        """Carve an L-shaped corridor between two points."""
        x1, y1 = from_point
        x2, y2 = to_point

        if random.choice([True, False]):
            for x in range(min(x1, x2), max(x1, x2) + 1):
                if 0 <= x < self.width and 0 <= y1 < self.height:
                    self.tiles[y1][x] = TILE_FLOOR
            for y in range(min(y1, y2), max(y1, y2) + 1):
                if 0 <= x2 < self.width and 0 <= y < self.height:
                    self.tiles[y][x2] = TILE_FLOOR
        else:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                if 0 <= x1 < self.width and 0 <= y < self.height:
                    self.tiles[y][x1] = TILE_FLOOR
            for x in range(min(x1, x2), max(x1, x2) + 1):
                if 0 <= x < self.width and 0 <= y2 < self.height:
                    self.tiles[y2][x] = TILE_FLOOR

    def _spawn_staircase(self):
        """Spawn a staircase in a random non-spawn room."""
        eligible = self.rooms[1:]
        if not eligible:
            return
        room = random.choice(eligible)
        floor_tiles = room.floor_tiles(self)
        free = [(x, y) for x, y in floor_tiles if not self.is_blocked(x, y)]
        if not free:
            # Fallback: any free tile in the room, ignoring entities
            free = floor_tiles
        if free:
            x, y = random.choice(free)
            self.entities.append(Entity(
                x=x, y=y,
                char=">",
                color=(255, 220, 80),
                name="Stairs Down",
                entity_type="staircase",
                blocks_movement=False,
                reveals_on_sight=True,
            ))

    def _build_room_tile_map(self):
        """Map each floor tile to the room index it belongs to."""
        self.room_tile_map = {}
        for room_idx, room in enumerate(self.rooms):
            for x, y in room.floor_tiles(self):
                self.room_tile_map[(x, y)] = room_idx

    def get_room_index_at(self, x: int, y: int) -> "int | None":
        """Return the room index at (x, y), or None if in a corridor."""
        return self.room_tile_map.get((x, y))

    def spawn_entities(self, player, floor_num=0, zone="crack_den", player_skills=None, special_rooms_spawned=None):
        """Spawn monsters and items in rooms."""
        self.zone = zone
        self.entities.append(player)

        # Roll for special rooms and claim rooms before normal spawning
        special_room_indices = set()
        if special_rooms_spawned is not None:
            special_room_indices = self._roll_special_rooms(floor_num, zone, special_rooms_spawned)

        for room_idx, room in enumerate(self.rooms[1:], start=1):
            if room_idx in special_room_indices:
                continue  # special rooms handle their own spawns

            floor_tiles = room.floor_tiles(self)
            if not floor_tiles:
                continue

            # Zone-based monster spawning (per-floor weighted tables)
            zone_table = get_spawn_table(zone, floor_num)
            if zone_table:
                enemy_types   = [t[0] for t in zone_table]
                enemy_weights = [t[1] for t in zone_table]

                # Precompute the frozenset of floor tiles for this room once,
                # so every monster spawned here can reference it cheaply.
                room_tile_set = frozenset(floor_tiles)

                # Dynamic monster count: size-scaling + floor bonus + populated/empty gate
                size_max = max(1, len(floor_tiles) // 10)
                floor_bonus = floor_num // 2  # +1 at floor 3, +2 at floor 5, etc.
                room_max = size_max + floor_bonus

                # 65% of rooms are "populated", 35% are empty — creates natural pacing
                if random.random() < 0.65:
                    # Weighted distribution: favor 1 group, allow occasional spikes
                    options = list(range(1, room_max + 1))
                    # Weights peak at 1 and taper linearly: [4, 3, 2, 1, ...]
                    weights = [max(1, room_max + 1 - i) for i in range(len(options))]
                    n_groups = random.choices(options, weights=weights, k=1)[0]
                else:
                    n_groups = 0

                for _ in range(n_groups):
                    enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
                    tmpl = MONSTER_REGISTRY[enemy_type]

                    # Pick a free tile for the primary monster
                    free = [(tx, ty) for tx, ty in floor_tiles if not self.is_blocked(tx, ty)]
                    if not free:
                        continue
                    x, y = random.choice(free)
                    monster = create_enemy(enemy_type, x, y)
                    # Tag with spawn room so room_guard AI can detect player entry.
                    monster.spawn_room_tiles = room_tile_set
                    self.entities.append(monster)

                    # Spawn escorts defined in the template (e.g. tweakers for drug dealer)
                    for escort_spec in tmpl.spawn_with:
                        escort_type  = escort_spec.type
                        escort_count = random.randint(*escort_spec.count)
                        for _ in range(escort_count):
                            nearby_free = [
                                (nx, ny) for nx, ny in floor_tiles
                                if abs(nx - x) <= 4 and abs(ny - y) <= 4
                                and not self.is_blocked(nx, ny)
                            ]
                            if nearby_free:
                                ex, ey = random.choice(nearby_free)
                                escort = create_enemy(escort_type, ex, ey)
                                escort.spawn_room_tiles = room_tile_set
                                # Mark the escort to follow the primary monster
                                escort.leader = monster
                                # Change from room_guard to escort AI
                                escort.ai_type = "escort"
                                escort.ai_state = None  # Let do_ai_turn reinit based on ai_type
                                self.entities.append(escort)


        # Spawn staircase first so its tile can be excluded from item/cash placement
        if floor_num < 3:
            self._spawn_staircase()

        # Collect staircase positions to exclude from item/cash spawning
        stair_tiles = frozenset(
            (e.x, e.y) for e in self.entities if getattr(e, "entity_type", None) == "staircase"
        )

        # Spawn floor loot via zone-based loot system (round-robin across rooms)
        floor_loot = generate_floor_loot(zone, floor_num, player_skills)
        random.shuffle(floor_loot)
        spawnable_rooms = self.rooms[1:]
        if spawnable_rooms:
            for i, (item_id, strain) in enumerate(floor_loot):
                room = spawnable_rooms[i % len(spawnable_rooms)]
                floor_tiles = room.floor_tiles(self)
                if floor_tiles:
                    x, y = random.choice(floor_tiles)
                    if not self.is_blocked(x, y) and (x, y) not in stair_tiles:
                        kwargs = create_item_entity(item_id, x, y, strain=strain)
                        self.entities.append(Entity(**kwargs))

        # Spawn cash piles: 7-10 total on the floor, 0-3 per room
        # Amounts 1-15 with decreasing probability (weight 15 for $1, weight 1 for $15)
        _CASH_AMOUNTS = list(range(1, 16))
        _CASH_WEIGHTS = list(range(15, 0, -1))
        cash_target = random.randint(7, 10)
        cash_total = 0

        for room in self.rooms[1:]:
            if cash_total >= cash_target:
                break
            floor_tiles = room.floor_tiles(self)
            if not floor_tiles:
                continue
            remaining = cash_target - cash_total
            n_cash = random.randint(0, min(3, remaining))
            for _ in range(n_cash):
                x, y = random.choice(floor_tiles)
                if not self.is_blocked(x, y) and (x, y) not in stair_tiles:
                    amount = random.choices(_CASH_AMOUNTS, weights=_CASH_WEIGHTS, k=1)[0]
                    self.entities.append(Entity(
                        x=x, y=y,
                        char="$",
                        color=(255, 215, 0),
                        name=f"${amount}",
                        entity_type="cash",
                        blocks_movement=False,
                        cash_amount=amount,
                    ))
                    cash_total += 1

    # ------------------------------------------------------------------
    # Special rooms
    # ------------------------------------------------------------------

    # Each entry: (room_key, eligible_floors, chance)
    SPECIAL_ROOM_DEFS = [
        ("niglet_den",   {0, 1, 2}, 0.10),  # floors 1-3 (0-indexed), 10% chance
        ("smoke_lounge", {1, 2, 3}, 0.10),  # floors 2-4 (0-indexed), 10% chance
        ("jerome_room",  {3},       1.00),  # floor 4 only (0-indexed), guaranteed
    ]

    def _roll_special_rooms(self, floor_num, zone, special_rooms_spawned):
        """Roll for special rooms on this floor. Returns set of room indices claimed."""
        claimed = set()
        # Need at least 3 rooms (room 0 is player spawn, need 1+ for normal + 1 for special)
        available_indices = [i for i in range(1, len(self.rooms)) if i not in claimed]

        for room_key, eligible_floors, chance in self.SPECIAL_ROOM_DEFS:
            if room_key in special_rooms_spawned:
                continue  # already spawned this game
            if floor_num not in eligible_floors:
                continue
            if random.random() > chance:
                continue
            if not available_indices:
                break

            # Jerome's room needs the largest available room (many entities to fit)
            if room_key == "jerome_room":
                large = [i for i in available_indices
                         if len(self.rooms[i].floor_tiles(self)) >= 20]
                if not large:
                    continue  # no room large enough; skip this floor
                room_idx = max(large, key=lambda i: len(self.rooms[i].floor_tiles(self)))
            else:
                # Pick a room — prefer smaller rooms for niglet den, larger for smoke lounge
                room_idx = random.choice(available_indices)

            room = self.rooms[room_idx]
            floor_tiles = room.floor_tiles(self)
            if not floor_tiles or len(floor_tiles) < 6:
                continue

            if room_key == "niglet_den":
                self._spawn_niglet_den(room, floor_tiles)
            elif room_key == "smoke_lounge":
                self._spawn_smoke_lounge(room, floor_tiles, zone)
            elif room_key == "jerome_room":
                self._spawn_jerome_room(room, floor_tiles)

            special_rooms_spawned.add(room_key)
            claimed.add(room_idx)
            available_indices = [i for i in available_indices if i not in claimed]

        return claimed

    def _spawn_niglet_den(self, room, floor_tiles):
        """Spawn a trap room packed with niglets. No loot — pure punishment."""
        room_tile_set = frozenset(floor_tiles)
        count = random.randint(5, 8)
        for _ in range(count):
            free = [(x, y) for x, y in floor_tiles if not self.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            monster = create_enemy("niglet", x, y)
            monster.spawn_room_tiles = room_tile_set
            self.entities.append(monster)

    def _spawn_smoke_lounge(self, room, floor_tiles, zone):
        """Spawn a lounge guarded by thugs with guaranteed smoking/rolling drops."""
        room_tile_set = frozenset(floor_tiles)

        # Spawn 2-3 thugs
        thug_count = random.randint(2, 3)
        for _ in range(thug_count):
            free = [(x, y) for x, y in floor_tiles if not self.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            monster = create_enemy("thug", x, y)
            monster.spawn_room_tiles = room_tile_set
            self.entities.append(monster)

        # Guaranteed loot drops
        loot_list = []

        # 1 grinder
        loot_list.append(("grinder", None))

        # 2-3 rolling papers
        for _ in range(random.randint(2, 3)):
            loot_list.append(("rolling_paper", None))

        # 2-3 kush (random strains)
        for _ in range(random.randint(2, 3)):
            strain = random.choice(STRAINS)
            loot_list.append(("kush", strain))

        # 1-2 joints (random strains)
        for _ in range(random.randint(1, 2)):
            strain = random.choice(STRAINS)
            loot_list.append(("joint", strain))

        # 1-2 weed nugs (random strains)
        for _ in range(random.randint(1, 2)):
            strain = random.choice(STRAINS)
            loot_list.append(("weed_nug", strain))

        # 1-2 chickens (food)
        for _ in range(random.randint(1, 2)):
            loot_list.append(("chicken", None))

        # Place loot on free tiles in the room
        for item_id, strain in loot_list:
            free = [(x, y) for x, y in floor_tiles if not self.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            kwargs = create_item_entity(item_id, x, y, strain=strain)
            self.entities.append(Entity(**kwargs))

    def _spawn_jerome_room(self, room, floor_tiles):
        """Spawn Jerome's guarded chamber on floor 4.

        Layout (y-axis, top=min_y, bottom=max_y):
          Back  (max_y row) — Jerome stands here, a door entity is placed in
                              the wall tile just behind him.
          Front (min_y half) — 2 Thugs + 2 Drug Dealers (each brings tweakers).
        """
        room_tile_set = frozenset(floor_tiles)

        min_x = min(x for x, y in floor_tiles)
        max_x = max(x for x, y in floor_tiles)
        min_y = min(y for x, y in floor_tiles)
        max_y = max(y for x, y in floor_tiles)
        center_x = (min_x + max_x) // 2
        mid_y    = (min_y + max_y) // 2

        # ── Door entity + 2×2 back room ──────────────────────────────────
        door_x = center_x
        door_y = max_y + 1  # one tile into the back wall

        if 0 < door_y < self.height - 3:  # need 3 more rows for door + 2×2 room
            # Carve the door tile
            self.tiles[door_y][door_x] = TILE_FLOOR
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
            self.entities.append(door_entity)

            # Carve 2×2 room behind the door
            room_left  = door_x - 1
            room_right = door_x
            room_top   = door_y + 1
            room_bot   = door_y + 2
            back_room_tiles = []
            for ry in range(room_top, room_bot + 1):
                for rx in range(room_left, room_right + 1):
                    if 0 < rx < self.width - 1 and 0 < ry < self.height - 1:
                        self.tiles[ry][rx] = TILE_FLOOR
                        back_room_tiles.append((rx, ry))

            # Place meth_zone_stairs in the back room
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
                self.entities.append(stairs)

        # ── Jerome: back row, centered, one tile in front of the door ────
        jerome_x = center_x
        jerome_y = max_y
        # Shift jerome_x slightly if the center tile is already blocked
        for candidate_x in [center_x, center_x - 1, center_x + 1,
                             center_x - 2, center_x + 2]:
            if (candidate_x, jerome_y) in room_tile_set and \
               not self.is_blocked(candidate_x, jerome_y):
                jerome_x = candidate_x
                break
        jerome = create_enemy("big_nigga_jerome", jerome_x, jerome_y)
        jerome.spawn_room_tiles = room_tile_set
        self.entities.append(jerome)

        # ── Front group: 2 thugs + 2 drug dealers (each with tweakers) ──
        front_tiles = [(x, y) for x, y in floor_tiles if y <= mid_y]
        if not front_tiles:
            front_tiles = floor_tiles  # fallback

        # Thugs
        for _ in range(2):
            free = [(x, y) for x, y in front_tiles if not self.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            thug = create_enemy("thug", x, y)
            thug.spawn_room_tiles = room_tile_set
            self.entities.append(thug)

        # Drug dealers + their tweaker escorts
        for _ in range(2):
            free = [(x, y) for x, y in front_tiles if not self.is_blocked(x, y)]
            if not free:
                break
            x, y = random.choice(free)
            dealer = create_enemy("drug_dealer", x, y)
            dealer.spawn_room_tiles = room_tile_set
            self.entities.append(dealer)

            # Spawn tweakers around each dealer (1–3 per dealer)
            tweaker_count = random.randint(1, 3)
            for _ in range(tweaker_count):
                nearby = [
                    (nx, ny) for nx, ny in floor_tiles
                    if abs(nx - x) <= 4 and abs(ny - y) <= 4
                    and not self.is_blocked(nx, ny)
                ]
                if not nearby:
                    break
                ex, ey = random.choice(nearby)
                tweaker = create_enemy("tweaker", ex, ey)
                tweaker.spawn_room_tiles = room_tile_set
                tweaker.leader   = dealer
                tweaker.ai_type  = "escort"
                tweaker.ai_state = None
                self.entities.append(tweaker)

    def is_terrain_blocked(self, x, y):
        """Check if terrain alone blocks a tile (ignores entities)."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return self.tiles[y][x] == TILE_WALL

    def is_blocked(self, x, y):
        """Check if a tile is blocked by wall or entity."""
        if self.is_terrain_blocked(x, y):
            return True
        # Only living entities with blocks_movement=True block a tile
        return any(e.x == x and e.y == y and getattr(e, "alive", True) and e.blocks_movement for e in self.entities)

    def get_entity_at(self, x, y):
        """Get first entity at position, if any."""
        for entity in self.entities:
            if entity.x == x and entity.y == y:
                return entity
        return None

    def get_blocking_entity_at(self, x, y):
        """Get the blocking entity at position, if any."""
        for entity in self.entities:
            if entity.x == x and entity.y == y and entity.blocks_movement and getattr(entity, "alive", True):
                return entity
        return None

    def get_entities_at(self, x, y):
        """Get all entities at a position."""
        return [e for e in self.entities if e.x == x and e.y == y]

    def get_monsters(self):
        """Get all monster entities."""
        return [e for e in self.entities if e.entity_type == "monster"]

    def add_entity(self, entity):
        """Add an entity to the dungeon."""
        self.entities.append(entity)

    def move_entity(self, entity, new_x, new_y):
        """Move an entity to a new position."""
        entity.x = new_x
        entity.y = new_y

    def compute_fov(self, x, y, radius=8):
        """Compute field of view using tcod symmetric shadowcasting. Walls and
        entities with blocks_fov=True (e.g. closed doors) block LOS."""
        transparency = np.array(self.tiles, dtype=np.int8) != TILE_WALL

        # Overlay entity-based FOV blockers (e.g. closed doors)
        for entity in self.entities:
            if getattr(entity, "blocks_fov", False) and getattr(entity, "alive", True):
                if 0 <= entity.y < self.height and 0 <= entity.x < self.width:
                    transparency[entity.y, entity.x] = False

        self.visible = tcod.map.compute_fov(
            transparency,
            (y, x),
            radius=radius,
            light_walls=True,
            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST,
        )
        self.explored |= self.visible

        # Landmark reveal: first time player sees a reveals_on_sight entity, mark it always_visible.
        self.newly_revealed_landmarks = []
        for entity in self.entities:
            if (
                entity.reveals_on_sight
                and not entity.always_visible
                and entity.alive
                and self.visible[entity.y, entity.x]
            ):
                entity.always_visible = True
                self.newly_revealed_landmarks.append(entity)

    def remove_entity(self, entity):
        """Remove entity from dungeon."""
        if entity in self.entities:
            self.entities.remove(entity)
