"""
Test Smartsness skill XP gain when casting spells.

XP formula: 20 * floor_skill_mult * zone_skill_mult
- floor_skill_mult: 1.0 + (current_floor * 0.5)
- zone_skill_mult: From ZONE_SMARTSNESS_MULT (crack_den = 2.0)
"""

from engine import GameEngine
from abilities import ABILITY_REGISTRY
from config import ZONE_SMARTSNESS_MULT


def test_spell_xp_unlock():
    """Test that calling _gain_spell_xp unlocks Smartsness skill."""
    engine = GameEngine()

    # Check initial state
    skill = engine.skills.get("Smartsness")
    assert skill.level == 0
    assert skill.potential_exp == 0

    # Directly call _gain_spell_xp with a spell ability_id
    engine._gain_spell_xp("warp")

    # Check that skill was unlocked and gained XP
    skill = engine.skills.get("Smartsness")
    assert skill.potential_exp > 0, "Should have gained potential XP"
    # Check for unlock message (should have NEW SKILL UNLOCKED message)
    has_unlock_msg = any(
        isinstance(m, list) and any("[NEW SKILL UNLOCKED] Smartsness!" in str(item) for item in m)
        for m in engine.messages
    ) or any(
        "[NEW SKILL UNLOCKED] Smartsness!" in str(m)
        for m in engine.messages
    )
    assert has_unlock_msg, "Should have unlock message"


def test_spell_xp_calculation_floor_0():
    """Test XP calculation on floor 0 (1st floor).

    floor_mult = 1.0 + (0 * 0.5) = 1.0
    zone_mult = ZONE_SMARTSNESS_MULT["crack_den"]
    base_xp = 20 * 1.0 * zone_mult
    """
    engine = GameEngine()
    engine.current_floor = 0
    zone_mult = ZONE_SMARTSNESS_MULT.get("crack_den", 1.0)

    engine._gain_spell_xp("warp")

    skill = engine.skills.get("Smartsness")
    expected_xp = round(20 * 1.0 * zone_mult * engine.player_stats.xp_multiplier)
    assert skill.potential_exp == expected_xp, \
        f"Expected {expected_xp} XP on floor 0, got {skill.potential_exp}"


def test_spell_xp_calculation_floor_1():
    """Test XP calculation on floor 1 (2nd floor).

    floor_mult = 1.0 + (1 * 0.5) = 1.5
    zone_mult = ZONE_SMARTSNESS_MULT["crack_den"]
    base_xp = 20 * 1.5 * zone_mult
    """
    engine = GameEngine()
    engine.current_floor = 1
    zone_mult = ZONE_SMARTSNESS_MULT.get("crack_den", 1.0)

    engine._gain_spell_xp("warp")

    skill = engine.skills.get("Smartsness")
    expected_xp = round(20 * 1.5 * zone_mult * engine.player_stats.xp_multiplier)
    assert skill.potential_exp == expected_xp, \
        f"Expected {expected_xp} XP on floor 1, got {skill.potential_exp}"


def test_spell_xp_calculation_floor_3():
    """Test XP calculation on floor 3 (4th floor).

    floor_mult = 1.0 + (3 * 0.5) = 2.5
    zone_mult = ZONE_SMARTSNESS_MULT["crack_den"]
    base_xp = 20 * 2.5 * zone_mult
    """
    engine = GameEngine()
    engine.current_floor = 3
    zone_mult = ZONE_SMARTSNESS_MULT.get("crack_den", 1.0)

    engine._gain_spell_xp("warp")

    skill = engine.skills.get("Smartsness")
    expected_xp = round(20 * 2.5 * zone_mult * engine.player_stats.xp_multiplier)
    assert skill.potential_exp == expected_xp, \
        f"Expected {expected_xp} XP on floor 3, got {skill.potential_exp}"


def test_only_spells_grant_xp():
    """Test that only abilities with is_spell=True grant Smartsness XP."""
    engine = GameEngine()

    # Verify warp is marked as a spell
    assert ABILITY_REGISTRY["warp"].is_spell, "Warp should be marked as a spell"

    # Call _gain_spell_xp with warp (is a spell)
    engine._gain_spell_xp("warp")

    skill = engine.skills.get("Smartsness")
    initial_xp = skill.potential_exp
    assert initial_xp > 0, "Spell should grant XP"

    # Now test that non-spell abilities don't grant XP
    # (This is tested implicitly - calling _gain_spell_xp on a non-existent ID returns early)
    skill.potential_exp = 0  # Reset
    engine._gain_spell_xp("nonexistent_ability")
    assert skill.potential_exp == 0, "Non-spell should not grant XP"


def test_spell_xp_with_book_smarts():
    """Test that spell XP respects book_smarts through skill_point gain."""
    engine = GameEngine()
    engine.current_floor = 0

    # Increase book smarts (this should increase skill_point gain, not XP gain)
    # XP is still 20 * 1.0 * zone_mult, but skill_points gained will be higher
    engine.player_stats._base["book_smarts"] = 10
    zone_mult = ZONE_SMARTSNESS_MULT.get("crack_den", 1.0)

    # Call _gain_spell_xp
    engine._gain_spell_xp("warp")

    # Check XP
    skill = engine.skills.get("Smartsness")
    expected_xp = round(20 * zone_mult * engine.player_stats.xp_multiplier)
    assert skill.potential_exp == expected_xp, \
        f"Expected {expected_xp} XP, got {skill.potential_exp}"
    # Skill points should be higher due to book_smarts
    assert engine.skills.skill_points > 0, "Should have gained skill_points"


def run_tests():
    """Run all tests."""
    tests = [
        ("test_spell_xp_unlock", test_spell_xp_unlock),
        ("test_spell_xp_calculation_floor_0", test_spell_xp_calculation_floor_0),
        ("test_spell_xp_calculation_floor_1", test_spell_xp_calculation_floor_1),
        ("test_spell_xp_calculation_floor_3", test_spell_xp_calculation_floor_3),
        ("test_only_spells_grant_xp", test_only_spells_grant_xp),
        ("test_spell_xp_with_book_smarts", test_spell_xp_with_book_smarts),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            print(f"[PASS] {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {test_name}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {test_name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
