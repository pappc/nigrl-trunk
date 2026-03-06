"""
Unified status effect system for NIGRL.

All status effects live here as Effect subclasses registered in EFFECT_REGISTRY.
Use apply_effect() to attach an effect to any entity.
Use tick_all_effects() once per turn for each entity.
"""
import random as _random


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

EFFECT_REGISTRY: dict[str, type] = {}


def register(cls):
    """Class decorator that adds the class to EFFECT_REGISTRY by its id."""
    EFFECT_REGISTRY[cls.id] = cls
    return cls


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Effect:
    """Base status effect — override hooks as needed."""

    id: str = "base"
    category: str = "debuff"   # "buff" | "debuff"  — drives UI colour
    priority: int = 0           # higher priority effects are checked first

    def __init__(self, duration: int = 1, **kwargs):
        self.duration = duration

    @property
    def expired(self) -> bool:
        return self.duration <= 0

    @property
    def display_name(self) -> str:
        return self.id.replace("_", " ").title()

    # ── Lifecycle hooks ──────────────────────────────────────────────────

    def apply(self, entity, engine):
        """Called once when the effect is first applied."""
        pass

    def tick(self, entity, engine):
        """Called once per game turn.  Decrement duration by default."""
        self.duration -= 1

    def expire(self, entity, engine):
        """Called when the effect is removed after expiring."""
        pass

    def on_reapply(self, existing, entity, engine):
        """Called when the same effect is applied to an entity that already has it.
        `existing` is the current Effect instance on the entity.
        Default: refresh duration to the longer of the two."""
        existing.duration = max(existing.duration, self.duration)

    # ── AI hooks (monsters only) ─────────────────────────────────────────

    def before_turn(self, entity, player, dungeon) -> bool:
        """Return True to skip the entity's entire AI turn."""
        return False

    def modify_energy_gain(self, amount: float, entity) -> float:
        """Return modified energy gained per tick. Return 0 to freeze accumulation."""
        return amount

    def modify_movement(self, dx, dy, entity, player, dungeon):
        """Return a modified (dx, dy) movement vector."""
        return dx, dy

    def modify_incoming_damage(self, damage: int, entity) -> int:
        """Return modified incoming melee damage. Default: no change."""
        return damage

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        """Called after the player successfully deals melee damage to a target."""
        pass


# ---------------------------------------------------------------------------
# Concrete effect classes
# ---------------------------------------------------------------------------

