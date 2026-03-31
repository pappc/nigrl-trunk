---
name: Unique Equipment Designs
description: 10 build-defining unique items (PoE/WoW legendary-style) for NIGRL — new fields, new hooks, new effects
type: project
---

# Unique Equipment Designs

Design doc: `nigrl-ideas/unique-equipment-designs.txt`

## The 10 Items

| # | Name | Slot | Core Mechanic | Zone |
|---|------|------|---------------|------|
| 1 | Dirty South Redux | Weapon (stabbing) | Filth counter; bypass-armor damage + kill extends buffs; taking dmg decays filth | Crack Den |
| 2 | The Baron's Iron | Weapon (beating) | str_scaling linear base=0 = full STR as damage; STR temp effects doubled | Crack Den |
| 3 | Pookie Stick | Weapon (stabbing) | 40% on-hit: random drug-skill XP + random status effect on both attacker and defender | Crack Den |
| 4 | Fentanyl Special | Sidearm (gun) | 1 shot/floor; damage = current missing HP; armor-piercing | Meth Lab |
| 5 | Dead Homie's Chain | Neck | On-kill absorb: STR/3, CON/3, power/4 as temp bonuses for the floor | Crack Den |
| 6 | Shadowboxer Wraps | Feet | Gap Close (auto-step on reach attacks), Ghost Step (free step on blocked hit), Combo→Slip at 5 hits | Crack Den |
| 7 | Prophet's Beads | Neck | 1/floor cheat-death: set HP=1, scatter all gear on ground, apply feared+slow | Crack Den |
| 8 | Auntie's Pocket Bible | Ring | On SP-spend: 25% chance +2 temp stat (20t); 10% room reveal; +3 BkSmt base | Crack Den |
| 9 | Glass Eye Ring | Ring | Omniscient enemy positions (faded render); instant aggro all enemies in FOV | Meth Lab |
| 10 | Uncle Ray's Cookin' Hat | Hat | Instant eat, doubled food effects, auto-consume on pickup (incl. negative foods!) | Both |

## New Engine Fields / Systems

### entity.py
- `dirty_south_filth: int = 0` — for Dirty South Redux weapon
- `shadowbox_combo: int = 0` — for Shadowboxer Wraps

### items.py
- `unique_id: str` — machine-readable unique identifier on item def
- `unique_item: bool` — if True, loot.py gates to one drop per run
- `on_kill_drug_drop: float` — chance (0-1) to drop a random drug consumable on kill

### abilities.py
- `fentanyl_special_shot` — PER_FLOOR 1, SINGLE_ENEMY_LOS, damage = missing HP, ignores armor

### effects.py
- `DivineOverflowBuff` (id="divine_overflow_buff") — timed stat bonus; apply adds, expire subtracts
  - Stores: stat: str, amount: int
- `SlipEffect` (id="slip") — if not yet implemented: +15 energy/tick, +10 dodge_chance; expire reverses

### loot.py
- `engine.dropped_unique_ids: set[str]` — initialized at run start; unique_item items check this before dropping

### inventory_mgr.py / engine.py
- Item entity: `_prophecy_charge: bool = True` — Prophet's Beads per-floor charge flag (getattr pattern)

### engine.py
- `_glass_eye_equipped() -> bool` helper
- Death interception block for Prophet's Beads (before game_over is set)
- entity_died handler for Dead Homie's Chain
- Floor transition: reset _prophecy_charge, reset dirty_south_filth if weapon unequipped

## Key Implementation Patterns

### "unique_id" dispatch pattern (combat.py)
```python
if wdefn.get("unique_id") == "dirty_south_redux":
    # item-specific logic
```
This is the standard pattern for all weapon unique effects in combat.py.

### Food effect multiplier pattern (foods.py / item_effects.py)
Add `effect_multiplier: float = 1.0` parameter to food effect application functions.
Uncle Ray's Cookin' Hat passes 2.0. All numeric amounts multiplied by this value.

### Scatter gear (Prophet's Beads)
Get current room from engine._get_current_room(px, py), find walkable tiles in room,
place each item entity on a separate tile via dungeon.add_entity(). Items become
floor pickups again.

## Balance Reference
- Fentanyl Special max shot: ~129 damage (CON 10, 1 HP). Per-floor limit prevents abuse.
- Dead Homie's Chain: ~+7 STR, +5 CON (effective only), +8 spell dmg after 10 kills. Resets each floor.
- Prophet's Beads: 0 armor cost is real. Post-proc state (1 HP, unequipped, feared 3t, slow 5t) is extremely dangerous.
- Dirty South Redux filth at max (10): +5 bypass-armor damage per hit. Decays 2 per hit taken.
- Uncle Ray's Cookin' Hat: Protein Powder doubling is the most dangerous power spike — consider cap at 1.5x for perm effects.
