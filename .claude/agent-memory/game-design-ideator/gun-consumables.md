---
name: Gun Consumable Designs
description: 10 food/drink consumables designed for gun/shooting builds, including elemental ammo, accuracy, mag size, and kill snowball effects
type: project
---

10 gun consumables documented in `nigrl-ideas/gun-consumable-designs.txt` (2026-03-26).

**Why:** Dead Shot Daiquiri was the only gun-specific consumable. These fill gaps:
accuracy, reload speed, mag size, elemental rounds, on-kill snowball, crit enhancement.

**Items (ID: primary mechanic):**
- scope_juice: +15 accuracy, +3 STS, 60t, non-alc, both zones common
- beef_jerky: food, +10 accuracy, -10 shot energy cost, 40t
- speed_loader: free reload on drink + -20 shot energy cost, 50t, non-alc
- bando_box: food, grants ammo (type auto-detected from equipped gun)
- incendiary_sauce: gun hits apply ignite, 40t, non-alc
- liquid_nitrogen_slurpee: gun hits apply chill, 40t, non-alc, meth_lab only
- static_charge: gun hits apply shocked, +2 STS, 35t, +1 hangover
- killstreak_kool_aid: +3 gun dmg per kill, 60t resets on kill, 5-kill auto-reload
- hollow_point_hennessy: +4 STS, +1 crit multiplier, 80t, +1 hangover
- gun_oil_smoothie: +4 mag_size until floor end, +2 STS, meth_lab only

**New engine fields required:**
  gun_accuracy_bonus, gun_energy_cost_reduction, elemental_ammo_type,
  gun_damage_bonus, killstreak_count

**New hook in gun_system.py:**
  apply_elemental_gun_hit(engine, target) after every confirmed hit
  _notify_killstreak_kill(engine) after every notify_gun_kill(engine)

**How to apply:** Reference for future gun-adjacent designs. The elemental ammo
pattern (engine.elemental_ammo_type field + apply_elemental_gun_hit hook) is
reusable for future elemental ammo items without adding new fields.
