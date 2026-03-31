---
name: Cryomancy Skill Trees
description: 5 linear L1-L6 designs for the Cryomancy skill (cold/ice counterpart to Pyromancy). Includes Freeze effect definition and 8 new ability specs.
type: project
---

# Cryomancy Skill Trees (2026-03-26)

Design doc: `nigrl-ideas/cryomancy-skill-tree-designs.txt`

## Chill Effect Retuning
- Multiplier: 0.85 → 0.90 per stack (less harsh stacking)
- Duration: 5 → 6 turns
- XP grant: 10 Cryomancy XP per chill stack applied

## Freeze Effect (NEW — id="frozen")
- Duration: 4 turns (some abilities grant 5-6)
- Hard CC: energy gain = 0, before_turn = True (fully paralysed)
- 40% incoming damage reduction (encased in ice)
- Does NOT break from regular damage — only breaks from:
  1. Duration expiry (natural)
  2. Ignite/fire application (fire melts ice, +5 fire bonus damage)
  3. Ice Lance shatter (TRIPLE damage, removes frozen first so 40% DR does not apply)
- Chill stacks preserved under freeze; restored on natural thaw (if >2t remaining)
- Applying freeze strips ignite; applying chill to a frozen target does nothing
- on_reapply: refresh duration only (no "deeper frozen")

## New Abilities
- frostbolt: SINGLE_ENEMY_LOS, PER_FLOOR 5, 8+BKS dmg, chill x2
- ice_lance: SINGLE_ENEMY_LOS, INFINITE, 6+BKS dmg, 3x vs frozen (strips freeze first)
- frost_nova: SELF (Chebyshev 1 AOE), PER_FLOOR 3, 4+BKS/2 dmg, chill x2
- cone_of_cold: SINGLE_ENEMY_LOS cone (reuses breath_fire), PER_FLOOR 3, 10+BKS, chill x1
- freeze_spell: SINGLE_ENEMY_LOS, PER_FLOOR 2, no damage, applies frozen (4t)
- blizzard: SINGLE_ENEMY_LOS, PER_FLOOR 1, creates BlizzardZone hazard entity, radius=3, 8 turns
- ice_barrier: SELF, PER_FLOOR 2 (3 after capstone), 20 HP absorb shield, chill attacker on shatter
- frozen_orb: SINGLE_ENEMY_LOS, PER_FLOOR 1, 8-tile travel, direct+mini-bolt hits, chill x1

## New Effects
- FrozenEffect: see design doc for full implementation
- IceBarrierBuff: absorb shield, shatters = chill attacker, Frost Ward passive trigger
- BlizzardZone: entity_type="hazard", hazard_type="blizzard_zone", processed in energy loop

## XP System
- _gain_cryomancy_xp(engine, damage=0, chill_stacks=0)
- XP = (damage * 1.5) + (chill_stacks * 10), with floor_mult and zone_mult
- Discoverable via existing Ray of Frost (already cold-tagged)
- No item dependency (unlike Pyromancy's BIC Torch)
- Ice Lance shatter bonus: flat +25 XP

## 5 Design Takes (all L1-L6 linear)

| Take | Identity | Frozen Orb | Key Passives | Stat Gains |
|------|----------|------------|--------------|------------|
| 1 Shatter | Chill→auto-Freeze→Ice Lance | None | Frostbite (auto-freeze at 4 stacks) | +6 BKS +2 TOL |
| 2 Control | CC management, Permafrost defence | L4 mid-tree | Permafrost (15% dmg red/chill stack) | +3 BKS +1 CON +1 STS |
| 3 Ice Storm | Blizzard zone denial, AOE | L5 penultimate | Eye of the Storm (Blizzard upgrade) | +2 BKS +2 CON +1 STS |
| 4 Icebreaker | Defensive tank, Ice Barrier | None | Frost Ward, Permafrost Shell | +5 CON +2 TOL |
| 5 Glaciologist | Max spell variety, Frozen Orb capstone | L6 CAPSTONE | None | +4 BKS |

## New PlayerStats Fields Implied
- permafrost_unlocked: bool (Takes 2, 4)
- ice_barrier_active: bool (Take 4 Frost Ward passive check)

## Key Implementation Notes
- cone_of_cold reuses breath_fire cone resolver in spells.py
- BlizzardZone processed in engine._run_energy_loop alongside fire tiles
- Frostbite (Take 1 L4): checked in ChillEffect.on_reapply — if stacks >= 4 and skill level >= 4, apply_effect frozen
- IgniteEffect.apply needs FrozenEffect break case (strip frozen + 5 bonus damage + message)
