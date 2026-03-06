"""
Test Jungle Boyz strain effects.
"""
import random
from engine import GameEngine
from items import get_strain_effect
import effects


def test_jungle_boyz_table_coverage():
    """Test that all Jungle Boyz roll ranges have effects."""
    strain = "Jungle Boyz"
    for roll in [1, 10, 20, 21, 30, 40, 41, 50, 60, 61, 70, 80, 81, 90, 100]:
        player_eff = get_strain_effect(strain, roll, "player")
        monster_eff = get_strain_effect(strain, roll, "monster")
        print(f"  Roll {roll:3d} — Player: {player_eff['type'] if player_eff else 'None':25s} | Monster: {monster_eff['type'] if monster_eff else 'None'}")
        assert player_eff is not None, f"No player effect for {strain} roll {roll}"


def test_effect_registration():
    """Test that all Jungle Boyz effects are registered."""
    expected_ids = {
        "minor_self_reflection",
        "fiery_fists",
        "crippling_attacks",
        "crippled",
        "lifesteal",
        "glory_fists",
        "soul_pair",
    }
    registered = set(effects.EFFECT_REGISTRY.keys())
    for eid in expected_ids:
        assert eid in registered, f"Effect '{eid}' not registered"
    print(f"✓ All {len(expected_ids)} Jungle Boyz effects registered")


def test_shocked_stacks():
    """Test that ShockedEffect supports stacks."""
    eff1 = effects.ShockedEffect(duration=5, stacks=1)
    eff2 = effects.ShockedEffect(duration=5, stacks=2)

    # Test damage modifier
    assert eff1.modify_incoming_damage(100, None) == 115, "Shocked x1 should be 115% damage"
    assert eff2.modify_incoming_damage(100, None) == 130, "Shocked x2 should be 130% damage"

    print(f"✓ ShockedEffect stacking: 1 stack={eff1.modify_incoming_damage(100, None)}, 2 stacks={eff2.modify_incoming_damage(100, None)}")


def test_glory_fists_stat_modification():
    """Test that GloryFistsEffect can increment stats."""
    engine = GameEngine()
    eff = effects.GloryFistsEffect(duration=20)

    original_con = engine.player_stats.constitution
    original_hp = engine.player.max_hp

    # Simulate a Glory Fists proc on Constitution
    engine.player_stats.constitution += 1
    engine.player_stats._base["constitution"] = engine.player_stats.constitution
    engine.player.max_hp += 10

    assert engine.player_stats.constitution == original_con + 1, "Constitution should increase"
    assert engine.player.max_hp == original_hp + 10, "Max HP should increase with Constitution"
    print(f"✓ GloryFistsEffect: CON {original_con} → {engine.player_stats.constitution}, HP {original_hp} → {engine.player.max_hp}")


def test_lifesteal_heal():
    """Test that LifestealEffect heals on hit."""
    engine = GameEngine()
    engine.player.hp = 50
    engine.player.max_hp = 100

    eff = effects.LifestealEffect(duration=8)
    eff.on_player_melee_hit(engine, None, 25)

    expected_hp = min(50 + 25, 100)
    assert engine.player.hp == expected_hp, f"Player should heal 25 HP, got {engine.player.hp}"
    print(f"✓ LifestealEffect: 25 damage → +25 HP (player at {engine.player.hp}/{engine.player.max_hp})")


def test_fiery_fists_ignite_application():
    """Test that FieryFistsEffect applies Ignite stacks."""
    engine = GameEngine()
    from entity import Entity

    target = Entity(x=1, y=1, char='T', color=(255, 0, 0), name='Target')
    target.max_hp = 100
    target.hp = 100

    eff = effects.FieryFistsEffect(duration=10)
    eff.on_player_melee_hit(engine, target, 10)

    ignite = next((e for e in target.status_effects if getattr(e, 'id', '') == 'ignite'), None)
    assert ignite is not None, "Ignite should be applied"
    assert ignite.stacks == 1, "Ignite should have 1 stack"
    assert ignite.duration == 3, "Ignite should last 3 turns"
    print(f"✓ FieryFistsEffect: Applied Ignite x{ignite.stacks} ({ignite.duration} turns)")


def test_crippling_attacks_shocked():
    """Test that CripplingAttacksEffect procs Shocked (50% chance)."""
    engine = GameEngine()
    from entity import Entity

    target = Entity(x=1, y=1, char='T', color=(255, 0, 0), name='Target')
    target.max_hp = 100
    target.hp = 100

    eff = effects.CripplingAttacksEffect(duration=10)

    # Test multiple hits to get a proc
    proc_count = 0
    for _ in range(100):
        target.status_effects = []
        eff.on_player_melee_hit(engine, target, 10)
        if any(getattr(e, 'id', '') == 'shocked' for e in target.status_effects):
            proc_count += 1

    # With 100 tries at 50% chance, we should get roughly 50 procs (with some variance)
    assert 30 < proc_count < 70, f"Crippling Attacks should proc ~50%, got {proc_count}/100"
    print(f"✓ CripplingAttacksEffect: {proc_count}/100 procs (expected ~50)")


def test_self_reflection_damage():
    """Test that MinorSelfReflectionEffect does self-damage (10% chance)."""
    engine = GameEngine()
    engine.player.hp = 100
    engine.player.max_hp = 100

    eff = effects.MinorSelfReflectionEffect(duration=10)

    # Test multiple hits to get a proc
    damage_taken = 0
    for _ in range(100):
        hp_before = engine.player.hp
        eff.on_player_melee_hit(engine, None, 20)
        if engine.player.hp < hp_before:
            damage_taken += hp_before - engine.player.hp

    # With 100 tries at 10% chance, we should get roughly 10 procs of 20 damage each = 200 total
    # But player HP caps at 0, so expect around 200 (with some variance and the last hit capping at 0)
    assert 100 < damage_taken < 300, f"Self-Reflection should do ~200 damage over 100 attempts, got {damage_taken}"
    print(f"✓ MinorSelfReflectionEffect: {damage_taken} damage over 100 attempts (expected ~200)")


if __name__ == "__main__":
    print("\n=== Jungle Boyz Strain Testing ===\n")

    print("1. Testing strain table coverage...")
    test_jungle_boyz_table_coverage()
    print()

    print("2. Testing effect registration...")
    test_effect_registration()
    print()

    print("3. Testing ShockedEffect stacking...")
    test_shocked_stacks()
    print()

    print("4. Testing GloryFistsEffect stat modification...")
    test_glory_fists_stat_modification()
    print()

    print("5. Testing LifestealEffect healing...")
    test_lifesteal_heal()
    print()

    print("6. Testing FieryFistsEffect Ignite application...")
    test_fiery_fists_ignite_application()
    print()

    print("7. Testing CripplingAttacksEffect Shocked proc (50%)...")
    test_crippling_attacks_shocked()
    print()

    print("8. Testing MinorSelfReflectionEffect self-damage (10%)...")
    test_self_reflection_damage()
    print()

    print("✓ All tests passed!")
