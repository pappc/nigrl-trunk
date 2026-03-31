"""
Test save/load system round-trip.
"""

import os
import tempfile
from engine import GameEngine
from save_system import save_game, load_game, has_save


def test_save_load_roundtrip():
    """Save a game, load it, and verify critical state matches."""
    # Create a seeded game for reproducibility
    engine = GameEngine(seed="SAVETEST01")

    # Play a few turns to create some state
    engine.process_action({"type": "move", "dx": 1, "dy": 0})
    engine.process_action({"type": "move", "dx": 0, "dy": 1})
    engine.process_action({"type": "wait"})

    # Save to a temp file
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_test_save.json")
    save_game(engine, tmp)
    assert os.path.isfile(tmp), "Save file not created"

    # Check file size is reasonable
    size = os.path.getsize(tmp)
    assert size > 1000, f"Save file too small: {size} bytes"
    print(f"[OK] Save file created: {size:,} bytes")

    # Load
    loaded = load_game(tmp)

    # Verify critical state
    assert loaded.seed == engine.seed, f"Seed mismatch: {loaded.seed} vs {engine.seed}"
    assert loaded.current_floor == engine.current_floor
    assert loaded.turn == engine.turn
    assert loaded.kills == engine.kills
    assert loaded.cash == engine.cash
    assert loaded.player.x == engine.player.x
    assert loaded.player.y == engine.player.y
    assert loaded.player.hp == engine.player.hp
    assert loaded.player.max_hp == engine.player.max_hp
    assert loaded.player.name == engine.player.name
    print("[OK] Player state matches")

    # Stats
    assert loaded.player_stats.constitution == engine.player_stats.constitution
    assert loaded.player_stats.strength == engine.player_stats.strength
    assert loaded.player_stats.swagger == engine.player_stats.swagger
    print("[OK] Player stats match")

    # Skills
    for name in loaded.skills.skills:
        orig = engine.skills.get(name)
        load = loaded.skills.get(name)
        assert load.level == orig.level, f"Skill {name} level mismatch"
        assert abs(load.real_exp - orig.real_exp) < 0.01
        assert abs(load.potential_exp - orig.potential_exp) < 0.01
    print("[OK] Skills match")

    # Dungeon rooms
    assert len(loaded.dungeon.rooms) == len(engine.dungeon.rooms)
    for i, (a, b) in enumerate(zip(loaded.dungeon.rooms, engine.dungeon.rooms)):
        assert (a.x1, a.y1, a.x2, a.y2) == (b.x1, b.y1, b.x2, b.y2), f"Room {i} mismatch"
    print("[OK] Dungeon rooms match")

    # Dungeon entities
    orig_ents = sorted([(e.name, e.x, e.y) for e in engine.dungeon.entities], key=lambda t: (t[1], t[2]))
    load_ents = sorted([(e.name, e.x, e.y) for e in loaded.dungeon.entities], key=lambda t: (t[1], t[2]))
    assert len(orig_ents) == len(load_ents), f"Entity count mismatch: {len(load_ents)} vs {len(orig_ents)}"
    for a, b in zip(orig_ents, load_ents):
        assert a == b, f"Entity mismatch: {a} vs {b}"
    print("[OK] Dungeon entities match")

    # Floor events
    assert loaded.floor_events == engine.floor_events
    print("[OK] Floor events match")

    # Messages preserved
    assert len(loaded.messages) == len(engine.messages)
    print("[OK] Messages preserved")

    # Engine can process actions after load
    loaded.process_action({"type": "wait"})
    assert loaded.turn == engine.turn + 1
    print("[OK] Loaded engine processes actions")

    # Cleanup
    os.unlink(tmp)
    print(f"\nAll save/load tests passed!")


def test_has_save():
    """Test has_save utility."""
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_test_has.json")
    if os.path.exists(tmp):
        os.unlink(tmp)
    assert not has_save(tmp)
    engine = GameEngine(seed="HASTEST001")
    save_game(engine, tmp)
    assert has_save(tmp)
    os.unlink(tmp)
    print("[OK] has_save works correctly")


if __name__ == "__main__":
    test_save_load_roundtrip()
    test_has_save()
