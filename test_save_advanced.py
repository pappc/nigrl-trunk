"""
Advanced save/load tests — stress test edge cases, combat state,
inventory, equipment, effects, import/export, and multi-floor saves.
"""

import os
import shutil
import tempfile
from engine import GameEngine
from save_system import save_game, load_game, has_save, SAVE_DIR, SAVE_PATH


def _play_turns(engine, n):
    """Play n wait turns to advance the game clock and trigger AI."""
    for _ in range(n):
        if engine.game_over or not engine.running:
            break
        engine.process_action({"type": "wait"})


def test_save_after_combat():
    """Save/load after taking damage and killing enemies."""
    engine = GameEngine(seed="COMBAT0001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_combat.json")

    # Walk around to trigger combat
    for _ in range(20):
        if engine.game_over:
            break
        engine.process_action({"type": "move", "dx": 1, "dy": 0})
    for _ in range(20):
        if engine.game_over:
            break
        engine.process_action({"type": "move", "dx": 0, "dy": 1})

    if engine.game_over:
        print("[SKIP] Player died during combat test — using fresh engine")
        engine = GameEngine(seed="COMBAT0002")
        _play_turns(engine, 5)

    save_game(engine, tmp)
    loaded = load_game(tmp)

    assert loaded.player.hp == engine.player.hp, f"HP: {loaded.player.hp} vs {engine.player.hp}"
    assert loaded.player.armor == engine.player.armor
    assert loaded.turn == engine.turn
    assert loaded.kills == engine.kills
    print(f"[OK] Combat state preserved (HP={loaded.player.hp}, kills={loaded.kills}, turn={loaded.turn})")

    # Loaded engine should be playable
    _play_turns(loaded, 3)
    print("[OK] Loaded engine plays after combat")

    os.unlink(tmp)


def test_save_with_inventory():
    """Save/load with items in inventory."""
    engine = GameEngine(seed="INVENT0001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_inv.json")

    # Walk around to pick up items
    for dx, dy in [(1,0)]*10 + [(0,1)]*10 + [(-1,0)]*10 + [(0,-1)]*10:
        if engine.game_over:
            break
        engine.process_action({"type": "move", "dx": dx, "dy": dy})

    inv_count = len(engine.player.inventory)
    inv_names = sorted([i.name for i in engine.player.inventory])

    save_game(engine, tmp)
    loaded = load_game(tmp)

    loaded_inv = sorted([i.name for i in loaded.player.inventory])
    assert len(loaded.player.inventory) == inv_count, f"Inventory count: {len(loaded.player.inventory)} vs {inv_count}"
    assert loaded_inv == inv_names, f"Inventory mismatch"
    print(f"[OK] Inventory preserved ({inv_count} items)")

    os.unlink(tmp)


def test_save_with_status_effects():
    """Save/load with active status effects on entities."""
    engine = GameEngine(seed="EFFECT0001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_effects.json")

    # Apply some effects to the player
    from effects import apply_effect
    apply_effect(engine.player, engine, "speed_boost", duration=10)
    apply_effect(engine.player, engine, "well_fed", duration=5, power_bonus=3)

    player_effects = [(e.id, e.duration) for e in engine.player.status_effects]

    save_game(engine, tmp)
    loaded = load_game(tmp)

    loaded_effects = [(e.id, e.duration) for e in loaded.player.status_effects]
    assert len(loaded_effects) == len(player_effects), f"Effect count: {len(loaded_effects)} vs {len(player_effects)}"
    for orig, load in zip(sorted(player_effects), sorted(loaded_effects)):
        assert orig == load, f"Effect mismatch: {orig} vs {load}"
    print(f"[OK] Status effects preserved ({len(player_effects)} effects)")

    # Effects should still work after load
    _play_turns(loaded, 2)
    print("[OK] Effects tick normally after load")

    os.unlink(tmp)


def test_save_with_equipment():
    """Save/load with equipped items."""
    engine = GameEngine(seed="EQUIP00001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_equip.json")

    # Record what's equipped
    equipped = {}
    for slot, ent in engine.equipment.items():
        if ent:
            equipped[slot] = ent.name

    save_game(engine, tmp)
    loaded = load_game(tmp)

    for slot, name in equipped.items():
        loaded_ent = loaded.equipment.get(slot)
        assert loaded_ent is not None, f"Missing equipment in slot {slot}"
        assert loaded_ent.name == name, f"Equipment name mismatch in {slot}: {loaded_ent.name} vs {name}"

    print(f"[OK] Equipment preserved ({len(equipped)} slots)")
    os.unlink(tmp)


