---
name: Colored Dranks — Meta Drink System
description: All colored drank designs (Orange through Clear) including system architecture, shared data structures, and cross-drank interaction matrix
type: project
---

# Colored Dranks — Meta Drink System

Design doc: `nigrl-ideas/item-colored-dranks.txt` (2026-03-15)

## Drank Roster (14 total)

| Color  | item_id       | Meta Role            | Mechanic Summary                                      |
|--------|---------------|----------------------|-------------------------------------------------------|
| Purple | purple_drank  | Echo/Copy            | Replays last drink; adds copy to inventory (EXISTING) |
| Blue   | blue_drank    | Multiplier           | Next drink x2^stacks (EXISTING)                       |
| Red    | red_drank     | Mode Shift           | Drinks free + doubled duration for 200t (EXISTING)    |
| Green  | green_drank   | On-Drink Trigger     | Each drink heals/cleanses, per stack (EXISTING)       |
| Orange | orange_drank  | Hangover Conversion  | Pending stacks → +15 HP (or +5 armor) each            |
| Yellow | yellow_drank  | Duration Sync        | Averages all drink buff durations across active buffs  |
| Pink   | pink_drank    | Buff Mirror          | Copies highest-duration buff to nearest enemy debuff  |
| White  | white_drank   | Cash Out             | Wipes all buffs → +1 perm stat per 50t of duration   |
| Grey   | grey_drank    | Freeze               | Pauses all drink buff timers for 30t                  |
| Black  | black_drank   | Roulette             | Applies random drink from zone loot pool               |
| Gold   | gold_drank    | Floor Carry          | Captures strongest buff; reapplies at next floor       |
| Silver | silver_drank  | Investment           | Counts drinks over 200t; tiered payout on expire       |
| Brown  | brown_drank   | Reroll               | Force-expires worst buff; random replacement           |
| Clear  | clear_drank   | Pre-Pay Hangover     | Pays pending stacks as mild debuff now (-10 e/tick/stack, 15t/stack) |

All are nonalcoholic, "soft_drink" type, Drinking skill only, 100 XP, value=25 (Gold=40), zones=["crack_den"].

## Key Shared Systems Introduced

### DRINK_BUFF_IDS set (effects.py)
Set of all drink buff effect ids for meta-drank targeting. Expands ALCOHOL_BUFF_IDS.
Includes both alcoholic and soft_drink buff ids. Excludes floor-duration effects.

### EXCLUDE_FROM_SYNC set (effects.py)
{"green_drank", "five_loco", "alco_seltzer_tox_resist", "four_fingers_of_fentanol"}
Floor-duration or debt-carrying effects excluded from Yellow/White/Grey/etc.

### engine._gold_drank_carry: tuple[str, int] | None (engine.py)
Stores (buff_id, duration) from Gold Drank. Applied at floor descent, then cleared.

### Grey Drank Freeze Pattern (engine.py tick loop)
grey_freeze = any(e.id == 'grey_drank' for e in entity.status_effects)
If True: skip eff.tick() for all effects in DRINK_BUFF_IDS.
This is the canonical pattern for "freeze all drink buff timers."

### Silver Drank Counter Pattern
SilverDrankEffect._drinks_consumed: int, incremented in inventory_mgr.py's drink dispatch.
On expire: tiered payout table (n=0 through n>=6, max payout = full HP + armor + 2 debuff clears + 50 energy + 1 perm stat).

## New Effect Classes Needed

- GreyDrankEffect     (id="grey_drank", 30t buff, no hooks — engine loop handles freeze)
- SilverDrankEffect   (id="silver_drank", 200t buff, _drinks_consumed counter, tiered expire payout)
- PinkMirroredEffect  (id="pink_mirrored", enemy debuff, stores inversion_type + magnitude)
- MiniHangoverEffect  (id="mini_hangover", debuff, -10 energy/tick per stack, 15t/stack)

## New Handlers Needed (xp_progression.py)

_handle_orange_drank, _handle_yellow_drank, _handle_pink_drank, _handle_white_drank,
_handle_grey_drank, _handle_black_drank, _handle_gold_drank, _handle_silver_drank,
_handle_brown_drank, _handle_clear_drank

Each delegated in engine.py, dispatched from inventory_mgr.py soft_drink elif chain.

## Key Design Rules for Dranks

- All new dranks respect Blue Drank (2^stacks handler calls), Red Drank (doubled duration),
  and Green Drank (on-drink trigger) automatically via the existing dispatch code.
- Purple Drank records last_drink_id = the new drank's id; replay fires the handler again.
- Black Drank and Brown Drank dispatch replacement drinks using the same pool as loot.py's
  ZONE_DRINK_TABLES; exclude meta-dranks from random pool (to keep recursion bounded).
- White Drank cap: max +6 permanent stat points per drink (300 duration equivalent).
- Gold Drank capture: records a snapshot (buff_id, duration) — does NOT hold a live reference.
  Buff may expire before descent; snapshot still reapplies at next floor.

## Notable Cross-Drank Combos (for future Drinking skill perk design)

- Red + Silver: free drink window → max Silver counter → perm stat on Silver expire
- Blue + Grey: 60t freeze window (double the normal 30t)
- White + Red: Red free actions → stack 5 buffs → White cash out for 5+ perm stats
- Gold + Red: capture Red Drank → free drink session on turn 1 of next floor
- Purple + Black: two random drinks total (Purple replays a new Black draw)
- Yellow + Pink: equalized durations = effectively random Pink mirror target

## Balance Anchors

White Drank max perm stats: 6 per drink. Requires 300t of buff duration to be active.
  Equivalent to ~3 mutation tiers of stat gain. Reasonable ceiling.
Silver Drank n>=6 stat: requires 6 separate drinks during 200t window.
  With Red Drank free actions this is achievable in one session — intended high ceiling.
Grey Drank freeze: 30t (Blue gives 60t). Red Drank has 200t frozen — power combo.
  Tuning knob: cap freeze duration or exclude Red Drank from DRINK_BUFF_IDS if too strong.
Pink Drank mirror duration: flag "200t shaken" case (Red Drank mirrored).
  Should probably cap mirror duration at 50t regardless of source.
