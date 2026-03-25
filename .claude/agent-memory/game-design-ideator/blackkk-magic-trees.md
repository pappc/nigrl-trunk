---
name: Blackkk Magic — Skill Tree Designs (v1 and v2)
description: All Blackkk Magic L1-L5 curse/hex tree variants, entity fields, effects, and abilities. V1 has 5 designs (A-E); V2 replaces C/D/E with 10 new designs (C-L).
type: project
---

## Design File Locations

V1 (Designs A–E): `nigrl-ideas/blackkk-magic-skill-designs.txt` (2026-03-22)
V2 (Designs C–L, 10 new): `nigrl-ideas/blackkk-magic-skill-designs-v2.txt` (2026-03-22)

**USER APPROVED**: A (The Mark) and B (Writ Large) from V1.
**REPLACED**: C (Soul Tax), D (Evil Eye), E (Jinx Juggling) — not liked.

XP source: curse LANDS on enemy (not on cast). 15 per application, 10 per passive proc,
25-50 XP bonus for combos/OVERLOADs. Exception: Hexburst (Design C-v2) = +25/doom_stack.

---

## V1 Designs A & B (APPROVED, retain for implementation)

**A — The Mark**: Single-target escalating hex. is_marked + mark_tier (0-5). Each debuff
applied to Marked enemy raises tier (+1 flat dmg/tier to all hits). Triple 6 Special
(PER_FLOOR 2, SINGLE_LOS) fires 6 + tier*6 no-defense damage, resets tier. L4 transfers
curses on death. L5 auto-stun+slow+cripple_armor at tier 5.

**B — Writ Large**: Setup-detonation system. entity.writ / entity.writ_2 (str|None).
Three Writ types: pain (melee-hit trigger, AOE burst), slow (movement trigger, AOE slow),
dread (sub-50% HP trigger, AOE fear). L4: two simultaneous writs + Double Tap cripple_armor
if both fire same turn. L5: doubled effects if target has 2+ debuffs at detonation.

---

## V2 Designs C–L Summary (10 new designs)

**C — Doom Clock**: PoE Doom mechanic. doom_stacks (0-5) increment each turn curse sits.
  Hexburst (INFINITE, SINGLE_LOS): consumes all doom for BKS*doom_stacks no-def damage.
  L4: 10*doom_stacks% skip-turn chance on hits. L5: doom spreads on death + Hexburst AOE
  fear at stacks>=4. Entity: doom_curse, doom_stacks.

**D — Haunt**: WoW Haunt. Ghost travels 1 tile/turn, haunts (+2 incoming dmg 10t), heals
  player on target death (3+BKS/4). L3: cold spot tiles along ghost path (35% slow proc).
  L4: two ghosts simultaneously. L5: teleport to dead target as ghost returns + loot carry.
  Engine: haunt_ghost dict, haunt_ghost_2.

**E — Impending Doom**: PoE Impending Doom. Hexbomb entity field with 8-turn fuse countdown.
  Detonates for (4+BKS) no-def + AOE(2+BKS/2). L2: dies-before-expiry also detonates.
  L3: force-detonate at reduced % ((8-fuse)/8 multiplier). L4: Doomchain — AOE-hit cursed
  enemies get chain bombs (fuse 4). L5: 1 dmg/tick + Nuclear Option at <25% HP (2x radius, 1.5x dmg).

**F — Punishment**: PoE Punishment. retribution_curse — every enemy attack triggers blowback
  to themselves: ceil(2+SWG/4) no-def. L2: karma_stacks compound multiplier (x1.75 at k=5).
  L3: STS/2 bonus when they attack player specifically; infinite duration (floor_duration).
  L4: Boomerang — karma-kill spreads curse to nearby enemy with full stack count.
  L5: karma>=7 triggers 1-turn faction flip (attack nearest ally). Every 7 stacks.

**G — Temporal Chains**: PoE Temporal Chains. time_taxed — energy reduction (10+TOL*2)%.
  Debuff durations extended +1/2 turns in chains. L2: buff durations on enemy tick 2x fast.
  L3: Temporal Snapshot (PER_FLOOR 2) — save HP+effects state; reactivate to REWIND target.
  L4: TOL*5% attack-skip chance each attempted attack. L5: Time Stop (PER_FLOOR 1) — all
  enemies gain 0 energy for 3 turns.

**H — Voodoo Doll**: Novel — dual-target link. Needle (attacker) / Doll (absorber).
  50% of Needle's damage echoes to Doll (no def). L2: 50% debuff propagation both directions.
  L3: Needle Drop (ADJACENT to Doll) — full damage to both simultaneously.
  L4: two simultaneous links; double-haunt = +4 dmg vuln + slow.
  L5: Self-link as Doll — 75% echo back to Needle; Y/N prompt on ability reuse.

