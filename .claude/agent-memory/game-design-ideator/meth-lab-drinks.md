# Meth Lab Drinks Design Notes

Full design: `nigrl-ideas/item-meth-lab-drinks.txt`
Date: 2026-03-15

## 10 New Drinks Summary

All are zones: ["meth_lab"], char: "!", value: 60 (Chrome Handle: 80).
All cost +1 hangover stack except Four Fingers (+2) and Chrome Handle (+2).

| drink_id                   | Color                  | Duration    | Stacks | Core Identity                                |
|----------------------------|------------------------|-------------|--------|----------------------------------------------|
| radioactive_remy           | (120,255,60) lime      | floor       | yes    | Halve rad gain, +1 mutation tier per stack   |
| long_island_iced_teeth     | (255,220,140) amber    | 100t        | yes    | 20% stun / 30% intimidate on melee hits      |
| cold_filtered_cope         | (180,220,255) ice blue | 100t        | yes    | Tox-scaled armor bonus (+3/tier/stack)       |
| buckshot_bourbon           | (180,100,40) brown     | 50t         | yes    | +1 gun pellet per stack (60% hit, 50% dmg)  |
| street_cred_spritzer       | (255,130,200) pink     | 100t        | yes    | +3 SWG temp, +5% dodge, better SWG formula  |
| lean_cuisine               | (150,80,200) purple    | 100t        | yes    | -20 energy/stack, +15% dmg, +0.25 crit mult |
| barrel_roll                | (200,160,60) tan       | 50t         | yes    | +15 energy/stack, 30% trip adj on move       |
| four_fingers_of_fentanol   | (240,200,255) lavender | 100t+extend | NO     | Heal to full, 50% DR, debt on expire         |
| gutter_merlot              | (140,30,60) wine red   | instant     | n/a    | 30% potential XP converted + BKS/-STS temp  |
| chrome_handle              | (220,220,230) silver   | 100t        | yes    | +30t to all buffs, +2 CON perm, +25% amps   |

## New Effects Needed (effects.py)

  RadioactiveRemyEffect     id: "radioactive_remy"
  LongIslandIcedTeethEffect id: "long_island_iced_teeth"
  ColdFilteredCopeEffect    id: "cold_filtered_cope"
  BuckshotBourbonEffect     id: "buckshot_bourbon"
  StreetCredSpritzertEffect id: "street_cred_spritzer"
  LeanCuisineEffect         id: "lean_cuisine"
  BarrelRollEffect          id: "barrel_roll"
  FourFingersEffect         id: "four_fingers_of_fentanol" (no-stack; extend only)
  ChromeHandleEffect        id: "chrome_handle"
  TrippedEffect             id: "tripped" (stun alias, for Barrel Roll)

Gutter Merlot: no effect class — all instant logic in _handle_alcohol elif.

## New Lifecycle Hooks Needed

  on_player_gun_fire(entity, engine, shot_data) — BuckshotBourbonEffect
  on_player_move(entity, engine, dest_x, dest_y, adjacents) — BarrelRollEffect
  modify_rad_gain(entity, engine, amount, source) — RadioactiveRemyEffect
    (These may already be added by stat-scaling-strains-v2 implementation)

## New Engine Fields

  engine._mutation_tier_bump: int = 0   (reset on floor change, Radioactive Remy)
  engine._chrome_handle_kill_bonus      (kill energy for Chrome Handle)

## New Constants / Helpers (effects.py)

  ALCOHOL_BUFF_IDS: set[str] — all drink buff effect ids Chrome Handle extends/amplifies
    (excludes: platinum_reserve, alco_seltzer_*, four_fingers_of_fentanol)
  get_chrome_handle_amplifier(engine) -> float
  buckshot_bourbon_active(engine) -> int
  lean_cuisine_damage_mult(engine) -> float
  lean_cuisine_crit_bonus(engine) -> float
  get_street_cred_spritzer_divisor(engine) -> float

## Key Design Rules Established

- Four Fingers: single instance only (extend on reapply, not new instance).
  Debt is unblockable on expire. One-turn warning at duration == 1.
- Chrome Handle amplifier: +25% per stack to compatible drink effects.
  NOT compatible: Cold Filtered Cope (hard cap), Four Fingers, Alco-Seltzer.
- Buckshot Bourbon pellets: do NOT recover ammo (Dead Shot Daiquiri ammo
  recovery does not apply to bonus pellets).
- Lean Cuisine energy floor: 30 energy/tick minimum regardless of stacks.
- Radioactive Remy + Five Loco: intentionally cancel rad gain rate but
  stack both tier bump AND polarity bonus. Designed interaction.

## Loot Weights (meth_lab zone)

  Four Fingers / Chrome Handle: weight 2 (rarest)
  Lean Cuisine / Gutter Merlot: weight 3
  Radioactive Remy / Buckshot Bourbon / Street Cred Spritzer / Barrel Roll: weight 4
  Long Island Iced Teeth / Cold Filtered Cope: weight 5 (most common)
