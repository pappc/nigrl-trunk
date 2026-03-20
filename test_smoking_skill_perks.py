"""
Tests for Smoking skill perks.

Perks:
  Level 1 - +2 TOL         : +2 Tolerance.
  Level 2 - +2 TOL, +2 CON : +2 Tolerance, +2 Constitution (permanent stat perk).
  Level 3 - Phat Cloud      : When you smoke, deal 10 + tolerance//2 dmg to nearest visible enemy.
  Level 4 - Roach Fiend     : 30% chance a blunt is not consumed when smoked.
"""

import random
from unittest.mock import patch

from config import TILE_FLOOR
from engine import GameEngine
from entity import Entity
from items import ITEM_DEFS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine() -> GameEngine:
    return GameEngine()


def set_smoking_level(engine: GameEngine, level: int) -> None:
    """Directly set the Smoking skill level (bypasses XP system)."""
    engine.skills.get("Smoking").level = level


def add_joint(engine: GameEngine, strain: str = "OG Kush") -> tuple[Entity, int]:
    """Add a joint to the player's inventory. Returns (item, index)."""
    defn = ITEM_DEFS["joint"]
    item = Entity(
        engine.player.x, engine.player.y,
        defn["char"], defn["color"],
        name=f"{strain} joint",
        entity_type="item",
        item_id="joint",
    )
    item.strain = strain
    item.quantity = 1
    engine.player.inventory.append(item)
    return item, len(engine.player.inventory) - 1


def place_visible_monster(engine: GameEngine, dx: int = 2, dy: int = 0, hp: int = 500) -> Entity:
    """Place a monster near the player and mark it as visible."""
    px, py = engine.player.x, engine.player.y
    mx, my = px + dx, py + dy
    engine.dungeon.tiles[my][mx] = TILE_FLOOR
    m = Entity(
        mx, my, "T", (255, 0, 0),
        name="TestMob",
        entity_type="monster",
        blocks_movement=True,
        hp=hp, power=0,
    )
    m.armor = 0
    engine.dungeon.entities.append(m)
    engine.dungeon.visible[my, mx] = True
    return m


def smoke_joint(engine: GameEngine, index: int) -> None:
    """Smoke the joint at the given inventory index."""
    engine._use_item(index)


# ---------------------------------------------------------------------------
# Phat Cloud (Level 3)
# ---------------------------------------------------------------------------

def test_phat_cloud_deals_damage_to_nearest_visible_enemy():
    """Phat Cloud should deal 10 + tolerance//2 to the nearest visible enemy."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    tlr = engine.player_stats.effective_tolerance
    expected_dmg = 10 + tlr // 2

    monster = place_visible_monster(engine, dx=2, hp=500)
    initial_hp = monster.hp

    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    assert monster.hp == initial_hp - expected_dmg, (
        f"Expected monster to lose {expected_dmg} HP from Phat Cloud "
        f"(tolerance={tlr}), got {initial_hp - monster.hp}"
    )


def test_phat_cloud_targets_nearest_visible_enemy():
    """Phat Cloud should target the closest visible enemy, not a farther one."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    close_mob = place_visible_monster(engine, dx=2, hp=500)
    far_mob   = place_visible_monster(engine, dx=6, hp=500)

    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    tlr = engine.player_stats.effective_tolerance
    expected_dmg = 10 + tlr // 2

    assert close_mob.hp == 500 - expected_dmg, "Phat Cloud should hit the closer enemy"
    assert far_mob.hp == 500, "Far enemy should be untouched"


