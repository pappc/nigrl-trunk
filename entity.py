"""
Entity class for all game objects (player, monsters, items).
"""

import uuid
from config import BASE_HP, BASE_POWER, BASE_DEFENSE


class Entity:
    """Represents any actor or object in the game."""

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
    ):
        self.x = x
        self.y = y
        self.char = char
        self.color = color
        self.name = name
        self.entity_type = entity_type  # "player", "monster", "item"
        # Monsters always block movement; explicitly enforce this
        self.blocks_movement = blocks_movement if entity_type != "monster" else True
        self.hp = hp
        self.max_hp = hp
        self.armor = 0                  # current armor
        self.max_armor = 0              # max armor (derived from equipment/effects)
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
        self.toxicity: int  = 0  # meth lab zone: damage-taken multiplier via power scaling

    def move(self, dx, dy):
        """Move entity by delta x, y."""
        self.x += dx
        self.y += dy

    def take_damage(self, damage):
        """Reduce armor first. If armor > 0, overflow damage is blocked. If armor = 0, damage goes to HP. Returns True if dead."""
        if self.dev_invincible:
            return False
        if any(getattr(e, 'id', None) == 'invulnerable' for e in self.status_effects):
            return False

        if self.armor > 0:
            # Armor absorbs damage; overflow is negated
            armor_absorbed = min(self.armor, damage)
            self.armor -= armor_absorbed
            hp_damage = 0
        else:
            # No armor; damage goes straight to HP
            hp_damage = damage

        self.hp -= hp_damage
        # Any damage provokes passive monsters (fire, DoT, etc.)
        if hp_damage > 0 and hasattr(self, "provoked") and not self.provoked:
            self.provoked = True
        if self.hp <= 0:
            self.alive = False
            return True
        return False

    def heal(self, amount):
        """Heal HP up to max."""
        self.hp = min(self.hp + amount, self.max_hp)

    def attack(self, target):
        """Calculate damage to target. Returns damage dealt."""
        # Simple formula: power - defense + variance
        damage = max(1, self.power - target.defense)
        target.take_damage(damage)
        return damage
