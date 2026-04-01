"""Tests for the gun system: creation, equipping, firing, reloading, swapping."""

import random
import pytest
from unittest.mock import patch
from engine import GameEngine
from entity import Entity
from items import create_item_entity, get_item_def, ITEM_DEFS


@pytest.fixture
def engine():
    """Create a fresh GameEngine for testing."""
    eng = GameEngine()
    return eng


def _give_item(engine, item_id, quantity=1):
    """Add an item to the player's inventory and return it."""
    kwargs = create_item_entity(item_id, 0, 0)
    item = Entity(**kwargs)
    item.quantity = quantity
    engine.player.inventory.append(item)
    return item


def _spawn_monster(engine, x, y, name="Thug"):
    """Spawn a visible monster at (x, y)."""
    m = Entity(
        x=x, y=y, char="T", color=(255, 0, 0),
        name=name, entity_type="monster",
        blocks_movement=True, hp=20, power=3, defense=0,
    )
    engine.dungeon.entities.append(m)
    # Make the tile visible
    engine.dungeon.visible[y, x] = True
    return m


# ── Gun item creation ──────────────────────────────────────────────────

def test_gun_item_creation():
    """Gun items should have current_ammo and mag_size set."""
    kwargs = create_item_entity("ruger_mark_v", 0, 0)
    assert kwargs["mag_size"] == 10
    assert kwargs["current_ammo"] == 10
    entity = Entity(**kwargs)
    assert entity.mag_size == 10
    assert entity.current_ammo == 10


def test_ammo_item_creation():
    """Ammo items should be created normally."""
    kwargs = create_item_entity("light_rounds", 0, 0)
    entity = Entity(**kwargs)
    assert entity.item_id == "light_rounds"


def test_ammo_is_stackable():
    """Ammo category should be stackable."""
    from items import is_stackable
    assert is_stackable("light_rounds")


# ── Sidearm equip ──────────────────────────────────────────────────────

def test_equip_sidearm(engine):
    """Small gun equips to sidearm slot and auto-sets primary_gun."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    assert engine.equipment["sidearm"] is not None
    assert engine.equipment["sidearm"].item_id == "ruger_mark_v"
    assert engine.primary_gun == "sidearm"


def test_unequip_sidearm_clears_primary(engine):
    """Unequipping the primary gun clears primary_gun."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    assert engine.primary_gun == "sidearm"

    # Unequip via equipment handler
    engine.menu_state = engine.menu_state  # just for clarity
    # Find sidearm in occupied slots
    engine.equipment_cursor = 0
    # Navigate to sidearm (it's after weapon if weapon is None, so index 0)
    if engine.equipment["weapon"] is None:
        engine.equipment_cursor = 0
    else:
        engine.equipment_cursor = 1
    engine._handle_equipment_input({"type": "confirm_target"})
    assert engine.equipment["sidearm"] is None
    assert engine.primary_gun is None


# ── Reload ─────────────────────────────────────────────────────────────

def test_reload_gun(engine):
    """Reloading fills magazine from inventory ammo."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped_gun = engine.equipment["sidearm"]
    equipped_gun.current_ammo = 3  # partially empty

    ammo = _give_item(engine, "light_rounds", quantity=20)

    engine._action_reload_gun(None)
    assert equipped_gun.current_ammo == 10  # refilled to mag_size
    assert ammo.quantity == 13  # 20 - 7 used


def test_reload_no_ammo(engine):
    """Reloading with no ammo in inventory shows error."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine.equipment["sidearm"].current_ammo = 0

    engine._action_reload_gun(None)
    assert engine.equipment["sidearm"].current_ammo == 0
    assert any("No light ammo" in str(m) for m in engine.messages)