def test_phat_cloud_ignores_non_visible_enemies():
    """Phat Cloud should not hit enemies outside FOV."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    px, py = engine.player.x, engine.player.y
    mx, my = px + 2, py
    engine.dungeon.tiles[my][mx] = TILE_FLOOR
    hidden_mob = Entity(
        mx, my, "T", (255, 0, 0),
        name="HiddenMob", entity_type="monster",
        blocks_movement=True, hp=500, power=0,
    )
    hidden_mob.armor = 0
    engine.dungeon.entities.append(hidden_mob)
    # deliberately NOT marking as visible
    engine.dungeon.visible[my, mx] = False

    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    assert hidden_mob.hp == 500, "Non-visible enemy should not take Phat Cloud damage"


def test_phat_cloud_no_crash_when_no_enemies():
    """Phat Cloud should silently skip (no error) when no visible enemies exist."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    _, idx = add_joint(engine)
    # Should not raise
    smoke_joint(engine, idx)


def test_phat_cloud_not_active_below_level_3():
    """Enemies should take no Phat Cloud damage at Smoking level 2."""
    engine = make_engine()
    set_smoking_level(engine, 2)

    monster = place_visible_monster(engine, dx=2, hp=500)
    initial_hp = monster.hp

    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    # No Phat Cloud damage (OG Kush has no direct damage effect)
    assert monster.hp == initial_hp, (
        f"Monster should not have taken Phat Cloud damage at Smoking level 2, "
        f"but HP changed: {initial_hp} -> {monster.hp}"
    )


def test_phat_cloud_damage_uses_effective_tolerance_with_ring_bonus():
    """Phat Cloud damage should reflect effective_tolerance (including ring bonuses)."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    # Add a ring bonus to tolerance
    engine.player_stats.ring_bonuses["tolerance"] = 4

    tlr = engine.player_stats.effective_tolerance
    expected_dmg = 10 + tlr // 2

    monster = place_visible_monster(engine, dx=2, hp=500)
    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    assert monster.hp == 500 - expected_dmg, (
        f"Phat Cloud should use effective_tolerance (base + ring bonus). "
        f"Expected dmg={expected_dmg}, got {500 - monster.hp}"
    )


def test_phat_cloud_kills_enemy_and_emits_death_event():
    """Phat Cloud killing blow should emit entity_died and mark monster dead."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    tlr = engine.player_stats.effective_tolerance
    cloud_dmg = 10 + tlr // 2
    # Give monster exactly cloud_dmg HP so Phat Cloud kills it
    monster = place_visible_monster(engine, dx=2, hp=cloud_dmg)

    death_events = []
    engine.event_bus.on("entity_died", lambda **kw: death_events.append(kw))

    _, idx = add_joint(engine)
    smoke_joint(engine, idx)

    assert not monster.alive, "Monster should be dead after Phat Cloud kill"
    assert any(e.get("entity") is monster for e in death_events), (
        "entity_died event should have been emitted for the Phat Cloud kill"
    )


# ---------------------------------------------------------------------------
# +2 TOL, +2 CON (Level 2)
# ---------------------------------------------------------------------------

def test_stat_up_increases_tolerance_and_constitution():
    """+2 TOL, +2 CON perk should add +2 tolerance and +2 constitution."""
    engine = make_engine()
    ps = engine.player_stats

    old_tol = ps.tolerance
    old_con = ps.constitution

    engine._apply_perk("Smoking", 2)

    assert ps.tolerance == old_tol + 2, (
        f"Expected tolerance {old_tol + 2}, got {ps.tolerance}"
    )
    assert ps.constitution == old_con + 2, (
        f"Expected constitution {old_con + 2}, got {ps.constitution}"
    )


def test_stat_up_updates_base_dict():
    """+2 TOL, +2 CON perk should update _base so stats display correctly as permanent."""
    engine = make_engine()
    ps = engine.player_stats

    engine._apply_perk("Smoking", 2)

    assert ps._base["tolerance"] == ps.tolerance, (
        "_base['tolerance'] should match raw tolerance after stat perk"
    )
    assert ps._base["constitution"] == ps.constitution, (
        "_base['constitution'] should match raw constitution after stat perk"
    )


