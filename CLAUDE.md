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

**Run single test file:**
```bash
python -m pytest test_food_system.py -v
```

**Install dependencies:**
```bash
pip install -r requirements.txt
```

## Project Overview

**NIGRL** is a traditional roguelike game engine written in Python using the tcod library (libtcod bindings). It features permadeath, dungeon generation, enemy AI, crafting, equipment, guns, mutations, and faction systems. Two zones: "Crack Den" (4 floors) and "Meth Lab" (in development, with toxicity/radiation mechanics and faction enemies).

## Architecture

### Core Files

- **nigrl.py**: Entry point. Sets up tcod context, loads tileset, runs main loop.
- **engine.py**: `GameEngine` class. Central hub for game state, turn management, action processing, and game events via EventBus. Delegates combat, inventory, spells, guns, items, and XP to extracted modules.
- **entity.py**: `Entity` class. Universal representation for players, monsters, items, and cash piles. Type discriminated via `entity_type` field. Includes toxicity, radiation, meth resource fields for Meth Lab zone.
- **dungeon.py**: `Dungeon` class with procedural generation (rooms + corridors), FOV computation, tile management, and entity spawning.
- **render.py**: Multi-panel tcod renderer. Left panel (stats/inventory), center (map/FOV), right (inventory/crafting). All UI menus rendered as overlays.
- **input_handler.py**: Converts tcod key events to action dicts.
- **config.py**: Global constants (screen size, dungeon dimensions, spawn rates, UI layout, equipment slots).

### Extracted Engine Modules

These were extracted from `engine.py` and take `engine` as first parameter:

- **combat.py**: Combat resolution, toxicity damage multipliers, death split/creep spawning, swagger defence calculation.
- **gun_system.py**: Gun targeting (cursor-based), firing, reloading, ammo management, fire mode toggling (accurate/fast), cone AOE resolution. Gun skill XP (Gatting, Sniping, Drive-By).
- **inventory_mgr.py**: Item pickup, stacking, deep fryer operations, equipment management. Sorts by category (tool → equipment → material → consumable → ammo).
- **item_effects.py**: Item use/effect dispatch, strain effects, ring/chain randomization, item-triggered skill XP.
- **spells.py**: Spell/ability execution, entity targeting, weapon reach, ability targeting modes.
- **xp_progression.py**: XP gain functions for all skill trees. Tracks skill unlock notifications.

### Game Systems

- **ai.py**: Behavioral state machine with AIState enum (IDLE, WANDERING, CHASING, FLEEING, ALERTING). Each AI mode declaratively specified. Central functions: `prepare_ai_tick()`, `do_ai_turn()`.
- **enemies.py**: `MonsterTemplate` dataclass-based registry system. Declarative enemy definitions with validation via `validate_registry()`. Supports variants, special attacks, on-hit effects, spawn tables per zone, and faction enemies (Aldor/Scryer).
- **items.py**: Item definition dict + crafting recipes. Factory function `create_item_entity()` instantiates items as Entity objects linked via `item_id`.
- **foods.py**: Food item definitions (`FOOD_DEFS`) separate from `items.py`. Foods require multi-turn eating; effects apply on completion. Effect types: `heal`, `hot` (HoT), `speed_boost`, `hot_cheetos`.
- **hazards.py**: Factory functions `create_crate()` and `create_fire()`. Hazards use `entity_type="hazard"` with custom graphical tiles (`0xE000` crate, `0xE001` fire).
- **abilities.py**: `AbilityDef` (declarative) + `AbilityInstance` (runtime). `ABILITY_REGISTRY` keyed by string id. `TargetType` enum: SELF, SINGLE_ENEMY_LOS, LINE_FROM_PLAYER, AOE_CIRCLE, ADJACENT. `ChargeType` enum: INFINITE, PER_FLOOR, TOTAL, ONCE, FLOOR_ONLY. Abilities granted via `engine.grant_ability()`.
- **loot.py**: Zone-based loot generation. `generate_floor_loot(zone, floor_num, player_skills)` returns `(item_id, strain_or_None)` tuples.
- **stats.py**: `PlayerStats` class. Six stats: Constitution, Strength, Book-Smarts, Street-Smarts, Tolerance, Swagger. 45 points distributed across 5 stats (each [6,12]); Swagger starts at 8 independently. Defence formula: `swagger_defence = int((effective_swagger - 8) / 2)`. Also tracks faction reputation, dodge chance, spell damage, tox/rad resistance, briskness, DR.
- **skills.py**: XP-based progression across 25 skill trees. Skills unlock perks (stat bonuses, passives, activated abilities) at level thresholds. Dual XP tracking: potential_exp (earned passively) converted to real_exp via skill_points.
- **effects.py**: Central status effect system. Base `Effect` class with lifecycle hooks: `apply()`, `tick()`, `expire()`, `before_turn()`, `modify_movement()`, `modify_energy_gain()`, `modify_incoming_damage()`, `on_player_melee_hit()`. Effects use `@register` class decorator. 40+ concrete effect subclasses.
- **mutations.py**: Radiation mutation system. Per-tick chance scales with rad level (0.1% per 50 rad). Three tiers: weak (50+ rad), strong (125+ rad), huge (250+ rad). 67% bad / 33% good polarity. Mutations are permanent stat/skill/equipment changes. Rad consumed on mutation.
- **zone_generators.py**: Zone generation registry. Delegates to zone-specific `generate()` and `spawn()` callables. Room types: Rect, L, U, T, Hall, Oct, Cross, Diamond, Cavern, Pillar, Circle.
- **menu_state.py**: `MenuState` enum (NONE, CHAR_SHEET, INVENTORY, SKILLS, EQUIPMENT, ITEM_MENU, COMBINE_SELECT, LOG, GUN_TARGETING, ENTITY_TARGETING, etc.).
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