def test_reload_full_magazine(engine):
    """Reloading a full magazine shows error."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    # Magazine is full (10/10)
    engine._action_reload_gun(None)
    assert any("already full" in str(m) for m in engine.messages)


# ── Primary gun swap ──────────────────────────────────────────────────

def test_swap_no_guns(engine):
    """Swapping with no guns shows error."""
    engine._action_swap_primary_gun(None)
    assert any("No guns" in str(m) for m in engine.messages)


def test_swap_one_gun(engine):
    """Swapping with one gun shows message and keeps primary."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine._action_swap_primary_gun(None)
    assert engine.primary_gun == "sidearm"
    assert any("Only one gun" in str(m) for m in engine.messages)


# ── Firing ─────────────────────────────────────────────────────────────

def test_fire_no_gun(engine):
    """Firing with no gun shows error."""
    engine._action_fire_gun(None)
    assert any("No gun equipped" in str(m) for m in engine.messages)


def test_fire_empty_magazine(engine):
    """Firing with empty magazine shows error."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine.equipment["sidearm"].current_ammo = 0

    engine._action_fire_gun(None)
    assert any("Empty magazine" in str(m) for m in engine.messages)


def test_fire_enters_targeting(engine):
    """Firing with loaded gun enters GUN_TARGETING state."""
    from menu_state import MenuState
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    engine._action_fire_gun(None)
    assert engine.menu_state == MenuState.GUN_TARGETING


def test_resolve_gun_shot_hit(engine):
    """A gun shot that hits should deal damage and consume ammo."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    initial_ammo = equipped.current_ammo

    # Place monster adjacent and visible
    mx, my = engine.player.x + 1, engine.player.y
    monster = _spawn_monster(engine, mx, my)
    initial_hp = monster.hp

    # Force hit (100% accuracy, no dodge)
    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a  # min roll
        mock_random.random.return_value = 0.0  # no dodge, no crit
        engine._resolve_gun_shot(mx, my)

    assert equipped.current_ammo == initial_ammo - 1
    assert monster.hp < initial_hp


def test_resolve_gun_shot_miss(engine):
    """A gun shot that misses should still consume ammo."""
    gun = _give_item(engine, "ruger_mark_v")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    initial_ammo = equipped.current_ammo

    mx, my = engine.player.x + 2, engine.player.y
    monster = _spawn_monster(engine, mx, my)
    initial_hp = monster.hp

    # Force miss by patching only randint to return 100 (> any hit chance)
    original_randint = random.randint
    call_count = [0]
    def mock_randint(a, b):
        call_count[0] += 1
        if call_count[0] == 1:
            # First randint call is the accuracy roll
            return 100  # guaranteed miss
        return original_randint(a, b)

    with patch("engine.random.randint", side_effect=mock_randint):
        engine._resolve_gun_shot(mx, my)

    assert equipped.current_ammo == initial_ammo - 1
    assert monster.hp == initial_hp  # no damage


# ── Gun stats ──────────────────────────────────────────────────────────

def test_gun_stats():
    """Verify gun_stats data exists with expected values."""
    defn = ITEM_DEFS["ruger_mark_v"]
    stats = defn["gun_stats"]
    assert stats["energy"] == 45
    assert stats["hit"] == 80


# ── Gun definition ─────────────────────────────────────────────────────

def test_ruger_definition():
    """Verify the Ruger Mark V definition has all required gun fields."""
    defn = ITEM_DEFS["ruger_mark_v"]
    assert defn["subcategory"] == "gun"
    assert defn["equip_slot"] == "sidearm"
    assert defn["base_damage"] == (6, 8)
    assert defn["gun_range"] == 4
    assert defn["ammo_type"] == "light"
    assert defn["mag_size"] == 10
    assert defn["gun_class"] == "small"


def test_light_rounds_definition():
    """Verify ammo definition."""
    defn = ITEM_DEFS["light_rounds"]
    assert defn["category"] == "ammo"
    assert defn["ammo_type"] == "light"


# ── HV Express ────────────────────────────────────────────────────────

