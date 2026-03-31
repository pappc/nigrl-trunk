"""
Entity class for all game objects (player, monsters, items).
"""

import uuid
from config import BASE_HP, BASE_POWER, BASE_DEFENSE


class Entity:
    """Represents any actor or object in the game."""

    _on_damage_callback = None   # set by engine at init
    _on_heal_callback = None     # set by engine at init

    def __init__(
        self,
        x,
        y,
        char,
        color,
        name="entity",
        entity_type="monster",
        blocks_movement=False,
        hp=BASE_HP,
        power=BASE_POWER,
        defense=BASE_DEFENSE,
        item_id=None,
        cash_amount=0,
        quantity=1,             # Stack size (stackable items only; always 1 for non-stackable)
        strain=None,            # Marijuana strain (e.g., "OG Kush") for cannabis items
        prefix=None,            # Active food prefix ("greasy", etc.); None = no prefix
        charges=None,           # Remaining uses for prefixed food; None = no charge system
        max_charges=None,       # Max uses at prefix-apply time
        current_ammo=0,         # Rounds currently loaded in this gun (0 for non-guns)
        mag_size=0,             # Magazine capacity (0 for non-guns)
        # --- Enemy fields (None/default for non-monsters) ---
        enemy_type=None,        # Registry key e.g. "tweaker", "crack_addict"
        gender=None,            # "male" | "female"
        base_stats=None,        # dict: {"constitution":n,"strength":n,"street_smarts":n,"book_smarts":n,"tolerance":n,"swagger":n}
        ai_type="meander",      # AI behavior mode (see ai.py)
        sight_radius=6,         # Detection radius in tiles
        speed=100,              # Energy gained per tick (higher = faster; 100 = same as player)
        energy=0.0,             # Current energy pool; entity acts when energy >= ENERGY_THRESHOLD
        is_chasing=False,       # State flag used by wander_ambush AI (legacy)
        provoked=False,         # State flag: passive_until_hit switches to chase when True
        ai_state=None,          # AIState enum — managed by the AI state machine
        special_attacks=None,   # List of special-attack dicts (see enemies.py guide)
        on_hit_effects=None,    # List of on-hit-effect dicts (see enemies.py guide)
        cash_drop=0,            # Cash awarded to player on this monster's death
        dodge_chance=0,         # Melee dodge chance as integer percentage (0-90)
        crit_chance=0,          # Crit chance as integer percentage (0-90), derived from street_smarts × 3
        bonus_spell_damage=0,   # Bonus spell damage, derived from book_smarts (future use)
        bonus_ranged_damage=0,  # Bonus ranged damage, derived from swagger (future use)
        reveals_on_sight=False, # If True, becomes always_visible the first time player sees it
        blocks_fov=False,       # If True, entity blocks line-of-sight in FOV computation
        hazard_type=None,       # "crate" | "fire" | "door" | None — used when entity_type == "hazard"
        move_cost=0,            # Energy cost override for movement (0 = use ENERGY_THRESHOLD)
        attack_cost=0,          # Energy cost override for attacks  (0 = use ENERGY_THRESHOLD)
        death_drop_chance=0.0,  # Probability (0.0–1.0) of dropping an item on death
        death_drop_table=None,  # List of item_ids to pick from on death drop
        death_drop_quantity=None,  # (min, max) stack size for dropped item
        faction=None,           # Faction key ("scryer" | "aldor" | None) for cartel enemies
        blink_charges=0,        # Emergency teleport charges (specialist enemies)
        ranged_attack=None,     # Ranged attack dict: {"range": int, "damage": (min, max), "miss_chance": float, "knockback": int}
        spawner_type=None,      # enemy_type key to spawn mid-combat (e.g. "rad_rat")
        max_spawned=0,          # max alive children at once
        # --- Timed hazard fields ---
        hazard_duration=0,      # turns remaining for timed hazards (0 = permanent)
        hazard_tox_per_turn=0,  # tox applied per tick to entities on this tile
        # --- Death behavior fields ---
        death_split_type=None,  # enemy_type key to spawn on death (e.g. "mini_sludge")
        death_split_count=0,    # number of children to spawn on death
        death_creep_radius=0,   # radius of toxic creep spawned on death
        death_creep_duration=0, # duration of death-spawned toxic creep
        death_creep_tox=0,      # tox per turn of death-spawned toxic creep
        leaves_trail=None,      # dict {"duration": int, "tox": int} for trail-leaving enemies
        is_summon=False,        # True for player-summoned allies (meatballs, etc.) — not auto-attacked by player
        summon_lifetime=0,      # Turns remaining before summon despawns (0 = no limit)
    ):
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.name = name
        self.entity_type = entity_type  # "player", "monster", "item"
        # Monsters always block movement (except summons); explicitly enforce this
        if entity_type == "monster" and not is_summon:
            self.blocks_movement = True
        else:
            self.blocks_movement = blocks_movement
        self.hp = hp
        self.max_hp = hp
        self.armor = 0                  # current armor
        self.max_armor = 0              # max armor (derived from equipment/effects)
        self.temp_hp = 0                # temporary HP shield (absorbed before armor and HP)
        self.power = power
        self.defense = defense
        self.alive = True
        self.inventory = []
        self.item_id = item_id          # links to items.ITEM_DEFS key (None for non-items)
        self.cash_amount = cash_amount  # dollar value for cash pile entities
        self.quantity = quantity        # stack size (1 for non-stackable items)
        self.strain = strain            # marijuana strain (e.g., "OG Kush") for cannabis items
        self.prefix = prefix            # active food prefix ("greasy", etc.); None = no prefix
        self.charges = charges          # remaining uses for prefixed food; None = no charge system
        self.max_charges = max_charges  # max uses at prefix-apply time
        self.current_ammo = current_ammo  # rounds loaded in this gun (0 for non-guns)
        self.mag_size = mag_size          # magazine capacity (0 for non-guns)
        self.status_effects = []        # list of active status effect dicts
        self.instance_id = str(uuid.uuid4())  # unique ID for tracking loot instances
        self.dev_invincible = False     # DEV TOOL: if True, take_damage always no-ops
        self.reveals_on_sight = reveals_on_sight  # marks always_visible when first seen
        self.always_visible = False     # if True, render even outside FOV (set by landmark system)
        self.blocks_fov = blocks_fov   # if True, blocks line-of-sight in FOV computation

        # Enemy-specific fields
        self.enemy_type     = enemy_type
        self.gender         = gender
        self.base_stats     = base_stats or {}
        self.ai_type        = ai_type
        self.sight_radius   = sight_radius
        self.speed          = speed
        self.energy         = energy
        self.is_chasing     = is_chasing
        self.provoked       = provoked
        self.ai_state       = ai_state
        self.special_attacks = special_attacks or []
        self.on_hit_effects  = on_hit_effects or []
        self.cash_drop      = cash_drop
        self.dodge_chance   = dodge_chance
        self.crit_chance    = crit_chance
        self.bonus_spell_damage  = bonus_spell_damage
        self.bonus_ranged_damage = bonus_ranged_damage
        self.hazard_type    = hazard_type
        self.move_cost         = move_cost
        self.attack_cost       = attack_cost
        self.death_drop_chance = death_drop_chance
        self.death_drop_table  = death_drop_table or []
        self.death_drop_quantity = death_drop_quantity
        self.faction           = faction
        self.blink_charges     = blink_charges
        self.ranged_attack     = ranged_attack
        self.spawner_type      = spawner_type
        self.max_spawned       = max_spawned
        self.spawned_children  = []   # list of entity references this spawner has created
        self.hazard_duration   = hazard_duration
        self.hazard_tox_per_turn = hazard_tox_per_turn
        self.death_split_type  = death_split_type
        self.death_split_count = death_split_count
        self.death_creep_radius  = death_creep_radius
        self.death_creep_duration = death_creep_duration
        self.death_creep_tox     = death_creep_tox
        self.leaves_trail        = leaves_trail
        self.is_summon           = is_summon
        self.summon_lifetime     = summon_lifetime
        self.aggro_target        = None  # entity ref: summon that provoked this monster
        self.toxicity: int  = 0  # meth lab zone: damage-taken multiplier via power scaling
        self.meth: int = 0         # current meth resource (spent on strong abilities)
        self.max_meth: int = 250   # max meth capacity
        self.tox_resistance: int = 0  # % reduction to toxicity gain; 100 = immune, negative = extra gain
        self.radiation: int = 0  # radiation level; effects TBD by zone mechanics
        self.rad_resistance: int = 0  # % reduction to radiation gain; 100 = immune, negative = extra gain
        self.infection: int = 0      # infection level; at 100 = 25 damage/turn
        self.max_infection: int = 100  # infection cap

    def move(self, dx, dy):
        """Move entity by delta x, y."""
        self.x += dx
        self.y += dy

    def take_damage(self, damage):
        """Absorb damage: temp HP first, then armor, then HP. Returns True if dead."""
        if self.dev_invincible:
            return False
        if any(getattr(e, 'id', None) == 'invulnerable' for e in self.status_effects):
            return False

        remaining = damage

        # Temp HP absorbs first; overflow passes through
        if self.temp_hp > 0:
            thp_absorbed = min(self.temp_hp, remaining)
            self.temp_hp -= thp_absorbed
            remaining -= thp_absorbed

        if remaining > 0 and self.armor > 0:
            # Armor absorbs remaining; overflow is negated
            armor_absorbed = min(self.armor, remaining)
            self.armor -= armor_absorbed
            hp_damage = 0
        elif remaining > 0:
            # No armor; remaining damage goes to HP
            hp_damage = remaining
        else:
            hp_damage = 0

        self.hp -= hp_damage
        # Floating damage number callback
        if Entity._on_damage_callback and damage > 0:
            Entity._on_damage_callback(self, damage, hp_damage)
        # Any damage provokes passive monsters (fire, DoT, etc.)
        if damage > 0 and hasattr(self, "provoked") and not self.provoked:
            self.provoked = True
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def heal(self, amount):
        """Heal HP up to max."""
        old_hp = self.hp
        self.hp = min(self.hp + amount, self.max_hp)
        actual = self.hp - old_hp
        if actual > 0 and Entity._on_heal_callback:
            Entity._on_heal_callback(self, actual)

    def attack(self, target):
        """Calculate damage to target. Returns damage dealt."""
        # Simple formula: power - defense + variance
        damage = max(1, self.power - target.defense)
        target.take_damage(damage)
        return damage
