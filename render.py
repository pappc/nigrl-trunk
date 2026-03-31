"""
Rendering system using tcod.
"""

import math
import time
import tcod
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    TILE_WALL, TILE_FLOOR,
    HEADER_HEIGHT, UI_HEIGHT, MAX_MESSAGES,
    MAP_WIDTH, PANEL_WIDTH,
    LEFT_PANEL_WIDTH, MAP_OFFSET_X,
    INVENTORY_KEYS, LOG_HISTORY_SIZE, RING_SLOTS, RING_FINGER_NAMES,
    DEV_MODE, ENERGY_THRESHOLD, PLAYER_BASE_SPEED,
)
from items import get_item_def, find_recipe, is_stackable, build_inventory_display_name, get_strain_color, PREFIX_TOOL_ITEMS, generate_examine_lines
from foods import FOOD_DEFS
from menu_state import MenuState
from enemies import MONSTER_REGISTRY
from abilities import ABILITY_REGISTRY
from skills import get_perk, SKILL_NAMES as _SKILL_NAMES

def _sample_gradient(stops, t):
    """Interpolate between multi-stop gradient colors. stops = [(r,g,b), ...], t = 0.0-1.0."""
    if len(stops) == 2:
        c0, c1 = stops
        return (int(c0[0] + (c1[0] - c0[0]) * t),
                int(c0[1] + (c1[1] - c0[1]) * t),
                int(c0[2] + (c1[2] - c0[2]) * t))
    # Multi-stop: find which segment t falls in
    segments = len(stops) - 1
    scaled = t * segments
    idx = min(int(scaled), segments - 1)
    local_t = scaled - idx
    c0, c1 = stops[idx], stops[idx + 1]
    return (int(c0[0] + (c1[0] - c0[0]) * local_t),
            int(c0[1] + (c1[1] - c0[1]) * local_t),
            int(c0[2] + (c1[2] - c0[2]) * local_t))


def _print_gradient_text(console, x, y, text, gradient, bg):
    """Print text with per-character color gradient using direct array writes."""
    n = max(len(text) - 1, 1)
    for i, ch in enumerate(text):
        cx = x + i
        if 0 <= cx < console.width and 0 <= y < console.height:
            console.ch[cx, y] = ord(ch)
            console.fg[cx, y] = _sample_gradient(gradient, i / n)
            console.bg[cx, y] = bg


def _print_alternating_text(console, x, y, text, colors, bg):
    """Print text with alternating per-character colors using direct array writes."""
    nc = len(colors)
    for i, ch in enumerate(text):
        cx = x + i
        if 0 <= cx < console.width and 0 <= y < console.height:
            console.ch[cx, y] = ord(ch)
            console.fg[cx, y] = colors[i % nc]
            console.bg[cx, y] = bg


# ── Unified border / panel colors ──────────────────────────────────────────
C_FRAME       = (130, 130, 190)    # outer double-line frame (screen edge)
C_PANEL_BORDER = (100, 100, 160)   # inner single-line panel dividers
C_SECTION_DIV  = (60, 60, 100)     # section dividers within panels
C_PANEL_TITLE  = (255, 255, 180)   # panel / section title text
C_PANEL_BG     = (18, 18, 28)      # panel background


def _draw_title_border(console, x, w, y, title, bg,
                       fg_border=None, fg_title=None):
    """Draw a horizontal border with embedded title: ──┤ TITLE ├──"""
    if fg_border is None:
        fg_border = C_PANEL_BORDER
    if fg_title is None:
        fg_title = C_PANEL_TITLE
    for px in range(w):
        console.print(x + px, y, "─", fg=fg_border, bg=bg)
    label = f"┤ {title} ├"
    tx = x + (w - len(label)) // 2
    console.print(tx, y, "┤", fg=fg_border, bg=bg)
    console.print(tx + 1, y, f" {title} ", fg=fg_title, bg=bg)
    console.print(tx + len(label) - 1, y, "├", fg=fg_border, bg=bg)


def _is_combine_target(src, cand) -> bool:
    """Return True if cand is a valid combine target for src."""
    # Graffiti gun loading: only spray cans
    if src.item_id == "graffiti_gun":
        return cand.item_id in ("red_spray_paint", "blue_spray_paint", "green_spray_paint", "orange_spray_paint", "silver_spray_paint")
    if find_recipe(src.item_id, cand.item_id):
        return True
    if src.item_id in PREFIX_TOOL_ITEMS and cand.item_id in FOOD_DEFS:
        return getattr(cand, "prefix", None) is None
    if src.item_id in FOOD_DEFS and cand.item_id in PREFIX_TOOL_ITEMS:
        return getattr(src, "prefix", None) is None
    # Items with torch_burn use_effect can target any item
    src_def = get_item_def(src.item_id)
    if src_def and (src_def.get("use_effect") or {}).get("type") == "torch_burn":
        return True
    return False


def wrap_text_for_width(text, max_width, indent_width=0):
    """
    Wrap text to fit within max_width.
    Returns a list of lines, each <= max_width characters.
    First line has no indent, subsequent lines are indented by indent_width.
    """
    if len(text) <= max_width:
        return [text]

    lines = []
    words = text.split(" ")
    current_line = ""
    indent = " " * indent_width
    first_line = True

    for word in words:
        prefix = "" if first_line else indent
        if not current_line:
            test_line = prefix + word
        else:
            test_line = current_line + " " + word

        if len(test_line) <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = prefix + word
            first_line = False

    if current_line:
        lines.append(current_line)

    return lines


def render_header(console, engine):
    """Render the top header as the outer top border with embedded zone name."""
    from config import get_zone_for_floor, get_zone_total_floors
    zone_key, zone_floor, zone_display, zone_type = get_zone_for_floor(engine.current_floor)
    if zone_type == "pseudozone":
        floor_text = zone_display
    else:
        zone_total = get_zone_total_floors(zone_key)
        floor_text = f"{zone_display} - Floor {zone_floor + 1}/{zone_total}"

    from config import get_zone_colors
    zc = get_zone_colors(zone_key)
    HDR_BG = zc["header_bg"]
    HDR_FG = zc["header_fg"]

    # Fill header background
    for x in range(SCREEN_WIDTH):
        console.print(x, 0, " ", bg=HDR_BG)

    # Double-line top border
    for x in range(SCREEN_WIDTH):
        console.print(x, 0, "═", fg=C_FRAME, bg=HDR_BG)
    console.print(0, 0, "╔", fg=C_FRAME, bg=HDR_BG)
    console.print(SCREEN_WIDTH - 1, 0, "╗", fg=C_FRAME, bg=HDR_BG)
    # Junctions where panel borders meet the top
    console.print(LEFT_PANEL_WIDTH - 1, 0, "╤", fg=C_FRAME, bg=HDR_BG)
    console.print(MAP_OFFSET_X + MAP_WIDTH, 0, "╤", fg=C_FRAME, bg=HDR_BG)

    # Center the zone text across the full screen width
    tx = SCREEN_WIDTH // 2 - len(floor_text) // 2
    console.print(tx - 1, 0, "╡", fg=C_FRAME, bg=HDR_BG)
    console.print(tx, 0, f" {floor_text} ", fg=HDR_FG, bg=HDR_BG)
    console.print(tx + len(floor_text) + 1, 0, "╞", fg=C_FRAME, bg=HDR_BG)

    # Seed display (right side of header)
    seed_label = f"Seed: {engine.seed}"
    seed_x = SCREEN_WIDTH - len(seed_label) - 2
    if DEV_MODE:
        inv_active = getattr(engine.player, "dev_invincible", False)
        dev_label = "[DEV | INV]" if inv_active else "[DEV]"
        dev_col = (255, 80, 80) if not inv_active else (80, 255, 80)
        console.print(SCREEN_WIDTH - len(dev_label) - 2, 0, dev_label, fg=dev_col, bg=HDR_BG)
        seed_x = SCREEN_WIDTH - len(dev_label) - len(seed_label) - 4
    console.print(seed_x, 0, seed_label, fg=(100, 100, 130), bg=HDR_BG)


def render_all(console, engine):
    """Render the entire game state."""
    render_header(console, engine)
    render_stats_panel(console, engine)
    render_dungeon(console, engine.dungeon)
    render_entities(console, engine.dungeon)
    render_inventory_panel(console, engine)
    render_hotbar(console, engine)
    render_ui(console, engine)

    # Overlay menus (one at a time)
    if engine.menu_state == MenuState.SKILLS:
        render_skills_menu(console, engine)
    elif engine.menu_state == MenuState.CHAR_SHEET:
        render_char_sheet(console, engine)
    elif engine.menu_state == MenuState.ITEM_MENU:
        render_item_menu(console, engine)
    elif engine.menu_state == MenuState.COMBINE_SELECT:
        render_combine_select(console, engine)
    elif engine.menu_state == MenuState.EQUIPMENT:
        render_equipment_screen(console, engine)
    elif engine.menu_state == MenuState.LOG:
        render_log_menu(console, engine)
    elif engine.menu_state == MenuState.DESTROY_CONFIRM:
        render_destroy_confirm(console, engine)
    elif engine.menu_state == MenuState.EXAMINE:
        render_examine(console, engine)
    elif engine.menu_state == MenuState.RING_REPLACE:
        render_ring_replace_menu(console, engine)
    elif engine.menu_state == MenuState.BESTIARY:
        render_bestiary_menu(console, engine)
    elif engine.menu_state == MenuState.TARGETING:
        render_targeting_mode(console, engine)
    elif engine.menu_state == MenuState.ENTITY_TARGETING:
        render_entity_targeting_mode(console, engine)
    elif engine.menu_state == MenuState.ADJACENT_TILE_TARGETING:
        render_adjacent_tile_targeting_mode(console, engine)
    elif engine.menu_state == MenuState.ABILITIES:
        render_abilities_menu(console, engine)
    elif engine.menu_state == MenuState.PERKS:
        render_perks_menu(console, engine)
    elif engine.menu_state == MenuState.DEV_MENU:
        render_dev_menu(console, engine)
    elif engine.menu_state == MenuState.DEV_ITEM_SELECT:
        render_dev_item_select(console, engine)
    elif engine.menu_state == MenuState.DEV_FLOOR_SELECT:
        render_dev_floor_select(console, engine)
    elif engine.menu_state == MenuState.DEV_SKILL_SELECT:
        render_dev_skill_select(console, engine)
    elif engine.menu_state == MenuState.DEEP_FRYER:
        render_deep_fryer_menu(console, engine)
    elif engine.menu_state == MenuState.GUN_TARGETING:
        render_gun_targeting_mode(console, engine)
    elif engine.menu_state == MenuState.PERK_POPUP:
        render_perk_popup(console, engine)
    elif engine.menu_state == MenuState.LOOK_TARGETING:
        render_look_targeting(console, engine)
    elif engine.menu_state == MenuState.LOOK_INFO:
        render_look_targeting(console, engine)
        render_look_info(console, engine)
    elif engine.menu_state == MenuState.SETTINGS:
        render_settings_menu(console, engine)
    elif engine.menu_state == MenuState.VENDING_MACHINE:
        render_vending_machine_menu(console, engine)
    elif engine.menu_state == MenuState.MIDAS_BREW:
        render_midas_brew_menu(console, engine)
    elif engine.menu_state == MenuState.SHOP_ITEM:
        render_shop_item_popup(console, engine)

def _wall_noise(x, y):
    """Return two deterministic offsets for a wall tile — subtle grime variation."""
    h1 = (x * 2654435761 ^ y * 2246822519) & 0xFFFFFFFF
    h2 = (x * 2246822519 ^ y * 2654435761) & 0xFFFFFFFF
    n1 = ((h1 >> 16) & 0xFF) % 17 - 8    # -8 to +8  (warm channel variation)
    n2 = ((h2 >> 16) & 0xFF) % 11 - 5    # -5 to +5  (cool channel suppression)
    return n1, n2


