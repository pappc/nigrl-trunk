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
        tileset[0xE000] = _pad_to_16x16(_crate)
    except Exception as e:
        print(f"[warn] Could not load crate tile: {e}")

    # Table tile: crop from urizen-nigrl-extratiles.png (tile #7, row at y=468, 12×12)
    try:
        extra_path = os.path.join(base_dir, "urizen-nigrl-extratiles.png")
        _extra = PilImage.open(extra_path).convert("RGBA")
        _table = np.array(_extra.crop((84, 468, 96, 480)))  # 12×12 RGBA
        tileset[0xE002] = _pad_to_16x16(_table)
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
        tileset[0xE001] = _fire
    except Exception as e:
        print(f"[warn] Could not load fire tile: {e}")

    # Web tile: cobweb from dev-assets (already 16×16)
    try:
        web_path = os.path.join(base_dir, "dev-assets", "cobweb_16x16.png")
        _web_img = PilImage.open(web_path).convert("RGBA")
        _web = np.array(_web_img, dtype=np.uint8)
        if _web.shape[0] != 16 or _web.shape[1] != 16:
            _web = _pad_to_16x16(_web)
        tileset[0xE003] = _web
    except Exception as e:
        print(f"[warn] Could not load web tile: {e}")

    # Spider hatchling tile: monocolor sprite from dev-assets (16×16)
    try:
        spider_path = os.path.join(base_dir, "dev-assets", "spiderling_16.png")
        _spider_img = PilImage.open(spider_path).convert("RGBA")
        _spider = np.array(_spider_img, dtype=np.uint8)
        if _spider.shape[0] != 16 or _spider.shape[1] != 16:
            _spider = _pad_to_16x16(_spider)
        tileset[0xE004] = _spider
    except Exception as e:
        print(f"[warn] Could not load spider hatchling tile: {e}")

    # Rosary tile: monocolor sprite from dev-assets (16×16)
    try:
        rosary_path = os.path.join(base_dir, "dev-assets", "rosary_16.png")
        _rosary_img = PilImage.open(rosary_path).convert("RGBA")
        _rosary = np.array(_rosary_img, dtype=np.uint8)
        if _rosary.shape[0] != 16 or _rosary.shape[1] != 16:
            _rosary = _pad_to_16x16(_rosary)
        tileset[0xE005] = _rosary
    except Exception as e:
        print(f"[warn] Could not load rosary tile: {e}")

    # Sword tile: monocolor sprite from dev-assets (16×16)
    try:
        sword_path = os.path.join(base_dir, "dev-assets", "sword_16.png")
        _sword_img = PilImage.open(sword_path).convert("RGBA")
        _sword = np.array(_sword_img, dtype=np.uint8)
        if _sword.shape[0] != 16 or _sword.shape[1] != 16:
            _sword = _pad_to_16x16(_sword)
        tileset[0xE006] = _sword
    except Exception as e:
        print(f"[warn] Could not load sword tile: {e}")

    # Dagger tile: monocolor sprite from dev-assets (16×16)
    try:
        dagger_path = os.path.join(base_dir, "dev-assets", "dagger_cursed_16.png")
        _dagger_img = PilImage.open(dagger_path).convert("RGBA")
        _dagger = np.array(_dagger_img, dtype=np.uint8)
        if _dagger.shape[0] != 16 or _dagger.shape[1] != 16:
            _dagger = _pad_to_16x16(_dagger)
        tileset[0xE007] = _dagger
    except Exception as e:
        print(f"[warn] Could not load dagger tile: {e}")

    # Blunt tile: monocolor sprite from dev-assets (16×16)
    try:
        blunt_path = os.path.join(base_dir, "dev-assets", "blunt_16.png")
        _blunt_img = PilImage.open(blunt_path).convert("RGBA")
        _blunt = np.array(_blunt_img, dtype=np.uint8)
        if _blunt.shape[0] != 16 or _blunt.shape[1] != 16:
            _blunt = _pad_to_16x16(_blunt)
        tileset[0xE008] = _blunt
    except Exception as e:
        print(f"[warn] Could not load blunt tile: {e}")

    # Amulet tile: monocolor sprite from dev-assets (16×16)
    try:
        amulet_path = os.path.join(base_dir, "dev-assets", "amulet_16.png")
        _amulet_img = PilImage.open(amulet_path).convert("RGBA")
        _amulet = np.array(_amulet_img, dtype=np.uint8)
        if _amulet.shape[0] != 16 or _amulet.shape[1] != 16:
            _amulet = _pad_to_16x16(_amulet)
        tileset[0xE009] = _amulet
    except Exception as e:
        print(f"[warn] Could not load amulet tile: {e}")

    # Ring tile: monocolor sprite from dev-assets (16×16)
    try:
        ring_path = os.path.join(base_dir, "dev-assets", "ring_16.png")
        _ring_img = PilImage.open(ring_path).convert("RGBA")
        _ring = np.array(_ring_img, dtype=np.uint8)
        if _ring.shape[0] != 16 or _ring.shape[1] != 16:
            _ring = _pad_to_16x16(_ring)
        tileset[0xE00A] = _ring
    except Exception as e:
        print(f"[warn] Could not load ring tile: {e}")

    # Boots tile: monocolor sprite from dev-assets (16×16)
    try:
        boots_path = os.path.join(base_dir, "dev-assets", "boots_16.png")
        _boots_img = PilImage.open(boots_path).convert("RGBA")
        _boots = np.array(_boots_img, dtype=np.uint8)
        if _boots.shape[0] != 16 or _boots.shape[1] != 16:
            _boots = _pad_to_16x16(_boots)
        tileset[0xE00B] = _boots
    except Exception as e:
        print(f"[warn] Could not load boots tile: {e}")

    # Small gun tile: monocolor sprite from dev-assets (16×16)
    try:
        gun_small_path = os.path.join(base_dir, "dev-assets", "gun_small_16.png")
        _gun_img = PilImage.open(gun_small_path).convert("RGBA")
        _gun = np.array(_gun_img, dtype=np.uint8)
        if _gun.shape[0] != 16 or _gun.shape[1] != 16:
            _gun = _pad_to_16x16(_gun)
        tileset[0xE00C] = _gun
    except Exception as e:
        print(f"[warn] Could not load small gun tile: {e}")

    # Hat tile: monocolor sprite from dev-assets (16×16)
    try:
        hat_path = os.path.join(base_dir, "dev-assets", "hat_16.png")
        _hat_img = PilImage.open(hat_path).convert("RGBA")
        _hat = np.array(_hat_img, dtype=np.uint8)
        if _hat.shape[0] != 16 or _hat.shape[1] != 16:
            _hat = _pad_to_16x16(_hat)
        tileset[0xE00D] = _hat
    except Exception as e:
        print(f"[warn] Could not load hat tile: {e}")

    # Battle axe tile: monocolor sprite from dev-assets (16×16)
    try:
        axe_path = os.path.join(base_dir, "dev-assets", "battle_axe_16.png")
        _axe_img = PilImage.open(axe_path).convert("RGBA")
        _axe = np.array(_axe_img, dtype=np.uint8)
        if _axe.shape[0] != 16 or _axe.shape[1] != 16:
            _axe = _pad_to_16x16(_axe)
        tileset[0xE00E] = _axe
    except Exception as e:
        print(f"[warn] Could not load battle axe tile: {e}")

    # Medium gun tile: monocolor sprite from dev-assets (16x16)
    try:
        gun_med_path = os.path.join(base_dir, "dev-assets", "gun_medium_16.png")
        _gun_med_img = PilImage.open(gun_med_path).convert("RGBA")
        _gun_med = np.array(_gun_med_img, dtype=np.uint8)
        if _gun_med.shape[0] != 16 or _gun_med.shape[1] != 16:
            _gun_med = _pad_to_16x16(_gun_med)
        tileset[0xE00F] = _gun_med
    except Exception as e:
        print(f"[warn] Could not load medium gun tile: {e}")

    # Maul tile: monocolor sprite from dev-assets (16x16)
    try:
        maul_path = os.path.join(base_dir, "dev-assets", "maul_16.png")
        _maul_img = PilImage.open(maul_path).convert("RGBA")
        _maul = np.array(_maul_img, dtype=np.uint8)
        if _maul.shape[0] != 16 or _maul.shape[1] != 16:
            _maul = _pad_to_16x16(_maul)
        tileset[0xE010] = _maul
    except Exception as e:
        print(f"[warn] Could not load maul tile: {e}")

    # Voodoo Doll tile: monocolor sprite from dev-assets (16x16)
    try:
        voodoo_path = os.path.join(base_dir, "dev-assets", "voodoo_16-export.png")
        _voodoo_img = PilImage.open(voodoo_path).convert("RGBA")
        _voodoo = np.array(_voodoo_img, dtype=np.uint8)
        if _voodoo.shape[0] != 16 or _voodoo.shape[1] != 16:
            _voodoo = _pad_to_16x16(_voodoo)
        tileset[0xE011] = _voodoo
    except Exception as e:
        print(f"[warn] Could not load voodoo tile: {e}")