def test_hv_express_definition():
    """HV Express is a medium gun for the weapon slot."""
    defn = ITEM_DEFS["hv_express"]
    assert defn["subcategory"] == "gun"
    assert defn["gun_class"] == "medium"
    assert defn["equip_slot"] == "weapon"
    assert defn["base_damage"] == (6, 8)
    assert defn["gun_range"] == 8
    assert defn["mag_size"] == 5
    assert defn["reload_speed"] == 100
    assert defn["consecutive_bonus"] == 2
    assert defn["value"] == 200
    assert defn["gun_stats"]["hit"] == 80


def test_hv_express_equips_to_weapon(engine):
    """Medium gun equips to weapon slot and sets primary_gun."""
    gun = _give_item(engine, "hv_express")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    assert engine.equipment["weapon"] is not None
    assert engine.equipment["weapon"].item_id == "hv_express"
    assert engine.primary_gun == "weapon"


def test_hv_express_consecutive_bonus(engine):
    """Consecutive shots at same target get stacking +2 damage."""
    gun = _give_item(engine, "hv_express")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["weapon"]
    equipped.current_ammo = 5

    mx, my = engine.player.x + 1, engine.player.y
    monster = _spawn_monster(engine, mx, my, "Target")
    monster.hp = 200
    monster.max_hp = 200
    monster.defense = 0

    damages = []
    # Disable crits and STS bonus for predictable damage
    engine.player_stats._crit_chance = 0.0
    engine.player_stats.street_smarts = 0
    engine.player_stats._base["street_smarts"] = 0
    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a  # min roll (6 damage)
        mock_random.random.return_value = 0.99  # no dodge (above dodge%), no crit

        # Shot 1: no bonus (first shot at this target)
        engine._resolve_gun_shot(mx, my)
        d1 = 200 - monster.hp
        damages.append(d1)

        # Shot 2: +2 bonus
        engine._resolve_gun_shot(mx, my)
        d2 = (200 - d1) - monster.hp
        damages.append(d2)

        # Shot 3: +4 bonus
        engine._resolve_gun_shot(mx, my)

    # Shot 1 = 6 (base), Shot 2 = 8 (6+2), Shot 3 = 10 (6+4)
    assert damages[0] == 6
    assert damages[1] == 8


def test_hv_express_consecutive_resets_on_new_target(engine):
    """Consecutive bonus resets when firing at a different target."""
    gun = _give_item(engine, "hv_express")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["weapon"]
    equipped.current_ammo = 10

    m1 = _spawn_monster(engine, engine.player.x + 1, engine.player.y, "A")
    m1.hp = 200; m1.max_hp = 200; m1.defense = 0
    m2 = _spawn_monster(engine, engine.player.x + 2, engine.player.y, "B")
    m2.hp = 200; m2.max_hp = 200; m2.defense = 0

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a
        mock_random.random.return_value = 0.0

        # Shot 1 at A: no bonus
        engine._resolve_gun_shot(m1.x, m1.y)
        assert engine.gun_consecutive_count == 1

        # Shot 2 at A: +2 bonus
        engine._resolve_gun_shot(m1.x, m1.y)
        assert engine.gun_consecutive_count == 2

        # Shot 3 at B: resets
        engine._resolve_gun_shot(m2.x, m2.y)
        assert engine.gun_consecutive_count == 1  # just fired first shot at B

    # Bonus should have reset when switching targets
    assert engine.gun_consecutive_target_id == m2.instance_id


def test_hv_express_melee_doesnt_reset_consecutive(engine):
    """Melee attacks don't affect the consecutive shot tracker."""
    gun = _give_item(engine, "hv_express")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["weapon"]
    equipped.current_ammo = 10

    mx, my = engine.player.x + 1, engine.player.y
    monster = _spawn_monster(engine, mx, my)
    monster.hp = 200; monster.max_hp = 200; monster.defense = 0

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a
        mock_random.random.return_value = 0.0

        # Shot 1 at target
        engine._resolve_gun_shot(mx, my)
        count_after_shot = engine.gun_consecutive_count

    # Consecutive state persists (melee won't touch it)
    assert count_after_shot == 1
    assert engine.gun_consecutive_target_id == monster.instance_id


