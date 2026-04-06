"""
Input handling for player actions.
"""

import tcod
from config import INVENTORY_KEYS, DEV_MODE


def handle_input(key):
    """Convert tcod key event to action dict."""
    if isinstance(key, tcod.event.KeyDown):
        key_sym = key.sym

        # Shift+Up/Down — inventory page scroll (before plain arrow movement)
        _shift = bool(key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT))
        if _shift and key_sym == tcod.event.KeySym.UP:
            return {"type": "inventory_page_up"}
        elif _shift and key_sym == tcod.event.KeySym.DOWN:
            return {"type": "inventory_page_down"}

        # Movement
        elif key_sym == tcod.event.KeySym.UP:
            return {"type": "move", "dx": 0, "dy": -1}
        elif key_sym == tcod.event.KeySym.DOWN:
            return {"type": "move", "dx": 0, "dy": 1}
        elif key_sym == tcod.event.KeySym.LEFT:
            return {"type": "move", "dx": -1, "dy": 0}
        elif key_sym == tcod.event.KeySym.RIGHT:
            return {"type": "move", "dx": 1, "dy": 0}

        # Numpad movement
        elif key_sym == tcod.event.KeySym.KP_8:
            return {"type": "move", "dx": 0, "dy": -1}
        elif key_sym == tcod.event.KeySym.KP_2:
            return {"type": "move", "dx": 0, "dy": 1}
        elif key_sym == tcod.event.KeySym.KP_4:
            return {"type": "move", "dx": -1, "dy": 0}
        elif key_sym == tcod.event.KeySym.KP_6:
            return {"type": "move", "dx": 1, "dy": 0}
        elif key_sym == tcod.event.KeySym.KP_7:
            return {"type": "move", "dx": -1, "dy": -1}
        elif key_sym == tcod.event.KeySym.KP_9:
            return {"type": "move", "dx": 1, "dy": -1}
        elif key_sym == tcod.event.KeySym.KP_1:
            return {"type": "move", "dx": -1, "dy": 1}
        elif key_sym == tcod.event.KeySym.KP_3:
            return {"type": "move", "dx": 1, "dy": 1}

        # Wait a turn
        elif key_sym == tcod.event.KeySym.KP_5 or (
            key_sym == tcod.event.KeySym.PERIOD
            and not bool(key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT))
        ):
            return {"type": "wait"}

        # Skills menu (lowercase only)
        elif key_sym == tcod.event.KeySym.s and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "toggle_skills"}

        # Skills menu navigation (always emitted; engine ignores outside SKILLS state)
        elif key_sym == tcod.event.KeySym.BACKSPACE:
            return {"type": "skills_backspace"}

        # Character sheet (lowercase only)
        elif key_sym == tcod.event.KeySym.c and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_char_sheet"}

        # Equipment screen (lowercase only)
        elif key_sym == tcod.event.KeySym.e and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_equipment"}


        # Escape — close any open menu
        elif key_sym == tcod.event.KeySym.ESCAPE:
            return {"type": "close_menu"}

        # Shift+Number — hotbar bind to slot
        elif tcod.event.KeySym.N0 <= key_sym <= tcod.event.KeySym.N9 and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            index = 9 if key_sym == tcod.event.KeySym.N0 else key_sym - tcod.event.KeySym.N1
            return {"type": "hotbar_bind_slot", "index": index}

        # Number keys 0-9 — action selection in menus or skills spend input
        elif tcod.event.KeySym.N0 <= key_sym <= tcod.event.KeySym.N9:
            digit = str(key_sym - tcod.event.KeySym.N0)
            index = 9 if key_sym == tcod.event.KeySym.N0 else key_sym - tcod.event.KeySym.N1
            return {"type": "select_action", "index": index, "digit": digit}

        # Minus / Equals — hotbar slots 11-12
        elif key_sym == tcod.event.KeySym.MINUS:
            return {"type": "select_action", "index": 10, "digit": "-"}
        elif key_sym == tcod.event.KeySym.EQUALS:
            return {"type": "select_action", "index": 11, "digit": "="}

        # Descend stairs (> = Shift+Period; SDL2 on Windows reports PERIOD+shift,
        # other platforms may report GREATER directly)
        elif key_sym == tcod.event.KeySym.GREATER or (
            key_sym == tcod.event.KeySym.PERIOD
            and bool(key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT))
        ):
            return {"type": "descend_stairs"}

        # Shift+L — open log menu
        elif key_sym == tcod.event.KeySym.l and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_log"}

        # Shift+B — open bestiary
        elif key_sym == tcod.event.KeySym.b and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_bestiary"}

        # Shift+E — open status effects menu
        elif key_sym == tcod.event.KeySym.e and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_status_effects"}

        # Shift+P — open perks menu
        elif key_sym == tcod.event.KeySym.p and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_perks_menu"}

        # Shift+` — open dev tools menu (DEV_MODE only)
        elif DEV_MODE and key_sym == tcod.event.KeySym.GRAVE and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "open_dev_menu"}

        # Space — item use / confirm in menus
        elif key_sym == tcod.event.KeySym.SPACE:
            return {"type": "item_use"}

        # Shift+D — destroy item in item menu
        elif key_sym == tcod.event.KeySym.d and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "destroy_item"}

        # D (no shift) — drop item in item menu
        elif key_sym == tcod.event.KeySym.d:
            return {"type": "drop_item"}

        # Enter — confirm targeting
        elif key_sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
            return {"type": "confirm_target"}

        # Shift+F — swap primary gun
        elif key_sym == tcod.event.KeySym.f and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "swap_primary_gun"}

        # F (no shift) — fire gun
        elif key_sym == tcod.event.KeySym.f and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "fire_gun"}

        # Shift+R — reload gun
        elif key_sym == tcod.event.KeySym.r and bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "reload_gun"}

        # R (no shift) — enter entity targeting mode (reach weapons)
        elif key_sym == tcod.event.KeySym.r and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "start_entity_targeting"}

        # / — autoexplore (keyboard slash or numpad /)
        elif key_sym in (tcod.event.KeySym.SLASH, tcod.event.KeySym.KP_DIVIDE):
            return {"type": "autoexplore"}

        # ; — look mode (inspect tiles)
        elif key_sym == tcod.event.KeySym.SEMICOLON:
            return {"type": "look"}

        # PgDown — inventory page down
        elif key_sym == tcod.event.KeySym.PAGEDOWN:
            return {"type": "inventory_page_down"}
        # PgUp — inventory page up
        elif key_sym == tcod.event.KeySym.PAGEUP:
            return {"type": "inventory_page_up"}
        # Backslash — inventory next page (accessible alternative)
        elif key_sym == tcod.event.KeySym.BACKSLASH:
            return {"type": "inventory_page_down"}

        # A — toggle Abilities menu (lowercase only, checked before inventory letter keys)
        elif key_sym == tcod.event.KeySym.a and not bool(
            key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT)
        ):
            return {"type": "toggle_abilities"}

        # Letter keys — inventory item selection (lowercase + uppercase in INVENTORY_KEYS)
        elif tcod.event.KeySym.a <= key_sym <= tcod.event.KeySym.z:
            _is_shift = bool(key.mod & (tcod.event.Modifier.LSHIFT | tcod.event.Modifier.RSHIFT))
            if _is_shift:
                char = chr(ord("A") + (key_sym - tcod.event.KeySym.a))
            else:
                char = chr(ord("a") + (key_sym - tcod.event.KeySym.a))
            if char in INVENTORY_KEYS:
                index = INVENTORY_KEYS.index(char)
                return {"type": "select_item", "index": index, "char": char}
            else:
                # Unbound letter — emit raw char for dev search and future text input
                return {"type": "raw_char", "char": char}

    return None
