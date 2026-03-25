"""
AI behavior system for NIGRL enemies.

Each AI mode is composed from reusable atomic ACTIONS and governed by an
explicit state machine.  The main entry point is do_ai_turn(), which manages
status-effect lifecycles, respects move_speed timers, evaluates state
transitions, and dispatches the action mapped to the monster's current state.

ARCHITECTURE
────────────
  AIState           Enum of every possible behavioral state.
  effects.Effect    Base class for status effects (see effects.py).
  prepare_ai_tick   Precomputes shared data ONCE per game tick:
                      • creature_positions — set of occupied tiles
                      • step_map — reverse-BFS from the player (Dijkstra map)
  Actions           Atomic things a monster can do: chase, wander, idle.
  Conditions        Predicates that trigger state transitions.
  Behaviors         Declarative dict per ai_type: transitions + actions + speed.

USAGE
─────
  # Once per game tick, before processing monster turns:
  tick_data = ai.prepare_ai_tick(player, dungeon, monsters)

  # Then for each living monster:
  ai.do_ai_turn(monster, player, dungeon, engine, **tick_data)

AI MODES
────────
  meander            Always steps toward the player.  Attacks when adjacent.
  wander_ambush      Wanders until player enters sight_radius, then chases.
  passive_until_hit  Wanders until damaged, then chases.
"""

import math
import random
from collections import deque
from enum import Enum

import effects


# ══════════════════════════════════════════════════════════════════════════════
# AI STATES
# ══════════════════════════════════════════════════════════════════════════════

class AIState(Enum):
    IDLE = "idle"
    WANDERING = "wandering"
    CHASING = "chasing"
    FLEEING = "fleeing"
    ALERTING = "alerting"


# ── Effect hooks (delegate to effects.Effect instances on the monster) ──────

def _sorted_effects(monster):
    """Return effects sorted by descending priority."""
    return sorted(monster.status_effects, key=lambda e: getattr(e, "priority", 0), reverse=True)


def _apply_before_turn(monster, player, dungeon):
    """Run before_turn hooks.  Return True if the turn should be skipped."""
    for effect in _sorted_effects(monster):
        if effect.before_turn(monster, player, dungeon):
            return True
    return False



def _apply_modify_movement(dx, dy, monster, player, dungeon):
    """Let every active effect modify the movement vector."""
    for effect in _sorted_effects(monster):
        if hasattr(effect, "modify_movement"):
            dx, dy = effect.modify_movement(dx, dy, monster, player, dungeon)
    return dx, dy


# ══════════════════════════════════════════════════════════════════════════════
# CREATURE POSITIONS  (built once per tick — O(n) total, not O(n²))
# ══════════════════════════════════════════════════════════════════════════════

def build_creature_positions(monsters):
    """
    Return a set of (x, y) positions occupied by living monsters.
    Built once per tick by prepare_ai_tick().
    """
    return {
        (m.x, m.y)
        for m in monsters
        if getattr(m, "hp", 1) > 0
    }


def _tile_free(x, y, dungeon, creature_positions=None, self_pos=None):
    """
    True when a tile is passable terrain AND not occupied by another
    creature or movement-blocking entity (e.g. table).
    *self_pos* is the checking monster's own tile — excluded
    so a monster doesn't consider itself an obstacle.
    """
    if dungeon.is_terrain_blocked(x, y):
        return False
    # Check for movement-blocking non-creature entities (tables, crates, etc.)
    getter = getattr(dungeon, 'get_entities_at', None)
    if getter is not None:
        for e in getter(x, y):
            if e.blocks_movement and e.entity_type == "hazard":
                return False
    if creature_positions is not None:
        if (x, y) in creature_positions and (x, y) != self_pos:
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# PATHFINDING — REVERSE BFS (DIJKSTRA MAP)
#
# A single BFS radiates outward from the player.  The resulting step_map
# lets every monster look up its next step toward the player in O(1).
# Built ONCE per tick by prepare_ai_tick().
#
# The map uses terrain only (ignores creature positions) so paths remain
# valid as monsters move sequentially during the tick.  Creature collision
# is enforced at move-time by _tile_free().
# ══════════════════════════════════════════════════════════════════════════════

_DIRECTIONS = [
    (dx, dy)
    for dx in (-1, 0, 1)
    for dy in (-1, 0, 1)
    if dx != 0 or dy != 0
]


def build_step_map(player, dungeon, max_depth=25):
    """
    Reverse BFS from the player.  Returns {(x, y): (dx, dy)} where
    (dx, dy) is the step a monster at (x, y) should take to move one
    tile closer to the player along the shortest path.

    Built once per tick, shared by every monster.  O(tiles_in_radius).
    """
    goal = (player.x, player.y)
    frontier = deque([(goal, 0)])
    came_from = {goal: None}

    # Pre-compute blocked hazard positions (tables, etc.) so BFS avoids them
    _blocked_hazards = set()
    for e in dungeon.entities:
        if e.blocks_movement and getattr(e, 'entity_type', '') == 'hazard':
            _blocked_hazards.add((e.x, e.y))

    while frontier:
        (cx, cy), depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for ddx, ddy in _DIRECTIONS:
            nx, ny = cx + ddx, cy + ddy
            if (nx, ny) in came_from:
                continue
            if dungeon.is_terrain_blocked(nx, ny):
                continue
            if (nx, ny) in _blocked_hazards:
                continue
            came_from[(nx, ny)] = (cx, cy)
            frontier.append(((nx, ny), depth + 1))

    # For each reachable tile, the step toward the player is the
    # direction toward its parent in the BFS tree.
    step_map = {}
    for pos, parent in came_from.items():
        if parent is None:
            continue
        step_map[pos] = (parent[0] - pos[0], parent[1] - pos[1])

    return step_map


# ══════════════════════════════════════════════════════════════════════════════
# TICK PREPARATION — call once, share with every do_ai_turn()
# ══════════════════════════════════════════════════════════════════════════════

def prepare_ai_tick(player, dungeon, monsters):
    """
    Precompute shared data for this game tick.

    Returns a dict suitable for **-unpacking into do_ai_turn():

        tick_data = ai.prepare_ai_tick(player, dungeon, monsters)
        for monster in monsters:
            ai.do_ai_turn(monster, player, dungeon, engine, **tick_data)
    """
    positions = build_creature_positions(monsters)
    positions.add((player.x, player.y))  # player tile is occupied; blocks wandering monsters
    return {
        "creature_positions": positions,
        "step_map":           build_step_map(player, dungeon),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Movement helpers
# ──────────────────────────────────────────────────────────────────────────────

def _dist(ax, ay, bx, by):
    return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2)