def render_dungeon(console, dungeon):
    """Render the dungeon map, offset right by MAP_OFFSET_X to make room for the stats panel."""
    from config import get_zone_colors
    zone = getattr(dungeon, "zone", "crack_den")
    zc = get_zone_colors(zone)
    # Unpack color scheme once for the tight loop
    wfb = zc["wall_fg_base"]
    wbg = zc["wall_bg"]
    fbg = zc["floor_bg"]
    ewfb = zc["explored_wall_fg_base"]
    ewbg = zc["explored_wall_bg"]
    efbg = zc["explored_floor_bg"]

    spray_paint = dungeon.spray_paint
    grease_tiles = dungeon.grease_tiles

    for y in range(dungeon.height):
        for x in range(dungeon.width):
            cx = x + MAP_OFFSET_X
            cy = y + HEADER_HEIGHT
            tile = dungeon.tiles[y][x]
            is_visible = dungeon.visible[y, x]
            is_explored = dungeon.explored[y, x]

            if is_visible:
                if tile == TILE_WALL:
                    n1, n2 = _wall_noise(x, y)
                    fg = (max(0, min(255, wfb[0] + n1)),
                          max(0, min(255, wfb[1] + n2)),
                          max(0, min(255, wfb[2] + (n1 + n2) // 2)))
                    console.print(cx, cy, "#", fg=fg, bg=wbg)
                elif tile == TILE_FLOOR:
                    if (x, y) in grease_tiles:
                        console.print(cx, cy, "~", fg=(190, 170, 50), bg=(40, 35, 15))
                    elif (sp := spray_paint.get((x, y))) is not None:
                        if sp == "red":
                            console.print(cx, cy, " ", bg=(140, 15, 15))
                        elif sp == "blue":
                            console.print(cx, cy, " ", bg=(15, 30, 140))
                        elif sp == "green":
                            console.print(cx, cy, " ", bg=(15, 100, 15))
                        elif sp == "orange":
                            console.print(cx, cy, " ", bg=(140, 80, 10))
                        elif sp == "silver":
                            console.print(cx, cy, " ", bg=(100, 100, 110))
                    else:
                        console.print(cx, cy, " ", bg=fbg)
            elif is_explored:
                if tile == TILE_WALL:
                    n1, n2 = _wall_noise(x, y)
                    fg = (max(0, min(255, ewfb[0] + n1 // 3)),
                          max(0, min(255, ewfb[1] + n2 // 3)),
                          max(0, min(255, ewfb[2] + (n1 + n2) // 6)))
                    console.print(cx, cy, "#", fg=fg, bg=ewbg)
                elif tile == TILE_FLOOR:
                    if (x, y) in grease_tiles:
                        console.print(cx, cy, "~", fg=(95, 85, 25), bg=(20, 18, 8))
                    elif (sp := spray_paint.get((x, y))) is not None:
                        if sp == "red":
                            console.print(cx, cy, " ", bg=(70, 8, 8))
                        elif sp == "blue":
                            console.print(cx, cy, " ", bg=(8, 15, 70))
                        elif sp == "green":
                            console.print(cx, cy, " ", bg=(8, 50, 8))
                        elif sp == "orange":
                            console.print(cx, cy, " ", bg=(70, 40, 5))
                        elif sp == "silver":
                            console.print(cx, cy, " ", bg=(50, 50, 55))
                    else:
                        console.print(cx, cy, " ", bg=efbg)
            else:
                console.print(cx, cy, " ", bg=(0, 0, 0))


def get_entity_color(entity):
    """Get color for entity based on type. Items use their ITEM_DEF color."""
    if entity.entity_type == "player":
        return (255, 255, 255)  # White
    elif entity.entity_type == "monster":
        return entity.color
    elif entity.entity_type == "item" and entity.item_id:
        strain = getattr(entity, "strain", None)
        if strain:
            return get_strain_color(strain)
        defn = get_item_def(entity.item_id)
        if defn:
            if defn.get("color_pulse"):
                import time, math
                t = time.time()
                lo, hi = defn["color_pulse"]
                frac = (1 + math.sin(t * 3)) / 2
                return tuple(int(lo[i] + (hi[i] - lo[i]) * frac) for i in range(3))
            return defn["color"]
        return entity.color
    elif getattr(entity, "hazard_type", None) == "vending_machine":
        import time, math
        t = time.time()
        pulse = int(140 + 115 * ((1 + math.sin(t * 3)) / 2))
        return (0, pulse, pulse)
    else:
        return entity.color      # Fallback to entity's own color


def render_entities(console, dungeon):
    """Render visible entities on the map, offset by MAP_OFFSET_X.

    Render order: items/cash first, then monsters, then player last.
    This ensures monsters always appear on top of floor items/cash,
    and the player always appears on top of everything.
    """
    def _render_priority(e):
        if e.entity_type == "player":
            return 2
        elif e.entity_type == "monster":
            return 1
        elif e.entity_type == "hazard":
            return -1 if e.hazard_type in ("fire", "toxic_creep") else 0
        return 0  # item, cash

    for entity in sorted(dungeon.entities, key=_render_priority):
        if not entity.alive:
            continue
        if dungeon.visible[entity.y, entity.x]:
            color = get_entity_color(entity)
            # Curse pulse: letter oscillates between deep purples (SDL keeps 60fps)
            if entity.entity_type == "monster" and any(
                getattr(e, 'is_curse', False) for e in entity.status_effects
            ):
                t = (math.sin(time.time() * 3.0) + 1.0) / 2.0
                color = (
                    int(90 + 50 * t),           # R: 90–140
                    0,
                    int(120 + 80 * (1.0 - t)),  # B: 120–200
                )
            console.print(entity.x + MAP_OFFSET_X, entity.y + HEADER_HEIGHT, entity.char, fg=color)
        elif entity.always_visible and dungeon.explored[entity.y, entity.x]:
            # Landmark: dimmed color so player can see it from anywhere on explored map
            color = get_entity_color(entity)
            dimmed = tuple(max(0, c // 3) for c in color)
            console.print(entity.x + MAP_OFFSET_X, entity.y + HEADER_HEIGHT, entity.char, fg=dimmed)


def get_message_color(msg):
    """Get color for a plain-string message based on content."""
    msg_lower = msg.lower()
    if "damage" in msg_lower or "dies" in msg_lower:
        return (255, 100, 100)  # Red for damage/death
    elif "healing" in msg_lower or "used" in msg_lower:
        return (100, 255, 100)  # Green for healing
    elif "picked up $" in msg_lower:
        return (255, 215, 0)    # Gold for cash
    elif "picked up" in msg_lower:
        return (255, 200, 100)  # Orange for items
    else:
        return (200, 200, 100)  # Yellow default


def _render_msg(console, x, y, msg, max_width, bg, fade=1.0):
    """Render a message that is either a plain string or a list of (text, color) segments.

    Plain strings use get_message_color for the whole line.
    Segment lists render each part in its own color, truncated to max_width total chars.
    fade: 0.0–1.0 brightness multiplier applied to all colors.
    """
    def _fade(color):
        return tuple(int(c * fade) for c in color)

    if isinstance(msg, str):
        console.print(x, y, msg[:max_width], fg=_fade(get_message_color(msg)), bg=bg)
    else:
        cx        = x
        remaining = max_width
        for text, color in msg:
            if remaining <= 0:
                break
            chunk = text[:remaining]
            console.print(cx, y, chunk, fg=_fade(color), bg=bg)
            cx        += len(chunk)
            remaining -= len(chunk)


def _draw_panel(console, x, y, w, h, bg):
    """Draw a filled bordered panel."""
    for py in range(h):
        for px in range(w):
            console.print(x + px, y + py, " ", bg=bg)
    for px in range(w):
        console.print(x + px, y,         "─", fg=C_PANEL_BORDER, bg=bg)
        console.print(x + px, y + h - 1, "─", fg=C_PANEL_BORDER, bg=bg)
    for py in range(h):
        console.print(x,         y + py, "│", fg=C_PANEL_BORDER, bg=bg)
        console.print(x + w - 1, y + py, "│", fg=C_PANEL_BORDER, bg=bg)
    console.print(x,         y,         "┌", fg=C_PANEL_BORDER, bg=bg)
    console.print(x + w - 1, y,         "┐", fg=C_PANEL_BORDER, bg=bg)
    console.print(x,         y + h - 1, "└", fg=C_PANEL_BORDER, bg=bg)
    console.print(x + w - 1, y + h - 1, "┘", fg=C_PANEL_BORDER, bg=bg)


def render_skills_menu(console, engine):
    """Render the skills overlay panel with potential/real exp and spend prompt."""
    BG       = (22, 22, 32)
    C_TITLE  = (255, 255, 180)
    C_HEAD   = (180, 180, 255)
    C_LABEL  = (180, 180, 180)
    C_VALUE  = (255, 255, 255)
    C_XP     = (120, 200, 120)
    C_MAXED  = (255, 200, 50)
    C_HINT   = (100, 100, 100)
    C_DIV    = (80,  80, 120)
    C_CURSOR = (50,  50,  80)   # highlighted row bg
    C_SP     = (255, 200, 100)  # skill points colour
    C_POT    = (160, 200, 255)  # potential exp colour

    unlocked_skills = sorted(engine.skills.unlocked(), key=lambda s: s.name.lower())
    num_skills = len(unlocked_skills)

    # Handle empty case
    if num_skills == 0:
        panel_w = 40
        panel_h = 5
        panel_x = (SCREEN_WIDTH  - panel_w) // 2
        panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

        _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)
        title = "SKILLS"
        console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1,
                      title, fg=C_TITLE, bg=BG)
        msg = "No skills unlocked yet"
        console.print(panel_x + (panel_w - len(msg)) // 2, panel_y + 2,
                      msg, fg=C_LABEL, bg=BG)
        return

    # Layout constants
    # Columns: Skill=2, Lv=18, Pot=23, Real=32, Next=41, Perk=51
    PERK_COL = 51
    DESC_ROWS = 3  # lines for next-perk description preview
    panel_w = 72
    # borders(2) + title(1) + sp(1) + div(1) + header(1) + div(1) + skills(n)
    # + desc_div(1) + desc_label(1) + desc(DESC_ROWS) + footer(1) + border_bottom(implicit in _draw_panel)
    panel_h = num_skills + 9 + DESC_ROWS + 2
    panel_x = (SCREEN_WIDTH  - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "SKILLS"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1,
                  title, fg=C_TITLE, bg=BG)

    # Skill Points row
    sp_label = "Skill Points: "
    sp_val   = str(int(engine.skills.skill_points))
    console.print(panel_x + 2, panel_y + 2, sp_label, fg=C_LABEL, bg=BG)
    console.print(panel_x + 2 + len(sp_label), panel_y + 2, sp_val, fg=C_SP, bg=BG)

    # Divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 3, "─", fg=C_DIV, bg=BG)

    # Column headers  — Skill=2, Lv=18, Pot=23, Real=32, Next=41, Perk=51
    console.print(panel_x + 2,        panel_y + 4, "Skill",     fg=C_HEAD, bg=BG)
    console.print(panel_x + 18,       panel_y + 4, "Lv",        fg=C_HEAD, bg=BG)
    console.print(panel_x + 23,       panel_y + 4, "Pot",       fg=C_HEAD, bg=BG)
    console.print(panel_x + 32,       panel_y + 4, "Real",      fg=C_HEAD, bg=BG)
    console.print(panel_x + 41,       panel_y + 4, "Next",      fg=C_HEAD, bg=BG)
    console.print(panel_x + PERK_COL, panel_y + 4, "Next Perk", fg=C_HEAD, bg=BG)

    # Divider under column headers
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 5, "─", fg=C_DIV, bg=BG)

    perk_max_len = panel_w - PERK_COL - 2  # chars available before right border

    # Track the selected skill's next perk for the description box
    selected_next_perk = None
    selected_skill_name = ""

    # Skill rows (only unlocked skills)
    for i, skill in enumerate(unlocked_skills):
        row = panel_y + 6 + i
        is_selected = (i == engine.skills_cursor)
        row_bg = C_CURSOR if is_selected else BG
        cursor_char = "►" if is_selected else " "

        if skill.is_maxed():
            real_str = "MAX"
            next_str = "---"
            perk_str = "---"
            c_real   = C_MAXED
            c_perk   = C_MAXED
            if is_selected:
                selected_skill_name = skill.name
        else:
            real_str  = str(int(skill.real_exp))
            next_str  = str(skill.xp_needed())
            c_real    = C_XP
            next_level = skill.level + 1
            perk = get_perk(skill.name, next_level)
            perk_str  = (perk["name"] if perk else "???")[:perk_max_len]
            c_perk    = C_HINT
            if is_selected:
                selected_next_perk = perk
                selected_skill_name = skill.name

        pot_str = str(int(skill.potential_exp))

        # Fill row bg for selected
        if is_selected:
            for px in range(1, panel_w - 1):
                console.print(panel_x + px, row, " ", bg=row_bg)

        console.print(panel_x + 1,        row, cursor_char,      fg=C_SP,    bg=row_bg)
        console.print(panel_x + 2,        row, skill.name,       fg=C_LABEL, bg=row_bg)
        console.print(panel_x + 18,       row, str(skill.level), fg=C_VALUE, bg=row_bg)
        console.print(panel_x + 23,       row, pot_str,          fg=C_POT,   bg=row_bg)
        console.print(panel_x + 32,       row, real_str,         fg=c_real,  bg=row_bg)
        console.print(panel_x + 41,       row, next_str,         fg=C_LABEL, bg=row_bg)
        console.print(panel_x + PERK_COL, row, perk_str,         fg=c_perk,  bg=row_bg)

    # --- Next Perk Description Preview ---
    desc_div_y = panel_y + 6 + num_skills
    _draw_title_border(console, panel_x + 1, panel_w - 2, desc_div_y,
                       "Next Perk", BG)

    C_DESC     = (200, 200, 170)
    C_NODESC   = (80,  80,  80)
    C_PERKNAME = (255, 215, 0)
    desc_inner_w = panel_w - 4

    if selected_next_perk and selected_next_perk.get("perk_type") != "none":
        perk_label = selected_next_perk["name"]
        ptype = selected_next_perk.get("perk_type", "")
        TYPE_TAGS = {"stat": "[STAT]", "passive": "[PASSIVE]", "activated": "[ABILITY]", "grant_item": "[ITEM]"}
        tag = TYPE_TAGS.get(ptype, "")
        header_line = f"{perk_label}  {tag}" if tag else perk_label
        console.print(panel_x + 2, desc_div_y + 1, header_line[:desc_inner_w],
                      fg=C_PERKNAME, bg=BG)

        desc = selected_next_perk.get("desc", "")
        if desc:
            wrapped = _wrap_text(desc, desc_inner_w)
            for j, line in enumerate(wrapped[:DESC_ROWS]):
                console.print(panel_x + 2, desc_div_y + 2 + j, line, fg=C_DESC, bg=BG)
        else:
            console.print(panel_x + 2, desc_div_y + 2, "No description.", fg=C_NODESC, bg=BG)
    else:
        if selected_next_perk and selected_next_perk.get("perk_type") == "none":
            console.print(panel_x + 2, desc_div_y + 1, "???", fg=C_NODESC, bg=BG)
        else:
            msg = "Skill maxed." if selected_skill_name else "No skill selected."
            console.print(panel_x + 2, desc_div_y + 1, msg, fg=C_NODESC, bg=BG)

    # Footer
    footer_y = panel_y + panel_h - 2
    if engine.skills_spend_mode:
        sel_skill  = unlocked_skills[engine.skills_cursor] if engine.skills_cursor < len(unlocked_skills) else unlocked_skills[0]
        skill_name = sel_skill.name
        max_spend  = min(int(engine.skills.skill_points),
                         int(sel_skill.potential_exp))
        prompt = f"Spend on {skill_name} (max {max_spend}): {engine.skills_spend_input}_"
        console.print(panel_x + 2, footer_y, prompt, fg=C_SP, bg=BG)
    else:
        hint = "[Enter] Spend  [↑↓] Nav  [S/Esc] Close"
        console.print(panel_x + (panel_w - len(hint)) // 2,
                      footer_y, hint, fg=C_HINT, bg=BG)


def render_stats_panel(console, engine):
    """Render the persistent left-side stats / health / status panel."""
    BG        = C_PANEL_BG
    C_LABEL   = (180, 180, 180)
    C_VALUE   = (255, 255, 255)
    C_HP_OK   = (80, 220, 80)
    C_HP_LOW  = (220, 80, 80)
    C_HP_BAR  = (40, 120, 40)
    C_HP_EMPTY = (30, 30, 30)
    C_ARMOR_BAR = (100, 180, 255)
    C_ARMOR_EMPTY = (30, 30, 30)
    C_BUFF    = (100, 220, 255)
    C_DEBUFF  = (255, 100, 100)
    C_EMPTY   = (80, 80, 80)

    pw    = LEFT_PANEL_WIDTH          # 22 cols (0..21)
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT  # rows available between header and UI bar

    # Background fill
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        for x in range(pw):
            console.print(x, y, " ", bg=BG)

    # Outer left border (screen edge)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(0, y, "║", fg=C_FRAME, bg=BG)

    # Right border (separator between stats panel and map)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(pw - 1, y, "│", fg=C_PANEL_BORDER, bg=BG)

    # ── Title-in-border ─────────────────────────────────────────────
    _draw_title_border(console, 1, pw - 2, HEADER_HEIGHT, "CHARACTER", BG)

    lx = 2                        # left margin (1 col padding from border)
    row = HEADER_HEIGHT + 2       # 1 row gap after title border

    # ── Health ───────────────────────────────────────────────────────
    p = engine.player
    hp_ratio = p.hp / max(1, p.max_hp)
    if hp_ratio > 0.75:
        hp_color = C_HP_OK              # green
    elif hp_ratio > 0.5:
        hp_color = (140, 220, 60)       # yellow-green
    elif hp_ratio > 0.3:
        hp_color = (220, 200, 50)       # yellow
    elif hp_ratio > 0.15:
        hp_color = (220, 120, 40)       # orange
    else:
        hp_color = C_HP_LOW             # red

    hp_label = "HP"
    hp_value = f"{p.hp}/{p.max_hp}"
    console.print(lx, row, f"{hp_label} {hp_value}", fg=C_LABEL, bg=BG)
    console.print(lx + len(hp_label) + 1, row, hp_value, fg=hp_color, bg=BG)
    row += 1

    # HP bar — fills inner width (left margin + right border margin)
    bar_w   = pw - lx - 2         # usable bar chars
    filled  = round(bar_w * hp_ratio)
    empty   = bar_w - filled
    console.print(lx, row, "█" * filled, fg=hp_color,  bg=BG)
    console.print(lx + filled, row, "░" * empty,  fg=C_HP_EMPTY, bg=BG)
    row += 1

    # ── Armor ────────────────────────────────────────────────────────
    armor_ratio = p.armor / max(1, p.max_armor) if p.max_armor > 0 else 0
    armor_label = "Armor"
    armor_value = f"{p.armor}/{p.max_armor}"
    console.print(lx, row, f"{armor_label} {armor_value}", fg=C_LABEL, bg=BG)
    console.print(lx + len(armor_label) + 1, row, armor_value, fg=C_VALUE, bg=BG)
    row += 1

    # Armor bar
    filled_armor  = round(bar_w * armor_ratio)
    empty_armor   = bar_w - filled_armor
    console.print(lx, row, "█" * filled_armor, fg=C_ARMOR_BAR, bg=BG)
    console.print(lx + filled_armor, row, "░" * empty_armor, fg=C_ARMOR_EMPTY, bg=BG)
    row += 1

    # ── Temp HP (only visible when > 0) ──────────────────────────
    C_MAGE_BAR   = (40, 60, 200)
    C_MAGE_EMPTY = (20, 20, 40)
    ma = getattr(p, "temp_hp", 0)
    if ma > 0:
        ma_label = "Temp HP"
        ma_value = str(ma)
        console.print(lx, row, f"{ma_label} ", fg=C_LABEL, bg=BG)
        console.print(lx + len(ma_label) + 1, row, ma_value, fg=(80, 120, 255), bg=BG)
        row += 1
        # Bar: doubling scale — 50, 100, 200, 400, ...
        ma_cap = 50
        while ma > ma_cap:
            ma_cap *= 2
        ma_bar_fill = min(bar_w, max(1, bar_w * ma // ma_cap))
        ma_bar_empty = bar_w - ma_bar_fill
        console.print(lx, row, "█" * ma_bar_fill, fg=C_MAGE_BAR, bg=BG)
        console.print(lx + ma_bar_fill, row, "░" * ma_bar_empty, fg=C_MAGE_EMPTY, bg=BG)
        row += 1

    # ── Meth (only visible after entering the Meth Lab) ────────────
    C_METH_BAR   = (0, 140, 255)
    C_METH_EMPTY = (30, 30, 30)
    if engine.entered_meth_lab:
        meth_ratio = p.meth / max(1, p.max_meth) if p.max_meth > 0 else 0
        meth_label = "Meth"
        meth_value = f"{p.meth}/{p.max_meth}"
        console.print(lx, row, f"{meth_label} {meth_value}", fg=C_LABEL, bg=BG)
        console.print(lx + len(meth_label) + 1, row, meth_value, fg=(0, 180, 255), bg=BG)
        row += 1
        filled_meth = round(bar_w * meth_ratio)
        empty_meth  = bar_w - filled_meth
        console.print(lx, row, "█" * filled_meth, fg=C_METH_BAR, bg=BG)
        console.print(lx + filled_meth, row, "░" * empty_meth, fg=C_METH_EMPTY, bg=BG)
        row += 1

    # ── Infection (visible when > 0) ─────────────────────────────────
    C_INF_BAR   = (120, 200, 50)
    C_INF_CRIT  = (200, 255, 50)
    C_INF_EMPTY = (30, 30, 30)
    if p.infection > 0:
        max_inf = getattr(p, 'max_infection', 100)
        inf_ratio = p.infection / max(1, max_inf)
        inf_color = C_INF_CRIT if p.infection >= max_inf else C_INF_BAR
        inf_label = "Infection"
        inf_value = f"{p.infection}/{max_inf}"
        console.print(lx, row, f"{inf_label} {inf_value}", fg=C_LABEL, bg=BG)
        console.print(lx + len(inf_label) + 1, row, inf_value, fg=inf_color, bg=BG)
        row += 1
        filled_inf = round(bar_w * inf_ratio)
        empty_inf  = bar_w - filled_inf
        console.print(lx, row, "█" * filled_inf, fg=inf_color, bg=BG)
        console.print(lx + filled_inf, row, "░" * empty_inf, fg=C_INF_EMPTY, bg=BG)
        row += 1

    # ── Spec Energy (visible when spec weapon equipped) ────────────────
    C_SPEC_BAR   = (220, 80, 80)
    C_SPEC_EMPTY = (30, 30, 30)
    if engine._has_spec_weapon():
        spec = engine.spec_energy
        spec_ratio = spec / 100.0
        spec_label = "Spec"
        spec_value = f"{int(spec)}/100"
        console.print(lx, row, f"{spec_label} {spec_value}", fg=C_LABEL, bg=BG)
        console.print(lx + len(spec_label) + 1, row, spec_value, fg=C_SPEC_BAR, bg=BG)
        row += 1
        filled_spec = round(bar_w * spec_ratio)
        empty_spec  = bar_w - filled_spec
        console.print(lx, row, "█" * filled_spec, fg=C_SPEC_BAR, bg=BG)
        console.print(lx + filled_spec, row, "░" * empty_spec, fg=C_SPEC_EMPTY, bg=BG)
        row += 1

    row += 1                      # 1 row gap before status section

    # ── Status effects ───────────────────────────────────────────────
    _draw_title_border(console, 1, pw - 2, row, "STATUS", BG,
                       fg_border=C_SECTION_DIV)
    row += 1

    # Reserve bottom rows: 2 for cash + 2 for tox/rad when in meth lab
    tox_rad_rows = 2 if engine.entered_meth_lab else 0
    cash_section_y = map_h - 3 - tox_rad_rows

    status_effects = engine.player.status_effects
    if not status_effects:
        console.print(lx, row, "(none)", fg=C_EMPTY, bg=BG)
        row += 1
    else:
        for effect in status_effects:
            if row >= cash_section_y - 1:
                break
            effect_id = getattr(effect, "id", "")
            # Strain effects use their strain color; other effects use themed colors
            if effect_id == "columbian_gold":
                color = get_strain_color("Columbian Gold")
                marker = "✦"
            elif effect_id == "agent_orange":
                color = get_strain_color("Agent Orange")
                marker = "✦"
            elif effect_id == "ignite":
                color = (255, 120, 40)
                marker = "-"
            elif effect_id == "chill":
                color = (100, 180, 255)
                marker = "-"
            elif effect_id == "shocked":
                color = (255, 220, 50)
                marker = "-"
            elif effect_id == "zoned_out":
                color = (100, 255, 200)
                marker = "+"
            else:
                is_buff = getattr(effect, "category", "debuff") == "buff"
                color   = C_BUFF if is_buff else C_DEBUFF
                marker  = "+" if is_buff else "-"

            # Line 1: marker + name, with stack count in parens if stackable
            max_w = pw - lx - 1  # usable columns before right border
            name = effect.display_name
            stack_count = effect.stack_count
            header = f"{marker} {name}"
            if stack_count is not None:
                header += f" ({stack_count})"
            console.print(lx, row, header[:max_w], fg=color, bg=BG)
            row += 1

            # Line 2: duration (dimmed)
            if row < cash_section_y - 1:
                dim = tuple(max(0, c - 70) for c in color)
                dur_line = f"\u25b8 {effect.display_duration}"
                console.print(lx, row, dur_line[:max_w], fg=dim, bg=BG)
                row += 1

    # ── Pending hangover warning ─────────────────────────────────────
    pending = getattr(engine, 'pending_hangover_stacks', 0)
    if pending > 0 and row < cash_section_y - 1:
        max_w = pw - lx - 1
        hangover_line = f"Hangover: -{pending} all stats next floor"
        console.print(lx, row, hangover_line[:max_w], fg=(120, 120, 120), bg=BG)
        row += 1

    # ── Gun ammo (shown only if a primary gun is equipped) ──────────
    primary_gun = engine._get_primary_gun()
    if primary_gun is not None:
        gun_defn = get_item_def(primary_gun.item_id)
        if gun_defn and gun_defn.get("subcategory") == "gun":
            gun_row = cash_section_y - 2
            if gun_row > row:
                mode_tag = "ACC" if engine.gun_firing_mode == "accurate" else engine.gun_firing_mode.upper()
                ammo_str = f"{primary_gun.current_ammo}/{primary_gun.mag_size}"
                gun_line = f"Ammo: {ammo_str} [{mode_tag}]"
                max_w = pw - lx - 1
                console.print(lx, gun_row, gun_line[:max_w], fg=(200, 180, 100), bg=BG)

    # ── Toxicity / Radiation (Meth Lab only) ──────────────────────────
    if engine.entered_meth_lab:
        C_TOX = (0, 255, 100)
        C_RAD = (100, 255, 50)
        tox_y = cash_section_y
        tox_str = f"Tox: {engine.player.toxicity}"
        rad_str = f"Rad: {engine.player.radiation}"
        console.print(lx, tox_y, tox_str, fg=C_TOX, bg=BG)
        console.print(lx, tox_y + 1, rad_str, fg=C_RAD, bg=BG)
        cash_section_y += 2

    # ── Cash ─────────────────────────────────────────────────────────
    _draw_title_border(console, 1, pw - 2, cash_section_y, "CASH", BG,
                       fg_border=C_SECTION_DIV)
    cash_str = f"${engine.cash}"
    console.print(pw - 2 - len(cash_str), cash_section_y + 1, cash_str, fg=(255, 215, 0), bg=BG)


def render_inventory_panel(console, engine):
    """Render the persistent right-side inventory panel (columns MAP_WIDTH to SCREEN_WIDTH)."""
    BG       = C_PANEL_BG
    C_LABEL  = (180, 180, 180)
    C_ITEM   = (255, 200, 0)
    C_EMPTY  = (80, 80, 80)

    px = MAP_OFFSET_X + MAP_WIDTH   # panel left edge (column 86)
    pw = PANEL_WIDTH                # 28 columns wide
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT  # height of the map area

    # Fill background
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        for x in range(pw):
            console.print(px + x, y, " ", bg=BG)

    # Left border (separator between map and panel)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(px, y, "│", fg=C_PANEL_BORDER, bg=BG)

    # Outer right border (screen edge)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(px + pw - 1, y, "║", fg=C_FRAME, bg=BG)

    # ── Title-in-border ─────────────────────────────────────────────
    _draw_title_border(console, px + 1, pw - 2, HEADER_HEIGHT, "INVENTORY", BG)

    # Category → display label (ALL CAPS for prominence)
    _CAT_LABEL = {
        "tool":       "TOOLS",
        "equipment":  "EQUIPMENT",
        "material":   "MATERIALS",
        "consumable": "CONSUMABLES",
    }
    C_HEADER         = (180, 180, 255)
    C_COMBINE_TARGET = (100, 255, 100)
    C_DIM            = (100, 100, 100)

    # Determine combine-select source
    combine_source = None
    if engine.menu_state == MenuState.COMBINE_SELECT and engine.selected_item_index is not None:
        combine_source = engine.player.inventory[engine.selected_item_index]

    inventory = engine.player.inventory
    start_y   = HEADER_HEIGHT + 2
    end_row   = start_y + (map_h - 3)

    if not inventory:
        console.print(px + 1, start_y, " (empty)", fg=C_EMPTY, bg=BG)
    else:
        cur_row      = start_y
        last_cat_hdr = None
        key_idx      = 0    # index into INVENTORY_KEYS
        overflow     = 0

        for inv_idx, item in enumerate(inventory):
            defn    = get_item_def(item.item_id) if item.item_id else None
            cat     = defn.get("category", "") if defn else ""
            cat_lbl = _CAT_LABEL.get(cat, cat.upper())

            # Category header: "─ LABEL ──────"
            if cat_lbl != last_cat_hdr:
                if cur_row >= end_row:
                    overflow = len(inventory) - inv_idx
                    break
                label_part = f"─ {cat_lbl} "
                fill = "─" * max(0, (pw - 1) - len(label_part))
                console.print(px + 1, cur_row, label_part + fill, fg=C_HEADER, bg=BG)
                cur_row     += 1
                last_cat_hdr = cat_lbl

            if cur_row >= end_row or key_idx >= len(INVENTORY_KEYS):
                overflow = len(inventory) - inv_idx
                break

            label = INVENTORY_KEYS[key_idx]
            console.print(px + 1, cur_row, f"{label})", fg=C_LABEL, bg=BG)

            # Name — gram-based for nugs/kush, x{n} suffix for others
            qty      = getattr(item, "quantity", 1)
            max_name = pw - 6
            item_prefix = getattr(item, "prefix", None)
            item_charges = getattr(item, "charges", None)
            item_max_charges = getattr(item, "max_charges", None)
            has_charges = (item_charges is not None
                          and item_max_charges is not None
                          and (item_prefix is not None
                               or get_item_def(item.item_id).get("tool_charges")
                               or get_item_def(item.item_id).get("staff_charges")))
            # Graffiti gun: show loaded spray charges
            if item.item_id == "graffiti_gun" and getattr(item, 'loaded_spray_id', None):
                has_charges = True
                item_charges = getattr(item, 'loaded_spray_charges', 0)
                item_max_charges = getattr(item, 'loaded_spray_max_charges', 0)

            full_name = build_inventory_display_name(
                item.item_id, getattr(item, "strain", None), qty,
                prefix=item_prefix,
                charges=item_charges if item_prefix is not None else None,
                max_charges=item_max_charges if item_prefix is not None else None,
            )

            # For prefixed foods: right-align charges, truncate name if needed
            charges_str = None
            if has_charges:
                charges_str = f"({item_charges}/{item_max_charges})"
                # Strip charges suffix only if build_inventory_display_name embedded it
                if item_prefix is not None and full_name.endswith(f"({item_charges}/{item_max_charges})"):
                    name_part = full_name[:-(len(charges_str) + 1)]
                else:
                    name_part = full_name
                name_space = max_name - len(charges_str) - 1     # 1-char gap
                if len(name_part) > name_space:
                    name = name_part[:name_space - 2] + ".."
                else:
                    name = name_part
            else:
                if len(full_name) > max_name:
                    name = full_name[:max_name - 2] + ".."
                else:
                    name = full_name

            # Item color: strain color if item has a strain, else definition color
            item_color = C_ITEM
            if defn:
                item_color = defn["color"]
            item_strain = getattr(item, "strain", None)
            if item_strain:
                item_color = get_strain_color(item_strain)
            # Graffiti gun: use loaded spray can's color
            if item.item_id == "graffiti_gun" and getattr(item, 'loaded_spray_id', None):
                loaded_defn = get_item_def(item.loaded_spray_id)
                if loaded_defn:
                    item_color = loaded_defn["color"]

            # Determine display color and background based on menu state
            C_SEL_BG = (60, 50, 80)
            is_item_selected = (
                engine.menu_state == MenuState.ITEM_MENU
                and inv_idx == engine.selected_item_index
            )
            is_combine_cursor = (
                engine.menu_state == MenuState.COMBINE_SELECT
                and inv_idx == getattr(engine, "combine_target_cursor", None)
            )
            row_bg = C_SEL_BG if (is_item_selected or is_combine_cursor) else BG

            if combine_source is not None:
                if inv_idx == engine.selected_item_index:
                    fg = C_DIM
                elif _is_combine_target(combine_source, item):
                    fg = item_color
                else:
                    fg = C_DIM
            else:
                fg = item_color

            row_highlighted = is_item_selected or is_combine_cursor
            if row_highlighted:
                # Fill entire row with selection background
                console.print(px + 1, cur_row, " " * (pw - 2), fg=fg, bg=row_bg)
                console.print(px + 1, cur_row, f"{label})", fg=(180, 180, 180), bg=row_bg)

            name_gradient = defn.get("name_gradient") if defn else None
            name_alternating = defn.get("name_alternating") if defn else None
            if name_alternating and fg == item_color:
                _print_alternating_text(console, px + 4, cur_row, name, name_alternating, row_bg)
            elif name_gradient and fg == item_color:
                _print_gradient_text(console, px + 4, cur_row, name, name_gradient, row_bg)
            else:
                console.print(px + 4, cur_row, name, fg=fg, bg=row_bg)
            if charges_str:
                charges_x = px + pw - 1 - len(charges_str)
                console.print(charges_x, cur_row, charges_str, fg=fg, bg=row_bg)

            cur_row += 1
            key_idx += 1

        if overflow > 0:
            console.print(px + 2, cur_row, f"  +{overflow} more", fg=C_EMPTY, bg=BG)

    # Divider above weight/count row
    footer_y = HEADER_HEIGHT + map_h - 2
    for x in range(1, pw - 1):
        console.print(px + x, footer_y, "─", fg=C_SECTION_DIV, bg=BG)

    count_text = f"Items: {len(inventory)}"
    console.print(px + 2, footer_y + 1, count_text, fg=C_LABEL, bg=BG)


def render_item_menu(console, engine):
    """Render the item action popup (small overlay near inventory panel)."""
    BG         = (30, 25, 40)
    C_ACTION   = (220, 220, 255)
    C_SELECTED = (255, 255, 100)
    BG_SEL     = (60, 50, 80)
    C_HINT     = (100, 100, 100)
    C_KEY      = (160, 160, 160)

    actions = engine.selected_item_actions
    cursor = engine.item_menu_cursor

    # Build keyhint per action — unique shortcuts + Spc for cursor selection
    key_hints = {}
    for act in actions:
        if act == "Examine":
            key_hints[act] = "e"
        elif act == "Drop":
            key_hints[act] = "d"
        elif act == "Destroy":
            key_hints[act] = "D"

    popup_w = 22
    popup_h = len(actions) + 2   # actions + hint line + top padding

    # Position left of the inventory panel, aligned with the item row
    popup_x = MAP_OFFSET_X + MAP_WIDTH - popup_w - 2
    popup_y = HEADER_HEIGHT + 4 + engine.selected_item_index

    # Clamp to screen bounds
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = max(HEADER_HEIGHT, HEADER_HEIGHT + map_h - popup_h)

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Actions with cursor highlight and keyhints
    for i, act in enumerate(actions):
        row_y = popup_y + 1 + i
        is_sel = (i == cursor)
        fg = C_SELECTED if is_sel else C_ACTION
        bg = BG_SEL if is_sel else BG
        prefix = "\x10 " if is_sel else "  "
        hint = key_hints.get(act, "")
        # Right-align keyhint
        label = f"{prefix}{act}"
        console.print(popup_x + 1, row_y, " " * (popup_w - 2), fg=fg, bg=bg)
        console.print(popup_x + 2, row_y, label, fg=fg, bg=bg)
        if hint:
            console.print(popup_x + popup_w - len(hint) - 2, row_y, hint, fg=C_KEY, bg=bg)

    # Hint
    console.print(popup_x + 2, popup_y + popup_h - 1, "Spc/Enter Sh+# Esc", fg=C_HINT, bg=BG)


def render_combine_select(console, engine):
    """Render the combine target prompt overlay."""
    BG     = (30, 25, 40)
    C_TEXT = (255, 200, 100)
    C_HINT = (100, 100, 100)

    item = engine.player.inventory[engine.selected_item_index]

    popup_w = 28
    popup_h = 5
    popup_x = MAP_OFFSET_X + MAP_WIDTH - popup_w - 2
    popup_y = HEADER_HEIGHT + 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    console.print(popup_x + 2, popup_y + 1, f"Use {item.name} on...", fg=C_TEXT, bg=BG)
    console.print(popup_x + 2, popup_y + 2, "Select target (a-z)", fg=C_TEXT, bg=BG)
    console.print(popup_x + 2, popup_y + 3, "[Esc] Cancel", fg=C_HINT, bg=BG)


def render_equipment_screen(console, engine):
    """Render the equipment screen overlay. Only occupied slots are shown; cursor indexes
    into the flat ordered list: weapon → neck → feet → rings (by finger)."""
    BG          = (22, 22, 32)
    C_TITLE     = (255, 255, 180)
    C_SLOT      = (180, 180, 255)
    C_ITEM      = (255, 200, 0)
    C_HINT      = (100, 100, 100)
    C_DIV       = (80, 80, 120)
    C_CURSOR    = (255, 255, 255)
    C_CURSOR_BG = (60, 60, 90)
    C_EMPTY     = (80, 80, 80)

    # Build flat ordered list of occupied slots: (label, item)
    occupied = []
    if engine.equipment["weapon"] is not None:
        occupied.append(("Weapon", engine.equipment["weapon"]))
    if engine.equipment.get("sidearm") is not None:
        label = "Sidearm"
        if engine.primary_gun == "sidearm":
            label = "Sidearm *"
        occupied.append((label, engine.equipment["sidearm"]))
    # Mark weapon as primary gun if applicable
    if engine.equipment["weapon"] is not None and engine.primary_gun == "weapon":
        wdefn = get_item_def(engine.equipment["weapon"].item_id)
        if wdefn and wdefn.get("subcategory") == "gun":
            occupied[0] = ("Weapon *", engine.equipment["weapon"])
    if engine.neck is not None:
        occupied.append(("Neck", engine.neck))
    if engine.feet is not None:
        occupied.append(("Feet", engine.feet))
    if engine.hat is not None:
        occupied.append(("Hat", engine.hat))
    for i, r in enumerate(engine.rings):
        if r is not None:
            occupied.append((RING_FINGER_NAMES[i], r))

    n = len(occupied)

    # Panel height: border + title + top_div + rows + bot_div + hint + border
    # rows = n if anything equipped, else 1 (empty message)
    panel_w = 46
    panel_h = 5 + max(n, 1) + 2  # +2 for top_div + bot_div
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "EQUIPMENT"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Top divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    cursor = engine.equipment_cursor
    label_width = max((len(label) for label, _ in occupied), default=0)

    def _draw_slot(row, cursor_idx, label, item):
        selected = cursor == cursor_idx
        bg = C_CURSOR_BG if selected else BG
        fg_label = C_CURSOR if selected else C_SLOT
        console.print(panel_x + 1, row, " " * (panel_w - 2), fg=BG, bg=bg)
        console.print(panel_x + 2, row, "►" if selected else " ", fg=C_CURSOR, bg=bg)
        padded_label = label.rjust(label_width)
        console.print(panel_x + 4, row, f"{padded_label}:", fg=fg_label, bg=bg)
        defn = get_item_def(item.item_id)
        bonus_parts = []
        if defn and defn.get("subcategory") == "gun":
            bonus_parts.append(f"{item.current_ammo}/{item.mag_size} ammo")
        elif defn and defn.get("staff_element"):
            ch = getattr(item, 'charges', 0)
            bonus_parts.append(f"{ch} charges")
        elif defn and defn.get("power_bonus"):
            bonus_parts.append(f"+{defn['power_bonus']}atk")
        if defn and defn.get("defense_bonus"):
            bonus_parts.append(f"+{defn['defense_bonus']}def")
        bonus = f" ({','.join(bonus_parts)})" if bonus_parts else ""
        col_start = panel_x + 4 + label_width + 2
        max_name = panel_w - 2 - (col_start - panel_x) - len(bonus)
        name_gradient = defn.get("name_gradient") if defn else None
        name_alternating = defn.get("name_alternating") if defn else None
        if name_alternating:
            _print_alternating_text(console, col_start, row, item.name[:max_name], name_alternating, bg)
            if bonus:
                console.print(col_start + len(item.name[:max_name]), row, bonus, fg=C_ITEM, bg=bg)
        elif name_gradient:
            _print_gradient_text(console, col_start, row, item.name[:max_name], name_gradient, bg)
            if bonus:
                console.print(col_start + len(item.name[:max_name]), row, bonus, fg=C_ITEM, bg=bg)
        else:
            console.print(col_start, row, f"{item.name[:max_name]}{bonus}", fg=C_ITEM, bg=bg)

    if n == 0:
        msg = "Nothing equipped"
        console.print(panel_x + (panel_w - len(msg)) // 2, panel_y + 3, msg, fg=C_EMPTY, bg=BG)
    else:
        for k, (label, item) in enumerate(occupied):
            _draw_slot(panel_y + 3 + k, k, label, item)

    # Bottom divider + hint
    bot_div_row = panel_y + 3 + max(n, 1)
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, bot_div_row, "─", fg=C_DIV, bg=BG)
    hint = "↑↓ Navigate  Enter Unequip  E/Esc Close"
    console.print(panel_x + (panel_w - len(hint)) // 2, bot_div_row + 1, hint, fg=C_HINT, bg=BG)


def render_midas_brew_menu(console, engine):
    """Render the Midas' Brew transmutation menu overlay."""
    from inventory_mgr import _midas_occupied_slots

    BG          = (22, 22, 32)
    C_TITLE     = (255, 255, 180)
    C_SLOT      = (180, 180, 255)
    C_ITEM      = (255, 200, 0)
    C_GOLD      = (255, 255, 100)
    C_HINT      = (100, 100, 100)
    C_DIV       = (80, 80, 120)
    C_CURSOR    = (255, 255, 255)
    C_CURSOR_BG = (60, 60, 90)
    C_CANCEL    = (180, 180, 180)

    occupied = _midas_occupied_slots(engine)
    n = len(occupied)

    # Slot labels
    _SLOT_LABELS = {
        "weapon": "Weapon", "sidearm": "Sidearm",
        "neck": "Neck", "feet": "Feet", "hat": "Hat",
    }

    def _label_for(slot_id):
        if isinstance(slot_id, tuple):
            return RING_FINGER_NAMES[slot_id[1]]
        return _SLOT_LABELS.get(slot_id, str(slot_id))

    labels = [_label_for(s) for s, _ in occupied]
    label_width = max((len(l) for l in labels), default=0)

    # Panel: border + title + divider + rows + cancel row + divider + hint + border
    panel_w = 46
    row_count = n + 1  # +1 for cancel row
    panel_h = 5 + row_count + 2
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "MIDAS' BREW"
    _print_gradient_text(console, panel_x + (panel_w - len(title)) // 2, panel_y + 1,
                         title, [(212, 175, 55), (255, 255, 100)], BG)

    # Top divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    cursor = engine.midas_cursor

    for k, (slot_id, item) in enumerate(occupied):
        row = panel_y + 3 + k
        selected = cursor == k
        bg = C_CURSOR_BG if selected else BG
        fg_label = C_CURSOR if selected else C_SLOT

        console.print(panel_x + 1, row, " " * (panel_w - 2), fg=BG, bg=bg)
        console.print(panel_x + 2, row, "►" if selected else " ", fg=C_CURSOR, bg=bg)

        label = labels[k]
        padded_label = label.rjust(label_width)
        console.print(panel_x + 4, row, f"{padded_label}:", fg=fg_label, bg=bg)

        defn = get_item_def(item.item_id)
        value = defn.get("value", 0) if defn else 0
        gold_str = f" -> ${value * 5}"
        col_start = panel_x + 4 + label_width + 2
        max_name = panel_w - 2 - (col_start - panel_x) - len(gold_str)

        name_gradient = defn.get("name_gradient") if defn else None
        name_alternating = defn.get("name_alternating") if defn else None
        if name_alternating:
            _print_alternating_text(console, col_start, row, item.name[:max_name], name_alternating, bg)
            console.print(col_start + len(item.name[:max_name]), row, gold_str, fg=C_GOLD, bg=bg)
        elif name_gradient:
            _print_gradient_text(console, col_start, row, item.name[:max_name], name_gradient, bg)
            console.print(col_start + len(item.name[:max_name]), row, gold_str, fg=C_GOLD, bg=bg)
        else:
            console.print(col_start, row, f"{item.name[:max_name]}{gold_str}", fg=C_ITEM, bg=bg)

    # Cancel row
    cancel_row = panel_y + 3 + n
    cancel_selected = cursor >= n
    bg = C_CURSOR_BG if cancel_selected else BG
    console.print(panel_x + 1, cancel_row, " " * (panel_w - 2), fg=BG, bg=bg)
    console.print(panel_x + 2, cancel_row, "►" if cancel_selected else " ", fg=C_CURSOR, bg=bg)
    console.print(panel_x + 4, cancel_row, "Cancel", fg=C_CURSOR if cancel_selected else C_CANCEL, bg=bg)

    # Bottom divider + hint
    bot_div_row = panel_y + 3 + row_count
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, bot_div_row, "─", fg=C_DIV, bg=BG)
    hint = "↑↓ Navigate  Enter Select  Esc Cancel"
    console.print(panel_x + (panel_w - len(hint)) // 2, bot_div_row + 1, hint, fg=C_HINT, bg=BG)


def render_char_sheet(console, engine):
    """Render the character sheet overlay (C key)."""
    BG        = (22, 22, 32)
    C_TITLE   = (255, 255, 180)
    C_HEAD    = (180, 180, 255)
    C_LABEL   = (180, 180, 180)
    C_VALUE   = (255, 220, 80)
    C_BUFF    = (100, 220, 255)
    C_DEBUFF  = (255, 100, 100)
    C_DESC    = (120, 120, 160)
    C_DERIVED = (100, 220, 120)
    C_DIV     = (80, 80, 120)
    C_HINT    = (100, 100, 100)

    ps = engine.player_stats
    panel_w = 50
    # Dynamic height based on content
    derived_count = 8  # base derived stats (5 original + speed + move cost + attack cost)
    if getattr(engine.player, "temp_hp", 0) > 0:
        derived_count += 1
    if ps.total_briskness != 0:
        derived_count += 1
    if ps.total_spell_damage > 0:
        derived_count += 1
    if engine.entered_meth_lab:
        derived_count += 5  # meth + toxicity + tox resist + radiation + rad resist
    # title(2) + div(1) + headers(1) + div(1) + stats(6) + div(1) + header(1)
    # + derived rows + div(1) + rep_header(1) + factions(2) + hint(2) + border(1)
    panel_h = 20 + derived_count + 4
    panel_x = (SCREEN_WIDTH  - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "CHARACTER SHEET"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    # Column headers
    console.print(panel_x + 2,  panel_y + 3, "Stat",   fg=C_HEAD, bg=BG)
    console.print(panel_x + 20, panel_y + 3, "Val",    fg=C_HEAD, bg=BG)
    console.print(panel_x + 26, panel_y + 3, "Effect", fg=C_HEAD, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 4, "─", fg=C_DIV, bg=BG)
    effective_values = {
        "constitution": ps.effective_constitution,
        "strength": ps.effective_strength,
        "book_smarts": ps.effective_book_smarts,
        "street_smarts": ps.effective_street_smarts,
        "tolerance": ps.effective_tolerance,
        "swagger": ps.effective_swagger,
    }
    for i, (label, value, desc, attr) in enumerate(ps.as_list()):
        row = panel_y + 5 + i
        current = effective_values[attr]
        base = ps._base[attr]
        val_color = C_DEBUFF if current < base else (C_BUFF if current > base else C_VALUE)
        val_str = f"{current} ({base})"
        console.print(panel_x + 2,  row, label,      fg=C_LABEL,  bg=BG)
        console.print(panel_x + 20, row, val_str, fg=val_color, bg=BG)
        console.print(panel_x + 26, row, desc[:panel_w - 28], fg=C_DESC, bg=BG)

    # Divider before derived stats
    div_row = panel_y + 11
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, div_row, "─", fg=C_DIV, bg=BG)

    # Derived stats header
    console.print(panel_x + 2, div_row + 1, "Derived Stats", fg=C_HEAD, bg=BG)

    # Derived values (all use effective stats for current calculations)
    p = engine.player
    unarmed_bonus = ps.effective_strength - 5
    unarmed_str = f"+{unarmed_bonus}" if unarmed_bonus >= 0 else str(unarmed_bonus)
    # Compute effective energy/tick matching engine._run_energy_loop logic
    base_speed = PLAYER_BASE_SPEED
    eff_speed = float(p.speed)
    for effect in p.status_effects:
        if hasattr(effect, "modify_energy_gain"):
            eff_speed = effect.modify_energy_gain(eff_speed, p)
    eff_speed = max(eff_speed, 10.0)
    eff_speed += ps.equipment_energy_per_tick
    if engine.skills.get("Meth-Head").level >= 3:
        eff_speed += (p.meth // 25) * 10
    eff_speed = int(eff_speed)

    speed_str = f"{eff_speed}"
    if eff_speed != base_speed:
        speed_str += f" ({base_speed})"

    move_base = ENERGY_THRESHOLD
    move_eff = max(0, engine.player_move_cost - engine.move_cost_reduction)
    move_str = f"{move_eff}"
    if move_eff != move_base:
        move_str += f" ({move_base})"

    atk_base = ENERGY_THRESHOLD
    atk_eff = engine.player_attack_cost
    atk_str = f"{atk_eff}"
    if atk_eff != atk_base:
        atk_str += f" ({atk_base})"

    derived = [
        ("Max HP",        f"{p.max_hp}",              f"Base 30 + CON*10"),
        ("Armor",         f"{p.armor}/{p.max_armor}", f"From equipment/effects, refills per floor"),
        ("Unarmed Bonus", f"{unarmed_str} dmg",       f"STR-5 (weapons scale differently)"),
        ("Crit Chance",   f"{ps.crit_chance:.0%}",    f"SS*3% per point, crits deal x2 dmg"),
        ("Dodge Chance",  f"{ps.dodge_chance}%",      f"Chance to dodge melee attacks (0–90%)"),
        ("Speed",         speed_str,                   f"Energy gained per tick",
         C_BUFF if eff_speed > base_speed else (C_DEBUFF if eff_speed < base_speed else None)),
        ("Move Cost",     move_str,                    f"Energy spent to move",
         C_BUFF if move_eff < move_base else (C_DEBUFF if move_eff > move_base else None)),
        ("Attack Cost",   atk_str,                     f"Energy spent to attack",
         C_BUFF if atk_eff < atk_base else (C_DEBUFF if atk_eff > atk_base else None)),
    ]
    if getattr(p, "temp_hp", 0) > 0:
        derived.append(("Temp HP", f"{p.temp_hp}", "Absorbs damage before armor and HP"))
    if ps.total_briskness != 0:
        sign = "+" if ps.total_briskness > 0 else ""
        derived.append(("Briskness", f"{sign}{ps.total_briskness}%", "Bonus to skill points from potential XP"))
    if ps.total_spell_damage > 0:
        derived.append(("Spell Damage", f"+{ps.total_spell_damage}", "Flat bonus to all spell damage"))
    if engine.entered_meth_lab:
        derived.append(("Meth", f"{engine.player.meth}/{engine.player.max_meth}", "Spent on strong abilities"))
        tox = engine.player.toxicity
        mult = 1.0 + (tox / 100) ** 0.6 if tox > 0 else 1.0
        derived.append(("Toxicity", f"{tox}  ({mult:.2f}x dmg)", "Meth Lab: damage taken multiplier"))
        tox_res = engine.player_stats.total_tox_resistance
        derived.append(("Tox Resist", f"{tox_res}%", "Reduces toxicity gained"))
        rad = engine.player.radiation
        rad_res = engine.player_stats.total_rad_resistance
        derived.append(("Radiation", f"{rad}", "Radiation level"))
        derived.append(("Rad Resist", f"{rad_res}%", "Reduces radiation gained"))
    for i, entry in enumerate(derived):
        label, val, note = entry[0], entry[1], entry[2]
        val_color = entry[3] if len(entry) > 3 and entry[3] else C_DERIVED
        row = div_row + 2 + i
        console.print(panel_x + 2,  row, label, fg=C_LABEL,  bg=BG)
        console.print(panel_x + 18, row, val,   fg=val_color, bg=BG)
        console.print(panel_x + 28, row, note[:panel_w - 30], fg=C_DESC, bg=BG)

    # Reputation section
    rep_div_row = div_row + 2 + len(derived)
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, rep_div_row, "─", fg=C_DIV, bg=BG)
    console.print(panel_x + 2, rep_div_row + 1, "Reputation", fg=C_HEAD, bg=BG)
    for i, faction_key in enumerate(("aldor", "scryer")):
        row = rep_div_row + 2 + i
        display_name = ps.FACTION_DISPLAY_NAMES[faction_key]
        title = ps.get_reputation_title(faction_key)
        color = ps.get_reputation_color(faction_key)
        rep_val = ps.reputation[faction_key]
        console.print(panel_x + 2, row, f"{display_name}:", fg=C_LABEL, bg=BG)
        console.print(panel_x + 12, row, title, fg=color, bg=BG)
        console.print(panel_x + 30, row, f"({rep_val})", fg=C_DESC, bg=BG)

    # Hint
    hint = "[C/Esc] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_log_menu(console, engine):
    """Full-screen log overlay with scrollable message history."""
    BG      = (18, 18, 28)
    C_TITLE = (255, 255, 180)
    C_DIV   = (80, 80, 120)
    C_HINT  = (100, 100, 130)
    C_SCROLL = (100, 100, 150)

    panel_w = SCREEN_WIDTH - 4
    panel_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - 2
    panel_x = 2
    panel_y = HEADER_HEIGHT + 1

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "MESSAGE LOG"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    # Visible rows for messages (inside border, below title + divider, above hint)
    visible_rows = panel_h - 5   # border(2) + title(1) + divider(1) + hint(1)
    content_x    = panel_x + 2
    content_w    = panel_w - 4
    first_row_y  = panel_y + 3

    all_msgs  = list(engine.messages)   # oldest → newest
    total     = len(all_msgs)
    scroll    = engine.log_scroll       # 0 = newest at bottom
    max_scroll = max(0, total - visible_rows)
    scroll    = min(scroll, max_scroll)

    # Which slice to show: newest at the bottom of the window
    end_idx   = total - scroll
    start_idx = max(0, end_idx - visible_rows)
    shown     = all_msgs[start_idx:end_idx]

    # Pad empty rows at the top so messages anchor to the bottom
    offset = visible_rows - len(shown)
    for i, msg in enumerate(shown):
        row = first_row_y + offset + i
        _render_msg(console, content_x, row, msg, content_w, BG)

    # Scroll position indicator on the right border
    if max_scroll > 0:
        bar_h    = max(1, visible_rows * visible_rows // max(total, 1))
        bar_pos  = round((max_scroll - scroll) / max_scroll * (visible_rows - bar_h))
        for bi in range(visible_rows):
            ch = "█" if bar_pos <= bi < bar_pos + bar_h else "░"
            console.print(panel_x + panel_w - 1, first_row_y + bi, ch, fg=C_SCROLL, bg=BG)

    # Hint
    if scroll > 0 and scroll < max_scroll:
        hint = "↑↓ Scroll  [Any] Close"
    elif scroll == 0 and max_scroll > 0:
        hint = "↑ Scroll up  [Any] Close"
    else:
        hint = "[Any] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_destroy_confirm(console, engine):
    """Render the destroy-item confirmation warning popup."""
    BG      = (22, 18, 28)
    C_TITLE = (190, 100, 100)
    C_TEXT  = (200, 200, 200)
    C_WARN  = (180, 150, 60)
    C_YES   = (210, 80,  80)
    C_NO    = (90,  190, 90)
    C_DIM   = (80,  80,  80)
    C_HINT  = (70,  70,  90)
    C_SEL_BG = (40, 28, 48)

    cursor = getattr(engine, "destroy_confirm_cursor", 0)  # 0=No, 1=Yes

    item = engine.player.inventory[engine.selected_item_index]
    qty  = getattr(item, "quantity", 1)
    name = build_inventory_display_name(
        item.item_id, getattr(item, "strain", None), qty,
        prefix=getattr(item, "prefix", None),
        charges=getattr(item, "charges", None),
        max_charges=getattr(item, "max_charges", None),
    )

    popup_w = 34
    popup_h = 11
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    title = "[ DESTROY ITEM ]"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    name_disp = name[:popup_w - 4]
    console.print(popup_x + (popup_w - len(name_disp)) // 2, popup_y + 3,
                  name_disp, fg=C_TEXT, bg=BG)

    warn = "This cannot be undone!"
    console.print(popup_x + (popup_w - len(warn)) // 2, popup_y + 5,
                  warn, fg=C_WARN, bg=BG)

    # Buttons — highlight selected with background tint and > cursor
    yes_label = "[Y] Destroy"
    no_label  = "[N] Cancel"
    yes_x = popup_x + 3
    no_x  = popup_x + popup_w - 3 - len(no_label)

    if cursor == 1:  # Yes selected
        console.print(yes_x - 2, popup_y + 7, ">", fg=C_YES, bg=C_SEL_BG)
        console.print(yes_x,     popup_y + 7, yes_label, fg=C_YES, bg=C_SEL_BG)
        console.print(no_x,      popup_y + 7, no_label,  fg=C_DIM, bg=BG)
    else:             # No selected (default)
        console.print(yes_x,     popup_y + 7, yes_label, fg=C_DIM, bg=BG)
        console.print(no_x - 2,  popup_y + 7, ">", fg=C_NO, bg=C_SEL_BG)
        console.print(no_x,      popup_y + 7, no_label,  fg=C_NO,  bg=C_SEL_BG)

    hint = "◄/►:move  Y/N  Enter:confirm"
    console.print(popup_x + (popup_w - len(hint)) // 2, popup_y + 9,
                  hint, fg=C_HINT, bg=BG)


def render_examine(console, engine):
    """Render the item examine overlay — centered transparent window with item details."""
    BG      = (20, 18, 30)
    C_TITLE = (255, 255, 180)
    C_HINT  = (100, 100, 100)

    item = engine.player.inventory[engine.selected_item_index]
    exam_lines = generate_examine_lines(item.item_id, engine)

    # Build title
    qty = getattr(item, "quantity", 1)
    title = build_inventory_display_name(
        item.item_id, getattr(item, "strain", None), qty,
        prefix=getattr(item, "prefix", None),
        charges=getattr(item, "charges", None),
        max_charges=getattr(item, "max_charges", None),
    )

    # Calculate width: widest line or title, capped at 50
    max_line_w = len(title)
    for line_parts in exam_lines:
        line_len = sum(len(t) for t, *_ in line_parts)
        if line_len > max_line_w:
            max_line_w = line_len
    popup_w = min(50, max_line_w + 6)

    # Height: title + divider + lines + padding (no hint row)
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_h = min(len(exam_lines) + 4, map_h - 2)

    # Center on map area
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (map_h - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Title
    title_disp = title[:popup_w - 4]
    console.print(popup_x + (popup_w - len(title_disp)) // 2, popup_y + 1,
                  title_disp, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, popup_w - 1):
        console.print(popup_x + px, popup_y + 2, "─", fg=(80, 80, 120), bg=BG)

    # Content lines — truncate to fit within popup
    content_w = popup_w - 4  # 2px padding each side
    max_content_lines = popup_h - 4  # title + divider + padding
    for i, line_parts in enumerate(exam_lines[:max_content_lines]):
        cx = popup_x + 2
        cy = popup_y + 3 + i
        chars_left = content_w
        for part in line_parts:
            if isinstance(part, tuple) and len(part) == 2:
                text, color = part
            else:
                text = str(part)
                color = (200, 200, 200)
            if chars_left <= 0:
                break
            text = text[:chars_left]
            console.print(cx, cy, text, fg=color, bg=BG)
            cx += len(text)
            chars_left -= len(text)



def render_ring_replace_menu(console, engine):
    """Render the ring replacement menu to select which ring to replace."""
    BG       = (20, 20, 30)
    C_TITLE  = (255, 200, 100)
    C_TEXT   = (220, 220, 220)
    C_CURSOR = (255, 255, 100)
    C_HINT   = (150, 150, 150)

    # Get the pending ring item for display
    if engine.pending_ring_item_index is None:
        return
    pending_ring = engine.player.inventory[engine.pending_ring_item_index]

    popup_w = 40
    popup_h = 5 + RING_SLOTS + 2  # title + spacing + ring rows + padding
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Title
    title = "Which ring to replace?"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    # Ring being equipped
    ring_name = pending_ring.name[:popup_w - 4]
    console.print(popup_x + 2, popup_y + 3, f"Equipping: {ring_name}", fg=C_TEXT, bg=BG)

    # Ring slots
    start_y = popup_y + 5
    for slot in range(RING_SLOTS):
        ring = engine.rings[slot]
        slot_text = f"[{slot}] "

        if ring is None:
            slot_display = f"{slot_text}(empty)"
            slot_color = C_HINT
        else:
            ring_display = ring.name[:popup_w - len(slot_text) - 4]
            slot_display = f"{slot_text}{ring_display}"
            slot_color = ring.color

        y = start_y + slot

        # Highlight cursor
        if slot == engine.ring_replace_cursor:
            console.print(popup_x + 1, y, ">", fg=C_CURSOR, bg=BG)
            console.print(popup_x + 2, y, slot_display, fg=C_CURSOR, bg=BG)
        else:
            console.print(popup_x + 2, y, slot_display, fg=slot_color, bg=BG)


def render_bestiary_menu(console, engine):
    """Render the bestiary overlay: list of all monsters with their char and name."""
    BG      = (18, 18, 28)
    C_TITLE = (255, 255, 180)
    C_DIV   = (80, 80, 120)
    C_HINT  = (100, 100, 130)

    monsters = list(MONSTER_REGISTRY.values())

    panel_w = 32
    panel_h = len(monsters) + 5   # border(2) + title(1) + divider(1) + entries + hint(1)
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    title = "BESTIARY"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    for i, tmpl in enumerate(monsters):
        row = panel_y + 3 + i
        console.print(panel_x + 2, row, tmpl.char, fg=(220, 50, 50), bg=BG)
        console.print(panel_x + 4, row, tmpl.name[:panel_w - 6], fg=(255, 255, 255), bg=BG)

    hint = "[Any] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_targeting_mode(console, engine):
    """Render targeting cursor overlay and info popup on the map."""
    cx, cy = engine.targeting_cursor
    map_cx  = cx + MAP_OFFSET_X
    map_cy  = cy + HEADER_HEIGHT

    is_visible = engine.dungeon.visible[cy, cx]
    in_range   = engine._is_targeting_in_range(cx, cy)
    if not is_visible:
        cursor_bg = (160, 30, 30)    # red: out of sight
    elif not in_range:
        cursor_bg = (160, 30, 30)    # red: out of range
    else:
        cursor_bg = (50, 50, 60)     # subtle highlight: valid target position

    # Highlight invalid (out-of-range / out-of-sight) tiles with light red
    C_INVALID_BG = (80, 25, 25)
    dw, dh = engine.dungeon.width, engine.dungeon.height
    for ty in range(dh):
        for tx in range(dw):
            if not engine.dungeon.visible[ty, tx]:
                continue  # not visible — already dark, skip
            if engine._is_targeting_in_range(tx, ty):
                continue  # valid target tile
            sx = tx + MAP_OFFSET_X
            sy = ty + HEADER_HEIGHT
            if 0 <= sx < SCREEN_WIDTH and 0 <= sy < SCREEN_HEIGHT:
                tile = console.rgb[sx, sy]
                ch = chr(tile['ch']) if tile['ch'] else ' '
                ch_color = tuple(tile['fg'][:3]) if tile['fg'] is not None else (255, 255, 255)
                console.print(sx, sy, ch, fg=ch_color, bg=C_INVALID_BG)

    # Highlight spell affected tiles (if applicable)
    stype = engine.targeting_spell.get("type", "") if engine.targeting_spell else ""
    if engine.targeting_spell is not None:
        affected_tiles = engine.get_targeting_affected_tiles(cx, cy)
        for tx, ty in affected_tiles:
            map_tx = tx + MAP_OFFSET_X
            map_ty = ty + HEADER_HEIGHT
            if 0 <= map_tx < SCREEN_WIDTH and 0 <= map_ty < SCREEN_HEIGHT:
                # Get the character and color already at this tile
                tile = console.rgb[map_tx, map_ty]
                ch = chr(tile['ch']) if tile['ch'] else ' '
                ch_color = tuple(tile['fg'][:3]) if tile['fg'] is not None else (255, 255, 255)
                # Overlay with semi-transparent highlight
                if stype == "graffiti_gun_fire":
                    _GUN_SPRAY_BG = {"red": (120, 30, 30), "blue": (30, 50, 120), "green": (30, 120, 30), "orange": (120, 80, 15), "silver": (80, 80, 90)}
                    gun_idx = engine.targeting_spell.get("item_index", 0)
                    _s_type = ""
                    if 0 <= gun_idx < len(engine.player.inventory):
                        _s_id = getattr(engine.player.inventory[gun_idx], 'loaded_spray_id', '')
                        _s_defn = get_item_def(_s_id) if _s_id else None
                        _s_type = (_s_defn["use_effect"]["spray_type"]) if _s_defn else ""
                    highlight_bg = _GUN_SPRAY_BG.get(_s_type, (100, 150, 80)) if engine.dungeon.visible[ty, tx] else (60, 80, 40)
                else:
                    highlight_bg = (100, 150, 80) if engine.dungeon.visible[ty, tx] else (60, 80, 40)
                console.print(map_tx, map_ty, ch, fg=ch_color, bg=highlight_bg)

    # Draw cursor over whatever is already rendered at that tile
    console.print(map_cx, map_cy, "X", fg=(255, 255, 255), bg=cursor_bg)

    # Find monster under cursor for info display
    target_monster = None
    if is_visible:
        for e in engine.dungeon.get_entities_at(cx, cy):
            if e.entity_type == "monster" and e.alive:
                target_monster = e
                break

    BG      = (20, 15, 30)
    C_BORDER= (160, 160, 210)
    C_INFO  = (220, 235, 255)
    C_HINT  = (140, 140, 170)
    C_ENEMY = (255, 140, 140)
    C_EMPTY = (160, 160, 160)

    if engine.targeting_spell is not None:
        stype = engine.targeting_spell.get("type", "spell")
        if stype == "graffiti_gun_fire":
            gun_idx = engine.targeting_spell.get("item_index", 0)
            if 0 <= gun_idx < len(engine.player.inventory):
                gun_item = engine.player.inventory[gun_idx]
                s_id = getattr(gun_item, 'loaded_spray_id', '')
                s_charges = getattr(gun_item, 'loaded_spray_charges', 0)
                s_max = getattr(gun_item, 'loaded_spray_max_charges', 0)
                s_defn = get_item_def(s_id) if s_id else None
                s_name = s_defn["name"] if s_defn else "Empty"
                line0 = f"Graffiti Gun: {s_name} ({s_charges}/{s_max})"
            else:
                line0 = "Graffiti Gun"
        else:
            spell_name = stype.replace("_", " ").title()
            count = engine.targeting_spell.get("count") or engine.targeting_spell.get("total_hits")
            line0 = f"Cast: {spell_name}" + (f" (x{count} left)" if count and count > 1 else "")
        if not in_range:
            line1 = "Out of range!"
            line1_color = (255, 160, 30)
        elif target_monster:
            line1 = f"Target: {target_monster.name} ({target_monster.hp}/{target_monster.max_hp} HP)"
            line1_color = C_ENEMY
        elif not is_visible:
            line1 = "Out of sight"
            line1_color = (255, 100, 100)
        else:
            line1 = "No enemy here"
            line1_color = C_EMPTY
        line2 = "[Enter] Fire   [Esc] Cancel" if stype == "graffiti_gun_fire" else "[Enter] Cast   [Esc] Cancel"
    else:
        item = engine.player.inventory[engine.targeting_item_index]
        line0 = f"Throw: {item.name}"
        if target_monster:
            line1 = f"Target: {target_monster.name} ({target_monster.hp}/{target_monster.max_hp} HP)"
            line1_color = C_ENEMY
        elif not is_visible:
            line1 = "Out of sight — cannot throw here"
            line1_color = (255, 100, 100)
        else:
            line1 = "Target: Empty (joint will be wasted)"
            line1_color = C_EMPTY
        line2 = "[Enter] Throw   [Esc] Cancel"

    popup_w = max(len(line0), len(line1), len(line2)) + 4
    popup_h = 5  # border(2) + 3 content lines

    # Place popup 3 tiles away from cursor, clamped to map + panel bounds
    map_h   = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_cx - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_cy + 3
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = map_cy - popup_h - 2

    # Draw semi-transparent popup via a temporary console blitted with bg_alpha
    popup_console = tcod.console.Console(popup_w, popup_h)
    for py in range(popup_h):
        for px in range(popup_w):
            popup_console.print(px, py, " ", bg=BG)
    for px in range(popup_w):
        popup_console.print(px, 0,           "─", fg=C_BORDER, bg=BG)
        popup_console.print(px, popup_h - 1, "─", fg=C_BORDER, bg=BG)
    for py in range(popup_h):
        popup_console.print(0,           py, "│", fg=C_BORDER, bg=BG)
        popup_console.print(popup_w - 1, py, "│", fg=C_BORDER, bg=BG)
    popup_console.print(0,           0,           "┌", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, 0,           "┐", fg=C_BORDER, bg=BG)
    popup_console.print(0,           popup_h - 1, "└", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, popup_h - 1, "┘", fg=C_BORDER, bg=BG)
    popup_console.print(2, 1, line0, fg=C_INFO,      bg=BG)
    popup_console.print(2, 2, line1, fg=line1_color, bg=BG)
    popup_console.print(2, 3, line2, fg=C_HINT,      bg=BG)
    popup_console.blit(console, popup_x, popup_y, fg_alpha=1.0, bg_alpha=0.72)


def _render_staff_targeting(console, engine, cx, cy, map_cx, map_cy):
    """Render staff bolt targeting cursor and info popup."""
    _STAFF_RANGE = 4
    _ELEMENT_COLORS = {
        "fire": (255, 100, 30),
        "lightning": (255, 255, 80),
        "cold": (100, 200, 255),
    }

    info = engine.staff_firing
    element = info["element"]
    elem_color = _ELEMENT_COLORS.get(element, (200, 200, 255))
    staff_item = get_item_def(info["item_id"])
    staff_name = staff_item["name"] if staff_item else "Staff"

    is_visible = engine.dungeon.visible[cy, cx]
    dist = max(abs(cx - engine.player.x), abs(cy - engine.player.y))
    in_range = 0 < dist <= _STAFF_RANGE

    # Tint out-of-range tiles
    C_INVALID_BG = (80, 25, 25)
    dw, dh = engine.dungeon.width, engine.dungeon.height
    for ty_ in range(dh):
        for tx_ in range(dw):
            if not engine.dungeon.visible[ty_, tx_]:
                continue
            d = max(abs(tx_ - engine.player.x), abs(ty_ - engine.player.y))
            if 0 < d <= _STAFF_RANGE:
                continue
            sx_ = tx_ + MAP_OFFSET_X
            sy_ = ty_ + HEADER_HEIGHT
            if 0 <= sx_ < SCREEN_WIDTH and 0 <= sy_ < SCREEN_HEIGHT:
                tile_ = console.rgb[sx_, sy_]
                ch_ = chr(tile_['ch']) if tile_['ch'] else ' '
                ch_color_ = tuple(tile_['fg'][:3]) if tile_['fg'] is not None else (255, 255, 255)
                console.print(sx_, sy_, ch_, fg=ch_color_, bg=C_INVALID_BG)

    # Cursor color
    if not is_visible:
        cursor_bg = (160, 30, 30)
    elif not in_range:
        cursor_bg = (200, 120, 30)
    else:
        cursor_bg = elem_color

    console.print(map_cx, map_cy, "X", fg=(255, 255, 255), bg=cursor_bg)

    # Find target under cursor
    target_monster = None
    if is_visible:
        for e in engine.dungeon.get_entities_at(cx, cy):
            if e.entity_type == "monster" and e.alive:
                target_monster = e
                break

    BG       = (20, 15, 30)
    C_BORDER = (160, 160, 210)
    C_INFO   = (220, 235, 255)
    C_HINT   = (140, 140, 170)
    C_ENEMY  = (255, 140, 140)
    C_EMPTY  = (160, 160, 160)

    bksmt = engine.player_stats.effective_book_smarts
    damage = 5 + bksmt // 3

    line0 = f"{staff_name} ({element.capitalize()} Bolt)"
    if not is_visible:
        line1 = "Out of sight"
        line1_color = (255, 100, 100)
    elif not in_range:
        line1 = "Out of range" if dist > _STAFF_RANGE else "No target here"
        line1_color = (255, 160, 30)
    elif target_monster:
        line1 = f"Target: {target_monster.name} ({target_monster.hp}/{target_monster.max_hp} HP)"
        line1_color = C_ENEMY
    else:
        line1 = "No enemy here"
        line1_color = C_EMPTY
    weapon = engine.equipment.get("weapon")
    staff_charges = getattr(weapon, 'charges', 0) if weapon else 0
    line2 = f"Dmg: {damage}  Range: {_STAFF_RANGE}  Charges: {staff_charges}"
    line3 = "[Enter] Fire  [Esc] Cancel"

    popup_w = max(len(line0), len(line1), len(line2), len(line3)) + 4
    popup_h = 6

    map_h   = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_cx - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_cy + 3
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = map_cy - popup_h - 2

    popup_console = tcod.console.Console(popup_w, popup_h)
    for py_ in range(popup_h):
        for px_ in range(popup_w):
            popup_console.print(px_, py_, " ", bg=BG)
    for px_ in range(popup_w):
        popup_console.print(px_, 0,           "─", fg=C_BORDER, bg=BG)
        popup_console.print(px_, popup_h - 1, "─", fg=C_BORDER, bg=BG)
    for py_ in range(popup_h):
        popup_console.print(0,           py_, "│", fg=C_BORDER, bg=BG)
        popup_console.print(popup_w - 1, py_, "│", fg=C_BORDER, bg=BG)
    popup_console.print(0,           0,           "┌", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, 0,           "┐", fg=C_BORDER, bg=BG)
    popup_console.print(0,           popup_h - 1, "└", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, popup_h - 1, "┘", fg=C_BORDER, bg=BG)
    popup_console.print(2, 1, line0, fg=elem_color, bg=BG)
    popup_console.print(2, 2, line1, fg=line1_color, bg=BG)
    popup_console.print(2, 3, line2, fg=C_INFO,      bg=BG)
    popup_console.print(2, 4, line3, fg=C_HINT,      bg=BG)
    popup_console.blit(console, popup_x, popup_y, fg_alpha=1.0, bg_alpha=0.72)


def render_gun_targeting_mode(console, engine):
    """Render gun targeting cursor overlay and info popup on the map."""
    cx, cy = engine.gun_targeting_cursor
    map_cx = cx + MAP_OFFSET_X
    map_cy = cy + HEADER_HEIGHT

    # Staff targeting mode — simplified UI
    if getattr(engine, 'staff_firing', None):
        _render_staff_targeting(console, engine, cx, cy, map_cx, map_cy)
        return

    gun = engine._get_primary_gun()
    if gun is None:
        return
    gun_defn = get_item_def(gun.item_id)
    if gun_defn is None:
        return
    gun_range = gun_defn.get("gun_range", 4)
    mode = engine.gun_firing_mode
    modes = gun_defn.get("firing_modes", {})
    mode_data = modes.get(mode, {"hit": 75, "energy": 50})

    is_visible = engine.dungeon.visible[cy, cx]
    dist = max(abs(cx - engine.player.x), abs(cy - engine.player.y))
    in_range = dist <= gun_range and dist > 0

    if not is_visible:
        cursor_bg = (160, 30, 30)      # red: out of sight
    elif not in_range:
        cursor_bg = (200, 120, 30)     # orange: out of range or self
    else:
        cursor_bg = (30, 60, 180)      # blue: valid target

    # AOE highlighting (cone, line, or gun ability override)
    ga = engine.gun_ability_active  # gun ability spec, if any
    if ga is not None:
        aoe_type = ga.get("aoe_type", "line")
        ability_range = ga.get("range", 4)
        # Override range check for gun abilities
        in_range = dist <= ability_range and dist > 0
        if not is_visible:
            cursor_bg = (160, 30, 30)
        elif not in_range:
            cursor_bg = (200, 120, 30)
        else:
            cursor_bg = (30, 60, 180)
    else:
        aoe_type = gun_defn.get("aoe_type", "target")

    # Highlight invalid (out-of-range / out-of-sight / self) tiles with light red
    effective_range = ga.get("range", 4) if ga is not None else gun_range
    C_INVALID_BG = (80, 25, 25)
    dw, dh = engine.dungeon.width, engine.dungeon.height
    for ty_ in range(dh):
        for tx_ in range(dw):
            if not engine.dungeon.visible[ty_, tx_]:
                continue
            d = max(abs(tx_ - engine.player.x), abs(ty_ - engine.player.y))
            if 0 < d <= effective_range:
                continue  # valid target tile
            sx_ = tx_ + MAP_OFFSET_X
            sy_ = ty_ + HEADER_HEIGHT
            if 0 <= sx_ < SCREEN_WIDTH and 0 <= sy_ < SCREEN_HEIGHT:
                tile_ = console.rgb[sx_, sy_]
                ch_ = chr(tile_['ch']) if tile_['ch'] else ' '
                ch_color_ = tuple(tile_['fg'][:3]) if tile_['fg'] is not None else (255, 255, 255)
                console.print(sx_, sy_, ch_, fg=ch_color_, bg=C_INVALID_BG)

    aoe_targets = 0
    if is_visible and in_range:
        if aoe_type == "cone" and ga is None:
            aoe_tiles = engine._get_gun_cone_tiles(cx, cy)
        elif aoe_type == "circle" and ga is None:
            aoe_radius = gun_defn.get("aoe_radius", 2)
            aoe_tiles = engine._get_gun_circle_tiles(cx, cy, aoe_radius)
        elif aoe_type == "line":
            ability_range_val = ga.get("range", 4) if ga else gun_range
            aoe_tiles = engine._get_gun_line_tiles(cx, cy, ability_range_val)
        else:
            aoe_tiles = []

        if aoe_tiles:
            C_AOE_BG = (80, 50, 20)  # dim orange tint for AOE area
            for (ctx, cty) in aoe_tiles:
                scx = ctx + MAP_OFFSET_X
                scy = cty + HEADER_HEIGHT
                if 0 <= scx < SCREEN_WIDTH and 0 <= scy < SCREEN_HEIGHT:
                    if engine.dungeon.visible[cty, ctx]:
                        console.print(scx, scy, " ", bg=C_AOE_BG)
                        for e in engine.dungeon.get_entities_at(ctx, cty):
                            if e.entity_type == "monster" and e.alive:
                                aoe_targets += 1
                                console.print(scx, scy, e.char, fg=e.color, bg=C_AOE_BG)

    # Draw cursor
    console.print(map_cx, map_cy, "X", fg=(255, 255, 255), bg=cursor_bg)

    # Find monster under cursor
    target_monster = None
    if is_visible:
        for e in engine.dungeon.get_entities_at(cx, cy):
            if e.entity_type == "monster" and e.alive:
                target_monster = e
                break

    BG       = (20, 15, 30)
    C_BORDER = (160, 160, 210)
    C_INFO   = (220, 235, 255)
    C_HINT   = (140, 140, 170)
    C_ENEMY  = (255, 140, 140)
    C_EMPTY  = (160, 160, 160)

    # Build popup text — gun ability mode vs normal gun fire
    if ga is not None:
        ability_name = ga.get("name", "Gun Ability")
        num_shots = ga.get("num_shots", 2)
        ga_dmg = ga.get("damage", (1, 1))
        ga_acc = ga.get("accuracy", 50)
        ga_energy = ga.get("energy", 80)
        line0 = f"{ability_name} ({gun.name})"
        if not is_visible:
            line1 = "Out of sight"
            line1_color = (255, 100, 100)
        elif not in_range:
            line1 = "Out of range"
            line1_color = (255, 160, 30)
        else:
            aoe_label = ga.get("aoe_type", "line").capitalize()
            line1 = f"{aoe_label}: {aoe_targets} target{'s' if aoe_targets != 1 else ''} | {num_shots} rounds"
            line1_color = C_ENEMY if aoe_targets > 0 else C_EMPTY
        line2 = f"Dmg: {ga_dmg[0]}-{ga_dmg[1]}  Hit: {ga_acc}%  Energy: {ga_energy}  Ammo: {gun.current_ammo}/{gun.mag_size}"
        line3 = "[Enter] Fire  [Esc] Cancel"
    else:
        line0 = f"Fire: {gun.name} ({mode.upper()})"
        if aoe_type == "cone":
            ammo_per_shot = gun_defn.get("ammo_per_shot", (1, 1))
            if isinstance(ammo_per_shot, (list, tuple)):
                ammo_str = f"{ammo_per_shot[0]}-{ammo_per_shot[1]}"
            else:
                ammo_str = str(ammo_per_shot)
            if not is_visible:
                line1 = "Out of sight"
                line1_color = (255, 100, 100)
            elif not in_range:
                line1 = "Out of range"
                line1_color = (255, 160, 30)
            else:
                line1 = f"Cone: {aoe_targets} target{'s' if aoe_targets != 1 else ''} | {ammo_str} rounds/burst"
                line1_color = C_ENEMY if aoe_targets > 0 else C_EMPTY
        elif aoe_type == "circle":
            aoe_radius = gun_defn.get("aoe_radius", 2)
            if not is_visible:
                line1 = "Out of sight"
                line1_color = (255, 100, 100)
            elif not in_range:
                line1 = "Out of range"
                line1_color = (255, 160, 30)
            else:
                line1 = f"Blast r{aoe_radius}: {aoe_targets} target{'s' if aoe_targets != 1 else ''}"
                line1_color = C_ENEMY if aoe_targets > 0 else C_EMPTY
        elif not is_visible:
            line1 = "Out of sight"
            line1_color = (255, 100, 100)
        elif not in_range:
            line1 = "Out of range" if dist > gun_range else "No target here"
            line1_color = (255, 160, 30)
        elif target_monster:
            line1 = f"Target: {target_monster.name} ({target_monster.hp}/{target_monster.max_hp} HP)"
            line1_color = C_ENEMY
        else:
            line1 = "No enemy here"
            line1_color = C_EMPTY
        line2 = f"Hit: {mode_data['hit']}%  Energy: {mode_data['energy']}  Ammo: {gun.current_ammo}/{gun.mag_size}"
        line3 = "[Enter] Fire  [TAB] Mode  [Esc] Cancel"

    popup_w = max(len(line0), len(line1), len(line2), len(line3)) + 4
    popup_h = 6  # border(2) + 4 content lines

    map_h   = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_cx - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_cy + 3
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = map_cy - popup_h - 2

    popup_console = tcod.console.Console(popup_w, popup_h)
    for py_ in range(popup_h):
        for px_ in range(popup_w):
            popup_console.print(px_, py_, " ", bg=BG)
    for px_ in range(popup_w):
        popup_console.print(px_, 0,           "─", fg=C_BORDER, bg=BG)
        popup_console.print(px_, popup_h - 1, "─", fg=C_BORDER, bg=BG)
    for py_ in range(popup_h):
        popup_console.print(0,           py_, "│", fg=C_BORDER, bg=BG)
        popup_console.print(popup_w - 1, py_, "│", fg=C_BORDER, bg=BG)
    popup_console.print(0,           0,           "┌", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, 0,           "┐", fg=C_BORDER, bg=BG)
    popup_console.print(0,           popup_h - 1, "└", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, popup_h - 1, "┘", fg=C_BORDER, bg=BG)
    popup_console.print(2, 1, line0, fg=C_INFO,      bg=BG)
    popup_console.print(2, 2, line1, fg=line1_color,  bg=BG)
    popup_console.print(2, 3, line2, fg=C_INFO,       bg=BG)
    popup_console.print(2, 4, line3, fg=C_HINT,       bg=BG)
    popup_console.blit(console, popup_x, popup_y, fg_alpha=1.0, bg_alpha=0.72)


def render_entity_targeting_mode(console, engine):
    """Highlight all valid targets; dim yellow for all, red for selected; popup near selected."""
    target_list = engine.entity_target_list
    sel_idx = engine.entity_target_index

    C_ALL_BG = (100, 80, 10)   # dim yellow — all valid targets
    C_SEL_BG = (180, 40, 40)   # red — currently selected target

    for i, entity in enumerate(target_list):
        map_ex = entity.x + MAP_OFFSET_X
        map_ey = entity.y + HEADER_HEIGHT
        bg = C_SEL_BG if i == sel_idx else C_ALL_BG
        console.print(map_ex, map_ey, entity.char, fg=entity.color, bg=bg)

    if not target_list:
        return

    selected = target_list[sel_idx]
    n = len(target_list)

    BG       = (20, 15, 30)
    C_BORDER = (160, 160, 210)
    C_ENEMY  = (255, 140, 140)
    C_INFO   = (220, 235, 255)
    C_HINT   = (140, 140, 170)

    # Determine action label: ability name if targeting for an ability, else "Attack"
    action_label = "Attack"
    if engine.targeting_ability_index is not None:
        from abilities import ABILITY_REGISTRY
        inst_list = engine.player_abilities
        if 0 <= engine.targeting_ability_index < len(inst_list):
            _defn = ABILITY_REGISTRY.get(inst_list[engine.targeting_ability_index].ability_id)
            if _defn:
                action_label = _defn.name

    line0 = f"Target: {selected.name} ({selected.hp}/{selected.max_hp} HP)"
    line1 = f"[</> ] Cycle ({sel_idx + 1}/{n})"
    line2 = f"[Enter] {action_label}   [Esc] Cancel"

    popup_w = max(len(line0), len(line1), len(line2)) + 4
    popup_h = 5

    map_sx = selected.x + MAP_OFFSET_X
    map_sy = selected.y + HEADER_HEIGHT
    map_h  = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_sx - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_sy + 3
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = map_sy - popup_h - 2

    popup_console = tcod.console.Console(popup_w, popup_h)
    for py in range(popup_h):
        for px in range(popup_w):
            popup_console.print(px, py, " ", bg=BG)
    for px in range(popup_w):
        popup_console.print(px, 0,           "─", fg=C_BORDER, bg=BG)
        popup_console.print(px, popup_h - 1, "─", fg=C_BORDER, bg=BG)
    for py in range(popup_h):
        popup_console.print(0,           py, "│", fg=C_BORDER, bg=BG)
        popup_console.print(popup_w - 1, py, "│", fg=C_BORDER, bg=BG)
    popup_console.print(0,           0,           "┌", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, 0,           "┐", fg=C_BORDER, bg=BG)
    popup_console.print(0,           popup_h - 1, "└", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, popup_h - 1, "┘", fg=C_BORDER, bg=BG)
    popup_console.print(2, 1, line0, fg=C_ENEMY, bg=BG)
    popup_console.print(2, 2, line1, fg=C_INFO,  bg=BG)
    popup_console.print(2, 3, line2, fg=C_HINT,  bg=BG)
    popup_console.blit(console, popup_x, popup_y, fg_alpha=1.0, bg_alpha=0.72)


def render_adjacent_tile_targeting_mode(console, engine):
    """Highlight non-wall adjacent tiles and show a direction-prompt popup."""
    px, py = engine.player.x, engine.player.y
    pending = getattr(engine, 'spray_paint_pending', None)

    C_VALID_BG = (50, 50, 60)       # subtle grey-blue — matches cursor targeting convention
    C_INVALID_BG = (80, 25, 25)      # dim red — wall/blocked tile

    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dx == 0 and dy == 0:
                continue
            tx, ty = px + dx, py + dy
            if 0 <= tx < engine.dungeon.width and 0 <= ty < engine.dungeon.height:
                if not engine.dungeon.is_terrain_blocked(tx, ty):
                    console.print(tx + MAP_OFFSET_X, ty + HEADER_HEIGHT, " ", bg=C_VALID_BG)
                else:
                    console.print(tx + MAP_OFFSET_X, ty + HEADER_HEIGHT, " ", bg=C_INVALID_BG)

    BG       = (20, 15, 30)
    C_HINT   = (200, 200, 200)

    _SPRAY_UI = {
        "blue":  ((40, 100, 255), (80, 140, 255)),
        "green": ((40, 200, 40),  (80, 255, 80)),
        "red":   ((255, 40, 40),  (255, 80, 80)),
    }
    if pending:
        st = pending.get("spray_type", "red")
        C_BORDER, C_TITLE = _SPRAY_UI.get(st, _SPRAY_UI["red"])
        line0 = "Spray Paint — Choose direction"
        line1 = "[Arrow/Numpad] Spray tile"
    else:
        C_BORDER = (255, 100, 0)
        C_TITLE  = (255, 160, 40)
        line0 = "Fire! — Choose direction"
        line1 = "[Arrow/Numpad] Place fire"
    line2 = "[Esc] Cancel"
    popup_w = max(len(line0), len(line1), len(line2)) + 4
    popup_h = 5

    map_px = px + MAP_OFFSET_X
    map_py = py + HEADER_HEIGHT
    map_h  = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_px - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_py + 3
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = map_py - popup_h - 2

    popup_console = tcod.console.Console(popup_w, popup_h)
    for iy in range(popup_h):
        for ix in range(popup_w):
            popup_console.print(ix, iy, " ", bg=BG)
    for ix in range(popup_w):
        popup_console.print(ix, 0,           "─", fg=C_BORDER, bg=BG)
        popup_console.print(ix, popup_h - 1, "─", fg=C_BORDER, bg=BG)
    for iy in range(popup_h):
        popup_console.print(0,           iy, "│", fg=C_BORDER, bg=BG)
        popup_console.print(popup_w - 1, iy, "│", fg=C_BORDER, bg=BG)
    popup_console.print(0,           0,           "┌", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, 0,           "┐", fg=C_BORDER, bg=BG)
    popup_console.print(0,           popup_h - 1, "└", fg=C_BORDER, bg=BG)
    popup_console.print(popup_w - 1, popup_h - 1, "┘", fg=C_BORDER, bg=BG)
    popup_console.print(2, 1, line0, fg=C_TITLE, bg=BG)
    popup_console.print(2, 2, line1, fg=C_HINT,  bg=BG)
    popup_console.print(2, 3, line2, fg=C_HINT,  bg=BG)
    popup_console.blit(console, popup_x, popup_y, fg_alpha=1.0, bg_alpha=0.72)


def render_abilities_menu(console, engine):
    """Render the abilities overlay panel (toggled with A key)."""
    BG      = (18, 18, 28)
    BG_SEL  = (35, 35, 55)
    C_TITLE = (255, 255, 180)
    C_HEAD  = (180, 180, 255)
    C_LABEL = (180, 180, 180)
    C_KEY   = (220, 220, 80)
    C_CHAR  = (100, 140, 255)
    C_CANT  = (100, 100, 100)
    C_DESC  = (150, 150, 190)
    C_DIV   = (80, 80, 120)
    C_HINT  = (100, 100, 100)
    C_AVAIL = (100, 220, 100)
    C_CURSOR = (255, 220, 80)

    abilities = engine.player_abilities

    # Build usable list (same filter as engine)
    usable_abilities = []
    for inst in abilities:
        defn = ABILITY_REGISTRY.get(inst.ability_id)
        if defn is not None and inst.can_use():
            usable_abilities.append((inst, defn))

    panel_w = 54
    n_rows = max(1, len(usable_abilities))
    # border(2) + title(1) + divider(1) + header(1) + divider(1) + rows + divider(1) + desc(2) + hint(1)
    desc_lines = 2
    panel_h = 7 + n_rows + 1 + desc_lines
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "ABILITIES"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    # Column headers
    console.print(panel_x + 2,  panel_y + 3, "#",      fg=C_HEAD, bg=BG)
    console.print(panel_x + 5,  panel_y + 3, "Ability", fg=C_HEAD, bg=BG)
    console.print(panel_x + 20, panel_y + 3, "Charges", fg=C_HEAD, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 4, "─", fg=C_DIV, bg=BG)

    # Clamp cursor
    cursor = getattr(engine, 'abilities_cursor', 0)
    if len(usable_abilities) > 0:
        cursor = max(0, min(cursor, len(usable_abilities) - 1))

    if not usable_abilities:
        console.print(panel_x + 2, panel_y + 5,
                      "(no abilities — gain them from items or skills)",
                      fg=C_CANT, bg=BG)
    else:
        for display_idx, (inst, defn) in enumerate(usable_abilities):
            row = panel_y + 5 + display_idx
            is_selected = (display_idx == cursor)
            row_bg = BG_SEL if is_selected else BG
            cd = engine.ability_cooldowns.get(inst.ability_id, 0)
            on_cooldown = cd > 0
            name_color = C_CANT if on_cooldown else defn.color

            # Highlight entire row background if selected
            if is_selected:
                for px in range(1, panel_w - 1):
                    console.print(panel_x + px, row, " ", fg=C_LABEL, bg=row_bg)

            # Cursor arrow
            if is_selected:
                console.print(panel_x + 1, row, ">", fg=C_CURSOR, bg=row_bg)

            # Key number (1-9)
            key_str = str(display_idx + 1) if display_idx < 9 else "-"
            console.print(panel_x + 2, row, f"{key_str})", fg=C_KEY, bg=row_bg)

            # Ability char glyph
            console.print(panel_x + 5, row, defn.char, fg=name_color, bg=row_bg)

            # Name
            console.print(panel_x + 7, row, defn.name[:12], fg=name_color, bg=row_bg)

            # Charges / cooldown
            if on_cooldown:
                charge_str = f"CD:{cd}t"
                console.print(panel_x + 20, row, charge_str[:11], fg=C_CANT, bg=row_bg)
            else:
                charge_str = inst.charge_display(defn)
                console.print(panel_x + 20, row, charge_str[:11], fg=C_AVAIL, bg=row_bg)

            # "per floor" tag anchored to right edge for floor-refresh abilities
            if defn.charge_type.value in ("per_floor", "floor_only"):
                tag = "per floor"
                tag_x = panel_x + panel_w - 2 - len(tag)
                console.print(tag_x, row, tag, fg=C_HINT, bg=row_bg)

    # Divider before description
    desc_div_y = panel_y + 5 + n_rows
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, desc_div_y, "─", fg=C_DIV, bg=BG)

    # Description of selected ability
    if usable_abilities and 0 <= cursor < len(usable_abilities):
        _, sel_defn = usable_abilities[cursor]
        desc_text = sel_defn.description or ""
        max_desc_w = panel_w - 4
        # Word-wrap to fit panel width, up to desc_lines lines
        words = desc_text.split()
        lines = []
        current_line = ""
        for word in words:
            test = f"{current_line} {word}".strip()
            if len(test) <= max_desc_w:
                current_line = test
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)
        for li, line in enumerate(lines[:desc_lines]):
            console.print(panel_x + 2, desc_div_y + 1 + li, line, fg=C_DESC, bg=BG)

    # Hint
    hint = "[Shift+#] Bind Hotbar  [A/Esc] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def _build_perks_items(engine):
    """Build the filtered list of display items for the perks menu.

    Returns (all_items, selectable_indices) where:
      all_items: list of dicts with kind, text, colour, perk
      selectable_indices: list of indices into all_items that are perk rows
    Only includes skills with level >= 1.  For each such skill shows earned
    perks plus the next one (greyed), skipping placeholder perks that aren't
    earned yet.
    """
    C_SKILL  = (180, 180, 255)
    C_EARNED = (120, 200, 120)
    C_NEXT   = (90,  90,  90)

    all_items = []
    for skill_name in _SKILL_NAMES:
        skill = engine.skills.get(skill_name)
        if not skill or skill.level < 1:
            continue
        all_items.append({"kind": "header", "text": skill_name, "colour": C_SKILL, "perk": None})
        next_level = skill.level + 1
        for lvl in range(1, min(next_level + 1, 11)):
            perk = get_perk(skill_name, lvl)
            if not perk:
                continue
            earned = (lvl <= skill.level)
            # Skip placeholder future perks (nothing to preview)
            if not earned and perk.get("perk_type") == "none":
                continue
            marker = "[+]" if earned else "[ ]"
            colour = C_EARNED if earned else C_NEXT
            all_items.append({
                "kind":   "perk",
                "text":   f"  {marker} Lv{lvl:2d}: {perk['name']}",
                "colour": colour,
                "perk":   perk,
                "earned": earned,
            })

    selectable = [i for i, item in enumerate(all_items) if item["kind"] == "perk"]
    return all_items, selectable


def count_perks_menu_selectables(engine) -> int:
    """Return the number of selectable perk rows (used by engine input handler)."""
    _, selectable = _build_perks_items(engine)
    return len(selectable)


def _wrap_text(text: str, width: int) -> list[str]:
    """Word-wrap text to fit within width, returning a list of lines."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current:
            candidate = current + " " + word
        else:
            candidate = word
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_perks_menu(console, engine):
    """Render the perks overlay: filtered skills/perks with cursor and description box."""
    BG       = (18, 18, 28)
    C_TITLE  = (255, 255, 180)
    C_DIV    = (80,  80, 120)
    C_HINT   = (100, 100, 130)
    C_CURSOR = (35,  55,  80)
    C_DESC   = (200, 200, 160)
    C_NODESC = (80,  80,  80)

    panel_w  = 58
    DESC_ROWS = 3  # lines of description text below the divider
    # total fixed overhead: top_border(1)+title(1)+div(1)+desc_div(1)+desc(DESC_ROWS)+hint(1)+bot_border(1) = 7+DESC_ROWS
    overhead  = 7 + DESC_ROWS
    max_list  = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - overhead
    max_list  = max(max_list, 4)

    all_items, selectable = _build_perks_items(engine)
    n_sel = len(selectable)

    # Nothing to show
    if not all_items:
        panel_h = 5
        panel_x = (SCREEN_WIDTH - panel_w) // 2
        panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2
        _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)
        title = "PERKS"
        console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)
        msg = "No skills unlocked yet"
        console.print(panel_x + (panel_w - len(msg)) // 2, panel_y + 2, msg, fg=C_NODESC, bg=BG)
        return

    # Clamp cursor
    cursor = max(0, min(getattr(engine, "perk_cursor", 0), n_sel - 1)) if n_sel > 0 else 0
    engine.perk_cursor = cursor

    # Resolve which all_items index the cursor points to
    cursor_item_idx = selectable[cursor] if selectable else 0

    visible = min(len(all_items), max_list)

    # Auto-scroll to keep cursor in view
    scroll = getattr(engine, "perks_scroll", 0)
    if cursor_item_idx < scroll:
        scroll = cursor_item_idx
    elif cursor_item_idx >= scroll + visible:
        scroll = cursor_item_idx - visible + 1
    scroll = max(0, min(scroll, max(0, len(all_items) - visible)))
    engine.perks_scroll = scroll

    panel_h  = overhead + visible
    panel_x  = (SCREEN_WIDTH - panel_w) // 2
    panel_y  = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "PERKS"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Top divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    # List rows
    for i, item in enumerate(all_items[scroll: scroll + visible]):
        row_y   = panel_y + 3 + i
        abs_idx = scroll + i
        is_sel  = (item["kind"] == "perk" and abs_idx == cursor_item_idx)
        row_bg  = C_CURSOR if is_sel else BG
        text    = item["text"][: panel_w - 4]
        # Fill row bg first, then print text
        console.print(panel_x + 1, row_y, " " * (panel_w - 2), fg=item["colour"], bg=row_bg)
        console.print(panel_x + 2, row_y, text, fg=item["colour"], bg=row_bg)
        # Cursor arrow on selected row
        if is_sel:
            console.print(panel_x + panel_w - 3, row_y, "◄", fg=C_TITLE, bg=row_bg)

    # Description divider
    desc_div_y = panel_y + 3 + visible
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, desc_div_y, "─", fg=C_DIV, bg=BG)

    # Description text
    if selectable:
        perk = all_items[cursor_item_idx].get("perk") or {}
        desc  = perk.get("desc", "")
    else:
        desc = ""

    if desc:
        wrapped = _wrap_text(desc, panel_w - 4)
        for i, line in enumerate(wrapped[: DESC_ROWS]):
            console.print(panel_x + 2, desc_div_y + 1 + i, line, fg=C_DESC, bg=BG)
    else:
        no_desc = "No description available."
        console.print(panel_x + 2, desc_div_y + 1, no_desc, fg=C_NODESC, bg=BG)

    # Hint
    hint = "[↑↓] Select  [Shift+P / Esc] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_look_targeting(console, engine):
    """Render the Look mode cursor on the map with a small tooltip."""
    from config import TILE_FLOOR

    cx, cy = engine.look_cursor
    map_cx = cx + MAP_OFFSET_X
    map_cy = cy + HEADER_HEIGHT

    is_visible = bool(engine.dungeon.visible[cy, cx])
    is_explored = bool(engine.dungeon.explored[cy, cx])

    # Color-code the cursor
    if not is_explored:
        cursor_bg = (80, 80, 80)
    elif not is_visible:
        cursor_bg = (60, 60, 100)
    else:
        cursor_bg = (30, 120, 60)

    console.print(map_cx, map_cy, "X", fg=(255, 255, 255), bg=cursor_bg)

    # Build one-line summary for tooltip
    summary = ""
    if is_visible:
        if engine.player.x == cx and engine.player.y == cy:
            summary = "You"
        entities = engine.dungeon.get_entities_at(cx, cy)
        for e in entities:
            if e.entity_type == "monster" and e.alive:
                summary = e.name
                break
            elif not summary:
                if e.entity_type in ("item", "staircase", "cash", "hazard"):
                    summary = e.name
        if not summary:
            tile = engine.dungeon.tiles[cy][cx]
            summary = "Floor" if tile == TILE_FLOOR else "Wall"
    elif is_explored:
        tile = engine.dungeon.tiles[cy][cx]
        summary = f"{'Floor' if tile == TILE_FLOOR else 'Wall'} (not visible)"
    else:
        summary = "Unexplored"

    # Draw tooltip popup near cursor
    BG = (20, 15, 30)
    C_HINT = (140, 140, 170)
    C_SUMMARY = (220, 235, 255)

    hint = "[Enter] Inspect  [Esc] Exit"
    popup_w = max(len(summary) + 4, len(hint) + 4)
    popup_h = 4

    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    popup_x = max(MAP_OFFSET_X, min(map_cx - 1, MAP_OFFSET_X + MAP_WIDTH - popup_w - 1))
    popup_y = map_cy + 2
    if popup_y + popup_h >= HEADER_HEIGHT + map_h:
        popup_y = map_cy - popup_h - 1

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)
    console.print(popup_x + 2, popup_y + 1, summary, fg=C_SUMMARY, bg=BG)
    console.print(popup_x + 2, popup_y + 2, hint, fg=C_HINT, bg=BG)


def render_look_info(console, engine):
    """Render the Look info popup — centered panel with tile/entity details."""
    BG      = (20, 18, 30)
    C_TITLE = (255, 255, 180)
    C_DIV   = (80,  80, 120)
    C_HINT  = (100, 100, 130)

    title = engine.look_info_title
    lines = engine.look_info_lines

    # Calculate width from content, capped at 44
    max_line_w = len(title)
    for line_parts in lines:
        line_len = sum(len(t) for t, *_ in line_parts)
        if line_len > max_line_w:
            max_line_w = line_len
    popup_w = min(44, max(20, max_line_w + 6))

    # Clamp line count so popup fits on screen
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    max_content_lines = max(4, map_h - 7)
    visible_lines = lines[:max_content_lines]

    # Height: border(1) + title(1) + div(1) + content(n) + hint(1) + border(1)
    popup_h = len(visible_lines) + 5
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (map_h - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Title
    title_disp = title[:popup_w - 4]
    console.print(popup_x + (popup_w - len(title_disp)) // 2, popup_y + 1,
                  title_disp, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, popup_w - 1):
        console.print(popup_x + px, popup_y + 2, "─", fg=C_DIV, bg=BG)

    # Content lines
    for i, line_parts in enumerate(visible_lines):
        cx = popup_x + 2
        cy = popup_y + 3 + i
        for part in line_parts:
            if isinstance(part, tuple) and len(part) >= 2:
                text, color = part[0], part[1]
            else:
                text = str(part)
                color = (200, 200, 200)
            clipped = text[:popup_w - (cx - popup_x) - 1]
            console.print(cx, cy, clipped, fg=color, bg=BG)
            cx += len(clipped)

    # Hint
    hint = "[Any key] Back"
    console.print(popup_x + (popup_w - len(hint)) // 2,
                  popup_y + popup_h - 2, hint, fg=C_HINT, bg=BG)


def render_perk_popup(console, engine):
    """Render a perk unlock popup — shown when the player levels up a skill."""
    if not engine.perk_popup_queue:
        return

    info = engine.perk_popup_queue[0]
    perk = info["perk"]
    skill_name = info["skill_name"]
    level = info["level"]
    perk_name = perk["name"]
    perk_type = perk.get("perk_type", "none")
    desc = perk.get("desc", "")

    BG        = (12, 12, 24)
    C_BORDER  = (180, 150, 50)
    C_SKILL   = (180, 180, 255)
    C_LEVEL   = (255, 255, 180)
    C_NAME    = (255, 215, 0)
    C_DESC    = (200, 200, 170)
    C_HINT    = (100, 100, 130)

    # Perk type badge colors
    TYPE_COLORS = {
        "stat":      ((80, 220, 160), "[STAT]"),
        "passive":   ((120, 180, 255), "[PASSIVE]"),
        "activated": ((255, 160, 80),  "[ABILITY]"),
        "grant_item":((200, 160, 255), "[ITEM]"),
    }
    badge_color, badge_text = TYPE_COLORS.get(perk_type, ((160, 160, 160), f"[{perk_type.upper()}]"))

    panel_w = 48
    inner_w = panel_w - 4  # 2 border + 2 padding
    desc_lines = _wrap_text(desc, inner_w) if desc else []
    # Clamp desc to reasonable height
    max_desc_lines = 6
    desc_lines = desc_lines[:max_desc_lines]

    # Layout: border(1) + blank(1) + "PERK UNLOCKED"(1) + blank(1) + skill+level(1)
    #       + perk_name(1) + badge(1) + div(1) + desc(n) + blank(1) + hint(1) + border(1)
    panel_h = 11 + len(desc_lines)
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    # Draw background
    for dy in range(panel_h):
        for dx in range(panel_w):
            console.print(panel_x + dx, panel_y + dy, " ", bg=BG)

    # Draw gold border
    # Top/bottom
    for dx in range(panel_w):
        console.print(panel_x + dx, panel_y, "═", fg=C_BORDER, bg=BG)
        console.print(panel_x + dx, panel_y + panel_h - 1, "═", fg=C_BORDER, bg=BG)
    # Left/right
    for dy in range(1, panel_h - 1):
        console.print(panel_x, panel_y + dy, "║", fg=C_BORDER, bg=BG)
        console.print(panel_x + panel_w - 1, panel_y + dy, "║", fg=C_BORDER, bg=BG)
    # Corners
    console.print(panel_x, panel_y, "╔", fg=C_BORDER, bg=BG)
    console.print(panel_x + panel_w - 1, panel_y, "╗", fg=C_BORDER, bg=BG)
    console.print(panel_x, panel_y + panel_h - 1, "╚", fg=C_BORDER, bg=BG)
    console.print(panel_x + panel_w - 1, panel_y + panel_h - 1, "╝", fg=C_BORDER, bg=BG)

    y = panel_y + 2
    # Title
    title = "PERK UNLOCKED"
    console.print(panel_x + (panel_w - len(title)) // 2, y, title, fg=C_NAME, bg=BG)
    y += 2

    # Skill name + level
    skill_line = f"{skill_name}  Lv {level}"
    console.print(panel_x + (panel_w - len(skill_line)) // 2, y, skill_line, fg=C_SKILL, bg=BG)
    y += 1

    # Perk name
    console.print(panel_x + (panel_w - len(perk_name)) // 2, y, perk_name, fg=C_NAME, bg=BG)
    y += 1

    # Badge
    console.print(panel_x + (panel_w - len(badge_text)) // 2, y, badge_text, fg=badge_color, bg=BG)
    y += 1

    # Divider
    for dx in range(1, panel_w - 1):
        console.print(panel_x + dx, y, "─", fg=C_BORDER, bg=BG)
    y += 1

    # Description
    for line in desc_lines:
        console.print(panel_x + 2, y, line, fg=C_DESC, bg=BG)
        y += 1

    # Hint at bottom
    remaining = len(engine.perk_popup_queue) - 1
    if remaining > 0:
        hint = f"[Any key] Next ({remaining} more)"
    else:
        hint = "[Any key] Continue"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_dev_menu(console, engine):
    """Render the dev tools overlay menu."""
    if not DEV_MODE:
        return

    BG       = (10, 10, 30)
    C_TITLE  = (255, 80, 80)
    C_DIV    = (100, 40, 40)
    C_OPTION = (220, 220, 220)
    C_CURSOR = (40, 40, 80)
    C_KEY    = (255, 200, 80)
    C_HINT   = (100, 100, 130)
    C_ON     = (80, 255, 80)
    C_OFF    = (160, 160, 160)

    options = [
        ("+500k Potential XP (All Skills)", "add_potential_xp"),
        ("Spawn Item...",                  "spawn_item"),
        ("Kill All Monsters in View",      "kill_in_view"),
        ("Invincibility",                  "toggle_invincible"),
        ("Reveal Entire Map",              "reveal_map"),
        ("Add $1,000 Cash",                "add_cash"),
        ("Full Heal",                      "full_heal"),
        ("Teleport to Stairs",             "teleport_stairs"),
        ("Teleport to Floor...",           "teleport_floor"),
        ("Add +5 to All Stats",            "add_stats"),
        ("Meth Lab Kit",                   "meth_lab_kit"),
    ]

    panel_w = 42
    panel_h = len(options) + 6  # border(2) + title(1) + div(1) + options + hint(1) + gap(1)
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    title = "[ DEV TOOLS ]"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    for i, (label, key) in enumerate(options):
        row_y = panel_y + 3 + i
        row_bg = C_CURSOR if i == engine.dev_menu_cursor else BG
        for px in range(1, panel_w - 1):
            console.print(panel_x + px, row_y, " ", bg=row_bg)

        num = str((i + 1) % 10) if i < 10 else "-"
        console.print(panel_x + 2, row_y, f"[{num}]", fg=C_KEY, bg=row_bg)

        # Special label for toggle option
        if key == "toggle_invincible":
            state_text = "ON " if engine.player.dev_invincible else "OFF"
            state_col  = C_ON if engine.player.dev_invincible else C_OFF
            console.print(panel_x + 6, row_y, label, fg=C_OPTION, bg=row_bg)
            console.print(panel_x + 6 + len(label) + 1, row_y, state_text, fg=state_col, bg=row_bg)
        else:
            console.print(panel_x + 6, row_y, label, fg=C_OPTION, bg=row_bg)

    hint = "[1-0/↑↓+Enter] Select  [Shift+`/Esc] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2, panel_y + panel_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_dev_item_select(console, engine):
    """Render the dev item spawn picker with search."""
    if not DEV_MODE:
        return

    from items import get_item_def

    BG       = (10, 10, 30)
    C_TITLE  = (255, 80, 80)
    C_DIV    = (100, 40, 40)
    C_ITEM   = (220, 220, 220)
    C_CURSOR = (40, 40, 80)
    C_HINT   = (100, 100, 130)
    C_CAT    = (180, 180, 100)
    C_SEARCH = (100, 255, 100)
    C_SEARCH_BG = (20, 30, 20)

    items = engine.dev_item_filtered
    n = len(items)
    rows = 18
    panel_w = 50
    panel_h = rows + 8
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    # Keep cursor in view
    if engine.dev_item_cursor < engine.dev_item_scroll:
        engine.dev_item_scroll = engine.dev_item_cursor
    elif engine.dev_item_cursor >= engine.dev_item_scroll + rows:
        engine.dev_item_scroll = engine.dev_item_cursor - rows + 1

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    title = "[ SPAWN ITEM ]"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    # Search bar
    search_y = panel_y + 2
    search_text = engine.dev_item_search
    search_display = f" Search: {search_text}_"
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, search_y, " ", bg=C_SEARCH_BG)
    console.print(panel_x + 2, search_y, search_display[:panel_w - 4], fg=C_SEARCH, bg=C_SEARCH_BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 3, "─", fg=C_DIV, bg=BG)

    list_start_y = panel_y + 4
    for row in range(rows):
        idx = engine.dev_item_scroll + row
        if idx >= n:
            break
        item_id = items[idx]
        defn = get_item_def(item_id)
        name = defn.get("name", item_id) if defn else item_id
        cat  = (defn.get("category", "") if defn else "")[:3].upper()
        row_y  = list_start_y + row
        row_bg = C_CURSOR if idx == engine.dev_item_cursor else BG
        for px in range(1, panel_w - 1):
            console.print(panel_x + px, row_y, " ", bg=row_bg)
        console.print(panel_x + 2, row_y, f"{cat:<3}", fg=C_CAT, bg=row_bg)
        console.print(panel_x + 6, row_y, name[:panel_w - 8], fg=C_ITEM, bg=row_bg)

    scroll_info = f" {engine.dev_item_scroll + 1}-{min(engine.dev_item_scroll + rows, n)}/{n} "
    hint = f"[Type] Search [Bksp] Clear [Enter] Spawn"
    console.print(panel_x + (panel_w - len(hint)) // 2, panel_y + panel_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_dev_floor_select(console, engine):
    """Render the dev floor teleport picker."""
    if not DEV_MODE:
        return

    from config import ZONE_ORDER, get_zone_for_floor, get_total_floors

    BG       = (10, 10, 30)
    C_TITLE  = (255, 80, 80)
    C_DIV    = (100, 40, 40)
    C_FLOOR  = (220, 220, 220)
    C_CURSOR = (40, 40, 80)
    C_HINT   = (100, 100, 130)
    C_ZONE   = (180, 140, 80)
    C_CURRENT = (80, 255, 80)

    total = get_total_floors()
    # Build floor list: [(label, global_floor_index), ...]
    floors = []
    for gf in range(total):
        zone_key, zone_floor, display_name, zone_type = get_zone_for_floor(gf)
        zone_total = sum(z["floors"] for z in ZONE_ORDER if z["key"] == zone_key)
        if zone_type == "pseudozone":
            label = display_name
        else:
            label = f"{display_name} - Floor {zone_floor + 1}/{zone_total}"
        floors.append((label, gf))

    n = len(floors)
    panel_w = 44
    panel_h = n + 6
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    title = "[ TELEPORT TO FLOOR ]"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    for i, (label, gf) in enumerate(floors):
        row_y = panel_y + 3 + i
        row_bg = C_CURSOR if i == engine.dev_floor_cursor else BG
        for px in range(1, panel_w - 1):
            console.print(panel_x + px, row_y, " ", bg=row_bg)

        # Highlight current floor
        fg = C_CURRENT if gf == engine.current_floor else C_FLOOR
        marker = " <" if gf == engine.current_floor else ""
        console.print(panel_x + 2, row_y, label[:panel_w - 6] + marker, fg=fg, bg=row_bg)

    hint = "[↑↓+Enter] Select  [Esc] Back"
    console.print(panel_x + (panel_w - len(hint)) // 2, panel_y + panel_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_dev_skill_select(console, engine):
    """Render the dev skill level-up picker."""
    if not DEV_MODE:
        return

    from skills import SKILL_NAMES, MAX_LEVEL

    BG       = (10, 10, 30)
    C_TITLE  = (255, 80, 80)
    C_DIV    = (100, 40, 40)
    C_SKILL  = (220, 220, 220)
    C_CURSOR = (40, 40, 80)
    C_HINT   = (100, 100, 130)
    C_LVL    = (120, 200, 120)
    C_MAXED  = (255, 200, 50)

    skills = SKILL_NAMES
    n = len(skills)
    rows = min(n, 24)
    panel_w = 50
    panel_h = rows + 6
    panel_x = (SCREEN_WIDTH - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    # Keep cursor in view
    if engine.dev_skill_cursor < engine.dev_skill_scroll:
        engine.dev_skill_scroll = engine.dev_skill_cursor
    elif engine.dev_skill_cursor >= engine.dev_skill_scroll + rows:
        engine.dev_skill_scroll = engine.dev_skill_cursor - rows + 1

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    title = "[ LEVEL UP SKILL ]"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1, title, fg=C_TITLE, bg=BG)

    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    for row in range(rows):
        idx = engine.dev_skill_scroll + row
        if idx >= n:
            break
        skill_name = skills[idx]
        skill = engine.skills.get(skill_name)
        lvl = skill.level
        row_y = panel_y + 3 + row
        row_bg = C_CURSOR if idx == engine.dev_skill_cursor else BG
        for px in range(1, panel_w - 1):
            console.print(panel_x + px, row_y, " ", bg=row_bg)
        is_max = lvl >= MAX_LEVEL
        lvl_fg = C_MAXED if is_max else C_LVL
        lvl_str = "MAX" if is_max else f"Lv {lvl}"
        console.print(panel_x + 2, row_y, skill_name[:30], fg=C_SKILL, bg=row_bg)
        console.print(panel_x + 34, row_y, lvl_str, fg=lvl_fg, bg=row_bg)

    scroll_info = f" {engine.dev_skill_scroll + 1}-{min(engine.dev_skill_scroll + rows, n)}/{n} "
    hint = f"[↑↓]{scroll_info}[Enter] +1 Level  [Esc] Back"
    console.print(panel_x + (panel_w - len(hint)) // 2, panel_y + panel_h - 2,
                  hint, fg=C_HINT, bg=BG)


def _render_hotbar_row(console, engine, slots, row_y, x_start, x_end):
    """Render one row of hotbar slots (up to 5 per row)."""
    from abilities import ABILITY_REGISTRY
    from config import HOTBAR_KEYS

    BG        = (18, 18, 24)
    C_KEY     = (120, 120, 150)
    C_CHARGE  = (100, 220, 100)
    C_EXHAUST = (60, 60, 60)
    C_CD      = (220, 200, 80)
    C_SEP     = (50, 50, 65)

    inner_w = x_end - x_start

    # Clear the row
    for x in range(x_start, x_end):
        console.print(x, row_y, " ", bg=BG)

    # Collect entries for these slots
    entries = []
    for slot in slots:
        binding = engine.hotbar[slot] if slot < len(engine.hotbar) else None
        if binding is None:
            entries.append(None)
            continue
        key_label = HOTBAR_KEYS[slot] if slot < len(HOTBAR_KEYS) else "?"

        if binding.startswith("item:"):
            # Item binding — show item name with count
            from items import ITEM_DEFS
            item_id = binding[5:]
            item_defn = ITEM_DEFS.get(item_id)
            if item_defn is None:
                entries.append(None)
                continue
            # Count how many the player has
            count = sum(1 for e in engine.player.inventory if e.item_id == item_id)
            entries.append(("item", key_label, item_defn, count))
        else:
            # Ability binding
            defn = ABILITY_REGISTRY.get(binding)
            if defn is None:
                entries.append(None)
                continue
            inst = next((a for a in engine.player_abilities if a.ability_id == binding), None)
            if inst is None:
                entries.append(None)
                continue
            entries.append(("ability", key_label, defn, inst))

    # Slot width: divide evenly across 5 slots
    slots_per_row = len(slots)
    slot_w = inner_w // slots_per_row

    for i, entry in enumerate(entries):
        slot_x = x_start + i * slot_w
        if entry is None:
            # Empty slot — show just the key dimmed
            key_label = HOTBAR_KEYS[slots[i]] if slots[i] < len(HOTBAR_KEYS) else "?"
            console.print(slot_x, row_y, f"[{key_label}]", fg=C_EXHAUST, bg=BG)
            continue

        entry_type = entry[0]

        if entry_type == "item":
            _, key_label, item_defn, count = entry
            name_color = tuple(item_defn.get("color", (200, 200, 200)))
            can_use = count > 0
            if not can_use:
                name_color = C_EXHAUST
            charge_str = f"x{count}" if count > 0 else "x0"
            charge_color = C_CHARGE if can_use else C_EXHAUST
            overhead = 3 + 1 + len(charge_str) + 1
            max_name = max(3, slot_w - overhead)
            name = item_defn.get("name", "???")[:max_name]
        else:
            _, key_label, defn, inst = entry
            cd = engine.ability_cooldowns.get(defn.ability_id, 0)
            can_use = inst.can_use() and cd <= 0
            name_color = defn.color if can_use else C_EXHAUST
            if cd > 0:
                charge_str = f"{cd}t"
                charge_color = C_CD
            else:
                charge_str = inst.charge_display(defn)
                charge_color = C_CHARGE if can_use else C_EXHAUST
            overhead = 3 + 1 + len(charge_str) + 1
            max_name = max(3, slot_w - overhead)
            name = defn.name[:max_name]

        col = slot_x
        console.print(col, row_y, f"[{key_label}]", fg=C_KEY, bg=BG)
        col += 3
        console.print(col, row_y, name, fg=name_color, bg=BG)
        col += len(name) + 1
        console.print(col, row_y, charge_str, fg=charge_color, bg=BG)


def render_hotbar(console, engine):
    """Render the ability hotbar (2 content rows) between the map and the UI panel.

    Row 1: slots 1-5 (indices 0-4)
    Row 2: slots 6-0 (indices 5-9)
    """
    from config import DUNGEON_HEIGHT

    x_start = MAP_OFFSET_X
    x_end   = MAP_OFFSET_X + MAP_WIDTH
    row0_y  = HEADER_HEIGHT + DUNGEON_HEIGHT
    row1_y  = row0_y + 1

    _render_hotbar_row(console, engine, [0, 1, 2, 3, 4], row0_y, x_start, x_end)
    _render_hotbar_row(console, engine, [5, 6, 7, 8, 9], row1_y, x_start, x_end)


def render_deep_fryer_menu(console, engine):
    """Render the deep-fryer food selection popup."""
    BG       = (22, 18, 28)
    C_TITLE  = (200, 140, 60)
    C_ITEM   = (220, 220, 220)
    C_CURSOR = (40, 30, 50)
    C_HINT   = (70, 70, 90)
    C_DIM    = (100, 100, 100)

    items = getattr(engine, "deep_fryer_items", [])
    cursor = getattr(engine, "deep_fryer_cursor", 0)
    n = len(items)

    popup_w = 36
    popup_h = min(n, 10) + 6
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    title = "[ DEEP FRYER ]"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    subtitle = "Select food to deep-fry:"
    console.print(popup_x + 2, popup_y + 2, subtitle, fg=C_DIM, bg=BG)

    visible = min(n, 10)
    scroll = max(0, cursor - visible + 1)
    for row in range(visible):
        idx = scroll + row
        if idx >= n:
            break
        _inv_idx, item = items[idx]
        row_y = popup_y + 3 + row
        row_bg = C_CURSOR if idx == cursor else BG
        for px in range(1, popup_w - 1):
            console.print(popup_x + px, row_y, " ", bg=row_bg)
        name = item.name[:popup_w - 4]
        console.print(popup_x + 2, row_y, name, fg=C_ITEM, bg=row_bg)

    hint = "[Up/Down] Select  [Enter] Fry  [Esc] Cancel"
    hint = hint[:popup_w - 2]
    console.print(popup_x + (popup_w - len(hint)) // 2, popup_y + popup_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_vending_machine_menu(console, engine):
    """Render the vending machine shop popup."""
    import time
    from items import get_item_def, get_item_value, get_strain_color

    BG       = (18, 22, 28)
    C_ITEM   = (220, 220, 220)
    C_CURSOR = (30, 40, 50)
    C_HINT   = (70, 70, 90)
    C_DIM    = (100, 100, 100)
    C_PRICE  = (255, 215, 0)
    C_CANT   = (255, 80, 80)

    # Pulsing title color (cyan gradient)
    t = time.time()
    pulse = int(180 + 75 * ((1 + __import__('math').sin(t * 3)) / 2))
    C_TITLE = (0, pulse, pulse)

    vm = getattr(engine, "vending_machine", None)
    stock = getattr(vm, "vending_stock", []) if vm else []
    cursor = getattr(engine, "vending_cursor", 0)
    n = len(stock)

    popup_w = 44
    popup_h = min(n, 10) + 7
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    title = "[ VENDING MACHINE ]"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    cash_str = f"Cash: ${engine.cash}"
    console.print(popup_x + popup_w - len(cash_str) - 2, popup_y + 2,
                  cash_str, fg=C_PRICE, bg=BG)

    if n == 0:
        console.print(popup_x + 2, popup_y + 3, "Empty!", fg=C_DIM, bg=BG)
    else:
        visible = min(n, 10)
        scroll = max(0, cursor - visible + 1)
        for row in range(visible):
            idx = scroll + row
            if idx >= n:
                break
            item_id, strain = stock[idx]
            defn = get_item_def(item_id) or {}
            name = defn.get("name", item_id)
            if strain:
                name = f"{strain} {name}"
            price = get_item_value(item_id, strain=strain)
            can_afford = engine.cash >= price

            row_y = popup_y + 3 + row
            row_bg = C_CURSOR if idx == cursor else BG
            for px in range(1, popup_w - 1):
                console.print(popup_x + px, row_y, " ", bg=row_bg)

            item_color = get_strain_color(strain) if strain else defn.get("color", C_ITEM)
            console.print(popup_x + 2, row_y, name[:popup_w - 14], fg=item_color, bg=row_bg)

            price_str = f"${price}"
            price_color = C_PRICE if can_afford else C_CANT
            console.print(popup_x + popup_w - len(price_str) - 2, row_y,
                          price_str, fg=price_color, bg=row_bg)

    hint = "[Up/Down] Select  [Enter] Buy  [Esc] Close"
    hint = hint[:popup_w - 2]
    console.print(popup_x + (popup_w - len(hint)) // 2, popup_y + popup_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_shop_item_popup(console, engine):
    """Render a small popup for a shop item in Tyrone's Penthouse."""
    from items import get_item_def, get_item_value

    BG       = (18, 22, 28)
    C_HINT   = (70, 70, 90)
    C_DIM    = (100, 100, 100)
    C_PRICE  = (255, 215, 0)
    C_CANT   = (255, 80, 80)

    entity = getattr(engine, "shop_item_entity", None)
    if entity is None:
        return

    item_id = getattr(entity, "item_id", None)
    price = getattr(entity, "shop_price", 0)
    defn = get_item_def(item_id) or {} if item_id else {}
    name = defn.get("name", str(item_id))
    description = defn.get("description", "")
    item_color = defn.get("color", (255, 255, 255))
    can_afford = engine.cash >= price

    # Wrap description to fit popup width
    popup_w = 34
    desc_lines = []
    if description:
        words = description.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 <= popup_w - 4:
                line = f"{line} {word}" if line else word
            else:
                desc_lines.append(line)
                line = word
        if line:
            desc_lines.append(line)

    popup_h = 6 + len(desc_lines)
    # Position popup near the item entity on screen
    # Convert world coords to screen coords (map panel offset)
    from config import LEFT_PANEL_WIDTH, HEADER_HEIGHT, MAP_WIDTH, SCREEN_HEIGHT, SCREEN_WIDTH, UI_HEIGHT
    cam_x = engine.player.x - MAP_WIDTH // 2
    cam_y = engine.player.y - (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT) // 2
    screen_x = LEFT_PANEL_WIDTH + (entity.x - cam_x)
    screen_y = HEADER_HEIGHT + (entity.y - cam_y)

    # Place popup below-right of the item, clamped to screen
    popup_x = min(screen_x + 2, SCREEN_WIDTH - popup_w - 1)
    popup_y = min(screen_y + 2, SCREEN_HEIGHT - UI_HEIGHT - popup_h - 1)
    popup_x = max(0, popup_x)
    popup_y = max(HEADER_HEIGHT, popup_y)

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Item name
    console.print(popup_x + 2, popup_y + 1, name[:popup_w - 4], fg=item_color, bg=BG)

    # Description lines
    for i, line in enumerate(desc_lines):
        console.print(popup_x + 2, popup_y + 2 + i, line[:popup_w - 4], fg=C_DIM, bg=BG)

    # Price + cash
    price_y = popup_y + 2 + len(desc_lines)
    price_str = f"Price: ${price}"
    price_color = C_PRICE if can_afford else C_CANT
    console.print(popup_x + 2, price_y, price_str, fg=price_color, bg=BG)

    cash_str = f"Cash: ${engine.cash}"
    console.print(popup_x + popup_w - len(cash_str) - 2, price_y, cash_str, fg=C_PRICE, bg=BG)

    # Hint
    hint = "[Enter] Buy  [Esc] Cancel"
    console.print(popup_x + (popup_w - len(hint)) // 2, popup_y + popup_h - 2,
                  hint, fg=C_HINT, bg=BG)


def render_ui(console, engine):
    """Render the bottom panel: messages on the left, stats on the right."""
    BG       = (28, 28, 38)
    C_HINT   = (80, 80, 110)
    C_TURN   = (160, 160, 180)
    C_LABEL  = (180, 180, 180)
    C_VALUE  = (255, 255, 255)
    C_BASE   = (110, 110, 110)   # muted gray for base value in parens
    C_BUFF   = (100, 220, 255)
    C_DEBUFF = (255, 100, 100)

    ui_y    = SCREEN_HEIGHT - UI_HEIGHT
    stats_x = MAP_OFFSET_X + MAP_WIDTH   # col 86 — aligns with inventory panel above
    bottom_y = SCREEN_HEIGHT - 1          # last row for bottom border

    # Fill background
    for x in range(SCREEN_WIDTH):
        for y in range(UI_HEIGHT):
            console.print(x, ui_y + y, " ", bg=BG)

    # ── Top separator with junction pieces ──────────────────────────
    for x in range(SCREEN_WIDTH):
        console.print(x, ui_y, "─", fg=C_PANEL_BORDER, bg=BG)
    # Left edge: double-line meets single horizontal
    console.print(0, ui_y, "╟", fg=C_FRAME, bg=BG)
    # Left panel border terminates here
    console.print(LEFT_PANEL_WIDTH - 1, ui_y, "┴", fg=C_PANEL_BORDER, bg=BG)
    # Right panel / stats border continues through
    console.print(stats_x, ui_y, "┼", fg=C_PANEL_BORDER, bg=BG)
    # Right edge: double-line meets single horizontal
    console.print(SCREEN_WIDTH - 1, ui_y, "╢", fg=C_FRAME, bg=BG)

    # Outer left border
    for dy in range(1, UI_HEIGHT - 1):
        console.print(0, ui_y + dy, "║", fg=C_FRAME, bg=BG)

    # Vertical border down the left edge of the stats area
    for dy in range(1, UI_HEIGHT - 1):
        console.print(stats_x, ui_y + dy, "│", fg=C_PANEL_BORDER, bg=BG)

    # Outer right border
    for dy in range(1, UI_HEIGHT - 1):
        console.print(SCREEN_WIDTH - 1, ui_y + dy, "║", fg=C_FRAME, bg=BG)

    # ── Bottom border (double-line) with keybind hints ──────────────
    for x in range(SCREEN_WIDTH):
        console.print(x, bottom_y, "═", fg=C_FRAME, bg=BG)
    console.print(0, bottom_y, "╚", fg=C_FRAME, bg=BG)
    console.print(stats_x, bottom_y, "╧", fg=C_FRAME, bg=BG)
    console.print(SCREEN_WIDTH - 1, bottom_y, "╝", fg=C_FRAME, bg=BG)

    # Keybind hints embedded in bottom border
    C_KEY_HINT = (120, 120, 160)
    C_KEY_LABEL = (80, 80, 110)
    hints = [
        ("S", "Skills"),
        ("A", "Abilities"),
        ("E", "Equip"),
        ("C", "Char"),
        ("F", "Fire"),
        (";", "Look"),
        ("^L", "Log"),
        ("^B", "Bestiary"),
        ("^P", "Perks"),
    ]
    hx = 2
    for key, label in hints:
        if hx + len(key) + len(label) + 2 > stats_x - 1:
            break
        console.print(hx, bottom_y, key, fg=C_KEY_HINT, bg=BG)
        hx += len(key)
        console.print(hx, bottom_y, f":{label}", fg=C_KEY_LABEL, bg=BG)
        hx += len(label) + 1 + 2  # colon + label + 2 space gap

    # Log hint (left of separator, on the top border)
    hint_text = "[Shift+L] Log"
    console.print(2, ui_y, hint_text, fg=C_HINT, bg=BG)

    # Turn counter just left of the stats column
    turn_text = f"Turn: {engine.turn}"
    console.print(stats_x - len(turn_text) - 2, ui_y, turn_text, fg=C_TURN, bg=BG)

    # "STATS" title-in-border on the top separator
    _draw_title_border(console, stats_x + 1, PANEL_WIDTH - 2, ui_y, "STATS", BG,
                       fg_border=C_PANEL_BORDER)

    # Stat rows — one per line in the right column
    # Current value = base + ring bonuses + temporary effects
    # Base value = raw stat (including permanent changes from effects like glory fists, but not temporary effects or rings)
    ps = engine.player_stats
    stat_rows = [
        ("Constitution",  ps.effective_constitution,  "constitution"),
        ("Strength",      ps.effective_strength,      "strength"),
        ("Book Smarts",   ps.effective_book_smarts,   "book_smarts"),
        ("Street Smarts", ps.effective_street_smarts, "street_smarts"),
        ("Tolerance",     ps.effective_tolerance,     "tolerance"),
        ("Swagger",       ps.effective_swagger,       "swagger"),
    ]
    C_SEP     = (45, 45, 65)
    sep_width = PANEL_WIDTH - 4
    for i, (label, current, attr) in enumerate(stat_rows):
        sy    = ui_y + 1 + i * 2
        base  = ps._base[attr]
        # Color based on whether current differs from base (includes rings + temporary effects)
        vc    = C_DEBUFF if current < base else (C_BUFF if current > base else C_VALUE)

        val_str  = str(current)
        base_str = f"({base})"

        # label left-aligned in 16 chars, value and base right-aligned at end
        console.print(stats_x + 2, sy, f"{label:<16}", fg=C_LABEL,  bg=BG)
        # Value and base together on the right (value + space + base)
        value_and_base = f"{val_str} {base_str}"
        console.print(stats_x + PANEL_WIDTH - len(value_and_base) - 2, sy, value_and_base, fg=vc,     bg=BG)
        # Recolor just the base portion
        console.print(stats_x + PANEL_WIDTH - len(base_str) - 2, sy, base_str,               fg=C_BASE, bg=BG)
        # Dot separator between stats (not after the last one)
        if i < len(stat_rows) - 1:
            console.print(stats_x + 2, sy + 1, "·" * sep_width, fg=C_SEP, bg=BG)

    # Message history — truncated to stay left of the stats border
    msg_width = stats_x - 3   # cols 2 … stats_x-2
    all_msgs  = list(engine.messages)
    visible   = UI_HEIGHT - 2  # reserve bottom row for border
    shown     = all_msgs[-visible:] if len(all_msgs) > visible else all_msgs
    n_shown   = len(shown)
    # Fade steps: oldest message at 35% brightness, newest at 100%
    for i, msg in enumerate(shown):
        msg_y  = ui_y + 1 + (visible - n_shown) + i
        # brightness 0.35 for oldest, 1.0 for newest
        fade   = 0.35 + 0.65 * (i / max(1, n_shown - 1))
        _render_msg(console, 2, msg_y, msg, msg_width, BG, fade=fade)

    # Death screen overlay
    if engine.game_over:
        # Darken the map area
        box_w, box_h = 30, 11
        box_x = SCREEN_WIDTH // 2 - box_w // 2
        box_y = SCREEN_HEIGHT // 2 - box_h // 2

        # Draw dark background box
        for bx in range(box_x, box_x + box_w):
            for by in range(box_y, box_y + box_h):
                console.print(bx, by, " ", fg=(0, 0, 0), bg=(20, 0, 0))

        # Border
        for bx in range(box_x, box_x + box_w):
            console.print(bx, box_y, chr(0x2500), fg=(150, 0, 0), bg=(20, 0, 0))
            console.print(bx, box_y + box_h - 1, chr(0x2500), fg=(150, 0, 0), bg=(20, 0, 0))
        for by in range(box_y, box_y + box_h):
            console.print(box_x, by, chr(0x2502), fg=(150, 0, 0), bg=(20, 0, 0))
            console.print(box_x + box_w - 1, by, chr(0x2502), fg=(150, 0, 0), bg=(20, 0, 0))
        # Corners
        console.print(box_x, box_y, chr(0x250C), fg=(150, 0, 0), bg=(20, 0, 0))
        console.print(box_x + box_w - 1, box_y, chr(0x2510), fg=(150, 0, 0), bg=(20, 0, 0))
        console.print(box_x, box_y + box_h - 1, chr(0x2514), fg=(150, 0, 0), bg=(20, 0, 0))
        console.print(box_x + box_w - 1, box_y + box_h - 1, chr(0x2518), fg=(150, 0, 0), bg=(20, 0, 0))

        # Title
        title = "YOU DIED"
        console.print(
            SCREEN_WIDTH // 2 - len(title) // 2, box_y + 2,
            title, fg=(255, 0, 0), bg=(20, 0, 0),
        )

        # Stats summary
        stats_line = f"Floor {engine.current_floor + 1}  |  {engine.kills} kills  |  Turn {engine.turn}"
        console.print(
            SCREEN_WIDTH // 2 - len(stats_line) // 2, box_y + 4,
            stats_line, fg=(180, 180, 180), bg=(20, 0, 0),
        )

        # Menu options
        options = ["Restart", "Quit to Menu"]
        for i, opt in enumerate(options):
            y = box_y + 7 + i
            if i == engine.death_screen_cursor:
                label = f"> {opt} <"
                fg = (255, 255, 0)
            else:
                label = f"  {opt}  "
                fg = (150, 150, 150)
            console.print(
                SCREEN_WIDTH // 2 - len(label) // 2, y,
                label, fg=fg, bg=(20, 0, 0),
            )


def render_settings_menu(console, engine):
    """Render the settings/display mode menu as a centered popup."""
    from engine import GameEngine
    modes = GameEngine.DISPLAY_MODES
    actions = GameEngine.SETTINGS_ACTIONS
    cursor = engine.settings_cursor
    current = engine.current_display_mode

    BG       = (20, 15, 30)
    C_BORDER = (160, 160, 210)
    C_TITLE  = (220, 235, 255)
    C_HINT   = (140, 140, 170)
    C_ITEM   = (200, 200, 220)
    C_ACTIVE = (100, 255, 100)
    C_CURSOR = (50, 40, 80)
    C_ACTION = (180, 220, 255)
    C_DIV    = (80, 80, 120)

    n_display = len(modes)
    n_actions = len(actions)
    n_total = n_display + n_actions
    # +2 for divider line and blank before actions
    popup_w = 36
    popup_h = n_total + 8
    popup_x = SCREEN_WIDTH // 2 - popup_w // 2
    popup_y = SCREEN_HEIGHT // 2 - popup_h // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    title = "[ SETTINGS ]"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    # Display modes
    for i, mode in enumerate(modes):
        row_y = popup_y + 3 + i
        row_bg = C_CURSOR if i == cursor else BG
        for px in range(1, popup_w - 1):
            console.print(popup_x + px, row_y, " ", bg=row_bg)
        label = mode["label"]
        if i == current:
            label += "  *"
            fg = C_ACTIVE
        else:
            fg = C_ITEM
        console.print(popup_x + 3, row_y, label, fg=fg, bg=row_bg)

    # Divider
    div_y = popup_y + 3 + n_display
    for px in range(1, popup_w - 1):
        console.print(popup_x + px, div_y, "-", fg=C_DIV, bg=BG)

    # Action items (Save Game, etc.)
    for i, act in enumerate(actions):
        row_y = div_y + 1 + i
        idx = n_display + i
        row_bg = C_CURSOR if idx == cursor else BG
        for px in range(1, popup_w - 1):
            console.print(popup_x + px, row_y, " ", bg=row_bg)
        console.print(popup_x + 3, row_y, act["label"], fg=C_ACTION, bg=row_bg)

    hint = "[Up/Down] Select  [Enter] Apply  [Esc] Close"
    console.print(popup_x + (popup_w - len(hint)) // 2, popup_y + popup_h - 2,
                  hint, fg=C_HINT, bg=BG)
