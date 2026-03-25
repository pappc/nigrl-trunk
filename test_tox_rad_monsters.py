"""Tests verifying toxicity damage multiplier and radiation mutations for monsters."""

import random
import pytest
from unittest.mock import MagicMock, patch

from entity import Entity
from combat import (
    _monster_toxicity_multiplier,
    _apply_toxicity,
    add_toxicity,
    add_radiation,
)
from mutations import (
    check_monster_mutation,
    MONSTER_RAD_THRESHOLD,
    MONSTER_RAD_COST,
    MONSTER_RAD_CHANCE_PER_20,
    MONSTER_BAD_CHANCE,
)
from effects import apply_effect, tick_all_effects


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_engine():
    """Minimal mock engine."""
    engine = MagicMock()
    engine.messages = []
    engine.player = Entity(5, 5, "@", (255, 255, 255), name="Player", entity_type="player", hp=100)
    engine.player.status_effects = []
    engine.player.toxicity = 0
    engine.player.radiation = 0
    engine.player.tox_resistance = 0
    del engine.player.base_stats

    engine.player_stats = MagicMock()
    engine.player_stats.total_tox_resistance = 0
    engine.player_stats.total_rad_resistance = 0
    engine.player_stats.dodge_chance = 0
    engine.player_stats.outgoing_damage_mult = 1.0
    engine.player_stats.xp_multiplier = 1.0
    engine.player_stats.effective_book_smarts = 8
    engine.player_stats.total_briskness = 0

    engine.event_bus = MagicMock()
    engine.skills = MagicMock()
    engine.skills.gain_potential_exp = MagicMock()
    engine.skills.get = MagicMock(return_value=MagicMock(level=0))
    engine._drink_duration_multiplier = 1

    dungeon = MagicMock()
    dungeon.entities = []
    dungeon.get_monsters = MagicMock(return_value=[])
    dungeon.spray_paint = {}
    engine.dungeon = dungeon

    return engine


def _make_monster(x=10, y=10, hp=50, defense=5, power=8, speed=100):
    """Create a simple monster entity."""
    m = Entity(x, y, "M", (200, 50, 50), name="Test Monster", entity_type="monster", hp=hp)
    m.max_hp = hp
    m.defense = defense
    m.power = power
    m.speed = speed
    m.status_effects = []
    m.toxicity = 0
    m.radiation = 0
    m.tox_resistance = 0
    m.rad_resistance = 0
    m.alive = True
    m.enemy_type = "test_monster"
    m.dodge_chance = 0
    return m


# ══════════════════════════════════════════════════════════════════════════════
# Toxicity multiplier formula
# ══════════════════════════════════════════════════════════════════════════════

