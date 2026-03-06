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
    creature.  *self_pos* is the checking monster's own tile — excluded
    so a monster doesn't consider itself an obstacle.
    """
    if dungeon.is_terrain_blocked(x, y):
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

    while frontier:
        (cx, cy), depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for ddx, ddy in _DIRECTIONS:
            nx, ny = cx + ddx, cy + ddy
            if (nx, ny) in came_from:
                continue
            if not dungeon.is_terrain_blocked(nx, ny):
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
    """Step toward the player.  Attack when adjacent."""
    dx, dy, _ = _step_toward(monster, player, dungeon,
                             creature_positions, step_map)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return

    nx, ny = monster.x + dx, monster.y + dy

    if nx == player.x and ny == player.y:
        engine.handle_monster_attack(monster)
    elif _tile_free(nx, ny, dungeon, creature_positions,
                    (monster.x, monster.y)):
        monster.move(dx, dy)


def wander(monster, player, dungeon, engine, creature_positions=None,
           step_map=None):
    """Take one random unblocked step."""
    dx, dy = _step_random(monster, dungeon, creature_positions)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return

    nx, ny = monster.x + dx, monster.y + dy

    if _tile_free(nx, ny, dungeon, creature_positions,
                  (monster.x, monster.y)):
        monster.move(dx, dy)


def wander_in_room(monster, player, dungeon, engine, creature_positions=None,
                   step_map=None):
    """Take one random unblocked step, but only to tiles within the monster's
    spawn room.  Keeps room_guard monsters from drifting into corridors before
    the player enters their room."""
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
            return


def flee(monster, player, dungeon, engine, creature_positions=None,
         step_map=None):
    """
    Step away from the player. Used by cowardly enemies like the niglet
    after they've landed a hit.
    """
    mx, my = monster.x, monster.y
    px, py = player.x, player.y

    # Move in the opposite direction of the player
    dx = 0 if px == mx else (-1 if px > mx else 1)
    dy = 0 if py == my else (-1 if py > my else 1)
    dx, dy = _apply_modify_movement(dx, dy, monster, player, dungeon)

    if dx == 0 and dy == 0:
        return

    nx, ny = monster.x + dx, monster.y + dy

    if _tile_free(nx, ny, dungeon, creature_positions, (monster.x, monster.y)):
        monster.move(dx, dy)


def follow_in_room(monster, player, dungeon, engine, creature_positions=None,
                   step_map=None):
    """Move toward the monster's leader while staying within the spawn room.
    Used by escort tweakers following their drug dealer."""
    leader = getattr(monster, "leader", None)
    if leader is None or not leader.alive:
        # Fallback to wandering if leader is gone
        wander_in_room(monster, player, dungeon, engine, creature_positions, step_map)
        return

    room_tiles = getattr(monster, "spawn_room_tiles", None)
    self_pos = (monster.x, monster.y)

    # Try to move one step closer to the leader, staying in room
    mx, my = monster.x, monster.y
    lx, ly = leader.x, leader.y

    # If we're already at the leader, stay put
    if (mx, my) == (lx, ly):
        return

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
            return

    if _tile_free(nx, ny, dungeon, creature_positions, self_pos):
        dx_final, dy_final = nx - mx, ny - my
        dx_final, dy_final = _apply_modify_movement(dx_final, dy_final, monster, player, dungeon)
        monster.move(dx_final, dy_final)


def idle(monster, player, dungeon, engine, creature_positions=None,
         step_map=None):
    """Do nothing."""
    pass


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
    """Run transitions, then execute the action for the resulting state."""
    _evaluate_transitions(behavior, monster, player, dungeon)
    action = behavior["actions"].get(monster.ai_state, idle)
    action(monster, player, dungeon, engine,
           creature_positions=creature_positions, step_map=step_map)


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
        return

    # ── Jerome's self-healing (boss mechanic) ────────────────────────────
    # When Jerome drops below 25 HP, he eats fried chicken to heal 10 HP
    # and gain a Well Fed buff (+2 power per stack). Limited to 2 meals.
    if monster.enemy_type == "big_nigga_jerome":
        if monster.hp < 25 and monster.hp > 0:
            eaten_count = getattr(monster, "eaten_count", 0)
            if eaten_count < 2:
                monster.hp = min(monster.hp + 10, 50)
                monster.eaten_count = eaten_count + 1
                engine.messages.append(
                    f"{monster.name} eats fried chicken and feels revitalized! "
                    f"({monster.eaten_count}/2)"
                )
                effects.apply_effect(monster, engine, "well_fed",
                                     duration=10, power_bonus=2)

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

    _evaluate_behavior(
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