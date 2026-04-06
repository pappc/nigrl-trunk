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
# Player-facing effect descriptions (shown in chat log on application)
# ---------------------------------------------------------------------------

_PLAYER_DESCRIPTIONS: dict[str, str] = {
    "acid_armor": "When attacked, chance to break an equipped item",
    "aftershock": "Next hits deal bonus damage and can stun",
    "colossus_wrecking": "+40% melee damage, can't dodge, -2 DR",
    "colossus_fortress": "+4 DR, 30% counter-attack + stun, -25% melee damage",
    "acid_meltdown": "Halved move cost; kills explode into acid pools",
    "toxic_slingshot_timer": "Toxic Slingshot active; dissipates when timer or ammo runs out",
    "toxic_shell": "Toxic barrier; nova detonates when temp HP hits 0",
    "purity_stacks": "Building purity; temp HP when this expires",
    "bastion": "-25% damage taken, -20% damage dealt",
    "gamma_aura": "Nearby enemies gain +5 rad/turn; 2x Decon XP from resisted rad",
    "ironsoul_aura": "+1 DR per visible enemy (cap 5); +2 FOV; melee converts rad to armor",
    "retribution_aura": "Enemies that melee you take true damage; drains rad",
    "absolution": "Gaining tox; tox lost deals damage to nearby enemies",
    "agent_orange": "Can't deal melee damage; 20 damage when it expires",
    "alco_seltzer_immunity": "Immune to debuffs",
    "alco_seltzer_tox_resist": "100% toxicity resistance",
    "arcane_intelligence": "+1 spell damage per stack",
    "banana_pudding": "Temp HP equal to rad removed; decays over 100 turns",
    "berserk": "+4 STR per stack",
    "bksmt_buff": "+Book-Smarts",
    "black_eye": "Stunned, then wanders aimlessly",
    "black_eye_wander": "Moving randomly",
    "bleeding": "Damage over time from wounds",
    "blue_lagoon_buff": "Using consumables chills nearest enemy",
    "butterbeer_buff": "+25% briskness",
    "calculated_aim": "Auto-reload, 10% per gun kill → +1 perm STS",
    "child_support": "Drains $1 per step",
    "chill": "-15% speed per stack",
    "columbian_gold": "1 damage/turn, +5 power",
    "confuse": "Movement direction randomized",
    "conversion": "Drains 2 from the higher of tox/rad each turn",
    "cornbread_buff": "+5 Book-Smarts",
    "cripple_armor": "Defense reduced to 0",
    "crippled": "Deals half melee damage",
    "crippling_attacks": "50% chance to shock on hit",
    "curse_covid": "Each turn: +20 rad or tox, chance to spread to nearby enemies",
    "curse_dot": "Stacking curse; deals increasing damage each turn",
    "curse_of_ham": "Attacks cost 50% more energy and deal 50% less damage",
    "dead_shot_daiquiri": "+5 STS, +5 gun damage, 50% ammo recovery",
    "disarmed": "Deals half melee damage",
    "distracted": "Next attack will miss",
    "divine_shield": "Each stack absorbs one hit",
    "empty_pockets": "Already been pickpocketed",
    "dot": "Taking damage each turn",
    "eagle_eye": "Unlimited vision range",
    "eating_food": "Eating; can't act until finished",
    "electric_root": "Rooted in place, can't move",
    "fear": "Forced to flee",
    "fiery_fists": "Melee attacks apply ignite",
    "fireball_shooter_buff": "Using consumables ignites nearest enemy",
    "five_loco": "2x rad gain, +33% good mutation chance",
    "force_sensitive": "+2 temp STR per 25 rad lost, reverts on expire",
    "forty_oz": "+5 Swagger per stack",
    "frozen": "Frozen solid; can't act, +99 damage resistance",
    "glass_shards": "1 damage per stack per turn",
    "glory_fists": "+5 STR, chance to permanently gain stats on hit",
    "cocoon": "Cocooned: immobilized, can't attack, venom bursts on break",
    "gouge": "Stunned until hit by the player",
    "greasy": "+3% dodge per stack",
    "green_drank": "Drinks heal HP/armor and remove rad/tox",
    "hamstrung": "-2 damage per stack on attacks",
    "hangover": "Stat penalties from drinking, applied next floor",
    "hard_boiled_egg": "Revive at half HP when killed",
    "hennessy": "-2 STR, +5 TOL, can double-smoke",
    "hex_slow": "-10 speed per stack",
    "hollow_points": "Next N gun shots deal +50% damage",
    "hollowed_out": "",
    "hot": "Healing over time",
    "hot_cheetos": "+2 to all stats per stack",
    "hot_pot": "Melee hits splash boiling oil to adjacent enemies",
    "hunger": "Melee heals 25% of damage dealt",
    "ignite": "1 fire damage per stack per turn",
    "invulnerable": "Can't take damage",
    "iron_lung_defense": "+defense",
    "iron_lung_dmg_reduction": "25% reduced outgoing damage",
    "jagermeister_buff": "+2 STR, +2 more per melee hit",
    "left_behind": "+1 DR per item left behind last floor",
    "leftovers_well_fed": "+1 power and spell damage per stack",
    "lesser_cloudkill": "1 damage/turn, -1 to all stats",
    "lifesteal": "Heal equal to melee damage dealt",
    "limoncello_chain_shock": "Shocking enemies chains to a nearby enemy",
    "loitering_tracker": "",
    "loitering_untargetable": "Enemies can't target you",
    "malt_liquor": "+8 STR, -2 CON, +20 temp HP per stack",
    "mana_drink": "Abilities heal 15% of damage dealt per stack",
    "milk_from_the_store": "All stats doubled",
    "minor_self_reflection": "10% chance to hurt yourself on melee hit",
    "mirror_entity": "Illusory copies absorb melee hits",
    "mogged": "Reduced swagger",
    "momentum": "Free movement per stack",
    "muffin_buff": "50% chance to save ability charges",
    "natty_light_buff": "+1 to all stats",
    "neuro_venom": "Stacking damage over time",
    "nigga_armor": "-1 incoming damage per stack",
    "nine_ring": "25% lifesteal on all damage",
    "outbreak": "Damage echoes 30% to other marked enemies nearby",
    "peace_of_mind": "+1 Street Smarts per stack",
    "phase_walk": "Walk through walls",
    "pipe_venom": "1 damage per turn",
    "platinum_reserve": "Triple max armor, restored to full",
    "protein_powder": "Permanent stat gains are doubled",
    "purge_infection": "-50% melee damage",
    "purple_halt_swagger": "+Swagger",
    "quick_eat": "Next food eaten instantly",
    "rabies": "-1 to all stats",
    "rad_nova_spell_buff": "+spell damage",
    "radiation_vent": "Vent radiates enemies and fires bolts",
    "rad_poison": "Gaining radiation each turn",
    "rainbow_rotgut": "Melee hits apply shocked, ignite, and chill to 3 random enemies in LOS",
    "rat_race": "+10 speed per stack",
    "red_drank": "Drinks last twice as long and cost no action",
    "root_beer": "Immobile, -10 incoming damage, +50 temp HP",
    "sangria": "+30% lifesteal per stack, slower movement",
    "shocked": "+10% damage taken per stack",
    "shortcut_channel": "Channeling a teleport",
    "sleeper_agent": "+1 damage, +2% lifesteal per stack; lost on move",
    "slipped": "Lost footing, lose next action",
    "slow": "Slowed, acting less often",
    "half_life_mark": "Detonates at 40% HP for AOE damage + radiation",
    "snipers_mark": "Taking 10% more damage permanently",
    "soul_count": "Tracking collected souls",
    "soul_empower": "+4 to a random stat",
    "soul_pair": "Damage dealt to player is reflected back",
    "sped": "Melee attacks cost half energy",
    "speed_boost": "Increased speed",
    "speedball": "+100 speed, +5 Swagger, 20% chance to lose turn",
    "spring_dodge": "+50% dodge chance",
    "stat_mod": "Temporarily modified stats",
    "stride": "50% reduced action cost",
    "stun": "Can't act",
    "surge": "+10 speed per stack",
    "swashbuckling": "+1 slash damage and +1% dodge per stack",
    "tetanus": "-1 to all stats per stack",
    "titan_form": "+50 temp HP, +50% melee damage, stuns on hit",
    "tox_spillover_aura": "Killed enemies spread their toxicity nearby",
    "toxic_harvest": "Gain 5 toxicity on kill",
    "unstable": "+2 melee/gun damage, hits irradiate enemies",
    "venom": "1 damage per stack per turn",
    "victory_rush": "Next melee attack has crit advantage",
    "virulent_vodka": "Damage applies toxicity; 10% for +1 CON on toxic kills",
    "voodoo_ham_stun": "Stunned",
    "web_stuck": "Stuck in a web, 50% escape chance per turn",
    "web_trail": "Leaving cobwebs behind when moving",
    "webbed": "-25 speed",
    "well_fed": "+damage per stack",
    "wet": "Extinguishes ignite",
    "white_gonster": "Chance to purge debuffs each turn, heals on purge",
    "white_out": "+8 Swagger, -25% damage dealt",
    "wizard_mind_bomb": "+5 Book-Smarts per stack",
    "wolf_spider_venom": "1 damage/turn, 15% miss chance",
    "yellowcake_buff": "10x mutation chance, blocks weak mutations",
    "zombie_rage": "+20% melee damage and +20 speed per stack",
    "zoned_out": "Immune to debuffs",
}


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Effect:
    """Base status effect — override hooks as needed."""

    id: str = "base"
    category: str = "debuff"   # "buff" | "debuff"  — drives UI colour
    priority: int = 0           # higher priority effects are checked first
    is_curse: bool = False      # If True, only one curse per monster (new replaces old)

    def __init__(self, duration: int = 1, custom_display_name: str = None, floor_duration: bool = False, **kwargs):
        self.duration = duration
        self.custom_display_name = custom_display_name
        self.floor_duration = floor_duration

    @property
    def expired(self) -> bool:
        if self.floor_duration:
            return False
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
    def short_description(self) -> str:
        """Return a short player-facing description."""
        return _PLAYER_DESCRIPTIONS.get(self.id, "")

    @property
    def display_duration(self) -> str:
        """Return human-readable duration string for the status panel."""
        if self.floor_duration:
            return "until floor end"
        d = self.duration
        return f"{d} turn{'s' if d != 1 else ''}"

    # ── Lifecycle hooks ──────────────────────────────────────────────────

    def apply(self, entity, engine):
        """Called once when the effect is first applied."""
        pass

    def tick(self, entity, engine):
        """Called once per game turn.  Decrement duration by default."""
        if not self.floor_duration:
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
    """Heal-over-time — heals amount HP per turn.
    Stacks with independent timers: each application adds its own timer."""
    id = "hot"
    category = "buff"
    priority = 5

    def __init__(self, duration: int = 5, amount: int = 2, **kwargs):
        super().__init__(duration=1, **kwargs)  # base duration unused; expiry via stack_timers
        self.amount = amount
        self.stack_timers: list = [duration]

    @property
    def duration(self) -> int:
        """Return the longest remaining stack timer (matches expected HoT duration)."""
        return max(self.stack_timers) if self.stack_timers else 0

    @duration.setter
    def duration(self, value: int):
        pass  # duration is derived from stack_timers; ignore direct sets

    @property
    def expired(self) -> bool:
        return len(self.stack_timers) == 0

    @property
    def stack_count(self):
        return len(self.stack_timers)

    @property
    def display_duration(self) -> str:
        if not self.stack_timers:
            return "0 turns"
        longest = max(self.stack_timers)
        return f"{longest} turn{'s' if longest != 1 else ''}"

    def tick(self, entity, engine):
        n = len(self.stack_timers)
        if entity.alive and n > 0:
            total_heal = self.amount * n
            entity.heal(total_heal)
            if entity == engine.player:
                if n > 1:
                    engine.messages.append(
                        f"{self.display_name} (x{n}) heals {total_heal} HP. "
                        f"({entity.hp}/{entity.max_hp} HP)"
                    )
                else:
                    engine.messages.append(
                        f"{self.display_name} heals {total_heal} HP. "
                        f"({entity.hp}/{entity.max_hp} HP)"
                    )
        self.stack_timers = [t - 1 for t in self.stack_timers if t - 1 > 0]

    def on_reapply(self, existing, entity, engine):
        new_dur = self.stack_timers[0] if self.stack_timers else 5
        existing.stack_timers.append(new_dur)


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
class VoodooHamStunEffect(Effect):
    """Voodoo Doll Curse of Ham detonation stun.
    Monster cannot accumulate energy and skips AI turn.
    Broken by player melee with 20% chance (handled in combat.py, like gouge)."""
    id = "voodoo_ham_stun"
    category = "debuff"
    priority = 100

    def modify_energy_gain(self, amount: float, entity) -> float:
        return 0.0

    def before_turn(self, entity, player, dungeon) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return "Voodoo Stun"


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
class RabiesEffect(Effect):
    """Rabies debuff — reduces all 6 base stats by 1 for the duration."""
    id = "rabies"
    category = "debuff"
    priority = 3

    _STATS = ("constitution", "strength", "street_smarts", "book_smarts", "tolerance", "swagger")

    def __init__(self, duration: int = 15, **kwargs):
        super().__init__(duration=duration, **kwargs)

    def apply(self, entity, engine):
        if entity == engine.player:
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, -1)

    def expire(self, entity, engine):
        if entity == engine.player:
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, 1)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


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
    """Fear — forced flee from the source.
    Player: engine._fear_flee() handles movement in the energy loop.
    Monsters: before_turn forces one step away from source each turn.
    50% chance to break when taking any damage from any source."""
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

    def before_turn(self, entity, player, dungeon) -> bool:
        """Monsters: flee one step away from fear source, skip normal AI."""
        if entity is player:
            return False  # player fear handled by engine._fear_flee()
        sx, sy = self.source_x, self.source_y
        mx, my = entity.x, entity.y
        dx = 0 if sx == mx else (-1 if sx > mx else 1)
        dy = 0 if sy == my else (-1 if sy > my else 1)
        # Try full diagonal, then cardinal fallbacks
        for try_dx, try_dy in [(dx, dy), (dx, 0), (0, dy)]:
            if try_dx == 0 and try_dy == 0:
                continue
            nx, ny = mx + try_dx, my + try_dy
            if dungeon.is_blocked(nx, ny):
                continue
            # Also prevent stacking on non-blocking entities (summons, etc.)
            if any(e.entity_type == "monster" and e.alive and e is not entity
                   for e in dungeon.get_entities_at(nx, ny)):
                continue
            entity.move(try_dx, try_dy)
            break
        return True  # skip normal AI turn whether or not we moved

    def modify_incoming_damage(self, damage: int, entity) -> int:
        """50% chance to break fear when taking any damage."""
        if damage > 0 and _random.random() < 0.50:
            self._broken_by_damage = True
            self.duration = 0  # mark expired so tick_all_effects removes it
        return damage

    def expire(self, entity, engine):
        if getattr(self, '_broken_by_damage', False):
            if entity is engine.player:
                engine.messages.append("The pain snaps you out of your fear!")
        else:
            if entity is engine.player:
                engine.messages.append("You are no longer frightened.")


@register
class DivineShieldEffect(Effect):
    """Buff: stacking divine shield. Each stack absorbs one direct hit.

    Ranged attacks (attacker not adjacent) have 50% chance to miss entirely
    without consuming a stack. Melee hits always consume a stack.
    Permanent — only removed when all stacks are consumed."""
    id = "divine_shield"
    category = "buff"
    priority = 60  # high priority — check before other damage modifiers

    def __init__(self, stacks: int = 1, **kwargs):
        kwargs.pop("duration", None)
        kwargs.pop("floor_duration", None)
        super().__init__(duration=9999, **kwargs)
        self.stacks = stacks

    def tick(self, entity, engine):
        # Permanent — never tick down duration
        pass

    @property
    def display_name(self) -> str:
        if self.stacks > 1:
            return f"Divine Shield x{self.stacks}"
        return "Divine Shield"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks

    def modify_incoming_damage(self, damage: int, entity) -> int:
        if damage <= 0 or self.stacks <= 0:
            return damage
        # Check if attacker is adjacent (melee) or ranged
        attacker = getattr(entity, '_current_attacker', None)
        if attacker is not None:
            dx = abs(attacker.x - entity.x)
            dy = abs(attacker.y - entity.y)
            if max(dx, dy) > 1 and _random.random() < 0.50:
                # Ranged dodge — no stack consumed
                return 0

        # Absorb the hit, consume one stack
        self.stacks -= 1
        if self.stacks <= 0:
            self.duration = 0  # trigger expiry
        return 0

    def expire(self, entity, engine):
        engine.messages.append([
            ("Divine Shield shattered!", (255, 255, 150)),
        ])


@register
class SoulCountEffect(Effect):
    """Buff (Amulet of Equivalent Exchange): tracks souls from kills. Display only."""
    id = "soul_count"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        kwargs.pop("duration", None)
        super().__init__(duration=9999, **kwargs)
        self.souls = 0

    def tick(self, entity, engine):
        # Permanent — sync soul count from amulet each tick for display
        from items import get_item_def
        neck = engine.neck
        if neck and "amulet_ee" in (get_item_def(neck.item_id) or {}).get("tags", []):
            self.souls = getattr(neck, "soul_count", 0)

    @property
    def display_name(self) -> str:
        return f"Souls: {self.souls}"

    def on_reapply(self, existing, entity, engine):
        pass  # Single instance only


@register
class SoulEmpowerEffect(Effect):
    """Buff (Soul Empower): +4 to a random stat until floor change."""
    id = "soul_empower"
    category = "buff"
    priority = 0

    def __init__(self, stat_name: str = "strength", **kwargs):
        kwargs.pop("duration", None)
        super().__init__(floor_duration=True, **kwargs)
        self.stat_name = stat_name
        self.amount = 4

    @property
    def display_name(self) -> str:
        _NAMES = {"constitution": "CON", "strength": "STR", "book_smarts": "BKS",
                   "street_smarts": "STS", "tolerance": "TOL", "swagger": "SWG"}
        return f"Soul Empower (+4 {_NAMES.get(self.stat_name, '?')})"

    def apply(self, entity, engine):
        engine.player_stats.add_temporary_stat_bonus(self.stat_name, self.amount)

    def on_reapply(self, existing, entity, engine):
        # Each use is a separate stat — apply as new effect instead
        # Remove reapply so a new instance is created
        engine.player_stats.add_temporary_stat_bonus(self.stat_name, self.amount)
        # Merge into existing by storing multiple stats
        if not hasattr(existing, '_extra_stats'):
            existing._extra_stats = []
        existing._extra_stats.append((self.stat_name, self.amount))

    def expire(self, entity, engine):
        engine.player_stats.add_temporary_stat_bonus(self.stat_name, -self.amount)
        for stat, amt in getattr(self, '_extra_stats', []):
            engine.player_stats.add_temporary_stat_bonus(stat, -amt)


