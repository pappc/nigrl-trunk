"""
Save/load system for NIGRL.

Serializes full game state to JSON for portable save files.
"""

import json
import os
import base64
import numpy as np

SAVE_DIR = os.path.join(os.path.dirname(__file__), "saves")
SAVE_PATH = os.path.join(SAVE_DIR, "save.json")
SAVE_VERSION = 1


# ── Entity serialization ────────────────────────────────────────────────

# Fields to skip on Entity (class-level or non-serializable)
_ENTITY_SKIP = {"stats"}  # player.stats is a ref to engine.player_stats

# Fields that hold Entity references (serialize as instance_id)
_ENTITY_REF_FIELDS = {"aggro_target", "leader"}
_ENTITY_REF_LIST_FIELDS = {"spawned_children"}


def _serialize_effect(eff):
    """Serialize a status effect instance to a dict."""
    d = {}
    for k, v in eff.__dict__.items():
        if k.startswith("_"):
            # Include private fields that carry state (e.g. _speed_granted)
            d[k] = v
        else:
            d[k] = v
    d["__effect_id"] = eff.id
    return d


def _deserialize_effect(data):
    """Reconstruct an Effect instance from saved dict."""
    from effects import EFFECT_REGISTRY
    eid = data.pop("__effect_id")
    cls = EFFECT_REGISTRY.get(eid)
    if cls is None:
        return None
    # Construct with minimal args, then overwrite state
    try:
        eff = cls.__new__(cls)
        Effect_base = cls.__mro__[-2] if len(cls.__mro__) > 2 else cls
        # Set all saved fields directly
        for k, v in data.items():
            setattr(eff, k, v)
        return eff
    except Exception:
        return None


def _serialize_entity(ent):
    """Serialize an Entity to a JSON-safe dict."""
    d = {}
    for k, v in ent.__dict__.items():
        if k in _ENTITY_SKIP:
            continue
        if k == "status_effects":
            d[k] = [_serialize_effect(e) for e in v]
        elif k == "inventory":
            d[k] = [_serialize_entity(item) for item in v]
        elif k in _ENTITY_REF_FIELDS:
            d[k] = v.instance_id if v is not None and hasattr(v, "instance_id") else None
        elif k in _ENTITY_REF_LIST_FIELDS:
            d[k] = [c.instance_id for c in v if hasattr(c, "instance_id")]
        elif k == "ai_state":
            # AIState enum -> serialize as string
            d[k] = v.value if v is not None else None
        elif isinstance(v, (int, float, str, bool, type(None))):
            d[k] = v
        elif isinstance(v, (list, tuple)):
            d[k] = _make_json_safe(list(v))
        elif isinstance(v, dict):
            d[k] = _make_json_safe(dict(v))
        elif isinstance(v, (set, frozenset)):
            d[k] = _make_json_safe(list(v))
        else:
            try:
                json.dumps(v)
                d[k] = v
            except (TypeError, ValueError):
                d[k] = str(v)
    return d


def _make_json_safe(obj):
    """Recursively convert non-JSON-safe types (frozenset, set, tuple) to lists/strings."""
    if isinstance(obj, (set, frozenset)):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, tuple):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, list):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    return str(obj)


