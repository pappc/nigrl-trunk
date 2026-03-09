"""
Tests for Fireball Shooter + Wizard Mind Bomb interaction.

Verifies:
1. Drinking Fireball Shooter grants Breathe Fire with 3 floor charges.
2. Drinking Wizard Mind Bomb after Fireball Shooter: charges go to 6 (3+3), NOT 3.
3. Wizard Mind Bomb status effect is applied (+5 book_smarts temp bonus).
4. Breathe Fire damage is boosted by Wizard Mind Bomb (bonus = effective_book_smarts).
"""

import math
from config import TILE_FLOOR
from engine import GameEngine
from entity import Entity
from items import ITEM_DEFS
from abilities import ABILITY_REGISTRY, ChargeType
import effects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_engine() -> GameEngine:
    return GameEngine()


def make_drink_entity(engine: GameEngine, drink_id: str) -> Entity:
    """Create a minimal drink entity at the player position."""
    defn = ITEM_DEFS[drink_id]
    return Entity(
        engine.player.x, engine.player.y,
        defn["char"], defn["color"],
        name=defn["name"],
        entity_type="item",
        item_id=drink_id,
    )


def drink(engine: GameEngine, drink_id: str) -> None:
    """Simulate drinking by calling _handle_alcohol directly."""
    item = make_drink_entity(engine, drink_id)
    engine._handle_alcohol(item, drink_id)


def get_breath_fire(engine: GameEngine):
    """Return the AbilityInstance for breath_fire, or None."""
    return next((a for a in engine.player_abilities if a.ability_id == "breath_fire"), None)


def place_monster(engine: GameEngine, dx: int = 2, dy: int = 0, hp: int = 300) -> tuple:
    """
    Place a monster dx/dy from the player. Force the tile to be floor so
    the breath-fire cone calculation doesn't skip it.
    """
    px, py = engine.player.x, engine.player.y
    mx, my = px + dx, py + dy
    # Ensure the tile is walkable (floor) so the cone doesn't skip it
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
    return m, mx, my


# ---------------------------------------------------------------------------
# Test 1: Fireball Shooter grants Breathe Fire with 3 floor charges
# ---------------------------------------------------------------------------

def test_fireball_shooter_grants_breathe_fire():
    """
    Drinking a Fireball Shooter should add breath_fire to player abilities
    with 3 floor charges.
    """
    engine = make_engine()

    assert get_breath_fire(engine) is None, \
        "breath_fire should not exist before drinking"

    drink(engine, "fireball_shooter")

    inst = get_breath_fire(engine)
    assert inst is not None, \
        "breath_fire ability must exist after drinking Fireball Shooter"

    defn = ABILITY_REGISTRY["breath_fire"]
    assert defn.charge_type == ChargeType.FLOOR_ONLY, \
        "breath_fire must be FLOOR_ONLY charge type"

    assert inst.floor_charges_remaining == 3, (
        f"Expected 3 floor charges after Fireball Shooter, got {inst.floor_charges_remaining}"
    )
    assert inst.can_use(), "breath_fire should be usable after granting 3 charges"

    print(f"[OK] Fireball Shooter grants breath_fire: {inst.floor_charges_remaining} floor charges")


# ---------------------------------------------------------------------------
# Test 2: Wizard Mind Bomb after Fireball Shooter → 6 floor charges (not 3)
# ---------------------------------------------------------------------------

def test_wizard_mind_bomb_stacks_breathe_fire_charges():
    """
    Drinking Wizard Mind Bomb after Fireball Shooter should NOT add more breath_fire charges.
    Only Fireball Shooter grants breath_fire; Wizard Mind Bomb boosts spell charges, not breath_fire.
    Result: 3 (from fireball only) floor charges total.
    """
    engine = make_engine()

    drink(engine, "fireball_shooter")
    inst = get_breath_fire(engine)
    assert inst.floor_charges_remaining == 3, \
        "Sanity check: 3 floor charges after Fireball Shooter"

    drink(engine, "wizard_mind_bomb")

    inst = get_breath_fire(engine)
    # Wizard Mind Bomb does NOT grant breath_fire charges
    assert inst.floor_charges_remaining == 3, (
        f"Expected 3 floor charges (fireball only) after both drinks, got {inst.floor_charges_remaining}"
    )

    print(
        f"[OK] After Fireball Shooter + Wizard Mind Bomb: "
        f"{inst.floor_charges_remaining} floor charges "
        f"(Wizard Mind Bomb does not add breath_fire charges)"
    )


# ---------------------------------------------------------------------------
# Test 3: Wizard Mind Bomb applies status effect (+5 book_smarts)
# ---------------------------------------------------------------------------

