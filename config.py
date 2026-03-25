# Game configuration constants

# Developer mode — set to False before shipping to players
DEV_MODE = True

# Screen dimensions (120×68 tiles × 16px = 1920×1088, nearest 16px fit to 1080p)
SCREEN_WIDTH = 120
SCREEN_HEIGHT = 68

# Left stats panel (Character / Health / Status)
LEFT_PANEL_WIDTH = 22
MAP_OFFSET_X     = LEFT_PANEL_WIDTH   # dungeon & entities render starting at this column

# Map/panel split (SCREEN_WIDTH = LEFT_PANEL_WIDTH + MAP_WIDTH + PANEL_WIDTH)
MAP_WIDTH   = 68
PANEL_WIDTH = 30

# Dungeon dimensions
DUNGEON_WIDTH  = MAP_WIDTH  # keep in sync with MAP_WIDTH
DUNGEON_HEIGHT = 54

# Dungeon generation (defaults — zones can override via ZONE_GENERATION_PARAMS)
ROOM_MIN_SIZE = 6
ROOM_MAX_SIZE = 15
MAX_ROOMS = 23

# Per-zone generation parameters.
# Each zone can override: room_min, room_max, max_rooms, corridor_width, room_shapes.
# Missing keys fall back to the top-level defaults above.
ZONE_GENERATION_PARAMS = {
    "crack_den": {
        "room_min": ROOM_MIN_SIZE,
        "room_max": ROOM_MAX_SIZE,
        "max_rooms": MAX_ROOMS,
        "corridor_width": 1,
    },
    "meth_lab": {
        "room_min": 8,
        "room_max": 18,
        "max_rooms": 16,          # fewer but bigger rooms
        "corridor_width": 2,      # 2-tile wide hallways
    },
    "tyrones_penthouse": {
        "room_min": 10,
        "room_max": 10,
        "max_rooms": 1,
        "corridor_width": 1,
    },
}

# Convenience accessor
def get_zone_gen_param(zone: str, key: str):
    """Get a generation parameter for a zone, falling back to defaults."""
    defaults = {"room_min": ROOM_MIN_SIZE, "room_max": ROOM_MAX_SIZE,
                "max_rooms": MAX_ROOMS, "corridor_width": 1}
    return ZONE_GENERATION_PARAMS.get(zone, {}).get(key, defaults.get(key))

# Legacy aliases (kept for any straggling references)
ML_ROOM_MIN_SIZE = ZONE_GENERATION_PARAMS["meth_lab"]["room_min"]
ML_ROOM_MAX_SIZE = ZONE_GENERATION_PARAMS["meth_lab"]["room_max"]
ML_MAX_ROOMS = ZONE_GENERATION_PARAMS["meth_lab"]["max_rooms"]
ML_CORRIDOR_WIDTH = ZONE_GENERATION_PARAMS["meth_lab"]["corridor_width"]

# Entity spawning
MAX_MONSTERS_PER_ROOM = 3
MAX_ITEMS_PER_ROOM = 4

# Player field of view
FOV_RADIUS = 9   # base light radius; increase via items/buffs with engine.fov_radius

# Energy / tick system
ENERGY_THRESHOLD = 100   # energy needed to take an action
PLAYER_BASE_SPEED = 100  # energy gained per tick at baseline

# Combat defaults
BASE_POWER = 4      # unarmed (fists) base damage
BASE_DEFENSE = 1
BASE_HP = 30
MIN_DAMAGE = 1      # floor on all damage rolls
UNARMED_STR_BASE = 5  # STR baseline for unarmed damage bonus (bonus = STR - this)

# Tile types
TILE_WALL = 0
TILE_FLOOR = 1

# UI positioning
HEADER_HEIGHT = 1
UI_HEIGHT = 13
MAX_MESSAGES = 11         # messages visible in the bottom panel (UI_HEIGHT - 2, bottom row is border)
LOG_HISTORY_SIZE = 200    # total messages kept in memory for the log menu

# Equipment slots
EQUIPMENT_SLOTS = ["weapon", "sidearm"]  # dedicated ring slots handled separately
RING_SLOTS = 5                # number of simultaneous rings
RING_FINGER_NAMES = [
    "Right Pinky",
    "Right Ring",
    "Right Middle",
    "Right Index",
    "Right Thumb",
]

# ---------------------------------------------------------------------------
# Zone progression
# ---------------------------------------------------------------------------

ZONE_ORDER = [
    {"key": "crack_den",          "display": "Crack Den",          "floors": 4, "type": "zone"},
    {"key": "tyrones_penthouse",  "display": "Tyrone's Penthouse", "floors": 1, "type": "pseudozone"},
    {"key": "meth_lab",           "display": "Meth Lab",           "floors": 7, "type": "zone"},
]


def get_total_floors():
    """Return the total number of floors across all zones."""
    return sum(z["floors"] for z in ZONE_ORDER)