def _deserialize_entity(data, entity_index):
    """Reconstruct an Entity from saved dict. Registers in entity_index for ref resolution."""
    from entity import Entity
    # Create entity with minimal required args
    ent = Entity.__new__(Entity)
    for k, v in data.items():
        if k == "status_effects":
            ent.status_effects = []
            for edata in v:
                eff = _deserialize_effect(dict(edata))
                if eff is not None:
                    ent.status_effects.append(eff)
        elif k == "inventory":
            ent.inventory = [_deserialize_entity(item_data, entity_index) for item_data in v]
        elif k == "ai_state":
            if v is not None:
                from ai import AIState
                try:
                    ent.ai_state = AIState(v)
                except (ValueError, KeyError):
                    ent.ai_state = None
            else:
                ent.ai_state = None
        elif k in _ENTITY_REF_FIELDS:
            # Store raw instance_id; resolve later
            setattr(ent, f"_save_ref_{k}", v)
        elif k in _ENTITY_REF_LIST_FIELDS:
            setattr(ent, f"_save_ref_{k}", v)
        elif k == "color":
            setattr(ent, k, tuple(v) if isinstance(v, list) else v)
        elif k == "spawn_room_tiles":
            # Restore frozenset of tuples from list of lists
            if isinstance(v, list):
                setattr(ent, k, frozenset(tuple(t) for t in v))
            else:
                setattr(ent, k, v)
        elif k == "death_drop_quantity":
            # Restore tuple from list
            if isinstance(v, list):
                setattr(ent, k, tuple(v))
            else:
                setattr(ent, k, v)
        else:
            setattr(ent, k, v)

    # Register for cross-reference resolution
    iid = getattr(ent, "instance_id", None)
    if iid:
        entity_index[iid] = ent
    return ent


def _resolve_entity_refs(entity_index):
    """Resolve instance_id references to actual Entity objects."""
    for ent in entity_index.values():
        for field in _ENTITY_REF_FIELDS:
            ref_key = f"_save_ref_{field}"
            if hasattr(ent, ref_key):
                ref_id = getattr(ent, ref_key)
                setattr(ent, field, entity_index.get(ref_id))
                delattr(ent, ref_key)
        for field in _ENTITY_REF_LIST_FIELDS:
            ref_key = f"_save_ref_{field}"
            if hasattr(ent, ref_key):
                ref_ids = getattr(ent, ref_key)
                setattr(ent, field, [entity_index[rid] for rid in ref_ids if rid in entity_index])
                delattr(ent, ref_key)


# ── Room serialization ──────────────────────────────────────────────────

def _serialize_room(room):
    """Serialize a Room subclass to a dict."""
    from dungeon import (RectRoom, LRoom, TRoom, CrossRoom, CircleRoom,
                         URoom, DiamondRoom, CavernRoom, HallRoom, OctRoom, PillarRoom)
    d = {"x1": room.x1, "y1": room.y1, "x2": room.x2, "y2": room.y2}
    cls = type(room)
    d["__type"] = cls.__name__
    # Store subclass-specific construction params
    if isinstance(room, CrossRoom):
        d["cx"] = room.cx
        d["cy"] = room.cy
        d["size"] = room.size
    elif isinstance(room, CircleRoom):
        d["cx"] = room.cx
        d["cy"] = room.cy
        d["radius"] = room.radius
    elif isinstance(room, DiamondRoom):
        d["cx"] = room.cx
        d["cy"] = room.cy
        d["radius"] = room.radius
    elif isinstance(room, CavernRoom):
        d["cx"] = room.cx
        d["cy"] = room.cy
        d["size"] = room.size
    elif isinstance(room, OctRoom):
        d["clip"] = room.clip
    elif isinstance(room, LRoom):
        d["rects"] = room.rects
    elif isinstance(room, URoom):
        d["rects"] = room.rects
    elif isinstance(room, TRoom):
        d["bar"] = list(room.bar)
        d["stem"] = list(room.stem)
    return d


