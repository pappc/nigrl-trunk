---
name: Spell Compendium Index
description: Quick-reference index for all spell compendiums (45 + 35 + 34 + 32 + 26 = 172 total ability designs)
type: project
---

Full document: `nigrl-ideas/spell_compendium.txt`
Written: 2026-03-15. Does NOT duplicate any existing ABILITY_REGISTRY entries.

## Existing Registry (30 entries as of writing)
warp, dimension_door, chain_lightning, ray_of_frost, firebolt, arcane_missile,
breath_fire, zap, corn_dog, lesser_cloudkill, pry, throw_bottle, bash,
black_eye_slap, gouge, pickpocket, force_push, fry_shot, place_fire, dash,
ignite_spell, quick_eat, double_tap, spray, burst, spray_and_pray,
slow_metabolism, pandemic, radiation_nova

## Sections and Ability IDs

### A — Drinking Magic (Drinking / Alcoholism trees)
A-01 liquid_courage     — Drinking L4. Melee boost + defense, blocks retreat.
A-02 hair_of_the_dog    — Alcoholism L4. Burn drink buffs for burst heal.
A-03 spiked_punch       — Drinking L5 or item. Debuff that doubles ignite dmg.
A-04 corkscrew          — Drinking L6. Bouncing bottle LINE attack.
A-05 blackout           — Alcoholism L5. ONCE 15-turn death immunity + vision loss.
A-06 last_call          — Alcoholism L5 alt / item. ONCE heal + mass stagger.

### B — Eating Magic (Munching / Deep-Frying trees)
B-01 gas_attack         — Munching L4. Radius-2 AOE, scales with food buffs active.
B-02 deep_fried_fireball — Deep-Frying L4. 3x3 AOE + fire hazard placement.
B-03 iron_gut           — Munching L5. CON DR + tox-to-heal conversion.
B-04 corn_dog_judgment  — Deep-Frying L5. LINE throw, drops corn dog as loot.
B-05 calorie_surge      — Munching L6. Speed+dmg spike, CON crash on expire.
B-06 enzyme_bomb        — Deep-Frying L6. AOE debuff, splash, floor-long def reduction.

### C — Smoking Magic (Smoking / Rolling / Pyromania trees)
C-01 phat_cloud_active  — Smoking L3 activated variant. Confusion zone, 4 turns.
C-02 contact_high       — Smoking L5 activated variant. Spread strain effect, inverted.
C-03 smoke_screen       — Rolling L4. ADJ_TILE LOS blocker, resets enemy chase.
C-04 spiritual_transcendence — Smoking L8 / rare item. ONCE 20-turn phasing.
C-05 dutch_courage_cloud — Rolling L5. Retaliate damage to all visible on taking hits.
C-06 slow_burn          — Smoking L6. INF cooldown DoT, ramps up, resets on reapply.
C-07 roach_resurrection — Rolling L6. Re-trigger last strain effect at saved roll value.

### D — Blackkk Magic tree
D-01 mind_bullets       — BM L3. Split psychic/physical dmg + diagonal block debuff.
D-02 curse_of_bad_luck  — BM L4. 30% miss + loot bonus on kill.
D-03 spirit_steal       — BM L5. Drain half target's stat bonuses for 10 turns.
D-04 voodoo_doll        — BM L6 / item. Damage-sharing tether.
D-05 forgotten_name     — BM L7. Mass AI state reset (all chasers → idle, 5-turn lock).
D-06 death_mark         — BM L8. Marks enemy; bonus dmg to marked, AOE on death.
D-07 psychic_scream     — BM L9. Fear healthy enemies, damage+confuse wounded ones.

### E — Combat / Physical trees (Stabbing, Beating, Smacking, Jaywalking, Stealing, Negromancy)
E-01 switchblade_twirl  — Stabbing L4. ADJACENT_ALL spin hit + bleed synergy.
E-02 cheap_shot         — Stealing L3. No damage, stun + free attack.
E-03 chain_snatch       — Stealing L4. Disarm enemy + cash reward.
E-04 ground_pound       — Beating L4. Prone CC (no move or attack for 3 turns).
E-05 ankle_breaker      — Jaywalking L4. Cripple (half speed + step damage) + free step.
E-06 blitz              — Jaywalking L5. 4-tile charge, damage on enemy in path.
E-07 exhume             — Negromancy L2. Summon last-dead as explosive shambling.
E-08 reap               — Negromancy L3 (cross-ref to memory — see soul shard notes).

### F — Zone 2 / Meth Lab exclusives
F-01 hazmat_protocol    — Chemical Warfare L1. Instant tox reduction + 8-turn shield.
F-02 meltdown           — Nuclear Research L4. Convert ALL rad to whole-floor damage.
F-03 chemical_cocktail  — Chemical Warfare L3. 40 bypass-tox + random secondary effect.
F-04 purity_shield      — Purity L2. 12-turn tox/mutation immunity, 30-tox backlash.
F-05 static_discharge   — Meth-Head L6. AOE lightning while Wire active, consumes 5t Wire.