@register
class DotEffect(Effect):
    """Damage-over-time — deals amount damage per turn."""
    id = "dot"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 4, amount: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    def tick(self, entity, engine):
        if entity.alive and self.amount > 0:
            entity.take_damage(self.amount)
            if entity == engine.player:
                engine.messages.append(
                    f"{self.display_name} deals {self.amount} damage! "
                    f"({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
                    engine.messages.append(
                        f"{entity.name} dies from {self.display_name}!"
                    )
        self.duration -= 1


@register
class HotEffect(Effect):
    """Heal-over-time — heals amount HP per turn."""
    id = "hot"
    category = "buff"
    priority = 5

    def __init__(self, duration: int = 5, amount: int = 2, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    def tick(self, entity, engine):
        if entity.alive and self.amount > 0:
            entity.heal(self.amount)
            if entity == engine.player:
                engine.messages.append(
                    f"{self.display_name} heals {self.amount} HP. "
                    f"({entity.hp}/{entity.max_hp} HP)"
                )
        self.duration -= 1


@register
class StunEffect(Effect):
    """Entity cannot accumulate energy and skips its AI turn."""
    id = "stun"
    category = "debuff"
    priority = 100

    def modify_energy_gain(self, amount: float, entity) -> float:
        return 0.0

    def before_turn(self, entity, player, dungeon) -> bool:
        return True


@register
class SlowEffect(Effect):
    """Reduces the entity's energy gain per tick, making it act less often.
    ratio=0.5 halves speed; ratio=0.9 is a minor slow; ratio=0.1 is near-frozen."""
    id = "slow"
    category = "debuff"
    priority = 50

    def __init__(self, duration: int = 3, ratio: float = 0.5, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.ratio = ratio

    def modify_energy_gain(self, amount: float, entity) -> float:
        return amount * self.ratio


@register
class ConfuseEffect(Effect):
    """Randomises movement direction each tick."""
    id = "confuse"
    category = "debuff"
    priority = 50

    def __init__(self, duration: int = 3, **kwargs):
        super().__init__(duration=duration, **kwargs)

    def modify_movement(self, dx, dy, entity, player, dungeon):
        return _random.choice([-1, 0, 1]), _random.choice([-1, 0, 1])


@register
class StatModEffect(Effect):
    """Temporarily modifies a stat and reverts it on expiry."""
    id = "stat_mod"
    category = "debuff"
    priority = 10

    def __init__(self, duration: int = 5, stat: str = None, amount: int = 0, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stat = stat
        self.amount = amount

    def apply(self, entity, engine):
        _mod_stat(entity, self.stat, self.amount)

    def expire(self, entity, engine):
        _mod_stat(entity, self.stat, -self.amount)


@register
class ChildSupportEffect(Effect):
    """Drains $1 per player move step."""
    id = "child_support"
    category = "debuff"
    priority = 0

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)
        engine.messages.append("Child support order extended!")


@register
class MoggedEffect(Effect):
    """Stacking debuff that temporarily reduces swagger until it wears off."""
    id = "mogged"
    category = "debuff"
    priority = 0

    def __init__(self, duration: int = 10, amount: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.amount)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", self.amount)

    def on_reapply(self, existing, entity, engine):
        amount_delta = self.amount
        existing.amount += self.amount
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -amount_delta)
        engine.messages.append(f"You feel more mogged! (Stack: {existing.amount})")


@register
class WellFedEffect(Effect):
    """Buff that increases damage per stack (Jerome boss mechanic)."""
    id = "well_fed"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, power_bonus: int = 2, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.power_bonus = power_bonus

    def apply(self, entity, engine):
        entity.power += self.power_bonus

    def expire(self, entity, engine):
        entity.power -= self.power_bonus

    def on_reapply(self, existing, entity, engine):
        entity.power += self.power_bonus
        existing.power_bonus += self.power_bonus
        existing.duration = max(existing.duration, self.duration)


@register
class FearEffect(Effect):
    """Placeholder fear effect."""
    id = "fear"
    category = "debuff"
    priority = 0


@register
class InvulnerableEffect(Effect):
    """Unit cannot take damage while this effect is active."""
    id = "invulnerable"
    category = "buff"
    priority = 100


@register
class ColumbiaoGoldEffect(Effect):
    """Strain combo effect: DoT (1/turn) + Power +5 for duration turns.
    Combines both effects into a single display item."""
    id = "columbian_gold"
    category = "debuff"
    priority = 10

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        # Sub-effects managed internally
        self.dot_amount = 1
        self.power_bonus = 5
        self.original_power = None

    @property
    def display_name(self) -> str:
        return "Columbian Gold"

    def apply(self, entity, engine):
        """Apply power boost and track it for removal on expire."""
        self.original_power = entity.power
        entity.power += self.power_bonus

    def tick(self, entity, engine):
        """Apply DoT damage each turn."""
        if entity.alive and self.dot_amount > 0:
            entity.take_damage(self.dot_amount)
            if entity == engine.player:
                engine.messages.append(
                    f"Columbian Gold burns: -{self.dot_amount} HP. "
                    f"({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.duration -= 1

    def expire(self, entity, engine):
        """Revert power boost."""
        if self.original_power is not None:
            entity.power = self.original_power


@register
class WetEffect(Effect):
    """Buff: entity is wet — extinguishes Ignite on application."""
    id = "wet"
    category = "buff"
    priority = 5

    def apply(self, entity, engine):
        had_ignite = any(getattr(e, 'id', '') == 'ignite' for e in entity.status_effects)
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'id', '') != 'ignite']
        if had_ignite:
            if entity == engine.player:
                engine.messages.append("The water douses your flames!")
            else:
                engine.messages.append(f"{entity.name}'s flames are doused!")


@register
class ZonedOutEffect(Effect):
    """Buff: entity cannot be debuffed while active."""
    id = "zoned_out"
    category = "buff"
    priority = 10

    @property
    def display_name(self) -> str:
        return "Zoned Out"


@register
class IgniteEffect(Effect):
    """Fire debuff: 1 damage per stack per turn. Stacks on reapply.
    Removed by wet buff; removes chill on apply."""
    id = "ignite"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 5, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    def apply(self, entity, engine):
        had_chill = any(getattr(e, 'id', '') == 'chill' for e in entity.status_effects)
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'id', '') != 'chill']
        if had_chill:
            if entity == engine.player:
                engine.messages.append("The fire burns away your chill!")
            else:
                engine.messages.append(f"{entity.name}'s chill is burned away!")

    def tick(self, entity, engine):
        if any(getattr(e, 'id', '') == 'wet' for e in entity.status_effects):
            self.duration = 0
            if entity == engine.player:
                engine.messages.append("You're too wet to burn. Ignite doused!")
            return
        if entity.alive and self.stacks > 0:
            entity.take_damage(self.stacks)
            if entity == engine.player:
                engine.messages.append(
                    f"You're burning! -{self.stacks} HP. ({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.duration -= 1

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.messages.append(f"You burn hotter! (Ignite x{existing.stacks})")


@register
class ChillEffect(Effect):
    """Debuff: cannot smoke joints. Removed when ignite is applied."""
    id = "chill"
    category = "debuff"
    priority = 5

    @property
    def display_name(self) -> str:
        return "Chill"


@register
class ShockedEffect(Effect):
    """Debuff: melee damage taken increased by 15% per stack (rounded up). Stacks on reapply."""
    id = "shocked"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 5, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Shocked x{self.stacks}" if self.stacks > 1 else "Shocked"

    def modify_incoming_damage(self, damage: int, entity) -> int:
        import math
        return math.ceil(damage * (1 + 0.15 * self.stacks))

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)


