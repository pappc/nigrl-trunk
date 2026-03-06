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
    MAX_ITEMS_PER_ROOM,
    BASE_HP,
    BASE_POWER,
    BASE_DEFENSE,
)
from entity import Entity
from items import create_item_entity, get_random_chain, get_random_jordans, STRAINS
from enemies import create_enemy, ZONE_SPAWN_TABLES, MONSTER_REGISTRY


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_item_strain(item_id):
    """Return a random strain for cannabis items, None for others."""
    if item_id in ("weed_nug", "kush", "joint"):
        return random.choice(STRAINS)
    return None


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

        # Set to True the first time any monster dies on this floor.
        # Used by the alarm_chaser AI (ugly strippers).
        self.first_kill_happened = False

        # Set to True the first time a female monster dies on this floor.
        # Used by the female_alarm AI (fat gooners).
        self.female_kill_happened = False

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
            ))

    def spawn_entities(self, player, floor_num=0):
        """Spawn monsters and items in rooms."""
        self.entities.append(player)

        for room in self.rooms[1:]:
            floor_tiles = room.floor_tiles(self)
            if not floor_tiles:
                continue

            # Zone-based monster spawning
            zone_table = ZONE_SPAWN_TABLES.get("crack_den", [])
            if zone_table:
                enemy_types   = [t[0] for t in zone_table]
                enemy_weights = [t[1] for t in zone_table]

                # Precompute the frozenset of floor tiles for this room once,
                # so every monster spawned here can reference it cheaply.
                room_tile_set = frozenset(floor_tiles)

                for _ in range(random.randint(0, MAX_MONSTERS_PER_ROOM)):
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

            # Weighted item spawn table
            # "chain" and "jordans" are pseudo-ids resolved to random variants at spawn
            _ITEM_IDS     = ["knife", "weed_nug", "grinder", "rolling_paper", "kush", "joint", "chain", "jordans"]
            _ITEM_WEIGHTS = [     3,          4,         4,               3,       1,       1,       2,        2]

            for _ in range(random.randint(0, MAX_ITEMS_PER_ROOM)):
                x, y = random.choice(floor_tiles)
                if not self.is_blocked(x, y):
                    item_id = random.choices(_ITEM_IDS, weights=_ITEM_WEIGHTS, k=1)[0]
                    if item_id == "chain":
                        item_id = get_random_chain("crack_den")
                    elif item_id == "jordans":
                        item_id = get_random_jordans()
                    strain = _get_item_strain(item_id)
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
                if not self.is_blocked(x, y):
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

        # Spawn staircase on floors that aren't the last one (4 floors total: 0-3)
        if floor_num < 3:
            self._spawn_staircase()

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
        """Compute field of view using tcod symmetric shadowcasting. Walls block LOS."""
        transparency = np.array(self.tiles, dtype=np.int8) != TILE_WALL

        self.visible = tcod.map.compute_fov(
            transparency,
            (y, x),
            radius=radius,
            light_walls=True,
            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST,
        )
        self.explored |= self.visible

    def remove_entity(self, entity):
        """Remove entity from dungeon."""
        if entity in self.entities:
            self.entities.remove(entity)
