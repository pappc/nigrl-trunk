"""
Tests for the targeting range framework and chain lightning fix.

Covers:
  1. AbilityDef has max_range, execute_at, validate, aoe_radius fields
  2. All targeted abilities have execute_at set
  3. max_range values match the plan
  4. _is_targeting_in_range: unlimited (0.0), in-range, out-of-range
  5. _get_targeting_ability_def: returns correct def or None
  6. Out-of-range cursor blocks cast and appends message
  7. In-range cursor executes spell via execute_at dispatch
  8. Dosidos fallback (_execute_dosidos_spell_at) used when targeting_ability_index=None
  9. Chain lightning bounce capped at 2-tile radius; fizzles with message when nothing in range
 10. Chain lightning fires on valid in-range target
 11. AOE_CIRCLE exists in TargetType
 12. render._is_targeting_in_range accessible from render module context
"""

import math
import numpy as np
from engine import GameEngine
from entity import Entity
from menu_state import MenuState
from abilities import ABILITY_REGISTRY, AbilityInstance, TargetType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    """Fresh engine for each test."""
    return GameEngine()


def grant(engine, ability_id: str):
    """Grant an ability and set targeting_ability_index to it."""
    defn = ABILITY_REGISTRY[ability_id]
    inst = AbilityInstance(ability_id, defn)
    inst.charges_remaining = 99
    inst.floor_charges_remaining = 99
    engine.player_abilities = [inst]
    engine.targeting_ability_index = 0
    engine.targeting_spell = {"type": ability_id}
    engine.menu_state = MenuState.TARGETING


def place_monster_visible(engine, dx=3, dy=0, hp=100):
    """Place a live monster near the player on a walkable, visible tile.

    Tries (px+dx, py+dy) first, then scans outward for a clear floor tile
    so the test doesn't break when the default offset lands on a wall.
    """
    px, py = engine.player.x, engine.player.y
    mx, my = px + dx, py + dy
    # If default position is blocked, find a nearby walkable tile in the same direction
    if engine.dungeon.is_terrain_blocked(mx, my):
        found = False
        sign_x = 1 if dx >= 0 else -1
        sign_y = 1 if dy >= 0 else -1
        for dist in range(1, 8):
            for ddx, ddy in [(dist * sign_x, 0), (0, dist * sign_y), (dist * sign_x, dist * sign_y)]:
                cx, cy = px + ddx, py + ddy
                if (0 <= cx < engine.dungeon.width and 0 <= cy < engine.dungeon.height
                        and not engine.dungeon.is_terrain_blocked(cx, cy)):
                    mx, my = cx, cy
                    found = True
                    break
            if found:
                break
    m = Entity(mx, my, "T", (255, 0, 0), name="TestMob",
               entity_type="monster", blocks_movement=True, hp=hp, power=0)
    engine.dungeon.entities.append(m)
    engine.dungeon.visible[my, mx] = True
    return m, mx, my


def get_new_msgs(engine, msgs_before_list):
    """Return new plain-string messages added since msgs_before_list snapshot."""
    all_msgs = list(engine.messages)
    new = all_msgs[len(msgs_before_list):]
    return [m for m in new if isinstance(m, str)]


def snapshot_msgs(engine):
    return list(engine.messages)


def clear_monsters(engine):
    engine.dungeon.entities = [
        e for e in engine.dungeon.entities if e.entity_type != "monster"
    ]


# ---------------------------------------------------------------------------
# 1. AbilityDef fields
# ---------------------------------------------------------------------------

def test_abilitydef_has_new_fields():
    defn = ABILITY_REGISTRY["chain_lightning"]
    assert hasattr(defn, "max_range"), "AbilityDef missing max_range"
    assert hasattr(defn, "aoe_radius"), "AbilityDef missing aoe_radius"
    assert hasattr(defn, "execute_at"), "AbilityDef missing execute_at"
    assert hasattr(defn, "validate"), "AbilityDef missing validate"
    print("[OK] AbilityDef has max_range, aoe_radius, execute_at, validate")


# ---------------------------------------------------------------------------
# 2. All targeted abilities have execute_at
# ---------------------------------------------------------------------------

def test_targeted_abilities_have_execute_at():
    no_execute_at = []
    for ability_id, defn in ABILITY_REGISTRY.items():
        if defn.target_type != TargetType.SELF:
            if defn.execute_at is None:
                no_execute_at.append(ability_id)
    assert not no_execute_at, f"Targeted abilities missing execute_at: {no_execute_at}"
    print("[OK] All targeted abilities have execute_at")