@register
class SleeperAgentEffect(Effect):
    """Buff (Sleeper Agent weapon): +1 dmg and +2% lifesteal per stack. Lost on move. Max 10."""
    id = "sleeper_agent"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, **kwargs):
        kwargs.pop("duration", None)
        kwargs.pop("floor_duration", None)
        super().__init__(duration=9999, **kwargs)
        self.stacks = stacks

    def tick(self, entity, engine):
        # Permanent — never tick down
        pass

    @property
    def display_name(self) -> str:
        pct = self.stacks * 2
        if self.stacks > 1:
            return f"Sleeper Agent x{self.stacks} (+{self.stacks} dmg, {pct}% lifesteal)"
        return "Sleeper Agent (+1 dmg, 2% lifesteal)"

    def on_reapply(self, existing, entity, engine):
        existing.stacks = self.stacks

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if self.stacks <= 0:
            return
        heal = max(1, damage * self.stacks * 2 // 100)
        engine.player.heal(heal)
        engine.messages.append([
            ("Sleeper Agent: ", (100, 255, 100)),
            (f"+{heal} HP", (150, 255, 150)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])


@register
class MirrorEntityEffect(Effect):
    """Mirror Entity — illusory copies absorb melee hits.

    Stacks represent mirror copies. When attacked, chance to hit real player
    is 1/(stacks+1). If a copy is hit, damage is nullified and one stack is
    consumed. Effect expires when duration ends or all stacks are consumed."""
    id = "mirror_entity"
    category = "buff"
    priority = 50

    def __init__(self, duration: int = 100, stacks: int = 3, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Mirror Entity x{self.stacks}" if self.stacks > 1 else "Mirror Entity"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        """Override: replace with new stacks and reset duration."""
        existing.duration = self.duration
        existing.stacks = self.stacks
        engine.messages.append(f"Mirror Entity refreshed! ({existing.stacks} copies)")

    def modify_incoming_damage(self, damage: int, entity) -> int:
        if damage <= 0 or self.stacks <= 0:
            return damage
        # Chance to hit real player: 1 / (stacks + 1)
        if _random.random() < 1.0 / (self.stacks + 1):
            return damage  # real hit — full damage, no stack loss
        # Mirror copy absorbs the hit
        self.stacks -= 1
        if self.stacks <= 0:
            self.duration = 0  # expire the effect
        return 0  # damage nullified

    def expire(self, entity, engine):
        if self.stacks <= 0:
            engine.messages.append("Your last mirror copy shatters!")
        else:
            engine.messages.append("Your mirror copies fade away.")


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
        entity.power -= self.power_bonus


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
    """Debuff: each stack reduces energy gain by 15% (multiplicative).
    At 3 stacks ~61% speed, 5 stacks ~44%. Removed when ignite is applied."""
    id = "chill"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 10, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Chill"

    @property
    def stack_count(self):
        return self.stacks

    def modify_energy_gain(self, amount: float, entity) -> float:
        """Each stack multiplies energy gain by 0.85 (15% slower per stack)."""
        return amount * (0.85 ** self.stacks)

    def apply(self, entity, engine):
        # Cryomancy XP: 10 per chill stack applied to a non-player entity
        if entity is not engine.player:
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Cryomancy", 10, bksmt)

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.messages.append(f"You feel chillier! (Chill x{existing.stacks})")
        else:
            # Cryomancy XP: 10 per chill stack applied to a non-player entity
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Cryomancy", 10, bksmt)


@register
class FrozenEffect(Effect):
    """Debuff: entity is frozen solid. Can't move, can't attack, +99 flat damage resistance.
    Loses 1 stack per turn. Expires when stacks reach 0. Removed by ignite."""
    id = "frozen"
    category = "debuff"
    priority = 100

    def __init__(self, duration: int = 99, stacks: int = 5, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Frozen"

    @property
    def stack_count(self):
        return self.stacks

    def before_turn(self, entity, player, dungeon) -> bool:
        """Skip the entity's turn entirely."""
        return True

    def modify_energy_gain(self, amount: float, entity) -> float:
        """Can't accumulate energy."""
        return 0.0

    def modify_incoming_damage(self, damage: int, entity) -> int:
        """99 flat damage resistance."""
        return max(0, damage - 99)

    def tick(self, entity, engine):
        self.stacks -= 1
        if self.stacks <= 0:
            self.duration = 0

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        # Cryomancy XP: 10 per frozen stack applied to a non-player entity
        if entity is not engine.player:
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Cryomancy", 10 * self.stacks, bksmt)

    def apply(self, entity, engine):
        # Cryomancy XP: 10 per frozen stack applied to a non-player entity
        if entity is not engine.player:
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Cryomancy", 10 * self.stacks, bksmt)


def _chain_shock_proc(shocked_entity, engine):
    """Limoncello Chain Shock: if player has the buff, shock one random different enemy within 5 tiles."""
    has_chain = any(getattr(e, 'id', '') == 'limoncello_chain_shock'
                    for e in engine.player.status_effects)
    if not has_chain:
        return
    # Prevent recursive chaining by checking a guard flag
    if getattr(engine, '_chain_shock_active', False):
        return
    engine._chain_shock_active = True
    try:
        candidates = []
        for ent in engine.dungeon.get_monsters():
            if ent is shocked_entity or not ent.alive:
                continue
            dist = max(abs(ent.x - shocked_entity.x), abs(ent.y - shocked_entity.y))
            if dist <= 5:
                candidates.append(ent)
        if candidates:
            target = _random.choice(candidates)
            apply_effect(target, engine, "shocked", duration=10, stacks=1, silent=True)
            engine.messages.append([
                ("Chain Shock! ", (255, 255, 80)),
                (f"Lightning arcs to {target.name}!", (255, 240, 150)),
            ])
    finally:
        engine._chain_shock_active = False


@register
class ShockedEffect(Effect):
    """Debuff: +10% increased damage taken per stack (additive with toxicity). No stack cap. 10t duration."""
    id = "shocked"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 10, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Shocked"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        # Electrodynamics XP: 10 per shocked stack applied to a non-player entity
        if entity is not engine.player:
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Electrodynamics", 10, bksmt)
            _chain_shock_proc(entity, engine)

    # NOTE: Shocked no longer uses modify_incoming_damage. Its damage amp is applied
    # additively with toxicity in combat.py _apply_toxicity_and_shocked() instead.

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1  # no cap
        existing.duration = max(existing.duration, self.duration)
        # Electrodynamics XP: 10 per shocked stack applied to a non-player entity
        if entity is not engine.player:
            bksmt = engine.player_stats.effective_book_smarts
            engine.skills.gain_potential_exp("Electrodynamics", 10, bksmt)
            _chain_shock_proc(entity, engine)


@register
class ElectricRootEffect(Effect):
    """Debuff: rooted in place by electricity. Cannot move for duration."""
    id = "electric_root"
    category = "debuff"
    priority = 90

    def __init__(self, duration: int = 5, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Rooted"

    def modify_movement(self, dx, dy, entity, player, dungeon):
        if dx == 0 and dy == 0:
            return dx, dy
        return 0, 0

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class LimoncelloChainShockEffect(Effect):
    """Buff (Limoncello): when you apply Shocked to an enemy, also shock one random different enemy within 5 tiles. 100 turns."""
    id = "limoncello_chain_shock"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Chain Shock"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class SurgeEffect(Effect):
    """Buff: +10 speed per stack. Stacks refresh duration. Gained from lightning spell hits (Electro L4)."""
    id = "surge"
    category = "buff"
    priority = 5

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks
        self._speed_granted = 0

    @property
    def display_name(self) -> str:
        return f"Surge x{self.stacks}"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        self._speed_granted = 10 * self.stacks
        entity.speed += self._speed_granted

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)
        entity.speed += 10
        existing._speed_granted += 10

    def expire(self, entity, engine):
        entity.speed -= self._speed_granted
        self._speed_granted = 0


@register
class TetanusEffect(Effect):
    """Debuff: -1 to all stats (power, defense). Stacks and refreshes duration."""
    id = "tetanus"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 10, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks
        self._applied_stacks = 0

    @property
    def display_name(self) -> str:
        return f"Tetanus x{self.stacks}"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        entity.power -= 1
        entity.defense -= 1
        self._applied_stacks = 1

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)
        entity.power -= 1
        entity.defense -= 1
        existing._applied_stacks += 1

    def expire(self, entity, engine):
        entity.power += self._applied_stacks
        entity.defense += self._applied_stacks
        self._applied_stacks = 0


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
    """Buff (Jungle Boyz 81-100): +5 STR, 5% chance per attack to permanently gain +1 to a random stat."""
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

    def apply(self, entity, engine):
        engine.player_stats.add_temporary_stat_bonus("strength", 5)

    def expire(self, entity, engine):
        engine.player_stats.add_temporary_stat_bonus("strength", -5)

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
                # Glass Shards from Broken Bong (stabbing weapon) — award Stabbing XP
                engine._gain_melee_xp("Stabbing", n)
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
        super().__init__(floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Hangover"

    @property
    def stack_count(self):
        return self.stacks

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
    """Buff (40oz bottle): +5 Swagger per stack, independent timers."""
    id = "forty_oz"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.timers: list[int] = [duration]
        self._active_stacks = 0

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"40oz Buzz x{n}" if n > 1 else "40oz Buzz"

    @property
    def stack_count(self):
        return len(self.timers)

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)
            self._active_stacks = 1

    def expire(self, entity, engine):
        if self._active_stacks > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5 * self._active_stacks)
            self._active_stacks = 0

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(self.duration)
        existing.duration = max(existing.timers)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)
            existing._active_stacks += 1

    def tick(self, entity, engine):
        prev = len(self.timers)
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        expired = prev - len(self.timers)
        if expired > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5 * expired)
            self._active_stacks -= expired
        self.duration = max(self.timers) if self.timers else 0


@register
class SpeedballEffect(Effect):
    """Buff (Speedball): +100 speed, +5 Swagger, 20% chance to lose turn per stack, independent timers."""
    id = "speedball"
    category = "buff"
    priority = 50

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.timers: list[int] = [duration]
        self._active_stacks = 0

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"Speedball x{n}" if n > 1 else f"Speedball"

    @property
    def stack_count(self):
        return len(self.timers)

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)
            self._active_stacks = 1

    def expire(self, entity, engine):
        if self._active_stacks > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5 * self._active_stacks)
            self._active_stacks = 0

    def modify_energy_gain(self, energy: float, entity) -> float:
        return energy + 100 * len(self.timers)

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(self.duration)
        existing.duration = max(existing.timers)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)
            existing._active_stacks += 1

    def tick(self, entity, engine):
        prev = len(self.timers)
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        expired = prev - len(self.timers)
        if expired > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5 * expired)
            self._active_stacks -= expired
        self.duration = max(self.timers) if self.timers else 0


@register
class ProteinPowderEffect(Effect):
    """Buff (Protein Powder): whenever you gain a permanent stat increase, gain an additional random permanent stat increase. Lasts until floor change."""
    id = "protein_powder"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(floor_duration=True, **kwargs)
        self._callback = None

    @property
    def display_name(self) -> str:
        return "Swole"

    def apply(self, entity, engine):
        import random as _rng
        ALL_STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]

        # Temporary STR boost (lasts until floor change): +2 base + 2 per Munching level
        munching_level = engine.skills.get("Munching").level
        self._str_bonus = 2 + 2 * munching_level
        engine.player_stats.add_temporary_stat_bonus("strength", self._str_bonus)
        engine._sync_player_max_hp()
        engine.messages.append([
            ("Protein Powder! ", (255, 200, 100)),
            (f"+{self._str_bonus} Strength (base 2 + {munching_level} Munching)", (100, 255, 100)),
        ])

        def _on_stat_increase(stat: str, amount: int):
            bonus_stat = _rng.choice(ALL_STATS)
            engine.player_stats.modify_base_stat(bonus_stat, 1, _from_callback=True)
            engine._sync_player_max_hp()
            stat_display = bonus_stat.replace("_", " ").title().replace("Book Smarts", "Book-Smarts").replace("Street Smarts", "Street-Smarts")
            engine.messages.append([
                ("Protein Powder! ", (255, 200, 100)),
                (f"+1 {stat_display}", (100, 255, 100)),
            ])

        self._callback = _on_stat_increase
        engine.player_stats._on_stat_increase_callbacks.append(self._callback)

    def expire(self, entity, engine):
        if self._callback and self._callback in engine.player_stats._on_stat_increase_callbacks:
            engine.player_stats._on_stat_increase_callbacks.remove(self._callback)
        # Revert the temporary STR bonus
        if hasattr(self, '_str_bonus') and self._str_bonus:
            engine.player_stats.add_temporary_stat_bonus("strength", -self._str_bonus)
            engine._sync_player_max_hp()

    def on_reapply(self, existing, entity, engine):
        # Stack the STR bonus; don't add another callback
        munching_level = engine.skills.get("Munching").level
        extra_str = 2 + 2 * munching_level
        existing._str_bonus += extra_str
        engine.player_stats.add_temporary_stat_bonus("strength", extra_str)
        engine._sync_player_max_hp()
        engine.messages.append([
            ("Protein Powder! ", (255, 200, 100)),
            (f"+{extra_str} Strength (total +{existing._str_bonus})", (100, 255, 100)),
        ])


@register
class MuffinBuffEffect(Effect):
    """Buff (Muffin): 50% chance to not consume a charge when using a limited-charge ability.
    Also grants +2 + 2*Munching Book-Smarts (stackable). Lasts until floor change."""
    id = "muffin_buff"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(floor_duration=True, **kwargs)
        self._bks_bonus = 0

    @property
    def display_name(self) -> str:
        return "Muffin Magic"

    def apply(self, entity, engine):
        munching_level = engine.skills.get("Munching").level
        self._bks_bonus = 2 + 2 * munching_level
        engine.player_stats.add_temporary_stat_bonus("book_smarts", self._bks_bonus)
        engine.messages.append([
            ("Muffin Magic! ", (255, 220, 130)),
            (f"+{self._bks_bonus} Book-Smarts (base 2 + {munching_level} Munching)", (100, 255, 100)),
        ])

    def expire(self, entity, engine):
        if self._bks_bonus:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", -self._bks_bonus)

    def on_reapply(self, existing, entity, engine):
        # Stack the BKS bonus; don't duplicate the charge-preserve effect
        munching_level = engine.skills.get("Munching").level
        extra_bks = 2 + 2 * munching_level
        existing._bks_bonus += extra_bks
        engine.player_stats.add_temporary_stat_bonus("book_smarts", extra_bks)
        engine.messages.append([
            ("Muffin Magic! ", (255, 220, 130)),
            (f"+{extra_bks} Book-Smarts (total +{existing._bks_bonus})", (100, 255, 100)),
        ])


@register
class HardBoiledEggEffect(Effect):
    """Buff (Hard Boiled Egg): death save — if reduced to 0 HP, revive at half HP and consume 1 stack."""
    id = "hard_boiled_egg"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        if self.stacks > 1:
            return f"Second Wind x{self.stacks}"
        return "Second Wind"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        existing.duration = max(existing.duration, self.duration)

    def on_death_save(self, entity, engine):
        """Consume 1 stack and revive at half HP. Returns True if death prevented."""
        entity.hp = entity.max_hp // 2
        entity.alive = True
        self.stacks -= 1
        engine.messages.append([
            ("Second Wind! ", (255, 255, 100)),
            ("Revived at half HP!", (100, 255, 100)),
        ])
        if self.stacks <= 0:
            entity.status_effects.remove(self)
            engine.messages.append([
                ("Second Wind fades.", (180, 180, 180)),
            ])
        else:
            engine.messages.append([
                (f"({self.stacks} stack{'s' if self.stacks != 1 else ''} remaining)", (180, 180, 180)),
            ])
        return True


@register
class EagleEyeEffect(Effect):
    """Buff (Carrot Cake): unlimited FOV radius. Lasts until floor change. Does not stack."""
    id = "eagle_eye"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Eagle Eye"

    def apply(self, entity, engine):
        engine.fov_radius = 99
        engine._compute_fov()

    def expire(self, entity, engine):
        from config import FOV_RADIUS
        from items import get_item_def
        fov_penalty = 0
        if engine.feet is not None:
            defn = get_item_def(engine.feet.item_id)
            if defn:
                fov_penalty += defn.get("fov_penalty", 0)
        engine.fov_radius = max(1, FOV_RADIUS - fov_penalty)
        engine._compute_fov()

    def on_reapply(self, existing, entity, engine):
        pass  # Does not stack — already active


