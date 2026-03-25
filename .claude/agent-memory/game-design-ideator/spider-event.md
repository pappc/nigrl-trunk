---
name: Spider Infestation Floor Event — 5 Enemy Designs
description: Design record for the spider_infestation floor event: 5 hostile spider types for Crack Den floors 2-3
type: project
---

Design doc: `nigrl-ideas/spider-event-monsters.txt`
Date: 2026-03-23

## Event System Context
- config.py FLOOR_EVENT_REGISTRY has "spider_infestation" already defined (name + message)
- config.py ZONE_FLOOR_EVENTS: eligible_floors=[1,2] (zone_floor indices, i.e. floors 2-3)
- No spawning logic exists yet — the event fires but does nothing beyond messaging
- Implementation needs: spawn table override + web hazard seeding in zone_generators.py or dungeon.py

## 5 Spider Enemy Designs

| Key          | char | color (RGB)       | HP range | Effective dmg | AI            | Speed | Unique threat             |
|--------------|------|-------------------|----------|---------------|---------------|-------|---------------------------|
| pipe_spider  | 's'  | (160,120,80)      | 7-12     | 1-2           | WANDER_AMBUSH | 130   | Swarm + venom stacking    |
| sac_spider   | 'S'  | (200,200,160)     | 14-24    | 2-4           | ROOM_GUARD    | 110   | Silk Shot = web_stuck CC  |
| wolf_spider  | 'w'  | (120,80,50)       | 20-30    | 3-6           | WANDER_AMBUSH | 140   | Pure speed + dodge 20%    |
| orb_weaver   | 'O'  | (180,140,200)     | 16-26    | 1-3           | STATIONARY_GUARD | 90 | Web Wrap stun + Venom Bite|
| brood_mother | 'M'  | (220,80,60)       | 40-55    | 3-5           | WANDER_AMBUSH | 90    | Boss; escort + death split|

## Key Implementation Notes
- Orb Weaver: STATIONARY_GUARD AI (never moves). Seeds 3-5 cobweb hazards at spawn point.
  Needs web immunity (check enemy_type == "orb_weaver") in engine.py line ~1003 web_stuck block.
- Brood Mother: escort=[SpawnEscort("pipe_spider", (2,4))], death_split_type="pipe_spider", death_split_count=3
- Sac Spider Silk Shot: uses STUN with duration=2 as approximation; developer to decide if web_stuck
  should become an OnHitEffect kind or keep STUN approximation
- Pipe Spider venom: 60% on-hit, 2 DOT for 6t. Uses VenomEffect stacking. Arachnigga XP should fire.
- Wolf Spider: no DOT, no CC. Pure physical + dodge. Pounce 1.5x, 30% chance.

## Spawn Table Structure
Suggested "crack_den_spider_event" table: zone_floor 1 (pipe 25, sac 20, wolf 20, orb 15, brood 8)
Normal enemies fill remaining ~12%. Floor 3 (zone_floor 2): wolf/brood weights +2 each.

## Arachnigga Synergy
- L1 web immunity makes pre-placed floor webs neutral (not traps)
- Brood Mother encounter = largest single Arachnigga XP source on the event floor
- Wolf Spider webbed = very high value play (stops speed advantage)
- Overall: event gives ~1.5-2x normal Arachnigga XP per cleared floor

## Balance Anchors Used
- Normal Crack Den: Tweaker 15-25 HP, Thug 25-30 HP. Spiders fit inside/around this range.
- Zone 0.5x damage mult applies to all spider physical damage.
- Player at this stage: ~80-130 HP. Spider DOT is real pressure, not instant death.
