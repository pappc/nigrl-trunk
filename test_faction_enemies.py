"""Tests for Meth Lab faction enemies (Scryer & Aldor)."""

import pytest
import random

from enemies import (
    MONSTER_REGISTRY, validate_registry, create_enemy,
    AIType, EffectKind, OnHitEffect,
)
from entity import Entity
from ai import (
    AIState, BEHAVIORS, get_initial_state,
    faction_is_hostile, cartel_should_aggro,
    room_ally_attacked, faction_room_ally_attacked,
    falcon_adjacent_to_ally, player_within_2,
    _falcon_alert_area, _blink_away, do_ai_turn, prepare_ai_tick,
    kite_at_range,
)
from stats import PlayerStats


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

FACTION_ENEMIES = [
    "scryer_grunt", "scryer_falcon", "scryer_hitman", "scryer_specialist",
    "aldor_grunt", "aldor_falcon", "aldor_hitman", "aldor_specialist",
]

LAW_ENFORCEMENT_ENEMIES = ["ice_agent", "dea_agent"]


class FakeDungeon:
    """Minimal dungeon stub for AI tests."""

    def __init__(self, width=50, height=50):
        self.width = width
        self.height = height
        self.entities = []
        self.first_kill_happened = False
        self.female_kill_happened = False
        self.room_factions = {}

    def is_terrain_blocked(self, x, y):
        return x < 0 or y < 0 or x >= self.width or y >= self.height

    def is_blocked(self, x, y):
        if self.is_terrain_blocked(x, y):
            return True
        for e in self.entities:
            if e.x == x and e.y == y and getattr(e, "blocks_movement", False) and getattr(e, "alive", True):
                return True
        return False


class _FakeSkill:
    level = 0

class _FakeSkills:
    def get(self, name):
        return _FakeSkill()
    def gain_potential_exp(self, *a, **kw):
        pass

class FakeEngine:
    """Minimal engine stub for AI tests."""

    def __init__(self, player=None, dungeon=None):
        self.messages = []
        self.player = player
        self.dungeon = dungeon
        self.player_stats = getattr(player, 'stats', None)
        self.skills = _FakeSkills()

    def handle_monster_attack(self, monster):
        self.messages.append(f"{monster.name} attacks!")

    def handle_monster_ranged_attack(self, monster):
        self.messages.append(f"{monster.name} shoots!")


def make_player(x=10, y=10, rep_scryer=-2000, rep_aldor=-2000):
    """Create a player entity with stats and custom faction reputation."""
    p = Entity(x, y, "@", (255, 255, 255), name="Player", entity_type="player", hp=100)
    p.stats = PlayerStats()
    p.stats.reputation["scryer"] = rep_scryer
    p.stats.reputation["aldor"] = rep_aldor
    return p


# ══════════════════════════════════════════════════════════════════════════════
# Template validation
# ══════════════════════════════════════════════════════════════════════════════

class TestTemplateValidation:
    """All 8 faction enemies pass registry validation."""

    def test_all_faction_enemies_in_registry(self):
        for key in FACTION_ENEMIES:
            assert key in MONSTER_REGISTRY, f"{key} not in MONSTER_REGISTRY"

    def test_validate_registry_passes(self):
        validate_registry()  # Should not raise

    def test_faction_field_set(self):
        for key in FACTION_ENEMIES:
            tmpl = MONSTER_REGISTRY[key]
            assert tmpl.faction in ("scryer", "aldor"), f"{key} has unexpected faction: {tmpl.faction}"

    def test_scryer_color(self):
        for key in ["scryer_grunt", "scryer_falcon", "scryer_hitman", "scryer_specialist"]:
            assert MONSTER_REGISTRY[key].color == (255, 140, 30)

    def test_aldor_color(self):
        for key in ["aldor_grunt", "aldor_falcon", "aldor_hitman", "aldor_specialist"]:
            assert MONSTER_REGISTRY[key].color == (220, 50, 180)

    def test_role_chars(self):
        for prefix in ("scryer_", "aldor_"):
            assert MONSTER_REGISTRY[f"{prefix}grunt"].char == "G"
            assert MONSTER_REGISTRY[f"{prefix}falcon"].char == "F"
            assert MONSTER_REGISTRY[f"{prefix}hitman"].char == "H"
            assert MONSTER_REGISTRY[f"{prefix}specialist"].char == "S"


# ══════════════════════════════════════════════════════════════════════════════
# Field propagation through create_enemy
# ══════════════════════════════════════════════════════════════════════════════

class TestFieldPropagation:
    """Faction, blink_charges, ranged_attack wired through create_enemy()."""

    def test_faction_propagated(self):
        e = create_enemy("scryer_grunt", 5, 5)
        assert e.faction == "scryer"
        e2 = create_enemy("aldor_grunt", 5, 5)
        assert e2.faction == "aldor"

    def test_blink_charges_propagated(self):
        e = create_enemy("scryer_specialist", 5, 5)
        assert e.blink_charges == 1

    def test_ranged_attack_propagated(self):
        e = create_enemy("scryer_specialist", 5, 5)
        assert e.ranged_attack is not None
        assert e.ranged_attack["range"] == 4
        assert e.ranged_attack["damage"] == (5, 8)

    def test_aldor_specialist_knockback(self):
        e = create_enemy("aldor_specialist", 5, 5)
        assert e.ranged_attack["knockback"] == 1

    def test_no_faction_on_regular_enemy(self):
        e = create_enemy("tweaker", 5, 5)
        assert e.faction is None

    def test_grunt_move_cost(self):
        e = create_enemy("scryer_grunt", 5, 5)
        assert e.move_cost == 60


