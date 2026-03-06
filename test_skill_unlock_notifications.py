"""Test that skill unlock notifications appear when skills are first unlocked."""

from engine import GameEngine
from entity import Entity
from items import create_item_entity


def test_stealing_unlock_notification():
    """Test that Stealing skill shows unlock notification on first item pickup."""
    engine = GameEngine()
    player = engine.player

    # Place item at destination
    dest_x, dest_y = player.x + 1, player.y
    kwargs = create_item_entity('weed_nug', dest_x, dest_y, strain=None)
    item = Entity(**kwargs)
    engine.dungeon.entities.append(item)

    msg_count_before = len(engine.messages)
    engine.handle_move(1, 0)
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check for unlock notification
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert has_unlock, "Stealing skill should show unlock notification on first pickup"
    print("[OK] Stealing skill shows unlock notification on first unlock")


def test_stealing_no_unlock_on_second_pickup():
    """Test that Stealing skill does NOT show unlock notification on second pickup."""
    engine = GameEngine()
    player = engine.player

    # First pickup
    dest_x, dest_y = player.x + 1, player.y
    kwargs = create_item_entity('weed_nug', dest_x, dest_y, strain=None)
    item = Entity(**kwargs)
    engine.dungeon.entities.append(item)
    engine.handle_move(1, 0)

    # Second pickup (same skill already unlocked)
    dest_x, dest_y = player.x + 1, player.y
    kwargs = create_item_entity('grinder', dest_x, dest_y, strain=None)
    item = Entity(**kwargs)
    engine.dungeon.entities.append(item)

    msg_count_before = len(engine.messages)
    engine.handle_move(1, 0)
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check that NO unlock notification appears
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert not has_unlock, "Stealing skill should NOT show unlock notification on second pickup"
    print("[OK] Stealing skill does not show unlock notification on second pickup")


def test_smoking_unlock_notification():
    """Test that Smoking skill shows unlock notification on first use."""
    engine = GameEngine()

    msg_count_before = len(engine.messages)
    engine._gain_smoking_xp('OG Kush')
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check for unlock notification
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert has_unlock, "Smoking skill should show unlock notification on first use"
    print("[OK] Smoking skill shows unlock notification on first unlock")


def test_rolling_unlock_notification():
    """Test that Rolling skill shows unlock notification on first use."""
    engine = GameEngine()

    msg_count_before = len(engine.messages)
    engine._gain_rolling_xp('OG Kush', is_grinding=False)
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check for unlock notification
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert has_unlock, "Rolling skill should show unlock notification on first use"
    print("[OK] Rolling skill shows unlock notification on first unlock")


def test_melee_unlock_notification():
    """Test that melee skills show unlock notification on first use."""
    engine = GameEngine()

    msg_count_before = len(engine.messages)
    engine._gain_melee_xp("Stabbing", 5)
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check for unlock notification
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert has_unlock, "Stabbing skill should show unlock notification on first use"
    print("[OK] Stabbing skill shows unlock notification on first unlock")


def test_dismantling_unlock_notification():
    """Test that Dismantling skill shows unlock notification on first use."""
    engine = GameEngine()

    msg_count_before = len(engine.messages)
    engine._gain_item_skill_xp("Dismantling", "grinder")
    new_msgs = list(engine.messages)[msg_count_before:]

    # Check for unlock notification
    has_unlock = any("[NEW SKILL UNLOCKED]" in str(m) for m in new_msgs)
    assert has_unlock, "Dismantling skill should show unlock notification on first use"
    print("[OK] Dismantling skill shows unlock notification on first unlock")


def test_skill_appears_in_menu_after_unlock():
    """Test that unlocked skill appears in skills menu."""
    engine = GameEngine()

    # Initially no unlocked skills
    assert len(engine.skills.unlocked()) == 0, "No skills should be unlocked initially"

    # Gain Stealing XP
    dest_x, dest_y = engine.player.x + 1, engine.player.y
    kwargs = create_item_entity('weed_nug', dest_x, dest_y, strain=None)
    item = Entity(**kwargs)
    engine.dungeon.entities.append(item)
    engine.handle_move(1, 0)

    # Check that Stealing appears in unlocked list
    unlocked_names = [s.name for s in engine.skills.unlocked()]
    assert "Stealing" in unlocked_names, "Stealing should appear in unlocked skills after first pickup"
    print("[OK] Skill appears in menu after unlock")


if __name__ == "__main__":
    test_stealing_unlock_notification()
    test_stealing_no_unlock_on_second_pickup()
    test_smoking_unlock_notification()
    test_rolling_unlock_notification()
    test_melee_unlock_notification()
    test_dismantling_unlock_notification()
    test_skill_appears_in_menu_after_unlock()
    print("\n[ALL TESTS PASSED]")