### G — Utility / Environmental / Cross-tree
G-01 dumpster_dive      — Abandoning L4 / environmental. Loot or Filthy debuff.
G-02 jury_rig           — Dismantling L4. Destroy 2 items to craft improvised weapon.
G-03 call_out           — Swagger passive / item. Pull all enemies + defense bonus.
G-04 dead_sprint        — Jaywalking L3 or L7. Auto or manual escape boost when outnumbered.
G-05 barter             — Stealing L5. Cash-for-peace vs. faction/named/generic enemies.
G-06 improvised_explosive — Deep-Frying L7 / Dismantling L5. TOTAL charges, fire spread.
G-07 clock_out          — Jaywalking L8. Skip 3 turns; stun enemies, gain free action after.
G-08 noise_complaint    — Item / Stealing L6. Stun chasers, reset alerters, flee idlers.
G-09 money_shot         — Stealing L7. $50 cost, 50 unavoidable dmg, room-wide idle.
G-10 last_man_standing  — CON 14 passive / item. ONCE cheat death + knockback + Battered.

### H — Experimental / High-Concept
H-01 recursive_blunt    — Rolling L9. Double-roll strain, take better result.
H-02 identity_theft     — Stealing L9. ONCE copy enemy ability kit for 20 turns.
H-03 market_crash       — Abandoning L5. Sacrifice all cash for permanent crit + free items.
H-04 chain_reaction     — Chemical Warfare L7. Volatile trigger, chain explosions.

## New Effects Needed (effects.py)
liquid_courage, decon_shell, iron_gut_effect, calorie_surge, dutch_courage,
slow_burn, phat_cloud_zone, phased, cursed, psychic_daze, death_mark_effect,
prone, crippled, nausea, voodoo_tether, volatile, battered, blinded_enemy

## New Lifecycle Hooks Needed (beyond existing)
  modify_tox_gain(entity, engine, amount, source) -> int  [already noted in memory]
  on_enemy_killed_by_player(entity, engine, killed_entity) -> None
  modify_player_cash_gain(entity, engine, amount) -> int
  on_player_takes_damage(entity, engine, attacker, damage) -> None

## Implementation Tiers (from compendium)
Tier 1 (low complexity, fills gaps): A-01, A-02, B-01, C-01, C-03, D-01, E-01, E-02
Tier 2 (moderate): A-04, B-02, C-06, D-02, D-05, E-03, E-05, G-01, G-03, G-09
Tier 3 (complex, high value): A-05, B-03, C-04, D-04, D-07, F-02, G-10, H-04
Tier 4 (high-concept, later): C-02, H-02, H-01, H-03

---

## SUPPLEMENT I — Classic D&D & Roguelike Spells
Full document: `nigrl-ideas/spell_compendium_classics.txt`
Written: 2026-03-15. 43 entries across 8 sub-categories.
None duplicate the registry OR Sections A-H.

### I-A — Movement & Escape
I-A-01 dip_out             — BM L2 / Burner Phone. Short-range blink (Chebyshev 4). Distinct from warp.
I-A-02 smoke_and_mirrors   — BM L6 / Stealing L7. Force-teleport enemy to random floor tile.
I-A-03 bounce              — Bus Pass / Abandoning L8. Teleport to current floor's entrance stairs.
I-A-04 ghost_walk          — Smoking L7. TOL-scaled wall-walking; expire-in-wall = damage.

### I-B — Battlefield Control
I-B-01 throw_the_nets      — Beating L5 / item. AOE radius-2 Web; cut free on melee hit.
I-B-02 wake_up_call        — BM L4 / Beating L3. All-adjacent Thunderwave with knockback.
I-B-03 lights_out          — Stealing L5. Radius-4 Darkness; enemy sight_radius → 1, player immune.
I-B-04 speed_bump          — Deep-Frying L3. Grease zone; 50% move cost + 25% slip per turn.
I-B-05 hold_it             — BM L3 / Taser item. Paralyze single (BKS/4 turns); breaks on first hit.
I-B-06 shut_up             — Stealing L4. Silence zone; blocks alarm_chaser / female_alarm alerts.

### I-C — Direct Damage
I-C-01 pop_pop_pop         — BM L1. 3 bolts × ceil(BKS/4), fully ignores defense. Magic Missile.
I-C-02 what_you_said       — BM L5. BKS+STS/2 psychic + FLEE + free opportunity attack.
I-C-03 toll_the_block      — Negromancy L4. Wound-scaling: BKS/3 → BKS → BKS×1.5 (bypasses def).
I-C-04 in_your_walls       — Negromancy L3. ADJACENT BKS+CON no-def + gain 1 soul shard on hit.
I-C-05 structural_damage   — BM L6 / Beating L6. AOE stun + remote smash all crates in radius.
I-C-06 spirit_shot         — Negromancy L5. 8-turn persistent summon; fires BKS/2 auto each turn-end.

### I-D — Summoning & Allies
I-D-01 call_the_squad      — Stealing L8 / Swagger 14+. ADJ_TILE ally spawn; SWG tier (Homie/Day-One/Soldier).
I-D-02 turn                — Negromancy L4 / BM L3. Turn all visible enemies; tier by base_hp.

### I-E — Detection & Knowledge
I-E-01 street_sense        — STS 12+ passive / Police Scanner. 3-turn full-floor enemy radar.
I-E-02 know_the_building   — BKS 10+ / Blueprints item. Instant floor map reveal (terrain only).
I-E-03 what_is_it          — BKS L4 / Loupe item. Forward-looking Identify slot; reveals floor items now.

### I-F — Buffs & Self-Enhancement
I-F-01 running_late        — Jaywalking L6. Haste: +50 speed + free auto-attack + 15% dodge; Hastedrop on expire.
I-F-02 dont_see_me         — BM L5 / Rolling L7. Blur: +30% dodge for 10 turns. Clean add/remove.
I-F-03 hustle_shield       — BM L2. +5 armor +2 defense for BKS/3+3 turns, 15t CD. Mage Armor.
I-F-04 second_wind         — CON 10 passive / Adrenaline Shot. Passive 1 HP/turn regen (CON tree).
I-F-05 the_look            — Swagger 16+ / Sunglasses item. Sanctuary: non-hostile enemies skip attacks; ends if player attacks.

