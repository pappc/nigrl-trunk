---
name: roguelike-inspired-drinks
description: Design notes for 30 roguelike-inspired drinks (2026-03-25)
type: project
---

## Roguelike-Inspired Drinks (2026-03-25)
Design doc: `nigrl-ideas/roguelike-inspired-drinks.txt`
30 drinks total. 20 alcoholic, 10 non-alcoholic (soft drinks / dranks).

### Zone Split
- Crack Den alcoholic (15): Night Train, Brass Monkey, Thunderbird, OE Tall Boy,
  Ripple Wine, MD 20/20, Pruno, Bartles & James, Diesel Stout, King Cobra,
  Thunderstruck, Old Tater Gin, Bumping Brew, Blackout Bock, Coffin Varnish
- Crack Den soft drinks (5): Grey Drank, Black Drank, White Drank, Yellow Drank,
  Sparkling Water
- Meth Lab alcoholic (5): Reagent Rum, Crystal Cordial, Solvent Schnapps,
  Precursor Punch, Isotope IPA
- Meth Lab soft drinks (5): Smart Water, Protein Shake, Power Surge,
  Shroom Tea, Flux Tonic

### New Engine Fields Needed
- black_drank_darkness_turns: int = 0
- mutation_threshold_multiplier: float = 1.0
- meth_gain_bonus: float = 0.0
- meth_drain_reduction: float = 0.0

### New PlayerStats Fields Needed
- crit_multiplier_bonus: float = 0.0  (Thunderstruck — melee crit multiplier)
- tox_gain_reduction: float = 0.0     (Reagent Rum — reduces environmental tox rate)
- sight_radius_bonus: int = 0         (Shroom Tea — expands player FOV)
- sound_radius_bonus: int = 0         (Shroom Tea — expands ALERTING propagation)

### Notable Design Patterns
- Bumping Brew: zero hangover, removes all buffs AND clears pending_hangover_stacks.
  Strategic reset before floor descent. item_id="bumping_brew", explicit `_add_hangover_stacks`
  call is simply skipped in the elif branch.
- Pruno: d6 random outcome table in elif branch (random.randint(1, 6)). 2 hangover stacks.
  Outcomes 5-6 give permanent stat gains. Blue Drank + Pruno = multiple d6 rolls.
- Bartles & James: floor-duration enemy reveal — set dungeon.visible per tick for alive
  monsters. Do NOT permanently set explored; override visible in effect.tick() before
  render pass. Alternative: track revealed positions in set, render grey outside FOV.
- Grey Drank: stealth — in ai.py sight check, if player has grey_drank effect active,
  return False for IDLE/WANDERING state transitions (chasing enemies still pathfind).
- Black Drank: engine.black_drank_darkness_turns field; ai.py uses
  max(2, monster.sight_radius - 4) while field > 0.
- Isotope IPA: permanent +1 STR +1 CON per drink (modify_base_stat calls).
  Also triggers Protein Powder callback twice if active — massive synergy.
- Precursor Punch: calls engine._try_mutate(forced=True) to bypass rad threshold.
  _try_mutate needs a `forced` parameter that skips the rad check.
- Solvent Schnapps: engine.mutation_threshold_multiplier = 0.5 for 30t.
  In engine._try_mutate: effective_threshold = base * mutation_threshold_multiplier.

### Stacking Type Reference
- Type A (independent-timer, same pattern as FortyOzEffect/MaltLiquorEffect):
  NightTrain, BrassMonkey, OETallBoy, DieselStout, KingCobra, Thunderstruck,
  OldTaterGin, BlackoutBock, ReagentRum
- Type B (floor-duration-stacks, same pattern as FiveLocoEffect):
  Thunderbird, YellowDrank, GreyDrank, ShroomTea, SmartWater, ProteinShake,
  CrystalCordial, CoffinVarnish (companion effect)
- Type C (immediate only, no Effect object):
  Pruno, Bumping Brew, White Drank, Sparkling Water, Flux Tonic
- Type D (immediate action + short companion Effect):
  Ripple Wine (+STS 20t), Coffin Varnish (map reveal + floor SWG/STS),
  Solvent Schnapps (mutation window 30t), Isotope IPA (perm + floor temp)

### Roguelike Source Mapping (brief)
DCSS Might→NightTrain, Haste→BrassMonkey, Resistance→Thunderbird,
  Ambrosia→KingCobra, Cure→RippleWine, Brilliance→MD20/20,
  Cancellation→BumpingBrew, Confusion→BlackoutBock, Mutation→PrecursorPunch.
Brogue Telepathy→BartlesJames, Darkness→BlackDrank, Healing→WhiteDrank.
Cogmind Kinetic→DieselStout, Thermal→OldTaterGin, EM→YellowDrank,
  Chemical→SolventSchnapps, Structural→ProteinShake.
CoQ Precognition→CoffinVarnish/ShroomTea, Metabolism→CrystalCordial.