@register
class YellowcakeBuff(Effect):
    """Buff (Yellowcake): 10x mutation chance, blocks weak-tier mutations. 50 turns."""
    id = "yellowcake_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Critical Mass"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class BananaPuddingShield(Effect):
    """Buff (Banana Pudding): removes half player's radiation, grants that much temp HP for 100 turns."""
    id = "banana_pudding"
    category = "buff"
    priority = 0

    def __init__(self, temp_hp_amount: int = 0, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._temp_hp_granted = temp_hp_amount

    @property
    def display_name(self) -> str:
        return "Potassium Shield"

    def apply(self, entity, engine):
        if self._temp_hp_granted > 0:
            entity.temp_hp += self._temp_hp_granted

    def tick(self, entity, engine):
        if self._temp_hp_granted > 0 and entity.temp_hp <= 0:
            self.duration = 0
            return
        self.duration -= 1

    def expire(self, entity, engine):
        pass  # temp HP stays until consumed or naturally lost

    def on_reapply(self, existing, entity, engine):
        # Stack: add new temp HP and refresh duration
        if self._temp_hp_granted > 0:
            entity.temp_hp += self._temp_hp_granted
            existing._temp_hp_granted += self._temp_hp_granted
        existing.duration = max(existing.duration, self.duration)


@register
class ScavengersEyeEffect(Effect):
    """Buff (Kimchi): 50% chance on kill to drop a random lesser consumable (radbar, rad_away, altoid, asbestos)."""
    id = "scavengers_eye"
    category = "buff"
    priority = 0

    _DROP_TABLE = ["radbar", "rad_away", "altoid", "asbestos"]

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Scavenger's Eye"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class PhaseWalkEffect(Effect):
    """Buff (Jolly Rancher): walk through walls. On expire, if inside a wall, teleport to random floor tile."""
    id = "phase_walk"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 12, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Phase Walk"

    def expire(self, entity, engine):
        from config import TILE_WALL
        # Check if player is inside a wall when buff expires
        if engine.dungeon.tiles[entity.y][entity.x] == TILE_WALL:
            import random as _rng
            # Find all floor tiles on the current floor
            floor_tiles = []
            for fy in range(engine.dungeon.height):
                for fx in range(engine.dungeon.width):
                    if not engine.dungeon.is_terrain_blocked(fx, fy):
                        floor_tiles.append((fx, fy))
            if floor_tiles:
                tx, ty = _rng.choice(floor_tiles)
                entity.x, entity.y = tx, ty
                engine._compute_fov()
                engine.messages.append([
                    ("Phase Walk expires! ", (255, 100, 200)),
                    ("You materialize on a random tile!", (255, 200, 255)),
                ])
            else:
                engine.messages.append("Phase Walk expires!")
        else:
            engine.messages.append([
                ("Phase Walk fades.", (200, 150, 200)),
            ])

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class PlatinumReserveEffect(Effect):
    """Buff (Platinum Reserve): triples max armor, restores to full for 100 turns. On expire, remove bonus and cap armor."""
    id = "platinum_reserve"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.armor_bonus_applied = 0

    @property
    def display_name(self) -> str:
        return "Platinum Reserve"

    def apply(self, entity, engine):
        if entity == engine.player:
            # Snapshot current max armor, then add 2x to triple it
            current_max = engine._compute_player_max_armor()
            self.armor_bonus_applied = current_max * 2
            engine.player_stats.temporary_armor_bonus += self.armor_bonus_applied
            new_max = engine._compute_player_max_armor()
            engine.player.max_armor = new_max
            engine.player.armor = new_max

    def on_reapply(self, existing, entity, engine):
        # Separate stacks: remove old bonus, recalculate with new triple
        if entity == engine.player:
            engine.player_stats.temporary_armor_bonus -= existing.armor_bonus_applied
            current_max = engine._compute_player_max_armor()
            existing.armor_bonus_applied = current_max * 2
            engine.player_stats.temporary_armor_bonus += existing.armor_bonus_applied
            new_max = engine._compute_player_max_armor()
            engine.player.max_armor = new_max
            engine.player.armor = new_max
            existing.duration = max(existing.duration, self.duration)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.temporary_armor_bonus -= self.armor_bonus_applied
            normal_max = engine._compute_player_max_armor()
            engine.player.max_armor = normal_max
            if engine.player.armor > normal_max:
                engine.player.armor = normal_max


@register
class MaltLiquorEffect(Effect):
    """Buff (Malt Liquor): +8 STR, -2 CON, +20 temp HP per stack, independent timers."""
    id = "malt_liquor"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.timers: list[int] = [duration]
        self._active_stacks = 0

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"Malt Liquor x{n}" if n > 1 else "Malt Liquor"

    @property
    def stack_count(self):
        return len(self.timers)

    def _apply_one_stack(self, engine):
        engine.player_stats.add_temporary_stat_bonus("strength", 8)
        engine.player_stats.add_temporary_stat_bonus("constitution", -2)
        engine._sync_player_max_hp()
        engine.player.temp_hp = getattr(engine.player, 'temp_hp', 0) + 20

    def _remove_stacks(self, engine, count):
        engine.player_stats.add_temporary_stat_bonus("strength", -8 * count)
        engine.player_stats.add_temporary_stat_bonus("constitution", 2 * count)
        engine._sync_player_max_hp()

    def apply(self, entity, engine):
        if entity == engine.player:
            self._apply_one_stack(engine)
            self._active_stacks = 1

    def expire(self, entity, engine):
        if self._active_stacks > 0 and entity == engine.player:
            self._remove_stacks(engine, self._active_stacks)
            self._active_stacks = 0

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(self.duration)
        existing.duration = max(existing.timers)
        if entity == engine.player:
            existing._apply_one_stack(engine)
            existing._active_stacks += 1

    def tick(self, entity, engine):
        prev = len(self.timers)
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        expired = prev - len(self.timers)
        if expired > 0 and entity == engine.player:
            self._remove_stacks(engine, expired)
            self._active_stacks -= expired
        self.duration = max(self.timers) if self.timers else 0


@register
class WizardMindBombEffect(Effect):
    """Buff (Wizard Mind-Bomb): +5 Book-Smarts per stack, independent timers."""
    id = "wizard_mind_bomb"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.timers: list[int] = [duration]
        self._active_stacks = 0

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"Wizard Mind Bomb x{n}" if n > 1 else "Wizard Mind Bomb"

    @property
    def stack_count(self):
        return len(self.timers)

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", 5)
            self._active_stacks = 1

    def expire(self, entity, engine):
        if self._active_stacks > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", -5 * self._active_stacks)
            self._active_stacks = 0

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(self.duration)
        existing.duration = max(existing.timers)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", 5)
            existing._active_stacks += 1

    def tick(self, entity, engine):
        prev = len(self.timers)
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        expired = prev - len(self.timers)
        if expired > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("book_smarts", -5 * expired)
            self._active_stacks -= expired
        self.duration = max(self.timers) if self.timers else 0


@register
class FireballShooterBuff(Effect):
    """Buff (Fireball Shooter): on consumable use, nearest visible enemy gains 1 ignite stack."""
    id = "fireball_shooter_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Fireball Breath"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class NattyLightBuff(Effect):
    """Buff (Natty Light): +1 all stats for 100 turns."""
    id = "natty_light_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Natty Buzz"

    def apply(self, entity, engine):
        engine.player_stats.temporary_stat_bonuses["constitution"] = \
            engine.player_stats.temporary_stat_bonuses.get("constitution", 0) + 1
        engine.player_stats.temporary_stat_bonuses["strength"] = \
            engine.player_stats.temporary_stat_bonuses.get("strength", 0) + 1
        engine.player_stats.temporary_stat_bonuses["book_smarts"] = \
            engine.player_stats.temporary_stat_bonuses.get("book_smarts", 0) + 1
        engine.player_stats.temporary_stat_bonuses["street_smarts"] = \
            engine.player_stats.temporary_stat_bonuses.get("street_smarts", 0) + 1
        engine.player_stats.temporary_stat_bonuses["tolerance"] = \
            engine.player_stats.temporary_stat_bonuses.get("tolerance", 0) + 1
        engine.player_stats.temporary_stat_bonuses["swagger"] = \
            engine.player_stats.temporary_stat_bonuses.get("swagger", 0) + 1

    def expire(self, entity, engine):
        for stat in ("constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"):
            engine.player_stats.temporary_stat_bonuses[stat] = \
                engine.player_stats.temporary_stat_bonuses.get(stat, 0) - 1

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class JagermeisterBuff(Effect):
    """Buff (Jagermeister): +2 STR, +2 more STR per melee hit. 15 turns."""
    id = "jagermeister_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 15, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._str_bonus = 0

    @property
    def display_name(self) -> str:
        return f"Jager Rage (+{self._str_bonus} STR)"

    def apply(self, entity, engine):
        self._str_bonus = 2
        engine.player_stats.add_temporary_stat_bonus("strength", 2)

    def expire(self, entity, engine):
        if self._str_bonus > 0:
            engine.player_stats.add_temporary_stat_bonus("strength", -self._str_bonus)

    def on_player_melee_hit(self, engine, defender, damage):
        self._str_bonus += 2
        engine.player_stats.add_temporary_stat_bonus("strength", 2)
        engine.messages.append([
            ("JAGER RAGE! ", (200, 100, 40)),
            (f"+2 STR! (total +{self._str_bonus})", (255, 180, 60)),
        ])

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class ButterbeerBuff(Effect):
    """Buff (Butterbeer): +25% briskness for 25 turns."""
    id = "butterbeer_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 25, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Butterbeer Buzz"

    def apply(self, entity, engine):
        engine.player_stats.temporary_briskness += 25

    def expire(self, entity, engine):
        engine.player_stats.temporary_briskness -= 25

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class BlueLagoonBuff(Effect):
    """Buff (Blue Lagoon): on consumable use, nearest visible enemy gains 1 chill stack."""
    id = "blue_lagoon_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Frozen Breath"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class HennessyEffect(Effect):
    """Buff (Homemade Hennessy): -2 STR, +5 TOL per stack, enables double smoking, independent timers."""
    id = "hennessy"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.timers: list[int] = [duration]
        self._active_stacks = 0

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"Hennessy High x{n}" if n > 1 else "Hennessy High"

    @property
    def stack_count(self):
        return len(self.timers)

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", -2)
            engine.player_stats.add_temporary_stat_bonus("tolerance", 5)
            self._active_stacks = 1

    def expire(self, entity, engine):
        if self._active_stacks > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", 2 * self._active_stacks)
            engine.player_stats.add_temporary_stat_bonus("tolerance", -5 * self._active_stacks)
            self._active_stacks = 0

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(self.duration)
        existing.duration = max(existing.timers)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", -2)
            engine.player_stats.add_temporary_stat_bonus("tolerance", 5)
            existing._active_stacks += 1

    def tick(self, entity, engine):
        prev = len(self.timers)
        self.timers = [t - 1 for t in self.timers]
        self.timers = [t for t in self.timers if t > 0]
        expired = prev - len(self.timers)
        if expired > 0 and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", 2 * expired)
            engine.player_stats.add_temporary_stat_bonus("tolerance", -5 * expired)
            self._active_stacks -= expired
        self.duration = max(self.timers) if self.timers else 0


@register
class RedDrankEffect(Effect):
    """Buff (Red Drank): drinks consumed while active have doubled duration, cost no action, and grant +100 energy."""
    id = "red_drank"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 200, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Red Drank"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class GreenDrankEffect(Effect):
    """Buff (Green Drank): each drink consumed heals 20 HP/armor, removes 20 rad/tox, removes a random debuff. Stacks. Lasts until floor change."""
    id = "green_drank"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, **kwargs):
        kwargs.pop("duration", None)
        super().__init__(floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        if self.stacks > 1:
            return f"Green Drank x{self.stacks}"
        return "Green Drank"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks


@register
class ManaDrinkEffect(Effect):
    """Buff (Mana Drink): abilities heal 15% of damage dealt per stack, remove 1 tox/rad per trigger. 100 turns."""
    id = "mana_drink"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Mana Drink x{self.stacks}" if self.stacks > 1 else "Mana Drink"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        existing.duration = max(existing.duration, self.duration)


@register
class VirulentVodkaEffect(Effect):
    """Buff (Virulent Vodka): direct player damage applies max(dmg, 10) toxicity per hit per stack. 10% chance +1 CON on killing enemy with 100+ tox."""
    id = "virulent_vodka"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Virulent Vodka x{self.stacks}" if self.stacks > 1 else "Virulent Vodka"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        existing.duration = max(existing.duration, self.duration)

    def on_player_melee_hit(self, engine, defender, damage):
        """Apply toxicity on melee hit."""
        _apply_virulent_vodka_tox(engine, defender, damage, self.stacks)


def _apply_virulent_vodka_tox(engine, target, damage, stacks):
    """Apply virulent vodka toxicity to a target. Called for any direct player damage."""
    from combat import add_toxicity
    import random as _rng
    tox_amount = max(damage, 10) * stacks
    if not hasattr(target, 'toxicity'):
        target.toxicity = 0
    add_toxicity(engine, target, tox_amount, from_player=True)

    # Check for +1 CON on kill with 100+ tox
    if not target.alive and getattr(target, 'toxicity', 0) >= 100:
        if _rng.random() < 0.10:
            engine.player_stats.modify_base_stat("constitution", 1)
            engine.player.max_hp = engine.player_stats.max_hp
            engine.messages.append([
                ("Virulent Kill! ", (0, 200, 0)),
                ("+1 permanent CON!", (100, 255, 100)),
            ])


@register
class RainbowRotgutEffect(Effect):
    """Buff (Rainbow Rotgut): on melee hit, apply 1 stack each of ignite, shocked, and chill
    to 3 random enemies in LOS. Same target can be hit multiple times."""
    id = "rainbow_rotgut"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Rainbow Rotgut"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        from ai import _has_los
        # Gather all visible living monsters in LOS
        px, py = engine.player.x, engine.player.y
        visible = engine.dungeon.visible
        targets = [
            e for e in engine.dungeon.entities
            if e.entity_type == "monster" and e.alive
            and visible[e.y, e.x]
            and _has_los(engine.dungeon, px, py, e.x, e.y)
        ]
        if not targets:
            return
        # Pick 3 random targets (with replacement — same target can be hit multiple times)
        picks = _random.choices(targets, k=3)
        effects_applied = []  # (effect_name, target_name)
        for i, target in enumerate(picks):
            if i == 0:
                # Shocked
                eff = apply_effect(target, engine, "shocked", duration=5, stacks=1, silent=True)
                if eff:
                    effects_applied.append(("shocked", target.name))
            elif i == 1:
                # Ignite
                dur = engine._player_ignite_duration()
                eff = apply_effect(target, engine, "ignite", duration=dur, stacks=1, silent=True)
                if eff:
                    effects_applied.append(("ignited", target.name))
            else:
                # Chill
                eff = apply_effect(target, engine, "chill", duration=10, stacks=1, silent=True)
                if eff:
                    effects_applied.append(("chilled", target.name))
        if effects_applied:
            summary = ", ".join(f"{name} {eff}" for eff, name in effects_applied)
            engine.messages.append(f"Rainbow Rotgut: {summary}!")


@register
class FiveLocoEffect(Effect):
    """Buff (Five Loco): 2x rad gain, +33% good mutation chance. Does not stack. Lasts until floor change."""
    id = "five_loco"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        kwargs.pop("duration", None)
        kwargs.pop("stacks", None)
        super().__init__(floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Five Loco"

    def apply(self, entity, engine):
        engine.player_stats.rad_gain_multiplier_bonus += 1.0
        engine.player_stats.good_mutation_multiplier += 0.33

    def on_reapply(self, existing, entity, engine):
        # Does not stack — just refresh duration
        pass

    def expire(self, entity, engine):
        engine.player_stats.rad_gain_multiplier_bonus -= 1.0
        engine.player_stats.good_mutation_multiplier -= 0.33


@register
class WhiteGonsterEffect(Effect):
    """Buff (White Gonster): 30%/turn purge random debuff, heal = debuff duration (cap 50). +5 Swagger. Stacks separately."""
    id = "white_gonster"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"White Gonster x{self.stacks}" if self.stacks > 1 else "White Gonster"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -5 * self.stacks)

    def tick(self, entity, engine):
        import random as _rng
        # Each stack gets its own 30% roll
        for _ in range(self.stacks):
            if _rng.random() < 0.30:
                _white_gonster_purge(entity, engine)
        self.duration -= 1


def _white_gonster_purge(entity, engine):
    """Purge one random debuff from entity, heal HP = debuff's remaining duration (cap 50)."""
    import random as _rng
    debuffs = [e for e in entity.status_effects if e.category == "debuff"]
    if not debuffs:
        return
    target_debuff = _rng.choice(debuffs)
    # Determine heal amount: duration of the debuff, capped at 50
    heal_amount = min(getattr(target_debuff, 'duration', 0), 50)
    # Remove the debuff and run its cleanup
    debuff_name = target_debuff.display_name
    entity.status_effects.remove(target_debuff)
    target_debuff.expire(entity, engine)
    # Heal
    if heal_amount > 0:
        entity.heal(heal_amount)
    if entity == engine.player:
        engine.messages.append([
            ("White Gonster purges ", (255, 255, 255)),
            (debuff_name, (255, 100, 100)),
            (f"! +{heal_amount} HP", (100, 255, 100)),
        ])


@register
class DeadShotDaiquiriEffect(Effect):
    """Buff (Dead Shot Daiquiri): +5 STS, +5 gun damage, 50% ammo recovery per bullet. Stacks separately."""
    id = "dead_shot_daiquiri"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, duration: int = 100, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Dead Shot Daiquiri x{self.stacks}" if self.stacks > 1 else "Dead Shot Daiquiri"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", 5)

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks
        existing.duration = max(existing.duration, self.duration)
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", 5)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("street_smarts", -5 * self.stacks)


def get_dead_shot_stacks(engine):
    """Return total Dead Shot Daiquiri stacks on the player, or 0."""
    for e in engine.player.status_effects:
        if getattr(e, 'id', '') == 'dead_shot_daiquiri':
            return e.stacks
    return 0


def dead_shot_gun_bonus(engine):
    """Return flat gun damage bonus from Dead Shot Daiquiri (+5 per stack)."""
    return 5 * get_dead_shot_stacks(engine)


def unstable_gun_bonus(engine):
    """Return flat gun damage bonus from Unstable effect (+2 while active)."""
    for e in engine.player.status_effects:
        if e.id == "unstable":
            return 2
    return 0


def unstable_gun_irradiate(engine, target):
    """If player has Unstable buff, irradiate gun hit target for 10 rad."""
    for e in engine.player.status_effects:
        if e.id == "unstable":
            from combat import add_radiation
            add_radiation(engine, target, 10)
            return


def dead_shot_ammo_recovery(engine, num_shots, ammo_type):
    """Roll 50% per bullet per stack for ammo recovery. Returns count recovered."""
    import random as _rng
    stacks = get_dead_shot_stacks(engine)
    if stacks <= 0:
        return 0
    _AMMO_TYPE_TO_ITEM = {"light": "light_rounds", "medium": "medium_rounds", "heavy": "heavy_rounds"}
    item_id = _AMMO_TYPE_TO_ITEM.get(ammo_type)
    if not item_id:
        return 0
    recovered = 0
    for _ in range(num_shots):
        # Each stack gives an independent 50% chance
        for _ in range(stacks):
            if _rng.random() < 0.50:
                recovered += 1
                break  # max 1 recovery per bullet
    if recovered > 0:
        from inventory_mgr import _add_item_to_inventory
        _add_item_to_inventory(engine, item_id, quantity=recovered)
        item_name = {"light": "Light Rounds", "medium": "Medium Rounds", "heavy": "Heavy Rounds"}[ammo_type]
        engine.messages.append([
            ("Dead Shot! ", (255, 200, 100)),
            (f"+{recovered} {item_name} recovered", (200, 255, 200)),
        ])
    return recovered


