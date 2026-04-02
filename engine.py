"""
Game engine and turn management.
"""

import math
import random
import time
from collections import deque
import numpy as np


class MessageLog:
    """Deque-like message log that auto-stamps each message with the current turn."""

    def __init__(self, engine, maxlen):
        self._engine = engine
        self._data = deque(maxlen=maxlen)

    def append(self, msg):
        self._data.append((self._engine.turn, msg))

    def __iter__(self):
        """Yield just the message content (without turn stamp)."""
        return (msg for _turn, msg in self._data)

    def stamped(self):
        """Yield (turn, msg) tuples — used by render and save."""
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def __getitem__(self, index):
        _turn, msg = self._data[index]
        return msg

    def __bool__(self):
        return bool(self._data)

    def clear(self):
        self._data.clear()
import tcod.path

from config import (
    BASE_HP, BASE_POWER, BASE_DEFENSE,
    DUNGEON_WIDTH, DUNGEON_HEIGHT, MAX_MESSAGES, LOG_HISTORY_SIZE,
    MIN_DAMAGE, UNARMED_STR_BASE, EQUIPMENT_SLOTS, RING_SLOTS, FOV_RADIUS,
    ENERGY_THRESHOLD, PLAYER_BASE_SPEED, ZONE_SMARTSNESS_MULT, ZONE_DAMAGE_MULT,
    DEV_MODE,
    ZONE_ORDER, get_total_floors, get_zone_for_floor, get_zone_total_floors,
)
from dungeon import Dungeon
from entity import Entity
from skills import Skills, SKILL_NAMES
from stats import PlayerStats
from items import get_item_def, find_recipe, get_actions, create_item_entity, get_craft_result_strain, is_stackable, build_inventory_display_name, get_strain_effect, get_random_ring_by_tags, PREFIX_TOOL_ITEMS, get_item_value, calc_tolerance_rolls
from loot import pick_random_consumable, pick_strain
from ai import do_ai_turn, prepare_ai_tick
from event_bus import EventBus
import effects
from foods import get_food_def, FOOD_DEFS, get_food_prefix_def
from menu_state import MenuState
from abilities import AbilityDef, AbilityInstance, ChargeType, TargetType, ABILITY_REGISTRY
import xp_progression
import item_effects
import combat
import spells
import gun_system
import inventory_mgr

# Spider enemy types — immune to webs
_SPIDER_ENEMY_TYPES = frozenset({
    "pipe_spider", "sac_spider", "wolf_spider", "black_widow",
})

# Colors for segmented log messages
_C_MSG_NEUTRAL = (200, 200, 100)   # default yellow
_C_MSG_PICKUP  = (255, 200, 100)   # orange  (matches get_message_color "picked up")
_C_MSG_USE     = (100, 255, 100)   # green   (matches get_message_color "used")

# Inventory sort order: tool → equipment → material → consumable
_INV_CATEGORY_ORDER = {
    "tool": 0,
    "equipment": 1,
    "material": 2,
    "consumable": 3,
    "ammo": 4,
}

_INV_SUBCATEGORY_ORDER = {
    "weapon": 0,
    "ring": 1,
    "gun": 2,
}

_WASTE_MESSAGES = [
    "The joint bounces off the floor and smolders away. You just wasted primo weed.",
    "Nothing there. Great job, you killed perfectly good chronic.",
    "You hucked a whole joint at an empty tile. Your dealer disowns you.",
    "The joint lands in the corner and burns up. What a tragic loss.",
    "Wasted. You threw good herb at absolutely nothing. Smooth move.",
    "That was GOOD weed, man. What are you doing?",
]


def _player_toxicity_multiplier(toxicity: int) -> float:
    """Damage-taken 'more' multiplier for the player.
    100 tox = 2x, 1000 tox ≈ 5x. Formula: 1 + (tox/100)^0.6"""
    if toxicity <= 0:
        return 1.0
    return 1.0 + (toxicity / 100) ** 0.6


def _monster_toxicity_multiplier(toxicity: int) -> float:
    """Damage-taken 'more' multiplier for monsters (more sensitive than player).
    50 tox = 2x, 500 tox ≈ 5x. Formula: 1 + (tox/50)^0.6"""
    if toxicity <= 0:
        return 1.0
    return 1.0 + (toxicity / 50) ** 0.6


_CHANNEL_DISPLAY_NAMES = {
    "ray_of_frost": "Ray of Frost",
    "discharge": "Discharge",
}

_CHANNEL_COLORS = {
    "ray_of_frost": (100, 200, 255),   # ice blue
    "discharge": (180, 160, 255),      # electric purple
}


