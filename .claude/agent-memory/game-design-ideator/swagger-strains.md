---
name: Swagger Mutation Strains
description: Design notes for the Swagger-focused Meth Lab strains — V1 (Flex Tape, Big Steppa, Front Page) and V2 (Hustle Hard, Known Associate, Cold Chain)
type: project
---

# Swagger / Mutation Strains (2026-03-14)

V1 design: `nigrl-ideas/swagger_mutation_strain_designs.txt`
V2 design: `nigrl-ideas/swagger_mutation_strain_designs_v2.txt` — PREFERRED CURRENT

These are the sixth and final stat strains, completing full stat coverage for the Meth Lab zone.
Swagger starts at 0 and is not rolled at character creation (stats.py:47).
swagger_defence = int(effective_swagger / 3) — every 3 Swagger = +1 melee defence.

## V1 Strains (reference/deprecated)

**Flex Tape** — pure gamble, forced mutations, perm SWG gain/loss. Gold Chain (neck) unique drop.
**Big Steppa** — kill-proc SWG growth, Steppa Shame redemption mechanic. Uses persistent buff window.
**Front Page** — rep meter (engine._front_page_rep). DISCARDED: rep meter is a new persistent engine field.

## V2 Strains (current design — strict pattern adherence)

**Hustle Hard** (Pattern A — Kushenheimer): color (215,185,55) burnished gold.
- Lower tiers cost MORE radiation (inversion). Tiers 4-5 force mutations.
- Tier 5: forced GOOD mutation (highest eligible tier) + +1 perm SWG + HustleHardBuff + 2 Hustle Shot charges.
- Tier 4: forced STANDARD mutation + +2 temp SWG (30t).
- Tier 3: 100 rad cost, +1 temp SWG (20t). No mutation.
- Tier 2: 125 rad cost, nothing. Pure waste.
- Tier 1: 0 rad cost, -1 perm SWG. Pure loss.
- Unique: "hustle_bracelet" (accessory, +2 SWG, +1 PWR, -25 to all Hustle Hard rad costs).
- Ability: "hustle_shot" (ADJACENT, TOTAL) — burns remaining buff duration into burst dmg scaling with swagger_defence.

**Known Associate** (Pattern B — Skywalker OG): color (200,165,40) champagne gold.
- Three strengths of "Street Presence" buff (I/II/III). Duration = max(floor, effective_swagger * multiplier).
- III (90-100): 40t Presence. On melee kill: forced GOOD weak mutation (50 rad). +1 perm SWG. +3 temp SWG.
- II (72-89): 25t. On melee kill: 20% forced GOOD weak mutation (50 rad). +2 temp SWG.
- I (50-71): 15t. No kill proc. +1 temp SWG.
- Tier 2 (25-49): +40 rad. Pure resource gain, no presence.
- Tier 1 (1-24): forced BAD mutation (highest eligible tier). -1 perm SWG.
- Unique: "the_reputation" (accessory, +3 SWG, +6t to all Street Presence durations).
- Ability: "call_the_play" (SELF, TOTAL) — gated by active Presence; fires STANDARD mutation now.

**Cold Chain** (Pattern C — Nigle Fart): color (100,160,220) steel blue.
- All tiers except 1 gain radiation (+20 to +70 rad). Tier 1 drains radiation (-40 rad).
- Tiers 3-5 apply ColdChainAura: modifies incoming damage with doubled Swagger defence.
- Aura also has on_player_melee_hit kill proc: 5/10/15% chance +1 perm SWG.
- All tiers 2-5 grant Cold Read ability charges (1-2 per tier).
- Tier 1 (1-21): -40 rad, -1 perm SWG, RadDrainEffect (halves rad gains 10t).
- Unique: "signet_ring" (ring, +3 SWG, +2 DEF, +2 DR while ColdChainAura active).
- Ability: "cold_read" (SELF, TOTAL) — 10x mutation probability check now, no guaranteed mutation.

## Shared New Effects (V2)

- SwaggerCrashEffect (id="swagger_crash") — V1 remains valid, reused in V2 (same mechanic)
- ShookMonsterEffect (id="shaken_monster") — monster -defence debuff, V1 defined, reused in V2
- HustleHardBuff (id="hustle_hard_buff") — temp SWG via apply/expire hooks
- StreetPresenceIII/II/I (ids="street_presence_iii/ii/i") — temp SWG + kill proc on_player_melee_hit
- ColdChainAura (id="cold_chain_aura") — modify_incoming_damage (doubled SWG) + kill proc
- ColdChainChill (id="cold_chain_chill") — monster energy + defence debuff
- RadDrainEffect (id="rad_drain") — modify_rad_gain, halves all rad gains for 10t

## V2 New Engine/Lifecycle Requirements

- modify_rad_gain hook on Effect base class (already in V2 plan; RadDrainEffect depends on it)
- force_mutation_good(engine, tier) helper — needed for Hustle Hard tier 5 and Known Associate III
- force_mutation_standard(engine, tier) helper — needed for Hustle Hard tier 4 and Call the Play
- force_mutation_bad(engine, tier) helper — needed for Known Associate tier 1

## Swagger Loss Floor Mechanic

modify_base_stat("swagger", -N) floors at 1 per call.
If swagger is 0 and loss fires: apply SwaggerCrashEffect instead (cosmetic shame, no permanent damage).
swagger_defence at negative effective_swagger: int() truncates toward zero → floors at 0.

## Loot Weights (V2)

- Hustle Hard: 3 (standard)
- Known Associate: 3 (standard)
- Cold Chain: 2 (slightly rarer — RadDrainEffect hook is non-trivial)

## Design Rule (recorded for future)

Front Page was rejected for introducing a persistent engine field (engine._front_page_rep)
and a new HUD element. V2 enforces: NO new persistent per-run engine state. All swagger
strain mechanics must live in status effects (lifecycle hooks), ability charges, and
one-time stat modifications. "call_the_play" being gated by active status effect is
acceptable because it checks engine.player.status_effects — no new engine flag.