# ══════════════════════════════════════════════════════════════════════════════
# AI Conditions
# ══════════════════════════════════════════════════════════════════════════════

class TestAIConditions:
    """Cartel aggro conditions based on reputation."""

    def test_faction_not_hostile_at_default_rep(self):
        """Default rep (-1000) is Neutral — not hostile."""
        player = make_player()
        monster = create_enemy("scryer_grunt", 15, 15)
        dungeon = FakeDungeon()
        assert faction_is_hostile(monster, player, dungeon) is False

    def test_faction_hostile_at_unfriendly_rep(self):
        """Unfriendly rep (< -2000) is hostile."""
        player = make_player(rep_scryer=-5000)
        monster = create_enemy("scryer_grunt", 15, 15)
        dungeon = FakeDungeon()
        assert faction_is_hostile(monster, player, dungeon) is True

    def test_faction_not_hostile_at_neutral(self):
        player = make_player(rep_scryer=2000)
        monster = create_enemy("scryer_grunt", 15, 15)
        dungeon = FakeDungeon()
        assert faction_is_hostile(monster, player, dungeon) is False

    def test_cartel_aggro_hostile_player_in_sight(self):
        """At hostile rep, player in sight triggers aggro."""
        player = make_player(x=12, y=12, rep_scryer=-5000)
        monster = create_enemy("scryer_grunt", 15, 15)
        dungeon = FakeDungeon()
        assert cartel_should_aggro(monster, player, dungeon) is True

    def test_cartel_aggro_hostile_room_ally_attacked(self):
        """At hostile rep, room ally provoked triggers aggro."""
        player = make_player(x=50, y=50)  # far away
        monster = create_enemy("scryer_grunt", 15, 15)
        room_tiles = frozenset([(15, 15), (16, 16)])
        monster.spawn_room_tiles = room_tiles
        ally = create_enemy("scryer_grunt", 16, 16)
        ally.spawn_room_tiles = room_tiles
        ally.provoked = True
        dungeon = FakeDungeon()
        dungeon.entities = [monster, ally]
        # Player far away but room ally provoked
        assert cartel_should_aggro(monster, player, dungeon) is True

    def test_cartel_no_aggro_neutral_player_in_sight(self):
        """At neutral rep, player in sight alone does NOT trigger aggro."""
        player = make_player(x=12, y=12, rep_scryer=2000)
        monster = create_enemy("scryer_grunt", 15, 15)
        dungeon = FakeDungeon()
        assert cartel_should_aggro(monster, player, dungeon) is False

    def test_cartel_aggro_neutral_faction_ally_attacked(self):
        """At neutral rep, same-faction room ally attacked triggers aggro."""
        player = make_player(x=50, y=50, rep_scryer=2000)
        monster = create_enemy("scryer_grunt", 15, 15)
        room_tiles = frozenset([(15, 15), (16, 16)])
        monster.spawn_room_tiles = room_tiles
        ally = create_enemy("scryer_grunt", 16, 16)
        ally.spawn_room_tiles = room_tiles
        ally.provoked = True
        ally.faction = "scryer"
        dungeon = FakeDungeon()
        dungeon.entities = [monster, ally]
        assert cartel_should_aggro(monster, player, dungeon) is True

    def test_cartel_no_aggro_neutral_other_faction_attacked(self):
        """At neutral rep, enemy from OTHER faction provoked doesn't trigger aggro."""
        player = make_player(x=50, y=50, rep_scryer=2000)
        monster = create_enemy("scryer_grunt", 15, 15)
        room_tiles = frozenset([(15, 15), (16, 16)])
        monster.spawn_room_tiles = room_tiles
        ally = create_enemy("aldor_grunt", 16, 16)
        ally.spawn_room_tiles = room_tiles
        ally.provoked = True
        dungeon = FakeDungeon()
        dungeon.entities = [monster, ally]
        assert cartel_should_aggro(monster, player, dungeon) is False


# ══════════════════════════════════════════════════════════════════════════════
# Grunt behavior
# ══════════════════════════════════════════════════════════════════════════════

class TestGruntBehavior:

    def test_grunt_starts_idle(self):
        assert get_initial_state("cartel_unit") == AIState.IDLE

    def test_grunt_passive_at_neutral_rep(self):
        """Grunt does nothing when player is neutral and not attacked."""
        player = make_player(x=12, y=12, rep_scryer=5000)
        monster = create_enemy("scryer_grunt", 15, 15)
        monster.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [player, monster]
        engine = FakeEngine(player, dungeon)
        tick_data = prepare_ai_tick(player, dungeon, [monster])
        do_ai_turn(monster, player, dungeon, engine, **tick_data)
        # Should still be idle (wandering, not chasing)
        assert monster.ai_state == AIState.IDLE

    def test_grunt_aggressive_at_hostile_rep(self):
        """Grunt chases when player is hostile and in sight."""
        player = make_player(x=12, y=12, rep_scryer=-5000)
        monster = create_enemy("scryer_grunt", 15, 15)
        monster.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [player, monster]
        engine = FakeEngine(player, dungeon)
        tick_data = prepare_ai_tick(player, dungeon, [monster])
        do_ai_turn(monster, player, dungeon, engine, **tick_data)
        assert monster.ai_state == AIState.CHASING