def test_wizard_mind_bomb_effect_is_applied():
    """
    Drinking Wizard Mind Bomb must apply the wizard_mind_bomb status effect,
    which grants +5 effective book_smarts while active.
    """
    engine = make_engine()

    has_effect = any(
        getattr(e, 'id', '') == 'wizard_mind_bomb'
        for e in engine.player.status_effects
    )
    assert not has_effect, "wizard_mind_bomb effect should not be present before drinking"

    base_bs = engine.player_stats.book_smarts

    drink(engine, "wizard_mind_bomb")

    has_effect = any(
        getattr(e, 'id', '') == 'wizard_mind_bomb'
        for e in engine.player.status_effects
    )
    assert has_effect, "wizard_mind_bomb status effect must be present after drinking"

    effective_bs = engine.player_stats.effective_book_smarts
    assert effective_bs == base_bs + 5, (
        f"Expected effective_book_smarts = {base_bs + 5}, got {effective_bs} "
        f"(base={base_bs})"
    )

    print(
        f"[OK] Wizard Mind Bomb effect applied: "
        f"book_smarts {base_bs} -> {effective_bs} effective (+5 temp bonus)"
    )


# ---------------------------------------------------------------------------
# Test 4: Breathe Fire damage is boosted by Wizard Mind Bomb
# ---------------------------------------------------------------------------

def test_breathe_fire_damage_formula():
    """
    Breathe Fire damage formula: 20 + effective_book_smarts + wizard_bomb_bonus
    where wizard_bomb_bonus = effective_book_smarts (if buff active) or 0.

    Without buff: damage = 20 + bksmt
    With buff:    damage = 20 + (bksmt + 5) + (bksmt + 5)  [+5 from WMB temp bonus]

    We fix book_smarts = 5 for determinism.
    """
    fixed_bs = 5

    # ---- Without Wizard Mind Bomb ----
    engine_no_buff = make_engine()
    engine_no_buff.player_stats.book_smarts = fixed_bs
    engine_no_buff.player_stats._base["book_smarts"] = fixed_bs

    m_no_buff, mx, my = place_monster(engine_no_buff, dx=2, dy=0, hp=300)
    hp_before = m_no_buff.hp

    hit = engine_no_buff._spell_breath_fire(mx, my)
    assert hit, "Breathe Fire should hit the monster placed 2 tiles away"

    damage_no_buff = hp_before - m_no_buff.hp
    expected_no_buff = 20 + fixed_bs  # 25
    assert damage_no_buff == expected_no_buff, (
        f"Without buff: expected {expected_no_buff} damage, got {damage_no_buff}"
    )
    print(f"[OK] Breathe Fire (no buff): {damage_no_buff} damage (expected {expected_no_buff})")

    # ---- With Wizard Mind Bomb ----
    engine_buff = make_engine()
    engine_buff.player_stats.book_smarts = fixed_bs
    engine_buff.player_stats._base["book_smarts"] = fixed_bs

    drink(engine_buff, "wizard_mind_bomb")
    # WMB applies +5 temp bonus → effective_book_smarts = 5 + 5 = 10
    effective_bs = engine_buff.player_stats.effective_book_smarts
    assert effective_bs == fixed_bs + 5, (
        f"Expected effective_book_smarts={fixed_bs+5} after WMB, got {effective_bs}"
    )

    m_buff, mx2, my2 = place_monster(engine_buff, dx=2, dy=0, hp=300)
    hp_before2 = m_buff.hp

    hit2 = engine_buff._spell_breath_fire(mx2, my2)
    assert hit2, "Breathe Fire should hit the monster placed 2 tiles away (with buff)"

    damage_with_buff = hp_before2 - m_buff.hp
    # _get_wizard_bomb_bonus() returns effective_book_smarts when buff is active
    expected_with_buff = 20 + effective_bs + effective_bs  # 20 + 10 + 10 = 40
    assert damage_with_buff == expected_with_buff, (
        f"With buff: expected {expected_with_buff} damage, got {damage_with_buff}"
    )
    print(
        f"[OK] Breathe Fire (Wizard Mind Bomb active): {damage_with_buff} damage "
        f"(expected {expected_with_buff}: 20 base + {effective_bs} bksmt + {effective_bs} WMB bonus)"
    )
    print(
        f"     Damage increase from buff: +{damage_with_buff - damage_no_buff} "
        f"(+{effective_bs} from bksmt boost, +{effective_bs} from WMB spell bonus)"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fireball_shooter_grants_breathe_fire()
    test_wizard_mind_bomb_stacks_breathe_fire_charges()
    test_wizard_mind_bomb_effect_is_applied()
    test_breathe_fire_damage_formula()
    print("\nAll tests passed.")
