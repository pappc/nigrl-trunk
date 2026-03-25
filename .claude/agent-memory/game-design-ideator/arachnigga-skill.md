---
name: Arachnigga Skill — 5 Perk Tree Proposals
description: Design record for Arachnigga perk trees: core mechanic, effects, abilities, balance notes
type: project
---

Design doc: `nigrl-ideas/arachnigga-perk-trees.txt`
Date: 2026-03-22

## Core Mechanic
- Cobweb tiles: freeze/stun enemies on contact, 50% chance to fail escape attempt per turn
- Venom DOT: poison flag, bypasses armor, re-apply refreshes (no stack)
- XP source: webbing enemies, applying venom_dot to enemies, spiderling kills

## 5 Trees Summary
- Tree A "The Trapper"     — web placement/quantity/permanence; floor-nuke capstone
- Tree B "Venom Dealer"    — poison DOT scaling; death-pool hazards; healing from kills
- Tree C "Eight Legs McGee"— mobility; webs deposited from movement; silk_rush speed
- Tree D "Spiderling Wrangler" — summon spiderlings; egg sac; swarm damage
- Tree E "Acid Freak"      — acid_web tiles (deal dmg + web); armor strip; self-harm/reward loop

## New Effects Needed (effects.py)
- webbed        — before_turn hook: 50% skip-move chance, 6t (reinforced: 75%)
- venom_dot     — DOT 3 or 5 dmg/turn, 4t, poison flag, refresh on reapply
- heavy_venom   — DOT 8 dmg/turn, 6t, from venom_strike ability
- molt          — +3 armor, 10t, refresh on reapply (from Tree C L1 and Tree E L4)
- silk_rush     — SpeedBoostEffect +20 energy/tick, 6t, no stack, refresh

## New Hazard Tile Types (hazards.py)
- cobweb       — char '#' dark yellow, webs entities on contact
- acid_web     — char '~' acid green, 3 dmg/turn + webs on contact
- venom_pool   — char '~' dark green, applies venom_dot on contact, 15t duration

## New Ally Entity Types
- spiderling   — entity_type="ally", char='s' lime green, hp=6/12/20 (upgrades), speed=120
- egg_sac      — entity_type="hazard", char='O' brown, hp=1, hatches on adjacent enemy

## New Ability IDs (abilities.py)
- lay_web        — ADJACENT_TILE, PER_FLOOR 3
- web_snare      — SINGLE_ENEMY_LOS, INFINITE (CD 8)
- web_burst      — SELF, PER_FLOOR 1
- molt_ability   — SELF, PER_FLOOR 2
- spider_run     — SELF, PER_FLOOR 2
- call_spider    — ADJACENT_TILE, PER_FLOOR 2 (→3 at L2)
- egg_sac_ability— ADJACENT_TILE, PER_FLOOR 1
- venom_strike   — ADJACENT, INFINITE (CD 10)
- acid_drip      — ADJACENT_TILE, PER_FLOOR 2 (Tree E L1 if no lay_web)
- acid_flood     — SELF, PER_FLOOR 1

## Engine Fields Needed
- engine.cobweb_tiles: dict[tuple, entity]
- engine.spiderlings: list[Entity]
- engine.player_consecutive_moves: int  (Tree C L2 streak counter)

## Key Balance Rules
- Cobwebs burn when fire tiles overlap (prevents Pyromania stacking trivially)
- Tree D spiderlings at L5 deal 8-12 effective dmg vs webbed targets; strong but gated
- Tree E acid_web self-damage: 3 dmg/turn; Exoskeleton (L4) gives 50% reduction + free molt
- Spiderling kills count as player web XP (XP hook in xp_progression.py)

## Cross-Skill Synergies Noted
- Stabbing Gouge + webbed = near-permanent CC on one enemy
- Pyromania fire DESTROYS cobwebs (negative interaction — warn players)
- Jaywalking Dash pairs with Tree C Silk Spitter (dash deposits web on origin tile)
- Catchin' Fades Unfazed: swagger grind while enemies are stuck in webs
