"""
Rendering system using tcod.
"""

import tcod
from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    TILE_WALL, TILE_FLOOR,
    HEADER_HEIGHT, UI_HEIGHT, MAX_MESSAGES,
    MAP_WIDTH, PANEL_WIDTH,
    LEFT_PANEL_WIDTH, MAP_OFFSET_X,
    INVENTORY_KEYS, LOG_HISTORY_SIZE, RING_SLOTS, RING_FINGER_NAMES,
)
from items import get_item_def, find_recipe, is_stackable, build_inventory_display_name, get_strain_color
from menu_state import MenuState
from enemies import MONSTER_REGISTRY
from abilities import ABILITY_REGISTRY


def render_header(console, engine):
    """Render the top header with zone and floor info."""
    zone_name = "Crack Den"  # TODO: support multiple zones
    floor_text = f"{zone_name} - Floor {engine.current_floor + 1}"

    # Fill header background
    for x in range(SCREEN_WIDTH):
        console.print(x, 0, " ", bg=(50, 50, 50))

    # Center the text in the header
    console.print(
        SCREEN_WIDTH // 2 - len(floor_text) // 2, 0,
        floor_text, fg=(200, 200, 255), bg=(50, 50, 50),
    )


def render_all(console, engine):
    """Render the entire game state."""
    render_header(console, engine)
    render_stats_panel(console, engine)
    render_dungeon(console, engine.dungeon)
    render_entities(console, engine.dungeon)
    render_inventory_panel(console, engine)
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
    elif engine.menu_state == MenuState.RING_REPLACE:
        render_ring_replace_menu(console, engine)
    elif engine.menu_state == MenuState.BESTIARY:
        render_bestiary_menu(console, engine)
    elif engine.menu_state == MenuState.TARGETING:
        render_targeting_mode(console, engine)
    elif engine.menu_state == MenuState.ABILITIES:
        render_abilities_menu(console, engine)


def render_dungeon(console, dungeon):
    """Render the dungeon map, offset right by MAP_OFFSET_X to make room for the stats panel."""
    for y in range(dungeon.height):
        for x in range(dungeon.width):
            cx = x + MAP_OFFSET_X
            cy = y + HEADER_HEIGHT
            tile = dungeon.tiles[y][x]
            is_visible = dungeon.visible[y, x]
            is_explored = dungeon.explored[y, x]

            if is_visible:
                if tile == TILE_WALL:
                    console.print(cx, cy, "#", fg=(140, 135, 130), bg=(28, 26, 24))
                elif tile == TILE_FLOOR:
                    console.print(cx, cy, ".", fg=(65, 60, 55), bg=(18, 16, 14))
            elif is_explored:
                if tile == TILE_WALL:
                    console.print(cx, cy, "#", fg=(65, 62, 60), bg=(14, 13, 12))
                elif tile == TILE_FLOOR:
                    console.print(cx, cy, ".", fg=(32, 30, 28), bg=(9, 8, 7))
            else:
                console.print(cx, cy, " ", fg=(0, 0, 0), bg=(0, 0, 0))


def get_entity_color(entity):
    """Get color for entity based on type. Items use their ITEM_DEF color."""
    if entity.entity_type == "player":
        return (255, 255, 255)  # White
    elif entity.entity_type == "monster":
        return (220, 50, 50)    # Red
    elif entity.entity_type == "item" and entity.item_id:
        strain = getattr(entity, "strain", None)
        if strain:
            return get_strain_color(strain)
        defn = get_item_def(entity.item_id)
        if defn:
            return defn["color"]
        return entity.color
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
        return 0  # item, cash

    for entity in sorted(dungeon.entities, key=_render_priority):
        if entity.alive and dungeon.visible[entity.y, entity.x]:
            color = get_entity_color(entity)
            console.print(entity.x + MAP_OFFSET_X, entity.y + HEADER_HEIGHT, entity.char, fg=color)


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


