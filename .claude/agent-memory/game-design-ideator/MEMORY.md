# Game Design Ideator — Agent Memory

## Skill Trees Overview (from skills.py)

17 total skill trees. 11 are fully placeholder. 6 have partial content (up to L3).
See `nigrl-ideas/skills_and_perks_table.txt` for the complete reference table.

Designed perks summary:
- Smoking L1-3: Phat Cloud (passive TBD), Stat Up! (+2 Tol/+2 Con), Roach Fiend (+2 Tol)
- Rolling L1-3: Stat Up! (+1 Str/+1 Tol), Seeing Double (passive TBD), Spectral Paper (passive TBD)
- Pyromania L4: Neva Burn Out (passive TBD) — levels 1-3 are placeholder
- Stabbing L1-3: Gouge (activated, adjacent stun ability), Stat Up! (+2 Street Smarts), Windfury (passive extra-hit)
- Alcoholism L1-3: Im Drinkin Here (passive TBD), Stat Up! (+2 Tol), Throw Bottle (activated, ability)
- Munching L1-3: Fatter (+1 Con), Even Fatter (+2 Con), Better Later (passive TBD)

Fully placeholder (no perks at all):
  Negromancy, Blackkk Magic, Beating, Smacking, Stealing, Jaywalking,
  Deep-Frying, Drinking, Dismantling, Abandoning, Meth-Head

## XP Curve Reference

DEFAULT_EXP_CURVE = [200, 400, 600, 800, 2000, 6000, 15000, 25000, 100000, 500000]
Total to max: 649,000. Same curve applies to all skill trees.

Book Smarts controls SP gain rate: min(0.5, 0.1 + 0.3 * sqrt(bksmt / 80))
At bksmt=0: 10% of potential XP becomes SP. At bksmt=50: ~34%.

## Output Directory

All design docs saved to: `nigrl-ideas/` (relative to project root).
Absolute path: C:/Users/pappc/claude-projects/nigrl-trunk/nigrl-ideas/

## Perk Type Vocabulary (skills.py conventions)

- "none"      → placeholder, does nothing
- "stat"      → effect dict has stat keys (e.g., {"tolerance": 2, "constitution": 2})
- "passive"   → always-on; effect=None means mechanically unimplemented (name-only seed)
- "activated" → effect dict has {"ability": "ability_id"} — grants an AbilityDef entry

## Stat Names (for perk effect dicts)

constitution, strength, street_smarts, book_smarts, tolerance, swagger

## L4/L5 Perk Designs

Full L4/L5 designs for all 14 trees with L1-L3 + full L1-L5 for Negromancy and
Meth-Head: see `nigrl-ideas/skill_perks_L4_L5.txt`.

Stat bonuses from "stat" perk_type can be NEGATIVE (e.g., constitution: -1).
This is valid — Negromancy L2 and Meth-Head L2 deliberately use negative BkSmt/CON.

## Balance Reference Points

- Player base stats: 5-12 range at start, sum=46 across 6 stats
- Player max HP: 30 + CON * 10. At CON 10: 130 HP.
- Swagger defence: int((effective_swagger - 8) / 2). Starts at 8 → 0 defense. Every +2 above 8 = +1, every -2 below 8 = -1.
- Crit chance: street_smarts * 3%. At start: 15%-36%.
- Enemy HP typical: base_hp + con*5. Tweaker (con 2-4): 10-20 HP.
- Enemy damage typical: 4-8 per hit on floor 1-2. Defense 0-3.
- Energy system: 100 energy/tick = base speed. +30 = ~23% faster vs baseline.
- Largest single STR grant in any perk: +4 (Meth-Head L2, Beating L5).
- Highest CON tree: Munching (+9 total L1-L5). Highest STR tree: Beating (+9).

## New Effects Introduced in L4/L5 Designs

effects.py additions needed:
  confused     — 40% chance to wander randomly instead of AI action
  cough        — stun alias (skip turn), 4t, 15% chance/turn in Hot Box
  wire         — +30 energy/tick; expires from damage → triggers crash
  crash        — -20 energy/tick, 5t; triggered by Wire expiry from damage
  rage         — +50% dmg dealt, +50% dmg taken, blocks Wire→Crash
  burned_out   — -15 energy/tick, 3t; blocks Wire gain; follows Rage expiry
  intimidated  — cannot move toward player, 5t
  shook        — -30 energy/tick + -2 damage, 15t; from Top of Food Chain
  slip         — +15 energy/tick + +10% dodge, 6t; from Hit-and-Run
  clean_slate  — +5 dmg, +5 armor, +15 energy/tick, 15t; from Burn Bridge
  staggered    — -30 energy/tick, +15% skip-turn chance, 10t; from Last Call

## New Abilities Introduced in L4/L5 Designs

