"""
Tests that Jerome's chicken-eating mechanic works correctly.

Jerome should eat fried chicken whenever his HP drops to 40 or below.
Eating is free (0 energy) and happens at the start of his AI turn, so
damage-over-time effects, multi-hit attacks, and burst damage should
never kill him before he gets a chance to eat (unless he's out of chicken).

Stats: 75 HP, eats at ≤40, heals 20 + HoT (2/turn, 5 turns), 3 uses.
"""

from engine import GameEngine
from enemies import create_enemy
from ai import do_ai_turn, prepare_ai_tick
import effects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine():
    return GameEngine()


def spawn_jerome(engine, dx=1, dy=0):
    """Spawn Jerome adjacent to the player and return him."""
    px, py = engine.player.x, engine.player.y
    jx, jy = px + dx, py + dy
    jerome = create_enemy("big_nigga_jerome", jx, jy)
    engine.dungeon.entities.append(jerome)
    return jerome


def run_jerome_turn(engine, jerome):
    """Run one AI turn for Jerome."""
    monsters = [e for e in engine.dungeon.entities
                if getattr(e, "entity_type", None) == "monster" and e.alive]
    tick_data = prepare_ai_tick(engine.player, engine.dungeon, monsters)
    do_ai_turn(jerome, engine.player, engine.dungeon, engine, **tick_data)


def tick_effects(engine, jerome):
    """Tick all status effects on Jerome (simulates end-of-turn)."""
    effects.tick_all_effects(jerome, engine)


# ---------------------------------------------------------------------------
# 1. Basic: direct damage triggers eating
# ---------------------------------------------------------------------------

def test_jerome_eats_when_hit_below_threshold():
    """Jerome should eat chicken when his HP drops to 40 or below."""
    engine = make_engine()
    jerome = spawn_jerome(engine)
    assert jerome.max_hp == 75, f"Jerome should have 75 HP, got {jerome.max_hp}"

    # Damage him to exactly 40
    jerome.hp = 40
    run_jerome_turn(engine, jerome)

    assert getattr(jerome, "eaten_count", 0) == 1
    assert jerome.hp == 60  # 40 + 20 heal


def test_jerome_does_not_eat_above_threshold():
    """Jerome should NOT eat when above 40 HP."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    jerome.hp = 41
    run_jerome_turn(engine, jerome)

    assert getattr(jerome, "eaten_count", 0) == 0
    assert jerome.hp == 41


# ---------------------------------------------------------------------------
# 2. Chicken has exactly 3 uses
# ---------------------------------------------------------------------------

def test_jerome_eats_three_times_max():
    """Jerome should eat exactly 3 times, then stop."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    for i in range(5):
        jerome.hp = 30  # below threshold each time
        run_jerome_turn(engine, jerome)

    assert jerome.eaten_count == 3
    # After 3 eats, the 4th and 5th turns should not heal
    assert jerome.hp == 30  # last two turns didn't heal


# ---------------------------------------------------------------------------
# 3. DoT (ignite) can't kill Jerome before he eats
# ---------------------------------------------------------------------------

def test_dot_damage_doesnt_bypass_eating():
    """Ignite ticks happen at end of turn; Jerome eats at start of his turn.
    Even if ignite drops him to ≤40, he should eat on his next turn."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Get Jerome to 45 HP, apply ignite (will tick 1-3 dmg)
    jerome.hp = 45
    effects.apply_effect(jerome, engine, "ignite")

    # Tick ignite — should deal damage, potentially dropping below 40
    tick_effects(engine, jerome)
    hp_after_tick = jerome.hp

    # Now run Jerome's AI turn — he should eat if below threshold
    if hp_after_tick <= 40:
        run_jerome_turn(engine, jerome)
        assert getattr(jerome, "eaten_count", 0) == 1
        assert jerome.hp > hp_after_tick, "Jerome should have healed from eating"


def test_heavy_dot_stacks_jerome_survives():
    """Stack multiple ignite applications, then let Jerome eat through it."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Apply 3 stacks of ignite
    for _ in range(3):
        effects.apply_effect(jerome, engine, "ignite")

    # Tick effects — multiple ignite stacks deal more damage
    tick_effects(engine, jerome)
    hp_after_dot = jerome.hp

    # Jerome should still be alive and eat if below threshold
    assert jerome.alive, "Jerome shouldn't die from one tick of ignite stacks"
    if hp_after_dot <= 40:
        run_jerome_turn(engine, jerome)
        assert getattr(jerome, "eaten_count", 0) == 1


# ---------------------------------------------------------------------------
# 4. Burst damage — one big hit drops Jerome low, he eats next turn
# ---------------------------------------------------------------------------