def _deserialize_room(data):
    """Reconstruct a Room from saved dict. Tiles are already saved separately."""
    from dungeon import (Room, RectRoom, LRoom, TRoom, CrossRoom, CircleRoom,
                         URoom, DiamondRoom, CavernRoom, HallRoom, OctRoom, PillarRoom)
    rtype = data["__type"]
    # Create a base Room shell with bounding box — tiles are saved in dungeon.tiles
    room = Room.__new__(Room)
    room.x1 = data["x1"]
    room.y1 = data["y1"]
    room.x2 = data["x2"]
    room.y2 = data["y2"]

    # Restore subclass type and extra fields
    cls_map = {
        "RectRoom": RectRoom, "LRoom": LRoom, "TRoom": TRoom,
        "CrossRoom": CrossRoom, "CircleRoom": CircleRoom, "URoom": URoom,
        "DiamondRoom": DiamondRoom, "CavernRoom": CavernRoom,
        "HallRoom": HallRoom, "OctRoom": OctRoom, "PillarRoom": PillarRoom,
        "Room": Room,
    }
    cls = cls_map.get(rtype, Room)
    room.__class__ = cls

    # Restore subclass-specific fields
    for k in ("cx", "cy", "size", "radius", "clip", "rects", "bar", "stem"):
        if k in data:
            val = data[k]
            if k in ("bar", "stem") and isinstance(val, list):
                val = tuple(val)
            if k == "rects" and isinstance(val, list):
                val = [tuple(r) if isinstance(r, list) else r for r in val]
            setattr(room, k, val)
    return room


# ── Dungeon serialization ───────────────────────────────────────────────

def _serialize_dungeon(dungeon):
    """Serialize a Dungeon to a JSON-safe dict."""
    d = {
        "width": dungeon.width,
        "height": dungeon.height,
        "zone": dungeon.zone,
        "floor_event": dungeon.floor_event,
        "tiles": dungeon.tiles,
        "rooms": [_serialize_room(r) for r in dungeon.rooms],
        "entities": [_serialize_entity(e) for e in dungeon.entities],
        "explored": base64.b64encode(dungeon.explored.tobytes()).decode("ascii"),
        "first_kill_happened": dungeon.first_kill_happened,
        "female_kill_happened": dungeon.female_kill_happened,
        "rooms_with_combat": list(dungeon.rooms_with_combat),
        "room_tile_map": {f"{x},{y}": idx for (x, y), idx in dungeon.room_tile_map.items()},
        "spray_paint": {f"{x},{y}": stype for (x, y), stype in dungeon.spray_paint.items()},
        "grease_tiles": {f"{x},{y}": turns for (x, y), turns in dungeon.grease_tiles.items()},
    }
    return d


def _deserialize_dungeon(data, entity_index):
    """Reconstruct a Dungeon from saved dict without running generation."""
    from dungeon import Dungeon
    d = Dungeon.__new__(Dungeon)
    d.width = data["width"]
    d.height = data["height"]
    d.zone = data["zone"]
    d.floor_event = data.get("floor_event")
    d.tiles = data["tiles"]
    d.rooms = [_deserialize_room(r) for r in data["rooms"]]
    d.entities = [_deserialize_entity(e, entity_index) for e in data["entities"]]
    d.explored = np.frombuffer(
        base64.b64decode(data["explored"]), dtype=bool
    ).reshape((d.height, d.width)).copy()
    d.visible = np.zeros((d.height, d.width), dtype=bool)
    d.newly_revealed_landmarks = []
    d.first_kill_happened = data.get("first_kill_happened", False)
    d.female_kill_happened = data.get("female_kill_happened", False)
    d.rooms_with_combat = set(data.get("rooms_with_combat", []))
    d.room_tile_map = {
        tuple(int(c) for c in k.split(",")): v
        for k, v in data.get("room_tile_map", {}).items()
    }
    d.spray_paint = {
        tuple(int(c) for c in k.split(",")): v
        for k, v in data.get("spray_paint", {}).items()
    }
    d.grease_tiles = {
        tuple(int(c) for c in k.split(",")): v
        for k, v in data.get("grease_tiles", {}).items()
    }
    return d


# ── PlayerStats serialization ───────────────────────────────────────────

def _serialize_stats(stats):
    """Serialize PlayerStats to a dict."""
    d = {}
    for k, v in stats.__dict__.items():
        if k.startswith("_on_"):  # skip callbacks
            continue
        if isinstance(v, (int, float, str, bool, type(None))):
            d[k] = v
        elif isinstance(v, dict):
            d[k] = dict(v)
        elif isinstance(v, list):
            d[k] = list(v)
    return d


