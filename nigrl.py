"""
NIGRL - A small roguelike game using tcod.

Traditional roguelike inspired by Rogue, Angband, Brogue, and Cataclysm: DDA.
"""

import os
import sys
import json
import base64
import io
import time
import tcod
import numpy as np
from PIL import Image as PilImage
from config import SCREEN_WIDTH, SCREEN_HEIGHT
from engine import GameEngine
from enemies import validate_registry
from input_handler import handle_input
from render import render_all


def _pad_to_16x16(arr: np.ndarray) -> np.ndarray:
    """Centre a small RGBA tile array on a 16×16 black canvas."""
    h, w = arr.shape[:2]
    canvas = np.zeros((16, 16, 4), dtype=np.uint8)
    off_y = (16 - h) // 2
    off_x = (16 - w) // 2
    canvas[off_y:off_y + h, off_x:off_x + w] = arr
    return canvas


def _inject_hazard_tiles(tileset):
    """Inject crate (0xE000) and fire (0xE001) tiles from asset files."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # Crate tile: crop from nigrl-tileset-2.png (col=26, row=34, 12×12 pixels)
    # Tileset pitch=13px per tile (12px tile + 1px border), origin at (0,0)
    try:
        ts2_path = os.path.join(base_dir, "nigrl-tileset-2.png")
        _ts2 = PilImage.open(ts2_path).convert("RGBA")
        _crate = np.array(_ts2.crop((339, 443, 351, 455)))  # 12×12 RGBA
        tileset.set_tile(0xE000, _pad_to_16x16(_crate))
    except Exception as e:
        print(f"[warn] Could not load crate tile: {e}")

    # Table tile: crop from urizen-nigrl-extratiles.png (tile #7, row at y=468, 12×12)
    try:
        extra_path = os.path.join(base_dir, "urizen-nigrl-extratiles.png")
        _extra = PilImage.open(extra_path).convert("RGBA")
        _table = np.array(_extra.crop((84, 468, 96, 480)))  # 12×12 RGBA
        tileset.set_tile(0xE002, _pad_to_16x16(_table))
    except Exception as e:
        print(f"[warn] Could not load table tile: {e}")

    # Fire tile: base64 PNG embedded in fire_tile.pixil JSON
    try:
        pixil_path = os.path.join(base_dir, "fire_tile.pixil")
        with open(pixil_path) as _f:
            _pixil = json.load(_f)
        _b64 = _pixil["frames"][0]["layers"][0]["src"].split(",", 1)[1]
        _fire_img = PilImage.open(io.BytesIO(base64.b64decode(_b64))).convert("RGBA")
        _fire = np.array(_fire_img)
        tileset.set_tile(0xE001, _pad_to_16x16(_fire))
    except Exception as e:
        print(f"[warn] Could not load fire tile: {e}")


def main():
    """Main game loop."""
    try:
        tileset_path = os.path.join(os.path.dirname(__file__), "Zilk_16x16.png")
        tileset = tcod.tileset.load_tilesheet(tileset_path, 16, 16, tcod.tileset.CHARMAP_CP437)
        _inject_hazard_tiles(tileset)

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
            running = True

            while running:
                engine = GameEngine()

                # Give engine a render callback for mid-turn visuals (fear flee, etc.)
                def _mid_turn_render():
                    console.clear()
                    render_all(console, engine)
                    context.present(console)
                engine.render_callback = _mid_turn_render

                while engine.running:
                    console.clear()
                    render_all(console, engine)
                    context.present(console)

                    if engine.auto_traveling:
                        # Non-blocking poll: any keypress cancels auto-travel
                        cancelled = False
                        for event in tcod.event.get():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                                cancelled = True
                                break
                            action = handle_input(event)
                            if action:
                                msg = "Autoexplore cancelled." if engine.autoexploring else "Auto-travel cancelled."
                                engine.cancel_auto_travel(msg)
                                # Re-trigger descend_stairs would restart travel; swallow it.
                                # Any other key is processed normally.
                                if action.get("type") not in ("descend_stairs", "autoexplore"):
                                    engine.process_action(action)
                                cancelled = True
                                break
                        if not cancelled and engine.auto_traveling:
                            time.sleep(0.02)
                            if engine.autoexploring:
                                engine.step_autoexplore()
                            else:
                                engine.step_auto_travel()
                    else:
                        for event in tcod.event.wait():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                engine.process_action(action)

                if not getattr(engine, "restart_requested", False):
                    running = False

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
