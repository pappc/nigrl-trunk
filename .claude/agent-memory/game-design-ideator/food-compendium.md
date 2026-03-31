---
name: Food Compendium Design Notes
description: Balance anchors, effect types, and design patterns for the 50-food compendium
type: project
---

## Food Compendium (2026-03-25)

Design doc: `nigrl-ideas/item-food-compendium.txt`
50 foods: 25 Crack Den (items 1-25), 25 Meth Lab (items 26-50).

## New Effect Types Introduced

All require new Effect subclasses in effects.py + food handler dispatch in item_effects.py:

  flat_damage_buff   — entity.power += N on apply; -N on expire. Modeled on WellFedEffect.
  overshield         — entity.max_hp += N; expire clamps entity.hp to new max.
  dodge_buff         — player_stats.add_dodge_chance(N); reverse on expire.
  lifesteal_melee    — configurable-percent on_player_melee_hit; heal = floor(dmg * pct).
                       Extend existing LifestealEffect to accept a `percent` param.
  thorns             — modify_incoming_damage: deal self.amount to attacker; no damage reduction.
                       Needs attacker entity in hook context.
  xp_mult            — player_stats.xp_mult float; all XP gains multiply by it.
                       Best stored as a list of active multipliers (product).
  cash_on_kill       — event_bus listener on entity_died; add cash if killer == player.
  stealth_shroud     — patch all enemy sight_radius by -N on apply; restore dict on expire.
  fear_aura          — before_turn hook on player: apply Fear to enemies within radius.
  fov_expand         — engine.fov_radius += N; recalculate FOV. Reverse on expire.
  debuff_immunity    — block category=="debuff" in apply_effect(). May be ZonedOutEffect clone.
  debuff_cleanse     — one-shot strip all category=="debuff" effects. Not a persistent Effect.
  one_of_random      — food handler picks randomly from options dict at eat time.

## Food Balance Anchors (confirmed from codebase)

  Eat times: 1 (stale chips, pack of crackers) to 8 (The Last Supper). Chicken=10 is longest.
  Crack Den values: $15-35. Meth Lab: $30-75.
  Crack Den heals: 8-50 HP immediate. Meth Lab: 15-100 HP.
  Duration range: 8-40 turns (Crack Den), 15-40 turns (Meth Lab).
  Power boost: flat_damage_buff — typical 2-6 Crack Den, 4-10 Meth Lab.
  Dodge cap: 90%. Start: 0%. Each food grants 10-20%.
  Lifesteal percent: 25-50% depending on zone and food rarity.
  Overshield HP: 15-50 extra max HP. Clamps on expire — unused is lost.
  Thorns flat: 3-4 per hit Crack Den. Not a % — strictly flat.

## Key Design Rules for Food

- Thorns do NOT reduce incoming damage (they're punishing, not defensive).
- Overshield clamping on expire is intentional — creates real tradeoff vs. just healing.
- Debuff cleanse (Honeybun, Menudo) removes ALL debuffs at once — very powerful situationally.
- No food grants permanent stat changes (Protein Powder's exclusive niche — don't step on it).
- XP mult foods (Oatmeal Cookies, Trail Mix, Soylent Green) have NO combat benefit.
- Fear aura (Durian Fruit, Fear Pheromone Taco) fires on player's turn via before_turn hook.
- Lifesteal heals are capped at missing HP — no overheal past max_hp.
- Rad/tox cost foods (Gray Market Shake, Radioactive Gummies, etc.) are intentional for builds
  that use radiation as a resource (mutation builds, Skywalker OG/Kushenheimer strain synergy).
- The Last Supper (8-turn eat) is intended as a planning puzzle — use only in cleared rooms.
- Mystery Meat Stew (one_of_random) has 4 outcomes ranging from great to costly.

## Notable Synergies

- Ghost Pepper Jerky: hot_cheetos effect (existing) + thorns — "burning porcupine" combo.
- Durian Fruit: stealth_shroud + fear_aura — enemies flee from things they can barely see.
- Fear Pheromone Taco: bigger version of Durian Fruit — r=5 vs r=3 aura, otherwise similar.
- Prison Wine + Wasabi Peas: berserk + crit combo. High risk, max DPS output.
- Tide Pod: tox gain as resource for Nigle Fart / Iron Lung builds. "Downside" is a benefit.
- Synthetic Muscle Paste: all three melee buffs (power + overshield + lifesteal) at once.
