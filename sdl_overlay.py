"""SDL2 overlay layer for pixel-level rendering on top of the tcod console.

Renders floating damage/heal numbers (and future effects like particles,
screen shake, etc.) using the SDL renderer exposed by tcod 20+.
Numbers float smoothly upward with transparency — the tile grid underneath
remains fully visible.

Replaces context.present(console) with a single-present pipeline:
  1. Render console to texture via SDLConsoleRender
  2. Copy console texture to renderer
  3. Draw overlays on top
  4. renderer.present() once
"""

import math
import os
import random as _rng
import time
import numpy as np
import tcod.render
import tcod.sdl.render
from dataclasses import dataclass, field
from config import MAP_OFFSET_X, HEADER_HEIGHT

# --- Configuration ---
FLOAT_DURATION = 1.0        # seconds for floating text to live
FLOAT_DISTANCE_PX = 48      # total pixels to drift upward (3 tiles)
GLYPH_W = 6                 # source glyph width in pixels
GLYPH_H = 5                 # source glyph height in pixels
GLYPH_SCALE = 2             # render at 2x (12x10 px per digit)
GLYPH_SPACING = 1           # 1 pixel gap between digits (at source scale)
TILE_PX = 16                # pixels per tile
STATUS_ICON_SCALE = 1       # render status icons at 1x (8x7 px per icon)
STATUS_ICON_SPACING = 1     # 1 pixel gap between status icons

# 6-wide x 5-tall bold pixel font — short, fat, chunky strokes
_GLYPH_BITMAPS = {
    '0': [0x3C, 0x66, 0x66, 0x66, 0x3C],
    '1': [0x18, 0x38, 0x18, 0x18, 0x3C],
    '2': [0x3C, 0x06, 0x3C, 0x60, 0x7E],
    '3': [0x3C, 0x06, 0x1C, 0x06, 0x3C],
    '4': [0x66, 0x66, 0x7E, 0x06, 0x06],
    '5': [0x7E, 0x60, 0x3C, 0x06, 0x3C],
    '6': [0x3C, 0x60, 0x7C, 0x66, 0x3C],
    '7': [0x7E, 0x06, 0x0C, 0x18, 0x18],
    '8': [0x3C, 0x66, 0x3C, 0x66, 0x3C],
    '9': [0x3C, 0x66, 0x3E, 0x06, 0x3C],
    '+': [0x00, 0x18, 0x7E, 0x18, 0x00],
    # A-Z uppercase
    'A': [0x3C, 0x66, 0x7E, 0x66, 0x66],
    'B': [0x7C, 0x66, 0x7C, 0x66, 0x7C],
    'C': [0x3C, 0x60, 0x60, 0x60, 0x3C],
    'D': [0x78, 0x6C, 0x66, 0x6C, 0x78],
    'E': [0x7E, 0x60, 0x7C, 0x60, 0x7E],
    'F': [0x7E, 0x60, 0x7C, 0x60, 0x60],
    'G': [0x3C, 0x60, 0x6E, 0x66, 0x3C],
    'H': [0x66, 0x66, 0x7E, 0x66, 0x66],
    'I': [0x3C, 0x18, 0x18, 0x18, 0x3C],
    'J': [0x06, 0x06, 0x06, 0x66, 0x3C],
    'K': [0x66, 0x6C, 0x78, 0x6C, 0x66],
    'L': [0x60, 0x60, 0x60, 0x60, 0x7E],
    'M': [0x66, 0x7E, 0x7E, 0x66, 0x66],
    'N': [0x66, 0x76, 0x7E, 0x6E, 0x66],
    'O': [0x3C, 0x66, 0x66, 0x66, 0x3C],
    'P': [0x7C, 0x66, 0x7C, 0x60, 0x60],
    'Q': [0x3C, 0x66, 0x66, 0x6C, 0x36],
    'R': [0x7C, 0x66, 0x7C, 0x6C, 0x66],
    'S': [0x3C, 0x60, 0x3C, 0x06, 0x3C],
    'T': [0x7E, 0x18, 0x18, 0x18, 0x18],
    'U': [0x66, 0x66, 0x66, 0x66, 0x3C],
    'V': [0x66, 0x66, 0x66, 0x3C, 0x18],
    'W': [0x66, 0x66, 0x7E, 0x7E, 0x66],
    'X': [0x66, 0x3C, 0x18, 0x3C, 0x66],
    'Y': [0x66, 0x66, 0x3C, 0x18, 0x18],
    'Z': [0x7E, 0x0C, 0x18, 0x30, 0x7E],
    # Lowercase (map to uppercase)
    # Punctuation / symbols
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x18],
    ',': [0x00, 0x00, 0x00, 0x18, 0x30],
    '!': [0x18, 0x18, 0x18, 0x00, 0x18],
    '?': [0x3C, 0x06, 0x1C, 0x00, 0x18],
    '-': [0x00, 0x00, 0x3C, 0x00, 0x00],
    "'": [0x18, 0x18, 0x00, 0x00, 0x00],
}
# Map lowercase to uppercase for lookups
for _c in 'abcdefghijklmnopqrstuvwxyz':
    _GLYPH_BITMAPS[_c] = _GLYPH_BITMAPS[_c.upper()]