def _render_msg(console, x, y, msg, max_width, bg):
    """Render a message that is either a plain string or a list of (text, color) segments.

    Plain strings use get_message_color for the whole line.
    Segment lists render each part in its own color, truncated to max_width total chars.
    """
    if isinstance(msg, str):
        console.print(x, y, msg[:max_width], fg=get_message_color(msg), bg=bg)
    else:
        cx        = x
        remaining = max_width
        for text, color in msg:
            if remaining <= 0:
                break
            chunk = text[:remaining]
            console.print(cx, y, chunk, fg=color, bg=bg)
            cx        += len(chunk)
            remaining -= len(chunk)


def _draw_panel(console, x, y, w, h, bg):
    """Draw a filled bordered panel."""
    for py in range(h):
        for px in range(w):
            console.print(x + px, y + py, " ", bg=bg)
    for px in range(w):
        console.print(x + px, y,         "─", fg=(150, 150, 200), bg=bg)
        console.print(x + px, y + h - 1, "─", fg=(150, 150, 200), bg=bg)
    for py in range(h):
        console.print(x,         y + py, "│", fg=(150, 150, 200), bg=bg)
        console.print(x + w - 1, y + py, "│", fg=(150, 150, 200), bg=bg)
    console.print(x,         y,         "┌", fg=(150, 150, 200), bg=bg)
    console.print(x + w - 1, y,         "┐", fg=(150, 150, 200), bg=bg)
    console.print(x,         y + h - 1, "└", fg=(150, 150, 200), bg=bg)
    console.print(x + w - 1, y + h - 1, "┘", fg=(150, 150, 200), bg=bg)


