# Game Design Ideator — Agent Memory

## Core Constants

- Output dir: `nigrl-ideas/` → `C:/Users/pappc/claude-projects/nigrl-trunk/nigrl-ideas/`
- XP curve: [200,400,600,800,2000,6000,15000,25000,100000,500000] (total: 649,000)
- Book Smarts SP rate: min(0.5, 0.1 + 0.3*sqrt(bksmt/80)). At bksmt=0: 10%. At bksmt=50: ~34%.
- Player HP: 30 + CON*10. At CON 10: 130 HP. Swagger defence: int((eff_swg-8)/2).
- Crit chance: street_smarts*3%. Enemy HP: base_hp + con*5. Enemy dmg floor 1-2: 4-8.
- Energy: 100/tick base. +30 = ~23% faster. MEGA_CRIT_MULTIPLIER = 4.
- Stat names: constitution, strength, street_smarts, book_smarts, tolerance, swagger

## Perk Type Vocabulary

- "none" → placeholder | "stat" → {stat_name: int} | "passive" → always-on | "activated" → {"ability": id}
- Stat bonuses can be NEGATIVE (Negromancy L2, Meth-Head L2). Mixed stat+ability dicts valid.

## Skill Trees Summary

32 total skill trees in skills.py. Skills with partial/full content:
  Smoking, Rolling, Stabbing, Alcoholism, Munching, Pyromancy, White Power, Mutation (L1-L3)
Full L4/L5 designs: `nigrl-ideas/skill_perks_L4_L5.txt`. Table: `nigrl-ideas/skills_and_perks_table.txt`

## Design Docs Index (by topic file)

### Equipment
- `nigrl-ideas/ability-granting-unique-items.txt` — 10 ability-granting uniques (4 resource-system, 6 single-ability); summary in `summaries/ability-granting-unique-items-summary.txt`
- `nigrl-ideas/ability-granting-batch2-currency.txt` — 13 resource/currency system uniques (all slots, 2 guns); summary in `summaries/ability-granting-batch2-currency-summary.txt`
- `nigrl-ideas/ability-granting-batch2-single.txt` — 12 single-ability uniques (all slots incl. first slashing weapon unique + first gun unique); summary in `summaries/ability-granting-batch2-single-summary.txt`
- `nigrl-ideas/osrs-unique-items.txt` — 25 OSRS-inspired uniques (all slots, 3 guns); summary in `summaries/osrs-unique-items-summary.txt`
- [legendary-items.md](legendary-items.md) — Items 1-10, Batches 1-4 (1-40), `legendary-equipment-designs.txt`
- [trad-roguelike-equipment.md](trad-roguelike-equipment.md) — Items 41-50 NetHack/DCSS/ADOM; `traditional-roguelike-inspired-equipment.txt`
- [unique-equipment.md](unique-equipment.md) — 10 build-defining uniques; `unique-equipment-designs.txt`
- [retro-items.md](retro-items.md) — 25 NES/SNES/N64 refs; `retro-reference-unique-items.txt`
- [anime-items.md](anime-items.md) — 25 anime refs; `anime-reference-unique-items.txt`
- `nigrl-ideas/retro-anime-unique-items-batch1.txt` — 25 Batch 1 items (PS1/N64/DC/GBA + 90s anime); summary in `summaries/retro-anime-batch1-summary.txt`
- `nigrl-ideas/retro-anime-unique-items-batch2.txt` — 25 Batch 2 items (PS1/DC/GBA/anime); summary in `summaries/retro-anime-items-batch2-summary.txt`
- [new-guns.md](new-guns.md) — 12 guns; `new-gun-concepts.txt`; [gun-trees.md](gun-trees.md) — 5 gun skill trees
- [gun-consumables.md](gun-consumables.md) — 10 gun consumables; `gun-consumable-designs.txt`
- `nigrl-ideas/unique-gun-designs.txt` — 10 unique guns (zones: [], special acquisition); summary in `summaries/unique-gun-designs-summary.txt`
- [meth-lab-weapons.md](meth-lab-weapons.md) — 8 stab weapons; `meth-lab-stab-weapons.txt`
- `nigrl-ideas/slashing-weapons-and-skill-tree.txt` — 10 slashing weapons + 5 L1-L3 variations
- `nigrl-ideas/indie-unique-items-batch1.txt` — 25 indie 2010-2020 refs; summary in `summaries/indie-unique-items-batch1-summary.txt`
- `nigrl-ideas/indie-unique-items-batch2.txt` — 25 indie golden age Batch 2; summary in `summaries/indie-unique-items-batch2-summary.txt`
- [cursed-blessed-items.md](cursed-blessed-items.md) — 10 cursed-to-blessed uniques; `cursed-to-blessed-unique-items.txt`; kill-counter unlock + 24 new fields
- `nigrl-ideas/unique-items-batch3.txt` — 25 original uniques (all slots); summary in `summaries/unique-items-batch3-summary.txt`
- `nigrl-ideas/poe-wow-unique-items.txt` — 25 PoE/WoW inspired uniques (all slots, 3 guns); summary in `summaries/poe-wow-unique-items-summary.txt`
### Strains / Drugs / Drinks
- [str-rad-strains.md](str-rad-strains.md), [bksmt-rad-strains.md](bksmt-rad-strains.md), [tox-tolerance-strains.md](tox-tolerance-strains.md)
- [swagger-strains.md](swagger-strains.md) — SWG strains V2; `swagger_mutation_strain_designs_v2.txt`
- `nigrl-ideas/stat-scaling-strains-v2.txt` — 30 strains V2 (CURRENT)
- [roguelike-drinks.md](roguelike-drinks.md) — 30 roguelike drinks; `roguelike-inspired-drinks.txt`
- [meth-lab-drinks.md](meth-lab-drinks.md) — 10 Meth Lab drinks; [colored-dranks.md](colored-dranks.md) — 14 colored dranks
- [food-compendium.md](food-compendium.md) — 50+35 foods; `item-food-compendium.txt`, `roguelike-inspired-foods-part2.txt`; + 6 meth lab tox-removal foods `item-meth-lab-tox-foods.txt`

