---
name: Electrodynamics Skill Trees
description: 5 linear L1-L6 designs for the Electrodynamics (lightning) skill tree
type: project
---

## Electrodynamics Skill Tree Designs (2026-03-26)

Doc: `nigrl-ideas/electrodynamics-skill-tree-designs.txt`
XP source: 1.5/dmg + 10/shocked stack applied. Hook: _gain_electrodynamics_xp() in xp_progression.py.
Mirrors Cryomancy XP pattern exactly.

### New Effects
- ParalyzedEffect (id="paralyzed"): full hard CC, 3t, does NOT break on damage. Unlike freeze.
  Shocked timer suspended while paralyzed (tick() extends shocked.duration by 1 each tick).
- StaticChargeEffect (id="static_charge"): player buff, stacks 1-5, +2 dmg/stack to next lightning spell.
  Consumed (all stacks) on any lightning spell fire. Duration 12t shared timer.
- StormBrandedEffect (id="storm_branded"): enemy debuff. Every 3 turns: 2+BKS/4 dmg + 1 shocked.
  One active brand at a time. engine._storm_brand_target: Entity | None.

### New Abilities
- zap_inf: Zap as INFINITE (CD 5). lightning_bolt: 7+BKS, 2 shocked, PER_FLOOR 5, range 8.
- discharge: SELF, PER_FLOOR 3, adjacent AoE, 4+BKS + 2 shocked.
- thunder_clap: SELF, PER_FLOOR 3, adjacent AoE, 6+STR + 2 shocked + knockback 1 tile.
- storm_brand: SINGLE_ENEMY_LOS, INFINITE (CD 8), applies storm_branded, range 6.
- volt_switch: SINGLE_ENEMY_LOS, PER_FLOOR 2, 8+STS + 3 shocked + random teleport 3-8 tiles.
- herald_of_thunder: passive ONCE grant, fires from kill handler (NOT user-activated).
  Guard: engine._herald_firing flag prevents recursive kill-herald loops.
- electric_terrain: SELF, PER_FLOOR 1, 8-turn global state (engine._electric_terrain_turns).
  Every 2 turns: all visible enemies get 1 shocked + 2+BKS/4 dmg.
- brand_detonate: SELF, PER_FLOOR 2, consumes storm_branded for 10+BKS+(shocked*5) damage.

### Conductivity Passive Flag
player_stats.conductivity: bool. After any player-sourced shocked apply, adjacent enemies
get 1 shocked stack. NOT recursive by default. Take 3 L5 (Lightning Rod) enables one-level recursion.
Implementation: in apply_effect() for "shocked", post-application, if conductivity flag set.
Adjacency: Chebyshev 1. Guard against thrall/allied entities.

### 5 Designs Summary
| Design           | Primary Stat  | Identity                    | Stat Totals                  |
|------------------|---------------|-----------------------------|------------------------------|
| Take 1: Storm Caller | BKS+STS  | Max stacks → Paralysis CC   | +4 BKS, +2 TOL, +2 STS      |
| Take 2: Street Brand | BKS      | Brand DoT + detonation      | +6 BKS, +2 TOL, +2 STS      |
| Take 3: Conductor    | CON+TOL  | Chain spread + Static Field | +3 CON, +3 TOL, +1 STR      |
| Take 4: Volt Striker | STS      | Melee hybrid + teleport     | +6 STS, +2 CON, +1 BKS      |
| Take 5: Overloaded   | BKS      | Static charge resource loop | +2 CON, +7 BKS, +2 TOL, +1 STS |

### Key Design Decisions
- Shocked amplifies MELEE DAMAGE TAKEN (not spell). Strategies reward closing in.
- Paralysis does NOT break from damage (unlike Freeze). 3 turns of free play.
- Electric Terrain is a global engine state, not an Effect subclass — similar pattern to
  engine._electric_terrain_turns: int. Don't put terrain as an effect on the player.
- Herald of Thunder must use _herald_firing guard flag to prevent recursive kill chains.
- Volt Switch fail case: if no valid teleport tile, damage + shocked still apply.
- Take 4 Grounded (L3): permanent shocked immunity for player (permanent, not timed).