def _deserialize_stats(data):
    """Reconstruct PlayerStats from saved dict."""
    from stats import PlayerStats
    stats = PlayerStats.__new__(PlayerStats)
    for k, v in data.items():
        setattr(stats, k, v)
    # Restore callbacks list and player back-ref
    stats._on_stat_increase_callbacks = []
    stats._player = None  # set by caller after player is restored
    return stats


# ── Skills serialization ────────────────────────────────────────────────

def _serialize_skills(skills):
    """Serialize Skills to a dict."""
    d = {"skill_points": skills.skill_points, "skills": {}}
    for name, skill in skills.skills.items():
        d["skills"][name] = {
            "level": skill.level,
            "real_exp": skill.real_exp,
            "potential_exp": skill.potential_exp,
            "skill_mod": skill.skill_mod,
        }
    return d


def _deserialize_skills(data):
    """Reconstruct Skills from saved dict."""
    from skills import Skills, Skill
    s = Skills()
    s.skill_points = data.get("skill_points", 0.0)
    for name, sdata in data.get("skills", {}).items():
        if name in s.skills:
            sk = s.skills[name]
            sk.level = sdata.get("level", 0)
            sk.real_exp = sdata.get("real_exp", 0.0)
            sk.potential_exp = sdata.get("potential_exp", 0.0)
            sk.skill_mod = sdata.get("skill_mod", 1.0)
    return s


# ── Abilities serialization ─────────────────────────────────────────────

def _serialize_abilities(abilities):
    """Serialize list of AbilityInstance to list of dicts."""
    return [
        {
            "ability_id": a.ability_id,
            "charges_remaining": a.charges_remaining,
            "floor_charges_remaining": a.floor_charges_remaining,
        }
        for a in abilities
    ]


def _deserialize_abilities(data):
    """Reconstruct AbilityInstance list from saved dicts."""
    from abilities import AbilityInstance, ABILITY_REGISTRY
    result = []
    for ad in data:
        aid = ad["ability_id"]
        defn = ABILITY_REGISTRY.get(aid)
        if defn is None:
            continue
        inst = AbilityInstance(aid, defn)
        inst.charges_remaining = ad.get("charges_remaining", -1)
        inst.floor_charges_remaining = ad.get("floor_charges_remaining", -1)
        result.append(inst)
    return result


# ── Engine serialization ────────────────────────────────────────────────

# Engine fields to skip (non-serializable or reconstructed)
_ENGINE_SKIP = {
    "render_callback", "tcod_context", "sdl_overlay", "event_bus",
    "_gameplay_handlers", "_menu_handlers",
    # Complex objects serialized separately
    "player", "player_stats", "skills", "dungeon", "dungeons",
    "player_abilities",
    # Transient state
    "entity_target_list", "look_info_lines",
    "dev_item_list", "dev_item_filtered",
    # Entity refs (resolved separately)
    "vending_machine", "last_targeted_enemy",
    "_sublevel_return_dungeon", "_midas_brew_item",
}


