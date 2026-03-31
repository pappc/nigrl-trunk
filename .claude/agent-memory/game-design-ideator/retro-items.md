---
name: Retro Reference Unique Items
description: 25 equipment items referencing classic retro games (NES/SNES/N64/Genesis/GB/arcade/PS1) with NIGRL-appropriate parody names and mechanically deep effects. Saved 2026-03-26.
type: project
---

## Design Doc
`nigrl-ideas/retro-reference-unique-items.txt`

## 25 Items at a Glance

| # | Item Name | Ref Game | Slot |
|---|-----------|----------|------|
| 1 | Plumber's Red Cap Pipe | Super Mario Bros (NES) | weapon |
| 2 | Spindash Knuckle Blade | Sonic the Hedgehog (Genesis) | weapon |
| 3 | Master Swordless (It's a Stick) | Zelda: A Link to the Past (SNES) | weapon |
| 4 | Blue-Back Critter Grabber | Pokemon Red/Blue (GB) | weapon |
| 5 | Rush Man's Slide Arm | Mega Man (NES) | weapon |
| 6 | Hadouken Handwraps | Street Fighter II (Arcade) | weapon |
| 7 | Morph-Ball Flail | Metroid (NES) | weapon |
| 8 | Whip of Dracula's Crib | Castlevania (NES) | weapon |
| 9 | Thunder Punch of Champ Row | Mike Tyson's Punch-Out!! (NES) | weapon |
| 10 | Ring of the Master Catcher | Pokemon Red/Blue (GB) | ring |
| 11 | Contra Code Loop | Contra (NES) | ring |
| 12 | Golden Tri-Ring | Legend of Zelda (NES/SNES) | ring |
| 13 | Eye of the Arcanist | Final Fantasy (NES) | ring |
| 14 | DK Barrel Ring | Donkey Kong Country (SNES) | ring |
| 15 | Pac-Dot Chain | Pac-Man (Arcade) | neck |
| 16 | Chrono Pendant | Chrono Trigger (SNES) | neck |
| 17 | Dog Tag of Liberty | Metal Gear Solid (PS1) | neck |
| 18 | Star Fox Step Boosters | Star Fox (SNES) | feet |
| 19 | EarthBound Hike Boots | EarthBound/Mother 2 (SNES) | feet |
| 20 | Renegade Roller Blades | Streets of Rage/Double Dragon | feet |
| 21 | Doom Marine Boots | Doom (PC) | feet |
| 22 | Samus's Visor (Cracked) | Metroid/Super Metroid | hat |
| 23 | Kirby's Puffed Cap | Kirby's Dream Land (GB) | hat |
| 24 | GoldenEye Ear Piece | GoldenEye 007 (N64) | hat |
| 25 | Galaga Bug Antenna | Galaga (Arcade) | hat |

## Key New Item Fields Introduced

- on_kill_heal_chance: dict (chance, amount, max_hp_bonus_on_full)
- on_hit_dash_through: dict (chance, tiles) — weapon step-back on hit
- triforce_slot_bonus: int — bonus damage per filled equipment slot
- on_hit_capture_check: dict (threshold, base_chance, per_floor_bonus) — monster capture
- per_kill_type_damage_bonus: dict — +X% per distinct enemy type killed this run
- on_low_hp_slide: dict — auto-dodge reaction when taking damage below threshold
- chip_damage: int — flat damage that bypasses defense
- focus_attack_chain: dict — stun on Nth consecutive hit on same target
- bounce_bomb_counter: dict — AOE bomb every N hits
- weapon_min_reach: int — minimum attack range (can't hit adjacent)
- on_hit_cross_toss: dict — projectile arc on hit chance
- star_punch_gain_on_hit: int — stars gained per incoming damage
- equip_passive_calm_chance: float — % chance to delay enemy's CHASING transition
- death_prevent_once_per_floor: bool — survive at 1 HP once per floor (consumes ring)
- tri_ring_balance_bonus: dict — bonus when 3 specified stats are equal
- equip_spell_charges_bonus: int — extra PER_FLOOR charges to all abilities
- equip_spell_damage_bonus: int — flat bonus to is_spell=True abilities
- on_pickup_energy_burst: dict — energy + speed burst on item pickup
- dual_tech_per_floor: int — chain a second ability for free after the first
- equip_alert_intercept_chance: float — cancel enemy ALERTING state
- equip_fear_linger: int — extra turns enemies stay in FLEEING
- barrel_roll_per_floor: bool — negate one hazard/melee trigger per floor
- move_cost_reduction: int — reduce energy cost of movement actions
- equip_homesick: bool — XP bonus scales with floor depth
- blitz_attack: dict — bonus damage + knockback after 3+ tiles of movement
- unarmed_damage_bonus: int — bonus damage when no weapon equipped
- energy_tank_floor_burst: dict — auto-heal when HP drops below high-water threshold
- energy_tank_shield: dict — flat damage reduction above HP threshold
- equip_food_heal_bonus: int — extra HP on food completion
- auto_aim_first_shot: bool — first gun shot per floor auto-hits + 50% dmg
- equip_fov_bonus: int — additional FOV radius tiles
- equip_tractor_beam: dict — pull enemy closer for N turns (passive proc)
- equip_idle_approach_bonus: bool — idle/wandering enemies step extra tile toward player

## New Effects Needed
BerserkEffect (15t 2.5x melee + 20% dmg resist), ExhaustionEffect (5t -3pwr +20movecost),
OneUpEffect (floor_duration stacking max HP bonus), CalmEffect (enemy: blocks ALERTING),
SlidePassiveEffect (once-per-floor reaction dodge), BerserkPackAbility (SELF, ONCE)

## New Engine State Needed
engine.enemies_killed_types: set[str] (unique enemy types killed this run)
engine.captured_monster_template: str|None
engine.focus_attack_state: dict
engine.star_punch_stars: int [0-3]
engine.weapon_hit_counter: int (per floor)
engine.dual_tech_remaining + engine.pendant_tp (per floor)
engine.tractor_beam_remaining, engine.auto_aim_remaining, engine.barrel_roll_remaining (per floor)
engine.player_visor_high_hp: int (per floor)
engine.player_tiles_moved_this_turn: int (per turn)
engine.pac_streak: int (reset on damage)
engine.player_stats.no_damage_turns: int
engine.player_stats.move_cost_reduction: int

## Zone Assignment
Crack Den only: items 1, 2, 3, 5, 8, 11, 12, 14, 15, 23, 25, 18
Meth Lab only: item 16 (Chrono Pendant), 21 (Doom Boots), 22 (Samus Visor)
Both zones: items 4, 6, 7, 9, 10, 13, 17, 19, 20, 24

## Rarity Convention
All items use weight: 1 (very rare). Tag: "retro_special" for easy loot.py filtering.

## Design Principle Established
Retro reference items should match the SOURCE GAME'S feel in their mechanic:
  - Speed game (Sonic) → speed/repositioning mechanics
  - Collection game (Pokemon) → capture/thrall mechanics
  - Power fantasy game (Mega Man) → accumulate power per enemy type killed
  - Symmetry game (Zelda) → bonus for balanced/complete kits
  - Rhythm game (Punch-Out) → set up stars by getting hit, then cash in
