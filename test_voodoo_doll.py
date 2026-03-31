"""Tests for Voodoo Doll curse detonation system.

Covers all three curse detonation types, multi-curse, range checks,
zero-stack edge cases, and the Voodoo Ham Stun break mechanic.
"""

import random
import pytest
from unittest.mock import patch
from engine import GameEngine
from entity import Entity
from effects import apply_effect
from item_effects import _voodoo_detonate, _detonate_ham, _detonate_dot, _detonate_covid


def _make_engine(seed="VOODOO1"):
    e = GameEngine(seed=seed)
    e.sdl_overlay = None
    return e


def _make_monster(engine, x, y, name="TestMob", hp=100):
    m = Entity(
        x=x, y=y, char="M", color=(255, 0, 0), name=name,
        entity_type="monster", blocks_movement=True, hp=hp, power=5, defense=0,
    )
    m.max_hp = hp
    m.speed = 80
    m.energy = 0
    m.status_effects = []
    m.toxicity = 0
    m.radiation = 0
    m.ai_type = "meander"
    m.sight_radius = 6
    m.enemy_type = "test_mob"
    engine.dungeon.entities.append(m)
    return m


class TestVoodooDetonateNoCurses:
    def test_no_cursed_enemies_message(self):
        engine = _make_engine()
        _make_monster(engine, engine.player.x + 2, engine.player.y)
        _voodoo_detonate(engine)
        msgs = [str(m) for m in engine.messages]
        assert any("no cursed enemies" in m.lower() for m in msgs)

    def test_no_monsters_at_all(self):
        engine = _make_engine()
        _voodoo_detonate(engine)
        msgs = [str(m) for m in engine.messages]
        assert any("no cursed enemies" in m.lower() for m in msgs)


class TestVoodooHamDetonation:
    def test_ham_curse_removed_and_stun_applied(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "curse_of_ham", silent=True)
        ham = next(e for e in m.status_effects if e.id == "curse_of_ham")
        ham.stacks = 5

        _voodoo_detonate(engine)

        assert not any(e.id == "curse_of_ham" for e in m.status_effects)
        stun = next((e for e in m.status_effects if e.id == "voodoo_ham_stun"), None)
        assert stun is not None
        assert stun.duration == 5

    def test_ham_zero_stacks_gives_1_turn_stun(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "curse_of_ham", silent=True)
        ham = next(e for e in m.status_effects if e.id == "curse_of_ham")
        ham.stacks = 0

        _voodoo_detonate(engine)

        stun = next(e for e in m.status_effects if e.id == "voodoo_ham_stun")
        assert stun.duration == 1

    def test_ham_stun_blocks_energy(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "voodoo_ham_stun", duration=5, silent=True)
        stun = next(e for e in m.status_effects if e.id == "voodoo_ham_stun")
        assert stun.modify_energy_gain(80.0, m) == 0.0
        assert stun.before_turn(m, engine.player, engine.dungeon) is True


class TestVoodooHamStunBreak:
    def test_stun_breaks_on_player_hit_20_percent(self):
        """With random seeded to always succeed (< 0.20), stun should break."""
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "voodoo_ham_stun", duration=10, silent=True)

        # Simulate combat.py check with forced random < 0.20
        with patch('combat.random.random', return_value=0.10):
            from combat import handle_attack
            handle_attack(engine, engine.player, m)

        assert not any(e.id == "voodoo_ham_stun" for e in m.status_effects)

    def test_stun_survives_when_roll_fails(self):
        """With random > 0.20, stun should remain."""
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "voodoo_ham_stun", duration=10, silent=True)

        with patch('combat.random.random', return_value=0.99):
            from combat import handle_attack
            handle_attack(engine, engine.player, m)

        assert any(e.id == "voodoo_ham_stun" for e in m.status_effects)

    def test_stun_not_broken_by_dot_damage(self):
        """Non-player damage (DOT) should not trigger the 20% break."""
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "voodoo_ham_stun", duration=10, silent=True)

        # Direct damage (not from player melee)
        m.take_damage(10)

        assert any(e.id == "voodoo_ham_stun" for e in m.status_effects)


