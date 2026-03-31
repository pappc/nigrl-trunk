"""Tests for hangover stat cleanup when cleansed by external effects.

Ensures that removing hangover through any mechanism (Flagellant's Mask,
White Gonster, Soul Cleanse, remove_debuffs) properly restores all-stat
penalties and doesn't cause permanent stat drift.
"""

import random
import pytest
from engine import GameEngine
from effects import apply_effect, HangoverEffect
from items import get_item_def, create_item_entity


def _make_engine(seed="HANGTEST1"):
    """Create a test engine."""
    e = GameEngine(seed=seed)
    e.sdl_overlay = None
    return e


def _get_all_stat_bonuses(ps):
    """Return sum of temporary stat bonuses for the 6 hangover stats."""
    total = 0
    for stat in HangoverEffect.STATS:
        total += ps.temporary_stat_bonuses.get(stat, 0)
    return total


def _get_stat_snapshot(ps):
    """Return dict of temporary bonuses for all hangover stats."""
    return {stat: ps.temporary_stat_bonuses.get(stat, 0) for stat in HangoverEffect.STATS}


class TestHangoverBasicExpire:
    """Hangover applies and removes stats correctly through normal expiry."""

    def test_hangover_apply_gives_penalty(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)
        apply_effect(engine.player, engine, "hangover", stacks=2)
        after = _get_stat_snapshot(engine.player_stats)
        for stat in HangoverEffect.STATS:
            assert after[stat] == before[stat] - 2, f"{stat} should have -2 penalty"

    def test_hangover_expire_restores_stats(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)
        apply_effect(engine.player, engine, "hangover", stacks=3)
        # Manually expire
        eff = next(e for e in engine.player.status_effects if e.id == "hangover")
        engine.player.status_effects.remove(eff)
        eff.expire(engine.player, engine)
        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Stats should be fully restored after expire"

    def test_hangover_stacking_then_expire(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)
        apply_effect(engine.player, engine, "hangover", stacks=1)
        apply_effect(engine.player, engine, "hangover", stacks=1)  # reapply stacks to 2
        eff = next(e for e in engine.player.status_effects if e.id == "hangover")
        assert eff.stacks == 2
        engine.player.status_effects.remove(eff)
        eff.expire(engine.player, engine)
        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Stats should be fully restored after stacked hangover expire"


class TestFlagellantMaskCleanse:
    """Flagellant's Mask debuff purge calls expire() and restores stats."""

    def test_flagellant_cleanse_restores_hangover_stats(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        # Apply hangover
        apply_effect(engine.player, engine, "hangover", stacks=3)
        mid = _get_stat_snapshot(engine.player_stats)
        for stat in HangoverEffect.STATS:
            assert mid[stat] == before[stat] - 3

        # Simulate Flagellant's Mask purge (same code path as engine.py)
        debuffs = [e for e in engine.player.status_effects if e.category == "debuff"]
        hangover = next(e for e in debuffs if e.id == "hangover")
        engine.player.status_effects = [e for e in engine.player.status_effects if e is not hangover]
        hangover.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Flagellant cleanse should fully restore hangover stats"

    def test_flagellant_no_double_bonus_on_cleanse(self):
        """Ensure cleansing hangover doesn't grant bonus stats (positive drift)."""
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        apply_effect(engine.player, engine, "hangover", stacks=1)
        # Cleanse
        eff = next(e for e in engine.player.status_effects if e.id == "hangover")
        engine.player.status_effects = [e for e in engine.player.status_effects if e is not eff]
        eff.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Should not have positive stat drift after cleanse"

    def test_flagellant_cleanse_stacked_hangover(self):
        """Stacked hangover cleansed = full stack penalty reversed."""
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        apply_effect(engine.player, engine, "hangover", stacks=1)
        apply_effect(engine.player, engine, "hangover", stacks=1)
        apply_effect(engine.player, engine, "hangover", stacks=1)  # stacks=3

        eff = next(e for e in engine.player.status_effects if e.id == "hangover")
        assert eff.stacks == 3
        engine.player.status_effects = [e for e in engine.player.status_effects if e is not eff]
        eff.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Stacked hangover cleanse should restore all stats"


class TestWhiteGonsterCleanse:
    """White Gonster purge calls expire() and restores stats."""

    def test_white_gonster_purge_restores_hangover(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        apply_effect(engine.player, engine, "hangover", stacks=2)

        # Simulate _white_gonster_purge selecting the hangover
        from effects import _white_gonster_purge
        # Force RNG to pick hangover (only debuff present)
        _white_gonster_purge(engine.player, engine)

        # Hangover should be gone
        assert not any(e.id == "hangover" for e in engine.player.status_effects)
        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "White Gonster purge should restore hangover stats"


class TestSoulCleanse:
    """Soul Cleanse (abilities.py) calls expire() and restores stats."""

    def test_soul_cleanse_restores_hangover(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        apply_effect(engine.player, engine, "hangover", stacks=4)

        # Simulate soul cleanse logic
        debuffs = [e for e in engine.player.status_effects if e.category == "debuff"]
        target = next(e for e in debuffs if e.id == "hangover")
        engine.player.status_effects.remove(target)
        target.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Soul Cleanse should restore hangover stats"


class TestRemoveDebuffsItem:
    """Item use_effect remove_debuffs calls expire() on all debuffs."""

    def test_remove_debuffs_restores_hangover(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        apply_effect(engine.player, engine, "hangover", stacks=5)

        # Simulate remove_debuffs logic from item_effects.py
        removed = [e for e in engine.player.status_effects if getattr(e, 'category', 'debuff') == 'debuff']
        engine.player.status_effects = [e for e in engine.player.status_effects if getattr(e, 'category', 'debuff') != 'debuff']
        for eff_obj in removed:
            eff_obj.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "remove_debuffs should restore hangover stats"


class TestNoStatDrift:
    """Repeated apply/cleanse cycles should not cause cumulative stat drift."""

    def test_multiple_apply_cleanse_cycles(self):
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        for _ in range(10):
            apply_effect(engine.player, engine, "hangover", stacks=random.randint(1, 5))
            eff = next(e for e in engine.player.status_effects if e.id == "hangover")
            engine.player.status_effects = [e for e in engine.player.status_effects if e is not eff]
            eff.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, f"10 apply/cleanse cycles should leave stats unchanged, got drift: {after}"

    def test_stack_then_cleanse_cycle(self):
        """Stack hangover multiple times, then cleanse. Repeat."""
        engine = _make_engine()
        before = _get_stat_snapshot(engine.player_stats)

        for _ in range(5):
            # Stack 3 times
            apply_effect(engine.player, engine, "hangover", stacks=1)
            apply_effect(engine.player, engine, "hangover", stacks=1)
            apply_effect(engine.player, engine, "hangover", stacks=1)
            # Cleanse
            eff = next(e for e in engine.player.status_effects if e.id == "hangover")
            engine.player.status_effects = [e for e in engine.player.status_effects if e is not eff]
            eff.expire(engine.player, engine)

        after = _get_stat_snapshot(engine.player_stats)
        assert before == after, "Repeated stack+cleanse should not drift stats"