# ---------------------------------------------------------------------------
# 3. max_range values
# ---------------------------------------------------------------------------

def test_max_range_values():
    expected = {
        "chain_lightning": 10.0,
        "firebolt": 12.0,
        "breath_fire": 5.0,
        "arcane_missile": 0.0,
        "dimension_door": 0.0,
        "ray_of_frost": 0.0,
        "warp": 0.0,
    }
    for ability_id, expected_range in expected.items():
        defn = ABILITY_REGISTRY[ability_id]
        assert defn.max_range == expected_range, (
            f"{ability_id}: expected max_range={expected_range}, got {defn.max_range}"
        )
    print("[OK] max_range values match plan")


# ---------------------------------------------------------------------------
# 4. AOE_CIRCLE in TargetType
# ---------------------------------------------------------------------------

def test_aoe_circle_exists():
    assert TargetType.AOE_CIRCLE is not None
    assert TargetType.AOE_CIRCLE.value == "aoe_circle"
    print("[OK] AOE_CIRCLE exists in TargetType")


# ---------------------------------------------------------------------------
# 5. _get_targeting_ability_def
# ---------------------------------------------------------------------------

def test_get_targeting_ability_def_none_when_no_index():
    e = make_engine()
    e.targeting_ability_index = None
    assert e._get_targeting_ability_def() is None
    print("[OK] _get_targeting_ability_def returns None with no index")


def test_get_targeting_ability_def_returns_correct_def():
    e = make_engine()
    grant(e, "chain_lightning")
    defn = e._get_targeting_ability_def()
    assert defn is not None
    assert defn.ability_id == "chain_lightning"
    print("[OK] _get_targeting_ability_def returns correct AbilityDef")


# ---------------------------------------------------------------------------
# 6. _is_targeting_in_range
# ---------------------------------------------------------------------------

def test_in_range_unlimited():
    """max_range=0.0 (arcane_missile) => always True."""
    e = make_engine()
    grant(e, "arcane_missile")
    assert e._is_targeting_in_range(1, 1)
    assert e._is_targeting_in_range(79, 43)
    print("[OK] _is_targeting_in_range: unlimited (max_range=0.0) always True")


def test_in_range_within_range():
    e = make_engine()
    grant(e, "chain_lightning")  # max_range=10.0
    px, py = e.player.x, e.player.y
    assert e._is_targeting_in_range(px + 5, py)   # 5 tiles: in range
    assert e._is_targeting_in_range(px + 10, py)  # exactly at boundary: in range
    print("[OK] _is_targeting_in_range: in-range tiles return True")


def test_in_range_outside_range():
    e = make_engine()
    grant(e, "chain_lightning")  # max_range=10.0
    px, py = e.player.x, e.player.y
    assert not e._is_targeting_in_range(px + 11, py)  # 11 tiles: out of range
    assert not e._is_targeting_in_range(px + 20, py)
    print("[OK] _is_targeting_in_range: out-of-range tiles return False")


def test_in_range_no_ability_index():
    """When targeting_ability_index=None (Dosidos), always in range."""
    e = make_engine()
    e.targeting_ability_index = None
    assert e._is_targeting_in_range(1, 1)
    assert e._is_targeting_in_range(79, 43)
    print("[OK] _is_targeting_in_range: no ability index => unlimited")


# ---------------------------------------------------------------------------
# 7. Out-of-range cursor blocks cast
# ---------------------------------------------------------------------------

def test_out_of_range_blocks_cast_appends_message():
    e = make_engine()
    grant(e, "chain_lightning")  # max_range=10.0
    px, py = e.player.x, e.player.y

    # Pick a cursor that is definitely out of range (Manhattan > 10) even after
    # clamping to dungeon bounds.  Try right first, fall back to left.
    out_x = px + 15
    if out_x >= e.dungeon.width:
        out_x = px - 15
    out_x = max(0, min(out_x, e.dungeon.width - 1))
    assert abs(out_x - px) > 10, "Test setup: could not place cursor out of range"

    e.targeting_cursor = [out_x, py]
    e.menu_state = MenuState.TARGETING

    snap = snapshot_msgs(e)
    e._handle_targeting_input({"type": "confirm_target"})
    new_msgs = get_new_msgs(e, snap)

    assert any("Out of range" in m for m in new_msgs), (
        f"Expected 'Out of range!' message, got: {new_msgs}"
    )
    assert e.menu_state == MenuState.TARGETING, "Targeting mode should stay open"
    print("[OK] Out-of-range cursor blocks cast and appends 'Out of range!' message")