@register
class AlcoSeltzerToxResistEffect(Effect):
    """Buff (Alco-Seltzer): 100% tox resistance for rest of floor."""
    id = "alco_seltzer_tox_resist"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        kwargs.pop("duration", None)
        super().__init__(floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Alco-Seltzer Tox Resist"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_tox_resistance(100)

    def on_reapply(self, existing, entity, engine):
        pass  # already at 100%, no stacking needed

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_tox_resistance(-100)


@register
class AlcoSeltzerImmunityEffect(Effect):
    """Buff (Alco-Seltzer): debuff immunity for 50 turns."""
    id = "alco_seltzer_immunity"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Debuff Immunity"

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class SpeedBoostEffect(Effect):
    """Buff: Increases energy gain per tick (e.g., from food buffs).
    Stacks with independent timers: each application adds its own timer."""
    id = "speed_boost"
    category = "buff"
    priority = 50

    def __init__(self, duration: int = 20, amount: int = 50, **kwargs):
        super().__init__(duration=1, **kwargs)  # base duration unused; expiry via stack_timers
        self.amount = amount
        self.stack_timers: list = [duration]

    @property
    def expired(self) -> bool:
        return len(self.stack_timers) == 0

    @property
    def stack_count(self):
        return len(self.stack_timers)

    @property
    def display_name(self) -> str:
        n = len(self.stack_timers)
        if n > 1:
            return f"Hyped Up x{n}"
        return "Hyped Up"

    @property
    def display_duration(self) -> str:
        if not self.stack_timers:
            return "0 turns"
        longest = max(self.stack_timers)
        return f"{longest} turn{'s' if longest != 1 else ''}"

    def tick(self, entity, engine):
        self.stack_timers = [t - 1 for t in self.stack_timers if t - 1 > 0]

    def modify_energy_gain(self, energy: float, entity) -> float:
        return energy + self.amount * len(self.stack_timers)

    def on_reapply(self, existing, entity, engine):
        new_dur = self.stack_timers[0] if self.stack_timers else 20
        existing.stack_timers.append(new_dur)


@register
class RootBeerEffect(Effect):
    """Buff ("Root" Beer): Immobile, -10 incoming damage, +50 Temp HP.
    Breaks early if Temp HP reaches 0."""
    id = "root_beer"
    category = "buff"
    priority = 50
    _DR = 10
    _TEMP_HP = 50

    def __init__(self, duration: int = 30, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._active = False

    @property
    def display_name(self) -> str:
        return "Rooted"

    def apply(self, entity, engine):
        entity.temp_hp += self._TEMP_HP
        self._active = True
        engine.messages.append([
            ("Your legs grow roots into the ground!", (140, 100, 50)),
        ])

    def modify_incoming_damage(self, damage, entity):
        return max(1, damage - self._DR)

    def tick(self, entity, engine):
        # Break early if temp HP is gone
        if self._active and entity.temp_hp <= 0:
            self.duration = 0
            return
        self.duration -= 1

    def expire(self, entity, engine):
        if self._active:
            self._active = False
            engine.messages.append([
                ("The roots release you. You can move again!", (100, 200, 100)),
            ])

    def on_reapply(self, existing, entity, engine):
        # Refresh duration and top up temp HP
        existing.duration = max(existing.duration, self.duration)
        deficit = self._TEMP_HP - entity.temp_hp
        if deficit > 0:
            entity.temp_hp += deficit


@register
class RatRaceEffect(Effect):
    """Buff (Ammo Rat L3): +10 speed per stack, refreshes duration on reapply."""
    id = "rat_race"
    category = "buff"
    priority = 50

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks
        self.amount_per_stack = 10

    @property
    def display_name(self) -> str:
        total = self.stacks * self.amount_per_stack
        return f"Rat Race x{self.stacks} (+{total} spd)"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = 20
        total = existing.stacks * existing.amount_per_stack
        engine.messages.append([
            ("Rat Race! ", (220, 200, 120)),
            (f"x{existing.stacks} (+{total} speed, 20t)", (180, 255, 150)),
        ])

    def modify_energy_gain(self, energy: float, entity) -> float:
        return energy + self.stacks * self.amount_per_stack



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
    """Buff (Smartsness L3): each stack adds +1 flat spell damage for 20 turns.
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
class RadNovaSpellBuffEffect(Effect):
    """Buff (Rad Nova strain): flat temporary spell damage for 20 turns.
    Reapply replaces with higher amount and refreshes duration."""
    id = "rad_nova_spell_buff"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, amount: int = 0, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    @property
    def display_name(self) -> str:
        return f"Rad Nova (+{self.amount} spell dmg)"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_spell_damage(self.amount)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.temporary_spell_damage = max(
                0, engine.player_stats.temporary_spell_damage - self.amount
            )

    def on_reapply(self, existing, entity, engine):
        if entity == engine.player:
            # Remove old amount, apply new
            engine.player_stats.temporary_spell_damage = max(
                0, engine.player_stats.temporary_spell_damage - existing.amount
            )
            engine.player_stats.add_temporary_spell_damage(self.amount)
        existing.amount = self.amount
        existing.duration = self.duration


@register
class RadiationVentEffect(Effect):
    """Buff (Kushenheimer): Tracks a placed radiation vent entity.
    Each tick: 10 rad to enemies within 2 tiles, bolt nearest enemy within 3 tiles.
    Bolt dmg: 10 + randint(1, BKS//2). Duration 10 turns. Removes vent entity on expire.
    Multiple vents = multiple instances (stackable=False bypassed by unique vent_id).
    """
    id = "radiation_vent"
    category = "buff"
    priority = 0
    stackable = False

    def __init__(self, vent_x: int = 0, vent_y: int = 0,
                 duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.vent_x = vent_x
        self.vent_y = vent_y

    @property
    def display_name(self) -> str:
        return f"Radiation Vent ({self.duration}t)"

    def apply(self, entity, engine):
        pass

    def on_reapply(self, existing, entity, engine):
        # Each vent is unique — this shouldn't be called, but just refresh if it is
        existing.duration = max(existing.duration, self.duration)

    def tick(self, entity, engine):
        from combat import add_radiation, deal_damage
        vx, vy = self.vent_x, self.vent_y
        # Rad aura: 10 rad to enemies within 2 tiles
        for ent in list(engine.dungeon.entities):
            if ent.entity_type != "monster" or not ent.alive:
                continue
            if max(abs(ent.x - vx), abs(ent.y - vy)) <= 2:
                add_radiation(engine, ent, 10)
        # Bolt: nearest enemy within 3 tiles
        best = None
        best_dist = 999
        for ent in engine.dungeon.entities:
            if ent.entity_type != "monster" or not ent.alive:
                continue
            dist = max(abs(ent.x - vx), abs(ent.y - vy))
            if dist <= 3 and dist < best_dist:
                best = ent
                best_dist = dist
        if best is not None:
            bks = engine.player_stats.effective_book_smarts
            half_bks = max(1, bks // 2)
            dmg = 10 + _random.randint(1, half_bks)
            actual = max(1, dmg - best.defense)
            killed = deal_damage(engine, actual, best)
            engine.messages.append([
                ("Rad Vent zaps ", (120, 255, 80)),
                (best.name, best.color),
                (f" for {actual}!", (120, 255, 80)),
            ])
            if killed:
                engine.event_bus.emit("entity_died", entity=best, killer=engine.player)
        self.duration -= 1

    def expire(self, entity, engine):
        # Remove the vent entity from the dungeon by position
        to_remove = None
        for ent in engine.dungeon.entities:
            if (getattr(ent, 'hazard_type', '') == 'radiation_vent'
                    and ent.x == self.vent_x and ent.y == self.vent_y):
                to_remove = ent
                break
        if to_remove is not None:
            engine.dungeon.entities.remove(to_remove)
        engine.messages.append("A Radiation Vent fizzles out.")


@register
class ToxicHarvestEffect(Effect):
    """Buff (Chemical Warfare L1): on any monster kill, gain 5 toxicity and
    refresh this buff's duration.  Cannot stack — reapply just refreshes."""
    id = "toxic_harvest"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    def on_reapply(self, existing, entity, engine):
        # Cannot stack — just refresh duration
        existing.duration = max(existing.duration, self.duration)


@register
class LoiteringTrackerEffect(Effect):
    """Hidden tracker (Jaywalking L5): counts consecutive idle turns.
    After 3 idle turns, grants 1 turn of untargetable + resets enemy AI.
    Any movement, attack, or ability resets the counter."""
    id = "loitering_tracker"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.idle_turns = 0

    @property
    def display_name(self) -> str:
        if self.idle_turns > 0:
            return f"Loitering ({self.idle_turns}/3)"
        return "Loitering"

    @property
    def stack_count(self):
        return self.idle_turns

    def on_reapply(self, existing, entity, engine):
        pass  # singleton


@register
class LoiteringUntargetableEffect(Effect):
    """Buff (Jaywalking L5): untargetable for 1 turn. Enemies skip this entity."""
    id = "loitering_untargetable"
    category = "buff"
    priority = 50

    def __init__(self, **kwargs):
        super().__init__(duration=1, **kwargs)

    @property
    def display_name(self) -> str:
        return "Loitering"


@register
class MomentumEffect(Effect):
    """Buff (Jaywalking L6): stacking charges. Each stack = 1 free move (0 energy).
    Consumed one at a time. No expiry."""
    id = "momentum"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Momentum x{self.stacks}" if self.stacks > 1 else "Momentum"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks


@register
class ShortcutChannelEffect(Effect):
    """Buff (Jaywalking L4): 2-turn channel. On expire, teleport to target tile.
    Moving immediately cancels the channel."""
    id = "shortcut_channel"
    category = "buff"
    priority = 100

    def __init__(self, target_x: int = 0, target_y: int = 0, **kwargs):
        super().__init__(duration=2, **kwargs)
        self.target_x = target_x
        self.target_y = target_y

    @property
    def display_name(self) -> str:
        return "Shortcut"

    def expire(self, entity, engine):
        if entity != engine.player:
            return
        tx, ty = self.target_x, self.target_y
        # Find an unblocked tile at or near the target
        if engine.dungeon.is_blocked(tx, ty):
            # Try nearby tiles in the target room
            room_idx = engine.dungeon.get_room_index_at(tx, ty)
            if room_idx is not None and room_idx < len(engine.dungeon.rooms):
                room = engine.dungeon.rooms[room_idx]
                for fx, fy in room.floor_tiles(engine.dungeon):
                    if not engine.dungeon.is_blocked(fx, fy):
                        tx, ty = fx, fy
                        break
                else:
                    engine.messages.append("Shortcut fizzles — destination is blocked!")
                    return
            else:
                engine.messages.append("Shortcut fizzles — destination is blocked!")
                return
        engine.dungeon.move_entity(entity, tx, ty)
        engine._compute_fov()
        engine._pickup_items_at(tx, ty)
        engine.messages.append([
            ("Shortcut! ", (100, 220, 255)),
            ("You reappear across the floor.", (180, 220, 255)),
        ])
        if engine.sdl_overlay:
            engine.sdl_overlay.add_tile_flash_ripple(
                [(tx, ty)], tx, ty,
                color=(100, 200, 255), duration=0.6,
            )


@register
class AcidMeltdownEffect(Effect):
    """Buff (Chemical Warfare L2): halves movement cost.  On any monster kill,
    the corpse explodes into a 3×3 acid pool.  Cannot stack."""
    id = "acid_meltdown"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._original_reduction: int = 0

    def apply(self, entity, engine):
        # Store the engine's current move_cost_reduction so we can undo later
        self._original_reduction = getattr(engine, 'move_cost_reduction', 0)
        engine.move_cost_reduction += 50  # ENERGY_THRESHOLD is 100, so +50 = half cost

    def expire(self, entity, engine):
        engine.move_cost_reduction -= 50

    def on_reapply(self, existing, entity, engine):
        # Cannot stack — just refresh duration
        existing.duration = max(existing.duration, self.duration)


@register
class ToxicSlingTimerEffect(Effect):
    """Timer for the Toxic Slingshot conjured gun.
    When this effect expires (or the gun runs out of ammo), the slingshot
    is removed from the sidearm slot (or inventory) and its granted ability revoked."""
    id = "toxic_slingshot_timer"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 30, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return f"Toxic Slingshot ({self.duration}t)"

    def tick(self, entity, engine):
        """Check if the gun still has ammo each tick. If not, expire early."""
        gun = engine.equipment.get("sidearm")
        if gun is not None and gun.item_id == "toxic_slingshot":
            if gun.current_ammo <= 0:
                self.duration = 0  # trigger expiry
                return
        # Also check inventory
        inv_gun = next(
            (item for item in entity.inventory if item.item_id == "toxic_slingshot"),
            None,
        )
        if gun is None and inv_gun is None:
            # Gun is gone already (somehow destroyed)
            self.duration = 0
            return

    def expire(self, entity, engine):
        _remove_toxic_slingshot(engine)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


def _remove_toxic_slingshot(engine):
    """Remove the Toxic Slingshot from sidearm slot or inventory and revoke Scattershot."""
    from items import get_item_def
    removed = False

    # Check sidearm slot
    gun = engine.equipment.get("sidearm")
    if gun is not None and gun.item_id == "toxic_slingshot":
        engine.equipment["sidearm"] = None
        if engine.primary_gun == "sidearm":
            # Fall back to weapon slot gun if available
            if engine.equipment.get("weapon") and get_item_def(
                engine.equipment["weapon"].item_id
            ).get("subcategory") == "gun":
                engine.primary_gun = "weapon"
            else:
                engine.primary_gun = None
        removed = True

    # Check inventory
    inv_gun = next(
        (item for item in engine.player.inventory if item.item_id == "toxic_slingshot"),
        None,
    )
    if inv_gun is not None:
        engine.player.inventory.remove(inv_gun)
        removed = True

    # Revoke Scattershot ability
    engine.revoke_ability("scattershot")

    if removed:
        engine.messages.append([
            ("Toxic Slingshot ", (80, 255, 80)),
            ("dissipates!", (160, 160, 160)),
        ])


@register
class ToxicShellEffect(Effect):
    """Buff (Chemical Warfare L5): watches for temp HP hitting 0, then fires
    a toxic nova (radius 4).  Damage = tox_consumed/2 + CW_level*2.
    Applies tox_consumed/2 toxicity to all enemies hit."""
    id = "toxic_shell"
    category = "buff"
    priority = 0

    def __init__(self, tox_consumed: int = 0, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.tox_consumed = tox_consumed

    @property
    def display_name(self) -> str:
        return f"Toxic Shell ({self.tox_consumed} tox)"

    def tick(self, entity, engine):
        """Fire nova when temp HP is depleted."""
        if entity.temp_hp <= 0:
            self._fire_nova(entity, engine)
            self.duration = 0  # expire

    def expire(self, entity, engine):
        # Floor transition — don't fire nova, just clean up silently
        pass

    def on_reapply(self, existing, entity, engine):
        # Should not happen (blocked in execute), but just in case
        pass

    def _fire_nova(self, entity, engine):
        """Toxic nova: radius 4, damage + tox to all enemies."""
        import combat
        cw_level = engine.skills.get("Chemical Warfare").level
        sts = engine.player_stats.effective_street_smarts
        nova_damage = self.tox_consumed // 5 + cw_level * 5 + sts // 3
        nova_tox = self.tox_consumed // 2
        px, py = entity.x, entity.y
        hits = 0

        for monster in engine.dungeon.get_monsters():
            if not monster.alive:
                continue
            dist = max(abs(monster.x - px), abs(monster.y - py))
            if dist <= 4:
                killed = combat.deal_damage(engine, nova_damage, monster)
                if nova_tox > 0:
                    combat.add_toxicity(engine, monster, nova_tox, from_player=True)
                hits += 1
                if killed:
                    engine.event_bus.emit("entity_died", entity=monster, killer=entity)

        engine.messages.append([
            ("Toxic Shell detonates! ", (80, 255, 80)),
            (f"{nova_damage} damage + {nova_tox} tox to {hits} enemies!", (160, 255, 160)),
        ])

        # Green ripple animation
        if engine.sdl_overlay:
            from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
            nova_tiles = [
                (px + dx, py + dy)
                for dx in range(-4, 5) for dy in range(-4, 5)
                if max(abs(dx), abs(dy)) <= 4
                and 0 <= px + dx < DUNGEON_WIDTH
                and 0 <= py + dy < DUNGEON_HEIGHT
            ]
            engine.sdl_overlay.add_tile_flash_ripple(
                nova_tiles, px, py,
                color=(80, 255, 80), duration=0.8, ripple_speed=0.06,
            )


@register
class ToxSpilloverAuraEffect(Effect):
    """Buff (Swamp Gas strain): on monster kill, transfer % of dead monster's tox
    to nearest alive enemy. Perm tolerance chance handled in engine event handler."""
    id = "tox_spillover_aura"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, spillover_pct: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.spillover_pct = spillover_pct

    @property
    def display_name(self) -> str:
        return f"Tox Spillover ({self.spillover_pct}%)"

    def on_reapply(self, existing, entity, engine):
        # Take the higher spillover %, refresh duration
        if self.spillover_pct > existing.spillover_pct:
            existing.spillover_pct = self.spillover_pct
        existing.duration = max(existing.duration, self.duration)


@register
class HotPotEffect(Effect):
    """Buff (Deep-Frying L4): stacking charges, no expiry.
    Each melee hit consumes 1 charge and splashes boiling oil to all
    enemies adjacent to the defender: CON + DeepFrying*2 damage, 2 Greasy stacks."""
    id = "hot_pot"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Hot Pot x{self.stacks}" if self.stacks > 1 else "Hot Pot"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        existing.stacks += self.stacks

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if self.stacks <= 0:
            return
        self.stacks -= 1
        con = engine.player_stats.effective_constitution
        df_level = engine.skills.get("Deep-Frying").level
        splash_dmg = max(1, con + df_level * 2)

        # Find all enemies adjacent to the defender (Chebyshev 1)
        hit_count = 0
        for m in engine.dungeon.get_monsters():
            if m is defender or not m.alive:
                continue
            if max(abs(m.x - defender.x), abs(m.y - defender.y)) == 1:
                m.take_damage(splash_dmg)
                apply_effect(m, engine, "greasy", duration=50, stacks=2, silent=True)
                hit_count += 1
                if not m.alive:
                    engine.event_bus.emit("entity_died", entity=m, killer=engine.player)

        # Deep-Frying XP
        if hit_count > 0:
            xp = splash_dmg * hit_count
            engine.skills.gain_potential_exp(
                "Deep-Frying", xp,
                engine.player_stats.effective_book_smarts,
                briskness=engine.player_stats.total_briskness,
            )

        charges_left = f" ({self.stacks} left)" if self.stacks > 0 else ""
        engine.messages.append([
            ("Hot Pot! ", (255, 160, 40)),
            (f"Boiling oil splashes {hit_count} enemy(ies) for {splash_dmg}!{charges_left}", (255, 200, 100)),
        ])

        if engine.sdl_overlay:
            tiles = [(defender.x + dx, defender.y + dy)
                     for dx in range(-1, 2) for dy in range(-1, 2)
                     if (dx, dy) != (0, 0)]
            engine.sdl_overlay.add_tile_flash_ripple(
                tiles, defender.x, defender.y,
                color=(255, 140, 30), duration=0.6,
            )

        # Auto-remove if no charges left
        if self.stacks <= 0:
            self.duration = 0


@register
class GreasyEffect(Effect):
    """Buff (Greasy food): +3% dodge per stack, max 10 stacks, 50-turn shared duration."""
    id = "greasy"
    category = "buff"
    priority = 0
    MAX_STACKS = 10
    DODGE_PER_STACK = 3

    def __init__(self, duration: int = 50, stacks: int = 1, **kwargs):
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
    """Buff (Hot Cheetos food): +2 to all stats per stack.
    Melee attacks have 50% chance per stack to apply 1 stack of Ignite.
    Each stack expires independently; on each expiry, apply 1 Ignite to player.
    Stacks with independent timers."""
    id = "hot_cheetos"
    category = "buff"
    priority = 0

    _STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]

    def __init__(self, duration: int = 30, **kwargs):
        super().__init__(duration=1, **kwargs)  # base duration unused; expiry via stack_timers
        self.stack_timers: list = [duration]

    @property
    def expired(self) -> bool:
        return len(self.stack_timers) == 0

    @property
    def stack_count(self):
        return len(self.stack_timers)

    @property
    def display_name(self) -> str:
        n = len(self.stack_timers)
        if n > 1:
            return f"Spicy Vibes x{n}"
        return "Spicy Vibes"

    @property
    def display_duration(self) -> str:
        if not self.stack_timers:
            return "0 turns"
        longest = max(self.stack_timers)
        return f"{longest} turn{'s' if longest != 1 else ''}"

    def apply(self, entity, engine):
        """Apply +2 to all stats for the first stack."""
        if entity == engine.player:
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, 2)
            engine._sync_player_max_hp()

    def tick(self, entity, engine):
        before = len(self.stack_timers)
        self.stack_timers = [t - 1 for t in self.stack_timers if t - 1 > 0]
        after = len(self.stack_timers)
        expired_count = before - after
        if expired_count > 0 and entity == engine.player:
            # Remove stat bonuses for each expired stack
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, -2 * expired_count)
            engine._sync_player_max_hp()
            # Each expired stack ignites the player
            for _ in range(expired_count):
                apply_effect(entity, engine, "ignite", duration=5, stacks=1, silent=False)

    def expire(self, entity, engine):
        """Clean up any remaining stat bonuses from active stacks."""
        remaining = len(self.stack_timers)
        if remaining > 0 and entity == engine.player:
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, -2 * remaining)
            engine._sync_player_max_hp()
            self.stack_timers.clear()

    def on_reapply(self, existing, entity, engine):
        new_dur = self.stack_timers[0] if self.stack_timers else 30
        existing.stack_timers.append(new_dur)
        # Apply +2 all stats for the new stack
        if entity == engine.player:
            for stat in self._STATS:
                engine.player_stats.add_temporary_stat_bonus(stat, 2)
            engine._sync_player_max_hp()

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        """50% chance per stack to apply 1 stack of Ignite to the target."""
        for _ in range(len(self.stack_timers)):
            if _random.random() < 0.50:
                dur = engine._player_ignite_duration()
                ignite_eff = apply_effect(defender, engine, "ignite", duration=dur, stacks=1, silent=True)
                if ignite_eff:
                    engine.messages.append(
                        f"Spicy attack! {defender.name} ignited! (x{ignite_eff.stacks})"
                    )
                break  # one ignite message per hit, but more stacks = higher chance


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
    """Debuff (Fart): 1 dmg/turn + all stats -1 for duration turns."""
    id = "lesser_cloudkill"
    category = "debuff"
    priority = 5

    _STATS = ["constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger"]

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stat_reductions: dict = {}

    @property
    def display_name(self) -> str:
        return "Stinky"

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
    """Buff: +1 melee power and +1 spell damage per stack. From eating Leftovers.
    Stacks with independent timers."""
    id = "leftovers_well_fed"
    category = "buff"
    priority = 5

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=1, **kwargs)  # base duration unused; expiry via stack_timers
        self.stack_timers: list = [duration]

    @property
    def expired(self) -> bool:
        return len(self.stack_timers) == 0

    @property
    def stack_count(self):
        return len(self.stack_timers)

    @property
    def display_name(self) -> str:
        n = len(self.stack_timers)
        if n > 1:
            return f"Well Fed x{n}"
        return "Well Fed"

    @property
    def display_duration(self) -> str:
        if not self.stack_timers:
            return "0 turns"
        longest = max(self.stack_timers)
        return f"{longest} turn{'s' if longest != 1 else ''}"

    def apply(self, entity, engine):
        entity.power += 1
        engine.player_stats.add_temporary_spell_damage(1)

    def tick(self, entity, engine):
        before = len(self.stack_timers)
        self.stack_timers = [t - 1 for t in self.stack_timers if t - 1 > 0]
        expired_count = before - len(self.stack_timers)
        if expired_count > 0:
            entity.power -= expired_count
            engine.player_stats.add_temporary_spell_damage(-expired_count)

    def expire(self, entity, engine):
        """Clean up any remaining power/spell damage bonuses from active stacks."""
        remaining = len(self.stack_timers)
        if remaining > 0:
            entity.power -= remaining
            engine.player_stats.add_temporary_spell_damage(-remaining)
            self.stack_timers.clear()

    def on_reapply(self, existing, entity, engine):
        new_dur = self.stack_timers[0] if self.stack_timers else 10
        existing.stack_timers.append(new_dur)
        # Apply +1 power, +1 spell dmg for the new stack
        entity.power += 1
        engine.player_stats.add_temporary_spell_damage(1)


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

    def __init__(self, duration: int = 10, food_name: str = "Food", food_id: str = "", food_effects: list = None, well_fed_effect_name: str = "Well Fed", greasy_stacks_per_charge: int = 0, is_fried: bool = False, sandwich_food_id: str = "", **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.food_name = food_name
        self.food_id = food_id
        self.food_effects = food_effects or []
        self.sandwich_food_id = sandwich_food_id
        self.well_fed_effect_name = well_fed_effect_name
        self.greasy_stacks_per_charge = greasy_stacks_per_charge
        self.is_fried = is_fried
        self.move_warned = False

    @property
    def display_name(self) -> str:
        return f"Eating {self.food_name}"

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
                engine.grant_ability_charges("firebolt", _random.randint(5, 10))

            elif effect_type == "greasy_buff":
                if self.greasy_stacks_per_charge > 0:
                    stacks = self.greasy_stacks_per_charge
                else:
                    stacks = 2 if engine.skills.get("Deep-Frying").level >= 2 else 1
                apply_effect(entity, engine, "greasy", duration=20, stacks=stacks, silent=True)
                bonus = " (+Extra Greasy!)" if stacks >= 2 else ""
                engine.messages.append(f"The {self.food_name} makes you feel Greasy!{bonus} (+{stacks * GreasyEffect.DODGE_PER_STACK}% dodge)")

            elif effect_type == "grant_ability_charges":
                ability_id = effect_dict.get("ability_id")
                charges_spec = effect_dict.get("charges", 1)
                if isinstance(charges_spec, (list, tuple)):
                    charges = _random.randint(charges_spec[0], charges_spec[1])
                else:
                    charges = charges_spec
                if ability_id:
                    engine.grant_ability_charges(ability_id, charges)

            elif effect_type == "cornbread_buff":
                duration = effect_dict.get("duration", 10)
                cb_effect = apply_effect(entity, engine, "cornbread_buff", duration=duration, silent=True)
                if cb_effect:
                    engine.messages.append("Cornbread High! +5 Book-Smarts for 10 turns.")

            elif effect_type == "radiation":
                amount = effect_dict.get("amount", 10)
                from combat import add_radiation
                add_radiation(engine, entity, amount)
                engine.messages.append(f"You feel irradiated! (+{amount} radiation)")

            elif effect_type == "remove_radiation":
                amount = effect_dict.get("amount", 10)
                from combat import remove_radiation
                remove_radiation(engine, entity, amount)
                engine.messages.append(f"You feel cleansed! (-{amount} radiation)")

            elif effect_type == "toxicity":
                amount = effect_dict.get("amount", 10)
                from combat import add_toxicity
                add_toxicity(engine, entity, amount)
                engine.messages.append(f"You feel toxic! (+{amount} toxicity)")

            elif effect_type == "remove_toxicity":
                amount = effect_dict.get("amount", 10)
                from combat import remove_toxicity
                remove_toxicity(engine, entity, amount)
                engine.messages.append(f"You feel purified! (-{amount} toxicity)")

            elif effect_type == "leftovers_well_fed":
                duration = effect_dict.get("duration", 10)
                lwf_effect = apply_effect(entity, engine, "leftovers_well_fed", duration=duration, silent=True)
                if lwf_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! (+1 power, +1 spell damage)")

            elif effect_type == "protein_powder":
                pp_effect = apply_effect(entity, engine, "protein_powder", silent=True)
                if pp_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! Stat gains are doubled this floor.")

            elif effect_type == "muffin_buff":
                mf_effect = apply_effect(entity, engine, "muffin_buff", silent=True)
                if mf_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! 50% chance to preserve spell charges.")

            elif effect_type == "phase_walk":
                duration = effect_dict.get("duration", 12)
                pw_effect = apply_effect(entity, engine, "phase_walk", duration=duration, silent=True)
                if pw_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! You can walk through walls!")

            elif effect_type == "holy_wafer":
                ds_effect = apply_effect(entity, engine, "divine_shield", stacks=5, silent=True)
                if ds_effect:
                    stk = ds_effect.stacks
                    engine.messages.append([
                        (f"You feel {self.well_fed_effect_name}! ", (255, 255, 200)),
                        (f"Divine Shield x{stk}!", (255, 255, 150)),
                    ])

            elif effect_type == "hard_boiled_egg":
                hbe_effect = apply_effect(entity, engine, "hard_boiled_egg", duration=100, stacks=1, silent=True)
                if hbe_effect:
                    stk = hbe_effect.stacks
                    engine.messages.append([
                        (f"You feel {self.well_fed_effect_name}! ", (255, 255, 100)),
                        (f"Death save active ({stk} stack{'s' if stk != 1 else ''}).", (100, 255, 100)),
                    ])

            elif effect_type == "eagle_eye":
                ee_effect = apply_effect(entity, engine, "eagle_eye", silent=True)
                if ee_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! Unlimited vision for this floor.")

            elif effect_type == "yellowcake_buff":
                yc_effect = apply_effect(entity, engine, "yellowcake_buff", silent=True)
                if yc_effect:
                    engine.messages.append(f"You feel {self.well_fed_effect_name}! 10x mutation chance. No weak mutations.")

            elif effect_type == "scavengers_eye":
                duration = effect_dict.get("duration", 100)
                se_effect = apply_effect(entity, engine, "scavengers_eye", duration=duration, silent=True)
                if se_effect:
                    engine.messages.append([
                        (f"You feel {self.well_fed_effect_name}! ", (180, 120, 200)),
                        ("50% chance for kills to drop consumables!", (100, 255, 100)),
                    ])

            elif effect_type == "banana_pudding":
                from combat import remove_radiation
                current_rad = entity.radiation
                rad_to_remove = current_rad // 2
                if rad_to_remove > 0:
                    remove_radiation(engine, entity, rad_to_remove)
                    bp_effect = apply_effect(entity, engine, "banana_pudding",
                                             temp_hp_amount=rad_to_remove, duration=100, silent=True)
                    if bp_effect:
                        engine.messages.append([
                            (f"You feel {self.well_fed_effect_name}! ", (255, 230, 120)),
                            (f"-{rad_to_remove} Radiation, +{rad_to_remove} Temp HP!", (100, 255, 100)),
                        ])
                else:
                    engine.messages.append([
                        (f"You feel {self.well_fed_effect_name}... ", (255, 230, 120)),
                        ("but you have no radiation to purge.", (180, 180, 180)),
                    ])

        # Grant munching skill XP (sandwich: half of combined XP)
        if self.food_id:
            if self.sandwich_food_id:
                from items import FOOD_MUNCHING_XP
                xp_a = FOOD_MUNCHING_XP.get(self.food_id, 5)
                xp_b = FOOD_MUNCHING_XP.get(self.sandwich_food_id, 5)
                half_xp = round((xp_a + xp_b) / 2)
                adjusted = round(half_xp * engine.player_stats.xp_multiplier)
                engine.skills.gain_potential_exp(
                    "Munching", adjusted,
                    engine.player_stats.effective_book_smarts,
                    briskness=engine.player_stats.total_briskness,
                )
            else:
                engine._gain_munching_xp(self.food_id)

        # Greasy food: award 50% of munching XP as deep-frying XP
        if self.is_fried and self.food_id:
            from items import FOOD_MUNCHING_XP
            base_xp = FOOD_MUNCHING_XP.get(self.food_id, 5)
            fry_xp = round(base_xp * 0.5 * engine.player_stats.xp_multiplier)
            if fry_xp > 0:
                engine.skills.gain_potential_exp(
                    "Deep-Frying", fry_xp,
                    engine.player_stats.effective_book_smarts,
                    briskness=engine.player_stats.total_briskness
                )
                engine.messages.append([
                    ("Deep-Frying skill: +", (255, 140, 0)),
                    (str(fry_xp), (255, 180, 100)),
                    (" potential XP (greasy bonus)", (255, 140, 0)),
                ])

        # Better Later perk: 25% chance to generate Leftovers on food completion
        munching_skill = engine.skills.get("Munching")
        if munching_skill.level >= 3:
            if _random.random() < 0.25:
                engine._add_item_to_inventory("leftovers")
                engine.messages.append("[Better Later] You saved some Leftovers!")

        # Ring of Sustenance: 15% chance to spawn a random food
        from inventory_mgr import _sustenance_ring_proc
        _sustenance_ring_proc(engine, "food")

        # Hot Pot (Deep-Frying L4): 50% chance to gain a charge
        if engine.skills.get("Deep-Frying").level >= 4:
            if _random.random() < 0.50:
                apply_effect(entity, engine, "hot_pot", stacks=1, silent=True)
                engine.messages.append([
                    ("Hot Pot! ", (255, 160, 40)),
                    ("+1 charge (next melee splashes oil)", (255, 200, 100)),
                ])


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
        had_frozen = any(getattr(e, 'id', '') == 'frozen' for e in entity.status_effects)
        entity.status_effects = [e for e in entity.status_effects if getattr(e, 'id', '') not in ('chill', 'frozen')]
        if had_chill or had_frozen:
            stripped = []
            if had_chill:
                stripped.append("chill")
            if had_frozen:
                stripped.append("frozen")
            label = " and ".join(stripped)
            if entity == engine.player:
                engine.messages.append(f"The fire burns away your {label}!")
            else:
                engine.messages.append(f"{entity.name}'s {label} is burned away!")

    def on_reapply(self, existing, entity, engine):
        """Add incoming stacks and refresh the shared timer to incoming duration."""
        existing.stacks = min(existing.stacks + self.stacks, self._MAX_STACKS)
        existing.duration = self.duration

    def tick(self, entity, engine):
        # Pyromania L3 (Neva Burn Out): player immune to ignite damage
        if entity == engine.player:
            pyro = engine.skills.get("Pyromania")
            if pyro and pyro.level >= 3:
                self.duration -= 1
                return
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
            # Wildfire (Pyromania L5): spread ignite to adjacent monsters with fewer stacks
            self._try_wildfire_spread(entity, engine)
        self.duration -= 1

    def _try_wildfire_spread(self, entity, engine):
        """Pyromania L5: 20% chance per adjacent monster to spread ignite stacks."""
        import random
        pyro_skill = engine.skills.get("Pyromania")
        if pyro_skill is None or pyro_skill.level < 5:
            return
        for mon in engine.dungeon.get_monsters():
            if mon is entity or not mon.alive or mon == engine.player:
                continue
            dx = abs(mon.x - entity.x)
            dy = abs(mon.y - entity.y)
            if max(dx, dy) != 1:
                continue
            # Only spread to monsters with fewer ignite stacks
            mon_ignite = next((e for e in mon.status_effects if getattr(e, 'id', '') == 'ignite'), None)
            mon_stacks = mon_ignite.stacks if mon_ignite else 0
            if mon_stacks >= self.stacks:
                continue
            if random.random() < 0.2:
                # Push target up to match source stacks
                stacks_to_add = self.stacks - mon_stacks
                apply_effect(mon, engine, "ignite", stacks=stacks_to_add)
                engine.messages.append(
                    f"Fire spreads from {entity.name} to {mon.name}! ({self.stacks} stacks)"
                )


@register
class VenomEffect(Effect):
    """Venom — stacking DOT from Spider Hatchling.  Each stack = 1 damage per turn.
    Duration refreshes on reapply; stacks accumulate."""
    id = "venom"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 10, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks: int = stacks

    @property
    def display_name(self) -> str:
        return "Venom"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        """Add one stack and refresh the shared timer."""
        existing.stacks += 1
        existing.duration = max(existing.duration, self.duration)

    def tick(self, entity, engine):
        # Cocoon pauses venom ticking — damage accumulates in cocoon effect instead
        if getattr(self, '_cocoon_paused', False):
            return
        damage = self.stacks
        # Venom can't kill the player — skip damage at 1 HP
        if entity == engine.player and entity.hp <= 1:
            self.duration -= 1
            return
        entity.take_damage(damage)
        if entity == engine.player:
            engine.messages.append(
                f"Venom deals {damage} damage! ({entity.hp}/{entity.max_hp} HP)"
            )
        else:
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
                engine.messages.append(f"{entity.name} dies from venom!")
        self.duration -= 1


@register
class CocoonEffect(Effect):
    """Cocoon — enemy wrapped in silk. Immobilized, can't attack, can't gain energy.
    Venom ticks silently (tracked internally). On expiry, all accumulated venom
    damage is dealt as a single burst. Spawns a micro-spider on break."""
    id = "cocoon"
    category = "debuff"
    priority = 100

    def __init__(self, duration: int = 3, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.venom_damage_stored = 0

    @property
    def display_name(self) -> str:
        return "Cocooned"

    def apply(self, entity, engine):
        # Pause venom effects — we'll tick them ourselves
        for eff in entity.status_effects:
            if getattr(eff, 'id', '') == 'venom':
                eff._cocoon_paused = True

    def modify_energy_gain(self, amount: float, entity) -> float:
        return 0.0

    def before_turn(self, entity, player, dungeon) -> bool:
        return True  # skip turn

    def modify_incoming_damage(self, damage: int, entity) -> int:
        return 0  # immune to damage while cocooned

    def tick(self, entity, engine):
        # Accumulate venom damage silently
        for eff in entity.status_effects:
            if getattr(eff, 'id', '') == 'venom':
                self.venom_damage_stored += getattr(eff, 'stacks', 1)
        self.duration -= 1

    def expire(self, entity, engine):
        # Unpause venom
        for eff in entity.status_effects:
            if getattr(eff, 'id', '') == 'venom':
                eff._cocoon_paused = False
        # Burst all stored venom damage at once
        if self.venom_damage_stored > 0 and entity.alive:
            entity.take_damage(self.venom_damage_stored)
            engine.messages.append([
                ("Cocoon bursts! ", (180, 180, 255)),
                (f"{entity.name} takes {self.venom_damage_stored} venom burst damage!", (80, 200, 60)),
            ])
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=engine.player)
        # Spawn a micro-spider if player has Brood Mother (L4+)
        if engine.skills.get("Arachnigga").level >= 4 and entity.alive or not entity.alive:
            from entity import Entity
            from ai import get_initial_state
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = entity.x + dx, entity.y + dy
                if not engine.dungeon.is_blocked(nx, ny):
                    micro = Entity(
                        x=nx, y=ny, char="s", color=(120, 200, 80),
                        name="Micro-Spider", entity_type="monster",
                        hp=1, max_hp=1, power=1, defense=0,
                        ai_type="spider_hatchling", speed=80,
                        is_summon=True, summon_lifetime=5,
                    )
                    micro._is_micro_spider = True
                    micro.ai_state = get_initial_state("spider_hatchling")
                    engine.dungeon.add_entity(micro)
                    break

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class CurseDotEffect(Effect):
    """Curse of DOT — permanent stacking curse.  Each turn, 50% chance to gain
    +1 stack and deals 1-5 weighted random damage.  At low stacks damage skews
    toward 1; at ~20 stacks, 75% chance of hitting 5.  On death the curse
    spreads to the nearest enemy within 2 tiles, inheriting the full stack count.
    """
    id = "curse_dot"
    category = "debuff"
    priority = 5

    def __init__(self, stacks: int = 0, **kwargs):
        # Permanent: duration=9999, but we never decrement it
        super().__init__(duration=9999, **kwargs)
        self.stacks: int = stacks

    @property
    def display_name(self) -> str:
        return "Curse of DOT"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        """Reapplication just bumps stacks by 1 (shouldn't normally happen)."""
        existing.stacks += 1

    def tick(self, entity, engine):
        if not entity.alive:
            return
        # 50% chance to gain +1 stack per turn
        import random as _rand2
        if _rand2.random() < 0.50:
            self.stacks += 1
        # Weighted damage: 1-5, skewing toward 5 at high stacks
        import random as _rand
        t = min(self.stacks, 20) / 20.0   # 0.0 → 1.0
        w1 = 5.0 * (1.0 - t) + 1.0 * t   # 5 → 1
        w2 = 4.0 * (1.0 - t) + 1.0 * t   # 4 → 1
        w3 = 3.0 * (1.0 - t) + 1.0 * t   # 3 → 1
        w4 = 2.0 * (1.0 - t) + 1.0 * t   # 2 → 1
        w5 = 1.0 * (1.0 - t) + 12.0 * t  # 1 → 12  (12/16 = 75% at t=1)
        damage = _rand.choices([1, 2, 3, 4, 5], weights=[w1, w2, w3, w4, w5])[0]
        entity.take_damage(damage)
        if entity == engine.player:
            engine.messages.append(
                f"Curse of DOT deals {damage} damage! "
                f"({self.stacks} stacks) ({entity.hp}/{entity.max_hp} HP)"
            )
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
        else:
            if not entity.alive:
                engine.event_bus.emit("entity_died", entity=entity, killer=None)
                engine.messages.append(f"{entity.name} succumbs to the curse!")
        # Duration never decrements — permanent until death


@register
class CurseCovidEffect(Effect):
    """Curse of COVID — permanent spreading curse.  Each turn:
    1. Apply 20 rad or 20 tox (50/50), capped at 150 each.
    2. 50% chance to gain +1 stack (stacks have no mechanical effect currently).
    3. 25% chance to spread to nearest enemy within 3 tiles (fresh at 1 stack).
    """
    id = "curse_covid"
    category = "debuff"
    priority = 5

    def __init__(self, stacks: int = 0, **kwargs):
        super().__init__(duration=9999, **kwargs)
        self.stacks: int = stacks

    @property
    def display_name(self) -> str:
        return "Curse of COVID"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1

    def tick(self, entity, engine):
        if not entity.alive:
            return
        import random as _rand
        from combat import add_radiation, add_toxicity

        # 1. Apply 20 rad or tox (50/50), skip if >= 150
        rad = getattr(entity, 'radiation', 0)
        tox = getattr(entity, 'toxicity', 0)
        can_rad = rad < 150
        can_tox = tox < 150
        if can_rad and can_tox:
            if _rand.random() < 0.5:
                add_radiation(engine, entity, 20, from_player=True)
            else:
                add_toxicity(engine, entity, 20, from_player=True)
        elif can_rad:
            add_radiation(engine, entity, 20, from_player=True)
        elif can_tox:
            add_toxicity(engine, entity, 20, from_player=True)
        # else: both >= 150, no rad/tox applied

        # 2. 50% chance to gain a stack
        if _rand.random() < 0.5:
            self.stacks += 1

        # 3. 25% chance to spread to nearest enemy within 3 tiles
        if _rand.random() < 0.25:
            sx, sy = entity.x, entity.y
            best = None
            best_dist = 999
            for m in engine.dungeon.get_monsters():
                if not m.alive or m is entity or getattr(m, "is_summon", False):
                    continue
                if any(getattr(e, 'id', '') == 'curse_covid' for e in m.status_effects):
                    continue
                dist = max(abs(m.x - sx), abs(m.y - sy))
                if dist <= 3 and dist < best_dist:
                    best_dist = dist
                    best = m
            if best is not None:
                apply_effect(best, engine, "curse_covid", stacks=0, silent=True)
                # Curse spread trail animation
                sdl = getattr(engine, "sdl_overlay", None)
                if sdl:
                    from engine import _curse_spread_path
                    path = _curse_spread_path(entity.x, entity.y, best.x, best.y)
                    sdl.add_tile_flash_trail(path, color=(140, 60, 180), duration=0.3, trail_speed=0.04)
                # +20 Blackkk Magic XP on spread
                adjusted_xp = round(20 * engine.player_stats.xp_multiplier)
                engine.skills.gain_potential_exp(
                    "Blackkk Magic", adjusted_xp,
                    engine.player_stats.effective_book_smarts,
                    briskness=engine.player_stats.total_briskness,
                )
                engine.messages.append([
                    ("Curse of COVID spreads to ", (80, 180, 60)),
                    (f"{best.name}!", (140, 220, 100)),
                ])
        # Duration never decrements — permanent until death


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


@register
class WebTrailEffect(Effect):
    """Web Trail: for 5 turns, every tile the player moves off of gets a cobweb."""
    id = "web_trail"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=5, **kwargs)

    @property
    def display_name(self) -> str:
        return "Web Trail"

    def on_reapply(self, existing, entity, engine):
        existing.duration = 5  # refresh