def _step_toward(monster, player, dungeon, creature_positions=None,
                 step_map=None):
    """
    Return (dx, dy, should_attack).

    1. Adjacent to player → attack direction immediately.
    2. step_map O(1) lookup (shared reverse BFS).
    3. Greedy fallback when the tile is outside the step_map.
    """
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    self_pos = (mx, my)

    # Greedy direction (used for adjacency check and fallback)
    gdx = 0 if px == mx else (1 if px > mx else -1)
    gdy = 0 if py == my else (1 if py > my else -1)

    # ── 1. Adjacency check ───────────────────────────────────────────
    for adx, ady in [(gdx, gdy), (gdx, 0), (0, gdy)]:
        if adx == 0 and ady == 0:
            continue
        if mx + adx == px and my + ady == py:
            return adx, ady, True

    # ── 2. Step-map lookup (O(1)) ────────────────────────────────────
    if step_map is not None:
        step = step_map.get(self_pos)
        if step is not None:
            dx, dy = step
            nx, ny = mx + dx, my + dy
            if nx == px and ny == py:
                return dx, dy, True
            if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
                return dx, dy, False

    # ── 3. Greedy fallback ───────────────────────────────────────────
    for adx, ady in [(gdx, gdy), (gdx, 0), (0, gdy)]:
        if adx == 0 and ady == 0:
            continue
        nx, ny = mx + adx, my + ady
        if nx == px and ny == py:
            return adx, ady, True
        if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
            return adx, ady, False

    return 0, 0, False


def _step_random(monster, dungeon, creature_positions=None):
    """Take one random unblocked step.  Returns (dx, dy)."""
    self_pos = (monster.x, monster.y)
    dirs = list(_DIRECTIONS)
    random.shuffle(dirs)
    for dx, dy in dirs:
        if _tile_free(monster.x + dx, monster.y + dy, dungeon,
                      creature_positions, self_pos):
            return dx, dy
    return 0, 0


# ──────────────────────────────────────────────────────────────────────────────
# ACTIONS — atomic things a monster can do on its turn
# ──────────────────────────────────────────────────────────────────────────────

def chase(monster, player, dungeon, engine, creature_positions=None,
          step_map=None):
    """Step toward the player.  Attack when adjacent.
    Returns "attack", "move", or "idle"."""
    dx, dy, _ = _step_toward(monster, player, dungeon,
                             creature_positions, step_map)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return "idle"

    nx, ny = monster.x + dx, monster.y + dy

    if nx == player.x and ny == player.y:
        engine.handle_monster_attack(monster)
        return "attack"
    elif _tile_free(nx, ny, dungeon, creature_positions,
                    (monster.x, monster.y)):
        monster.move(dx, dy)
        return "move"
    return "idle"


def wander(monster, player, dungeon, engine, creature_positions=None,
           step_map=None):
    """Take one random unblocked step.
    Returns "move" or "idle"."""
    dx, dy = _step_random(monster, dungeon, creature_positions)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return "idle"

    nx, ny = monster.x + dx, monster.y + dy

    if _tile_free(nx, ny, dungeon, creature_positions,
                  (monster.x, monster.y)):
        monster.move(dx, dy)
        return "move"
    return "idle"


def wander_in_room(monster, player, dungeon, engine, creature_positions=None,
                   step_map=None):
    """Take one random unblocked step, but only to tiles within the monster's
    spawn room.  Keeps room_guard monsters from drifting into corridors before
    the player enters their room.
    Returns "move" or "idle"."""
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    self_pos = (monster.x, monster.y)
    dirs = list(_DIRECTIONS)
    random.shuffle(dirs)
    for dx, dy in dirs:
        nx, ny = monster.x + dx, monster.y + dy
        # Don't wander onto the player — that's handled by state transition to CHASING
        if nx == player.x and ny == player.y:
            continue
        if room_tiles is not None and (nx, ny) not in room_tiles:
            continue
        if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
            dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)
            monster.move(dx, dy)
            return "move"
    return "idle"


def flee(monster, player, dungeon, engine, creature_positions=None,
         step_map=None):
    """Step away from the player. Tries the direct opposite direction first,
    then falls back to alternative directions sorted by distance from player.
    Returns "move" or "idle"."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    self_pos = (mx, my)

    # Primary flee direction
    dx = 0 if px == mx else (-1 if px > mx else 1)
    dy = 0 if py == my else (-1 if py > my else 1)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx != 0 or dy != 0:
        nx, ny = mx + dx, my + dy
        if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
            monster.move(dx, dy)
            return "move"

    # Primary blocked — try all 8 neighbors, preferring those farthest from player
    candidates = []
    for cdx in (-1, 0, 1):
        for cdy in (-1, 0, 1):
            if cdx == 0 and cdy == 0:
                continue
            nx, ny = mx + cdx, my + cdy
            if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
                dist = max(abs(nx - px), abs(ny - py))
                candidates.append((dist, cdx, cdy))

    if candidates:
        # Pick the direction that maximizes distance from player
        candidates.sort(key=lambda c: c[0], reverse=True)
        _, best_dx, best_dy = candidates[0]
        best_dx, best_dy = _apply_modify_movement(best_dx, best_dy, monster, player, dungeon)
        if best_dx != 0 or best_dy != 0:
            nx, ny = mx + best_dx, my + best_dy
            if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
                monster.move(best_dx, best_dy)
                return "move"

    return "idle"


def follow_in_room(monster, player, dungeon, engine, creature_positions=None,
                   step_map=None):
    """Move toward the monster's leader while staying within the spawn room.
    Used by escort tweakers following their drug dealer.
    Returns "move" or "idle"."""
    leader = getattr(monster, "leader", None)
    if leader is None or not leader.alive:
        # Fallback to wandering if leader is gone
        return wander_in_room(monster, player, dungeon, engine, creature_positions, step_map)

    room_tiles = getattr(monster, "spawn_room_tiles", None)
    self_pos = (monster.x, monster.y)

    # Try to move one step closer to the leader, staying in room
    mx, my = monster.x, monster.y
    lx, ly = leader.x, leader.y

    # If we're already at the leader, stay put
    if (mx, my) == (lx, ly):
        return "idle"

    # Simple greedy direction toward leader
    dx = 0 if lx == mx else (1 if lx > mx else -1)
    dy = 0 if ly == my else (1 if ly > my else -1)

    # Try the direct step
    nx, ny = mx + dx, my + dy
    if room_tiles is not None and (nx, ny) not in room_tiles:
        # Can't move there (outside room), try just horizontal or vertical
        if room_tiles and (mx + dx, my) in room_tiles:
            nx, ny = mx + dx, my
        elif room_tiles and (mx, my + dy) in room_tiles:
            nx, ny = mx, my + dy
        else:
            return "idle"

    if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
        dx_final, dy_final = nx - mx, ny - my
        dx_final, dy_final = _apply_modify_movement(dx_final, dy_final, monster, player, dungeon)
        monster.move(dx_final, dy_final)
        return "move"
    return "idle"


def idle(monster, player, dungeon, engine, creature_positions=None,
         step_map=None):
    """Do nothing.  Returns "idle"."""
    return "idle"


def cartel_idle(monster, player, dungeon, engine, creature_positions=None,
                step_map=None):
    """Cartel unit idle — occasionally wander. 25% chance, can't move twice in a row."""
    if getattr(monster, '_idle_moved_last', False):
        monster._idle_moved_last = False
        return "idle"
    if random.random() > 0.25:
        return "idle"
    dx, dy = _step_random(monster, dungeon, creature_positions)
    if dx == 0 and dy == 0:
        return "idle"
    monster.move(dx, dy)
    monster._idle_moved_last = True
    return "move"