def test_out_of_range_does_not_consume_charge():
    e = make_engine()
    grant(e, "chain_lightning")
    px, py = e.player.x, e.player.y
    out_x = px + 15
    if out_x >= e.dungeon.width:
        out_x = px - 15
    out_x = max(0, min(out_x, e.dungeon.width - 1))
    e.targeting_cursor = [out_x, py]
    e.menu_state = MenuState.TARGETING

    charges_before = e.player_abilities[0].charges_remaining
    e._handle_targeting_input({"type": "confirm_target"})
    assert e.player_abilities[0].charges_remaining == charges_before, "Charge was consumed on out-of-range"
    print("[OK] Out-of-range cast does not consume a charge")


# ---------------------------------------------------------------------------
# 8. execute_at dispatch for ability-indexed spells
# ---------------------------------------------------------------------------

def test_execute_at_dispatch_chain_lightning_fires():
    """Chain lightning should fire (and consume charge) when target is valid in-range monster."""
    e = make_engine()
    clear_monsters(e)
    grant(e, "chain_lightning")
    m, mx, my = place_monster_visible(e, dx=3, dy=0)

    # Make sure the target tile is visible
    e.dungeon.visible[my, mx] = True
    e.targeting_cursor = [mx, my]
    e.menu_state = MenuState.TARGETING

    hp_before = m.hp
    charges_before = e.player_abilities[0].charges_remaining

    e._handle_targeting_input({"type": "confirm_target"})

    assert m.hp < hp_before, "Monster should have taken damage"
    assert e.player_abilities[0].charges_remaining == charges_before - 1, "Charge should have been consumed"
    assert e.menu_state == MenuState.NONE, "Targeting should close after cast"
    print("[OK] execute_at dispatch fires chain lightning, consumes charge, closes menu")


def test_execute_at_dispatch_firebolt_fires():
    """Firebolt should fire when target is valid and in range."""
    e = make_engine()
    clear_monsters(e)
    grant(e, "firebolt")
    m, mx, my = place_monster_visible(e, dx=3, dy=0)
    e.dungeon.visible[my, mx] = True
    e.targeting_cursor = [mx, my]
    e.menu_state = MenuState.TARGETING

    hp_before = m.hp
    charges_before = e.player_abilities[0].charges_remaining

    e._handle_targeting_input({"type": "confirm_target"})

    assert m.hp < hp_before, "Monster should have taken damage from firebolt"
    assert e.player_abilities[0].charges_remaining == charges_before - 1
    assert e.menu_state == MenuState.NONE
    print("[OK] execute_at dispatch fires firebolt correctly")


def test_execute_at_dispatch_arcane_missile_fires():
    """Arcane missile should hit a visible monster."""
    e = make_engine()
    clear_monsters(e)
    grant(e, "arcane_missile")
    m, mx, my = place_monster_visible(e, dx=3, dy=0)
    e.dungeon.visible[my, mx] = True
    e.targeting_cursor = [mx, my]
    e.menu_state = MenuState.TARGETING

    hp_before = m.hp
    e._handle_targeting_input({"type": "confirm_target"})
    assert m.hp < hp_before, "Monster should take damage from arcane missile"
    assert e.menu_state == MenuState.NONE
    print("[OK] execute_at dispatch fires arcane missile correctly")


def test_execute_at_ray_of_frost_self_target_blocked():
    """Ray of frost aimed at self should produce error message and not fire."""
    e = make_engine()
    grant(e, "ray_of_frost")
    px, py = e.player.x, e.player.y
    e.targeting_cursor = [px, py]  # aim at self
    e.menu_state = MenuState.TARGETING

    snap = snapshot_msgs(e)
    e._handle_targeting_input({"type": "confirm_target"})
    new_msgs = get_new_msgs(e, snap)

    assert any("aim" in m.lower() or "yourself" in m.lower() for m in new_msgs), (
        f"Expected self-aim error, got: {new_msgs}"
    )
    assert e.menu_state == MenuState.TARGETING, "Should stay in targeting mode"
    print("[OK] Ray of Frost aimed at self is blocked with error message")


# ---------------------------------------------------------------------------
# 9. Dosidos fallback (_execute_dosidos_spell_at)
# ---------------------------------------------------------------------------

