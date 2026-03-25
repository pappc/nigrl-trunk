---
name: Elemental Spell Compendium — Key Facts
description: Effects, entity fields, engine fields, combo chart, and Blackkk Magic direction from spell_compendium_elemental.txt
type: project
---

Design doc: `nigrl-ideas/spell_compendium_elemental.txt`
48 abilities across 9 schools (4 per school) + 3 cross-element meta-spells.
Primary stat: Book-Smarts (floor(BKS/4) bonus damage standard).
Secondary stats: STR (earth/wind/physical), SWG (holy/light), TOL (frost/tank), CON (earth/tank).

## Effects
EXISTING effects used: ignite, chill, shocked, wet, slow, stun, confuse, dot, fear.
NEW effects introduced (16 total): frozen, arcane_mark, earthbound, shadowed, luminous,
  poisoned, plagued, windswept, phoenix_coat, faraday_cage, stone_skin, sacred_ground,
  kinetic_shield, tailwind, catalyst, acid_corroded.

## Entity / Engine Fields
NEW entity fields: entity.brittle (bool), entity.shadowed (bool).
NEW engine fields: force_walls dict, toxic_clouds dict, hurricane state, sacred_tile,
  player_faraday bool, stone_skin_active bool, elements_used set, pending_rockslide dict,
  weather_report_active bool.

## Element Combo System
Conditions: Wet, Burning, Chill, Shocked, Frozen, Poisoned, Earthbound, Arcane Mark,
  Luminous, Shadowed, Windswept interact when secondary element hits conditioned target.
Full combo chart is in the design doc. Key combos:
  Wet + Lightning → SURGE (double dmg, +2 shocked stacks, strips Wet)
  Wet + Ice       → quick FREEZE (half-duration frozen)
  Burning + Ice   → QUENCH (strip ignite, +3 cold bonus dmg)
  Frozen + Phys   → SHATTER (consume brittle, +50% damage)
  Luminous + Holy → SMITE doubled (see Smite E-H-04)
  Shadow + Holy   → PURGE (strip shadowed, +8 damage)
  Poisoned + Fire → BOIL (2x poison tick rate for 3 turns)
  Windswept + Fire→ INFERNO (+3 ignite stacks — hurricane fans flames)

## Blackkk Magic Tree Direction
Suggested progression: multi-element arcane caster.
  L1: element choice (one of 6 low-tier spells)
  L2: Arcane Bolt + Life Tap (universal)
  L3: mid-tier element + Elemental Catalyst
  L4: Kinetic Shield + Faraday Cage + specialism
  L5: high-tier element capstone + Prism Strike if 4+ elements used