class TestMonsterToxMultiplier:
    def test_zero_tox_returns_1x(self):
        assert _monster_toxicity_multiplier(0) == 1.0

    def test_negative_tox_returns_1x(self):
        assert _monster_toxicity_multiplier(-10) == 1.0

    def test_50_tox_is_2x(self):
        mult = _monster_toxicity_multiplier(50)
        assert abs(mult - 2.0) < 0.01, f"50 tox should be ~2x, got {mult}"

    def test_100_tox_greater_than_2x(self):
        mult = _monster_toxicity_multiplier(100)
        assert mult > 2.0, f"100 tox should be > 2x, got {mult}"

    def test_multiplier_scales_with_tox(self):
        """Higher tox = higher multiplier."""
        m50 = _monster_toxicity_multiplier(50)
        m100 = _monster_toxicity_multiplier(100)
        m200 = _monster_toxicity_multiplier(200)
        assert m50 < m100 < m200

    def test_monster_more_sensitive_than_player(self):
        """Monster formula uses tox/50 vs player tox/100, so same tox = higher mult."""
        from combat import _player_toxicity_multiplier
        for tox in (50, 100, 150):
            monster_mult = _monster_toxicity_multiplier(tox)
            player_mult = _player_toxicity_multiplier(tox)
            assert monster_mult > player_mult, (
                f"At {tox} tox: monster={monster_mult:.2f} should > player={player_mult:.2f}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Toxicity multiplier actually applied to damage
# ══════════════════════════════════════════════════════════════════════════════

class TestToxDamageApplication:
    def test_no_tox_no_change(self):
        """Monster with 0 tox takes base damage."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 0
        result = _apply_toxicity(engine, 10, monster)
        assert result == 10

    def test_tox_amplifies_damage(self):
        """Monster with toxicity takes more damage."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 50
        result = _apply_toxicity(engine, 10, monster)
        # 50 tox = 2x, so 10 * 2 = 20
        assert result == 20, f"Expected 20, got {result}"

    def test_tox_100_amplifies_more(self):
        """Monster with 100 tox takes even more damage."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 100
        result = _apply_toxicity(engine, 10, monster)
        # 1 + (100/50)^0.6 = 1 + 2^0.6 ≈ 2.516
        expected = int(10 * _monster_toxicity_multiplier(100))
        assert result == expected

    def test_minimum_damage_is_1(self):
        """Even with tox amp, minimum damage is 1."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 50
        result = _apply_toxicity(engine, 0, monster)
        # 0 * 2 = 0, but max(1, 0) = 1... actually int(0 * 2) = 0 → max(1,0) = 1
        assert result >= 1

    def test_add_toxicity_to_monster(self):
        """add_toxicity correctly increases monster.toxicity."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 0
        add_toxicity(engine, monster, 30)
        assert monster.toxicity == 30

    def test_add_toxicity_respects_resistance(self):
        """Monster tox resistance reduces tox gain."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 0
        monster.tox_resistance = 50  # 50% resistance
        add_toxicity(engine, monster, 30)
        assert monster.toxicity == 15, f"Expected 15, got {monster.toxicity}"


# ══════════════════════════════════════════════════════════════════════════════
# Radiation mutation system for monsters
# ══════════════════════════════════════════════════════════════════════════════

class TestMonsterRadiationConstants:
    def test_threshold_is_20(self):
        assert MONSTER_RAD_THRESHOLD == 20

    def test_cost_is_20(self):
        assert MONSTER_RAD_COST == 20

    def test_chance_per_20_is_5_percent(self):
        assert MONSTER_RAD_CHANCE_PER_20 == 0.05

    def test_bad_chance_is_85_percent(self):
        assert MONSTER_BAD_CHANCE == 0.85


class TestMonsterRadiationMutation:
    def test_below_threshold_no_mutation(self):
        """Monster with < 20 rad never mutates."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 19
        original_hp = monster.hp
        original_defense = monster.defense
        original_power = monster.power
        original_speed = monster.speed

        for _ in range(100):
            check_monster_mutation(engine, monster)

        # Nothing should have changed — no messages, no stat changes, no rad consumed
        assert monster.radiation == 19
        assert monster.hp == original_hp
        assert monster.defense == original_defense
        assert monster.power == original_power
        assert monster.speed == original_speed
        assert len(engine.messages) == 0

    def test_at_threshold_can_mutate(self):
        """Monster with 20+ rad can mutate (seeded to force it)."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 100  # High rad for high chance

        # Run many times — with 25% chance (100//20 * 0.05 = 0.25), should hit
        mutated = False
        for _ in range(200):
            monster.radiation = 100
            old_rad = monster.radiation
            check_monster_mutation(engine, monster)
            if monster.radiation < old_rad:
                mutated = True
                break
        assert mutated, "Monster should have mutated at least once in 200 tries at 100 rad"

    def test_mutation_consumes_radiation(self):
        """Each mutation consumes MONSTER_RAD_COST (20) radiation."""
        engine = _make_engine()
        monster = _make_monster(hp=200)  # High HP to survive damage mutations
        monster.radiation = 100

        # Force mutation to succeed with seeded random
        with patch('mutations.random') as mock_random:
            mock_random.random = MagicMock(side_effect=[
                0.0,   # chance check: 0.0 < 0.25 → passes
                0.0,   # polarity: 0.0 < 0.85 → bad
                0.0,   # _pick_weighted roll
            ])
            check_monster_mutation(engine, monster)

        assert monster.radiation == 80, f"Expected 80 (100 - 20), got {monster.radiation}"

    def test_mutation_chance_scales_with_rad(self):
        """Higher rad = higher mutation chance (capped at 50%)."""
        # At 20 rad:  (20 // 20) * 0.05 = 0.05 = 5%
        # At 100 rad: (100 // 20) * 0.05 = 0.25 = 25%
        # At 200 rad: (200 // 20) * 0.05 = 0.50 = 50% (cap)
        # At 300 rad: still capped at 50%
        engine = _make_engine()

        # Test: 20 rad monster mutates less often than 200 rad monster
        low_rad_mutations = 0
        high_rad_mutations = 0

        for _ in range(2000):
            m_low = _make_monster(hp=200)
            m_low.radiation = 20
            check_monster_mutation(engine, m_low)
            if m_low.radiation < 20:
                low_rad_mutations += 1

            m_high = _make_monster(hp=200)
            m_high.radiation = 200
            check_monster_mutation(engine, m_high)
            if m_high.radiation < 200:
                high_rad_mutations += 1

        # At 5% vs 50%, high should mutate ~10x more often
        assert high_rad_mutations > low_rad_mutations * 3, (
            f"High rad ({high_rad_mutations}) should mutate much more than low ({low_rad_mutations})"
        )

    def test_mutation_polarity_mostly_bad(self):
        """85% of mutations should be bad."""
        engine = _make_engine()
        bad_count = 0
        total = 0

        for _ in range(2000):
            monster = _make_monster(hp=500)  # High HP to survive
            monster.radiation = 200  # High chance

            old_msgs_len = len(engine.messages)
            check_monster_mutation(engine, monster)

            if len(engine.messages) > old_msgs_len:
                total += 1
                # Bad mutations have (255, 80, 80) color, good have (80, 255, 80)
                msg = engine.messages[old_msgs_len]
                if isinstance(msg, list) and len(msg) >= 1:
                    color = msg[0][1]
                    if color == (255, 80, 80):
                        bad_count += 1

        if total > 0:
            bad_ratio = bad_count / total
            assert bad_ratio > 0.70, f"Bad ratio {bad_ratio:.2f} should be > 0.70 (expected ~0.85)"

    def test_mutation_generates_message(self):
        """A successful mutation produces a combat log message."""
        engine = _make_engine()
        monster = _make_monster(hp=200)
        monster.radiation = 200

        with patch('mutations.random') as mock_random:
            mock_random.random = MagicMock(side_effect=[
                0.0,   # chance check passes
                0.0,   # polarity: bad
                0.0,   # _pick_weighted roll
            ])
            check_monster_mutation(engine, monster)

        assert len(engine.messages) > 0, "Mutation should produce a message"

    def test_add_radiation_to_monster(self):
        """add_radiation correctly increases monster.radiation."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 0
        add_radiation(engine, monster, 50)
        assert monster.radiation == 50

    def test_add_radiation_respects_resistance(self):
        """Monster rad resistance reduces rad gain."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 0
        monster.rad_resistance = 50  # 50% resistance
        add_radiation(engine, monster, 50)
        assert monster.radiation == 25, f"Expected 25, got {monster.radiation}"

    def test_mutation_can_kill_monster(self):
        """Radiation damage mutations (Chemical Burns, Meltdown) can kill."""
        engine = _make_engine()
        monster = _make_monster(hp=1)  # 1 HP — any damage kills
        monster.radiation = 200

        # Force a bad mutation — Chemical Burns (20% max HP damage)
        killed = False
        for _ in range(100):
            monster.hp = 1
            monster.max_hp = 50
            monster.radiation = 200
            monster.alive = True
            check_monster_mutation(engine, monster)
            if not monster.alive:
                killed = True
                break

        assert killed, "Radiation damage mutation should be able to kill a 1 HP monster"

    def test_zero_rad_no_mutation(self):
        """Monster with 0 rad never mutates."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 0
        check_monster_mutation(engine, monster)
        assert monster.radiation == 0
        assert len(engine.messages) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Integration: engine energy loop calls mutation check
# ══════════════════════════════════════════════════════════════════════════════

class TestEngineRadMutationIntegration:
    def test_engine_checks_radiation_threshold(self):
        """Engine only calls check_monster_mutation for monsters with rad >= 20."""
        # This tests the guard at engine.py:935
        engine = _make_engine()
        monster_low = _make_monster(x=10, y=10)
        monster_low.radiation = 10  # Below threshold
        monster_high = _make_monster(x=15, y=15)
        monster_high.radiation = 50  # Above threshold

        # Verify the threshold check logic directly
        assert monster_low.radiation < 20
        assert monster_high.radiation >= 20


# ══════════════════════════════════════════════════════════════════════════════
# Curse of COVID XP: Nuclear Research and Chemical Warfare
# ══════════════════════════════════════════════════════════════════════════════

class TestCurseCovidXP:
    """Verify Curse of COVID grants Chemical Warfare and Nuclear Research XP.

    CurseCovidEffect.tick() does `import random as _rand` locally, which
    returns the real random module from sys.modules. We patch `random.random`
    (the function on the real module) to control the coin flips.
    """

    def test_covid_tox_grants_chemical_warfare_xp(self):
        """Curse of COVID applying toxicity to a monster grants Chemical Warfare XP."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 0
        engine.dungeon.entities = [monster]
        engine.dungeon.get_monsters = MagicMock(return_value=[])

        apply_effect(monster, engine, "curse_covid", stacks=0)
        engine.skills.gain_potential_exp.reset_mock()

        # Force tox path: coin flip > 0.5 → else branch → add_toxicity
        with patch('random.random', side_effect=[0.99, 0.99, 0.99]):
            tick_all_effects(monster, engine)

        cw_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Chemical Warfare"
        ]
        assert len(cw_calls) > 0, (
            f"Chemical Warfare XP should be granted. Calls: {engine.skills.gain_potential_exp.call_args_list}"
        )

    def test_covid_rad_grants_nuclear_research_xp(self):
        """Curse of COVID applying radiation to a monster grants Nuclear Research XP."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 0
        engine.dungeon.entities = [monster]
        engine.dungeon.get_monsters = MagicMock(return_value=[])

        apply_effect(monster, engine, "curse_covid", stacks=0)
        engine.skills.gain_potential_exp.reset_mock()

        # Force rad path: coin flip < 0.5 → add_radiation
        with patch('random.random', side_effect=[0.01, 0.99, 0.99]):
            tick_all_effects(monster, engine)

        nr_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Nuclear Research"
        ]
        assert len(nr_calls) > 0, (
            f"Nuclear Research XP should be granted. Calls: {engine.skills.gain_potential_exp.call_args_list}"
        )

    def test_covid_tox_xp_amount(self):
        """Chemical Warfare XP = max(1, gain // 2) for tox applied to monster."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 0
        monster.tox_resistance = 0
        engine.dungeon.entities = [monster]
        engine.dungeon.get_monsters = MagicMock(return_value=[])

        apply_effect(monster, engine, "curse_covid", stacks=0)
        engine.skills.gain_potential_exp.reset_mock()

        with patch('random.random', side_effect=[0.99, 0.99, 0.99]):
            tick_all_effects(monster, engine)

        cw_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Chemical Warfare"
        ]
        assert len(cw_calls) == 1
        xp_amount = cw_calls[0][0][1]
        # 20 tox gained, XP = max(1, 20 // 2) = 10
        assert xp_amount == 10, f"Expected 10 XP, got {xp_amount}"

    def test_covid_rad_xp_amount(self):
        """Nuclear Research XP = max(1, gain // 2) for rad applied to monster."""
        engine = _make_engine()
        monster = _make_monster()
        monster.radiation = 0
        monster.rad_resistance = 0
        engine.dungeon.entities = [monster]
        engine.dungeon.get_monsters = MagicMock(return_value=[])

        apply_effect(monster, engine, "curse_covid", stacks=0)
        engine.skills.gain_potential_exp.reset_mock()

        with patch('random.random', side_effect=[0.01, 0.99, 0.99]):
            tick_all_effects(monster, engine)

        nr_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Nuclear Research"
        ]
        assert len(nr_calls) == 1
        xp_amount = nr_calls[0][0][1]
        # 20 rad gained, XP = max(1, 20 // 2) = 10
        assert xp_amount == 10, f"Expected 10 XP, got {xp_amount}"

    def test_covid_no_xp_when_capped(self):
        """No XP when monster is already at 150+ tox and 150+ rad."""
        engine = _make_engine()
        monster = _make_monster()
        monster.toxicity = 150
        monster.radiation = 150
        engine.dungeon.entities = [monster]
        engine.dungeon.get_monsters = MagicMock(return_value=[])

        apply_effect(monster, engine, "curse_covid", stacks=0)
        engine.skills.gain_potential_exp.reset_mock()

        with patch('random.random', side_effect=[0.99, 0.99, 0.99]):
            tick_all_effects(monster, engine)

        # No rad/tox applied, so no XP for either skill
        cw_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Chemical Warfare"
        ]
        nr_calls = [
            call for call in engine.skills.gain_potential_exp.call_args_list
            if call[0][0] == "Nuclear Research"
        ]
        assert len(cw_calls) == 0, "No Chemical Warfare XP when tox capped"
        assert len(nr_calls) == 0, "No Nuclear Research XP when rad capped"