def test_dosidos_fallback_used_when_no_ability_index():
    """When targeting_ability_index=None, _execute_dosidos_spell_at handles the cast."""
    e = make_engine()
    clear_monsters(e)
    m, mx, my = place_monster_visible(e, dx=3, dy=0)
    e.dungeon.visible[my, mx] = True

    # Simulate Dosidos-triggered chain lightning (no ability index)
    e.targeting_ability_index = None
    e.targeting_spell = {"type": "chain_lightning", "total_hits": 4}
    e.targeting_cursor = [mx, my]
    e.menu_state = MenuState.TARGETING

    hp_before = m.hp
    e._handle_targeting_input({"type": "confirm_target"})

    assert m.hp < hp_before, "Dosidos chain lightning should damage monster"
    assert e.menu_state == MenuState.NONE, "Targeting should close"
    print("[OK] Dosidos fallback path works for chain lightning")


def test_dosidos_fallback_no_range_check():
    """Dosidos spells (no ability index) skip the range check."""
    e = make_engine()
    clear_monsters(e)
    # Place monster 15 tiles away (out of chain_lightning's 10-tile ability range)
    m, mx, my = place_monster_visible(e, dx=15, dy=0)
    mx = min(mx, e.dungeon.width - 1)
    my = min(my, e.dungeon.height - 1)
    e.dungeon.visible[my, mx] = True

    # Dosidos — no ability index, no range cap
    e.targeting_ability_index = None
    e.targeting_spell = {"type": "chain_lightning", "total_hits": 1}
    e.targeting_cursor = [mx, my]
    e.menu_state = MenuState.TARGETING

    snap = snapshot_msgs(e)
    e._handle_targeting_input({"type": "confirm_target"})
    new_msgs = get_new_msgs(e, snap)

    assert not any("Out of range" in msg for msg in new_msgs), (
        "Dosidos spells should not be blocked by range check"
    )
    print("[OK] Dosidos fallback skips range check")


# ---------------------------------------------------------------------------
# 10. Chain lightning bounce cap
# ---------------------------------------------------------------------------

def test_chain_lightning_bounce_fizzles_no_nearby():
    """Lightning fizzles after first hit when no other monster within 2 tiles."""
    e = make_engine()
    clear_monsters(e)

    # Primary target: hp=1 so it dies on first hit, removing it from bounce candidates
    m1, mx1, my1 = place_monster_visible(e, dx=3, dy=0, hp=1)
    e.dungeon.visible[my1, mx1] = True

    # Second monster far away (10+ tiles from m1) — out of 2-tile bounce range
    m2_x = min(mx1 + 10, e.dungeon.width - 1)
    m2 = Entity(m2_x, my1, "T", (255, 0, 0), name="FarMob",
                entity_type="monster", blocks_movement=True, hp=100, power=0)
    e.dungeon.entities.append(m2)

    snap = snapshot_msgs(e)
    result = e._spell_chain_lightning(mx1, my1, total_hits=4)
    new_msgs = get_new_msgs(e, snap)

    assert result is True, "Spell should fire (first hit)"
    assert not m1.alive, "Primary target should be dead"
    assert m2.hp == 100, "Far monster should NOT be hit (out of bounce range)"
    assert any("fizzles" in msg.lower() for msg in new_msgs), (
        f"Expected 'fizzles' message, got: {new_msgs}"
    )
    print("[OK] Chain lightning bounce fizzles when no monster within 2 tiles")


def test_chain_lightning_bounce_hits_nearby():
    """Lightning bounces to nearby monster after primary target dies."""
    e = make_engine()
    clear_monsters(e)

    # Primary target: hp=1 so it dies on first hit, clearing the way for bounce
    m1, mx1, my1 = place_monster_visible(e, dx=3, dy=0, hp=1)
    e.dungeon.visible[my1, mx1] = True

    # Second monster 1 tile from m1 — within 2-tile bounce range
    m2_x = mx1 + 1
    m2 = Entity(m2_x, my1, "T", (255, 0, 0), name="NearMob",
                entity_type="monster", blocks_movement=True, hp=100, power=0)
    e.dungeon.entities.append(m2)

    result = e._spell_chain_lightning(mx1, my1, total_hits=2)
    assert result is True
    assert not m1.alive, "Primary target should be dead"
    assert m2.hp < 100, "Nearby monster should be hit by bounce"
    print("[OK] Chain lightning bounces to monster within 2 tiles")


