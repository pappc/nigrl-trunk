---
name: BkSmt/Radiation Strains
description: Three BkSmt-focused radiation strains for Meth Lab: Fallout Scholar, Dead Star, Isotope
type: project
---

## BkSmt/Radiation Strains (3 strains, 2026-03-13)

Full design: `nigrl-ideas/bksmt_radiation_strain_designs.txt`

3 strains: Fallout Scholar, Dead Star, Isotope.

### Fallout Scholar
- Color: (160, 220, 100) — sickly academic yellow-green
- Fantasy: Radiation hoarder. High rad = strong spells (temp spell_damage). Nuclear Thesis spends 75 rad for BkSmt*8 + sd + rad_bonus single-target nuke.
- Perm BkSmt: On roll 92-100 (~9% chance) +1 permanent BkSmt. Roll 1-9 loses -1 permanent BkSmt (high stakes).
- Rad flow: gains 25-60 rad on good rolls; loses 20-35 rad on mid rolls; gains 60-100 on bad rolls (punishment).
- Key new ability: "nuclear_thesis" — SINGLE_ENEMY_LOS, INFINITE, costs 75 rad to fire.

### Dead Star
- Color: (80, 60, 180) — deep cold violet
- Fantasy: Deferred detonation. Bank radiation across multiple smokes, then Rad Nova for massive AOE.
- Perm BkSmt: Granted when roll 88-100 PUSHES player PAST 125 rad threshold (requires prior buildup). Requires tracking rad before and after add_radiation call.
- Rad flow: gains 20-60 rad on good rolls; loses 30-50 rad on bad rolls. Clean binary.
- Key new ability: "rad_nova" — SELF, INFINITE, costs ALL radiation (min 50 to fire). AOE_CIRCLE r=3, Chebyshev distance. Damage = rad_total//3 + BkSmt*4 + sd.

### Isotope
- Color: (200, 100, 60) — irradiated amber-orange
- Fantasy: Tag-and-nuke. Smokes spread radiation to nearby enemies. Chain Reaction bounces between irradiated targets. Kill irradiated enemies for perm BkSmt.
- Perm BkSmt: 15% chance on killing any enemy with radiation > 0 AND player possesses "chain_reaction" ability. Combat-integrated, not roll-integrated.
- Rad flow: player gains 20-45 rad on good rolls; enemies irradiated by 20-80 rad on most rolls. Roll 1-14 reversal: player +70 rad, enemies LOSE rad.
- Key new ability: "chain_reaction" — SINGLE_ENEMY_LOS, INFINITE, costs 60 rad. Bounces to 3 irradiated enemies within 3 tiles (5 if primary killed). Damage = BkSmt*5 + sd primary; BkSmt*3 + sd + enemy_rad//5 per bounce.

### New Systems Required

**entity.py**: monsters need entity.radiation field (int, default 0).
**engine.py**: enemy radiation decay -10/turn; on-kill BkSmt proc for Isotope.
**abilities.py**: add "nuclear_thesis", "rad_nova", "chain_reaction" to ABILITY_REGISTRY.
**effects.py**: "spell_damage_temp" effect class (apply/expire pattern).
**render.py**: green-tint irradiated enemies (entity.radiation > 0 in FOV).
**items.py**: add all three strains to STRAINS, XP tables, tolerance thresholds, STRAIN_TABLES, get_strain_color.
**loot.py**: add to meth_lab floor 5-6 loot tables.

### Key Pattern: Rad-Spending Abilities
All three radiation-spending abilities share a pattern:
- validate() returns error string if insufficient rad
- execute / execute_at spends rad via remove_radiation() or direct assignment
- All three are is_spell=True, INFINITE charges (gated by rad resource)
- Damage formula includes total_spell_damage as additive component

### Key Pattern: Perm BkSmt Acquisition
Three different mechanisms used across the three strains — intentionally distinct:
1. Roll table direct grant (Fallout Scholar — ~9% per smoke, with risk of loss)
2. Resource threshold crossing (Dead Star — requires prior buildup + good roll)
3. Combat proc on irradiated kill (Isotope — ~15% per irradiated kill)
These three mechanisms should be the canonical templates for future perm-stat designs.

### Tolerance / Smoking/Rolling XP
All three: first_bonus_roll=11, add_bonus_roll=6, Smoking XP=125, Rolling XP=125.
(Matches Meth Lab standard set by Iron Lung / Skywalker OG / Street Scholar.)