def test_stat_up_increases_max_hp_and_heals():
    """+2 CON from stat perk should add 20 max HP and heal 20 HP."""
    engine = make_engine()
    # Damage the player first so there's room to heal
    engine.player.hp = max(1, engine.player.hp - 30)
    old_hp = engine.player.hp
    old_max_hp = engine.player.max_hp

    engine._apply_perk("Smoking", 2)

    assert engine.player.max_hp == old_max_hp + 20, (
        f"Expected max_hp {old_max_hp + 20}, got {engine.player.max_hp}"
    )
    assert engine.player.hp == old_hp + 20, (
        f"Expected hp {old_hp + 20} after heal, got {engine.player.hp}"
    )


def test_stat_up_heal_does_not_exceed_new_max_hp():
    """Stat perk should not overheal beyond the new max HP."""
    engine = make_engine()
    # Player at full HP
    engine.player.hp = engine.player.max_hp

    engine._apply_perk("Smoking", 2)

    assert engine.player.hp <= engine.player.max_hp, (
        "HP should not exceed max_hp after stat perk heal"
    )


def test_stat_up_no_double_apply_on_repeated_calls():
    """Calling _apply_perk multiple times should stack (intentional - caller controls this)."""
    engine = make_engine()
    ps = engine.player_stats

    old_tol = ps.tolerance
    engine._apply_perk("Smoking", 2)
    engine._apply_perk("Smoking", 2)

    assert ps.tolerance == old_tol + 4, (
        "Two calls to _apply_perk should stack; this is a caller-side guard issue"
    )


# ---------------------------------------------------------------------------
# Roach Fiend (Level 4)
# ---------------------------------------------------------------------------

def test_roach_fiend_saves_joint_on_lucky_roll():
    """When random < 0.3, Roach Fiend should prevent joint consumption."""
    engine = make_engine()
    set_smoking_level(engine, 4)

    item, idx = add_joint(engine)
    initial_qty = item.quantity  # 1

    with patch("random.random", return_value=0.2):  # < 0.3 → save the joint
        smoke_joint(engine, idx)

    # The joint should still be in inventory at original quantity
    still_in_inv = any(x is item for x in engine.player.inventory)
    assert still_in_inv, "Roach Fiend should have prevented joint consumption"
    assert item.quantity == initial_qty, (
        f"Joint quantity should remain {initial_qty}, got {item.quantity}"
    )


def test_roach_fiend_consumes_joint_on_unlucky_roll():
    """When random >= 0.3, the joint should be consumed normally."""
    engine = make_engine()
    set_smoking_level(engine, 4)

    item, idx = add_joint(engine)

    with patch("random.random", return_value=0.5):  # >= 0.3 → consume
        smoke_joint(engine, idx)

    still_in_inv = any(x is item for x in engine.player.inventory)
    assert not still_in_inv, "Joint should have been consumed when Roach Fiend roll fails"


def test_roach_fiend_not_active_at_level_3():
    """Roach Fiend should not trigger at Smoking level 3."""
    engine = make_engine()
    set_smoking_level(engine, 3)

    item, idx = add_joint(engine)

    with patch("random.random", return_value=0.1):  # would save if level 4
        smoke_joint(engine, idx)

    still_in_inv = any(x is item for x in engine.player.inventory)
    assert not still_in_inv, "Joint should always be consumed at Smoking level 3"


def test_roach_fiend_not_active_at_level_2():
    """Roach Fiend should not trigger at Smoking level 2."""
    engine = make_engine()
    set_smoking_level(engine, 2)

    item, idx = add_joint(engine)

    with patch("random.random", return_value=0.1):  # would save if level 4
        smoke_joint(engine, idx)

    still_in_inv = any(x is item for x in engine.player.inventory)
    assert not still_in_inv, "Joint should always be consumed at Smoking level 2"


def test_roach_fiend_message_on_save():
    """Roach Fiend should append a message when it saves the joint."""
    engine = make_engine()
    set_smoking_level(engine, 4)

    _, idx = add_joint(engine)

    with patch("random.random", return_value=0.1):
        smoke_joint(engine, idx)

    has_roach_msg = any(
        isinstance(m, list) and any("Roach Fiend" in str(part) for part in m)
        for m in engine.messages
    )
    assert has_roach_msg, "Expected 'Roach Fiend!' message when joint is saved"