def suicide_chase(monster, player, dungeon, engine, creature_positions=None,
                  step_map=None):
    """Chase the player. When adjacent, explode instead of normal attack.
    Returns "attack", "move", or "idle"."""
    dx, dy, _ = _step_toward(monster, player, dungeon,
                             creature_positions, step_map)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return "idle"

    nx, ny = monster.x + dx, monster.y + dy

    if nx == player.x and ny == player.y:
        engine.handle_suicide_explosion(monster)
        return "attack"
    elif _tile_free(nx, ny, dungeon, creature_positions,
                    (monster.x, monster.y)):
        monster.move(dx, dy)
        return "move"
    return "idle"


def throw_vial(monster, player, dungeon, engine, creature_positions=None,
               step_map=None):
    """Stationary ranged attack: throw a toxic vial at the player if in range + LOS.
    Never moves when attacking. Returns "attack" or "idle"."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    dist = max(abs(mx - px), abs(my - py))

    if dist <= 5 and _has_los(dungeon, mx, my, px, py):
        engine.handle_chemist_vial(monster)
        return "attack"

    # Out of range or no LOS — wander
    return wander(monster, player, dungeon, engine, creature_positions, step_map)


def sac_spider_attack(monster, player, dungeon, engine, creature_positions=None,
                      step_map=None):
    """Sac Spider: shoots web at range 3 if player not webbed; melee chase if webbed."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    dist = max(abs(mx - px), abs(my - py))

    player_webbed = any(
        getattr(e, 'id', '') == 'webbed' for e in player.status_effects
    )

    # If player is NOT webbed and within range 3 with LOS → shoot web
    if not player_webbed and dist <= 3 and _has_los(dungeon, mx, my, px, py):
        engine._sac_spider_web_shot(monster)
        return "attack"

    # Player is webbed (or out of range) → chase for melee
    return chase(monster, player, dungeon, engine, creature_positions, step_map)


def spawner_idle(monster, player, dungeon, engine, creature_positions=None,
                 step_map=None):
    """Stationary spawner — never moves, spawns children if under cap.  Returns "idle"."""
    if not hasattr(monster, "spawned_children"):
        return "idle"
    # Prune dead children
    monster.spawned_children = [c for c in monster.spawned_children if getattr(c, "alive", False)]
    if len(monster.spawned_children) < monster.max_spawned:
        engine.spawn_child(monster, creature_positions)
    return "idle"


def falcon_run_to_ally(monster, player, dungeon, engine, creature_positions=None,
                       step_map=None):
    """Falcon moves toward nearest same-faction ally.  When adjacent, alerts the area."""
    faction = getattr(monster, "faction", None)
    best_ally = None
    best_dist = float("inf")
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "faction", None) != faction:
            continue
        d = max(abs(monster.x - entity.x), abs(monster.y - entity.y))
        if d < best_dist:
            best_dist = d
            best_ally = entity

    if best_ally is None:
        # No allies — just chase
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    # If adjacent to ally, alert and transition to chase
    if best_dist <= 1:
        _falcon_alert_area(monster, dungeon, engine)
        monster.ai_state = AIState.CHASING
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    # Step toward ally — try all 8 directions, pick the one closest to target
    mx, my = monster.x, monster.y
    ax, ay = best_ally.x, best_ally.y
    candidates = []
    for adx in (-1, 0, 1):
        for ady in (-1, 0, 1):
            if adx == 0 and ady == 0:
                continue
            nx, ny = mx + adx, my + ady
            if _tile_free(nx, ny, dungeon, creature_positions, (mx, my)):
                dist = max(abs(ax - nx), abs(ay - ny))
                candidates.append((dist, adx, ady))
    if candidates:
        candidates.sort()
        _, adx, ady = candidates[0]
        monster.move(adx, ady)
        return "move"
    return "idle"


def _falcon_alert_area(falcon, dungeon, engine):
    """Alert all same-faction enemies within 4 tiles of the falcon."""
    faction = getattr(falcon, "faction", None)
    alerted = 0
    for entity in dungeon.entities:
        if entity is falcon or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "faction", None) != faction:
            continue
        if (max(abs(falcon.x - entity.x), abs(falcon.y - entity.y)) <= 4
                and _has_los(dungeon, falcon.x, falcon.y, entity.x, entity.y)):
            entity.ai_state = AIState.CHASING
            entity.provoked = True
            alerted += 1
    if alerted > 0:
        engine.messages.append(
            f"{falcon.name} lets out a piercing whistle! {alerted} allies alerted!"
        )


