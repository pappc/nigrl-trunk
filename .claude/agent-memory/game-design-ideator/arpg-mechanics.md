---
name: ARPG-Inspired Mechanics
description: 18 ARPG mechanics (PoE/D3/LE) added to mechanic-brainstorm-effects.txt on 2026-03-25
type: project
---

Design doc: `nigrl-ideas/mechanic-brainstorm-effects.txt` (appended section at bottom).

## New Engine Fields Proposed

- `engine.player_ward: int = 0` — Ward buffer (A2). Cleared on floor descent.
- `engine.shook_this_floor: set[int]` — entity IDs that have fled from Shook to Bone (B2). Cleared on descent.
- `engine.glass_jaw_checked_this_floor: set[int]` — first-hit check per entity per floor (E3).

## New take_damage() Parameter Proposed

- `source: str = "melee"` — tags damage as "melee", "ranged", "dot", "special", "environmental"
  Required by Iron Skin (D3) to selectively block only melee hits.
  Propagated through combat.py's monster attack resolution path.

## New MonsterTemplate Field Proposed

- `stun_resist: float = 0.0` — Resistance to Stun Threshold (B1). Default 0. Bosses/heavies = 0.5.

## Category A — Leech and Sustain

- **Street Leech (A1)**: on_player_melee_hit stores 15% of damage in leech_pool (max 30% max_hp).
  Drains at 3 HP/tick. Halved by Hemorrhage. Sources: Blessed Rag (equip), Beating L4.
- **Ward (A2)**: Absorb-first layer above mage_armor. Decays 5/tick. Max = 50% max_hp.
  Generated: kill=+10, ability use=+5, drink=+15. Requires render.py HP bar update.
- **Gutted (A3)**: Debuff on enemy. 25% of damage THEY deal is added to player's ward pool.
  Combat.py monster-attack side-effect check. Requires A2 ward system.

## Category B — Threshold Ailments

- **Stun Threshold (B1)**: Auto-stun when single hit >= 15% max_hp.
  Duration = 1 + int((pct - 0.15) / 0.10), capped 4. Halved by stun_resist.
- **Shook to Bone (B2)**: Auto-FLEEING when single hit >= 30% max_hp.
  Returns with ShookBonusEffect (+10% damage dealt, 5t). Once per entity per floor.
- **Wired Shut (B3)**: Every hit >= 5% max_hp applies proportional slow.
  reduction = int(clamp(hit/max_hp, 0.05, 0.40) * 100) energy/tick, 3t.
  Max-merge on_reapply (stronger slow wins).

## Category C — Stacking Ramp Debuffs

- **Shred (C1)**: Enemy debuff. -1 defense per stack. Independent 6t timers. Cap 8 stacks.
  Applied in combat.py damage formula directly (effective_defense -= shred_stacks).
- **Marked for Death (C2)**: +3% damage taken per stack. Independent 8t timers. Cap 10 stacks (max +30%).
  Multiplicative with Marked effect (+50%) → 1.30 * 1.50 = 1.95x at 10 MFD + Marked.
- **Impale (C3)**: Stores 20% of damage dealt in pool. After 5 hits: burst fires stored damage,
  bypass_armor=True. On enemy death while impaled: burst/2 splashes adjacent enemies.

## Category D — Guard and Barrier

- **Grease Shield (D1)**: AbilityDef, PER_FLOOR 1. Shield = 20 + CON*3 HP absorption layer.
  On break (not natural expiry): explode 5 + CON*2 bypass_armor to Chebyshev(1) + 1t Invulnerable.
  Source: Deep-Frying tree.
- **Cool Down (D2)**: Phase 1 (t1-5): 25% DR. Phase 2 (t6-15): 10% DR. Phase 3 (t16+): 5% DR.
  SWG >= 10 → 25/10/5. SWG >= 12 → 30/12/6. No reapply during Phases 1-2. Source: Alcoholism L4.
- **Iron Skin (D3)**: SELF ability, INFINITE with 12t cooldown. Blocks ALL melee damage for 2-4t
  (STR<10: 2t, STR>=10: 3t, STR>=12: 4t). Does NOT block ranged, DoT, specials.
  Requires damage_source param on take_damage().

## Category E — Damage Conversion and Amplification

- **Tenderized (E1)**: +20% damage taken + 30% bleed chance on each hit. Duration 12t.
  Source: iron pipe weapon, Beating perks.
- **Conduct (E2)**: 25% of player melee damage converted to bypass_armor tox component.
  Formula: normal = int(max(1, power - defense) * 0.75); tox = int(power * 0.25); total = normal + tox.
  In Meth Lab: tox component also adds tox_comp//2 to target.tox. Source: Chemical Rag equip.
- **Glass Jaw (E3)**: First-hit check per entity per floor. If first hit >= 20% max_hp:
  bonus_pct = min(hit_pct - 0.20, 0.20). Applies GlassJawEffect (damage_mult = 1+bonus_pct, 15t).
  Source: Stealing L4 Cheap Shot (no threshold), Blackkk Magic Bane ability.

## Key Design Patterns Established

- bypass_armor parameter: take_damage(amount, bypass_armor=False) — skips mage_armor and armor.
  Used by: Impale burst, Grease Shield explosion, Iron Skin's exempt damage types.
- damage_source parameter: take_damage(amount, source="melee") — used by Iron Skin filter.
- max-merge on_reapply: effect keeps stronger value, refreshes duration (Wired Shut pattern).
- entity-ID-per-floor tracking sets: glass_jaw_checked_this_floor, shook_this_floor (engine sets).

## Why: Balance calibration

At player max_hp=130 (CON 10): ward cap=65, leech pool cap=39, grease shield=50 HP.
At enemy max_hp=15 (Tweaker): stun threshold at 2-3 damage. Fear threshold at 4-5 damage.
At enemy max_hp=80 (Sludge Amalgam): stun threshold at 12, fear threshold at 24.
