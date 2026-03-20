---
name: Spell Compendium Index
description: Quick-reference index for all three spell compendiums (45 + 35 + 34 = 114 total ability designs)
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