### I-G — Debuffs & Monster Control
I-G-01 put_em_to_sleep     — BM L1. Sleep: HP-gated (≤15 sure, 16-30 BKS%, >30 immune). Crit on sleeping.
I-G-02 sit_down            — Swagger 14+ / Stealing L6. Command submenu: STOP/RUN/DROP/COME. DROP = early loot.
I-G-03 get_confused        — BM L2 / Experimental Strain. AOE delivery of existing confuse effect.
I-G-04 hit_list            — Stealing L3 / Negromancy L2. Hex/Mark: +STS/3 dmg, heal on kill, auto-transfers.
I-G-05 get_slow            — BM L4. AOE delivery of existing slow effect + 30% attack failure added.
I-G-06 dance_fool          — BM L7. Otto's Dance: random movement + cannot attack, 5 turns + stun after.

### I-H — Terrain & Environmental Manipulation
I-H-01 dig                 — Dismantling L3 / Power Drill. 10-tile LINE tunnels through walls permanently.
I-H-02 bear_trap           — Stealing L4 / Bear Trap Kit. ADJ_TILE hidden trap; STS dmg + stun on trigger.
I-H-03 leave_a_mark        — BM L4. Glyph of Warding: 2-tile AOE BKS dmg + stun on trigger. 2-rune cap.
I-H-04 earthquake          — BM L8 / Beating L8. ONCE; floor-wide dmg + stun + 20% tiles cracked 5t.
I-H-05 make_it_rain        — BM L7. Sleet Storm: radius-4 zone; extinguish fire, halve enemy sight, WetEffect.

### I-Z — Standalone Classics (too iconic to categorize)
I-Z-01 polymorph           — BM L9 / Weird Mushroom. Enemy → random weaker type. Self version: random stat shuffle.
I-Z-02 invisibility        — BM L5 / Stealing L6 / item. STS+5 turns; enemies lose chase, first attack crits, any action breaks.
I-Z-03 levitate            — BM L6 / Rolling L8. TOL/3+5 turns; immune to fire/slick/tox floor tiles.
I-Z-04 mirror_image        — BM L4 / Rolling L6. 3 decoy entities (1 HP); 50% redirect incoming attacks.
I-Z-05 banishment          — BM L8. Remove enemy for 15t (8t if base_hp>30, returns healed 50%).

### New Effects Needed (Supplement I additions)
netted, paralyzed, intangible, hustle_shield_effect, running_late_effect, hastedrop,
dont_see_me_effect, slicked_tile, silence_zone, sleep, the_look_effect, dance_fool_effect,
decoy_entity (entity not effect), levitate_effect, cracked_tile_state, invisible

### New Engine State Needed (Supplement I)
engine.spirit_shot_turns: int  — spirit shot auto-attacks per turn
engine.hit_list_target: Entity — hex/mark target; auto-transfers on kill
engine.banished_entities: list[(Entity, int)]  — return-turn pairs
engine.player_levitating: bool  — immunity to floor effects
engine.player_intangible: bool  — wall-walk state

### New AI Modes Needed (Supplement I)
ally_meander  — like meander but targets enemies (for Call the Squad)

### Cross-references within Supplement I
dip_out vs warp: short range vs full floor
wake_up_call vs force_push: all-adjacent vs single target
lights_out vs forgotten_name: sight block vs AI state wipe
throw_the_nets vs ankle_breaker: AOE vs single target slow
pop_pop_pop vs arcane_missile: no-defense vs ?
get_confused/get_slow vs compendium C-06/D-07: ability delivers existing effect
hit_list vs death_mark: rotation buff vs setup burst
put_em_to_sleep vs stun: HP-gated vs flat
invisibility vs ghost_walk: AI-blind vs wall-walk
mirror_image vs dont_see_me: ablative decoys vs dodge %
banishment vs smoke_and_mirrors: temporary removal vs repositioning
turn vs psychic_scream: HP-tier flee vs HP-ratio flee/damage

---

## SUPPLEMENT II — Weird, Busted & Dangerous Abilities
Full document: `nigrl-ideas/spell_compendium_weird.txt`
Written: 2026-03-15. 34 entries across 12 sections (W-A through W-L).
Theme: system weaponization, inverse scaling, run-modifying mechanics, risky power.

### W-A — Turn Order & Energy Manipulation
W-A-01 stop_time       — BM L5. ONCE; 3+BKS//3 turns where enemies don't accumulate energy.
W-A-02 gear_grind      — Meth-Head L3. INF CD25; +80 energy/tick for CON-scaled turns; crash on expire.
W-A-03 borrow_time     — Negromancy L4. SINGLE_LOS CD12; steal enemy's energy (reset to 0), grant player +THRESHOLD.

### W-B — Mutation & Radiation Weaponization
W-B-01 just_a_bit_more — Nuclear Research L3. TOTAL 3; self-apply +75 rad + immediate mutation roll.
W-B-02 mutation_grenade — Nuclear Research L5. TOTAL 2; AOE 2; enemies+player get rad, monster mutation chance.
W-B-03 irradiate_self  — Mutation L4. INF CD20; +50 rad self; 10t buff: +4 power, +10% dodge, +rad on melee hits.

