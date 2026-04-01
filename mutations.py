"""
Radiation mutation system.

Per-tick mutation chance scales with rad level (0.1% per 50 rad).
Three tiers: weak (50+ rad), strong (125+ rad), huge (250+ rad).
67% bad / 33% good polarity.
Mutations are permanent stat/skill/equipment changes.
Rad is consumed on mutation.
"""

import random

from skills import SKILL_NAMES

# --- Constants ---
RAD_THRESHOLDS = {"weak": 75, "strong": 125, "huge": 250}
RAD_COSTS = {"weak": 50, "strong": 125, "huge": 200}
BASE_CHANCE_PER_50 = 0.001  # 0.1% per 50 rad
STAT_NAMES = ["constitution", "strength", "street_smarts", "book_smarts", "tolerance", "swagger"]
BAD_CHANCE = 0.67

_COLOR_GOOD = (80, 255, 80)
_COLOR_BAD = (255, 80, 80)


# --- Helper functions ---

def _apply_all_stats(engine, amount):
    """Modify all 6 stats by amount."""
    for stat in STAT_NAMES:
        engine.player_stats.modify_base_stat(stat, amount)


def _apply_single_stat(engine, stat, amount):
    """Modify one stat by amount."""
    engine.player_stats.modify_base_stat(stat, amount)


def _apply_resistance(engine, res_type, amount):
    """Modify tox_resistance or rad_resistance on PlayerStats."""
    if res_type == "tox":
        engine.player_stats.tox_resistance += amount
    elif res_type == "rad":
        engine.player_stats.rad_resistance += amount


def _apply_skill_points(engine, amount):
    """Modify skill_points (can go negative)."""
    engine.skills.skill_points += amount


def _apply_skill_level(engine, skill_name, amount):
    """Modify a skill's level by amount, clamped to [0, MAX_LEVEL]."""
    skill = engine.skills.get(skill_name)
    engine.skills.set_skill_level(skill_name, skill.level + amount)


def _apply_briskness(engine, amount):
    """Modify permanent briskness."""
    engine.player_stats.briskness += amount


def _apply_dr(engine, amount):
    """Modify permanent damage reduction."""
    engine.player_stats.permanent_dr += amount


def _apply_lose_slot(engine, slot):
    """Clear an equipment slot. Returns description suffix."""
    item = getattr(engine, slot, None)
    if item is None:
        return " ...but nothing happened"
    name = item.name
    setattr(engine, slot, None)
    return f" (lost {name})"


def _apply_lose_5_skills(engine):
    """Pick min(5, eligible) skills with level > 0 and reduce each by 1."""
    eligible = [name for name in SKILL_NAMES if engine.skills.get(name).level > 0]
    chosen = random.sample(eligible, min(5, len(eligible)))
    for name in chosen:
        _apply_skill_level(engine, name, -1)
    return chosen


# --- Stat display names ---
_STAT_DISPLAY = {
    "constitution": "Constitution",
    "strength": "Strength",
    "street_smarts": "Street Smarts",
    "book_smarts": "Book Smarts",
    "tolerance": "Tolerance",
    "swagger": "Swagger",
}


# --- Mutation table builders ---
# Each entry: (description_string, apply_function(engine) -> optional_suffix)

def _build_weak_bad():
    entries = []
    # -1 to all stats
    entries.append(("-1 to all stats", lambda e: _apply_all_stats(e, -1)))
    # -1 to each specific stat
    for stat in STAT_NAMES:
        desc = f"-1 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, -1)))
    # -10% tox resistance
    entries.append(("-10% toxicity resistance", lambda e: _apply_resistance(e, "tox", -10)))
    # -10% rad resistance
    entries.append(("-10% radiation resistance", lambda e: _apply_resistance(e, "rad", -10)))
    # -100 skill points
    entries.append(("-100 skill points", lambda e: _apply_skill_points(e, -100)))
    return entries


def _build_weak_good():
    entries = []
    entries.append(("+1 to all stats", lambda e: _apply_all_stats(e, 1)))
    for stat in STAT_NAMES:
        desc = f"+1 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, 1)))
    entries.append(("+10% toxicity resistance", lambda e: _apply_resistance(e, "tox", 10)))
    entries.append(("+10% radiation resistance", lambda e: _apply_resistance(e, "rad", 10)))
    entries.append(("+100 skill points", lambda e: _apply_skill_points(e, 100)))
    return entries