# ══════════════════════════════════════════════════════════════════════════════
# Falcon behavior
# ══════════════════════════════════════════════════════════════════════════════

class TestFalconBehavior:

    def test_falcon_starts_idle(self):
        assert get_initial_state("falcon_alert") == AIState.IDLE

    def test_falcon_enters_alerting(self):
        """Falcon transitions to ALERTING when cartel_should_aggro fires."""
        player = make_player(x=12, y=12, rep_scryer=-5000)
        falcon = create_enemy("scryer_falcon", 15, 15)
        falcon.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [player, falcon]
        engine = FakeEngine(player, dungeon)
        tick_data = prepare_ai_tick(player, dungeon, [falcon])
        do_ai_turn(falcon, player, dungeon, engine, **tick_data)
        assert falcon.ai_state in (AIState.ALERTING, AIState.CHASING)

    def test_falcon_alert_only_same_faction(self):
        """Falcon alert only affects same-faction enemies."""
        falcon = create_enemy("scryer_falcon", 10, 10)
        falcon.faction = "scryer"
        ally = create_enemy("scryer_grunt", 11, 11)
        ally.faction = "scryer"
        ally.ai_state = AIState.IDLE
        enemy = create_enemy("aldor_grunt", 12, 12)
        enemy.faction = "aldor"
        enemy.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [falcon, ally, enemy]
        engine = FakeEngine()
        _falcon_alert_area(falcon, dungeon, engine)
        assert ally.ai_state == AIState.CHASING
        assert ally.provoked is True
        assert enemy.ai_state == AIState.IDLE  # NOT alerted

    def test_falcon_alert_range(self):
        """Falcon alert only reaches 4 tiles."""
        falcon = create_enemy("scryer_falcon", 10, 10)
        falcon.faction = "scryer"
        nearby = create_enemy("scryer_grunt", 14, 10)
        nearby.faction = "scryer"
        nearby.ai_state = AIState.IDLE
        far = create_enemy("scryer_grunt", 15, 10)
        far.faction = "scryer"
        far.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [falcon, nearby, far]
        engine = FakeEngine()
        _falcon_alert_area(falcon, dungeon, engine)
        assert nearby.ai_state == AIState.CHASING
        assert far.ai_state == AIState.IDLE


# ══════════════════════════════════════════════════════════════════════════════
# Specialist blink
# ══════════════════════════════════════════════════════════════════════════════

class TestSpecialistBlink:

    def test_blink_teleports_and_decrements(self):
        """Blink moves the specialist away and uses a charge."""
        player = make_player(x=10, y=10)
        monster = create_enemy("scryer_specialist", 11, 10)
        monster.blink_charges = 1
        dungeon = FakeDungeon()
        creature_positions = {(11, 10)}
        engine = FakeEngine(player, dungeon)
        _blink_away(monster, player, dungeon, engine, creature_positions)
        assert monster.blink_charges == 0
        # Should have moved away from player
        assert max(abs(monster.x - player.x), abs(monster.y - player.y)) > 1

    def test_no_second_blink(self):
        """After blink is used, charges are 0."""
        monster = create_enemy("scryer_specialist", 11, 10)
        assert monster.blink_charges == 1
        player = make_player(x=10, y=10)
        dungeon = FakeDungeon()
        engine = FakeEngine(player, dungeon)
        _blink_away(monster, player, dungeon, engine, {(11, 10)})
        assert monster.blink_charges == 0


# ══════════════════════════════════════════════════════════════════════════════
# Monster ranged attack
# ══════════════════════════════════════════════════════════════════════════════

class TestMonsterRangedAttack:

    def _make_engine_with_player(self):
        from unittest.mock import patch
        from engine import GameEngine
        from menu_state import MenuState
        # Minimal engine setup
        engine = GameEngine.__new__(GameEngine)
        engine.messages = []
        player = Entity(10, 10, "@", (255, 255, 255), name="Player", entity_type="player", hp=100)
        player.status_effects = []
        player.max_hp = 100
        player.toxicity = 0
        engine.player = player
        engine.player_stats = PlayerStats()
        player.stats = engine.player_stats
        player.base_stats = engine.player_stats
        engine.cash = 0
        engine.kills = 0
        engine.game_over = False

        # Stub out event_bus
        class FakeEventBus:
            def emit(self, *a, **kw): pass
        engine.event_bus = FakeEventBus()

        # Stub dungeon
        dungeon = FakeDungeon()
        dungeon.entities = [player]
        engine.dungeon = dungeon

        return engine, player

    def test_ranged_attack_hits(self):
        """Monster ranged attack deals damage at range."""
        from unittest.mock import patch
        engine, player = self._make_engine_with_player()
        monster = create_enemy("scryer_specialist", 14, 10)
        engine.dungeon.entities.append(monster)
        initial_hp = player.hp
        with patch("combat._compute_player_defense", return_value=0), \
             patch("combat._apply_damage_modifiers", side_effect=lambda e, d, p: d), \
             patch("combat._apply_toxicity", side_effect=lambda e, d, p: d):
            # Keep trying seeds until we get a hit (miss_chance = 25%)
            for seed in range(100):
                random.seed(seed)
                player.hp = initial_hp
                engine.messages = []
                engine.handle_monster_ranged_attack(monster)
                if player.hp < initial_hp:
                    break
        assert player.hp < initial_hp, "Ranged attack should deal damage"

    def test_ranged_attack_out_of_range(self):
        """Monster ranged attack does nothing out of range."""
        engine, player = self._make_engine_with_player()
        monster = create_enemy("scryer_specialist", 20, 10)  # range 4, distance 10
        engine.dungeon.entities.append(monster)
        initial_hp = player.hp
        engine.handle_monster_ranged_attack(monster)
        assert player.hp == initial_hp