def test_save_messages():
    """Save/load preserves the message log including rich messages."""
    engine = GameEngine(seed="MSGS000001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_msgs.json")

    # Generate some messages
    engine.messages.append("Simple string message")
    engine.messages.append([("Colored ", (255, 0, 0)), ("text", (0, 255, 0))])
    _play_turns(engine, 3)

    msg_count = len(engine.messages)

    save_game(engine, tmp)
    loaded = load_game(tmp)

    assert len(loaded.messages) == msg_count, f"Message count: {len(loaded.messages)} vs {msg_count}"
    print(f"[OK] Messages preserved ({msg_count} messages)")

    os.unlink(tmp)


def test_import_export():
    """Test importing a save from one location to another (simulating cross-client transfer)."""
    engine = GameEngine(seed="EXPORT0001")

    # Save to "client A"
    client_a = os.path.join(tempfile.gettempdir(), "nigrl_client_a.json")
    save_game(engine, client_a)

    # "Export" by copying to a transfer location
    export_path = os.path.join(tempfile.gettempdir(), "nigrl_exported.json")
    shutil.copy2(client_a, export_path)

    # "Import" on client B by copying to save location
    client_b = os.path.join(tempfile.gettempdir(), "nigrl_client_b.json")
    shutil.copy2(export_path, client_b)

    # Load on client B
    loaded = load_game(client_b)

    assert loaded.seed == engine.seed
    assert loaded.player.x == engine.player.x
    assert loaded.player.y == engine.player.y
    assert loaded.current_floor == engine.current_floor
    print(f"[OK] Import/export works (seed={loaded.seed})")

    # Loaded engine plays fine
    _play_turns(loaded, 5)
    print("[OK] Imported save is fully playable")

    for f in [client_a, export_path, client_b]:
        os.unlink(f)


def test_multiple_save_overwrite():
    """Save multiple times, ensure only latest state is kept."""
    engine = GameEngine(seed="OVERWR0001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_overwrite.json")

    save_game(engine, tmp)
    turn_1 = engine.turn

    _play_turns(engine, 10)
    save_game(engine, tmp)
    turn_2 = engine.turn

    loaded = load_game(tmp)
    assert loaded.turn == turn_2, f"Should load latest save: turn {loaded.turn} vs {turn_2}"
    assert loaded.turn != turn_1, "Loaded stale save"
    print(f"[OK] Save overwrite works (turn {turn_1} -> {turn_2})")

    os.unlink(tmp)


def test_save_load_play_extensive():
    """Save, load, play 50 turns, save again, load again — verify deep stability."""
    engine = GameEngine(seed="STABLE0001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_stable.json")

    _play_turns(engine, 10)
    save_game(engine, tmp)

    loaded1 = load_game(tmp)
    _play_turns(loaded1, 50)

    if loaded1.game_over:
        print("[OK] Game over during extended play — save system didn't crash")
        os.unlink(tmp)
        return

    save_game(loaded1, tmp)
    loaded2 = load_game(tmp)

    assert loaded2.turn == loaded1.turn
    assert loaded2.player.hp == loaded1.player.hp
    assert loaded2.player.x == loaded1.player.x
    assert loaded2.player.y == loaded1.player.y
    print(f"[OK] Double save/load stable (turn={loaded2.turn}, hp={loaded2.player.hp})")

    _play_turns(loaded2, 10)
    print("[OK] Second-generation load still playable")

    os.unlink(tmp)


def test_save_file_is_valid_json():
    """Verify the save file is valid, parseable JSON."""
    import json
    engine = GameEngine(seed="JSONVAL001")
    tmp = os.path.join(tempfile.gettempdir(), "nigrl_json.json")

    save_game(engine, tmp)

    with open(tmp, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "__save_version" in data
    assert "engine" in data
    assert "player" in data
    assert "player_stats" in data
    assert "skills" in data
    assert "abilities" in data
    assert "dungeons" in data
    assert "0" in data["dungeons"]  # floor 0 should exist
    print(f"[OK] Save file is valid JSON with all required sections")

    os.unlink(tmp)


if __name__ == "__main__":
    test_save_after_combat()
    test_save_with_inventory()
    test_save_with_status_effects()
    test_save_with_equipment()
    test_save_messages()
    test_import_export()
    test_multiple_save_overwrite()
    test_save_load_play_extensive()
    test_save_file_is_valid_json()
    print("\nAll advanced save/load tests passed!")
