"""
Skill definitions and progression system.

Levels: 0 - 10
XP thresholds per level (DEFAULT_EXP_CURVE):
  0 ->  1:    200
  1 ->  2:    400
  2 ->  3:    600
  3 ->  4:    800
  4 ->  5:  2,000
  5 ->  6:  6,000
  6 ->  7: 15,000
  7 ->  8: 25,000
  8 ->  9: 100,000
  9 -> 10: 500,000
  Total to max: 649,000

Potential exp is earned passively by doing actions.
Real exp is earned by spending skill_points to convert potential -> real.
Skill_points are gained as a fraction of potential_exp (scaled by book_smarts).
"""

SKILL_NAMES = [
    "Smoking",
    "Rolling",
    "Pyromania",
    "Blackkk Magic",
    "Smartsness",
    "Stabbing",
    "Beating",
    "Smacking",
    "Slashing",
    "Stealing",
    "Jaywalking",
    "Deep-Frying",
    "Drinking",
    "Alcoholism",
    "Munching",
    "Dismantling",
    "Abandoning",
    "Meth-Head",
    "Chemical Warfare",
    "White Power",
    "Mutation",
    "Nuclear Research",
    "Decontamination",
    "Gunplay",
    "Drive-By",
    "Ammo Rat",
    "L Farming",
    "Arachnigga",
    "Graffiti",
    "Infected",
    "Cryomancy",
    "Electrodynamics",
    "Elementalist",
]

DEFAULT_EXP_CURVE = [200, 400, 600, 800, 2000, 6000, 15000, 25000, 100000, 500000]
MAX_LEVEL = 10

# Placeholder perk data for all 17 skills × 10 levels.
# Each entry: {"name": str, "perk_type": str, "effect": dict | None}
# perk_type: "none" (placeholder), "stat", "passive", "activated"
_PLACEHOLDER = {"name": "Placeholder", "perk_type": "none", "effect": None}

SKILL_PERKS: dict[str, list[dict]] = {
    skill_name: [_PLACEHOLDER] * 10
    for skill_name in [
        "Smoking", "Rolling", "Pyromania", "Blackkk Magic",
        "Smartsness", "Stabbing", "Beating", "Smacking", "Slashing", "Stealing", "Jaywalking",
        "Deep-Frying", "Drinking", "Alcoholism", "Munching", "Dismantling",
        "Abandoning", "Meth-Head", "Chemical Warfare", "White Power",
        "Mutation", "Nuclear Research", "Decontamination", "Gunplay",
        "Drive-By",
        "Ammo Rat",
        "L Farming",
        "Arachnigga",
        "Graffiti",
        "Infected",
        "Cryomancy",
        "Electrodynamics",
        "Elementalist",
    ]
}