def maintain_distance(monster, player, dungeon, engine, creature_positions=None,
                      step_map=None):
    """Ranged AI: maintain distance from player, shoot when in range + LOS.
    If player too close and blink available, teleport away."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    ra = monster.ranged_attack
    if ra is None:
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    dist = max(abs(mx - px), abs(my - py))

    # If player within 2 tiles and blink available, teleport away
    if dist <= 2 and monster.blink_charges > 0:
        _blink_away(monster, player, dungeon, engine, creature_positions)
        return "move"

    atk_range = ra["range"]

    # In range + LOS: shoot
    if dist <= atk_range and _has_los(dungeon, mx, my, px, py):
        engine.handle_monster_ranged_attack(monster)
        return "attack"

    # Too close (but no blink): flee
    if dist <= 2:
        return flee(monster, player, dungeon, engine, creature_positions, step_map)

    # Too far: step toward but stop at range
    if dist > atk_range:
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    # At edge of range but no LOS: step toward
    return chase(monster, player, dungeon, engine, creature_positions, step_map)


def kite_at_range(monster, player, dungeon, engine, creature_positions=None,
                  step_map=None):
    """Ranged AI that only fires at exactly the weapon's range.
    Moves closer if too far, backs away if too close, shoots at exact range."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    ra = monster.ranged_attack
    if ra is None:
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    dist = max(abs(mx - px), abs(my - py))
    atk_range = ra["range"]

    # At exact range with LOS: shoot
    if dist == atk_range and _has_los(dungeon, mx, my, px, py):
        engine.handle_monster_ranged_attack(monster)
        return "attack"

    # Too close: step away
    if dist < atk_range:
        return flee(monster, player, dungeon, engine, creature_positions, step_map)

    # Too far or no LOS: step toward
    return chase(monster, player, dungeon, engine, creature_positions, step_map)


def occultist_attack(monster, player, dungeon, engine, creature_positions=None,
                     step_map=None):
    """Occultist AI: if player within range and LOS, cast hex. Otherwise chase."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y
    ra = monster.ranged_attack
    if ra is None:
        return chase(monster, player, dungeon, engine, creature_positions, step_map)

    dist = max(abs(mx - px), abs(my - py))
    atk_range = ra["range"]

    # Within range with LOS: always attack (prioritize over moving)
    if dist <= atk_range and _has_los(dungeon, mx, my, px, py):
        engine.handle_monster_ranged_attack(monster)
        return "attack"

    # Out of range: chase
    return chase(monster, player, dungeon, engine, creature_positions, step_map)


def _blink_away(monster, player, dungeon, engine, creature_positions):
    """Teleport ~3 tiles away from the player along the flee vector."""
    mx, my = monster.x, monster.y
    px, py = player.x, player.y

    # Flee direction
    fdx = 0 if px == mx else (-1 if px > mx else 1)
    fdy = 0 if py == my else (-1 if py > my else 1)

    # Try 3 tiles, then 2, then 1 along flee vector
    for dist in (3, 2, 1):
        nx, ny = mx + fdx * dist, my + fdy * dist
        if _tile_free(nx, ny, dungeon, creature_positions, (mx, my)):
            if creature_positions is not None:
                creature_positions.discard((mx, my))
                creature_positions.add((nx, ny))
            monster.x, monster.y = nx, ny
            monster.blink_charges -= 1
            engine.messages.append(f"{monster.name} blinks away!")
            return
    # Fallback: couldn't blink
    monster.blink_charges -= 1
    engine.messages.append(f"{monster.name} tries to blink but has no room!")


# ──────────────────────────────────────────────────────────────────────────────
# CONDITIONS — predicates that drive state transitions
# ──────────────────────────────────────────────────────────────────────────────

def always(monster, player, dungeon):
    """Unconditional.  Useful as a catch-all transition."""
    return True


def _has_los(dungeon, x1, y1, x2, y2):
    """True if no wall tile lies between (x1, y1) and (x2, y2).
    Samples the line at integer-tile intervals using linear interpolation."""
    dx = x2 - x1
    dy = y2 - y1
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return True
    for i in range(1, steps):
        tx = round(x1 + dx * i / steps)
        ty = round(y1 + dy * i / steps)
        if dungeon.is_terrain_blocked(tx, ty):
            return False
    return True


def player_in_sight(monster, player, dungeon):
    """True when the player is within the monster's sight_radius with clear LOS."""
    if _dist(monster.x, monster.y, player.x, player.y) > monster.sight_radius:
        return False
    return _has_los(dungeon, monster.x, monster.y, player.x, player.y)


def player_lost(monster, player, dungeon):
    """True when the player has escaped beyond 2 × sight_radius."""
    return _dist(monster.x, monster.y, player.x, player.y) > monster.sight_radius * 2


def was_provoked(monster, player, dungeon):
    """True when external code (damage system) has set monster.provoked."""
    return getattr(monster, "provoked", False)


def player_in_monster_room(monster, player, dungeon):
    """True when the player occupies a tile inside this monster's spawn room.
    Falls back to player_in_sight if no spawn room was recorded at spawn."""
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if room_tiles is None:
        return player_in_sight(monster, player, dungeon)
    return (player.x, player.y) in room_tiles


def floor_alarm_triggered(monster, player, dungeon):
    """True once the first monster on this floor has been killed.
    The dungeon sets dungeon.first_kill_happened = True in that event."""
    return getattr(dungeon, "first_kill_happened", False)


def combat_in_monster_room(monster, player, dungeon):
    """True when the player has attacked a monster in the same room this monster
    is currently standing in (not spawn room — current position)."""
    room_idx = dungeon.get_room_index_at(monster.x, monster.y)
    if room_idx is None:
        return False
    return room_idx in getattr(dungeon, "rooms_with_combat", set())


def female_killed_on_floor(monster, player, dungeon):
    """True once any female monster on this floor has been killed.
    The engine sets dungeon.female_kill_happened = True in that event."""
    return getattr(dungeon, "female_kill_happened", False)


def leader_in_room(monster, player, dungeon):
    """True when the escort's leader is in the same spawn room."""
    leader = getattr(monster, "leader", None)
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if leader is None or not leader.alive or room_tiles is None:
        return False
    return (leader.x, leader.y) in room_tiles


def has_scored_hit(monster, player, dungeon):
    """True when the monster has successfully attacked the player this encounter."""
    return getattr(monster, "has_attacked_player", False)


def is_far_away(monster, player, dungeon):
    """True when the player is far beyond the monster's sight radius (safe to reset)."""
    return _dist(monster.x, monster.y, player.x, player.y) > monster.sight_radius * 3


def faction_is_hostile(monster, player, dungeon):
    """True if the player's reputation with this monster's faction is Unfriendly or worse (< -2000)."""
    faction = getattr(monster, "faction", None)
    if not faction:
        return True
    stats = getattr(player, "stats", None)
    if stats is None:
        return True
    return stats.reputation.get(faction, -1000) < -2000


def room_ally_attacked(monster, player, dungeon):
    """True if ANY enemy in this monster's spawn room has been provoked."""
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if room_tiles is None:
        return False
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "provoked", False) and (entity.x, entity.y) in room_tiles:
            return True
    return False


