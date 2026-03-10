"""
Unified status effect system for NIGRL.

All status effects live here as Effect subclasses registered in EFFECT_REGISTRY.
Use apply_effect() to attach an effect to any entity.
Use tick_all_effects() once per turn for each entity.
"""
import math as _math
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

    def __init__(self, duration: int = 1, custom_display_name: str = None, **kwargs):
        self.duration = duration
        self.custom_display_name = custom_display_name

    @property
    def expired(self) -> bool:
        return self.duration <= 0

    @property
    def display_name(self) -> str:
        if self.custom_display_name:
            return self.custom_display_name
        return self.id.replace("_", " ").title()

    @property
    def stack_count(self):
        """Return stack count for display, or None if this effect does not stack."""
        return None

    @property
    def display_duration(self) -> str:
        """Return human-readable duration string for the status panel."""
        d = self.duration
        return f"{d} turn{'s' if d != 1 else ''}"

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
class BleedingEffect(Effect):
    """Bleeding — damage over time from wounds."""
    id = "bleeding"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 4, amount: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    @property
    def display_name(self) -> str:
        return "Bleeding"

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
class GougeEffect(Effect):
    """Gouge — stun that breaks when the gouged entity takes damage from the player.
    While active the entity cannot accumulate energy and skips its AI turn."""
    id = "gouge"
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
class CrippleArmorEffect(Effect):
    """Sets enemy defense stat to 0 for the duration. Restores on expiry."""
    id = "cripple_armor"
    category = "debuff"
    priority = 10

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._saved_defense: int = 0

    def apply(self, entity, engine):
        self._saved_defense = entity.defense
        entity.defense = 0

    def expire(self, entity, engine):
        entity.defense = self._saved_defense

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)  # refresh, don't stack


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

    @property
    def stack_count(self):
        return self.amount

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
    """Fear — player is forced to flee from the source.
    Cannot take any actions except forced movement away from the fear source.
    50% chance to break when taking any damage."""
    id = "fear"
    category = "debuff"
    priority = 100  # high priority like stun — overrides other effects

    def __init__(self, duration: int = 10, source_x: int = 0, source_y: int = 0, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.source_x = source_x
        self.source_y = source_y

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)
        existing.source_x = self.source_x
        existing.source_y = self.source_y

    @property
    def display_name(self) -> str:
        return "Frightened"

    def modify_incoming_damage(self, damage: int, entity) -> int:
        """50% chance to break fear when taking any damage."""
        if damage > 0 and _random.random() < 0.50:
            self._broken_by_damage = True
            self.duration = 0  # mark expired so tick_all_effects removes it
        return damage

    def expire(self, entity, engine):
        if getattr(self, '_broken_by_damage', False):
            engine.messages.append("The pain snaps you out of your fear!")
        else:
            engine.messages.append("You are no longer frightened.")


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
class ChillEffect(Effect):
    """Debuff: reduces speed by 10 per stack (hard minimum 10 energy/tick).
    Removed when ignite is applied."""
    id = "chill"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 5, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Chill"

    @property
    def stack_count(self):
        return self.stacks

    def modify_energy_gain(self, amount: float, entity) -> float:
        """Reduce energy gain by 10 per stack."""
        return amount - (10 * self.stacks)

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.messages.append(f"You feel chillier! (Chill x{existing.stacks})")


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
        return "Shocked"

    @property
    def stack_count(self):
        return self.stacks

    def modify_incoming_damage(self, damage: int, entity) -> int:
        import math
        return math.ceil(damage * (1 + 0.15 * self.stacks))

    def on_reapply(self, existing, entity, engine):
        existing.stacks = min(existing.stacks + 1, 5)
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
        dur = engine._player_ignite_duration()
        ignite_eff = apply_effect(defender, engine, "ignite", duration=dur, stacks=1, silent=True)
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
class GlassShardsEffect(Effect):
    """Debuff (Broken Bong): deals 1 damage per active stack per turn.
    Each stack has its own independent timer; new stacks never reset existing timers."""
    id = "glass_shards"
    category = "debuff"
    priority = 5

    def __init__(self, stacks: int = 1, duration: int = 5, **kwargs):
        super().__init__(duration=1, **kwargs)  # base duration unused; expiry tracked via stack_timers
        self.stack_timers: list = [duration] * stacks

    @property
    def expired(self) -> bool:
        return len(self.stack_timers) == 0

    @property
    def display_name(self) -> str:
        return "Glass Shards"

    @property
    def stack_count(self):
        return len(self.stack_timers)

    @property
    def display_duration(self) -> str:
        if not self.stack_timers:
            return "0 turns"
        longest = max(self.stack_timers)
        shortest = min(self.stack_timers)
        if len(self.stack_timers) > 1 and shortest != longest:
            return f"{longest} ({shortest}) turns"
        return f"{longest} turn{'s' if longest != 1 else ''}"

    def tick(self, entity, engine):
        n = len(self.stack_timers)
        if entity.alive and n > 0:
            entity.take_damage(n)
            if entity == engine.player:
                engine.messages.append(
                    f"Glass Shards ({n} stack{'s' if n != 1 else ''}) cut for {n} damage! "
                    f"({entity.hp}/{entity.max_hp} HP)"
                )
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
            else:
                if not entity.alive:
                    engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.stack_timers = [t - 1 for t in self.stack_timers if t - 1 > 0]

    def on_reapply(self, existing, entity, engine):
        new_duration = self.stack_timers[0] if self.stack_timers else 5
        existing.stack_timers.append(new_duration)
        n = len(existing.stack_timers)
        if entity == engine.player:
            engine.messages.append(f"Glass Shards stacks! ({n} stack{'s' if n != 1 else ''})")
        else:
            engine.messages.append(f"{entity.name} has {n} Glass Shards stacks!")


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