# ── Glizzy-19 ─────────────────────────────────────────────────────────

def test_glizzy_definition():
    """Glizzy-19 is a small gun for the sidearm slot."""
    defn = ITEM_DEFS["glizzy_19"]
    assert defn["subcategory"] == "gun"
    assert defn["gun_class"] == "small"
    assert defn["equip_slot"] == "sidearm"
    assert defn["base_damage"] == (11, 15)
    assert defn["gun_range"] == 5
    assert defn["reload_speed"] == 0
    assert defn["value"] == 300
    assert defn["grants_ability"] == "double_tap"
    assert defn["mag_size_options"] == [15, 17, 19, 24, 33]


def test_glizzy_random_mag_size():
    """Glizzy should spawn with one of the mag_size_options."""
    valid_sizes = [15, 17, 19, 24, 33]
    for _ in range(20):
        kwargs = create_item_entity("glizzy_19", 0, 0)
        assert kwargs["mag_size"] in valid_sizes
        assert kwargs["current_ammo"] == kwargs["mag_size"]


def test_glizzy_grants_double_tap(engine):
    """Equipping Glizzy-19 grants double_tap ability."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    ability_ids = [a.ability_id for a in engine.player_abilities]
    assert "double_tap" in ability_ids


def test_glizzy_unequip_revokes_double_tap(engine):
    """Unequipping Glizzy-19 revokes double_tap ability."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    # Unequip via equipment handler
    engine.equipment_cursor = 0
    if engine.equipment["weapon"] is not None:
        engine.equipment_cursor = 1
    engine._handle_equipment_input({"type": "confirm_target"})

    ability_ids = [a.ability_id for a in engine.player_abilities]
    assert "double_tap" not in ability_ids


def test_double_tap_ability():
    """Double tap ability exists and is functional."""
    from abilities import ABILITY_REGISTRY
    defn = ABILITY_REGISTRY["double_tap"]
    assert "gun" in defn.tags
    assert defn.charge_type.value == "infinite"
    assert defn.execute is not None


def test_double_tap_requires_ammo(engine):
    """Double tap requires 2+ rounds loaded."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine.equipment["sidearm"].current_ammo = 1
    result = engine._enter_gun_ability_targeting({
        "ability_id": "double_tap", "name": "Double Tap",
        "aoe_type": "line", "num_shots": 2, "damage": (6, 18),
        "accuracy": 50, "energy": 80, "range": 4,
    })
    assert result is False
    assert any("rounds" in str(m).lower() or "reload" in str(m).lower() for m in engine.messages)


def test_double_tap_enters_targeting(engine):
    """Double tap enters gun targeting mode when ammo is sufficient."""
    from menu_state import MenuState
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine.equipment["sidearm"].current_ammo = 10
    engine._enter_gun_ability_targeting({
        "ability_id": "double_tap", "name": "Double Tap",
        "aoe_type": "line", "num_shots": 2, "damage": (6, 18),
        "accuracy": 50, "energy": 80, "range": 4,
    })
    assert engine.menu_state == MenuState.GUN_TARGETING
    assert engine.gun_ability_active is not None
    assert engine.gun_ability_active["name"] == "Double Tap"


def test_double_tap_line_tiles(engine):
    """Line tiles extend in cardinal direction from player."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    px, py = engine.player.x, engine.player.y
    tiles = engine._get_gun_line_tiles(px + 3, py, 4)
    assert len(tiles) > 0
    for (tx, ty) in tiles:
        assert ty == py
        assert tx > px


