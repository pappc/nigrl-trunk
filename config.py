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

# Dungeon generation
ROOM_MIN_SIZE = 6
ROOM_MAX_SIZE = 15
MAX_ROOMS = 23

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
EQUIPMENT_SLOTS = ["weapon"]  # dedicated ring slots handled separately
RING_SLOTS = 5                # number of simultaneous rings
RING_FINGER_NAMES = [
    "Right Pinky",
    "Right Ring",
    "Right Middle",
    "Right Index",
    "Right Thumb",
]

# Zone damage multipliers — scales ALL attack damage in the zone (default 1.0)
ZONE_DAMAGE_MULT = {
    "crack_den": 0.5,
}

# Jaywalking skill XP zone multipliers (zone_key -> float)
ZONE_JAYWALK_MULT = {
    "crack_den": 1.0,
}

# Blackkk Magic skill XP zone multipliers (zone_key -> float)
ZONE_BLACKK_MAGIC_MULT = {
    "crack_den": 2.0,
}

# Inventory key labels — letters available for item selection.
# Lowercase (19): excludes a (Abilities), c (char sheet), d (drop), e (equipment),
#                 f (firing), q (quit), s (skills)
# Uppercase/Shift (22): excludes Shift+B (bestiary), Shift+D (destroy), Shift+L (log),
#                       Shift+P (perks), Shift+` (dev menu), Shift+. (stairs)
# RULE: if a Shift+letter is later bound to a feature, remove it from INVENTORY_KEYS here.
INVENTORY_KEYS = "bghijklmnoprtuvwxyz" + "ACEFGHIJKMOQRSTUVWXYZ"
