"""
NIGRL - A small roguelike game using tcod.

Traditional roguelike inspired by Rogue, Angband, Brogue, and Cataclysm: DDA.
"""

import os
import sys
import tcod
from config import SCREEN_WIDTH, SCREEN_HEIGHT
from engine import GameEngine
from enemies import validate_registry
from input_handler import handle_input
from render import render_all


def main():
    """Main game loop."""
    try:
        tileset_path = os.path.join(os.path.dirname(__file__), "nigrl-ascii-v3.png")
        tileset = tcod.tileset.load_tilesheet(tileset_path, 16, 16, tcod.tileset.CHARMAP_CP437)

        context = tcod.context.new(
            columns=SCREEN_WIDTH,
            rows=SCREEN_HEIGHT,
            title="NIGRL - Roguelike",
            tileset=tileset,
            vsync=True,
        )

        console = tcod.console.Console(SCREEN_WIDTH, SCREEN_HEIGHT, order="F")

        with context:
            validate_registry()
            engine = GameEngine()

            while engine.is_running():
                console.clear()
                render_all(console, engine)
                context.present(console)

                for event in tcod.event.wait():
                    if isinstance(event, tcod.event.Quit):
                        engine.running = False
                    else:
                        action = handle_input(event)
                        engine.process_action(action)

    except FileNotFoundError as e:
        print("Error: Could not load tileset. Make sure rl-ascii.png is in the same directory as nigrl.py")
        print(f"Details: {e}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