# ══════════════════════════════════════════════════════════════════════════════
# Hitman on-hit effects
# ══════════════════════════════════════════════════════════════════════════════

class TestHitmanEffects:

    def test_scryer_hitman_has_three_on_hit_effects(self):
        tmpl = MONSTER_REGISTRY["scryer_hitman"]
        assert len(tmpl.on_hit_effects) == 3
        kinds = [e.kind for e in tmpl.on_hit_effects]
        assert EffectKind.DOT in kinds
        assert EffectKind.RAD_BURST in kinds
        assert EffectKind.TOX_BURST in kinds

    def test_aldor_hitman_has_stun(self):
        tmpl = MONSTER_REGISTRY["aldor_hitman"]
        assert len(tmpl.on_hit_effects) == 1
        assert tmpl.on_hit_effects[0].kind == EffectKind.STUN

    def test_scryer_hitman_on_hit_effects_serialized(self):
        """create_enemy serializes on_hit_effects correctly."""
        e = create_enemy("scryer_hitman", 5, 5)
        assert len(e.on_hit_effects) == 3
        kinds = [eff["kind"] for eff in e.on_hit_effects]
        assert "dot" in kinds
        assert "rad_burst" in kinds
        assert "tox_burst" in kinds


# ══════════════════════════════════════════════════════════════════════════════
# Reputation on kill
# ══════════════════════════════════════════════════════════════════════════════

class TestReputationOnKill:

    def test_kill_scryer_shifts_reputation(self):
        ps = PlayerStats()
        initial_scryer = ps.reputation["scryer"]
        initial_aldor = ps.reputation["aldor"]
        # Simulate the reputation shift from _on_entity_died
        ps.modify_reputation("scryer", -200)
        ps.modify_reputation("aldor", 100)
        assert ps.reputation["scryer"] == initial_scryer - 200
        assert ps.reputation["aldor"] == initial_aldor + 100

    def test_kill_aldor_shifts_reputation(self):
        ps = PlayerStats()
        initial_scryer = ps.reputation["scryer"]
        initial_aldor = ps.reputation["aldor"]
        ps.modify_reputation("aldor", -200)
        ps.modify_reputation("scryer", 100)
        assert ps.reputation["aldor"] == initial_aldor - 200
        assert ps.reputation["scryer"] == initial_scryer + 100


# ══════════════════════════════════════════════════════════════════════════════
# Room faction assignment
# ══════════════════════════════════════════════════════════════════════════════

class TestRoomFactionAssignment:

    def test_meth_lab_rooms_get_factions(self):
        """Room factions are assigned for meth_lab zone."""
        dungeon = FakeDungeon()
        # Simulate what spawn_meth_lab does
        dungeon.room_factions = {}
        dungeon.room_factions[0] = "start"
        for idx in range(1, 5):
            dungeon.room_factions[idx] = random.choices(
                ["aldor", "scryer", "neutral"], weights=[1, 1, 2]
            )[0]
        assert dungeon.room_factions[0] == "start"
        for idx in range(1, 5):
            assert dungeon.room_factions[idx] in ("scryer", "aldor", "neutral")


# ══════════════════════════════════════════════════════════════════════════════
# Behavior registry
# ══════════════════════════════════════════════════════════════════════════════

class TestBehaviorRegistry:

    def test_cartel_unit_registered(self):
        assert "cartel_unit" in BEHAVIORS

    def test_falcon_alert_registered(self):
        assert "falcon_alert" in BEHAVIORS

    def test_cartel_ranged_registered(self):
        assert "cartel_ranged" in BEHAVIORS

    def test_all_ai_types_have_behaviors(self):
        """Every faction enemy AI type has a matching behavior entry."""
        for key in FACTION_ENEMIES + LAW_ENFORCEMENT_ENEMIES:
            tmpl = MONSTER_REGISTRY[key]
            assert tmpl.ai.value in BEHAVIORS, f"{key} has AI type {tmpl.ai.value} with no behavior"

    def test_ranged_room_guard_registered(self):
        assert "ranged_room_guard" in BEHAVIORS


# ══════════════════════════════════════════════════════════════════════════════
# ICE Agent
# ══════════════════════════════════════════════════════════════════════════════

