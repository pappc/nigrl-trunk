---
name: Traditional Roguelike Inspired Equipment (Items 41-50)
description: 10 legendary equipment items inspired by NetHack/DCSS/ADOM/Angband artifacts, filed as items 41-50
type: project
---

## File
`nigrl-ideas/traditional-roguelike-inspired-equipment.txt` — 10 items (41-50), each citing a specific
traditional roguelike source artifact and mechanic.

## Item Roster

| # | Item ID | Slot | Inspiration |
|---|---------|------|-------------|
| 41 | cold_snap_weapon | weapon (stabbing) | NetHack Frost Brand + DCSS Frostbite |
| 42 | one_for_one_weapon | weapon (beating) | NetHack Stormbringer (sentience + mirror dmg) |
| 43 | silver_service_weapon | weapon (stabbing) | NetHack Grayswandir + ADOM precrowning silver |
| 44 | magicbane_chain | neck | NetHack Magicbane (1d6 spell proc table) |
| 45 | finisher_ring | ring | DCSS Finisher (floor-scaled execute threshold) |
| 46 | vorpal_ring | ring | NetHack Vorpal Blade (% instant-kill) |
| 47 | adom_soles_cursed | feet | ADOM BUC curse lock + corruption (permanent stat drain) |
| 48 | hat_skin_zhor | hat | DCSS Skin of Zhor (passive AoE chill aura) |
| 49 | leech_chain | neck | DCSS Leech/Bloodbane (ability lifesteal + Blood Frenzy) |
| 50 | adom_talisman | neck | ADOM alignment-reactive artifacts (kill/mercy ratio tracking) |

## Key Mechanic Highlights

**Cold Snap (41)**: Chill on every hit. Cold resistance tiers: 5/10/20 kills on floor → partial/full
immunity. Frost patch hazard entities spawn on kills (hazard_type="frost_patch", hazard_duration field).

**One For One (42)**: 2x outgoing / 2x incoming melee. Autonomous attack OR self-drain every 12 ticks.
Windfury explicitly disabled while equipped. Sentience narrative via engine state.

**Silver Service (43)**: True damage component vs. swagger >= 8 enemies scales with player swagger.
-2 dmg vs. low-swagger. Confuse immunity. +2 silver bonus if smoked this floor.

**Magicbane Chain (44)**: 20%+BkSmt*2% proc per hit (capped 50%). 1d6 table: Probe/Stagger/Scare/
Cancel/Confuse/Backfire. 60% blanket debuff immunity via curse_resistance flag.
Needs force_apply=True parameter on apply_effect() for Backfire self-application.

**Finisher Ring (45)**: Execute threshold = 5%+(floor*4)% max HP. 20%+STS*1.5% execute chance.
-3 swagger cost. Scales dramatically floor 1 (9%) → floor 4 (21%).

**Vorpal Ring (46)**: 35% instant kill on mega-crit (Sniping L3 check). 5% on regular crit.
HP > 60% guard blocks activation. Boss immunity. Once-per-turn cap.

**Wanderer's Soles (47)**: starts_cursed field (new) = can't unequip until condition met.
Free movement (0 energy). 3x Jaywalking XP. Permanent -1 random stat (excl. swagger) every 30 steps.
Uncurse condition: 200 steps walked while equipped.

**Iced Out Fisherman's Net (48)**: Passive chill pulse every max(5, 12-TOL//2) ticks. 50% per
Chebyshev(3) enemy. Player chill immune. Chilled enemies visible through explored-but-dark tiles.

**Leech Chain (49)**: 25% lifesteal on ability damage. "Blood Frenzy" activated mode: 1.5x ability
damage + blocks all heals for 6t, then 8t starvation. Needs new modify_heal() lifecycle hook on
Effect base class.

**Talisman of Order (50)**: Tracks engine.talisman_kills vs engine.talisman_mercy_moves per-run.
65% threshold → Ordered mode (+3 STR, +5 dmg, +15% kill XP, 2-tile pressure aura) or Wandering
(+3 STS, +10 spd, +20% Jaywalking XP, enemies lose interest at >6 tiles). Neutral below threshold.

## New Engine State Required
- engine.talisman_kills: int (incremented on kill while talisman equipped)
- engine.talisman_mercy_moves: int (incremented when descending without clearing a floor)
- engine.talisman_mode: str ("neutral" | "ordered" | "wandering")
- entity.frost_patch_duration: int (for frost_patch hazard entities)

## New Item Fields Required
- starts_cursed: bool — item cannot be unequipped until a condition is met
- curse_unlock_steps: int — steps to walk to break the curse (for adom_soles_cursed)
- curse_steps_walked: int (runtime tracking on Entity)

## New Effect Lifecycle Hook Required
- Effect.modify_heal(amount: int, entity: Entity, engine: GameEngine) -> int
  Used by Leech Chain Blood Frenzy to block all healing (return 0).

## New Hazard Entity Type
- hazard_type="frost_patch": created on Cold Snap kill. hazard_duration field (turns).
  On entity entering tile: apply chill. On hazard_duration expiry: remove entity.

## New force_apply Parameter
- apply_effect(entity, engine, effect_id, force_apply=False, **kwargs)
  When force_apply=True: bypass debuff immunity (ZonedOutEffect, curse_resistance).
  Needed for Magicbane Backfire (self-applying debuffs to the player).

## Traditional Roguelike Sources NOT Yet Used (for future batches)
- Pathos NetHack codex items
- Cogmind unique components (modular assembly)
- UnReal World unique items (survival-sim mechanics)
- Cataclysm DDA CBMs (bionic augmentation)
- ADOM postcrowning artifacts (second alignment tier)
- Brogue allies/companions
- ToME4 Dimensional Step / Paradox Mage spells
- DoomRL unique assemblies (weapon modification combinations)