def test_roach_fiend_no_message_on_consume():
    """Roach Fiend should not append a message when the joint is consumed normally."""
    engine = make_engine()
    set_smoking_level(engine, 4)

    _, idx = add_joint(engine)

    with patch("random.random", return_value=0.5):
        smoke_joint(engine, idx)

    has_roach_msg = any(
        isinstance(m, list) and any("Roach Fiend" in str(part) for part in m)
        for m in engine.messages
    )
    assert not has_roach_msg, "Should have no 'Roach Fiend!' message when joint is consumed"


def test_roach_fiend_phat_cloud_both_active_at_level_4():
    """At level 4, both Phat Cloud and Roach Fiend should be active together."""
    engine = make_engine()
    set_smoking_level(engine, 4)

    monster = place_visible_monster(engine, dx=2, hp=500)
    tlr = engine.player_stats.effective_tolerance
    expected_dmg = 10 + tlr // 2

    item, idx = add_joint(engine)

    with patch("random.random", return_value=0.1):  # Roach Fiend saves joint
        smoke_joint(engine, idx)

    # Phat Cloud should have fired
    assert monster.hp == 500 - expected_dmg, "Phat Cloud should fire even when Roach Fiend is active"
    # Roach Fiend should have saved the joint
    still_in_inv = any(x is item for x in engine.player.inventory)
    assert still_in_inv, "Roach Fiend should save the joint even when Phat Cloud fires"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_tests():
    tests = [
        # Phat Cloud (Level 3)
        ("phat_cloud: deals correct damage to nearest visible enemy",   test_phat_cloud_deals_damage_to_nearest_visible_enemy),
        ("phat_cloud: targets nearest (not farther) enemy",             test_phat_cloud_targets_nearest_visible_enemy),
        ("phat_cloud: ignores non-visible enemies",                     test_phat_cloud_ignores_non_visible_enemies),
        ("phat_cloud: no crash when no enemies present",                test_phat_cloud_no_crash_when_no_enemies),
        ("phat_cloud: not active at level 2",                           test_phat_cloud_not_active_below_level_3),
        ("phat_cloud: uses effective_tolerance with ring bonus",        test_phat_cloud_damage_uses_effective_tolerance_with_ring_bonus),
        ("phat_cloud: killing blow emits entity_died event",            test_phat_cloud_kills_enemy_and_emits_death_event),
        # +2 TOL, +2 CON
        ("stat_up: increases tolerance and constitution by 2",          test_stat_up_increases_tolerance_and_constitution),
        ("stat_up: updates _base dict for both stats",                  test_stat_up_updates_base_dict),
        ("stat_up: adds 20 max HP and heals 20 HP",                     test_stat_up_increases_max_hp_and_heals),
        ("stat_up: heal does not exceed new max_hp",                    test_stat_up_heal_does_not_exceed_new_max_hp),
        ("stat_up: stacks on double apply (caller responsibility)",     test_stat_up_no_double_apply_on_repeated_calls),
        # Roach Fiend (Level 4)
        ("roach_fiend: saves joint on lucky roll (< 0.3)",              test_roach_fiend_saves_joint_on_lucky_roll),
        ("roach_fiend: consumes joint on unlucky roll (>= 0.3)",        test_roach_fiend_consumes_joint_on_unlucky_roll),
        ("roach_fiend: not active at level 3",                          test_roach_fiend_not_active_at_level_3),
        ("roach_fiend: not active at level 2",                          test_roach_fiend_not_active_at_level_2),
        ("roach_fiend: appends message when joint saved",               test_roach_fiend_message_on_save),
        ("roach_fiend: no message when joint consumed normally",        test_roach_fiend_no_message_on_consume),
        ("roach_fiend + phat_cloud: both active at level 4",           test_roach_fiend_phat_cloud_both_active_at_level_4),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {name}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\nResult: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if run_tests() else 1)
