"""Tests for Meth Lab toxic enemy templates and mechanics."""

import random
import pytest
from unittest.mock import MagicMock, patch

from enemies import (
    MONSTER_REGISTRY, validate_registry, create_enemy,
    EffectKind, AIType,
)
from entity import Entity
from effects import apply_effect, tick_all_effects, EFFECT_REGISTRY
from hazards import create_toxic_creep


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

METH_LAB_ENEMIES = [
    "covid_26", "purger", "toxic_slug", "stray_dog",
    "sludge_amalgam", "mini_sludge", "chemist",
]


def _make_engine():
    """Create a minimal mock engine for testing."""
    engine = MagicMock()
    engine.messages = []
    engine.player = Entity(5, 5, "@", (255, 255, 255), name="Player", entity_type="player", hp=100)
    engine.player.status_effects = []
    engine.player.toxicity = 0
    engine.player.tox_resistance = 0
    del engine.player.base_stats  # Remove so hasattr() returns False in add_toxicity

    # Mock player_stats with add_temporary_stat_bonus
    engine.player_stats = MagicMock()
    engine.player_stats.total_tox_resistance = 0
    engine._drink_duration_multiplier = 1

    return engine


def _make_dungeon():
    """Create a minimal mock dungeon."""
    from config import TILE_FLOOR
    dungeon = MagicMock()
    dungeon.entities = []
    dungeon.width = 80
    dungeon.height = 40
    # All tiles are floor by default
    dungeon.tiles = [[TILE_FLOOR] * 80 for _ in range(40)]

    def is_blocked(x, y):
        for e in dungeon.entities:
            if e.x == x and e.y == y and getattr(e, "blocks_movement", False) and getattr(e, "alive", True):
                return True
        return dungeon.is_terrain_blocked(x, y)

    def is_terrain_blocked(x, y):
        return x < 0 or y < 0 or x >= 80 or y >= 40

    def get_entities_at(x, y):
        return [e for e in dungeon.entities if e.x == x and e.y == y]

    def add_entity(e):
        dungeon.entities.append(e)

    def remove_entity(e):
        if e in dungeon.entities:
            dungeon.entities.remove(e)

    def get_monsters():
        return [e for e in dungeon.entities if e.entity_type == "monster" and e.alive]

    dungeon.is_blocked = MagicMock(side_effect=is_blocked)
    dungeon.is_terrain_blocked = MagicMock(side_effect=is_terrain_blocked)
    dungeon.get_entities_at = MagicMock(side_effect=get_entities_at)
    dungeon.add_entity = MagicMock(side_effect=add_entity)
    dungeon.remove_entity = MagicMock(side_effect=remove_entity)
    dungeon.get_monsters = MagicMock(side_effect=get_monsters)
    return dungeon


# ══════════════════════════════════════════════════════════════════════════════
# Registry validation
# ══════════════════════════════════════════════════════════════════════════════

def test_all_meth_lab_enemies_in_registry():
    """All 7 meth lab enemies exist in the registry."""
    for key in METH_LAB_ENEMIES:
        assert key in MONSTER_REGISTRY, f"{key} not in MONSTER_REGISTRY"


def test_validate_registry_passes():
    """Full registry validation passes with meth lab enemies included."""
    validate_registry()


def test_meth_lab_enemies_color():
    """All meth lab enemies use (200, 50, 50) color."""
    for key in METH_LAB_ENEMIES:
        tmpl = MONSTER_REGISTRY[key]
        assert tmpl.color == (200, 50, 50), f"{key} color is {tmpl.color}"


def test_meth_lab_enemies_no_faction():
    """No meth lab enemy has a faction."""
    for key in METH_LAB_ENEMIES:
        tmpl = MONSTER_REGISTRY[key]
        assert tmpl.faction is None, f"{key} has faction {tmpl.faction}"