@register
class SlippedEffect(Effect):
    """Slipped on silver spray paint.  Entity must spend their next move/attack
    action standing up.  While slipped, take 50% more melee damage.

    For monsters: before_turn returns True (skip turn = stand up).
    For the player: handled in engine.handle_move (move/attack consumed to stand).
    Player can still use consumables, fire guns, and cast spells while slipped.
    Does not stack; reapply refreshes."""
    id = "slipped"
    category = "debuff"
    priority = 95

    def __init__(self, **kwargs):
        super().__init__(duration=2, **kwargs)

    @property
    def display_name(self) -> str:
        return "Slipped"

    def before_turn(self, entity, player, dungeon):
        """Monsters: skip turn to stand up, then remove self."""
        if entity == player:
            return False
        entity.status_effects.remove(self)
        return True

    def modify_incoming_damage(self, damage, entity):
        """50% more melee damage while slipped."""
        return int(damage * 1.5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = 2


@register
class WebStuckEffect(Effect):
    """Stuck in a web. 50% chance to escape each move attempt; auto-escape after 5 failures.

    For monsters the hook is modify_movement (returns (0,0) on failure).
    For the player the check is handled directly in engine.handle_move.
    When the entity escapes, the web hazard entity is destroyed.
    """
    id = "web_stuck"
    category = "debuff"
    priority = 90

    def __init__(self, web_entity=None, **kwargs):
        super().__init__(duration=9999, **kwargs)
        self.escape_attempts = 0
        self.max_attempts = 5
        self.web_entity = web_entity

    def modify_movement(self, dx, dy, entity, player, dungeon):
        """For monsters: 50% chance to break free, otherwise stuck."""
        if dx == 0 and dy == 0:
            return dx, dy
        if _random.random() < 0.5:
            self._break_free(entity, dungeon)
            return dx, dy
        self.escape_attempts += 1
        if self.escape_attempts >= self.max_attempts:
            self._break_free(entity, dungeon)
            return dx, dy
        return 0, 0

    def _break_free(self, entity, dungeon):
        """Remove the web hazard and this effect."""
        if self.web_entity is not None:
            try:
                dungeon.remove_entity(self.web_entity)
            except ValueError:
                pass
        if self in entity.status_effects:
            entity.status_effects.remove(self)
        self.duration = 0


@register
class BerserkEffect(Effect):
    """Buff (Berserker's Ring): +4 STR for 10 turns. Each instance stacks independently."""
    id = "berserk"
    display_name = "Berserk"
    category = "buff"
    priority = 10

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self._applied = False

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", 4)
            self._applied = True

    def expire(self, entity, engine):
        if self._applied and entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("strength", -4)

    @property
    def stack_count(self):
        return 4

    def on_reapply(self, existing, entity, engine):
        # Independent stacking — handled by caller appending new instances directly
        pass


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

    # Red Drank: double duration of effects applied during drink handling
    if getattr(engine, '_drink_duration_multiplier', 1) > 1 and hasattr(incoming, 'duration'):
        incoming.duration *= engine._drink_duration_multiplier

    # Debuff immunity: block incoming debuffs
    if incoming.category == "debuff":
        blocker_id = None
        if any(getattr(e, 'id', None) == 'zoned_out' for e in entity.status_effects):
            blocker_id = 'zoned_out'
        elif any(getattr(e, 'id', None) == 'alco_seltzer_immunity' for e in entity.status_effects):
            blocker_id = 'alco_seltzer_immunity'
        if blocker_id:
            if not silent:
                if blocker_id == 'zoned_out':
                    msg = "too zoned out"
                else:
                    msg = "immune"
                if entity == engine.player:
                    engine.messages.append(f"You're {msg} to be debuffed!")
                else:
                    engine.messages.append(f"{entity.name} is {msg} to be debuffed!")
            return None

    # One curse per monster: if incoming is a curse and target already has one, block it
    if incoming.is_curse and any(getattr(e, 'is_curse', False) for e in entity.status_effects):
        if not silent:
            curse_name = next(
                e.display_name for e in entity.status_effects if getattr(e, 'is_curse', False)
            )
            if entity == engine.player:
                engine.messages.append(f"You're already cursed ({curse_name})!")
            else:
                engine.messages.append(f"{entity.name} is already cursed ({curse_name})!")
        return None

    existing = next(
        (e for e in entity.status_effects if type(e) is type(incoming)),
        None,
    )

    if existing is not None:
        incoming.on_reapply(existing, entity, engine)
        if effect_id in ('greasy', 'ignite'):
            _check_grease_fire_synergy(entity, engine)
        # Pyromania XP: 10 XP when player applies ignite to a monster
        if effect_id == 'ignite' and entity != engine.player and entity.entity_type == "monster":
            engine.skills.gain_potential_exp(
                "Pyromania", 10,
                engine.player_stats.effective_book_smarts,
                briskness=engine.player_stats.total_briskness,
            )
        return existing

    incoming.apply(entity, engine)
    entity.status_effects.append(incoming)

    if not silent:
        name = incoming.display_name
        if entity == engine.player:
            if incoming.category == "debuff":
                engine.messages.append(f"Afflicted with {name}!")
            else:
                engine.messages.append(f"Gained {name}!")
            desc = incoming.short_description
            if desc:
                engine.messages.append(f"  ({desc})")
        else:
            if incoming.category == "debuff":
                engine.messages.append(f"{entity.name} afflicted with {name}!")
            else:
                engine.messages.append(f"{entity.name} gained {name}!")

    if effect_id in ('greasy', 'ignite'):
        _check_grease_fire_synergy(entity, engine)

    # Pyromania XP: 10 XP when player applies ignite to a monster
    if effect_id == 'ignite' and entity != engine.player and entity.entity_type == "monster":
        engine.skills.gain_potential_exp(
            "Pyromania", 10,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness,
        )

    return incoming


_DRINK_BUFF_IDS = frozenset({
    "forty_oz", "malt_liquor", "wizard_mind_bomb", "hennessy", "peace_of_mind",
    "fireball_shooter_buff", "blue_lagoon_buff", "limoncello_chain_shock",
    "natty_light_buff", "jagermeister_buff", "butterbeer_buff", "platinum_reserve",
    "mana_drink", "virulent_vodka", "five_loco", "white_gonster",
    "dead_shot_daiquiri", "speedball", "rainbow_rotgut", "root_beer", "sangria",
    "red_drank", "green_drank",
})


def tick_all_effects(entity, engine) -> None:
    """Tick every Effect on entity by one turn, removing expired ones.

    Call once per turn for each entity (player and monsters) from the
    engine's end-of-turn processing.
    """
    is_player = entity == engine.player
    still_active = []
    hair_of_dog_reapply = []
    original_effects = set(id(e) for e in entity.status_effects)

    for effect in list(entity.status_effects):
        if effect not in entity.status_effects:
            continue  # removed mid-loop (e.g. by WhiteGonster purge)
        effect.tick(entity, engine)
        if effect.expired or effect not in entity.status_effects:
            if effect.expired:
                effect.expire(entity, engine)
            if is_player and effect.expired:
                engine.messages.append(f"{effect.display_name} has worn off.")
                # Hair of the Dog (Drinking L3): 30% to reapply expired drink buffs
                if (getattr(effect, 'id', '') in _DRINK_BUFF_IDS
                        and engine.skills.get("Drinking").level >= 3):
                    import random as _rng
                    if _rng.random() < 0.30:
                        hair_of_dog_reapply.append(effect.id)
        else:
            still_active.append(effect)

    # Preserve effects added during expire() callbacks (e.g. eating_food
    # applying hot_cheetos on completion). Only keep truly new effects,
    # not expired ones that were already in the original list.
    for eff in entity.status_effects:
        if id(eff) not in original_effects and eff not in still_active:
            still_active.append(eff)
    entity.status_effects = still_active

    # Apply Hair of the Dog reapplications after the main loop
    for eff_id in hair_of_dog_reapply:
        apply_effect(entity, engine, eff_id, silent=True)
        engine.messages.append([
            ("Hair of the Dog! ", (200, 160, 80)),
            (f"{eff_id.replace('_', ' ').title()} kicks back in!", (255, 220, 120)),
        ])


# ---------------------------------------------------------------------------
# Radiation DOT effect
# ---------------------------------------------------------------------------

@register
class RadPoisonEffect(Effect):
    """Radiation DOT — applies radiation per tick instead of HP damage.

    Does not stack; reapplication refreshes duration.
    """
    id = "rad_poison"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 5, amount: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    def on_reapply(self, existing, entity, engine):
        existing.duration = self.duration  # refresh, don't stack

    def tick(self, entity, engine):
        engine.add_radiation(entity, self.amount)
        if entity == engine.player:
            engine.messages.append(
                f"Radiation poisons you! (+{self.amount} rad)"
            )
        self.duration -= 1


# ---------------------------------------------------------------------------
# Conversion effect
# ---------------------------------------------------------------------------

@register
class ConversionEffect(Effect):
    """Conversion debuff — each tick drains 2 from the higher of tox/rad
    and adds 1 to the lower (2:1 ratio).  Equal values = no-op.
    """
    id = "conversion"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)

    def on_reapply(self, existing, entity, engine):
        existing.duration = self.duration  # refresh, don't stack

    def tick(self, entity, engine):
        from combat import add_toxicity, add_radiation
        tox = getattr(entity, "toxicity", 0)
        rad = getattr(entity, "radiation", 0)
        if tox > rad:
            entity.toxicity = max(0, tox - 2)
            add_radiation(engine, entity, 1, pierce_resistance=True)
            if entity == engine.player:
                engine.messages.append("Conversion: toxicity seeps into radiation! (-2 tox, +1 rad)")
        elif rad > tox:
            entity.radiation = max(0, rad - 2)
            add_toxicity(engine, entity, 1, pierce_resistance=True)
            if entity == engine.player:
                engine.messages.append("Conversion: radiation seeps into toxicity! (-2 rad, +1 tox)")
        self.duration -= 1


