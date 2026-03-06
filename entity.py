"""
Entity class for all game objects (player, monsters, items).
"""

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
        self.status_effects = []        # list of active status effect dicts

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

    def move(self, dx, dy):
        """Move entity by delta x, y."""
        self.x += dx
        self.y += dy

    def take_damage(self, damage):
        """Reduce armor first. If armor > 0, overflow damage is blocked. If armor = 0, damage goes to HP. Returns True if dead."""
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