ABILITY_REGISTRY additions needed (ability_id: key details):
  hot_box        — SELF, PER_FLOOR 1, Smoking L5
  reap           — SINGLE_ENEMY_LOS, INFINITE (CD 15), Negromancy L3
  raise_dead     — SINGLE_ENEMY_LOS (targets dead entity), PER_FLOOR 2, Neg L5
  grease_bomb    — AOE_CIRCLE r=3, PER_FLOOR 2, Deep-Frying L5
  wrecking_ball  — SELF, PER_FLOOR 1, Dismantling L5
  rage_quit      — SELF, PER_FLOOR 2, Meth-Head L4
  burn_bridge    — SELF, PER_FLOOR 1, Abandoning L4
  last_call      — SELF, ONCE, Alcoholism L5

## Negromancy — Soul Shards Resource

engine.soul_shards: int 0-5. +1 on kill. Passive +1 flat damage per shard.
Consumed by Reap (2 shards) and Raise Dead (all shards).
fresh_corpse flag on Entity: set on death, timer=20 turns.
Thrall: alive=True entity with is_thrall=True, hp=1, MEANDER AI vs enemies.

## Meth-Head — Wire/Crash Loop

Wire (+30 energy/tick): gained on kill, stacks duration (max 40t).
Crash (-20 energy/tick, 5t): triggered when Wire expires from taking damage.
Rage L4: blocks Wire→Crash conversion; ends with Burned Out (3t, -15 speed).
Supernova L5: Wire crash shockwave = STR*2 to Chebyshev(1) enemies, no defense.

## Zone 2 — Meth Lab (Toxicity + Meth Meter)

Full details in: `.claude/agent-memory/game-design-ideator/zone2-meth-lab.md`
Design docs in: `nigrl-ideas/toxicity_mechanic.txt`, `crackhead_skill_variants.txt`,
  `toxicity_skill_variants.txt`

## Tox Resistance Items (Zone 2)

Full design in: `nigrl-ideas/tox-resistance-items.txt`
6 items across equipment and consumable categories:

  Painter's Respirator  — accessory, +20% passive res, -1 SWG
  Industrial Hand Soap  — food (3t eat), +30% temp res (40t), minor heal
  Hazmat Gloves         — ring, +15% passive res, 20% on-hit tox negation chance
  Charcoal-Filtered Bandana — accessory, +25% passive res, -2 sight_radius
  Cold Medicine         — consumable (instant), +35% temp res + +2 TOL + -2 STSMT (25t)
  Tinfoil Hat           — MOVED TO HAT SLOT — see tinfoil-hats.txt (HAT-06)
                          (was ring +30% cond; now hat +35% cond, same mechanic)

New item fields introduced: tox_resistance (int), on_hit_tox_reduction (float),
  sight_radius_mod (int), conditional_tox_resistance (dict).
New engine method needed: _recalculate_tox_resistance() — sums all sources.
New effect needed: ToxResistTempEffect.
New food effect type: "tox_resist_temp".
New consumable use_effect types: "tox_resist_temp", "stat_temp".
Use_effect may need to support a list of effect dicts (not just single dict).

## Hat Equipment Slot

Full design in: `nigrl-ideas/tinfoil-hats.txt`
12 hats across both zones. Equip slot: "hat". char: '^'.
Supports: power_bonus, defense_bonus, armor_bonus, stat_bonus, tox_resistance,
          conditional_tox_resistance (same mechanic as tox-resistance-items.txt).

Hat balance anchors:
  - armor_bonus cap: 15 (Hard Hat) — chains are primary armor source
  - Common hats: 1 minor-ring-equivalent in stat value, no tradeoffs
  - Rare hats: multi-stat OR conditional mechanic, sometimes negative tradeoffs
  - Tinfoil Hat: +35% cond tox resist (tox < 50), +1 BKS — Detox lane keystone
  - Triple-Layered Foil: +30% UNCONDITIONAL tox resist, -1 PWR, -2 SWG
  - Crown: RARE, +4 SWG +1 STSMT +2 PWR, no tradeoffs — Crack Den only
  - Hard Hat: +3 DEF +15 ARM +10% tox, -3 SWG -1 STSMT — tank hat, low-SWG builds
  - Shower Cap: +20% tox +2 TOL, -3 SWG — junk hat, free for low-SWG builds

Loot table: add "hat" bucket to crack_den and meth_lab zone configs in loot.py.
Zone 1-only hats: wave_cap, backwards_cap, crown.
Zone 2-only hats: tinfoil_hat, triple_foil_hat, foil_lined_durag, hard_hat, shower_cap.
Both zones: fitted_cap, durag, knit_beanie, bike_helmet.

## Gun Skill Trees

5 total trees designed. Full notes in:
  `.claude/agent-memory/game-design-ideator/gun-trees.md`
  Design docs: `nigrl-ideas/skill-gun-trees.txt`, `nigrl-ideas/skill-gun-firing-modes.txt`

Three standard trees (XP: gun damage dealt): Gang Violence, Trigger Discipline,
  Corner Store Hustler.