@register
class AcidArmorEffect(Effect):
    """Debuff (Blue Lobster): when attacked, 5-10% chance to break a random equipped item (player only)."""
    id = "acid_armor"
    category = "debuff"
    priority = 0

    def __init__(self, duration: int = 10, break_chance: float = 0.05, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.break_chance = break_chance

    @property
    def display_name(self) -> str:
        return "Acid Armor"


# ---------------------------------------------------------------------------
# Alcohol consumables effects
# ---------------------------------------------------------------------------

@register
class HangoverEffect(Effect):
    """Debuff: Accumulates from drinking alcohol; applies stat penalties for the next floor.
    Not affected by zoned_out immunity — must be endured."""
    id = "hangover"
    category = "debuff"
    priority = 0

    # Stats affected by hangover
    STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=999999, **kwargs)  # Floor-managed, not turn-managed
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Hangover"

    @property
    def stack_count(self):
        return self.stacks

    @property
    def display_duration(self) -> str:
        return "until next floor"

    def apply(self, entity, engine):
        for stat in self.STATS:
            engine.player_stats.add_temporary_stat_bonus(stat, -self.stacks)
        engine._sync_player_max_hp()

    def on_reapply(self, existing, entity, engine):
        # Revert old penalty, increase stacks, apply new penalty
        for stat in self.STATS:
            engine.player_stats.add_temporary_stat_bonus(stat, existing.stacks)
        existing.stacks += self.stacks
        for stat in self.STATS:
            engine.player_stats.add_temporary_stat_bonus(stat, -existing.stacks)
        engine._sync_player_max_hp()

    def expire(self, entity, engine):
        for stat in self.STATS:
            engine.player_stats.add_temporary_stat_bonus(stat, self.stacks)
        engine._sync_player_max_hp()


