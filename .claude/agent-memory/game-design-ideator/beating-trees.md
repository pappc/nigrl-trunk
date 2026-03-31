---
name: Beating Skill Tree Variants
description: 10 distinct Beating skill tree designs (L1-L5 each) covering crowd control, crits, tank, knockback, debuff/attrition, combo meter, AOE/cleave, counter-attack, berserker/rage, and utility/healing themes.
type: project
---

Design doc: `nigrl-ideas/beating-skill-tree-designs.txt`
Date: 2026-03-26

## 10 Variants Summary

1. **Skull Cracker** (CC/Stun) — L1 Brass Knuckle Theory (20% stun on hit), L2 Headache (ADJACENT 3/floor, daze->stun), L3 Wide Swing (stun splashes to adjacent), L4 No Witnesses (+2 STS, kill stunned = extend all stuns +5t), L5 Chain Gang (SINGLE_ENEMY_LOS AOE stun 4t r=3 2/floor)

2. **Headhunter** (Crit) — L1 Eye on Prize (+3 STS = +9% crit), L2 Skull Tap (ADJACENT INFINITE always-crits + skull_tapped +25% dmg taken), L3 Eyes Wide Open (2.5x crit mult + 35% free extra hit on crit), L4 I Feel It (+5% crit/stack InTheZone max 5), L5 Glory Days (SELF 1/floor 15t auto-crit all swings)

3. **Iron Curtain** (Tank) — L1 Thick Skin (+3 CON +2 STR), L2 War Wound (hit-taken = +1 power stack 15t timers), L3 Tough As Nails (after 3 hits taken: 15% lifesteal on attacks), L4 Bunker Up (SELF 3/floor fortified: +6 def + stun immune 8t), L5 Last Man Standing (once/floor: heal 25% at <30% HP; <50% HP = slow on all hits)

4. **Pinball Wizard** (Knockback) — L1 Send It (+4 STR), L2 Billiards (knockback chain = +STR/2 bonus + 1 extra slide), L3 Pinball (Bash cooldown 10->5, wall collision resets CD), L4 Crowd Control (SELF 2/floor: 6t all melee knockback 2 tiles), L5 House of Pain (SELF 1/floor: adjacent enemies take STR/3/turn + knockback trap 10t)

5. **Grinder** (Debuff/Attrition) — L1 Wear 'Em Down (every hit: Roughed Up stack = -1def -5energy, max 6), L2 Knee Tap (ADJACENT INFINITE extreme slow ratio=0.3 12t CD), L3 Keep Swinging (end-of-attack-turn: extend all Roughed Up +1t; 4th+ consec hit +25% dmg), L4 Bone Deep (kill with 3+ stacks: transfer half stacks to adjacent), L5 Beaten Into Submission (ADJACENT 2/floor: 6 stacks + Broken: can move, cannot attack 5t)

6. **Built Different** (Combo/Momentum) — L1 Momentum (melee hit = +1 stack max 10, lose all if no attack that turn or take 20+), L2 First Gear (+2 STR; 3+ stacks = +2 dmg, 6+ = +5), L3 Second Wind (SELF INFINITE, cost all stacks min 3: heal 5+stacks*3, grant energy action, 8t CD), L4 Detonation (at 10 stacks: 3x dmg + Overwhelmed -4 all stats 5t), L5 On A Roll (Detonation resets to 5 stacks, Detonation kill = chain free Detonation within 3t)

7. **Wrecking Crew** (AOE/Cleave) — L1 Wide Load (+2 CON +3 STR), L2 Backswing (30% free half-dmg hit on random other adjacent enemy), L3 All-Out (SELF 3/floor 5t CD: next attack cleaves all adjacent independently), L4 Ripple Effect (kill = STR/2 splash to all within 2 tiles, no defense), L5 HAYMAKER (LINE_FROM_PLAYER 1/floor: 2x dmg all on line, perpendicular knockback 2t)

8. **Counterpuncher** (Reactive/Counter) — L1 Bobbing and Weaving (+3 SWG), L2 Counter (when hit deals 0 net damage: free counter-attack), L3 Parry (SELF 4/floor 6t CD: stance blocks next hit -> 200% crit counter), L4 Payback (take 8+ dmg: next attack +50% for 10t), L5 Retaliation (ONCE, death-trigger: final slam all adjacent for STR*3 undefended before death resolves)

9. **Berserker** (Rage) — L1 Bloodlust (each hit taken = +1 BloodDebt stack, max 8, ALL consumed on next attack as flat damage), L2 Pain is Fuel (-2 CON +5 STR), L3 RAGE (SELF 2/floor: 15t fury = +60% dmg dealt/+40% dmg taken/+20 energy, expires -> Crashed -10 energy 8t), L4 Feed the Beast (kill during rage = +3 rage duration, 25% refund charge), L5 Blackout (rage natural expiry: no Crashed + free AOE slam STR dmg adj + 5hp/target)

10. **Street Medic** (Utility/Healing) — L1 Percussive Maintenance (kill with beating weapon = heal 8HP, upgrades at L5), L2 Bone Saw (ADJACENT_TILE 3/floor: vs enemy = rattled -2 power 8t; vs self tile = clear 1 DoT stack + heal 2d6), L3 Concussion Protocol (stun expiry: post-stun-daze = first attack after stun deals 0 dmg), L4 Emergency Surgery (SELF 1/floor: <50%HP only, full turn, heal 30% max HP + clear DoTs + Stabilized -30% dmg 5t), L5 Body Shop (end-of-floor >80%HP = permanent +1 CON, max 3 total; L1 now heals 8+CON/3)

## New Effects Needed
dazed, skull_tapped, in_the_zone, glory_days_effect, war_wound, fortified, roughed_up, broken, momentum, overwhelmed, crowd_control_active, house_of_pain_active, payback, parried (priority=150), blood_debt, fury (berserker rage), crashed_berserker, post_stun_daze, stabilized, rattled (if missing), all_out_pending

## New Abilities Needed
headache, chain_gang, skull_tap, glory_days, bunker_up, crowd_control, house_of_pain, knee_tap, beaten_into_sub, second_wind, all_out, haymaker, parry, retaliation (death-trigger ONCE), berserker_rage, bone_saw, emergency_surgery

## Key Engine Flags Needed
floor_hits_taken, last_melee_target_id, consecutive_hit_turns, next_attack_cleaves, detonation_chain_available, detonation_chain_turn, iron_curtain_heal_used (per-floor bool), body_shop_gains (permanent int)

## Balance Notes
- Safest to implement: Street Medic (kill hooks + SELF abilities), Skull Cracker (uses existing stun system)
- Riskiest: Berserker RAGE (+40% dmg taken could spike deaths — start at +25%), Retaliation (death interrupt needs careful ordering)
- Beating XP: all abilities that deal damage should call gain_potential_exp("Beating", damage, bksmt) per existing Bash pattern
- Fury effect naming: use "fury" to avoid conflict with Meth-Head tree's "rage" naming convention from L4/L5 designs

**Why:** Confirmed actual current state of Beating tree in skills.py: only L1-L3 partially designed (+3 STR, Bash ability, Crit+ passive), L4-L10 all placeholder. The "Largest single STR grant = +4" note in MEMORY.md refers to other trees — Pinball Wizard V1 L1 (+4 STR) is the new highest in Beating variants.