def _curse_spread_path(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Build a tile path from (x0,y0) to (x1,y1) via linear interpolation."""
    dx = x1 - x0
    dy = y1 - y0
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return [(x1, y1)]
    tiles = []
    for step in range(1, steps + 1):
        x = round(x0 + dx * step / steps)
        y = round(y0 + dy * step / steps)
        tiles.append((x, y))
    return tiles


class GameEngine:
    """Main game logic and state management."""

    # Display mode presets
    DISPLAY_MODES = [
        {"label": "Windowed",              "flags": "windowed",   "width": 1920, "height": 1088},
        {"label": "Borderless 1080p",      "flags": "borderless", "width": 1920, "height": 1080},
        {"label": "Borderless 1440p",      "flags": "borderless", "width": 2560, "height": 1440},
    ]

    def __init__(self, seed=None):
        # --- Seed (for reproducible runs) ---
        if seed is None:
            # Generate a random 10-char alphanumeric seed for display
            _chars = "1346789ABCDEFGHIJKLMNPQRTUVWXY"
            seed = "".join(random.choice(_chars) for _ in range(10))
        random.seed(seed)
        self.seed = seed

        # Reset cached per-game state in loot generation
        from loot import generate_floor_loot
        if hasattr(generate_floor_loot, '_guaranteed_weapon_floor'):
            del generate_floor_loot._guaranteed_weapon_floor

        # --- Render callback (set by main loop for mid-turn rendering) ---
        self.render_callback = None
        self.tcod_context = None  # set by main loop

        # --- Settings menu state ---
        self.settings_cursor: int = 0
        self.current_display_mode: int = 0  # index into DISPLAY_MODES

        # --- Event bus ---
        self.event_bus = EventBus()
        self._register_events()

        # --- Floating damage/heal numbers (SDL overlay, set by nigrl.py) ---
        self.sdl_overlay = None
        Entity._on_damage_callback = self._on_entity_damaged
        Entity._on_heal_callback = self._on_entity_healed

        # --- Floor management ---
        self.current_floor = 0
        self.total_floors = get_total_floors()
        self.dungeons: dict[int, Dungeon] = {}
        self.special_rooms_spawned: set[str] = set()  # tracks once-per-game special rooms

        # --- Floor events (random modifiers for specific floors) ---
        # Maps global_floor -> event_id. Rolled once at game start.
        self.floor_events: dict[int, str] = {}
        self._roll_floor_events()

        # --- Dungeon ---
        self.dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, floor_num=0)
        self.dungeons[0] = self.dungeon

        # --- Player ---
        self.player = Entity(
            x=0, y=0,
            char="@",
            color=(255, 255, 255),
            name="player",
            entity_type="player",
            blocks_movement=True,
            hp=BASE_HP,
            power=BASE_POWER,
            defense=BASE_DEFENSE,
        )

        self.player_stats = PlayerStats()
        self.player_stats._player = self.player        # back-ref for total_spell_damage WMB check
        self.player.stats = self.player_stats          # expose stats to AI condition functions
        self.player.max_hp = self.player_stats.max_hp
        self.player.hp = self.player_stats.max_hp
        self.player.speed = PLAYER_BASE_SPEED
        self.player.energy = ENERGY_THRESHOLD  # player acts first

        if self.dungeon.rooms:
            x, y = self.dungeon.rooms[0].center()
            if self.dungeon.is_blocked(x, y):
                for tx, ty in self.dungeon.rooms[0].floor_tiles(self.dungeon):
                    if not self.dungeon.is_blocked(tx, ty):
                        x, y = tx, ty
                        break
            self.player.x = x
            self.player.y = y

        # --- FOV ---
        self.fov_radius = FOV_RADIUS   # base radius; items/buffs can modify this

        self.skills = Skills()
        zone_key, zone_floor, _, _ = self._get_zone_info()
        self.dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned, floor_event=self.get_floor_event(self.current_floor))
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)

        # --- Core state ---
        self.turn = 0
        self.kills = 0
        self.running = True
        self.game_over = False
        self.perk_popup_queue: list[dict] = []  # queued perk popups to show one at a time
        self._perk_popup_return_state: MenuState = MenuState.NONE  # menu to return to after popup
        self.death_screen_cursor: int = 0  # 0 = Restart, 1 = Quit
        self.destroy_confirm_cursor: int = 0  # 0 = No (default), 1 = Yes
        self.midas_cursor: int = 0
        self._midas_brew_item = None
        self.restart_requested: bool = False
        self.zones_visited: set[str] = set()  # tracks first-visit per zone
        self.skills_cursor: int = 0        # selected skill row (0-14)
        self.skills_spend_mode: bool = False   # spend-amount prompt open
        self.skills_spend_input: str = ""      # digits typed by user
        self.messages = MessageLog(self, maxlen=LOG_HISTORY_SIZE)
        self.log_scroll: int = 0   # 0 = newest; higher = further back in history
        self.perks_scroll: int = 0  # scroll offset for the perks menu
        self.perk_cursor: int = 0   # cursor index into selectable perk rows
        self.cash = 0
        self.picked_up_items: set[str] = set()  # tracks item instance_ids that have been looted (prevents drop/pickup abuse)
        self.visited_rooms: dict[int, set[int]] = {0: {0}}  # floor -> visited room indices; room 0 pre-visited (player spawn)
        self.destroyed_items: list[dict] = []  # {"name": str, "quantity": int}
        self.pending_hangover_stacks: int = 0  # cumulative hangover stacks pending application on next floor descent
        self.last_drink_id: str | None = None  # tracks last consumed drink (alcohol or soft_drink) for Purple Drank
        self.blue_drank_stacks: int = 0  # Blue Drank doubling stacks; next drink effect called 2^stacks times
        self.crack_hallucinations_active: bool = False  # Meth-Head L2: next consumable grants meth = item value
        self._drink_duration_multiplier: int = 1  # Red Drank: temporarily set to 2 during drink handling
        self._red_drank_free_action: bool = False  # Red Drank: set True to make drink not cost an action

        # --- Equipment ---
        self.equipment: dict[str, Entity | None] = {
            slot: None for slot in EQUIPMENT_SLOTS
        }
        self.rings: list[Entity | None] = [None] * RING_SLOTS
        self.neck: Entity | None = None  # neck slot (only one)
        self.feet: Entity | None = None  # feet slot (only one)
        self.hat: Entity | None = None   # hat slot (only one)
        self._best_chain_armor_this_floor: int = 0  # anti-exploit: tracks best chain equipped this floor
        self.equipment_cursor: int = 0  # indexes into flat occupied-slot list (weapon → neck → feet → hat → rings)

        # --- Sublevel state ---
        self._sublevel_return_floor: int | None = None
        self._sublevel_return_dungeon = None
        self._sublevel_return_pos: tuple | None = None
        self._sublevel_cache: dict = {}  # {sublevel_key: (dungeon, player_pos)}

        # --- Menu state (single enum replaces bools + strings) ---
        self.menu_state = MenuState.NONE
        self.selected_item_index: int | None = None
        self.selected_item_actions: list[str] = []
        self.item_menu_cursor: int = 0
        self.combine_target_cursor: int | None = None  # inventory index highlighted in COMBINE_SELECT
        self.inventory_page: int = 0  # current page for paged inventory display

        # --- Ring replacement state ---
        self.pending_ring_item_index: int | None = None  # inventory index of ring being equipped
        self.ring_replace_cursor: int = 0  # which equipped ring to replace (0-9)

        # --- Targeting mode state ---
        self.targeting_item_index: int | None = None
        self.targeting_cursor: list[int] = [0, 0]
        self.targeting_spell: dict | None = None
        self.targeting_ability_index: int | None = None  # ability whose charge to consume on fire
        self.spray_paint_pending: dict | None = None     # {"item_index": int, "spray_type": str}
        self.spider_egg_pending: dict | None = None      # {"item_index": int}
        self.graffiti_gun_loading: bool = False
        self.last_targeted_enemy = None  # Entity ref: last enemy targeted by any cursor targeting

        # --- Entity targeting state (f-key target select) ---
        self.entity_target_list: list = []  # visible monsters within weapon range
        self.entity_target_index: int = 0   # currently selected target index

        # --- Auto-travel state ---
        self.auto_traveling: bool = False
        self.auto_travel_path: list[tuple[int, int]] = []  # remaining (x, y) waypoints
        self.autoexploring: bool = False  # True when autoexplore is active (re-paths each step)

        # --- Ability system ---
        # Players start with no abilities; abilities are granted by items and skills.
        self.player_abilities: list[AbilityInstance] = []
        self.selected_ability_index: int | None = None
        self.abilities_cursor: int = 0
        self.ability_cooldowns: dict[str, int] = {}  # ability_id -> turns remaining
        self.crit_multiplier: int = 2  # base crit damage multiplier (Crit+ perk increases this)
        self._spellweaver_last_spell: str | None = None  # ability_id of last spell cast
        self._spellweaver_last_turn: int = -99           # turn number of last spell cast
        self.move_cost_reduction: int = 0  # energy refunded per actual move step (Air Jordans perk)
        self._player_just_moved: bool = False  # True when the last handle_move did real movement
        self._last_action_was_attack: bool = False  # set True when a melee/gun attack resolves
        self.player_move_cost: int = ENERGY_THRESHOLD     # energy spent per move action
        self.player_attack_cost: int = ENERGY_THRESHOLD   # energy spent per attack action
        self.action_cost_mult: float = 1.0               # multiplier on all player action costs (Stride buff)
        self._titan_blood_available: bool = True          # Titan's Blood Ring: can proc this floor
        self._titan_blood_was_above_25: bool = True       # Titan's Blood Ring: player was above 25% HP

        # --- Gun system state ---
        self.primary_gun: str | None = None       # "sidearm" or "weapon" slot name
        self.gun_targeting_cursor: list[int] = [0, 0]  # (x, y) cursor for gun targeting
        self.gun_consecutive_target_id: str | None = None  # instance_id of last target fired at
        self.gun_consecutive_count: int = 0                # stacking consecutive hit counter
        self.gatting_consecutive_target_id: str | None = None  # Gunplay L1 perk tracker
        self.gatting_consecutive_count: int = 0                # Gunplay L1 stacking bonus
        self.gun_ability_active: dict | None = None  # active gun ability spec during GUN_TARGETING
        self.gun_jammed: bool = False  # True when gun is jammed; must clear before firing
        self.staff_firing: dict | None = None  # active staff info during GUN_TARGETING
        self.arcane_flux_active: bool = False  # Elementalist L3: charge preservation applies to cooldowns
        self.snipers_mark_target_id: str | None = None  # instance_id of marked target
        self.dead_eye_swagger_gained: int = 0              # Gunplay L4: swagger gained this floor
        self.unfazed_swagger_gained: int = 0               # L Farming L3: swagger gained this floor

        # --- Spec energy system (spec weapon special attacks) ---
        self.spec_energy: float = 0.0       # 0–100; drained by spec abilities, restored passively
        self._spec_energy_counter: int = 0  # ticks since last spec regen

        # --- Electrodynamics L5: Static Reserve charge regen timer ---
        self._static_reserve_timer: int = 0

        # --- Mutation system ---
        self.mutation_log: list[dict] = []
        self._mutations_scroll: int = 0
        self._status_effects_scroll: int = 0

        # --- Vending machine state ---
        self.vending_machine: object = None     # Entity ref: active vending machine
        self.vending_cursor: int = 0            # cursor in vending menu

        # --- Shop item state (Tyrone's Penthouse) ---
        self.shop_item_entity: object = None    # Entity ref: shop item being inspected

        # --- Hotbar state ---
        from config import HOTBAR_SLOTS
        self.hotbar: list[str | None] = [None] * HOTBAR_SLOTS  # ability_id per slot

        # --- Channeling state ---
        # Active channel: {"ability_id": str, "turns_remaining": int, "params": dict}
        # params holds ability-specific data (e.g. direction for Ray of Frost)
        self._channel: dict | None = None

        # --- Look mode state ---
        self.look_cursor: list[int] = [0, 0]
        self.look_info_lines: list = []
        self.look_info_title: str = ""

        # --- Dev tools state (only active when DEV_MODE = True) ---
        self.dev_menu_cursor: int = 0           # selected option in dev menu
        self.dev_item_list: list[str] = []      # flat sorted list of item_ids for spawn picker
        self.dev_item_cursor: int = 0           # cursor position in spawn picker
        self.dev_item_scroll: int = 0           # scroll offset for spawn picker
        self.dev_item_search: str = ""          # search filter for spawn picker
        self.dev_item_filtered: list[str] = []  # filtered item list based on search
        self.dev_floor_cursor: int = 0          # cursor position in floor teleport picker
        self.dev_skill_cursor: int = 0          # cursor position in skill level-up picker
        self.dev_skill_scroll: int = 0          # scroll offset for skill level-up picker

        # --- Action dispatch tables ---
        self._gameplay_handlers = {
            "move": self._action_move,
            "wait": self._action_wait,
            "toggle_skills": self._action_toggle_skills,
            "open_char_sheet": self._action_toggle_char_sheet,
            "open_equipment": self._action_open_equipment,
            "open_log": self._action_open_log,
            "open_bestiary": self._action_open_bestiary,
            "open_perks_menu": self._action_open_perks_menu,
            "toggle_abilities": self._action_toggle_abilities,
            "select_item": self._action_select_item,
            "select_action": self._action_hotbar_use,
            "close_menu": self._action_close_menu,
            "quit": self._action_quit,
            "descend_stairs": self._action_descend_stairs,
            "start_entity_targeting": self._action_start_entity_targeting,
            "fire_gun": self._action_fire_gun,
            "reload_gun": self._action_reload_gun,
            "swap_primary_gun": self._action_swap_primary_gun,
            "open_dev_menu": self._action_open_dev_menu,
            "autoexplore": self._action_autoexplore,
            "look": self._action_look,
            "inventory_page_down": self._action_inventory_page_down,
            "inventory_page_up": self._action_inventory_page_up,
        }

        self._menu_handlers = {
            MenuState.EQUIPMENT: self._handle_equipment_input,
            MenuState.ITEM_MENU: self._handle_item_menu_input,
            MenuState.COMBINE_SELECT: self._handle_combine_input,
            MenuState.LOG: self._handle_log_input,
            MenuState.DESTROY_CONFIRM: self._handle_destroy_confirm_input,
            MenuState.EXAMINE: self._handle_examine_input,
            MenuState.TARGETING: self._handle_targeting_input,
            MenuState.ABILITIES: self._handle_abilities_menu_input,
            MenuState.RING_REPLACE: self._handle_ring_replace_input,
            MenuState.ENTITY_TARGETING: self._handle_entity_targeting_input,
            MenuState.PERKS: self._handle_perks_input,
            MenuState.DEV_MENU: self._handle_dev_menu_input,
            MenuState.DEV_ITEM_SELECT: self._handle_dev_item_select_input,
            MenuState.DEV_FLOOR_SELECT: self._handle_dev_floor_select_input,
            MenuState.DEV_SKILL_SELECT: self._handle_dev_skill_select_input,
            MenuState.ADJACENT_TILE_TARGETING: self._handle_adjacent_tile_targeting_input,
            MenuState.DEEP_FRYER: self._handle_deep_fryer_input,
            MenuState.GUN_TARGETING: self._handle_gun_targeting_input,
            MenuState.LOOK_TARGETING: self._handle_look_targeting,
            MenuState.LOOK_INFO: self._handle_look_info,
            MenuState.SETTINGS: self._handle_settings_input,
            MenuState.VENDING_MACHINE: self._handle_vending_machine_input,
            MenuState.MIDAS_BREW: self._handle_midas_brew_input,
            MenuState.SHOP_ITEM: self._handle_shop_item_input,
        }

    # ------------------------------------------------------------------
    # Zone helpers
    # ------------------------------------------------------------------

    def _roll_floor_events(self):
        """Roll random floor events for each zone at game start."""
        from config import ZONE_FLOOR_EVENTS, ZONE_ORDER
        cumulative = 0
        for zone in ZONE_ORDER:
            zone_key = zone["key"]
            cfg = ZONE_FLOOR_EVENTS.get(zone_key)
            if cfg and cfg["eligible_floors"] and cfg["event_pool"]:
                zone_floor = random.choice(cfg["eligible_floors"])
                event_id = random.choice(cfg["event_pool"])
                global_floor = cumulative + zone_floor
                self.floor_events[global_floor] = event_id
            cumulative += zone["floors"]

    def get_floor_event(self, global_floor: int) -> str | None:
        """Return the event_id for a floor, or None if no event."""
        return self.floor_events.get(global_floor)

    def _get_zone_info(self):
        """Return (zone_key, zone_floor_num, display_name, zone_type) for current floor."""
        return get_zone_for_floor(self.current_floor)

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def _register_events(self):
        self.event_bus.on("entity_died", self._on_entity_died)
        self.event_bus.on("entity_died", self._on_kill_cash_drop)
        self.event_bus.on("entity_died", self._on_kill_loot_drop)
        self.event_bus.on("entity_died", self._on_kill_shakedown)
        self.event_bus.on("entity_died", self._on_kill_tox_spillover)
        self.event_bus.on("entity_died", self._on_kill_toxic_harvest)
        self.event_bus.on("entity_died", self._on_kill_acid_meltdown)
        self.event_bus.on("entity_died", self._on_kill_snipers_mark)
        self.event_bus.on("entity_died", self._on_kill_shake_it_off)
        self.event_bus.on("entity_died", self._on_kill_curse_dot_spread)
        self.event_bus.on("entity_died", self._on_death_graffiti_heal)
        self.event_bus.on("entity_died", self._on_death_graffiti_xp)
        self.event_bus.on("entity_died", self._on_black_widow_death)
        self.event_bus.on("entity_died", self._on_kill_fireball_charge)
        self.event_bus.on("entity_died", self._on_kill_sangria_extend)
        self.event_bus.on("entity_died", self._on_kill_venom_pool)
        self.event_bus.on("entity_died", self._on_kill_staff_charge)
        self.event_bus.on("entity_died", self._on_kill_victory_rush)
        self.event_bus.on("entity_died", self._on_kill_berserk)
        self.event_bus.on("entity_died", self._on_kill_corpse_explosion)
        self.event_bus.on("entity_died", self._on_kill_curse_voodoo_drop)
        self.event_bus.on("entity_died", self._on_kill_scavengers_eye)

    def _on_kill_scavengers_eye(self, entity, killer=None):
        """Scavenger's Eye (Kimchi): 50% chance on kill to drop a random lesser consumable."""
        if entity.entity_type != "monster" or killer is not self.player:
            return
        eff = next(
            (e for e in self.player.status_effects
             if getattr(e, 'id', '') == 'scavengers_eye'),
            None,
        )
        if eff is None:
            return
        if random.random() < 0.50:
            from items import create_item_entity
            from effects import ScavengersEyeEffect
            item_id = random.choice(ScavengersEyeEffect._DROP_TABLE)
            kwargs = create_item_entity(item_id, entity.x, entity.y)
            self.dungeon.add_entity(Entity(**kwargs))
            item_name = kwargs.get("name", item_id)
            self.messages.append([
                ("Scavenger's Eye! ", (180, 120, 200)),
                (f"{entity.name} dropped {item_name}.", (100, 255, 100)),
            ])

    def _on_kill_berserk(self, entity, killer=None):
        """Berserker's Ring: on melee kill, apply independent +4 STR for 10 turns."""
        if entity.entity_type != "monster" or killer != self.player:
            return
        if not self._last_action_was_attack:
            return
        # Check if any equipped ring has the berserkers_ring tag
        has_ring = any(
            r is not None and "berserkers_ring" in (get_item_def(r.item_id) or {}).get("tags", [])
            for r in self.rings
        )
        if not has_ring:
            return
        import effects as _eff
        berserk = _eff.BerserkEffect(duration=10)
        berserk.apply(self.player, self)
        self.player.status_effects.append(berserk)
        # Count active stacks
        stack_count = sum(1 for e in self.player.status_effects if getattr(e, 'id', '') == 'berserk')
        self.messages.append([
            ("Berserk! ", (255, 80, 40)),
            (f"+4 STR for 10 turns (x{stack_count})", (255, 180, 100)),
        ])

    def _on_kill_curse_voodoo_drop(self, entity, killer=None):
        """Blackkk Magic L4 (Dark Covenant): 25% chance to drop a Voodoo Doll when a cursed enemy dies."""
        if entity.entity_type != "monster" or killer != self.player:
            return
        if self.skills.get("Blackkk Magic").level < 4:
            return
        # Check if the enemy had a curse effect
        if not any(getattr(e, 'is_curse', False) for e in entity.status_effects):
            return
        if random.random() >= 0.25:
            return
        from items import create_item_entity
        kwargs = create_item_entity("voodoo_doll", entity.x, entity.y)
        self.dungeon.add_entity(Entity(**kwargs))
        self.messages.append([
            ("Dark Covenant! ", (140, 60, 180)),
            (f"The {entity.name} dropped a Voodoo Doll.", (200, 160, 255)),
        ])

    def _on_black_widow_death(self, entity, killer=None):
        """When a Black Widow dies, cleanse all venom effects from the player."""
        if getattr(entity, 'enemy_type', None) != 'black_widow':
            return
        venom_ids = {'neuro_venom', 'pipe_venom', 'wolf_spider_venom', 'venom'}
        before = len(self.player.status_effects)
        self.player.status_effects = [
            e for e in self.player.status_effects
            if getattr(e, 'id', '') not in venom_ids
        ]
        cleansed = before - len(self.player.status_effects)
        if cleansed > 0:
            self.messages.append([
                ("The Black Widow's death breaks the venom! ", (100, 255, 100)),
                (f"{cleansed} venom effect(s) cleansed!", (200, 255, 200)),
            ])

    def _on_kill_fireball_charge(self, entity, killer=None):
        """Pyromania L6: killing an enemy with 5+ ignite stacks grants +1 Fireball charge."""
        if killer is not self.player:
            return
        pyro = self.skills.get("Pyromania")
        if not pyro or pyro.level < 6:
            return
        ignite_eff = next((e for e in entity.status_effects
                           if getattr(e, 'id', '') == 'ignite'), None)
        if ignite_eff and ignite_eff.stacks >= 5:
            self.grant_ability_charges("fireball", 1, silent=False)
            self.messages.append([
                ("Inferno Kill! ", (255, 100, 20)),
                ("+1 Fireball charge!", (255, 200, 60)),
            ])

    def _on_kill_sangria_extend(self, entity, killer=None):
        """Sangria 40: killing an enemy extends Sangria buff by 20 turns."""
        if killer is not self.player:
            return
        sangria = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'sangria'),
            None,
        )
        if sangria:
            sangria.extend_on_kill(self)

    def _on_kill_venom_pool(self, entity, killer=None):
        """Arachnigga L3 — Toxic Bite: enemies that die while venomed leave a Venom Pool."""
        if entity.entity_type != "monster":
            return
        if self.skills.get("Arachnigga").level < 3:
            return
        has_venom = any(getattr(e, 'id', '') == 'venom' for e in entity.status_effects)
        if not has_venom:
            return
        from hazards import create_venom_pool
        # Don't spawn if a venom pool already exists at this tile
        if any(getattr(h, 'hazard_type', None) == 'venom_pool'
               for h in self.dungeon.get_entities_at(entity.x, entity.y)):
            return
        self.dungeon.add_entity(create_venom_pool(entity.x, entity.y))
        self.messages.append([
            ("The ", (200, 200, 200)),
            (f"{entity.name}", (200, 200, 220)),
            ("'s venom pools on the ground!", (80, 200, 60)),
        ])

    def _on_kill_staff_charge(self, entity, killer=None):
        """Any enemy death: +1 charge to all staves (equipped + inventory), cap 99."""
        if entity.entity_type != "monster":
            return
        from items import get_item_def
        staves = []
        # Check equipped weapon
        weapon = self.equipment.get("weapon")
        if weapon:
            wdefn = get_item_def(weapon.item_id)
            if wdefn and wdefn.get("staff_element"):
                staves.append(weapon)
        # Check inventory
        for item in self.player.inventory:
            if not hasattr(item, 'item_id'):
                continue
            idefn = get_item_def(item.item_id)
            if idefn and idefn.get("staff_element"):
                staves.append(item)
        for staff in staves:
            if getattr(staff, 'charges', None) is not None:
                staff.charges = min(99, staff.charges + 1)

    def _on_kill_victory_rush(self, entity, killer=None):
        """Kill with a beating weapon: +1 Victory Rush charge (max 1)."""
        if entity.entity_type != "monster" or killer != self.player:
            return
        vr = next((a for a in self.player_abilities if a.ability_id == "victory_rush"), None)
        if vr is None:
            return
        # Check if wielding a beating weapon
        from items import get_item_def, weapon_matches_type
        weapon = self.equipment.get("weapon")
        if weapon:
            wdefn = get_item_def(weapon.item_id)
            if not wdefn or not weapon_matches_type(wdefn, "beating"):
                return
        else:
            # Unarmed counts as smacking, not beating
            return
        if vr.charges_remaining < 1:
            vr.charges_remaining = 1
            self.messages.append([
                ("Victory Rush: ", (255, 200, 50)),
                ("+1 charge!", (200, 255, 100)),
            ])

    def _on_kill_corpse_explosion(self, entity, killer=None):
        """Infected L4: Corpse Explosion. Enemies killed during Zombie Rage explode."""
        if entity.entity_type != "monster":
            return
        if self.skills.get("Infected").level < 4:
            return
        # Must have Zombie Rage active
        if not any(getattr(e, 'id', '') == 'zombie_rage' for e in self.player.status_effects):
            return

        import math
        from combat import add_infection

        # Track chain depth for escalating infection cost
        depth = getattr(self, '_corpse_chain_depth', 0)
        self._corpse_chain_depth = depth + 1

        # Explosion damage: 30% of dead enemy's max HP
        raw_dmg = max(1, int(entity.max_hp * 0.30))

        # Hit all enemies in Euclidean radius 3
        targets_hit = []
        for ent in list(self.dungeon.entities):
            if ent.entity_type != "monster" or not ent.alive or ent is entity:
                continue
            dx = ent.x - entity.x
            dy = ent.y - entity.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 3.0:
                actual_dmg = max(1, raw_dmg - ent.defense)
                ent.take_damage(actual_dmg)
                targets_hit.append((ent, actual_dmg))

        if targets_hit:
            # Infection gain: 2 base + 2 per chain depth
            infection_gain = 2 + 2 * depth
            add_infection(self, self.player, infection_gain)

            names = ", ".join(f"{t.name} ({d})" for t, d in targets_hit)
            self.messages.append([
                ("Corpse Explosion! ", (200, 80, 50)),
                (f"{entity.name} explodes! {names}", (220, 150, 100)),
                (f" (+{infection_gain} infection)", (120, 200, 50)),
            ])

            # Check for Infection Nova trigger
            if (self.player.infection >= self.player.max_infection
                    and not any(getattr(e, 'id', '') == 'hollowed_out'
                                for e in self.player.status_effects)):
                self._trigger_infection_nova()

            # Emit entity_died for explosion kills → chains
            for ent, _dmg in targets_hit:
                if not ent.alive:
                    self.event_bus.emit("entity_died", entity=ent, killer=self.player)

        self._corpse_chain_depth = depth  # restore

    def _trigger_infection_nova(self):
        """Infection Nova: STR×3 damage + 2t stun in Euclidean radius 5. Reset to 50 infection."""
        import math
        import effects

        str_val = self.player_stats.effective_strength
        nova_dmg = str_val * 3
        px, py = self.player.x, self.player.y
        hit_count = 0

        targets_killed = []
        for ent in list(self.dungeon.entities):
            if ent.entity_type != "monster" or not ent.alive:
                continue
            dx = ent.x - px
            dy = ent.y - py
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= 5.0:
                actual_dmg = max(1, nova_dmg - ent.defense)
                ent.take_damage(actual_dmg)
                if ent.alive:
                    effects.apply_effect(ent, self, "stun", duration=2, silent=True)
                else:
                    targets_killed.append(ent)
                hit_count += 1

        # Reset infection to 50 and apply Hollowed Out
        self.player.infection = 50
        effects.apply_effect(self.player, self, "hollowed_out")

        self.messages.append([
            ("INFECTION NOVA! ", (255, 50, 50)),
            (f"{nova_dmg} damage to {hit_count} enemies! Infection reset to 50.", (255, 180, 100)),
        ])

        # Emit entity_died for nova kills (can chain more explosions)
        for ent in targets_killed:
            self.event_bus.emit("entity_died", entity=ent, killer=self.player)

    def _on_entity_damaged(self, entity, raw_damage, hp_damage):
        """Callback for floating damage numbers, Titan's Blood, and Outbreak echo."""
        if entity == self.player and hp_damage > 0:
            self._check_titan_blood_proc()

        # Outbreak echo: if damaged entity has Outbreak, echo 30% to other marked enemies
        if (entity.entity_type == "monster" and hp_damage > 0
                and not getattr(self, '_outbreak_echoing', False)):
            has_outbreak = any(getattr(e, 'id', '') == 'outbreak'
                              for e in entity.status_effects)
            if has_outbreak:
                self._process_outbreak_echo(entity, hp_damage)

        if self.sdl_overlay is None or entity == self.player:
            return
        amount = hp_damage if hp_damage > 0 else raw_damage
        self.sdl_overlay.add_floating_text(entity.x, entity.y, str(amount), (255, 80, 80))

    def _process_outbreak_echo(self, source, hp_damage):
        """Echo 30% of damage to other Outbreak-marked enemies within radius 3 of source.
        Each enemy echoes at most once per event (guard flag prevents chain echoing)."""
        import math
        echo_dmg = max(1, int(hp_damage * 0.30))
        self._outbreak_echoing = True  # prevent echo from triggering more echoes
        try:
            killed = []
            for ent in list(self.dungeon.entities):
                if (ent is source or ent.entity_type != "monster"
                        or not ent.alive):
                    continue
                if not any(getattr(e, 'id', '') == 'outbreak'
                           for e in ent.status_effects):
                    continue
                dx = ent.x - source.x
                dy = ent.y - source.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= 3.0:
                    actual = max(1, echo_dmg - ent.defense)
                    ent.take_damage(actual)
                    if not ent.alive:
                        killed.append(ent)
            # Emit entity_died for echo kills (can trigger Corpse Explosion)
            for ent in killed:
                self.event_bus.emit("entity_died", entity=ent, killer=self.player)
        finally:
            self._outbreak_echoing = False

    def _on_entity_healed(self, entity, amount):
        """Callback for floating heal numbers + Titan's Blood tracking."""
        if entity == self.player and self.player.max_hp > 0:
            if self.player.hp > self.player.max_hp * 0.25:
                self._titan_blood_was_above_25 = True
        if self.sdl_overlay is None:
            return
        self.sdl_overlay.add_floating_text(entity.x, entity.y, str(amount), (80, 255, 80))

    def _tick_rad_bomb_crystals(self, monsters):
        """Tick all rad bomb crystals. Detonate when countdown reaches 0."""
        from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
        crystals = [
            e for e in self.dungeon.entities
            if getattr(e, 'hazard_type', None) == 'rad_bomb_crystal'
        ]
        for crystal in crystals:
            crystal.hazard_duration -= 1
            if crystal.hazard_duration <= 0:
                self._detonate_rad_bomb(crystal, monsters)

    def _detonate_rad_bomb(self, crystal, monsters):
        """Explode a rad bomb crystal in a 5x5 square."""
        from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
        cx, cy = crystal.x, crystal.y
        damage = getattr(crystal, 'rad_bomb_damage', 20)
        self.dungeon.remove_entity(crystal)
        self.messages.append([
            ("RAD BOMB DETONATES! ", (120, 255, 80)),
            (f"({damage} damage, 5x5 area)", (160, 255, 120)),
        ])
        targets = [self.player] + [m for m in monsters if m.alive]
        for entity in targets:
            dx = abs(entity.x - cx)
            dy = abs(entity.y - cy)
            if dx <= 2 and dy <= 2:
                entity.take_damage(damage)
                if entity == self.player:
                    self._gain_catchin_fades_xp(damage)
                    self.messages.append(f"You take {damage} radiation blast damage!")
                else:
                    self.messages.append(f"The {entity.name} takes {damage} radiation blast damage!")
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=self.player)

    def _tick_scrap_turrets(self, monsters):
        """Tick all scrap turrets. Shoot nearest enemy in range, decrement duration."""
        import math
        turrets = [
            e for e in self.dungeon.entities
            if getattr(e, 'hazard_type', None) == 'scrap_turret' and getattr(e, 'alive', False)
        ]
        for turret in turrets:
            turret.hazard_duration -= 1
            if turret.hazard_duration <= 0 or not turret.alive:
                self.dungeon.remove_entity(turret)
                self.messages.append("Scrap Turret falls apart.")
                continue

            # Shoot nearest visible enemy within range
            tx, ty = turret.x, turret.y
            best_target = None
            best_dist = float('inf')
            for m in monsters:
                if not m.alive:
                    continue
                dx = m.x - tx
                dy = m.y - ty
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= turret.turret_range and dist < best_dist:
                    best_target = m
                    best_dist = dist

            if best_target is not None:
                damage = max(1, turret.power - best_target.defense)
                best_target.take_damage(damage)
                hp_str = f"{best_target.hp}/{best_target.max_hp}" if best_target.alive else "dead"
                self.messages.append([
                    ("Turret! ", (200, 150, 50)),
                    (f"Shoots {best_target.name} for {damage} dmg ({hp_str})", (220, 180, 100)),
                ])
                if not best_target.alive:
                    # Dismantling L6: turret kills drop Scrap
                    if self.skills.get("Dismantling").level >= 6:
                        from items import create_item_entity
                        scrap_kwargs = create_item_entity("scrap", best_target.x, best_target.y)
                        if scrap_kwargs:
                            self.dungeon.add_entity(Entity(**scrap_kwargs))
                            self.messages.append([
                                ("Scrap! ", (160, 130, 80)),
                                (f"{best_target.name} drops salvageable scrap.", (180, 160, 120)),
                            ])
                    self.event_bus.emit("entity_died", entity=best_target, killer=self.player)

    def _on_entity_died(self, entity, killer=None):
        """Universal death handler — removes entity and bookkeeps kills."""
        # Death save: check for effects that prevent death (e.g. Hard Boiled Egg)
        if entity == self.player:
            for eff in list(entity.status_effects):
                if hasattr(eff, "on_death_save") and eff.on_death_save(entity, self):
                    return  # Death prevented — skip all death processing
            # Straw Hat death save (checked after consumable effects like Hard Boiled Egg)
            if self._straw_hat_death_save():
                return
        self.dungeon.remove_entity(entity)
        # Clear aggro references pointing at a dying summon
        if getattr(entity, "is_summon", False):
            for m in self.dungeon.get_monsters():
                if getattr(m, "aggro_target", None) is entity:
                    m.aggro_target = None
        if entity.entity_type == "monster" and not getattr(entity, "is_summon", False):
            self.kills += 1
            # Amulet of Equivalent Exchange: +1 soul per kill
            if self.neck and "amulet_ee" in (get_item_def(self.neck.item_id) or {}).get("tags", []):
                self.neck.soul_count = getattr(self.neck, "soul_count", 0) + 1
            # Trigger the floor alarm (first_kill_happened flag).
            if not self.dungeon.first_kill_happened:
                self.dungeon.first_kill_happened = True
            # Trigger female alarm so fat_gooner enemies start chasing.
            if getattr(entity, "gender", None) == "female" and not self.dungeon.female_kill_happened:
                self.dungeon.female_kill_happened = True
                self.messages.append("An angry rumble echoes down the hall...")
            # Faction reputation shift on kill: -200 with killed faction, +100 with rival
            faction = getattr(entity, "faction", None)
            if faction and hasattr(self, "player_stats"):
                self.player_stats.modify_reputation(faction, -200)
                other = "scryer" if faction == "aldor" else "aldor"
                self.player_stats.modify_reputation(other, 100)
            # Zombie kill: +10 Infected XP
            if getattr(entity, "enemy_type", None) == "zombie":
                bksmt = self.player_stats.effective_book_smarts
                self.skills.gain_potential_exp("Infected", 10, bksmt)
            # Death split: spawn children on death
            if getattr(entity, "death_split_type", None):
                self._spawn_death_split(entity)
            # Death creep: spawn toxic creep around death position
            if getattr(entity, "death_creep_radius", 0) > 0:
                self._spawn_death_creep(entity)
        if entity == self.player:
            self.game_over = True
            self.menu_state = MenuState.DEATH_SCREEN
            self.death_screen_cursor = 0
            self.messages.append("You died!")

    def _on_kill_cash_drop(self, entity, killer=None):
        """Award cash from killed monsters."""
        if entity.entity_type != "monster":
            return
        cash = getattr(entity, "cash_drop", 0)
        if cash > 0:
            self.cash += cash
            self.messages.append(f"[+${cash}]")

    def _on_kill_loot_drop(self, entity, killer=None):
        """Spawn an item on the ground when a monster with a death_drop_table is killed."""
        if entity.entity_type != "monster":
            return
        drop_table = getattr(entity, "death_drop_table", [])
        drop_chance = getattr(entity, "death_drop_chance", 0.0)
        if not drop_table or random.random() >= drop_chance:
            return
        item_id = random.choice(drop_table)
        strain_items = frozenset(("joint", "kush", "weed_nug"))
        strain = pick_strain(self.dungeon.zone, self.player_stats) if item_id in strain_items else None
        kwargs = create_item_entity(item_id, entity.x, entity.y, strain=strain)
        # Ammo drops use death_drop_quantity for stack size
        drop_qty = getattr(entity, "death_drop_quantity", None)
        if drop_qty and isinstance(drop_qty, (list, tuple)) and len(drop_qty) == 2:
            kwargs["quantity"] = random.randint(drop_qty[0], drop_qty[1])
        self.dungeon.add_entity(Entity(**kwargs))
        item_name = kwargs.get("name", item_id)
        qty_str = f" x{kwargs.get('quantity', 1)}" if kwargs.get("quantity", 1) > 1 else ""
        strain_suffix = f" ({strain})" if strain else ""
        self.messages.append(f"The {entity.name} dropped {item_name}{qty_str}{strain_suffix}.")

    def _on_kill_shakedown(self, entity, killer=None):
        """Stealing L3 — Shakedown: chance to drop a bonus consumable on enemy death."""
        if entity.entity_type != "monster":
            return
        if killer is not self.player:
            return
        stealing_skill = self.skills.get("Stealing")
        if not stealing_skill or stealing_skill.level < 3:
            return
        stsmt = self.player_stats.effective_street_smarts
        chance = (10 + stsmt / 3) / 100.0  # (10 + STS/3) percent
        if random.random() >= chance:
            return
        from loot import pick_random_consumable
        item_id, strain = pick_random_consumable(self.dungeon.zone, self.player_stats)
        kwargs = create_item_entity(item_id, entity.x, entity.y, strain=strain)
        self.dungeon.add_entity(Entity(**kwargs))
        item_name = kwargs.get("name", item_id)
        strain_suffix = f" ({strain})" if strain else ""
        self.messages.append([
            ("Shakedown! ", (255, 200, 50)),
            (f"The {entity.name} dropped {item_name}{strain_suffix}.", (200, 200, 200)),
        ])

    def _on_kill_tox_spillover(self, entity, killer=None):
        """Tox Spillover Aura: transfer % of dead monster's tox to nearest alive enemy.
        Also roll for permanent tolerance on kill of toxic enemy."""
        if entity.entity_type != "monster":
            return
        if killer is not self.player:
            return
        aura = next(
            (e for e in self.player.status_effects
             if getattr(e, 'id', '') == 'tox_spillover_aura'),
            None,
        )
        if aura is None:
            return
        dead_tox = getattr(entity, 'toxicity', 0)
        # Permanent tolerance chance: 1% per 40 enemy tox, cap 8%
        if dead_tox > 0:
            chance = min(8, dead_tox // 40)
            if chance > 0 and random.randint(1, 100) <= chance:
                self.player_stats.modify_base_stat("tolerance", 1)
                self.messages.append([
                    ("Swamp Gas: +1 permanent Tolerance!", (200, 180, 60)),
                ])
        # Spillover: transfer % of dead monster's tox to nearest alive enemy
        if dead_tox <= 0:
            return
        transfer = int(dead_tox * aura.spillover_pct / 100)
        if transfer <= 0:
            return
        # Find nearest alive monster
        best = None
        best_dist = 999
        for m in self.dungeon.get_monsters():
            if not m.alive or m is entity:
                continue
            dist = max(abs(m.x - entity.x), abs(m.y - entity.y))
            if dist < best_dist:
                best_dist = dist
                best = m
        if best is not None:
            from combat import add_toxicity
            add_toxicity(self, best, transfer)
            self.messages.append(
                f"Tox spillover! {transfer} toxicity spreads to {best.name}."
            )

    def _on_kill_toxic_harvest(self, entity, killer=None):
        """Toxic Harvest buff: any monster kill grants +25 toxicity and refreshes the buff."""
        if entity.entity_type != "monster":
            return
        harvest = next(
            (e for e in self.player.status_effects
             if getattr(e, 'id', '') == 'toxic_harvest'),
            None,
        )
        if harvest is None:
            return
        # Goes through resistance: positive res reduces gain, negative res increases it
        self.add_toxicity(self.player, 25)
        harvest.duration = 10  # refresh full duration
        self.messages.append([
            ("Toxic Harvest: ", (80, 255, 80)),
            ("+25 toxicity!", (160, 255, 160)),
        ])

    def _on_kill_acid_meltdown(self, entity, killer=None):
        """Acid Meltdown buff: any monster kill spawns a 3x3 acid pool centered on the corpse."""
        if entity.entity_type != "monster":
            return
        meltdown = next(
            (e for e in self.player.status_effects
             if getattr(e, 'id', '') == 'acid_meltdown'),
            None,
        )
        if meltdown is None:
            return
        from hazards import create_acid_pool
        cx, cy = entity.x, entity.y
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                tx, ty = cx + dx, cy + dy
                # Skip walls
                if self.dungeon.is_terrain_blocked(tx, ty):
                    continue
                # Skip if acid pool already exists at this tile
                has_acid = any(
                    getattr(h, 'hazard_type', None) == 'acid_pool'
                    for h in self.dungeon.get_entities_at(tx, ty)
                )
                if has_acid:
                    continue
                self.dungeon.add_entity(create_acid_pool(tx, ty))

    def _on_kill_snipers_mark(self, entity, killer=None):
        """Sniper's Mark: refund ability charge when marked target dies."""
        if entity.entity_type != "monster":
            return
        target_id = getattr(entity, 'instance_id', id(entity))
        if self.snipers_mark_target_id != target_id:
            return
        self.snipers_mark_target_id = None
        # Refund the charge
        from abilities import ABILITY_REGISTRY
        for inst in self.player_abilities:
            if inst.ability_id == "snipers_mark":
                defn = ABILITY_REGISTRY.get("snipers_mark")
                if defn and inst.charges < defn.max_charges:
                    inst.charges += 1
                    self.messages.append([
                        ("Sniper's Mark: ", (255, 100, 100)),
                        ("Target eliminated — charge refunded!", (200, 200, 200)),
                    ])
                break

    def _on_kill_shake_it_off(self, entity, killer=None):
        """L Farming L1 perk: Shake It Off — heal 2 HP on kill."""
        if entity.entity_type != "monster":
            return
        if killer is not self.player:
            return
        if self.skills.get("L Farming").level < 1:
            return
        heal = 2
        old_hp = self.player.hp
        self.player.heal(heal)
        actual = self.player.hp - old_hp
        if actual > 0:
            self.messages.append([
                ("Shake It Off! ", (100, 255, 150)),
                (f"+{actual} HP", (100, 255, 100)),
                (f" ({self.player.hp}/{self.player.max_hp})", (150, 150, 150)),
            ])

    def _on_kill_curse_dot_spread(self, entity, killer=None):
        """Curse of DOT: on death, spread to nearest enemy within 2 tiles
        with inherited stack count."""
        if entity.entity_type != "monster":
            return
        import effects as _eff
        curse = next(
            (e for e in entity.status_effects if getattr(e, 'id', '') == 'curse_dot'),
            None,
        )
        if curse is None:
            return
        stacks = curse.stacks
        # Find nearest non-summon monster within Chebyshev distance 2
        best = None
        best_dist = 999
        for m in self.dungeon.get_monsters():
            if not m.alive or m is entity or getattr(m, "is_summon", False):
                continue
            # Skip monsters that already have curse_dot
            if any(getattr(e, 'id', '') == 'curse_dot' for e in m.status_effects):
                continue
            dist = max(abs(m.x - entity.x), abs(m.y - entity.y))
            if dist <= 2 and dist < best_dist:
                best_dist = dist
                best = m
        if best is None:
            return
        _eff.apply_effect(best, self, "curse_dot", stacks=stacks, silent=True)
        # Curse spread trail animation
        sdl = getattr(self, "sdl_overlay", None)
        if sdl:
            path = _curse_spread_path(entity.x, entity.y, best.x, best.y)
            sdl.add_tile_flash_trail(path, color=(140, 60, 180), duration=0.3, trail_speed=0.04)
        # +20 Blackkk Magic XP on spread
        adjusted_xp = round(20 * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Blackkk Magic", adjusted_xp,
            self.player_stats.effective_book_smarts,
            briskness=self.player_stats.total_briskness,
        )
        self.messages.append([
            ("Curse of DOT spreads to ", (120, 40, 160)),
            (f"{best.name}!", (180, 120, 220)),
            (f" ({stacks} stacks)", (160, 100, 200)),
        ])

    def _on_death_graffiti_heal(self, entity, killer=None):
        """Graffiti L2: when any monster dies, heal 5 HP per spray-paint match.
        Check both the dead monster's tile and the player's tile independently."""
        if entity.entity_type != "monster" or getattr(entity, "is_summon", False):
            return
        if self.skills.get("Graffiti").level < 2:
            return
        heals = 0
        if self.dungeon.spray_paint.get((entity.x, entity.y)):
            heals += 1
        if self.dungeon.spray_paint.get((self.player.x, self.player.y)):
            heals += 1
        if heals > 0:
            total = 5 * heals
            self.player.heal(total)
            self.messages.append([
                ("Street Art! ", (255, 180, 80)),
                (f"+{total} HP", (100, 255, 100)),
            ])

    def _on_death_graffiti_xp(self, entity, killer=None):
        """Graffiti XP on kill: +5 if enemy dies on red, +5 if player on green."""
        if entity.entity_type != "monster" or entity == self.player:
            return
        xp = 0
        # Red: enemy dies on red spray paint
        if self.dungeon.spray_paint.get((entity.x, entity.y)) == "red":
            xp += 5
        # Green: player standing on green spray paint when enemy dies
        if self.dungeon.spray_paint.get((self.player.x, self.player.y)) == "green":
            xp += 5
        if xp > 0:
            adjusted = round(xp * self.player_stats.xp_multiplier)
            self.skills.gain_potential_exp(
                "Graffiti", adjusted,
                self.player_stats.effective_book_smarts,
                briskness=self.player_stats.total_briskness
            )

    # ------------------------------------------------------------------
    # Death behaviors (split, creep)
    # ------------------------------------------------------------------

    def _spawn_death_split(self, entity):
        return combat._spawn_death_split(self, entity)

    def _spawn_death_creep(self, entity):
        return combat._spawn_death_creep(self, entity)

    def spawn_trail_creep(self, x, y, trail_info):
        return combat.spawn_trail_creep(self, x, y, trail_info)

    # ------------------------------------------------------------------
    # Suicide / Chemist attack handlers
    # ------------------------------------------------------------------

    def handle_suicide_explosion(self, monster):
        return combat.handle_suicide_explosion(self, monster)

    def handle_chemist_vial(self, monster):
        return combat.handle_chemist_vial(self, monster)

    def handle_chemist_ranged(self, monster):
        return combat.handle_chemist_ranged(self, monster)

    def _sac_spider_web_shot(self, monster):
        """Sac Spider ranged attack: shoot web at player's tile, spawn cobweb, apply webbed."""
        from hazards import create_web
        px, py = self.player.x, self.player.y

        # Deal damage (normal monster attack)
        damage = max(1, monster.power - combat._compute_player_defense(self))
        combat.deal_damage(self, damage, self.player)

        # Spawn cobweb on player's tile (if not already webbed by a cobweb there)
        has_web = any(
            getattr(ent, 'hazard_type', None) == 'web'
            for ent in self.dungeon.get_entities_at(px, py)
        )
        if not has_web:
            web = create_web(px, py)
            self.dungeon.add_entity(web)
            # Immediately stick the player
            if not any(getattr(e, 'id', '') == 'web_stuck' for e in self.player.status_effects):
                # Only stick if not immune (Arachnigga L1)
                web_immune = self.skills.get("Arachnigga").level >= 1
                if not web_immune:
                    effects.apply_effect(self.player, self, "web_stuck",
                                         silent=True, web_entity=web)

        # Apply webbed slow debuff
        effects.apply_effect(self.player, self, "webbed", silent=True)

        self.messages.append([
            (f"{monster.name} shoots a web at you for {damage} damage! ", (200, 50, 50)),
            ("You're webbed!", (180, 180, 220)),
        ])

        if not self.player.alive:
            self.event_bus.emit("entity_died", entity=self.player, killer=monster)

    # ------------------------------------------------------------------
    # FOV helper
    # ------------------------------------------------------------------

    def get_action_cost(self, base: int | None = None) -> int:
        """Return action energy cost with stride multiplier applied."""
        if base is None:
            base = ENERGY_THRESHOLD
        if self.action_cost_mult != 1.0:
            return int(base * self.action_cost_mult)
        return base

    def _compute_fov(self):
        """Recompute FOV and log messages for any newly revealed landmarks."""
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)
        for entity in self.dungeon.newly_revealed_landmarks:
            self.messages.append(
                f"You spot {entity.name} in the distance — it's marked on your map."
            )

    def _update_tile_stat_bonuses(self):
        """Recalculate tile-based stat/defense bonuses from spray paint at the player's position."""
        bonuses = self.player_stats.tile_stat_bonuses
        for k in bonuses:
            bonuses[k] = 0
        self.player_stats.tile_defense_bonus = 0

        spray = self.dungeon.spray_paint.get((self.player.x, self.player.y))
        if spray == "blue":
            bonuses["street_smarts"] = 5
        elif spray == "green":
            self.player_stats.tile_defense_bonus = 4

    def _update_sleeper_stacks(self):
        """Update Sleeper Agent weapon stacks based on whether player moved."""
        weapon = self.equipment["weapon"]
        if weapon is None:
            return
        wdefn = get_item_def(weapon.item_id)
        if not wdefn or "sleeper_agent" not in wdefn.get("tags", []):
            return

        if getattr(self, '_player_moved_this_turn', False):
            old_stacks = getattr(weapon, "sleeper_stacks", 0)
            weapon.sleeper_stacks = 0
            if old_stacks > 0:
                self.player.status_effects = [
                    e for e in self.player.status_effects
                    if getattr(e, 'id', '') != 'sleeper_agent'
                ]
                self.messages.append([
                    ("Sleeper Agent stacks lost!", (180, 80, 255)),
                ])
        else:
            old_stacks = getattr(weapon, "sleeper_stacks", 0)
            if old_stacks < 10:
                weapon.sleeper_stacks = old_stacks + 1
                effects.apply_effect(
                    self.player, self, "sleeper_agent",
                    stacks=weapon.sleeper_stacks, silent=True
                )

    # ------------------------------------------------------------------
    # Main action dispatch
    # ------------------------------------------------------------------

    def process_action(self, action):
        """Process player action and update game state. Returns True if a turn was consumed."""
        if not action:
            return False

        self._player_moved_this_turn = False
        action_type = action.get("type")

        # After death, only allow death screen navigation
        if self.game_over:
            if action_type == "move":
                dy = action.get("dy", 0)
                if dy != 0:
                    self.death_screen_cursor = (self.death_screen_cursor + dy) % 2
            elif action_type in ("confirm_target", "item_use"):
                # Enter or Space to confirm selection
                if self.death_screen_cursor == 0:
                    self.restart_requested = True
                    self.running = False
                else:
                    self.running = False
            elif action_type == "quit":
                self.running = False
            return False

        # --- Perk popup (blocks all input until dismissed) ---
        if self.menu_state == MenuState.PERK_POPUP:
            # Any key dismisses the current popup
            if self.perk_popup_queue:
                self.perk_popup_queue.pop(0)
            if self.perk_popup_queue:
                pass  # still more popups to show
            else:
                self.menu_state = self._perk_popup_return_state
                self._perk_popup_return_state = MenuState.NONE
            return False

        # --- Dev item search: intercept ALL input before other handlers ---
        if self.menu_state == MenuState.DEV_ITEM_SELECT:
            return self._handle_dev_item_select_input(action) or False

        # --- Skills / Char sheet toggles (block other menus) ---
        if action_type == "toggle_skills":
            return self._action_toggle_skills(action)

        if self.menu_state == MenuState.SKILLS:
            unlocked_skills = sorted(self.skills.unlocked(), key=lambda s: s.name.lower())
            if not unlocked_skills:
                if action_type in ("close_menu", "toggle_skills"):
                    self.menu_state = MenuState.NONE
                return False

            # Clamp cursor to sorted list bounds
            self.skills_cursor = max(0, min(self.skills_cursor, len(unlocked_skills) - 1))

            if not self.skills_spend_mode:
                if action_type == "move":
                    dy = action.get("dy", 0)
                    self.skills_cursor = (self.skills_cursor + dy) % len(unlocked_skills)
                elif action_type == "confirm_target":
                    self.skills_spend_mode = True
                    self.skills_spend_input = ""
                elif action_type in ("close_menu", "toggle_skills"):
                    self.menu_state = MenuState.NONE
            else:
                if action_type == "select_action" and "digit" in action:
                    self.skills_spend_input += action["digit"]
                elif action_type == "skills_backspace":
                    self.skills_spend_input = self.skills_spend_input[:-1]
                elif action_type == "confirm_target":
                    amount = int(self.skills_spend_input or "0")
                    skill_name = unlocked_skills[self.skills_cursor].name
                    gained = self.skills.spend_on_skill(skill_name, amount)
                    if gained:
                        skill = self.skills.get(skill_name)
                        new_level = skill.level
                        for lvl in range(new_level - gained + 1, new_level + 1):
                            self.messages.append(f"{skill_name} reached level {lvl}!")
                            self._apply_perk(skill_name, lvl)
                        # Show perk popup(s) if any were queued
                        if self.perk_popup_queue:
                            self._perk_popup_return_state = MenuState.SKILLS
                            self.menu_state = MenuState.PERK_POPUP
                    self.skills_spend_mode = False
                    self.skills_spend_input = ""
                elif action_type == "close_menu":
                    self.skills_spend_mode = False
                    self.skills_spend_input = ""
            return False

        if action_type == "open_char_sheet":
            return self._action_toggle_char_sheet(action)

        if self.menu_state == MenuState.CHAR_SHEET:
            if action_type == "close_menu":
                self.menu_state = MenuState.NONE
            elif action.get("char") == "m" or action_type == "raw_char" and action.get("char") == "m":
                self.menu_state = MenuState.MUTATIONS
                self._mutations_scroll = 0
            return False

        if self.menu_state == MenuState.MUTATIONS:
            if action_type == "close_menu":
                self.menu_state = MenuState.CHAR_SHEET
            elif action_type == "move" and action.get("dy", 0) < 0:
                self._mutations_scroll = max(0, self._mutations_scroll - 1)
            elif action_type == "move" and action.get("dy", 0) > 0:
                self._mutations_scroll += 1
            return False

        if action_type == "open_status_effects":
            if self.menu_state == MenuState.NONE:
                self.menu_state = MenuState.STATUS_EFFECTS
                self._status_effects_scroll = 0
            elif self.menu_state == MenuState.STATUS_EFFECTS:
                self.menu_state = MenuState.NONE
            return False

        if self.menu_state == MenuState.STATUS_EFFECTS:
            if action_type == "close_menu":
                self.menu_state = MenuState.NONE
            elif action_type == "move" and action.get("dy", 0) < 0:
                self._status_effects_scroll = max(0, self._status_effects_scroll - 1)
            elif action_type == "move" and action.get("dy", 0) > 0:
                self._status_effects_scroll += 1
            return False

        if action_type == "open_bestiary":
            return self._action_open_bestiary(action)

        if self.menu_state == MenuState.BESTIARY:
            if action_type in ("close_menu", "open_bestiary"):
                self.menu_state = MenuState.NONE
            return False

        if action_type == "toggle_abilities":
            return self._action_toggle_abilities(action)

        if self.menu_state == MenuState.ABILITIES:
            if action_type == "close_menu":
                self.menu_state = MenuState.NONE
                self.selected_ability_index = None
                return False
            return self._handle_abilities_menu_input(action)

        # --- No pre-conversion needed; DESTROY_CONFIRM handler handles Y/N and cursor ---

        # --- Convert number key selections to ring slot selections in ring replacement menu ---
        if self.menu_state == MenuState.RING_REPLACE and action_type == "select_action":
            slot_index = action.get("index")
            if 0 <= slot_index < RING_SLOTS:
                action = {"type": "select_ring_slot", "slot": slot_index}
                action_type = action.get("type")

        # --- Delegate to menu handler if a menu is active ---
        if self.menu_state != MenuState.NONE:
            handler = self._menu_handlers.get(self.menu_state)
            if handler:
                result = handler(action)
                if result and self.running and self.player.alive:
                    self.player.energy -= ENERGY_THRESHOLD
                    self._run_energy_loop()
                return result
            return False

        # --- Cancel channel on any non-wait action ---
        if self._channel is not None and action_type != "wait":
            self._channel_end("Channel cancelled.")

        # --- Normal gameplay dispatch ---
        handler = self._gameplay_handlers.get(action_type)
        if not handler:
            return False

        self._last_action_was_attack = False
        result = handler(action)

        # Energy tick: player spends energy, then run ticks until player can act again
        if result and self.running and self.player.alive:
            # Determine action cost based on type
            if self._last_action_was_attack:
                cost = self.player_attack_cost
            elif action_type == "move" and self._player_just_moved:
                self._player_moved_this_turn = True
                cost = self.player_move_cost
                if self.move_cost_reduction > 0:
                    cost = max(0, cost - self.move_cost_reduction)
                # Momentum (Jaywalking L6): consume 1 stack for free move
                momentum = next(
                    (e for e in self.player.status_effects if getattr(e, 'id', '') == 'momentum'),
                    None,
                )
                if momentum and momentum.stacks > 0:
                    cost = 0
                    momentum.stacks -= 1
                    if momentum.stacks <= 0:
                        momentum.duration = 0  # mark for removal
            else:
                cost = ENERGY_THRESHOLD
            if self.action_cost_mult != 1.0:
                cost = int(cost * self.action_cost_mult)
            self.player.energy -= cost
            self._run_energy_loop()

        return result

    def _run_energy_loop(self):
        """Advance the game clock by ticking energy until the player can act again.

        Each iteration of the while loop is one "tick":
          1. Every living entity gains energy equal to its speed (modified by effects).
          2. All monsters with energy >= ENERGY_THRESHOLD act (sorted by energy desc),
             each subtracting ENERGY_THRESHOLD per action; fast monsters may act multiple
             times if they accumulate >= 2× the threshold in a single tick.
          3. Effects tick once per energy cycle (duration counts down by 1).
        The loop exits when the player has accumulated enough energy to act again.
        """
        self._update_sleeper_stacks()
        while True:
            if not self.player.alive or not self.running:
                break

            # If player has enough energy, check for fear auto-flee or break
            if self.player.energy >= ENERGY_THRESHOLD:
                fear = next(
                    (e for e in self.player.status_effects
                     if getattr(e, 'id', '') == 'fear' and not e.expired),
                    None,
                )
                if fear:
                    self._fear_flee(fear)
                    fear_cost = max(0, min(self.player_move_cost, ENERGY_THRESHOLD) - self.move_cost_reduction)
                    self.player.energy -= fear_cost
                    # Stay in loop — player doesn't get to act
                    continue

                # Speedball: 20% chance to lose a turn (nodding off)
                speedball = next(
                    (e for e in self.player.status_effects
                     if getattr(e, 'id', '') == 'speedball' and not e.expired),
                    None,
                )
                if speedball and random.random() < 0.20:
                    self.player.energy -= ENERGY_THRESHOLD
                    self.messages.append([
                        ("You nod off for a moment...", (200, 150, 255)),
                    ])
                    # Stay in loop — player loses this turn
                    continue

                break  # normal: return control to player

            monsters = list(self.dungeon.get_monsters())
            npcs = list(self.dungeon.get_npcs())
            tick_data = prepare_ai_tick(self.player, self.dungeon, monsters)

            # 1. Distribute energy to all living entities (including NPCs)
            for entity in [self.player] + monsters + npcs:
                if not entity.alive:
                    continue
                gain = float(entity.speed)
                for effect in entity.status_effects:
                    if hasattr(effect, "modify_energy_gain"):
                        gain = effect.modify_energy_gain(gain, entity)
                # Toxicity slows enemies: up to 50% energy reduction at 100 tox
                if entity is not self.player:
                    tox = getattr(entity, "toxicity", 0)
                    if tox > 0:
                        penalty = min(tox, 100) * 0.005  # 0.5% per tox, max 50%
                        gain *= (1.0 - penalty)
                # Hard minimum: entities always gain at least 10 energy/tick
                gain = max(gain, 10.0)
                if entity is self.player:
                    gain += self.player_stats.equipment_energy_per_tick
                    # Meth-Head L3: Tweaker — +10 speed per 25 meth
                    if self.skills.get("Meth-Head").level >= 3:
                        gain += (self.player.meth // 25) * 10
                    # Chemical Warfare L2: Toxic Frenzy — +1 speed per 10 tox (cap 500)
                    if self.skills.get("Chemical Warfare").level >= 2:
                        gain += min(self.player.toxicity, 500) // 10
                entity.energy += gain

            # 2. Process all monsters that have enough energy, highest energy first
            def _monster_min_cost(m):
                return min(
                    getattr(m, "move_cost", 0) or ENERGY_THRESHOLD,
                    getattr(m, "attack_cost", 0) or ENERGY_THRESHOLD,
                )
            acting = sorted(
                [m for m in monsters if m.alive and m.energy >= _monster_min_cost(m)],
                key=lambda m: -m.energy,
            )
            for monster in acting:
                min_cost = _monster_min_cost(monster)
                while monster.alive and monster.energy >= min_cost:
                    action_type = do_ai_turn(monster, self.player, self.dungeon, self, **tick_data)
                    if action_type == "attack":
                        cost = getattr(monster, "attack_cost", 0) or ENERGY_THRESHOLD
                    elif action_type == "move":
                        cost = getattr(monster, "move_cost", 0) or ENERGY_THRESHOLD
                        # Silver spray paint: slip monsters on entry
                        if self.dungeon.spray_paint.get((monster.x, monster.y)) == "silver":
                            if not any(getattr(e, 'id', '') == 'slipped' for e in monster.status_effects):
                                effects.apply_effect(monster, self, "slipped", silent=True)
                    else:
                        cost = ENERGY_THRESHOLD
                    monster.energy -= cost

            # 2b. Process NPCs that have enough energy
            for npc in npcs:
                if npc.alive and npc.energy >= ENERGY_THRESHOLD:
                    do_ai_turn(npc, self.player, self.dungeon, self, **tick_data)
                    npc.energy -= ENERGY_THRESHOLD

            # 3. Tick status effects once per energy cycle
            self.turn += 1
            effects.tick_all_effects(self.player, self)

            # Loitering (Jaywalking L5): track consecutive idle turns
            loiter = next(
                (e for e in self.player.status_effects if getattr(e, 'id', '') == 'loitering_tracker'),
                None,
            )
            if loiter is not None:
                player_acted = self._player_just_moved or self._last_action_was_attack
                if player_acted:
                    loiter.idle_turns = 0
                else:
                    loiter.idle_turns += 1
                    if loiter.idle_turns >= 3:
                        loiter.idle_turns = 0
                        # Grant untargetable
                        effects.apply_effect(self.player, self, "loitering_untargetable", silent=True)
                        # Reset all chasing monsters to IDLE
                        from ai import AIState
                        reset_count = 0
                        for m in self.dungeon.get_monsters():
                            if m.alive and getattr(m, 'ai_state', None) == AIState.CHASING:
                                m.ai_state = AIState.IDLE
                                reset_count += 1
                        self.messages.append([
                            ("Loitering! ", (180, 220, 255)),
                            (f"You fade from notice. {reset_count} enemy(ies) lose track of you.", (150, 200, 255)),
                        ])

            for monster in monsters:
                if monster.alive:
                    effects.tick_all_effects(monster, self)

            # Monster radiation mutations
            import mutations as _mut
            for monster in monsters:
                if monster.alive and getattr(monster, 'radiation', 0) >= 20:
                    _mut.check_monster_mutation(self, monster)

            # Meth decay: -1 meth per 100 turns
            if self.player.meth > 0 and self.turn % 100 == 0:
                self.player.meth -= 1

            # Infection damage: 25/turn at max infection
            if self.player.infection >= self.player.max_infection:
                self.player.take_damage(25)
                self.messages.append([
                    ("Infection! ", (120, 200, 50)),
                    ("You take 25 damage from the infection!", (180, 255, 100)),
                ])
                if not self.player.alive:
                    self.event_bus.emit("entity_died", entity=self.player, killer=None)

            # Rosary passive: grant Divine Shield every 10 turns without one
            if self.neck is not None and "rosary" in (get_item_def(self.neck.item_id) or {}).get("tags", []):
                self._rosary_timer = getattr(self, '_rosary_timer', 0) + 1
                has_ds = any(getattr(e, 'id', '') == 'divine_shield' for e in self.player.status_effects)
                if not has_ds:
                    if self._rosary_timer >= 10:
                        effects.apply_effect(self.player, self, "divine_shield", silent=True)
                        self.messages.append([
                            ("The Rosary glows... ", (212, 175, 55)),
                            ("Divine Shield granted!", (255, 255, 150)),
                        ])
                        self._rosary_timer = 0
                else:
                    self._rosary_timer = 0  # reset while shield is active
            else:
                self._rosary_timer = 0

            # Flagellant's Mask: 1-5 self-damage per turn (can't kill), 10% chance to purge a debuff
            if self.hat is not None and "flagellant" in (get_item_def(self.hat.item_id) or {}).get("tags", []):
                dmg = random.randint(1, 5)
                self.player.hp = max(1, self.player.hp - dmg)
                if random.random() < 0.10:
                    debuffs = [e for e in self.player.status_effects if e.category == "debuff"]
                    if debuffs:
                        target_debuff = random.choice(debuffs)
                        debuff_name = target_debuff.display_name
                        self.player.status_effects = [e for e in self.player.status_effects if e is not target_debuff]
                        target_debuff.expire(self.player, self)
                        self.messages.append([
                            ("Penance! ", (180, 50, 50)),
                            (f"-{dmg} HP. {debuff_name} cleansed!", (200, 150, 150)),
                        ])

            # Thinking Cap: consume 1 skill point, grant 2 real XP to a random unlocked skill
            if self.hat is not None and "thinking_cap" in (get_item_def(self.hat.item_id) or {}).get("tags", []):
                if self.skills.skill_points >= 1:
                    unlocked = [s for s in self.skills.unlocked() if not s.is_maxed()]
                    if unlocked:
                        target_skill = random.choice(unlocked)
                        self.skills.skill_points -= 1
                        levels_gained = target_skill.add_real_exp(2)
                        for lvl in range(target_skill.level - levels_gained + 1, target_skill.level + 1):
                            self.messages.append(f"{target_skill.name} reached level {lvl}!")
                            self._apply_perk(target_skill.name, lvl)

            # Tick ability cooldowns
            for key in list(self.ability_cooldowns):
                self.ability_cooldowns[key] -= 1
                if self.ability_cooldowns[key] <= 0:
                    del self.ability_cooldowns[key]

            # Spec energy regen: +10 every 30 ticks when a spec weapon is equipped
            if self._has_spec_weapon():
                self._spec_energy_counter += 1
                if self._spec_energy_counter >= 30:
                    self._spec_energy_counter = 0
                    if self.spec_energy < 100.0:
                        self.spec_energy = min(100.0, self.spec_energy + 10.0)

            # Static Reserve: regen Chain Lightning charges
            if hasattr(self, '_static_reserve_timer'):
                self._static_reserve_timer += 1
                if self._static_reserve_timer >= 50:
                    self._static_reserve_timer = 0
                    cl = next((a for a in self.player_abilities if a.ability_id == "chain_lightning"), None)
                    if cl and cl.charges_remaining < 3:
                        cl.charges_remaining += 1
                        self.messages.append([("Static Reserve: ", (200, 200, 255)), ("+1 Chain Lightning charge.", (255, 240, 80))])

            # Tick rad bomb crystals
            self._tick_rad_bomb_crystals(monsters)

            # Tick scrap turrets
            self._tick_scrap_turrets(monsters)

            # 4. Fire / toxic creep hazard: affect entities standing on hazard tiles
            for entity in [self.player] + monsters:
                if not entity.alive:
                    continue
                for hazard in self.dungeon.get_entities_at(entity.x, entity.y):
                    ht = getattr(hazard, "hazard_type", None)
                    if ht == "fire":
                        # Pyromania L3 (Neva Burn Out): player immune to fire tiles
                        if entity == self.player:
                            pyro = self.skills.get("Pyromania")
                            if pyro and pyro.level >= 3:
                                break
                        effects.apply_effect(entity, self, "ignite", silent=True)
                        break
                    elif ht == "toxic_creep":
                        tox = getattr(hazard, "hazard_tox_per_turn", 5)
                        self.add_toxicity(entity, tox)
                        break
                    elif ht == "acid_pool":
                        dmg = getattr(hazard, "hazard_damage_per_turn", 3)
                        entity.take_damage(dmg)
                        if entity == self.player:
                            self._gain_catchin_fades_xp(dmg)
                            self.messages.append(f"The acid burns you for {dmg} damage!")
                        if not entity.alive:
                            self.event_bus.emit("entity_died", entity=entity, killer=None)
                        break
                    elif ht == "venom_pool":
                        effects.apply_effect(entity, self, "venom", duration=10, stacks=1, silent=True)
                        if entity == self.player:
                            self.messages.append("The venom pool poisons you!")
                        break
                    elif ht == "web" and entity != self.player:
                        # All spiders walk through webs unaffected
                        _etype = getattr(entity, 'enemy_type', '') or ''
                        if (_etype in _SPIDER_ENEMY_TYPES
                                or (getattr(entity, 'is_summon', False) and entity.ai_type == "spider_hatchling")):
                            break
                        # Apply web_stuck to monsters (player handled in handle_move)
                        if not any(getattr(e, 'id', '') == 'web_stuck'
                                   for e in entity.status_effects):
                            effects.apply_effect(entity, self, "web_stuck",
                                                 silent=True, web_entity=hazard)
                            # Arachnigga XP: +10 when an enemy gets webbed
                            adjusted_xp = round(10 * self.player_stats.xp_multiplier)
                            self.skills.gain_potential_exp(
                                "Arachnigga", adjusted_xp,
                                self.player_stats.effective_book_smarts,
                                briskness=self.player_stats.total_briskness,
                            )
                        break

            # 4a. Orange spray paint: damage entities standing on orange tiles
            _graffiti_lvl = self.skills.get("Graffiti").level
            for entity in [self.player] + monsters:
                if not entity.alive:
                    continue
                if self.dungeon.spray_paint.get((entity.x, entity.y)) == "orange":
                    dmg = 5 + 2 * _graffiti_lvl
                    entity.take_damage(dmg)
                    if entity == self.player:
                        self._gain_catchin_fades_xp(dmg)
                        self.messages.append(f"Orange paint burns you for {dmg} damage!")
                    else:
                        # Graffiti XP: damage dealt
                        adjusted_xp = round(dmg * self.player_stats.xp_multiplier)
                        self.skills.gain_potential_exp(
                            "Graffiti", adjusted_xp,
                            self.player_stats.effective_book_smarts,
                            briskness=self.player_stats.total_briskness,
                        )
                    if not entity.alive:
                        self.event_bus.emit("entity_died", entity=entity, killer=self.player if entity != self.player else None)

            # 4b. Tick timed hazards (decrement duration, remove expired)
            for hazard in list(self.dungeon.entities):
                if getattr(hazard, "entity_type", None) != "hazard":
                    continue
                hd = getattr(hazard, "hazard_duration", 0)
                if hd > 0:
                    hazard.hazard_duration -= 1
                    if hazard.hazard_duration <= 0:
                        self.dungeon.remove_entity(hazard)

            # 4c. Grease tile effects: apply greasy stacks + damage, tick timers
            if self.dungeon.grease_tiles:
                con = self.player_stats.effective_constitution
                df_level = self.skills.get("Deep-Frying").level
                grease_dmg = con // 3 + df_level // 2
                for entity in [self.player] + monsters:
                    if not entity.alive:
                        continue
                    pos = (entity.x, entity.y)
                    if pos not in self.dungeon.grease_tiles:
                        continue
                    if entity == self.player:
                        # Player capped at 3 greasy stacks from grease tiles
                        existing = next((e for e in entity.status_effects if getattr(e, 'id', '') == 'greasy'), None)
                        current_stacks = existing.stacks if existing else 0
                        if current_stacks < 3:
                            effects.apply_effect(entity, self, "greasy", duration=50, stacks=1, silent=True)
                    else:
                        # Enemies get +1 greasy stack and take damage
                        effects.apply_effect(entity, self, "greasy", duration=50, stacks=1, silent=True)
                        if grease_dmg > 0:
                            entity.take_damage(grease_dmg)
                            if not entity.alive:
                                self.event_bus.emit("entity_died", entity=entity, killer=self.player)
                # Tick grease tile timers
                expired = [pos for pos, t in self.dungeon.grease_tiles.items() if t <= 1]
                for pos in expired:
                    del self.dungeon.grease_tiles[pos]
                for pos in self.dungeon.grease_tiles:
                    self.dungeon.grease_tiles[pos] -= 1

            # 5. Radiation mutation check
            if self.player.alive:
                import mutations
                mutations.check_mutation(self)

            if not self.player.alive:
                self.game_over = True
                self.menu_state = MenuState.DEATH_SCREEN
                self.death_screen_cursor = 0
                return

    # ------------------------------------------------------------------
    # Gameplay action handlers
    # ------------------------------------------------------------------

    def _action_move(self, action):
        return self.handle_move(action["dx"], action["dy"])

    def _action_wait(self, _action):
        """Consume a turn without performing any action.
        If channeling, continue the channel instead."""
        if self._channel is not None:
            return self._channel_tick()
        return True

    @property
    def channel_info(self) -> tuple[str, int, tuple[int,int,int]] | None:
        """Return (display_name, turns_remaining, color) if channeling, else None."""
        if self._channel is None:
            return None
        aid = self._channel["ability_id"]
        color = _CHANNEL_COLORS.get(aid, (100, 200, 255))
        return (_CHANNEL_DISPLAY_NAMES.get(aid, aid), self._channel["turns_remaining"], color)

    def start_channel(self, ability_id: str, turns: int, params: dict):
        """Begin channeling an ability. The first tick fires immediately;
        subsequent ticks fire when the player presses Wait."""
        self._channel = {
            "ability_id": ability_id,
            "turns_remaining": turns,
            "params": params,
        }

    def _channel_tick(self) -> bool:
        """Fire one tick of the active channel. Returns True (turn consumed)."""
        ch = self._channel
        if ch is None:
            return True
        ability_id = ch["ability_id"]
        params = ch["params"]

        # Fire the channeled effect
        if ability_id == "ray_of_frost":
            from spells import _ray_of_frost_beam
            dx, dy = params["dx"], params["dy"]
            _ray_of_frost_beam(self, dx, dy)

        if ability_id == "discharge":
            from abilities import _discharge_tick
            tick_num = params["tick_num"]
            _discharge_tick(self, tick_num)
            params["tick_num"] = tick_num + 1

        ch["turns_remaining"] -= 1
        if ch["turns_remaining"] <= 0:
            self._channel_end("Channel complete.")
        elif ch["turns_remaining"] == 1:
            name = _CHANNEL_DISPLAY_NAMES.get(ability_id, ability_id)
            self.messages.append([
                ("Final tick! ", (255, 220, 100)),
                (f"Press Wait to finish {name}.", (220, 200, 150)),
            ])
        else:
            self.messages.append([
                ("Channeling... ", (100, 200, 255)),
                (f"{ch['turns_remaining']} turn(s) remaining. Wait to continue.", (180, 200, 220)),
            ])
        return True

    def _channel_end(self, reason: str = "Channel ended."):
        """End the active channel."""
        if self._channel is not None:
            self._channel = None
            self.messages.append([(reason, (180, 180, 200))])

    def _channel_interrupt_on_damage(self):
        """Called when the player takes damage while channeling.
        25% chance to break the channel."""
        if self._channel is None:
            return
        import random as _rng
        if _rng.random() < 0.25:
            self._channel_end("Your channel is interrupted by the hit!")

    def _action_open_log(self, _action):
        self.menu_state = MenuState.LOG
        self.log_scroll = 0
        return False

    def _action_open_bestiary(self, _action):
        self.menu_state = MenuState.BESTIARY
        return False

    def _action_open_perks_menu(self, _action):
        self.menu_state = MenuState.PERKS
        self.perks_scroll = 0
        self.perk_cursor = 0
        return False

    # ------------------------------------------------------------------
    # Dev tools (DEV_MODE only)
    # ------------------------------------------------------------------

    # Dev menu option indices
    _DEV_OPTIONS = [
        "add_potential_xp",
        "spawn_item",
        "kill_in_view",
        "toggle_invincible",
        "reveal_map",
        "add_cash",
        "full_heal",
        "teleport_stairs",
        "teleport_floor",
        "add_stats",
        "spawn_crack_consumables",
        "spawn_meth_consumables",
    ]

    def _action_open_dev_menu(self, _action):
        if not DEV_MODE:
            return False
        self.menu_state = MenuState.DEV_MENU
        return False

    def _handle_dev_menu_input(self, action):
        """Handle input in the dev menu overlay."""
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            return False

        if action_type == "open_dev_menu":
            self.menu_state = MenuState.NONE
            return False

        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            if dy != 0 and dx == 0:
                self.dev_menu_cursor = (self.dev_menu_cursor + dy) % len(self._DEV_OPTIONS)
            return False

        if action_type == "confirm_target":
            self._dev_execute(self._DEV_OPTIONS[self.dev_menu_cursor])
            return False

        if action_type == "select_action":
            digit = action.get("digit")
            if digit is not None:
                # digit is a string "0"-"9"; map 1-9 → index 0-8, 0 → index 9
                idx = (int(digit) - 1) % 10
                if 0 <= idx < len(self._DEV_OPTIONS):
                    self._dev_execute(self._DEV_OPTIONS[idx])
            return False

        return False

    def _dev_execute(self, option: str):
        """Execute a dev menu action by option key."""
        if option == "add_potential_xp":
            from skills import SKILL_NAMES
            for name in SKILL_NAMES:
                self.skills.gain_potential_exp(
                    name, 500000,
                    self.player_stats.effective_book_smarts,
                    briskness=self.player_stats.total_briskness,
                )
            self.messages.append("[DEV] +500,000 potential XP added to all skills.")

        elif option == "spawn_item":
            from items import ITEM_DEFS
            # Build sorted item list: static named items first, then generated ones
            static_ids = [
                k for k in ITEM_DEFS
                if not any(k.startswith(p) for p in ("minor_ring_", "greater_ring_", "divine_ring_", "advanced_ring_", "chain_", "jordans_"))
            ]
            generated_ids = [
                k for k in ITEM_DEFS
                if any(k.startswith(p) for p in ("minor_ring_", "greater_ring_", "divine_ring_", "advanced_ring_", "chain_", "jordans_"))
            ]
            self.dev_item_list = sorted(static_ids) + sorted(generated_ids)
            self.dev_item_search = ""
            self.dev_item_filtered = self.dev_item_list[:]
            self.dev_item_cursor = 0
            self.dev_item_scroll = 0
            self.menu_state = MenuState.DEV_ITEM_SELECT
            return  # don't close dev menu, switching to sub-menu

        elif option == "kill_in_view":
            killed = 0
            for monster in list(self.dungeon.get_monsters()):
                if monster.alive and self.dungeon.visible[monster.y, monster.x]:
                    monster.alive = False
                    monster.hp = 0
                    self.event_bus.emit("entity_died", entity=monster, killer=self.player)
                    killed += 1
            self.messages.append(f"[DEV] Killed {killed} monster(s) in view.")

        elif option == "toggle_invincible":
            self.player.dev_invincible = not self.player.dev_invincible
            state = "ON" if self.player.dev_invincible else "OFF"
            self.messages.append(f"[DEV] Invincibility: {state}")

        elif option == "reveal_map":
            import numpy as np
            self.dungeon.explored[:] = True
            self.messages.append("[DEV] Entire map revealed.")

        elif option == "add_cash":
            self.cash += 1000
            self.messages.append("[DEV] +$1,000 cash.")

        elif option == "full_heal":
            self.player.hp = self.player.max_hp
            self.player.armor = self.player.max_armor
            self.messages.append("[DEV] HP and armor fully restored.")

        elif option == "teleport_stairs":
            stair = next(
                (e for e in self.dungeon.entities if e.entity_type == "staircase"),
                None,
            )
            if stair:
                self.player.x, self.player.y = stair.x, stair.y
                self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)  # DEV: skip landmark announce
                self.messages.append("[DEV] Teleported to stairs.")
            else:
                self.messages.append("[DEV] No stairs on this floor.")

        elif option == "teleport_floor":
            self.dev_floor_cursor = self.current_floor
            self.menu_state = MenuState.DEV_FLOOR_SELECT
            return  # don't close dev menu, switching to sub-menu

        elif option == "add_stats":
            for stat in ("constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"):
                setattr(self.player_stats, stat, getattr(self.player_stats, stat) + 5)
                self.player_stats._base[stat] = self.player_stats._base.get(stat, 0) + 5
            self.player.max_hp = self.player_stats.max_hp
            self.player.hp = min(self.player.hp, self.player.max_hp)
            self.messages.append("[DEV] +5 to all base stats.")

        elif option == "spawn_crack_consumables":
            from loot import pick_random_consumable
            for _ in range(5):
                item_id, strain = pick_random_consumable("crack_den")
                self._add_item_to_inventory(item_id, strain=strain)
            self.messages.append("[DEV] Spawned 5 random Crack Den consumables.")

        elif option == "spawn_meth_consumables":
            from loot import pick_random_consumable
            for _ in range(5):
                item_id, strain = pick_random_consumable("meth_lab")
                self._add_item_to_inventory(item_id, strain=strain)
            self.messages.append("[DEV] Spawned 5 random Meth Lab consumables.")

        self.menu_state = MenuState.NONE

    def _dev_item_apply_search(self):
        """Filter dev_item_list by search string, matching item name or id."""
        if not self.dev_item_search:
            self.dev_item_filtered = self.dev_item_list[:]
        else:
            query = self.dev_item_search.lower()
            filtered = []
            for item_id in self.dev_item_list:
                defn = get_item_def(item_id)
                name = defn.get("name", item_id).lower() if defn else item_id.lower()
                if query in name or query in item_id.lower():
                    filtered.append(item_id)
            self.dev_item_filtered = filtered
        self.dev_item_cursor = 0
        self.dev_item_scroll = 0

    def _handle_dev_item_select_input(self, action):
        """Handle input in the dev item spawn picker with search."""
        action_type = action.get("type")
        items = self.dev_item_filtered
        n = len(items)

        if action_type == "close_menu":
            self.dev_item_search = ""
            self.menu_state = MenuState.DEV_MENU
            return False

        if action_type == "open_dev_menu":
            self.dev_item_search = ""
            self.menu_state = MenuState.NONE
            return False

        # Typing: map all key-bound actions back to characters for search
        _ACTION_TO_CHAR = {
            "toggle_skills": "s", "open_char_sheet": "c", "open_equipment": "e",
            "drop_item": "d", "fire_gun": "f", "start_entity_targeting": "r",
            "toggle_abilities": "a", "open_bestiary": "b", "open_perks_menu": "p",
            "open_log": "l", "wait": ".", "item_use": " ", "look": ";",
            "autoexplore": "/",
            "swap_primary_gun": "f", "reload_gun": "r", "destroy_item": "d",
        }
        if action_type == "raw_char":
            ch = action.get("char", "")
            if ch:
                self.dev_item_search += ch
                self._dev_item_apply_search()
            return False

        if action_type in _ACTION_TO_CHAR:
            ch = _ACTION_TO_CHAR[action_type]
            if ch.isalnum() or ch in ".-_ ":
                self.dev_item_search += ch
                self._dev_item_apply_search()
            return False

        if action_type == "select_item":
            idx = action.get("index", 0)
            from config import INVENTORY_KEYS
            if 0 <= idx < len(INVENTORY_KEYS):
                self.dev_item_search += INVENTORY_KEYS[idx].lower()
                self._dev_item_apply_search()
            return False

        if action_type == "select_action":
            num = action.get("index", -1)
            if 0 <= num <= 9:
                self.dev_item_search += str(num)
                self._dev_item_apply_search()
            return False

        if action_type == "skills_backspace":
            if self.dev_item_search:
                self.dev_item_search = self.dev_item_search[:-1]
                self._dev_item_apply_search()
            return False

        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            if dy != 0 and dx == 0:
                self.dev_item_cursor = max(0, min(n - 1, self.dev_item_cursor + dy))
            return False

        if action_type == "confirm_target":
            if items:
                item_id = items[self.dev_item_cursor]
                entity = Entity(**create_item_entity(item_id, 0, 0))
                self.player.inventory.append(entity)
                self._sort_inventory()
                from items import get_item_def
                defn = get_item_def(item_id)
                name = defn.get("name", item_id) if defn else item_id
                self.messages.append(f"[DEV] Added {name} to inventory.")
            self.dev_item_search = ""
            self.menu_state = MenuState.DEV_MENU
            return False

        return False

    def _handle_dev_floor_select_input(self, action):
        """Handle input in the dev floor teleport picker."""
        action_type = action.get("type")
        n = self.total_floors

        if action_type == "close_menu":
            self.menu_state = MenuState.DEV_MENU
            return False

        if action_type == "open_dev_menu":
            self.menu_state = MenuState.NONE
            return False

        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            if dy != 0 and dx == 0:
                self.dev_floor_cursor = max(0, min(n - 1, self.dev_floor_cursor + dy))
            return False

        if action_type == "confirm_target":
            self._dev_teleport_to_floor(self.dev_floor_cursor)
            self.menu_state = MenuState.NONE
            return False

        return False

    def _handle_dev_skill_select_input(self, action):
        """Handle input in the dev skill level-up picker."""
        from skills import SKILL_NAMES, MAX_LEVEL
        action_type = action.get("type")
        n = len(SKILL_NAMES)

        if action_type == "close_menu":
            self.menu_state = MenuState.DEV_MENU
            return False

        if action_type == "open_dev_menu":
            self.menu_state = MenuState.NONE
            return False

        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            if dy != 0 and dx == 0:
                self.dev_skill_cursor = max(0, min(n - 1, self.dev_skill_cursor + dy))
            return False

        if action_type == "confirm_target":
            skill_name = SKILL_NAMES[self.dev_skill_cursor]
            skill = self.skills.get(skill_name)
            if skill.level >= MAX_LEVEL:
                self.messages.append(f"[DEV] {skill_name} is already max level.")
            else:
                old_level = skill.level
                skill.level += 1
                self._apply_perk(skill_name, skill.level)
                self.messages.append(
                    f"[DEV] {skill_name} leveled up: {old_level} → {skill.level}"
                )
            return False

        return False

    def _dev_teleport_to_floor(self, target_floor: int):
        """Teleport the player to a specific global floor index."""
        if target_floor == self.current_floor:
            self.messages.append("[DEV] Already on this floor.")
            return

        zone_key, zone_floor, display_name, zone_type = get_zone_for_floor(target_floor)

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        if target_floor not in self.dungeons:
            event_id = self.get_floor_event(target_floor)
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key, floor_event=event_id, floor_num=zone_floor)
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            new_dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned, floor_event=self.get_floor_event(target_floor))
            self.dungeons[target_floor] = new_dungeon
        else:
            new_dungeon = self.dungeons[target_floor]
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            if self.player not in new_dungeon.entities:
                new_dungeon.entities.insert(0, self.player)

        self.current_floor = target_floor
        self.dungeon = new_dungeon
        self.dungeon.first_kill_happened = False
        self.dungeon.female_kill_happened = False
        if target_floor not in self.visited_rooms:
            self.visited_rooms[target_floor] = {0}
        self._compute_fov()
        self.player.energy = ENERGY_THRESHOLD

        # Track zone first visit
        self.zones_visited.add(zone_key)

        zone_total = get_zone_total_floors(zone_key)
        if zone_type == "pseudozone":
            self.messages.append(f"[DEV] Teleported to {display_name}.")
        else:
            self.messages.append(
                f"[DEV] Teleported to {display_name} - Floor {zone_floor + 1}/{zone_total}."
            )

    def _handle_perks_input(self, action):
        """Handle input in the perks overlay. UP/DOWN move cursor; anything else closes."""
        from render import count_perks_menu_selectables
        action_type = action.get("type")
        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            n_sel = count_perks_menu_selectables(self)
            if dy == -1 and dx == 0:
                self.perk_cursor = max(0, self.perk_cursor - 1)
            elif dy == 1 and dx == 0:
                if n_sel > 0:
                    self.perk_cursor = min(n_sel - 1, self.perk_cursor + 1)
        else:
            self.menu_state = MenuState.NONE
        return False

    # ------------------------------------------------------------------
    # Look mode
    # ------------------------------------------------------------------

    def _action_look(self, _action):
        """Enter Look mode — free cursor targeting for tile inspection."""
        self.look_cursor = [self.player.x, self.player.y]
        self.menu_state = MenuState.LOOK_TARGETING
        return False

    def _handle_look_targeting(self, action):
        """Handle input while in Look targeting mode."""
        from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            return False

        if action_type == "move":
            dx = action.get("dx", 0)
            dy = action.get("dy", 0)
            self.look_cursor[0] = max(0, min(DUNGEON_WIDTH - 1, self.look_cursor[0] + dx))
            self.look_cursor[1] = max(0, min(DUNGEON_HEIGHT - 1, self.look_cursor[1] + dy))
            return False

        if action_type == "confirm_target":
            self._build_look_info()
            self.menu_state = MenuState.LOOK_INFO
            return False

        return False

    def _handle_look_info(self, action):
        """Any key dismisses the look info popup, returning to look cursor mode."""
        self.menu_state = MenuState.LOOK_TARGETING
        return False

    # Settings menu layout: display modes + actions
    SETTINGS_ACTIONS = [
        {"label": "Save Game", "action": "save_game"},
        {"label": "Save & Exit to Menu", "action": "exit_to_menu"},
    ]

    def _handle_settings_input(self, action):
        """Handle input for the settings/display menu."""
        action_type = action.get("type")
        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            return False
        n_display = len(self.DISPLAY_MODES)
        n_total = n_display + len(self.SETTINGS_ACTIONS)
        if action_type == "move":
            dy = action.get("dy", 0)
            if dy != 0:
                self.settings_cursor = (self.settings_cursor + dy) % n_total
            return False
        if action_type in ("confirm_target", "item_use"):
            if self.settings_cursor < n_display:
                self._apply_display_mode(self.settings_cursor)
            else:
                act_idx = self.settings_cursor - n_display
                act = self.SETTINGS_ACTIONS[act_idx]
                if act["action"] == "save_game":
                    self._do_save_game()
                elif act["action"] == "exit_to_menu":
                    self._do_save_game()
                    self.running = False
            return False
        return False

    def _do_save_game(self):
        """Save the game to disk."""
        from save_system import save_game
        try:
            save_game(self)
            self.messages.append([("Game saved.", (100, 255, 100))])
        except Exception as e:
            self.messages.append([("Save failed: ", (255, 100, 100)), (str(e), (255, 200, 200))])
        self.menu_state = MenuState.NONE

    def _apply_display_mode(self, index: int):
        """Apply a display mode preset by changing the SDL window."""
        from tcod._internal import lib as _sdl_lib
        ctx = getattr(self, 'tcod_context', None)
        if ctx is None:
            return
        mode = self.DISPLAY_MODES[index]
        self.current_display_mode = index
        try:
            wp = ctx.sdl_window.p  # raw SDL_Window pointer
            w, h = mode["width"], mode["height"]
            if mode["flags"] == "borderless":
                _sdl_lib.SDL_SetWindowBordered(wp, False)
                _sdl_lib.SDL_SetWindowSize(wp, w, h)
                _sdl_lib.SDL_SetWindowPosition(wp, 0, 0)
            else:
                _sdl_lib.SDL_SetWindowBordered(wp, True)
                _sdl_lib.SDL_SetWindowSize(wp, w, h)
                _sdl_lib.SDL_SetWindowPosition(wp, _sdl_lib.SDL_WINDOWPOS_CENTERED,
                                                   _sdl_lib.SDL_WINDOWPOS_CENTERED)
            self.messages.append(f"Display: {mode['label']}")
        except Exception as e:
            self.messages.append(f"Display change failed: {e}")
        self.menu_state = MenuState.NONE

    def _build_look_info(self):
        """Build description lines for the tile under the look cursor."""
        from items import generate_examine_lines, build_inventory_display_name
        from config import TILE_FLOOR

        lx, ly = self.look_cursor
        lines = []

        C_LABEL  = (180, 180, 220)
        C_VALUE  = (255, 255, 200)
        C_GOOD   = (100, 220, 100)
        C_BAD    = (255, 100, 100)
        C_INFO   = (200, 200, 200)
        C_ENEMY  = (255, 140, 140)
        C_BUFF   = (100, 200, 255)
        C_DEBUFF = (255, 130, 80)

        is_visible = bool(self.dungeon.visible[ly, lx])
        is_explored = bool(self.dungeon.explored[ly, lx])

        if not is_explored:
            self.look_info_title = "Unknown"
            self.look_info_lines = [[("You haven't explored this area.", C_INFO)]]
            return

        tile = self.dungeon.tiles[ly][lx]
        tile_name = "Floor" if tile == TILE_FLOOR else "Wall"

        if not is_visible:
            self.look_info_title = f"{tile_name} (not visible)"
            self.look_info_lines = [[("This tile is not in your field of view.", C_INFO)]]
            return

        entities = self.dungeon.get_entities_at(lx, ly)
        is_player_tile = (self.player.x == lx and self.player.y == ly)

        if not entities and not is_player_tile:
            self.look_info_title = tile_name
            self.look_info_lines = [[("Nothing here.", C_INFO)]]
            return

        title = tile_name

        if is_player_tile:
            lines.append([("You", C_GOOD)])

        for e in entities:
            if e.entity_type == "monster" and e.alive:
                if lines:
                    lines.append([])  # blank separator
                gender = getattr(e, 'gender', None)
                gender_tag = f" ({gender[0].upper()})" if gender else ""
                lines.append([(f"{e.name}{gender_tag}", C_ENEMY)])

                # Wound level
                hp_pct = e.hp / e.max_hp if e.max_hp > 0 else 0
                if hp_pct >= 1.0:
                    wound, wound_color = "Unhurt", C_GOOD
                elif hp_pct > 0.66:
                    wound, wound_color = "Light Wounds", C_VALUE
                elif hp_pct > 0.33:
                    wound, wound_color = "Medium Wounds", C_DEBUFF
                elif hp_pct > 0.15:
                    wound, wound_color = "Heavy Wounds", C_BAD
                else:
                    wound, wound_color = "Almost Dead", (255, 50, 50)
                lines.append([("  Condition: ", C_LABEL), (wound, wound_color)])

                # Status effects
                if e.status_effects:
                    parts = [("  Effects: ", C_LABEL)]
                    for i, eff in enumerate(e.status_effects):
                        if i > 0:
                            parts.append((", ", C_INFO))
                        color = C_BUFF if eff.category == "buff" else C_DEBUFF
                        parts.append((eff.display_name, color))
                    lines.append(parts)

                # Status icon legend (matches SDL overlay icons)
                _ICON_MAP = {
                    'chill':        ('C', (100, 180, 255), 'Chill'),
                    'shocked':      ('S', (255, 255, 60),  'Shocked'),
                    'ignite':       ('I', (255, 120, 30),  'Ignite'),
                    'stun':         ('!', (255, 255, 255), 'Stunned'),
                    'fear':         ('F', (180, 80, 255),  'Feared'),
                    'snipers_mark': ('M', (255, 60, 60),   "Sniper's Mark"),
                }
                icon_parts = []
                for eff in e.status_effects:
                    eff_id = getattr(eff, 'id', '')
                    entry = _ICON_MAP.get(eff_id)
                    if entry:
                        letter, lcolor, label = entry
                        icon_parts.append((letter, lcolor, label))
                rad = getattr(e, 'radiation', 0)
                if rad > 0:
                    rc = (255, 60, 60) if rad >= 150 else (255, 255, 60) if rad >= 75 else (60, 255, 60)
                    icon_parts.append(('R', rc, f'Radiation ({rad})'))
                tox = getattr(e, 'toxicity', 0)
                if tox > 0:
                    tc = (255, 60, 60) if tox >= 100 else (255, 255, 60) if tox >= 50 else (60, 255, 60)
                    icon_parts.append(('T', tc, f'Toxicity ({tox})'))
                if icon_parts:
                    legend = [("  Icons: ", C_LABEL)]
                    for j, (letter, lcolor, label) in enumerate(icon_parts):
                        if j > 0:
                            legend.append((" ", C_INFO))
                        legend.append((letter, lcolor))
                        legend.append((f"={label}", C_INFO))
                    lines.append(legend)

                title = e.name

            elif e.entity_type == "item":
                if lines:
                    lines.append([])
                display = build_inventory_display_name(
                    e.item_id, getattr(e, "strain", None),
                    getattr(e, "quantity", 1),
                    prefix=getattr(e, "prefix", None),
                    charges=getattr(e, "charges", None),
                    max_charges=getattr(e, "max_charges", None),
                )
                lines.append([(display, C_VALUE)])
                exam_lines = generate_examine_lines(e.item_id, self)
                lines.extend(exam_lines)
                if title == tile_name:
                    title = display

            elif e.entity_type == "cash":
                if lines:
                    lines.append([])
                lines.append([(e.name, (255, 215, 0))])

            elif e.entity_type == "hazard":
                if lines:
                    lines.append([])
                lines.append([(e.name, C_DEBUFF)])

            elif e.entity_type == "staircase":
                if lines:
                    lines.append([])
                lines.append([(e.name, (255, 220, 80))])
                title = e.name

        # Clean up leading empty separators
        while lines and lines[0] == []:
            lines.pop(0)

        self.look_info_title = title
        self.look_info_lines = lines if lines else [[("Nothing of note.", C_INFO)]]

    def _apply_perk(self, skill_name: str, level: int) -> None:
        """Apply the perk for skill_name at the given level (1-10)."""
        from skills import get_perk
        perk = get_perk(skill_name, level)
        if not perk:
            return
        name = perk["name"]
        self.messages.append(f"  Perk unlocked: {name}")

        # Queue popup for non-placeholder perks
        if perk.get("perk_type") != "none":
            self.perk_popup_queue.append({
                "skill_name": skill_name,
                "level": level,
                "perk": perk,
            })

        if perk["perk_type"] == "stat" and perk.get("effect"):
            ps = self.player_stats
            stat_msgs = []
            for stat, amount in perk["effect"].items():
                setattr(ps, stat, getattr(ps, stat) + amount)
                if stat in ps._base:
                    ps._base[stat] = getattr(ps, stat)
                if stat == "constitution":
                    self.player.max_hp += 10 * amount
                    self.player.heal(10 * amount)
                label = stat.replace("_", " ").title()
                sign = "+" if amount >= 0 else ""
                stat_msgs.append(f"{sign}{amount} {label}")
            self.messages.append(f"  [{name}] {', '.join(stat_msgs)}")

        if name == "Spectral Paper":
            self._add_item_to_inventory("spectral_paper")
            self.messages.append("  [Spectral Paper] A ghostly rolling paper materializes in your inventory!")

        if name == "Nutrient Producer":
            self._add_item_to_inventory("nutrient_producer")
            self.messages.append("  [Nutrient Producer] A strange device materializes in your inventory. Combine it with any consumable to produce RadBars!")

        if name == "Emission":
            self.grant_ability("emission")
            self.messages.append("  [Emission] Irradiate all visible enemies with your radiation! (1/floor)")

        if name == "Sniper's Mark":
            self.grant_ability("snipers_mark")
            self.messages.append("  [Sniper's Mark] Mark an enemy to take 10% more damage! (1/floor, refunds on kill)")

        if name == "Bitch Slap":
            self.grant_ability("black_eye_slap")
            self.messages.append("  [Bitch Slap] You learn to slap enemies senseless!")

        if name == "Black Eye":
            self.messages.append("  [Black Eye] Unarmed attacks now have a 10% chance to stun enemies!")

        if name == "Victory Rush":
            self.grant_ability("victory_rush")
            self.grant_ability_charges("victory_rush", 1)
            self.messages.append("  [Victory Rush] Gain 1 charge. Kills grant charges. Activate for lucky crit + 25% heal!")

        if name == "Bash":
            self.grant_ability("bash")
            self.messages.append("  [Bash] You learn to send enemies flying with your beating weapon!")

        if name == "Crit+":
            self.crit_multiplier += 1
            self.messages.append(f"  [Crit+] Your critical hits now deal {self.crit_multiplier}x damage!")

        if name == "Aftershock":
            self.messages.append("  [Aftershock] Critical hits with blunt weapons empower your next 3 attacks!")

        if name == "Overkill":
            self.messages.append("  [Overkill] Excess damage from blunt weapon kills splashes to nearby enemies!")

        if name == "Colossus":
            self.grant_ability("colossus")
            self.messages.append("  [Colossus] Toggle between Wrecking (+dmg) and Fortress (+DR, counter) stances!")

        if name == "Gouge":
            self.grant_ability("gouge")
            self.messages.append("  [Gouge] You learn to gouge enemies with your blade!")

        if name == "Whirlwind":
            self.grant_ability("whirlwind")
            self.messages.append("  [Whirlwind] Slash all adjacent enemies at once!")

        if name == "Fire!":
            self.grant_ability("place_fire")
            ps = self.player_stats
            ps.constitution += 2
            ps._base["constitution"] = ps.constitution
            self.player.max_hp += 20
            self.player.heal(20)
            self.messages.append("  [Fire!] +2 Constitution. Spawn a line of fire once per floor!")

        if name == "Ignite":
            self.grant_ability("ignite_spell")
            self.messages.append("  [Ignite] You can now ignite enemies from a distance!")

        if name == "Spell Retention":
            self.messages.append("  [Spell Retention] 15% chance to preserve spell charges on cast!")

        if name == "Spell Echo":
            self.messages.append("  [Spell Echo] 15% chance for spells to fire again at 50% damage! Can chain!")

        if name == "Spellweaver":
            self.messages.append("  [Spellweaver] Alternate between different spells for +30% damage!")

        if name == "Throw Bottle":
            self.grant_ability_charges("throw_bottle", 1)

        if name == "Air Jordans":
            self.move_cost_reduction += 10
            self.messages.append("  [Air Jordans] Your kicks feel lighter. Move cost -10 energy.")

        if name == "Dash":
            self.grant_ability("dash")
            self.messages.append("  [Dash] You can now dash up to 2 tiles instantly!")

        if name == "Airer Jordans":
            self.player.speed += 10
            self.messages.append(f"  [Airer Jordans] Your speed increases. (+10 speed, now {self.player.speed})")

        if name == "Shortcut":
            self.grant_ability("shortcut")
            self.messages.append("  [Shortcut] Target an explored tile to recall there after 2 turns! 2/floor.")

        if name == "Loitering":
            effects.apply_effect(self.player, self, "loitering_tracker", silent=True)
            self.messages.append("  [Loitering] Stand still 3 turns to become untargetable and reset enemy aggro!")

        if name == "Momentum":
            self.messages.append("  [Momentum] 40% on melee hit: gain a free move stack!")

        if name == "Charged Up":
            self.player.speed += 10

        if name == "Volt Dash":
            self.grant_ability("volt_dash")
            self.messages.append("  [Volt Dash] Blink through enemies in a bolt of lightning! 4/floor.")

        if name == "Discharge":
            self.grant_ability("discharge")
            self.messages.append("  [Discharge] Channel a devastating electrical storm! 25t cooldown.")

        if name == "Elemental Staves":
            import random as _rng
            # Grant one staff matching the highest elemental skill (random on tie)
            elem_skills = [
                ("Pyromania", "staff_of_fire", "Staff of Fire"),
                ("Cryomancy", "staff_of_ice", "Staff of Ice"),
                ("Electrodynamics", "staff_of_lightning", "Staff of Lightning"),
            ]
            best_level = max(self.skills.get(s).level for s, _, _ in elem_skills)
            tied = [(sid, sname) for s, sid, sname in elem_skills
                    if self.skills.get(s).level == best_level]
            staff_id, staff_name = _rng.choice(tied)
            self._add_item_to_inventory(staff_id)
            self.messages.append(f"  [Elemental Staves] You receive a {staff_name}! Equip it and press F to fire.")

        if name == "Chromatic Orb":
            self.grant_ability("chromatic_orb")
            self.messages.append("  [Chromatic Orb] Hurl a random-element orb! Damage scales with elemental skill levels. 20t cooldown.")

        if name == "Arcane Flux":
            self.arcane_flux_active = True
            self.messages.append("  [Arcane Flux] +10% charge preservation. Charge preservation now also negates spell cooldowns!")

        if name == "Static Reserve":
            self.grant_ability_charges("chain_lightning", 3)
            self._static_reserve_timer = 0
            self.messages.append("  [Static Reserve] +3 Chain Lightning charges. Regen 1 charge every 50 turns while below 3.")

        if name == "Reject the Poison":
            self.player_stats.tox_resistance += 20
            self.messages.append("  [Reject the Poison] +20% tox resistance. Resisted tox builds Purity → temp HP!")

        if name == "Whitewash":
            self.grant_ability("whitewash")
            self.messages.append("  [Whitewash] 1/floor: consume half your toxicity as temp HP.")

        if name == "Fry Shot":
            self.grant_ability("fry_shot")
            self.messages.append("  [Fry Shot] You can now hurl hot grease at enemies within 4 tiles!")

        if name == "Oil Dump":
            self.grant_ability("oil_dump")
            self.messages.append("  [Oil Dump] Dump oil in a radius-3 area. Enemies get greased, floor becomes a grease pool!")

        if name == "Hair of the Dog":
            self.messages.append("  [Hair of the Dog] 30% chance for drink buffs to reapply when they expire!")

        if name == "Liquid Courage":
            self.messages.append("  [Liquid Courage] +10% melee damage and +3% crit per drink stack while drinking!")

        if name == "Chop Shop":
            ps = self.player_stats
            ps.swagger += 2
            ps._base["swagger"] = ps.swagger
            ps.street_smarts += 2
            ps._base["street_smarts"] = ps.street_smarts
            self.messages.append("  [Chop Shop] +2 Swagger, +2 Street Smarts.")

        if name == "Nigga Armor":
            ps = self.player_stats
            ps.swagger += 2
            ps._base["swagger"] = ps.swagger
            ps.street_smarts += 2
            ps._base["street_smarts"] = ps.street_smarts
            self.messages.append("  [Nigga Armor] +2 Swagger, +2 Street Smarts.")

        if name == "Pickpocket":
            self.grant_ability("pickpocket")
            ps = self.player_stats
            ps.street_smarts += 2
            ps._base["street_smarts"] = ps.street_smarts
            self.messages.append("  [Pickpocket] +2 Street Smarts. You can now pickpocket adjacent enemies for cash!")

        if name == "Sleight of Hand":
            ps = self.player_stats
            ps.street_smarts += 2
            ps._base["street_smarts"] = ps.street_smarts
            self.messages.append("  [Sleight of Hand] +2 Street Smarts. Pickpocket now distracts enemies, causing their next attack to miss!")

        if name == "Milk From The Store":
            self.grant_ability("milk_from_the_store")
            ps = self.player_stats
            for stat in ("constitution", "strength", "street_smarts", "book_smarts", "tolerance", "swagger"):
                setattr(ps, stat, getattr(ps, stat) + 1)
                ps._base[stat] = getattr(ps, stat)
            self.player.max_hp += 10
            self.player.heal(10)
            self.messages.append("  [Milk From The Store] +1 all stats. Activate to double all stats for 10 turns! (3/floor)")

        if name == "Toxic Harvest":
            self.grant_ability("toxic_harvest")
            self.messages.append("  [Toxic Harvest] Activate to gain toxicity from kills for 10 turns!")

        if name == "Toxic Frenzy":
            self.messages.append("  [Toxic Frenzy] Your toxicity fuels your fury! +damage and +speed scaling with tox.")

        if name == "Scarred Tissue":
            self.messages.append("  [Scarred Tissue] Bad mutations now also grant +1 to a random stat.")

        if name == "Favorable Odds":
            self.player_stats.good_mutation_multiplier += 0.50
            self.messages.append("  [Favorable Odds] +50% good mutation chance multiplier.")

        if name == "Shed":
            self.grant_ability("shed")
            self.messages.append("  [Shed] Sacrifice a good mutation to cleanse a debuff and regain radiation.")

        if name == "Pure":
            self.player_stats.tox_resistance += 20
            self.messages.append("  [Pure] +20% tox resistance. Double XP from toxicity resisted.")

        if name == "Bastion":
            self.grant_ability("bastion")
            self.messages.append("  [Bastion] Toggle: -25% damage taken, -20% dealt. Costs 10 tox per activation. (5/floor)")

        if name == "Absolution":
            self.grant_ability("absolution")
            self.messages.append("  [Absolution] Your cleansing becomes wrath. Tox lost deals damage to 2 nearby enemies! (3/floor)")

        if name == "Immaculate":
            self.messages.append("  [Immaculate] Purity cap → 100, temp HP cap → 100. 2x Purity stacks while Bastion active. Melee hits in Bastion grant 3 stacks.")

        if name == "Acid Meltdown":
            self.grant_ability("acid_meltdown")
            self.messages.append("  [Acid Meltdown] Spend 25 tox: halve move cost, kills explode into acid!")

        if name == "Toxic Slingshot":
            self.grant_ability("toxic_slingshot")
            self.messages.append("  [Toxic Slingshot] Spend 50 tox to conjure a toxic gun in your sidearm! Scales with CW level.")

        if name == "Toxic Shell":
            self.grant_ability("toxic_shell")
            self.messages.append("  [Toxic Shell] Barrier from your toxicity. When it breaks, toxic nova! (3/floor)")

        if name == "Fast Food":
            ps = self.player_stats
            ps.constitution += 2
            ps._base["constitution"] = ps.constitution
            self.player.max_hp += 20
            self.player.heal(20)
            self.grant_ability("quick_eat")
            self.messages.append("  [Fast Food] +2 Constitution. You learn Quick Eat! Use it to instantly eat your next food.")

        if name == "Rad Bomb":
            self.grant_ability("rad_bomb")
            self.messages.append("  [Rad Bomb] You can place radiation crystals that detonate in 3 turns! 3/floor.")

        if name == "Curse of Ham":
            self.grant_ability("curse_of_ham")
            self.messages.append("  [Curse of Ham] You learn a dark curse that weakens enemies in a cone! 3/floor.")

        if name == "Curse of DOT":
            self.grant_ability("curse_of_dot")
            self.messages.append("  [Curse of DOT] You learn a curse that deals escalating damage over time! 3/floor.")

        if name == "Curse of COVID":
            self.grant_ability("curse_of_covid")
            self.messages.append("  [Curse of COVID] You learn a plague curse that irradiates and poisons enemies! 3/floor.")

        if name == "Dark Covenant":
            # Set all existing curse abilities to 6 charges immediately
            for inst in self.player_abilities:
                defn = ABILITY_REGISTRY.get(inst.ability_id)
                if defn and defn.is_curse:
                    new_max = defn.max_charges + 3
                    if defn.charge_type in (ChargeType.PER_FLOOR, ChargeType.FLOOR_ONLY):
                        inst.floor_charges_remaining = new_max
                    elif defn.charge_type in (ChargeType.TOTAL, ChargeType.ONCE):
                        inst.charges_remaining = new_max
            self.messages.append("  [Dark Covenant] All curses now have 6 charges per floor! Cursed enemies may drop Voodoo Dolls.")

        if name == "Freeze":
            self.grant_ability("freeze")
            self.messages.append("  [Freeze] Freeze a visible enemy solid! 5 stacks of Frozen. 5/floor.")

        if name == "Ice Lance":
            self.grant_ability("ice_lance")
            self.messages.append("  [Ice Lance] Piercing frost projectile. Shatters frozen enemies for massive damage! 10-turn cooldown.")

        if name == "Glacier Mind":
            ps = self.player_stats
            ps.book_smarts += 5
            ps._base["book_smarts"] = ps.book_smarts
            self.messages.append("  [Glacier Mind] +5 Book Smarts. Cold spell charges are doubled!")

        if name == "Ice Barrier":
            self.grant_ability("ice_barrier")
            self.messages.append("  [Ice Barrier] Consume Chill stacks from nearby enemies to gain Temp HP! 3/floor.")

        if name == "Web Trail":
            self.grant_ability("web_trail")
            self.messages.append("  [Web Trail] You are immune to webs and can leave cobwebs in your wake! 3/floor.")

        if name == "Summon Spider":
            self.grant_ability("summon_spiderling")
            self.messages.append("  [Summon Spider] Hatch spiderlings on adjacent tiles! They guard and bite. 5/floor.")

        if name == "Toxic Bite":
            self.grant_ability("toxic_bite")
            self.messages.append("  [Toxic Bite] Bite enemies for STS damage + 2 Venom stacks! Venomed kills leave Venom Pools. 6/floor.")

        # Graffiti: every perk grants a random spray paint
        if skill_name == "Graffiti":
            import random as _rng
            _SPRAY_TABLE = ["red_spray_paint", "blue_spray_paint", "green_spray_paint", "orange_spray_paint", "silver_spray_paint"]
            chosen = _rng.choice(_SPRAY_TABLE)
            self._add_item_to_inventory(chosen)
            from items import ITEM_DEFS
            spray_name = ITEM_DEFS[chosen]["name"]
            self.messages.append(f"  [Graffiti] You find a {spray_name} in your pocket!")

        if name == "Living Canvas":
            self._add_item_to_inventory("graffiti_gun")
            self.messages.append("  [Living Canvas] You receive a Graffiti Gun! Load spray cans and paint at range.")

        if name == "Purge":
            self.grant_ability("purge")
            self.messages.append("  [Purge] Remove 20 infection at the cost of 3 weak melee hits. Unlimited uses.")

        if name == "Zombie Rage":
            ps = self.player_stats
            ps.strength += 2
            ps._base["strength"] = ps.strength
            self.grant_ability("zombie_rage")
            self.messages.append("  [Zombie Rage] +2 Strength. Activate for a burst of undead fury! 40t cooldown.")

        if name == "Zombie Stare":
            ps = self.player_stats
            ps.strength += 2
            ps._base["strength"] = ps.strength
            self.grant_ability("zombie_stare")
            self.messages.append("  [Zombie Stare] +2 Strength. Stare down enemies to stun and fear them! 15t cooldown.")

        if name == "Corpse Explosion":
            self.messages.append("  [Corpse Explosion] Enemies killed during Zombie Rage now explode! Chain kills push infection — hit 100 for an Infection Nova.")

        if name == "Hunger":
            ps = self.player_stats
            ps.strength += 2
            ps._base["strength"] = ps.strength
            ps.constitution += 2
            ps._base["constitution"] = ps.constitution
            self.player.max_hp += 20
            self.player.heal(20)
            self.messages.append("  [Hunger] +2 STR, +2 CON. Purge now grants Hunger (heal on hit). Zombie Stare upgraded to 90° cone! Infection cost: 8.")

        if name == "Outbreak":
            self.grant_ability("outbreak")
            self.messages.append("  [Outbreak] Target a 7×7 area — enemies become linked. Damage echoes between them! 30t cooldown.")

        if name == "Scrap Turret":
            self.grant_ability("scrap_turret")
            self._last_destroyed_item_value = 25  # default
            self.messages.append("  [Scrap Turret] Destroy items to load a turret charge. Place on adjacent tile to deploy!")

        if name == "Salvage Volley":
            self.messages.append("  [Salvage Volley] Destroying items fires 3 bonus turret shots. Turret kills drop Scrap!")

    def _handle_log_input(self, action):
        """Handle input while the log menu is open. UP/DOWN scroll; anything else closes."""
        action_type = action.get("type")
        if action_type == "move":
            dy = action.get("dy", 0)
            dx = action.get("dx", 0)
            if dy == -1 and dx == 0:          # up → older messages
                max_scroll = max(0, len(self.messages) - 1)
                self.log_scroll = min(self.log_scroll + 1, max_scroll)
            elif dy == 1 and dx == 0:         # down → newer messages
                self.log_scroll = max(0, self.log_scroll - 1)
        else:
            self.menu_state = MenuState.NONE
        return False

    def _action_toggle_skills(self, _action):
        if self.menu_state == MenuState.NONE:
            self.menu_state = MenuState.SKILLS
            self.skills_cursor = 0
            self.skills_spend_mode = False
            self.skills_spend_input = ""
        elif self.menu_state == MenuState.SKILLS:
            self.menu_state = MenuState.NONE
            self.skills_spend_mode = False
            self.skills_spend_input = ""
        return False

    def _action_toggle_char_sheet(self, _action):
        if self.menu_state == MenuState.NONE:
            self.menu_state = MenuState.CHAR_SHEET
        elif self.menu_state == MenuState.CHAR_SHEET:
            self.menu_state = MenuState.NONE
        return False

    def _action_open_equipment(self, _action):
        self.menu_state = MenuState.EQUIPMENT
        return False

    def _action_select_item(self, action):
        from config import INVENTORY_PAGE_SIZE
        index = action["index"] + self.inventory_page * INVENTORY_PAGE_SIZE
        if 0 <= index < len(self.player.inventory):
            self._open_item_menu(index)
        return False

    def _action_inventory_page_down(self, _action):
        from config import INVENTORY_PAGE_SIZE
        total = len(self.player.inventory)
        last_page = max(0, (total - 1) // INVENTORY_PAGE_SIZE) if total > 0 else 0
        if self.inventory_page >= last_page:
            self.inventory_page = 0
        else:
            self.inventory_page += 1
        return False

    def _action_inventory_page_up(self, _action):
        from config import INVENTORY_PAGE_SIZE
        total = len(self.player.inventory)
        last_page = max(0, (total - 1) // INVENTORY_PAGE_SIZE) if total > 0 else 0
        if self.inventory_page <= 0:
            self.inventory_page = last_page
        else:
            self.inventory_page -= 1
        return False

    def _clamp_inventory_page(self):
        from config import INVENTORY_PAGE_SIZE
        total = len(self.player.inventory)
        if total == 0:
            self.inventory_page = 0
        else:
            last_page = (total - 1) // INVENTORY_PAGE_SIZE
            self.inventory_page = min(self.inventory_page, last_page)

    def _action_hotbar_use(self, action):
        """Use a hotbar-bound ability or item, or fall through to inventory selection."""
        slot = action.get("index", -1)
        if 0 <= slot < len(self.hotbar) and self.hotbar[slot] is not None:
            binding = self.hotbar[slot]

            if binding.startswith("item:"):
                # Item binding — find first matching item in inventory and use it
                item_id = binding[5:]
                for i, ent in enumerate(self.player.inventory):
                    if ent.item_id == item_id:
                        from inventory_mgr import _use_item
                        from menu_state import MenuState
                        self._red_drank_free_action = False
                        prev_menu = self.menu_state
                        _use_item(self, i)
                        if self.menu_state != prev_menu:
                            return False  # entered submenu — no turn cost yet
                        if self._red_drank_free_action:
                            self._red_drank_free_action = False
                            return False
                        return True
                # Item not in inventory anymore — silently ignore
                return False

            # Ability binding
            for i, inst in enumerate(self.player_abilities):
                if inst.ability_id == binding:
                    return self._execute_ability(i)
            # Ability not found (was removed) — silently ignore
            return False
        # No hotbar binding — fall through to inventory item selection (original behavior)
        return self._action_select_item(action)

    def _action_close_menu(self, _action):
        if self.menu_state == MenuState.NONE:
            # No menu open — open settings
            self.menu_state = MenuState.SETTINGS
            self.settings_cursor = 0
            return False
        self.menu_state = MenuState.NONE
        self.selected_item_index = None
        return False

    def _action_quit(self, _action):
        self.running = False
        return False

    def _action_descend_stairs(self, _action):
        # Standing on stairs → descend immediately
        for entity in self.dungeon.get_entities_at(self.player.x, self.player.y):
            if entity.entity_type == "staircase":
                self.cancel_auto_travel()
                # Sublevel stairs: enter a side-dungeon
                sublevel = getattr(entity, "sublevel", None)
                if sublevel:
                    return self._enter_sublevel(sublevel)
                # Upstairs in a sublevel: return to the floor we came from
                if getattr(self, "_sublevel_return_floor", None) is not None and entity.char == "<":
                    return self._exit_sublevel()
                return self._descend()
        # Start (or restart) auto-travel to discovered stairs
        stair = self._get_discovered_stairs()
        if stair:
            self._start_auto_travel(stair)
        else:
            self.messages.append("You haven't found the stairs yet.")
        return False

    def _descend(self):
        """Move player down to the next floor."""
        if self.sdl_overlay:
            self.sdl_overlay.clear()
        next_floor = self.current_floor + 1
        if next_floor >= self.total_floors:
            self.messages.append("This is the deepest floor of this zone.")
            return False

        # Determine zone info for the next floor
        zone_key, zone_floor, display_name, zone_type = get_zone_for_floor(next_floor)
        prev_zone_key = self._get_zone_info()[0]

        # Award abandoning XP for items/cash left on this floor
        self._gain_abandoning_xp()

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        if next_floor not in self.dungeons:
            event_id = self.get_floor_event(next_floor)
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key, floor_event=event_id, floor_num=zone_floor)
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                # Find a free tile if center is blocked (e.g. table on it)
                if new_dungeon.is_blocked(x, y):
                    for tx, ty in new_dungeon.rooms[0].floor_tiles(new_dungeon):
                        if not new_dungeon.is_blocked(tx, ty):
                            x, y = tx, ty
                            break
                self.player.x = x
                self.player.y = y
            new_dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned, floor_event=self.get_floor_event(next_floor))
            self.dungeons[next_floor] = new_dungeon
        else:
            new_dungeon = self.dungeons[next_floor]
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                if new_dungeon.is_blocked(x, y):
                    for tx, ty in new_dungeon.rooms[0].floor_tiles(new_dungeon):
                        if not new_dungeon.is_blocked(tx, ty):
                            x, y = tx, ty
                            break
                self.player.x = x
                self.player.y = y
            if self.player not in new_dungeon.entities:
                new_dungeon.entities.insert(0, self.player)

        self.current_floor = next_floor
        self.dungeon = new_dungeon
        self.dungeon.first_kill_happened = False
        # Pre-mark spawn room as visited so no XP is awarded for the landing tile
        if next_floor not in self.visited_rooms:
            self.visited_rooms[next_floor] = {0}
        self.dungeon.female_kill_happened = False
        self._compute_fov()
        self._update_tile_stat_bonuses()
        self.player.energy = ENERGY_THRESHOLD  # player acts first on new floor

        # Floor event: show title card and chat message
        event_id = self.get_floor_event(next_floor)
        if event_id:
            from config import FLOOR_EVENT_REGISTRY
            event = FLOOR_EVENT_REGISTRY.get(event_id, {})
            if self.sdl_overlay:
                self.sdl_overlay.show_title_card(event.get("name", event_id), duration=3.0)
            self.messages.append(event.get("message", "Something feels different about this floor..."))

        # Reset Gunplay L4 "Dead Eye" swagger bonus
        if self.dead_eye_swagger_gained > 0:
            self.player_stats.swagger -= self.dead_eye_swagger_gained
            self.dead_eye_swagger_gained = 0

        # Reset L Farming L3 "Unfazed" swagger bonus
        if self.unfazed_swagger_gained > 0:
            self.player_stats.swagger -= self.unfazed_swagger_gained
            self.unfazed_swagger_gained = 0

        # Reset per-floor ability charges
        cryo_double = self.skills.get("Cryomancy").level >= 4
        dark_covenant = self.skills.get("Blackkk Magic").level >= 4
        for inst in self.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn:
                inst.reset_floor(defn)
                # Cryomancy L4 (Glacier Mind): double per-floor charges for cold abilities
                if cryo_double and "cold" in defn.tags:
                    if defn.charge_type == ChargeType.PER_FLOOR:
                        inst.floor_charges_remaining = defn.max_charges * 2
                # Blackkk Magic L4 (Dark Covenant): +3 per-floor charges for curse abilities
                if dark_covenant and defn.is_curse:
                    if defn.charge_type in (ChargeType.PER_FLOOR, ChargeType.FLOOR_ONLY):
                        inst.floor_charges_remaining += 3

        # Reset reload-per-floor counters on equipped guns
        for gun_slot in ("weapon", "sidearm"):
            gun = self.equipment.get(gun_slot)
            if gun and hasattr(gun, 'reloads_this_floor'):
                gun.reloads_this_floor = 0

        # Reset Titan's Blood Ring
        self._titan_blood_available = True
        self._titan_blood_was_above_25 = self.player.hp > self.player.max_hp * 0.25

        # Throw Bottle: +1 charge per floor (only if ability unlocked)
        if any(a.ability_id == "throw_bottle" for a in self.player_abilities):
            self.grant_ability_charges("throw_bottle", 1)

        # Clear floor-duration effects (Green Drank, Five Loco, Protein Powder, etc.)
        for eff in list(self.player.status_effects):
            if getattr(eff, 'floor_duration', False):
                eff.expire(self.player, self)
                self.player.status_effects.remove(eff)

        # Handle hangover from previous floor's alcohol consumption
        from effects import apply_effect
        # Apply pending hangover stacks
        if self.pending_hangover_stacks > 0:
            apply_effect(self.player, self, "hangover", stacks=self.pending_hangover_stacks)
            self.messages.append(f"Your hangover hits... (-{self.pending_hangover_stacks} all stats this floor)")
            self.pending_hangover_stacks = 0

        # Reset temporary spell damage
        self.player_stats.temporary_spell_damage = 0

        # Refill armor at floor start and reset chain armor tracker
        self.player.armor = self.player.max_armor
        self._best_chain_armor_this_floor = 0
        if self.neck:
            from items import get_item_def
            neck_defn = get_item_def(self.neck.item_id)
            if neck_defn:
                self._best_chain_armor_this_floor = neck_defn.get("armor_bonus", 0)

        # Abandoning L2: Anotha Motha — spawn 5 extra items on the new floor (zones only)
        if zone_type == "zone" and self.skills.get("Abandoning").level >= 2:
            from loot import pick_random_consumable
            spawnable = self.dungeon.rooms[1:] if len(self.dungeon.rooms) > 1 else self.dungeon.rooms
            placed = 0
            for _ in range(5):
                item_id, strain = pick_random_consumable(zone_key, self.player_stats)
                # Try multiple tiles to avoid silent drops
                for _attempt in range(10):
                    room = random.choice(spawnable)
                    tiles = room.floor_tiles(self.dungeon)
                    if not tiles:
                        continue
                    x, y = random.choice(tiles)
                    if not self.dungeon.is_blocked(x, y):
                        ent = Entity(**create_item_entity(item_id, x, y, strain=strain))
                        self.dungeon.add_entity(ent)
                        placed += 1
                        break
            if placed > 0:
                self.messages.append(f"  [Anotha Motha] {placed} extra items spawned on this floor!")

        # Track zone first visit
        first_visit = zone_key not in self.zones_visited
        self.zones_visited.add(zone_key)

        # Zone transition message
        zone_total = get_zone_total_floors(zone_key)
        if zone_key != prev_zone_key:
            self.messages.append(f"You enter {display_name}.")
        if zone_type == "pseudozone":
            self.messages.append(f"{display_name}")
            if zone_key == "tyrones_penthouse" and first_visit:
                self.messages.append([
                    ("Tyrone: ", (255, 215, 0)),
                    ("Welcome to the Penthouse. Watch your fingers — buy whatever you want.", (220, 220, 220)),
                ])
        else:
            self.messages.append(
                f"You descend deeper... ({display_name} - Floor {zone_floor + 1}/{zone_total})"
            )

        # Auto-save on floor entry
        try:
            from save_system import save_game
            save_game(self)
        except Exception:
            pass  # don't block gameplay if save fails

        return True

    def _enter_sublevel(self, sublevel_key: str):
        """Enter a sublevel dungeon (e.g. Haitian Daycare). Reuses cached dungeon on re-entry."""
        if self.sdl_overlay:
            self.sdl_overlay.clear()

        # Remember where we came from
        self._sublevel_return_floor = self.current_floor
        self._sublevel_return_dungeon = self.dungeon
        self._sublevel_return_pos = (self.player.x, self.player.y)

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        # Check cache for existing sublevel
        cached = self._sublevel_cache.get(sublevel_key)
        if cached:
            sublevel_dungeon, cached_pos = cached
            self.player.x, self.player.y = cached_pos
            if self.player not in sublevel_dungeon.entities:
                sublevel_dungeon.entities.insert(0, self.player)
        else:
            # Generate a fresh sublevel
            sublevel_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=sublevel_key)
            if sublevel_dungeon.rooms:
                x, y = sublevel_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            sublevel_dungeon.spawn_entities(
                self.player, floor_num=0, zone=sublevel_key,
                player_skills=self.skills, player_stats=self.player_stats,
                special_rooms_spawned=self.special_rooms_spawned,
            )
            sublevel_dungeon.first_kill_happened = False
            sublevel_dungeon.female_kill_happened = False

        self.dungeon = sublevel_dungeon
        self._compute_fov()
        self._update_tile_stat_bonuses()
        self.player.energy = ENERGY_THRESHOLD

        # Title card
        _SUBLEVEL_NAMES = {"haitian_daycare": "Haitian Daycare"}
        display = _SUBLEVEL_NAMES.get(sublevel_key, sublevel_key)
        if self.sdl_overlay:
            self.sdl_overlay.show_title_card(display, duration=3.0)
        self.messages.append(f"You descend into the {display}...")
        return True

    def _exit_sublevel(self):
        """Return from a sublevel to the floor we came from."""
        if self.sdl_overlay:
            self.sdl_overlay.clear()

        return_floor = self._sublevel_return_floor
        return_dungeon = self._sublevel_return_dungeon
        rx, ry = self._sublevel_return_pos

        # Cache the sublevel dungeon so we can return to the same one
        sublevel_zone = getattr(self.dungeon, 'zone', None)
        if sublevel_zone:
            self.dungeon.remove_entity(self.player)
            self._sublevel_cache[sublevel_zone] = (self.dungeon, (self.player.x, self.player.y))
        else:
            self.dungeon.remove_entity(self.player)

        # Restore position and dungeon
        self.player.x = rx
        self.player.y = ry
        self.dungeon = return_dungeon
        self.current_floor = return_floor
        if self.player not in self.dungeon.entities:
            self.dungeon.entities.insert(0, self.player)

        self._sublevel_return_floor = None
        self._sublevel_return_dungeon = None
        self._sublevel_return_pos = None

        self._compute_fov()
        self._update_tile_stat_bonuses()
        self.player.energy = ENERGY_THRESHOLD
        self.messages.append("You ascend back to the floor above.")
        return True

    # ------------------------------------------------------------------
    # Auto-travel
    # ------------------------------------------------------------------

    def _get_discovered_stairs(self):
        """Return the staircase entity if the player has already seen it, else None."""
        for entity in self.dungeon.entities:
            if entity.entity_type == "staircase" and entity.always_visible:
                return entity
        return None

    def _start_auto_travel(self, stair):
        """Compute an A* path to stair and begin auto-travel."""
        cost = np.array(self.dungeon.tiles, dtype=np.int8)
        astar = tcod.path.AStar(cost=cost)
        raw_path = astar.get_path(self.player.y, self.player.x, stair.y, stair.x)
        if not raw_path:
            self.messages.append("No path to the stairs.")
            return
        # raw_path is list of (row, col) = (y, x); convert to (x, y)
        self.auto_travel_path = [(x, y) for y, x in raw_path]
        self.auto_traveling = True
        self.messages.append("Auto-traveling to stairs... (any key to cancel)")

    def cancel_auto_travel(self, reason: str = ""):
        """Stop auto-travel/autoexplore, optionally logging a reason."""
        if not self.auto_traveling:
            return
        self.auto_traveling = False
        self.autoexploring = False
        self.auto_travel_path = []
        if reason:
            self.messages.append(reason)

    def step_auto_travel(self):
        """Advance one step along the auto-travel path. Called once per 20ms tick."""
        # Cancel if a monster entered FOV
        for entity in self.dungeon.entities:
            if (
                entity.entity_type == "monster"
                and getattr(entity, "alive", True)
                and self.dungeon.visible[entity.y, entity.x]
            ):
                self.cancel_auto_travel("Monster spotted! Auto-travel cancelled.")
                return

        # Arrived — no more waypoints
        if not self.auto_travel_path:
            self.auto_traveling = False
            for entity in self.dungeon.get_entities_at(self.player.x, self.player.y):
                if entity.entity_type == "staircase":
                    self.messages.append("You reach the stairs. (Press > to descend)")
                    return
            self.messages.append("Auto-travel complete.")
            return

        next_x, next_y = self.auto_travel_path.pop(0)
        dx = next_x - self.player.x
        dy = next_y - self.player.y
        result = self.handle_move(dx, dy)

        # If movement failed (blocked by wall edge case), abort
        if result is False or result is None:
            self.cancel_auto_travel("Path blocked. Auto-travel cancelled.")
            return

        # Check if we've just arrived at the stairs
        for entity in self.dungeon.get_entities_at(self.player.x, self.player.y):
            if entity.entity_type == "staircase":
                self.auto_traveling = False
                self.auto_travel_path = []
                self.messages.append("You reach the stairs. (Press > to descend)")
                return

    # ------------------------------------------------------------------
    # Autoexplore
    # ------------------------------------------------------------------

    def _action_autoexplore(self, _action):
        """Start autoexplore mode — walk toward nearest unexplored floor tile."""
        # Check if already eating food
        eating = any(getattr(e, 'id', '') == 'eating_food' for e in self.player.status_effects)
        if eating:
            self.messages.append("Can't autoexplore while eating.")
            return False
        # Check for visible monsters already in FOV
        for entity in self.dungeon.entities:
            if (
                entity.entity_type == "monster"
                and getattr(entity, "alive", True)
                and self.dungeon.visible[entity.y, entity.x]
            ):
                self.messages.append("Can't autoexplore with monsters in sight!")
                return False
        path = self._find_autoexplore_path()
        if not path:
            self.messages.append("Nothing left to explore.")
            return False
        self.auto_travel_path = path
        self.auto_traveling = True
        self.autoexploring = True
        self._autoexplore_last_hp = self.player.hp
        self.messages.append("Autoexploring... (any key to cancel)")
        return False  # no turn consumed; step_auto_travel does the walking

    def _find_autoexplore_path(self):
        """BFS from player to find nearest unexplored floor tile, return A* path to it.

        Target: the nearest *explored floor* tile that is adjacent to an unexplored tile.
        This makes the player walk to the edge of explored territory."""
        from collections import deque as _deque
        from config import TILE_FLOOR, TILE_WALL

        dungeon = self.dungeon
        px, py = self.player.x, self.player.y
        w, h = dungeon.width, dungeon.height

        # Build set of tiles with lootable items (items/cash on explored floor)
        item_tiles = set()
        for e in dungeon.entities:
            if not getattr(e, "alive", True):
                continue
            if e.entity_type in ("item", "cash") and dungeon.explored[e.y, e.x]:
                item_tiles.add((e.x, e.y))

        # BFS on walkable explored tiles — prioritize items over unexplored frontier
        visited = set()
        visited.add((px, py))
        queue = _deque()
        queue.append((px, py, 0))
        best_item_target = None
        best_item_dist = float('inf')
        best_frontier_target = None
        best_frontier_dist = float('inf')

        while queue:
            x, y, dist = queue.popleft()
            # Early exit if we've found items and passed their distance
            if dist > best_item_dist and dist > best_frontier_dist:
                break

            # Check for lootable items on this tile
            if (x, y) in item_tiles and dist < best_item_dist:
                best_item_target = (x, y)
                best_item_dist = dist

            # Check if this explored floor tile borders any unexplored tile
            if dist < best_frontier_dist:
                for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        if not dungeon.explored[ny, nx]:
                            best_frontier_target = (x, y)
                            best_frontier_dist = dist
                            break

            # Expand to walkable explored neighbors
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1),
                           (x-1, y-1), (x+1, y-1), (x-1, y+1), (x+1, y+1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    if dungeon.tiles[ny][nx] == TILE_FLOOR and dungeon.explored[ny, nx]:
                        # Skip permanent blockers (tables, crates) but allow
                        # monster-occupied tiles — monsters are temporary obstacles
                        # and will move by the time the player arrives.
                        blocked_by_hazard = any(
                            e.x == nx and e.y == ny and e.blocks_movement
                            and e.entity_type == "hazard"
                            for e in dungeon.entities
                        )
                        if not blocked_by_hazard:
                            visited.add((nx, ny))
                            queue.append((nx, ny, dist + 1))

        # Items take priority over frontier exploration
        best_target = best_item_target or best_frontier_target

        if best_target is None:
            return []

        tx, ty = best_target
        if tx == px and ty == py:
            return []  # already there

        # A* path to the target — mark blocking hazards as impassable
        cost = np.array(dungeon.tiles, dtype=np.int8)
        for e in dungeon.entities:
            if e.entity_type == "hazard" and e.blocks_movement:
                cost[e.y, e.x] = 0
        astar = tcod.path.AStar(cost=cost)
        raw_path = astar.get_path(py, px, ty, tx)
        if not raw_path:
            return []
        return [(x, y) for y, x in raw_path]

    def step_autoexplore(self):
        """Advance one step of autoexplore. Re-paths after each step."""
        # Cancel if a monster entered FOV
        for entity in self.dungeon.entities:
            if (
                entity.entity_type == "monster"
                and getattr(entity, "alive", True)
                and self.dungeon.visible[entity.y, entity.x]
            ):
                self.cancel_auto_travel("Monster spotted! Autoexplore cancelled.")
                return

        # Check if player took damage since last step (hp tracking)
        if hasattr(self, '_autoexplore_last_hp') and self.player.hp < self._autoexplore_last_hp:
            self.cancel_auto_travel("Taking damage! Autoexplore cancelled.")
            return

        # Re-path each step (new tiles revealed)
        path = self._find_autoexplore_path()
        if not path:
            self.auto_traveling = False
            self.autoexploring = False
            self.auto_travel_path = []
            self.messages.append("Exploration complete.")
            return

        next_x, next_y = path[0]
        dx = next_x - self.player.x
        dy = next_y - self.player.y

        self._autoexplore_last_hp = self.player.hp
        result = self.handle_move(dx, dy)

        if result is False or result is None:
            self.cancel_auto_travel("Path blocked. Autoexplore cancelled.")
            return

        # Consume energy and let monsters act (unlike auto-travel, explore is real-time)
        if result and self.running and self.player.alive:
            move_cost = max(0, self.player_move_cost - self.move_cost_reduction)
            self.player.energy -= move_cost
            self._run_energy_loop()

        # Check if player died or game ended during energy loop
        if not self.player.alive or not self.running:
            self.autoexploring = False
            return

        # Check if player took damage from the move / monster attacks
        if self.player.hp < self._autoexplore_last_hp:
            self.cancel_auto_travel("Taking damage! Autoexplore cancelled.")
            return

        # Re-check for visible monsters after energy loop (monsters may have moved into FOV)
        for entity in self.dungeon.entities:
            if (
                entity.entity_type == "monster"
                and getattr(entity, "alive", True)
                and self.dungeon.visible[entity.y, entity.x]
            ):
                self.cancel_auto_travel("Monster spotted! Autoexplore cancelled.")
                return

        # Check if we're standing on stairs
        for entity in self.dungeon.get_entities_at(self.player.x, self.player.y):
            if entity.entity_type == "staircase":
                self.auto_traveling = False
                self.autoexploring = False
                self.auto_travel_path = []
                self.messages.append("Found the stairs! (Press > to descend)")
                return

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def _fear_flee(self, fear_effect):
        """Force the player to move away from the fear source.
        Picks the best walkable tile that maximises distance from the source."""
        self._player_just_moved = False
        px, py = self.player.x, self.player.y
        sx, sy = fear_effect.source_x, fear_effect.source_y

        # Compute direction away from the fear source
        raw_dx = px - sx
        raw_dy = py - sy
        # Normalize to -1/0/1
        flee_dx = (1 if raw_dx > 0 else -1 if raw_dx < 0 else 0)
        flee_dy = (1 if raw_dy > 0 else -1 if raw_dy < 0 else 0)

        # Try candidates in order of preference: direct flee, then partial,
        # then any adjacent tile that increases distance
        def _dist_sq(x, y):
            return (x - sx) ** 2 + (y - sy) ** 2

        current_dist = _dist_sq(px, py)
        candidates = []

        # All 8 directions, sorted by how much they increase distance
        for ddx in (-1, 0, 1):
            for ddy in (-1, 0, 1):
                if ddx == 0 and ddy == 0:
                    continue
                nx, ny = px + ddx, py + ddy
                if self.dungeon.is_blocked(nx, ny):
                    continue
                # Also skip tiles with living monsters
                has_monster = False
                for ent in self.dungeon.get_entities_at(nx, ny):
                    if ent.entity_type == "monster" and getattr(ent, "alive", True):
                        has_monster = True
                        break
                if has_monster:
                    continue
                candidates.append((ddx, ddy, _dist_sq(nx, ny)))

        if candidates:
            # Prefer the direction that moves furthest from source
            candidates.sort(key=lambda c: -c[2])
            best_dx, best_dy, _ = candidates[0]
            new_x, new_y = px + best_dx, py + best_dy
            self._player_just_moved = True
            self.dungeon.move_entity(self.player, new_x, new_y)
            self.messages.append("You flee in terror!")
        else:
            # Cornered — can't move, turn is still consumed
            self.messages.append("You cower in fear!")

        # Render mid-turn so the player can see each fear step
        if self.render_callback:
            self._compute_fov()
            self.render_callback()
            time.sleep(0.18)

    def handle_move(self, dx, dy):
        """Handle player movement using spatial index."""
        self._player_just_moved = False

        # Slipped check — must stand up before moving/attacking
        slip_effect = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'slipped'),
            None,
        )
        if slip_effect:
            self.player.status_effects.remove(slip_effect)
            self.messages.append([
                ("You get back on your feet!", (200, 200, 210)),
            ])
            return True  # turn consumed standing up

        # Web escape check — must break free before moving
        web_effect = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'web_stuck'),
            None,
        )
        if web_effect:
            import random as _rng
            web_effect.escape_attempts += 1
            if _rng.random() < 0.5 or web_effect.escape_attempts >= web_effect.max_attempts:
                # Escaped!
                web_effect._break_free(self.player, self.dungeon)
                self.messages.append([
                    ("You tear free from the web!", (200, 200, 255)),
                ])
                # Turn consumed by escaping — player doesn't move this turn
                return True
            # Failed to escape
            self.messages.append([
                ("You struggle against the web... ", (180, 180, 180)),
                (f"({web_effect.escape_attempts}/{web_effect.max_attempts})", (150, 150, 150)),
            ])
            return True  # turn consumed

        # Check if player is channeling Shortcut
        shortcut_eff = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'shortcut_channel'),
            None
        )
        if shortcut_eff:
            self.player.status_effects.remove(shortcut_eff)
            self.messages.append([
                ("Shortcut cancelled! ", (255, 150, 100)),
                ("You moved.", (200, 150, 150)),
            ])

        # Root Beer: player is rooted and cannot move (can still attack adjacent)
        if any(getattr(e, 'id', '') == 'root_beer' for e in self.player.status_effects):
            self.messages.append([
                ("You are rooted! You can't move.", (140, 100, 50)),
            ])
            return False

        # Check if player is eating food
        eating_effect = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'eating_food'),
            None
        )
        if eating_effect:
            if not eating_effect.move_warned:
                eating_effect.move_warned = True
                self.messages.append([
                    ("You're eating the ", (255, 255, 255)),
                    (eating_effect.food_name, (150, 200, 150)),
                    ("! Moving will waste it.", (255, 200, 100)),
                ])
                return
            # Second move attempt: waste the food
            self.player.status_effects.remove(eating_effect)
            self.messages.append([
                ("Your ", (200, 100, 100)),
                (eating_effect.food_name, (150, 150, 150)),
                (" was wasted.", (200, 100, 100)),
            ])

        new_x = self.player.x + dx
        new_y = self.player.y + dy

        # Phase Walk: allow walking through walls (but not off-map)
        has_phase = any(getattr(e, 'id', '') == 'phase_walk'
                        for e in self.player.status_effects)
        if has_phase and self.dungeon.is_terrain_blocked(new_x, new_y):
            # Allow wall movement, but check bounds
            if not (0 <= new_x < self.dungeon.width and 0 <= new_y < self.dungeon.height):
                return False
            self._player_just_moved = True
            self.dungeon.move_entity(self.player, new_x, new_y)
            self._compute_fov()
            self._pickup_items_at(new_x, new_y)
            self._gain_jaywalking_xp()
            return True

        # Check for blocking entity (wall, monster, crate hazard, etc.)
        if self.dungeon.is_blocked(new_x, new_y):
            target = self.dungeon.get_blocking_entity_at(new_x, new_y)
            if target and target.entity_type == "monster" and not getattr(target, "is_summon", False):
                self.handle_attack(self.player, target)
                self._last_action_was_attack = True
                return True
            elif target and getattr(target, "hazard_type", None) == "crate":
                self._smash_crate(target)
                return True
            elif target and getattr(target, "hazard_type", None) == "deep_fryer":
                self._open_deep_fryer()
                return False  # no turn consumed — just opens menu
            elif target and getattr(target, "hazard_type", None) == "vending_machine":
                self._open_vending_machine(target)
                return False  # no turn consumed — just opens menu
            elif target and getattr(target, "hazard_type", None) == "shop_item":
                self._open_shop_item(target)
                return False  # no turn consumed — just opens popup
            elif target and getattr(target, "hazard_type", None) == "door":
                self._try_unlock_door(target)
                return True
            return False  # pure wall — no turn consumed

        # Failsafe: explicitly check that no living monster occupies the destination
        # This prevents any edge cases where blocks_movement might be incorrectly set
        for entity in self.dungeon.get_entities_at(new_x, new_y):
            if entity.entity_type == "monster" and getattr(entity, "alive", True) and not getattr(entity, "is_summon", False):
                self.handle_attack(self.player, entity)
                self._last_action_was_attack = True
                return True

        # Rooted check — can't move but attacks above still work
        rooted = any(getattr(e, 'id', '') == 'root_beer' for e in self.player.status_effects)
        if rooted:
            self.messages.append([
                ("Your legs have become roots!", (140, 100, 50)),
            ])
            return False  # no turn consumed — just blocked

        # Move player through spatial index
        old_x, old_y = self.player.x, self.player.y
        self._player_just_moved = True
        self.dungeon.move_entity(self.player, new_x, new_y)
        self._update_tile_stat_bonuses()

        # Web Trail (Arachnigga L1): leave a cobweb on the tile we just left
        if any(getattr(e, 'id', '') == 'web_trail' for e in self.player.status_effects):
            # Only spawn if no web already on that tile
            if not any(getattr(ent, 'hazard_type', None) == 'web'
                       for ent in self.dungeon.get_entities_at(old_x, old_y)):
                from hazards import create_web
                web = create_web(old_x, old_y)
                self.dungeon.add_entity(web)

        # Lunge (Stabbing L5): free auto-crit on enemy directly ahead after moving
        if self.skills.get("Stabbing").level >= 5:
            weapon = self.equipment.get("weapon")
            if weapon:
                from items import get_item_def, weapon_matches_type
                wdefn = get_item_def(weapon.item_id)
                if weapon_matches_type(wdefn, "stabbing"):
                    ahead_x = new_x + dx
                    ahead_y = new_y + dy
                    for ent in self.dungeon.get_entities_at(ahead_x, ahead_y):
                        if ent.entity_type == "monster" and getattr(ent, "alive", True):
                            self.messages.append([
                                ("Lunge! ", (255, 80, 80)),
                                (f"You drive your blade into {ent.name}!", (200, 200, 200)),
                            ])
                            combat.handle_attack(self, self.player, ent, _windfury_eligible=False, force_crit=True)
                            break

        # Jaywalking XP: award on first entry into each room
        room_idx = self.dungeon.get_room_index_at(new_x, new_y)
        if room_idx is not None:
            floor_visited = self.visited_rooms.setdefault(self.current_floor, {0})
            if room_idx not in floor_visited:
                floor_visited.add(room_idx)
                self._gain_jaywalking_xp()
                # Stash Finder (Alcoholism L3): 15% chance to find a random bottle
                if self.skills.get("Alcoholism").level >= 3 and random.random() < 0.15:
                    self._stash_finder_proc()
                # Ring of Intimidation: fear enemies whose max HP <= 30% of player max HP
                self._intimidation_ring_proc(room_idx)

        # Child Support debuff: drain $1 per step
        for effect in self.player.status_effects:
            if effect.id == "child_support":
                if self.cash > 0:
                    self.cash -= 1
                    self.messages.append("Child support payment auto-withdrawn. -$1")
                else:
                    self.messages.append("Child support due but you're broke!")
                break

        # Web hazard: stick the player if they walked onto a web
        # Arachnigga L1: immune to webs — walk through without getting stuck or destroying them
        web_immune = self.skills.get("Arachnigga").level >= 1
        for ent in self.dungeon.get_entities_at(new_x, new_y):
            if getattr(ent, "hazard_type", None) == "web":
                if web_immune:
                    break
                # Only apply if not already webbed
                if not any(getattr(e, 'id', '') == 'web_stuck' for e in self.player.status_effects):
                    effects.apply_effect(self.player, self, "web_stuck",
                                         silent=True, web_entity=ent)
                    self.messages.append([
                        ("You walk into a web and get stuck!", (180, 180, 220)),
                    ])
                break

        # Silver spray paint: slip on entry
        if self.dungeon.spray_paint.get((new_x, new_y)) == "silver":
            if not any(getattr(e, 'id', '') == 'slipped' for e in self.player.status_effects):
                effects.apply_effect(self.player, self, "slipped", silent=True)
                self.messages.append([
                    ("You slip on the silver paint!", (200, 200, 210)),
                ])

        # Recompute FOV
        self._compute_fov()

        # Check for pickups at new position
        for entity in list(self.dungeon.get_entities_at(self.player.x, self.player.y)):
            if entity == self.player:
                continue
            if entity.entity_type == "item":
                self.dungeon.remove_entity(entity)
                # Check if this item instance has been looted before (prevent drop/pickup abuse)
                is_first_pickup = entity.instance_id not in self.picked_up_items
                if is_first_pickup:
                    self.picked_up_items.add(entity.instance_id)
                    self._gain_item_skill_xp("Stealing", entity.item_id)
                    self._sticky_fingers_check(entity.item_id)
                # Try to merge into an existing stack
                # Charged items (e.g. greasy food) stack if charges and prefix match
                if is_stackable(entity.item_id):
                    e_charges = getattr(entity, "charges", None)
                    e_max = getattr(entity, "max_charges", None)
                    e_prefix = getattr(entity, "prefix", None)
                    existing = next(
                        (i for i in self.player.inventory
                         if i.item_id == entity.item_id and i.strain == entity.strain
                         and getattr(i, "charges", None) == e_charges
                         and getattr(i, "max_charges", None) == e_max
                         and getattr(i, "prefix", None) == e_prefix),
                        None,
                    )
                    if existing:
                        existing.quantity += entity.quantity
                        display = build_inventory_display_name(
                            existing.item_id, existing.strain, existing.quantity
                        )
                        self.messages.append([
                            ("Picked up ", _C_MSG_PICKUP),
                            (entity.name, entity.color),
                            (f" ({display})", _C_MSG_NEUTRAL),
                        ])
                        break
                self.player.inventory.append(entity)
                self._sort_inventory()
                self.messages.append([
                    ("Picked up ", _C_MSG_PICKUP),
                    (entity.name, entity.color),
                ])
                break
            elif entity.entity_type == "cash":
                self.dungeon.remove_entity(entity)
                self.cash += entity.cash_amount
                self.messages.append(f"Picked up ${entity.cash_amount}!")
                break

        return True

    # ------------------------------------------------------------------
    # Hazard interactions
    # ------------------------------------------------------------------

    def _smash_crate(self, crate):
        """Destroy a crate and drop a random consumable on its tile."""
        cx, cy = crate.x, crate.y
        self.dungeon.remove_entity(crate)

        item_id, strain = pick_random_consumable(self._get_zone_info()[0], self.player_stats)
        kwargs = create_item_entity(item_id, cx, cy, strain=strain)
        self.dungeon.add_entity(Entity(**kwargs))

        self.messages.append("You smash the crate open! Something falls out.")

    def _try_unlock_door(self, door):
        """Attempt to unlock a door. Checks player inventory for the matching key."""
        key = next(
            (item for item in self.player.inventory
             if getattr(item, "item_id", None) == "big_niggas_key"),
            None,
        )
        if key is None:
            self.messages.append("The door is locked.")
            return
        # Consume the key and remove the door
        self.player.inventory.remove(key)
        self.dungeon.remove_entity(door)
        self.messages.append([
            ("You use ", (200, 200, 200)),
            ("Big Nigga's Key", (220, 180, 60)),
            (" — the door swings open.", (200, 200, 200)),
        ])
        # Recompute FOV so the back room is now visible
        self.dungeon.compute_fov(self.player.x, self.player.y)

    # ------------------------------------------------------------------
    # Deep Fryer
    # ------------------------------------------------------------------

    def _open_deep_fryer(self):
        return inventory_mgr._open_deep_fryer(self)

    def _deep_fry_selected(self):
        return inventory_mgr._deep_fry_selected(self)

    # ------------------------------------------------------------------
    # Vending Machine
    # ------------------------------------------------------------------

    def _open_vending_machine(self, vm_entity):
        """Open the vending machine shop menu."""
        from menu_state import MenuState
        stock = getattr(vm_entity, "vending_stock", [])
        if not stock:
            self.messages.append("The vending machine is empty.")
            return
        self.vending_machine = vm_entity
        self.vending_cursor = 0
        self.menu_state = MenuState.VENDING_MACHINE

    def _handle_vending_machine_input(self, action):
        from menu_state import MenuState
        from items import get_item_value, get_item_def
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.vending_machine = None
            return False

        stock = getattr(self.vending_machine, "vending_stock", [])
        if not stock:
            self.menu_state = MenuState.NONE
            self.vending_machine = None
            return False

        if action_type == "move":
            dy = action.get("dy", 0)
            if dy != 0:
                self.vending_cursor = (self.vending_cursor + dy) % len(stock)
            return False

        if action_type in ("confirm_target", "item_use"):
            item_id, strain = stock[self.vending_cursor]
            price = get_item_value(item_id, strain=strain)
            if self.cash < price:
                self.messages.append(f"Not enough cash! Need ${price}, have ${self.cash}.")
                return False
            self.cash -= price
            self._add_item_to_inventory(item_id, strain=strain)
            defn = get_item_def(item_id) or {}
            name = defn.get("name", item_id)
            self.messages.append([
                ("Bought ", (100, 255, 100)),
                (name, defn.get("color", (255, 255, 255))),
                (f" for ${price}.", (100, 255, 100)),
            ])
            stock.pop(self.vending_cursor)
            if not stock:
                self.messages.append("The vending machine is now empty.")
                self.menu_state = MenuState.NONE
                self.vending_machine = None
            elif self.vending_cursor >= len(stock):
                self.vending_cursor = len(stock) - 1
            return False

        return False

    # ------------------------------------------------------------------
    # Shop item (Tyrone's Penthouse)
    # ------------------------------------------------------------------

    def _open_shop_item(self, entity):
        """Open the shop item buy/cancel popup."""
        from menu_state import MenuState
        self.shop_item_entity = entity
        self.menu_state = MenuState.SHOP_ITEM

    def _handle_shop_item_input(self, action):
        """Handle input for the shop item popup: Enter=buy, C=coupon, Esc=cancel."""
        from menu_state import MenuState
        from items import get_item_def
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.shop_item_entity = None
            return False

        # [C] Use Tyrone's Coupon — free item
        if action_type == "open_char_sheet":
            entity = self.shop_item_entity
            if entity is None:
                self.menu_state = MenuState.NONE
                return False
            coupon = next(
                (it for it in self.player.inventory
                 if getattr(it, "item_id", None) == "tyrones_coupon"),
                None,
            )
            if not coupon:
                self.messages.append("You don't have a coupon.")
                return False
            item_id = getattr(entity, "item_id", None)
            self.player.inventory.remove(coupon)
            self._add_item_to_inventory(item_id)
            defn = get_item_def(item_id) or {}
            name = defn.get("name", item_id)
            self.messages.append([
                ("Redeemed ", (255, 215, 0)),
                ("Tyrone's Coupon", (255, 215, 0)),
                (" for ", (255, 215, 0)),
                (name, defn.get("color", (255, 255, 255))),
                ("!", (255, 215, 0)),
            ])
            if entity in self.dungeon.entities:
                self.dungeon.entities.remove(entity)
            self.menu_state = MenuState.NONE
            self.shop_item_entity = None
            return False

        if action_type in ("confirm_target", "item_use"):
            entity = self.shop_item_entity
            if entity is None:
                self.menu_state = MenuState.NONE
                return False
            item_id = getattr(entity, "item_id", None)
            price = getattr(entity, "shop_price", 0)
            if self.cash < price:
                self.messages.append(f"Not enough cash! Need ${price}, have ${self.cash}.")
                self.menu_state = MenuState.NONE
                self.shop_item_entity = None
                return False
            # Normal purchase
            self.cash -= price
            self._add_item_to_inventory(item_id)
            defn = get_item_def(item_id) or {}
            name = defn.get("name", item_id)
            self.messages.append([
                ("Bought ", (100, 255, 100)),
                (name, defn.get("color", (255, 255, 255))),
                (f" for ${price}.", (100, 255, 100)),
            ])
            # Remove item entity from the map
            if entity in self.dungeon.entities:
                self.dungeon.entities.remove(entity)
            self.menu_state = MenuState.NONE
            self.shop_item_entity = None
            return False

        return False

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def _compute_str_bonus(self, weapon_item):
        return combat._compute_str_bonus(self, weapon_item)

    def _has_spec_weapon(self) -> bool:
        """Check if player has a spec weapon equipped in weapon or sidearm slot."""
        for slot in ["weapon", "sidearm"]:
            item = self.equipment.get(slot)
            if item:
                defn = get_item_def(item.item_id)
                if defn and "spec_weapon" in defn.get("tags", []):
                    return True
        return False

    def _compute_player_attack_power(self):
        return combat._compute_player_attack_power(self)

    def _compute_player_defense(self):
        return combat._compute_player_defense(self)

    def _compute_player_max_armor(self):
        return combat._compute_player_max_armor(self)

    def _apply_damage_modifiers(self, damage: int, defender) -> int:
        return combat._apply_damage_modifiers(self, damage, defender)

    def _apply_toxicity(self, damage: int, defender) -> int:
        return combat._apply_toxicity(self, damage, defender)

    def add_toxicity(self, entity, amount: int, from_player: bool = False,
                     pierce_resistance: bool = False):
        return combat.add_toxicity(self, entity, amount, from_player=from_player,
                                   pierce_resistance=pierce_resistance)

    def remove_toxicity(self, entity, amount: int):
        return combat.remove_toxicity(self, entity, amount)

    def add_radiation(self, entity, amount: int, pierce_resistance: bool = False):
        return combat.add_radiation(self, entity, amount, pierce_resistance=pierce_resistance)

    def remove_radiation(self, entity, amount: int):
        return combat.remove_radiation(self, entity, amount)

    def _player_meets_weapon_req(self) -> bool:
        return combat._player_meets_weapon_req(self)

    def handle_attack(self, attacker, defender, _windfury_eligible=True):
        return combat.handle_attack(self, attacker, defender, _windfury_eligible)

    # ------------------------------------------------------------------
    # Monster AI
    # ------------------------------------------------------------------

    def update_monsters(self):
        """Update all monsters via the AI system with shared tick data."""
        monsters = list(self.dungeon.get_monsters())
        tick_data = prepare_ai_tick(self.player, self.dungeon, monsters)
        for entity in monsters:
            if entity.alive:
                do_ai_turn(entity, self.player, self.dungeon, self, **tick_data)

    # ------------------------------------------------------------------
    # Monster attack handling
    # ------------------------------------------------------------------

    def handle_monster_attack(self, monster):
        return combat.handle_monster_attack(self, monster)

    def _apply_monster_hit_effect(self, effect, monster=None):
        return combat._apply_monster_hit_effect(self, effect, monster)

    def handle_monster_ranged_attack(self, monster):
        return combat.handle_monster_ranged_attack(self, monster)

    def _deport_player(self, stun_duration: int):
        return combat._deport_player(self, stun_duration)

    # ------------------------------------------------------------------
    # Spawner mechanic
    # ------------------------------------------------------------------

    def spawn_child(self, spawner, creature_positions=None):
        return combat.spawn_child(self, spawner, creature_positions)

    # ------------------------------------------------------------------
    # Item menu
    # ------------------------------------------------------------------

    def _open_item_menu(self, index):
        return inventory_mgr._open_item_menu(self, index)

    def _handle_item_menu_input(self, action):
        return inventory_mgr._handle_item_menu_input(self, action)

    def _execute_item_action(self, action_name):
        return inventory_mgr._execute_item_action(self, action_name)

    # ------------------------------------------------------------------
    # Equipment
    # ------------------------------------------------------------------

    def _equip_item(self, index) -> bool:
        return inventory_mgr._equip_item(self, index)

    def _handle_equipment_input(self, action):
        return inventory_mgr._handle_equipment_input(self, action)

    # ------------------------------------------------------------------
    # Ring stat bonuses
    # ------------------------------------------------------------------

    def _refresh_ring_stat_bonuses(self):
        return inventory_mgr._refresh_ring_stat_bonuses(self)

    def _sync_player_max_hp(self):
        return inventory_mgr._sync_player_max_hp(self)

    # ------------------------------------------------------------------
    # Inventory sort
    # ------------------------------------------------------------------

    def _sort_inventory(self):
        return inventory_mgr._sort_inventory(self)

    def _add_item_to_inventory(self, item_id, strain=None, quantity=1):
        return inventory_mgr._add_item_to_inventory(self, item_id, strain, quantity)

    def _acid_armor_break_equipment(self):
        return inventory_mgr._acid_armor_break_equipment(self)

    # ------------------------------------------------------------------
    # Drop / Use
    # ------------------------------------------------------------------

    def _drop_item(self, index):
        return inventory_mgr._drop_item(self, index)

    def _use_item(self, index):
        return inventory_mgr._use_item(self, index)

    def _use_food(self, item, food_id):
        return inventory_mgr._use_food(self, item, food_id)

    # ------------------------------------------------------------------
    # Destroy
    # ------------------------------------------------------------------

    def _handle_examine_input(self, action):
        return inventory_mgr._handle_examine_input(self, action)

    def _handle_midas_brew_input(self, action):
        return inventory_mgr._handle_midas_brew_input(self, action)

    def _handle_destroy_confirm_input(self, action):
        return inventory_mgr._handle_destroy_confirm_input(self, action)

    def _handle_deep_fryer_input(self, action):
        return inventory_mgr._handle_deep_fryer_input(self, action)

    def _destroy_item(self, index):
        return inventory_mgr._destroy_item(self, index)

    # ------------------------------------------------------------------
    # Ring Replacement
    # ------------------------------------------------------------------

    def _handle_ring_replace_input(self, action):
        return inventory_mgr._handle_ring_replace_input(self, action)

    def _replace_ring_at_slot(self, slot_index: int):
        return inventory_mgr._replace_ring_at_slot(self, slot_index)

    # ------------------------------------------------------------------
    # Crafting / Combine
    # ------------------------------------------------------------------

    def _is_valid_combine_target(self, inv_idx):
        return inventory_mgr._is_valid_combine_target(self, inv_idx)

    def _get_valid_combine_targets(self):
        return inventory_mgr._get_valid_combine_targets(self)

    def _init_combine_cursor(self):
        return inventory_mgr._init_combine_cursor(self)

    def _handle_combine_input(self, action):
        return inventory_mgr._handle_combine_input(self, action)

    def _try_combine(self, index_a, index_b):
        return inventory_mgr._try_combine(self, index_a, index_b)

    # ------------------------------------------------------------------
    # Targeting mode
    # ------------------------------------------------------------------

    def _get_smart_targeting_cursor(self) -> list[int]:
        """Return [x, y] for cursor start: last targeted enemy if alive/visible,
        else nearest visible enemy, else player position."""
        last = self.last_targeted_enemy
        if (last is not None and getattr(last, 'alive', False)
                and self.dungeon.visible[last.y, last.x]):
            return [last.x, last.y]
        # Fallback: nearest visible enemy (no range cap)
        best = None
        best_dist = 9999
        for entity in self.dungeon.get_monsters():
            if not entity.alive:
                continue
            if not self.dungeon.visible[entity.y, entity.x]:
                continue
            dist = abs(entity.x - self.player.x) + abs(entity.y - self.player.y)
            if dist < best_dist:
                best = entity
                best_dist = dist
        if best is not None:
            return [best.x, best.y]
        return [self.player.x, self.player.y]

    def _record_targeted_enemy_at(self, tx: int, ty: int) -> None:
        """Record the alive monster at (tx, ty) as the last targeted enemy."""
        for e in self.dungeon.get_entities_at(tx, ty):
            if e.entity_type == "monster" and e.alive:
                self.last_targeted_enemy = e
                return

    # ------------------------------------------------------------------
    # Entity targeting (f-key: cycle visible monsters within weapon range)
    # ------------------------------------------------------------------

    def _get_weapon_reach(self) -> int:
        return spells._get_weapon_reach(self)

    def _build_entity_target_list(self, reach: int) -> list:
        return spells._build_entity_target_list(self, reach)

    def _action_start_entity_targeting(self, _action):
        return spells._action_start_entity_targeting(self, _action)

    def _handle_entity_targeting_input(self, action):
        return spells._handle_entity_targeting_input(self, action)

    # ------------------------------------------------------------------
    # Gun system
    # ------------------------------------------------------------------

    def _get_primary_gun(self):
        return gun_system._get_primary_gun(self)

    def _find_nearest_visible_enemy(self, max_range):
        return gun_system._find_nearest_visible_enemy(self, max_range)

    def _enter_gun_ability_targeting(self, spec: dict) -> bool:
        return gun_system._enter_gun_ability_targeting(self, spec)

    def _action_fire_gun(self, _action):
        return gun_system._action_fire_gun(self, _action)

    def _handle_gun_targeting_input(self, action):
        return gun_system._handle_gun_targeting_input(self, action)

    def _get_gun_cone_tiles(self, tx, ty):
        return gun_system._get_gun_cone_tiles(self, tx, ty)

    def _get_gun_line_tiles(self, tx, ty, max_range):
        return gun_system._get_gun_line_tiles(self, tx, ty, max_range)

    def _get_gun_circle_tiles(self, cx, cy, radius):
        return gun_system._get_gun_circle_tiles(self, cx, cy, radius)

    def _resolve_gun_ability_shot(self, tx, ty):
        return gun_system._resolve_gun_ability_shot(self, tx, ty)

    def _resolve_cone_shot(self, tx, ty):
        return gun_system._resolve_cone_shot(self, tx, ty)

    def _resolve_circle_shot(self, tx, ty):
        return gun_system._resolve_circle_shot(self, tx, ty)

    def _resolve_gun_shot(self, tx, ty):
        return gun_system._resolve_gun_shot(self, tx, ty)

    def _action_reload_gun(self, _action):
        return gun_system._action_reload_gun(self, _action)

    def _action_swap_primary_gun(self, _action):
        return gun_system._action_swap_primary_gun(self, _action)

    def _enter_targeting(self, item_index):
        return spells._enter_targeting(self, item_index)

    def _handle_targeting_input(self, action):
        return spells._handle_targeting_input(self, action)

    def _throw_item(self, item_index, tx, ty):
        return spells._throw_item(self, item_index, tx, ty)

    # ------------------------------------------------------------------
    # Dosidos spell targeting
    # ------------------------------------------------------------------

    def _get_targeting_ability_def(self):
        return spells._get_targeting_ability_def(self)

    def _is_targeting_in_range(self, tx: int, ty: int) -> bool:
        return spells._is_targeting_in_range(self, tx, ty)

    def _enter_spell_targeting(self, spell_dict: dict) -> None:
        return spells._enter_spell_targeting(self, spell_dict)

    def _execute_spell_at(self, tx: int, ty: int) -> bool:
        self._snapshot_monster_hps()
        result = spells._execute_spell_at(self, tx, ty)
        if result:
            self._check_post_ability_drink_effects()
        return result

    def _execute_dosidos_spell_at(self, tx: int, ty: int) -> bool:
        return spells._execute_dosidos_spell_at(self, tx, ty)

    # ------------------------------------------------------------------
    # Dosidos spell implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _dist_sq(x0: int, y0: int, x1: int, y1: int) -> int:
        return spells._dist_sq(x0, y0, x1, y1)

    def _ray_tiles(self, start_x: int, start_y: int, dx: int, dy: int, max_dist: int = 10):
        return spells._ray_tiles(self, start_x, start_y, dx, dy, max_dist)

    def _trace_projectile(self, x0: int, y0: int, tx: int, ty: int):
        return spells._trace_projectile(self, x0, y0, tx, ty)

    def _spell_dimension_door(self, tx: int, ty: int) -> bool:
        return spells._spell_dimension_door(self, tx, ty)

    def _spell_chain_lightning(self, tx: int, ty: int, total_hits: int) -> bool:
        return spells._spell_chain_lightning(self, tx, ty, total_hits)

    def _spell_ray_of_frost(self, dx: int, dy: int) -> None:
        return spells._spell_ray_of_frost(self, dx, dy)

    def _spell_warp(self) -> None:
        return spells._spell_warp(self)

    def _player_ignite_duration(self) -> int:
        return spells._player_ignite_duration(self)

    def _spell_firebolt(self, tx: int, ty: int) -> bool:
        return spells._spell_firebolt(self, tx, ty)

    def _spell_arcane_missile(self, tx: int, ty: int) -> bool:
        return spells._spell_arcane_missile(self, tx, ty)

    def _spell_breath_fire(self, tx: int, ty: int) -> bool:
        return spells._spell_breath_fire(self, tx, ty)

    def _spell_fireball(self, tx: int, ty: int) -> bool:
        return spells._spell_fireball(self, tx, ty)

    def _get_cone_tiles(self, cx: int, cy: int, dir_x: float, dir_y: float, range_dist: int = 5):
        return spells._get_cone_tiles(self, cx, cy, dir_x, dir_y, range_dist)

    def _spell_zap(self, tx: int, ty: int) -> bool:
        return spells._spell_zap(self, tx, ty)

    def _spell_corn_dog(self, tx: int, ty: int) -> bool:
        return spells._spell_corn_dog(self, tx, ty)

    def _spell_pry(self, tx: int, ty: int) -> bool:
        return spells._spell_pry(self, tx, ty)

    def _spell_ags_charge(self, tx: int, ty: int) -> bool:
        return spells._spell_ags_charge(self, tx, ty)

    def _spell_polarize(self, tx: int, ty: int) -> bool:
        return spells._spell_polarize(self, tx, ty)

    def _spell_ddd_puncture(self, tx: int, ty: int) -> bool:
        return spells._spell_ddd_puncture(self, tx, ty)

    def _spell_lesser_cloudkill(self, tx: int, ty: int) -> bool:
        return spells._spell_lesser_cloudkill(self, tx, ty)

    def _get_lesser_cloudkill_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells._get_lesser_cloudkill_affected_tiles(self, tx, ty)

    def _get_wizard_bomb_bonus(self) -> int:
        return spells._get_wizard_bomb_bonus(self)

    # ------------------------------------------------------------------
    # Spell targeting visualization
    # ------------------------------------------------------------------

    def get_spell_affected_tiles(self, spell_type: str, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells.get_spell_affected_tiles(self, spell_type, tx, ty)

    def get_targeting_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells.get_targeting_affected_tiles(self, tx, ty)

    def _get_breath_fire_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells._get_breath_fire_affected_tiles(self, tx, ty)

    def _spell_curse_of_ham(self, tx: int, ty: int) -> bool:
        return spells._spell_curse_of_ham(self, tx, ty)

    def _spell_curse_of_dot(self, tx: int, ty: int) -> bool:
        return spells._spell_curse_of_dot(self, tx, ty)

    def _spell_curse_of_covid(self, tx: int, ty: int) -> bool:
        return spells._spell_curse_of_covid(self, tx, ty)

    def _get_curse_of_ham_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells._get_curse_of_ham_affected_tiles(self, tx, ty)

    def _get_ray_of_frost_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells._get_ray_of_frost_affected_tiles(self, tx, ty)

    def _get_outbreak_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        return spells._get_outbreak_affected_tiles(self, tx, ty)

    def _get_zombie_stare_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Return affected tiles for Zombie Stare. Cone at L5+, single tile otherwise."""
        if self.skills.get("Infected").level >= 5:
            import math
            dx = tx - self.player.x
            dy = ty - self.player.y
            if dx == 0 and dy == 0:
                return []
            dist = math.sqrt(dx * dx + dy * dy)
            return spells._get_cone_tiles(
                self, self.player.x, self.player.y,
                dx / dist, dy / dist,
                range_dist=3, half_angle_deg=45, min_spread=0,
            )
        return [(tx, ty)]

    # ------------------------------------------------------------------
    # Ability system
    # ------------------------------------------------------------------

    def grant_ability(self, ability_id: str):
        return spells.grant_ability(self, ability_id)

    def revoke_ability(self, ability_id: str):
        return spells.revoke_ability(self, ability_id)

    def grant_ability_charges(self, ability_id: str, n: int, silent: bool = False) -> None:
        return spells.grant_ability_charges(self, ability_id, n, silent)

    def _consume_ability_charge(self) -> str | None:
        return spells._consume_ability_charge(self)

    def _action_toggle_abilities(self, _action):
        return spells._action_toggle_abilities(self, _action)

    def _get_usable_abilities(self):
        return spells._get_usable_abilities(self)

    def _handle_abilities_menu_input(self, action):
        return spells._handle_abilities_menu_input(self, action)

    def _execute_ability(self, index: int) -> bool:
        self._snapshot_monster_hps()
        result = spells._execute_ability(self, index)
        if result:
            self._check_post_ability_drink_effects()
        return result

    def _enter_adjacent_ability_targeting(self, index: int, defn) -> bool:
        return spells._enter_adjacent_ability_targeting(self, index, defn)

    def _fire_adjacent_ability(self, tx: int, ty: int) -> bool:
        self._snapshot_monster_hps()
        result = spells._fire_adjacent_ability(self, tx, ty)
        if result:
            self._check_post_ability_drink_effects()
        return result

    def _handle_adjacent_tile_targeting_input(self, action) -> bool:
        return spells._handle_adjacent_tile_targeting_input(self, action)

    def _pickup_items_at(self, x: int, y: int):
        return item_effects._pickup_items_at(self, x, y)

    def _apply_item_effect_to_entity(self, effect_def, entity):
        return item_effects._apply_item_effect_to_entity(self, effect_def, entity)

    def _apply_strain_effect(self, entity, strain, roll, target="player"):
        return item_effects._apply_strain_effect(self, entity, strain, roll, target)

    def _gain_smoking_xp(self, strain):
        return xp_progression._gain_smoking_xp(self, strain)

    def _gain_rolling_xp(self, strain, is_grinding=False):
        return xp_progression._gain_rolling_xp(self, strain, is_grinding)

    def _gain_munching_xp(self, food_id):
        return xp_progression._gain_munching_xp(self, food_id)

    def _gain_deep_frying_xp(self, food_item_id):
        return xp_progression._gain_deep_frying_xp(self, food_item_id)

    def _gain_ammo_rat_xp(self, item_id: str):
        return xp_progression._gain_ammo_rat_xp(self, item_id)

    def _gain_alcohol_xp(self, drink_id: str):
        return xp_progression._gain_alcohol_xp(self, drink_id)

    def _handle_alcohol(self, item, drink_id: str):
        return xp_progression._handle_alcohol(self, item, drink_id)

    def _handle_purple_drank(self, item):
        return xp_progression._handle_purple_drank(self, item)

    def _handle_red_drank(self, item):
        return xp_progression._handle_red_drank(self, item)

    def _handle_green_drank(self, item):
        return xp_progression._handle_green_drank(self, item)

    def _handle_blue_drank(self, item):
        return xp_progression._handle_blue_drank(self, item)

    def _handle_mana_drink(self, item, drink_id: str):
        return xp_progression._handle_mana_drink(self, item, drink_id)

    def _apply_virulent_vodka(self, target, damage):
        """Apply Virulent Vodka toxicity if buff is active. Called after direct player damage."""
        from effects import _apply_virulent_vodka_tox
        vv = next((e for e in self.player.status_effects
                    if getattr(e, 'id', '') == 'virulent_vodka'), None)
        if vv:
            _apply_virulent_vodka_tox(self, target, damage, vv.stacks)

    def _check_decontamination_proc(self, target):
        """Decontamination L3: 20% chance on any player damage to apply 100 radiation to target."""
        if (target.entity_type != "monster" or not target.alive
                or self.skills.get("Decontamination").level < 3):
            return
        import random as _rng
        if _rng.random() < 0.20:
            from combat import add_radiation
            add_radiation(self, target, 100)
            self.messages.append([
                (f"{target.name} is irradiated! ", (120, 255, 80)),
                ("+100 radiation", (160, 255, 120)),
            ])

    def _snapshot_monster_hps(self):
        """Snapshot current HP of all monsters for ability damage tracking (Mana Drink)."""
        self._monster_hp_snapshot = {
            id(m): m.hp for m in self.dungeon.get_monsters() if m.alive
        }

    def _check_post_ability_drink_effects(self):
        """After ability execution, process Mana Drink heal and Virulent Vodka tox from snapshot."""
        import random as _rng
        from effects import _apply_virulent_vodka_tox
        snapshot = getattr(self, '_monster_hp_snapshot', None)
        if snapshot is None:
            return

        mana_eff = next((e for e in self.player.status_effects
                         if getattr(e, 'id', '') == 'mana_drink'), None)
        vv_eff = next((e for e in self.player.status_effects
                       if getattr(e, 'id', '') == 'virulent_vodka'), None)

        if mana_eff is None and vv_eff is None:
            self._monster_hp_snapshot = None
            return

        # Calculate per-target damage
        per_target_dmg = {}
        for m in self.dungeon.get_monsters():
            old_hp = snapshot.get(id(m))
            if old_hp is not None and m.hp < old_hp:
                per_target_dmg[id(m)] = (m, old_hp - m.hp)
        # Include killed monsters no longer in entity list
        for mid, old_hp in snapshot.items():
            if mid not in per_target_dmg:
                found = any(id(m) == mid for m in self.dungeon.get_monsters())
                if not found:
                    per_target_dmg[mid] = (None, old_hp)

        total_dmg = sum(dmg for _, dmg in per_target_dmg.values())

        # Virulent Vodka: apply tox per target
        if vv_eff and per_target_dmg:
            for mid, (target, dmg) in per_target_dmg.items():
                if target is not None:
                    _apply_virulent_vodka_tox(self, target, dmg, vv_eff.stacks)

        # Decontamination L3: proc on each damaged target
        for mid, (target, dmg) in per_target_dmg.items():
            if target is not None:
                self._check_decontamination_proc(target)

        # Mana Drink: heal based on total damage
        if mana_eff and total_dmg > 0:
            heal_pct = 0.15 * mana_eff.stacks
            heal_amt = max(1, int(total_dmg * heal_pct))
            old_hp = self.player.hp
            self.player.heal(heal_amt)
            actual = self.player.hp - old_hp
            if actual > 0:
                self.messages.append([
                    ("Mana Drink: ", (0, 220, 220)),
                    (f"+{actual} HP", (100, 255, 255)),
                    (f" ({self.player.hp}/{self.player.max_hp})", (150, 150, 150)),
                ])
            # Remove 1 tox or 1 rad at random per heal trigger
            has_tox = getattr(self.player, 'toxicity', 0) > 0
            has_rad = getattr(self.player, 'radiation', 0) > 0
            if has_tox or has_rad:
                choices = []
                if has_tox:
                    choices.append('tox')
                if has_rad:
                    choices.append('rad')
                pick = _rng.choice(choices)
                if pick == 'tox':
                    self.player.toxicity = max(0, self.player.toxicity - 1)
                    self.messages.append([("  -1 toxicity", (100, 255, 200))])
                else:
                    self.player.radiation = max(0, self.player.radiation - 1)
                    self.messages.append([("  -1 radiation", (100, 200, 255))])
        self._monster_hp_snapshot = None

    def _gain_item_skill_xp(self, skill_name: str, item_id: str, silent: bool = False) -> None:
        return xp_progression._gain_item_skill_xp(self, skill_name, item_id, silent)

    def _sticky_fingers_check(self, item_id: str) -> None:
        return xp_progression._sticky_fingers_check(self, item_id)

    def _gain_jaywalking_xp(self) -> None:
        return xp_progression._gain_jaywalking_xp(self)

    _STASH_FINDER_DRINKS = [
        "40oz", "natty_light", "jagermeister", "butterbeer", "fireball_shooter",
        "blue_lagoon", "absinthe", "malt_liquor", "homemade_hennessy", "steel_reserve",
        "mana_drink", "five_loco",
    ]

    def _stash_finder_proc(self):
        """Alcoholism L3 Stash Finder: add a random alcohol to inventory."""
        drink = random.choice(self._STASH_FINDER_DRINKS)
        self._add_item_to_inventory(drink)
        from items import ITEM_DEFS
        name = ITEM_DEFS[drink]["name"]
        self.messages.append([
            ("Stash Finder! ", (255, 200, 100)),
            (f"You found a {name} stashed in the room!", (200, 180, 120)),
        ])

    def _check_titan_blood_proc(self):
        """Titan's Blood Ring: activate Titan Form on crossing below 25% HP."""
        if not self._titan_blood_available or not self._titan_blood_was_above_25:
            return
        if self.player.max_hp <= 0:
            return
        ratio = self.player.hp / self.player.max_hp
        if ratio >= 0.25:
            return
        # Crossed below 25% — check if ring is equipped
        from items import get_item_def
        has_ring = False
        for ring in self.rings:
            if ring is not None:
                defn = get_item_def(ring.item_id)
                if defn and "titan_blood" in defn.get("tags", []):
                    has_ring = True
                    break
        if not has_ring:
            return
        self._titan_blood_available = False
        self._titan_blood_was_above_25 = False
        effects.apply_effect(self.player, self, "titan_form", duration=20)
        self.messages.append([
            ("TITAN FORM! ", (255, 50, 50)),
            ("+50 temp HP, +50% melee damage, 25% stun chance for 20 turns!", (255, 180, 180)),
        ])

    def _straw_hat_death_save(self) -> bool:
        """Straw Hat: negate killing blow, revive at 50% HP, teleport to room 0, destroy hat."""
        from items import get_item_def
        hat = self.hat
        if hat is None:
            return False
        defn = get_item_def(hat.item_id)
        if not defn or "straw_hat" not in defn.get("tags", []):
            return False
        # Revive
        self.player.hp = self.player.max_hp // 2
        self.player.alive = True
        # Teleport to spawn room (room 0)
        import random as _rng
        room = self.dungeon.rooms[0]
        tiles = room.floor_tiles(self.dungeon)
        free = [(x, y) for x, y in tiles if not self.dungeon.is_blocked(x, y)]
        if not free:
            free = tiles
        tx, ty = _rng.choice(free)
        self.dungeon.move_entity(self.player, tx, ty)
        self._compute_fov()
        # Destroy the hat
        self.hat = None
        from inventory_mgr import _refresh_ring_stat_bonuses
        _refresh_ring_stat_bonuses(self)
        self.messages.append([
            ("The Straw Hat glows! ", (220, 200, 80)),
            ("You are saved from death!", (255, 255, 100)),
        ])
        self.messages.append([
            ("The Straw Hat crumbles to dust...", (180, 160, 80)),
        ])
        return True

    def _intimidation_ring_proc(self, room_idx: int) -> None:
        """Ring of Intimidation: fear all enemies in the room whose max HP <= 30% of player max HP."""
        from items import get_item_def
        has_ring = False
        for ring in self.rings:
            if ring is not None:
                defn = get_item_def(ring.item_id)
                if defn and "intimidation_ring" in defn.get("tags", []):
                    has_ring = True
                    break
        if not has_ring:
            return
        threshold = self.player.max_hp * 0.30
        feared = []
        for ent in self.dungeon.entities:
            if ent.entity_type != "monster" or not getattr(ent, "alive", True):
                continue
            if self.dungeon.get_room_index_at(ent.x, ent.y) != room_idx:
                continue
            if ent.max_hp <= threshold:
                effects.apply_effect(ent, self, "fear", duration=15,
                                     source_x=self.player.x, source_y=self.player.y)
                feared.append(ent.name)
        if feared:
            names = ", ".join(feared)
            self.messages.append([
                ("Intimidation! ", (200, 50, 50)),
                (f"{names} cower in fear!", (220, 180, 180)),
            ])

    def _gain_abandoning_xp(self) -> None:
        return xp_progression._gain_abandoning_xp(self)

    def _gain_melee_xp(self, skill_name: str, damage: int) -> None:
        return xp_progression._gain_melee_xp(self, skill_name, damage)

    def _gain_catchin_fades_xp(self, damage: int) -> None:
        return xp_progression._gain_catchin_fades_xp(self, damage)

    def _gain_elementalist_xp(self, target, damage: int, spell_element: str) -> None:
        return xp_progression._gain_elementalist_xp(self, target, damage, spell_element)

    def _gain_spell_xp(self, ability_id: str) -> None:
        xp_progression._gain_spell_xp(self, ability_id)
        # Blue graffiti XP: +10 when casting a spell while on blue spray paint
        if self.dungeon.spray_paint.get((self.player.x, self.player.y)) == "blue":
            adjusted = round(10 * self.player_stats.xp_multiplier)
            self.skills.gain_potential_exp(
                "Graffiti", adjusted,
                self.player_stats.effective_book_smarts,
                briskness=self.player_stats.total_briskness
            )
        self._graffiti_proc_blue()

    def _graffiti_proc_blue(self):
        """Graffiti L3: 20% chance on ability use to paint player's tile blue."""
        if self.skills.get("Graffiti").level < 3:
            return
        import random as _rng
        if _rng.random() < 0.20:
            px, py = self.player.x, self.player.y
            self.dungeon.spray_paint[(px, py)] = "blue"
            self.messages.append([
                ("Graffiti! ", (80, 140, 255)),
                ("Your tile turns blue!", (130, 180, 255)),
            ])

    def _graffiti_proc_red(self, defender):
        """Graffiti L3: 20% chance on melee hit to paint enemy's tile red."""
        if self.skills.get("Graffiti").level < 3:
            return
        import random as _rng
        if _rng.random() < 0.20:
            self.dungeon.spray_paint[(defender.x, defender.y)] = "red"
            self.messages.append([
                ("Graffiti! ", (255, 40, 40)),
                (f"{defender.name}'s tile turns red!", (255, 100, 100)),
            ])

    def _smoking_proc_on_hit(self):
        """Smoking L3: 10% chance when hit to auto-smoke a random joint from inventory."""
        if not hasattr(self, 'skills') or self.skills.get("Smoking").level < 3:
            return
        import random as _rng
        if _rng.random() >= 0.10:
            return
        # Find joints in inventory
        joints = [
            (i, item) for i, item in enumerate(self.player.inventory)
            if getattr(item, 'item_id', None) == "joint" and getattr(item, 'strain', None)
        ]
        if not joints:
            return
        idx, joint = _rng.choice(joints)
        # Roll and apply strain effect
        from inventory_mgr import calc_tolerance_rolls
        tlr = self.player_stats.effective_tolerance
        num_rolls, roll_floor = calc_tolerance_rolls(joint.strain, tlr)
        rolls = [max(roll_floor + 1, _rng.randint(1, 100)) for _ in range(num_rolls)]
        roll = max(rolls)
        self.messages.append([
            ("Stress Smoke! ", (180, 140, 60)),
            (f"You reflexively smoke a {joint.name}. (Roll: {roll})", (220, 200, 120)),
        ])
        self._apply_strain_effect(self.player, joint.strain, roll, "player")
        self._gain_smoking_xp(joint.strain)

    def _graffiti_proc_green(self):
        """Graffiti L3: 20% chance on taking damage to paint player's tile green."""
        if not hasattr(self, 'skills') or self.skills.get("Graffiti").level < 3:
            return
        import random as _rng
        if _rng.random() < 0.20:
            px, py = self.player.x, self.player.y
            self.dungeon.spray_paint[(px, py)] = "green"
            self.messages.append([
                ("Graffiti! ", (80, 255, 80)),
                ("Your tile turns green!", (130, 255, 130)),
            ])

    def _apply_blue_lobster_effect(self, entity, roll, is_player):
        return item_effects._apply_blue_lobster_effect(self, entity, roll, is_player)

    # ------------------------------------------------------------------
    # Status effects
    # ------------------------------------------------------------------

    def tick_status_effects(self, entity):
        """Tick all status effects on entity. Delegates to effects.tick_all_effects."""
        effects.tick_all_effects(entity, self)

    # ------------------------------------------------------------------

    def is_running(self):
        """Check if game should continue."""
        return self.running and not self.game_over
