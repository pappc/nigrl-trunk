---
name: Graffiti Skill Tree
description: L1-L5 tile-painting skill tree centered on territorial control and graffiti culture
type: project
---

Full design in: `nigrl-ideas/graffiti-skill-designs.txt`

## Five Perks Summary

L1 — Tag (activated, ability: "tag"): Paint an adjacent tile red. Enemies on it take +20%
  incoming damage ("tagged" debuff, 2t linger after leaving). INFINITE charges, 50 energy.
  Tile cap: STS/2 (min 3). Graffiti tiles: char '%', color (220,60,60), hazard_type="graffiti".

L2 — Throw-Up (passive): Tag now paints plus-pattern (5 tiles). Tile cap becomes STS tiles.
  Player standing on own graffiti gets "home_ground" buff: +15% crit chance, +10 energy/tick,
  3t linger.

L3 — Burner (activated, ability: "burner"): 3-tile line of vivid blue graffiti. PER_FLOOR 2.
  Entry-triggered: enemies who walk ONTO a burner tile for first time get "captivated" (skip 1
  turn). Re-entry immune for 10t ("burner_immune" effect). Damage amp still applies.

L4 — Chrome (passive): First kill on own graffiti upgrades ALL tiles to chrome (silver, x1.40
  amp instead of x1.20). Player on chrome: "chrome_aura" buff (+20 energy/tick, +1 power).
  Once per floor (engine.graffiti_chrome_triggered flag). Post-trigger new tiles are already chrome.

L5 — Bombing Run (activated, ability: "bombing_run"): SELF, PER_FLOOR 1. Paints every floor tile
  in current room (fallback: 3x3 in corridor). Enemies inside get "spotted" debuff (20t):
  cannot use FLEEING/WANDERING/IDLE AI states — forced to CHASING.

## New Effects Needed (effects.py)

  tagged           — debuff, 2t, modify_incoming_damage x1.20
  tagged_chrome    — debuff, 2t, modify_incoming_damage x1.40
  home_ground      — buff, 3t, +15% crit, +10 energy/tick
  chrome_aura      — buff, 3t, +20 energy/tick, +1 power
  captivated       — debuff, 1t, before_turn skip
  burner_immune    — debuff, 10t, blocks captivated re-trigger
  spotted          — debuff, 20t, before_turn forces AIState.CHASING

## New Engine/Stats Fields

  engine.graffiti_tiles: list[Entity]  — FIFO cap enforcement
  engine.graffiti_chrome_triggered: bool  — reset on floor change
  engine.entity_prev_positions: dict[str, tuple]  — burner entry detection
  PlayerStats.temporary_crit_bonus: int
  PlayerStats.temporary_power_bonus: int

## XP

  5 XP placing a tag, 10 XP per hit on graffiti, 25 XP kill on graffiti, 50 XP Bombing Run cast.

## Key Design Rules

- Graffiti = floor_duration hazard entities; char '%'; render on explored tiles
- Chrome replaces tagged (remove old effect when tile upgrades)
- home_ground + chrome_aura can coexist: +30 energy/tick total on chrome at L4+
- Spotted enemy in corridor fallback: force WANDERING (not CHASING) if no LOS path
- Graffiti + fire on same tile is valid: both effects apply independently
