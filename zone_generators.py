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

def generate_crack_den(dungeon):
    """Place rooms randomly, then connect them all with MST corridors + extra connections."""
    from dungeon import build_mst, RectRoom, LRoom, URoom, TRoom, HallRoom, OctRoom, CrossRoom, DiamondRoom, CavernRoom, PillarRoom, CircleRoom

    attempts = 0
    max_attempts = MAX_ROOMS * 6

    while len(dungeon.rooms) < MAX_ROOMS and attempts < max_attempts:
        attempts += 1
        room = _random_crack_den_room(dungeon)
        if room is None:
            continue
        if any(room.intersects(other) for other in dungeon.rooms):
            continue
        room.carve(dungeon)
        dungeon.rooms.append(room)

    # Carve MST corridors (guaranteed connectivity)
    for i, j in build_mst(dungeon.rooms):
        dungeon.carve_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center())

    # Add extra connections for more interconnected layout
    if len(dungeon.rooms) > 2:
        for _ in range(len(dungeon.rooms) // 3):
            i = random.randint(0, len(dungeon.rooms) - 1)
            j = random.randint(0, len(dungeon.rooms) - 1)
            if i != j:
                dungeon.carve_corridor(dungeon.rooms[i].center(), dungeon.rooms[j].center())

    # Build room tile map after all corridors are carved
    dungeon._build_room_tile_map()


def _random_crack_den_room(dungeon):
    """Pick a random room shape and position for crack den."""
    from dungeon import RectRoom, LRoom, URoom, TRoom, HallRoom, OctRoom, CrossRoom, DiamondRoom, CavernRoom, PillarRoom, CircleRoom

    shape = random.choices(
        ["rect", "l", "u", "t", "hall", "oct", "cross", "diamond", "cavern", "pillar", "circle"],
        weights=[  6,   4,   4,   3,      5,      3,       2,          2,          2,       2,        1],
    )[0]

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


def spawn_crack_den(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned):
    """Spawn monsters, items, and cash for the Crack Den zone."""
    dungeon.zone = zone
    dungeon.entities.append(player)

    # Roll for special rooms and claim rooms before normal spawning
    special_room_indices = set()
    if special_rooms_spawned is not None:
        special_room_indices = _roll_special_rooms(dungeon, floor_num, zone, special_rooms_spawned)

    for room_idx, room in enumerate(dungeon.rooms[1:], start=1):
        if room_idx in special_room_indices:
            continue  # special rooms handle their own spawns

        floor_tiles = room.floor_tiles(dungeon)
        if not floor_tiles:
            continue

        # Zone-based monster spawning (per-floor weighted tables)
        zone_table = get_spawn_table(zone, floor_num)
        if zone_table:
            enemy_types   = [t[0] for t in zone_table]
            enemy_weights = [t[1] for t in zone_table]

            room_tile_set = frozenset(floor_tiles)

            # Dynamic monster count: size-scaling + floor bonus + populated/empty gate
            size_max = max(1, len(floor_tiles) // 10)
            floor_bonus = floor_num // 2
            room_max = size_max + floor_bonus

            # 65% populated, 35% empty
            if random.random() < 0.65:
                options = list(range(1, room_max + 1))
                weights = [max(1, room_max + 1 - i) for i in range(len(options))]
                n_groups = random.choices(options, weights=weights, k=1)[0]
            else:
                n_groups = 0

            for _ in range(n_groups):
                enemy_type = random.choices(enemy_types, weights=enemy_weights, k=1)[0]
                tmpl = MONSTER_REGISTRY[enemy_type]

                free = [(tx, ty) for tx, ty in floor_tiles if not dungeon.is_blocked(tx, ty)]
                if not free:
                    continue
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

    # ── Hallway spawning (zone-specific) ──────────────────────────────
    hallway_table = get_hallway_spawn_table(zone, floor_num)
    if hallway_table:
        hallway_tiles = dungeon.get_hallway_tiles()
        if hallway_tiles:
            h_types   = [t[0] for t in hallway_table]
            h_weights = [t[1] for t in hallway_table]

            n_hallway_monsters = max(1, min(8, len(hallway_tiles) // 15))

            for _ in range(n_hallway_monsters):
                free = [(hx, hy) for hx, hy in hallway_tiles
                        if not dungeon.is_blocked(hx, hy)]
                if not free:
                    break
                hx, hy = random.choice(free)
                h_enemy_type = random.choices(h_types, weights=h_weights, k=1)[0]
                h_monster = create_enemy(h_enemy_type, hx, hy)
                dungeon.entities.append(h_monster)

    # Spawn staircase
    dungeon._spawn_staircase_for_zone(zone, floor_num)

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

        if room_key == "jerome_room":
            large = [i for i in available_indices
                     if len(dungeon.rooms[i].floor_tiles(dungeon)) >= 20]
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

    # 2 Ugly Strippers with proximity_alarm AI
    for _ in range(2):
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        stripper = create_enemy("ugly_stripper", x, y)
        stripper.spawn_room_tiles = room_tile_set
        stripper.ai_type = "proximity_alarm"
        stripper.ai_state = None
        dungeon.entities.append(stripper)

    # Guaranteed loot: heavy weed payout
    loot_list = []
    loot_list.append(("grinder", None))
    for _ in range(random.randint(4, 5)):
        loot_list.append(("kush", random.choice(STRAINS)))
    for _ in range(3):
        loot_list.append(("joint", random.choice(STRAINS)))
    for _ in range(random.randint(2, 3)):
        loot_list.append(("pack_of_cones", None))
    for _ in range(2):
        loot_list.append(("weed_nug", random.choice(STRAINS)))

    for item_id, strain in loot_list:
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
        kwargs = create_item_entity(item_id, x, y, strain=strain)
        dungeon.entities.append(Entity(**kwargs))


def _spawn_dive_bar(dungeon, room, floor_tiles, zone):
    """The Dive Bar — 5 thugs + 1 proximity_alarm ugly stripper.
    Guaranteed full set of 6 alcohol drinks."""
    from loot import DRINKS_SUBTABLE
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

    # 1 Ugly Stripper with proximity_alarm AI
    free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
    if free:
        x, y = random.choice(free)
        stripper = create_enemy("ugly_stripper", x, y)
        stripper.spawn_room_tiles = room_tile_set
        stripper.ai_type = "proximity_alarm"
        stripper.ai_state = None
        dungeon.entities.append(stripper)

    # Guaranteed loot: 1 of each alcohol drink
    drink_ids = [drink_id for drink_id, _ in DRINKS_SUBTABLE]
    for drink_id in drink_ids:
        free = [(x, y) for x, y in floor_tiles if not dungeon.is_blocked(x, y)]
        if not free:
            break
        x, y = random.choice(free)
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
    door_x = center_x
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

    # ── Jerome: back row, centered ────
    jerome_x = center_x
    jerome_y = max_y
    for candidate_x in [center_x, center_x - 1, center_x + 1,
                         center_x - 2, center_x + 2]:
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


def spawn_meth_lab(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned):
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
    """Build a static 10x10 room for Tyrone's Penthouse.

    - Single room, centered in the map
    - No monsters, no loot
    """
    from dungeon import RectRoom

    rx = (dungeon.width - 10) // 2
    ry = (dungeon.height - 10) // 2
    room = RectRoom(rx, ry, 10, 10)
    room.carve(dungeon)
    dungeon.rooms.append(room)
    dungeon._build_room_tile_map()


def spawn_penthouse(dungeon, player, floor_num, zone, player_skills, player_stats, special_rooms_spawned):
    """Place player and stairs in the penthouse."""
    dungeon.zone = zone

    # Place player at room center
    cx, cy = dungeon.rooms[0].center()
    player.x = cx
    player.y = cy
    dungeon.entities.append(player)

    # Stairs down at far end of the room
    rx = (dungeon.width - 10) // 2
    sx, sy = cx, rx + 8  # match original: ry + 8 where ry = (height-10)//2
    # Recalculate properly
    ry = (dungeon.height - 10) // 2
    sx, sy = cx, ry + 8
    dungeon.entities.append(Entity(
        x=sx, y=sy,
        char=">",
        color=(255, 220, 80),
        name="Stairs Down",
        entity_type="staircase",
        blocks_movement=False,
        reveals_on_sight=True,
    ))


# ===================================================================
# Zone Generator Registry
# ===================================================================

ZONE_GENERATORS = {
    "crack_den":         {"generate": generate_crack_den,  "spawn": spawn_crack_den},
    "meth_lab":          {"generate": generate_meth_lab,   "spawn": spawn_meth_lab},
    "tyrones_penthouse": {"generate": generate_penthouse,  "spawn": spawn_penthouse},
}