@register
class AgentOrangeEffect(Effect):
    """Debuff: cannot deal melee damage. On expiry, take 20 damage."""
    id = "agent_orange"
    category = "debuff"
    priority = 10

    @property
    def display_name(self) -> str:
        return "Agent Orange"

    def expire(self, entity, engine):
        entity.take_damage(20)
        if entity == engine.player:
            engine.messages.append(
                f"Agent Orange wears off — you take 20 damage! ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            engine.messages.append(
                f"{entity.name}'s Agent Orange wears off with a surge of damage!"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)


# ---------------------------------------------------------------------------
# Jungle Boyz strain effects
# ---------------------------------------------------------------------------

@register
class MinorSelfReflectionEffect(Effect):
    """Debuff (Jungle Boyz 1-20): 10% chance on melee hit to deal the same damage to yourself."""
    id = "minor_self_reflection"
    category = "debuff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Minor Self Reflection"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if _random.random() < 0.10:
            engine.player.take_damage(damage)
            engine.messages.append(
                f"Self Reflection — you hurt yourself for {damage}! "
                f"({engine.player.hp}/{engine.player.max_hp} HP)"
            )
            if not engine.player.alive:
                engine.event_bus.emit("entity_died", entity=engine.player, killer=None)


@register
class FieryFistsEffect(Effect):
    """Buff (Jungle Boyz 21-40): attacks apply 1 stack of Ignite (3 turns) to the target."""
    id = "fiery_fists"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Fiery Fists"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        ignite_eff = apply_effect(defender, engine, "ignite", duration=3, stacks=1, silent=True)
        if ignite_eff:
            engine.messages.append(
                f"Fiery Fists: {defender.name} ignited! (x{ignite_eff.stacks})"
            )


@register
class CripplingAttacksEffect(Effect):
    """Buff (Jungle Boyz 41-60): 50% chance per attack to apply 1 stack of Shocked to target."""
    id = "crippling_attacks"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Crippling Attacks"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if _random.random() < 0.50:
            shocked_eff = apply_effect(defender, engine, "shocked", duration=5, stacks=1, silent=True)
            if shocked_eff:
                engine.messages.append(
                    f"Crippling! {defender.name} is shocked ({shocked_eff.stacks} stack{'s' if shocked_eff.stacks != 1 else ''})."
                )


@register
class CrippledEffect(Effect):
    """Debuff (Jungle Boyz 41-60): monster deals half melee damage while active."""
    id = "crippled"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 8, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Crippled"


@register
class LifestealEffect(Effect):
    """Buff (Jungle Boyz 61-80): heal HP equal to melee damage dealt. Lasts 8 turns."""
    id = "lifesteal"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 8, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Lifesteal"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        engine.player.heal(damage)
        engine.messages.append(
            f"Lifesteal: +{damage} HP. ({engine.player.hp}/{engine.player.max_hp} HP)"
        )