### Skills / Abilities
- `nigrl-ideas/wow-inspired-melee-abilities.txt` — 25 WoW-adapted melee abilities; all 4 weapon types
- [arachnigga-skill.md](arachnigga-skill.md) — 5 tree proposals, cobweb/venom
- [blackkk-magic-trees.md](blackkk-magic-trees.md) — 10 designs V2; `blackkk-magic-skill-designs-v2.txt`
- `nigrl-ideas/mutation-branching-skill-trees.txt` — 10 branching Mutation trees (all 10 shapes); summary in `summaries/mutation-branching-skill-trees-summary.txt`
- [graffiti-skill.md](graffiti-skill.md) — L1-L5 Tag→Bombing Run; `graffiti-skill-designs.txt`
- [beating-trees.md](beating-trees.md) — 10 L4+L5 variants; `beating-skill-tree-designs.txt`
- [stabbing-branching-trees.md](stabbing-branching-trees.md) — V1+V2 (10 total); two .txt files
- [cryomancy-skill.md](cryomancy-skill.md) — 5 L1-L6 takes; `cryomancy-skill-tree-designs.txt`
- [electrodynamics-skill.md](electrodynamics-skill.md) — 5 L1-L6 takes; `electrodynamics-skill-tree-designs.txt`
- `nigrl-ideas/pyromancy-skill-tree-designs.txt` — 5 L1-L6 takes (RENAME Pyromania→Pyromancy)
- `nigrl-ideas/rolling-branching-skill-trees.txt` — 5 branching designs
- `nigrl-ideas/pyromania-branching-skill-trees.txt` — 5 branching designs
- `nigrl-ideas/gatting-branching-skill-trees.txt` — 10 branching designs; summary in `summaries/gatting-branching-skill-trees-summary.txt`
- `nigrl-ideas/skill_perks_L4_L5.txt` — L4/L5 for 14 trees
- `nigrl-ideas/chemical-warfare-skill-tree-variations.txt` — 10 L1-L4 variations; summary in `summaries/chemical-warfare-variations-summary.txt`
- `nigrl-ideas/chemical-warfare-branching-skill-trees.txt` — 10 branching topology variations (Y-split x2, Diamond x3, Triple Fork x2, W-shape x2, Long Trunk Y x1); summary in `summaries/chemical-warfare-branching-trees-summary.txt`
- `nigrl-ideas/white-power-branching-skill-trees.txt` — 10 branching topology variations (all 10 shapes, each used once); summary in `summaries/white-power-branching-trees-summary.txt`
- `nigrl-ideas/white-power-tox-inversion-trees.txt` — 10 NEW branching trees; TOX INVERSION as core mechanic (tox = less damage taken AND dealt); all 10 shapes; summary in `summaries/white-power-tox-inversion-summary.txt`
- `nigrl-ideas/nuclear-research-branching-skill-trees.txt` — 10 branching Nuclear Research trees (all 10 shapes); BKS-scaling rad spells, 16 new abilities; summary in `summaries/nuclear-research-branching-trees-summary.txt`
- [spell-compendium-index.md](spell-compendium-index.md) — full ability index across all compendium docs
- `nigrl-ideas/skill-deep-frying-combat-abilities.txt` — 10 Deep-Frying L3-L10 abilities (CON-scaling DPS tree); summary in `summaries/skill-deep-frying-combat-abilities-summary.txt`
- `nigrl-ideas/deep-frying-skill-tree-variants.txt` — 10 complete L1-L10 Deep-Frying tree layouts (10 themes); summary in `summaries/deep-frying-skill-tree-variants-summary.txt`
- `nigrl-ideas/smartsness-branching-skill-trees.txt` — 10 L1-L3 Smartsness variations; all 30 perks new; 10 abilities, 8 effects; summary in `summaries/smartsness-branching-skill-trees-summary.txt`
- `nigrl-ideas/skill-decontamination-perks-L3-L6.txt` — 6 perk options for Decon L3-L6; new rad_tiles dungeon system, HalfLifeAuraEffect, Consecrate/Sponge/Wake; summary in `summaries/skill-decontamination-perks-L3-L6-summary.txt`
- `nigrl-ideas/skill-decontamination-L2-aura-perks.txt` — 6 Decon L2 toggleable aura options (replaces Emission); Half-Life Field/Purification Corona/Sanctified Ground/Radiant Judgment/Ironsoul Aura/Abscess Ward; summary in `summaries/skill-decontamination-L2-aura-perks-summary.txt`
- `nigrl-ideas/skill-decontamination-L4-aura-options.txt` — 6 Decon L4 toggle aura options; Sacred Ground/Divine Sight/Corona of Judgment/Penitent/Absolution/Ironsoul; summary in `summaries/skill-decontamination-L4-aura-options-summary.txt`
- `nigrl-ideas/skill-decontamination-L5-consecrate-upgrade.txt` — 6 Decon L5 Consecrate upgrade options (+30 max armor passive decided); Nuclear Verdict/Sanctified Discharge/Scourging Flame/Divine Terror/Cursed Earth/Judgment Strike; summary in `summaries/skill-decontamination-L5-consecrate-upgrade-summary.txt`
- `nigrl-ideas/skill-decontamination-L6-aura-options.txt` — 6 Decon L6 capstone offensive auras; Wrath of God/Corona of Judgment/Martyr's Fire/Penitent/Radiant Presence/Atomic Fist; summary in `summaries/skill-decontamination-L6-aura-options-summary.txt`
- `nigrl-ideas/consecrate-ability-designs.txt` — 5 distinct Consecrate variants (Decon L3); all use 5x3 directional zone; Iron Seal/Flensing/Cyclone/Vigil/Judgment; summary in `summaries/consecrate-ability-designs-summary.txt`

