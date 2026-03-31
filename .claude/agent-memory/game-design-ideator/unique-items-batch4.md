---
name: Unique Items Batch 4 Patterns
description: Key mechanics, engine fields, and design patterns from unique-items-batch4.txt (25 items)
type: project
---

Source: `nigrl-ideas/unique-items-batch4.txt`; summary: `summaries/unique-items-batch4-summary.txt`

**Why:** Design reference to avoid duplicating mechanics in future batches.
**How to apply:** Check these patterns before designing new weapons/rings/neck/feet/hat uniques.

### New Engine Fields
prophets_shank_charges (int, resets on floor), ancestral_kill_count (run-wide kill counter),
chain_whip_stance (int, resets on player move), second_wind_used_this_floor (bool),
counterfeit_ring_active (bool, cash >= $50 threshold), ring_of_block_chilled_rooms (set),
pension_ring_kill_count + milestones (run-wide), comeuppance_active + comeuppance_turns_remaining,
specter_proc_turns + specter_damage_active, marathon_steps_this_floor (int),
welder_fire_bonus_active (bool), crucifix_dodge_last (int), seven_deadly_sins_this_floor (int),
fitted_cap_hp_below_50 (bool guard flag)

### New PlayerStats Fields
permanent_crit_bonus: float = 0.0 (Fitted Cap of the Streets)
  - Included in crit_chance property: return effective_street_smarts * 0.01 + permanent_crit_bonus

### Key New Design Patterns
- "Take damage to charge" weapon (Prophet's Shank): player HP loss = combat power buildup
- "Kill-or-suffer" execution weapon (Chrome Shorty): kill = buff, survive = self-damage
- Run-wide accumulating weapon stat (Ancestral Beater): no cap, rewards long runs
- Stationary-stance mechanics (Chain Whip): parallels Gatting Fortify heat pattern
- "Clean kill" crit accumulation with HP-threshold reset (Fitted Cap): zero-to-hero + glass
- Per-debuff dodge scaling (Crackhead Crucifix): suffering = defense
- On-equip permanent stat gain with ongoing penalty (Seven Deadly Chains)
- Cash-threshold conditional bonus (Counterfeit Ring)
- Run-wide kill milestones → permanent stat (Pension Ring): every 20 kills
- Room-entry proc vs. IDLE/WANDERING enemies (Specter Creepers, Ring of the Block)
- Consumable doubling on pickup (Dealer's Chain): 30% chance, any consumable
- Item always_visible on equip (Bucket Hat of Knowing): reveals all items on floor

### Existing Systems Reused
- tol_scaling (Tol Hammer — same pattern as Massive Blunt)
- on_hit_bounce dynamic (Chain Whip — Extension Cord pattern but calculated at runtime)
- outgoing_damage_mults (Ring of Comeuppance, Specter Creepers — append/remove 1.5x or 1.3x)
- modify_base_stat() for permanent stat changes (Pension Ring, Seven Deadly Chains)
- entity_died event bus (Pension Ring, Ancestral Beater, Chrome Shorty, Fitted Cap)
- grants_ability: "pry" reuse (Saint's Crowbar)
- add_radiation() hook location (Tinfoil Throne SP proc)
- always_visible flag on Entity (Bucket Hat of Knowing loot reveal)
- FearEffect pattern for room-entry fear → Chill used instead for Ring of the Block

### Next Available Graphical Tiles (as of Batch 4)
- 0xE00F: assigned to stabbing weapons (Prophet's Shank, Widow's Needle) — needs sprite
- 0xE010: assigned to beating weapons (Ancestral Beater, Saint's Crowbar) — needs sprite
- 0xE011+: free for future use