@register
class FortyOzEffect(Effect):
    """Buff (40oz bottle): +5 Swagger for 50 turns."""
    id = "forty_oz"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "40oz Buzz"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class MaltLiquorEffect(Effect):
    """Buff (Malt Liquor): +8 Strength, -2 Constitution, +20 temporary armor for 50 turns."""
    id = "malt_liquor"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Malt Liquor"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", 8)
            engine.player_stats.add_temporary_stat_bonus("constitution", -2)
            engine._sync_player_max_hp()
            engine.player_stats.temporary_armor_bonus += 20
            engine._compute_player_max_armor()
            engine.player.armor = min(engine.player.armor + 20, engine.player.max_armor)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", -8)
            engine.player_stats.add_temporary_stat_bonus("constitution", 2)
            engine._sync_player_max_hp()
            engine.player_stats.temporary_armor_bonus -= 20
            engine._compute_player_max_armor()
            engine.player.armor = min(engine.player.armor, engine.player.max_armor)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class WizardMindBombEffect(Effect):
    """Buff (Wizard Mind-Bomb): +5 Book-Smarts, spells gain bonus damage for 50 turns."""
    id = "wizard_mind_bomb"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Wizard Mind Bomb"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", -5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class HennessyEffect(Effect):
    """Buff (Homemade Hennessy): -2 Strength, +5 Tolerance, enables double smoking for 50 turns."""
    id = "hennessy"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Hennessy High"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", -2)
            engine.player_stats.add_temporary_stat_bonus("tolerance", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", 2)
            engine.player_stats.add_temporary_stat_bonus("tolerance", -5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class SpeedBoostEffect(Effect):
    """Buff: Increases energy gain per tick (e.g., from food buffs)."""
    id = "speed_boost"
    category = "buff"
    priority = 50

    def __init__(self, duration: int = 20, amount: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    @property
    def display_name(self) -> str:
        return f"Hyped Up ({self.duration})"

    def modify_energy_gain(self, energy: float, entity) -> float:
        return energy + self.amount


@register
class PeaceOfMindEffect(Effect):
    """Buff (Alcoholism perk): +1 Street Smarts per stack, refreshes to 20 turns on reapply."""
    id = "peace_of_mind"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Peace of Mind"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", self.stacks)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", -self.stacks)

    def on_reapply(self, existing, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", 1)
        existing.stacks += 1
        existing.duration = 20


@register
class ArcaneIntelligenceEffect(Effect):
    """Buff (Blackkk Magic L3): each stack adds +1 flat spell damage for 20 turns.
    Reapplying adds stacks and refreshes duration to 20 turns."""
    id = "arcane_intelligence"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, stacks: int = 2, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Arcane Intelligence"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_spell_damage(self.stacks)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.temporary_spell_damage = max(
                0, engine.player_stats.temporary_spell_damage - self.stacks
            )

    def on_reapply(self, existing, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_spell_damage(self.stacks)
        existing.stacks += self.stacks
        existing.duration = 20


@register
class GreasyEffect(Effect):
    """Buff (Greasy food): +3% dodge per stack, max 3 stacks, 20-turn shared duration."""
    id = "greasy"
    category = "buff"
    priority = 0
    MAX_STACKS = 10
    DODGE_PER_STACK = 3

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = min(stacks, self.MAX_STACKS)

    @property
    def display_name(self) -> str:
        return "Greasy"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_dodge_chance(self.stacks * self.DODGE_PER_STACK)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_dodge_chance(-(self.stacks * self.DODGE_PER_STACK))

    def on_reapply(self, existing, entity, engine):
        """Increment stacks (up to MAX_STACKS) and refresh timer."""
        add = min(self.stacks, self.MAX_STACKS - existing.stacks)
        if add > 0:
            if entity == engine.player:
                engine.player_stats.add_dodge_chance(add * self.DODGE_PER_STACK)
            existing.stacks += add
        existing.duration = max(existing.duration, self.duration)


@register
class NiggaArmorEffect(Effect):
    """Buff: each stack grants -1 incoming damage for 30 turns. Stacks have independent timers."""
    id = "nigga_armor"
    category = "buff"
    priority = 5  # apply before % modifiers

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=30, **kwargs)
        self.timers: list[int] = [30] * stacks

    @property
    def display_name(self) -> str:
        return "Nigga Armor"

    @property
    def stack_count(self):
        return len(self.timers)

    def modify_incoming_damage(self, damage: int, entity) -> int:
        return max(0, damage - len(self.timers))

    def on_reapply(self, existing, entity, engine):
        for _ in range(self.stack_count):
            existing.timers.append(30)
        existing.duration = max(existing.timers)

    def tick(self, entity, engine):
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        self.duration = max(self.timers) if self.timers else 0


@register
class HotCheetosEffect(Effect):
    """Buff (Hot Cheetos food): +2 to all stats for duration.
    Melee attacks have 50% chance to apply 1 stack of Ignite (5 turns).
    On expire, apply 1 stack of Ignite to the player."""
    id = "hot_cheetos"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 30, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Spicy Vibes"

    def apply(self, entity, engine):
        """Apply +2 to all stats."""
        if entity == engine.player:
            for stat in ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]:
                engine.player_stats.add_temporary_stat_bonus(stat, 2)
            engine._sync_player_max_hp()

    def expire(self, entity, engine):
        """Revert stat bonuses and apply Ignite to player."""
        if entity == engine.player:
            for stat in ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]:
                engine.player_stats.add_temporary_stat_bonus(stat, -2)
            engine._sync_player_max_hp()
            # Apply 1 stack of Ignite when buff expires
            apply_effect(entity, engine, "ignite", duration=5, stacks=1, silent=False)

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        """50% chance to apply 1 stack of Ignite to the target."""
        if _random.random() < 0.50:
            dur = engine._player_ignite_duration()
            ignite_eff = apply_effect(defender, engine, "ignite", duration=dur, stacks=1, silent=True)
            if ignite_eff:
                engine.messages.append(
                    f"Spicy attack! {defender.name} ignited! (x{ignite_eff.stacks})"
                )


