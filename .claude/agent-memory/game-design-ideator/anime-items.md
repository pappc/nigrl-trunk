---
name: Anime Reference Unique Items
description: 25 equipment items referencing anime series (DBZ, Naruto, One Piece, Bleach, AOT, MHA, JJK, Demon Slayer, HxH, Death Note, FMA, Cowboy Bebop, EVA, SAO, JoJo, OPM, Mob Psycho, Chainsaw Man, Berserk). Saved 2026-03-26.
type: project
---

## Design Doc
`nigrl-ideas/anime-reference-unique-items.txt`

## 25 Items at a Glance

| # | Item Name | Anime Ref | Slot |
|---|-----------|-----------|------|
| 1 | Saiyan Rage Knuckles | DBZ — Zenkai/Saiyan power-up | weapon |
| 2 | Shadow Clone Shiv | Naruto — Shadow Clone Jutsu | weapon |
| 3 | Straw Hat's Gum-Gum Glove | One Piece — Gomu Gomu devil fruit | weapon |
| 4 | Bankai Release Blade | Bleach — Bankai escalation system | weapon |
| 5 | ODM Gear Hook Blade | AoT — ODM gear + nape strike | weapon |
| 6 | One For All Handwraps | MHA — OFA power stockpile per kill | weapon |
| 7 | Cursed Technique Rags | JJK — Gojo's Infinity veil | weapon |
| 8 | Nichirin Notch Blade | Demon Slayer — breathing form stacks | weapon |
| 9 | Berserk Plate Fragment | Berserk — berserker armor (HP/swing cost) | weapon |
| 10 | Conqueror's Haki Loop | One Piece — Haoshoku Haki room-clear | ring |
| 11 | Death Note Ring | Death Note — write a name/pay max HP | ring |
| 12 | Nen Binding Ring | HxH — Emperor Time (single ring only) | ring |
| 13 | Mob's 100% Ring | Mob Psycho — 0-100% psychic meter | ring |
| 14 | Contract Devil Sigil Ring | Chainsaw Man — devil contract (can't unequip) | ring |
| 15 | Equivalent Exchange Chain | FMA — transmute (lose half HP for random buff) | neck |
| 16 | AT Field Pendant | EVA — sync rate + armor scaling | neck |
| 17 | Bebop Bandolier | Cowboy Bebop — bounty XP + gun-fu | neck |
| 18 | Zoro's Three-Step Boots | One Piece — 20% random direction movement | feet |
| 19 | Flash Step Sneakers | Bleach — Shunpo teleport + after-image dodge | feet |
| 20 | OPM Workout Kicks | OPM — mundane step count → Serious Punch | feet |
| 21 | Straw Hat's Actual Straw Hat | One Piece — once-per-run death nullify | hat |
| 22 | Titan Shifter Headwrap | AoT — titan shift transformation (PF1) | hat |
| 23 | Quirk Suppression Cap | MHA — FOV-based special attack erasure | hat |
| 24 | Sorcerer's Domain Hat | JJK — domain expansion (ONCE, sure-hit crits) | hat |
| 25 | Dio's Time Stop Hat | JoJo — ZA WARUDO time stop (PF1, 5 turns) | hat |

## Key New Item Fields Introduced
- zenkai_awakening_bonus: int (flat dmg at <25% HP)
- shadow_clone_chance: float (double-hit proc)
- rubber_immune_shock: bool (shock immunity)
- gear_second_proc_chance: float (reactive speed burst on taking hit)
- nape_strike_multiplier: float (3x for behind-attacks via last_move_dir)
- ofa_damage_per_kill: float (1.5 flat dmg per run-wide kill count)
- breathing_form: bool (stack management: 0-12, changes on-hit elemental behavior)
- devil_leech_per_kill: int (unconditional HP per kill)
- lost_but_lethal_chance: float (random redirect + free adjacency hit)
- shunpo_teleport_range: int (extended range tile targeting)
- erasure_fov_suppression: bool (suppresses enemy specials in FOV)
- time_stop_turns: int (player actions during time stop)
- dios_pride_dodge_penalty: float (-10% dodge while equipped, outside time stop)

## Key New Engine Fields
engine.zenkai_damage_taken, engine.ofa_kill_stockpile, engine.bankai_release_state,
engine.brand_debt, engine.berserk_active, engine.mob_percent, engine.at_sync_rate,
engine.infinity_veil_active, engine.breathing_form_stacks, engine.time_stop_active,
engine.domain_expansion_active, engine.quirk_suppression_active, engine.erased_entities

## Key Design Patterns Established
- "Power at a cost" is central — every top-tier anime item has a meaningful drawback.
- ONCE-per-run abilities (Straw Hat will, Domain Expansion) are acceptable for
  extraordinarily powerful effects if the reset is genuine and permanent.
- Time Stop (ZA WARUDO) implemented as loop control (skip enemy processing N turns),
  NOT as a freeze effect on individual entities. Simpler and cleaner.
- Bankai state system (0/1/2 engine int) is the template for multi-state weapon toggles.
- Domain Hat + Dio Hat mutual exclusivity: use engine.dominant_hat_spawned flag in loot.py.
- entity.last_move_dir: (dx, dy) field enables behind-attack detection (ODM blade).
- Death Note: engine.player_stats.max_hp_penalty field (new, subtracted from max HP).

## Zone Assignment
- Crack Den only: items 1-7, 9-15, 17-21
- Meth Lab only: items 16 (AT Field), 23 (Quirk Cap), 24 (Domain Hat), 25 (Dio Hat)
- Both zones: items 3, 5, 7, 8, 9, 12, 13, 14, 15, 17, 18, 19