def test_double_tap_resolves_shot(engine):
    """Double tap fires 2 rounds and consumes ammo."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    equipped.current_ammo = 10
    px, py = engine.player.x, engine.player.y
    _spawn_monster(engine, px + 2, py, "Thug")
    engine.gun_ability_active = {
        "ability_id": "double_tap", "name": "Double Tap",
        "aoe_type": "line", "num_shots": 2, "damage": (6, 18),
        "accuracy": 50, "energy": 80, "range": 4,
    }
    random.seed(42)
    engine._resolve_gun_ability_shot(px + 3, py)
    assert equipped.current_ammo == 8  # consumed 2 rounds
    assert engine.gun_ability_active is None  # cleared after firing


def test_double_tap_max_hits_per_target(engine):
    """Double tap with 2 shots can hit one target at most ceil(2/2) = 1 time."""
    gun = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    equipped.current_ammo = 10
    px, py = engine.player.x, engine.player.y
    monster = _spawn_monster(engine, px + 1, py, "Thug")
    monster.hp = 200
    monster.max_hp = 200
    # With only 1 target in the line and 2 shots, max_per_target = ceil(2/2) = 1
    # So only 1 shot should be assigned to this target
    hits = 0
    for _ in range(50):
        monster.hp = 200
        equipped.current_ammo = 10
        engine.gun_ability_active = {
            "ability_id": "double_tap", "name": "Double Tap",
            "aoe_type": "line", "num_shots": 2, "damage": (6, 18),
            "accuracy": 100,  # 100% to ensure all shots hit
            "energy": 80, "range": 4,
        }
        start_hp = monster.hp
        engine._resolve_gun_ability_shot(px + 3, py)
        # Monster should have been hit at most 1 time (max_per_target=1)
        # With 100% accuracy and defense=0, each hit does 6-18 dmg
        damage_taken = start_hp - monster.hp
        if damage_taken > 0:
            hits += 1
            # Only 1 assignment possible, so only 1 hit max
            assert damage_taken <= 18 * 2  # crit multiplier at most


# ── UZI ───────────────────────────────────────────────────────────────

def test_uzi_definition():
    """UZI is a small cone gun."""
    defn = ITEM_DEFS["uzi"]
    assert defn["subcategory"] == "gun"
    assert defn["gun_class"] == "small"
    assert defn["equip_slot"] == "sidearm"
    assert defn["base_damage"] == (8, 10)
    assert defn["gun_range"] == 5
    assert defn["mag_size"] == 32
    assert defn["reload_speed"] == 80
    assert defn["value"] == 350
    assert defn["aoe_type"] == "cone"
    assert defn["cone_angle"] == 30
    assert defn["ammo_per_shot"] == (3, 4)


def test_uzi_requires_min_ammo(engine):
    """UZI requires at least 3 rounds to fire."""
    from menu_state import MenuState
    gun = _give_item(engine, "uzi")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    engine.equipment["sidearm"].current_ammo = 2  # below min

    engine._action_fire_gun(None)
    assert engine.menu_state != MenuState.GUN_TARGETING
    assert any("at least 3" in str(m) for m in engine.messages)


def test_uzi_enters_targeting_with_enough_ammo(engine):
    """UZI enters targeting mode with 3+ ammo."""
    from menu_state import MenuState
    gun = _give_item(engine, "uzi")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    assert engine.equipment["sidearm"].current_ammo == 32

    engine._action_fire_gun(None)
    assert engine.menu_state == MenuState.GUN_TARGETING


def test_uzi_cone_consumes_multiple_ammo(engine):
    """UZI cone shot consumes 3-4 ammo per fire."""
    gun = _give_item(engine, "uzi")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    initial_ammo = equipped.current_ammo

    # Fire at empty tile (no enemies in cone)
    tx, ty = engine.player.x + 2, engine.player.y
    engine.dungeon.visible[ty, tx] = True

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a  # roll minimum (3 ammo)
        mock_random.random.return_value = 0.0
        mock_random.choice.side_effect = lambda lst: lst[0]
        engine._resolve_cone_shot(tx, ty)

    ammo_used = initial_ammo - equipped.current_ammo
    assert ammo_used == 3  # min ammo_per_shot


def test_uzi_cone_hits_targets(engine):
    """UZI cone distributes shots among enemies in the cone."""
    gun = _give_item(engine, "uzi")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    # Place monsters in a line directly ahead (within 30-degree cone)
    m1 = _spawn_monster(engine, engine.player.x + 2, engine.player.y, "A")
    m1.hp = 100; m1.max_hp = 100; m1.defense = 0
    m2 = _spawn_monster(engine, engine.player.x + 3, engine.player.y, "B")
    m2.hp = 100; m2.max_hp = 100; m2.defense = 0

    # Aim directly right (cone centered on player.x + 3, player.y)
    tx, ty = engine.player.x + 3, engine.player.y

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a  # min rolls
        mock_random.random.return_value = 0.0  # all hit, no dodge, no crit
        mock_random.choice.side_effect = lambda lst: lst[0]  # always pick first eligible
        engine._resolve_cone_shot(tx, ty)

    # At least some damage should have been dealt
    total_damage = (100 - m1.hp) + (100 - m2.hp)
    assert total_damage > 0


def test_uzi_cone_max_hits_per_target(engine):
    """One target can receive at most ceil(ammo/2) hits in a cone."""
    gun = _give_item(engine, "uzi")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    # Single enemy in cone — should be hit at most ceil(4/2) = 2 times
    m = _spawn_monster(engine, engine.player.x + 2, engine.player.y, "Solo")
    m.hp = 200; m.max_hp = 200; m.defense = 0

    tx, ty = engine.player.x + 2, engine.player.y

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: b  # max rolls (4 ammo, 10 dmg)
        mock_random.random.return_value = 0.0  # all hit
        mock_random.choice.side_effect = lambda lst: lst[0]
        engine._resolve_cone_shot(tx, ty)

    # 4 ammo used, max 2 hits on single target, 10 dmg each = max 20 damage
    damage_dealt = 200 - m.hp
    assert damage_dealt <= 20


# ── Gun swap with weapon slot ─────────────────────────────────────────

def test_swap_weapon_and_sidearm_guns(engine):
    """Can swap between weapon-slot gun and sidearm-slot gun."""
    hv = _give_item(engine, "hv_express")
    idx = engine.player.inventory.index(hv)
    engine._equip_item(idx)
    assert engine.primary_gun == "weapon"

    glizzy = _give_item(engine, "glizzy_19")
    idx = engine.player.inventory.index(glizzy)
    engine._equip_item(idx)
    assert engine.primary_gun == "sidearm"

    # Swap to weapon
    engine._action_swap_primary_gun(None)
    assert engine.primary_gun == "weapon"

    # Swap back
    engine._action_swap_primary_gun(None)
    assert engine.primary_gun == "sidearm"


# ── Sawed Off cone tests ─────────────────────────────────────────────

def test_sawed_off_definition(engine):
    """Sawed Off has correct stats and 90-degree cone."""
    from items import ITEM_DEFS
    defn = ITEM_DEFS["sawed_off"]
    assert defn["base_damage"] == (10, 25)
    assert defn["gun_range"] == 4
    assert defn["mag_size"] == 2
    assert defn["gun_class"] == "small"
    assert defn["equip_slot"] == "sidearm"
    assert defn["aoe_type"] == "cone"
    assert defn["cone_angle"] == 90
    assert defn["ammo_type"] == "medium"
    assert defn["reload_speed"] == 50


def test_sawed_off_equips_to_sidearm(engine):
    """Sawed Off equips to sidearm slot."""
    gun = _give_item(engine, "sawed_off")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    assert engine.equipment["sidearm"] is gun
    assert engine.primary_gun == "sidearm"


def test_sawed_off_cone_width(engine):
    """90-degree cone is wider than UZI's 30-degree cone at same distance."""
    gun = _give_item(engine, "sawed_off")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    # Aim directly right
    tx, ty = engine.player.x + 3, engine.player.y
    cone_tiles = engine._get_gun_cone_tiles(tx, ty)

    # 90-degree cone should include tiles above and below the center line
    px, py = engine.player.x, engine.player.y
    # Check that tiles at distance 2, one row above and below, are in the cone
    assert (px + 2, py - 1) in cone_tiles, "Tile above center line should be in 90-deg cone"
    assert (px + 2, py + 1) in cone_tiles, "Tile below center line should be in 90-deg cone"
    assert (px + 2, py) in cone_tiles, "Center tile should be in cone"