def get_zone_for_floor(global_floor):
    """Map a global floor index to zone info.

    Returns (zone_key, zone_floor_num, display_name, zone_type).
    """
    cumulative = 0
    for zone in ZONE_ORDER:
        if global_floor < cumulative + zone["floors"]:
            return (zone["key"], global_floor - cumulative, zone["display"], zone["type"])
        cumulative += zone["floors"]
    # Past the last floor — clamp to final zone's last floor
    last = ZONE_ORDER[-1]
    return (last["key"], last["floors"] - 1, last["display"], last["type"])


def get_zone_total_floors(zone_key):
    """Return the number of floors in a specific zone."""
    for zone in ZONE_ORDER:
        if zone["key"] == zone_key:
            return zone["floors"]
    return 0


# ---------------------------------------------------------------------------
# Random floor events — per-zone pools of special events that modify a floor.
# Each game, one floor is chosen at random and one event is assigned to it.
# The event_id is stored on the engine and passed to dungeon generation.
# ---------------------------------------------------------------------------
FLOOR_EVENT_REGISTRY = {
    "spider_infestation": {
        "name": "Infested with Spiders",
        "message": "The floor appears to be infested by spiders.",
    },
    "stench_of_death": {
        "name": "Smells Like Rotting Flesh",
        "message": "The air reeks of rotting flesh. Shambling figures lurch in the shadows...",
    },
    "occult_occupation": {
        "name": "Inhabited by the Occult",
        "message": "This area is inhabited by the occult. You sense a dark presence below...",
    },
}

# Per-zone: which zone_floors can have events, and which event IDs are in the pool.
ZONE_FLOOR_EVENTS = {
    "crack_den": {
        "eligible_floors": [1, 2],   # zone_floor indices (2nd and 3rd floor)
        "event_pool": ["spider_infestation", "stench_of_death", "occult_occupation"],
    },
}


# Zone damage multipliers — scales ALL attack damage in the zone (default 1.0)
ZONE_DAMAGE_MULT = {
    "crack_den": 0.5,
    "tyrones_penthouse": 1.0,
    "meth_lab": 1.0,
}

# Jaywalking skill XP zone multipliers (zone_key -> float)
ZONE_JAYWALK_MULT = {
    "crack_den": 1.0,
    "tyrones_penthouse": 1.0,
    "meth_lab": 1.5,
}

# Smartsness skill XP zone multipliers (zone_key -> float)
ZONE_SMARTSNESS_MULT = {
    "crack_den": 2.0,
    "tyrones_penthouse": 1.0,
    "meth_lab": 2.5,
}

# Per-zone visual color schemes for map rendering.
# Each zone defines colors for walls and floors in visible/explored states,
# plus header bar colors. Wall colors are base values — render.py adds noise.
# New zones: add an entry here; render.py picks it up automatically.
ZONE_COLORS = {
    "crack_den": {
        "header_bg": (45, 32, 12),
        "header_fg": (220, 190, 120),
        # Visible tiles
        "wall_fg_base": (128, 108, 80),       # warm ochre-gray
        "wall_bg": (22, 17, 12),
        "floor_bg": (36, 28, 19),             # stained concrete — warm dark brown
        # Explored (dimmed) tiles
        "explored_wall_fg_base": (42, 34, 24),
        "explored_wall_bg": (9, 7, 4),
        "explored_floor_bg": (14, 11, 7),
    },
    "tyrones_penthouse": {
        "header_bg": (45, 32, 12),
        "header_fg": (220, 190, 120),
        "wall_fg_base": (128, 108, 80),
        "wall_bg": (22, 17, 12),
        "floor_bg": (36, 28, 19),
        "explored_wall_fg_base": (42, 34, 24),
        "explored_wall_bg": (9, 7, 4),
        "explored_floor_bg": (14, 11, 7),
    },
    "meth_lab": {
        "header_bg": (50, 50, 52),
        "header_fg": (210, 210, 210),
        # Visible tiles — clean white walls, grey concrete floors
        "wall_fg_base": (210, 210, 210),
        "wall_bg": (30, 30, 32),
        "floor_bg": (50, 50, 52),
        # Explored (dimmed) tiles
        "explored_wall_fg_base": (70, 70, 70),
        "explored_wall_bg": (12, 12, 13),
        "explored_floor_bg": (20, 20, 21),
    },
}

# Fallback color scheme for zones not in ZONE_COLORS
_DEFAULT_ZONE_COLORS = ZONE_COLORS["crack_den"]


def get_zone_colors(zone: str) -> dict:
    """Get the color scheme for a zone, falling back to crack_den defaults."""
    return ZONE_COLORS.get(zone, _DEFAULT_ZONE_COLORS)

# Inventory key labels — letters available for item selection.
# Lowercase (18): excludes a (Abilities), c (char sheet), d (drop), e (equipment),
#                 f (fire gun), q (quit), r (reach/entity targeting), s (skills)
# Uppercase/Shift (19): excludes Shift+B (bestiary), Shift+D (destroy), Shift+F (swap gun),
#                       Shift+L (log), Shift+P (perks), Shift+R (reload),
#                       Shift+` (dev menu), Shift+. (stairs)
# RULE: if a Shift+letter is later bound to a feature, remove it from INVENTORY_KEYS here.
INVENTORY_KEYS = "bghijklmnoptuvwxyz" + "ACEGHIJKMOQSTUVWXYZ"