@register
class CornbreadBuffEffect(Effect):
    """Buff (Cornbread food): +5 Book-Smarts for 10 turns."""
    id = "cornbread_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Cornbread High"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", -5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class LesserCloudkillEffect(Effect):
    """Debuff (Lightskin Beans spell): 1 dmg/turn + all stats -1 for duration turns."""
    id = "lesser_cloudkill"
    category = "debuff"
    priority = 5

    _STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stat_reductions: dict = {}

    @property
    def display_name(self) -> str:
        return "Lesser Cloudkill"

    def apply(self, entity, engine):
        if isinstance(getattr(entity, 'base_stats', None), dict):
            for stat in self._STATS:
                old = entity.base_stats.get(stat, 0)
                reduced = min(old, 1)
                entity.base_stats[stat] = max(0, old - 1)
                self.stat_reductions[stat] = reduced

    def tick(self, entity, engine):
        if entity.alive:
            entity.take_damage(1)
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.duration -= 1

    def expire(self, entity, engine):
        if isinstance(getattr(entity, 'base_stats', None), dict):
            for stat, amount in self.stat_reductions.items():
                entity.base_stats[stat] = entity.base_stats.get(stat, 0) + amount

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


# ---------------------------------------------------------------------------
# Food system
# ---------------------------------------------------------------------------

@register
class LeftoversWellFedEffect(Effect):
    """Buff: +1 melee power and +1 spell damage for duration. From eating Leftovers."""
    id = "leftovers_well_fed"
    category = "buff"
    priority = 5

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Well Fed"

    def apply(self, entity, engine):
        entity.power += 1
        engine.player_stats.add_temporary_spell_damage(1)

    def expire(self, entity, engine):
        entity.power -= 1
        engine.player_stats.add_temporary_spell_damage(-1)

    def on_reapply(self, existing, entity, engine):
        """Extend duration, don't stack."""
        existing.duration = max(existing.duration, self.duration)


@register
class QuickEatEffect(Effect):
    """Buff: Next food eaten is consumed instantly (skip multi-turn eating)."""
    id = "quick_eat"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 999, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Quick Eat"

    def on_reapply(self, existing, entity, engine):
        """Don't stack — keep existing."""
        pass


