"""
Test that the seeding system produces reproducible game worlds.
"""

from engine import GameEngine


def _snapshot(engine):
    """Capture a snapshot of the generated world for comparison."""
    d = engine.dungeon
    rooms = [(r.x1, r.y1, r.x2, r.y2) for r in d.rooms]
    entities = sorted(
        [(e.name, e.entity_type, e.x, e.y, e.hp) for e in d.entities],
        key=lambda t: (t[2], t[3], t[0]),
    )
    monsters = [e for e in entities if e[1] == "monster"]
    items = [e for e in entities if e[1] == "item"]
    hazards = [e for e in entities if e[1] == "hazard"]
    player_pos = (engine.player.x, engine.player.y)
    floor_events = dict(engine.floor_events)
    return {
        "rooms": rooms,
        "entities": entities,
        "monsters": monsters,
        "items": items,
        "hazards": hazards,
        "player_pos": player_pos,
        "floor_events": floor_events,
    }


def test_same_seed_identical():
    """Two engines with the same seed must produce identical worlds."""
    seed = "TESTSEED01"
    snap_a = _snapshot(GameEngine(seed=seed))
    snap_b = _snapshot(GameEngine(seed=seed))

    assert snap_a["rooms"] == snap_b["rooms"], "Room layouts differ"
    assert snap_a["player_pos"] == snap_b["player_pos"], "Player positions differ"
    assert snap_a["entities"] == snap_b["entities"], "Entity lists differ"
    assert snap_a["floor_events"] == snap_b["floor_events"], "Floor events differ"
    print("[OK] Same seed produces identical worlds")


def test_different_seed_differs():
    """Different seeds should produce different worlds."""
    snap_a = _snapshot(GameEngine(seed="AAAAAAAAAA"))
    snap_b = _snapshot(GameEngine(seed="ZZZZZZZZZZ"))

    differences = []
    if snap_a["rooms"] != snap_b["rooms"]:
        differences.append("rooms")
    if snap_a["player_pos"] != snap_b["player_pos"]:
        differences.append("player_pos")
    if snap_a["entities"] != snap_b["entities"]:
        differences.append("entities")
    if snap_a["floor_events"] != snap_b["floor_events"]:
        differences.append("floor_events")

    assert len(differences) > 0, "Different seeds produced identical worlds!"
    print(f"[OK] Different seeds differ in: {', '.join(differences)}")


def test_seed_report():
    """Print a detailed report of what the seed controls."""
    seed = "REPORT1234"
    engine = GameEngine(seed=seed)
    snap = _snapshot(engine)

    print(f"\n{'='*60}")
    print(f"  SEED REPORT: {seed}")
    print(f"{'='*60}")

    print(f"\n  Rooms: {len(snap['rooms'])}")
    for i, (x1, y1, x2, y2) in enumerate(snap["rooms"]):
        print(f"    Room {i}: ({x1},{y1})-({x2},{y2})  size {x2-x1}x{y2-y1}")

    print(f"\n  Player position: {snap['player_pos']}")

    print(f"\n  Monsters: {len(snap['monsters'])}")
    for name, _, x, y, hp in snap["monsters"]:
        print(f"    {name:20s} at ({x:2d},{y:2d})  HP={hp}")

    print(f"\n  Items: {len(snap['items'])}")
    for name, _, x, y, _ in snap["items"]:
        print(f"    {name:20s} at ({x:2d},{y:2d})")

    print(f"\n  Hazards: {len(snap['hazards'])}")
    for name, _, x, y, _ in snap["hazards"]:
        print(f"    {name:20s} at ({x:2d},{y:2d})")

    print(f"\n  Floor events: {snap['floor_events'] or 'None'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    test_same_seed_identical()
    test_different_seed_differs()
    test_seed_report()
    print("\nAll seed tests passed!")
