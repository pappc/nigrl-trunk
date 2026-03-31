"""Tests for Infected L4: Corpse Explosion and Infection Nova."""
import pytest
from engine import GameEngine
from entity import Entity
import effects


def _make_engine(seed=42):
    engine = GameEngine(seed=seed)
    engine.player.hp = 200
    engine.player.max_hp = 200
    return engine


def _spawn_monster(engine, x, y, hp=30, max_hp=None, defense=0, name="Zombie"):
    m = Entity(x, y, "Z", (180, 50, 50), name, blocks_movement=True)
    m.entity_type = "monster"
    m.hp = hp
    m.max_hp = max_hp if max_hp is not None else hp
    m.defense = defense
    m.alive = True
    m.power = 5
    m.status_effects = []
    engine.dungeon.entities.append(m)
    return m


def _give_infected_l4(engine):
    """Give player Infected level 4 and apply Zombie Rage."""
    skill = engine.skills.get("Infected")
    skill.set_level(4)
    # Apply Zombie Rage buff
    effects.apply_effect(engine.player, engine, "zombie_rage")


def test_corpse_explosion_triggers_on_rage_kill():
    """Killing during Zombie Rage explodes the corpse."""
    engine = _make_engine()
    _give_infected_l4(engine)

    # Place two monsters adjacent to each other
    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=30)  # will die instantly
    m2 = _spawn_monster(engine, 6, 5, hp=100)

    # Kill m1 via take_damage + emit entity_died
    m1.take_damage(10)
    assert not m1.alive
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    # m2 should have taken explosion damage (30% of m1's max_hp=30 → 9)
    assert m2.hp < 100, f"m2 should have taken explosion damage, hp={m2.hp}"