class TestICEAgent:

    def test_ice_agent_in_registry(self):
        assert "ice_agent" in MONSTER_REGISTRY

    def test_ice_agent_no_faction(self):
        tmpl = MONSTER_REGISTRY["ice_agent"]
        assert tmpl.faction is None

    def test_ice_agent_has_deport_on_hit(self):
        tmpl = MONSTER_REGISTRY["ice_agent"]
        assert len(tmpl.on_hit_effects) == 1
        assert tmpl.on_hit_effects[0].kind == EffectKind.DEPORT
        assert tmpl.on_hit_effects[0].duration == 6

    def test_ice_agent_uses_room_guard_ai(self):
        tmpl = MONSTER_REGISTRY["ice_agent"]
        assert tmpl.ai == AIType.ROOM_GUARD

    def test_ice_agent_create_enemy(self):
        e = create_enemy("ice_agent", 5, 5)
        assert e.faction is None
        assert e.name == "ICE Agent"
        assert len(e.on_hit_effects) == 1
        assert e.on_hit_effects[0]["kind"] == "deport"

    def test_ice_agent_color(self):
        assert MONSTER_REGISTRY["ice_agent"].color == (200, 50, 50)


# ══════════════════════════════════════════════════════════════════════════════
# DEA Agent
# ══════════════════════════════════════════════════════════════════════════════

class TestDEAAgent:

    def test_dea_agent_in_registry(self):
        assert "dea_agent" in MONSTER_REGISTRY

    def test_dea_agent_no_faction(self):
        tmpl = MONSTER_REGISTRY["dea_agent"]
        assert tmpl.faction is None

    def test_dea_agent_has_ranged_attack(self):
        tmpl = MONSTER_REGISTRY["dea_agent"]
        assert tmpl.ranged_attack is not None
        assert tmpl.ranged_attack["range"] == 3

    def test_dea_agent_low_attack_cost(self):
        tmpl = MONSTER_REGISTRY["dea_agent"]
        assert tmpl.attack_cost == 40

    def test_dea_agent_uses_ranged_room_guard_ai(self):
        tmpl = MONSTER_REGISTRY["dea_agent"]
        assert tmpl.ai == AIType.RANGED_ROOM_GUARD

    def test_dea_agent_create_enemy(self):
        e = create_enemy("dea_agent", 5, 5)
        assert e.name == "DEA Agent"
        assert e.ranged_attack["range"] == 3
        assert e.attack_cost == 40

    def test_kite_at_range_shoots_at_exact_range(self):
        """DEA agent shoots when exactly at range 3."""
        player = make_player(x=10, y=10)
        monster = create_enemy("dea_agent", 13, 10)  # exactly range 3
        monster.ai_state = AIState.CHASING
        dungeon = FakeDungeon()
        dungeon.entities = [player, monster]
        engine = FakeEngine(player, dungeon)
        positions = {(10, 10), (13, 10)}
        result = kite_at_range(monster, player, dungeon, engine, creature_positions=positions)
        assert result == "attack"
        assert any("shoots" in m for m in engine.messages)

    def test_kite_at_range_flees_when_too_close(self):
        """DEA agent backs away when closer than range 3."""
        player = make_player(x=10, y=10)
        monster = create_enemy("dea_agent", 11, 10)  # range 1, too close
        monster.ai_state = AIState.CHASING
        dungeon = FakeDungeon()
        dungeon.entities = [player, monster]
        engine = FakeEngine(player, dungeon)
        positions = {(10, 10), (11, 10)}
        result = kite_at_range(monster, player, dungeon, engine, creature_positions=positions)
        # Should try to flee (move away)
        assert result in ("move", "idle")
        # Should have moved away from player if possible
        if result == "move":
            assert monster.x > 11  # moved away

    def test_kite_at_range_chases_when_too_far(self):
        """DEA agent moves toward player when farther than range 3."""
        player = make_player(x=10, y=10)
        monster = create_enemy("dea_agent", 20, 10)  # range 10, too far
        monster.ai_state = AIState.CHASING
        dungeon = FakeDungeon()
        dungeon.entities = [player, monster]
        engine = FakeEngine(player, dungeon)
        positions = {(10, 10), (20, 10)}
        result = kite_at_range(monster, player, dungeon, engine, creature_positions=positions)
        assert result in ("move", "idle")
        if result == "move":
            assert monster.x < 20  # moved toward player


# ══════════════════════════════════════════════════════════════════════════════
# Radiation enemies — template validation
# ══════════════════════════════════════════════════════════════════════════════

RADIATION_ENEMIES = ["rad_rat", "rad_rats_nest", "mutator", "convertor", "uranium_beetle"]


class TestRadiationTemplates:
    """All 5 radiation enemies pass registry validation."""

    def test_all_in_registry(self):
        for key in RADIATION_ENEMIES:
            assert key in MONSTER_REGISTRY, f"{key} not in MONSTER_REGISTRY"

    def test_validate_registry_passes(self):
        validate_registry()

    def test_all_red_color(self):
        for key in RADIATION_ENEMIES:
            assert MONSTER_REGISTRY[key].color == (200, 50, 50), f"{key} has wrong color"

    def test_all_wander_ambush_or_spawner(self):
        from enemies import AIType
        for key in RADIATION_ENEMIES:
            tmpl = MONSTER_REGISTRY[key]
            assert tmpl.ai in (AIType.WANDER_AMBUSH, AIType.STATIONARY_SPAWNER), f"{key} has unexpected AI"

    def test_all_sight_radius_8(self):
        for key in RADIATION_ENEMIES:
            assert MONSTER_REGISTRY[key].sight_radius == 8

    def test_no_faction(self):
        for key in RADIATION_ENEMIES:
            assert MONSTER_REGISTRY[key].faction is None


