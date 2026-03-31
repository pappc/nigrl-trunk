---
name: Cursed-to-Blessed Unique Items
description: 10 cursed-to-blessed items designed 2026-03-27; curse/blessed patterns, new fields, and balance anchors.
type: project
---

Full design doc: `nigrl-ideas/cursed-to-blessed-unique-items.txt`
Summary: `nigrl-ideas/summaries/cursed-to-blessed-items-summary.txt`

## Curse Unlock Triggers (two types)

- `curse_unlock_steps: int` — walk N steps while equipped (established: Soul Edge 300 steps)
- `curse_unlock_kills: int` — kill N enemies while equipped (NEW pattern, this batch)
- New engine flag per item: `engine.curse_broken_{item_id}: bool = False` (run-persistent)
- Counter vars: `engine.{item_id}_kills: int` or `engine.{item_id}_steps: int`
- On unequip before curse breaks: reset counter to 0, curse persists.

## 10 Items Quick Reference

| Item ID                        | Slot     | Unlock       | Curse                                | Blessed                             |
|-------------------------------|----------|--------------|--------------------------------------|-------------------------------------|
| penitent_nail                 | weapon   | 40 kills     | on_hit_self_damage 2 (true dmg)      | 35% vampiric, bleed, +1 crit mult   |
| blindfold_of_truth            | hat      | 500 steps    | -4 sight, no_map_memory              | telepathy, +6 STS, +3 BKS           |
| ring_of_necessary_pain        | ring     | 25 kills     | hp_drain 1/turn, +3 incoming damage  | regen 2/turn, damage_reduction 2    |
| anchored_boots (Millstone)    | feet     | 350 steps    | speed -40 (60%), no_run              | speed +50, 2 dash charges/floor     |
| collar_of_contrition          | neck     | 35 kills     | -3 STR/-3 STS, vuln_mult 1.25       | +4/+4/+2, reflect 15%, 25 armor     |
| ring_of_the_condemned         | ring     | 400 steps    | hp_cap 50% of max HP                 | +5 CON, +50 flat HP, low-HP 1.5x   |
| the_albatross                 | weapon   | 30 kills     | xp_blocked (all XP = 0)             | xp_multiplier 2.0, reach 2, 14 base |
| cursed_cylinder               | sidearm  | 300 steps    | misfire 25% (5 self-dmg)            | 3-shot, free reload, Fan ability    |
| ring_of_static_noise          | ring     | 20 kills     | ability_lockout, -4 BKS             | +6 BKS, +8 spell dmg, 2 SP/floor   |
| crown_of_thorns_and_dollars   | hat      | 15 kills     | $30/kill drain, no_loot_pickup       | +6 SWG, $20/kill, intimidation aura |

## New Item Fields (this batch)

on_hit_self_damage: int, cash_drain_per_kill: int, no_loot_pickup: bool, cash_on_kill: int,
intimidation_aura: bool, curse_unlock_kills: int, vulnerability_multiplier: float,
damage_reflection: float, hp_cap: float, hp_bonus: int, damage_at_low_hp: bool,
xp_penalty: bool, misfire_chance: float, curse_gun: bool, ability_lockout: bool,
spell_damage_bonus: int, sp_regen: int, dash_charges: int, speed_penalty: int, no_run: bool,
hp_drain_per_turn: int, incoming_damage_bonus: int, regen_per_turn: int, damage_reduction: int

## New PlayerStats Fields (this batch)

sight_radius_bonus*, sound_radius_bonus*, no_map_memory, telepathy, speed_bonus,
movement_cursed, hp_cap_ratio, max_hp_bonus, incoming_damage_bonus, damage_reduction,
regen_per_turn, hp_drain_per_turn, vulnerability_multiplier, xp_blocked, ability_locked,
spell_damage_bonus*, sp_regen*

(*) Some of these overlap with fields proposed in earlier batches.

## New Abilities (this batch)

- "millstone_dash": ADJACENT_TILE, PER_FLOOR max_charges=2 (Millstone Boots blessed)
- "blessed_cylinder_fan": SINGLE_ENEMY_LOS, FLOOR_ONLY (Cursed Cylinder blessed — fire all ammo)

## Key Design Patterns Established

- Cursed item stat blocks: two logical configs per item_id (cursed vs blessed); engine flag selects.
- hp_drain_per_turn / regen_per_turn: handled in _run_energy_loop BEFORE player action, not as Effect.
- no_loot_pickup: checked in handle_move() auto-pickup logic. Blocks new pickups; doesn't clear inventory.
- ability_lockout: checked in spells.py execute AND ability menu render ("[STATIC]" label).
- vulnerability_multiplier: applied in combat.py AFTER defense/armor, multiplicative.
- damage_reflection: applies after final damage calc to player; attacker.take_damage(true dmg).
- intimidation_aura: checked in ai.py do_ai_turn(); 25% fear proc on enemies within radius 3.
- hp_cap_ratio: entity.heal() capped to int(max_hp * hp_cap_ratio). Immediate HP trim on equip.
- xp_blocked: checked in all xp_progression.py gain functions; suppresses messages too.
- misfire_chance: checked in gun_system.py fire_gun(); misfire = self-damage + consume ammo.
- Curse rendering: purple tint on cursed item char; gold tint on blessed; one-time "CURSE BROKEN" msg.

## Balance Anchors

- Fastest unlock: Crown 15 kills (but floor 4 only, loot vacuum cost)
- Longest step curse: Blindfold 500 steps (~2.5 floors of exploration)
- Biggest stat swing: Collar — from -3/-3 to +4/+4/+2 (net +14 stat points total)
- Highest vampiric: Penitent 35% (above Bone Club 30%, above Blooded Shank 20%)
- Unique mechanics not found elsewhere: telepathy (Blindfold), regen_per_turn (Ring of Pain),
  free-reload sidearm (Cursed Cylinder), hp_cap (Condemned Ring), 2x XP (Albatross)

**Why:** Established the cursed-to-blessed pattern as a full 10-item batch, expanding the
Soul Edge Shard's single precedent into a proper mechanical archetype.
**How to apply:** When designing future cursed items, reference curse durations above and
ensure blessed payoff includes at least one mechanically unique effect unavailable elsewhere.
