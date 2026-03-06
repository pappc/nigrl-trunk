# Game configuration constants

# Screen dimensions
SCREEN_WIDTH = 114
SCREEN_HEIGHT = 64

# Left stats panel (Character / Health / Status)
LEFT_PANEL_WIDTH = 20
MAP_OFFSET_X     = LEFT_PANEL_WIDTH   # dungeon & entities render starting at this column

# Map/panel split (SCREEN_WIDTH = LEFT_PANEL_WIDTH + MAP_WIDTH + PANEL_WIDTH)
MAP_WIDTH   = 66
PANEL_WIDTH = 28

# Dungeon dimensions
DUNGEON_WIDTH  = MAP_WIDTH
DUNGEON_HEIGHT = 55

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
UI_HEIGHT = 8
MAX_MESSAGES = 7          # messages visible in the bottom panel (UI_HEIGHT - 1)
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

# Inventory key labels — letters available for item selection.
# Excludes keys already bound to menus: c (char sheet), e (equipment), s (skills)
INVENTORY_KEYS = "bdfghijklmnopqrtuvwxyz"  # 'a' reserved for Abilities menu
