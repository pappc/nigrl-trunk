# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

**Run the game:**
```bash
python nigrl.py
```

**Run tests:**
```bash
python -m pytest test_*.py -v
python test_game.py
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Project Overview

**NIGRL** is a traditional roguelike game engine written in Python using the tcod library (libtcod bindings). It features permadeath, dungeon generation, enemy AI, crafting, and equipment systems. Currently supports 4 floors in the "Crack Den" zone with 8+ unique enemy types.

## Architecture

The codebase follows a clean, modular design with clear separation of concerns:

### Core Files

- **nigrl.py**: Entry point. Sets up tcod context, loads tileset, runs main loop.
- **engine.py**: `GameEngine` class. Central hub for game state, turn management, action processing, and game events via EventBus.
- **entity.py**: `Entity` class. Universal representation for players, monsters, items, and cash piles with support for combat, HP, status effects, and equipment.
- **dungeon.py**: `Dungeon` class with procedural generation (rooms + corridors), FOV computation, tile management, and entity spawning.
- **render.py**: Multi-panel tcod renderer. Left panel (stats/inventory), center (map/FOV), right (inventory/crafting). All UI menus rendered as overlays.
- **input_handler.py**: Converts tcod key events to action dicts.
- **config.py**: Global constants (screen size, dungeon dimensions, spawn rates, UI layout).

### Game Systems

- **ai.py**: Behavioral state machine with AIState enum (IDLE, WANDERING, CHASING, FLEEING, ALERTING). Each AI mode declaratively specified. Status effects as pluggable lifecycle hooks. Central functions: `prepare_ai_tick()`, `do_ai_turn()`.
- **enemies.py**: `MonsterTemplate` dataclass-based registry system. Declarative enemy definitions with easy validation via `validate_registry()`. Supports variants, special attacks, on-hit effects, and spawn tables per zone.
- **items.py**: Item definition dict + crafting recipes. Factory function `create_item_entity()` instantiates items as Entity objects linked via `item_id`.
- **stats.py**: `PlayerStats` class. Stat calculations (HP, damage, defense) derived from base stats (Constitution, Strength, Street Smarts, Book Smarts, Tolerance, Swagger).
- **skills.py**: Player skill/unlock system.
- **status_effect.py**: Base `StatusEffect` class. Subclasses override lifecycle hooks: `tick()`, `on_expire()`, `before_turn()`, `modify_speed()`, `modify_movement()`.
- **menu_state.py**: `MenuState` enum (NONE, CHAR_SHEET, INVENTORY, SKILLS, EQUIPMENT, ITEM_MENU, COMBINE_SELECT, LOG).
- **event_bus.py**: EventBus for decoupled event publishing.

### Data-Driven Design

- Enemy stats, AI types, special attacks, and spawn tables live in **enemies.py** as declarative data.
- Item definitions and recipes live in **items.py**.
- Monster spawning uses zone-based spawn tables; dungeon dimensions and spawning constants defined in **config.py**.

## Key Design Patterns

### AI State Machine

AI modes are stateless; each turn `do_ai_turn()` evaluates transition conditions and dispatches the action mapped to the current AIState. Modes:
- **meander**: Drift toward player, attack adjacent.
- **wander_ambush**: Wander until player in sight radius, then chase.
- **passive_until_hit**: Ignore player until damaged.
- **room_guard**, **alarm_chaser**, **escort**, **hit_and_run**, **female_alarm**: See enemies.py for details.

### Entity as Container

`Entity` unifies player, monsters, items, and cash. Type discriminated via `entity_type` field. Optional fields (enemy_type, base_stats, ai_type, sight_radius, special_attacks, etc.) used only by monsters.

### Status Effects as Lifecycle Hooks

Status effects are objects (not dicts) with pluggable hooks. Old dict-based effects auto-upgraded on first access for backward compatibility.

### Menu System

Single `menu_state` enum controls which overlay is rendered. `render_all()` dispatches to the appropriate `render_*_menu()` function.

## Important Notes

### FOV and Visibility
- FOV computed once per player move via tcod.map.compute_fov() (can upgrade to shadowcasting).
- `dungeon.visible` (current turn), `dungeon.explored` (persistent). Render respects both.

### Combat
- Damage formula: `max(1, attacker.power - defender.defense)`.
- Player power derived from equipped weapon or base power + STR scaling.
- Status effects (stun, fear) modify damage, movement, or skip turn entirely via hooks.

### Item Pickup & Dropping
- Player walks onto item tile → item auto-picked into inventory.
- Manual drop via menu (sets item on ground as Entity).
- Equipable items in weapon/armor/accessory slots modify stats via `modify_stats()`.

### Permadeath
- Player dies → `engine.game_over = True` → main loop stops (no respawns or continues).

## Testing

- **test_game.py**: Core mechanics (initialization, movement, combat, pickup, permadeath).
- **test_jerome.py**, **test_niglet.py**, **test_thug.py**: Individual enemy behavior tests.
- Run all: `python -m pytest test_*.py -v`

## Common Tasks

### Adding a New Enemy
1. Create a `MonsterTemplate` entry in `enemies.py` MONSTER_REGISTRY with a unique key (e.g., "zombie").
2. Add the key + weight to `ZONE_SPAWN_TABLES` under zones where it spawns.
3. Run `validate_registry()` to catch typos and bad ranges.
4. If custom AI or special attacks needed, define in the template; see existing enemies for examples.

### Adding a New Item
1. Add entry to `ITEM_DEFS` dict in **items.py** with category, char, color, and effects.
2. If equippable, set `equip_slot` and stat bonuses (power_bonus, defense_bonus, etc.).
3. If usable, define `use_verb` (e.g., "Smoke") and `use_effect` dict.
4. Item automatically appears in dungeon via spawn tables when loot rolls hit its weight.

### Adding a New Menu
1. Add enum value to `MenuState` in **menu_state.py**.
2. Add condition in `engine.process_action()` to set `menu_state`.
3. Add corresponding `render_*_menu()` function in **render.py** called from `render_all()`.

### Debugging Monster AI
- Check `ai_type` and `AIState` enum value; set in enemies.py template.
- Use `prepare_ai_tick()` output (creature_positions, step_map) to verify pathfinding.
- Add print statements in `do_ai_turn()` to trace state transitions.

## Known Limitations & Future Work

- FOV uses simple distance check; shadowcasting recommended for complex room layouts.
- Floors 2–4 are placeholders (identical to floor 1).
- Item placement purely random; unique room encounters planned.
- Inventory system basic; item stacking not yet implemented.

## Code Style

- Snake_case for functions, variables, keys.
- CamelCase for classes.
- Dataclasses (`@dataclass`) for structured data (MonsterTemplate, SpecialAttack, etc.).
- Enums for state (AIState, MenuState, EffectKind, EffectCategory).
- Type hints on function signatures.
- Docstrings on classes and public functions.