@dataclass
class _FloatingText:
    """A floating text instance with pixel-level positioning."""
    x_px: float          # screen pixel x (left edge of originating tile)
    y_px: float          # screen pixel y (top of originating tile)
    text: str
    color: tuple[int, int, int]
    birth: float = field(default_factory=time.time)
    num_chars: int = 0   # pre-computed count of renderable chars


@dataclass
class _Ember:
    """A single floating ember particle above a fire tile."""
    x_px: float
    y_px: float
    color: tuple[int, int, int]
    birth: float
    lifetime: float      # seconds this ember lives
    drift_x: float       # horizontal drift per second (pixels)
    drift_y: float       # vertical drift per second (pixels, negative = up)
    size: int            # pixel size (1-3)


# Ember configuration
_EMBER_SPAWN_RATE = 3.0      # embers spawned per fire tile per second
_EMBER_LIFETIME_MIN = 0.4
_EMBER_LIFETIME_MAX = 1.0
_EMBER_DRIFT_Y = -20.0       # pixels/sec upward
_EMBER_DRIFT_X_RANGE = 8.0   # max horizontal drift pixels/sec
_EMBER_COLORS = [
    (255, 200, 60),   # bright yellow
    (255, 160, 30),   # orange
    (255, 100, 20),   # deep orange
    (255, 80, 10),    # red-orange
    (255, 220, 100),  # pale yellow
]


