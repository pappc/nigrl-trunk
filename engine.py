"""
Game engine and turn management.
"""

import math
import random
import time
from collections import deque
import numpy as np
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


class GameEngine:
    """Main game logic and state management."""

    # Display mode presets
    DISPLAY_MODES = [
        {"label": "Windowed",              "flags": "windowed",   "width": 1920, "height": 1088},
        {"label": "Borderless 1080p",      "flags": "borderless", "width": 1920, "height": 1080},
        {"label": "Borderless 1440p",      "flags": "borderless", "width": 2560, "height": 1440},
    ]

    def __init__(self):
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
        self.dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT)
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
        self.restart_requested: bool = False
        self.entered_meth_lab: bool = False  # unlocks toxicity display on char sheet
        self.skills_cursor: int = 0        # selected skill row (0-14)
        self.skills_spend_mode: bool = False   # spend-amount prompt open
        self.skills_spend_input: str = ""      # digits typed by user
        self.messages: deque = deque(maxlen=LOG_HISTORY_SIZE)
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
        self.equipment_cursor: int = 0  # indexes into flat occupied-slot list (weapon → neck → feet → hat → rings)

        # --- Sublevel state ---
        self._sublevel_return_floor: int | None = None
        self._sublevel_return_dungeon = None
        self._sublevel_return_pos: tuple | None = None

        # --- Menu state (single enum replaces bools + strings) ---
        self.menu_state = MenuState.NONE
        self.selected_item_index: int | None = None
        self.selected_item_actions: list[str] = []
        self.item_menu_cursor: int = 0
        self.combine_target_cursor: int | None = None  # inventory index highlighted in COMBINE_SELECT

        # --- Ring replacement state ---
        self.pending_ring_item_index: int | None = None  # inventory index of ring being equipped
        self.ring_replace_cursor: int = 0  # which equipped ring to replace (0-9)

        # --- Targeting mode state ---
        self.targeting_item_index: int | None = None
        self.targeting_cursor: list[int] = [0, 0]
        self.targeting_spell: dict | None = None
        self.targeting_ability_index: int | None = None  # ability whose charge to consume on fire
        self.spray_paint_pending: dict | None = None     # {"item_index": int, "spray_type": str}
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
        self.move_cost_reduction: int = 0  # energy refunded per actual move step (Air Jordans perk)
        self._player_just_moved: bool = False  # True when the last handle_move did real movement

        # --- Gun system state ---
        self.primary_gun: str | None = None       # "sidearm" or "weapon" slot name
        self.gun_firing_mode: str = "accurate"    # current mode for gun targeting UI
        self.gun_targeting_cursor: list[int] = [0, 0]  # (x, y) cursor for gun targeting
        self.gun_consecutive_target_id: str | None = None  # instance_id of last target fired at
        self.gun_consecutive_count: int = 0                # stacking consecutive hit counter
        self.gatting_consecutive_target_id: str | None = None  # Gatting L1 perk tracker
        self.gatting_consecutive_count: int = 0                # Gatting L1 stacking bonus
        self.gun_ability_active: dict | None = None  # active gun ability spec during GUN_TARGETING
        self.gun_jammed: bool = False  # True when gun is jammed; must clear before firing
        self.snipers_mark_target_id: str | None = None  # instance_id of marked target
        self.dead_eye_swagger_gained: int = 0              # Sniping L2: swagger gained this floor
        self.unfazed_swagger_gained: int = 0               # L Farming L3: swagger gained this floor

        # --- Mutation system ---
        self.mutation_log: list[dict] = []

        # --- Look mode state ---
        self.look_cursor: list[int] = [0, 0]
        self.look_info_lines: list = []
        self.look_info_title: str = ""

        # --- Dev tools state (only active when DEV_MODE = True) ---
        self.dev_menu_cursor: int = 0           # selected option in dev menu
        self.dev_item_list: list[str] = []      # flat sorted list of item_ids for spawn picker
        self.dev_item_cursor: int = 0           # cursor position in spawn picker
        self.dev_item_scroll: int = 0           # scroll offset for spawn picker
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

    def _on_entity_damaged(self, entity, raw_damage, hp_damage):
        """Callback for floating damage numbers (monsters only)."""
        if self.sdl_overlay is None or entity == self.player:
            return
        amount = hp_damage if hp_damage > 0 else raw_damage
        self.sdl_overlay.add_floating_text(entity.x, entity.y, str(amount), (255, 80, 80))

    def _on_entity_healed(self, entity, amount):
        """Callback for floating heal numbers."""
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

    def _on_entity_died(self, entity, killer=None):
        """Universal death handler — removes entity and bookkeeps kills."""
        self.dungeon.remove_entity(entity)
        # Clear aggro references pointing at a dying summon
        if getattr(entity, "is_summon", False):
            for m in self.dungeon.get_monsters():
                if getattr(m, "aggro_target", None) is entity:
                    m.aggro_target = None
        if entity.entity_type == "monster" and not getattr(entity, "is_summon", False):
            self.kills += 1
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
                    ("Nigle Fart: +1 permanent Tolerance!", (200, 180, 60)),
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
        """Toxic Harvest buff: any monster kill grants +5 toxicity and refreshes the buff."""
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
        self.add_toxicity(self.player, 5)
        harvest.duration = 10  # refresh full duration
        self.messages.append([
            ("Toxic Harvest: ", (80, 255, 80)),
            ("+5 toxicity!", (160, 255, 160)),
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

    # ------------------------------------------------------------------
    # Main action dispatch
    # ------------------------------------------------------------------

    def process_action(self, action):
        """Process player action and update game state. Returns True if a turn was consumed."""
        if not action:
            return False

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

        # --- Normal gameplay dispatch ---
        handler = self._gameplay_handlers.get(action_type)
        if not handler:
            return False

        result = handler(action)

        # Energy tick: player spends energy, then run ticks until player can act again
        if result and self.running and self.player.alive:
            self.player.energy -= ENERGY_THRESHOLD
            if action_type == "move" and self._player_just_moved and self.move_cost_reduction > 0:
                self.player.energy += self.move_cost_reduction
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
                    self.player.energy -= ENERGY_THRESHOLD
                    if self._player_just_moved and self.move_cost_reduction > 0:
                        self.player.energy += self.move_cost_reduction
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
            tick_data = prepare_ai_tick(self.player, self.dungeon, monsters)

            # 1. Distribute energy to all living entities
            for entity in [self.player] + monsters:
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
                    else:
                        cost = ENERGY_THRESHOLD
                    monster.energy -= cost

            # 3. Tick status effects once per energy cycle
            self.turn += 1
            effects.tick_all_effects(self.player, self)
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

            # Tick ability cooldowns
            for key in list(self.ability_cooldowns):
                self.ability_cooldowns[key] -= 1
                if self.ability_cooldowns[key] <= 0:
                    del self.ability_cooldowns[key]

            # Tick rad bomb crystals
            self._tick_rad_bomb_crystals(monsters)

            # 4. Fire / toxic creep hazard: affect entities standing on hazard tiles
            for entity in [self.player] + monsters:
                if not entity.alive:
                    continue
                for hazard in self.dungeon.get_entities_at(entity.x, entity.y):
                    ht = getattr(hazard, "hazard_type", None)
                    if ht == "fire":
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

            # 4b. Tick timed hazards (decrement duration, remove expired)
            for hazard in list(self.dungeon.entities):
                if getattr(hazard, "entity_type", None) != "hazard":
                    continue
                hd = getattr(hazard, "hazard_duration", 0)
                if hd > 0:
                    hazard.hazard_duration -= 1
                    if hazard.hazard_duration <= 0:
                        self.dungeon.remove_entity(hazard)

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
        """Consume a turn without performing any action."""
        return True

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
        "meth_lab_kit",
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

        elif option == "meth_lab_kit":
            self._dev_meth_lab_kit()

        self.menu_state = MenuState.NONE

    def _dev_meth_lab_kit(self):
        """Set up a mid-game character for Meth Lab testing."""
        import random as _rng
        from skills import SKILL_NAMES, MAX_LEVEL
        from items import ITEM_DEFS, create_item_entity
        from loot import pick_random_consumable

        # --- Skills: 1 at level 2, 4 at level 4 ---
        skill_pool = list(SKILL_NAMES)
        _rng.shuffle(skill_pool)
        picked = skill_pool[:5]
        # First skill → level 2
        s = self.skills.get(picked[0])
        old = s.level
        s.level = max(s.level, 2)
        for lvl in range(old + 1, s.level + 1):
            self._apply_perk(picked[0], lvl)
        # Next 4 skills → level 4
        for name in picked[1:5]:
            s = self.skills.get(name)
            old = s.level
            s.level = max(s.level, 4)
            for lvl in range(old + 1, s.level + 1):
                self._apply_perk(name, lvl)

        # --- 5,000 potential XP spread across random skills ---
        all_skills = list(SKILL_NAMES)
        for _ in range(50):  # 50 chunks of 100
            sk = _rng.choice(all_skills)
            self.skills.get(sk).potential_exp += 100

        # --- 300 skill points ---
        self.skills.skill_points += 300

        # --- 15 random consumables ---
        for _ in range(15):
            item_id, strain = pick_random_consumable("crack_den")
            ent = Entity(**create_item_entity(item_id, 0, 0))
            if strain:
                ent.strain = strain
            self.player.inventory.append(ent)

        # --- Equipment: 4 rings, 1 neck, 1 feet, 2 weapons (crack_den only, no guns) ---
        def _in_crack_den(v):
            return "crack_den" in v.get("zones", [])

        ring_ids = [k for k, v in ITEM_DEFS.items()
                    if v.get("equip_slot") == "ring" and _in_crack_den(v)]
        neck_ids = [k for k, v in ITEM_DEFS.items()
                    if v.get("equip_slot") == "neck" and _in_crack_den(v)]
        feet_ids = [k for k, v in ITEM_DEFS.items()
                    if v.get("equip_slot") == "feet" and _in_crack_den(v)]
        weapon_ids = [k for k, v in ITEM_DEFS.items()
                      if v.get("equip_slot") == "weapon" and "gun_class" not in v
                      and _in_crack_den(v)]

        for item_id in _rng.sample(ring_ids, min(4, len(ring_ids))):
            self.player.inventory.append(Entity(**create_item_entity(item_id, 0, 0)))
        for item_id in _rng.sample(neck_ids, min(1, len(neck_ids))):
            self.player.inventory.append(Entity(**create_item_entity(item_id, 0, 0)))
        for item_id in _rng.sample(feet_ids, min(1, len(feet_ids))):
            self.player.inventory.append(Entity(**create_item_entity(item_id, 0, 0)))
        for item_id in _rng.sample(weapon_ids, min(2, len(weapon_ids))):
            self.player.inventory.append(Entity(**create_item_entity(item_id, 0, 0)))

        # --- All crack den tools ---
        from loot import ZONE_TOOL_TABLES
        for tool_id, _ in ZONE_TOOL_TABLES.get("crack_den", []):
            self.player.inventory.append(Entity(**create_item_entity(tool_id, 0, 0)))

        self._sort_inventory()
        self.messages.append("[DEV] Meth Lab Kit applied! Skills, items, and equipment added.")

    def _handle_dev_item_select_input(self, action):
        """Handle input in the dev item spawn picker."""
        action_type = action.get("type")
        n = len(self.dev_item_list)

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
                self.dev_item_cursor = max(0, min(n - 1, self.dev_item_cursor + dy))
            return False

        if action_type == "confirm_target":
            if self.dev_item_list:
                item_id = self.dev_item_list[self.dev_item_cursor]
                entity = Entity(**create_item_entity(item_id, 0, 0))
                self.player.inventory.append(entity)
                self._sort_inventory()
                from items import get_item_def
                defn = get_item_def(item_id)
                name = defn.get("name", item_id) if defn else item_id
                self.messages.append(f"[DEV] Added {name} to inventory.")
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
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key, floor_event=event_id)
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

        # Track meth lab entry
        if zone_key == "meth_lab" and not self.entered_meth_lab:
            self.entered_meth_lab = True

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

    def _handle_settings_input(self, action):
        """Handle input for the settings/display menu."""
        action_type = action.get("type")
        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            return False
        if action_type == "move":
            dy = action.get("dy", 0)
            if dy != 0:
                n = len(self.DISPLAY_MODES)
                self.settings_cursor = (self.settings_cursor + dy) % n
            return False
        if action_type in ("confirm_target", "item_use"):
            self._apply_display_mode(self.settings_cursor)
            return False
        return False

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
                lines.append([(e.name, C_ENEMY)])

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

        if name == "Bash":
            self.grant_ability("bash")
            self.messages.append("  [Bash] You learn to send enemies flying with your beating weapon!")

        if name == "Crit+":
            self.crit_multiplier += 1
            self.messages.append(f"  [Crit+] Your critical hits now deal {self.crit_multiplier}x damage!")

        if name == "Gouge":
            self.grant_ability("gouge")
            self.messages.append("  [Gouge] You learn to gouge enemies with your blade!")

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

        if name == "Force Be With You":
            self.grant_ability("force_push")
            self.messages.append("  [Force Be With You] You can now force push adjacent enemies!")

        if name == "Throw Bottle":
            self.grant_ability_charges("throw_bottle", 1)

        if name == "Air Jordans":
            self.move_cost_reduction += 5
            self.messages.append("  [Air Jordans] Your kicks feel lighter. Move cost -5 energy.")

        if name == "Dash":
            self.grant_ability("dash")
            self.messages.append("  [Dash] You can now dash up to 2 tiles instantly!")

        if name == "Airer Jordans":
            self.player.speed += 10
            self.messages.append(f"  [Airer Jordans] Your speed increases. (+10 speed, now {self.player.speed})")

        if name == "Bleached":
            self.player_stats.tox_resistance += 20
            self.messages.append("  [Bleached] +20% toxicity resistance.")

        if name == "Fry Shot":
            self.grant_ability("fry_shot")
            self.messages.append("  [Fry Shot] You can now hurl hot grease at enemies within 4 tiles!")

        if name == "Slow Metabolism":
            self.grant_ability("slow_metabolism")
            self.messages.append("  [Slow Metabolism] You can now double the duration of your active drink buffs (2/floor)!")

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

        if name == "Mutagen":
            from mutations import force_mutation
            force_mutation(self)

        if name == "Favorable Odds":
            self.player_stats.good_mutation_multiplier += 0.50
            self.messages.append("  [Favorable Odds] +50% good mutation chance multiplier.")

        if name == "White Out":
            self.grant_ability("white_out")
            self.messages.append("  [White Out] Gain 25 tox for +8 Swagger and -25% damage dealt (50t). 3/floor.")

        if name == "Acid Meltdown":
            self.grant_ability("acid_meltdown")
            self.messages.append("  [Acid Meltdown] Spend 25 tox: halve move cost, kills explode into acid!")

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

        if name == "Web Trail":
            self.grant_ability("web_trail")
            self.messages.append("  [Web Trail] You are immune to webs and can leave cobwebs in your wake! 3/floor.")

        if name == "Summon Spider":
            self.grant_ability("summon_spiderling")
            self.messages.append("  [Summon Spider] Hatch spiderlings on adjacent tiles! They guard and bite. 5/floor.")

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
        index = action["index"]
        if 0 <= index < len(self.player.inventory):
            self._open_item_menu(index)
        return False

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
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key, floor_event=event_id)
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

        # Reset Sniping L2 "Dead Eye" swagger bonus
        if self.dead_eye_swagger_gained > 0:
            self.player_stats.swagger -= self.dead_eye_swagger_gained
            self.dead_eye_swagger_gained = 0

        # Reset L Farming L3 "Unfazed" swagger bonus
        if self.unfazed_swagger_gained > 0:
            self.player_stats.swagger -= self.unfazed_swagger_gained
            self.unfazed_swagger_gained = 0

        # Reset per-floor ability charges
        for inst in self.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn:
                inst.reset_floor(defn)

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

        # Refill armor at floor start
        self.player.armor = self.player.max_armor

        # Abandoning L2: Anotha Motha — spawn 5 extra items on the new floor (zones only)
        if zone_type == "zone" and self.skills.get("Abandoning").level >= 2:
            from loot import generate_floor_loot
            extra = generate_floor_loot(zone_key, zone_floor, self.skills, self.player_stats)[:5]
            spawnable = self.dungeon.rooms[1:] if len(self.dungeon.rooms) > 1 else self.dungeon.rooms
            for item_id, strain in extra:
                room = random.choice(spawnable)
                tiles = room.floor_tiles(self.dungeon)
                if tiles:
                    x, y = random.choice(tiles)
                    if not self.dungeon.is_blocked(x, y):
                        ent = Entity(**create_item_entity(item_id, x, y, strain=strain))
                        self.dungeon.add_entity(ent)
            self.messages.append("  [Anotha Motha] 5 extra items spawned on this floor!")

        # Track meth lab entry
        if zone_key == "meth_lab" and not self.entered_meth_lab:
            self.entered_meth_lab = True

        # Zone transition message
        zone_total = get_zone_total_floors(zone_key)
        if zone_key != prev_zone_key:
            self.messages.append(f"You enter {display_name}.")
        if zone_type == "pseudozone":
            self.messages.append(f"{display_name}")
        else:
            self.messages.append(
                f"You descend deeper... ({display_name} - Floor {zone_floor + 1}/{zone_total})"
            )
        return True

    def _enter_sublevel(self, sublevel_key: str):
        """Enter a sublevel dungeon (e.g. Haitian Daycare)."""
        if self.sdl_overlay:
            self.sdl_overlay.clear()

        # Remember where we came from
        self._sublevel_return_floor = self.current_floor
        self._sublevel_return_dungeon = self.dungeon
        self._sublevel_return_pos = (self.player.x, self.player.y)

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        # Generate the sublevel
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

        self.dungeon = sublevel_dungeon
        self.dungeon.first_kill_happened = False
        self.dungeon.female_kill_happened = False
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

        # Remove player from sublevel
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

        # A* path to the target
        cost = np.array(dungeon.tiles, dtype=np.int8)
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
            self.player.energy -= ENERGY_THRESHOLD
            if self._player_just_moved and self.move_cost_reduction > 0:
                self.player.energy += self.move_cost_reduction
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

        # Check for blocking entity (wall, monster, crate hazard, etc.)
        if self.dungeon.is_blocked(new_x, new_y):
            target = self.dungeon.get_blocking_entity_at(new_x, new_y)
            if target and target.entity_type == "monster" and not getattr(target, "is_summon", False):
                self.handle_attack(self.player, target)
                return True
            elif target and getattr(target, "hazard_type", None) == "crate":
                self._smash_crate(target)
                return True
            elif target and getattr(target, "hazard_type", None) == "deep_fryer":
                self._open_deep_fryer()
                return False  # no turn consumed — just opens menu
            elif target and getattr(target, "hazard_type", None) == "door":
                self._try_unlock_door(target)
                return True
            return False  # pure wall — no turn consumed

        # Failsafe: explicitly check that no living monster occupies the destination
        # This prevents any edge cases where blocks_movement might be incorrectly set
        for entity in self.dungeon.get_entities_at(new_x, new_y):
            if entity.entity_type == "monster" and getattr(entity, "alive", True) and not getattr(entity, "is_summon", False):
                self.handle_attack(self.player, entity)
                return True

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
                # Try to merge into an existing stack (skip charged items — each is unique)
                if is_stackable(entity.item_id) and getattr(entity, "charges", None) is None:
                    existing = next(
                        (i for i in self.player.inventory
                         if i.item_id == entity.item_id and i.strain == entity.strain
                         and getattr(i, "charges", None) is None),
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
    # Combat
    # ------------------------------------------------------------------

    def _compute_str_bonus(self, weapon_item):
        return combat._compute_str_bonus(self, weapon_item)

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

    def _get_cone_tiles(self, cx: int, cy: int, dir_x: float, dir_y: float, range_dist: int = 5):
        return spells._get_cone_tiles(self, cx, cy, dir_x, dir_y, range_dist)

    def _spell_zap(self, tx: int, ty: int) -> bool:
        return spells._spell_zap(self, tx, ty)

    def _spell_corn_dog(self, tx: int, ty: int) -> bool:
        return spells._spell_corn_dog(self, tx, ty)

    def _spell_pry(self, tx: int, ty: int) -> bool:
        return spells._spell_pry(self, tx, ty)

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

    def _check_glow_up_proc(self, target):
        """Glow Up L3: 20% chance on any player damage to apply 100 radiation to target."""
        if (target.entity_type != "monster" or not target.alive
                or self.skills.get("Glow Up").level < 3):
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

        # Glow Up L3: proc on each damaged target
        for mid, (target, dmg) in per_target_dmg.items():
            if target is not None:
                self._check_glow_up_proc(target)

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
        "40oz", "fireball_shooter", "malt_liquor", "homemade_hennessy",
        "steel_reserve", "mana_drink", "five_loco",
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

    def _gain_abandoning_xp(self) -> None:
        return xp_progression._gain_abandoning_xp(self)

    def _gain_melee_xp(self, skill_name: str, damage: int) -> None:
        return xp_progression._gain_melee_xp(self, skill_name, damage)

    def _gain_catchin_fades_xp(self, damage: int) -> None:
        return xp_progression._gain_catchin_fades_xp(self, damage)

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
        """Smoking L2: 10% chance when hit to auto-smoke a random joint from inventory."""
        if not hasattr(self, 'skills') or self.skills.get("Smoking").level < 2:
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