# ---------------------------------------------------------------------------
# Iron Lung strain effects
# ---------------------------------------------------------------------------

@register
class CalculatedAimEffect(Effect):
    """Buff (Street Scholar): Auto-reload. 10% chance per gun kill → +1 permanent STS."""
    id = "calculated_aim"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        # Ignore legacy tier/bksmt_chance params from old saves
        kwargs.pop("tier", None)
        kwargs.pop("bksmt_chance", None)
        super().__init__(duration=duration, **kwargs)
        self.auto_reload = True

    @property
    def display_name(self) -> str:
        return "Calculated Aim (10% STS/kill)"

    def apply(self, entity, engine):
        pass

    def expire(self, entity, engine):
        pass

    def on_gun_kill(self, entity, engine):
        """Called when a gun kill happens. 10% chance for +1 permanent STS."""
        if _random.random() < 0.10:
            engine.player_stats.modify_base_stat("street_smarts", 1)
            engine.messages.append([
                ("Calculated Aim: +1 permanent Street Smarts!", (180, 160, 220)),
            ])

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class HollowPointsEffect(Effect):
    """Buff (Street Scholar): Next N gun shots deal +50% damage. Charges consumed per shot."""
    id = "hollow_points"
    category = "buff"
    priority = 0

    def __init__(self, charges: int = 5, **kwargs):
        kwargs.pop("duration", None)
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.charges = charges

    @property
    def display_name(self) -> str:
        return f"Hollow Points ({self.charges} shots)"

    def apply(self, entity, engine):
        pass

    def expire(self, entity, engine):
        pass

    def on_reapply(self, existing, entity, engine):
        existing.charges += self.charges


def hollow_points_modify_damage(engine, damage):
    """If Hollow Points active, consume 1 charge and return damage * 1.5. Else return damage unchanged."""
    for eff in engine.player.status_effects:
        if getattr(eff, 'id', '') == 'hollow_points' and eff.charges > 0:
            eff.charges -= 1
            boosted = int(damage * 1.5)
            engine.messages.append([
                ("Hollow Point! ", (255, 180, 80)),
                (f"{damage}\u2192{boosted} damage", (255, 220, 140)),
            ])
            if eff.charges <= 0:
                eff.duration = 0  # expire on next tick
            return boosted
    return damage


def notify_gun_kill(engine):
    """Call on_gun_kill on the Calculated Aim effect if active."""
    aim = next(
        (e for e in engine.player.status_effects
         if getattr(e, 'id', '') == 'calculated_aim'),
        None,
    )
    if aim is not None:
        aim.on_gun_kill(engine.player, engine)


@register
class ForceSensitiveEffect(Effect):
    """Buff (Skywalker OG): Tracks rad lost during buff. +2 temp STR per 25 rad lost.
    All bonus STR reverts on expire. Re-smoking resets and refreshes.
    """
    id = "force_sensitive"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 66, **kwargs):
        kwargs.pop("tier", None)  # ignore legacy tier param from old saves
        super().__init__(duration=duration, **kwargs)
        self.rad_lost_counter = 0   # rad lost during this buff
        self.bonus_str = 0          # temp STR awarded so far
        self.max_duration = duration

    @property
    def display_name(self) -> str:
        return f"Force Sensitive (+{self.bonus_str} STR)"

    def apply(self, entity, engine):
        pass

    def on_rad_lost(self, entity, engine, amount):
        """Called when the entity loses radiation. Track and award +2 temp STR per 25 lost."""
        self.rad_lost_counter += amount
        new_thresholds = self.rad_lost_counter // 25
        old_thresholds = (self.rad_lost_counter - amount) // 25
        if new_thresholds > old_thresholds:
            crossed = new_thresholds - old_thresholds
            gained = crossed * 2
            self.bonus_str += gained
            entity.power += gained
            engine.player_stats.modify_base_stat("strength", gained)
            engine.messages.append(
                f"Force Sensitive: +{gained} STR from rad loss! (total +{self.bonus_str})"
            )

    def expire(self, entity, engine):
        """Remove all bonus STR when the buff ends."""
        if self.bonus_str > 0:
            entity.power -= self.bonus_str
            engine.player_stats.modify_base_stat("strength", -self.bonus_str)
            engine.messages.append(
                f"Force Sensitive fades. Lost {self.bonus_str} bonus STR."
            )

    def on_reapply(self, existing, entity, engine):
        existing.expire(entity, engine)
        existing.rad_lost_counter = 0
        existing.bonus_str = 0
        existing.max_duration = self.max_duration
        existing.duration = self.max_duration


@register
class IronLungDefenseEffect(Effect):
    """Buff (Iron Lung strain): temporary defense bonus."""
    id = "iron_lung_defense"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 50, defense_amount: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.defense_amount = defense_amount

    @property
    def display_name(self) -> str:
        return f"Iron Lung (+{self.defense_amount} DEF)"

    def apply(self, entity, engine):
        entity.defense += self.defense_amount

    def expire(self, entity, engine):
        entity.defense -= self.defense_amount

    def on_reapply(self, existing, entity, engine):
        # Remove old, apply new
        entity.defense -= existing.defense_amount
        existing.defense_amount = self.defense_amount
        existing.duration = self.duration
        entity.defense += existing.defense_amount


