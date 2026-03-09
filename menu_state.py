"""
Menu state enum — single source of truth for which UI overlay is active.
"""

from enum import Enum


class MenuState(Enum):
    NONE = "none"
    SKILLS = "skills"
    CHAR_SHEET = "char_sheet"
    EQUIPMENT = "equipment"
    ITEM_MENU = "item_menu"
    COMBINE_SELECT = "combine_select"
    LOG = "log"
    DESTROY_CONFIRM = "destroy_confirm"
    BESTIARY = "bestiary"
    TARGETING = "targeting"
    ABILITIES = "abilities"
    RING_REPLACE = "ring_replace"
    ENTITY_TARGETING = "entity_targeting"
    PERKS = "perks"
    DEV_MENU = "dev_menu"
    DEV_ITEM_SELECT = "dev_item_select"
    ADJACENT_TILE_TARGETING = "adjacent_tile_targeting"
    EXAMINE = "examine"
    DEATH_SCREEN = "death_screen"