class SDLOverlay:
    """Manages SDL2 overlay rendering on top of the tcod console.

    Owns the full present pipeline — call present() instead of context.present().
    """

    def __init__(self, context):
        self._renderer = context.sdl_renderer
        self._console_render = tcod.render.SDLConsoleRender(context.sdl_atlas)
        self._digit_textures: dict[str, tcod.sdl.render.Texture] = {}
        self._floating_texts: list[_FloatingText] = []
        self._cursed_tiles: list[tuple[int, int]] = []  # (dungeon_x, dungeon_y)
        self._title_card: dict | None = None  # {"text": str, "birth": float, "duration": float}
        self._tile_flashes: list[dict] = []  # [{"x": int, "y": int, "birth": float, "delay": float, "duration": float, "color": (r,g,b)}]
        self._embers: list[_Ember] = []
        self._fire_tiles: list[tuple[int, int]] = []  # (dungeon_x, dungeon_y) of visible fire hazards
        self._frozen_tiles: list[tuple[int, int]] = []  # (dungeon_x, dungeon_y) of visible frozen monsters
        self._gradient_tiles: list[tuple] = []  # (dungeon_x, dungeon_y, item_id) for gradient items
        self._gradient_textures: dict = {}  # item_id -> SDL texture (lazily built)
        self._status_icon_data: list[tuple[int, int, list[tuple[str, tuple[int,int,int]]]]] = []
        self._last_ember_spawn: float = 0.0
        self._init_digit_textures()
        self._init_status_glyph_textures()

    def _init_digit_textures(self):
        """Pre-cache digit textures: outline (black) + foreground (white, tintable)."""
        border = 1  # outline thickness in source pixels
        out_w = GLYPH_W + border * 2
        out_h = GLYPH_H + border * 2
        self._outline_textures: dict[str, tcod.sdl.render.Texture] = {}
        for ch, rows in _GLYPH_BITMAPS.items():
            # --- Outline texture: black border pixels only ---
            outline_px = np.zeros((out_h, out_w, 4), dtype=np.uint8)
            fg_px = np.zeros((out_h, out_w, 4), dtype=np.uint8)
            for row_i, bits in enumerate(rows):
                for col_i in range(GLYPH_W):
                    if bits & (1 << (GLYPH_W - 1 - col_i)):
                        cy = row_i + border
                        cx = col_i + border
                        # Mark foreground
                        fg_px[cy, cx] = [255, 255, 255, 255]
                        # Mark outline neighbors
                        for dy in range(-border, border + 1):
                            for dx in range(-border, border + 1):
                                ny, nx = cy + dy, cx + dx
                                if 0 <= ny < out_h and 0 <= nx < out_w:
                                    outline_px[ny, nx] = [0, 0, 0, 255]
            # Clear foreground pixels from outline (outline = border only)
            for row_i, bits in enumerate(rows):
                for col_i in range(GLYPH_W):
                    if bits & (1 << (GLYPH_W - 1 - col_i)):
                        outline_px[row_i + border, col_i + border] = [0, 0, 0, 0]

            otex = self._renderer.upload_texture(outline_px)
            otex.blend_mode = tcod.sdl.render.BlendMode.BLEND
            otex.scale_mode = tcod.sdl.render.ScaleMode.NEAREST
            self._outline_textures[ch] = otex

            ftex = self._renderer.upload_texture(fg_px)
            ftex.blend_mode = tcod.sdl.render.BlendMode.BLEND
            ftex.scale_mode = tcod.sdl.render.ScaleMode.NEAREST
            self._digit_textures[ch] = ftex
        self._glyph_render_w = out_w
        self._glyph_render_h = out_h

    # Status effect glyph PNGs: key -> filename in dev-assets/
    _STATUS_GLYPH_FILES = {
        "_chill": "chill-glyph.png",
        "_ignite": "ignite-glyph.png",
        "_shock": "shock-glyph.png",
        "_rad": "rad-glyph.png",
        "_tox": "toxic-glyph.png",
    }

    def _init_status_glyph_textures(self):
        """Load status effect glyph PNGs and create outline+foreground texture pairs."""
        from PIL import Image as PilImage
        border = 1
        base_dir = os.path.dirname(os.path.abspath(__file__))
        for key, filename in self._STATUS_GLYPH_FILES.items():
            try:
                path = os.path.join(base_dir, "dev-assets", filename)
                img = PilImage.open(path).convert("RGBA")
                src = np.array(img, dtype=np.uint8)
                h, w = src.shape[:2]
                out_h = h + border * 2
                out_w = w + border * 2
                # Build foreground: white pixels where source alpha > 0
                fg_px = np.zeros((out_h, out_w, 4), dtype=np.uint8)
                outline_px = np.zeros((out_h, out_w, 4), dtype=np.uint8)
                for row_i in range(h):
                    for col_i in range(w):
                        if src[row_i, col_i, 3] > 0:
                            cy = row_i + border
                            cx = col_i + border
                            fg_px[cy, cx] = [255, 255, 255, 255]
                            for dy in range(-border, border + 1):
                                for dx in range(-border, border + 1):
                                    ny, nx = cy + dy, cx + dx
                                    if 0 <= ny < out_h and 0 <= nx < out_w:
                                        outline_px[ny, nx] = [0, 0, 0, 255]
                # Clear foreground pixels from outline
                for row_i in range(h):
                    for col_i in range(w):
                        if src[row_i, col_i, 3] > 0:
                            outline_px[row_i + border, col_i + border] = [0, 0, 0, 0]

                otex = self._renderer.upload_texture(outline_px)
                otex.blend_mode = tcod.sdl.render.BlendMode.BLEND
                otex.scale_mode = tcod.sdl.render.ScaleMode.NEAREST
                self._outline_textures[key] = otex

                ftex = self._renderer.upload_texture(fg_px)
                ftex.blend_mode = tcod.sdl.render.BlendMode.BLEND
                ftex.scale_mode = tcod.sdl.render.ScaleMode.NEAREST
                self._digit_textures[key] = ftex
            except Exception as e:
                print(f"[warn] Could not load status glyph {filename}: {e}")

    def _tile_to_pixel(self, dungeon_x: int, dungeon_y: int) -> tuple[float, float]:
        """Convert dungeon tile coords to screen pixel coords.

        Returns the pixel position one tile above the entity so the number
        starts above the monster's head and floats further up from there.
        """
        screen_tile_x = dungeon_x + MAP_OFFSET_X
        screen_tile_y = dungeon_y + HEADER_HEIGHT
        return (screen_tile_x * TILE_PX, (screen_tile_y - 1) * TILE_PX)

    def add_floating_text(self, dungeon_x: int, dungeon_y: int, text: str,
                          color: tuple[int, int, int]):
        """Spawn a floating text at a dungeon position.

        If a same-color floating text already exists at this tile from the
        same game tick (within 50ms), merge into e.g. '5+3' instead of
        overlapping.
        """
        px, py = self._tile_to_pixel(dungeon_x, dungeon_y)
        now = time.time()
        # Try to merge with a recent same-position, same-color text
        for ft in self._floating_texts:
            if (ft.x_px == px and ft.y_px == py
                    and ft.color == color
                    and (now - ft.birth) < 0.05):
                ft.text += "+" + text
                ft.num_chars = sum(1 for c in ft.text if c in self._digit_textures)
                return
        nc = sum(1 for c in text if c in self._digit_textures)
        self._floating_texts.append(_FloatingText(px, py, text, color, num_chars=nc))

    def has_active(self) -> bool:
        """Check if any overlays need animating (floating texts, curses, title card)."""
        now = time.time()
        self._floating_texts = [
            ft for ft in self._floating_texts
            if (now - ft.birth) < FLOAT_DURATION
        ]
        if self._title_card and (now - self._title_card["birth"]) >= self._title_card["duration"]:
            self._title_card = None
        # Prune expired tile flashes
        self._tile_flashes = [
            f for f in self._tile_flashes
            if (now - f["birth"]) < f["delay"] + f["duration"]
        ]
        # Only count truly animated elements (floating texts, flashes, embers, title cards).
        # Static overlays (fire tiles, frozen tiles, gradients, status icons) don't need
        # animation polling — they're redrawn on game-state renders.
        return (len(self._floating_texts) > 0
                or self._title_card is not None
                or len(self._tile_flashes) > 0
                or len(self._embers) > 0)

    # Keep individual methods as thin wrappers for backward compat (called from nigrl.py)
    def update_fire_tiles(self, engine):
        pass  # handled by update_all_entity_overlays

    def update_cursed_tiles(self, engine):
        pass  # handled by update_all_entity_overlays

    def update_frozen_tiles(self, engine):
        pass  # handled by update_all_entity_overlays

    def update_gradient_tiles(self, engine):
        pass  # handled by update_all_entity_overlays

    def update_status_icons(self, engine):
        pass  # handled by update_all_entity_overlays

    # Per-item gradient config: item_id → (tile_file, color_stops, pulse, steps)
    # color_stops = [(R,G,B), ...] for diagonal gradient (bottom-left → top-right)
    # steps=0 means smooth gradient; steps=N means N discrete color bands
    _GRADIENT_CONFIG = {
        "yinyang_ichimonji": ("sword_16.png", [(0, 0, 0), (255, 255, 255)], True, 0),
        "sleeper_agent": ("dagger_cursed_16.png", [(180, 80, 255), (100, 255, 100)], False, 0),
        "massive_blunt": ("blunt_16.png", [(139, 90, 43), (50, 255, 50)], False, 4),
        "amulet_of_equivalent_exchange": ("amulet_16.png", [(160, 160, 160), (160, 50, 220), (160, 160, 160)], False, 0),
        "nine_ring": ("ring_16.png", [(180, 150, 0), (255, 255, 80)], False, 4),
        "boots_of_blinding_speed": ("boots_16.png", [(80, 180, 255), (200, 240, 255), (255, 255, 255)], False, 4),
        "boots_of_springing": ("boots_16.png", [(160, 120, 70), (60, 40, 20)], False, 2),
        "decimator": ("gun_small_16.png", [(255, 120, 40), (200, 30, 30)], False, 0),
        "straw_hat": ("hat_16.png", [(30, 30, 30), (220, 200, 80)], False, 0),
        "boots_of_striding": ("boots_16.png", [(60, 40, 20), (160, 120, 70)], False, 2),
        "rune_scraper": ("dagger_cursed_16.png", [(160, 60, 220), (30, 10, 40)], True, 0, 6.0),
        "whirlwind_axe": ("battle_axe_16.png", [(220, 60, 60), (140, 140, 140)], False, 0),
        "titans_blood_ring": ("ring_16.png", [(30, 10, 10), (200, 30, 30), (30, 10, 10)], False, 0),
        "flagellants_mask": ("hat_16.png", [(180, 50, 50), (80, 20, 20)], False, 0),
        "thinking_cap": ("hat_16.png", [(30, 40, 160), (220, 230, 255)], False, 0),
        "thunder_gun": ("gun_medium_16.png", [(255, 255, 80), (80, 120, 255)], False, 0),
        "ring_of_sustenance": ("ring_16.png", [(240, 130, 30), (255, 240, 80)], False, 0),
    }
    _GRADIENT_ITEM_IDS = frozenset(_GRADIENT_CONFIG.keys())

    def update_all_entity_overlays(self, engine):
        """Single-pass rebuild of all per-entity overlay data (fire, cursed, frozen, gradient, status icons)."""
        from menu_state import MenuState
        menu_open = engine.menu_state != MenuState.NONE

        if menu_open:
            self._fire_tiles = []
            self._embers.clear()
            self._frozen_tiles = []
            self._gradient_tiles = []
            self._status_icon_data = []
            self._cursed_tiles = []
            return

        fire = []
        cursed = []
        frozen = []
        gradient = []
        status_icons = []

        visible = engine.dungeon.visible
        for entity in engine.dungeon.entities:
            if not visible[entity.y, entity.x]:
                continue

            etype = entity.entity_type

            if etype == "hazard":
                ht = getattr(entity, 'hazard_type', None)
                if ht == 'fire':
                    fire.append((entity.x, entity.y))

            elif etype == "item":
                item_id = getattr(entity, 'item_id', None)
                if item_id and item_id in self._GRADIENT_ITEM_IDS:
                    gradient.append((entity.x, entity.y, item_id))

            elif etype == "monster" and entity.alive:
                effects = entity.status_effects
                has_curse = False
                has_frozen = False
                icons = []
                for eff in effects:
                    eff_id = getattr(eff, 'id', '')
                    if getattr(eff, 'is_curse', False):
                        has_curse = True
                    if eff_id == 'frozen':
                        has_frozen = True
                    elif eff_id == 'chill':
                        icons.append(('_chill', (100, 180, 255)))
                    elif eff_id == 'shocked':
                        icons.append(('_shock', (255, 255, 60)))
                    elif eff_id == 'ignite':
                        icons.append(('_ignite', (255, 120, 30)))
                    elif eff_id == 'stun':
                        icons.append(('_shock', (255, 255, 255)))
                    elif eff_id == 'voodoo_ham_stun':
                        icons.append(('_shock', (180, 80, 255)))
                    elif eff_id == 'fear':
                        icons.append(('F', (180, 80, 255)))
                    elif eff_id == 'snipers_mark':
                        icons.append(('M', (255, 60, 60)))
                    elif eff_id == 'slipped':
                        icons.append(('S', (200, 200, 210)))
                    elif eff_id == 'webbed':
                        dur = getattr(eff, 'duration', 0)
                        icons.append(('W', (220, 220, 230)))
                        if dur > 0:
                            icons.append((str(min(dur, 9)), (220, 220, 230)))
                if has_curse:
                    cursed.append((entity.x, entity.y))
                if has_frozen:
                    frozen.append((entity.x, entity.y))
                rad = getattr(entity, 'radiation', 0)
                if rad > 0:
                    rc = (255, 60, 60) if rad >= 150 else (255, 255, 60) if rad >= 75 else (60, 255, 60)
                    icons.append(('_rad', rc))
                tox = getattr(entity, 'toxicity', 0)
                if tox > 0:
                    tc = (255, 60, 60) if tox >= 100 else (255, 255, 60) if tox >= 50 else (60, 255, 60)
                    icons.append(('_tox', tc))
                if icons:
                    status_icons.append((entity.x, entity.y, icons))

        self._fire_tiles = fire
        self._cursed_tiles = cursed
        self._frozen_tiles = frozen
        self._gradient_tiles = gradient
        self._status_icon_data = status_icons

    def add_tile_flash_ripple(self, tiles: list[tuple[int, int]],
                             origin_x: int, origin_y: int,
                             color: tuple[int, int, int] = (255, 120, 30),
                             duration: float = 0.8,
                             ripple_speed: float = 0.06):
        """Flash tiles with a color that fades to transparent, rippling outward from origin.

        ripple_speed: seconds of delay per tile of Chebyshev distance from origin.
        """
        now = time.time()
        for tx, ty in tiles:
            dist = max(abs(tx - origin_x), abs(ty - origin_y))
            delay = dist * ripple_speed
            self._tile_flashes.append({
                "x": tx, "y": ty,
                "birth": now, "delay": delay,
                "duration": duration,
                "color": color,
            })

    def show_title_card(self, text: str, duration: float = 3.0):
        """Show a full-screen title card that fades out over the given duration."""
        self._title_card = {"text": text, "birth": time.time(), "duration": duration}

    def clear(self):
        """Remove all floating texts."""
        self._floating_texts.clear()

    def present(self, console):
        """Render console + overlays in a single present. Replaces context.present()."""
        # Step 1: Render console to texture (no present)
        console_tex = self._console_render.render(console)

        # Step 2: Copy console texture to renderer (scaled to fill window)
        self._renderer.copy(console_tex)

        # Step 3: Spawn ember particles (only if fire tiles visible)
        self._spawn_embers()

        # Step 4: Draw overlays on top (only if there's something to draw)
        if (self._floating_texts or self._tile_flashes
                or self._title_card or self._embers
                or self._frozen_tiles or self._gradient_tiles
                or self._status_icon_data):
            console_px_w = console.width * TILE_PX
            console_px_h = console.height * TILE_PX
            self._renderer.logical_size = (console_px_w, console_px_h)
            if self._embers:
                self._render_embers()
            if self._frozen_tiles:
                self._render_frozen_tiles()
            if self._gradient_tiles:
                self._render_gradient_tiles()
            if self._tile_flashes:
                self._render_tile_flashes()
            if self._status_icon_data:
                self._render_status_icons()
            if self._floating_texts:
                self._render_floating_texts()
            if self._title_card:
                self._render_title_card()

        # Step 5: Single present
        self._renderer.present()

    _TITLE_SCALE = 4  # 4x scale → each letter is 24x20 pixels

    def _render_title_card(self):
        """Draw a dimmed overlay over the map with big centered title text."""
        if self._title_card is None:
            return
        elapsed = time.time() - self._title_card["birth"]
        duration = self._title_card["duration"]
        if elapsed >= duration:
            self._title_card = None
            return

        progress = elapsed / duration
        if progress < 0.4:
            dim_alpha = 200
            text_alpha = 255
        else:
            fade = (progress - 0.4) / 0.6
            dim_alpha = int(200 * (1.0 - fade))
            text_alpha = int(255 * (1.0 - fade))

        from config import MAP_WIDTH, DUNGEON_HEIGHT
        map_px = MAP_OFFSET_X * TILE_PX
        map_py = HEADER_HEIGHT * TILE_PX
        map_pw = MAP_WIDTH * TILE_PX
        map_ph = DUNGEON_HEIGHT * TILE_PX

        old_blend = self._renderer.draw_blend_mode
        self._renderer.draw_blend_mode = tcod.sdl.render.BlendMode.BLEND

        # Dim the map
        self._renderer.draw_color = (0, 0, 0, dim_alpha)
        self._renderer.fill_rect((map_px, map_py, map_pw, map_ph))

        # Draw title text with glyph bitmaps
        text = self._title_card["text"]
        scale = self._TITLE_SCALE
        gw = self._glyph_render_w * scale
        gh = self._glyph_render_h * scale
        spacing = GLYPH_SPACING * scale
        num_chars = sum(1 for c in text if c in self._digit_textures)
        num_spaces = sum(1 for c in text if c == ' ' and ' ' in self._digit_textures)
        total_w = num_chars * gw + (num_chars - 1) * spacing if num_chars else 0

        start_x = map_px + (map_pw - total_w) // 2
        center_y = map_py + (map_ph - gh) // 2

        dx = 0
        for ch in text:
            fg_tex = self._digit_textures.get(ch)
            ol_tex = self._outline_textures.get(ch)
            if fg_tex is None:
                continue
            dest = (start_x + dx, center_y, gw, gh)
            if ol_tex is not None:
                ol_tex.alpha_mod = text_alpha
                self._renderer.copy(ol_tex, dest=dest)
            fg_tex.color_mod = (255, 255, 255)
            fg_tex.alpha_mod = text_alpha
            self._renderer.copy(fg_tex, dest=dest)
            dx += gw + spacing

        self._renderer.draw_blend_mode = old_blend

    def render_title_text_on_console(self, console):
        """No-op — title text is now rendered entirely in the SDL layer."""
        pass

    def _render_tile_flashes(self):
        """Draw fading colored rectangles over tiles (e.g. fire breath impact)."""
        if not self._tile_flashes:
            return
        now = time.time()
        old_blend = self._renderer.draw_blend_mode
        self._renderer.draw_blend_mode = tcod.sdl.render.BlendMode.BLEND

        for flash in self._tile_flashes:
            elapsed = now - flash["birth"]
            delay = flash["delay"]
            duration = flash["duration"]
            # Not started yet (ripple hasn't reached this tile)
            if elapsed < delay:
                continue
            # Expired
            local_elapsed = elapsed - delay
            if local_elapsed >= duration:
                continue
            # Fade: start at full alpha, ease out to 0
            progress = local_elapsed / duration
            alpha = int(180 * (1.0 - progress) ** 1.5)  # ease-out curve
            if alpha <= 0:
                continue
            r, g, b = flash["color"]
            self._renderer.draw_color = (r, g, b, alpha)
            px = (flash["x"] + MAP_OFFSET_X) * TILE_PX
            py = (flash["y"] + HEADER_HEIGHT) * TILE_PX
            self._renderer.fill_rect((px, py, TILE_PX, TILE_PX))

        self._renderer.draw_blend_mode = old_blend

    def _render_status_icons(self):
        """Draw small letter-based status icons above enemies with active effects."""
        if not self._status_icon_data:
            return
        scale = STATUS_ICON_SCALE
        gw = self._glyph_render_w * scale
        gh = self._glyph_render_h * scale
        spacing = STATUS_ICON_SPACING

        for dx, dy, icons in self._status_icon_data:
            num = len(icons)
            total_w = num * gw + (num - 1) * spacing
            tile_px = (dx + MAP_OFFSET_X) * TILE_PX
            tile_py = (dy + HEADER_HEIGHT) * TILE_PX
            start_x = tile_px + (TILE_PX - total_w) / 2
            draw_y = tile_py - gh - 1

            offset = 0
            for ch, color in icons:
                fg_tex = self._digit_textures.get(ch)
                ol_tex = self._outline_textures.get(ch)
                if fg_tex is None:
                    continue
                dest = (start_x + offset, draw_y, gw, gh)
                if ol_tex is not None:
                    ol_tex.alpha_mod = 255
                    self._renderer.copy(ol_tex, dest=dest)
                fg_tex.color_mod = color
                fg_tex.alpha_mod = 255
                self._renderer.copy(fg_tex, dest=dest)
                offset += gw + spacing

    def _render_curse_pulses(self):
        """Curse visuals are rendered on the character in tcod (render_entities).
        This method is a no-op; the SDL layer only keeps the 60fps poll loop alive
        via has_active() when _cursed_tiles is non-empty."""
        pass

    @staticmethod
    def _sample_gradient_color(stops, t):
        """Interpolate multi-stop gradient. stops = [(R,G,B), ...], t = 0.0-1.0."""
        if len(stops) == 2:
            c0, c1 = stops
            return (int(c0[0] + (c1[0] - c0[0]) * t),
                    int(c0[1] + (c1[1] - c0[1]) * t),
                    int(c0[2] + (c1[2] - c0[2]) * t))
        segments = len(stops) - 1
        scaled = t * segments
        idx = min(int(scaled), segments - 1)
        local_t = scaled - idx
        c0, c1 = stops[idx], stops[idx + 1]
        return (int(c0[0] + (c1[0] - c0[0]) * local_t),
                int(c0[1] + (c1[1] - c0[1]) * local_t),
                int(c0[2] + (c1[2] - c0[2]) * local_t))

    def _build_gradient_texture(self, item_id):
        """Build a gradient texture masked by the item tile's alpha channel."""
        config = self._GRADIENT_CONFIG.get(item_id)
        if not config:
            self._gradient_textures[item_id] = False
            return
        tile_file = config[0]
        color_stops = config[1]
        steps = config[3] if len(config) > 3 else 0
        try:
            from PIL import Image as PilImage
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, "dev-assets", tile_file)
            img = PilImage.open(path).convert("RGBA")
            arr = np.array(img, dtype=np.uint8)
            if arr.shape[0] != 16 or arr.shape[1] != 16:
                canvas = np.zeros((16, 16, 4), dtype=np.uint8)
                h, w = arr.shape[:2]
                oy, ox = (16 - h) // 2, (16 - w) // 2
                canvas[oy:oy+h, ox:ox+w] = arr
                arr = canvas
            # Build diagonal gradient: bottom-left → top-right, multi-stop
            grad = np.zeros_like(arr)
            for row in range(16):
                for col in range(16):
                    t = (col + (15 - row)) / 30.0
                    if steps > 0:
                        t = math.floor(t * steps) / steps
                    r, g, b = self._sample_gradient_color(color_stops, t)
                    grad[row, col, 0] = r
                    grad[row, col, 1] = g
                    grad[row, col, 2] = b
            grad[:, :, 3] = arr[:, :, 3]  # mask by original alpha
            tex = self._renderer.upload_texture(grad)
            tex.blend_mode = tcod.sdl.render.BlendMode.BLEND
            tex.scale_mode = tcod.sdl.render.ScaleMode.NEAREST
            self._gradient_textures[item_id] = tex
        except Exception as e:
            print(f"[warn] Could not build gradient texture for {item_id}: {e}")
            self._gradient_textures[item_id] = False

    def _render_gradient_tiles(self):
        """Draw masked gradient overlays on special weapon tiles."""
        if not self._gradient_tiles:
            return

        # Pulsing shimmer for items that use it
        t = time.time()

        for dx, dy, item_id in self._gradient_tiles:
            # Lazy-init per-item texture
            if item_id not in self._gradient_textures:
                self._build_gradient_texture(item_id)
            tex = self._gradient_textures.get(item_id)
            if not tex:
                continue
            config = self._GRADIENT_CONFIG.get(item_id)
            uses_pulse = config[2] if config and len(config) > 2 else True
            pulse_speed = config[4] if config and len(config) > 4 else 1.5
            if uses_pulse:
                tex.alpha_mod = int(80 + 60 * ((math.sin(t * pulse_speed) + 1.0) / 2.0))
            else:
                tex.alpha_mod = 200
            px = (dx + MAP_OFFSET_X) * TILE_PX
            py = (dy + HEADER_HEIGHT) * TILE_PX
            self._renderer.copy(tex, dest=(px, py, TILE_PX, TILE_PX))

    def _render_frozen_tiles(self):
        """Draw a pulsing light-blue transparent overlay with ice crystal pixels on frozen monsters."""
        if not self._frozen_tiles:
            return
        old_blend = self._renderer.draw_blend_mode
        self._renderer.draw_blend_mode = tcod.sdl.render.BlendMode.BLEND

        # Pulse alpha between 60-100 for a subtle shimmer
        t = time.time()
        pulse = (math.sin(t * 2.5) + 1.0) / 2.0  # 0.0-1.0
        base_alpha = int(60 + 40 * pulse)

        for dx, dy in self._frozen_tiles:
            px = (dx + MAP_OFFSET_X) * TILE_PX
            py = (dy + HEADER_HEIGHT) * TILE_PX

            # Light blue transparent overlay
            self._renderer.draw_color = (100, 180, 255, base_alpha)
            self._renderer.fill_rect((px, py, TILE_PX, TILE_PX))

            # Ice crystal pixels — small white/cyan dots at fixed positions
            # Creates a subtle ice texture pattern over the character
            crystal_alpha = int(80 + 60 * pulse)
            ice_pixels = [
                (2, 1), (12, 2), (7, 3),       # top scatter
                (1, 7), (14, 8),                 # sides
                (4, 12), (10, 13), (8, 5),       # mid scatter
                (3, 14), (13, 11), (6, 10),      # bottom scatter
            ]
            for cx, cy in ice_pixels:
                self._renderer.draw_color = (200, 240, 255, crystal_alpha)
                self._renderer.fill_rect((px + cx, py + cy, 2, 2))

        self._renderer.draw_blend_mode = old_blend

    def _render_floating_texts(self):
        """Draw all active floating damage/heal numbers."""
        now = time.time()
        alive = []
        for ft in self._floating_texts:
            elapsed = now - ft.birth
            if elapsed >= FLOAT_DURATION:
                continue
            alive.append(ft)
            progress = elapsed / FLOAT_DURATION

            # Smooth ease-out: fast at start, slows down
            eased = 1.0 - (1.0 - progress) ** 2
            y_offset = eased * FLOAT_DISTANCE_PX

            # Fade out: fully opaque for first 40%, then fade to 0
            if progress < 0.4:
                alpha = 255
            else:
                alpha = int(255 * (1.0 - (progress - 0.4) / 0.6))

            # Calculate total text width for centering (using bordered glyph size)
            num_chars = ft.num_chars
            char_w = self._glyph_render_w * GLYPH_SCALE
            char_h = self._glyph_render_h * GLYPH_SCALE
            spacing = GLYPH_SPACING * GLYPH_SCALE
            total_w = num_chars * char_w + (num_chars - 1) * spacing if num_chars else 0

            # Center on the originating tile
            start_x = ft.x_px + (TILE_PX - total_w) / 2
            draw_y = ft.y_px - y_offset

            dx = 0
            for ch in ft.text:
                fg_tex = self._digit_textures.get(ch)
                ol_tex = self._outline_textures.get(ch)
                if fg_tex is None:
                    continue
                dest_x = start_x + dx
                dest = (dest_x, draw_y, char_w, char_h)
                # Draw black outline first (no color tint)
                if ol_tex is not None:
                    ol_tex.alpha_mod = alpha
                    self._renderer.copy(ol_tex, dest=dest)
                # Draw colored foreground on top
                fg_tex.color_mod = ft.color
                fg_tex.alpha_mod = alpha
                self._renderer.copy(fg_tex, dest=dest)
                dx += char_w + spacing

        self._floating_texts = alive

    def _spawn_embers(self):
        """Spawn new ember particles for each visible fire tile based on elapsed time."""
        if not self._fire_tiles:
            return
        now = time.time()
        dt = now - self._last_ember_spawn if self._last_ember_spawn > 0 else 0.016
        self._last_ember_spawn = now
        # How many embers to spawn this frame across all fire tiles
        embers_per_tile = _EMBER_SPAWN_RATE * dt
        for fx, fy in self._fire_tiles:
            # Probabilistic spawn: fractional part becomes a chance
            count = int(embers_per_tile)
            if _rng.random() < (embers_per_tile - count):
                count += 1
            for _ in range(count):
                # Random position within the fire tile
                px = (fx + MAP_OFFSET_X) * TILE_PX + _rng.uniform(2, TILE_PX - 2)
                py = (fy + HEADER_HEIGHT) * TILE_PX + _rng.uniform(0, TILE_PX - 4)
                self._embers.append(_Ember(
                    x_px=px,
                    y_px=py,
                    color=_rng.choice(_EMBER_COLORS),
                    birth=now,
                    lifetime=_rng.uniform(_EMBER_LIFETIME_MIN, _EMBER_LIFETIME_MAX),
                    drift_x=_rng.uniform(-_EMBER_DRIFT_X_RANGE, _EMBER_DRIFT_X_RANGE),
                    drift_y=_rng.uniform(_EMBER_DRIFT_Y * 1.3, _EMBER_DRIFT_Y * 0.7),
                    size=_rng.choice([1, 1, 2, 2, 3]),
                ))

    def _render_embers(self):
        """Draw all active ember particles as small colored dots."""
        if not self._embers:
            return
        now = time.time()
        old_blend = self._renderer.draw_blend_mode
        self._renderer.draw_blend_mode = tcod.sdl.render.BlendMode.BLEND
        alive = []
        for ember in self._embers:
            elapsed = now - ember.birth
            if elapsed >= ember.lifetime:
                continue
            alive.append(ember)
            progress = elapsed / ember.lifetime
            # Position: drift from spawn point
            x = ember.x_px + ember.drift_x * elapsed
            y = ember.y_px + ember.drift_y * elapsed
            # Fade out in the last 40%
            if progress < 0.6:
                alpha = 220
            else:
                alpha = int(220 * (1.0 - (progress - 0.6) / 0.4))
            if alpha <= 0:
                continue
            r, g, b = ember.color
            self._renderer.draw_color = (r, g, b, alpha)
            s = ember.size
            self._renderer.fill_rect((int(x), int(y), s, s))
        self._embers = alive
        self._renderer.draw_blend_mode = old_blend