def render_skills_menu(console, engine):
    """Render the skills/stats overlay panel."""
    BG       = (22, 22, 32)
    C_TITLE  = (255, 255, 180)
    C_HEAD   = (180, 180, 255)
    C_LABEL  = (180, 180, 180)
    C_VALUE  = (255, 255, 255)  # white for stat values
    C_XP     = (120, 200, 120)
    C_MAXED  = (255, 200, 50)
    C_HINT   = (100, 100, 100)
    C_DIV    = (80,  80, 120)

    panel_w = 46
    # header(3) + divider(1) + stats(3) + divider(1) + skill rows(14) + footer(2) + borders(2)
    panel_h = 26
    panel_x = (SCREEN_WIDTH  - panel_w) // 2
    panel_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - panel_h) // 2

    _draw_panel(console, panel_x, panel_y, panel_w, panel_h, BG)

    # Title
    title = "SKILLS"
    console.print(panel_x + (panel_w - len(title)) // 2, panel_y + 1,
                  title, fg=C_TITLE, bg=BG)

    # Divider
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 2, "─", fg=C_DIV, bg=BG)

    # Stats row — compact format
    p = engine.player
    hp_str = f"{p.hp}/{p.max_hp}"
    console.print(panel_x + 2,  panel_y + 3, f"HP {hp_str}", fg=C_LABEL, bg=BG)
    console.print(panel_x + 2 + 3 + 1, panel_y + 3, hp_str, fg=C_VALUE, bg=BG)

    kills_str = str(engine.kills)
    console.print(panel_x + 24, panel_y + 3, f"Kills {kills_str}", fg=C_LABEL, bg=BG)
    console.print(panel_x + 24 + 6 + 1, panel_y + 3, kills_str, fg=C_VALUE, bg=BG)

    power_str = str(p.power)
    console.print(panel_x + 2,  panel_y + 4, f"Power {power_str}", fg=C_LABEL, bg=BG)
    console.print(panel_x + 2 + 5 + 1, panel_y + 4, power_str, fg=C_VALUE, bg=BG)

    turn_str = str(engine.turn)
    console.print(panel_x + 24, panel_y + 4, f"Turn {turn_str}", fg=C_LABEL, bg=BG)
    console.print(panel_x + 24 + 5 + 1, panel_y + 4, turn_str, fg=C_VALUE, bg=BG)

    # Divider + skills header
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 5, "─", fg=C_DIV, bg=BG)
    console.print(panel_x + 2,  panel_y + 6, "Skill",   fg=C_HEAD, bg=BG)
    console.print(panel_x + 18, panel_y + 6, "Lv",      fg=C_HEAD, bg=BG)
    console.print(panel_x + 24, panel_y + 6, "XP",      fg=C_HEAD, bg=BG)
    console.print(panel_x + 34, panel_y + 6, "Next",    fg=C_HEAD, bg=BG)

    # Divider under column headers
    for px in range(1, panel_w - 1):
        console.print(panel_x + px, panel_y + 7, "─", fg=C_DIV, bg=BG)

    # Skill rows
    for i, skill in enumerate(engine.skills.all()):
        row = panel_y + 8 + i
        if skill.is_maxed():
            color_xp   = C_MAXED
            xp_str     = "MAX"
            next_str   = "---"
        else:
            color_xp   = C_XP
            xp_str     = str(skill.xp)
            next_str   = str(skill.xp_needed())

        console.print(panel_x + 2,  row, skill.name,      fg=C_LABEL,  bg=BG)
        console.print(panel_x + 18, row, str(skill.level), fg=C_VALUE, bg=BG)
        console.print(panel_x + 24, row, xp_str,          fg=color_xp, bg=BG)
        console.print(panel_x + 34, row, next_str,        fg=C_LABEL,  bg=BG)

    # Close hint
    hint = "[S] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_stats_panel(console, engine):
    """Render the persistent left-side stats / health / status panel."""
    BG        = (18, 18, 28)
    C_TITLE   = (255, 255, 180)
    C_LABEL   = (180, 180, 180)
    C_VALUE   = (255, 255, 255)
    C_HP_OK   = (80, 220, 80)
    C_HP_LOW  = (220, 80, 80)
    C_HP_BAR  = (40, 120, 40)
    C_HP_EMPTY = (30, 30, 30)
    C_ARMOR_BAR = (100, 180, 255)
    C_ARMOR_EMPTY = (30, 30, 30)
    C_DIV     = (60, 60, 100)
    C_BORDER  = (100, 100, 160)
    C_BUFF    = (100, 220, 255)
    C_DEBUFF  = (255, 100, 100)
    C_EMPTY   = (80, 80, 80)

    pw    = LEFT_PANEL_WIDTH          # 20 cols (0..19)
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT  # rows available between header and UI bar

    # Background fill
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        for x in range(pw):
            console.print(x, y, " ", bg=BG)

    # Right border (separator between stats panel and map)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(pw - 1, y, "│", fg=C_BORDER, bg=BG)

    row = HEADER_HEIGHT + 1

    # ── Title ────────────────────────────────────────────────────────
    title = "CHARACTER"
    console.print((pw - 1 - len(title)) // 2, row, title, fg=C_TITLE, bg=BG)
    row += 1

    # Divider
    for x in range(pw - 1):
        console.print(x, row, "─", fg=C_DIV, bg=BG)
    row += 1

    # ── Health ───────────────────────────────────────────────────────
    p = engine.player
    hp_ratio = p.hp / max(1, p.max_hp)
    hp_color = C_HP_OK if hp_ratio > 0.4 else C_HP_LOW

    hp_label = "HP"
    hp_value = f"{p.hp}/{p.max_hp}"
    console.print(1, row, f"{hp_label} {hp_value}", fg=C_LABEL, bg=BG)
    console.print(1 + len(hp_label) + 1, row, hp_value, fg=hp_color, bg=BG)
    row += 1

    # HP bar — fills inner width (pw-2 for margins, -1 for border)
    bar_w   = pw - 3          # 17 usable bar chars
    filled  = round(bar_w * hp_ratio)
    empty   = bar_w - filled
    console.print(1, row, "█" * filled, fg=hp_color,  bg=BG)
    console.print(1 + filled, row, "░" * empty,  fg=C_HP_EMPTY, bg=BG)
    row += 1

    # ── Armor ────────────────────────────────────────────────────────
    armor_ratio = p.armor / max(1, p.max_armor) if p.max_armor > 0 else 0
    armor_label = "Armor"
    armor_value = f"{p.armor}/{p.max_armor}"
    console.print(1, row, f"{armor_label} {armor_value}", fg=C_LABEL, bg=BG)
    console.print(1 + len(armor_label) + 1, row, armor_value, fg=C_VALUE, bg=BG)
    row += 1

    # Armor bar
    filled_armor  = round(bar_w * armor_ratio)
    empty_armor   = bar_w - filled_armor
    console.print(1, row, "█" * filled_armor, fg=C_ARMOR_BAR, bg=BG)
    console.print(1 + filled_armor, row, "░" * empty_armor, fg=C_ARMOR_EMPTY, bg=BG)
    row += 1

    # Divider
    for x in range(pw - 1):
        console.print(x, row, "─", fg=C_DIV, bg=BG)
    row += 1

    # ── Status effects ───────────────────────────────────────────────
    status_title = "STATUS"
    console.print((pw - 1 - len(status_title)) // 2, row, status_title, fg=C_TITLE, bg=BG)
    row += 1

    for x in range(pw - 1):
        console.print(x, row, "─", fg=C_DIV, bg=BG)
    row += 1

    cash_section_y = map_h - 3  # reserve bottom 2 rows for cash display

    status_effects = engine.player.status_effects
    if not status_effects:
        console.print(1, row, "(none)", fg=C_EMPTY, bg=BG)
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
                is_buff   = getattr(effect, "category", "debuff") == "buff"
                color     = C_BUFF if is_buff else C_DEBUFF
                marker    = "+" if is_buff else "-"
            name      = effect.display_name[: pw - 7]   # truncate
            # Append stack count for mogged effects
            if effect_id == "mogged" and getattr(effect, "amount", 0) > 0:
                name = f"{name} ({effect.amount})"
            turns_str = str(effect.duration)
            console.print(1, row, f"{marker} {name}", fg=color, bg=BG)
            console.print(pw - 2 - len(turns_str), row, turns_str, fg=color, bg=BG)
            row += 1

    # ── Cash ─────────────────────────────────────────────────────────
    for x in range(pw - 1):
        console.print(x, cash_section_y, "─", fg=C_DIV, bg=BG)
    cash_str = f"${engine.cash}"
    console.print(1, cash_section_y + 1, "CASH:", fg=C_LABEL, bg=BG)
    console.print(pw - 2 - len(cash_str), cash_section_y + 1, cash_str, fg=(255, 215, 0), bg=BG)


def render_inventory_panel(console, engine):
    """Render the persistent right-side inventory panel (columns MAP_WIDTH to SCREEN_WIDTH)."""
    BG       = (18, 18, 28)
    C_TITLE  = (255, 255, 180)
    C_LABEL  = (180, 180, 180)
    C_ITEM   = (255, 200, 0)
    C_EMPTY  = (80, 80, 80)
    C_DIV    = (60, 60, 100)
    C_BORDER = (100, 100, 160)

    px = MAP_OFFSET_X + MAP_WIDTH   # panel left edge (column 76)
    pw = PANEL_WIDTH                # 24 columns wide
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT  # height of the map area

    # Fill background
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        for x in range(pw):
            console.print(px + x, y, " ", bg=BG)

    # Left border (separator between map and panel)
    for y in range(HEADER_HEIGHT, HEADER_HEIGHT + map_h):
        console.print(px, y, "│", fg=C_BORDER, bg=BG)

    # Title
    title = "INVENTORY"
    console.print(px + (pw - len(title)) // 2, HEADER_HEIGHT + 1, title, fg=C_TITLE, bg=BG)

    # Divider under title
    for x in range(1, pw):
        console.print(px + x, HEADER_HEIGHT + 2, "─", fg=C_DIV, bg=BG)

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
    start_y   = HEADER_HEIGHT + 4
    end_row   = start_y + (map_h - 5)

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
            name = build_inventory_display_name(
                item.item_id, getattr(item, "strain", None), qty
            )[:max_name]

            # Item color: strain color if item has a strain, else definition color
            item_color = C_ITEM
            if defn:
                item_color = defn["color"]
            item_strain = getattr(item, "strain", None)
            if item_strain:
                item_color = get_strain_color(item_strain)

            # Combine-select coloring
            if combine_source is not None:
                if inv_idx == engine.selected_item_index:
                    console.print(px + 4, cur_row, name, fg=C_DIM, bg=BG)
                elif find_recipe(combine_source.item_id, item.item_id):
                    console.print(px + 4, cur_row, name, fg=C_COMBINE_TARGET, bg=BG)
                else:
                    console.print(px + 4, cur_row, name, fg=C_DIM, bg=BG)
            else:
                console.print(px + 4, cur_row, name, fg=item_color, bg=BG)

            cur_row += 1
            key_idx += 1

        if overflow > 0:
            console.print(px + 2, cur_row, f"  +{overflow} more", fg=C_EMPTY, bg=BG)

    # Divider above weight/count row
    footer_y = HEADER_HEIGHT + map_h - 2
    for x in range(1, pw):
        console.print(px + x, footer_y, "─", fg=C_DIV, bg=BG)

    count_text = f"Items: {len(inventory)}"
    console.print(px + 2, footer_y + 1, count_text, fg=C_LABEL, bg=BG)


def render_item_menu(console, engine):
    """Render the item action popup (small overlay near inventory panel)."""
    BG       = (30, 25, 40)
    C_TITLE  = (255, 255, 180)
    C_ACTION = (220, 220, 255)
    C_HINT   = (100, 100, 100)

    item = engine.player.inventory[engine.selected_item_index]
    actions = engine.selected_item_actions

    popup_w = 22
    popup_h = len(actions) + 4   # title + divider + actions + hint

    # Position left of the inventory panel, aligned with the item row
    popup_x = MAP_OFFSET_X + MAP_WIDTH - popup_w - 2
    popup_y = HEADER_HEIGHT + 4 + engine.selected_item_index

    # Clamp to screen bounds
    map_h = SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT
    if popup_y + popup_h > HEADER_HEIGHT + map_h:
        popup_y = max(HEADER_HEIGHT, HEADER_HEIGHT + map_h - popup_h)

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    # Item name — gram-based for nugs/kush, x{n} suffix for others
    qty  = getattr(item, "quantity", 1)
    name = build_inventory_display_name(
        item.item_id, getattr(item, "strain", None), qty
    )[:popup_w - 4]
    console.print(popup_x + 2, popup_y + 1, name, fg=C_TITLE, bg=BG)

    # Numbered actions
    for i, act in enumerate(actions):
        console.print(popup_x + 2, popup_y + 2 + i, f"{i + 1}) {act}", fg=C_ACTION, bg=BG)

    # Hint
    console.print(popup_x + 2, popup_y + popup_h - 1, "[Esc] Cancel", fg=C_HINT, bg=BG)


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
    if engine.neck is not None:
        occupied.append(("Neck", engine.neck))
    if engine.feet is not None:
        occupied.append(("Feet", engine.feet))
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
        if defn and defn.get("power_bonus"):
            bonus_parts.append(f"+{defn['power_bonus']}atk")
        if defn and defn.get("defense_bonus"):
            bonus_parts.append(f"+{defn['defense_bonus']}def")
        bonus = f" ({','.join(bonus_parts)})" if bonus_parts else ""
        col_start = panel_x + 4 + label_width + 2
        max_name = panel_w - 2 - (col_start - panel_x) - len(bonus)
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

    panel_w = 50
    panel_h = 22
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

    # Stat rows — show current value (with modifiers) and base value in parens
    ps = engine.player_stats
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
    derived = [
        ("Max HP",        f"{p.max_hp}",              f"Base 30 + CON*10"),
        ("Armor",         f"{p.armor}/{p.max_armor}", f"From equipment/effects, refills per floor"),
        ("Unarmed Bonus", f"{unarmed_str} dmg",       f"STR-5 (weapons scale differently)"),
        ("Crit Chance",   f"{ps.crit_chance:.0%}",    f"SS*3% per point, crits deal x2 dmg"),
        ("XP Bonus",      f"x{ps.xp_multiplier:.1f}", f"BSM: +10% per point above 5"),
        ("Drug Potency",  f"x{ps.drug_multiplier:.1f}", f"TOL: lower = stronger drug effects"),
    ]
    for i, (label, val, note) in enumerate(derived):
        row = div_row + 2 + i
        console.print(panel_x + 2,  row, label, fg=C_LABEL,  bg=BG)
        console.print(panel_x + 18, row, val,   fg=C_DERIVED, bg=BG)
        console.print(panel_x + 28, row, note[:panel_w - 30], fg=C_DESC, bg=BG)

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
    BG      = (40, 18, 18)
    C_TITLE = (255, 80, 80)
    C_TEXT  = (220, 220, 220)
    C_WARN  = (255, 180, 50)
    C_YES   = (255, 80, 80)
    C_NO    = (100, 220, 100)

    item = engine.player.inventory[engine.selected_item_index]
    qty  = getattr(item, "quantity", 1)
    name = build_inventory_display_name(
        item.item_id, getattr(item, "strain", None), qty
    )

    popup_w = 32
    popup_h = 9
    popup_x = (SCREEN_WIDTH - popup_w) // 2
    popup_y = HEADER_HEIGHT + (SCREEN_HEIGHT - HEADER_HEIGHT - UI_HEIGHT - popup_h) // 2

    _draw_panel(console, popup_x, popup_y, popup_w, popup_h, BG)

    title = "! DESTROY ITEM !"
    console.print(popup_x + (popup_w - len(title)) // 2, popup_y + 1,
                  title, fg=C_TITLE, bg=BG)

    name_disp = name[:popup_w - 4]
    console.print(popup_x + (popup_w - len(name_disp)) // 2, popup_y + 3,
                  name_disp, fg=C_TEXT, bg=BG)

    warn = "This cannot be undone!"
    console.print(popup_x + (popup_w - len(warn)) // 2, popup_y + 5,
                  warn, fg=C_WARN, bg=BG)

    yes_text = "[Y] Destroy"
    no_text  = "[N] Cancel"
    console.print(popup_x + 3,                        popup_y + 7, yes_text, fg=C_YES, bg=BG)
    console.print(popup_x + popup_w - 3 - len(no_text), popup_y + 7, no_text,  fg=C_NO,  bg=BG)


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
    cursor_bg  = (30, 60, 180) if is_visible else (160, 30, 30)

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
        spell_name = stype.replace("_", " ").title()
        count = engine.targeting_spell.get("count") or engine.targeting_spell.get("total_hits")
        line0 = f"Cast: {spell_name}" + (f" (x{count} left)" if count and count > 1 else "")
        if target_monster:
            line1 = f"Target: {target_monster.name} ({target_monster.hp}/{target_monster.max_hp} HP)"
            line1_color = C_ENEMY
        elif not is_visible:
            line1 = "Out of sight"
            line1_color = (255, 100, 100)
        else:
            line1 = "No enemy here"
            line1_color = C_EMPTY
        line2 = "[Enter] Cast   [Esc] Cancel"
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


def render_abilities_menu(console, engine):
    """Render the abilities overlay panel (toggled with A key)."""
    BG      = (18, 18, 28)
    C_TITLE = (255, 255, 180)
    C_HEAD  = (180, 180, 255)
    C_LABEL = (180, 180, 180)
    C_KEY   = (220, 220, 80)
    C_CHAR  = (100, 140, 255)
    C_CANT  = (100, 100, 100)
    C_DESC  = (120, 120, 160)
    C_DIV   = (80, 80, 120)
    C_HINT  = (100, 100, 100)
    C_AVAIL = (100, 220, 100)

    abilities = engine.player_abilities
    panel_w = 54
    # border(2) + title(1) + divider(1) + header(1) + divider(1) + rows + hint(1)
    n_rows  = max(1, len(abilities))
    panel_h = 7 + n_rows
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

    if not abilities:
        console.print(panel_x + 2, panel_y + 5,
                      "(no abilities — gain them from items or skills)",
                      fg=C_CANT, bg=BG)
    else:
        display_idx = 0
        for i, inst in enumerate(abilities):
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn is None:
                continue
            usable = inst.can_use()
            # Skip abilities with no charges
            if not usable:
                continue
            row = panel_y + 5 + display_idx
            name_color = defn.color

            # Key number (1-9)
            key_str = str(display_idx + 1) if display_idx < 9 else "-"
            console.print(panel_x + 2, row, f"{key_str})", fg=C_KEY, bg=BG)

            # Ability char glyph
            console.print(panel_x + 5, row, defn.char, fg=defn.color, bg=BG)

            # Name
            console.print(panel_x + 7, row, defn.name[:12], fg=name_color, bg=BG)

            # Charges
            charge_str = inst.charge_display(defn)
            console.print(panel_x + 20, row, charge_str[:11], fg=C_AVAIL, bg=BG)

            display_idx += 1

    # Hint
    hint = "[1-9] Use  [A/Esc] Close"
    console.print(panel_x + (panel_w - len(hint)) // 2,
                  panel_y + panel_h - 2, hint, fg=C_HINT, bg=BG)


def render_ui(console, engine):
    """Render the bottom panel: messages on the left, stats on the right."""
    BG       = (28, 28, 38)
    C_SEP    = (120, 120, 160)
    C_BORDER = (100, 100, 160)
    C_HINT   = (80, 80, 110)
    C_TURN   = (160, 160, 180)
    C_TITLE  = (255, 255, 180)
    C_LABEL  = (180, 180, 180)
    C_VALUE  = (255, 255, 255)
    C_BASE   = (110, 110, 110)   # muted gray for base value in parens
    C_BUFF   = (100, 220, 255)
    C_DEBUFF = (255, 100, 100)

    ui_y    = SCREEN_HEIGHT - UI_HEIGHT
    stats_x = MAP_OFFSET_X + MAP_WIDTH   # col 90 — aligns with inventory panel above

    # Fill background
    for x in range(SCREEN_WIDTH):
        for y in range(UI_HEIGHT):
            console.print(x, ui_y + y, " ", bg=BG)

    # Top separator — full width with junction char at stats column
    for x in range(SCREEN_WIDTH):
        console.print(x, ui_y, "─", fg=C_SEP, bg=BG)
    console.print(stats_x, ui_y, "┬", fg=C_SEP, bg=BG)

    # Vertical border down the left edge of the stats area
    for dy in range(1, UI_HEIGHT):
        console.print(stats_x, ui_y + dy, "│", fg=C_BORDER, bg=BG)

    # Log hint (left of separator)
    hint_text = "[Shift+L] Log"
    console.print(2, ui_y, hint_text, fg=C_HINT, bg=BG)

    # Turn counter just left of the stats column
    turn_text = f"Turn: {engine.turn}"
    console.print(stats_x - len(turn_text) - 2, ui_y, turn_text, fg=C_TURN, bg=BG)

    # "STATS" header centred in the right section, overwriting separator dashes
    stats_title = "STATS"
    console.print(
        stats_x + (PANEL_WIDTH - len(stats_title)) // 2,
        ui_y, stats_title, fg=C_TITLE, bg=BG,
    )

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
    for i, (label, current, attr) in enumerate(stat_rows):
        sy    = ui_y + 1 + i
        base  = ps._base[attr]
        # Color based on whether current differs from base (includes rings + temporary effects)
        vc    = C_DEBUFF if current < base else (C_BUFF if current > base else C_VALUE)

        val_str  = str(current)
        base_str = f"({base})"

        # label left-aligned in 16 chars, value and base right-aligned at end
        console.print(stats_x + 2, sy, f"{label:<16}", fg=C_LABEL,  bg=BG)
        # Value and base together on the right (value + space + base)
        value_and_base = f"{val_str} {base_str}"
        console.print(stats_x + PANEL_WIDTH - len(value_and_base) - 1, sy, value_and_base, fg=vc,     bg=BG)
        # Recolor just the base portion
        console.print(stats_x + PANEL_WIDTH - len(base_str) - 1, sy, base_str,               fg=C_BASE, bg=BG)

    # Message history — truncated to stay left of the stats border
    msg_width = stats_x - 3   # cols 2 … stats_x-2
    all_msgs  = list(engine.messages)
    visible   = UI_HEIGHT - 1
    shown     = all_msgs[-visible:] if len(all_msgs) > visible else all_msgs
    for i, msg in enumerate(shown):
        msg_y = ui_y + 1 + (visible - len(shown)) + i
        _render_msg(console, 2, msg_y, msg, msg_width, BG)

    # Game over overlay
    if engine.game_over:
        game_over_text = "GAME OVER - Press Q to quit"
        console.print(
            SCREEN_WIDTH // 2 - len(game_over_text) // 2,
            ui_y + UI_HEIGHT // 2,
            game_over_text,
            fg=(255, 0, 0), bg=BG,
        )