@register
class EatingFoodEffect(Effect):
    """Buff: Player is eating food. Prevents all actions. When expired, applies food effects."""
    id = "eating_food"
    category = "buff"
    priority = 100  # High priority to prevent any actions

    def __init__(self, duration: int = 10, food_name: str = "Food", food_id: str = "", food_effects: list = None, well_fed_effect_name: str = "Well Fed", **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.food_name = food_name
        self.food_id = food_id
        self.food_effects = food_effects or []
        self.well_fed_effect_name = well_fed_effect_name
        self.move_warned = False

    @property
    def display_name(self) -> str:
        return f"Eating {self.food_name} ({self.duration})"

    def expire(self, entity, engine):
        """When eating is done, apply all food effects."""
        if entity != engine.player:
            return

        engine.messages.append(f"You finish eating the {self.food_name}.")

        for effect_dict in self.food_effects:
            effect_type = effect_dict.get("type")

            if effect_type == "heal":
                amount_spec = effect_dict.get("amount")
                if isinstance(amount_spec, (list, tuple)):
                    amount = _random.randint(amount_spec[0], amount_spec[1])
                else:
                    amount = amount_spec
                entity.heal(amount)
                engine.messages.append(f"Healed {amount} HP. ({entity.hp}/{entity.max_hp} HP)")

            elif effect_type == "hot":
                # Parse stat formula and calculate per-turn healing
                # Formula format: "constitution / 5" (stat name / divisor)
                formula = effect_dict.get("stat_formula", "constitution / 5")
                parts = formula.split("/")
                if len(parts) == 2:
                    stat_name = parts[0].strip()
                    divisor = int(parts[1].strip())
                    stat_value = getattr(engine.player_stats, stat_name, 10)
                    heal_amount = _math.ceil(stat_value / divisor)
                else:
                    heal_amount = 1

                duration = effect_dict.get("duration", 10)
                # Apply hot effect with custom display name "Well Fed"
                hot_effect = apply_effect(entity, engine, "hot", duration=duration, amount=heal_amount,
                                         custom_display_name=self.well_fed_effect_name, silent=True)
                if hot_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}!")

            elif effect_type == "speed_boost":
                amount = effect_dict.get("amount", 50)
                duration = effect_dict.get("duration", 20)
                speed_effect = apply_effect(entity, engine, "speed_boost", duration=duration, amount=amount,
                                           custom_display_name=self.well_fed_effect_name, silent=True)
                if speed_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}!")

            elif effect_type == "hot_cheetos":
                duration = effect_dict.get("duration", 30)
                hot_cheetos_effect = apply_effect(entity, engine, "hot_cheetos", duration=duration,
                                                 custom_display_name=self.well_fed_effect_name, silent=True)
                if hot_cheetos_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}!")

            elif effect_type == "greasy_buff":
                stacks = 2 if engine.skills.get("Deep-Frying").level >= 2 else 1
                apply_effect(entity, engine, "greasy", duration=20, stacks=stacks, silent=True)
                bonus = " (+Extra Greasy!)" if stacks == 2 else ""
                engine.messages.append(f"The {self.food_name} makes you feel Greasy!{bonus} (+{stacks * GreasyEffect.DODGE_PER_STACK}% dodge)")

            elif effect_type == "grant_ability_charges":
                ability_id = effect_dict.get("ability_id")
                charges = effect_dict.get("charges", 1)
                if ability_id:
                    engine.grant_ability_charges(ability_id, charges)

            elif effect_type == "cornbread_buff":
                duration = effect_dict.get("duration", 10)
                cb_effect = apply_effect(entity, engine, "cornbread_buff", duration=duration, silent=True)
                if cb_effect:
                    engine.messages.append("Cornbread High! +5 Book-Smarts for 10 turns.")

            elif effect_type == "leftovers_well_fed":
                duration = effect_dict.get("duration", 10)
                lwf_effect = apply_effect(entity, engine, "leftovers_well_fed", duration=duration, silent=True)
                if lwf_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! (+1 power, +1 spell damage)")

        # Grant munching skill XP
        if self.food_id:
            engine._gain_munching_xp(self.food_id)

        # Better Later perk: 25% chance to generate Leftovers on food completion
        munching_skill = engine.skills.get("Munching")
        if munching_skill.level >= 3:
            if _random.random() < 0.25:
                engine._add_item_to_inventory("leftovers")
                engine.messages.append("[Better Later] You saved some Leftovers!")


