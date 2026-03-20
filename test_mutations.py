"""Tests for the radiation mutation system."""

import random
import pytest
import mutations
from skills import SKILL_NAMES, MAX_LEVEL


# --- Minimal stubs for testing ---

class FakePlayer:
    def __init__(self):
        self.radiation = 0
        self.alive = True
        self.status_effects = []


class FakeStats:
    def __init__(self):
        self.constitution = 10
        self.strength = 10
        self.street_smarts = 10
        self.book_smarts = 10
        self.tolerance = 10
        self.swagger = 5
        self._base = {
            "constitution": 10, "strength": 10, "street_smarts": 10,
            "book_smarts": 10, "tolerance": 10, "swagger": 5,
        }
        self.tox_resistance = 0
        self.rad_resistance = 0
        self.briskness = 0
        self.effective_book_smarts = 10
        self.permanent_dr = 0
        self.good_mutation_base_bonus = 0.0
        self.good_mutation_multiplier = 0.0

    def modify_base_stat(self, stat, amount):
        current = getattr(self, stat)
        new_val = max(1, current + amount)
        setattr(self, stat, new_val)
        self._base[stat] = new_val


class FakeSkill:
    def __init__(self, name, level=0):
        self.name = name
        self.level = level
        self.real_exp = 0.0
        self.potential_exp = 0.0

    def set_level(self, level):
        self.level = max(0, min(MAX_LEVEL, level))


class FakeSkills:
    def __init__(self):
        self.skills = {name: FakeSkill(name) for name in SKILL_NAMES}
        self.skill_points = 500.0

    def get(self, name):
        return self.skills[name]

    def set_skill_level(self, name, level):
        self.skills[name].set_level(level)

    def gain_potential_exp(self, skill_name, amount, book_smarts=0, briskness=0):
        self.skills[skill_name].potential_exp += amount


class FakeEngine:
    def __init__(self):
        self.player = FakePlayer()
        self.player_stats = FakeStats()
        self.skills = FakeSkills()
        self.messages = []
        self.mutation_log = []
        self.neck = None
        self.feet = None
        self.hat = None


class FakeItem:
    def __init__(self, name="Test Item"):
        self.name = name


# --- Helper to force a mutation ---

def force_mutation(engine, tier="weak", polarity="bad", table_index=0):
    """Directly apply a specific mutation entry for testing."""
    table = mutations.MUTATION_TABLES[(tier, polarity)]
    desc, apply_fn = table[table_index]
    suffix = apply_fn(engine) or ""
    return desc, suffix


# --- Tests ---

class TestCheckMutationThresholds:
    def test_no_mutation_below_75_rad(self):
        engine = FakeEngine()
        engine.player.radiation = 74
        random.seed(0)
        mutations.check_mutation(engine)
        assert len(engine.mutation_log) == 0

    def test_mutation_possible_at_75_rad(self):
        engine = FakeEngine()
        engine.player.radiation = 75
        # Force the random checks to succeed
        mutated = False
        for seed in range(10000):
            engine.player.radiation = 75
            engine.mutation_log.clear()
            engine.messages.clear()
            random.seed(seed)
            mutations.check_mutation(engine)
            if engine.mutation_log:
                mutated = True
                break
        assert mutated, "Should be possible to mutate at 75 rad given enough tries"

    def test_rad_consumed_on_mutation(self):
        engine = FakeEngine()
        engine.player.radiation = 300
        for seed in range(10000):
            engine.player.radiation = 300
            engine.mutation_log.clear()
            engine.messages.clear()
            random.seed(seed)
            mutations.check_mutation(engine)
            if engine.mutation_log:
                # Rad should have been consumed
                assert engine.player.radiation < 300
                break

    def test_higher_rad_higher_chance(self):
        """Higher rad should produce more mutations over many tries."""
        low_count = 0
        high_count = 0
        for seed in range(5000):
            e1 = FakeEngine()
            e1.player.radiation = 75
            random.seed(seed)
            mutations.check_mutation(e1)
            if e1.mutation_log:
                low_count += 1

            e2 = FakeEngine()
            e2.player.radiation = 500
            random.seed(seed)
            mutations.check_mutation(e2)
            if e2.mutation_log:
                high_count += 1
        assert high_count > low_count