### W-C — Toxicity Weaponization
W-C-01 purge           — Chemical Warfare L3. SELF immediate; tox//5 damage to adjacent, player tox→0.
W-C-02 septic_aura     — Chemical Warfare L5. /FL 1; aura deals 5/turn to Chebyshev(2) enemies; +5 tox/turn self.
W-C-03 venom_exchange  — Chemical Warfare L4. INF CD15; STS. Swap player/enemy tox, or transfer 50%.

### W-D — Food Buff Weaponization
W-D-01 force_feed      — Munching L4. ADJACENT CD8; STR. Consume food, invert effects on adjacent enemy.
W-D-02 sympathy_eat    — Munching L5. /FL 2; CON. Lifesteal on melee hits (dmg//4 heal) for CON+4 turns.
W-D-03 bottomless_pit  — Munching L3. ONCE; 5t: eat time=1, all food effects doubled, eating = free action.

### W-E — Inverse HP Scaling
W-E-01 from_the_grave  — Negromancy L2. Passive; +2/+5/+10 damage and crit at 75/50/25% HP thresholds.
W-E-02 debt_collection — BM L3. INF CD6; spend 10 HP; dmg = 15 + (max_hp - hp) * 0.4 * BKS mult.
W-E-03 desperation_strike — Beating L4. FLOOR_ONLY 1; STR*4 + HP_missing, always crit, no defense; 3t lockout.

### W-F — AI State Manipulation
W-F-01 spook           — BM L1. INF CD10; SINGLE_LOS; set FLEEING state for SWG//3+3 turns.
W-F-02 make_friends    — Stealing L4. /FL 1; SWG. Charm: WANDERING lock; SWG 12 = attacks other enemies.
W-F-03 snitch          — Jaywalking L4. TOTAL 3; all dormant enemies → CHASING simultaneously.

### W-G — Permanent Run Modification
W-G-01 burn_the_map    — Pyromania L4. ONCE; ignite ALL monsters on floor, destroy ALL items; self-ignite 1 stack.
W-G-02 sign_the_lease  — Rolling L5. ONCE; consume joint; +3 power weapon, 15% 5HP regen proc; CAN NEVER UNEQUIP.
W-G-03 take_the_deal   — BM L4. TOTAL 6 (once/stat); sacrifice stat permanently (-3 base) for +2 power + 50 SP.

### W-H — Physics / Space Abuse
W-H-01 fold            — BM L3. /FL 2; SINGLE_LOS 12; teleport adjacent to target; 2t movement lockout (BKS scales off).
W-H-02 pocket_dimension — Dismantling L4. TOTAL 5; phase item out for 3 floors, auto-return.

### W-I — Status Effect Recycling
W-I-01 spite           — Smacking L3. Passive; +3 damage per unique debuff on player (+4 at TOL 10).
W-I-02 transmute_pain  — Smacking L5. INF CD15; AOE radius 2; 8 dmg per debuff to all nearby; clears all debuffs.
W-I-03 hangover_fuel   — Alcoholism L4. Passive; +10 energy/tick + 1 power per Hangover stack (+15/+2 at TOL 10).

### W-J — Gun System Abuse
W-J-01 dry_fire        — Gatting L4. Passive; when ammo=0, attack button = melee with gun (STR*2 + gun_avg//2).
W-J-02 full_auto_prayer — Drive-By L4. FLOOR_ONLY 1; dump entire mag at primary target; jammed 5t after.
W-J-03 ricochet_shot   — Sniping L4. INF CD8; ADJ_TILE wall; 90-degree bounce shot hits first enemy in path.

### W-K — Strain System Integration
W-K-01 share_the_wealth — Smoking L4. SINGLE_LOS 3 CD5; transfer active strain effect from player to enemy (inverted).
W-K-02 joint_rolling_factory — Rolling L4. /FL 1; combine 2 joints → 1 mixed joint with both strain effects.

### W-L — Busted Capstones
W-L-01 last_hit        — Stabbing L5. /FL 3; SINGLE_LOS; instant kill if enemy <= 20% HP; charge consumed even if fail.
W-L-02 bless_this_mess — BM L5. ONCE; AOE radius 4; 8 outcomes d8 per enemy; player has 30% chance to also get one.
W-L-03 skin_shed       — Negromancy L5. ONCE passive auto-trigger on death; 10% HP respawn, transfer all effects.
W-L-04 debt_spiral     — Negromancy L4. Passive; +1 dmg per kill (max 30); pays count*3 HP on each descent.
W-L-05 unfinished_business — Smacking L4. ONCE passive; survive to 1 HP for STR//3+3 turns; guaranteed death on expire.

### New Effects Needed (Supplement II)
GearGrindEffect, CrashEffect, SpookedEffect, CharmedEffect, SepticAuraEffect,
RadSurgeEffect, BottomlessPitEffect, SympathyEatEffect, UnfinishedBusinessEffect,
FoldDisorientEffect

### New Engine Flags Needed (Supplement II)
_time_stopped, _time_stop_turns_remaining, _gear_grind_active, _bottomless_pit_active,
_skin_shed_available, _unfinished_business, _from_the_grave_active, _spite_active,
_hangover_fuel_active, _lease_weapon_id, _debt_spiral_count, _pocket_dimension (list)

### Design Patterns Established by Supplement II
- "ONCE" charge type = signature run moment (Stop Time, Bless This Mess, Burn the Map)
- FLOOR_ONLY charges = tactical commitment that resets on descent (not on death)
- Passive abilities granted by perks: use engine flag (engine._xxx_active = True) to gate
- Death-override hook pattern: check flag before entity_died, set HP to 1, set flag to False
- AI state manipulation: write monster.ai_state directly + apply effect to re-assert each turn
- Inverse scaling: compute bonus from (max_hp - hp) or debuff count at action-resolve time
- Debt mechanics: track count in engine field, bill on floor transition (not on use)

---

## VOLUME II — New Elemental, Water School, and Multi-Element Combos
Full document: `nigrl-ideas/elemental-ability-compendium-v2.txt`
Written: 2026-03-26. 32 new castable ability IDs + 5 passive terrain interaction rules.
PRIMARY: builds the Water/Wet school from scratch (8 spells).
Also: fire/ice/lightning second-wave abilities, multi-element combo spells, weird entries.

### W-W — Water / Wet School (8 spells, entirely new school)
W-W-01 hydrant_burst    — INF CD5; SINGLE_LOS; 3+BKS/4 dmg; applies Wet (6t). Wet primer.
W-W-02 splash_zone      — /FL 4; ADJ_TILE; wet_puddle terrain (8t). Conducts lightning to all puddle entities.
W-W-03 muck_flood       — /FL 2; LINE 8 pierce; Wet (5t) all hit; creates mud_tile terrain. Absorbs puddles for range bonus.
W-W-04 waterlogged_spell — /FL 3; SINGLE_LOS; Wet (8t) + WaterloggedEffect (-30 spd, -1 def). Doubles on pre-Wet targets.
W-W-05 pressure_washer  — /FL 2; CONE 5; STR+BKS; Wet (4t) + pushback. STRIPS all ignite/fire from cone. Converts fire tiles to puddles.
W-W-06 flash_flood      — ONCE; SELF room-wide; Wet (10t) all visible; room becomes puddles; strips all fire terrain, thaws frozen.
W-W-07 rinse_cycle      — /FL 3; SELF; strip ALL elemental debuffs; brief self-Wet (4t); CON-scaled HoT.
W-W-08 tidal_slap       — INF CD4; SINGLE_LOS; 5+BKS/4+STR/4; Wet (5t); 1-tile pushback. 2-tile + earthbound on mud targets.

### V-F2 — Fire Second Wave (5 spells)
slow_cook   — INF CD3; SINGLE_LOS; TOL; 1 ignite stack, 10t timer. Maintenance tool. Refreshes (no new stacks) on 3+ stacks.
fire_wall   — /FL 2; ADJ_TILE; places 3 fire hazard entities in perpendicular line. Corridor blocker.
ember_burst — INF CD10; SINGLE_LOS; BKS+TOL; detonates ALL ignite stacks (3+BKS/6+TOL/6 per stack). Applies Scorch (can't re-ignite 8t).
magma_fist  — INF CD3; ADJACENT; STR+TOL; 4+STR/3+TOL/4; applies ignite (2 stacks). Shatters frozen targets. +50% vs earthbound.
smoke_signal — /FL 3; LINE 12; STS+BKS; 2+BKS/4+STS/4; 1 ignite stack. fire_marked 2-shot mechanic: second cast = double dmg + 3 stacks.

### V-I2 — Ice Second Wave (4 spells)
black_ice    — /FL 3; ADJ_TILE; STS; invisible trap tile (15t). Trigger: 2+STS/4 cold, chill 2, 50% stun 1t. Freezes adjacent puddles.
cold_snap    — /FL 2; SELF room-wide; BKS; chill 1 to all visible. Wet entities → chill 2 + Wet stripped. Converts puddles to ice_terrain.
polar_vortex — /FL 1; AOE_CIRCLE r3; BKS; 6+BKS/4 cold; chill 3 (8t) all. Pre-2+ chill → frozen 4t. Creates ice_terrain in radius.
ice_clone    — /FL 2; ADJ_TILE; BKS; places ice_clone entity (1 HP, decoy). Shatter on death: chill 2 adj. Fire death = steam burst.

### V-L2 — Lightning Second Wave (4 spells)
static_field   — /FL 3; ADJ_TILE; BKS; static_field terrain (10t). Trigger: 1+BKS/4 lightning + shocked 1. Amplified on puddle. Chain between adjacent fields.
conductor      — INF CD6; SINGLE_LOS; BKS; conductor_mark (8t). Inward arc: 3 dmg when OTHER entities take lightning. Outward arc: Chebyshev 2 when directly hit.
discharge_aura — /FL 2; SELF; TOL+BKS; buff 10t. Melee hits arc shocked (1) to adj. Wet player → expand to Chebyshev 2, double discharge.
electric_slide — /FL 3; SELF movement; STS+BKS; 2-tile electrified dash. Shocked sweep to entities passed. Post-slide melee bonus.

### V-C — Multi-Element Combos (6 spells)
steam_cannon     — /FL 3; LINE 6; BKS+STR; [FIRE+WATER] Consumes adjacent puddle; 8+scaling dmg; earthbound+scorch. Double if target Wet.
thunderstorm     — /FL 1; AOE_CIRCLE r4; BKS; [LIGHTNING+WATER] Requires 2+ Wet or puddles; Wet+shocked 2 all. Pre-Wet targets = double + 4 stacks.
permadeath_frost — ONCE; SINGLE_LOS; BKS; [ICE+SHADOW] Requires target has chill + shadowed. DarkFrozenEffect: freeze + +50% dmg taken, fire-proof.
mudslide         — /FL 2; LINE 6 pierce; STR+BKS; [EARTH+WATER] Requires adjacent water. Earthbound (5t) all. Creates mud terrain. Prone on pre-earthbound.
frozen_lightning — /FL 1; SINGLE_LOS; BKS; [ICE+LIGHTNING] chill 3 + shocked 3 simultaneously. Shatter frozen for triple. Paralysis if 3+ prior shocked.
acid_rain        — /FL 2; AOE_CIRCLE r3 DELAYED; BKS; [WATER+POISON] Wet+poisoned all; pre-Wet = double. Creates acid_puddle terrain.

### V-W Weird Entries (5 spells)
cold_hard_cash — INF CD6; SINGLE_LOS; STS+TOL; costs 10 cash; chill 2. More cash = more stacks/earthbound.
live_wire      — /FL 2; SELF; TOL+CON; hybrid buff/debuff. Melee arcs shocked. +2 water dmg taken. Meth-Head Wire combo.
fossilize      — ONCE; SINGLE_LOS; CON+BKS; [EARTH extreme] Requires earthbound + (ignite 3+ OR poisoned). FossilizedEffect: immobile -4 def, shatter hits, fire cracks.
electric_slide — (already listed in V-L2 section above)
undertow       — /FL 1; SELF room; STR+BKS; [WATER] Requires 3+ puddles. 5-turn current: pulls puddle-entities toward player 1 tile/turn. Free melee on arrival.

### New Effects (Volume II)
WetEffect, WaterloggedEffect, ScorchEffect, DarkFrozenEffect, FossilizedEffect,
LiveWireEffect, ElectricSlideEffect, DischargeAuraEffect, ConductorMarkEffect,
FireMarkedEffect (player-side 1t flag)

### New Engine Terrain State (Volume II)
wet_puddles, mud_tiles, ice_terrain, black_ice_tiles, static_fields, acid_puddles,
charged_puddles, static_field_links, pending_acid_rain
+ engine flags: _water_current_active, _water_current_turns, _fire_marked,
  _discharge_aura, _live_wire_grounds_crash

### New Entity Fields (Volume II)
entity.wet: bool (formalized), entity.scorched: bool, entity_type="ice_clone"

### Key Design Patterns (Volume II)
- Water school = enabler school: no standalone power; all payoffs in what it enables for fire/ice/lightning
- Terrain system: multiple terrain types (wet_puddle, mud, ice, static_field, acid_puddle, black_ice)
  interact passively — fire eats water, ice freezes puddles, static amplifies on puddles
- Terrain resource consumption: Steam Cannon spends wet_puddle tiles, Undertow requires puddle count
- DarkFrozenEffect: combines freeze + 50% damage amplifier + fire-immune — unlike normal FrozenEffect
- Scorch debuff: post-Ember Burst state prevents re-ignition for 8t, forces fire build to rotate
- fire_marked two-shot rhythm: Smoke Signal's setup → confirm loop
- Combo REQUIRE conditions: some spells explicitly fail (or fire weakly) without pre-conditions
  (Steam Cannon, Thunderstorm, Fossilize, Undertow) — reward setup, punish blind use

---

## VOLUME III PART 1 — Elementalist Spells / Earth Expansion / Wind Expansion
Full document: `nigrl-ideas/elemental-ability-compendium-v3-part1.txt`
Written: 2026-03-26. 33 new abilities across 3 categories.

### CATEGORY 1 — Elementalist Spells (17 entries)
Three new PASSIVE ENGINE SYSTEMS (no ability slot):
  Elemental Convergence  — passive: 2+ debuffs on same target → burst 8+BKS/3+2/element
  Elemental Overload     — passive: alternate element → +BKS/4 flat damage bonus
  Primal Attunement      — passive: scales with # elemental trees (tiers 1-3)
  Focused Element        — passive: COUNTER to Overload; 3 same-element streak → +2 flat

Herald system (3 entries, mutual exclusive, /FL 1 each):
  Herald of Fire   — melee reflect ignite + fire radiate on cast
  Herald of Ice    — melee reflect chill + freeze pulse on nearby freeze
  Herald of Lightning — melee reflect shocked + crit chain arc

Active abilities (10 entries):
  convergence_strike — SINGLE_LOS INF CD8; +3/debuff on target; shuffles debuffs
  attunement_shift   — SELF free; cycles element attunement; +3 to next matching spell
  elemental_surge    — SELF /FL 2; 5t window; +2 speed/element cast; discharge on expire
  wild_element       — SINGLE_LOS INF CD6; random debuff from available elements
  schematic          — SINGLE_LOS TOTAL 3; 4+ elements → detonation 12+BKS/3
  elemental_echo     — SELF TOTAL 4; 3t echo window; 50% dmg echo to random target
  elemental_communion — SELF ONCE; expunge all buffs → mass multi-element blast
  elemental_weaving  — SELF /FL 2; 4t; previous spell re-casts at 60% dmg
  elemental_chain    — SINGLE_LOS TOTAL 5; requires 3+ elements received by target
  storm_caller       — SELF ONCE; all-6-element mass blast; 20t burnout after

### CATEGORY 2 — Earth/Stone Expansion (9 entries)
pothole           — ADJ_TILE /FL 3; creates enemy-blocking terrain, trip on placement
rubble_shield     — SELF INF CD8; absorbs 3 physical hits, reflects, detonates
stone_wall        — ADJ_TILE /FL 2; 3-tile destructible wall (15 HP); blocks sight
quicksand         — ADJ_TILE /FL 2; hidden trap; earthbound refresh while on tile
tremor            — SELF INF CD12; r4 AoE; 50% stun; double vs earthbound
petrify           — SINGLE_LOS /FL 1; HP-gated; not fire-removable; stone_explosion on death
tectonic_surge    — ADJ_TILE /FL 1; detonates own stone_wall or pothole terrain
granite_fist      — SELF INF CD5; buff next melee: +dmg+earthbound; crushing vs earthbound
pillar_of_stone   — SELF ONCE; 10t immobile, stone aura, cracked terrain, Collapse on expire

### CATEGORY 3 — Wind/Air Expansion (7 entries)
step_dodge        — SELF /FL 4; 3t window; dodge chance+blink+windswept on attacker
crosswind         — LINE /FL 3; sustained wind barrier; deflects projectiles; fans flames
updraft           — SELF /FL 2; blink to visible tile; windswept pulse; fans fire on origin
dust_devil        — ADJ_TILE /FL 2; autonomous entity 6t; absorbs fire→fire_devil; arcs on static
slip_stream       — passive; 3-move sprint → +20 energy/tick +10% dodge for 2t
scattering_wind   — SELF /FL 1; r6 push all enemies 3 tiles; disoriented on full push
cyclone_step      — ADJACENT /FL 3; dash-strike; hits all adj to start+end tile; free during hurricane

### New Engine Flags (Part 1)
_convergence_available, _last_element_cast, _attunement_level, _attunement,
_available_attunements, _surge_active/_turns/_elements_hit/_stacks,
_weaving_active/_turns/_last_ability/_last_target,
_focused_element_streak/_tag/_active, _elemental_echo_active/_turns,
_pillar_active/_turns, _granite_fist_ready, _slipstream_tiles,
_active_herald: str | None, crosswind_lines list, dust_devils list

### New Terrain Types (Part 1 — beyond Vol II terrain)
engine.stone_walls: dict[(x,y) → hp], engine.potholes: set[(x,y)],
engine.quicksand_tiles: set[(x,y)], engine.cracked_tiles: set[(x,y)]

### New Entity Fields (Part 1)
entity.elements_received: set[str]  — debuff history for Elemental Chain / Schematic
entity_type="dust_devil"            — autonomous wander_random AI entity

---

## VOLUME III PART 2 — Shadow School Expansion, Multi-Element Combos, Terrain Fields
Full document: `nigrl-ideas/elemental-ability-compendium-v3-part2.txt`
Written: 2026-03-26. 26 new ability IDs across 3 categories.

### Shadow School Expansion (8 new abilities — builds on Supplement III seeds)
INTRODUCES: engine._shadow_dark (0-10 darkness meter). Decays 1/turn; fire tiles
  each decay +1/turn. Enemy sight_radius reduced -1 per 2 darkness levels.

kill_the_lights  — SELF INF CD6; +3 dark, mass shadowed all FOV enemies, dims fire 4t
shadow_step      — SINGLE_LOS INF CD8; requires darkness 2+ OR target shadowed;
                   blink to adj target, damage + shadow_marked (3t). Silent at dark 5+
eclipse          — SELF /FL 2; +5 dark, mass blinded (5t) all room enemies.
                   At dark 4+: extends to 8t, enemies deal -4 dmg while blinded
dark_mirror      — SINGLE_LOS INF CD7; curse: each damage instance reflects BKS/4+STS/4
                   bypass shadow dmg back to target (cap 8/trigger, 5 turns)
night_terror     — SINGLE_LOS INF CD10; HP-gated stochastic fear; +2 dark per panic trigger.
                   At dark 6+: spreads to all FOV enemies
penumbra         — SELF /FL 3; +15% dodge, +1 dark/turn while active (4t).
                   Free action on expire if dark >= 3
void_strike      — ADJACENT INF CD5; 6+STS/3+BKS/4 bypass-50%, void_torn (3t: -2 def all,
                   -all def for shadow). No CD at dark 5+. Triple + free kill_the_lights
                   if target has shadow_marked + shadowed simultaneously
shadow_harvest   — SELF ONCE; spend ALL darkness: D*3 bypass-50% AOE + D*5 bypass-all
                   to shadow-afflicted targets + D*2 heal. Permanent: shadow effects +2t.
                   Fire tiles in room reduce effective D (fire fights your harvest)

### Multi-Element Combos (11 new abilities)
dark_fire       — /FL 3 SINGLE_LOS; [SHADOW+FIRE] converts ignite→dark_flames (wet-immune).
                  At dark 5+: dark_flames bypass all def
magma_trap      — /FL 3 ADJ_TILE; [FIRE+EARTH] magma_tile terrain (10t): earthbound+ignite on entry.
                  Mud in tile → radius-1 lava pool
static_storm    — /FL 1 AOE r3; [LIGHTNING+WIND] requires shocked/windswept in radius.
                  shocked(3)+windswept(3)+push. Pre-shocked: +2 stacks, 2-tile push.
                  Earthbound → stripped + 6 bonus dmg
cinders_and_ash — INF CD9 SINGLE_LOS; [FIRE+SHADOW] requires target <50% HP.
                  Ignite → detonation auto-convert. Cinders DoT reduces healing 25%
frostburn       — /FL 2 SINGLE_LOS; [FIRE+ICE paradox] bypasses both resists.
                  ignite+chill simultaneously → FROSTBURST (3x dmg, stun 2t).
                  Frozen target → thaw + ignite 3
swamp_gas       — /FL 3 ADJ_TILE; [EARTH+POISON] radius-1 poison cloud 6t. Fire = explosion
                  (8 fire dmg, stun 1t, cloud removed). Pre-poisoned = double stacks
chain_of_ice    — /FL 2 SINGLE_LOS; [ICE+LIGHTNING] requires chill 2+ on primary.
                  Arc chains to all shocked enemies in sight (chill 2 each, freeze if 3+)
dust_devil      — INF CD6 LINE; [EARTH+WIND] grit_blinded(3t)+windswept(3t). Consumes mud
                  for +5 dmg. Strips earthbound with 2-tile knockback
blood_lightning — /FL 2 SINGLE_LOS; [LIGHTNING+SHADOW] costs 8 HP. Soul shards: +3dmg/+1shocked
                  per shard (not consumed). Soul_drain active = HP cost refunded
frozen_ground   — /FL 3 ADJ_TILE; [ICE+EARTH] frozen_ground terrain r1 (12t): double move cost,
                  chill 1 on entry, 50% slip if windswept. Wet puddles → radius 2 expansion
asphalt_storm   — ONCE SELF r3; [EARTH+WIND] signature urban. Earthbound(3)+windswept(3)+damage
                  all r3. Creates rubble_tiles at 30% radius. Pre-earthbound: prone 2t

### Elemental Terrain / Field Effects (7 new, RARE / ONCE / per-floor-1)
acid_rain_weather — ONCE floor-wide 15t; universal Wet every 2t + 1 bypass acid/t +
                    sight -2 all. Lightning +25%. Fire hazards suppressed to 1 dmg, 2t
dead_block        — ONCE floor-wide 20t; Negromancy capstone. dark=8, enemy sight -3.
                    Kill = +1 extra soul shard. Revenant spawns at turns 5/10/15.
                    All healing -25%
crack_house_fire  — ONCE floor-wide 25t; Pyromania capstone. Fire spreads every 2t from
                    player tile (cap 30). Smoke: 2 bypass dmg every 3t all entities.
                    Collapse at turn 20: 20% tiles cracked
heat_wave         — ONCE floor-wide 20t; item or Pyromania alt. Spontaneous ignite(1) every
                    3t to non-Wet entities. Cold spells half duration. Move +2 energy cost.
                    Fire spells +3 dmg. TOL mitigates movement cost
aurora_drain      — ONCE floor-wide 15t; cyclic elemental drain from enemies to player.
                    5 phases: fire→ice→lightning→shadow→chaos. Chaos phase: -5 HP player
consecrated_gutter— /FL 1 ADJ_TILE zone 3x3 20t; player: +2 HP/t, +2 def, shadow resist.
                    enemies: 1 holy dmg/t, alarm suppressed. Soul shards preserved on death
flash_freeze      — ONCE floor-wide instant+terrain; all wet_puddles→ice_terrain, mud→frozen_ground,
                    room floor→ice_floor (20t). All entities: chill check (chill 2+→frozen,
                    ignite→stripped). Ice_floor: 20% slip, chill 1 on entry, melts to puddles 15t

### New Effects (Part 2)
shadow_marked, blinded (full room version), dark_mirrored (is_curse), night_terror_effect,
penumbra_buff, void_torn, dark_flames (wet-immune ignite variant), grit_blinded,
frostburned (paradox DoT), cinders, soul_drained (minor soul drain variant)

### New Terrain (Part 2 — beyond Part 1)
engine.magma_tiles, engine.swamp_gas_clouds, engine.frozen_ground_tiles,
engine.rubble_tiles, engine.ice_floor

### New Engine Flags (Part 2)
_shadow_dark (0-10), _fire_dimmed_turns, _acid_rain_active/_turns,
_dead_block_active/_turns, _crack_fire_active/_turns, _heat_wave_active/_turns,
_aurora_active/_turns/_phase, _consecrated_zone (set)/_turns,
_free_action_pending, _shadow_harvest_used, _shadow_mark_targets (set),
_wet_applications_this_weather

### Key Design Patterns (Part 2)
- Darkness meter = shadow school resource: build with penumbra/kill_the_lights,
  spend with shadow_harvest/void_strike (no-CD), thresholds at 2/3/4/5/6/8/10
- Fire is shadow's natural enemy: each fire tile decays darkness 1/turn extra
- Combo REQUIRE pattern extended: shadow_step (dark 2+ or shadowed target),
  chain_of_ice (chill 2+ on primary), frostburn (both resists bypassed = weaker solo)
- HP cost spells (blood_lightning -8 HP): CON scales both pool and damage simultaneously
- Terrain field events: ONCE or /FL 1; affect BOTH sides equally; both sides is the design
- Darkness meter anti-synergy with crack_house_fire: you cannot run both simultaneously
  (fire eats darkness) — forces build commitment
- New hooks introduced: on_after_damage (dark_mirror reflection), modify_incoming_heal (cinders)

### New AbilityDef Field
element: str | None  — needed across ALL elemental abilities for Overload/Convergence tracking

### Key Design Patterns (Part 1)
- Three passive systems with no ability slot: engine-level rules checked in execute callables
- HERALD pattern: /FL 1 floor-duration buff that transforms one element school's behavior; mutual exclusive
- TERRAIN OWNERSHIP: player-created earth terrain is targeted by tectonic_surge (own terrain only)
- ENTITY DEBUFF HISTORY: entity.elements_received tracks what elements hit this floor (not just active effects)
- AUTONOMOUS ENTITY: dust_devil uses wander_random AI (new mode) — no aggro, just random walk
- CAPSTONE TENSION: Pillar of Stone (immobile tank) vs Cyclone Step (hyperactive mobile) are opposites
- FOCUSED vs OVERLOAD: two passives that directly oppose each other — mono-element vs multi-element playstyle choice
