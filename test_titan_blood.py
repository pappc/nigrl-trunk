"""Tests for Titan's Blood Ring — proc, expiry, and anti-exploit."""

import pytest
from unittest.mock import patch
from engine import GameEngine
from entity import Entity
from items import create_item_entity, ITEM_DEFS
from effects import TitanFormEffect, tick_all_effects


def _make_engine():
    engine = GameEngine(seed="TITAN")
    engine.player.max_hp = 100
    engine.player.hp = 100
    return engine


def _equip_titan_ring(engine):
    """Create and equip a Titan's Blood Ring."""
    ring_id = None
    for item_id, defn in ITEM_DEFS.items():
        if "titan_blood" in defn.get("tags", []):
            ring_id = item_id
            break
    assert ring_id is not None, "No item with titan_blood tag found"
    kwargs = create_item_entity(ring_id, 0, 0)
    ring = Entity(**kwargs)
    engine.rings[0] = ring
    return ring


def _has_titan_form(engine):
    return any(getattr(e, 'id', '') == 'titan_form' for e in engine.player.status_effects)


def _get_titan_form(engine):
    return next((e for e in engine.player.status_effects if getattr(e, 'id', '') == 'titan_form'), None)


class TestTitanBloodProc:
    """Titan Form activates when dropping below 25% HP with ring equipped."""

    def test_procs_on_crossing_25_percent(self):
        engine = _make_engine()
        _equip_titan_ring(engine)
        assert engine._titan_blood_available
        assert engine._titan_blood_was_above_25

        # Drop to 24 HP (below 25%)
        engine.player.hp = 24
        engine._check_titan_blood_proc()

        assert _has_titan_form(engine), "Titan Form should activate below 25%"
        assert not engine._titan_blood_available, "Should be consumed for this floor"

    def test_no_proc_above_25_percent(self):
        engine = _make_engine()
        _equip_titan_ring(engine)

        engine.player.hp = 26
        engine._check_titan_blood_proc()

        assert not _has_titan_form(engine), "Should not activate above 25%"

    def test_no_proc_without_ring(self):
        engine = _make_engine()
        # No ring equipped
        engine.player.hp = 10
        engine._check_titan_blood_proc()

        assert not _has_titan_form(engine), "Should not activate without ring"

    def test_no_double_proc_same_floor(self):
        engine = _make_engine()
        _equip_titan_ring(engine)

        # First proc
        engine.player.hp = 20
        engine._check_titan_blood_proc()
        assert _has_titan_form(engine)

        # Remove the effect manually
        engine.player.status_effects = [
            e for e in engine.player.status_effects
            if getattr(e, 'id', '') != 'titan_form'
        ]

        # Heal back up and drop again
        engine.player.hp = 100
        engine._titan_blood_was_above_25 = True
        engine.player.hp = 10
        engine._check_titan_blood_proc()

        assert not _has_titan_form(engine), "Should not proc twice per floor"

    def test_must_cross_threshold_not_start_below(self):
        """If player starts the floor below 25%, Titan Form shouldn't proc."""
        engine = _make_engine()
        _equip_titan_ring(engine)
        engine._titan_blood_was_above_25 = False  # never was above 25%

        engine.player.hp = 10
        engine._check_titan_blood_proc()

        assert not _has_titan_form(engine), "Must cross from above 25% to below"


class TestTitanFormExpiry:
    """Titan Form expires after 20 turns and cleans up properly."""

    def test_expires_after_20_ticks(self):
        engine = _make_engine()
        _equip_titan_ring(engine)
        engine.player.hp = 20
        engine._check_titan_blood_proc()

        eff = _get_titan_form(engine)
        assert eff is not None
        assert eff.duration == 20

        # Tick 20 times
        for i in range(20):
            tick_all_effects(engine.player, engine)
            if i < 19:
                assert _has_titan_form(engine), f"Should still be active at tick {i+1}"

        assert not _has_titan_form(engine), "Should have expired after 20 ticks"

    def test_damage_mult_removed_on_expiry(self):
        engine = _make_engine()
        _equip_titan_ring(engine)
        engine.player.hp = 20
        engine._check_titan_blood_proc()

        assert 1.5 in engine.player_stats.outgoing_damage_mults

        # Expire it
        for _ in range(20):
            tick_all_effects(engine.player, engine)

        assert 1.5 not in engine.player_stats.outgoing_damage_mults, \
            "Damage multiplier should be removed on expiry"

    def test_temp_hp_cleared_on_expiry(self):
        engine = _make_engine()
        _equip_titan_ring(engine)
        engine.player.hp = 20
        engine._check_titan_blood_proc()

        assert engine.player.temp_hp > 0, "Should have temp HP during Titan Form"

        for _ in range(20):
            tick_all_effects(engine.player, engine)

        assert engine.player.temp_hp == 0, "Temp HP should be cleared on expiry"

    def test_resets_on_new_floor(self):
        engine = _make_engine()
        _equip_titan_ring(engine)

        # Use up the proc
        engine.player.hp = 20
        engine._check_titan_blood_proc()
        assert not engine._titan_blood_available

        # Simulate floor reset
        engine._titan_blood_available = True
        engine._titan_blood_was_above_25 = True

        # Remove old effect
        engine.player.status_effects = [
            e for e in engine.player.status_effects
            if getattr(e, 'id', '') != 'titan_form'
        ]

        # Should be able to proc again
        engine.player.hp = 20
        engine._check_titan_blood_proc()
        assert _has_titan_form(engine), "Should be able to proc again on new floor"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