@register
class IgniteEffect(Effect):
    """Burning — 1 damage per stack per turn. Shared 5-turn timer; all stacks refresh on reapply.

    Applying ignite strips Chill. Wet extinguishes all stacks instantly.
    Damage per tick = stacks. Capped at 9999 stacks.
    """
    id = "ignite"
    category = "debuff"
    priority = 5
    _MAX_STACKS = 9999

    def __init__(self, duration: int = 5, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks: int = min(stacks, self._MAX_STACKS)

    @property
    def display_name(self) -> str:
        return "Burning"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        had_chill = any(getattr(e, 'id', '') == 'chill' for e in entity.status_effects)
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'id', '') != 'chill']
        if had_chill:
            if entity == engine.player:
                engine.messages.append("The fire burns away your chill!")
            else:
                engine.messages.append(f"{entity.name}'s chill is burned away!")

    def on_reapply(self, existing, entity, engine):
        """Add incoming stacks and refresh the shared timer to incoming duration."""
        existing.stacks = min(existing.stacks + self.stacks, self._MAX_STACKS)
        existing.duration = self.duration

    def tick(self, entity, engine):
        damage = self.stacks
        entity.take_damage(damage)
        if entity == engine.player:
            engine.messages.append(
                f"You are burning! ({damage} dmg) ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
                engine.messages.append(f"{entity.name} burns to death!")
        self.duration -= 1


@register
class DisarmEffect(Effect):
    """Debuff (Monkey Wrench): monster deals half melee damage while active."""
    id = "disarmed"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 3, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Disarmed"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_grease_fire_synergy(entity, engine) -> None:
    """Trigger Grease Fire reaction if entity has both Greasy and Ignite."""
    greasy = next((e for e in entity.status_effects if getattr(e, 'id', '') == 'greasy'), None)
    ignite = next((e for e in entity.status_effects if getattr(e, 'id', '') == 'ignite'), None)
    if greasy is None or ignite is None:
        return

    greasy_stacks = greasy.stacks
    damage = greasy_stacks * 2
    bonus_stacks = greasy_stacks * 2

    # Remove greasy (undo dodge bonus for player)
    if entity == engine.player:
        engine.player_stats.add_dodge_chance(-(greasy_stacks * GreasyEffect.DODGE_PER_STACK))
    entity.status_effects = [e for e in entity.status_effects if getattr(e, 'id', '') != 'greasy']

    # Deal burst damage
    entity.take_damage(damage)

    # Add ignite stacks (refresh duration to at least 5)
    ignite.stacks = min(ignite.stacks + bonus_stacks, IgniteEffect._MAX_STACKS)
    ignite.duration = max(ignite.duration, 5)

    # Messages
    if entity == engine.player:
        engine.messages.append(
            f"Grease Fire! The grease ignites! {damage} dmg, Burning x{ignite.stacks}! (Greasy consumed)"
        )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=None)
    else:
        engine.messages.append(
            f"{entity.name} erupts in a Grease Fire! {damage} dmg, Burning x{ignite.stacks}!"
        )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=None)
            engine.messages.append(f"{entity.name} is consumed by the Grease Fire!")


@register
class BlackEyeEffect(Effect):
    """Black Eye stun — entity stunned for 2 turns, then gains BlackEyeWanderEffect for 10 turns."""
    id = "black_eye"
    category = "debuff"
    priority = 100

    def modify_energy_gain(self, amount: float, entity) -> float:
        return 0.0

    def before_turn(self, entity, player, dungeon) -> bool:
        return True

    def expire(self, entity, engine):
        apply_effect(entity, engine, "black_eye_wander", duration=10, silent=True)
        if entity != engine.player:
            engine.messages.append(f"{entity.name} staggers around dazed!")


@register
class BlackEyeWanderEffect(Effect):
    """Post-Black Eye daze — entity moves randomly for 10 turns."""
    id = "black_eye_wander"
    category = "debuff"
    priority = 50

    def modify_movement(self, dx, dy, entity, player, dungeon):
        return _random.choice([-1, 0, 1]), _random.choice([-1, 0, 1])


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
        if effect_id in ('greasy', 'ignite'):
            _check_grease_fire_synergy(entity, engine)
        return existing

    incoming.apply(entity, engine)
    entity.status_effects.append(incoming)

    if not silent:
        if entity == engine.player:
            engine.messages.append(f"You are {incoming.display_name}!")
        else:
            engine.messages.append(f"{entity.name} is {incoming.display_name}!")

    if effect_id in ('greasy', 'ignite'):
        _check_grease_fire_synergy(entity, engine)

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
