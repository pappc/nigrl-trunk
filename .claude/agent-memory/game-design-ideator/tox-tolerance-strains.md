---
name: Tox/Tolerance Strains — Design Notes
description: Three TOL-scaling Meth Lab strains that gain (not spend) toxicity as their core mechanic, with shared Pandemic ability
type: project
---

## Tox/Tolerance Strains (3 strains, 2026-03-13)

Full design: `nigrl-ideas/tox_tolerance_strain_designs.txt`

### Strains

**Street Rot** — color (210, 180, 30) — Aggressor
  Tiers 85-100 / 65-84 / 40-64 / 15-39 / 1-14
  Glory: +150 tox + StreetRotBuff (outgoing dmg += tox//30, 30t) + StreetRotSurge (lethal-hit block, AOE tox dump) + 1 Pandemic charge (40 tox/enemy)
  Bad tier: +150 tox + Nauseous (25% skip-turn, 6t)
  Unique item drop: Rot Rag (accessory, tox_resistance: -15, power_bonus: 3)

**Neighborhood Watch** — color (200, 140, 40) — Tactician / Pandemic-centric
  Tiers 88-100 / 68-87 / 42-67 / 18-41 / 1-17
  Glory: +60 tox + NWSpilloverAura (floor-permanent: on-monster-death, apply tox//2 to Chebyshev(2) neighbors) + 2 Pandemic charges (50 tox/enemy)
  Bad tier: +80 tox + ALL Pandemic charges deleted (charges_remaining = 0)
  Unique item drop: Gas Mask (accessory, tox_resistance: 30, on_kill_spillover_bonus: 10)

**Bleach Hit** — color (220, 215, 200) — Survivor / Defensive
  Tiers 87-100 / 64-86 / 40-63 / 16-39 / 1-15
  Glory: +120 tox + BleachArmorEffect (incoming DR = tox//25, 35t) + BleachPurity (15% chance on melee hit: remove 10 tox, 35t) + 1 Pandemic charge (25 tox + bleached debuff 6t)
  Bad tier: +120 tox + ToxFlare (+20% incoming damage, 10t)
  Unique item drop: Respirator (accessory, tox_resistance: 25, defense_bonus: 3, on_tox_threshold_dr: {threshold:150, bonus_dr:5})

### Shared Pandemic Ability

  ability_id: "pandemic"
  TargetType.SELF, ChargeType.TOTAL (charges granted dynamically)
  execute: iterate all alive monsters on floor → add_toxicity(engine, monster, engine._pandemic_tox_per_charge, from_player=True)
  XP: Chemical Warfare += (total tox applied) // 2

  engine._pandemic_tox_per_charge: int — set by each strain roll that grants charges.
  Last smoked strain wins if multiple strains provide charges.

### New Effects Needed

  street_rot_buff     — modify_outgoing_damage += player.tox // divisor
  street_rot_surge    — on-lethal-hit block (modify_incoming_damage → 0 once), engine queues AOE tox dump at radius 1
  nauseous            — before_turn 25% skip-turn
  nw_spillover_aura   — on_entity_death: apply dying.tox//2 to Chebyshev(2) neighbors; floor-permanent (-1 duration)
  bleach_armor        — modify_incoming_damage -= player.tox // divisor
  bleach_purity       — on_player_melee_hit 15% → remove_toxicity(player, 10)
  tox_flare           — modify_incoming_damage *= 1.20 (debuff)
  bleached            — monster debuff: modify_incoming_damage *= 1.20

  Requires adding on_entity_death hook to Effect base class if not already present.

### New Item Fields Needed

  on_kill_spillover_bonus: int  (Gas Mask — apply N tox to radius-2 monsters on kill)
  on_tox_threshold_dr: dict     (Respirator — bonus DR when player.toxicity >= threshold)

### Balance Notes

  Player tox damage multiplier: 1.0 + (tox/100)^0.6. At 120 tox: ~1.72x. At 250: ~2.18x.
  Monster tox multiplier: 1.0 + (tox/50)^0.6. At 50 tox: ~2x. At 80 tox: ~2.5x.
  TOL rate modifier: max(0.3, 1.5 - tol*0.1). At TOL 11: 40% gain. At TOL 14: 30%.
  Pandemic hitting 14 monsters at 50 tox each = 700 total tox applied → very strong.
  All three strains: first_bonus_roll=11, add_bonus_roll=6, Smoking/Rolling XP=125.
  Loot weights suggestion: Street Rot 3, Neighborhood Watch 3, Bleach Hit 2.
