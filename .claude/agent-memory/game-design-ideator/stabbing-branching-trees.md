---
name: Stabbing Branching Skill Trees
description: 5 branching tree designs for the Stabbing skill — bleed mechanics, stealth, tox synergy, and unique topologies
type: project
---

Design doc: `nigrl-ideas/stabbing-branching-skill-trees.txt`
Date: 2026-03-26

## Trunk (Shared All Designs)
L1 Gouge — activated, ADJACENT, INFINITE, req stabbing weapon. Dmg = STS - def. 5t stun (breaks on player hit). 12t CD.
L2 +2 STS — stat perk.
L3 Windfury — min(30, STS)% extra attack on stabbing melee hit. Cannot chain.

## BleedStabEffect (Critical New Effect)
id = "bleed_stab". Independent-timer stacking DOT.
Stack structure: list[tuple[int, int]] = list of (timer, tox_snapshot).
Damage per tick = sum(1 + floor(tox_snapshot/15) for each active stack).
on_reapply: append new (duration, tox_snapshot) entries (no shared timer reset).
expired = len(stack_timers) == 0. Max 20 stacks (configurable per branch).
Pattern: identical to HotEffect.stack_timers but for damage. tox_snapshot defaults to 0 (base = 1 dmg/stack/tick).

## New Entity Fields Needed (entity.py)
- stabbing_marked: bool = False
- stabbing_mark_timer: int = 0
- tox_seizure_triggered: bool = False
- wound_severity: int = 0
- exsanguinate_triggered: bool = False
- dazed_turns: int = 0

## New PlayerStats Fields (stats.py)
- coil_charge: int = 0 (Take 2 Coil branch)

## New Effects Needed (effects.py)
- bleed_stab — see above
- ShadowEffect (id="shadow", buff, duration variable) — breaks on player_melee_hit
- GougedDecisionEffect (id="gouged_decision", debuff) — nullifies first monster attack in 5t window
- FearEffect (id="fear") — if not already present: target.ai_state → FLEEING, duration-based
- ShadowEffect.on_player_melee_hit: expire self immediately

## New Engine State Needed (engine.py)
- fadeout_turns_remaining: int = 0 (Take 5 Phantom branch)
- Decrement at end of player turn.

## New AI Hooks Needed (ai.py)
- LOS aggro check (IDLE/WANDERING → CHASING): if engine.fadeout_turns_remaining > 0 OR player has "shadow" effect: skip.
- dazed_turns: before do_ai_turn(), if entity.dazed_turns > 0: decrement, return.
- Unaware check: (entity.ai_state in {AIState.IDLE, AIState.WANDERING, AIState.PASSIVE_UNTIL_HIT} and not entity.provoked)

## Five Design Summaries

**Take 1: Surgeon vs Butcher (Y-split L3)**
Surgeon: Cold Read (+STS dmg vs unaware), Arterial (bleed on stun break), Grey Matter (nullify decision instead of freeze).
Butcher: First Cut (1 bleed/hit), Rip and Tear (2x bleed on Windfury; 100% Windfury at 4+ stacks), Blood Rain (corpse bleed splash 50% per stack).
Best for: Surgeon = elite enemies. Butcher = packs.

**Take 2: The Coiled Spring (Diamond)**
Fang: Inject (+3 tox/hit), Venom (tox-scaled bleed damage), Overdose (50+ tox triggers seizure: 3t stun + 8 bleed stacks).
Coil: Patient Strike (coil_charge builds on non-attack turns, max 5, bonus dmg on discharge), Spring Release (coil → guaranteed crit + stacks), Perfect Strike (Gouge + coil discharge, 2-hit stun window).
Shared T3: Toxic Rush (kill with bleed+tox = speed boost + heal).
Best for: Fang = Meth Lab / tox weapons. Coil = isolated tough targets.

**Take 3: They Never See It Coming (Triple Fork L4)**
Trunk L4: Lacerate (1 bleed/hit every stab, always).
Blur: Flurry Step (free move on stabbing kill), Bleeding Speed (+5 speed/2 total floor bleed stacks, cap +30).
Open Vein: Deeper Cut (2x bleed stacks per hit, 9t duration), Hemorrhage (defense → 0 at 8+ stacks, stacks never expire).
Ghost Blade: Shadow Walk (3t no-new-aggro after kill), The Last One They See (Shadow Gouge: 3x dmg + fear 10t + 6t CD).
Best for: Blur = fast clears. Open Vein = tanky armored. Ghost Blade = unaware enemies.

**Take 4: The Bleeding Edge (W-shape)**
Trunk: all L1-L3 trunk. Split immediately at L4 into Wound/Mark.
Wound: Bleed Out (1 bleed/hit + slow on first stack), Wound Master (+2STS+2STR, bleed lasts 3t longer).
Mark: Hunter's Mark (Gouge applies 15t mark: +2 dmg to all hits), Mark Mastery (+2STS+2SWG; all damage sources bleed marked target).
Shared T3: Cut Deep (+2STS+2STR+2CON; 5+ stacks = double bleed dmg; Gouge CD 12→8).
Wound T4: Exsanguinate (below 30% HP + 3+ stacks: instant burst = sum of all remaining tick damage).
Mark T4: Execute Window (marked target below 40% HP: Gouge CD removed + 2x Gouge damage).
Best for: Wound = tanky enemies. Mark = elites/named.

**Take 5: The Switchblade Philosopher (Long trunk Y-split)**
Trunk L4: Serrated (1 bleed/hit, 8t, wound_severity: +1/bleed tick → -1 defense per 5 severity).
Trunk L5: Reading Bodies (+STS/2 bonus vs unaware enemies, bypasses defense).
Phantom: Fadeout (kill unaware → floor-wide no-new-aggro 3t), Wraith (Shadow Gouge: 4x dmg, no-provoke, 1t daze, 6t CD vs unaware).
Hurricane: Red Tide (Windfury cap 50%, 2x bleed on Windfury procs), Feeding Frenzy (recursive Windfury chains max 4x if any enemy has 5+ stacks; 4x bleed dmg in Frenzy).
Best for: Phantom = unaware floor. Hurricane = dense room carnage.

## Gouge Upgrade Summary (cross-design)
- Surgeon T3 (Grey Matter): nullify-action instead of freeze. Two free hits before retaliation.
- Coil T4 (Perfect Gouge): coil_charge amplifies damage + 2-hit stun window.
- Ghost Blade T2 (Shadow Gouge): 3x dmg + fear 10t + halved CD when used from Shadow.
- Phantom T2 (Wraith Strike): 4x dmg + no-provoke + 1t daze when used vs unaware.
- Mark T4 (Execute Window): CD removed + 2x dmg vs marked target below 40%.

## Recommended Implementation Order
1. BleedStabEffect (required by all branches)
2. Take 1 Surgeon/Butcher (cleanest Y-split; most standard; best for piloting)
3. Take 5 Hurricane/Phantom (richest trunk; most mechanical depth)
4. Takes 2, 3, 4 (more novel topology; implement after bleed system is live)

**Why:** Confirmed by design review — Take 1 is the recommended pilot design.