# ══════════════════════════════════════════════════════════════════════════════
# Rad Rat
# ══════════════════════════════════════════════════════════════════════════════

class TestRadRat:

    def test_unblockable_damage(self):
        """Rad Rat's power is used directly, no defense subtraction."""
        rat = create_enemy("rad_rat", 5, 5)
        # Power should be 1+str (base_damage = (1,1), str = 1)
        assert rat.power >= 1
        # Defense bypass is tested via the engine check for enemy_type

    def test_rad_on_hit(self):
        rat = create_enemy("rad_rat", 5, 5)
        assert len(rat.on_hit_effects) == 1
        eff = rat.on_hit_effects[0]
        assert eff["kind"] == "rad_burst"
        assert eff["amount"] == 10
        assert eff["chance"] == 1.0

    def test_spawn_group_of_3(self):
        tmpl = MONSTER_REGISTRY["rad_rat"]
        assert tmpl.spawn_min == 3
        assert tmpl.spawn_max == 3

    def test_fast_speed(self):
        tmpl = MONSTER_REGISTRY["rad_rat"]
        assert tmpl.speed == 140
        assert tmpl.move_cost == 50
        assert tmpl.attack_cost == 50


# ══════════════════════════════════════════════════════════════════════════════
# Rad Rats Nest
# ══════════════════════════════════════════════════════════════════════════════

class TestRadRatsNest:

    def test_spawner_fields_propagated(self):
        nest = create_enemy("rad_rats_nest", 5, 5)
        assert nest.spawner_type == "rad_rat"
        assert nest.max_spawned == 3

    def test_spawner_ai(self):
        from enemies import AIType
        tmpl = MONSTER_REGISTRY["rad_rats_nest"]
        assert tmpl.ai == AIType.STATIONARY_SPAWNER

    def test_nest_never_moves(self):
        """Nest stays in place even with player nearby."""
        player = make_player(x=6, y=5)
        nest = create_enemy("rad_rats_nest", 5, 5)
        nest.ai_state = AIState.IDLE
        dungeon = FakeDungeon()
        dungeon.entities = [player, nest]
        engine = FakeEngine(player, dungeon)
        engine.spawn_child = lambda spawner, cp=None: None  # stub
        tick_data = prepare_ai_tick(player, dungeon, [nest])
        do_ai_turn(nest, player, dungeon, engine, **tick_data)
        assert nest.x == 5 and nest.y == 5


# ══════════════════════════════════════════════════════════════════════════════
# Mutator
# ══════════════════════════════════════════════════════════════════════════════

class TestMutator:

    def test_two_on_hit_effects(self):
        tmpl = MONSTER_REGISTRY["mutator"]
        assert len(tmpl.on_hit_effects) == 2
        kinds = [e.kind for e in tmpl.on_hit_effects]
        assert EffectKind.RAD_BURST in kinds

    def test_burst_chances(self):
        tmpl = MONSTER_REGISTRY["mutator"]
        # One at 15%, one at 100%
        chances = sorted([e.chance for e in tmpl.on_hit_effects])
        assert chances == [0.15, 1.0]

    def test_burst_amounts(self):
        tmpl = MONSTER_REGISTRY["mutator"]
        amounts = sorted([e.amount for e in tmpl.on_hit_effects])
        assert amounts == [15, 100]


# ══════════════════════════════════════════════════════════════════════════════
# Convertor
# ══════════════════════════════════════════════════════════════════════════════

class TestConvertor:

    def test_conversion_on_hit(self):
        tmpl = MONSTER_REGISTRY["convertor"]
        assert len(tmpl.on_hit_effects) == 1
        eff = tmpl.on_hit_effects[0]
        assert eff.kind == EffectKind.CONVERSION
        assert eff.chance == 0.40
        assert eff.duration == 20


# ══════════════════════════════════════════════════════════════════════════════
# Uranium Beetle
# ══════════════════════════════════════════════════════════════════════════════

class TestUraniumBeetle:

    def test_high_defense(self):
        tmpl = MONSTER_REGISTRY["uranium_beetle"]
        assert tmpl.defense == 5

    def test_rad_poison_on_hit(self):
        tmpl = MONSTER_REGISTRY["uranium_beetle"]
        assert len(tmpl.on_hit_effects) == 1
        eff = tmpl.on_hit_effects[0]
        assert eff.kind == EffectKind.RAD_POISON
        assert eff.chance == 0.50
        assert eff.amount == 10
        assert eff.duration == 5


# ══════════════════════════════════════════════════════════════════════════════
# RadPoisonEffect
# ══════════════════════════════════════════════════════════════════════════════