def faction_room_ally_attacked(monster, player, dungeon):
    """True if any SAME-FACTION enemy in this monster's spawn room has been provoked."""
    faction = getattr(monster, "faction", None)
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if room_tiles is None or faction is None:
        return False
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "faction", None) != faction:
            continue
        if getattr(entity, "provoked", False) and (entity.x, entity.y) in room_tiles:
            return True
    return False


def room_spider_alerted(monster, player, dungeon):
    """True if any pipe_spider in this monster's spawn room is already CHASING."""
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if room_tiles is None:
        return False
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "enemy_type", None) != "pipe_spider":
            continue
        if (entity.x, entity.y) in room_tiles and getattr(entity, "ai_state", None) == AIState.CHASING:
            return True
    return False


def room_zombie_alerted(monster, player, dungeon):
    """True if any zombie in this monster's spawn room is already CHASING."""
    room_tiles = getattr(monster, "spawn_room_tiles", None)
    if room_tiles is None:
        return False
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "enemy_type", None) != "zombie":
            continue
        if (entity.x, entity.y) in room_tiles and getattr(entity, "ai_state", None) == AIState.CHASING:
            return True
    return False


def cartel_should_deaggro(monster, player, dungeon):
    """True when the faction is friendly and no same-faction ally was attacked — stand down."""
    return not cartel_should_aggro(monster, player, dungeon)


def cartel_should_aggro(monster, player, dungeon):
    """Unified aggro check for cartel_unit and cartel_ranged AI.

    Hostile (rep < 2000): aggro if player in sight OR any room ally attacked.
    Neutral+ (rep >= 2000): aggro only if same-faction room ally attacked.
    """
    if faction_is_hostile(monster, player, dungeon):
        return player_in_sight(monster, player, dungeon) or room_ally_attacked(monster, player, dungeon)
    else:
        return faction_room_ally_attacked(monster, player, dungeon)


def falcon_adjacent_to_ally(monster, player, dungeon):
    """True when the falcon is within Chebyshev distance 1 of a same-faction ally."""
    faction = getattr(monster, "faction", None)
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "faction", None) != faction:
            continue
        if max(abs(monster.x - entity.x), abs(monster.y - entity.y)) <= 1:
            return True
    return False


def player_within_2(monster, player, dungeon):
    """True when the player is within 2 tiles (Chebyshev)."""
    return max(abs(monster.x - player.x), abs(monster.y - player.y)) <= 2


def nearby_ally_attacked(monster, player, dungeon):
    """True when any monster within 10 tiles has been provoked (attacked by player).
    Used by proximity_alarm AI — strippers who react when nearby allies are hit."""
    for entity in dungeon.entities:
        if entity is monster or entity.entity_type != "monster":
            continue
        if not getattr(entity, "alive", True):
            continue
        if getattr(entity, "provoked", False):
            if _dist(monster.x, monster.y, entity.x, entity.y) <= 10:
                return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
# BEHAVIOR REGISTRY
#
# Each entry fully defines a monster archetype:
#
#   initial_state   AIState assigned when the monster spawns.
#   fast_states     Set of states that use chase_speed for the timer.
#   transitions     {current_state: [(condition, target_state), ...]}
#                   Evaluated top-to-bottom; first True wins.
#   actions         {state: action_fn}
#                   Unmapped states fall back to idle.
#
# To add a new monster AI, add an entry here.  You only need a new
# action or condition function if none of the existing ones fit.
# ══════════════════════════════════════════════════════════════════════════════