class TestVoodooDotDetonation:
    def test_dot_deals_correct_aoe_damage(self):
        engine = _make_engine()
        cx, cy = engine.player.x + 3, engine.player.y
        m1 = _make_monster(engine, cx, cy, name="CursedMob", hp=200)
        m2 = _make_monster(engine, cx + 1, cy, name="NearbyMob", hp=200)

        apply_effect(m1, engine, "curse_dot", stacks=10, silent=True)
        dot = next(e for e in m1.status_effects if e.id == "curse_dot")
        dot.stacks = 10

        _voodoo_detonate(engine)

        # 2 * 10 = 20 damage to both monsters (m2 is in 5x5 of m1)
        assert m1.hp == 180
        assert m2.hp == 180

    def test_dot_no_player_damage(self):
        engine = _make_engine()
        # Place monster adjacent to player so player is in 5x5 AOE
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "curse_dot", stacks=10, silent=True)
        dot = next(e for e in m.status_effects if e.id == "curse_dot")
        dot.stacks = 10

        hp_before = engine.player.hp
        _voodoo_detonate(engine)
        assert engine.player.hp == hp_before

    def test_dot_no_curse_spread_on_kill(self):
        engine = _make_engine()
        cx, cy = engine.player.x + 3, engine.player.y
        m1 = _make_monster(engine, cx, cy, name="CursedMob", hp=5)
        m2 = _make_monster(engine, cx + 1, cy, name="NearbyMob", hp=200)

        apply_effect(m1, engine, "curse_dot", stacks=10, silent=True)
        dot = next(e for e in m1.status_effects if e.id == "curse_dot")
        dot.stacks = 10

        _voodoo_detonate(engine)

        # m1 should be dead, m2 should NOT have curse_dot
        assert not m1.alive
        assert not any(e.id == "curse_dot" for e in m2.status_effects)

    def test_dot_zero_stacks_minimum_damage(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y, hp=100)
        apply_effect(m, engine, "curse_dot", stacks=0, silent=True)

        _voodoo_detonate(engine)

        assert m.hp == 99  # max(1, 2*0) = 1 damage


class TestVoodooCovidDetonation:
    def test_covid_doubles_tox_and_rad(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        m.toxicity = 50
        m.radiation = 60
        apply_effect(m, engine, "curse_covid", stacks=5, silent=True)

        _voodoo_detonate(engine)

        # Tox doubled: 50 -> 100, Rad doubled then consumed by mutations
        assert m.toxicity == 100
        # Rad was 120, mutations consume 20 each, so rad should be reduced
        assert m.radiation < 120

    def test_covid_forces_mutations(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y, hp=500)
        m.toxicity = 0
        m.radiation = 100
        apply_effect(m, engine, "curse_covid", stacks=3, silent=True)

        _voodoo_detonate(engine)

        # Rad doubled to 200, mutations consume 20 each = 10 mutations max
        # Rad should be at 0
        assert m.radiation == 0

    def test_covid_zero_rad_tox_still_detonates(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        m.toxicity = 0
        m.radiation = 0
        apply_effect(m, engine, "curse_covid", stacks=2, silent=True)

        _voodoo_detonate(engine)

        # Curse removed, tox/rad stay 0, no mutations
        assert not any(e.id == "curse_covid" for e in m.status_effects)
        assert m.toxicity == 0
        assert m.radiation == 0


class TestVoodooMultiCurse:
    def test_multiple_curses_all_detonate(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y, hp=500)
        m.radiation = 0
        m.toxicity = 0
        # Apply multiple curses (curse_dot and curse_of_ham can coexist
        # since only curse_of_ham has is_curse=True)
        apply_effect(m, engine, "curse_of_ham", silent=True)
        apply_effect(m, engine, "curse_dot", stacks=5, silent=True)
        ham = next(e for e in m.status_effects if e.id == "curse_of_ham")
        ham.stacks = 3
        dot = next(e for e in m.status_effects if e.id == "curse_dot")
        dot.stacks = 5

        _voodoo_detonate(engine)

        # Both curses should be gone
        assert not any(e.id == "curse_of_ham" for e in m.status_effects)
        assert not any(e.id == "curse_dot" for e in m.status_effects)
        # Ham → stun applied
        assert any(e.id == "voodoo_ham_stun" for e in m.status_effects)
        # DOT → damage dealt (2*5=10)
        assert m.hp == 490


class TestVoodooRange:
    def test_enemy_at_8_tiles_is_detonated(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 8, engine.player.y)
        apply_effect(m, engine, "curse_of_ham", silent=True)
        ham = next(e for e in m.status_effects if e.id == "curse_of_ham")
        ham.stacks = 2

        _voodoo_detonate(engine)

        assert not any(e.id == "curse_of_ham" for e in m.status_effects)
        assert any(e.id == "voodoo_ham_stun" for e in m.status_effects)

    def test_enemy_at_9_tiles_not_detonated(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 9, engine.player.y)
        apply_effect(m, engine, "curse_of_ham", silent=True)

        _voodoo_detonate(engine)

        # Curse should still be on the monster
        assert any(e.id == "curse_of_ham" for e in m.status_effects)


class TestVoodooXP:
    def test_detonation_awards_blackkk_magic_xp(self):
        engine = _make_engine()
        m = _make_monster(engine, engine.player.x + 1, engine.player.y)
        apply_effect(m, engine, "curse_of_ham", silent=True)
        ham = next(e for e in m.status_effects if e.id == "curse_of_ham")
        ham.stacks = 1

        skill = engine.skills.get("Blackkk Magic")
        xp_before = skill.potential_exp

        _voodoo_detonate(engine)

        assert skill.potential_exp > xp_before