def save_game(engine, path=None):
    """Serialize the full game state to a JSON file."""
    if path is None:
        path = SAVE_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = {"__save_version": SAVE_VERSION}

    # Engine scalar fields
    engine_data = {}
    for k, v in engine.__dict__.items():
        if k in _ENGINE_SKIP:
            continue
        if k == "messages":
            engine_data[k] = [
                _serialize_message(m) for m in v
            ]
            continue
        if k == "menu_state":
            engine_data[k] = v.value if hasattr(v, "value") else str(v)
            continue
        if k == "equipment":
            engine_data[k] = {
                slot: _serialize_entity(ent) if ent else None
                for slot, ent in v.items()
            }
            continue
        if k == "rings":
            engine_data[k] = [_serialize_entity(r) if r else None for r in v]
            continue
        if k in ("neck", "feet", "hat"):
            engine_data[k] = _serialize_entity(v) if v else None
            continue
        if k == "picked_up_items":
            engine_data[k] = list(v)
            continue
        if k == "special_rooms_spawned":
            engine_data[k] = list(v)
            continue
        if k == "visited_rooms":
            engine_data[k] = {str(floor): list(rooms) for floor, rooms in v.items()}
            continue
        if k == "floor_events":
            engine_data[k] = {str(floor): ev for floor, ev in v.items()}
            continue
        if k == "hotbar":
            engine_data[k] = list(v)
            continue
        if isinstance(v, (int, float, str, bool, type(None))):
            engine_data[k] = v
        elif isinstance(v, (list, tuple)):
            engine_data[k] = list(v)
        elif isinstance(v, dict):
            # Convert any non-string keys
            engine_data[k] = {str(kk): vv for kk, vv in v.items()}
        elif isinstance(v, set):
            engine_data[k] = list(v)

    data["engine"] = engine_data

    # Player
    data["player"] = _serialize_entity(engine.player)

    # Player stats
    data["player_stats"] = _serialize_stats(engine.player_stats)

    # Skills
    data["skills"] = _serialize_skills(engine.skills)

    # Abilities
    data["abilities"] = _serialize_abilities(engine.player_abilities)

    # All dungeons
    data["dungeons"] = {
        str(floor): _serialize_dungeon(dun)
        for floor, dun in engine.dungeons.items()
    }
    data["current_floor"] = engine.current_floor

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))

    return path


def _serialize_message(msg):
    """Serialize a message (which can be a string or list of (text, color) tuples)."""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, (list, tuple)):
        return [{"text": t, "color": list(c)} if isinstance(t, str) and isinstance(c, (tuple, list)) else str(t)
                for t, *rest in ([m] if isinstance(m, str) else [m] for m in msg)
                for t, c in [(t, rest[0]) if rest else (t, (255, 255, 255))]]
    return str(msg)


def _serialize_message(msg):
    """Serialize a message entry from engine.messages deque."""
    if isinstance(msg, str):
        return {"type": "str", "text": msg}
    if isinstance(msg, (list, tuple)):
        parts = []
        for part in msg:
            if isinstance(part, (list, tuple)) and len(part) == 2:
                text, color = part
                parts.append({"text": str(text), "color": list(color)})
            else:
                parts.append({"text": str(part), "color": [255, 255, 255]})
        return {"type": "rich", "parts": parts}
    return {"type": "str", "text": str(msg)}