def test_corpse_explosion_no_trigger_without_rage():
    """No explosion without Zombie Rage active."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(4)
    # Do NOT apply Zombie Rage

    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=30)
    m2 = _spawn_monster(engine, 6, 5, hp=100)

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    assert m2.hp == 100, "m2 should be untouched without Zombie Rage"


def test_corpse_explosion_infection_gain():
    """Explosion adds +2 infection at chain depth 0."""
    engine = _make_engine()
    _give_infected_l4(engine)
    engine.player.infection = 0

    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=30)
    m2 = _spawn_monster(engine, 6, 5, hp=100)  # survives

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    # +5 from Zombie Rage activation, +2 from corpse explosion depth 0
    # add_infection also adds Infected XP via combat.add_infection
    assert engine.player.infection >= 2, f"Should have at least +2 infection, got {engine.player.infection}"


def test_corpse_explosion_chain_escalates_infection():
    """Chain explosions escalate infection: +2, +4, +6..."""
    engine = _make_engine()
    _give_infected_l4(engine)
    engine.player.infection = 0

    # m1 at (5,5), m2 at (6,5) with 1 hp (will chain), m3 at (7,5)
    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=50, name="Z1")
    m2 = _spawn_monster(engine, 6, 5, hp=1, max_hp=50, name="Z2")  # will die from explosion (15 dmg)
    m3 = _spawn_monster(engine, 7, 5, hp=100, name="Z3")

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    # m1 explodes (30% of 50 = 15) → hits m2 (kills it, +2 infection) → m2 explodes → hits m3 (+4 infection)
    assert not m2.alive, "m2 should have been killed by m1's explosion"
    assert m3.hp < 100, "m3 should have taken damage from m2's chain explosion"
    # Total infection from explosions: 2 (depth 0) + 4 (depth 1) = 6
    # Plus 5 from Zombie Rage activation
    assert engine.player.infection >= 6, f"Expected at least 6 infection from chains, got {engine.player.infection}"


def test_infection_nova_triggers_at_100():
    """Infection Nova fires when explosions push infection to 100."""
    engine = _make_engine()
    _give_infected_l4(engine)
    engine.player.infection = 99  # one away from nova

    px, py = engine.player.x, engine.player.y
    # Place bomber adjacent to player, bystander next to bomber
    m1 = _spawn_monster(engine, px + 2, py, hp=1, max_hp=30, name="Bomber")
    m2 = _spawn_monster(engine, px + 3, py, hp=100, name="Bystander")  # in explosion range
    # Place enemy within Nova radius 5 of PLAYER but outside explosion radius 3 of bomber
    m3 = _spawn_monster(engine, px + 4, py, hp=100, name="NovaTarget")

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    # Explosion adds +2 infection → 101 → triggers Nova
    # Infection should reset to 50
    assert engine.player.infection == 50, f"Infection should reset to 50, got {engine.player.infection}"

    # Hollowed Out should be applied
    has_hollowed = any(getattr(e, 'id', '') == 'hollowed_out' for e in engine.player.status_effects)
    assert has_hollowed, "Player should have Hollowed Out debuff"

    # m3 at distance 4 from player should be hit by Nova (radius 5)
    assert m3.hp < 100, f"NovaTarget should be hit by Nova, hp={m3.hp}"


def test_nova_only_once_per_floor():
    """Hollowed Out prevents a second Nova."""
    engine = _make_engine()
    _give_infected_l4(engine)
    engine.player.infection = 99

    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=30)
    m2 = _spawn_monster(engine, 6, 5, hp=200)

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    assert engine.player.infection == 50  # Nova reset

    # Now push infection to 100 again
    engine.player.infection = 99
    m4 = _spawn_monster(engine, 5, 5, hp=1, max_hp=30, name="Z4")
    m5 = _spawn_monster(engine, 6, 5, hp=200, name="Z5")

    m4.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m4, killer=engine.player)

    # Should NOT reset to 50 again — Hollowed Out blocks it
    assert engine.player.infection > 50, f"Second nova should not trigger, infection={engine.player.infection}"


def test_explosion_respects_defense():
    """Explosion damage is reduced by target defense."""
    engine = _make_engine()
    _give_infected_l4(engine)

    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=50, name="Bomber")
    m2 = _spawn_monster(engine, 6, 5, hp=100, defense=5, name="Tank")

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    # Explosion = 30% of 50 = 15. After defense 5 = max(1, 15-5) = 10
    assert m2.hp == 90, f"Expected 90 hp after defended explosion, got {m2.hp}"


def test_explosion_radius_euclidean():
    """Enemies beyond Euclidean radius 3 are not hit."""
    engine = _make_engine()
    _give_infected_l4(engine)

    m1 = _spawn_monster(engine, 5, 5, hp=1, max_hp=50, name="Bomber")
    # Distance 4 — outside radius 3
    m_far = _spawn_monster(engine, 9, 5, hp=100, name="Far")
    # Distance ~2.83 — inside radius 3
    m_near = _spawn_monster(engine, 7, 7, hp=100, name="Near")

    m1.take_damage(10)
    engine.event_bus.emit("entity_died", entity=m1, killer=engine.player)

    assert m_far.hp == 100, "Enemy at distance 4 should not be hit"
    assert m_near.hp < 100, f"Enemy at distance ~2.83 should be hit, hp={m_near.hp}"


# ---------------------------------------------------------------------------
# Infected L5: Hunger tests
# ---------------------------------------------------------------------------

def _give_infected_l5(engine):
    """Give player Infected level 5 and apply Zombie Rage."""
    skill = engine.skills.get("Infected")
    skill.set_level(5)
    effects.apply_effect(engine.player, engine, "zombie_rage")


def test_hunger_applied_on_purge_at_l5():
    """Purge at Infected L5 grants Hunger buff."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(5)
    engine.player.infection = 30

    from abilities import _execute_purge
    _execute_purge(engine)

    has_hunger = any(getattr(e, 'id', '') == 'hunger' for e in engine.player.status_effects)
    assert has_hunger, "Purge at L5 should grant Hunger buff"