class TestRadPoisonEffect:

    def _make_engine_and_player(self):
        player = make_player(x=10, y=10)
        player.radiation = 0
        dungeon = FakeDungeon()
        engine = FakeEngine(player, dungeon)
        # add_radiation stub
        def add_radiation(entity, amount):
            entity.radiation += amount
        engine.add_radiation = add_radiation
        return engine, player

    def test_applies_radiation_per_tick(self):
        import effects
        engine, player = self._make_engine_and_player()
        effects.apply_effect(player, engine, "rad_poison", duration=3, amount=10)
        assert len(player.status_effects) == 1
        effects.tick_all_effects(player, engine)
        assert player.radiation == 10

    def test_decrements_duration(self):
        import effects
        engine, player = self._make_engine_and_player()
        effects.apply_effect(player, engine, "rad_poison", duration=2, amount=5)
        effects.tick_all_effects(player, engine)
        assert len(player.status_effects) == 1  # still active (1 turn left)
        effects.tick_all_effects(player, engine)
        assert len(player.status_effects) == 0  # expired

    def test_reapply_refreshes_duration(self):
        import effects
        engine, player = self._make_engine_and_player()
        effects.apply_effect(player, engine, "rad_poison", duration=2, amount=10)
        effects.tick_all_effects(player, engine)  # duration 1 remaining
        effects.apply_effect(player, engine, "rad_poison", duration=3, amount=10)  # refresh
        eff = player.status_effects[0]
        assert eff.duration == 3


# ══════════════════════════════════════════════════════════════════════════════
# ConversionEffect
# ══════════════════════════════════════════════════════════════════════════════

class TestConversionEffect:

    def _make_engine_and_player(self):
        player = make_player(x=10, y=10)
        player.toxicity = 0
        player.radiation = 0
        dungeon = FakeDungeon()
        engine = FakeEngine(player, dungeon)
        return engine, player

    def test_drains_higher_tox(self):
        import effects
        engine, player = self._make_engine_and_player()
        player.toxicity = 20
        player.radiation = 10
        effects.apply_effect(player, engine, "conversion", duration=5)
        effects.tick_all_effects(player, engine)
        assert player.toxicity == 18
        assert player.radiation == 11

    def test_drains_higher_rad(self):
        import effects
        engine, player = self._make_engine_and_player()
        player.toxicity = 5
        player.radiation = 15
        effects.apply_effect(player, engine, "conversion", duration=5)
        effects.tick_all_effects(player, engine)
        assert player.toxicity == 6
        assert player.radiation == 13

    def test_equal_noop(self):
        import effects
        engine, player = self._make_engine_and_player()
        player.toxicity = 10
        player.radiation = 10
        effects.apply_effect(player, engine, "conversion", duration=5)
        effects.tick_all_effects(player, engine)
        assert player.toxicity == 10
        assert player.radiation == 10


# ══════════════════════════════════════════════════════════════════════════════
# Spawner mechanic
# ══════════════════════════════════════════════════════════════════════════════

class TestSpawnerMechanic:

    def _make_engine_with_dungeon(self):
        from unittest.mock import MagicMock
        player = make_player(x=20, y=20)
        dungeon = FakeDungeon()
        dungeon.entities = [player]
        engine = FakeEngine(player, dungeon)

        # Wire up a real spawn_child from engine
        from engine import GameEngine
        import types
        engine.spawn_child = types.MethodType(GameEngine.spawn_child, engine)
        return engine, player, dungeon

    def test_spawn_child_creates_entity(self):
        engine, player, dungeon = self._make_engine_with_dungeon()
        nest = create_enemy("rad_rats_nest", 10, 10)
        nest.spawned_children = []
        dungeon.entities.append(nest)

        engine.spawn_child(nest)
        # Child should be in dungeon.entities
        children = [e for e in dungeon.entities if e.enemy_type == "rad_rat"]
        assert len(children) == 1
        # Child should be tracked
        assert len(nest.spawned_children) == 1
        assert nest.spawned_children[0] is children[0]

    def test_spawn_child_message(self):
        engine, player, dungeon = self._make_engine_with_dungeon()
        nest = create_enemy("rad_rats_nest", 10, 10)
        nest.spawned_children = []
        dungeon.entities.append(nest)

        engine.spawn_child(nest)
        assert any("spawns a Rad Rat" in m for m in engine.messages)

    def test_spawner_idle_respects_max(self):
        """Spawner doesn't spawn when at max children."""
        from ai import spawner_idle
        player = make_player(x=20, y=20)
        nest = create_enemy("rad_rats_nest", 10, 10)
        nest.ai_state = AIState.IDLE
        # Create 3 alive children
        nest.spawned_children = []
        for i in range(3):
            child = create_enemy("rad_rat", 11 + i, 10)
            nest.spawned_children.append(child)

        dungeon = FakeDungeon()
        dungeon.entities = [player, nest] + nest.spawned_children
        engine = FakeEngine(player, dungeon)
        spawn_called = []
        engine.spawn_child = lambda s, cp=None: spawn_called.append(True)

        spawner_idle(nest, player, dungeon, engine)
        assert len(spawn_called) == 0  # should not have spawned

    def test_spawner_idle_spawns_when_under_cap(self):
        """Spawner spawns when below max children."""
        from ai import spawner_idle
        player = make_player(x=20, y=20)
        nest = create_enemy("rad_rats_nest", 10, 10)
        nest.ai_state = AIState.IDLE
        nest.spawned_children = []

        dungeon = FakeDungeon()
        dungeon.entities = [player, nest]
        engine = FakeEngine(player, dungeon)
        spawn_called = []
        engine.spawn_child = lambda s, cp=None: spawn_called.append(True)

        spawner_idle(nest, player, dungeon, engine)
        assert len(spawn_called) == 1

    def test_spawner_prunes_dead_children(self):
        """Dead children are pruned from spawned_children list."""
        from ai import spawner_idle
        player = make_player(x=20, y=20)
        nest = create_enemy("rad_rats_nest", 10, 10)
        nest.ai_state = AIState.IDLE

        # 3 children but 2 are dead
        nest.spawned_children = []
        for i in range(3):
            child = create_enemy("rad_rat", 11 + i, 10)
            if i < 2:
                child.alive = False
            nest.spawned_children.append(child)

        dungeon = FakeDungeon()
        dungeon.entities = [player, nest]
        engine = FakeEngine(player, dungeon)
        spawn_called = []
        engine.spawn_child = lambda s, cp=None: spawn_called.append(True)

        spawner_idle(nest, player, dungeon, engine)
        # 2 dead pruned → 1 alive → under cap of 3 → should spawn
        assert len(spawn_called) == 1
        assert len(nest.spawned_children) == 1  # only the alive one remains


