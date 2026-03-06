"""
Input handling for player actions.
"""

import tcod
from config import INVENTORY_KEYS


def handle_input(key):
    """Convert tcod key event to action dict."""
    if isinstance(key, tcod.event.KeyDown):
        key_sym = key.sym

        # Movement
        if key_sym == tcod.event.KeySym.UP:
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
        elif key_sym == tcod.event.KeySym.KP_5:
            return {"type": "wait"}

        # Skills menu
        elif key_sym == tcod.event.KeySym.s:
            return {"type": "toggle_skills"}

        # Skills menu navigation (always emitted; engine ignores outside SKILLS state)
        elif key_sym == tcod.event.KeySym.BACKSPACE:
            return {"type": "skills_backspace"}

        # Character sheet
        elif key_sym == tcod.event.KeySym.c:
            return {"type": "open_char_sheet"}

        # Equipment screen
        elif key_sym == tcod.event.KeySym.e:
            return {"type": "open_equipment"}


        # Escape — close any open menu
        elif key_sym == tcod.event.KeySym.ESCAPE:
            return {"type": "close_menu"}

        # Number keys 0-9 — action selection in menus or skills spend input
        elif tcod.event.KeySym.N0 <= key_sym <= tcod.event.KeySym.N9:
            digit = str(key_sym - tcod.event.KeySym.N0)
            index = 9 if key_sym == tcod.event.KeySym.N0 else key_sym - tcod.event.KeySym.N1
            return {"type": "select_action", "index": index, "digit": digit}

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

        # Enter — confirm targeting
        elif key_sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
            return {"type": "confirm_target"}

        # F — enter entity targeting mode
        elif key_sym == tcod.event.KeySym.f:
            return {"type": "start_entity_targeting"}

        # A — toggle Abilities menu (checked before inventory letter keys)
        elif key_sym == tcod.event.KeySym.a:
            return {"type": "toggle_abilities"}

        # Letter keys — inventory item selection (only keys in INVENTORY_KEYS)
        elif tcod.event.KeySym.a <= key_sym <= tcod.event.KeySym.z:
            char = chr(ord("a") + (key_sym - tcod.event.KeySym.a))
            if char in INVENTORY_KEYS:
                index = INVENTORY_KEYS.index(char)
                return {"type": "select_item", "index": index}

    return None