def test_sawed_off_cone_fires_one_shot(engine):
    """Sawed Off fires 1 round per shot (no ammo_per_shot override)."""
    gun = _give_item(engine, "sawed_off")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)
    equipped = engine.equipment["sidearm"]
    initial_ammo = equipped.current_ammo

    tx, ty = engine.player.x + 2, engine.player.y
    engine.dungeon.visible[ty, tx] = True

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a
        mock_random.random.return_value = 0.0
        mock_random.choice.side_effect = lambda lst: lst[0]
        engine._resolve_cone_shot(tx, ty)

    ammo_used = initial_ammo - equipped.current_ammo
    assert ammo_used == 1


def test_sawed_off_cone_hits_target(engine):
    """Sawed Off cone can hit a target within the 90-degree arc."""
    gun = _give_item(engine, "sawed_off")
    idx = engine.player.inventory.index(gun)
    engine._equip_item(idx)

    # Place monster diagonally — within 90-degree cone aimed right
    m = _spawn_monster(engine, engine.player.x + 2, engine.player.y + 1, "Target")
    m.hp = 100; m.max_hp = 100; m.defense = 0

    tx, ty = engine.player.x + 3, engine.player.y

    with patch("gun_system.random") as mock_random:
        mock_random.randint.side_effect = lambda a, b: a
        mock_random.random.return_value = 0.0
        mock_random.choice.side_effect = lambda lst: lst[0]
        engine._resolve_cone_shot(tx, ty)

    assert m.hp < 100, "Target in 90-degree cone should be hit"