class TestWeakMutations:
    def test_all_stats_minus_1(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "bad", 0)
        assert engine.player_stats.constitution == 9
        assert engine.player_stats.strength == 9

    def test_all_stats_plus_1(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "good", 0)
        assert engine.player_stats.constitution == 11
        assert engine.player_stats.strength == 11

    def test_single_stat_minus_1(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "bad", 1)  # -1 constitution
        assert engine.player_stats.constitution == 9
        assert engine.player_stats.strength == 10  # unchanged

    def test_single_stat_plus_1(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "good", 1)  # +1 constitution
        assert engine.player_stats.constitution == 11

    def test_tox_resistance_minus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "bad", 7)  # -10% tox res
        assert engine.player_stats.tox_resistance == -10

    def test_tox_resistance_plus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "good", 7)  # +10% tox res
        assert engine.player_stats.tox_resistance == 10

    def test_rad_resistance_minus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "bad", 8)  # -10% rad res
        assert engine.player_stats.rad_resistance == -10

    def test_rad_resistance_plus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "good", 8)  # +10% rad res
        assert engine.player_stats.rad_resistance == 10

    def test_skill_points_minus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "bad", 9)  # -100 skill points
        assert engine.skills.skill_points == 400.0

    def test_skill_points_plus(self):
        engine = FakeEngine()
        force_mutation(engine, "weak", "good", 9)  # +100 skill points
        assert engine.skills.skill_points == 600.0


class TestStrongMutations:
    def test_single_stat_minus_3(self):
        engine = FakeEngine()
        force_mutation(engine, "strong", "bad", 1)  # -3 constitution
        assert engine.player_stats.constitution == 7

    def test_single_stat_plus_3(self):
        engine = FakeEngine()
        force_mutation(engine, "strong", "good", 1)  # +3 constitution
        assert engine.player_stats.constitution == 13

    def test_skill_level_minus_1(self):
        engine = FakeEngine()
        engine.skills.get("Smoking").level = 3
        force_mutation(engine, "strong", "bad", 7)  # -1 Smoking level
        assert engine.skills.get("Smoking").level == 2

    def test_skill_level_plus_1(self):
        engine = FakeEngine()
        engine.skills.get("Smoking").level = 3
        force_mutation(engine, "strong", "good", 7)  # +1 Smoking level
        assert engine.skills.get("Smoking").level == 4

    def test_briskness_plus(self):
        engine = FakeEngine()
        # +5% briskness is second-to-last in strong good
        table = mutations.MUTATION_TABLES[("strong", "good")]
        idx = len(table) - 2  # +5% briskness
        desc, apply_fn = table[idx]
        assert "briskness" in desc
        apply_fn(engine)
        assert engine.player_stats.briskness == 5

    def test_dr_plus_3(self):
        engine = FakeEngine()
        table = mutations.MUTATION_TABLES[("strong", "good")]
        idx = len(table) - 1  # +3 DR
        desc, apply_fn = table[idx]
        assert "DR" in desc
        apply_fn(engine)
        assert engine.player_stats.permanent_dr == 3


class TestHugeMutations:
    def test_lose_5_skills(self):
        engine = FakeEngine()
        for name in SKILL_NAMES[:7]:
            engine.skills.get(name).level = 3
        force_mutation(engine, "huge", "bad", 0)
        reduced = [name for name in SKILL_NAMES[:7] if engine.skills.get(name).level == 2]
        assert len(reduced) == 5

    def test_lose_5_skills_fewer_eligible(self):
        engine = FakeEngine()
        engine.skills.get("Smoking").level = 2
        engine.skills.get("Rolling").level = 1
        desc, suffix = force_mutation(engine, "huge", "bad", 0)
        # Only 2 eligible, both reduced by 1
        assert engine.skills.get("Smoking").level == 1
        assert engine.skills.get("Rolling").level == 0

    def test_all_stats_minus_2(self):
        engine = FakeEngine()
        force_mutation(engine, "huge", "bad", 1)
        assert engine.player_stats.constitution == 8
        assert engine.player_stats.strength == 8

    def test_single_stat_minus_5(self):
        engine = FakeEngine()
        force_mutation(engine, "huge", "bad", 2)  # -5 constitution
        assert engine.player_stats.constitution == 5

    def test_lose_neck_item(self):
        engine = FakeEngine()
        engine.neck = FakeItem("Gold Chain")
        table = mutations.MUTATION_TABLES[("huge", "bad")]
        idx = len(table) - 3  # lose neck
        desc, apply_fn = table[idx]
        suffix = apply_fn(engine)
        assert engine.neck is None
        assert "Gold Chain" in suffix

    def test_lose_empty_slot(self):
        engine = FakeEngine()
        engine.neck = None
        table = mutations.MUTATION_TABLES[("huge", "bad")]
        idx = len(table) - 3  # lose neck
        desc, apply_fn = table[idx]
        suffix = apply_fn(engine)
        assert "nothing happened" in suffix

    def test_lose_feet_item(self):
        engine = FakeEngine()
        engine.feet = FakeItem("Timbs")
        table = mutations.MUTATION_TABLES[("huge", "bad")]
        idx = len(table) - 2  # lose feet
        desc, apply_fn = table[idx]
        suffix = apply_fn(engine)
        assert engine.feet is None

    def test_lose_hat_item(self):
        engine = FakeEngine()
        engine.hat = FakeItem("Durag")
        table = mutations.MUTATION_TABLES[("huge", "bad")]
        idx = len(table) - 1  # lose hat
        desc, apply_fn = table[idx]
        suffix = apply_fn(engine)
        assert engine.hat is None

    def test_skill_plus_5_levels(self):
        engine = FakeEngine()
        engine.skills.get("Smoking").level = 2
        force_mutation(engine, "huge", "good", 0)  # +5 Smoking
        assert engine.skills.get("Smoking").level == 7

    def test_all_stats_plus_2(self):
        engine = FakeEngine()
        table = mutations.MUTATION_TABLES[("huge", "good")]
        idx = len(SKILL_NAMES)  # +2 to all stats entry
        desc, apply_fn = table[idx]
        apply_fn(engine)
        assert engine.player_stats.constitution == 12
        assert engine.player_stats.swagger == 7

    def test_dr_plus_5(self):
        engine = FakeEngine()
        table = mutations.MUTATION_TABLES[("huge", "good")]
        idx = len(table) - 1  # +5 DR
        desc, apply_fn = table[idx]
        apply_fn(engine)
        assert engine.player_stats.permanent_dr == 5


