"""Test stealing XP gain from picking up items and abuse prevention."""

from engine import GameEngine
from entity import Entity
from items import get_skill_xp, create_item_entity, ITEM_DEFS


def test_stealing_xp_on_first_pickup():
    """Test that picking up an item for the first time grants Stealing XP."""
    engine = GameEngine()
    player = engine.player

    # Create a weed_nug item and place it at player position
    kwargs = create_item_entity("weed_nug", player.x, player.y, strain=None)
    item_entity = Entity(**kwargs)
    engine.dungeon.entities.append(item_entity)

    initial_xp = engine.skills.get("Stealing").potential_exp

    # Pick up the item directly
    engine._pickup_items_at(player.x, player.y)

    # Verify XP was gained
    final_xp = engine.skills.get("Stealing").potential_exp
    expected_xp = get_skill_xp("weed_nug", "Stealing") * engine.player_stats.xp_multiplier

    assert final_xp > initial_xp, "Stealing XP should increase on first pickup"
    print(f"[OK] First pickup gains XP: {initial_xp} -> {final_xp}")


def test_stealing_xp_prevents_drop_pickup_abuse():
    """Test that picking up the same item instance twice doesn't grant XP again."""
    engine = GameEngine()
    player = engine.player

    # Create an item and place it at player position
    kwargs = create_item_entity("grinder", player.x, player.y, strain=None)
    item_entity = Entity(**kwargs)
    instance_id = item_entity.instance_id
    engine.dungeon.entities.append(item_entity)

    initial_xp = engine.skills.get("Stealing").potential_exp

    # Simulate first pickup by manually triggering it
    engine._pickup_items_at(player.x, player.y)
    first_pickup_xp = engine.skills.get("Stealing").potential_exp

    assert instance_id in engine.picked_up_items, "Item instance should be marked as picked up"
    assert first_pickup_xp > initial_xp, "First pickup should grant XP"

    # Now simulate dropping and re-picking up the item
    # Find the item in inventory and drop it
    grinder = next((item for item in player.inventory if item.item_id == "grinder"), None)
    assert grinder is not None, "Grinder should be in inventory"

    # Drop it (create new entity with same item_id but we'll use the existing entity)
    player.inventory.remove(grinder)
    engine.dungeon.add_entity(grinder)

    # Try to pick it up again
    engine._pickup_items_at(player.x, player.y)
    second_pickup_xp = engine.skills.get("Stealing").potential_exp

    # Verify no XP was gained on second pickup
    assert second_pickup_xp == first_pickup_xp, "Second pickup of same item should NOT grant XP"
    print(f"[OK] Drop/pickup abuse prevented: second pickup grants 0 XP")


def test_different_item_instances_grant_separate_xp():
    """Test that two different instances of the same item each grant XP."""
    engine = GameEngine()
    player = engine.player

    # Create two grinder items
    kwargs1 = create_item_entity("grinder", player.x, player.y, strain=None)
    item1 = Entity(**kwargs1)
    kwargs2 = create_item_entity("grinder", player.x, player.y, strain=None)
    item2 = Entity(**kwargs2)

    engine.dungeon.entities.append(item1)
    engine.dungeon.entities.append(item2)

    initial_xp = engine.skills.get("Stealing").potential_exp
    expected_xp_per_grinder = get_skill_xp("grinder", "Stealing") * engine.player_stats.xp_multiplier

    # Pick up both items (both are at player's tile, picked up in one call)
    engine._pickup_items_at(player.x, player.y)
    xp_after_pickup = engine.skills.get("Stealing").potential_exp

    # Both different instances should have granted XP
    total_xp_gained = xp_after_pickup - initial_xp
    assert total_xp_gained >= expected_xp_per_grinder * 2, (
        f"Two different grinder instances should each grant XP. "
        f"Expected at least {expected_xp_per_grinder * 2}, got {total_xp_gained}"
    )
    print(f"[OK] Different instances grant separate XP: {initial_xp} -> {xp_after_pickup}")


def test_stealing_xp_scales_by_item():
    """Test that different items grant different XP amounts based on value."""
    # Check XP values follow expected scaling (Stealing = 50% of item value)
    weed_nug_xp = get_skill_xp("weed_nug", "Stealing")    # value=15 * 0.5 = 7
    grinder_xp = get_skill_xp("grinder", "Stealing")      # value=75 * 0.5 = 37

    assert grinder_xp > weed_nug_xp, "Grinder should grant more XP than weed_nug"
    assert weed_nug_xp == 8, f"Weed nug XP should be 8, got {weed_nug_xp}"
    print(f"[OK] XP scales by item value: weed_nug={weed_nug_xp}, grinder={grinder_xp}")


if __name__ == "__main__":
    test_stealing_xp_on_first_pickup()
    test_stealing_xp_prevents_drop_pickup_abuse()
    test_different_item_instances_grant_separate_xp()
    test_stealing_xp_scales_by_item()
    print("\n[ALL TESTS PASSED]")
