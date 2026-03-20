# Zone 2 — Meth Lab Design Notes

Full design docs:
- `nigrl-ideas/toxicity_mechanic.txt`
- `nigrl-ideas/crackhead_skill_variants.txt`
- `nigrl-ideas/toxicity_skill_variants.txt`

## Toxicity System

entity.toxicity: int = 0. No cap. Persists across zones.
Player incoming damage: mult = 1.0 + (tox/100)^0.6
Monster incoming damage: mult = 1.0 + (tox/50)^0.6
Crit damage: 2.0 + (tox/1000). Base crit = 2.0x.

On-crit procs by threshold (highest wins):
  250+ tox  → Acid Splash (AOE r=1, tox//100 dmg)
  600+ tox  → Toxic Shock (DOT, tox//200 dmg/turn, 4t)
  1500+ tox → Chemical Cascade (defense=0 for 3t + bonus dmg)

Tolerance modulates passive/consumable tox GAIN rate:
  rate = max(0.3, 1.5 - (tolerance * 0.1))
  Does NOT affect enemy on-hit tox or Synthesize.

Natural decay (outside Meth Lab): max(1, tox//50) per 20 turns.
No decay inside Meth Lab.

New EffectKind needed: TOXICITY_DOSE — bypasses apply_effect, directly
  calls engine._apply_toxicity(entity, amount, source="enemy_hit").
New effects needed: poisoned (DOT variant), dissolving (3t defense=0),
  nauseous (cosmetic/flavor only).

Two new skill trees (total becomes 19 + gun trees = 22):
  Chemical Warfare — spend tox on abilities, scale with high tox
    L1 Synthesize: SELF, INFINITE w/cooldown 12t, +100 tox
    L2 Chemical Fury: passive, (tox_spent//50) flat dmg bonus for 6t on spend
    L3 Acid Bath: SINGLE_LOS, PER_FLOOR 3, costs 150 tox, dmg = tox_before//10
  Clean — resist tox pressure, purity bonus at low tox
    L1 Constitution of a Cockroach: +25 tox_resistance, +2 CON when tox<50
    L2 Flush: SELF, PER_FLOOR 2, -120 tox + heal HP equal to amount reduced
    L3 Purity Offensive: passive, +25% dmg dealt while tox < 100

engine.player_tox_resistance: int = 0 (not on PlayerStats).
ChargeType.COOLDOWN may need adding for Synthesize (open question).

## Meth Meter System

engine.meth_meter: int = 0. Soft cap 200 (decay accelerates past it).
Displayed on HUD alongside Toxicity.

Blue Meth item: item_id="blue_meth", char='%', color=(0,180,255), category="consumable"
  Scattered on floor tiles in Meth Lab (2-4 per floor). Does NOT add Toxicity by default.
  Spike formula: spike = int(80 * max(0.5, 1.5 - tolerance * 0.1))

Three Crack-Head variant identities:
  Speed Freak  — action economy; Cardiac Event ability (dump meter → speed burst)
  Tweaker Tank — berserker; Superconductor (AOE r=3, dmg=meter//8, no defense)
  Manifest     — hallucination tactician; The Vision (map reveal + 3 crits)

## Toxicity Skill Tree Variants (10 total: 5 offensive, 5 defensive)

Offensive:
  Runoff, Cooker, Product, Venom House, Hollow
Defensive:
  Quarantine, Boiled Down, Sober, Ghost, Transmute

Key effects from variants:
  corroded, contaminated, melting, saturated, bleed_out, rallied,
  second_wind_regen, clarity_burst

Key abilities from variants:
  purge, hit_the_batch, final_product, dead_air, flash_point,
  second_wind, cut_and_run, clarity_burst