Two firing-mode trees: Mag Rat (FAST specialist), Dead Eye (ACCURATE specialist).
Prerequisite: gun_entity.fire_mode: str ("accurate"|"fast"). Toggle = free action.
Mixed perk effect dict (stat keys + "ability" key in same dict) is valid — engine
  must handle it. Munching L1 already does this as precedent.

## Stat-Scaling Strains

V2 design (CURRENT): `nigrl-ideas/stat-scaling-strains-v2.txt` — 30 strains, full Meth Lab integration.
Full lifecycle hooks, engine flags, and stat groupings: see `stat-scaling-strains-v2.md` (topic file TBD).
Key rules: tox as offensive resource; SWG strains need SWG investment; Mule's Back caps tox mult.

## Recent Design Docs Index

See individual topic files in `.claude/agent-memory/game-design-ideator/` for details.

  new-guns.md           — 12 new guns (2026-03-12); nigrl-ideas/new-gun-concepts.txt
  meth-lab-weapons.md   — 8 stab weapons (2026-03-13); nigrl-ideas/meth-lab-stab-weapons.txt
  str-rad-strains.md    — 5 STR/rad strains; nigrl-ideas/str_radiation_strain_designs.txt
  bksmt-rad-strains.md  — 3 BkSmt/rad strains; nigrl-ideas/bksmt_radiation_strain_designs.txt
  tox-tolerance-strains.md — 3 tox/TOL strains; nigrl-ideas/tox_tolerance_strain_designs.txt
  swagger-strains.md    — SWG strains V2 + High Society; nigrl-ideas/swagger_mutation_strain_designs_v2.txt
  spell-compendium-index.md — ability index; nigrl-ideas/spell_compendium.txt + spell_compendium_classics.txt
  meth-lab-drinks.md    — 10 new Meth Lab drinks (2026-03-15); nigrl-ideas/item-meth-lab-drinks.txt
  colored-dranks.md     — 14 colored dranks (2026-03-15); nigrl-ideas/item-colored-dranks.txt

Key design rules carried across all Meth Lab content:
  - No persistent per-run engine state in swagger strain designs (use effect hooks + charges)
  - Tox as offensive resource (strains-v2 paradigm)
  - AOE gun fire: ceil(num_shots/2) max hits per target (universal rule)
  spell_compendium_weird.txt       — 34 abilities, Sections W-A through W-L (WEIRD/BUSTED/RISKY)
  spell_compendium_elemental.txt   — 48 abilities, 9 element schools + cross-element system (2026-03-15)

## Elemental Compendium — Key Facts

Design doc: `nigrl-ideas/spell_compendium_elemental.txt`
48 abilities across 9 schools (4 per school) + 3 cross-element meta-spells.
Primary stat: Book-Smarts (floor(BKS/4) bonus damage standard).
Secondary stats: STR (earth/wind/physical), SWG (holy/light), TOL (frost/tank), CON (earth/tank).

EXISTING effects used: ignite, chill, shocked, wet, slow, stun, confuse, dot, fear.
NEW effects introduced (16 total): frozen, arcane_mark, earthbound, shadowed, luminous,
  poisoned, plagued, windswept, phoenix_coat, faraday_cage, stone_skin, sacred_ground,
  kinetic_shield, tailwind, catalyst, acid_corroded.
NEW entity fields: entity.brittle (bool), entity.shadowed (bool).
NEW engine fields: force_walls dict, toxic_clouds dict, hurricane state, sacred_tile,
  player_faraday bool, stone_skin_active bool, elements_used set, pending_rockslide dict,
  weather_report_active bool.

Element combo system: conditions (Wet, Burning, Chill, Shocked, Frozen, Poisoned, Earthbound,
  Arcane Mark, Luminous, Shadowed, Windswept) interact when secondary element hits a conditioned
  target. Full combo chart in the design doc.

Key combo pairs:
  Wet + Lightning → SURGE (double dmg, +2 shocked stacks, strips Wet)
  Wet + Ice       → quick FREEZE (half-duration frozen)
  Burning + Ice   → QUENCH (strip ignite, +3 cold bonus dmg)
  Frozen + Phys   → SHATTER (consume brittle, +50% damage)
  Luminous + Holy → SMITE doubled (see Smite E-H-04)
  Shadow + Holy   → PURGE (strip shadowed, +8 damage)
  Poisoned + Fire → BOIL (2x poison tick rate for 3 turns)
  Windswept + Fire→ INFERNO (+3 ignite stacks — hurricane fans flames)

Suggested Blackkk Magic tree direction: multi-element arcane caster.
  L1: element choice (one of 6 low-tier spells)
  L2: Arcane Bolt + Life Tap (universal)
  L3: mid-tier element + Elemental Catalyst
  L4: Kinetic Shield + Faraday Cage + specialism
  L5: high-tier element capstone + Prism Strike if 4+ elements used
