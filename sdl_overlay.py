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
        self._init_digit_textures()

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
        """Spawn a floating text at a dungeon position."""
        px, py = self._tile_to_pixel(dungeon_x, dungeon_y)
        self._floating_texts.append(_FloatingText(px, py, text, color))

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
        return (len(self._floating_texts) > 0
                or len(self._cursed_tiles) > 0
                or self._title_card is not None
                or len(self._tile_flashes) > 0)

    def update_cursed_tiles(self, engine):
        """Rebuild the list of visible cursed monster tiles from current game state."""
        tiles = []
        for entity in engine.dungeon.entities:
            if (entity.entity_type == "monster"
                    and entity.alive
                    and engine.dungeon.visible[entity.y, entity.x]
                    and any(getattr(e, 'is_curse', False) for e in entity.status_effects)):
                tiles.append((entity.x, entity.y))
        self._cursed_tiles = tiles

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

        # Step 3: Draw overlays on top (only if there's something to draw)
        has_overlays = (self._floating_texts or self._tile_flashes
                        or self._title_card)
        if has_overlays:
            # Set logical size so overlays draw in tile-pixel coordinates
            console_px_w = console.width * TILE_PX
            console_px_h = console.height * TILE_PX
            self._renderer.logical_size = (console_px_w, console_px_h)
            self._render_tile_flashes()
            self._render_floating_texts()
            self._render_title_card()

        # Step 4: Single present
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

    def _render_curse_pulses(self):
        """Curse visuals are rendered on the character in tcod (render_entities).
        This method is a no-op; the SDL layer only keeps the 60fps poll loop alive
        via has_active() when _cursed_tiles is non-empty."""
        pass

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
            num_chars = sum(1 for c in ft.text if c in self._digit_textures)
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