### Abilities
- `nigrl-ideas/poe-inspired-melee-abilities.txt` — 25 PoE-inspired melee abilities; all 4 weapon types; strikes/slams/warcries/passives/triggers

### Mechanics / World
- [zone2-meth-lab.md](zone2-meth-lab.md) — Meth Lab full design (toxicity + meth meter)
- [arpg-mechanics.md](arpg-mechanics.md) — Ward, Leech, Threshold, Shred, Impale etc.
- `nigrl-ideas/mechanic-branching-skill-trees.txt` — BTD6-inspired L4 branch system
- Spray paints: 25 total. V2 `spray-paint-designs-v2.txt`, V3 `spray-paint-designs-v3.txt`, V4 `spray-paint-designs-v4.txt`; summaries in `summaries/`; V4 adds Midnight/Magenta/Navy/Amber/Bone/Slate/Chartreuse/Umber/Tawny/Indigo; new fields: tile_dodge_bonus, tile_swagger_mult
- `nigrl-ideas/dungeon-generation-designs.txt` — 9 room generation techniques
- [spider-event.md](spider-event.md) — Spider Infestation; `spider-enemy-roster.txt`, `black-widow-boss-designs.txt`
- `nigrl-ideas/tyrone-penthouse-features.txt` — 12 Penthouse hub features (NPCs, interactables, services); summary in `summaries/tyrone-penthouse-features-summary.txt`
- `nigrl-ideas/tyrone-penthouse-npcs-new7.txt` — 7 new one-time free service NPCs (Delroy/Bartender, La'Quisha/SkillTrader, Rico/Pawn, Precious/Tattoo, DrPill/Ability, Marcus/Intel, BigJerome/Coach); summary in `summaries/tyrone-penthouse-npcs-new7-summary.txt`
- `nigrl-ideas/tyrone-penthouse-npcs-final4.txt` — Final 4 NPCs completing pool of 10 (Soloman/Enchanter, Deja/Mixologist, Kline/GeneDoctor, Carlton/Fixer); adds entity.enchanted_locked, player_stats.permanent_penalties ledger, 8 cocktail items, VenomSlingEffect; summary in `summaries/tyrone-penthouse-npcs-final4-summary.txt`
- `nigrl-ideas/brainstorm-penthouse-npc-tenth.txt` — 6 concepts for the 10th/final Penthouse NPC; top picks: Darnell (run-history tally mirror, A+), Sandman (blind ability-charge cost for sleep benefits, A), Lola (3 permanent movement techs, B+); summary in `summaries/brainstorm-penthouse-npc-tenth-summary.txt`
- NOTE: Canonical in-game Penthouse NPCs (9 existing): Gun Dealer, Chef, Plug, La'Quisha, Precious, Rico, Soloman, Sage/Mixologist (drink on rocks), Dice/Craps Dealer. Deja/Kline/Carlton are designed but not yet implemented.
- `nigrl-ideas/mutation-overhaul/mutation-overhaul-plan.txt` — FULL OVERHAUL V2: remove Huge tier, 80 mutations (20wG/20wB/20sG/20sB), upgrade system (re-roll = upgrade), 10 new effects, 5 new abilities; summary inside mutation-overhaul/ subdir
- `nigrl-ideas/mutation-overhaul/rimworld-inspired-mutations.txt` — 20 additional mutation candidates (5wG/5wB/5sG/5sB); Rimworld Biotech inspired; full L1-L3 specs
- `nigrl-ideas/mutation-overhaul/qud-rimworld-hybrid-mutations.txt` — 10 hybrid mutations (3wG/2wB/3sG/2sB); Qud verbs + Rimworld costs; Force Barricade/Body Jack/Glimmer Buildup/Evil Twin; NOTE: all mutation docs now live in mutation-overhaul/ subdir

## Key Engine/System Notes

### Equipment Fields (items.py)
Existing weapon fields: vampiric, on_hit_effect, on_hit_stun_chance, str_scaling (tiered/ratio/dim),
  reach, weapon_type, bonus_crit_mult, grants_ability, on_hit_rad, thorns, execute, on_hit_knockback,
  on_hit_bounce, on_hit_sunder, break_hits/break_final_mult, on_hit_tox, on_hit_skill_xp
New fields proposed (various batches): starts_cursed, curse_unlock_steps, unique_id, unique_item,
  on_kill_drug_drop, tox_resistance, rad_resistance, conditional_tox_resistance, energy_per_tick
Slashing weapon fields proposed: on_hit_bleed {chance, amount, duration}, on_hit_lacerate {stacks},
  on_hit_cleave {chance, damage_pct}
Unique gun fields proposed: vampiric_gun/vampiric_gun_amount, tox_on_hit (gun), bksmt_scaling_gun/bksmt_scaling_ratio,
  ricochet/ricochet_damage_pct/ricochet_range, wind_up_gun/wind_up_per_turn/wind_up_max_turns,
  hp_cost_gun/hp_cost_per_shot, ambush_first_shot/ambush_crit_bonus_mult, panic_scaling/panic_scaling_cap,
  full_mag_dump/full_mag_dump_min_shots, earned_power/earned_power_per_kills/earned_power_cap
Unique gun render rules: mag_size==999 → display "inf"; wind_up_gun → show "Charged: +N dmg" in gun info

### New Lifecycle Hooks Proposed
- Effect.modify_heal(amount, entity, engine) -> int — block/modify healing (Leech Chain Blood Frenzy)
- on_after_damage(entity, engine, damage) — post-damage hook (Shadow compendium)
- modify_incoming_heal(amount, entity, engine) -> int — reduce enemy healing (Mortal Wound, V3P2 shadow)
- apply_elemental_gun_hit(engine, target) — after confirmed gun hit (gun consumables)

### New Entity Fields Proposed (cumulative)
entity.is_boss, entity.fresh_corpse, entity.is_thrall, entity.last_move_dir, entity.ambush_eligible,
entity.elements_received, entity.frost_patch_duration, entity.dirty_south_filth, entity.shadowbox_combo, entity._prophecy_charge

### New Engine State Proposed (cumulative)
soul_shards, talisman_kills/mercy_moves/mode, reaping_charge_pool, roller_momentum_debt,
chain_first_use_set, wind_up_charged, horseshoe_reroll_used_this_turn, unique_effects_applied,
gun_accuracy/damage_bonus, killstreak_count, _shadow_dark, _active_herald, last_completed_food_id,
first_blood_hit_set, _slashing_fast_bleed, grit_charges, last_kill_was_melee, player_free_action,
haymaker_counter, rage_stacks/rage_timers, last_rites_cooldown, crit_burst_cooldown,
blood_oath_pending, berserk_stun_on, curse_broken_{item_id} (10 flags; cursed-blessed batch),
job_wind_up/job_equip_id (Patience of Job), cold_open_shot_targets: set (reset/floor),
respect_kills/respect_bonus (persist til unequip; run-wide kill counter)
mutation_count (run-wide), mutation_reroll_available/genome_locked_stat (per-floor), rad_berserker_stacks/freak_speed_stacks (per-floor),
adaptive_dr_bonus/scar_tissue_hits/last_mutation_was_good/mutation_streak (run-wide),
irradiate_splash_radius, contamination_cloud_active, forced_strong_next/forced_huge_next,
mutation_xp_multiplier (float), genome_splice_used (bool), forced_evolution_charges (per-floor)
### Mutation Overhaul V2 — New Engine/PlayerStats State (mutation-overhaul-plan.txt)
player_stats: ~65 bool/int flags (see doc), necrotic_fist_penalty(int), blocked_equip_slots(set), mut_fov_bonus(int), mut_gun_range_penalty(int), max_hp_penalty(int)
engine per-floor: adrenaline_surge_used, turtle_neck_triggered, mut_first_hit_buffer, wall_crawler_inside, reflex_counter_pending, chitin_hit_streak, rad_absorb_bonus, slow_blink_combat_active, slow_blink_turns_remaining, phantom_hunger_counter, hyperactive_bladder_counter, parasitic_relationship_counter, sensory_safe_dir, hollow_echo_pending
engine run-wide: redundant_organs_death_save_used, redundant_organs_death_saves_remaining, mutation_levels(dict[str,int]), degen_nervous_cooldown_bonus(int)
Reversal types: "grant_ability","flag","speed","fov_bonus","slot_block","compound","ability_and_flag","stat_and_flag"
Huge tier REMOVED. Strong threshold bumped to 150. 80 mutations total. Upgrade system: re-roll = upgrade (mutation_levels dict). Light Sensitivity REMOVED.
New abilities: acid_spit (ADJACENT→LOS at L3), telekinetic_lash (SINGLE_LOS,3-5/floor), touch_of_frost/fire/shock (ADJACENT, INFINITE, cooldown-based)
New effects: HardeningEffect, FeralRushEffect, CorrodedEffect, SpikedEffect, ExhaustedEffect, EnragedEffect, MetabolizedEffect
wp_fortress_stacks (per-floor; clears on move), wp_crust_stacks (per-turn decay), wp_scab_charged (per-hit),
wp_martyr_stacks (run-persistent), wp_oath_pool: float (run-persistent), wp_inversion_prevented_dmg (per-floor),
wp_tincan_hits_remaining (per-floor), wp_room_first_hit (per-room), wp_kiln_regen_bonus, wp_last_armor_value
### Consecrate Ability Designs — New Engine State (per-floor unless noted)
dungeon.rad_tiles: dict[tuple, tuple] = {(x,y): (turns_remaining, mode_str)} — mode strings:
  "ironseal"|"flensing"|"cyclone"|"vigil"|"judgment"
  NOTE: original L3-L6 doc used dict[tuple,int]; consecrate-ability-designs.txt upgrades to tuple format.
ironseal_depth_map: dict[tuple,int] (pos->col_index), ironseal_hold_streak: int
flensing_executed_ids: set[Entity], cyclone_stand_turns: int
vigil_debuffed_entities: dict[entity,int], vigil_tile_occupancy: dict[tuple,int]
judgment_triggered_ids: set[Entity], judgment_burst_count: int (RUN-WIDE; cap 5),
judgment_xp_pending: int, player_stats.vigil_active: bool (refreshed each tick)
New effects: CycloneSlowedEffect (id="cyclone_slowed", dur=1, energy_gain *=0.6)
             ConsecratedGroundEffect (id="consecrated_ground", dur=1, modify_incoming_damage -= rad//40 cap 6)
### Ability-Granting Batch 2 — New Engine State (single-ability items)
hoodoo_proxy_target_id (str|None; clears on entity death + floor change),
parolee_id (str|None; clears on floor change; kill handler pays $25 payout),
cod_study_target_id (str|None; Coroner's Badge studied target; floor/death clear),
warrant_target_id (str|None; The Warrant wanted target; floor/death clear),
_read_the_room_fov_penalty (int default 0; subtracted from fov_radius in _compute_fov),
stash_sneakers_item_id (str|None; persists floor; drops on unequip),
stash_sneakers_pending_store (bool default False)
### Ability-Granting Currency Batch 2 — New Engine State (resource items)
floor_tracker_rooms (int, 0; cumulative run-wide), floor_tracker_rooms_visited (set, reset/floor),
dodge_ledger_evasions (int, 0; reset on unequip), block_party_ring_blocked (int, 0; reset on unequip),
tox_budget_ring_budget (int, 0; reset on unequip), accumulator_charge (int, 0; reset per floor+unequip),
sawed_off_breach (int, 0; lifetime; reset on unequip), rad_dial_charge (int, 0; reset on unequip),
respect_knucks_chain (int, 0; reset on miss/hit-taken/unequip), respect_knucks_target_id (str|None),
_last_ability_fired_id (str|None; updated after every ability fire — for Inscription Chain)
### Ability-Granting Batch 2 — New Effects
hoodoo_proxy (floor_dur; mirror player-taken dmg to marked enemy; expires on entity death),
parolee (floor_dur; ai_type override to passive_until_hit; compliance stun within 2 tiles),
cause_of_death_mark (dur=8; modify_incoming_damage × (1 + bonus_pct/100); BKS-scaled),
wanted (floor_dur; marker for gun defense-bypass shot; ammo recovery on kill),
read_the_room_active (dur=8; forces all hits to crit; FOV -3 while active)
### Ability-Granting Batch 2 — New Hazard + Enemy
hazard_type="blood_patch" (char='.', red; dur=10; applies bleeding 2t on enemies standing on it)
enemy_type="scurry_rat" (MonsterTemplate spawn_weight=0; only spawned by Swarm Call summon)
### Ability-Granting Batch 2 — New AbilityDef Field
AbilityDef.is_passive: bool = False — if True: UI shows "(passive)" label, no targeting entered

### New PlayerStats Fields Proposed
shock_resistance, fire_immune, tile_armor_bonus, max_hp_penalty, surge_charges,
momentum_kills, crit_multiplier_bonus, tox_gain_reduction, melee_damage_bonus,
+ cursed-blessed batch: hp_cap_ratio, regen/drain_per_turn, speed_bonus, vulnerability_multiplier,
  xp_blocked, ability_locked, spell_damage_bonus, sp_regen, sight/sound_radius_bonus, telepathy, no_map_memory
+ Mutation branching batch: rad_gain_multiplier_bonus (float), mutation_good_base_bonus (float),
  mutation_trigger_multiplier (float), mutation_tier_skip_weak (bool), adaptive_dr (int),
  mutation_melee_bonus (int), rad_to_power_ratio (float), mutation_count_mirror (int)
+ Spray paint v2 batch: tile_max_hp_bonus (int, 0; pink REJECTED), tile_xp_bonus (float, 0.0; teal; mult on all skill XP gains)
+ Spray paint v3 batch: tile_spell_damage_bonus (int, 0; cobalt; reset on step-off), tile_melee_damage_bonus (int, 0; violet; optional inline)
+ Spray paint v3 effect: RustedEffect (id="rusted", floor_duration=True, stacks field max 10; defense reduction read in combat.py)
+ White Power tox inversion batch: tox_inversion_active (bool), wp_inversion_coefficient (float, def 0.5),
  wp_inversion_outgoing_coefficient (float), wp_no_outgoing_penalty (bool), wp_grinding_stone_active (bool),
  wp_paper_wall_used (per-floor bool), wp_iron_will_first_hit (per-floor bool)

### OSRS Batch — New Engine State
spec_energy: float=100.0 (+25/turn; 100 max; shared pool across all spec weapons; display in UI),
granite_free_used_this_turn (bool; reset each turn), berserker_coil_bonus (int; max +8 STR),
calamity_shield_active (bool), snitch_task_enemy_type (str|None; set per floor),
skull_kill_count (int; 3 kills = activate), skull_ring_active/equipped (bool),
seers_bks_kill_stacks (int; max 3), void_item_count (int; count of void-tagged equipped items),
entity.witness_charges: int=50 (ring entity), entity.witness_depleted: bool=False (ring entity)
### OSRS Batch — New Item Fields Proposed
dharoks_passive (bool), smite_drain (bool), vitur_sweep (bool), ignore_dodge (bool),
ignore_defense_chance (float), attack_cost_override (int),
on_gun_hit_tox (int; applies tox after confirmed gun hit), reduced_energy_cost_gun (int),
tox_scaling_gun (dict: bonus_per_100_tox/max_bonus), void (bool; for set counting)

### PoE/WoW Batch — New Engine Flags
glass_cannon_equipped, borrowed_time_equipped, accountability_mirror_budget (per-floor),
meth_lab_overalls_equipped, backpedal_boots_equipped, preachers_belt_equipped,
snitches_get_stitches_equipped, grudge_beads_damage (persist across floors),
prophecy_charges/prophecy_killed_this_floor, street_tax_equipped, hollow_point_hat_equipped,
corner_store_equipped, static_discharge_equipped, snitches_triggered_this_turn (per-turn reset),
deadweight_stacks/no_kill_turns/target_id, knucklehead_dazed_target_id/count,
manifesto_tox_bonus (0-25, run-wide), vicar_proc_active
### PoE/WoW Batch — New Effects
borrowed_time_hot (HoT 5/turn, floor_duration), bks_surge (+1 temp BKS/stack max 4, dur 10),
dazed (-40% energy gain, dur 2)
### PoE/WoW Batch — New PlayerStats
melee_damage_bonus: int (additive to atk_power in _compute_player_attack_power)
### Important Rules
- Multiplicative damage AFTER all additive bonuses (Two Down Ring pattern)
- Debuff duration doubling: multiply `duration` param at apply_effect call site
- Windfury disabled by One For One weapon (one_for_one_weapon)
- force_apply=True on apply_effect bypasses debuff immunity (Magicbane Backfire)
- Angband non-stacking rule: shock_resistance is bool (not stacking int)
- starts_cursed: item can't unequip until curse_unlock_steps walked
- Gun AOE: ceil(num_shots/2) max hits per target (universal rule)
- "Pass turn" check: engine.player_attacked_this_turn flag
- Pyromania → Pyromancy rename needed across: skills.py, engine.py, effects.py, spells.py,
    inventory_mgr.py, items.py, test_bic_torch.py

### Hazard Entity Types
- hazard_type="crate" (0xE000), "fire" (0xE001) — existing
- hazard_type="frost_patch" — proposed (Cold Snap, trad roguelike batch), hazard_duration field
- hazard_type="bomb" — proposed (Bomberman Boots Batch 2), char='*', fuse 3t, cross AOE
- smoke_cloud — proposed (Rolling branching trees)

### Retro/Anime Batch 1 — New Fields (items.py)
hiten_draw_bonus/hiten_pierce_defense, vagrant_risk_weapon, energy_attack_cost_multiplier,
ghost_camo_weapon/ghost_camo_ambush_bonus/ghost_camo_stun_turns,
od_gauge_weapon/od_passive_fill/od_hit_fill/od_burst_damage,
soul_feed_per_kill/soul_feed_max_bonus, plant_regen_per_combat_turn/entangle_chance,
wolf_blade_hunting/resolve_threshold/resolved_bleed/stun_chance,
ginga_chain_weapon/bonus_per_3/cap/sweep_interval/sweep_chance,
caster_discharge/caster_discharge_damage/radius/knockback,
chaotic_amp_scarf/multiplier/self_hit_chance/pyro_free,
tenchu_shadow_kill/sound_radius_reduction, drift_shoes/drift_interval,
seraphic_gate_sandals/einherjar_bonus, defense_vs_ranged (hat/feet)

### Retro/Anime Batch 1 — New Engine State
vagrant_risk (0-100, per-floor), parasite_od_gauge (0-100, per-floor),
soul_edge_kill_bonus (float, persists til unequip), wolf_blade_kills (run-wide),
ginga_chain, deathblow_combo (per floor/miss), majora_floor_timer/majora_desperate_bonus,
player_has_been_seen_this_floor, drift_move_count, einherjar_candidate,
tournament_points/iron_fist_title_earned, spirit_gun_charges (run-wide),
_parasite_eve_full_set, mito_awakening_bonus (perm tol), _hiten_blade_drawn,
ghost_camo_active/ghost_no_attack_turns, caster_shell_discharged, player_was_hit_this_turn,
mercy_band_kills/mercy_band_current_floor_kills, zero_system_kills_this_floor/zero_fever_triggered,
lodoss_spirit_used, nypd_analyzed_this_floor

### Retro/Anime Batch 1 — Key Patterns
- Floor timer: majora_floor_timer (90t countdown, resets). Committed weapon: soul_edge_kill_bonus persists til unequip.
- 3-piece set: Parasite Eve (weapon+ring+neck = OD tripled + all stats). defense_vs_ranged: int on hat/feet.

### Retro/Anime Batch 2 — Key State/Fields
Fields: demolition_shot_interval, assimilate_bonuses, tension_pulse, inverted_scaling, law_chaos_alignment,
  sp_pool_weapon, phase_shift_passive, floor_scan_passive, reishi_absorption, raitei_threshold, monkey_radar,
  graffiti_synergy, hado_tracking, stealing_xp_multiplier
State: hearse_hit_counter, assimilated_enemy_types, tension_meter, gavel_alignment, blue_rogue_sp,
  quincy_gun_bonus, bomberman_bomb_pos/fuse, knocked_back_entities, hado_level, jagan_used_on,
  seen_entities_this_floor (Boogiepop first-sight), fate_heal_triggered_this_floor
PlayerStats: xp_multiplier (Lain, * all skill XP), assimilate_power/speed/hp/tox_bonus
Patterns: inverted scaling (2.0 - hp_ratio), SP pool cross-floor, auto-proc at <25% HP (once/floor flag),
  threat erasure first FOV entry, Monkey Radar '?' rendering in render.py

### Indie Batch 1 — Key State/Fields
Fields: ranged_deflect_chance, katana_damage_vulnerability
State: pale_nail_soul, shade_soul_charged, execution_rush_turns, hotline_panic_mode,
  chrono_first_strike_entities, chrono_pause_active, transistor_function_id, brutality_scroll_count,
  cogmind_scavenged_types, shovel_pogo_charged, boon_seal_trial, thought_cabinet_stats/bonus,
  defect_orb_slots/dark_energy, karma_level/aura_active, dash_charges, mercy_kill_count,
  vs_crit_streak, proselytized_allies, robo_baby_active, drifter_gear_nodes/illness_hp_loss
Patterns: in-item resource (Soul/Orbs/Karma), route-forking (Undertale pacifist/genocide,
  Thought Cabinet behavior mirror), pass-through movement (HLD Boots), enemy conversion (Qud Hood),
  familiar auto-fire (Robo-Baby BKS-scaling). Chaos procs: self-damage or mass-aggro in proc table.

### Indie Batch 2 — Key Design Patterns
- Mutual fragility (Ghostrunner Edge): max HP = 1 via max_hp_penalty; death saves become essential
- Accumulate/reset threshold (Deaths Door, Blasphemous guilt): choose WHEN to cash in charges
- Run-wide degradation (terror 0-100, player_stress 0-10): never reset per floor; compounds
- Environmental fuel (DRG Boots): fire/hazard tiles → power source, not threat
- RNG-as-mechanic (Noita d6, Disco Hat d8, World Seed 1-9999): chaos IS the feature
- Full field/state detail: `summaries/indie-unique-items-batch2-summary.txt`

### Gatting Branching Trees — Key Pattern
Heat meter (0-100): builds via shots, decays idle. Fortify = stationary stacks. Firing_buffer
= shots vs idle turns. 21 new abilities; the_last_man = ONCE per run. Full detail: `summaries/`.
entity.naked (bool); Effects: first_blood, reaped, staggered, suppressed, pinned, branded, last_man.

### Batch 3+4 Unique Items
- Full Batch 3 patterns: `summaries/unique-items-batch3-summary.txt`
- Full Batch 4 patterns: [unique-items-batch4.md](unique-items-batch4.md) + `summaries/unique-items-batch4-summary.txt`
- Batch 4 adds: permanent_crit_bonus (PlayerStats), 0xE00F/0xE010 tile assignments,
  take-damage-to-charge, kill-or-self-damage, run-wide accumulating weapon stat,
  stationary stance, per-debuff dodge scaling, cash-threshold conditional bonus.

### Hat Slot
equip_slot="hat", char='^'. Existing hat IDs: wave_cap, backwards_cap, crown, tinfoil_hat,
  triple_foil_hat, foil_lined_durag, hard_hat, shower_cap, fitted_cap, durag, knit_beanie, bike_helmet

### grants_ability Slot Support (inventory_mgr.py, as of 2026-03-28)
- SUPPORTED (single): weapon, sidearm, feet — grant/revoke on equip/unequip
- SUPPORTED (list): neck — grants_abilities list, all granted/revoked on equip/unequip
- NOT SUPPORTED: hat, ring — must add grants_ability/grants_abilities processing to equip blocks
  to use ability-granting items in those slots. Mirror neck slot logic.

### Cursed-to-Blessed Pattern
Two unlock triggers: curse_unlock_steps (steps walked) OR curse_unlock_kills (kills).
New engine bool per item: curse_broken_{item_id}. New PlayerStats fields: hp_cap_ratio,
regen_per_turn, hp_drain_per_turn, speed_bonus, vulnerability_multiplier, xp_blocked, etc.
Blessed payoff rule: each item must have at least one unique effect not found elsewhere.
See [cursed-blessed-items.md](cursed-blessed-items.md) for full field list and patterns.