def _build_strong_bad():
    entries = []
    entries.append(("-1 to all stats", lambda e: _apply_all_stats(e, -1)))
    for stat in STAT_NAMES:
        desc = f"-3 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, -3)))
    for skill in SKILL_NAMES:
        desc = f"-1 {skill} level"
        entries.append((desc, lambda e, sk=skill: _apply_skill_level(e, sk, -1)))
    entries.append(("-200 skill points", lambda e: _apply_skill_points(e, -200)))
    return entries


def _build_strong_good():
    entries = []
    entries.append(("+1 to all stats", lambda e: _apply_all_stats(e, 1)))
    for stat in STAT_NAMES:
        desc = f"+3 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, 3)))
    for skill in SKILL_NAMES:
        desc = f"+1 {skill} level"
        entries.append((desc, lambda e, sk=skill: _apply_skill_level(e, sk, 1)))
    entries.append(("+200 skill points", lambda e: _apply_skill_points(e, 200)))
    entries.append(("+5% briskness", lambda e: _apply_briskness(e, 5)))
    entries.append(("+3 DR", lambda e: _apply_dr(e, 3)))
    return entries


def _build_huge_bad():
    entries = []
    # -1 level to 5 random skills
    def _lose_5(e):
        chosen = _apply_lose_5_skills(e)
        if chosen:
            return f" ({', '.join(chosen)})"
        return " ...but nothing happened"
    entries.append(("-1 level to 5 random skills", _lose_5))
    entries.append(("-2 to all stats", lambda e: _apply_all_stats(e, -2)))
    for stat in STAT_NAMES:
        desc = f"-5 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, -5)))
    entries.append(("lose neck item", lambda e: _apply_lose_slot(e, "neck")))
    entries.append(("lose feet item", lambda e: _apply_lose_slot(e, "feet")))
    entries.append(("lose hat item", lambda e: _apply_lose_slot(e, "hat")))
    return entries


def _build_huge_good():
    entries = []
    for skill in SKILL_NAMES:
        desc = f"+5 {skill} levels"
        entries.append((desc, lambda e, sk=skill: _apply_skill_level(e, sk, 5)))
    entries.append(("+2 to all stats", lambda e: _apply_all_stats(e, 2)))
    for stat in STAT_NAMES:
        desc = f"+5 {_STAT_DISPLAY[stat]}"
        entries.append((desc, lambda e, s=stat: _apply_single_stat(e, s, 5)))
    entries.append(("+5% briskness", lambda e: _apply_briskness(e, 5)))
    entries.append(("+5 DR", lambda e: _apply_dr(e, 5)))
    return entries


# Pre-built tables
MUTATION_TABLES = {
    ("weak", "bad"): _build_weak_bad(),
    ("weak", "good"): _build_weak_good(),
    ("strong", "bad"): _build_strong_bad(),
    ("strong", "good"): _build_strong_good(),
    ("huge", "bad"): _build_huge_bad(),
    ("huge", "good"): _build_huge_good(),
}


# --- Core mutation check ---

