"""
NIGRL - A small roguelike game using tcod.

Traditional roguelike inspired by Rogue, Angband, Brogue, and Cataclysm: DDA.
"""

import os
import sys
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

    # Fire tile: mono-color PNG from dev-assets, tinted orange
    try:
        fire_path = os.path.join(base_dir, "dev-assets", "fire_tile_v1.png")
        _fire_img = PilImage.open(fire_path).convert("RGBA")
        _fire = np.array(_fire_img, dtype=np.uint8)
        # Tint all visible pixels to orange, preserve alpha
        _mask = _fire[:, :, 3] > 0
        _fire[_mask, 0] = 255   # R
        _fire[_mask, 1] = 140   # G
        _fire[_mask, 2] = 0     # B
        tileset.set_tile(0xE001, _fire)
    except Exception as e:
        print(f"[warn] Could not load fire tile: {e}")

    # Web tile: cobweb from dev-assets (already 16×16)
    try:
        web_path = os.path.join(base_dir, "dev-assets", "cobweb_16x16.png")
        _web_img = PilImage.open(web_path).convert("RGBA")
        _web = np.array(_web_img, dtype=np.uint8)
        if _web.shape[0] != 16 or _web.shape[1] != 16:
            _web = _pad_to_16x16(_web)
        tileset.set_tile(0xE003, _web)
    except Exception as e:
        print(f"[warn] Could not load web tile: {e}")

    # Spider hatchling tile: monocolor sprite from dev-assets (16×16)
    try:
        spider_path = os.path.join(base_dir, "dev-assets", "spiderling_16.png")
        _spider_img = PilImage.open(spider_path).convert("RGBA")
        _spider = np.array(_spider_img, dtype=np.uint8)
        if _spider.shape[0] != 16 or _spider.shape[1] != 16:
            _spider = _pad_to_16x16(_spider)
        tileset.set_tile(0xE004, _spider)
    except Exception as e:
        print(f"[warn] Could not load spider hatchling tile: {e}")


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

            # SDL overlay for pixel-level effects (floating damage numbers, etc.)
            from sdl_overlay import SDLOverlay
            sdl_overlay = SDLOverlay(context)

            while running:
                engine = GameEngine()
                engine.sdl_overlay = sdl_overlay
                engine.tcod_context = context

                # Give engine a render callback for mid-turn visuals (fear flee, etc.)
                def _mid_turn_render():
                    console.clear()
                    render_all(console, engine)
                    sdl_overlay.render_title_text_on_console(console)
                    sdl_overlay.update_cursed_tiles(engine)
                    sdl_overlay.present(console)
                engine.render_callback = _mid_turn_render

                # Initial render before first input
                console.clear()
                render_all(console, engine)
                sdl_overlay.render_title_text_on_console(console)
                sdl_overlay.update_cursed_tiles(engine)
                sdl_overlay.present(console)

                _needs_render = True
                _last_anim_render = 0.0

                while engine.running:
                    # --- INPUT FIRST (minimal latency) ---
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
                        _needs_render = True
                    elif sdl_overlay.has_active():
                        # Poll so floating texts animate without blocking
                        for event in tcod.event.get():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                if action:
                                    engine.process_action(action)
                                    _needs_render = True
                        # Animation frames: render at ~30fps when idle
                        now = time.time()
                        if not _needs_render and (now - _last_anim_render) >= 0.033:
                            _needs_render = True
                        if not _needs_render:
                            time.sleep(0.005)
                            continue  # skip render
                    else:
                        # Block until input — no animation running
                        for event in tcod.event.wait():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                engine.process_action(action)
                            break  # process one event, then render
                        _needs_render = True

                    # --- RENDER (only when needed) ---
                    if not engine.running:
                        break
                    if _needs_render:
                        console.clear()
                        render_all(console, engine)
                        sdl_overlay.render_title_text_on_console(console)
                        sdl_overlay.update_cursed_tiles(engine)
                        sdl_overlay.present(console)
                        _needs_render = False
                        _last_anim_render = time.time()

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
