---
name: Meth Lab Weapon Designs
description: Balance anchors, new fields, and new effects from Zone 2 weapon design docs
type: project
---

## Meth Lab Stabbing Weapons (2026-03-13)

Full design: `nigrl-ideas/meth-lab-stab-weapons.txt`
8 weapons. Damage range 5-11 base, STR req 2-8, reach 1-3.

Summary:
  Scalpel           — 5dmg STR2 r1, dual-scaling (STR+STSMT), corrode 25%, +2 Stab XP/hit
  Shiv (Glass)      — 7dmg STR3 r1, glass_shards DoT, break 12%, final-hit 1.5x bonus
  Syringe Lance     — 6dmg STR4 r2, injects +30 tox (→+50 at player tox>=200), poisoned 20%, +1 Stab XP
  Tuning Fork Shiv  — 8dmg STR5 r1, 30% silence 4t, silence extends 20% on subsequent hits
  Ritualist's Athame— 9dmg STR5 r1, BKS-scaling (threshold 5), 15% doom 10t, Negromancy XP on doom-kill
  Rebar Spike       — 10dmg STR7 r3, pure STR tiered/1, no on-hit, only reach-3 stab weapon
  Petrification Needle— 7dmg STR6 r1, 15% petrify 3t (30% vs irradiated), double dmg taken while petrified
  Charm Bolt        — 11dmg STR8 r1, SWG-scaling threshold 6, 10% charm 8t, charm resets on kill

**New item fields needed:**
  on_hit_corrode_chance: float — probabilistic perm defense reduction (unlike on_hit_sunder guaranteed)
  final_hit_bonus: float       — multiplier on the hit that triggers break_chance
  on_hit_tox_inject: dict      — {"base": int, "tox_threshold": int, "bonus": int}
  silence_extend_on_hit: dict  — {"requires": str, "chance": float, "extension": int}
  on_kill_doomed_xp: dict      — {"skill": str, "amount": int}; checks doom active with duration>0
  irrad_bonus_chance: float    — adds to proc chance if target irradiated or tox>=100
  charm_reset_on_kill: bool    — sets charm duration back to 8 when charmed entity gets a kill

**New effects needed:**
  corrode         — one-shot apply(), reduces target.defense by amount permanently (no timer)
  silence         — duration=4, blocks SpecialAttack firing in do_ai_turn(); on_reapply no-op
  doom            — duration=10, expire() kills entity; on_reapply no-op; cleanse_immune=True
  poisoned        — duration=5, 2 dmg/tick, bypasses armor (like bleeding but poison flavor)
  petrify         — duration=3, skips turn + doubles incoming damage; expire() applies petrify_immune
  petrify_immune  — duration=3, passive; blocks new petrify application
  charm           — duration=8, flips entity AI to hunt allies; on_reapply releases old charm

**Balance anchors established:**
  - Stab weapon damage ceiling Zone 2: 11 base (Charm Bolt), peak ~15 with scaling
  - Stab weapon damage ceiling Zone 1: 10 base (Sharp Pole), peak ~15 with STR
  - Reach-3 exists only on Rebar Spike (stab); no Zone 1 stab had reach 3
  - Dual-scaling (two independent scaling sources summed) introduced on Scalpel
  - Charm proc rate 10% is floor for the most powerful CC in the game
  - Silence proc 30% is intentionally higher than stun (10-20%) since silence is weaker CC
  - Doom proc 15% is low; doom is a win-condition not a reliable opener

**Dual scaling note:** Scalpel has both str_scaling and stat_scaling present simultaneously.
  Engine must sum both contributions independently. No prior weapon does this — new engine
  handling required in damage resolution.