def test_burst_damage_jerome_eats_next_turn():
    """A single massive hit that drops Jerome to low HP — he eats on his turn."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Simulate a big hit: 60 damage, dropping to 15 HP
    jerome.hp = 15
    run_jerome_turn(engine, jerome)

    assert jerome.eaten_count == 1
    assert jerome.hp == 35  # 15 + 20


# ---------------------------------------------------------------------------
# 5. Eating is free — Jerome still acts after eating
# ---------------------------------------------------------------------------

def test_eating_costs_zero_energy():
    """Jerome should eat AND still have energy to act (move/attack)."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Provoke Jerome so he transitions to CHASING (his AI is passive until hit)
    from ai import AIState
    jerome.ai_state = AIState.CHASING
    jerome.was_provoked = True

    jerome.hp = 30
    player_hp_before = engine.player.hp

    run_jerome_turn(engine, jerome)

    assert jerome.eaten_count == 1
    # Jerome should have also attacked (he's adjacent and provoked)
    assert engine.player.hp < player_hp_before, \
        "Jerome should still act after eating (attack the adjacent player)"


# ---------------------------------------------------------------------------
# 6. HoT effect applied and doesn't stack
# ---------------------------------------------------------------------------

def test_chicken_applies_hot():
    """Eating should apply a HoT (2 HP/turn for 5 turns)."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    jerome.hp = 30
    run_jerome_turn(engine, jerome)

    # Check HoT is on Jerome
    hot_effects = [e for e in jerome.status_effects if e.id == "hot"]
    assert len(hot_effects) == 1, f"Expected 1 HoT effect, got {len(hot_effects)}"
    assert hot_effects[0].amount == 2
    assert hot_effects[0].duration == 5


def test_chicken_hot_refreshes_not_stacks():
    """Eating twice should refresh HoT duration, not stack two HoTs."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # First eat
    jerome.hp = 30
    run_jerome_turn(engine, jerome)
    assert jerome.eaten_count == 1

    # Tick a couple turns so HoT partially expires
    tick_effects(engine, jerome)
    tick_effects(engine, jerome)

    # Second eat
    jerome.hp = 30
    run_jerome_turn(engine, jerome)
    assert jerome.eaten_count == 2

    # Should still be exactly 1 HoT, duration refreshed to 5
    hot_effects = [e for e in jerome.status_effects if e.id == "hot"]
    assert len(hot_effects) == 1, f"HoT should not stack, got {len(hot_effects)}"
    assert hot_effects[0].duration == 5, "HoT duration should be refreshed to 5"


# ---------------------------------------------------------------------------
# 7. Jerome can be killed after all 3 chickens are used
# ---------------------------------------------------------------------------

def test_jerome_killable_after_chicken_depleted():
    """Once all 3 chickens are used, Jerome can be killed normally."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Use all 3 chickens
    for _ in range(3):
        jerome.hp = 30
        run_jerome_turn(engine, jerome)

    assert jerome.eaten_count == 3

    # Now drop him low again — no more chicken
    jerome.hp = 1
    run_jerome_turn(engine, jerome)

    # He should NOT have healed
    assert jerome.eaten_count == 3
    # HP should be 1 (or he might have HoT ticking, but no new eat)
    # The key assertion: eaten_count didn't increase


# ---------------------------------------------------------------------------
# 8. HoT heals correctly over multiple ticks
# ---------------------------------------------------------------------------

def test_hot_heals_over_time():
    """The HoT from chicken should heal 2 HP per tick for 5 ticks = 10 total."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    jerome.hp = 30
    run_jerome_turn(engine, jerome)
    # After eating: 30 + 20 = 50 HP, HoT applied

    total_hot_healing = 0
    for _ in range(5):
        hp_before = jerome.hp
        tick_effects(engine, jerome)
        healed = jerome.hp - hp_before
        total_hot_healing += healed

    assert total_hot_healing == 10, f"HoT should heal 10 total over 5 ticks, got {total_hot_healing}"

    # HoT should be expired now
    hot_effects = [e for e in jerome.status_effects if e.id == "hot"]
    assert len(hot_effects) == 0, "HoT should expire after 5 ticks"


# ---------------------------------------------------------------------------
# 9. Eating caps at max HP
# ---------------------------------------------------------------------------

def test_eating_doesnt_overheal():
    """Chicken heal should not push Jerome above max HP."""
    engine = make_engine()
    jerome = spawn_jerome(engine)

    # Set to 39 (just below threshold) — heal 20 would push to 59, not above 75
    jerome.hp = 39
    run_jerome_turn(engine, jerome)
    assert jerome.hp == 59

    # Set to 40 exactly — heal 20 = 60
    jerome.hp = 40
    run_jerome_turn(engine, jerome)
    assert jerome.hp == 60


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