def test_chain_lightning_bounce_dist_cap():
    """After primary dies, bounce hits monster at dist=2 but not dist=3."""
    e = make_engine()
    clear_monsters(e)

    # Primary: hp=1 so it dies, then bounce candidates are m2 and m3
    m1, mx1, my1 = place_monster_visible(e, dx=3, dy=0, hp=1)
    e.dungeon.visible[my1, mx1] = True

    # At exactly 2 tiles from m1 — at boundary (dist_sq=4)
    m2 = Entity(mx1 + 2, my1, "T", (255, 0, 0), name="BoundaryMob",
                entity_type="monster", blocks_movement=True, hp=100, power=0)
    e.dungeon.entities.append(m2)

    # At 3 tiles from m1 — just outside boundary (dist_sq=9)
    m3 = Entity(mx1 + 3, my1, "T", (255, 0, 0), name="OutsideMob",
                entity_type="monster", blocks_movement=True, hp=100, power=0)
    e.dungeon.entities.append(m3)

    result = e._spell_chain_lightning(mx1, my1, total_hits=2)
    assert result is True
    assert not m1.alive, "Primary target should be dead"
    assert m2.hp < 100, "Monster at exactly 2 tiles should be hit by bounce"
    assert m3.hp == 100, "Monster at 3 tiles should NOT be hit"
    print("[OK] Chain lightning bounce: dist=2 hit, dist=3 not hit")


def test_chain_lightning_invalid_target():
    """Chain lightning with no enemy at target tile returns False."""
    e = make_engine()
    e.dungeon.visible[5, 5] = True
    result = e._spell_chain_lightning(5, 5, total_hits=4)
    assert result is False
    print("[OK] Chain lightning returns False for empty tile")


def test_chain_lightning_out_of_sight():
    """Chain lightning target not in sight returns False."""
    e = make_engine()
    clear_monsters(e)
    m, mx, my = place_monster_visible(e, dx=3, dy=0)
    e.dungeon.visible[my, mx] = False  # not visible
    result = e._spell_chain_lightning(mx, my, total_hits=4)
    assert result is False
    print("[OK] Chain lightning returns False when target out of sight")


# ---------------------------------------------------------------------------
# 11. Esc in targeting mode clears all state
# ---------------------------------------------------------------------------

def test_esc_clears_targeting_state():
    e = make_engine()
    grant(e, "chain_lightning")
    e.targeting_cursor = [5, 5]

    e._handle_targeting_input({"type": "close_menu"})

    assert e.menu_state == MenuState.NONE
    assert e.targeting_spell is None
    assert e.targeting_ability_index is None
    assert e.targeting_item_index is None
    print("[OK] Esc clears all targeting state")


# ---------------------------------------------------------------------------
# 12. render module can call _is_targeting_in_range
# ---------------------------------------------------------------------------

def test_render_uses_in_range_helper():
    """Verify render.py can call engine._is_targeting_in_range without error."""
    e = make_engine()
    grant(e, "chain_lightning")
    cx, cy = e.player.x, e.player.y

    # Simulate what render_targeting_mode does
    in_range = e._is_targeting_in_range(cx, cy)
    assert isinstance(in_range, bool)

    # Out of range
    out_range = e._is_targeting_in_range(cx + 50, cy)
    assert isinstance(out_range, bool)
    assert not out_range or (cx + 50 >= e.dungeon.width)  # either false or clamped
    print("[OK] render module helper _is_targeting_in_range works correctly")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_abilitydef_has_new_fields,
        test_targeted_abilities_have_execute_at,
        test_max_range_values,
        test_aoe_circle_exists,
        test_get_targeting_ability_def_none_when_no_index,
        test_get_targeting_ability_def_returns_correct_def,
        test_in_range_unlimited,
        test_in_range_within_range,
        test_in_range_outside_range,
        test_in_range_no_ability_index,
        test_out_of_range_blocks_cast_appends_message,
        test_out_of_range_does_not_consume_charge,
        test_execute_at_dispatch_chain_lightning_fires,
        test_execute_at_dispatch_firebolt_fires,
        test_execute_at_dispatch_arcane_missile_fires,
        test_execute_at_ray_of_frost_self_target_blocked,
        test_dosidos_fallback_used_when_no_ability_index,
        test_dosidos_fallback_no_range_check,
        test_chain_lightning_bounce_fizzles_no_nearby,
        test_chain_lightning_bounce_hits_nearby,
        test_chain_lightning_bounce_dist_cap,
        test_chain_lightning_invalid_target,
        test_chain_lightning_out_of_sight,
        test_esc_clears_targeting_state,
        test_render_uses_in_range_helper,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as ex:
            print(f"[FAIL] {t.__name__}: {ex}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests.")
    if failed:
        raise SystemExit(1)
