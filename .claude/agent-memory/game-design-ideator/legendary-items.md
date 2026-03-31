---
name: Legendary Equipment Reference
description: 10 legendary/unique items designed in session 2026-03-26; key patterns and balance anchors.
type: project
---

Full design doc: `nigrl-ideas/legendary-equipment-designs.txt` (2026-03-26)

## 10 Legendaries Summary

| ID                  | Slot    | Zone(s)        | Unlock Condition                               | Key Mechanic                              |
|---------------------|---------|----------------|-----------------------------------------------|-------------------------------------------|
| old_smoke           | weapon  | crack_den F3-4 | Smoking L3 on floor gen OR boss drop           | Self-ability: HoT 4/turn x8t, 8t cooldown|
| blooded_shank       | weapon  | both           | Perfect floor (20 kills, 0 dmg taken) OR shrine| Blood Frenzy stacks on kill (+3 dmg/stk)  |
| the_long_arm        | weapon  | crack_den      | Evidence locker / faction Friendly             | Reach 3, pre-turn shove, follow-through   |
| rat_king_shiv       | weapon  | crack_den F2-4 | Rat King enemy drop OR Rat Nest room           | Plague Vector: rabies spread; -1 all stats|
| soul_chain          | neck    | both           | Negromancy L2+ OR 10 BM kills                  | Siphon on kill: heal+armor; blocks shards |
| ring_dead_mans      | ring    | both           | "Last Chance" room, enter at <=15% HP          | 25% survive at 1HP (1/floor) + low-HP buff|
| ring_seven_fingered | ring    | crack_den      | Jeweler NPC ($180) OR smash-window event        | 2x Stealing XP, cash procs, crate pocket |
| ghost_walks         | feet    | both           | Clean floor OR Black Widow drop (15%)          | Phase Step: 3/floor, pushes monsters      |
| hat_lucky_fitted    | hat     | crack_den      | 1.5% chance replacing any hat drop             | Lucky Roll: 25% on crit, random bonus     |
| hat_iron_crown      | hat     | meth_lab       | Jerome no-consumable kill OR faction leader 5% | Intimidation aura + crown thorns 20%      |

## New Engine State Needed
- engine.blood_frenzy_stacks, engine.blood_frenzy_decay_timer
- engine.dead_mans_ring_procced_floor (int, -1 = never)
- engine.iron_crown_intimidated_ids (set of entity IDs)
- engine.jerome_fight_consumable_used (bool)
- engine.player_stats.guaranteed_next_dodge (bool)
- entity.hp_before_kill (int)

## New Abilities Needed
- "second_wind_smoke": SELF, INFINITE, 8-turn cooldown (Old Smoke)
- "phase_step": ADJACENT_TILE, PER_FLOOR 3 (Ghost Walks)

## New Effects Needed
- "ghost_step": buff, +10 dodge_chance, 3 turns
- "flanked": debuff, -2 incoming damage, 1 turn (monsters only)

## Design Patterns Established
- grants_ability field must be revoked on unequip: engine._ability_granted_by_item dict.
- equipped_stat_penalty: {"all": N} — processed in equip/unequip, temp bonus.
- Unlock conditions that require play-state flags (clean floor, no-consumable boss fight):
  engine-side bool flags reset per floor or per boss encounter.
- "last_stand" ring survival check: goes in deal_damage or event_bus entity_died
  handler BEFORE alive=False finalises.
- Legendary hat: loot.py checks for legendary hat FIRST before procedural hat roll.
  Pattern: if random.random() < 0.015 and not already_found_this_run: return "hat_lucky_fitted"
- Crown thorns are "true damage" (entity.take_damage, not deal_damage) — bypasses tile amps.
- Negative CON stat_bonus on items is valid: established by Meth-Head L2 design and
  Negromancy L2 design. Soul Chain uses {"constitution": -1}.

## Balance Anchors Referenced
- armor_bonus 25 on Iron Crown: exceeds Hard Hat (15) deliberately as boss-tier item.
- Best chains top at ~25 for Silver Iced-Out Designer — soul_chain's 20 is below that.
- Crit mult: Prison Shank has +1x; Old Smoke also +1x. Anything above +2x bonus would
  be exceptional (mega-crit territory).
- Reach 3: Kids Basketball Pole also has reach 3 — The Long Arm is not unique in reach,
  but is unique in its follow-through mechanic.
- Vampiric 0.20 (Blooded Shank) vs 0.30 (Bone Club) — compensation via frenzy stacks.

**Why:** Needed accurate balance benchmarks against existing items for legendary tier.
**How to apply:** When designing future legendary items, reference these 10 as calibration
  points. Legendaries should exceed normal item ceiling but require specific unlock conditions.