SKILL_PERKS["White Power"] = [
    {"name": "Reject the Poison", "perk_type": "passive", "effect": None, "desc": "+20% toxicity resistance. Toxicity resisted builds Purity stacks (max 50, 20t, refreshes). When Purity expires: heal for stacks, overflow as temp HP (cap 50)."},  # level 1
    {"name": "Bastion", "perk_type": "activated", "effect": {"ability": "bastion", "swagger": 2}, "desc": "+2 Swagger. Toggle (5/floor): ON costs 1 charge + 10 tox. OFF is free. While ON: -25% damage taken, -20% damage dealt."},  # level 2
    {"name": "Pure",  "perk_type": "stat", "effect": {"swagger": 4}, "desc": "+4 Swagger, +20% toxicity resistance. Double XP from toxicity resisted."},  # level 3
    {"name": "Whitewash", "perk_type": "activated", "effect": {"ability": "whitewash", "constitution": 4}, "desc": "+4 CON. 1/floor: consume half your toxicity. Heals first, overflow as temp HP."},  # level 4
    {"name": "Absolution", "perk_type": "activated", "effect": {"ability": "absolution"}, "desc": "3/floor. 15 turns: gain 5 tox/turn. All toxicity you lose deals that amount as damage to 2 random enemies within 4 tiles."},  # level 5
    {"name": "Immaculate", "perk_type": "passive", "effect": {"swagger": 2}, "desc": "+2 Swagger. Purity stack cap → 100, temp HP cap → 100. Purity stacks accumulate 2x faster while Bastion is active. Taking a melee hit while Bastion is active grants 3 Purity stacks."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 7-10
]

SKILL_PERKS["Mutation"] = [
    {"name": "Scarred Tissue", "perk_type": "passive", "effect": None, "desc": "Bad mutations also grant +1 to a random stat permanently. Your body adapts to the damage."},  # level 1
    {"name": "Unstable", "perk_type": "passive", "effect": None, "desc": "20% on melee hit: gain Unstable buff (20t). +5 rad on apply, +2 melee and gun dmg, hits irradiate enemies for 10 rad."},  # level 2
    {"name": "Favorable Odds", "perk_type": "passive", "effect": None, "desc": "+50% good mutation multiplier. Mutations are more likely to be positive."},  # level 3
    {"name": "Shed", "perk_type": "activated", "effect": {"ability": "shed"}, "desc": "Grants Shed ability (unlimited). Sacrifice a random good mutation, undoing it. Cleanses a debuff. Refunds half the tier's rad threshold."},  # level 4
    {"name": "Triple Helix", "perk_type": "passive", "effect": None, "desc": "30% chance when you mutate to fire a bonus mutation. Same tier, rerolls polarity and effect. No extra rad cost."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]

SKILL_PERKS["Nuclear Research"] = [
    {"name": "Irradiated Intellect", "perk_type": "stat", "effect": {"book_smarts": 3}, "desc": "+3 Book Smarts. Radiation gained increased by Book Smarts% of amount gained."},  # level 1
    {"name": "Rad Bomb", "perk_type": "activated", "effect": {"ability": "rad_bomb"}, "desc": "Place a crystal within 2 tiles that detonates after 3 turns, dealing 15+BKS/2 damage in a 5x5 area. 3 charges/floor. Each cast costs 25 radiation and grants 50 Nuclear Research XP. At 100+ rad, the charge is refunded (rad still spent). Passive: can't mutate below 150 rad."},  # level 2
    {"name": "Nutrient Producer", "perk_type": "grant_item", "effect": {"item_id": "nutrient_producer"}, "desc": "Gain a Nutrient Producer tool. Combine it with any consumable to convert it into a RadBar."},  # level 3
    {"name": "Half-Life Mark", "perk_type": "activated", "effect": {"ability": "half_life_mark"}, "desc": "Mark a visible enemy (costs 20 rad). When it drops below 40% HP, it detonates for 15+BKS damage in a 3x3 area and irradiates hit enemies for 30 rad. 2 charges/floor. At 200+ radiation, the charge is not consumed. Passive: can't mutate below 250 rad."},  # level 4
    {"name": "Enrichment", "perk_type": "activated", "effect": {"ability": "enrichment"}, "desc": "Spend 25 rad to gain an Enrichment stack (max 5). Your next Rad Bomb or Half-Life detonation consumes all stacks: +4 damage per stack, +1 blast radius per 2 stacks. Rad Bomb hitting a Half-Life Marked enemy transfers stacks to the mark. Passive: Rad Bomb placement range +3 (to 5), fuse +1 turn (to 4)."},  # level 5
    {"name": "Nuclear Feedback", "perk_type": "passive", "effect": None, "desc": "Each enemy hit by a Rad Bomb or Half-Life detonation grants you +10 radiation (pierces resistance). Passive: can't mutate below 400 rad."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 7-10
]

SKILL_PERKS["Deep-Frying"] = [
    {"name": "Fry Shot",     "perk_type": "activated", "effect": {"ability": "fry_shot"},    "desc": "Hurl a ball of scorching hot oil that deals burn damage in a small area. Damage dealt = Deep-Frying XP."},   # level 1
    {"name": "Extra Greasy", "perk_type": "passive",   "effect": None,                       "desc": "Your fried food items restore +20% HP when eaten."},                         # level 2
    {"name": "Oil Dump",     "perk_type": "activated", "effect": {"ability": "oil_dump"},    "desc": "3/floor. Dump oil in radius-3 circle. Enemies get 3 Greasy stacks. Floor becomes grease (25t). Enemies on grease take CON/3 + DeepFrying/2 dmg/turn. Player capped at 3 Greasy stacks from grease tiles."},   # level 3
    {"name": "Hot Pot", "perk_type": "passive", "effect": {"tolerance": 2}, "desc": "+2 TOL. Eating food: 50% chance to gain a Hot Pot charge (no cap, no expiry). Melee hits consume 1 charge to splash boiling oil: CON + DeepFrying*2 damage to all adjacent enemies, applies 2 Greasy stacks each."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                # levels 5-10
]

SKILL_PERKS["Dismantling"] = [
    {"name": "Scrapper's Eye",    "perk_type": "stat",    "effect": {"constitution": 2}, "desc": "+2 CON. Destroying items heals 10% of item value (min 3 HP)."},  # level 1
    {"name": "Chop Shop",   "perk_type": "passive", "effect": None,                                  "desc": "+2 SWG, +2 STS. Destroying an item grants +5 armor and +$20 cash. 20% chance to gain Scrap."},      # level 2
    {"name": "Nigga Armor", "perk_type": "passive", "effect": None,                                  "desc": "+2 SWG, +2 STS. Gain a stack of Nigga Armor on destroy (-1 DR, 30t)."},    # level 3
    {"name": "Salvage Insight", "perk_type": "stat", "effect": {"constitution": 2}, "desc": "+2 CON. 10% chance on destroy to gain +1 to a random stat permanently."},  # level 4
    {"name": "Scrap Turret", "perk_type": "activated", "effect": {"ability": "scrap_turret"}, "desc": "Grants Scrap Turret (0 charges, max 1). Destroying an item loads 1 charge. Place on adjacent tile. Duration: last item value/5 turns. Dmg: Dismantling lvl×3. HP: Dismantling lvl×5. Range 3. Max 1 turret."},  # level 5
    {"name": "Salvage Volley", "perk_type": "passive", "effect": None, "desc": "Destroying an item while turret is alive fires 3 rapid shots at nearest enemy. Turret kills drop Scrap (value 25, destroyable, triggers all Dismantling perks)."},  # level 6
    _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 7-10
]

SKILL_PERKS["Abandoning"] = [
    {"name": "+1 All Stats", "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 to all stats. Leaving things behind builds character."},  # level 1
    {"name": "Anotha Motha", "perk_type": "passive", "effect": None, "desc": "Receive 5 extra item drops when descending to the next floor."},                                                                                           # level 2
    {"name": "Left Behind",  "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 all stats. On descend, gain +1 DR per item left on the floor (lasts until next floor)."},  # level 3
    {"name": "Milk From The Store", "perk_type": "activated", "effect": {"ability": "milk_from_the_store"}, "desc": "+1 all stats. Activate to double all stats for 10 turns. 3 charges/floor."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                          # levels 5-10
]

SKILL_PERKS["Smoking"] = [
    {"name": "+3 TOL, +3 CON",    "perk_type": "stat",    "effect": {"tolerance": 3, "constitution": 3},     "desc": "+3 Tolerance, +3 Constitution. Your body adapts to the abuse."},              # level 1
    {"name": "Phat Cloud",        "perk_type": "passive",  "effect": None,                                    "desc": "Smoking blows a phat cloud at the nearest enemy, dealing damage based on Tolerance."},  # level 2
    {"name": "Stress Smoke",      "perk_type": "passive",  "effect": None,                                    "desc": "10% chance when hit to auto-smoke a random joint. The joint is not consumed."},  # level 3
    {"name": "Roach Fiend",       "perk_type": "passive",  "effect": None,                                    "desc": "30% chance a joint is not consumed when smoked."},                            # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 5-10
]

SKILL_PERKS["Pyromania"] = [
    {"name": "Ignite",        "perk_type": "activated", "effect": {"ability": "ignite_spell", "constitution": 2}, "desc": "+2 Constitution. Targeted ignite spell — set a visible enemy ablaze from a distance."},  # level 1
    {"name": "Fire!",         "perk_type": "activated", "effect": {"ability": "place_fire"},   "desc": "Spawn a line of 3 fire tiles in a cardinal direction (10 turns). 3/floor."},             # level 2
    {"name": "Neva Burn Out", "perk_type": "activated", "effect": {"ability": "place_fire_permanent"}, "desc": "Immune to fire tile and ignite damage. Grants ability to place a permanent fire tile. 3/floor."},  # level 3
    {"name": "+3 CON",       "perk_type": "stat",      "effect": {"constitution": 3},          "desc": "+3 Constitution. Ignite you apply lasts 5 turns longer."},                              # level 4
    {"name": "Wildfire",      "perk_type": "passive",   "effect": None,                        "desc": "Ignited enemies have a 20% chance per turn to spread fire to adjacent enemies with fewer stacks."},  # level 5
    {"name": "Fireball",     "perk_type": "activated", "effect": {"ability": "fireball"},      "desc": "Hurl an explosive fireball (2-tile radius AOE). 15 + BKS dmg, applies 3 ignite. 1/floor. +1 charge on killing an enemy with 5+ ignite stacks."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                    # levels 7-10
]

SKILL_PERKS["Blackkk Magic"] = [
    {"name": "Curse of Ham",    "perk_type": "activated", "effect": {"ability": "curse_of_ham"},    "desc": "Curse enemies in a cone (range 3, 60°). Cursed monsters attack slower and deal 50% less damage. 3/floor."},  # level 1
    {"name": "Curse of DOT",    "perk_type": "activated", "effect": {"ability": "curse_of_dot"},    "desc": "Curse a single enemy. Each turn gains a stack and deals 1-5 damage, hitting harder at high stacks. Spreads on death. 3/floor."},  # level 2
    {"name": "Curse of COVID",  "perk_type": "activated", "effect": {"ability": "curse_of_covid"},  "desc": "Curse a single enemy. Each turn applies 20 rad or tox (capped 150). 50% to stack, 25% to spread. 3/floor."},  # level 3
    {"name": "Dark Covenant",   "perk_type": "passive",   "effect": None,                           "desc": "All curses gain +3 charges per floor (6 total). Cursed enemies have a 25% chance to drop a Voodoo Doll on death."},  # level 4
    _PLACEHOLDER,                                                                                    # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                          # levels 6-10
]

SKILL_PERKS["Rolling"] = [
    {"name": "+2 SWG, +2 TOL",       "perk_type": "stat",    "effect": {"swagger": 2, "tolerance": 2}, "desc": "+2 Swagger, +2 Tolerance. Rolling builds swagger and resistance."},  # level 1
    {"name": "Spectral Paper", "perk_type": "stat",    "effect": {"tolerance": 2},                "desc": "+2 Tolerance. Gain a Spectral Paper — a reusable rolling paper that is never consumed."},  # level 2
    {"name": "Seeing Double",  "perk_type": "passive", "effect": None,                             "desc": "50% chance to roll an extra blunt when you roll one up."},           # level 3
    {"name": "Snickelfritz",  "perk_type": "passive", "effect": None,                             "desc": "25% chance to gain a bonus Snickelfritz joint when rolling. Grenade strain — best thrown at enemies."},  # level 4
    {"name": "Rollin' Cloud", "perk_type": "passive", "effect": None,                             "desc": "Rolling a joint triggers Phat Cloud, hitting the nearest visible enemy."},              # level 5
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                      # levels 6-10
]

SKILL_PERKS["Alcoholism"] = [
    {"name": "Throw Bottle",    "perk_type": "activated", "effect": {"ability": "throw_bottle"},    "desc": "Hurl a bottle at an enemy for damage with a chance to stun them."},            # level 1
    {"name": "+4 TOL",        "perk_type": "stat",      "effect": {"tolerance": 4},               "desc": "+4 Tolerance. Your liver is basically pickled at this point."},                 # level 2
    {"name": "Stash Finder",  "perk_type": "passive",   "effect": None,                           "desc": "15% chance when entering a new room to find a random bottle in your inventory."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                       # levels 4-10
]

SKILL_PERKS["Drinking"] = [
    {"name": "Liquid Bandage",  "perk_type": "passive",   "effect": None,                             "desc": "Any drink heals +10% of your max HP on use, in addition to normal effects."},      # level 1
    {"name": "One More Sip",    "perk_type": "passive",   "effect": None,                             "desc": "20% chance a drink item is not consumed when used."},                              # level 2
    {"name": "Hair of the Dog", "perk_type": "passive", "effect": {"tolerance": 2}, "desc": "+2 TOL. When a drink buff expires naturally, 30% chance to fully reapply it (same effects, full duration). Does not trigger hangover."},  # level 3
    {"name": "Liquid Courage", "perk_type": "passive", "effect": {"constitution": 2, "tolerance": 1}, "desc": "+2 CON, +1 TOL. While any drink buff is active, deal 10% more melee damage. Each active drink stack adds +3% crit chance."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 5-10
]

SKILL_PERKS["Beating"] = [
    {"name": "+3 STR",  "perk_type": "stat",      "effect": {"strength": 3},         "desc": "+3 Strength. Beating people up makes you stronger. Simple as that."},    # level 1
    {"name": "Bash",      "perk_type": "activated",  "effect": {"ability": "bash"},    "desc": "Bash an adjacent enemy with full force, stunning them for 1 turn."},       # level 2
    {"name": "Crit+",     "perk_type": "passive",    "effect": None,                   "desc": "+1 crit damage multiplier on all melee attacks."},                # level 3
    {"name": "Aftershock", "perk_type": "passive", "effect": {"strength": 2}, "desc": "+2 STR. Landing a critical hit with a blunt weapon grants Aftershock (15t): next 3 attacks deal +Beating level×2 bonus damage and have 30% chance to stun (1 turn)."},  # level 4
    {"name": "Overkill", "perk_type": "passive", "effect": {"strength": 2}, "desc": "+2 STR. Killing an enemy with a blunt weapon splashes excess damage to all enemies within radius 2. If the splash kills, it chains. No chain limit."},  # level 5
    {"name": "Colossus", "perk_type": "activated", "effect": {"ability": "colossus", "strength": 3, "constitution": 3}, "desc": "+3 STR, +3 CON. Toggle between two stances (free action, 5t cooldown). Wrecking: +40% melee damage, can't dodge, -2 DR. Fortress: +4 DR, 30% counter-attack for STR damage + 1t stun, -25% melee damage."},  # level 6
    _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                          # levels 7-10
]

SKILL_PERKS["Stabbing"] = [
    {"name": "Gouge",     "perk_type": "activated", "effect": {"ability": "gouge"},        "desc": "Gouge an adjacent enemy. Dmg: Street-Smarts. Stuns 5 turns (breaks if you attack the target). 12-turn cooldown."},   # level 1
    {"name": "+2 STS",  "perk_type": "stat",      "effect": {"street_smarts": 2},        "desc": "+2 Street Smarts. You learn to read people by poking holes in them."},        # level 2
    {"name": "Windfury",  "perk_type": "passive",   "effect": None,                        "desc": "min(30, STS)% chance for an extra hit on stab attacks."},                # level 3
    {"name": "+4 STS, +4 STR", "perk_type": "stat", "effect": {"street_smarts": 4, "strength": 4}, "desc": "+4 Street Smarts, +4 Strength. The blade becomes an extension of your body."},  # level 4
    {"name": "Lunge",    "perk_type": "passive",   "effect": None,                        "desc": "Moving into a tile with an enemy directly ahead auto-crits them for free."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                              # levels 6-10
]

SKILL_PERKS["Slashing"] = [
    {"name": "Swashbuckling", "perk_type": "passive", "effect": None, "desc": "20% on slash hit: gain Swashbuckling (+1 slash dmg, +1% dodge). 20 turns, stacks infinitely, reapply refreshes duration."},  # level 1
    {"name": "Whirlwind", "perk_type": "activated", "effect": {"ability": "whirlwind"}, "desc": "Full melee attack on all adjacent enemies. Procs on-hit effects. 22-turn cooldown. Requires slashing weapon."},  # level 2
    {"name": "Execute", "perk_type": "passive", "effect": None, "desc": "Enemies below 25% HP take 2x damage from all sources. Multiplicative with toxicity and shocked."},  # level 3
    {"name": "Blade Dancer", "perk_type": "stat", "effect": {"street_smarts": 3, "strength": 3}, "desc": "+3 Street Smarts, +3 Strength. +15% dodge chance while wielding a slashing weapon."},  # level 4
    {"name": "Crippling Strikes", "perk_type": "stat", "effect": {"strength": 2}, "desc": "+2 Strength. 50% on slash hit: apply Hamstrung (-2 flat dmg per stack, stacks infinitely). Reduces melee and ranged damage."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]

SKILL_PERKS["Smartsness"] = [
    {"name": "Forbidden Knowledge", "perk_type": "stat", "effect": {"book_smarts": 3}, "desc": "+3 Book Smarts."},  # level 1
    {"name": "Spell Retention",    "perk_type": "passive",   "effect": {"book_smarts": 1},           "desc": "+1 BKS. 15% chance when casting a spell to not consume the charge."},     # level 2
    {"name": "Arcane Intelligence", "perk_type": "passive",   "effect": None,                         "desc": "On Smartsness XP gain: 25% chance to gain +2 Arcane Intelligence stacks (+1 spell damage per stack, 20 turns)."},  # level 3
    {"name": "Spell Echo",          "perk_type": "passive",   "effect": {"book_smarts": 1},           "desc": "+1 BKS. 15% chance on spell cast: spell fires again at same target for 50% damage, no charge consumed. Echo can chain. Retargets if target dies. Not channeled spells."},  # level 4
    {"name": "Spellweaver",         "perk_type": "passive",   "effect": {"book_smarts": 3},           "desc": "+3 BKS. Casting a different spell than your last within 5 turns deals +30% damage. Chain indefinitely by alternating spells."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 6-10
]

SKILL_PERKS["Smacking"] = [
    {"name": "Bitch Slap",  "perk_type": "activated", "effect": {"ability": "black_eye_slap"},         "desc": "Slap an adjacent enemy. Dmg: STR (vs females: 10 + 2×STR). 25-turn cooldown."},  # level 1
    {"name": "+3 STR, +3 CON",    "perk_type": "stat",       "effect": {"strength": 3, "constitution": 3},   "desc": "+3 Strength, +3 Constitution. Slapping builds muscle."},                                        # level 2
    {"name": "Black Eye",   "perk_type": "passive",    "effect": None,                                  "desc": "Unarmed attacks have a 10% chance to cause Black Eye: stun 2 turns, then 10 turns of dazed wandering."},  # level 3
    {"name": "Victory Rush", "perk_type": "activated", "effect": {"ability": "victory_rush"},            "desc": "Gain 1 charge. On kill: +1 charge (max 1). Activate: next melee rolls crit twice (advantage) and heals 25% of damage dealt. 20t, no energy cost."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                           # levels 5-10
]

SKILL_PERKS["Munching"] = [
    {"name": "Fast Food",    "perk_type": "activated", "effect": {"constitution": 2, "ability": "quick_eat"}, "desc": "+2 Constitution. Grants Quick Eat: instantly eat your next food. 1 use per floor."},  # level 1
    {"name": "+2 CON",  "perk_type": "stat",    "effect": {"constitution": 2}, "desc": "+2 Constitution. You're a unit. No cap."},                     # level 2
    {"name": "Better Later", "perk_type": "passive", "effect": None,               "desc": "Food effects last 50% longer before wearing off."},            # level 3
    {"name": "Double Batch", "perk_type": "passive",   "effect": None,             "desc": "20% chance a food item is not consumed when you eat it."},     # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                      # levels 5-10
]

SKILL_PERKS["Jaywalking"] = [
    {"name": "Air Jordans",   "perk_type": "passive",   "effect": None,                    "desc": "Movement costs -10 energy. You move like you own these streets."},     # level 1
    {"name": "Dash",          "perk_type": "activated", "effect": {"ability": "dash"},     "desc": "Dash in a direction, instantly moving 3 tiles. Great for escaping."},  # level 2
    {"name": "Airer Jordans", "perk_type": "passive",   "effect": None,                    "desc": "+10 Speed. Even fresher kicks. Even faster feet."},                    # level 3
    {"name": "Shortcut", "perk_type": "activated", "effect": {"ability": "shortcut"}, "desc": "2/floor. Target an explored tile to recall there. Channels for 2 turns (moving cancels). Teleports to the target room's center."},  # level 4
    {"name": "Loitering", "perk_type": "passive", "effect": None, "desc": "Stand still for 3 consecutive turns (no move/attack/ability). Become untargetable for 1 turn and all chasing enemies reset to IDLE."},  # level 5
    {"name": "Momentum", "perk_type": "passive", "effect": None, "desc": "40% chance on melee hit to gain a Momentum stack. Each stack makes your next movement free (0 energy). Stacks consumed one at a time."},  # level 6
    _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                               # levels 7-10
]

SKILL_PERKS["Stealing"] = [
    {"name": "Pickpocket",      "perk_type": "activated", "effect": {"ability": "pickpocket"},    "desc": "Pickpocket adjacent enemies for 1-10 + STS cash. Also grants +2 Street Smarts."},  # level 1
    {"name": "Sticky Fingers",  "perk_type": "passive",   "effect": None,                         "desc": "Chance to gain +1 Street Smarts on the first item pickup each floor."},             # level 2
    {"name": "Shakedown",      "perk_type": "passive",   "effect": None,                         "desc": "Enemies drop a bonus consumable on death. Chance: 10 + STS/3 %."},              # level 3
    {"name": "Sleight of Hand", "perk_type": "passive", "effect": None,                         "desc": "Pickpocket has min(STS*2, 60)% chance to distract the target, causing their next attack to miss. +2 Street Smarts."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                      # levels 4-10
]

SKILL_PERKS["Gunplay"] = [
    {"name": "Locked In", "perk_type": "passive", "effect": None, "desc": "Consecutive gun shots on the same target deal +1 stacking damage. Resets on target switch, melee, or ability use."},  # level 1
    {"name": "Sniper's Mark", "perk_type": "activated", "effect": {"ability": "snipers_mark"}, "desc": "Mark a visible enemy (+10% damage taken, rounds up). 1 use/floor. Charge refunded on marked target's death."},  # level 2
    {"name": "Doin' It Sideways", "perk_type": "passive", "effect": None, "desc": "-10% accuracy (min 5%), -10 energy cost per shot (min 10)."},  # level 3
    {"name": "Dead Eye", "perk_type": "passive", "effect": None, "desc": "Killing an enemy with a gun shot grants +1 Swagger for the rest of the floor."},  # level 4
    {"name": "Gun Crit", "perk_type": "passive", "effect": None, "desc": "Guns can now critically hit. Crit chance scales with Street Smarts."},  # level 5
    {"name": "Mega Crit", "perk_type": "stat", "effect": {"street_smarts": 2}, "desc": "+2 Street Smarts. Gun crits can crit again for 4x damage."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 7-10
]

SKILL_PERKS["Chemical Warfare"] = [
    {"name": "Toxic Harvest", "perk_type": "activated", "effect": {"ability": "toxic_harvest"}, "desc": "50t cooldown. For 10 turns, any monster kill grants +25 toxicity and refreshes this buff."},  # level 1
    {"name": "Toxic Frenzy", "perk_type": "passive", "effect": {"tolerance": 2}, "desc": "+2 TOL. +1% melee and gun damage per 10 toxicity (cap 500 tox, max +50%). +1 speed per 10 toxicity (cap +50). The poison fuels your fury."},  # level 2
    {"name": "Acid Meltdown", "perk_type": "activated", "effect": {"ability": "acid_meltdown"}, "desc": "50t cooldown. Cost: 25 tox. 10 turns: halve move cost. Kills explode into 3x3 acid pools."},  # level 3
    {"name": "Toxic Slingshot", "perk_type": "activated", "effect": {"ability": "toxic_slingshot"}, "desc": "10t cooldown. Cost: 50 tox. Conjure a toxic slingshot in your sidearm (requires empty slot). 20 ammo, 30 turn duration. Damage scales with CW level. Applies toxicity on hit. Grants Scattershot (cone AOE)."},  # level 4
    {"name": "Toxic Shell", "perk_type": "activated", "effect": {"ability": "toxic_shell"}, "desc": "3/floor. Consume 1/10th of your toxicity as a barrier (temp HP). When temp HP hits 0, nova (radius 4): deals tox/5 + CW×5 + STS/3 damage, applies tox_consumed/2 toxicity to enemies."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]

SKILL_PERKS["Meth-Head"] = [
    {"name": "Sped", "perk_type": "passive", "effect": None, "desc": "20% on melee hit: gain Sped for 5 turns (half melee energy cost). Costs 10 meth. Cannot proc while active."},  # level 1
    {"name": "Crack Hallucinations", "perk_type": "activated", "effect": {"ability": "crack_hallucinations"}, "desc": "1/floor. Next consumable used grants meth equal to its value, plus Meth-Head XP."},  # level 2
    {"name": "Tweaker", "perk_type": "passive", "effect": None, "desc": "+10 speed per 25 meth. At full meth (250), that's +100 speed."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
]

SKILL_PERKS["L Farming"] = [
    {"name": "Shake It Off", "perk_type": "stat", "effect": {"constitution": 2}, "desc": "+2 Constitution. Heal 2 HP whenever you kill an enemy."},  # level 1
    {"name": "Built Different", "perk_type": "stat", "effect": {"swagger": 4, "constitution": 2}, "desc": "+4 Swagger, +2 Constitution. You've been hit so many times it doesn't even phase you."},  # level 2
    {"name": "Unfazed", "perk_type": "passive", "effect": None, "desc": "25% chance when taking damage to gain +1 Swagger for the rest of the floor. Stacks."},  # level 3
    {"name": "Armor Up", "perk_type": "passive", "effect": None, "desc": "35% chance when hit while you have armor to block the hit, reducing damage to 1."},  # level 4
    _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 5-10
]

SKILL_PERKS["Ammo Rat"] = [
    {"name": "Scrounger", "perk_type": "passive", "effect": None, "desc": "50% chance to gain +1 bonus round when picking up ammo."},  # level 1
    {"name": "Ammo Nerd", "perk_type": "stat", "effect": {"book_smarts": 2, "street_smarts": 2}, "desc": "+2 Book-Smarts, +2 Street-Smarts. 2x XP from picking up ammo."},  # level 2
    {"name": "Rat Race", "perk_type": "passive", "effect": None, "desc": "Dismantling any item yields ammo (5 light, 3 medium, 1 heavy). 20% chance on ammo pickup: +10 speed for 20 turns (stacks, refreshes)."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
]


SKILL_PERKS["Decontamination"] = [
    {"name": "Radiant", "perk_type": "stat", "effect": {"tolerance": 2, "strength": 2, "rad_resistance": 30}, "desc": "+10 Max Armor. +30% Rad Resistance, +2 Tolerance, +2 Strength."},  # level 1
    {"name": "Gamma Aura", "perk_type": "activated", "effect": {"ability": "gamma_aura", "strength": 3}, "desc": "+3 STR. Toggle aura: enemies within 2 tiles gain +5 rad/turn. 2x Decontamination XP from resisted radiation. Nearby enemy dying with 50+ rad removes 25 of your radiation."},  # level 2
    {"name": "Consecrate", "perk_type": "activated", "effect": {"ability": "consecrate", "rad_resistance": 15}, "desc": "+20 Max Armor. 2/floor, 30t CD. Lay a 5x3 rad zone (20t). Enemies: +10 rad/turn, true dmg. Standing in zone: +1 Swagger/turn (cap 5). Low rad = chance to preserve charge. +15% rad resist."},  # level 3
    {"name": "Ironsoul Aura", "perk_type": "activated", "effect": {"ability": "ironsoul_aura", "swagger": 2}, "desc": "+2 SWG. Toggle aura: +1 DR per visible enemy (cap 5), +2 FOV radius. Hits from visible enemies grant +10 rad. 25% on melee hit: lose damage dealt in radiation, gain it as armor."},  # level 4
    {"name": "Sanctified Discharge", "perk_type": "passive", "effect": None, "desc": "+30 Max Armor. Consecrate upgraded: 4 charges/floor, +20 rad/turn. 30% chance/turn: +1 Ignite stack, +1 Shocked stack (independent, cap 10 each). Both capped: double true damage."},  # level 5
    {"name": "Retribution Aura", "perk_type": "activated", "effect": {"ability": "retribution_aura", "street_smarts": 2}, "desc": "+2 STS. Toggle aura: enemies that melee you take rad/20 + Decon level true damage (cap 30) and you drain 5 rad per proc."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 7-10
]

SKILL_PERKS["Arachnigga"] = [
    {"name": "Web Trail", "perk_type": "activated", "effect": {"ability": "web_trail"}, "desc": "You are immune to webs. Activate: for 5 turns, every tile you move off of gets a cobweb. 3/floor."},  # level 1
    {"name": "Summon Spider", "perk_type": "activated", "effect": {"ability": "summon_spiderling"}, "desc": "Summon a Spider Hatchling on an adjacent tile. It guards until enemies approach, then chases and bites. 5/floor."},  # level 2
    {"name": "Toxic Bite", "perk_type": "activated", "effect": {"ability": "toxic_bite"}, "desc": "Bite an adjacent enemy for STS damage + 2 Venom stacks (10t). Enemies that die while venomed leave a Venom Pool. 6/floor."},  # level 3
    {"name": "Brood Mother", "perk_type": "passive", "effect": None, "desc": "Spider Hatchlings split into 2 micro-spiders on death (1 HP, 5t lifespan). Venom Pools hatch a spiderling after 3 turns."},  # level 4
    {"name": "Spider's Nest", "perk_type": "activated", "effect": {"ability": "spiders_nest"}, "desc": "+30 speed on cobweb tiles. Activate: 7x7 cobweb area. 20% per tile to place a spider egg (hatches in 2t). Enemies caught are cocooned (3t, immobile, venom bursts on break). 2/floor."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                      # levels 6-10
]

SKILL_PERKS["Graffiti"] = [
    {"name": "Taggin'", "perk_type": "stat", "effect": {"swagger": 1, "street_smarts": 2}, "desc": "+1 Swagger, +2 Street-Smarts. 50% chance spraying doesn't consume a charge."},  # level 1
    {"name": "Street Art", "perk_type": "passive", "effect": None, "desc": "When any enemy dies on a painted tile, heal 5 HP. If you're also on a painted tile, heal 5 more."},  # level 2
    {"name": "Living Canvas", "perk_type": "passive", "effect": None, "desc": "20% on melee hit: enemy tile turns red. 20% when hit: your tile turns green. 20% on ability use: your tile turns blue."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,                                                                # levels 4-5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                      # levels 6-10
]

SKILL_PERKS["Infected"] = [
    {"name": "Purge", "perk_type": "activated", "effect": {"ability": "purge"}, "desc": "Unlimited. Remove 20 infection. Your next 3 melee attacks deal 50% damage. Stacks."},  # level 1
    {"name": "Zombie Rage", "perk_type": "activated", "effect": {"ability": "zombie_rage"}, "desc": "+2 Strength. Activate: +20% melee damage, +20 energy/tick for 10 turns. Stacks. +5 infection on use and per kill. Kills reset cooldown. 20t cooldown."},  # level 2
    {"name": "Zombie Stare", "perk_type": "activated", "effect": {"ability": "zombie_stare"}, "desc": "+2 Strength. Target enemy within 3 tiles: stunned 3 turns, feared 10 turns. +5 infection. 15t cooldown."},  # level 3
    {"name": "Corpse Explosion", "perk_type": "passive", "effect": None, "desc": "Enemies killed during Zombie Rage explode (30% max HP, radius 3). +2 infection per explosion, +2 more per chain depth. If explosions push infection to 100: Infection Nova (STR×3 dmg, 2t stun, radius 5). Resets to 50 infection. 1/floor."},  # level 4
    {"name": "Hunger", "perk_type": "passive", "effect": {"strength": 2, "constitution": 2}, "desc": "+2 STR, +2 CON. Purge grants Hunger (10t): melee heals 25% of dmg dealt, +1 infection per hit. Zombie Stare upgraded to 90° cone (range 3). Infection cost increased to 8."},  # level 5
    {"name": "Outbreak", "perk_type": "activated", "effect": {"ability": "outbreak"}, "desc": "Target 7×7 area (center within 3). Enemies gain Outbreak (12t): damage echoes 30% to other marked enemies within r3. +2 infection per enemy marked. 30t cooldown."},  # level 6
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                      # levels 7-10
]


SKILL_PERKS["Cryomancy"] = [
    {"name": "Freeze", "perk_type": "activated", "effect": {"ability": "freeze"}, "desc": "Freeze a visible enemy within 5 tiles. 5 stacks of Frozen (can't move, can't attack, +99 DR). 4 charges/floor."},  # level 1
    {"name": "Ice Lance", "perk_type": "activated", "effect": {"ability": "ice_lance"}, "desc": "Piercing projectile (6 tiles). Dmg: 3x Cryo + BKS/2. +1 Chill per enemy. Shatters Frozen enemies for 3x Cryo + 2x BKS. 10-turn cooldown."},  # level 2
    {"name": "Chill Out", "perk_type": "passive", "effect": None, "desc": "Chilled enemies deal 10% less melee damage per chill stack (multiplicative, cap 50%). 3 stacks = 73%, 5 stacks = 59%."},  # level 3
    {"name": "Glacier Mind", "perk_type": "stat", "effect": {"book_smarts": 5}, "desc": "+5 Book Smarts. Cold spell charges are doubled (per-floor resets and granted charges)."},  # level 4
    {"name": "Ice Barrier", "perk_type": "activated", "effect": {"ability": "ice_barrier"}, "desc": "Consume all Chill stacks from enemies within 7 tiles. Gain 10 Temp HP per stack consumed. +5 Cryo XP per stack. 3/floor."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                        # levels 6-10
]


SKILL_PERKS["Electrodynamics"] = [
    {"name": "Charged Up", "perk_type": "stat", "effect": {"swagger": 2}, "desc": "+10 Speed, +2 Swagger."},  # level 1
    {"name": "Volt Dash", "perk_type": "activated", "effect": {"ability": "volt_dash"}, "desc": "Blink to tile within 5 radius. Deal 1-(10+5×Electro lvl) dmg along the line and adjacent to landing. +1 Shock. 4/floor."},  # level 2
    {"name": "Discharge", "perk_type": "activated", "effect": {"ability": "discharge"}, "desc": "Channel 6 turns (3 cycles). Wave 1: +1 Shocked (LOS, 7 radius). Wave 2: 1-(10+10×Electro lvl) lightning dmg (LOS, 5 radius). 25t cooldown."},  # level 3
    {"name": "Surge", "perk_type": "passive", "effect": None, "desc": "Lightning spell hits have 50% chance to grant Surge (+10 speed per stack, 20 turns, stacks & refreshes)."},  # level 4
    {"name": "Static Reserve", "perk_type": "passive", "effect": None, "desc": "Gain 3 Chain Lightning charges. While below 3 charges, regenerate 1 charge every 50 turns."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                        # levels 6-10
]


SKILL_PERKS["Drive-By"] = [
    {"name": "+3 SWG, +3 STS", "perk_type": "stat", "effect": {"swagger": 3, "street_smarts": 3}, "desc": "+3 Swagger, +3 Street Smarts. You move like you own the block."},  # level 1
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,   # levels 2-5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]

SKILL_PERKS["Elementalist"] = [
    {"name": "Elemental Staves", "perk_type": "stat", "effect": {"book_smarts": 1}, "desc": "+1 Book Smarts. Receive an elemental staff matching your highest elemental skill (Pyromania/Cryomancy/Electrodynamics). Staves fire bolts (F key, range 4, 5+BKS/3 dmg, +1 element debuff). Req 12 BKS."},  # level 1
    {"name": "Chromatic Orb", "perk_type": "activated", "effect": {"ability": "chromatic_orb"}, "desc": "Targeted projectile. Randomly picks fire/cold/lightning. Dmg: element skill level × 6. Applies 3 stacks of that debuff. 20-turn cooldown."},  # level 2
    {"name": "Arcane Flux", "perk_type": "passive", "effect": None, "desc": "+10% chance to preserve spell charges. Charge preservation effects (Muffin Magic, Blue Paint, etc.) now also apply to cooldown-based spells, negating the cooldown."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,   # levels 4-5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]


def get_perk(skill_name: str, level: int) -> dict | None:
    """Return perk dict for skill at given level (1-10), or None if invalid."""
    perks = SKILL_PERKS.get(skill_name)
    if not perks or level < 1 or level > 10:
        return None
    return perks[level - 1]

def bksmt_mod(bksmt: int) -> float:
    """Sqrt-based skill_point gain rate from book_smarts.

    Calibrated so bksmt=0 -> 0.1, bksmt=8 -> ~0.19, caps at 0.5.
    Approximate targets: bksmt=8 ~0.19, bksmt=12 ~0.22, bksmt=50 ~0.34.
    """
    import math
    return min(0.5, 0.1 + 0.3 * math.sqrt(max(0, bksmt) / 80.0))


class Skill:
    """A single skill with a level (0-10) and dual exp tracking."""

    def __init__(self, name: str, skill_mod: float = 1.0):
        self.name = name
        self.level = 0
        self.real_exp: float = 0.0      # counts toward level-ups
        self.potential_exp: float = 0.0  # earned passively; converted via spending
        self.skill_mod = skill_mod

    def xp_needed(self, exp_curve=None) -> int:
        """XP required to reach the next level. Returns 0 at max level."""
        if self.level >= MAX_LEVEL:
            return 0
        curve = exp_curve if exp_curve is not None else DEFAULT_EXP_CURVE
        return curve[self.level]

    def add_real_exp(self, amount: float) -> int:
        """Add to real_exp and level up if threshold crossed. Returns levels gained."""
        if self.level >= MAX_LEVEL:
            return 0

        self.real_exp += amount
        gained = 0

        while self.level < MAX_LEVEL and self.real_exp >= DEFAULT_EXP_CURVE[self.level]:
            self.real_exp -= DEFAULT_EXP_CURVE[self.level]
            self.level += 1
            gained += 1

        return gained

    def add_potential_exp(self, amount: float) -> None:
        """Add to potential_exp (uncapped)."""
        self.potential_exp += amount

    def set_level(self, level: int) -> None:
        """Set skill level directly, clamping to [0, MAX_LEVEL]."""
        self.level = max(0, min(MAX_LEVEL, level))

    def is_maxed(self) -> bool:
        return self.level >= MAX_LEVEL


class Skills:
    """Container for all player skills."""

    def __init__(self):
        self.skills = {name: Skill(name) for name in SKILL_NAMES}
        self.skill_points: float = 0.0

    def get(self, name: str) -> Skill:
        """Get a skill by name."""
        return self.skills[name]

    def all(self):
        """Return all skills in definition order."""
        return [self.skills[name] for name in SKILL_NAMES]

    def unlocked(self):
        """Return only unlocked skills (those with level > 0, real_exp > 0, or potential_exp > 0)."""
        return [skill for skill in self.all() if skill.level > 0 or skill.real_exp > 0 or skill.potential_exp > 0]

    def gain_potential_exp(self, skill_name: str, amount: float, bksmt: int,
                           skill_mod_override: float = None,
                           briskness: int = 0) -> None:
        """Award potential_exp to a skill and add scaled skill_points.

        skill_points gained = amount * (bksmt_mod(bksmt) + briskness/100) * skill.skill_mod
        briskness is a percentage bonus (can be negative, no upper cap).
        """
        skill = self.skills[skill_name]
        smod = skill_mod_override if skill_mod_override is not None else skill.skill_mod
        sp_gained = amount * (bksmt_mod(bksmt) + briskness / 100) * smod
        skill.add_potential_exp(amount)
        self.skill_points += sp_gained

    def spend_on_skill(self, skill_name: str, amount: int) -> int:
        """Convert potential_exp to real_exp for a skill by spending skill_points.

        Spends min(amount, potential_exp, skill_points) and returns levels gained.
        """
        skill = self.skills[skill_name]
        if skill.is_maxed():
            return 0
        spendable = min(amount, int(skill.potential_exp), int(self.skill_points))
        if spendable <= 0:
            return 0
        skill.potential_exp -= spendable
        self.skill_points -= spendable
        return skill.add_real_exp(spendable)

    def set_skill_level(self, name: str, level: int) -> None:
        """Set a skill's level directly, clamping to [0, MAX_LEVEL]."""
        self.skills[name].set_level(level)

    def add_xp(self, name: str, amount: float) -> int:
        """Legacy: add directly to real_exp (used for backward compat). Returns levels gained."""
        return self.skills[name].add_real_exp(amount)
