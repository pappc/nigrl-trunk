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

    def __init__(self):
        # --- Render callback (set by main loop for mid-turn rendering) ---
        self.render_callback = None

        # --- Event bus ---
        self.event_bus = EventBus()
        self._register_events()

        # --- Floor management ---
        self.current_floor = 0
        self.total_floors = get_total_floors()
        self.dungeons: dict[int, Dungeon] = {}
        self.special_rooms_spawned: set[str] = set()  # tracks once-per-game special rooms

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
            self.player.x = x
            self.player.y = y

        # --- FOV ---
        self.fov_radius = FOV_RADIUS   # base radius; items/buffs can modify this

        self.skills = Skills()
        zone_key, zone_floor, _, _ = self._get_zone_info()
        self.dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned)
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)

        # --- Core state ---
        self.turn = 0
        self.kills = 0
        self.running = True
        self.game_over = False
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

        # --- Mutation system ---
        self.mutation_log: list[dict] = []

        # --- Dev tools state (only active when DEV_MODE = True) ---
        self.dev_menu_cursor: int = 0           # selected option in dev menu
        self.dev_item_list: list[str] = []      # flat sorted list of item_ids for spawn picker
        self.dev_item_cursor: int = 0           # cursor position in spawn picker
        self.dev_item_scroll: int = 0           # scroll offset for spawn picker
        self.dev_floor_cursor: int = 0          # cursor position in floor teleport picker

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
            MenuState.ADJACENT_TILE_TARGETING: self._handle_adjacent_tile_targeting_input,
            MenuState.DEEP_FRYER: self._handle_deep_fryer_input,
            MenuState.GUN_TARGETING: self._handle_gun_targeting_input,
        }

    # ------------------------------------------------------------------
    # Zone helpers
    # ------------------------------------------------------------------

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
        self.event_bus.on("entity_died", self._on_kill_tox_spillover)
        self.event_bus.on("entity_died", self._on_kill_toxic_harvest)
        self.event_bus.on("entity_died", self._on_kill_acid_meltdown)
        self.event_bus.on("entity_died", self._on_kill_snipers_mark)

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
                    self.messages.append(f"You take {damage} radiation blast damage!")
                else:
                    self.messages.append(f"The {entity.name} takes {damage} radiation blast damage!")
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity, killer=self.player)

    def _on_entity_died(self, entity, killer=None):
        """Universal death handler — removes entity and bookkeeps kills."""
        self.dungeon.remove_entity(entity)
        if entity.entity_type == "monster":
            self.kills += 1
            # Trigger the floor alarm so alarm_chaser enemies (ugly strippers)
            # start pursuing the player from anywhere on the floor.
            if not self.dungeon.first_kill_happened:
                self.dungeon.first_kill_happened = True
                self.messages.append("The noise draws attention from elsewhere...")
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

        # --- Skills / Char sheet toggles (block other menus) ---
        if action_type == "toggle_skills":
            return self._action_toggle_skills(action)

        if self.menu_state == MenuState.SKILLS:
            unlocked_skills = self.skills.unlocked()
            if not unlocked_skills:
                if action_type in ("close_menu", "toggle_skills"):
                    self.menu_state = MenuState.NONE
                return False

            if not self.skills_spend_mode:
                if action_type == "move":
                    dy = action.get("dy", 0)
                    # Navigate through unlocked skills only
                    current_skill_name = SKILL_NAMES[self.skills_cursor] if self.skills_cursor < len(SKILL_NAMES) else unlocked_skills[0].name
                    unlocked_names = [s.name for s in unlocked_skills]
                    if current_skill_name in unlocked_names:
                        current_idx = unlocked_names.index(current_skill_name)
                    else:
                        current_idx = 0
                    new_idx = (current_idx + dy) % len(unlocked_names)
                    self.skills_cursor = SKILL_NAMES.index(unlocked_names[new_idx])
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
                    skill_name = SKILL_NAMES[self.skills_cursor]
                    gained = self.skills.spend_on_skill(skill_name, amount)
                    if gained:
                        skill = self.skills.get(skill_name)
                        new_level = skill.level
                        for lvl in range(new_level - gained + 1, new_level + 1):
                            self.messages.append(f"{skill_name} reached level {lvl}!")
                            self._apply_perk(skill_name, lvl)
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
                            self.messages.append(f"The acid burns you for {dmg} damage!")
                        if not entity.alive:
                            self.event_bus.emit("entity_died", entity=entity, killer=None)
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
        "max_skills",
        "add_skillpoints",
        "spawn_item",
        "kill_in_view",
        "toggle_invincible",
        "reveal_map",
        "add_cash",
        "full_heal",
        "teleport_stairs",
        "teleport_floor",
        "add_stats",
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
        if option == "max_skills":
            from skills import SKILL_NAMES, DEFAULT_EXP_CURVE, MAX_LEVEL
            for name in SKILL_NAMES:
                skill = self.skills.get(name)
                if not skill.is_maxed():
                    old_level = skill.level
                    skill.real_exp = 0
                    skill.potential_exp = 0
                    skill.level = MAX_LEVEL
                    # Apply all perks that were skipped
                    for lvl in range(old_level + 1, MAX_LEVEL + 1):
                        self._apply_perk(name, lvl)
            self.messages.append("[DEV] All skills set to level 10.")

        elif option == "add_skillpoints":
            self.skills.skill_points += 10000
            self.messages.append("[DEV] +10,000 skill points added.")

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

        self.menu_state = MenuState.NONE

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

    def _dev_teleport_to_floor(self, target_floor: int):
        """Teleport the player to a specific global floor index."""
        if target_floor == self.current_floor:
            self.messages.append("[DEV] Already on this floor.")
            return

        zone_key, zone_floor, display_name, zone_type = get_zone_for_floor(target_floor)

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        if target_floor not in self.dungeons:
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key)
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            new_dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned)
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

    def _apply_perk(self, skill_name: str, level: int) -> None:
        """Apply the perk for skill_name at the given level (1-10)."""
        from skills import get_perk
        perk = get_perk(skill_name, level)
        if not perk:
            return
        name = perk["name"]
        self.messages.append(f"  Perk unlocked: {name}")

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
            self.messages.append("  [Fire!] You can now spark a fire on an adjacent tile once per floor!")

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
            self.messages.append("  [Pickpocket] You can now strike adjacent enemies and snag $25 from them!")

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
            # Set cursor to first unlocked skill, or 0 if none unlocked
            unlocked = self.skills.unlocked()
            if unlocked:
                self.skills_cursor = SKILL_NAMES.index(unlocked[0].name)
            else:
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
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT, zone=zone_key)
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            new_dungeon.spawn_entities(self.player, floor_num=zone_floor, zone=zone_key, player_skills=self.skills, player_stats=self.player_stats, special_rooms_spawned=self.special_rooms_spawned)
            self.dungeons[next_floor] = new_dungeon
        else:
            new_dungeon = self.dungeons[next_floor]
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
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
        self.player.energy = ENERGY_THRESHOLD  # player acts first on new floor

        # Reset Sniping L2 "Dead Eye" swagger bonus
        if self.dead_eye_swagger_gained > 0:
            self.player_stats.swagger -= self.dead_eye_swagger_gained
            self.dead_eye_swagger_gained = 0

        # Reset per-floor ability charges
        for inst in self.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn:
                inst.reset_floor(defn)

        # Clear floor-only effects (Green Drank, Five Loco, Protein Powder)
        for eff in list(self.player.status_effects):
            if getattr(eff, 'id', '') in ('green_drank', 'five_loco', 'alco_seltzer_tox_resist', 'protein_powder', 'muffin_buff'):
                eff.expire(self.player, self)
                self.player.status_effects.remove(eff)

        # Handle hangover from previous floor's alcohol consumption
        from effects import apply_effect
        # Expire existing hangover first
        for eff in list(self.player.status_effects):
            if eff.id == "hangover":
                eff.expire(self.player, self)
                self.player.status_effects.remove(eff)

        # Apply pending hangover stacks
        if self.pending_hangover_stacks > 0:
            apply_effect(self.player, self, "hangover", stacks=self.pending_hangover_stacks)
            self.messages.append(f"Your hangover hits... (-{self.pending_hangover_stacks} all stats this floor)")
            self.pending_hangover_stacks = 0

        # Reset temporary spell damage
        self.player_stats.temporary_spell_damage = 0

        # Refill armor at floor start
        self.player.armor = self.player.max_armor

        # Abandoning L3: Anotha Motha — spawn 5 extra items on the new floor (zones only)
        if zone_type == "zone" and self.skills.get("Abandoning").level >= 3:
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

        # BFS on walkable explored tiles to find the nearest one adjacent to unexplored
        visited = set()
        visited.add((px, py))
        queue = _deque()
        queue.append((px, py, 0))
        best_target = None
        best_dist = float('inf')

        while queue:
            x, y, dist = queue.popleft()
            if dist > best_dist:
                break

            # Check if this explored floor tile borders any unexplored tile
            is_frontier = False
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= nx < w and 0 <= ny < h:
                    if not dungeon.explored[ny, nx]:
                        is_frontier = True
                        break

            if is_frontier:
                # Also check for items on unexplored tiles we'd like to path through
                if best_target is None or dist < best_dist:
                    best_target = (x, y)
                    best_dist = dist

            # Expand to walkable explored neighbors
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1),
                           (x-1, y-1), (x+1, y-1), (x-1, y+1), (x+1, y+1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                    if dungeon.tiles[ny][nx] == TILE_FLOOR and dungeon.explored[ny, nx]:
                        # Don't path through blocking entities (monsters, crates)
                        blocked_by_entity = any(
                            e.x == nx and e.y == ny and e.blocks_movement and getattr(e, "alive", True)
                            for e in dungeon.entities
                        )
                        if not blocked_by_entity:
                            visited.add((nx, ny))
                            queue.append((nx, ny, dist + 1))

        if best_target is None:
            # No frontier tiles found — try to find unexplored reachable tiles
            # (the above can miss if unexplored tiles are walls we can't know about yet)
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
        self._player_just_moved = True
        self.dungeon.move_entity(self.player, new_x, new_y)

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

        # Child Support debuff: drain $1 per step
        for effect in self.player.status_effects:
            if effect.id == "child_support":
                if self.cash > 0:
                    self.cash -= 1
                    self.messages.append("Child support payment auto-withdrawn. -$1")
                else:
                    self.messages.append("Child support due but you're broke!")
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

    def _gain_abandoning_xp(self) -> None:
        return xp_progression._gain_abandoning_xp(self)

    def _gain_melee_xp(self, skill_name: str, damage: int) -> None:
        return xp_progression._gain_melee_xp(self, skill_name, damage)

    def _gain_spell_xp(self, ability_id: str) -> None:
        return xp_progression._gain_spell_xp(self, ability_id)

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
