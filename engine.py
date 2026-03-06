"""
Game engine and turn management.
"""

import math
import random
from collections import deque

from config import (
    BASE_HP, BASE_POWER, BASE_DEFENSE,
    DUNGEON_WIDTH, DUNGEON_HEIGHT, MAX_MESSAGES, LOG_HISTORY_SIZE,
    MIN_DAMAGE, UNARMED_STR_BASE, EQUIPMENT_SLOTS, RING_SLOTS, FOV_RADIUS,
    ENERGY_THRESHOLD, PLAYER_BASE_SPEED,
)
from dungeon import Dungeon
from entity import Entity
from skills import Skills
from stats import PlayerStats
from items import get_item_def, find_recipe, get_actions, create_item_entity, get_craft_result_strain, is_stackable, build_inventory_display_name, get_strain_effect, get_random_ring_by_tags
from ai import do_ai_turn, prepare_ai_tick
from event_bus import EventBus
import effects
from menu_state import MenuState
from abilities import AbilityDef, AbilityInstance, ABILITY_REGISTRY

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


class GameEngine:
    """Main game logic and state management."""

    def __init__(self):
        # --- Event bus ---
        self.event_bus = EventBus()
        self._register_events()

        # --- Floor management ---
        self.current_floor = 0
        self.total_floors = 4
        self.dungeons: dict[int, Dungeon] = {}

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

        self.dungeon.spawn_entities(self.player, floor_num=0)
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)

        # --- Core state ---
        self.turn = 0
        self.kills = 0
        self.running = True
        self.game_over = False
        self.skills = Skills()
        self.messages: deque = deque(maxlen=LOG_HISTORY_SIZE)
        self.log_scroll: int = 0   # 0 = newest; higher = further back in history
        self.cash = 0
        self.destroyed_items: list[dict] = []  # {"name": str, "quantity": int}

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

        # --- Ring replacement state ---
        self.pending_ring_item_index: int | None = None  # inventory index of ring being equipped
        self.ring_replace_cursor: int = 0  # which equipped ring to replace (0-9)

        # --- Targeting mode state ---
        self.targeting_item_index: int | None = None
        self.targeting_cursor: list[int] = [0, 0]
        self.targeting_spell: dict | None = None
        self.targeting_ability_index: int | None = None  # ability whose charge to consume on fire

        # --- Ability system ---
        # Players start with no abilities; abilities are granted by items and skills.
        self.player_abilities: list[AbilityInstance] = []
        self.selected_ability_index: int | None = None

        # --- Action dispatch tables ---
        self._gameplay_handlers = {
            "move": self._action_move,
            "wait": self._action_wait,
            "toggle_skills": self._action_toggle_skills,
            "open_char_sheet": self._action_toggle_char_sheet,
            "open_equipment": self._action_open_equipment,
            "open_log": self._action_open_log,
            "open_bestiary": self._action_open_bestiary,
            "toggle_abilities": self._action_toggle_abilities,
            "select_item": self._action_select_item,
            "close_menu": self._action_close_menu,
            "quit": self._action_quit,
            "descend_stairs": self._action_descend_stairs,
        }

        self._menu_handlers = {
            MenuState.EQUIPMENT: self._handle_equipment_input,
            MenuState.ITEM_MENU: self._handle_item_menu_input,
            MenuState.COMBINE_SELECT: self._handle_combine_input,
            MenuState.LOG: self._handle_log_input,
            MenuState.DESTROY_CONFIRM: self._handle_destroy_confirm_input,
            MenuState.TARGETING: self._handle_targeting_input,
            MenuState.ABILITIES: self._handle_abilities_menu_input,
            MenuState.RING_REPLACE: self._handle_ring_replace_input,
        }

    # ------------------------------------------------------------------
    # Event bus wiring
    # ------------------------------------------------------------------

    def _register_events(self):
        self.event_bus.on("entity_died", self._on_entity_died)
        self.event_bus.on("entity_died", self._on_kill_cash_drop)

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
            self.messages.append("You died!")

    def _on_kill_cash_drop(self, entity, killer=None):
        """Award cash from killed monsters."""
        if entity.entity_type != "monster":
            return
        cash = getattr(entity, "cash_drop", 0)
        if cash > 0:
            self.cash += cash
            self.messages.append(f"[+${cash}]")

    # ------------------------------------------------------------------
    # Main action dispatch
    # ------------------------------------------------------------------

    def process_action(self, action):
        """Process player action and update game state. Returns True if a turn was consumed."""
        if not action:
            return False

        action_type = action.get("type")

        # --- Skills / Char sheet toggles (block other menus) ---
        if action_type == "toggle_skills":
            return self._action_toggle_skills(action)

        if self.menu_state == MenuState.SKILLS:
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

        # --- Convert Y/N item selections to confirmation actions in confirmation dialogs ---
        if self.menu_state == MenuState.DESTROY_CONFIRM and action_type == "select_item":
            index = action.get("index")
            # In INVENTORY_KEYS "bdfghijklmnopqrtuvwxyz": 'n' is index 10, 'y' is index 20
            if index == 20:  # 'y'
                action = {"type": "confirm_yes"}
            elif index == 10:  # 'n'
                action = {"type": "confirm_no"}
            action_type = action.get("type")

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
                return handler(action)
            return False

        # --- Normal gameplay dispatch ---
        handler = self._gameplay_handlers.get(action_type)
        if not handler:
            return False

        result = handler(action)

        # Energy tick: player spends energy, then run ticks until player can act again
        if result and self.running and self.player.alive:
            self.player.energy -= ENERGY_THRESHOLD
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
        while self.player.energy < ENERGY_THRESHOLD:
            if not self.player.alive or not self.running:
                break

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
                entity.energy += gain

            # 2. Process all monsters that have enough energy, highest energy first
            acting = sorted(
                [m for m in monsters if m.alive and m.energy >= ENERGY_THRESHOLD],
                key=lambda m: -m.energy,
            )
            for monster in acting:
                while monster.alive and monster.energy >= ENERGY_THRESHOLD:
                    do_ai_turn(monster, self.player, self.dungeon, self, **tick_data)
                    monster.energy -= ENERGY_THRESHOLD

            # 3. Tick status effects once per energy cycle
            self.turn += 1
            effects.tick_all_effects(self.player, self)
            for monster in monsters:
                if monster.alive:
                    effects.tick_all_effects(monster, self)

            if not self.player.alive:
                self.game_over = True
                return

    # ------------------------------------------------------------------
    # Gameplay action handlers
    # ------------------------------------------------------------------

    def _action_move(self, action):
        self.handle_move(action["dx"], action["dy"])
        return True

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
        elif self.menu_state == MenuState.SKILLS:
            self.menu_state = MenuState.NONE
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
        for entity in self.dungeon.get_entities_at(self.player.x, self.player.y):
            if entity.entity_type == "staircase":
                return self._descend()
        self.messages.append("There are no stairs here. (Stand on > to descend)")
        return False

    def _descend(self):
        """Move player down to the next floor."""
        next_floor = self.current_floor + 1
        if next_floor >= self.total_floors:
            self.messages.append("This is the deepest floor of this zone.")
            return False

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
            new_dungeon.spawn_entities(self.player, floor_num=next_floor)
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
        self.dungeon.female_kill_happened = False
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)
        self.player.energy = ENERGY_THRESHOLD  # player acts first on new floor

        # Reset per-floor ability charges
        for inst in self.player_abilities:
            defn = ABILITY_REGISTRY.get(inst.ability_id)
            if defn:
                inst.reset_floor(defn)

        # Refill armor at floor start
        self.player.armor = self.player.max_armor

        self.messages.append(
            f"You descend deeper into the crack den... (Floor {self.current_floor + 1}/{self.total_floors})"
        )
        return True

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def handle_move(self, dx, dy):
        """Handle player movement using spatial index."""
        new_x = self.player.x + dx
        new_y = self.player.y + dy

        # Check for blocking entity (wall, monster, etc.)
        if self.dungeon.is_blocked(new_x, new_y):
            target = self.dungeon.get_blocking_entity_at(new_x, new_y)
            if target and target.entity_type == "monster":
                self.handle_attack(self.player, target)
            return

        # Failsafe: explicitly check that no living monster occupies the destination
        # This prevents any edge cases where blocks_movement might be incorrectly set
        for entity in self.dungeon.get_entities_at(new_x, new_y):
            if entity.entity_type == "monster" and getattr(entity, "alive", True):
                self.handle_attack(self.player, entity)
                return

        # Move player through spatial index
        self.dungeon.move_entity(self.player, new_x, new_y)

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
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)

        # Check for pickups at new position
        for entity in list(self.dungeon.get_entities_at(self.player.x, self.player.y)):
            if entity == self.player:
                continue
            if entity.entity_type == "item":
                self.dungeon.remove_entity(entity)
                # Try to merge into an existing stack
                if is_stackable(entity.item_id):
                    existing = next(
                        (i for i in self.player.inventory
                         if i.item_id == entity.item_id and i.strain == entity.strain),
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

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def _compute_str_bonus(self, weapon_item):
        """Return the STR damage bonus for the given weapon (or unarmed)."""
        strength = self.player_stats.effective_strength
        if weapon_item is None:
            return strength - UNARMED_STR_BASE
        defn = get_item_def(weapon_item.item_id)
        scaling = defn.get("str_scaling")
        if not scaling:
            return 0
        if scaling["type"] == "tiered":
            req = defn.get("str_req", 1)
            divisor = scaling.get("divisor", 2)
            return (strength - req) // divisor
        if scaling["type"] == "linear":
            base = scaling.get("base", UNARMED_STR_BASE)
            return strength - base
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
        # Add temporary armor bonuses from effects
        max_armor += getattr(self.player_stats, 'temporary_armor_bonus', 0)
        return max_armor

    def _apply_damage_modifiers(self, damage: int, defender) -> int:
        """Apply modify_incoming_damage hooks from defender's status effects."""
        for eff in defender.status_effects:
            damage = eff.modify_incoming_damage(damage, defender)
        return damage

    def handle_attack(self, attacker, defender):
        """Handle melee attack with equipment bonuses and player stat effects."""
        # Agent Orange: attacker cannot deal melee damage
        if any(getattr(e, 'id', None) == 'agent_orange' for e in attacker.status_effects):
            if attacker == self.player:
                self.messages.append("Agent Orange — you can't deal melee damage!")
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

        damage = max(MIN_DAMAGE, atk_power - def_defense)
        if is_crit:
            damage *= 2
        damage = self._apply_damage_modifiers(damage, defender)
        defender.take_damage(damage)

        # On-hit effects: notify player's active buffs/debuffs
        if attacker == self.player:
            for eff in list(self.player.status_effects):
                eff.on_player_melee_hit(self, defender, damage)

        # Passive monsters become provoked when hit
        if hasattr(defender, "provoked") and not defender.provoked:
            defender.provoked = True

        crit_str = " CRITICAL!" if is_crit else ""
        msg = f"{attacker.name} deals {damage} damage to {defender.name}{crit_str}"

        if not defender.alive:
            msg += f" ({defender.name} dies)"
            self.messages.append(msg)
            self.event_bus.emit("entity_died", entity=defender, killer=attacker)
        else:
            self.messages.append(msg)

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
                damage = self._apply_damage_modifiers(damage, player)
                if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
                    damage = max(MIN_DAMAGE, damage // 2)
                player.take_damage(damage)
                self.messages.append(
                    f"{monster.name} hits you with {sa['name']} for {damage} damage!"
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

                hit_eff = sa.get("on_hit_effect")
                if hit_eff:
                    self._apply_monster_hit_effect(hit_eff)
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
        damage = self._apply_damage_modifiers(damage, player)
        if any(getattr(e, 'id', None) == 'crippled' for e in monster.status_effects):
            damage = max(MIN_DAMAGE, damage // 2)
        player.take_damage(damage)
        self.messages.append(f"{monster.name} hits you for {damage} damage!")
        if any(getattr(e, 'id', None) == 'soul_pair' for e in monster.status_effects):
            monster.take_damage(damage)
            self.messages.append(
                f"Soul-Pair: {monster.name} shares your pain! (-{damage} HP)"
            )
            if not monster.alive:
                self.event_bus.emit("entity_died", entity=monster, killer=player)

        for hit_eff in monster.on_hit_effects:
            if random.random() < hit_eff["chance"]:
                self._apply_monster_hit_effect(hit_eff)

        if not player.alive:
            self.event_bus.emit("entity_died", entity=player, killer=monster)

    def _apply_monster_hit_effect(self, effect):
        """Apply a status debuff from a monster hit to the player."""
        effect_id = effect["kind"]
        duration = effect["duration"]
        amount = effect.get("amount", 0)
        effects.apply_effect(self.player, self, effect_id, duration=duration, amount=amount)

    # ------------------------------------------------------------------
    # Item menu
    # ------------------------------------------------------------------

    def _open_item_menu(self, index):
        item = self.player.inventory[index]
        self.selected_item_index = index
        self.selected_item_actions = get_actions(item.item_id)
        self.menu_state = MenuState.ITEM_MENU

    def _handle_item_menu_input(self, action):
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        if action_type == "select_action":
            idx = action["index"]
            if 0 <= idx < len(self.selected_item_actions):
                return self._execute_item_action(self.selected_item_actions[idx])
            return False

        return False

    def _execute_item_action(self, action_name):
        item = self.player.inventory[self.selected_item_index]
        defn = get_item_def(item.item_id)

        if action_name == "Equip":
            self._equip_item(self.selected_item_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        elif action_name == "Drop":
            self._drop_item(self.selected_item_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        elif action_name == "Use on...":
            self.menu_state = MenuState.COMBINE_SELECT
            return False

        elif action_name == defn.get("use_verb"):
            self._use_item(self.selected_item_index)
            self.selected_item_index = None
            if self.menu_state != MenuState.TARGETING:
                self.menu_state = MenuState.NONE
            return False

        elif action_name == defn.get("throw_verb"):
            self._enter_targeting(self.selected_item_index)
            return False

        elif action_name == "Destroy":
            self.menu_state = MenuState.DESTROY_CONFIRM
            return False

        return False

    # ------------------------------------------------------------------
    # Equipment
    # ------------------------------------------------------------------

    def _equip_item(self, index):
        item = self.player.inventory[index]
        defn = get_item_def(item.item_id)
        slot = defn["equip_slot"]
        if slot is None:
            return

        str_req = defn.get("str_req")
        if str_req is not None and self.player_stats.effective_strength < str_req:
            self.messages.append(
                f"Need {str_req} STR to equip {item.name}! "
                f"(you have {self.player_stats.effective_strength})"
            )
            return

        if slot == "weapon":
            if self.equipment["weapon"] is not None:
                swapped = self.equipment["weapon"]
                self.player.inventory.append(swapped)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
            self.equipment["weapon"] = self.player.inventory.pop(index)
        elif slot == "neck":
            if self.neck is not None:
                swapped = self.neck
                self.player.inventory.append(swapped)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
            self.neck = self.player.inventory.pop(index)
        elif slot == "feet":
            if self.feet is not None:
                swapped = self.feet
                self.player.inventory.append(swapped)
                self._sort_inventory()
                self.messages.append([("Unequipped ", _C_MSG_NEUTRAL), (swapped.name, swapped.color)])
            self.feet = self.player.inventory.pop(index)
        elif slot == "ring":
            empty = next((i for i, r in enumerate(self.rings) if r is None), None)
            if empty is None:
                # All ring slots are full; open menu to select which ring to replace
                self.pending_ring_item_index = index
                self.ring_replace_cursor = 0
                self.menu_state = MenuState.RING_REPLACE
                return
            self.rings[empty] = self.player.inventory.pop(index)
        else:
            return

        self._refresh_ring_stat_bonuses()
        self.messages.append([("Equipped ", _C_MSG_NEUTRAL), (item.name, item.color)])

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
            if self.equipment_cursor < len(occupied):
                slot_id, item = occupied[self.equipment_cursor]
                if slot_id == "weapon":
                    self.equipment["weapon"] = None
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
            self._refresh_ring_stat_bonuses()
            return False

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

        if effect_type == "message":
            text = effect["text"].format(name=item.name)
            self.messages.append(text)

        elif effect_type == "heal":
            base_amount = effect.get("amount", 5)
            amount = round(base_amount * self.player_stats.drug_multiplier)
            self.player.heal(amount)
            self.messages.append([
                ("Used ", _C_MSG_USE), (item.name, item.color),
                (f". Healed {amount} HP.", _C_MSG_USE),
            ])

        elif effect_type == "strain_roll":
            if any(getattr(e, 'id', None) == 'chill' for e in self.player.status_effects):
                self.messages.append("You're too chilled out to smoke right now!")
                return
            roll = random.randint(1, 100)
            self.messages.append([
                ("You smoke the ", _C_MSG_USE), (item.name, item.color),
                (f". (Roll: {roll})", _C_MSG_USE),
            ])
            self._apply_strain_effect(self.player, item.strain, roll, "player")

        elif effect_type == "stat_boost" or "effect_id" in effect:
            amount = effect.get("amount", 0)
            stat = effect.get("stat")
            duration = effect.get("duration", 10)
            effect_id = effect.get("effect_id", "stat_mod")
            self.messages.append([("Used ", _C_MSG_USE), (item.name, item.color), (".", _C_MSG_USE)])
            effects.apply_effect(self.player, self, effect_id,
                                 duration=duration, amount=amount, stat=stat)

        # Skill XP
        skill_xp = effect.get("skill_xp")
        if skill_xp:
            for skill_name, xp_amount in skill_xp.items():
                adjusted_xp = round(xp_amount * self.player_stats.xp_multiplier)
                gained = self.skills.add_xp(skill_name, adjusted_xp)
                if gained:
                    self.messages.append(f"{skill_name} leveled up!")

        if effect.get("consumed", True):
            # Use identity search instead of index — apply_effect may have mutated the inventory
            item.quantity -= 1
            if item.quantity <= 0:
                for i, x in enumerate(self.player.inventory):
                    if x is item:
                        self.player.inventory.pop(i)
                        break

    # ------------------------------------------------------------------
    # Destroy
    # ------------------------------------------------------------------

    def _handle_destroy_confirm_input(self, action):
        action_type = action.get("type")
        if action_type == "confirm_yes":
            self._destroy_item(self.selected_item_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
        elif action_type in ("confirm_no", "close_menu"):
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
        return False

    def _destroy_item(self, index):
        item = self.player.inventory[index]
        qty = getattr(item, "quantity", 1)
        self.destroyed_items.append({"name": item.name, "quantity": qty})
        self.player.inventory.pop(index)
        self.messages.append([
            ("Destroyed ", (200, 80, 80)),
            (item.name, item.color),
            (".", (200, 80, 80)),
        ])

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
            return False

        if action_type == "confirm_target":
            # Enter key to confirm selection
            self._replace_ring_at_slot(self.ring_replace_cursor)
            self.menu_state = MenuState.NONE
            self.pending_ring_item_index = None
            return False

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

    def _handle_combine_input(self, action):
        action_type = action.get("type")

        if action_type == "close_menu":
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        if action_type == "select_item":
            target_index = action["index"]
            if target_index == self.selected_item_index:
                return False
            if 0 <= target_index < len(self.player.inventory):
                self._try_combine(self.selected_item_index, target_index)
            self.menu_state = MenuState.NONE
            self.selected_item_index = None
            return False

        return False

    def _try_combine(self, index_a, index_b):
        item_a = self.player.inventory[index_a]
        item_b = self.player.inventory[index_b]
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

        # Try to merge result into an existing stack
        if is_stackable(result_id):
            existing = next(
                (i for i in self.player.inventory
                 if i.item_id == result_id and i.strain == result_strain),
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
                return

        kwargs = create_item_entity(result_id, 0, 0, strain=result_strain)
        result_item = Entity(**kwargs)
        self.player.inventory.append(result_item)
        self._sort_inventory()
        self.messages.append([
            ("Combined into ", _C_MSG_NEUTRAL),
            (result_item.name, result_item.color),
            ("!", _C_MSG_NEUTRAL),
        ])

    # ------------------------------------------------------------------
    # Targeting mode
    # ------------------------------------------------------------------

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

    def _enter_spell_targeting(self, spell_dict: dict) -> None:
        """Enter cursor targeting mode for a Dosidos spell cast."""
        self.targeting_spell = dict(spell_dict)
        self.targeting_item_index = None
        self.targeting_cursor = [self.player.x, self.player.y]
        self.menu_state = MenuState.TARGETING

    def _execute_spell_at(self, tx: int, ty: int) -> bool:
        """Execute the pending Dosidos spell at (tx, ty).
        Returns True to close targeting (final cast done), False to keep it open."""
        spell = self.targeting_spell
        spell_type = spell["type"]

        if spell_type == "dimension_door":
            if self._spell_dimension_door(tx, ty):
                self._consume_ability_charge()
                self.menu_state = MenuState.NONE
                self.targeting_spell = None
            return False

        elif spell_type == "chain_lightning":
            if self._spell_chain_lightning(tx, ty, spell.get("total_hits", 4)):
                self._consume_ability_charge()
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
            self._consume_ability_charge()
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
                self._consume_ability_charge()
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
                self._consume_ability_charge()
                count = spell.get("count", 1) - 1
                if count > 0:
                    spell["count"] = count
                    self.targeting_cursor = [self.player.x, self.player.y]
                    self.messages.append(f"Magic Missile! {count} shot(s) remaining — pick next target.")
                else:
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
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)
        self.messages.append(f"Dimension Door! You blink to ({tx}, {ty}).")
        self._pickup_items_at(tx, ty)
        return True

    def _spell_chain_lightning(self, tx: int, ty: int, total_hits: int) -> bool:
        """Chain lightning hitting total_hits times, bouncing to the nearest monster each time.
        Returns True if the spell fired, False if the target was invalid."""
        stsmt = self.player_stats.effective_street_smarts
        tlr   = self.player_stats.effective_tolerance
        damage = 5 + stsmt + tlr

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
                min_d = min(self._dist_sq(last_x, last_y, e.x, e.y) for e in living)
                nearest = [e for e in living
                           if self._dist_sq(last_x, last_y, e.x, e.y) == min_d]
                target = random.choice(nearest)
        return True

    def _spell_ray_of_frost(self, dx: int, dy: int) -> None:
        """Fire a Ray of Frost in direction (dx, dy). Deals 12+BKSMT damage to all monsters
        in a 10-tile line; stops at walls."""
        bksmt  = self.player_stats.effective_book_smarts
        damage = 12 + bksmt
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
        self.dungeon.compute_fov(self.player.x, self.player.y, self.fov_radius)
        self.messages.append("Warp! You vanish and reappear elsewhere on the floor.")
        self._pickup_items_at(tx, ty)

    def _spell_firebolt(self, tx: int, ty: int) -> bool:
        """Fire a Firebolt toward (tx, ty). Blocked by walls and entities. Returns True on hit."""
        bksmt  = self.player_stats.effective_book_smarts
        damage = 10 + bksmt
        if not self.dungeon.visible[ty, tx]:
            self.messages.append("Firebolt: no line of sight to that tile.")
            return False
        hit = self._trace_projectile(self.player.x, self.player.y, tx, ty)
        if hit is None:
            self.messages.append("Firebolt fizzles — no target in path!")
            return False
        hit.take_damage(damage)
        effects.apply_effect(hit, self, "ignite", duration=10, stacks=1, silent=True)
        ignite_eff = next(
            (e for e in hit.status_effects if getattr(e, 'id', '') == 'ignite'), None
        )
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
        damage = math.ceil(8 + bksmt / 2)
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

    def grant_ability_charges(self, ability_id: str, n: int) -> None:
        """Add n charges of a spell ability. Creates the ability slot if not yet owned."""
        defn = ABILITY_REGISTRY.get(ability_id)
        if defn is None:
            return
        inst = next((a for a in self.player_abilities if a.ability_id == ability_id), None)
        if inst is None:
            inst = AbilityInstance(ability_id, defn)
            inst.charges_remaining = 0  # start at 0; we'll add n below
            self.player_abilities.append(inst)
        inst.charges_remaining += n
        self.messages.append(
            f"+{n}x {defn.name} added to abilities! ({inst.charges_remaining} charges)"
        )

    def _consume_ability_charge(self) -> None:
        """Consume one charge from the ability that triggered the current targeting session."""
        idx = self.targeting_ability_index
        if idx is not None and 0 <= idx < len(self.player_abilities):
            self.player_abilities[idx].consume()
        self.targeting_ability_index = None

    def _action_toggle_abilities(self, _action):
        if self.menu_state == MenuState.NONE:
            self.menu_state = MenuState.ABILITIES
        elif self.menu_state == MenuState.ABILITIES:
            self.menu_state = MenuState.NONE
            self.selected_ability_index = None
        return False

    def _handle_abilities_menu_input(self, action):
        """Handle input while the abilities menu is open."""
        action_type = action.get("type")

        if action_type in ("close_menu", "toggle_abilities"):
            self.menu_state = MenuState.NONE
            self.selected_ability_index = None
            return False

        if action_type == "select_action":
            idx = action["index"]
            if 0 <= idx < len(self.player_abilities):
                return self._execute_ability(idx)
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

        if not inst.can_use():
            self.messages.append(f"{defn.name}: no charges remaining!")
            return False

        self.menu_state = MenuState.NONE
        self.selected_ability_index = None
        # Track index so _execute_spell_at can consume the charge when the spell fires.
        self.targeting_ability_index = index

        result = defn.execute(self)
        if result:
            inst.consume()
            self.targeting_ability_index = None
        # result == False means targeting mode was entered; charge consumed later in _execute_spell_at.
        return result

    def _pickup_items_at(self, x: int, y: int):
        """Pick up items and cash at (x, y). Used by abilities that teleport the player."""
        for entity in list(self.dungeon.get_entities_at(x, y)):
            if entity == self.player:
                continue
            if entity.entity_type == "item":
                self.dungeon.remove_entity(entity)
                if is_stackable(entity.item_id):
                    existing = next(
                        (i for i in self.player.inventory
                         if i.item_id == entity.item_id and i.strain == entity.strain),
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
                self.messages.append([
                    ("You float above it all — ", (220, 220, 220)),
                    ("Zoned Out", (100, 220, 255)),
                    (" for 10 turns!", (220, 220, 220)),
                ])
            else:
                self.messages.append(f"{entity.name} looks untouchable!")

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
            # 5 stacks of Ignite (5 turns) applied to monster
            for _ in range(5):
                effects.apply_effect(entity, self, "ignite", duration=5, stacks=1, silent=True)
            ignite_eff = next((e for e in entity.status_effects if getattr(e, 'id', '') == 'ignite'), None)
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