def test_hunger_not_applied_below_l5():
    """Purge below L5 does NOT grant Hunger."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(4)
    engine.player.infection = 30

    from abilities import _execute_purge
    _execute_purge(engine)

    has_hunger = any(getattr(e, 'id', '') == 'hunger' for e in engine.player.status_effects)
    assert not has_hunger, "Purge below L5 should not grant Hunger"


def test_hunger_heals_on_melee():
    """Hunger heals 25% of melee damage dealt."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(5)
    engine.player.infection = 10

    # Apply Hunger directly
    effects.apply_effect(engine.player, engine, "hunger")

    # Damage player so healing is visible
    engine.player.hp = 100
    old_hp = engine.player.hp

    # Simulate on_player_melee_hit via the effect
    hunger = next(e for e in engine.player.status_effects if getattr(e, 'id', '') == 'hunger')
    hunger.on_player_melee_hit(engine, None, 40)

    # Should heal 25% of 40 = 10
    assert engine.player.hp == old_hp + 10, f"Expected {old_hp + 10} HP, got {engine.player.hp}"
    # Should add +1 infection
    assert engine.player.infection == 11, f"Expected 11 infection, got {engine.player.infection}"


def test_zombie_stare_cone_at_l5():
    """At Infected L5, Zombie Stare hits multiple enemies in a 90° cone."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(5)
    engine.player.infection = 0

    px, py = engine.player.x, engine.player.y
    # Place two enemies in a cone to the east
    m1 = _spawn_monster(engine, px + 2, py, hp=100, name="East1")
    m2 = _spawn_monster(engine, px + 2, py + 1, hp=100, name="East2")

    from abilities import _execute_at_zombie_stare
    # Target east direction
    result = _execute_at_zombie_stare(engine, px + 3, py)

    assert result is True, "Zombie Stare cone should succeed"
    # Both should be stunned
    m1_stunned = any(getattr(e, 'id', '') == 'stun' for e in m1.status_effects)
    m2_stunned = any(getattr(e, 'id', '') == 'stun' for e in m2.status_effects)
    assert m1_stunned, "m1 should be stunned by cone"
    assert m2_stunned, "m2 should be stunned by cone"
    # Infection cost should be 8 (cone mode)
    assert engine.player.infection == 8, f"Expected 8 infection (cone cost), got {engine.player.infection}"


def test_zombie_stare_single_target_below_l5():
    """Below L5, Zombie Stare is single target with +5 infection."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(4)
    engine.player.infection = 0

    px, py = engine.player.x, engine.player.y
    m1 = _spawn_monster(engine, px + 2, py, hp=100, name="Target")
    m2 = _spawn_monster(engine, px + 2, py + 1, hp=100, name="Nearby")

    from abilities import _execute_at_zombie_stare
    result = _execute_at_zombie_stare(engine, px + 2, py)

    assert result is True
    m1_stunned = any(getattr(e, 'id', '') == 'stun' for e in m1.status_effects)
    m2_stunned = any(getattr(e, 'id', '') == 'stun' for e in m2.status_effects)
    assert m1_stunned, "Targeted enemy should be stunned"
    assert not m2_stunned, "Nearby enemy should NOT be stunned in single-target mode"
    assert engine.player.infection == 5, f"Expected 5 infection (single target), got {engine.player.infection}"


# ---------------------------------------------------------------------------
# Infected L6: Outbreak tests
# ---------------------------------------------------------------------------