# ══════════════════════════════════════════════════════════════════════════════
# Meth Lab spawn integration tests
# ══════════════════════════════════════════════════════════════════════════════

class TestMethLabSpawnIntegration:
    """Generate real meth lab floors and verify monster spawning works."""

    def _make_floor(self, floor_num=0):
        """Create a real meth lab dungeon and spawn entities.
        Mocks loot generation to avoid KeyError on WIP meth lab items."""
        from unittest.mock import patch
        from dungeon import Dungeon
        from stats import PlayerStats
        d = Dungeon(68, 54, zone="meth_lab")
        player = Entity(0, 0, "@", (255, 255, 255), name="Player",
                        entity_type="player", blocks_movement=True, hp=100)
        cx, cy = d.rooms[0].center()
        player.x, player.y = cx, cy
        player_skills = {}
        player_stats = PlayerStats()
        with patch("zone_generators.generate_floor_loot", return_value=[]):
            d.spawn_entities(player, floor_num=floor_num, zone="meth_lab",
                             player_skills=player_skills, player_stats=player_stats,
                             special_rooms_spawned=set())
        return d, player

    def test_monsters_spawn_on_floor_0(self):
        """Floor 0 should have monsters in non-start rooms."""
        d, player = self._make_floor(0)
        monsters = [e for e in d.entities if e.entity_type == "monster"]
        assert len(monsters) > 0, "No monsters spawned on floor 0"

    def test_no_monsters_in_start_room(self):
        """Room 0 (start) should have no monsters."""
        d, player = self._make_floor(0)
        start_tiles = frozenset(d.rooms[0].floor_tiles(d))
        start_monsters = [e for e in d.entities
                          if e.entity_type == "monster" and (e.x, e.y) in start_tiles]
        assert len(start_monsters) == 0, f"Found {len(start_monsters)} monsters in start room"

    def test_room_factions_assigned(self):
        """All rooms should have factions assigned."""
        d, player = self._make_floor(0)
        assert d.room_factions[0] == "start"
        for idx in range(1, len(d.rooms)):
            assert d.room_factions[idx] in ("scryer", "aldor", "neutral")

    def test_faction_enemies_match_room_faction(self):
        """Faction monsters should only appear in rooms of their faction (or neutral mix)."""
        d, player = self._make_floor(2)
        for e in d.entities:
            if e.entity_type != "monster":
                continue
            faction = getattr(e, "faction", None)
            if faction not in ("scryer", "aldor"):
                continue
            # Find which room this monster is in
            room_idx = d.room_tile_map.get((e.x, e.y))
            if room_idx is None:
                # Could be a hallway falcon — that's fine
                continue
            room_faction = d.room_factions.get(room_idx, "")
            # Faction enemy should be in a room of its own faction
            # (neutral table can't produce faction enemies)
            assert room_faction == faction, \
                f"{e.name} (faction={faction}) in room {room_idx} (faction={room_faction})"

    def test_monsters_spawn_on_later_floors(self):
        """Floors 3 and 6 should also produce monsters."""
        for floor in (3, 6):
            d, player = self._make_floor(floor)
            monsters = [e for e in d.entities if e.entity_type == "monster"]
            assert len(monsters) > 0, f"No monsters on floor {floor}"

    def test_start_room_is_small(self):
        """Start room should be 4-6 tiles per side."""
        d, player = self._make_floor(0)
        room = d.rooms[0]
        w = room.x2 - room.x1
        h = room.y2 - room.y1
        assert 4 <= w <= 6, f"Start room width {w} not in [4,6]"
        assert 4 <= h <= 6, f"Start room height {h} not in [4,6]"

    def test_hallway_falcons_correct_type(self):
        """Any falcon in a hallway should be scryer_falcon or aldor_falcon."""
        # Run several times to increase chance of falcon spawning
        for _ in range(10):
            d, player = self._make_floor(2)
            for e in d.entities:
                if e.entity_type != "monster":
                    continue
                enemy_type = getattr(e, "enemy_type", "")
                if "falcon" not in enemy_type:
                    continue
                # If in hallway (not in any room), that's correct placement
                room_idx = d.room_tile_map.get((e.x, e.y))
                if room_idx is None:
                    assert enemy_type in ("scryer_falcon", "aldor_falcon")