def _show_title_screen(console, context, sdl_overlay):
    """Display the title screen. Returns (action, seed_or_None).
    action: 'start', 'continue', or 'exit'."""
    from save_system import has_save, export_save_to_clipboard, import_save_from_clipboard

    TITLE_ART = [
        "NN    NN IIIIIII  GGGGG  RRRRR   LL      ",
        "NNN   NN   III   GG      RR  RR  LL      ",
        "NNNN  NN   III   GG GGG  RRRRR   LL      ",
        "NN NN NN   III   GG  GG  RR RR   LL      ",
        "NN  NNNN   III   GG  GG  RR  RR  LL      ",
        "NN   NNN IIIIIII  GGGGG  RR   RR LLLLLLL ",
    ]

    BG = (12, 12, 18)
    C_TITLE = (255, 220, 100)
    C_SUBTITLE = (100, 100, 130)
    C_SELECTED = (255, 255, 0)
    C_UNSELECTED = (150, 150, 150)
    C_DISABLED = (60, 60, 60)
    C_HINT = (80, 80, 110)
    C_SEP = (130, 130, 190)
    C_STATUS_OK = (100, 255, 100)
    C_STATUS_ERR = (255, 100, 100)

    save_exists = has_save()
    options = ["Start Game", "Continue", "Seeded Run", "Export Save", "Import Save", "Exit"]
    # Options that require a save to be selectable
    _needs_save = {"Continue", "Export Save"}
    cursor = 0
    status_msg = ""
    status_color = C_STATUS_OK

    def _is_disabled(opt):
        return opt in _needs_save and not save_exists

    while True:
        console.clear()
        console.bg[:, :] = BG

        # ASCII title art (centered)
        art_width = len(TITLE_ART[0])
        art_x = (SCREEN_WIDTH - art_width) // 2
        art_y = 15
        for row_idx, line in enumerate(TITLE_ART):
            for col_idx, ch in enumerate(line):
                if ch != " ":
                    console.print(art_x + col_idx, art_y + row_idx, ch,
                                  fg=C_TITLE, bg=BG)

        # Subtitle
        subtitle = "A Roguelike"
        console.print((SCREEN_WIDTH - len(subtitle)) // 2,
                       art_y + len(TITLE_ART) + 2, subtitle,
                       fg=C_SUBTITLE, bg=BG)

        # Separator
        sep = "~ ~ ~ ~ ~ ~ ~ ~ ~"
        console.print((SCREEN_WIDTH - len(sep)) // 2,
                       art_y + len(TITLE_ART) + 4, sep,
                       fg=C_SEP, bg=BG)

        # Menu options
        menu_y = art_y + len(TITLE_ART) + 7
        for i, opt in enumerate(options):
            disabled = _is_disabled(opt)
            if disabled:
                label = f"  {opt}  "
                fg = C_DISABLED
            elif i == cursor:
                label = f"> {opt} <"
                fg = C_SELECTED
            else:
                label = f"  {opt}  "
                fg = C_UNSELECTED
            console.print((SCREEN_WIDTH - len(label)) // 2,
                           menu_y + i * 2, label, fg=fg, bg=BG)

        # Status message (below menu, above hint)
        if status_msg:
            console.print((SCREEN_WIDTH - len(status_msg)) // 2,
                           menu_y + len(options) * 2 + 1, status_msg,
                           fg=status_color, bg=BG)

        # Navigation hint
        hint = "[Up/Down] Navigate    [Enter] Select"
        console.print((SCREEN_WIDTH - len(hint)) // 2,
                       SCREEN_HEIGHT - 3, hint, fg=C_HINT, bg=BG)

        sdl_overlay.present(console)

        # Input (blocking, one event per iteration)
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return ("exit", None)
            if isinstance(event, tcod.event.KeyDown):
                ks = event.sym
                if ks in (tcod.event.KeySym.UP, tcod.event.KeySym.KP_8):
                    cursor = (cursor - 1) % len(options)
                    if _is_disabled(options[cursor]):
                        cursor = (cursor - 1) % len(options)
                elif ks in (tcod.event.KeySym.DOWN, tcod.event.KeySym.KP_2):
                    cursor = (cursor + 1) % len(options)
                    if _is_disabled(options[cursor]):
                        cursor = (cursor + 1) % len(options)
                elif ks in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
                    opt = options[cursor]
                    if opt == "Continue" and save_exists:
                        return ("continue", None)
                    elif opt == "Start Game":
                        return ("start", None)
                    elif opt == "Seeded Run":
                        seed = _show_seed_input(console, context, sdl_overlay)
                        if seed is not None:
                            return ("start", seed)
                    elif opt == "Export Save":
                        if export_save_to_clipboard():
                            status_msg = "Save copied to clipboard!"
                            status_color = C_STATUS_OK
                        else:
                            status_msg = "Export failed."
                            status_color = C_STATUS_ERR
                    elif opt == "Import Save":
                        ok, msg = import_save_from_clipboard()
                        status_msg = msg
                        status_color = C_STATUS_OK if ok else C_STATUS_ERR
                        if ok:
                            save_exists = True  # refresh so Continue is now enabled
                    elif opt == "Exit":
                        return ("exit", None)
            break