@register
class IronLungDmgReductionEffect(Effect):
    """Debuff (Iron Lung strain): 25% reduced outgoing damage dealt."""
    id = "iron_lung_dmg_reduction"
    category = "debuff"
    priority = 0

    def __init__(self, duration: int = 50, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Iron Lung (-25% dmg dealt)"

    def apply(self, entity, engine):
        engine.player_stats.outgoing_damage_mults.append(0.75)

    def expire(self, entity, engine):
        try:
            engine.player_stats.outgoing_damage_mults.remove(0.75)
        except ValueError:
            pass

    def on_reapply(self, existing, entity, engine):
        existing.duration = self.duration  # refresh, don't stack


@register
class UnstableEffect(Effect):
    """Buff (Mutation L2): +5 rad on apply, +2 melee/gun dmg, hits irradiate enemies for 10 rad. 20 turns."""
    id = "unstable"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Unstable (+2 dmg, +10 rad on hit)"

    def apply(self, entity, engine):
        from combat import add_radiation
        add_radiation(engine, entity, 5, pierce_resistance=True)

    def expire(self, entity, engine):
        pass

    def on_reapply(self, existing, entity, engine):
        from combat import add_radiation
        add_radiation(engine, entity, 5, pierce_resistance=True)
        existing.duration = self.duration  # refresh, don't stack

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        from combat import add_radiation
        add_radiation(engine, defender, 10)


@register
class AbsolutionEffect(Effect):
    """Buff (White Power L5 'Absolution'): gain 5 tox/turn.
    All toxicity the player loses (resisted or removed) deals that amount
    as damage to 2 random enemies within 4 tiles."""
    id = "absolution"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 15, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return f"Absolution ({self.duration}t)"

    def tick(self, entity, engine):
        """Gain 5 toxicity per turn (goes through resistance)."""
        from combat import add_toxicity
        add_toxicity(engine, entity, 5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


def absolution_on_tox_lost(engine, amount: int):
    """Called when the player loses toxicity while Absolution is active.
    Deals `amount` damage split across 2 random enemies within 4 tiles."""
    import random as _rng
    import combat

    if amount <= 0:
        return
    player = engine.player
    # Find alive enemies within Chebyshev distance 4
    candidates = [
        m for m in engine.dungeon.get_monsters()
        if m.alive and max(abs(m.x - player.x), abs(m.y - player.y)) <= 4
    ]
    if not candidates:
        return

    # Pick up to 2 different targets
    if len(candidates) >= 2:
        targets = _rng.sample(candidates, 2)
    else:
        targets = [candidates[0]]

    for target in targets:
        killed = combat.deal_damage(engine, amount, target)
        engine.messages.append([
            ("Absolution: ", (220, 220, 255)),
            (f"{amount} damage to {target.name}!", (180, 200, 255)),
        ])
        if killed:
            engine.event_bus.emit("entity_died", entity=target, killer=player)


@register
class BastionEffect(Effect):
    """Buff (White Power L2 'Bastion'): toggle.
    While active: -25% incoming damage, -20% outgoing damage.
    floor_duration so it persists until toggled off or floor ends."""
    id = "bastion"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Bastion (-25% taken, -20% dealt)"

    def apply(self, entity, engine):
        engine.player_stats.outgoing_damage_mults.append(0.80)

    def modify_incoming_damage(self, damage: int, entity) -> int:
        return max(1, int(damage * 0.75))

    def expire(self, entity, engine):
        try:
            engine.player_stats.outgoing_damage_mults.remove(0.80)
        except ValueError:
            pass

    def on_reapply(self, existing, entity, engine):
        pass  # shouldn't happen — toggle logic prevents it


@register
class PurityStacksEffect(Effect):
    """Buff (White Power L1 'Reject the Poison'): accumulates stacks from
    resisted toxicity.  When the buff expires, heals for stacks then overflow
    as temp HP.  Immaculate (WP L6) doubles caps and grants 2x stacks
    while Bastion is active."""
    id = "purity_stacks"
    category = "buff"
    priority = 0

    def __init__(self, stacks: int = 0, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = min(stacks, 100)  # hard max even with Immaculate

    @staticmethod
    def _has_immaculate(engine) -> bool:
        return engine.skills.get("White Power").level >= 6

    def _max_stacks(self, engine) -> int:
        return 100 if self._has_immaculate(engine) else 50

    def _max_temp_hp(self, engine) -> int:
        return 100 if self._has_immaculate(engine) else 50

    @property
    def display_name(self) -> str:
        return f"Purity ({self.stacks})"

    def add_stacks(self, amount: int, engine=None):
        """Add stacks and refresh duration. Returns actual stacks added.
        If engine is provided and Immaculate + Bastion active, stacks are doubled."""
        # Immaculate (WP L6): 2x stacks while Bastion is active
        if engine and self._has_immaculate(engine):
            has_bastion = any(
                getattr(e, 'id', '') == 'bastion'
                for e in engine.player.status_effects
            )
            if has_bastion:
                amount *= 2
        cap = self._max_stacks(engine) if engine else 100
        old = self.stacks
        self.stacks = min(self.stacks + amount, cap)
        self.duration = 20  # refresh
        return self.stacks - old

    def expire(self, entity, engine):
        if self.stacks <= 0:
            return
        remaining = self.stacks
        healed = 0
        temp_gained = 0
        max_temp = self._max_temp_hp(engine)
        # Heal first
        missing_hp = entity.max_hp - entity.hp
        if missing_hp > 0:
            healed = min(remaining, missing_hp)
            entity.hp += healed
            remaining -= healed
        # Overflow as temp HP (capped)
        if remaining > 0:
            temp_gained = max(0, min(remaining, max_temp - entity.temp_hp))
            entity.temp_hp += temp_gained
        # Message
        parts = []
        if healed > 0:
            parts.append(f"+{healed} HP")
        if temp_gained > 0:
            parts.append(f"+{temp_gained} temp HP")
        if parts:
            engine.messages.append([
                ("Purity crystallizes! ", (220, 220, 255)),
                (", ".join(parts), (180, 255, 180)),
            ])
        else:
            engine.messages.append([
                ("Purity fades ", (220, 220, 255)),
                ("(HP full, temp HP at cap)", (160, 160, 160)),
            ])

    def on_reapply(self, existing, entity, engine):
        # Shouldn't happen — stacks added via add_stacks(), not reapply
        existing.stacks = min(existing.stacks + self.stacks, self.MAX_STACKS)
        existing.duration = 20


@register
class PurpleHaltSwaggerEffect(Effect):
    """Temporary Swagger buff from Double Helix strain (bad tier consolation)."""
    id = "purple_halt_swagger"
    category = "buff"
    priority = 3

    def __init__(self, duration: int = 15, amount: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.amount = amount

    @property
    def display_name(self) -> str:
        return f"Double Helix (+{self.amount} SWG)"

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", self.amount)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.amount)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class SpedEffect(Effect):
    """Meth-Head L3: melee attacks cost half energy for 5 turns.

    Cannot be reapplied while active — procs are blocked.
    Halving is done by refunding ENERGY_THRESHOLD // 2 after each melee attack.
    """

    id = "sped"
    category = "buff"
    priority = 10

    def __init__(self, **kwargs):
        super().__init__(duration=5, **kwargs)

    @property
    def display_name(self) -> str:
        return "Sped"

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        from config import ENERGY_THRESHOLD
        engine.player.energy += ENERGY_THRESHOLD // 2

    def on_reapply(self, existing, entity, engine):
        # Cannot refresh or stack — block reapplication entirely
        pass


@register
class HalfLifeMarkEffect(Effect):
    """Half-Life Mark: enemy detonates when dropping below 40% HP.
    3x3 AOE dealing 15+BKS damage, irradiates hit enemies for 30 rad."""
    id = "half_life_mark"
    category = "debuff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.triggered = False
        self.enrichment_stacks = 0  # transferred from Rad Bomb or direct Enrichment

    def check_threshold(self, entity, engine):
        """Check if entity dropped below 40% HP. If so, detonate."""
        if self.triggered:
            return
        if not entity.alive or entity.hp > entity.max_hp * 0.4:
            return
        self.triggered = True
        self._detonate(entity, engine)

    def _detonate(self, entity, engine):
        """AOE centered on the marked entity. Base 3x3, expanded by Enrichment."""
        from combat import add_radiation
        from config import DUNGEON_WIDTH, DUNGEON_HEIGHT
        bks = engine.player_stats.effective_book_smarts
        damage = 15 + bks
        radius = 1  # default 3x3
        # Apply enrichment stacks
        stacks = self.enrichment_stacks
        if stacks > 0:
            damage += stacks * 4
            radius += stacks // 2
            engine.messages.append([
                ("Enrichment consumed! ", (180, 255, 80)),
                (f"+{stacks * 4} damage, radius {radius * 2 + 1}x{radius * 2 + 1}", (160, 255, 120)),
            ])
        cx, cy = entity.x, entity.y
        size = radius * 2 + 1
        engine.messages.append([
            ("HALF-LIFE DETONATION! ", (120, 255, 80)),
            (f"{entity.name} erupts for {damage} damage! ({size}x{size})", (160, 255, 120)),
        ])
        # Pulse animation
        if engine.sdl_overlay:
            tiles = [
                (cx + ddx, cy + ddy)
                for ddx in range(-radius, radius + 1)
                for ddy in range(-radius, radius + 1)
                if 0 <= cx + ddx < DUNGEON_WIDTH and 0 <= cy + ddy < DUNGEON_HEIGHT
            ]
            engine.sdl_overlay.add_tile_flash_ripple(
                tiles, cx, cy, color=(80, 255, 80), duration=0.6
            )
        # Gather all targets in area
        targets = []
        for e in engine.dungeon.entities:
            if not getattr(e, 'alive', False):
                continue
            if e.entity_type not in ("monster", "player"):
                continue
            if abs(e.x - cx) <= radius and abs(e.y - cy) <= radius:
                targets.append(e)
        enemies_hit = 0
        for target in targets:
            target.take_damage(damage)
            add_radiation(engine, target, 30)
            if target is engine.player:
                engine._gain_catchin_fades_xp(damage)
                engine.messages.append(f"You take {damage} half-life blast damage!")
            else:
                enemies_hit += 1
                engine.messages.append(
                    f"{target.name} takes {damage} half-life blast + 30 rad!"
                )
                if not target.alive:
                    engine.event_bus.emit("entity_died", entity=target, killer=engine.player)
        # Nuclear Research L6 "Nuclear Feedback": +10 rad per enemy hit
        if enemies_hit > 0 and engine.skills.get("Nuclear Research").level >= 6:
            feedback_rad = enemies_hit * 10
            add_radiation(engine, engine.player, feedback_rad, pierce_resistance=True)
            engine.messages.append([
                ("Nuclear Feedback! ", (180, 255, 80)),
                (f"+{feedback_rad} rad ({enemies_hit} enemies hit)", (160, 255, 120)),
            ])
        # Remove this effect from the entity
        if self in entity.status_effects:
            entity.status_effects.remove(self)

    @property
    def display_name(self) -> str:
        return "Half-Life Mark"

    def on_reapply(self, existing, entity, engine):
        pass  # no stacking — one mark per target


@register
class SnipersMarkEffect(Effect):
    """Sniper's Mark: target takes 10% more damage (rounded up). Permanent until death."""
    id = "snipers_mark"
    category = "debuff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=9999, **kwargs)

    def modify_incoming_damage(self, damage: int, entity) -> int:
        bonus = -(-damage // 10)  # ceil(damage * 0.10)
        return damage + bonus

    @property
    def display_name(self) -> str:
        return "Sniper's Mark"

    def on_reapply(self, existing, entity, engine):
        pass  # no stacking


# ---------------------------------------------------------------------------
# Curse effects (Blackkk Magic)
# ---------------------------------------------------------------------------

@register
class CurseOfHamEffect(Effect):
    """Curse of Ham: monster attacks cost 50% more energy, deal 50% less damage.
    Unlimited duration.  Each turn, 50% chance to gain +1 stack (stacks reserved
    for future interactions with other Blackkk Magic effects)."""
    id = "curse_of_ham"
    category = "debuff"
    is_curse = True
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self.stacks = 0

    def modify_energy_gain(self, amount: float, entity) -> float:
        # 67% energy gain ≈ actions cost 50% more time
        return amount * 2 / 3

    def tick(self, entity, engine):
        import random as _rng
        if _rng.random() < 0.50:
            self.stacks += 1

    @property
    def display_name(self) -> str:
        if self.stacks > 0:
            return f"Curse of Ham x{self.stacks}"
        return "Curse of Ham"

    def on_reapply(self, existing, entity, engine):
        pass  # blocked by one-curse-per-monster rule; should never reach here


@register
class HexSlowEffect(Effect):
    """Hex debuff (Occultist): -10 speed per stack. Stacks on reapply, refreshes duration."""
    id = "hex_slow"
    category = "debuff"
    priority = 5

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Hexed"

    @property
    def stack_count(self):
        return self.stacks

    def modify_energy_gain(self, amount: float, entity) -> float:
        return max(amount - (10 * self.stacks), 10)

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = 20
        if entity == engine.player:
            engine.messages.append([
                ("Hexed! ", (140, 50, 180)),
                (f"-{existing.stacks * 10} speed ({existing.stacks} stacks)", (180, 100, 220)),
            ])


@register
class PurgeInfectionEffect(Effect):
    """Purge debuff (Infected L1): 3 stacks, -50% melee damage.
    Lose 1 stack per melee hit (+5 Infected XP per stack lost).
    Permanent until all stacks are consumed — persists across floors."""
    id = "purge_infection"
    category = "debuff"
    priority = 5

    def __init__(self, stacks: int = 3, **kwargs):
        super().__init__(duration=9999, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return "Purging"

    @property
    def stack_count(self):
        return self.stacks

    @property
    def display_duration(self) -> str:
        return f"{self.stacks} hit{'s' if self.stacks != 1 else ''} left"

    def on_reapply(self, existing, entity, engine):
        """Reapplying adds 3 stacks."""
        existing.stacks += 3

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        self.stacks -= 1
        # +5 Infected XP per stack consumed
        adjusted_xp = round(5 * engine.player_stats.xp_multiplier)
        engine.skills.gain_potential_exp(
            "Infected", adjusted_xp,
            engine.player_stats.effective_book_smarts,
            briskness=engine.player_stats.total_briskness,
        )
        engine.messages.append([
            ("Purge! ", (120, 200, 50)),
            (f"Infection clears... ({self.stacks} left) ", (180, 220, 120)),
            (f"(+{adjusted_xp} Infected XP)", (160, 200, 100)),
        ])
        if self.stacks <= 0:
            if self in engine.player.status_effects:
                engine.player.status_effects.remove(self)
            self.duration = 0


@register
class ZombieRageEffect(Effect):
    """Zombie Rage buff (Infected L2): stacking buff.  Each stack = +20% melee
    damage, +20 energy/tick.  Stacks have independent 10-turn timers.
    On melee kill: +5 infection per stack and reset cooldown.
    Nerf: if Purity is active, melee damage is hard-capped to 1."""
    id = "zombie_rage"
    category = "buff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)
        self.timers: list[int] = [10]

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        label = f"Zombie Rage x{n}" if n > 1 else "Zombie Rage"
        if self.timers:
            return f"{label}"
        return label

    def apply(self, entity, engine):
        engine.player_stats.outgoing_damage_mults.append(1.20)

    def on_reapply(self, existing, entity, engine):
        """Add a new stack and refresh all existing timers to 10."""
        existing.timers = [10] * (len(existing.timers) + 1)
        existing.duration = 10
        engine.player_stats.outgoing_damage_mults.append(1.20)

    def tick(self, entity, engine):
        self.timers = [t - 1 for t in self.timers]
        # Count expiring stacks and remove their damage mults
        expired = sum(1 for t in self.timers if t <= 0)
        for _ in range(expired):
            try:
                engine.player_stats.outgoing_damage_mults.remove(1.20)
            except ValueError:
                pass
        self.timers = [t for t in self.timers if t > 0]
        if self.timers:
            self.duration = max(self.timers)
        else:
            self.duration = 0

    def expire(self, entity, engine):
        # Clean up any remaining mults (safety net)
        for _ in range(len(self.timers)):
            try:
                engine.player_stats.outgoing_damage_mults.remove(1.20)
            except ValueError:
                pass

    def modify_energy_gain(self, amount: float, entity) -> float:
        return amount + 20 * len(self.timers)

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if not defender.alive:
            from combat import add_infection
            stacks = len(self.timers)
            infection_gain = 5 * stacks
            add_infection(engine, engine.player, infection_gain)
            # Reset cooldown so ability can be used again immediately
            engine.ability_cooldowns.pop("zombie_rage", None)
            engine.messages.append([
                ("Zombie Rage! ", (180, 50, 50)),
                (f"+{infection_gain} infection from the kill! Cooldown reset!", (220, 120, 120)),
            ])


@register
class HollowedOutEffect(Effect):
    """Hollowed Out: floor-duration marker that prevents Infection Nova from triggering again.
    No mechanical effect — purely a gate for the once-per-floor Nova."""
    id = "hollowed_out"
    category = "debuff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    def get_display_name(self) -> str:
        return "Hollowed Out"

    def get_description(self) -> str:
        return "Your body is spent from the Infection Nova. Cannot trigger another this floor."

    def on_reapply(self, existing, entity, engine):
        pass  # should never reapply


@register
class HungerEffect(Effect):
    """Hunger (Infected L5): melee attacks heal 25% of damage dealt, +1 infection per hit.
    Applied when Purge is used while player has Infected level >= 5."""
    id = "hunger"
    category = "buff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)

    def get_display_name(self) -> str:
        return "Hunger"

    def get_description(self) -> str:
        return "Melee attacks heal 25% of damage dealt. Each hit adds +1 infection."

    def on_reapply(self, existing, entity, engine):
        existing.duration = 10  # refresh

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        # Heal 25% of damage dealt
        heal = max(1, int(damage * 0.25))
        engine.player.heal(heal)
        # +1 infection per hit
        from combat import add_infection
        add_infection(engine, engine.player, 1)
        engine.messages.append([
            ("Hunger! ", (120, 200, 50)),
            (f"+{heal} HP", (100, 255, 100)),
            (f" (+1 infection)", (180, 220, 100)),
        ])


@register
class OutbreakEffect(Effect):
    """Outbreak (Infected L6): marks an enemy. When damaged, 30% echoes to other
    marked enemies within radius 3. Each enemy echoes at most once per damage event."""
    id = "outbreak"
    category = "debuff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=12, **kwargs)

    def get_display_name(self) -> str:
        return "Outbreak"

    def get_description(self) -> str:
        return "Linked. Damage dealt echoes 30% to other linked enemies within 3 tiles."

    def on_reapply(self, existing, entity, engine):
        existing.duration = 12  # refresh


# ---------------------------------------------------------------------------
# Spider effects
# ---------------------------------------------------------------------------

@register
class WebSlowEffect(Effect):
    """Webbed: -25 speed (flat energy reduction) for 10 turns. No stacking; reapply refreshes."""
    id = "webbed"
    category = "debuff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)

    @property
    def display_name(self) -> str:
        return "Webbed"

    def modify_energy_gain(self, energy: float, entity) -> float:
        return max(1, energy - 25)

    def on_reapply(self, existing, entity, engine):
        existing.duration = 10


@register
class WolfSpiderVenomEffect(Effect):
    """Wolf Spider Venom: 1 dmg/turn for 10 turns + 15% melee miss chance. No stack; refresh."""
    id = "wolf_spider_venom"
    category = "debuff"
    priority = 0
    miss_chance = 0.15  # checked by combat.handle_attack

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)

    @property
    def display_name(self) -> str:
        return "Wolf Venom"

    def tick(self, entity, engine):
        # Venom can't kill the player — skip damage at 1 HP
        if entity == engine.player and entity.hp <= 1:
            self.duration -= 1
            return
        entity.take_damage(1)
        if entity == engine.player:
            engine.messages.append(
                f"Wolf Venom deals 1 damage! ({entity.hp}/{entity.max_hp} HP)"
            )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.duration -= 1

    def on_reapply(self, existing, entity, engine):
        existing.duration = 10


@register
class NeuroVenomEffect(Effect):
    """Neuro Venom (Black Widow): independent-timer stacking DOT.
    Each application adds a 12-turn timer. Damage per tick = active timer count.
    Timers count down and expire independently (like ignite's timers pattern)."""
    id = "neuro_venom"
    category = "debuff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=12, **kwargs)
        self.timers: list[int] = [12]

    @property
    def display_name(self) -> str:
        n = len(self.timers)
        return f"Neuro Venom x{n}" if n > 1 else "Neuro Venom"

    def on_reapply(self, existing, entity, engine):
        existing.timers.append(12)
        existing.duration = max(existing.timers)

    def tick(self, entity, engine):
        damage = len(self.timers)
        # Venom can't kill the player — skip damage at 1 HP
        if entity == engine.player and entity.hp <= 1:
            self.timers = [t - 1 for t in self.timers if t - 1 > 0]
            self.duration = max(self.timers) if self.timers else 0
            return
        entity.take_damage(damage)
        if entity == engine.player and damage > 0:
            engine.messages.append(
                f"Neuro Venom! -{damage} HP ({len(self.timers)} stacks)"
            )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=None)
        # Decrement all timers, remove expired
        self.timers = [t - 1 for t in self.timers if t - 1 > 0]
        self.duration = max(self.timers) if self.timers else 0


@register
class PipeVenomEffect(Effect):
    """Pipe Venom: 1 damage per turn for 10 turns. Does not stack; reapply refreshes duration."""
    id = "pipe_venom"
    category = "debuff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)

    @property
    def display_name(self) -> str:
        return "Pipe Venom"

    def tick(self, entity, engine):
        # Venom can't kill the player — skip damage at 1 HP
        if entity == engine.player and entity.hp <= 1:
            self.duration -= 1
            return
        entity.take_damage(1)
        if entity == engine.player:
            engine.messages.append(
                f"Pipe Venom deals 1 damage! ({entity.hp}/{entity.max_hp} HP)"
            )
        if not entity.alive:
            engine.event_bus.emit("entity_died", entity=entity, killer=None)
        self.duration -= 1

    def on_reapply(self, existing, entity, engine):
        existing.duration = 10


@register
class DistractedEffect(Effect):
    """Sleight of Hand: monster's next melee attack misses. Consumed on attack attempt."""
    id = "distracted"
    category = "debuff"
    priority = 5

    def __init__(self, **kwargs):
        super().__init__(duration=99, **kwargs)

    @property
    def display_name(self) -> str:
        return "Distracted"

    def on_reapply(self, existing, entity, engine):
        pass  # no stacking, just keep existing


@register
class EmptyPocketsEffect(Effect):
    """Marker debuff: enemy has already been pickpocketed. Permanent, no gameplay effect."""
    id = "empty_pockets"
    category = "debuff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, **kwargs)
        self.floor_duration = True

    @property
    def display_name(self) -> str:
        return "Empty Pockets"

    def on_reapply(self, existing, entity, engine):
        pass  # no stacking


@register
class LeftBehindEffect(Effect):
    """Abandoning L3: +1 DR per item left behind on the previous floor. Lasts until floor end."""
    id = "left_behind"
    category = "buff"
    priority = 5

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=1, floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Left Behind x{self.stacks}"

    @property
    def stack_count(self):
        return self.stacks

    def modify_incoming_damage(self, damage: int, entity) -> int:
        return max(0, damage - self.stacks)

    def on_reapply(self, existing, entity, engine):
        existing.stacks = self.stacks  # replace with new count


@register
class MilkFromTheStoreEffect(Effect):
    """Abandoning L4: double all stats for 10 turns."""
    id = "milk_from_the_store"
    category = "buff"
    priority = 10

    _STATS = ("constitution", "strength", "book_smarts", "street_smarts", "tolerance", "swagger")

    def __init__(self, **kwargs):
        super().__init__(duration=10, **kwargs)
        self._bonuses: dict[str, int] = {}

    @property
    def display_name(self) -> str:
        return "Milk From The Store"

    def apply(self, entity, engine):
        ps = engine.player_stats
        for stat in self._STATS:
            base = getattr(ps, f"effective_{stat}")
            ps.add_temporary_stat_bonus(stat, base)
            self._bonuses[stat] = base

    def expire(self, entity, engine):
        ps = engine.player_stats
        for stat, amount in self._bonuses.items():
            ps.add_temporary_stat_bonus(stat, -amount)

    def on_reapply(self, existing, entity, engine):
        pass  # no refresh while active


@register
class SangriaEffect(Effect):
    """Buff: +30% lifesteal (melee/spell/gun) per stack, +1x move cost per stack.
    Stacks refresh duration and add a stack.  Kills extend duration by 20 turns."""
    id = "sangria"
    category = "buff"
    priority = 0

    _LIFESTEAL_PER_STACK = 0.30
    _MOVE_COST_PER_STACK = 100  # ENERGY_THRESHOLD

    def __init__(self, duration: int = 50, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        pct = int(self.stacks * self._LIFESTEAL_PER_STACK * 100)
        if self.stacks > 1:
            return f"Sangria x{self.stacks} ({pct}% LS)"
        return f"Sangria ({pct}% LS)"

    def apply(self, entity, engine):
        engine.player_move_cost += self._MOVE_COST_PER_STACK * self.stacks

    def expire(self, entity, engine):
        engine.player_move_cost -= self._MOVE_COST_PER_STACK * self.stacks

    def tick(self, entity, engine):
        self.duration -= 1

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1
        existing.duration = 50
        engine.player_move_cost += self._MOVE_COST_PER_STACK

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        heal = max(1, int(damage * self._LIFESTEAL_PER_STACK * self.stacks))
        engine.player.heal(heal)
        engine.messages.append([
            ("Sangria: ", (160, 30, 60)),
            (f"+{heal} HP", (100, 255, 100)),
            (f" ({engine.player.hp}/{engine.player.max_hp})", (150, 150, 150)),
        ])

    def extend_on_kill(self, engine):
        """Called via entity_died event when player kills an enemy."""
        self.duration += 20
        engine.messages.append([
            ("Sangria: ", (160, 30, 60)),
            ("+20 turns!", (255, 200, 100)),
        ])


@register
class VictoryRushEffect(Effect):
    """Buff (Smacking L4): Next melee attack rolls crit twice (advantage)
    and heals 25% of damage dealt. Consumed on next melee hit."""
    id = "victory_rush"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Victory Rush"

    def on_player_melee_hit(self, engine, target, damage):
        """Lucky crit + 25% lifesteal, then consume self."""
        heal = max(1, damage // 4)
        engine.player.hp = min(engine.player.hp + heal, engine.player.max_hp)
        engine.messages.append([
            ("Victory Rush! ", (255, 200, 50)),
            (f"+{heal} HP", (100, 255, 100)),
        ])
        # Remove self after this hit
        self.duration = 0


@register
class SwashbucklingEffect(Effect):
    """Buff (Slashing L1): +1 damage with slash weapons and +1% dodge per stack.
    20-turn duration. Stacks infinitely; reapplying refreshes all stacks' duration."""
    id = "swashbuckling"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, stacks: int = 1, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        if self.stacks > 1:
            return f"Swashbuckling x{self.stacks} (+{self.stacks} slash dmg, +{self.stacks}% dodge)"
        return "Swashbuckling (+1 slash dmg, +1% dodge)"

    @property
    def stack_count(self):
        return self.stacks

    def apply(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_dodge_chance(self.stacks)

    def expire(self, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_dodge_chance(-self.stacks)

    def on_reapply(self, existing, entity, engine):
        if entity == engine.player:
            engine.player_stats.add_dodge_chance(1)
        existing.stacks += 1
        existing.duration = self.duration  # refresh all stacks


@register
class AftershockEffect(Effect):
    """Buff (Beating L4): granted on crit with a blunt weapon.
    Next 3 melee attacks deal +Beating level×2 bonus damage and 30% stun (1 turn).
    Consumes a stack per hit. Expires when stacks or duration run out."""
    id = "aftershock"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 15, stacks: int = 3, **kwargs):
        super().__init__(duration=duration, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        return f"Aftershock x{self.stacks}" if self.stacks > 1 else "Aftershock"

    @property
    def stack_count(self):
        return self.stacks

    def on_reapply(self, existing, entity, engine):
        existing.stacks = 3  # refresh to full
        existing.duration = self.duration

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        if self.stacks <= 0 or not defender.alive:
            return
        # Only proc with beating weapons
        from items import get_item_def, weapon_matches_type
        weapon = engine.equipment.get("weapon")
        if not weapon:
            return
        wdefn = get_item_def(weapon.item_id)
        if not wdefn or not weapon_matches_type(wdefn, "beating"):
            return
        self.stacks -= 1
        beating_level = engine.skills.get("Beating").level
        bonus = max(1, beating_level * 2)
        defender.take_damage(bonus)
        msg_parts = [
            ("Aftershock! ", (255, 160, 40)),
            (f"+{bonus} dmg", (255, 200, 100)),
        ]
        if not defender.alive:
            engine.event_bus.emit("entity_died", entity=defender, killer=engine.player)
            msg_parts.append((f" — {defender.name} dies!", (255, 100, 100)))
        elif _random.random() < 0.30:
            apply_effect(defender, engine, "stun", duration=1, silent=True)
            msg_parts.append((" — stunned!", (255, 220, 100)))
        msg_parts.append((f" ({self.stacks} left)", (180, 180, 180)))
        engine.messages.append(msg_parts)


@register
class ColossusWreckingEffect(Effect):
    """Buff (Beating L6 — Colossus Wrecking stance): +40% melee damage, can't dodge, -2 DR.
    Floor-duration; removed when switching to Fortress or leaving the floor."""
    id = "colossus_wrecking"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Colossus: Wrecking (+40% dmg, -2 DR, no dodge)"

    def apply(self, entity, engine):
        engine.player_stats.outgoing_damage_mults.append(1.40)
        engine.player_stats.permanent_dr -= 2
        engine.player_stats.add_dodge_chance(-999)  # effectively disable dodge

    def expire(self, entity, engine):
        if 1.40 in engine.player_stats.outgoing_damage_mults:
            engine.player_stats.outgoing_damage_mults.remove(1.40)
        engine.player_stats.permanent_dr += 2
        engine.player_stats.add_dodge_chance(999)

    def on_reapply(self, existing, entity, engine):
        pass  # already active, do nothing


@register
class ColossusFortressEffect(Effect):
    """Buff (Beating L6 — Colossus Fortress stance): +4 DR, 30% counter-attack for STR dmg + 1t stun, -25% melee damage.
    Floor-duration; removed when switching to Wrecking or leaving the floor."""
    id = "colossus_fortress"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Colossus: Fortress (+4 DR, counter+stun, -25% dmg)"

    def apply(self, entity, engine):
        engine.player_stats.permanent_dr += 4
        engine.player_stats.outgoing_damage_mults.append(0.75)

    def expire(self, entity, engine):
        engine.player_stats.permanent_dr -= 4
        if 0.75 in engine.player_stats.outgoing_damage_mults:
            engine.player_stats.outgoing_damage_mults.remove(0.75)

    def on_reapply(self, existing, entity, engine):
        pass  # already active, do nothing


@register
class SpringDodgeEffect(Effect):
    """Buff (Boots of Springing): +50% dodge chance for 5 turns."""
    id = "spring_dodge"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 5, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Spring (+50% dodge)"

    def apply(self, entity, engine):
        engine.player_stats.add_dodge_chance(50)

    def expire(self, entity, engine):
        engine.player_stats.add_dodge_chance(-50)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)


@register
class TitanFormEffect(Effect):
    """Buff (Titan's Blood Ring): +50 temp HP, +50% melee damage, 25% stun on melee, +10 temp HP/turn. 20 turns."""
    id = "titan_form"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 20, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Titan Form"

    def apply(self, entity, engine):
        entity.temp_hp += 50
        engine.player_stats.outgoing_damage_mults.append(1.5)

    def tick(self, entity, engine):
        # Regenerate 10 temp HP per turn
        entity.temp_hp += 10
        self.duration -= 1

    def expire(self, entity, engine):
        entity.temp_hp = 0
        if 1.5 in engine.player_stats.outgoing_damage_mults:
            engine.player_stats.outgoing_damage_mults.remove(1.5)

    def on_reapply(self, existing, entity, engine):
        existing.duration = max(existing.duration, self.duration)

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        import random
        if random.random() < 0.25 and defender.alive:
            apply_effect(defender, engine, "stun", duration=1)
            engine.messages.append([
                ("Titan stun! ", (255, 80, 80)),
                (f"{defender.name} is stunned!", (255, 200, 200)),
            ])


@register
class StrideEffect(Effect):
    """Buff (Boots of Striding): 50% reduced action cost for 10 turns."""
    id = "stride"
    category = "buff"
    priority = 0

    def __init__(self, duration: int = 10, **kwargs):
        super().__init__(duration=duration, **kwargs)

    @property
    def display_name(self) -> str:
        return "Stride (-50% action cost)"

    def apply(self, entity, engine):
        engine.action_cost_mult = 0.5

    def expire(self, entity, engine):
        engine.action_cost_mult = 1.0

    def on_reapply(self, existing, entity, engine):
        # Does not stack — just refresh duration
        existing.duration = max(existing.duration, self.duration)


@register
class NineRingEffect(Effect):
    """Permanent buff (The 9 Ring): 25% lifesteal on all damage (melee/gun/spell)."""
    id = "nine_ring"
    category = "buff"
    priority = 0

    _LIFESTEAL = 0.25

    def __init__(self, **kwargs):
        super().__init__(duration=1, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "The 9 Ring (25% Lifesteal)"

    def on_reapply(self, existing, entity, engine):
        pass  # only one ring

    # Lifesteal handled centrally in deal_damage() for all damage types (melee/gun/spell).

@register
class HamstrungEffect(Effect):
    """Debuff (Slashing L5): -2 flat damage per stack on all attacks. Stacks infinitely."""
    id = "hamstrung"
    category = "debuff"
    priority = 5

    def __init__(self, stacks: int = 1, **kwargs):
        super().__init__(duration=1, floor_duration=True, **kwargs)
        self.stacks = stacks

    @property
    def display_name(self) -> str:
        reduction = self.stacks * 2
        return f"Hamstrung x{self.stacks} (-{reduction} dmg)"

    def on_reapply(self, existing, entity, engine):
        existing.stacks += 1


@register
class ConsecratedGroundEffect(Effect):
    """Buff (Decontamination L3): +1 Swagger/turn while standing on rad tiles, cap +5.
    Resets when player steps off. Floor-duration passive."""
    id = "consecrated_ground"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=1, floor_duration=True, **kwargs)
        self.swagger_bonus = 0

    @property
    def display_name(self) -> str:
        if self.swagger_bonus > 0:
            return f"Consecrated (+{self.swagger_bonus} SWG)"
        return "Consecrated Ground"

    def before_turn(self, entity, engine):
        pos = (entity.x, entity.y)
        on_rad_tile = pos in engine.dungeon.rad_tiles
        if on_rad_tile and self.swagger_bonus < 5:
            self.swagger_bonus += 1
            engine.player_stats.add_temporary_stat_bonus("swagger", 1)
        elif not on_rad_tile and self.swagger_bonus > 0:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.swagger_bonus)
            self.swagger_bonus = 0

    def expire(self, entity, engine):
        if self.swagger_bonus > 0:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.swagger_bonus)
            self.swagger_bonus = 0

    def on_reapply(self, existing, entity, engine):
        pass  # floor-duration, no stacking


@register
class ConsecratedGroundEffect(Effect):
    """Buff (Decontamination L3): +1 Swagger/turn while standing on rad tiles, cap +5.
    Resets when player steps off. Floor-duration passive."""
    id = "consecrated_ground"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=1, floor_duration=True, **kwargs)
        self.swagger_bonus = 0

    @property
    def display_name(self) -> str:
        if self.swagger_bonus > 0:
            return f"Consecrated (+{self.swagger_bonus} SWG)"
        return "Consecrated Ground"

    def before_turn(self, entity, engine):
        pos = (entity.x, entity.y)
        on_rad_tile = pos in engine.dungeon.rad_tiles
        if on_rad_tile and self.swagger_bonus < 5:
            self.swagger_bonus += 1
            engine.player_stats.add_temporary_stat_bonus("swagger", 1)
        elif not on_rad_tile and self.swagger_bonus > 0:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.swagger_bonus)
            self.swagger_bonus = 0

    def expire(self, entity, engine):
        if self.swagger_bonus > 0:
            engine.player_stats.add_temporary_stat_bonus("swagger", -self.swagger_bonus)
            self.swagger_bonus = 0

    def on_reapply(self, existing, entity, engine):
        pass  # floor-duration, no stacking


@register
class GammaAuraEffect(Effect):
    """Buff (Decontamination L2 'Gamma Aura'): toggle.
    While active: enemies within 2 tiles gain +5 rad/turn (earns Decon XP).
    2x Decontamination XP from resisting radiation.
    floor_duration so it persists until toggled off or floor ends."""
    id = "gamma_aura"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Gamma Aura"

    def apply(self, entity, engine):
        pass

    def tick(self, entity, engine):
        """Each tick: irradiate enemies within Chebyshev 2 of the player."""
        from combat import add_radiation
        px, py = entity.x, entity.y
        for m in engine.dungeon.entities:
            if m.entity_type != "monster" or not m.alive:
                continue
            if max(abs(m.x - px), abs(m.y - py)) <= 2:
                add_radiation(engine, m, 5, from_player=True)
                # Decontamination XP for rad applied via aura
                bksmt = engine.player_stats.effective_book_smarts
                engine.skills.gain_potential_exp("Decontamination", 5, bksmt)

    def expire(self, entity, engine):
        pass

    def on_reapply(self, existing, entity, engine):
        pass  # toggle logic prevents reapply


@register
class IronsoulAuraEffect(Effect):
    """Buff (Decontamination L4 'Ironsoul Aura'): toggle.
    While active: +1 DR per visible enemy in FOV (cap 5), +2 FOV radius.
    Hits from visible enemies grant +10 rad.
    25% on melee hit: lose damage dealt in radiation, gain it as armor.
    floor_duration so it persists until toggled off or floor ends."""
    id = "ironsoul_aura"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)
        self._cached_dr = 0

    @property
    def display_name(self) -> str:
        if self._cached_dr > 0:
            return f"Ironsoul Aura ({self._cached_dr} DR)"
        return "Ironsoul Aura"

    def apply(self, entity, engine):
        engine.fov_radius += 2
        engine._compute_fov()

    def _count_visible_enemies(self, engine) -> int:
        visible = engine.dungeon.visible
        count = 0
        for m in engine.dungeon.entities:
            if m.entity_type == "monster" and m.alive and visible[m.y][m.x]:
                count += 1
        return count

    def modify_incoming_damage(self, damage: int, entity) -> int:
        """Flat DR based on visible enemy count (cap 5)."""
        if not hasattr(entity, '_game_engine'):
            return damage
        engine = entity._game_engine
        dr = min(5, self._count_visible_enemies(engine))
        self._cached_dr = dr
        return max(1, damage - dr)

    def before_turn(self, entity, engine):
        """Cache the engine reference on entity for modify_incoming_damage."""
        entity._game_engine = engine

    def on_player_melee_hit(self, engine, defender, damage: int) -> None:
        """25% chance: lose damage dealt in radiation, gain it as armor."""
        import random
        if random.random() >= 0.25:
            return
        player = engine.player
        rad_to_lose = min(damage, player.radiation)
        if rad_to_lose <= 0:
            return
        from combat import remove_radiation
        remove_radiation(engine, player, rad_to_lose)
        max_armor = engine._compute_player_max_armor()
        armor_gain = min(rad_to_lose, max(0, max_armor - player.armor))
        if armor_gain > 0:
            player.armor += armor_gain
        engine.messages.append([
            ("Ironsoul! ", (180, 200, 255)),
            (f"-{rad_to_lose} rad → +{armor_gain} armor.", (160, 180, 240)),
        ])

    def expire(self, entity, engine):
        engine.fov_radius -= 2
        engine._compute_fov()
        if hasattr(entity, '_game_engine'):
            del entity._game_engine

    def on_reapply(self, existing, entity, engine):
        pass  # toggle logic prevents reapply


@register
class RetributionAuraEffect(Effect):
    """Buff (Decontamination L6 'Retribution Aura'): toggle.
    While active: enemies that melee you take rad/20 + Decon level true damage (cap 30).
    Drains 5 rad per proc. floor_duration, persists until toggled off or floor ends."""
    id = "retribution_aura"
    category = "buff"
    priority = 0

    def __init__(self, **kwargs):
        super().__init__(duration=9999, floor_duration=True, **kwargs)

    @property
    def display_name(self) -> str:
        return "Retribution Aura"

    def apply(self, entity, engine):
        pass

    def expire(self, entity, engine):
        pass

    def on_reapply(self, existing, entity, engine):
        pass  # toggle logic prevents reapply