Status effects are objects (not dicts) with pluggable hooks defined in **effects.py**. Each effect subclass overrides lifecycle methods. Effects are applied via `apply_effect(entity, effect_name, **kwargs)` and registered with the `@register` decorator.

### Menu System

Single `menu_state` enum controls which overlay is rendered. `render_all()` dispatches to the appropriate `render_*_menu()` function.

### Adjacent Targeting

ALL abilities that target an adjacent tile use quick-select (not cursor targeting). `TargetType.ADJACENT` auto-fires if 1 adjacent enemy, otherwise enters entity targeting cycle (left/right + Enter).

## Important Notes

### Stat System
- 5 stats (CON, STR, BKS, STS, TOL) share 45 points, each clamped to [6, 12].
- Swagger starts at 8 independently. Defence: `int((effective_swagger - 8) / 2)`. At 8 = 0, 10 = +1, 12 = +2, 6 = -1, 4 = -2.
- Three modifier layers: permanent (`_base`), ring bonuses, temporary effects. `effective_*` properties sum all three.

### Combat
- Damage formula: `max(1, attacker.power - defender.defense)`.
- Player power derived from equipped weapon or base power + STR scaling.
- Meth Lab zone: toxicity multiplies incoming damage via `1.0 + (tox/100)^0.6`.
- Status effects (stun, fear) modify damage, movement, or skip turn entirely via hooks.

### Gun System
- Sidearm slot in `EQUIPMENT_SLOTS`; `Entity` has `current_ammo`/`mag_size` fields.
- `MenuState.GUN_TARGETING` for cursor-based ranged targeting; TAB toggles accurate/fast mode.
- Gun class: "small" → sidearm only, "medium"+ → weapon only.
- Keybinds: F=fire, Shift+R=reload, Shift+F=swap, TAB=toggle mode.
- AOE rule: all valid targets have equal chance; one target hit at most `ceil(num_shots / 2)` times.

### Faction System
- Two factions: Aldor and Scryer. Reputation tracked as integer values in `PlayerStats.reputation`.
- Tiers: Archenemy → Hated → Unfriendly → Neutral → Friendly → Hombre → One of Their Own.
- Faction enemies spawn in Meth Lab zone.

### FOV and Visibility
- FOV computed once per player move via tcod.map.compute_fov().
- `dungeon.visible` (current turn), `dungeon.explored` (persistent). Render respects both.

### Item Pickup & Dropping
- Player walks onto item tile → item auto-picked into inventory.
- Manual drop via menu (sets item on ground as Entity).
- Equipable items in weapon/armor/accessory slots modify stats.