def _show_seed_input(console, context, sdl_overlay):
    """Show seed input screen. Returns seed string or None if cancelled."""
    BG = (12, 12, 18)
    C_TITLE = (255, 255, 180)
    C_LABEL = (180, 180, 200)
    C_INPUT = (255, 255, 255)
    C_CURSOR = (255, 220, 100)
    C_HINT = (80, 80, 110)
    C_BOX = (130, 130, 190)

    seed_text = ""
    MAX_SEED_LEN = 40

    while True:
        console.clear()
        console.bg[:, :] = BG

        # Title
        title = "SEEDED RUN"
        console.print((SCREEN_WIDTH - len(title)) // 2, 20,
                       title, fg=C_TITLE, bg=BG)

        # Label
        label = "Enter a seed:"
        console.print((SCREEN_WIDTH - len(label)) // 2, 24,
                       label, fg=C_LABEL, bg=BG)

        # Input box
        box_w = MAX_SEED_LEN + 4
        box_x = (SCREEN_WIDTH - box_w) // 2
        box_y = 27
        # Top border
        console.print(box_x, box_y, "+" + "-" * (box_w - 2) + "+",
                       fg=C_BOX, bg=BG)
        # Middle row with text
        display = seed_text + "_"
        padded = display.ljust(box_w - 4)
        console.print(box_x, box_y + 1, "| ", fg=C_BOX, bg=BG)
        console.print(box_x + 2, box_y + 1, padded[:box_w - 4],
                       fg=C_INPUT, bg=BG)
        console.print(box_x + box_w - 2, box_y + 1, " |", fg=C_BOX, bg=BG)
        # Blinking cursor color on the underscore
        cursor_x = box_x + 2 + len(seed_text)
        if cursor_x < box_x + box_w - 2:
            console.print(cursor_x, box_y + 1, "_", fg=C_CURSOR, bg=BG)
        # Bottom border
        console.print(box_x, box_y + 2, "+" + "-" * (box_w - 2) + "+",
                       fg=C_BOX, bg=BG)

        # Hint
        hint = "[Enter] Confirm    [Esc] Cancel"
        console.print((SCREEN_WIDTH - len(hint)) // 2,
                       SCREEN_HEIGHT - 3, hint, fg=C_HINT, bg=BG)

        sdl_overlay.present(console)

        # Input
        for event in tcod.event.wait():
            if isinstance(event, tcod.event.Quit):
                return None
            if isinstance(event, tcod.event.KeyDown):
                ks = event.sym
                if ks == tcod.event.KeySym.ESCAPE:
                    return None
                elif ks in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER):
                    if seed_text:
                        return seed_text
                elif ks == tcod.event.KeySym.BACKSPACE:
                    seed_text = seed_text[:-1]
                elif ks == tcod.event.KeySym.v and (event.mod & tcod.event.Modifier.CTRL):
                    # Ctrl+V paste
                    try:
                        import ctypes
                        ctypes.windll.user32.OpenClipboard(0)
                        handle = ctypes.windll.user32.GetClipboardData(13)  # CF_UNICODETEXT
                        if handle:
                            ctypes.windll.kernel32.GlobalLock.restype = ctypes.c_wchar_p
                            pasted = ctypes.windll.kernel32.GlobalLock(handle)
                            if pasted:
                                seed_text = (seed_text + pasted)[:MAX_SEED_LEN]
                                ctypes.windll.kernel32.GlobalUnlock(handle)
                        ctypes.windll.user32.CloseClipboard()
                    except Exception:
                        pass  # clipboard unavailable
                else:
                    # Direct alphanumeric input (SDL3 may not emit TextInput)
                    # Exclude ambiguous chars: O/0, I/1/L, S/5, Z/2, B/8
                    _SEED_CHARS = frozenset("1346789ABCDEFGHIJKLMNPQRTUVWXY")
                    v = ks.value
                    if 97 <= v <= 122:  # a-z → always uppercase
                        ch = chr(v).upper()
                        if ch in _SEED_CHARS:
                            seed_text = (seed_text + ch)[:MAX_SEED_LEN]
                    elif 48 <= v <= 57:  # 0-9
                        ch = chr(v)
                        if ch in _SEED_CHARS:
                            seed_text = (seed_text + ch)[:MAX_SEED_LEN]
            elif isinstance(event, tcod.event.TextInput):
                ch = event.text.upper()
                if all(c in "1346789ABCDEFGHIJKLMNPQRTUVWXY" for c in ch):
                    seed_text = (seed_text + ch)[:MAX_SEED_LEN]
            break


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

            _skip_title = False
            _seed = None
            while running:
                if not _skip_title:
                    choice, _seed = _show_title_screen(console, context, sdl_overlay)
                    if choice == "exit":
                        break
                if _skip_title:
                    choice = "new_game"
                _skip_title = False

                if choice == "continue":
                    from save_system import load_game
                    engine = load_game()
                    if engine is None:
                        # Corrupt save was deleted — fall back to new game
                        engine = GameEngine(seed=_seed)
                else:
                    engine = GameEngine(seed=_seed)
                _seed = None
                engine.sdl_overlay = sdl_overlay
                engine.tcod_context = context

                # Give engine a render callback for mid-turn visuals (fear flee, etc.)
                def _mid_turn_render():
                    console.clear()
                    render_all(console, engine)
                    sdl_overlay.render_title_text_on_console(console)
                    sdl_overlay.update_all_entity_overlays(engine)
                    sdl_overlay.present(console)
                engine.render_callback = _mid_turn_render

                # Initial render before first input
                console.clear()
                render_all(console, engine)
                sdl_overlay.render_title_text_on_console(console)
                sdl_overlay.update_all_entity_overlays(engine)
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
                        # Poll for input — process ALL pending events immediately
                        for event in tcod.event.get():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                if action:
                                    engine.process_action(action)
                                    _needs_render = True
                        # Animation-only frames: render overlays at ~24fps
                        now = time.time()
                        if not _needs_render and (now - _last_anim_render) >= 0.042:
                            # Only re-render SDL overlays, reuse cached console texture
                            sdl_overlay.update_all_entity_overlays(engine)
                            sdl_overlay.present(console, skip_console_render=True)
                            _last_anim_render = now
                        if not _needs_render:
                            time.sleep(0.005)
                            continue  # skip full render
                    else:
                        # Block until first input, then drain all pending events
                        _any_action = False
                        for event in tcod.event.wait():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                if action:
                                    engine.process_action(action)
                                    _any_action = True
                            break  # unblock after first event
                        # Drain remaining queued events (KeyUp, repeats, etc.)
                        for event in tcod.event.get():
                            if isinstance(event, tcod.event.Quit):
                                engine.running = False
                                running = False
                            else:
                                action = handle_input(event)
                                if action:
                                    engine.process_action(action)
                                    _any_action = True
                        if _any_action:
                            _needs_render = True

                    # --- RENDER (only when needed) ---
                    if not engine.running:
                        break
                    if _needs_render:
                        console.clear()
                        render_all(console, engine)
                        sdl_overlay.render_title_text_on_console(console)
                        sdl_overlay.update_all_entity_overlays(engine)
                        sdl_overlay.present(console)
                        _needs_render = False
                        _last_anim_render = time.time()

                # Restart skips title screen; quit returns to it
                if not engine.running and not getattr(engine, "restart_requested", False):
                    continue  # back to title screen
                # restart_requested: loop back and skip title via flag
                _skip_title = getattr(engine, "restart_requested", False)

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