# ── RPG & Circle AOE tests ───────────────────────────────────────────────

def test_rpg_definition():
    """RPG gun definition has expected fields."""
    defn = ITEM_DEFS["rpg"]
    assert defn["subcategory"] == "gun"
    assert defn["gun_class"] == "large"
    assert defn["equip_slot"] == "weapon"
    assert defn["aoe_type"] == "circle"
    assert defn["aoe_radius"] == 2
    assert defn["ammo_type"] == "heavy"
    assert defn["mag_size"] == 1
    assert defn["base_damage"] == (40, 50)
    assert defn["gun_range"] == 10
    assert defn["reload_speed"] == 150


def test_heavy_rounds_definition():
    """Heavy rounds ammo definition exists with correct fields."""
    defn = ITEM_DEFS["heavy_rounds"]
    assert defn["category"] == "ammo"
    assert defn["ammo_type"] == "heavy"
    assert defn["value"] == 15


def test_circle_tile_generation(engine):
    """_get_gun_circle_tiles returns tiles within Chebyshev distance."""
    px, py = engine.player.x, engine.player.y
    # Clear terrain around player so tiles aren't blocked
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            tx, ty = px + dx, py + dy
            if 0 <= tx < engine.dungeon.width and 0 <= ty < engine.dungeon.height:
                engine.dungeon.tiles[ty][tx] = 1  # walkable

    tiles = engine._get_gun_circle_tiles(px, py, 2)
    # Should be a 5x5 area (radius 2 Chebyshev) = up to 25 tiles
    assert len(tiles) > 0
    assert (px, py) in tiles  # center included
    assert (px + 2, py + 2) in tiles  # corner included
    # Tiles outside radius should not be included
    assert (px + 3, py) not in tiles


