---
name: STR/Radiation Strain Designs
description: Design notes for the 5 STR-radiation marijuana strains and their mechanics
type: project
---

Full design: `nigrl-ideas/str_radiation_strain_designs.txt`

## 5 Strains Summary

| Strain          | Best Roll                         | Core Mechanic                              | Risk       |
|-----------------|-----------------------------------|--------------------------------------------|------------|
| Gamma Punch     | +3 perm STR, +60 rad              | Flat STR buff + rad injection; rad-scaled bonus dmg | Medium |
| Hulk Weed       | rad//20 unresisted/hit, +50 rad   | Live-scaling damage from current radiation | Med-High   |
| Rad Bull        | +150 rad, forced good mutation    | Mutation accelerator; speed to leverage rad| Low-Med    |
| Hulk's Blood    | Radiation exchange loop, 20t      | Both player and target irradiated per hit  | Medium     |
| Berserker Kush  | +5 STR +3 dmg, 0 defense, 15t    | Delayed rad crash on expiry; defense stripped | Very High |

All five: first_bonus_roll=11, add_bonus_roll=6, Smoking/Rolling XP=125.

## Unique Items (95-100 tier drops)

- **Gamma Knuckles** (weapon/blunt): +15 rad on hit, rad>=100 → +STR//3 unresisted bonus, kills remove 20 rad from player.
- **Gamma Leaf** (weapon/blunt): rad 20 on hit if any hulk_/gamma_punch_buff active; kills add 15 rad to player.
- **Irradiated Energy Drink** (consumable): +80 rad +40 speed 10t; 20% chance forced mutation on drink.
- **Hulk Shorts** (feet): +2 STR; 25% of incoming rad → temporary armor (rad/5 per absorbed point).
- **Berserker Belt** (feet): +1 STR +1 CON; +15 energy/tick while berserker_kush effect active.

## New Effects Needed

- `gamma_punch_buff` — temp STR toggle (StatModEffect pattern)
- `hulk_rampage` — on_player_melee_hit: unresisted bonus = rad//20; +15% dmg taken
- `hulk_rage` — flat power bonus + % dmg taken
- `hulks_blood` — on_player_melee_hit: irradiate both combatants; conditional STR//4 bonus
- `berserker_kush` — apply: strip defense + stat bonus + power; expire: restore all + inject rad + optional stun

## New Fields Needed

- `rad_threshold_bonus: {"threshold": int, "formula": "str//3"}` — weapon bonus dmg at rad level
- `on_kill_remove_rad: int` — remove rad from player on kill with weapon
- `rad_on_hit_if_buff: {"prefix": str, "also": str, "rad": int}` — irradiate target if named buff active
- `rad_absorb_to_armor: {"ratio": float, "armor_per_rad": float, "duration": int}` — feet item mechanic
- `buff_synergy_energy: {"prefix": str, "energy": int}` — energy bonus while named buff family active

## Reflect Irradiation Hook

HulksBloodEffect (full tier) needs to irradiate the attacker when player takes damage.
modify_incoming_damage doesn't provide the attacker entity.
Two options:
  1. Add `on_player_take_melee_damage(engine, attacker)` hook to Effect base class.
  2. Track `engine.last_melee_attacker` in combat.py and read it in modify_incoming_damage.
Option 2 is lower surface area; option 1 is cleaner for future use.

## Cross-Strain Synergies Designed

- Gamma Punch + Hulk Weed: Gamma Leaf activates off both buff families.
- Rad Bull + Mutation build: Irradiated Energy Drink bridges between smokes.
- Hulk's Blood + Windfury: Extra Windfury hit calls on_player_melee_hit → more irradiation per turn.
- Berserker Kush + Iron Lung: Tactical rotation to survive crash window.
- Hulk's Blood + Petrification Needle: Loads enemy to irrad>=50, doubles petrify proc.
- Berserker Kush + Smacking skill: Unarmored berserker = maximum synergy.

## Monster Effect Pattern

Each strain has a 3-tier monster effect:
  heavy: 80-100 rad + secondary CC (shocked 3 stacks, cripple_armor)
  medium: 40-60 rad + light CC
  minor: 30-40 rad only

Suggested rad-link effect (id="rad_link", duration=9999): whenever monster takes damage, +30 rad.
This is the monster-facing analogue to the SoulPair effect from Jungle Boyz.