def _deserialize_message(data):
    """Reconstruct a message from saved data."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        if data.get("type") == "str":
            return data["text"]
        if data.get("type") == "rich":
            return [(p["text"], tuple(p["color"])) for p in data["parts"]]
    return str(data)


def load_game(path=None):
    """Load a saved game and return a reconstructed GameEngine."""
    if path is None:
        path = SAVE_PATH

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    from engine import GameEngine
    from entity import Entity
    from collections import deque
    from config import LOG_HISTORY_SIZE, EQUIPMENT_SLOTS, RING_SLOTS, ENERGY_THRESHOLD
    from menu_state import MenuState
    from event_bus import EventBus

    entity_index = {}  # instance_id -> Entity

    # Create bare engine shell
    engine = GameEngine.__new__(GameEngine)

    # Reconstruct non-serializable infrastructure
    engine.render_callback = None
    engine.tcod_context = None
    engine.sdl_overlay = None
    engine.event_bus = EventBus()
    engine._register_events()
    Entity._on_damage_callback = engine._on_entity_damaged
    Entity._on_heal_callback = engine._on_entity_healed

    # Restore engine scalar fields
    edata = data["engine"]
    for k, v in edata.items():
        if k == "messages":
            engine.messages = deque(
                [_deserialize_message(m) for m in v],
                maxlen=LOG_HISTORY_SIZE,
            )
            continue
        if k == "menu_state":
            try:
                engine.menu_state = MenuState(v)
            except (ValueError, KeyError):
                engine.menu_state = MenuState.NONE
            continue
        if k == "equipment":
            engine.equipment = {
                slot: _deserialize_entity(ent_data, entity_index) if ent_data else None
                for slot, ent_data in v.items()
            }
            continue
        if k == "rings":
            engine.rings = [
                _deserialize_entity(r, entity_index) if r else None
                for r in v
            ]
            # Pad if save has fewer ring slots
            while len(engine.rings) < RING_SLOTS:
                engine.rings.append(None)
            continue
        if k in ("neck", "feet", "hat"):
            setattr(engine, k, _deserialize_entity(v, entity_index) if v else None)
            continue
        if k == "picked_up_items":
            engine.picked_up_items = set(v)
            continue
        if k == "special_rooms_spawned":
            engine.special_rooms_spawned = set(v)
            continue
        if k == "visited_rooms":
            engine.visited_rooms = {int(floor): set(rooms) for floor, rooms in v.items()}
            continue
        if k == "floor_events":
            engine.floor_events = {int(floor): ev for floor, ev in v.items()}
            continue
        if k == "ability_cooldowns":
            engine.ability_cooldowns = dict(v)
            continue
        setattr(engine, k, v)

    # Restore player
    engine.player = _deserialize_entity(data["player"], entity_index)

    # Restore player stats
    engine.player_stats = _deserialize_stats(data["player_stats"])
    engine.player_stats._player = engine.player
    engine.player.stats = engine.player_stats

    # Restore skills
    engine.skills = _deserialize_skills(data["skills"])

    # Restore abilities
    engine.player_abilities = _deserialize_abilities(data["abilities"])

    # Restore dungeons
    engine.dungeons = {}
    for floor_str, dun_data in data["dungeons"].items():
        floor_num = int(floor_str)
        engine.dungeons[floor_num] = _deserialize_dungeon(dun_data, entity_index)

    engine.current_floor = data["current_floor"]
    engine.dungeon = engine.dungeons.get(engine.current_floor)

    # Replace the duplicate player entity in dungeon.entities with engine.player
    if engine.dungeon:
        for i, ent in enumerate(engine.dungeon.entities):
            if getattr(ent, "entity_type", None) == "player":
                engine.dungeon.entities[i] = engine.player
                break

    # Resolve all entity cross-references
    _resolve_entity_refs(entity_index)

    # Rebuild transient state defaults
    engine.entity_target_list = []
    engine.look_info_lines = []
    engine.dev_item_list = []
    engine.dev_item_filtered = []
    engine.vending_machine = None
    engine.last_targeted_enemy = None
    engine._sublevel_return_dungeon = None
    engine._midas_brew_item = None

    # Rebuild action dispatch tables
    engine._gameplay_handlers = {
        "move": engine._action_move,
        "wait": engine._action_wait,
        "toggle_skills": engine._action_toggle_skills,
        "open_char_sheet": engine._action_toggle_char_sheet,
        "open_equipment": engine._action_open_equipment,
        "open_log": engine._action_open_log,
        "open_bestiary": engine._action_open_bestiary,
        "open_perks_menu": engine._action_open_perks_menu,
        "toggle_abilities": engine._action_toggle_abilities,
        "select_item": engine._action_select_item,
        "select_action": engine._action_hotbar_use,
        "close_menu": engine._action_close_menu,
        "quit": engine._action_quit,
        "descend_stairs": engine._action_descend_stairs,
        "start_entity_targeting": engine._action_start_entity_targeting,
        "fire_gun": engine._action_fire_gun,
        "reload_gun": engine._action_reload_gun,
        "swap_primary_gun": engine._action_swap_primary_gun,
        "open_dev_menu": engine._action_open_dev_menu,
        "autoexplore": engine._action_autoexplore,
        "look": engine._action_look,
    }
    engine._menu_handlers = {
        MenuState.EQUIPMENT: engine._handle_equipment_input,
        MenuState.ITEM_MENU: engine._handle_item_menu_input,
        MenuState.COMBINE_SELECT: engine._handle_combine_input,
        MenuState.LOG: engine._handle_log_input,
        MenuState.DESTROY_CONFIRM: engine._handle_destroy_confirm_input,
        MenuState.EXAMINE: engine._handle_examine_input,
        MenuState.TARGETING: engine._handle_targeting_input,
        MenuState.ABILITIES: engine._handle_abilities_menu_input,
        MenuState.RING_REPLACE: engine._handle_ring_replace_input,
        MenuState.ENTITY_TARGETING: engine._handle_entity_targeting_input,
        MenuState.PERKS: engine._handle_perks_input,
        MenuState.DEV_MENU: engine._handle_dev_menu_input,
        MenuState.DEV_ITEM_SELECT: engine._handle_dev_item_select_input,
        MenuState.DEV_FLOOR_SELECT: engine._handle_dev_floor_select_input,
        MenuState.DEV_SKILL_SELECT: engine._handle_dev_skill_select_input,
        MenuState.ADJACENT_TILE_TARGETING: engine._handle_adjacent_tile_targeting_input,
        MenuState.DEEP_FRYER: engine._handle_deep_fryer_input,
        MenuState.GUN_TARGETING: engine._handle_gun_targeting_input,
        MenuState.LOOK_TARGETING: engine._handle_look_targeting,
        MenuState.LOOK_INFO: engine._handle_look_info,
        MenuState.SETTINGS: engine._handle_settings_input,
        MenuState.VENDING_MACHINE: engine._handle_vending_machine_input,
        MenuState.MIDAS_BREW: engine._handle_midas_brew_input,
        MenuState.SHOP_ITEM: engine._handle_shop_item_input,
    }

    # Recompute FOV
    if engine.dungeon:
        fov_r = getattr(engine, "fov_radius", 8)
        engine.dungeon.compute_fov(engine.player.x, engine.player.y, fov_r)

    # Ensure total_floors is current
    from config import get_total_floors
    engine.total_floors = get_total_floors()

    return engine


def has_save(path=None):
    """Check if a save file exists."""
    if path is None:
        path = SAVE_PATH
    return os.path.isfile(path)


def export_save_to_clipboard():
    """Read save.json, base64-encode it, and copy to clipboard. Returns True on success."""
    if not has_save():
        return False
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = f.read()
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        # Copy to clipboard via Windows API
        import ctypes
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        # Set proper 64-bit arg/return types
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p]
        user32.OpenClipboard(0)
        user32.EmptyClipboard()
        # Allocate global memory for the string
        data = encoded.encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
        ptr = kernel32.GlobalLock(h)
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(13, h)  # CF_UNICODETEXT
        user32.CloseClipboard()
        return True
    except Exception:
        return False


def import_save_from_clipboard():
    """Read base64 from clipboard, decode to JSON, validate, and write to save.json.
    Returns (True, msg) on success, (False, msg) on failure."""
    try:
        import ctypes
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_wchar_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard(0)
        handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not handle:
            user32.CloseClipboard()
            return (False, "Clipboard is empty.")
        raw = kernel32.GlobalLock(handle)
        text = str(raw).strip() if raw else ""
        kernel32.GlobalUnlock(handle)
        user32.CloseClipboard()

        if not text:
            return (False, "Clipboard is empty.")

        # Decode base64
        try:
            decoded = base64.b64decode(text).decode("utf-8")
        except Exception:
            return (False, "Invalid save data (not valid base64).")

        # Validate JSON and save version
        try:
            data = json.loads(decoded)
        except json.JSONDecodeError:
            return (False, "Invalid save data (not valid JSON).")

        if not isinstance(data, dict) or "__save_version" not in data:
            return (False, "Invalid save data (missing version).")

        # Write to save path
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            f.write(decoded)
        return (True, "Save imported successfully!")
    except Exception as e:
        return (False, f"Import failed: {e}")