class TestEdgeCases:
    def test_stat_floors_at_1(self):
        engine = FakeEngine()
        engine.player_stats.constitution = 1
        engine.player_stats._base["constitution"] = 1
        mutations._apply_single_stat(engine, "constitution", -5)
        assert engine.player_stats.constitution == 1

    def test_skill_at_0_minus_1(self):
        engine = FakeEngine()
        assert engine.skills.get("Smoking").level == 0
        mutations._apply_skill_level(engine, "Smoking", -1)
        assert engine.skills.get("Smoking").level == 0

    def test_skill_at_max_plus_1(self):
        engine = FakeEngine()
        engine.skills.get("Smoking").level = MAX_LEVEL
        mutations._apply_skill_level(engine, "Smoking", 1)
        assert engine.skills.get("Smoking").level == MAX_LEVEL

    def test_skill_points_go_negative(self):
        engine = FakeEngine()
        engine.skills.skill_points = 50.0
        mutations._apply_skill_points(engine, -200)
        assert engine.skills.skill_points == -150.0

    def test_rad_drops_below_threshold(self):
        engine = FakeEngine()
        engine.player.radiation = 55
        # After weak mutation, rad drops to 5 (55-50)
        # Subsequent check_mutation should do nothing
        engine.player.radiation = 5
        mutations.check_mutation(engine)
        assert len(engine.mutation_log) == 0


class TestMutationTables:
    def test_weak_bad_count(self):
        assert len(mutations.MUTATION_TABLES[("weak", "bad")]) == 10

    def test_weak_good_count(self):
        assert len(mutations.MUTATION_TABLES[("weak", "good")]) == 10

    def test_strong_bad_count(self):
        expected = 8 + len(SKILL_NAMES)  # 8 + 17 = 25
        assert len(mutations.MUTATION_TABLES[("strong", "bad")]) == expected

    def test_strong_good_count(self):
        expected = 10 + len(SKILL_NAMES)  # 10 + 17 = 27
        assert len(mutations.MUTATION_TABLES[("strong", "good")]) == expected

    def test_huge_bad_count(self):
        assert len(mutations.MUTATION_TABLES[("huge", "bad")]) == 11

    def test_huge_good_count(self):
        expected = 9 + len(SKILL_NAMES)  # 9 + 17 = 26
        assert len(mutations.MUTATION_TABLES[("huge", "good")]) == expected


class TestMessageFormat:
    def test_mutation_message_is_colored(self):
        engine = FakeEngine()
        engine.player.radiation = 300
        for seed in range(10000):
            engine.player.radiation = 300
            engine.mutation_log.clear()
            engine.messages.clear()
            random.seed(seed)
            mutations.check_mutation(engine)
            if engine.mutation_log:
                msg = engine.messages[-1]
                assert isinstance(msg, list), "Message should be a colored segment list"
                text, color = msg[0]
                assert "You mutate!" in text
                assert color in (mutations._COLOR_GOOD, mutations._COLOR_BAD)
                break

    def test_mutation_log_entry(self):
        engine = FakeEngine()
        engine.player.radiation = 300
        for seed in range(10000):
            engine.player.radiation = 300
            engine.mutation_log.clear()
            engine.messages.clear()
            random.seed(seed)
            mutations.check_mutation(engine)
            if engine.mutation_log:
                entry = engine.mutation_log[0]
                assert "tier" in entry
                assert "polarity" in entry
                assert "description" in entry
                assert entry["tier"] in ("weak", "strong", "huge")
                assert entry["polarity"] in ("bad", "good")
                break
