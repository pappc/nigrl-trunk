"""
Dungeon generation and map management.
"""

import random
import numpy as np
import tcod
from config import (
    TILE_WALL,
    TILE_FLOOR,
)
from entity import Entity


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

    def __init__(self, width, height, zone="crack_den"):
        self.width = width
        self.height = height
        self.zone = zone
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

        from zone_generators import ZONE_GENERATORS
        gen = ZONE_GENERATORS[zone]["generate"]
        gen(self)

    def _carve_wide_corridor(self, from_point, to_point, width):
        """Carve an L-shaped corridor with a given tile width."""
        x1, y1 = from_point
        x2, y2 = to_point
        half = width // 2

        if random.choice([True, False]):
            # Horizontal first, then vertical
            for x in range(min(x1, x2), max(x1, x2) + 1):
                for dy in range(-half, -half + width):
                    ny = y1 + dy
                    if 0 <= x < self.width and 0 <= ny < self.height:
                        self.tiles[ny][x] = TILE_FLOOR
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for dx in range(-half, -half + width):
                    nx = x2 + dx
                    if 0 <= nx < self.width and 0 <= y < self.height:
                        self.tiles[y][nx] = TILE_FLOOR
        else:
            # Vertical first, then horizontal
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for dx in range(-half, -half + width):
                    nx = x1 + dx
                    if 0 <= nx < self.width and 0 <= y < self.height:
                        self.tiles[y][nx] = TILE_FLOOR
            for x in range(min(x1, x2), max(x1, x2) + 1):
                for dy in range(-half, -half + width):
                    ny = y2 + dy
                    if 0 <= x < self.width and 0 <= ny < self.height:
                        self.tiles[ny][x] = TILE_FLOOR

    def _place_tables(self, room):
        """Place 0-3 rectangular tables inside a room.
        Tables block movement but not FOV."""
        # Skip very small rooms
        room_w = room.x2 - room.x1
        room_h = room.y2 - room.y1
        if room_w < 6 or room_h < 6:
            return

        num_tables = random.choices([0, 1, 2, 3], weights=[2, 4, 3, 1])[0]

        for _ in range(num_tables):
            # Table dimensions: 1-3 wide, 1-3 tall
            tw = random.randint(1, 3)
            th = random.randint(1, 3)

            # Try to place with 1-tile margin from walls
            for _attempt in range(20):
                tx = random.randint(room.x1 + 1, room.x2 - tw - 1)
                ty = random.randint(room.y1 + 1, room.y2 - th - 1)

                # Check all table tiles are floor and unoccupied
                valid = True
                for dy in range(th):
                    for dx in range(tw):
                        px, py = tx + dx, ty + dy
                        if not (0 <= px < self.width and 0 <= py < self.height):
                            valid = False
                            break
                        if self.tiles[py][px] != TILE_FLOOR:
                            valid = False
                            break
                        if self.is_blocked(px, py):
                            valid = False
                            break
                    if not valid:
                        break
                if not valid:
                    continue

                # Place table entities
                table_color = (255, 255, 255) if getattr(self, "zone", "crack_den") == "meth_lab" else (139, 119, 101)
                for dy in range(th):
                    for dx in range(tw):
                        px, py = tx + dx, ty + dy
                        table = Entity(
                            x=px, y=py,
                            char="\u2588",  # full block character
                            color=table_color,
                            name="Table",
                            entity_type="hazard",
                            hazard_type="table",
                            blocks_movement=True,
                            blocks_fov=False,
                        )
                        self.entities.append(table)
                break  # placed successfully

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

    def _spawn_staircase_for_zone(self, zone: str, floor_num: int):
        """Conditionally spawn a staircase based on zone/floor rules."""
        from config import get_total_floors, ZONE_ORDER
        cumulative = 0
        for z in ZONE_ORDER:
            if z["key"] == zone:
                global_floor = cumulative + floor_num
                break
            cumulative += z["floors"]
        is_final_floor = (global_floor >= get_total_floors() - 1)
        is_jerome_floor = (zone == "crack_den" and floor_num == 3)
        if not is_final_floor and not is_jerome_floor:
            self._spawn_staircase()

    def _build_room_tile_map(self):
        """Map each floor tile to the room index it belongs to."""
        self.room_tile_map = {}
        for room_idx, room in enumerate(self.rooms):
            for x, y in room.floor_tiles(self):
                self.room_tile_map[(x, y)] = room_idx

    def get_room_index_at(self, x: int, y: int) -> "int | None":
        """Return the room index at (x, y), or None if in a corridor."""
        return self.room_tile_map.get((x, y))

    def get_hallway_tiles(self) -> list[tuple[int, int]]:
        """Return all walkable floor tiles that are NOT inside any room (i.e. corridor tiles)."""
        hallway = []
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x] == TILE_FLOOR and (x, y) not in self.room_tile_map:
                    hallway.append((x, y))
        return hallway

    def spawn_entities(self, player, floor_num=0, zone="crack_den", player_skills=None, player_stats=None, special_rooms_spawned=None):
        """Spawn monsters and items in rooms. Delegates to zone-specific spawner."""
        from zone_generators import ZONE_GENERATORS
        spawner = ZONE_GENERATORS[zone]["spawn"]
        spawner(self, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned)

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