def test_outbreak_marks_enemies_in_area():
    """Outbreak marks all enemies in a 7x7 area."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(6)
    engine.player.infection = 0

    px, py = engine.player.x, engine.player.y
    # Place enemies within 7x7 centered 2 tiles east of player (all adjacent to center)
    cx, cy = px + 2, py
    m1 = _spawn_monster(engine, cx, cy, hp=100, name="Center")
    m2 = _spawn_monster(engine, cx + 1, cy, hp=100, name="East")
    m3 = _spawn_monster(engine, cx - 1, cy, hp=100, name="West")

    from abilities import _execute_at_outbreak
    result = _execute_at_outbreak(engine, cx, cy)

    assert result is True, "Outbreak should succeed"
    for m in (m1, m2, m3):
        has_outbreak = any(getattr(e, 'id', '') == 'outbreak' for e in m.status_effects)
        assert has_outbreak, f"{m.name} should be marked with Outbreak"

    # +2 infection per enemy = 6
    assert engine.player.infection >= 6, f"Expected at least 6 infection, got {engine.player.infection}"


def test_outbreak_echo_damage():
    """Damage to a marked enemy echoes 30% to other marked enemies within radius 3."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(6)

    m1 = _spawn_monster(engine, 5, 5, hp=100, name="Victim")
    m2 = _spawn_monster(engine, 6, 5, hp=100, name="Linked")

    # Apply Outbreak to both
    effects.apply_effect(m1, engine, "outbreak", silent=True)
    effects.apply_effect(m2, engine, "outbreak", silent=True)

    # Deal 40 damage to m1
    m1.take_damage(40)

    # m2 should have taken 30% of 40 = 12, minus defense (0) = 12
    assert m2.hp < 100, f"Linked enemy should take echo damage, hp={m2.hp}"
    expected = 100 - max(1, int(40 * 0.30))
    assert m2.hp == expected, f"Expected {expected} hp, got {m2.hp}"


def test_outbreak_echo_no_chain():
    """Echo damage should NOT trigger further echoes (no infinite loops)."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(6)

    m1 = _spawn_monster(engine, 5, 5, hp=100, name="A")
    m2 = _spawn_monster(engine, 6, 5, hp=100, name="B")
    m3 = _spawn_monster(engine, 7, 5, hp=100, name="C")

    effects.apply_effect(m1, engine, "outbreak", silent=True)
    effects.apply_effect(m2, engine, "outbreak", silent=True)
    effects.apply_effect(m3, engine, "outbreak", silent=True)

    # Deal 40 damage to m1
    m1.take_damage(40)

    # m2 should take echo from m1 (30% of 40 = 12)
    assert m2.hp == 88, f"m2 should take 12 echo, got hp={m2.hp}"
    # m3 should also take echo from m1 (within radius 3 of m1 at distance 2)
    # But m3 should NOT take echo from m2's echo damage (no chain)
    assert m3.hp == 88, f"m3 should take 12 echo from m1 only, got hp={m3.hp}"


def test_outbreak_echo_triggers_corpse_explosion():
    """Echo kills during Zombie Rage should trigger Corpse Explosion."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(6)
    engine.player.infection = 0

    # Apply Zombie Rage for Corpse Explosion
    effects.apply_effect(engine.player, engine, "zombie_rage")

    m1 = _spawn_monster(engine, 5, 5, hp=100, max_hp=100, name="Victim")
    m2 = _spawn_monster(engine, 6, 5, hp=1, max_hp=50, name="Weak")  # will die from echo
    m3 = _spawn_monster(engine, 7, 5, hp=200, name="Far")  # should take corpse explosion damage

    effects.apply_effect(m1, engine, "outbreak", silent=True)
    effects.apply_effect(m2, engine, "outbreak", silent=True)

    # Deal 40 damage to m1 → echo 12 to m2 → m2 dies → corpse explosion hits m3
    m1.take_damage(40)

    assert not m2.alive, f"m2 should die from echo damage (hp was 1)"
    assert m3.hp < 200, f"m3 should take corpse explosion damage from m2's death, hp={m3.hp}"


def test_outbreak_too_far():
    """Outbreak fails if center is more than 3 tiles from player."""
    engine = _make_engine()
    skill = engine.skills.get("Infected")
    skill.set_level(6)

    px, py = engine.player.x, engine.player.y
    from abilities import _execute_at_outbreak
    result = _execute_at_outbreak(engine, px + 5, py)
    assert result is False, "Should fail — too far from player"