def check_mutation(engine):
    """Called once per energy tick. Check if player mutates from radiation."""
    rad = engine.player.radiation
    if rad < min(RAD_THRESHOLDS.values()):
        return
    # Nuclear Research L2 "Rad Bomb": passive mutations blocked below 150 rad
    if engine.skills.get("Nuclear Research").level >= 2 and rad < 150:
        return

    chance = (rad // 50) * BASE_CHANCE_PER_50
    # Yellowcake buff: 10x mutation chance
    has_yellowcake = any(getattr(e, 'id', '') == 'yellowcake_buff'
                         for e in engine.player.status_effects)
    if has_yellowcake:
        chance *= 10
    if random.random() >= chance:
        return

    # Pick tier: collect eligible tiers, pick uniformly
    eligible_tiers = [
        tier for tier, threshold in RAD_THRESHOLDS.items()
        if rad >= threshold
    ]
    # Yellowcake buff: block weak-tier mutations (only strong/huge)
    if has_yellowcake:
        eligible_tiers = [t for t in eligible_tiers if t != "weak"]
        if not eligible_tiers:
            return  # not enough rad for strong/huge — no mutation
    tier = random.choice(eligible_tiers)

    # Pick polarity — modified by good_mutation_base_bonus and good_mutation_multiplier
    base_good = 1.0 - BAD_CHANCE  # 0.33
    base_good += engine.player_stats.good_mutation_base_bonus
    good_chance = min(1.0, base_good * (1.0 + engine.player_stats.good_mutation_multiplier))
    polarity = "good" if random.random() < good_chance else "bad"

    # Pick mutation from table
    table = MUTATION_TABLES[(tier, polarity)]
    desc, apply_fn = random.choice(table)

    # Deduct rad
    engine.player.radiation = max(0, rad - RAD_COSTS[tier])

    # Refresh Force Sensitive buff on mutation
    for eff in engine.player.status_effects:
        if getattr(eff, 'id', '') == 'force_sensitive':
            eff.refresh(engine.player, engine)
            break

    # Apply mutation
    suffix = apply_fn(engine) or ""

    # Mutation skill XP: weak=100, strong=250, huge=500
    _MUTATION_XP = {"weak": 100, "strong": 250, "huge": 500}
    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Mutation", _MUTATION_XP[tier], bksmt)

    # Build message
    color = _COLOR_GOOD if polarity == "good" else _COLOR_BAD
    tier_label = tier.capitalize()
    full_desc = f"You mutate! [{tier_label}] {desc}{suffix}"

    engine.messages.append([(full_desc, color)])

    # Log to mutation_log
    engine.mutation_log.append({
        "tier": tier,
        "polarity": polarity,
        "description": desc,
        "suffix": suffix,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Monster radiation mutation system
# ═══════════════════════════════════════════════════════════════════════════════

MONSTER_RAD_THRESHOLD = 20       # Minimum rad to mutate
MONSTER_RAD_COST = 20            # Rad consumed per mutation
MONSTER_RAD_CHANCE_PER_20 = 0.05 # 5% per 20 rad
MONSTER_BAD_CHANCE = 0.85        # 85% bad, 15% good

# --- Monster mutation table ---
# Each entry: (weight, description, apply_fn)
# apply_fn(monster, engine) -> suffix_str or None

MONSTER_MUTATIONS_BAD = [
    # Direct damage
    (20, "Chemical Burns",
     lambda m, e: _monster_rad_damage(m, e, 0.20)),
    (10, "Meltdown",
     lambda m, e: _monster_rad_damage(m, e, 0.35)),
    # Defense shred
    (20, "Brittle Bones",
     lambda m, e: _monster_mod_stat(m, "defense", -3)),
    (10, "Peeling Skin",
     lambda m, e: _monster_mod_stat(m, "defense", -5)),
    (5,  "Total Exposure",
     lambda m, e: _monster_set_stat(m, "defense", 0)),
    # Speed reduction
    (15, "Jelly Legs",
     lambda m, e: _monster_mod_stat(m, "speed", -20)),
    (8,  "Lead Feet",
     lambda m, e: _monster_mod_stat(m, "speed", -40)),
    # Power reduction
    (15, "Weaker Arms",
     lambda m, e: _monster_mod_stat(m, "power", -2)),
    (8,  "Noodle Arms",
     lambda m, e: _monster_mod_stat(m, "power", -4)),
]

MONSTER_MUTATIONS_GOOD = [
    # Heal
    (30, "Second Wind",
     lambda m, e: _monster_heal(m, 0.25)),
    # Defense boost
    (25, "Thick Skin",
     lambda m, e: _monster_mod_stat(m, "defense", 3)),
    # Power boost
    (25, "Roid Rage",
     lambda m, e: _monster_mod_stat(m, "power", 2)),
    # Speed boost
    (20, "Tweakin'",
     lambda m, e: _monster_mod_stat(m, "speed", 20)),
]


def _monster_rad_damage(monster, engine, fraction):
    """Deal a fraction of monster's max HP as radiation damage."""
    damage = max(1, int(monster.max_hp * fraction))
    monster.take_damage(damage)
    return f" ({damage} damage)"


def _monster_mod_stat(monster, stat, amount):
    """Modify a monster stat, floor at 0 for defense, 1 for power, 10 for speed."""
    floors = {"defense": 0, "power": 1, "speed": 10}
    current = getattr(monster, stat, 0)
    new_val = max(floors.get(stat, 0), current + amount)
    setattr(monster, stat, new_val)
    return f" ({current} → {new_val})"


def _monster_set_stat(monster, stat, value):
    """Set a monster stat to a fixed value."""
    old = getattr(monster, stat, 0)
    setattr(monster, stat, value)
    return f" ({old} → {value})"


def _monster_shrink_hp(monster, fraction):
    """Reduce monster's max HP by a fraction. Current HP clamped to new max."""
    lost = max(1, int(monster.max_hp * fraction))
    monster.max_hp = max(1, monster.max_hp - lost)
    if monster.hp > monster.max_hp:
        monster.hp = monster.max_hp
    return f" (-{lost} max HP)"


def _monster_heal(monster, fraction):
    """Heal a monster by a fraction of its max HP."""
    amount = max(1, int(monster.max_hp * fraction))
    old_hp = monster.hp
    monster.hp = min(monster.hp + amount, monster.max_hp)
    healed = monster.hp - old_hp
    return f" (+{healed} HP)" if healed > 0 else " (already full)"


def _pick_weighted(table):
    """Pick a random entry from a weighted table. Returns (desc, apply_fn)."""
    total = sum(w for w, _, _ in table)
    roll = random.random() * total
    cumulative = 0
    for weight, desc, fn in table:
        cumulative += weight
        if roll < cumulative:
            return desc, fn
    return table[-1][1], table[-1][2]


def check_monster_mutation(engine, monster):
    """Called once per energy tick for each living monster with radiation.

    At 25+ rad: 5% chance per 25 rad. Costs 25 rad per mutation.
    85% bad / 15% good.
    """
    rad = getattr(monster, 'radiation', 0)
    if rad < MONSTER_RAD_THRESHOLD:
        return

    chance = (rad // MONSTER_RAD_THRESHOLD) * MONSTER_RAD_CHANCE_PER_20
    chance = min(chance, 0.50)  # Cap at 50%
    if random.random() >= chance:
        return

    # Consume radiation
    monster.radiation = max(0, rad - MONSTER_RAD_COST)

    # Pick polarity
    polarity = "bad" if random.random() < MONSTER_BAD_CHANCE else "good"
    table = MONSTER_MUTATIONS_BAD if polarity == "bad" else MONSTER_MUTATIONS_GOOD
    desc, apply_fn = _pick_weighted(table)

    suffix = apply_fn(monster, engine) or ""

    # Message
    color = _COLOR_BAD if polarity == "bad" else _COLOR_GOOD
    engine.messages.append([
        (f"{monster.name} mutates: ", color),
        (f"{desc}!{suffix}", color),
    ])

    # Kill check — radiation damage mutations can kill
    if not monster.alive:
        engine.messages.append(f"The {monster.name} dies from radiation mutation!")
        engine.event_bus.emit("entity_died", entity=monster, killer=engine.player)


def force_monster_mutation(engine, monster):
    """Force a single mutation on a monster (guaranteed, no chance roll).
    Consumes MONSTER_RAD_COST radiation. Returns True if the monster died."""
    monster.radiation = max(0, getattr(monster, 'radiation', 0) - MONSTER_RAD_COST)

    polarity = "bad" if random.random() < MONSTER_BAD_CHANCE else "good"
    table = MONSTER_MUTATIONS_BAD if polarity == "bad" else MONSTER_MUTATIONS_GOOD
    desc, apply_fn = _pick_weighted(table)
    suffix = apply_fn(monster, engine) or ""

    color = _COLOR_BAD if polarity == "bad" else _COLOR_GOOD
    engine.messages.append([
        (f"{monster.name} mutates: ", color),
        (f"{desc}!{suffix}", color),
    ])

    if not monster.alive:
        engine.messages.append(f"The {monster.name} dies from forced mutation!")
        engine.event_bus.emit("entity_died", entity=monster, killer=engine.player)
        return True
    return False


def force_mutation(engine):
    """Force a single mutation. Picks tier based on current rad (weak if < 50).
    Uses normal polarity odds. Does NOT consume radiation."""
    rad = engine.player.radiation

    eligible_tiers = [
        tier for tier, threshold in RAD_THRESHOLDS.items()
        if rad >= threshold
    ]
    tier = random.choice(eligible_tiers) if eligible_tiers else "weak"

    base_good = 1.0 - BAD_CHANCE
    base_good += engine.player_stats.good_mutation_base_bonus
    good_chance = min(1.0, base_good * (1.0 + engine.player_stats.good_mutation_multiplier))
    polarity = "good" if random.random() < good_chance else "bad"

    table = MUTATION_TABLES[(tier, polarity)]
    desc, apply_fn = random.choice(table)

    for eff in engine.player.status_effects:
        if getattr(eff, 'id', '') == 'force_sensitive':
            eff.refresh(engine.player, engine)
            break

    suffix = apply_fn(engine) or ""

    bksmt = engine.player_stats.effective_book_smarts
    engine.skills.gain_potential_exp("Mutation", {"weak": 100, "strong": 250, "huge": 500}[tier], bksmt)

    color = _COLOR_GOOD if polarity == "good" else _COLOR_BAD
    tier_label = tier.capitalize()
    full_desc = f"You mutate! [{tier_label}] {desc}{suffix}"
    engine.messages.append([(full_desc, color)])

    # Log to mutation_log
    engine.mutation_log.append({
        "tier": tier,
        "polarity": polarity,
        "description": desc,
        "suffix": suffix,
    })