BEHAVIORS = {

    # ── Meander ──────────────────────────────────────────────────────────
    # Single state.  Always plods toward the player.
    "meander": {
        "initial_state": AIState.CHASING,
        "transitions":   {},
        "actions": {
            AIState.CHASING: chase,
        },
    },

    # ── Wander → Ambush ─────────────────────────────────────────────────
    # Two states with bidirectional transitions.
    "wander_ambush": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_sight, AIState.CHASING)],
            AIState.CHASING:   [(player_lost,     AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Passive until hit ────────────────────────────────────────────────
    # One-way transition: once provoked, never reverts.
    "passive_until_hit": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(was_provoked, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Room guard ───────────────────────────────────────────────────────
    # Wanders within its spawn room.  Once the player steps into that room,
    # it permanently switches to chasing (follows the player anywhere).
    "room_guard": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_monster_room, AIState.CHASING)],
            # No revert — once triggered it chases forever.
        },
        "actions": {
            AIState.WANDERING: wander_in_room,
            AIState.CHASING:   chase,
        },
    },

    # ── Alarm chaser ─────────────────────────────────────────────────────
    # Wanders normally until the first monster on the floor is killed, then
    # chases from anywhere — permanently.
    "alarm_chaser": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(floor_alarm_triggered, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Room combat ───────────────────────────────────────────────────────
    # Wanders passively until the player attacks a monster in the same room
    # this monster is currently in, then permanently chases.
    "room_combat": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(combat_in_monster_room, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Female alarm (Fat Gooner) ─────────────────────────────────────────
    # Wanders passively until a female monster anywhere on the floor is killed.
    # Then permanently rages and chases the player.
    "female_alarm": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(female_killed_on_floor, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Escort (tweaker bodyguard) ────────────────────────────────────────
    # Follows a leader (drug dealer) around within their shared spawn room.
    # Once the player enters the room, permanently switches to chasing.
    "escort": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_monster_room, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: follow_in_room,
            AIState.CHASING:   chase,
        },
    },

    # ── Stationary Guard ─────────────────────────────────────────────────
    # Stands motionless until struck by the player.  Once provoked, chases
    # permanently (never reverts to idle).
    "stationary_guard": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(was_provoked, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: idle,
            AIState.CHASING:   chase,
        },
    },

    # ── Jerome Guard ────────────────────────────────────────────────────
    # Jerome-specific: stands motionless until ANY damage provokes him,
    # then chases permanently.  Faster action rate than normal guards.
    "jerome_guard": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(was_provoked, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: idle,
            AIState.CHASING:   chase,
        },
    },

    # ── Proximity Alarm ─────────────────────────────────────────────────
    # Meanders until any monster within 10 tiles is attacked by the player,
    # then permanently chases.  Used by strippers in special rooms.
    "proximity_alarm": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(nearby_ally_attacked, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Ranged Room Guard (DEA Agent) ───────────────────────────────────────
    # Wanders in spawn room until player enters, then kites at exact weapon range.
    "ranged_room_guard": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_monster_room, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander_in_room,
            AIState.CHASING:   kite_at_range,
        },
    },

    # ── Cartel Unit (Grunt / Hitman) ────────────────────────────────────────
    # Stationary until aggro'd via faction reputation rules, then chases permanently.
    "cartel_unit": {
        "initial_state": AIState.IDLE,
        "transitions": {
            AIState.IDLE:    [(cartel_should_aggro, AIState.CHASING)],
            AIState.CHASING: [(cartel_should_deaggro, AIState.IDLE)],
        },
        "actions": {
            AIState.IDLE:    cartel_idle,
            AIState.CHASING: chase,
        },
    },

    # ── Falcon Alert (Falcon) ─────────────────────────────────────────────
    # Runs to nearest same-faction ally, alerts 9x9, then chases.
    "falcon_alert": {
        "initial_state": AIState.IDLE,
        "transitions": {
            AIState.IDLE:     [(cartel_should_aggro, AIState.ALERTING)],
            AIState.ALERTING: [(cartel_should_deaggro, AIState.IDLE),
                               (falcon_adjacent_to_ally, AIState.CHASING)],
            AIState.CHASING:  [(cartel_should_deaggro, AIState.IDLE)],
        },
        "actions": {
            AIState.IDLE:     cartel_idle,
            AIState.ALERTING: falcon_run_to_ally,
            AIState.CHASING:  chase,
        },
    },

    # ── Cartel Ranged (Specialist) ────────────────────────────────────────
    # Maintains distance, shoots, blinks away if cornered.
    "cartel_ranged": {
        "initial_state": AIState.IDLE,
        "transitions": {
            AIState.IDLE:    [(cartel_should_aggro, AIState.CHASING)],
            AIState.CHASING: [(cartel_should_deaggro, AIState.IDLE)],
        },
        "actions": {
            AIState.IDLE:    cartel_idle,
            AIState.CHASING: maintain_distance,
        },
    },

    # ── Suicide Bomber (Covid-26) ─────────────────────────────────────────
    # Wanders until player spotted, then chases. Explodes on adjacency.
    "suicide_bomber": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_sight, AIState.CHASING)],
            AIState.CHASING:   [(player_lost,     AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   suicide_chase,
        },
    },

    # ── Chemist Ranged (Chemist) ──────────────────────────────────────────
    # Wanders until player spotted, then throws vials at range. Stationary when attacking.
    "chemist_ranged": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_sight, AIState.CHASING)],
            AIState.CHASING:   [(player_lost,     AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   throw_vial,
        },
    },

    # ── Stationary Spawner (Rad Rats Nest) ────────────────────────────────
    # Never moves.  Spawns children up to max_spawned each turn.
    "stationary_spawner": {
        "initial_state": AIState.IDLE,
        "transitions":   {},
        "actions": {
            AIState.IDLE: spawner_idle,
        },
    },

    # ── Hit and Run (Niglet) ──────────────────────────────────────────────
    # Cowardly enemy that ambushes from a distance. Wanders until player is
    # spotted, then chases briefly. After one successful attack, immediately
    # flees and doesn't return unless the player is far away.
    "hit_and_run": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_sight, AIState.CHASING)],
            AIState.CHASING:   [
                (has_scored_hit, AIState.FLEEING),
                (player_lost,    AIState.WANDERING),
            ],
            AIState.FLEEING: [
                (is_far_away, AIState.WANDERING),
            ],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
            AIState.FLEEING:   flee,
        },
    },
    # ── Meatball (summoned projectile) ────────────────────────────────────
    # Chases nearest enemy; explosion logic handled in do_ai_turn.
    "meatball": {
        "initial_state": AIState.CHASING,
        "transitions":   {},
        "actions": {
            AIState.CHASING: chase,
        },
    },
    # ── Spider Hatchling (stationary summon) ─────────────────────────────
    # Stationary; attacks adjacent enemies. Custom turn logic in do_ai_turn.
    "spider_hatchling": {
        "initial_state": AIState.IDLE,
        "transitions":   {},
        "actions": {
            AIState.IDLE: idle,
        },
    },

    # ── Sac Spider ───────────────────────────────────────────────────────
    # Room guard; shoots web at range when player not webbed, melee when webbed.
    "sac_spider": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [
                (player_in_monster_room, AIState.CHASING),
                (room_ally_attacked, AIState.CHASING),
            ],
            AIState.CHASING: [(player_lost, AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander_in_room,
            AIState.CHASING:   sac_spider_attack,
        },
    },

    # ── Zombie Pack ────────────────────────────────────────────────────
    # Wanders until player in sight (10 tiles, LOS required); chases.
    # When one zombie in the room aggros, all zombies in that room aggro.
    "zombie_pack": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [
                (player_in_sight, AIState.CHASING),
                (room_ally_attacked, AIState.CHASING),
                (room_zombie_alerted, AIState.CHASING),
            ],
            AIState.CHASING: [(player_lost, AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Black Widow (mini-boss) ────────────────────────────────────────
    # Room guard; once aggro'd, chases permanently (never reverts).
    "black_widow": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [
                (player_in_monster_room, AIState.CHASING),
                (room_ally_attacked, AIState.CHASING),
                (was_provoked, AIState.CHASING),
            ],
        },
        "actions": {
            AIState.WANDERING: wander_in_room,
            AIState.CHASING:   chase,
        },
    },

    # ── Wolf Spider ──────────────────────────────────────────────────────
    # Fast predator. Wanders until player in sight, then chases hard.
    "wolf_spider": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_sight, AIState.CHASING)],
            AIState.CHASING:   [(player_lost,     AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Pipe Spider Pack ────────────────────────────────────────────────
    # Slow wander; chases when player in sight (4 tiles), any room ally is
    # hit, or any other pipe_spider in the room is already chasing.
    "pipe_spider_pack": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [
                (player_in_sight, AIState.CHASING),
                (room_ally_attacked, AIState.CHASING),
                (room_spider_alerted, AIState.CHASING),
            ],
            AIState.CHASING: [(player_lost, AIState.WANDERING)],
        },
        "actions": {
            AIState.WANDERING: wander,
            AIState.CHASING:   chase,
        },
    },

    # ── Occultist Ranged ──────────────────────────────────────────────
    # Room aggro; within range: always hex (prioritize attack over move).
    "occultist_ranged": {
        "initial_state": AIState.WANDERING,
        "transitions": {
            AIState.WANDERING: [(player_in_monster_room, AIState.CHASING)],
        },
        "actions": {
            AIState.WANDERING: wander_in_room,
            AIState.CHASING:   occultist_attack,
        },
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def get_initial_state(ai_type):
    """
    Return the starting AIState for *ai_type*.

    Call this when spawning a monster:
        monster.ai_state = ai.get_initial_state(monster.ai_type)
    """
    behavior = BEHAVIORS.get(ai_type)
    if behavior is None:
        raise ValueError(
            f"Unknown ai_type {ai_type!r}. "
            f"Registered types: {list(BEHAVIORS)}"
        )
    return behavior["initial_state"]


# ──────────────────────────────────────────────────────────────────────────────
# STATE MACHINE EVALUATION
# ──────────────────────────────────────────────────────────────────────────────

def _evaluate_transitions(behavior, monster, player, dungeon):
    """Check transition rules for the current state.  First match wins."""
    transitions = behavior["transitions"].get(monster.ai_state, [])
    for condition, new_state in transitions:
        if condition(monster, player, dungeon):
            monster.ai_state = new_state
            return


def _evaluate_behavior(behavior, monster, player, dungeon, engine,
                       creature_positions, step_map):
    """Run transitions, then execute the action for the resulting state.
    Returns "attack", "move", or "idle"."""
    _evaluate_transitions(behavior, monster, player, dungeon)
    action = behavior["actions"].get(monster.ai_state, idle)
    return action(monster, player, dungeon, engine,
                  creature_positions=creature_positions, step_map=step_map) or "idle"


# ══════════════════════════════════════════════════════════════════════════════
# SUMMON AI — custom turn logic for player-summoned entities
# ══════════════════════════════════════════════════════════════════════════════

def _do_meatball_turn(meatball, player, dungeon, engine, creature_positions):
    """Meatball summon: chase nearest enemy, explode when adjacent.

    Explosion: 3x3 area centered on meatball. Damages all entities in range
    (including player). Damage = 10 + effective_book_smarts / 2.
    Despawns after exploding or when summon_lifetime reaches 0.
    """
    from config import DUNGEON_WIDTH, DUNGEON_HEIGHT

    mx, my = meatball.x, meatball.y

    # Decrement lifetime
    meatball.summon_lifetime -= 1
    if meatball.summon_lifetime <= 0:
        engine.messages.append(f"The {meatball.name} fizzles out.")
        meatball.alive = False
        dungeon.remove_entity(meatball)
        return "idle"

    # Find nearest non-summon enemy
    nearest = None
    best_dist = 999
    for m in dungeon.get_monsters():
        if not m.alive or m is meatball or getattr(m, "is_summon", False):
            continue
        dist = max(abs(m.x - mx), abs(m.y - my))  # Chebyshev
        if dist < best_dist:
            best_dist = dist
            nearest = m

    if nearest is None:
        return "idle"  # no enemies — just wait

    # Check if adjacent to any non-summon enemy (Chebyshev distance 1)
    adjacent_enemy = False
    for m in dungeon.get_monsters():
        if not m.alive or m is meatball or getattr(m, "is_summon", False):
            continue
        if max(abs(m.x - mx), abs(m.y - my)) <= 1:
            adjacent_enemy = True
            break

    if adjacent_enemy:
        # EXPLODE — deal damage in 3x3 area
        bks = engine.player_stats.effective_book_smarts
        damage = 10 + bks // 2
        hit_names = []
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                tx, ty = mx + dx, my + dy
                if not (0 <= tx < DUNGEON_WIDTH and 0 <= ty < DUNGEON_HEIGHT):
                    continue
                # Damage player if in range
                if player.x == tx and player.y == ty:
                    player.take_damage(damage)
                    hit_names.append("you")
                    if not player.alive:
                        engine.messages.append(f"You were killed by a {meatball.name} explosion!")
                # Damage monsters in range
                for ent in dungeon.get_entities_at(tx, ty):
                    if ent.entity_type == "monster" and ent.alive and not getattr(ent, "is_summon", False):
                        ent.take_damage(damage)
                        hit_names.append(ent.name)
                        if not ent.alive:
                            engine.event_bus.emit("entity_died", entity=ent, killer=player)
        engine.messages.append([
            ("MEATBALL EXPLOSION! ", (255, 140, 40)),
            (f"{damage} dmg to: {', '.join(hit_names)}", (255, 200, 150)),
        ])
        meatball.alive = False
        dungeon.remove_entity(meatball)
        return "attack"

    # Chase nearest enemy — simple step toward
    dx = 0 if nearest.x == mx else (1 if nearest.x > mx else -1)
    dy = 0 if nearest.y == my else (1 if nearest.y > my else -1)
    # Try full diagonal, then cardinal fallbacks
    for try_dx, try_dy in [(dx, dy), (dx, 0), (0, dy)]:
        if try_dx == 0 and try_dy == 0:
            continue
        nx, ny = mx + try_dx, my + try_dy
        if not dungeon.is_blocked(nx, ny):
            meatball.move(try_dx, try_dy)
            return "move"
    return "idle"


def _do_spider_hatchling_turn(spider, player, dungeon, engine, creature_positions):
    """Spider Hatchling summon: stationary until an enemy enters 1-tile radius,
    then chases that enemy.

    Deals 2 flat damage (ignores defense) and applies 1 venom stack.
    Sets aggro_target on the bitten monster so it retaliates.
    """
    import random as _rand

    sx, sy = spider.x, spider.y
    chase = getattr(spider, "_chase_target", None)

    # Priority: if something hit us, chase that instead
    attacked_by = getattr(spider, "_attacked_by", None)
    if attacked_by is not None and getattr(attacked_by, "alive", False):
        chase = attacked_by
        spider._chase_target = chase
    spider._attacked_by = None

    # Clear dead/invalid chase target
    if chase is not None and not getattr(chase, "alive", False):
        spider._chase_target = None
        chase = None

    # If no chase target, scan for adjacent enemies to lock onto
    if chase is None:
        adjacent_enemies = []
        for m in dungeon.get_monsters():
            if not m.alive or m is spider or getattr(m, "is_summon", False):
                continue
            if max(abs(m.x - sx), abs(m.y - sy)) <= 1:
                adjacent_enemies.append(m)
        if not adjacent_enemies:
            return "idle"  # stationary — no enemies nearby
        chase = _rand.choice(adjacent_enemies)
        spider._chase_target = chase

    # Check if adjacent to chase target
    dist = max(abs(sx - chase.x), abs(sy - chase.y))
    if dist <= 1:
        # Attack the chase target
        damage = 2
        chase.take_damage(damage)
        engine.messages.append(
            f"Spider Hatchling bites {chase.name} for {damage} damage!"
        )
        effects.apply_effect(chase, engine, "venom", duration=10, stacks=1)
        chase.aggro_target = spider
        if not chase.alive:
            engine.event_bus.emit("entity_died", entity=chase, killer=player)
            spider._chase_target = None
        return "attack"

    # Not adjacent — chase the target
    dx = 0 if chase.x == sx else (1 if chase.x > sx else -1)
    dy = 0 if chase.y == sy else (1 if chase.y > sy else -1)
    for try_dx, try_dy in [(dx, dy), (dx, 0), (0, dy)]:
        if try_dx == 0 and try_dy == 0:
            continue
        nx, ny = sx + try_dx, sy + try_dy
        if not dungeon.is_blocked(nx, ny):
            old_pos = (sx, sy)
            spider.move(try_dx, try_dy)
            if creature_positions is not None:
                creature_positions.discard(old_pos)
                creature_positions.add((spider.x, spider.y))
            return "move"
    return "idle"  # blocked, can't reach target


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def do_ai_turn(monster, player, dungeon, engine,
               creature_positions=None, step_map=None):
    """
    Called once per game turn for each living monster.

    Parameters
    ----------
    monster             : The monster whose turn it is.
    player              : The player entity.
    dungeon             : The dungeon / map object.
    engine              : Game engine (for attack callbacks, etc.).
    creature_positions  : Optional set of (x, y) occupied by living monsters.
                          When provided, monsters path around each other and
                          never stack on the same tile.  Built once per tick
                          via prepare_ai_tick().
    step_map            : Optional {(x, y): (dx, dy)} reverse-BFS from the
                          player.  Shared by every monster for O(1) pathfinding.
                          Built once per tick via prepare_ai_tick().
    """
    # ── Status effects: before-turn hooks ────────────────────────────────
    # (ticking is done by engine.py's _end_of_turn after all monsters move)
    if _apply_before_turn(monster, player, dungeon):
        return "idle"

    # ── Meatball summon AI ───────────────────────────────────────────────
    # Chases nearest enemy, explodes on adjacency. Fully custom — bypasses
    # the behavior state machine.
    if getattr(monster, "is_summon", False) and monster.ai_type == "meatball":
        return _do_meatball_turn(monster, player, dungeon, engine, creature_positions)

    # ── Spider Hatchling summon AI ─────────────────────────────────────
    if getattr(monster, "is_summon", False) and monster.ai_type == "spider_hatchling":
        return _do_spider_hatchling_turn(monster, player, dungeon, engine, creature_positions)

    # ── Universal aggro intercept ──────────────────────────────────────
    # Monsters hit by a summon (e.g. spider hatchling) target it instead
    # of the player until the aggro target dies.
    aggro = getattr(monster, "aggro_target", None)
    if aggro is not None:
        if not getattr(aggro, "alive", False):
            # Aggro target died — clear and resume normal AI
            monster.aggro_target = None
        else:
            mx, my = monster.x, monster.y
            dist = max(abs(mx - aggro.x), abs(my - aggro.y))
            if dist <= 1:
                # Adjacent — attack the aggro target
                damage = max(1, monster.power)
                aggro.take_damage(damage)
                # Let summons know who hit them so they can retaliate
                if getattr(aggro, "is_summon", False):
                    aggro._attacked_by = monster
                engine.messages.append(
                    f"{monster.name} attacks {aggro.name} for {damage} damage!"
                )
                if not aggro.alive:
                    engine.event_bus.emit("entity_died", entity=aggro, killer=monster)
                    monster.aggro_target = None
                return "attack"
            else:
                # Step toward aggro target (greedy pathfinding)
                tx, ty = aggro.x, aggro.y
                dx = 0 if tx == mx else (1 if tx > mx else -1)
                dy = 0 if ty == my else (1 if ty > my else -1)
                for try_dx, try_dy in [(dx, dy), (dx, 0), (0, dy)]:
                    if try_dx == 0 and try_dy == 0:
                        continue
                    nx, ny = mx + try_dx, my + try_dy
                    if not dungeon.is_blocked(nx, ny):
                        old_pos = (mx, my)
                        monster.move(try_dx, try_dy)
                        if creature_positions is not None:
                            creature_positions.discard(old_pos)
                            creature_positions.add((monster.x, monster.y))
                        return "move"
                return "idle"  # blocked, can't reach target

    # ── Jerome's self-healing (boss mechanic) ────────────────────────────
    # When Jerome drops to 40 HP or below, he eats fried chicken to heal
    # 20 HP + HoT (2 HP/turn for 5 turns, doesn't stack). 3 uses. Costs
    # 0 energy so he can still act the same turn.
    if monster.enemy_type == "big_nigga_jerome":
        if monster.hp <= 40 and monster.hp > 0:
            eaten_count = getattr(monster, "eaten_count", 0)
            if eaten_count < 3:
                monster.hp = min(monster.hp + 20, monster.max_hp)
                monster.eaten_count = eaten_count + 1
                engine.messages.append(
                    f"{monster.name} eats fried chicken and feels revitalized! "
                    f"({monster.eaten_count}/3)"
                )
                # HoT: 2 HP/turn for 5 turns — refreshes, doesn't stack
                effects.apply_effect(monster, engine, "hot",
                                     duration=5, amount=2)

    # ── Look up behavior ─────────────────────────────────────────────────
    behavior = BEHAVIORS.get(monster.ai_type)
    if behavior is None:
        raise ValueError(
            f"Unknown ai_type {monster.ai_type!r} on {monster!r}. "
            f"Registered types: {list(BEHAVIORS)}"
        )

    # Lazy-init ai_state for monsters that predate the state machine
    if not hasattr(monster, "ai_state") or monster.ai_state is None:
        monster.ai_state = behavior["initial_state"]

    # ── Run state machine ────────────────────────────────────────────────
    old_pos = (monster.x, monster.y)

    action_type = _evaluate_behavior(
        behavior, monster, player, dungeon, engine,
        creature_positions, step_map,
    )

    # Keep creature_positions current so every subsequent monster this tick
    # sees accurate occupancy and can't walk onto an already-occupied tile.
    if creature_positions is not None:
        new_pos = (monster.x, monster.y)
        if new_pos != old_pos:
            creature_positions.discard(old_pos)
            creature_positions.add(new_pos)

            # Trail-leaving enemies spawn toxic creep on their old tile
            trail = getattr(monster, "leaves_trail", None)
            if trail:
                engine.spawn_trail_creep(old_pos[0], old_pos[1], trail)

    return action_type