### Permadeath
- Player dies → `engine.game_over = True` → main loop stops (no respawns or continues).

## Testing

- **test_game.py**: Core mechanics (initialization, movement, combat, pickup, permadeath).
- **test_jerome.py**, **test_niglet.py**, **test_thug.py**, **test_baby_momma.py**, **test_jungle_boyz.py**: Individual enemy behavior tests.
- **test_jerome_eating.py**: Jerome's chicken-eating heal mechanic.
- **test_food_system.py**: Food eating mechanics and effects.
- **test_bic_torch.py**, **test_fireball_wizard_bomb.py**, **test_blackkk_magic_xp.py**: Ability/spell system tests.
- **test_smoking_skill_perks.py**, **test_stealing_xp.py**, **test_ring_replacement.py**, **test_skill_unlock_notifications.py**: Skill and XP system tests.
- **test_targeting_framework.py**: Ability targeting tests.
- **test_stack_display.py**: Item stack display formatting tests.
- **test_gun_system.py**: Gun creation, equipping, firing, reloading, AOE mechanics.
- **test_faction_enemies.py**: Meth Lab faction enemies (Scryer/Aldor variants, law enforcement, faction AI).
- **test_meth_lab_enemies.py**: Toxic enemies (Covid-26, Purger, Toxic Slug, Sludge Amalgam, Chemist).
- **test_mutations.py**: Radiation mutation tiers, polarity, stat/skill/equipment mutations, rad consumption.
- Run all: `python -m pytest test_*.py -v`
- Run single test file: `python -m pytest test_food_system.py -v`

## Common Tasks

### Adding a New Enemy
1. Create a `MonsterTemplate` entry in `enemies.py` MONSTER_REGISTRY with a unique key.
2. Add the key + weight to `ZONE_SPAWN_TABLES` under zones where it spawns.
3. Run `validate_registry()` to catch typos and bad ranges.
4. If custom AI or special attacks needed, define in the template; see existing enemies for examples.

### Adding a New Item
1. Add entry to `ITEM_DEFS` dict in **items.py** with category, char, color, and effects. For food items, add to `FOOD_DEFS` in **foods.py** instead.
2. If equippable, set `equip_slot` and stat bonuses (power_bonus, defense_bonus, etc.).
3. If usable, define `use_verb` (e.g., "Smoke") and `use_effect` dict.
4. Tag with `"zones": ["crack_den"]` and set a `weight`; item will appear via `loot.py` generation.

### Adding a New Ability
1. Add an `AbilityDef` entry to `ABILITY_REGISTRY` in **abilities.py** with `target_type`, `charge_type`, and an `execute` callable.
2. Grant it via `engine.grant_ability(ability_id)` from an item use effect or skill unlock.
3. No other files need changing — the targeting/UI system dispatches based on `target_type`.

### Adding a New Menu
1. Add enum value to `MenuState` in **menu_state.py**.
2. Add condition in `engine.process_action()` to set `menu_state`.
3. Add corresponding `render_*_menu()` function in **render.py** called from `render_all()`.

### Adding a New Status Effect
1. Create a subclass of `Effect` in **effects.py** with `@register` decorator.
2. Override lifecycle hooks as needed (`apply`, `tick`, `expire`, `before_turn`, `modify_incoming_damage`, etc.).
3. Set `category` (buff/debuff) and `priority`. Apply via `apply_effect(entity, "effect_id")`.

### Debugging Monster AI
- Check `ai_type` and `AIState` enum value; set in enemies.py template.
- Use `prepare_ai_tick()` output (creature_positions, step_map) to verify pathfinding.
- Add print statements in `do_ai_turn()` to trace state transitions.

## Known Limitations & Future Work

- FOV uses simple distance check; shadowcasting recommended for complex room layouts.
- Inventory uses item stacking with count-based display.
- Guns not in loot tables yet — spawn via dev menu for testing.

## Code Style

- Snake_case for functions, variables, keys.
- CamelCase for classes.
- Dataclasses (`@dataclass`) for structured data (MonsterTemplate, SpecialAttack, etc.).
- Enums for state (AIState, MenuState, EffectKind, EffectCategory).
- Type hints on function signatures.
- Docstrings on classes and public functions.