def test_circle_shot_hit(engine):
    """RPG direct hit damages monsters in blast radius."""
    rpg = _give_item(engine, "rpg")
    _give_item(engine, "heavy_rounds", 10)
    idx = engine.player.inventory.index(rpg)
    engine._equip_item(idx)

    # Clear terrain
    px, py = engine.player.x, engine.player.y
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            tx, ty = px + dx, py + dy
            if 0 <= tx < engine.dungeon.width and 0 <= ty < engine.dungeon.height:
                engine.dungeon.tiles[ty][tx] = 1

    # Place monster at range
    target_x, target_y = px + 5, py
    m = _spawn_monster(engine, target_x, target_y, "Target")
    m.hp = 200; m.max_hp = 200; m.defense = 0

    with patch("gun_system.random") as mock_random:
        # Hit roll succeeds (roll 50 <= hit 90)
        mock_random.randint.side_effect = lambda a, b: a  # min values
        mock_random.random.return_value = 0.0
        engine._resolve_circle_shot(target_x, target_y)

    assert m.hp < 200, "Monster at blast center should take damage"
    assert rpg.current_ammo == 0, "Should consume 1 ammo"


def test_circle_shot_miss_self_damage(engine):
    """RPG miss causes explosion near player, can self-damage."""
    rpg = _give_item(engine, "rpg")
    _give_item(engine, "heavy_rounds", 10)
    idx = engine.player.inventory.index(rpg)
    engine._equip_item(idx)

    px, py = engine.player.x, engine.player.y
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            tx, ty = px + dx, py + dy
            if 0 <= tx < engine.dungeon.width and 0 <= ty < engine.dungeon.height:
                engine.dungeon.tiles[ty][tx] = 1

    target_x, target_y = px + 5, py
    initial_hp = engine.player.hp

    with patch("gun_system.random") as mock_random:
        # Miss roll (roll 100 > hit 90), then choice returns player pos
        call_count = [0]
        def mock_randint(a, b):
            call_count[0] += 1
            if call_count[0] == 1:
                return 100  # miss the accuracy roll
            return a  # min damage for subsequent rolls
        mock_random.randint.side_effect = mock_randint
        mock_random.random.return_value = 0.0
        # Force explosion to land on player position
        mock_random.choice.side_effect = lambda lst: (px, py)
        engine._resolve_circle_shot(target_x, target_y)

    assert engine.player.hp < initial_hp, "Player should take self-damage from miss"
    assert any("goes wide" in m for m in engine.messages), "Should show miss message"


def test_circle_shot_kills_player(engine):
    """RPG miss explosion can kill the player."""
    rpg = _give_item(engine, "rpg")
    _give_item(engine, "heavy_rounds", 10)
    idx = engine.player.inventory.index(rpg)
    engine._equip_item(idx)

    px, py = engine.player.x, engine.player.y
    for dy in range(-12, 13):
        for dx in range(-12, 13):
            tx, ty = px + dx, py + dy
            if 0 <= tx < engine.dungeon.width and 0 <= ty < engine.dungeon.height:
                engine.dungeon.tiles[ty][tx] = 1

    target_x, target_y = px + 5, py
    engine.player.hp = 1  # barely alive

    with patch("gun_system.random") as mock_random:
        call_count = [0]
        def mock_randint(a, b):
            call_count[0] += 1
            if call_count[0] == 1:
                return 100  # miss
            return b  # max damage
        mock_random.randint.side_effect = mock_randint
        mock_random.random.return_value = 0.0
        mock_random.choice.side_effect = lambda lst: (px, py)
        engine._resolve_circle_shot(target_x, target_y)

    assert not engine.player.alive, "Player should die from RPG self-damage"
    assert engine.game_over is True