**I — Profane Bloom**: PoE Profane Bloom. Cursed enemies explode on death: (4+STS/2) no-def
  to r=(1+debuffs//2) tile radius. L2: spread one random curse to each bloom-hit enemy (50% dur).
  L3: damage += BKS/3; radius also scales on distinct curse types; player takes 50% backsplash.
  L4: bloom_marked (+50% bloom damage for 3t) on bloom-hit enemies.
  L5: Unholy Ground — dead enemy tile cursed permanently this floor; 60% curse proc on walk.

**J — Spiritual Debt**: WoW Dark Pact. Pay the Price (SELF, INFINITE): spend 10% HP →
  debt++ + next curse doubled. Debt discharges on cursed kills (3+maxhp/10 per kill).
  L3: Absolution state at debt=0 — next curse tripled + Swagger bonus.
  L4: stack up to 3x Pay the Price (x2/x4/x8 multiplier) with permanent charge.
  L5: 20% lifesteal while debt==0. engine.spirit_debt int.

**K — Bane**: PoE Bane. BaneEffect ticks BKS/4 * distinct_debuff_count no-def damage.
  bane_meter = distinct curse types (0-5). L2: +1 flat bonus to all other debuff ticks.
  L3: OVERLOAD at bane_meter=5 — BKS*5 burst + refresh all debuff durations.
  L4: bane_overload_count persists per floor, boosting base formula; echo hit post-OVERLOAD.
  L5: Bane spreads on death (radius 1+bane_meter); OVERLOAD becomes AOE (r=1+TOL tiles).

**L — The Numbers Game**: Novel hex trap tiles. Drop a Bag (ADJACENT_TILE, PER_FLOOR 3):
  place '^' trap entity; triggers hex_snare (2t stun + 4t cripple_armor) on step.
  L2: traps invisible to enemies (no pathfinding avoidance); alert nearby enemies on trigger.
  L3: trap variants — Snare/Line Blast/Isolation Trap (key prompt at placement).
  L4: BKS*5% charge refund per trigger; snared enemies take +25% damage.
  L5: Spirit Grid — traps within 4 tiles network; triggering one powers up others (2x strength, 3t).

---

## New Entity Fields (V2 Designs C–L)

doom_curse: bool, doom_stacks: int (C)
hexbomb: bool, hexbomb_fuse: int (E)
retribution_curse: bool, karma_stacks: int, ai_override_turns: int, ai_override_mode: str|None (F)
time_taxed: bool, snapshot_hp: int|None, snapshot_effects: list|None, snapshot_exists: bool (G)
voodoo_linked: bool, voodoo_partner_id: int|None, voodoo_role: str|None (H)
bloom_marked: bool, bloom_marked_turns: int (I)
bane_active: bool, bane_meter: int, bane_tick_bonus: int, bane_overloaded_this_turn: bool (K)
powered_up: bool, power_up_turns: int, trap_type: str (on HexTrap entities, L)

## New Engine Fields (V2)

haunt_ghost: dict|None, haunt_ghost_2: dict|None (D)
time_stop_turns: int (G)
last_hit_was_karma: bool, retribution_count: int (F)
spirit_debt: int, spirit_debt_charged: bool, spirit_debt_charged_stacks: int (J)
absolution_available: bool, absolution_turns: int (J)
bane_overload_count: int, bane_overload_echo_ready: bool (K)
doom_active_entity_id: int|None (C)
hexbomb_active_entity_id: int|None (E)

## New Effects Needed (V2)

DoomCurseEffect — floor_duration (C)
HauntedEffect — 10t, +2 incoming dmg (D)
TimeTaxEffect — modify_energy_gain, buff double-tick, debuff duration extension (G)
RetributionEffect — floor_duration, karma_stacks on entity (F)
VoodooLinkEffect — floor_duration, expire_reason field for L4 natural-expiry burst (H)
BaneEffect — floor_duration, tick computes bane_meter, OVERLOAD check, original_duration field (K)
HexSnareEffect — 2t stun + 4t cripple_armor composite (L)

Effect base class: add original_duration: int field (needed for K OVERLOAD refresh).

## New Ability IDs (V2)

put_the_curse_on (C L1), hexburst (C L3)
go_get_em_unc (D L1)
set_the_timer (E L1)
catch_these_hands (F L1)
temporal_snapshot (G L3, PER_FLOOR 2), time_stop (G L5, PER_FLOOR 1)
stitch_em_together (H L1, dual-phase targeting), needle_drop (H L3, ADJACENT)
pay_the_price (J L1, SELF)
bane_of_existence (K L1)
drop_a_bag (L L1, ADJACENT_TILE, PER_FLOOR 3)

## Dungeon Fields Needed (V2)

dungeon.cold_spots: dict[(x,y) → int] (D L3)
dungeon.unholy_tiles: dict[(x,y) → list[...]] (I L5)
dungeon.trap_grid: list[set[int]] (L L5)

## Design Philosophy Notes

- Time Stop (G L5) is the single most powerful ability in any BM design — 1/floor, 3 free turns.
- OVERLOAD (K L3) is the highest single-XP event (+50) — rewards multi-tree curse stacking.
- Spirit Grid (L L5) is the only tile-network mechanic in the game — corridor-specific power.
- Temporal Snapshot (G L3) is the only rewind mechanic designed for NIGRL.
- Self-link as Doll (H L5) is the only self-debuff-for-power design besides Spiritual Debt.
- Designs G, H, L need new UI states or secondary targeting prompts.
- "No defense" damage: entity.hp -= amount directly, per established convention from V1.
