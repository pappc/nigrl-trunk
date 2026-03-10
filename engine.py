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
    ENERGY_THRESHOLD, PLAYER_BASE_SPEED, ZONE_BLACKK_MAGIC_MULT, ZONE_DAMAGE_MULT,
    DEV_MODE,
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
}

_INV_SUBCATEGORY_ORDER = {
    "weapon": 0,
    "ring": 1,
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
        self.total_floors = 4
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
        self.dungeon.spawn_entities(self.player, floor_num=0, zone="crack_den", player_skills=self.skills, special_rooms_spawned=self.special_rooms_spawned)
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

        # --- Equipment ---
        self.equipment: dict[str, Entity | None] = {
            slot: None for slot in EQUIPMENT_SLOTS
        }
        self.rings: list[Entity | None] = [None] * RING_SLOTS
        self.neck: Entity | None = None  # neck slot (only one)
        self.feet: Entity | None = None  # feet slot (only one)
        self.equipment_cursor: int = 0  # indexes into flat occupied-slot list (weapon → neck → feet → rings)

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

        # --- Ability system ---
        # Players start with no abilities; abilities are granted by items and skills.
        self.player_abilities: list[AbilityInstance] = []
        self.selected_ability_index: int | None = None
        self.abilities_cursor: int = 0
        self.ability_cooldowns: dict[str, int] = {}  # ability_id -> turns remaining
        self.crit_multiplier: int = 2  # base crit damage multiplier (Crit+ perk increases this)
        self.move_cost_reduction: int = 0  # energy refunded per actual move step (Air Jordans perk)
        self._player_just_moved: bool = False  # True when the last handle_move did real movement

        # --- Dev tools state (only active when DEV_MODE = True) ---
        self.dev_menu_cursor: int = 0           # selected option in dev menu
        self.dev_item_list: list[str] = []      # flat sorted list of item_ids for spawn picker
        self.dev_item_cursor: int = 0           # cursor position in spawn picker
        self.dev_item_scroll: int = 0           # scroll offset for spawn picker

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
            "open_dev_menu": self._action_open_dev_menu,
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
            MenuState.ADJACENT_TILE_TARGETING: self._handle_adjacent_tile_targeting_input,
        }

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def _register_events(self):
        self.event_bus.on("entity_died", self._on_entity_died)
        self.event_bus.on("entity_died", self._on_kill_cash_drop)
        self.event_bus.on("entity_died", self._on_kill_loot_drop)

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
        strain = pick_strain(self.dungeon.zone) if item_id in strain_items else None
        kwargs = create_item_entity(item_id, entity.x, entity.y, strain=strain)
        self.dungeon.add_entity(Entity(**kwargs))
        item_name = kwargs.get("name", item_id)
        strain_suffix = f" ({strain})" if strain else ""
        self.messages.append(f"The {entity.name} dropped {item_name}{strain_suffix}.")

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
                else:
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
                # Hard minimum: entities always gain at least 10 energy/tick
                gain = max(gain, 10.0)
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

            # Tick ability cooldowns
            for key in list(self.ability_cooldowns):
                self.ability_cooldowns[key] -= 1
                if self.ability_cooldowns[key] <= 0:
                    del self.ability_cooldowns[key]

            # 4. Fire hazard: ignite any entity standing on a fire tile
            for entity in [self.player] + monsters:
                if not entity.alive:
                    continue
                for hazard in self.dungeon.get_entities_at(entity.x, entity.y):
                    if getattr(hazard, "hazard_type", None) == "fire":
                        effects.apply_effect(entity, self, "ignite", silent=True)
                        break

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
                ps._base[stat] = getattr(ps, stat)
                if stat == "constitution":
                    self.player.max_hp += 10 * amount
                    self.player.heal(10 * amount)
                label = stat.replace("_", " ").title()
                stat_msgs.append(f"+{amount} {label}")
            self.messages.append(f"  [{name}] {', '.join(stat_msgs)}")

        if name == "Spectral Paper":
            self._add_item_to_inventory("spectral_paper")
            self.messages.append("  [Spectral Paper] A ghostly rolling paper materializes in your inventory!")

        if name == "Bitch Slap":
            self.grant_ability("black_eye_slap")
            self.messages.append("  [Bitch Slap] You learn to slap enemies senseless!")

        if name == "Black Eye":
            self.messages.append("  [Black Eye] Unarmed attacks now have a 10% chance to stun enemies!")

        if name == "Bash":
            self.grant_ability("bash")
            self.messages.append("  [Bash] You learn to send enemies flying with your blunt weapon!")

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

        if name == "Fry Shot":
            self.grant_ability("fry_shot")
            self.messages.append("  [Fry Shot] You can now hurl hot grease at enemies within 4 tiles!")

        if name == "Slow Metabolism":
            self.grant_ability("slow_metabolism")
            self.messages.append("  [Slow Metabolism] You can now double the duration of your active drink buffs (2/floor)!")

        if name == "Pickpocket":
            self.grant_ability("pickpocket")
            self.messages.append("  [Pickpocket] You can now strike adjacent enemies and snag $25 from them!")

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

        # Award abandoning XP for items/cash left on this floor
        self._gain_abandoning_xp()

        # Remove player from current floor
        self.dungeon.remove_entity(self.player)

        if next_floor not in self.dungeons:
            # Generate a fresh floor
            new_dungeon = Dungeon(DUNGEON_WIDTH, DUNGEON_HEIGHT)
            self.dungeons[next_floor] = new_dungeon
            if new_dungeon.rooms:
                x, y = new_dungeon.rooms[0].center()
                self.player.x = x
                self.player.y = y
            new_dungeon.spawn_entities(self.player, floor_num=next_floor, zone="crack_den", player_skills=self.skills, special_rooms_spawned=self.special_rooms_spawned)
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

        # Reset per-floor ability charges
        for inst in self.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn:
                inst.reset_floor(defn)

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

        # Abandoning L3: Anotha Motha — spawn 5 extra items on the new floor
        if self.skills.get("Abandoning").level >= 3:
            from loot import generate_floor_loot
            extra = generate_floor_loot("crack_den", next_floor, self.skills)[:5]
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

        self.messages.append(
            f"You descend deeper into the crack den... (Floor {self.current_floor + 1}/{self.total_floors})"
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
        """Stop auto-travel, optionally logging a reason."""
        if not self.auto_traveling:
            return
        self.auto_traveling = False
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
            if target and target.entity_type == "monster":
                self.handle_attack(self.player, target)
                return True
            elif target and getattr(target, "hazard_type", None) == "crate":
                self._smash_crate(target)
                return True
            elif target and getattr(target, "hazard_type", None) == "door":
                self._try_unlock_door(target)
                return True
            return False  # pure wall — no turn consumed

        # Failsafe: explicitly check that no living monster occupies the destination
        # This prevents any edge cases where blocks_movement might be incorrectly set
        for entity in self.dungeon.get_entities_at(new_x, new_y):
            if entity.entity_type == "monster" and getattr(entity, "alive", True):
                self.handle_attack(self.player, entity)
                return True

        # Move player through spatial index
        self._player_just_moved = True
        self.dungeon.move_entity(self.player, new_x, new_y)

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

        item_id, strain = pick_random_consumable("crack_den")
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
    # Combat
    # ------------------------------------------------------------------

    def _compute_str_bonus(self, weapon_item):
        """Return the stat damage bonus for the given weapon (or unarmed)."""
        strength = self.player_stats.effective_strength
        if weapon_item is None:
            return strength - UNARMED_STR_BASE
        defn = get_item_def(weapon_item.item_id)
        # STR-based scaling
        scaling = defn.get("str_scaling")
        if scaling:
            if scaling["type"] == "tiered":
                req = defn.get("str_req", 1)
                divisor = scaling.get("divisor", 2)
                return max(0, (strength - req) // divisor)
            if scaling["type"] == "linear":
                base = scaling.get("base", UNARMED_STR_BASE)
                return max(0, strength - base)
            if scaling["type"] == "diminishing_tiered":
                req = defn.get("str_req", 1)
                excess = max(0, strength - req)
                bonus = 0
                divisor = 1
                tier_size = 2
                remaining = excess
                while remaining > 0:
                    if divisor >= 8:
                        bonus += remaining // 8
                        break
                    chunk = min(remaining, tier_size)
                    bonus += chunk // divisor
                    remaining -= chunk
                    divisor += 1
                    tier_size += 2
                return bonus
            if scaling["type"] == "ratio":
                req = defn.get("str_req", 1)
                numer = scaling.get("numerator", 1)
                denom = scaling.get("denominator", 1)
                return max(0, (strength - req) * numer // denom)
        # Arbitrary stat scaling (threshold or swagger_linear)
        stat_scaling = defn.get("stat_scaling")
        if stat_scaling:
            if stat_scaling["type"] == "threshold":
                stat_name = stat_scaling["stat"]
                threshold = stat_scaling["threshold"]
                stat_value = getattr(self.player_stats, f"effective_{stat_name}", 0)
                return max(0, stat_value - threshold)
            if stat_scaling["type"] == "swagger_linear":
                divisor = stat_scaling.get("divisor", 2)
                swagger = getattr(self.player_stats, "effective_swagger", 0)
                return swagger // divisor
        return 0

    def _compute_player_attack_power(self):
        """Compute the player's total attack power including equipment and STR."""
        weapon = self.equipment["weapon"]
        weapon_defn = get_item_def(weapon.item_id) if weapon else None

        if weapon and weapon_defn.get("base_damage") is not None:
            atk_power = weapon_defn["base_damage"]
        else:
            atk_power = self.player.power

        # Ring power bonuses
        for ring in self.rings:
            if ring is not None:
                defn = get_item_def(ring.item_id)
                if defn:
                    atk_power += defn.get("power_bonus", 0)

        # Neck power bonus
        if self.neck is not None:
            defn = get_item_def(self.neck.item_id)
            if defn:
                atk_power += defn.get("power_bonus", 0)

        # Feet power bonus
        if self.feet is not None:
            defn = get_item_def(self.feet.item_id)
            if defn:
                atk_power += defn.get("power_bonus", 0)

        atk_power += self._compute_str_bonus(weapon)
        return atk_power

    def _compute_player_defense(self):
        """Compute the player's total melee defence including equipment and swagger."""
        defense = self.player.defense
        weapon = self.equipment["weapon"]
        if weapon is not None:
            defn = get_item_def(weapon.item_id)
            if defn:
                defense += defn.get("defense_bonus", 0)
        for ring in self.rings:
            if ring is not None:
                defn = get_item_def(ring.item_id)
                if defn:
                    defense += defn.get("defense_bonus", 0)
        if self.neck is not None:
            defn = get_item_def(self.neck.item_id)
            if defn:
                defense += defn.get("defense_bonus", 0)
        if self.feet is not None:
            defn = get_item_def(self.feet.item_id)
            if defn:
                defense += defn.get("defense_bonus", 0)
        defense += self.player_stats.swagger_defence
        return defense

    def _compute_player_max_armor(self):
        """Compute the player's total max armor including equipment bonuses."""
        max_armor = 0
        weapon = self.equipment["weapon"]
        if weapon is not None:
            defn = get_item_def(weapon.item_id)
            if defn:
                max_armor += defn.get("armor_bonus", 0)
        for ring in self.rings:
            if ring is not None:
                defn = get_item_def(ring.item_id)
                if defn:
                    max_armor += defn.get("armor_bonus", 0)
        if self.neck is not None:
            defn = get_item_def(self.neck.item_id)
            if defn:
                max_armor += defn.get("armor_bonus", 0)
        if self.feet is not None:
            defn = get_item_def(self.feet.item_id)
            if defn:
                max_armor += defn.get("armor_bonus", 0)
        # Add permanent and temporary armor bonuses
        max_armor += getattr(self.player_stats, 'permanent_armor_bonus', 0)
        max_armor += getattr(self.player_stats, 'temporary_armor_bonus', 0)
        return max_armor

    def _apply_damage_modifiers(self, damage: int, defender) -> int:
        """Apply modify_incoming_damage hooks from defender's status effects."""
        for eff in defender.status_effects:
            damage = eff.modify_incoming_damage(damage, defender)
        return damage

    def _apply_toxicity(self, damage: int, defender) -> int:
        """Apply toxicity 'more' multiplier to incoming damage (multiplicative after all other mods)."""
        tox = getattr(defender, 'toxicity', 0)
        if tox <= 0:
            return damage
        if defender is self.player:
            mult = _player_toxicity_multiplier(tox)
        else:
            mult = _monster_toxicity_multiplier(tox)
        return max(1, int(damage * mult))

    def _player_meets_weapon_req(self) -> bool:
        """Return True if the player meets all stat requirements for their equipped weapon.

        Checks both the legacy `str_req` shorthand and the general `stat_reqs` dict
        (e.g. {"street_smarts": 7, "strength": 5}) against effective stat values.
        """
        weapon = self.equipment.get("weapon")
        if weapon is None:
            return True
        defn = get_item_def(weapon.item_id)
        if defn is None:
            return True

        # Legacy shorthand: str_req
        reqs = dict(defn.get("stat_reqs", {}))
        if "str_req" in defn:
            reqs.setdefault("strength", defn["str_req"])

        for stat, required in reqs.items():
            effective = getattr(self.player_stats, f"effective_{stat}", None)
            if effective is None:
                continue
            if effective < required:
                return False
        return True

    def handle_attack(self, attacker, defender, _windfury_eligible=True):
        """Handle melee attack with equipment bonuses and player stat effects."""
        # Agent Orange: attacker cannot deal melee damage
        if any(getattr(e, 'id', None) == 'agent_orange' for e in attacker.status_effects):
            if attacker == self.player:
                self.messages.append("Agent Orange — you can't deal melee damage!")
            return

        # Weapon stat requirement check: if player doesn't meet requirements, deal no damage
        if attacker == self.player and not self._player_meets_weapon_req():
            weapon = self.equipment.get("weapon")
            defn = get_item_def(weapon.item_id)
            wname = defn.get("name", weapon.name)
            reqs = dict(defn.get("stat_reqs", {}))
            if "str_req" in defn:
                reqs.setdefault("strength", defn["str_req"])
            unmet = [
                stat for stat, req in reqs.items()
                if getattr(self.player_stats, f"effective_{stat}", req) < req
            ]
            req_strs = ", ".join(
                f"{stat.replace('_', ' ').title()} {reqs[stat]}" for stat in unmet
            )
            self.messages.append([
                ("Your stats are too low to wield ", (200, 100, 100)),
                (wname, weapon.color),
                (f" (need {req_strs})!", (200, 100, 100)),
            ])
            return

        is_crit = False

        if attacker == self.player:
            atk_power = self._compute_player_attack_power()
            if random.random() < self.player_stats.crit_chance:
                is_crit = True
        else:
            atk_power = attacker.power

        if defender == self.player:
            def_defense = self._compute_player_defense()
        else:
            def_defense = defender.defense

        # Check dodge before applying damage
        defender_dodge_chance = self.player_stats.dodge_chance if defender == self.player else defender.dodge_chance
        if random.random() * 100 < defender_dodge_chance:
            msg = f"{defender.name} dodges the attack!"
            self.messages.append(msg)
            return

        damage = max(MIN_DAMAGE, atk_power - def_defense)
        if is_crit:
            damage *= self.crit_multiplier
        damage = self._apply_damage_modifiers(damage, defender)
        damage = self._apply_toxicity(damage, defender)
        defender.take_damage(damage)

        # On-hit effects: notify player's active buffs/debuffs
        if attacker == self.player:
            for eff in list(self.player.status_effects):
                eff.on_player_melee_hit(self, defender, damage)

        # Weapon on-hit effects (e.g. Glass Shards, Meth-Head XP)
        if attacker == self.player:
            weapon = self.equipment.get("weapon")
            if weapon:
                wdefn = get_item_def(weapon.item_id)
                if wdefn:
                    # Vampiric (e.g. Bone Club): heal 30% of damage dealt after defense
                    vampiric = wdefn.get("vampiric", 0)
                    if vampiric and damage > 0:
                        heal_amt = max(1, int(damage * vampiric))
                        self.player.heal(heal_amt)

                    on_hit = wdefn.get("on_hit_effect")
                    if on_hit:
                        effects.apply_effect(
                            defender, self, on_hit["type"],
                            stacks=on_hit.get("stacks", 1),
                            duration=on_hit.get("duration", 5),
                            silent=True,
                        )
                    skill_xp = wdefn.get("on_hit_skill_xp")
                    if skill_xp:
                        # Check if skill is newly unlocked (no XP before this call)
                        skill = self.skills.get(skill_xp["skill"])
                        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

                        xp_amount = round(skill_xp["amount"] * self.player_stats.xp_multiplier)
                        self.skills.gain_potential_exp(
                            skill_xp["skill"], xp_amount,
                            self.player_stats.effective_book_smarts
                        )
                        # Add unlock notification if this is the first XP
                        if was_locked:
                            self.messages.append([
                                (f"[NEW SKILL UNLOCKED] {skill_xp['skill']}!", (255, 215, 0)),
                            ])
                    # Stun on-hit chance (e.g. Blackjack)
                    stun_chance = wdefn.get("on_hit_stun_chance", 0)
                    if stun_chance and random.random() < stun_chance:
                        stun_dur = wdefn.get("stun_duration", 3)
                        effects.apply_effect(defender, self, "stun", duration=stun_dur, silent=True)
                        self.messages.append(f"{defender.name} is stunned!")

                    # Disarm on-hit chance (e.g. Monkey Wrench)
                    disarm_chance = wdefn.get("on_hit_disarm_chance", 0)
                    if disarm_chance and random.random() < disarm_chance:
                        disarm_dur = wdefn.get("disarm_duration", 3)
                        effects.apply_effect(defender, self, "disarmed", duration=disarm_dur, silent=True)
                        self.messages.append(f"{defender.name} is disarmed!")

                    # Sunder: permanently reduce defender defense by 1 (e.g. Masonry Hammer)
                    sunder = wdefn.get("on_hit_sunder", 0)
                    if sunder and defender.alive:
                        defender.defense -= sunder

                    # Bounce chain (e.g. Extension Cord): arc to nearest adjacent enemy
                    bounce = wdefn.get("on_hit_bounce")
                    if bounce and defender.alive and random.random() < bounce["chance"]:
                        bounce_target = min(
                            (
                                m for m in self.dungeon.get_monsters()
                                if m.alive and m is not defender
                                and max(abs(m.x - defender.x), abs(m.y - defender.y)) <= 1
                            ),
                            key=lambda m: max(abs(m.x - defender.x), abs(m.y - defender.y)),
                            default=None,
                        )
                        if bounce_target:
                            bounce_dmg = max(1, int(damage * bounce["damage_pct"]))
                            bounce_target.take_damage(bounce_dmg)
                            self.messages.append(
                                f"The cord arcs to {bounce_target.name}! ({bounce_dmg} dmg)"
                            )
                            if not bounce_target.alive:
                                self.event_bus.emit("entity_died", entity=bounce_target, killer=self.player)

                    # Weapon break chance (e.g. Crooked Baseball Bat)
                    break_chance = wdefn.get("break_chance", 0)
                    if break_chance and random.random() < break_chance:
                        self.messages.append(f"Your {weapon.name} breaks!")
                        self.equipment["weapon"] = None
                        # Revoke any ability the weapon granted
                        granted = wdefn.get("grants_ability")
                        if granted:
                            self.revoke_ability(granted)

            # Melee skill XP: equal to damage dealt
            _WEAPON_TYPE_SKILL = {"stabbing": "Stabbing", "blunt": "Beating"}
            if weapon and wdefn:
                melee_skill = _WEAPON_TYPE_SKILL.get(wdefn.get("weapon_type"))
            else:
                melee_skill = "Smacking"
            if melee_skill:
                self._gain_melee_xp(melee_skill, damage)

            # Smacking L3 passive: 10% chance to black eye on unarmed hits
            if (not weapon and attacker == self.player and defender.alive
                    and self.skills.get("Smacking").level >= 3
                    and random.random() < 0.10):
                effects.apply_effect(defender, self, "black_eye", duration=2, silent=True)
                self.messages.append(f"Black Eye! {defender.name} gets stunned for 2 turns then staggers!")

        # Acid Armor counterattack: when monster is hit, chance to break player's equipment
        if attacker == self.player and defender != self.player:
            acid_armor_effect = next(
                (e for e in defender.status_effects if getattr(e, 'id', '') == 'acid_armor'),
                None
            )
            if acid_armor_effect and random.random() < acid_armor_effect.break_chance:
                self._acid_armor_break_equipment()

        # Passive monsters become provoked when hit
        if hasattr(defender, "provoked") and not defender.provoked:
            defender.provoked = True
            if getattr(defender, 'name', '') == "Big Nigga Jerome":
                self.messages.append([
                    ("Jerome: ", (220, 80, 50)),
                    ("don't fuck with me nigga", (255, 50, 50)),
                ])

        crit_str = " CRITICAL!" if is_crit else ""
        msg = f"{attacker.name} deals {damage} damage to {defender.name}{crit_str}"

        if not defender.alive:
            msg += f" ({defender.name} dies)"
            self.messages.append(msg)
            self.event_bus.emit("entity_died", entity=defender, killer=attacker)
        else:
            self.messages.append(msg)

        # Gouge break: player damage removes gouge stun from the defender
        if attacker == self.player and defender.alive:
            gouge_eff = next(
                (e for e in defender.status_effects if getattr(e, 'id', '') == 'gouge'),
                None,
            )
            if gouge_eff:
                defender.status_effects.remove(gouge_eff)
                self.messages.append(f"{defender.name}'s gouge stun is broken!")

        # Windfury: extra attack with stabbing weapon (Stabbing level 3+)
        if (attacker == self.player and _windfury_eligible
                and defender.alive
                and self.skills.get("Stabbing").level >= 3):
            weapon = self.equipment.get("weapon")
            if weapon:
                wdefn = get_item_def(weapon.item_id)
                if wdefn and wdefn.get("weapon_type") == "stabbing":
                    stsmt = self.player_stats.effective_street_smarts
                    chance = min(30, stsmt) / 100.0
                    if random.random() < chance:
                        self.messages.append("Windfury! Your blade strikes again!")
                        self.handle_attack(attacker, defender, _windfury_eligible=False)

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
        """Resolve a monster attacking the player."""
        # Agent Orange: monster cannot deal melee damage
        if any(getattr(e, 'id', None) == 'agent_orange' for e in monster.status_effects):
            return

        player = self.player
        def_defense = self._compute_player_defense()

        # Special attack check
        for sa in monster.special_attacks:
            if random.random() < sa["chance"]:
                # Mark monster as having attacked (for hit-and-run AI)
                monster.has_attacked_player = True

                # Handle Pickpocket (cash stealing) attacks
                if sa.get("name") == "Pickpocket":
                    # Steal 1-30 cash (heavily skewed to lower values)
                    # Roll 2d10 (lower values more common) with cap at 30
                    stolen = min(random.randint(1, 10) + random.randint(1, 10), 30)
                    stolen = min(stolen, self.cash)  # Can't steal more than player has
                    self.cash -= stolen
                    self.messages.append(
                        f"{monster.name} pickpockets you for ${stolen}!"
                    )
                    return

                mult = sa.get("damage_mult", 1.0)
                # Jerome's damage penetrates defense
                # (Well Fed bonus is already baked into monster.power via WellFedEffect.apply)
                if monster.enemy_type == "big_nigga_jerome":
                    damage = int(monster.power * mult)
                else:
                    damage = max(MIN_DAMAGE, int(monster.power * mult) - def_defense)
                # Monster crit check (special attack)
                is_monster_crit = random.random() * 100 < monster.crit_chance
                if is_monster_crit:
                    damage *= 2
                damage = self._apply_damage_modifiers(damage, player)
                damage = self._apply_toxicity(damage, player)
                if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
                    damage = max(MIN_DAMAGE, damage // 2)
                if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
                    damage = max(MIN_DAMAGE, damage // 2)
                player.take_damage(damage)
                crit_str = " CRITICAL!" if is_monster_crit else ""
                self.messages.append(
                    f"{monster.name} hits you with {sa['name']} for {damage} damage!{crit_str}"
                )
                if any(getattr(e, 'id', None) == 'soul_pair' for e in monster.status_effects):
                    monster.take_damage(damage)
                    self.messages.append(
                        f"Soul-Pair: {monster.name} shares your pain! (-{damage} HP)"
                    )
                    if not monster.alive:
                        self.event_bus.emit("entity_died", entity=monster, killer=player)

                # Handle Knockback Punch
                if sa.get("name") == "Knockback Punch":
                    dx = 0 if monster.x == player.x else (1 if player.x > monster.x else -1)
                    dy = 0 if monster.y == player.y else (1 if player.y > monster.y else -1)
                    nx, ny = player.x + dx, player.y + dy
                    if self.dungeon.is_terrain_blocked(nx, ny):
                        self.messages.append("You brace yourself against the knockback!")
                    else:
                        player.x, player.y = nx, ny
                        self.messages.append("You're knocked back 1 tile!")
                    effects.apply_effect(player, self, "stun", duration=2, silent=True)
                    self.messages.append("You're stunned!")

                hit_eff = sa.get("on_hit_effect")
                if hit_eff:
                    self._apply_monster_hit_effect(hit_eff, monster=monster)
                if not player.alive:
                    self.event_bus.emit("entity_died", entity=player, killer=monster)
                return

        # Normal attack
        monster.has_attacked_player = True
        # Niglet and Jerome damage ignores defense
        # (Jerome's Well Fed bonus is already baked into monster.power via WellFedEffect.apply)
        if monster.enemy_type in ("niglet", "big_nigga_jerome"):
            damage = monster.power
        else:
            damage = max(MIN_DAMAGE, monster.power - def_defense)
        # Monster crit check (normal attack)
        is_monster_crit = random.random() * 100 < monster.crit_chance
        if is_monster_crit:
            damage *= 2
        damage = self._apply_damage_modifiers(damage, player)
        damage = self._apply_toxicity(damage, player)
        if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
            damage = max(MIN_DAMAGE, damage // 2)
        if any(getattr(e, 'id', None) == 'disarmed' for e in monster.status_effects):
            damage = max(MIN_DAMAGE, damage // 2)
        player.take_damage(damage)
        crit_str = " CRITICAL!" if is_monster_crit else ""
        self.messages.append(f"{monster.name} hits you for {damage} damage!{crit_str}")
        if any(getattr(e, 'id', None) == 'soul_pair' for e in monster.status_effects):
            monster.take_damage(damage)
            self.messages.append(
                f"Soul-Pair: {monster.name} shares your pain! (-{damage} HP)"
            )
            if not monster.alive:
                self.event_bus.emit("entity_died", entity=monster, killer=player)

        for hit_eff in monster.on_hit_effects:
            if random.random() < hit_eff["chance"]:
                self._apply_monster_hit_effect(hit_eff, monster=monster)

        if not player.alive:
            self.event_bus.emit("entity_died", entity=player, killer=monster)

    def _apply_monster_hit_effect(self, effect, monster=None):
        """Apply a status debuff from a monster hit to the player."""
        effect_id = effect["kind"]
        # Map specific named effects to their custom effect IDs
        if effect.get("name") == "Bleeding":
            effect_id = "bleeding"
        duration = effect["duration"]
        amount = effect.get("amount", 0)
        kwargs = dict(duration=duration, amount=amount)
        # Fear needs the source position so the player flees away from it
        if effect_id == "fear" and monster is not None:
            kwargs["source_x"] = monster.x
            kwargs["source_y"] = monster.y
        effects.apply_effect(self.player, self, effect_id, **kwargs)

    # ------------------------------------------------------------------
    # Item menu
    # ------------------------------------------------------------------

    def _open_item_menu(self, index):
        item = self.player.inventory[index]
        self.selected_item_index = index
        self.selected_item_actions = get_actions(item.item_id)
        # Auto-position cursor on the use_verb if available
        defn = get_item_def(item.item_id)
        use_verb = defn.get("use_verb") if defn else None
        if use_verb and use_verb in self.selected_item_actions:
            self.item_menu_cursor = self.selected_item_actions.index(use_verb)
        else:
            self.item_menu_cursor = 0
        self.menu_state = MenuState.ITEM_MENU

    def _handle_item_menu_input(self, action):
        action_type = action.get("type")
        actions = self.selected_item_actions
        item = self.player.inventory[self.selected_item_index]
        defn = get_item_def(item.item_id)

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        # Up/Down — scroll through valid inventory items (those with a use_verb)
        if action_type == "move":
            dy = action.get("dy", 0)
            if dy != 0:
                valid_indices = [
                    i for i, it in enumerate(self.player.inventory)
                    if it.item_id and get_item_def(it.item_id) and get_item_def(it.item_id).get("use_verb")
                ]
                if len(valid_indices) > 1 and self.selected_item_index in valid_indices:
                    cur_pos = valid_indices.index(self.selected_item_index)
                    new_idx = valid_indices[(cur_pos + dy) % len(valid_indices)]
                    self._open_item_menu(new_idx)
                    # Position cursor on the use_verb row
                    new_verb = get_item_def(self.player.inventory[new_idx].item_id).get("use_verb")
                    if new_verb in self.selected_item_actions:
                        self.item_menu_cursor = self.selected_item_actions.index(new_verb)
            return False

        # Enter — execute action at cursor
        if action_type == "confirm_target":
            return self._execute_item_action(actions[self.item_menu_cursor])

        # Number keys — still work as direct selection
        if action_type == "select_action":
            idx = action["index"]
            if 0 <= idx < len(actions):
                return self._execute_item_action(actions[idx])
            return False

        # Spacebar — execute the use verb / "Use on..." / Equip (first actionable verb)
        if action_type == "item_use":
            use_verb = defn.get("use_verb")
            throw_verb = defn.get("throw_verb")
            for act in actions:
                if act == use_verb or act == throw_verb or act == "Use on..." or act == "Equip":
                    return self._execute_item_action(act)
            return False

        # E — examine
        if action_type == "open_equipment":
            if "Examine" in actions:
                return self._execute_item_action("Examine")
            return False

        # D — drop
        if action_type == "drop_item":
            if "Drop" in actions:
                return self._execute_item_action("Drop")
            return False

        # Shift+D — destroy
        if action_type == "destroy_item":
            if "Destroy" in actions:
                return self._execute_item_action("Destroy")
            return False

        return False

    def _execute_item_action(self, action_name):
        item = self.player.inventory[self.selected_item_index]
        defn = get_item_def(item.item_id)

        if action_name == "Equip":
            success = self._equip_item(self.selected_item_index)
            if success:
                self.menu_state = MenuState.NONE
                self.selected_item_index = None
            return success

        elif action_name == "Drop":
            self._drop_item(self.selected_item_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        elif action_name == "Use on...":
            self.menu_state = MenuState.COMBINE_SELECT
            self._init_combine_cursor()
            return False

        elif action_name == defn.get("use_verb"):
            self._use_item(self.selected_item_index)
            if self.menu_state not in (MenuState.TARGETING, MenuState.COMBINE_SELECT):
                self.selected_item_index = None
                self.menu_state = MenuState.NONE
            return True

        elif action_name == defn.get("throw_verb"):
            self._enter_targeting(self.selected_item_index)
            return False

        elif action_name == "Examine":
            self.menu_state = MenuState.EXAMINE
            return False

        elif action_name == "Destroy":
            self.menu_state = MenuState.DESTROY_CONFIRM
            self.destroy_confirm_cursor = 0  # default to No
            return False

        return False

    # ------------------------------------------------------------------
    # Equipment
    # ------------------------------------------------------------------

    def _equip_item(self, index) -> bool:
        item = self.player.inventory[index]
        defn = get_item_def(item.item_id)
        slot = defn["equip_slot"]
        if slot is None:
            return False

        str_req = defn.get("str_req")
        if str_req is not None and self.player_stats.effective_strength < str_req:
            self.messages.append(
                f"Need {str_req} STR to equip {item.name}! "
                f"(you have {self.player_stats.effective_strength})"
            )
            return False

        if slot == "weapon":
            new_weapon = self.player.inventory[index]
            old_weapon = self.equipment["weapon"]
            if old_weapon is not None:
                self.player.inventory.append(old_weapon)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (old_weapon.name, old_weapon.color)])
            self.player.inventory.remove(new_weapon)
            self.equipment["weapon"] = new_weapon

            # Revoke any ability granted by the old weapon
            if old_weapon:
                old_defn = get_item_def(old_weapon.item_id)
                revoked = old_defn.get("grants_ability") if old_defn else None
                if revoked:
                    self.revoke_ability(revoked)

            # Grant any ability given by the new weapon
            new_defn = get_item_def(self.equipment["weapon"].item_id)
            granted = new_defn.get("grants_ability") if new_defn else None
            if granted:
                self.grant_ability(granted)
        elif slot == "neck":
            new_neck = self.player.inventory[index]
            if self.neck is not None:
                swapped = self.neck
                self.player.inventory.append(swapped)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
            self.player.inventory.remove(new_neck)
            self.neck = new_neck
        elif slot == "feet":
            new_feet = self.player.inventory[index]
            if self.feet is not None:
                swapped = self.feet
                self.player.inventory.append(swapped)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
            self.player.inventory.remove(new_feet)
            self.feet = new_feet
        elif slot == "ring":
            empty = next((i for i, r in enumerate(self.rings) if r is None), None)
            if empty is None:
                # All ring slots are full; open menu to select which ring to replace
                self.pending_ring_item_index = index
                self.ring_replace_cursor = 0
                self.menu_state = MenuState.RING_REPLACE
                return False
            self.rings[empty] = self.player.inventory.pop(index)
        else:
            return False

        self._refresh_ring_stat_bonuses()
        self.messages.append([("Equipped ", _C_MSG_NEUTRAL), (item.name, item.color)])
        return True

    def _handle_equipment_input(self, action):
        action_type = action.get("type")

        if action_type in ("close_menu", "open_equipment"):
            self.menu_state = MenuState.NONE
            return False

        # Build flat ordered list of occupied slots: (slot_id, item)
        # slot_id is "weapon", "neck", "feet", or ("ring", index)
        def _occupied_slots():
            slots = []
            if self.equipment["weapon"] is not None:
                slots.append(("weapon", self.equipment["weapon"]))
            if self.neck is not None:
                slots.append(("neck", self.neck))
            if self.feet is not None:
                slots.append(("feet", self.feet))
            for i, r in enumerate(self.rings):
                if r is not None:
                    slots.append((("ring", i), r))
            return slots

        # Cursor navigation (up/down arrows — intercepted here, not passed to move)
        if action_type == "move":
            dy = action.get("dy", 0)
            n = max(0, len(_occupied_slots()) - 1)
            self.equipment_cursor = max(0, min(n, self.equipment_cursor + dy))
            return False

        # Enter = unequip item at cursor
        if action_type == "confirm_target":
            occupied = _occupied_slots()
            did_unequip = False
            if self.equipment_cursor < len(occupied):
                slot_id, item = occupied[self.equipment_cursor]
                if slot_id == "weapon":
                    self.equipment["weapon"] = None
                    old_defn = get_item_def(item.item_id)
                    revoked = old_defn.get("grants_ability") if old_defn else None
                    if revoked:
                        self.revoke_ability(revoked)
                elif slot_id == "neck":
                    self.neck = None
                elif slot_id == "feet":
                    self.feet = None
                else:
                    _, ring_idx = slot_id
                    self.rings[ring_idx] = None
                self.player.inventory.append(item)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (item.name, item.color)])
                # Clamp cursor to new list length
                n_remaining = max(0, len(occupied) - 2)
                self.equipment_cursor = min(self.equipment_cursor, n_remaining)
                did_unequip = True
            self._refresh_ring_stat_bonuses()
            return did_unequip

        return False

    # ------------------------------------------------------------------
    # Ring stat bonuses
    # ------------------------------------------------------------------

    def _refresh_ring_stat_bonuses(self):
        """Recompute ring/neck stat bonuses from all equipped rings and neck item and apply to player_stats.
        Also syncs player.max_hp (clamping hp to new max if it dropped) and max_armor."""
        totals: dict[str, int] = {}
        for ring in self.rings:
            if ring is None:
                continue
            defn = get_item_def(ring.item_id)
            if defn:
                for stat, amount in defn.get("stat_bonus", {}).items():
                    totals[stat] = totals.get(stat, 0) + amount
        if self.neck is not None:
            defn = get_item_def(self.neck.item_id)
            if defn:
                for stat, amount in defn.get("stat_bonus", {}).items():
                    totals[stat] = totals.get(stat, 0) + amount
        if self.feet is not None:
            defn = get_item_def(self.feet.item_id)
            if defn:
                for stat, amount in defn.get("stat_bonus", {}).items():
                    totals[stat] = totals.get(stat, 0) + amount
        self.player_stats.set_ring_bonuses(totals)
        new_max = self.player_stats.max_hp
        self.player.max_hp = new_max
        if self.player.hp > new_max:
            self.player.hp = new_max

        # Update max_armor (clamp current armor to new max if needed)
        new_max_armor = self._compute_player_max_armor()
        self.player.max_armor = new_max_armor
        if self.player.armor > new_max_armor:
            self.player.armor = new_max_armor

    def _sync_player_max_hp(self):
        """Sync entity max_hp from player_stats.max_hp after constitution changes.
        Clamps current HP to the new max if it dropped."""
        new_max = self.player_stats.max_hp
        self.player.max_hp = new_max
        if self.player.hp > new_max:
            self.player.hp = new_max

    # ------------------------------------------------------------------
    # Inventory sort
    # ------------------------------------------------------------------

    def _sort_inventory(self):
        """Sort player inventory: tools → equipment (by subcategory) → materials → consumables."""
        def _key(item):
            defn = get_item_def(item.item_id)
            if defn:
                cat    = defn.get("category", "")
                subcat = defn.get("subcategory") or ""
            else:
                cat = subcat = ""
            return (
                _INV_CATEGORY_ORDER.get(cat, 99),
                _INV_SUBCATEGORY_ORDER.get(subcat, 99),
                item.name,
                item.strain or "",
            )
        self.player.inventory.sort(key=_key)

    def _add_item_to_inventory(self, item_id, strain=None, quantity=1):
        """Create an item and add it to player inventory, stacking if possible."""
        for _ in range(quantity):
            # Try to stack with existing item (skip charged items — each is unique)
            if is_stackable(item_id):
                for existing in self.player.inventory:
                    if (existing.item_id == item_id and existing.strain == strain
                            and getattr(existing, "charges", None) is None):
                        existing.quantity += 1
                        return
            # Create new item
            kwargs = create_item_entity(item_id, self.player.x, self.player.y, strain=strain)
            new_item = Entity(**kwargs)
            self.player.inventory.append(new_item)
        self._sort_inventory()

    def _acid_armor_break_equipment(self):
        """Break a random piece of equipped equipment from Acid Armor effect."""
        equipped_items = []
        if self.equipment.get("weapon"):
            equipped_items.append(("weapon", self.equipment["weapon"]))
        if self.equipment.get("neck"):
            equipped_items.append(("neck", self.equipment["neck"]))
        for i, ring in enumerate(self.rings):
            if ring:
                equipped_items.append((f"ring_{i}", ring))
        if self.equipment.get("feet"):
            equipped_items.append(("feet", self.equipment["feet"]))

        if equipped_items:
            slot, item = random.choice(equipped_items)
            # Unequip the item
            if slot == "weapon":
                self.equipment["weapon"] = None
            elif slot == "neck":
                self.equipment["neck"] = None
            elif slot == "feet":
                self.equipment["feet"] = None
            elif slot.startswith("ring_"):
                idx = int(slot.split("_")[1])
                self.rings[idx] = None
            self.messages.append(f"Acid Armor breaks your {item.name}!")
        else:
            self.messages.append("Acid Armor attacks, but you have no equipped items!")

    # ------------------------------------------------------------------
    # Drop / Use
    # ------------------------------------------------------------------

    def _drop_item(self, index):
        item = self.player.inventory[index]
        if item.quantity > 1:
            item.quantity -= 1
            kwargs = create_item_entity(item.item_id, self.player.x, self.player.y, strain=item.strain)
            dropped = Entity(**kwargs)
            self.dungeon.add_entity(dropped)
            self.messages.append([("Dropped ", _C_MSG_NEUTRAL), (dropped.name, dropped.color)])
        else:
            self.player.inventory.pop(index)
            item.x = self.player.x
            item.y = self.player.y
            self.dungeon.add_entity(item)
            self.messages.append([("Dropped ", _C_MSG_NEUTRAL), (item.name, item.color)])

    def _use_item(self, index):
        item = self.player.inventory[index]
        defn = get_item_def(item.item_id)
        effect = defn.get("use_effect")

        if effect is None:
            return

        effect_type = effect.get("type")
        skip_consume = False

        if effect_type == "message":
            text = effect["text"].format(name=item.name)
            self.messages.append(text)

        elif effect_type == "heal":
            base_amount = effect.get("amount", 5)
            amount = base_amount
            self.player.heal(amount)
            self.messages.append([
                ("Used ", _C_MSG_USE), (item.name, item.color),
                (f". Healed {amount} HP.", _C_MSG_USE),
            ])

        elif effect_type == "strain_roll":
            tlr = self.player_stats.effective_tolerance
            num_rolls, roll_floor = calc_tolerance_rolls(item.strain, tlr)
            rolls = [max(roll_floor + 1, random.randint(1, 100))
                     for _ in range(num_rolls)]
            roll = max(rolls)
            if num_rolls > 1:
                self.messages.append([
                    ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                    (f". Rolled {num_rolls}x: {rolls} -> {roll}", _C_MSG_USE),
                ])
            else:
                self.messages.append([
                    ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                    (f". (Roll: {roll})", _C_MSG_USE),
                ])
            self._apply_strain_effect(self.player, item.strain, roll, "player")

            # Gain smoking skill XP based on strain
            self._gain_smoking_xp(item.strain)

            # Check for double-smoking effects (e.g., Hennessy)
            # Any effect that grants double smoking has a 20% chance to trigger
            for effect_obj in self.player.status_effects:
                if getattr(effect_obj, 'id', '') == 'hennessy':
                    if random.random() < 0.20:
                        # Re-apply the same strain effect
                        self.messages.append([
                            ("The Hennessy amplifies the high! ", (200, 100, 100)),
                        ])
                        henny_rolls = [max(roll_floor + 1, random.randint(1, 100))
                                       for _ in range(num_rolls)]
                        henny_roll = max(henny_rolls)
                        self._apply_strain_effect(self.player, item.strain, henny_roll, "player")
                        self._gain_smoking_xp(item.strain)
                    break

            # Phat Cloud (Smoking level 1): deal 10 + tolerance//2 dmg to nearest visible enemy
            smoking_level = self.skills.get("Smoking").level
            if smoking_level >= 1:
                tlr = self.player_stats.effective_tolerance
                cloud_dmg = 10 + tlr // 2
                best = None
                best_dist = float("inf")
                for mon in self.dungeon.get_monsters():
                    if not mon.alive:
                        continue
                    if not self.dungeon.visible[mon.y, mon.x]:
                        continue
                    d = self._dist_sq(self.player.x, self.player.y, mon.x, mon.y)
                    if d < best_dist:
                        best_dist = d
                        best = mon
                if best is not None:
                    best.take_damage(cloud_dmg)
                    hp_disp = f"{best.hp}/{best.max_hp}" if best.alive else "dead"
                    self.messages.append([
                        ("Phat Cloud! ", (150, 255, 150)),
                        (f"Hit {best.name} for {cloud_dmg} dmg! ({hp_disp})", _C_MSG_USE),
                    ])
                    if not best.alive:
                        self.event_bus.emit("entity_died", entity=best, killer=self.player)

            # Roach Fiend (Smoking level 3): 50% chance joint is not consumed
            if smoking_level >= 3:
                if random.random() < 0.5:
                    skip_consume = True
                    self.messages.append([
                        ("Roach Fiend! ", (200, 255, 100)),
                        ("The roach hangs on.", _C_MSG_USE),
                    ])

        elif effect_type == "stat_boost" or "effect_id" in effect:
            amount = effect.get("amount", 0)
            stat = effect.get("stat")
            duration = effect.get("duration", 10)
            effect_id = effect.get("effect_id", "stat_mod")
            self.messages.append([("Used ", _C_MSG_USE), (item.name, item.color), (".", _C_MSG_USE)])
            effects.apply_effect(self.player, self, effect_id,
                                 duration=duration, amount=amount, stat=stat)

        elif effect_type == "alcohol":
            drink_id = effect.get("drink_id")
            self._handle_alcohol(item, drink_id)
            # Drinking perk 2: 20% chance not consumed
            drink_level = self.skills.get("Drinking").level
            if drink_level >= 2 and random.random() < 0.20:
                skip_consume = True
                self.messages.append([
                    ("One More Sip! ", (100, 200, 255)),
                    ("The bottle's not empty yet.", (200, 200, 200)),
                ])

        elif effect_type == "food":
            food_id = effect.get("food_id")
            self._use_food(item, food_id)

        elif effect_type == "torch_burn":
            # Enter combine mode to select which item to burn
            self.menu_state = MenuState.COMBINE_SELECT
            self.selected_item_index = index
            self._init_combine_cursor()
            self.messages.append([
                ("Select an item to burn with ", _C_MSG_USE), (item.name, item.color),
            ])
            return

        # Skill XP
        skill_xp = effect.get("skill_xp")
        if skill_xp:
            for skill_name, xp_amount in skill_xp.items():
                # Check if skill is newly unlocked (no XP before this call)
                skill = self.skills.get(skill_name)
                was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

                adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
                self.skills.gain_potential_exp(
                    skill_name, adjusted_xp,
                    self.player_stats.effective_book_smarts
                )
                # Add unlock notification if this is the first XP
                if was_locked:
                    self.messages.append([
                        (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
                    ])

        if effect.get("consumed", True) and not skip_consume:
            # Use identity search instead of index — apply_effect may have mutated the inventory
            if getattr(item, "charges", None) is not None:
                item.charges -= 1
                if item.charges <= 0:
                    for i, x in enumerate(self.player.inventory):
                        if x is item:
                            self.player.inventory.pop(i)
                            break
            else:
                item.quantity -= 1
                if item.quantity <= 0:
                    for i, x in enumerate(self.player.inventory):
                        if x is item:
                            self.player.inventory.pop(i)
                            break

    def _use_food(self, item, food_id):
        """Apply a food item: consume immediately and apply eating effect."""
        food_defn = get_food_def(food_id)
        if not food_defn:
            self.messages.append(f"Unknown food: {food_id}")
            return

        food_name = food_defn.get("name", "Food")
        eat_length = food_defn.get("eat_length", 10)
        eating_effect_name = food_defn.get("eating_effect_name", f"Eating {food_name}")
        well_fed_effect_name = food_defn.get("well_fed_effect_name", "Well Fed")
        food_effects = list(food_defn.get("effects", []))

        # Prepend prefix adjective to displayed food name and inject prefix effects
        item_prefix = getattr(item, "prefix", None)
        if item_prefix:
            pdef = get_food_prefix_def(item_prefix)
            adj = pdef["display_adjective"] if pdef else item_prefix.title()
            food_name = f"{adj} {food_name}"
            if pdef:
                for eff_type in pdef.get("effects", []):
                    food_effects.append({"type": eff_type})

        # Check for Quick Eat buff — if active, consume food instantly
        quick_eat = next(
            (e for e in self.player.status_effects if getattr(e, 'id', '') == 'quick_eat'),
            None,
        )
        if quick_eat:
            self.player.status_effects.remove(quick_eat)
            self.messages.append([
                ("[Quick Eat] ", (255, 200, 50)),
                ("You scarf down the ", (150, 200, 150)),
                (item.name, item.color),
                (" instantly!", (150, 200, 150)),
            ])
            # Apply food effects immediately by creating a temporary eating effect and expiring it
            eating = effects.EatingFoodEffect(
                duration=0,
                food_id=food_id,
                food_name=food_name,
                food_effects=food_effects,
                well_fed_effect_name=well_fed_effect_name,
            )
            eating.expire(self.player, self)
            return

        self.messages.append([
            ("You start eating ", (150, 200, 150)),
            (item.name, item.color),
            ("...", (150, 200, 150)),
        ])

        effects.apply_effect(
            self.player, self, "eating_food",
            duration=eat_length,
            food_id=food_id,
            food_name=food_name,
            food_effects=food_effects,
            well_fed_effect_name=well_fed_effect_name,
            silent=True
        )

    # ------------------------------------------------------------------
    # Destroy
    # ------------------------------------------------------------------

    def _handle_examine_input(self, action):
        action_type = action.get("type")
        if action_type == "close_menu":
            self.menu_state = MenuState.ITEM_MENU
        return False

    def _handle_destroy_confirm_input(self, action):
        action_type = action.get("type")

        # Left/right arrows move cursor between No (0) and Yes (1)
        if action_type == "move":
            dx = action.get("dx", 0)
            if dx != 0:
                self.destroy_confirm_cursor = 1 - self.destroy_confirm_cursor
            return False

        # Y key (select_item index 17 in INVENTORY_KEYS) → confirm yes
        # N key (select_item index 8 in INVENTORY_KEYS) → confirm no
        if action_type == "select_item":
            idx = action.get("index")
            if idx == 17:    # 'y'
                action_type = "confirm_yes"
            elif idx == 8:   # 'n'
                action_type = "confirm_no"

        # Enter or Space confirms based on cursor position
        if action_type in ("confirm_target", "item_use"):
            action_type = "confirm_yes" if self.destroy_confirm_cursor == 1 else "confirm_no"

        if action_type == "confirm_yes":
            self._destroy_item(self.selected_item_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            self.destroy_confirm_cursor = 0
        elif action_type in ("confirm_no", "close_menu"):
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            self.destroy_confirm_cursor = 0
        return False

    def _destroy_item(self, index):
        item = self.player.inventory[index]
        qty = getattr(item, "quantity", 1)
        self._gain_item_skill_xp("Dismantling", item.item_id)
        self.destroyed_items.append({"name": item.name, "quantity": qty})
        self.player.inventory.pop(index)
        self.messages.append([
            ("Destroyed ", (200, 80, 80)),
            (item.name, item.color),
            (".", (200, 80, 80)),
        ])
        # Dismantling L2: Chop Shop — bonus armor and cash on destroy
        dm_level = self.skills.get("Dismantling").level
        if dm_level >= 2:
            gained = min(5, self.player.max_armor - self.player.armor)
            self.player.armor += gained
            self.cash += 20
            self.messages.append(f"  [Chop Shop] +{gained} armor, +$20 from salvage!")
        # Dismantling L3: Nigga Armor — stack on destroy
        if dm_level >= 3:
            import effects as _eff
            _eff.apply_effect(self.player, self, "nigga_armor", stacks=1, silent=True)
            na = next((e for e in self.player.status_effects if getattr(e, "id", "") == "nigga_armor"), None)
            count = len(na.timers) if na else 1
            self.messages.append(f"  [Nigga Armor] x{count} (-{count} incoming dmg, 30t)")

    # ------------------------------------------------------------------
    # Ring Replacement
    # ------------------------------------------------------------------

    def _handle_ring_replace_input(self, action):
        """Handle input for selecting which ring to replace."""
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.pending_ring_item_index = None
            return False

        if action_type == "move":
            # Up/down to move cursor through rings
            dy = action.get("dy", 0)
            self.ring_replace_cursor = max(0, min(9, self.ring_replace_cursor + dy))
            return False

        if action_type == "select_ring_slot":
            # Converted from select_action in process_action
            slot = action.get("slot")
            self._replace_ring_at_slot(slot)
            self.menu_state = MenuState.NONE
            self.pending_ring_item_index = None
            return True

        if action_type == "confirm_target":
            # Enter key to confirm selection
            self._replace_ring_at_slot(self.ring_replace_cursor)
            self.menu_state = MenuState.NONE
            self.pending_ring_item_index = None
            return True

        return False

    def _replace_ring_at_slot(self, slot_index: int):
        """Replace the ring at the given slot with the pending ring item."""
        if not (0 <= slot_index < RING_SLOTS):
            return

        if self.pending_ring_item_index is None:
            return

        # Get the new ring from inventory
        new_ring = self.player.inventory[self.pending_ring_item_index]

        # Get the old ring at this slot
        old_ring = self.rings[slot_index]

        # Equip the new ring (pop from inventory first to avoid index issues after sorting)
        self.rings[slot_index] = self.player.inventory.pop(self.pending_ring_item_index)

        # Return the old ring to inventory and sort
        if old_ring is not None:
            self.player.inventory.append(old_ring)
            self._sort_inventory()
            self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (old_ring.name, old_ring.color)])

        self._refresh_ring_stat_bonuses()
        self.messages.append([("Equipped ", _C_MSG_NEUTRAL), (new_ring.name, new_ring.color)])

    # ------------------------------------------------------------------
    # Crafting / Combine
    # ------------------------------------------------------------------

    def _is_valid_combine_target(self, inv_idx):
        """Return True if the item at inv_idx is a valid combine target for selected_item."""
        if inv_idx == self.selected_item_index:
            return False
        src = self.player.inventory[self.selected_item_index]
        cand = self.player.inventory[inv_idx]
        if find_recipe(src.item_id, cand.item_id):
            return True
        if src.item_id in PREFIX_TOOL_ITEMS and cand.item_id in FOOD_DEFS:
            return getattr(cand, "prefix", None) is None
        if src.item_id in FOOD_DEFS and cand.item_id in PREFIX_TOOL_ITEMS:
            return getattr(src, "prefix", None) is None
        src_def = get_item_def(src.item_id)
        if src_def and (src_def.get("use_effect") or {}).get("type") == "torch_burn":
            return True
        return False

    def _get_valid_combine_targets(self):
        """Return list of inventory indices that are valid combine targets."""
        return [i for i in range(len(self.player.inventory)) if self._is_valid_combine_target(i)]

    def _init_combine_cursor(self):
        """Set combine_target_cursor to the first valid target."""
        targets = self._get_valid_combine_targets()
        self.combine_target_cursor = targets[0] if targets else None

    def _handle_combine_input(self, action):
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            self.combine_target_cursor = None
            return False

        # Up/Down — scroll through valid combine targets
        if action_type == "move":
            dy = action.get("dy", 0)
            if dy != 0:
                targets = self._get_valid_combine_targets()
                if targets and self.combine_target_cursor is not None:
                    cur_pos = targets.index(self.combine_target_cursor) if self.combine_target_cursor in targets else 0
                    self.combine_target_cursor = targets[(cur_pos + dy) % len(targets)]
            return False

        # Enter — confirm target at cursor
        if action_type == "confirm_target":
            if self.combine_target_cursor is not None:
                result = bool(self._try_combine(self.selected_item_index, self.combine_target_cursor))
                self.menu_state = MenuState.NONE
                self.selected_item_index = None
                self.combine_target_cursor = None
                return result
            return False

        # Letter keys — still work as direct selection
        if action_type == "select_item":
            target_index = action["index"]
            if target_index == self.selected_item_index:
                return False
            result = False
            if 0 <= target_index < len(self.player.inventory):
                result = bool(self._try_combine(self.selected_item_index, target_index))
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            self.combine_target_cursor = None
            return result

        return False

    def _try_combine(self, index_a, index_b):
        item_a = self.player.inventory[index_a]
        item_b = self.player.inventory[index_b]

        # Torch burn path: bic_torch + any item → destroy item, gain Pyromania XP
        torch_item = target_item = None
        if item_a.item_id == "bic_torch" and item_b.item_id != "bic_torch":
            torch_item, target_item = item_a, item_b
            target_index = index_b
        elif item_b.item_id == "bic_torch" and item_a.item_id != "bic_torch":
            torch_item, target_item = item_b, item_a
            target_index = index_a

        if torch_item and target_item:
            # Gain Pyromania XP equal to 2x item value
            xp_amount = get_item_value(target_item.item_id) * 2
            adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)

            # Check if skill is newly unlocked
            skill = self.skills.get("Pyromania")
            was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

            self.skills.gain_potential_exp(
                "Pyromania", adjusted_xp,
                self.player_stats.effective_book_smarts
            )

            # Remove the target item
            target_item.quantity -= 1
            if target_item.quantity <= 0:
                self.player.inventory.pop(target_index)

            self.messages.append([
                (f"Burned ", (255, 100, 0)), (target_item.name, target_item.color),
                (f" with ", (255, 100, 0)), (torch_item.name, torch_item.color),
                (f". Gained {adjusted_xp} Pyromania XP!", (255, 215, 0)),
            ])

            # Add unlock notification if this is the first XP
            if was_locked:
                self.messages.append([
                    (f"[NEW SKILL UNLOCKED] Pyromania!", (255, 215, 0)),
                ])
            return True

        # Prefix-tool path: fry_daddy (or other PREFIX_TOOL_ITEMS) + food → prefixed food
        tool_item = food_item = None
        if item_a.item_id in PREFIX_TOOL_ITEMS and item_b.item_id in FOOD_DEFS:
            tool_item, food_item = item_a, item_b
        elif item_b.item_id in PREFIX_TOOL_ITEMS and item_a.item_id in FOOD_DEFS:
            tool_item, food_item = item_b, item_a

        if tool_item and food_item:
            if getattr(food_item, "prefix", None) is not None:
                self.messages.append(f"{food_item.name} already has the '{food_item.prefix}' prefix applied!")
                return
            # Split stack: only prefix one unit
            if food_item.quantity > 1:
                food_item.quantity -= 1
                kwargs = create_item_entity(food_item.item_id, self.player.x, self.player.y, strain=food_item.strain)
                new_ent = Entity(**kwargs)
                self.player.inventory.append(new_ent)
                food_item = new_ent
            # Apply prefix
            prefix_name = PREFIX_TOOL_ITEMS[tool_item.item_id]
            pdef = get_food_prefix_def(prefix_name)
            food_item.prefix = prefix_name
            food_item.charges = pdef["charges"]
            food_item.max_charges = pdef["charges"]
            adj = pdef["display_adjective"]
            base_name = get_item_def(food_item.item_id)["name"]
            food_item.name = f"{adj} {base_name}"
            c = food_item.charges
            self.messages.append(f"Applied '{prefix_name}' prefix to {food_item.name} ({c}/{c})!")
            # Gain deep-frying XP when a food is fried (greasy prefix from fry_daddy)
            if tool_item.item_id == "fry_daddy":
                self._gain_deep_frying_xp(food_item.item_id)
            # Deep-Frying L3: Double Batch — 20% chance to keep the food item
            if tool_item.item_id == "fry_daddy" and self.skills.get("Deep-Frying").level >= 3:
                if random.random() < 0.20:
                    refund_kwargs = create_item_entity(food_item.item_id, self.player.x, self.player.y)
                    refund = Entity(**refund_kwargs)
                    self.player.inventory.append(refund)
                    self.messages.append(f"  [Double Batch] Proc! You kept a {get_item_def(food_item.item_id)['name']}!")
            self._sort_inventory()
            return True

        recipe = find_recipe(item_a.item_id, item_b.item_id)

        if recipe is None:
            self.messages.append(f"Can't combine {item_a.name} with {item_b.name}")
            return

        # Capture strain before any removals
        result_id = recipe["result"]
        result_strain = get_craft_result_strain(item_a, item_b)

        # Consume 1 from each consumed item's stack (remove when quantity hits 0)
        consumed_ids = recipe["consumed"]
        to_consume = []
        if item_a.item_id in consumed_ids:
            to_consume.append(index_a)
        if item_b.item_id in consumed_ids:
            to_consume.append(index_b)

        for idx in sorted(to_consume, reverse=True):
            item = self.player.inventory[idx]
            item.quantity -= 1
            if item.quantity <= 0:
                self.player.inventory.pop(idx)

        # Try to merge result into an existing stack (skip charged items — each is unique)
        if is_stackable(result_id):
            existing = next(
                (i for i in self.player.inventory
                 if i.item_id == result_id and i.strain == result_strain
                 and getattr(i, "charges", None) is None),
                None,
            )
            if existing:
                existing.quantity += 1
                display = build_inventory_display_name(existing.item_id, existing.strain, existing.quantity)
                self.messages.append([
                    ("Combined into ", _C_MSG_NEUTRAL),
                    (display, existing.color),
                    ("!", _C_MSG_NEUTRAL),
                ])
                # Award rolling skill XP for grinding (nug -> kush) or rolling (kush -> joint)
                if result_strain and result_id in ("joint", "kush"):
                    is_grinding = result_id == "kush"
                    self._gain_rolling_xp(result_strain, is_grinding=is_grinding)
                # Seeing Double (Rolling level 2): 50% chance to roll an extra joint
                if result_id == "joint" and self.skills.get("Rolling").level >= 2:
                    if random.random() < 0.5:
                        self._add_item_to_inventory("joint", strain=result_strain)
                        self.messages.append([
                            ("Seeing Double! ", (255, 220, 80)),
                            ("You rolled an extra joint.", _C_MSG_USE),
                        ])
                return True

        kwargs = create_item_entity(result_id, 0, 0, strain=result_strain)
        result_item = Entity(**kwargs)
        self.player.inventory.append(result_item)
        self._sort_inventory()
        self.messages.append([
            ("Combined into ", _C_MSG_NEUTRAL),
            (result_item.name, result_item.color),
            ("!", _C_MSG_NEUTRAL),
        ])
        # Award rolling skill XP for grinding (nug -> kush) or rolling (kush -> joint)
        if result_strain and result_id in ("joint", "kush"):
            is_grinding = result_id == "kush"
            self._gain_rolling_xp(result_strain, is_grinding=is_grinding)
        # Seeing Double (Rolling level 2): 50% chance to roll an extra joint
        if result_id == "joint" and self.skills.get("Rolling").level >= 2:
            if random.random() < 0.5:
                self._add_item_to_inventory("joint", strain=result_strain)
                self.messages.append([
                    ("Seeing Double! ", (255, 220, 80)),
                    ("You rolled an extra joint.", _C_MSG_USE),
                ])
        return True

    # ------------------------------------------------------------------
    # Targeting mode
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Entity targeting (f-key: cycle visible monsters within weapon range)
    # ------------------------------------------------------------------

    def _get_weapon_reach(self) -> int:
        """Return the reach of the equipped weapon (1 = adjacent, 2+ = extended)."""
        weapon = self.equipment.get("weapon")
        if weapon:
            defn = get_item_def(weapon.item_id)
            return defn.get("reach", 1)
        return 1

    def _build_entity_target_list(self, reach: int) -> list:
        """Return visible living monsters within Chebyshev reach, sorted closest-first."""
        targets = []
        for entity in self.dungeon.get_monsters():
            if not entity.alive:
                continue
            dx = abs(entity.x - self.player.x)
            dy = abs(entity.y - self.player.y)
            dist = max(dx, dy)  # Chebyshev distance
            if dist <= reach and self.dungeon.visible[entity.y, entity.x]:
                targets.append((dist, entity.x, entity))
        targets.sort(key=lambda t: (t[0], t[1]))
        return [e for _, _, e in targets]

    def _action_start_entity_targeting(self, _action):
        """Enter entity targeting mode if there are valid targets in weapon range."""
        reach = self._get_weapon_reach()
        if reach < 1:
            self.messages.append("Your weapon cannot be used at range.")
            return False
        target_list = self._build_entity_target_list(reach)
        if not target_list:
            self.messages.append("No targets in range.")
            return False
        self.entity_target_list = target_list
        self.entity_target_index = 0
        self.menu_state = MenuState.ENTITY_TARGETING
        return False

    def _handle_entity_targeting_input(self, action):
        """Left/right cycle targets; Enter attacks/fires ability; Esc cancels."""
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.entity_target_list = []
            self.targeting_ability_index = None
            return False

        if action_type == "move":
            dx = action.get("dx", 0)
            if dx != 0 and self.entity_target_list:
                n = len(self.entity_target_list)
                self.entity_target_index = (self.entity_target_index + dx) % n
            return False

        if action_type == "confirm_target":
            if not self.entity_target_list:
                self.menu_state = MenuState.NONE
                self.targeting_ability_index = None
                return False
            target = self.entity_target_list[self.entity_target_index]
            self.entity_target_list = []
            self.menu_state = MenuState.NONE

            # Ability adjacent targeting: fire the ability instead of a weapon attack
            if self.targeting_ability_index is not None:
                if target.alive:
                    result = self._fire_adjacent_ability(target.x, target.y)
                    if result and self.running and self.player.alive:
                        self.player.energy -= ENERGY_THRESHOLD
                        self._run_energy_loop()
                    return result
                self.targeting_ability_index = None
                return False

            if target.alive:
                self.handle_attack(self.player, target)
                if self.running and self.player.alive:
                    self.player.energy -= ENERGY_THRESHOLD
                    self._run_energy_loop()
            return True

        return False

    def _enter_targeting(self, item_index):
        """Enter targeting mode for a throw action. Cursor starts at player position."""
        self.targeting_item_index = item_index
        self.targeting_cursor = [self.player.x, self.player.y]
        self.selected_item_index = None
        self.menu_state = MenuState.TARGETING

    def _handle_targeting_input(self, action):
        """Handle input while in targeting mode. Arrow keys move cursor; Enter throws/casts; Esc cancels."""
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.targeting_item_index = None
            self.targeting_spell = None
            self.targeting_ability_index = None
            return False

        if action_type == "move":
            nx = self.targeting_cursor[0] + action["dx"]
            ny = self.targeting_cursor[1] + action["dy"]
            if 0 <= nx < DUNGEON_WIDTH and 0 <= ny < DUNGEON_HEIGHT:
                self.targeting_cursor = [nx, ny]
            return False

        if action_type == "confirm_target":
            tx, ty = self.targeting_cursor
            if self.targeting_spell is not None:
                if not self._is_targeting_in_range(tx, ty):
                    self.messages.append("Out of range!")
                    return False
                return self._execute_spell_at(tx, ty)
            return self._throw_item(self.targeting_item_index, tx, ty)

        return False

    def _throw_item(self, item_index, tx, ty):
        """Throw item at target tile. Apply throw_effect to monster if present, else waste it."""
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("You can't throw there — it's not in your line of sight.")
            self.menu_state = MenuState.NONE
            self.targeting_item_index = None
            return False

        item = self.player.inventory[item_index]
        defn = get_item_def(item.item_id)
        throw_effect = defn.get("throw_effect")
        item_name = item.name
        item_color = item.color

        target_monster = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )

        # Consume one from the stack
        item.quantity -= 1
        if item.quantity <= 0:
            self.player.inventory.pop(item_index)

        self.menu_state = MenuState.NONE
        self.targeting_item_index = None

        if target_monster is not None and throw_effect:
            self.messages.append([
                ("You threw ", _C_MSG_NEUTRAL),
                (item_name, item_color),
                (f" at {target_monster.name}!", _C_MSG_NEUTRAL),
            ])
            if throw_effect.get("type") == "strain_roll":
                roll = random.randint(1, 100)
                self._apply_strain_effect(target_monster, item.strain, roll, "monster")
            else:
                self._apply_item_effect_to_entity(throw_effect, target_monster)
            return True

        # No monster — wasted
        self.messages.append(random.choice(_WASTE_MESSAGES))
        return True

    # ------------------------------------------------------------------
    # Dosidos spell targeting
    # ------------------------------------------------------------------

    def _get_targeting_ability_def(self):
        """Return the AbilityDef for the ability currently being targeted, or None."""
        if self.targeting_ability_index is not None:
            if 0 <= self.targeting_ability_index < len(self.player_abilities):
                inst = self.player_abilities[self.targeting_ability_index]
                return ABILITY_REGISTRY.get(inst.ability_id)
        return None

    def _is_targeting_in_range(self, tx: int, ty: int) -> bool:
        """Return True if (tx, ty) is within the current ability's max_range (0.0 = unlimited, Manhattan distance)."""
        defn = self._get_targeting_ability_def()
        if defn is None or defn.max_range == 0.0:
            return True
        dist = abs(tx - self.player.x) + abs(ty - self.player.y)
        return dist <= defn.max_range

    def _enter_spell_targeting(self, spell_dict: dict) -> None:
        """Enter cursor targeting mode for a Dosidos spell cast."""
        self.targeting_spell = dict(spell_dict)
        self.targeting_item_index = None
        self.targeting_cursor = [self.player.x, self.player.y]
        self.menu_state = MenuState.TARGETING

    def _execute_spell_at(self, tx: int, ty: int) -> bool:
        """Dispatch spell execution at (tx, ty).
        If the current ability has an execute_at, call it and handle charge/menu cleanup.
        Otherwise fall back to _execute_dosidos_spell_at for item-triggered spells."""
        defn = self._get_targeting_ability_def()
        if defn is not None and defn.execute_at is not None:
            fired = defn.execute_at(self, tx, ty)
            if fired:
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return fired
        return self._execute_dosidos_spell_at(tx, ty)

    def _execute_dosidos_spell_at(self, tx: int, ty: int) -> bool:
        """Execute an item-triggered (Dosidos) spell at (tx, ty).
        Returns True to close targeting (final cast done), False to keep it open."""
        spell = self.targeting_spell
        spell_type = spell["type"]

        if spell_type == "dimension_door":
            if self._spell_dimension_door(tx, ty):
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return False

        elif spell_type == "chain_lightning":
            if self._spell_chain_lightning(tx, ty, spell.get("total_hits", 4)):
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return False

        elif spell_type == "ray_of_frost":
            dx = tx - self.player.x
            dy = ty - self.player.y
            if dx == 0 and dy == 0:
                self.messages.append("Ray of Frost: aim your cursor away from yourself!")
                return False
            unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
            unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0
            self._spell_ray_of_frost(unit_dx, unit_dy)
            ability_id = self._consume_ability_charge()
            if ability_id:
                self._gain_spell_xp(ability_id)
            count = spell.get("count", 1) - 1
            if count > 0:
                spell["count"] = count
                self.targeting_cursor = [self.player.x, self.player.y]
                self.messages.append(f"Ray of Frost! {count} shot(s) remaining — aim again.")
            else:
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return False

        elif spell_type == "firebolt":
            if self._spell_firebolt(tx, ty):
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                count = spell.get("count", 1) - 1
                if count > 0:
                    spell["count"] = count
                    self.targeting_cursor = [self.player.x, self.player.y]
                    self.messages.append(f"Firebolt! {count} shot(s) remaining — pick next target.")
                else:
                    self.menu_state = MenuState.NONE
                    self.targeting_spell = None
            return False

        elif spell_type == "arcane_missile":
            if self._spell_arcane_missile(tx, ty):
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                count = spell.get("count", 1) - 1
                if count > 0:
                    spell["count"] = count
                    self.targeting_cursor = [self.player.x, self.player.y]
                    self.messages.append(f"Magic Missile! {count} shot(s) remaining — pick next target.")
                else:
                    self.menu_state = MenuState.NONE
                    self.targeting_spell = None
            return False

        elif spell_type == "breath_fire":
            if self._spell_breath_fire(tx, ty):
                ability_id = self._consume_ability_charge()
                if ability_id:
                    self._gain_spell_xp(ability_id)
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return False

        self.menu_state = MenuState.NONE
        self.targeting_spell = None
        return False

    # ------------------------------------------------------------------
    # Dosidos spell implementations
    # ------------------------------------------------------------------

    @staticmethod
    def _dist_sq(x0: int, y0: int, x1: int, y1: int) -> int:
        return (x0 - x1) ** 2 + (y0 - y1) ** 2

    def _ray_tiles(self, start_x: int, start_y: int, dx: int, dy: int, max_dist: int = 10):
        """Yield (x, y) tiles along a ray starting one step from origin, stopping before walls."""
        tiles = []
        x, y = start_x + dx, start_y + dy
        for _ in range(max_dist):
            if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
                break
            if self.dungeon.is_terrain_blocked(x, y):
                break
            tiles.append((x, y))
            x += dx
            y += dy
        return tiles

    def _trace_projectile(self, x0: int, y0: int, tx: int, ty: int):
        """Trace a projectile from (x0,y0) toward (tx,ty) via linear interpolation.
        Returns the first alive monster Entity hit, or None if blocked by wall first."""
        dx = tx - x0
        dy = ty - y0
        steps = max(abs(dx), abs(dy))
        if steps == 0:
            return None
        for step in range(1, steps + 1):
            x = round(x0 + dx * step / steps)
            y = round(y0 + dy * step / steps)
            if not (0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT):
                return None
            if self.dungeon.is_terrain_blocked(x, y):
                return None
            for entity in self.dungeon.get_entities_at(x, y):
                if entity.entity_type == "monster" and entity.alive:
                    return entity
        return None

    def _spell_dimension_door(self, tx: int, ty: int) -> bool:
        """Teleport to target explored tile. Returns True on success."""
        if not self.dungeon.explored[ty, tx]:
            self.messages.append("Dimension Door: you haven't explored that tile yet.")
            return False
        if self.dungeon.is_terrain_blocked(tx, ty):
            self.messages.append("Dimension Door: that tile is blocked by a wall.")
            return False
        blocker = self.dungeon.get_blocking_entity_at(tx, ty)
        if blocker is not None and blocker is not self.player:
            self.messages.append(f"Dimension Door: {blocker.name} is in the way!")
            return False
        self.dungeon.move_entity(self.player, tx, ty)
        self._compute_fov()
        self.messages.append(f"Dimension Door! You blink to ({tx}, {ty}).")
        self._pickup_items_at(tx, ty)
        return True

    def _spell_chain_lightning(self, tx: int, ty: int, total_hits: int) -> bool:
        """Chain lightning hitting total_hits times, bouncing to the nearest monster each time.
        Returns True if the spell fired, False if the target was invalid."""
        stsmt = self.player_stats.effective_street_smarts
        tlr   = self.player_stats.effective_tolerance
        damage = 5 + stsmt + tlr + self._get_wizard_bomb_bonus()

        target = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if target is None:
            self.messages.append("Chain Lightning: no enemy at that tile!")
            return False
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("Chain Lightning: target not in line of sight!")
            return False

        self.messages.append(f"Chain Lightning! ({total_hits} hits, {damage} dmg each)")
        for i in range(total_hits):
            if target is None:
                break
            last_x, last_y = target.x, target.y
            target.take_damage(damage)
            hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
            self.messages.append(f"  Lightning hits {target.name} for {damage} ({hp_disp})")
            if not target.alive:
                self.event_bus.emit("entity_died", entity=target, killer=self.player)
            if i < total_hits - 1:
                living = [e for e in self.dungeon.get_monsters() if e.alive]
                if not living:
                    break
                BOUNCE_DIST_SQ = 4  # 2-tile Euclidean radius (2^2 = 4)
                candidates = [e for e in living
                              if self._dist_sq(last_x, last_y, e.x, e.y) <= BOUNCE_DIST_SQ]
                if not candidates:
                    self.messages.append("  Lightning fizzles — no target in range to chain!")
                    break
                min_d = min(self._dist_sq(last_x, last_y, e.x, e.y) for e in candidates)
                nearest = [e for e in candidates
                           if self._dist_sq(last_x, last_y, e.x, e.y) == min_d]
                target = random.choice(nearest)
        return True

    def _spell_ray_of_frost(self, dx: int, dy: int) -> None:
        """Fire a Ray of Frost in direction (dx, dy). Deals 12+BKSMT damage to all monsters
        in a 10-tile line; stops at walls."""
        bksmt  = self.player_stats.effective_book_smarts
        damage = 12 + bksmt + self._get_wizard_bomb_bonus()
        tiles  = self._ray_tiles(self.player.x, self.player.y, dx, dy, max_dist=10)
        hit_count = 0
        for x, y in tiles:
            for entity in list(self.dungeon.get_entities_at(x, y)):
                if entity.entity_type == "monster" and entity.alive:
                    entity.take_damage(damage)
                    hp_disp = f"{entity.hp}/{entity.max_hp}" if entity.alive else "dead"
                    self.messages.append(
                        f"Ray of Frost hits {entity.name} for {damage} dmg! ({hp_disp})"
                    )
                    hit_count += 1
                    if not entity.alive:
                        self.event_bus.emit("entity_died", entity=entity, killer=self.player)
        if hit_count == 0:
            self.messages.append("Ray of Frost — no targets in that direction.")

    def _spell_warp(self) -> None:
        """Teleport to a random passable, unoccupied floor tile."""
        candidates = []
        for room in self.dungeon.rooms:
            for rx, ry in room.floor_tiles(self.dungeon):
                if self.dungeon.is_terrain_blocked(rx, ry):
                    continue
                blocker = self.dungeon.get_blocking_entity_at(rx, ry)
                if blocker is None or blocker is self.player:
                    if not (rx == self.player.x and ry == self.player.y):
                        candidates.append((rx, ry))
        if not candidates:
            self.messages.append("Warp: nowhere to go!")
            return
        tx, ty = random.choice(candidates)
        self.dungeon.move_entity(self.player, tx, ty)
        self._compute_fov()
        self.messages.append("Warp! You vanish and reappear elsewhere on the floor.")
        self._pickup_items_at(tx, ty)

    def _player_ignite_duration(self) -> int:
        """Base ignite duration the player applies. +5 with Neva Burn Out (Pyromania lv4)."""
        base = 5
        pyro = self.skills.get("Pyromania")
        if pyro and pyro.level >= 4:
            base += 5
        return base

    def _spell_firebolt(self, tx: int, ty: int) -> bool:
        """Fire a Firebolt toward (tx, ty). Blocked by walls and entities. Returns True on hit."""
        bksmt  = self.player_stats.effective_book_smarts
        damage = 10 + bksmt + self._get_wizard_bomb_bonus()
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("Firebolt: no line of sight to that tile.")
            return False
        hit = self._trace_projectile(self.player.x, self.player.y, tx, ty)
        if hit is None:
            self.messages.append("Firebolt fizzles — no target in path!")
            return False
        hit.take_damage(damage)
        ignite_eff = effects.apply_effect(hit, self, "ignite", duration=self._player_ignite_duration(), stacks=1, silent=True)
        stacks = ignite_eff.stacks if ignite_eff else 1
        hp_disp = f"{hit.hp}/{hit.max_hp}" if hit.alive else "dead"
        self.messages.append(
            f"Firebolt! {hit.name} takes {damage} dmg and ignites (x{stacks})! ({hp_disp})"
        )
        if not hit.alive:
            self.event_bus.emit("entity_died", entity=hit, killer=self.player)
        return True

    def _spell_arcane_missile(self, tx: int, ty: int) -> bool:
        """Fire an Arcane Missile at a visible target at (tx, ty). Returns True on hit."""
        bksmt  = self.player_stats.effective_book_smarts
        damage = math.ceil(8 + bksmt / 2 + self._get_wizard_bomb_bonus())
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("Arcane Missile: target not in view.")
            return False
        target = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if target is None:
            self.messages.append("Arcane Missile: no visible enemy there.")
            return False
        target.take_damage(damage)
        hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
        self.messages.append(f"Arcane Missile! {target.name} takes {damage} dmg! ({hp_disp})")
        if not target.alive:
            self.event_bus.emit("entity_died", entity=target, killer=self.player)
        return True

    def _spell_breath_fire(self, tx: int, ty: int) -> bool:
        """Breathe a cone of fire toward (tx, ty). Cone: 5-tile range, 90° spread.
        Affected by walls, passes through enemies."""
        bksmt = self.player_stats.effective_book_smarts
        damage = 20 + bksmt + self._get_wizard_bomb_bonus()

        # Determine center direction toward target
        dx = tx - self.player.x
        dy = ty - self.player.y
        if dx == 0 and dy == 0:
            self.messages.append("Breath Fire: aim away from yourself!")
            return False

        # Normalize to unit vector
        dist = math.sqrt(dx*dx + dy*dy)
        center_dx = dx / dist
        center_dy = dy / dist

        # Get cone tiles (5-tile range, 90° spread)
        # For simplicity: create tiles in a cone pattern
        # Center: -2 to +2 angle from center direction, 1-5 tiles out
        cone_tiles = self._get_cone_tiles(self.player.x, self.player.y, center_dx, center_dy, range_dist=5)

        if not cone_tiles:
            self.messages.append("Breath Fire: no valid targets!")
            return False

        # Apply damage to all enemies in cone
        hit_targets = set()
        for cx, cy in cone_tiles:
            for entity in self.dungeon.get_entities_at(cx, cy):
                if entity.entity_type == "monster" and entity.alive and entity not in hit_targets:
                    entity.take_damage(damage)
                    effects.apply_effect(entity, self, "ignite", duration=self._player_ignite_duration(), stacks=3, silent=True)
                    hit_targets.add(entity)

        if not hit_targets:
            self.messages.append("Breath Fire: no enemies in range!")
            return False

        self.messages.append(f"You breathe a cone of fire! {len(hit_targets)} enemy(ies) engulfed.")
        for entity in hit_targets:
            if not entity.alive:
                self.event_bus.emit("entity_died", entity=entity, killer=self.player)

        return True

    def _get_cone_tiles(self, cx: int, cy: int, dir_x: float, dir_y: float, range_dist: int = 5):
        """Get all tiles in a cone (5-range, 90° spread) centered on direction.
        Blocked by walls, passes through enemies."""
        import math
        tiles = []

        # Get perpendicular vector for spread
        perp_x = -dir_y
        perp_y = dir_x

        # For each distance level (1 to range_dist)
        for dist in range(1, range_dist + 1):
            # Get the center point at this distance
            center_x = cx + dir_x * dist
            center_y = cy + dir_y * dist

            # Determine spread angle (wider at further distances)
            # 90° spread means 45° left/right from center
            spread = max(1, dist // 2)

            # Get tiles in the spread
            for spread_offset in range(-spread, spread + 1):
                tx = int(center_x + perp_x * spread_offset)
                ty = int(center_y + perp_y * spread_offset)

                # Check bounds
                if not (0 <= tx < DUNGEON_WIDTH and 0 <= ty < DUNGEON_HEIGHT):
                    continue

                # Check if blocked by wall
                if self.dungeon.is_terrain_blocked(tx, ty):
                    continue

                if (tx, ty) not in tiles:
                    tiles.append((tx, ty))

        return tiles

    def _spell_zap(self, tx: int, ty: int) -> bool:
        """Zap a target within 4 tiles. Dmg: 5 + Book-Smarts/2. Applies 1 Shocked stack."""
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("Zap: no line of sight.")
            return False
        target = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if target is None:
            self.messages.append("Zap: no enemy there.")
            return False
        dist = math.sqrt((tx - self.player.x) ** 2 + (ty - self.player.y) ** 2)
        if dist > 4.0:
            self.messages.append("Zap: target out of range (max 4 tiles).")
            return False
        bksmt = self.player_stats.effective_book_smarts
        damage = 5 + bksmt // 2
        target.take_damage(damage)
        effects.apply_effect(target, self, "shocked", duration=10, stacks=1, silent=True)
        shocked_eff = next(
            (e for e in target.status_effects if getattr(e, 'id', '') == 'shocked'), None
        )
        stacks = shocked_eff.stacks if shocked_eff else 1
        hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
        self.messages.append(
            f"Zap! {target.name} takes {damage} dmg! Shocked x{stacks}. ({hp_disp})"
        )
        if not target.alive:
            self.event_bus.emit("entity_died", entity=target, killer=self.player)
        return True

    def _spell_corn_dog(self, tx: int, ty: int) -> bool:
        """Corn Dog an adjacent enemy: 5 armor-piercing damage + stun 4 turns."""
        target = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if target is None:
            self.messages.append("Corn Dog: no enemy there.")
            return False
        dist = max(abs(tx - self.player.x), abs(ty - self.player.y))  # Chebyshev
        if dist > 1:
            self.messages.append("Corn Dog: must be adjacent to target.")
            return False
        target.take_damage(5)
        effects.apply_effect(target, self, "stun", duration=4, silent=True)
        hp_disp = f"{target.hp}/{target.max_hp}" if target.alive else "dead"
        self.messages.append(
            f"Corn Dog! {target.name} takes 5 dmg and is stunned for 4 turns! ({hp_disp})"
        )
        if not target.alive:
            self.event_bus.emit("entity_died", entity=target, killer=self.player)
        return True

    def _spell_pry(self, tx: int, ty: int) -> bool:
        """Pry an adjacent enemy: sets their defense to 0 for 10 turns."""
        target = next(
            (e for e in self.dungeon.get_entities_at(tx, ty)
             if e.entity_type == "monster" and e.alive),
            None,
        )
        if target is None:
            self.messages.append("Pry: no enemy there.")
            return False
        dist = max(abs(tx - self.player.x), abs(ty - self.player.y))
        if dist > 1:
            self.messages.append("Pry: must be adjacent to target.")
            return False
        effects.apply_effect(target, self, "cripple_armor", duration=10)
        self.messages.append(
            f"You pry open {target.name}'s defenses! Their armor is crippled for 10 turns!"
        )
        self.ability_cooldowns["pry"] = 50
        return True

    def _spell_lesser_cloudkill(self, tx: int, ty: int) -> bool:
        """Lesser Cloudkill 3×3 AoE (cannot include player). Damage + debuff."""
        px, py = self.player.x, self.player.y
        if abs(tx - px) <= 1 and abs(ty - py) <= 1:
            self.messages.append("Lesser Cloudkill: can't target an area that includes yourself!")
            return False
        bksmt = self.player_stats.effective_book_smarts
        swag = self.player_stats.effective_swagger
        damage = max(1, 25 - swag + bksmt // 2)
        tiles = self._get_lesser_cloudkill_affected_tiles(tx, ty)
        hit_count = 0
        hit_entities = []
        for x, y in tiles:
            for entity in self.dungeon.get_entities_at(x, y):
                if entity.entity_type == "monster" and entity.alive and entity not in hit_entities:
                    hit_entities.append(entity)
                    entity.take_damage(damage)
                    effects.apply_effect(entity, self, "lesser_cloudkill", duration=10, silent=True)
                    hit_count += 1
        self.messages.append(
            f"Lesser Cloudkill! {hit_count} enem{'y' if hit_count == 1 else 'ies'} hit "
            f"for {damage} dmg and are now Smelly."
        )
        for entity in hit_entities:
            if not entity.alive:
                self.event_bus.emit("entity_died", entity=entity, killer=self.player)
        return True

    def _get_lesser_cloudkill_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Return all non-terrain-blocked tiles in a 3×3 area centred on (tx, ty)."""
        tiles = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                x, y = tx + dx, ty + dy
                if 0 <= x < DUNGEON_WIDTH and 0 <= y < DUNGEON_HEIGHT:
                    if not self.dungeon.is_terrain_blocked(x, y):
                        tiles.append((x, y))
        return tiles

    def _get_wizard_bomb_bonus(self) -> int:
        """Return spell damage bonus from Wizard Mind-Bomb effect + total spell damage."""
        bonus = 0
        for effect in self.player.status_effects:
            if getattr(effect, 'id', '') == 'wizard_mind_bomb':
                bonus += self.player_stats.effective_book_smarts
        bonus += self.player_stats.total_spell_damage
        return bonus

    # ------------------------------------------------------------------
    # Spell targeting visualization
    # ------------------------------------------------------------------

    def get_spell_affected_tiles(self, spell_type: str, tx: int, ty: int) -> list[tuple[int, int]]:
        """Get list of tiles that will be affected by a spell at target location (tx, ty).
        Used for rendering visualization during targeting mode."""
        if spell_type == "breath_fire":
            return self._get_breath_fire_affected_tiles(tx, ty)
        elif spell_type == "ray_of_frost":
            return self._get_ray_of_frost_affected_tiles(tx, ty)
        elif spell_type == "chain_lightning":
            # Single target, but show it
            if any(e for e in self.dungeon.get_entities_at(tx, ty) if e.entity_type == "monster" and e.alive):
                return [(tx, ty)]
            return []
        elif spell_type in ("firebolt", "arcane_missile", "dimension_door"):
            # Single target spells
            if any(e for e in self.dungeon.get_entities_at(tx, ty) if e.entity_type == "monster" and e.alive):
                return [(tx, ty)]
            return []
        elif spell_type == "lesser_cloudkill":
            return self._get_lesser_cloudkill_affected_tiles(tx, ty)
        return []

    def get_targeting_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Get affected tiles for the current targeting mode, delegating to the ability definition."""
        defn = self._get_targeting_ability_def()
        if defn is not None:
            if defn.get_affected_tiles is not None:
                return defn.get_affected_tiles(self, tx, ty)
            # Single-target default: highlight tile if enemy is present
            if (self.dungeon.visible[ty, tx] and
                    any(e for e in self.dungeon.get_entities_at(tx, ty)
                        if e.entity_type == "monster" and e.alive)):
                return [(tx, ty)]
            return []
        # Fallback: item-triggered spells (Dosidos), dispatch by spell type string
        spell_type = self.targeting_spell.get("type", "") if self.targeting_spell else ""
        return self.get_spell_affected_tiles(spell_type, tx, ty)

    def _get_breath_fire_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Get all tiles in the breath fire cone."""
        dx = tx - self.player.x
        dy = ty - self.player.y
        if dx == 0 and dy == 0:
            return []

        dist = math.sqrt(dx*dx + dy*dy)
        center_dx = dx / dist
        center_dy = dy / dist

        return self._get_cone_tiles(self.player.x, self.player.y, center_dx, center_dy, range_dist=5)

    def _get_ray_of_frost_affected_tiles(self, tx: int, ty: int) -> list[tuple[int, int]]:
        """Get all tiles in the ray of frost line."""
        dx = tx - self.player.x
        dy = ty - self.player.y
        if dx == 0 and dy == 0:
            return []

        steps = max(abs(dx), abs(dy))
        unit_dx = (1 if dx > 0 else -1) if dx != 0 else 0
        unit_dy = (1 if dy > 0 else -1) if dy != 0 else 0

        return self._ray_tiles(self.player.x, self.player.y, unit_dx, unit_dy, max_dist=10)

    # ------------------------------------------------------------------
    # Ability system
    # ------------------------------------------------------------------

    def grant_ability(self, ability_id: str):
        """Grant the player an ability by ID. Silently ignored if already owned."""
        if ability_id not in ABILITY_REGISTRY:
            return
        if any(a.ability_id == ability_id for a in self.player_abilities):
            return
        defn = ABILITY_REGISTRY[ability_id]
        self.player_abilities.append(AbilityInstance(ability_id, defn))
        self.messages.append(f"Ability unlocked: {defn.name}!")

    def revoke_ability(self, ability_id: str):
        """Remove a granted ability. Does NOT reset its cooldown."""
        self.player_abilities = [a for a in self.player_abilities if a.ability_id != ability_id]

    def grant_ability_charges(self, ability_id: str, n: int, silent: bool = False) -> None:
        """Add n charges of a spell ability. Creates the ability slot if not yet owned."""
        defn = ABILITY_REGISTRY.get(ability_id)
        if defn is None:
            return
        inst = next((a for a in self.player_abilities if a.ability_id == ability_id), None)
        if inst is None:
            inst = AbilityInstance(ability_id, defn)
            if defn.charge_type != ChargeType.FLOOR_ONLY:
                inst.charges_remaining = 0  # start at 0; we'll add n below
            self.player_abilities.append(inst)
        if defn.charge_type == ChargeType.FLOOR_ONLY:
            inst.floor_charges_remaining += n
            display_count = inst.floor_charges_remaining
        else:
            inst.charges_remaining += n
            display_count = inst.charges_remaining
        if not silent:
            self.messages.append(
                f"+{n}x {defn.name} added to abilities! ({display_count} charges)"
            )

    def _consume_ability_charge(self) -> str | None:
        """Consume one charge from the ability that triggered the current targeting session.
        Returns the ability_id of the consumed ability, or None."""
        idx = self.targeting_ability_index
        ability_id = None
        if idx is not None and 0 <= idx < len(self.player_abilities):
            ability_id = self.player_abilities[idx].ability_id
            self.player_abilities[idx].consume()
        self.targeting_ability_index = None
        return ability_id

    def _action_toggle_abilities(self, _action):
        if self.menu_state == MenuState.NONE:
            self.menu_state = MenuState.ABILITIES
            self.abilities_cursor = 0
        elif self.menu_state == MenuState.ABILITIES:
            self.menu_state = MenuState.NONE
            self.selected_ability_index = None
        return False

    def _get_usable_abilities(self):
        """Build filtered list of usable abilities (same as render logic)."""
        usable = []
        for inst in self.player_abilities:
            if inst.can_use():
                usable.append(inst)
        return usable

    def _handle_abilities_menu_input(self, action):
        """Handle input while the abilities menu is open."""
        action_type = action.get("type")

        if action_type in ("close_menu", "toggle_abilities"):
            self.menu_state = MenuState.NONE
            self.selected_ability_index = None
            return False

        usable_abilities = self._get_usable_abilities()
        n = len(usable_abilities)

        # Arrow key cursor navigation
        if action_type == "move" and n > 0:
            dy = action.get("dy", 0)
            if dy != 0:
                self.abilities_cursor = (self.abilities_cursor + dy) % n
            return False

        # Enter key activates cursor selection
        if action_type == "confirm_target" and n > 0:
            if 0 <= self.abilities_cursor < n:
                target_ability = usable_abilities[self.abilities_cursor]
                actual_index = self.player_abilities.index(target_ability)
                return self._execute_ability(actual_index)
            return False

        # Number key shortcuts (existing behavior)
        if action_type == "select_action":
            idx = action["index"]
            if 0 <= idx < n:
                target_ability = usable_abilities[idx]
                actual_index = self.player_abilities.index(target_ability)
                return self._execute_ability(actual_index)
            return False

        return False

    def _execute_ability(self, index: int) -> bool:
        """Execute the ability at the given player_abilities index. Returns True if a turn is consumed."""
        if index < 0 or index >= len(self.player_abilities):
            return False

        inst = self.player_abilities[index]
        defn = ABILITY_REGISTRY.get(inst.ability_id)
        if defn is None:
            return False

        cd = self.ability_cooldowns.get(inst.ability_id, 0)
        if cd > 0:
            self.messages.append(f"{defn.name}: on cooldown ({cd} turns remaining)!")
            return False

        if not inst.can_use():
            self.messages.append(f"{defn.name}: no charges remaining!")
            return False

        self.menu_state = MenuState.NONE
        self.selected_ability_index = None
        # Track index so _execute_spell_at can consume the charge when the spell fires.
        self.targeting_ability_index = index

        # ADJACENT targeting: quick-select from adjacent enemies
        if defn.target_type == TargetType.ADJACENT:
            return self._enter_adjacent_ability_targeting(index, defn)

        # ADJACENT_TILE targeting: press a directional key to pick an adjacent tile
        if defn.target_type == TargetType.ADJACENT_TILE:
            self.menu_state = MenuState.ADJACENT_TILE_TARGETING
            self.messages.append(f"{defn.name}: choose a direction (arrow keys / numpad). [Esc] cancel.")
            return False

        result = defn.execute(self)
        if result:
            inst.consume()
            self.targeting_ability_index = None
            # Grant Blackkk Magic XP for spell abilities that executed immediately
            if defn.is_spell:
                self._gain_spell_xp(inst.ability_id)
        # result == False means targeting mode was entered; charge consumed later in _execute_spell_at.
        return result

    def _enter_adjacent_ability_targeting(self, index: int, defn) -> bool:
        """Enter quick-select targeting for an ADJACENT ability.
        Auto-fires if exactly one adjacent enemy; otherwise enters entity targeting."""
        targets = self._build_entity_target_list(reach=1)
        if not targets:
            self.messages.append(f"{defn.name}: no adjacent enemies!")
            self.targeting_ability_index = None
            return False
        if len(targets) == 1:
            # Auto-target the single adjacent enemy
            target = targets[0]
            return self._fire_adjacent_ability(target.x, target.y)
        # Multiple targets: enter entity targeting quick-select
        self.entity_target_list = targets
        self.entity_target_index = 0
        self.menu_state = MenuState.ENTITY_TARGETING
        return False

    def _fire_adjacent_ability(self, tx: int, ty: int) -> bool:
        """Execute the current adjacent ability at (tx, ty) and handle charge/cleanup."""
        index = self.targeting_ability_index
        if index is None or index >= len(self.player_abilities):
            return False
        inst = self.player_abilities[index]
        defn = ABILITY_REGISTRY.get(inst.ability_id)
        if defn is None or defn.execute_at is None:
            self.targeting_ability_index = None
            return False
        fired = defn.execute_at(self, tx, ty)
        if fired:
            inst.consume()
            self.targeting_ability_index = None
            if defn.is_spell:
                self._gain_spell_xp(inst.ability_id)
            return True
        self.targeting_ability_index = None
        return False

    def _handle_adjacent_tile_targeting_input(self, action) -> bool:
        """Handle input while in ADJACENT_TILE_TARGETING state.
        A directional key places the ability on the chosen adjacent tile; Esc cancels."""
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.targeting_ability_index = None
            return False

        if action_type == "move":
            dx = action.get("dx", 0)
            dy = action.get("dy", 0)
            if dx == 0 and dy == 0:
                return False
            tx = self.player.x + dx
            ty = self.player.y + dy
            # Validate: within bounds and not a wall
            if (tx < 0 or ty < 0 or tx >= self.dungeon.width or ty >= self.dungeon.height
                    or self.dungeon.is_wall(tx, ty)):
                self.messages.append("Fire!: can't place fire on a wall.")
                return False
            self.menu_state = MenuState.NONE
            fired = self._fire_adjacent_ability(tx, ty)
            if fired and self.running and self.player.alive:
                self.player.energy -= ENERGY_THRESHOLD
                self._run_energy_loop()
            return fired

        return False

    def _pickup_items_at(self, x: int, y: int):
        """Pick up items and cash at (x, y). Used by abilities that teleport the player."""
        for entity in list(self.dungeon.get_entities_at(x, y)):
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
                # Skip charged items from stacking — each is unique
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
                        return
                self.player.inventory.append(entity)
                self._sort_inventory()
                self.messages.append([
                    ("Picked up ", _C_MSG_PICKUP),
                    (entity.name, entity.color),
                ])
                return
            elif entity.entity_type == "cash":
                self.dungeon.remove_entity(entity)
                self.cash += entity.cash_amount
                self.messages.append(f"Picked up ${entity.cash_amount}!")
                return

    def _apply_item_effect_to_entity(self, effect_def, entity):
        """Apply an item throw_effect dict to any entity via the unified effects system."""
        effect_id = effect_def.get("effect_id") or effect_def.get("type", "stat_mod")
        duration = effect_def.get("duration", 10)
        amount = effect_def.get("amount", 0)
        stat = effect_def.get("stat")
        effects.apply_effect(entity, self, effect_id,
                             duration=duration, amount=amount, stat=stat)

    def _apply_strain_effect(self, entity, strain, roll, target="player"):
        """Resolve a strain table roll and apply the resulting effect to entity."""
        eff = get_strain_effect(strain, roll, target)
        if eff is None:
            self.messages.append("Nothing happens.")
            return

        is_player = entity == self.player
        eff_type = eff.get("type")

        if eff_type == "heal_percent":
            amount = int(entity.max_hp * eff["amount"])
            entity.heal(amount)
            if is_player:
                self.messages.append(
                    f"You feel much better! Healed {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
            else:
                self.messages.append(
                    f"{entity.name} recovers {amount} HP! ({entity.hp}/{entity.max_hp} HP)"
                )

        elif eff_type == "heal_flat":
            amount = eff["amount"]
            entity.heal(amount)
            if is_player:
                self.messages.append(
                    f"You feel better! Healed {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
            else:
                self.messages.append(
                    f"{entity.name} recovers {amount} HP! ({entity.hp}/{entity.max_hp} HP)"
                )

        elif eff_type == "damage_percent":
            amount = max(1, int(entity.max_hp * eff["amount"]))
            entity.take_damage(amount)
            if is_player:
                self.messages.append(
                    f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                self.messages.append(
                    f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)

        elif eff_type == "invulnerable":
            duration = eff.get("duration", 10)
            effects.apply_effect(entity, self, "invulnerable", duration=duration)
            if is_player:
                self.messages.append(
                    f"You feel untouchable! ({duration} turns)"
                )
            else:
                self.messages.append(
                    f"{entity.name} looks untouchable! ({duration} turns)"
                )

        elif eff_type == "cg_buff_debuff":
            duration = eff.get("duration", 10)
            effects.apply_effect(entity, self, "columbian_gold", duration=duration, silent=True)
            if is_player:
                self.messages.append([
                    ("You smoke the rush — stronger but ", (220, 220, 220)),
                    ("burning", (220, 100, 50)),
                    (" inside! (", (220, 220, 220)),
                    (str(duration), (220, 150, 50)),
                    (" turns)", (220, 220, 220)),
                ])
            else:
                self.messages.append(
                    f"{entity.name} looks stronger but pained! ({duration} turns)"
                )

        elif eff_type == "damage_flat":
            amount = eff["amount"]
            entity.take_damage(amount)
            if is_player:
                self.messages.append(
                    f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                self.messages.append(
                    f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)

        elif eff_type == "damage_stsmt":
            base = eff["base"]
            minimum = eff.get("min", 10)
            if is_player:
                stsmt = self.player_stats.effective_street_smarts
            else:
                stsmt = entity.base_stats.get("street_smarts", 1)
            amount = max(minimum, base - stsmt)
            entity.take_damage(amount)
            if is_player:
                self.messages.append(
                    f"That hit wrong. You lose {amount} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                self.messages.append(
                    f"{entity.name} coughs and takes {amount} damage! ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    self.event_bus.emit("entity_died", entity=entity, killer=None)

        elif eff_type == "remove_debuffs":
            removed = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') == 'debuff']
            entity.status_effects = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') != 'debuff']
            if is_player:
                if removed:
                    self.messages.append("The smoke clears your head — all debuffs removed!")
                else:
                    self.messages.append("The smoke clears your head.")

        elif eff_type == "remove_debuffs_zoned_out":
            entity.status_effects = [e for e in entity.status_effects if getattr(e, 'category', 'debuff') != 'debuff']
            effects.apply_effect(entity, self, "zoned_out", duration=10, silent=True)
            if is_player:
                self.messages.append("You seem out of it! (10 turns)")
            else:
                self.messages.append(f"{entity.name} seems out of it!")

        elif eff_type == "random_dot_debuff":
            duration_mode = eff.get("duration_mode")
            if duration_mode == "tlr":
                if is_player:
                    tlr = self.player_stats.effective_tolerance
                else:
                    bs = getattr(entity, 'base_stats', {})
                    tlr = bs.get("tolerance", 7) if isinstance(bs, dict) else 7
                duration = max(5, math.ceil(20 - tlr / 2))
            else:
                duration = eff.get("duration", 20)
            debuff_id = random.choice(["ignite", "chill", "shocked"])
            effects.apply_effect(entity, self, debuff_id, duration=duration, silent=True)
            _DOT_NAMES = {"ignite": ("Ignite", (255, 120, 40)),
                          "chill":  ("Chill",  (100, 180, 255)),
                          "shocked":("Shocked",(255, 220, 50))}
            dname, dcolor = _DOT_NAMES[debuff_id]
            if is_player:
                self.messages.append([
                    ("The smoke hits wrong — ", (220, 220, 220)),
                    (dname, dcolor),
                    (f" for {duration} turns!", (220, 220, 220)),
                ])
            else:
                self.messages.append(f"{entity.name} is afflicted with {dname}!")

        elif eff_type == "agent_orange_debuff":
            duration = eff.get("duration", 10)
            if is_player:
                if self.player_stats.effective_tolerance >= 12:
                    self.messages.append("The Agent Orange rolls right off you. (Tolerance max)")
                else:
                    effects.apply_effect(entity, self, "agent_orange", duration=duration, silent=True)
                    self.messages.append([
                        ("Agent Orange kicks in — ", (220, 120, 50)),
                        ("melee disabled", (255, 80, 20)),
                        (f" for {duration} turns!", (220, 120, 50)),
                    ])
            else:
                effects.apply_effect(entity, self, "agent_orange", duration=duration, silent=True)
                self.messages.append(f"{entity.name} is debilitated by Agent Orange!")

        # ── Jungle Boyz effects ──────────────────────────────────────────────
        elif eff_type == "jb_self_reflection":
            duration = eff.get("duration", 10)
            effects.apply_effect(entity, self, "minor_self_reflection", duration=duration, silent=True)
            self.messages.append([
                ("Jungle Boyz hits — ", (100, 200, 100)),
                ("Minor Self Reflection", (200, 100, 100)),
                (f" for {duration} turns!", (100, 200, 100)),
            ])

        elif eff_type == "jb_fiery_fists":
            duration = eff.get("duration", 10)
            effects.apply_effect(entity, self, "fiery_fists", duration=duration, silent=True)
            self.messages.append([
                ("Jungle Boyz burns — ", (100, 200, 100)),
                ("Fiery Fists", (255, 120, 40)),
                (f" for {duration} turns!", (100, 200, 100)),
            ])

        elif eff_type == "jb_monster_ignite":
            # 5 stacks of Ignite applied to monster
            ignite_eff = effects.apply_effect(entity, self, "ignite", duration=5, stacks=5, silent=True)
            stacks = ignite_eff.stacks if ignite_eff else 5
            self.messages.append(f"{entity.name} erupts in flames! (Ignite x{stacks})")

        elif eff_type == "jb_crippling_attacks":
            duration = eff.get("duration", 10)
            effects.apply_effect(entity, self, "crippling_attacks", duration=duration, silent=True)
            self.messages.append([
                ("Jungle Boyz crips — ", (100, 200, 100)),
                ("Crippling Attacks", (200, 220, 80)),
                (f" for {duration} turns!", (100, 200, 100)),
            ])

        elif eff_type == "jb_crippled":
            duration = eff.get("duration", 8)
            effects.apply_effect(entity, self, "crippled", duration=duration, silent=True)
            self.messages.append(f"{entity.name} is crippled! (deals half damage for {duration} turns)")

        elif eff_type == "jb_lifesteal":
            duration = eff.get("duration", 8)
            effects.apply_effect(entity, self, "lifesteal", duration=duration, silent=True)
            self.messages.append([
                ("Jungle Boyz flows — ", (100, 200, 100)),
                ("Lifesteal", (200, 80, 80)),
                (f" for {duration} turns!", (100, 200, 100)),
            ])

        elif eff_type == "jb_heal_damage":
            # Monster takes 20 damage, player heals 20
            entity.take_damage(20)
            self.player.heal(20)
            self.messages.append(
                f"{entity.name} takes 20 damage! You heal 20 HP. "
                f"({self.player.hp}/{self.player.max_hp} HP)"
            )
            if not entity.alive:
                self.event_bus.emit("entity_died", entity=entity, killer=self.player)

        elif eff_type == "jb_glory_fists":
            duration = eff.get("duration", 20)
            effects.apply_effect(entity, self, "glory_fists", duration=duration, silent=True)
            self.messages.append([
                ("Jungle Boyz blesses — ", (100, 200, 100)),
                ("Glory Fists", (220, 180, 255)),
                (f" for {duration} turns!", (100, 200, 100)),
            ])

        elif eff_type == "jb_soul_pair":
            effects.apply_effect(entity, self, "soul_pair", duration=9999, silent=True)
            self.messages.append([
                ("The smoke links your souls — ", (100, 200, 100)),
                ("Soul-Pair", (180, 100, 220)),
                (f" applied to {entity.name}!", (100, 200, 100)),
            ])

        elif eff_type == "blue_lobster":
            self._apply_blue_lobster_effect(entity, roll, is_player)

        elif eff_type == "none":
            if is_player:
                self.messages.append("You feel nothing.")
            else:
                self.messages.append(f"{entity.name} seems unaffected.")

        # ── Spell effects — grant ability charges for later use ──────────────
        elif eff_type == "dosidos_dimension_door":
            if is_player:
                self.grant_ability_charges("dimension_door", 1)
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        elif eff_type == "dosidos_chain_lightning":
            if is_player:
                # total_hits encodes how many charges to grant (4 or 2); spell always fires 4 bounces.
                charges = eff.get("total_hits", 4)
                self.grant_ability_charges("chain_lightning", charges)
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        elif eff_type == "dosidos_ray_of_frost":
            if is_player:
                self.grant_ability_charges("ray_of_frost", eff.get("count", 1))
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        elif eff_type == "dosidos_warp":
            if is_player:
                self.grant_ability_charges("warp", 1)
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        elif eff_type == "dosidos_firebolt":
            if is_player:
                self.grant_ability_charges("firebolt", eff.get("count", 1))
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        elif eff_type == "dosidos_arcane_missile":
            if is_player:
                self.grant_ability_charges("arcane_missile", eff.get("count", 1))
            else:
                self.messages.append(f"{entity.name} flickers briefly.")

        # ── Dosidos monster buff ─────────────────────────────────────────────
        elif eff_type == "dosidos_bksmt_buff":
            amount = eff.get("amount", 5)
            effects.apply_effect(entity, self, "bksmt_buff", amount=amount, duration=9999, silent=True)
            self.messages.append(
                f"{entity.name} gains +{amount} Book-Smarts from the Dosidos smoke!"
            )

    def _gain_smoking_xp(self, strain):
        """Award smoking skill XP based on the strain smoked."""
        from items import STRAIN_SMOKING_XP

        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get("Smoking")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        xp_amount = STRAIN_SMOKING_XP.get(strain, 5)  # Default 5 XP for unknown strains
        adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Smoking", adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        # Add unlock notification if this is the first XP
        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Smoking!", (255, 215, 0)),
            ])
        # Provide feedback to the player
        self.messages.append([
            ("Smoking skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _gain_rolling_xp(self, strain, is_grinding=False):
        """Award rolling skill XP based on the strain rolled/ground."""
        from items import STRAIN_ROLLING_XP

        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get("Rolling")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        xp_amount = STRAIN_ROLLING_XP.get(strain, 5)  # Default 5 XP for unknown strains
        adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Rolling", adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        # Add unlock notification if this is the first XP
        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Rolling!", (255, 215, 0)),
            ])
        # Provide feedback to the player
        action = "Grinding" if is_grinding else "Rolling"
        self.messages.append([
            ("Rolling skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _gain_munching_xp(self, food_id):
        """Award munching skill XP based on food eaten."""
        from items import FOOD_MUNCHING_XP

        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get("Munching")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        xp_amount = FOOD_MUNCHING_XP.get(food_id, 5)  # Default 5 XP for unknown foods
        adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Munching", adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        # Add unlock notification if this is the first XP
        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Munching!", (255, 215, 0)),
            ])
        # Provide feedback to the player
        self.messages.append([
            ("Munching skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _gain_deep_frying_xp(self, food_item_id):
        """Award deep-frying skill XP based on food fried."""
        from items import get_deep_frying_xp

        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get("Deep-Frying")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        xp_amount = get_deep_frying_xp(food_item_id)
        adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Deep-Frying", adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        # Add unlock notification if this is the first XP
        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Deep-Frying!", (255, 215, 0)),
            ])
        # Provide feedback to the player
        self.messages.append([
            ("Deep-Frying skill: +", (255, 140, 0)),
            (str(adjusted_xp), (255, 180, 100)),
            (" potential XP", (255, 140, 0)),
        ])

    def _gain_alcohol_xp(self, drink_id: str):
        """Award alcoholism and drinking skill XP based on drink type."""
        from items import ITEM_DEFS

        # Get value from item definition (for consistency)
        base_xp = ITEM_DEFS.get(drink_id, {}).get("value", 20)
        adjusted = round(base_xp * 2 * self.player_stats.xp_multiplier)
        bksmt = self.player_stats.effective_book_smarts

        # Award primary skill (Alcoholism)
        self.skills.gain_potential_exp("Alcoholism", adjusted, bksmt)
        # Award secondary skill (Drinking) at half rate
        self.skills.gain_potential_exp("Drinking", adjusted // 2, bksmt)

        # Feedback
        self.messages.append([
            ("Alcoholism skill: +", (100, 150, 200)),
            (str(adjusted), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _handle_alcohol(self, item, drink_id: str):
        """Handle alcohol consumable effects."""
        from abilities import ABILITY_REGISTRY

        # Gain skill XP first
        self._gain_alcohol_xp(drink_id)

        # Apply drink-specific effects
        if drink_id == "40oz":
            restore = self.player.max_armor // 2
            self.player.armor = min(self.player.armor + restore, self.player.max_armor)
            effects.apply_effect(self.player, self, "forty_oz")
            self.pending_hangover_stacks += 1

        elif drink_id == "fireball_shooter":
            self.grant_ability_charges("breath_fire", 3)
            self.pending_hangover_stacks += 2

        elif drink_id == "malt_liquor":
            effects.apply_effect(self.player, self, "malt_liquor")
            self.pending_hangover_stacks += 1

        elif drink_id == "wizard_mind_bomb":
            # Add 2 charges to all active magic spells
            for inst in self.player_abilities:
                defn = ABILITY_REGISTRY.get(inst.ability_id)
                if defn and defn.is_spell and inst.can_use():
                    inst.charges_remaining += 2
            effects.apply_effect(self.player, self, "wizard_mind_bomb")
            self.pending_hangover_stacks += 1

        elif drink_id == "homemade_hennessy":
            effects.apply_effect(self.player, self, "hennessy")
            self.pending_hangover_stacks += 1

        elif drink_id == "steel_reserve":
            heal = self.player.max_hp // 2
            self.player.heal(heal)
            self.player_stats.permanent_armor_bonus += 3
            self.player.max_armor = self._compute_player_max_armor()
            self.player.armor = min(self.player.armor + 3, self.player.max_armor)
            self.pending_hangover_stacks += 1

        self.messages.append([
            ("You drink the ", (200, 200, 200)), (item.name, item.color), (".", (200, 200, 200))
        ])

        # Alcoholism perks
        alc_level = self.skills.get("Alcoholism").level
        if alc_level >= 1:
            effects.apply_effect(self.player, self, "peace_of_mind", duration=20, stacks=1, silent=True)
            self.messages.append([("Peace of Mind (+1 StSmrt)", (100, 200, 255))])
        if alc_level >= 3:
            self.grant_ability_charges("throw_bottle", 1, silent=True)
            inst = next((a for a in self.player_abilities if a.ability_id == "throw_bottle"), None)
            count = inst.charges_remaining if inst else 0
            self.messages.append([("  +1 Throw Bottle charge", (180, 120, 60)), (f" ({count})", (150, 150, 150))])

        # Drinking perk 1: heal 10% max HP on any drink
        drink_level = self.skills.get("Drinking").level
        if drink_level >= 1:
            heal_amt = max(1, self.player.max_hp // 10)
            self.player.heal(heal_amt)
            self.messages.append([
                ("Liquid Bandage! ", (100, 200, 255)),
                (f"+{heal_amt} HP", (100, 255, 100)),
                (f" ({self.player.hp}/{self.player.max_hp})", (150, 150, 150)),
            ])

    def _gain_item_skill_xp(self, skill_name: str, item_id: str, silent: bool = False) -> None:
        """Award potential XP to a skill based on item value * skill multiplier."""
        from items import get_skill_xp

        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get(skill_name)
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        xp_amount = get_skill_xp(item_id, skill_name)
        adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            skill_name, adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        if not silent:
            # Add unlock notification if this is the first XP
            if was_locked:
                self.messages.append([
                    (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
                ])
            self.messages.append([
                (f"{skill_name} skill: +", (100, 150, 200)),
                (str(adjusted_xp), (150, 200, 255)),
                (" potential XP", (100, 150, 200)),
            ])

    def _sticky_fingers_check(self, item_id: str) -> None:
        """Perk 3 of Stealing — Sticky Fingers: chance to gain +1 StSmt on first pickup.

        Chance = item_value / 1000, capped at 50%.
        Only fires if the player has Stealing level >= 3.
        """
        stealing_skill = self.skills.get("Stealing")
        if not stealing_skill or stealing_skill.level < 3:
            return
        import random
        from items import get_item_value
        value = get_item_value(item_id)
        chance = min(0.5, value / 1000.0)
        if random.random() < chance:
            ps = self.player_stats
            ps.street_smarts += 1
            ps._base["street_smarts"] = ps.street_smarts
            self.messages.append([
                ("Sticky Fingers! ", (255, 200, 50)),
                ("+1 Street Smarts", (200, 230, 255)),
                (f" (now {ps.street_smarts})", (150, 150, 150)),
            ])

    def _gain_jaywalking_xp(self) -> None:
        """Award Jaywalking XP when the player enters a room for the first time."""
        from config import ZONE_JAYWALK_MULT
        zone = "crack_den"
        zone_mult = ZONE_JAYWALK_MULT.get(zone, 1.0)
        floor_mult = self.current_floor + 1
        base_xp = 10 * zone_mult * floor_mult
        adjusted_xp = round(base_xp * self.player_stats.xp_multiplier)

        skill = self.skills.get("Jaywalking")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        self.skills.gain_potential_exp(
            "Jaywalking", adjusted_xp,
            self.player_stats.effective_book_smarts
        )

        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Jaywalking!", (255, 215, 0)),
            ])
        self.messages.append([
            ("Jaywalking skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _gain_abandoning_xp(self) -> None:
        """Award Abandoning XP for items and cash left on the current floor."""
        from items import get_skill_xp

        total_xp = 0
        for entity in self.dungeon.entities:
            if entity.entity_type == "item":
                total_xp += get_skill_xp(entity.item_id, "Abandoning")
            elif entity.entity_type == "cash":
                total_xp += entity.cash_amount

        if total_xp <= 0:
            return

        skill = self.skills.get("Abandoning")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        adjusted_xp = round(total_xp * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            "Abandoning", adjusted_xp,
            self.player_stats.effective_book_smarts
        )

        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Abandoning!", (255, 215, 0)),
            ])
        self.messages.append([
            ("Abandoning skill: +", (100, 150, 200)),
            (str(adjusted_xp), (150, 200, 255)),
            (" potential XP", (100, 150, 200)),
        ])

    def _gain_melee_xp(self, skill_name: str, damage: int) -> None:
        """Award melee skill potential XP equal to damage dealt. Shows unlock notification only."""
        # Check if skill is newly unlocked (no XP before this call)
        skill = self.skills.get(skill_name)
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        zone = "crack_den"
        zone_dmg_mult = ZONE_DAMAGE_MULT.get(zone, 1.0)
        adjusted_xp = round(damage * zone_dmg_mult * self.player_stats.xp_multiplier)
        self.skills.gain_potential_exp(
            skill_name, adjusted_xp,
            self.player_stats.effective_book_smarts
        )
        # Show unlock notification (no regular message for melee XP)
        if was_locked:
            self.messages.append([
                (f"[NEW SKILL UNLOCKED] {skill_name}!", (255, 215, 0)),
            ])

    def _gain_spell_xp(self, ability_id: str) -> None:
        """Award Blackkk Magic XP when a spell is activated and its charge is consumed.

        XP calculation: 20 * floor_skill_mult * zone_skill_mult
        - floor_skill_mult: 1.0 + (current_floor * 0.5) [floors 1,2,3,4... get 1.0, 1.5, 2.0, 2.5...]
        - zone_skill_mult: From ZONE_BLACKK_MAGIC_MULT (crack_den = 1.0)
        """
        # Check if this is a spell
        defn = ABILITY_REGISTRY.get(ability_id)
        if defn is None or not defn.is_spell:
            return

        # Calculate floor multiplier: 1.0 + (current_floor * 0.5)
        # current_floor is 0-indexed, so floor 0 (1st floor) -> 1.0, floor 1 (2nd floor) -> 1.5, etc.
        floor_mult = 1.0 + (self.current_floor * 0.5)

        # Get zone multiplier
        zone = "crack_den"
        zone_mult = ZONE_BLACKK_MAGIC_MULT.get(zone, 1.0)

        # Calculate base XP: 20 * floor_skill_mult * zone_skill_mult
        base_xp = 20 * floor_mult * zone_mult
        adjusted_xp = round(base_xp * self.player_stats.xp_multiplier)

        # Check if skill is newly unlocked
        skill = self.skills.get("Blackkk Magic")
        was_locked = skill.potential_exp == 0 and skill.real_exp == 0 and skill.level == 0

        self.skills.gain_potential_exp(
            "Blackkk Magic", adjusted_xp,
            self.player_stats.effective_book_smarts
        )

        if was_locked:
            self.messages.append([
                ("[NEW SKILL UNLOCKED] Blackkk Magic!", (255, 215, 0)),
            ])

        # Arcane Intelligence perk (Blackkk Magic L3): 25% chance to gain 2 stacks
        if self.skills.get("Blackkk Magic").level >= 3 and random.random() < 0.25:
            effects.apply_effect(self.player, self, "arcane_intelligence", duration=20, stacks=2)
            ai_eff = next(
                (e for e in self.player.status_effects if getattr(e, "id", "") == "arcane_intelligence"),
                None,
            )
            total_stacks = ai_eff.stacks if ai_eff else 2
            self.messages.append(
                f"Arcane Intelligence! +2 spell dmg stacks ({total_stacks} total, "
                f"+{self.player_stats.total_spell_damage} bonus spell dmg)"
            )

    def _apply_blue_lobster_effect(self, entity, roll, is_player):
        """Apply Blue Lobster strain effect based on roll (1-100).

        Player effects: gain items, lose items
        Monster effects: drop cash, gain Acid Armor
        """
        from items import (
            ITEM_DEFS, get_random_ring_by_tags, get_random_chain, STRAINS
        )

        if is_player:
            # Player effects
            if 90 <= roll <= 100:
                # Add random tool
                candidates = [iid for iid, defn in ITEM_DEFS.items()
                             if defn.get("category") == "tool" and "crack_den" in defn.get("zones", [])]
                if candidates:
                    tool_id = random.choice(candidates)
                    self._add_item_to_inventory(tool_id, strain=None)
                    self.messages.append(f"Blue Lobster grants: {ITEM_DEFS[tool_id]['name']}!")
                else:
                    self.messages.append("The Blue Lobster would grant a tool, but found none!")

            elif 83 <= roll <= 89:
                # Add 1-3 random joints
                num_joints = random.randint(1, 3)
                strain = random.choice(STRAINS)
                for _ in range(num_joints):
                    self._add_item_to_inventory("joint", strain=strain)
                self.messages.append(f"Blue Lobster grants {num_joints} {strain} joint{'s' if num_joints > 1 else ''}!")

            elif 60 <= roll <= 82:
                # Add random ring (80% minor, 10% greater, 5% divine, 5% advanced)
                roll_ring = random.randint(1, 100)
                if roll_ring <= 80:
                    tags = ["minor"]
                elif roll_ring <= 90:
                    tags = ["greater"]
                elif roll_ring <= 95:
                    tags = ["divine"]
                else:
                    tags = ["advanced"]
                ring_id = get_random_ring_by_tags(tags)
                if ring_id:
                    self._add_item_to_inventory(ring_id, strain=None)
                    self.messages.append(f"Blue Lobster grants: {ITEM_DEFS[ring_id]['name']}!")
                else:
                    self.messages.append("The Blue Lobster would grant a ring, but found none!")

            elif 45 <= roll <= 59:
                # Add random neck (chain) directly
                neck_id = get_random_chain("crack_den")
                if neck_id:
                    self._add_item_to_inventory(neck_id, strain=None)
                    self.messages.append(f"Blue Lobster grants: {ITEM_DEFS[neck_id]['name']}!")
                else:
                    self.messages.append("The Blue Lobster would grant a neck, but found none!")

            elif 20 <= roll <= 44:
                # Add random weapon directly
                candidates = [
                    iid for iid, defn in ITEM_DEFS.items()
                    if defn.get("subcategory") == "weapon"
                    and "crack_den" in defn.get("zones", [])
                ]
                if candidates:
                    weapon_id = random.choice(candidates)
                    self._add_item_to_inventory(weapon_id, strain=None)
                    self.messages.append(f"Blue Lobster grants: {ITEM_DEFS[weapon_id]['name']}!")
                else:
                    self.messages.append("The Blue Lobster would grant a weapon, but found none!")

            elif 5 <= roll <= 19:
                # Delete random item from inventory
                if self.player.inventory:
                    idx = random.randint(0, len(self.player.inventory) - 1)
                    deleted = self.player.inventory.pop(idx)
                    self.messages.append(f"Blue Lobster curse: {deleted.name} deleted!")
                else:
                    self.messages.append("The Blue Lobster would curse an item, but you have none!")

            elif 1 <= roll <= 4:
                # Delete random equipped item
                equipped_items = []
                if self.equipment.get("weapon"):
                    equipped_items.append(("weapon", self.equipment["weapon"]))
                if self.equipment.get("neck"):
                    equipped_items.append(("neck", self.equipment["neck"]))
                for i, ring in enumerate(self.rings):
                    if ring:
                        equipped_items.append((f"ring_{i}", ring))
                if self.equipment.get("feet"):
                    equipped_items.append(("feet", self.equipment["feet"]))

                if equipped_items:
                    slot, item = random.choice(equipped_items)
                    # Unequip the item
                    if slot == "weapon":
                        self.equipment["weapon"] = None
                    elif slot == "neck":
                        self.equipment["neck"] = None
                    elif slot == "feet":
                        self.equipment["feet"] = None
                    elif slot.startswith("ring_"):
                        idx = int(slot.split("_")[1])
                        self.rings[idx] = None
                    self.messages.append(f"Blue Lobster curse: {item.name} unequipped!")
                else:
                    self.messages.append("The Blue Lobster would curse equipped items, but you have none!")

        else:
            # Monster effects
            if 90 <= roll <= 100:
                # Drop 100-50 cash
                cash = random.randint(50, 100)
                cash_entity = Entity(
                    x=entity.x, y=entity.y,
                    char="$", color=(255, 215, 0),
                    name=f"${cash}",
                    entity_type="cash",
                    blocks_movement=False,
                    cash_amount=cash,
                )
                self.dungeon.add_entity(cash_entity)
                self.messages.append(f"Blue Lobster grants ${cash}!")

            elif 83 <= roll <= 89:
                # Drop 75-50 cash
                cash = random.randint(50, 75)
                cash_entity = Entity(
                    x=entity.x, y=entity.y,
                    char="$", color=(255, 215, 0),
                    name=f"${cash}",
                    entity_type="cash",
                    blocks_movement=False,
                    cash_amount=cash,
                )
                self.dungeon.add_entity(cash_entity)
                self.messages.append(f"Blue Lobster grants ${cash}!")

            elif 60 <= roll <= 82:
                # Drop 60-30 cash
                cash = random.randint(30, 60)
                cash_entity = Entity(
                    x=entity.x, y=entity.y,
                    char="$", color=(255, 215, 0),
                    name=f"${cash}",
                    entity_type="cash",
                    blocks_movement=False,
                    cash_amount=cash,
                )
                self.dungeon.add_entity(cash_entity)
                self.messages.append(f"Blue Lobster grants ${cash}!")

            elif 45 <= roll <= 59:
                # Nothing
                self.messages.append(f"{entity.name} seems unaffected by the Blue Lobster.")

            elif 20 <= roll <= 44:
                # Nothing
                self.messages.append(f"{entity.name} seems unaffected by the Blue Lobster.")

            elif 5 <= roll <= 19:
                # Gain Acid Armor (5% break chance, 10 turns)
                effects.apply_effect(entity, self, "acid_armor", duration=10, break_chance=0.05, silent=True)
                self.messages.append(f"{entity.name} gains Acid Armor!")

            elif 1 <= roll <= 4:
                # Gain Acid Armor (10% break chance, 20 turns)
                effects.apply_effect(entity, self, "acid_armor", duration=20, break_chance=0.10, silent=True)
                self.messages.append(f"{entity.name} gains Acid Armor!")

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