@register
class GloryFistsEffect(Effect):
    """Buff (Jungle Boyz 81-100): 5% chance per attack to permanently gain +1 to a random stat."""
    id = "glory_fists"
    category = "buff"
    priority = 0

    _STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]
    _STAT_LABELS = {
        "constitution":  "Constitution",
        "strength":      "Strength",
        "book_smarts":   "Book-Smarts",
        "street_smarts": "Street-Smarts",
        "tolerance":     "Tolerance",
        "swagger":       "Swagger",
    }

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Glory Fists"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if _random.random() < 0.05:
            stat = _random.choice(self._STATS)
            ps = engine.player_stats
            setattr(ps, stat, getattr(ps, stat) + 1)
            ps._base[stat] = getattr(ps, stat)   # permanent — update base so it doesn't flag as buffed
            if stat == "constitution":
                engine.player.max_hp += 10
                engine.player.heal(10)
            engine.messages.append(
                f"Glory Fists! {self._STAT_LABELS[stat]} permanently +1!"
            )


@register
class SoulPairEffect(Effect):
    """Debuff (Jungle Boyz 81-100): whenever this monster deals melee damage to the player,
    the monster takes the same damage."""
    id = "soul_pair"
    category = "debuff"
    priority = 0

    @property
    def display_name(self) -> str:
        return "Soul-Pair"


@register
class BksmtBuffEffect(Effect):
    """Buff (Dosidos monster effect): temporarily boosts Book-Smarts stat."""
    id = "bksmt_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 9999, amount: int = 5, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    @property
    def display_name(self) -> str:
        return f"Book-Smarts +{self.amount}"

    def apply(self, entity, engine):
        if isinstance(getattr(entity, 'base_stats', None), dict):
            entity.base_stats["book_smarts"] = entity.base_stats.get("book_smarts", 5) + self.amount

    def expire(self, entity, engine):
        if isinstance(getattr(entity, 'base_stats', None), dict):
            entity.base_stats["book_smarts"] = max(0, entity.base_stats.get("book_smarts", 5) - self.amount)

    def on_reapply(self, existing, entity, engine):
        existing.amount += self.amount
        existing.duration = max(existing.duration, self.duration)
        if isinstance(getattr(entity, 'base_stats', None), dict):
            entity.base_stats["book_smarts"] = entity.base_stats.get("book_smarts", 5) + self.amount


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mod_stat(entity, stat, amount):
    """Apply a signed delta to entity.power or entity.defense."""
    if not stat or not amount:
        return
    if stat == "power":
        entity.power += amount
    elif stat == "defense":
        entity.defense += amount


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_effect(entity, engine, effect_id: str, silent: bool = False, **kwargs) -> "Effect":
    """Apply a named effect to an entity.

    If the entity already has the same effect type, call on_reapply() instead
    of creating a duplicate.  Returns the active Effect instance.

    Raises KeyError if effect_id is not in EFFECT_REGISTRY.

    silent: if True, suppress the default "You are [effect]!" message.
    """
    cls = EFFECT_REGISTRY.get(effect_id)
    if cls is None:
        raise KeyError(
            f"Unknown effect ID '{effect_id}'. "
            f"Registered: {sorted(EFFECT_REGISTRY)}"
        )

    incoming = cls(**kwargs)

    # Zoned-out immunity: block incoming debuffs
    if incoming.category == "debuff":
        if any(getattr(e, 'id', None) == 'zoned_out' for e in entity.status_effects):
            if not silent:
                if entity == engine.player:
                    engine.messages.append("You're too zoned out to be debuffed!")
                else:
                    engine.messages.append(f"{entity.name} is too zoned out to be debuffed!")
            return None

    existing = next(
        (e for e in entity.status_effects if type(e) is type(incoming)),
        None,
    )

    if existing is not None:
        incoming.on_reapply(existing, entity, engine)
        return existing

    incoming.apply(entity, engine)
    entity.status_effects.append(incoming)

    if not silent:
        if entity == engine.player:
            engine.messages.append(f"You are {incoming.display_name}!")
        else:
            engine.messages.append(f"{entity.name} is {incoming.display_name}!")

    return incoming


def tick_all_effects(entity, engine) -> None:
    """Tick every Effect on entity by one turn, removing expired ones.

    Call once per turn for each entity (player and monsters) from the
    engine's end-of-turn processing.
    """
    is_player = entity == engine.player
    still_active = []

    for effect in entity.status_effects:
        effect.tick(entity, engine)
        if effect.expired:
            effect.expire(entity, engine)
            if is_player:
                engine.messages.append(f"{effect.display_name} has worn off.")
        else:
            still_active.append(effect)

    entity.status_effects = still_active