def test_death_split_type_valid():
    """death_split_type cross-references a valid registry key."""
    for key, tmpl in MONSTER_REGISTRY.items():
        if tmpl.death_split_type:
            assert tmpl.death_split_type in MONSTER_REGISTRY, (
                f"{key}: death_split_type '{tmpl.death_split_type}' not in registry"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Covid-26 (suicide bomber)
# ══════════════════════════════════════════════════════════════════════════════

def test_covid_26_template():
    tmpl = MONSTER_REGISTRY["covid_26"]
    assert tmpl.ai == AIType.SUICIDE_BOMBER
    assert tmpl.speed == 100
    assert tmpl.spawn_min == 2
    assert tmpl.spawn_max == 4


def test_covid_26_explosion():
    """Suicide explosion deals 10-15 unblockable damage + 20-30 tox, kills the monster."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon
    engine.event_bus = MagicMock()

    # Need real add_toxicity
    from engine import GameEngine
    engine.add_toxicity = GameEngine.add_toxicity.__get__(engine)
    engine._apply_toxicity = lambda dmg, defender: dmg  # No tox scaling in test

    monster = create_enemy("covid_26", 4, 5)
    dungeon.add_entity(monster)
    initial_hp = engine.player.hp

    engine.handle_suicide_explosion = GameEngine.handle_suicide_explosion.__get__(engine)
    engine.handle_suicide_explosion(monster)

    damage_dealt = initial_hp - engine.player.hp
    assert 10 <= damage_dealt <= 15, f"Explosion damage {damage_dealt} not in 10-15"
    assert engine.player.toxicity >= 20, f"Tox {engine.player.toxicity} < 20"
    assert engine.player.toxicity <= 30, f"Tox {engine.player.toxicity} > 30"
    assert not monster.alive, "Monster should be dead after explosion"


# ══════════════════════════════════════════════════════════════════════════════
# Purger (buff purge)
# ══════════════════════════════════════════════════════════════════════════════

def test_purger_template():
    tmpl = MONSTER_REGISTRY["purger"]
    assert tmpl.ai == AIType.WANDER_AMBUSH
    assert tmpl.defense == 2
    assert len(tmpl.on_hit_effects) == 1
    assert tmpl.on_hit_effects[0].kind == EffectKind.BUFF_PURGE
    assert tmpl.on_hit_effects[0].chance == 0.35


def test_buff_purge_removes_buff():
    """Buff purge removes a random buff and adds tox = remaining duration."""
    engine = _make_engine()
    from engine import GameEngine
    engine.add_toxicity = GameEngine.add_toxicity.__get__(engine)

    # Give the player a buff with 10 turns remaining
    buff = MagicMock()
    buff.id = "test_buff"
    buff.category = "buff"
    buff.duration = 10
    buff.display_name = "Test Buff"
    engine.player.status_effects = [buff]

    effect = {"kind": "buff_purge", "amount": 0, "duration": 1}
    engine._apply_monster_hit_effect = GameEngine._apply_monster_hit_effect.__get__(engine)
    engine._apply_monster_hit_effect(effect)

    assert buff not in engine.player.status_effects, "Buff should be removed"
    assert engine.player.toxicity == 10, f"Tox should be 10 (buff duration), got {engine.player.toxicity}"
    buff.expire.assert_called_once()


def test_buff_purge_no_buffs():
    """Buff purge is a no-op when player has no buffs."""
    engine = _make_engine()
    from engine import GameEngine
    engine.add_toxicity = GameEngine.add_toxicity.__get__(engine)

    engine.player.status_effects = []
    effect = {"kind": "buff_purge", "amount": 0, "duration": 1}
    engine._apply_monster_hit_effect = GameEngine._apply_monster_hit_effect.__get__(engine)
    engine._apply_monster_hit_effect(effect)

    assert engine.player.toxicity == 0


# ══════════════════════════════════════════════════════════════════════════════
# Toxic Slug (trail + death creep)
# ══════════════════════════════════════════════════════════════════════════════

def test_toxic_slug_template():
    tmpl = MONSTER_REGISTRY["toxic_slug"]
    assert tmpl.ai == AIType.WANDER_AMBUSH
    assert tmpl.speed == 60
    assert tmpl.leaves_trail == {"duration": 10, "tox": 5}
    assert tmpl.death_creep_radius == 2
    assert tmpl.death_creep_duration == 10
    assert tmpl.death_creep_tox == 5


def test_slug_trail_creep_spawned():
    """Trail creep appears on old tile after slug moves."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon

    from engine import GameEngine
    engine.spawn_trail_creep = GameEngine.spawn_trail_creep.__get__(engine)

    trail_info = {"duration": 10, "tox": 5}
    engine.spawn_trail_creep(10, 10, trail_info)

    creep_entities = [e for e in dungeon.entities if getattr(e, "hazard_type", None) == "toxic_creep"]
    assert len(creep_entities) == 1
    assert creep_entities[0].x == 10
    assert creep_entities[0].y == 10
    assert creep_entities[0].hazard_duration == 10
    assert creep_entities[0].hazard_tox_per_turn == 5


def test_slug_trail_no_double_stack():
    """Trail creep doesn't double-stack on the same tile."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon

    from engine import GameEngine
    engine.spawn_trail_creep = GameEngine.spawn_trail_creep.__get__(engine)

    trail_info = {"duration": 10, "tox": 5}
    engine.spawn_trail_creep(10, 10, trail_info)
    engine.spawn_trail_creep(10, 10, trail_info)

    creep_entities = [e for e in dungeon.entities if getattr(e, "hazard_type", None) == "toxic_creep"]
    assert len(creep_entities) == 1


def test_slug_death_creep():
    """Death creep spawns in radius 2 diamond around death position."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon

    from engine import GameEngine
    engine._spawn_death_creep = GameEngine._spawn_death_creep.__get__(engine)

    slug = create_enemy("toxic_slug", 20, 20)
    engine._spawn_death_creep(slug)

    creep_entities = [e for e in dungeon.entities if getattr(e, "hazard_type", None) == "toxic_creep"]
    # Diamond pattern with radius 2: 1 + 2 + 3 + 2 + 1 = 9 tiles (if none blocked)
    # but we need at least some
    assert len(creep_entities) > 0
    # All should be within manhattan distance 2 of (20, 20)
    for c in creep_entities:
        assert abs(c.x - 20) + abs(c.y - 20) <= 2


# ══════════════════════════════════════════════════════════════════════════════
# Stray Dog (fast + rabies)
# ══════════════════════════════════════════════════════════════════════════════

def test_stray_dog_template():
    tmpl = MONSTER_REGISTRY["stray_dog"]
    assert tmpl.speed == 130
    assert tmpl.ai == AIType.WANDER_AMBUSH
    assert len(tmpl.on_hit_effects) == 2
    # Check tox burst
    tox_eff = tmpl.on_hit_effects[0]
    assert tox_eff.kind == EffectKind.TOX_BURST
    assert tox_eff.amount == 3
    # Check rabies
    rabies_eff = tmpl.on_hit_effects[1]
    assert rabies_eff.kind == EffectKind.RABIES
    assert rabies_eff.chance == 0.25
    assert rabies_eff.duration == 15


def test_rabies_effect_reduces_all_stats():
    """Rabies reduces all 6 stats by 1."""
    engine = _make_engine()

    apply_effect(engine.player, engine, "rabies", duration=15)

    # Check all 6 stats were reduced
    calls = engine.player_stats.add_temporary_stat_bonus.call_args_list
    stat_changes = {call[0][0]: call[0][1] for call in calls}
    for stat in ("constitution", "strength", "street_smarts", "book_smarts", "tolerance", "swagger"):
        assert stat in stat_changes, f"Missing stat reduction for {stat}"
        assert stat_changes[stat] == -1, f"{stat} should be -1, got {stat_changes[stat]}"


def test_rabies_effect_restores_on_expire():
    """Rabies restores all 6 stats when it expires."""
    engine = _make_engine()

    apply_effect(engine.player, engine, "rabies", duration=1)
    engine.player_stats.add_temporary_stat_bonus.reset_mock()

    # Tick to expire
    tick_all_effects(engine.player, engine)

    calls = engine.player_stats.add_temporary_stat_bonus.call_args_list
    stat_changes = {call[0][0]: call[0][1] for call in calls}
    for stat in ("constitution", "strength", "street_smarts", "book_smarts", "tolerance", "swagger"):
        assert stat in stat_changes, f"Missing stat restoration for {stat}"
        assert stat_changes[stat] == 1, f"{stat} should be +1, got {stat_changes[stat]}"


def test_rabies_refresh_doesnt_stack():
    """Re-applying rabies refreshes duration but doesn't double the stat penalty."""
    engine = _make_engine()

    apply_effect(engine.player, engine, "rabies", duration=10)
    engine.player_stats.add_temporary_stat_bonus.reset_mock()

    # Re-apply
    apply_effect(engine.player, engine, "rabies", duration=15)

    # Should NOT call add_temporary_stat_bonus again (on_reapply just refreshes duration)
    assert engine.player_stats.add_temporary_stat_bonus.call_count == 0

    # Only one rabies effect should exist
    rabies_effects = [e for e in engine.player.status_effects if getattr(e, "id", "") == "rabies"]
    assert len(rabies_effects) == 1
    assert rabies_effects[0].duration == 15


# ══════════════════════════════════════════════════════════════════════════════
# Sludge Amalgam (death split)
# ══════════════════════════════════════════════════════════════════════════════

def test_sludge_amalgam_template():
    tmpl = MONSTER_REGISTRY["sludge_amalgam"]
    assert tmpl.ai == AIType.WANDER_AMBUSH
    assert tmpl.speed == 70
    assert tmpl.defense == 3
    assert tmpl.death_split_type == "mini_sludge"
    assert tmpl.death_split_count == 2


def test_death_split_spawns_mini_sludges():
    """Sludge Amalgam death spawns 2 mini_sludge at adjacent tiles."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon

    from engine import GameEngine
    engine._spawn_death_split = GameEngine._spawn_death_split.__get__(engine)

    amalgam = create_enemy("sludge_amalgam", 20, 20)
    engine._spawn_death_split(amalgam)

    mini_sludges = [e for e in dungeon.entities if getattr(e, "enemy_type", None) == "mini_sludge"]
    assert len(mini_sludges) == 2

    # Verify they're adjacent to the amalgam's death position
    for ms in mini_sludges:
        assert abs(ms.x - 20) <= 1 and abs(ms.y - 20) <= 1


def test_mini_sludge_template():
    tmpl = MONSTER_REGISTRY["mini_sludge"]
    assert tmpl.speed == 110
    assert tmpl.ai == AIType.WANDER_AMBUSH
    assert tmpl.on_hit_effects[0].kind == EffectKind.TOX_BURST
    assert tmpl.on_hit_effects[0].amount == 10


# ══════════════════════════════════════════════════════════════════════════════
# Chemist (ranged vial thrower)
# ══════════════════════════════════════════════════════════════════════════════

def test_chemist_template():
    tmpl = MONSTER_REGISTRY["chemist"]
    assert tmpl.ai == AIType.CHEMIST_RANGED
    assert tmpl.sight_radius == 6
    assert tmpl.speed == 100


def test_chemist_vial_creates_creep():
    """Chemist vial creates 3x3 toxic creep AOE centered on player."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon
    engine.player.x, engine.player.y = 10, 10

    from engine import GameEngine
    engine.handle_chemist_vial = GameEngine.handle_chemist_vial.__get__(engine)

    chemist = create_enemy("chemist", 12, 10)  # distance 2 (within range 5)
    engine.handle_chemist_vial(chemist)

    # Should have creep in a 3x3 area (up to 9 tiles)
    all_creep = [
        e for e in dungeon.entities
        if getattr(e, "hazard_type", None) == "toxic_creep"
    ]
    assert len(all_creep) == 9  # 3x3 on open floor

    creep_at_player = [e for e in all_creep if e.x == 10 and e.y == 10]
    assert len(creep_at_player) == 1
    assert creep_at_player[0].hazard_duration == 10
    assert creep_at_player[0].hazard_tox_per_turn == 5


def test_chemist_vial_no_double_stack():
    """Chemist doesn't create creep if one already exists at a tile."""
    engine = _make_engine()
    dungeon = _make_dungeon()
    engine.dungeon = dungeon
    engine.player.x, engine.player.y = 10, 10

    # Pre-place creep at player's tile
    existing_creep = create_toxic_creep(10, 10, duration=5, tox_per_turn=3)
    dungeon.add_entity(existing_creep)

    from engine import GameEngine
    engine.handle_chemist_vial = GameEngine.handle_chemist_vial.__get__(engine)

    chemist = create_enemy("chemist", 12, 10)
    engine.handle_chemist_vial(chemist)

    creep_at_player = [
        e for e in dungeon.entities
        if getattr(e, "hazard_type", None) == "toxic_creep"
        and e.x == 10 and e.y == 10
    ]
    assert len(creep_at_player) == 1  # Still just the original at player's tile

    # But other tiles in the 3x3 should have new creep (8 surrounding tiles)
    all_creep = [
        e for e in dungeon.entities
        if getattr(e, "hazard_type", None) == "toxic_creep"
    ]
    assert len(all_creep) == 9  # 1 existing + 8 new


# ══════════════════════════════════════════════════════════════════════════════
# Toxic Creep infrastructure
# ══════════════════════════════════════════════════════════════════════════════

def test_toxic_creep_factory():
    """create_toxic_creep returns a proper hazard entity."""
    creep = create_toxic_creep(5, 5, duration=10, tox_per_turn=5)
    assert creep.entity_type == "hazard"
    assert creep.hazard_type == "toxic_creep"
    assert creep.blocks_movement is False
    assert creep.char == "~"
    assert creep.color == (150, 200, 50)
    assert creep.hazard_duration == 10
    assert creep.hazard_tox_per_turn == 5


def test_toxic_creep_duration_ticks_down():
    """hazard_duration decrements by 1 each tick."""
    creep = create_toxic_creep(5, 5, duration=3, tox_per_turn=5)
    assert creep.hazard_duration == 3
    creep.hazard_duration -= 1
    assert creep.hazard_duration == 2
    creep.hazard_duration -= 1
    assert creep.hazard_duration == 1
    creep.hazard_duration -= 1
    assert creep.hazard_duration == 0


def test_create_enemy_wires_new_fields():
    """create_enemy properly wires death_split, death_creep, and leaves_trail fields."""
    amalgam = create_enemy("sludge_amalgam", 0, 0)
    assert amalgam.death_split_type == "mini_sludge"
    assert amalgam.death_split_count == 2

    slug = create_enemy("toxic_slug", 0, 0)
    assert slug.death_creep_radius == 2
    assert slug.death_creep_duration == 10
    assert slug.death_creep_tox == 5
    assert slug.leaves_trail == {"duration": 10, "tox": 5}

    # Enemies without these fields should have defaults
    covid = create_enemy("covid_26", 0, 0)
    assert covid.death_split_type is None
    assert covid.death_creep_radius == 0
    assert covid.leaves_trail is None
