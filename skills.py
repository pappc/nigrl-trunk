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
    "Glow Up",
    "Gatting",
    "Sniping",
    "Drive-By",
    "Ammo Rat",
    "L Farming",
    "Arachnigga",
    "Graffiti",
    "Infected",
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
        "Smartsness", "Stabbing", "Beating", "Smacking", "Stealing", "Jaywalking",
        "Deep-Frying", "Drinking", "Alcoholism", "Munching", "Dismantling",
        "Abandoning", "Meth-Head", "Chemical Warfare", "White Power",
        "Mutation", "Nuclear Research", "Glow Up", "Gatting", "Sniping",
        "Drive-By",
        "Ammo Rat",
        "L Farming",
        "Arachnigga",
        "Graffiti",
        "Infected",
    ]
}

SKILL_PERKS["White Power"] = [
    {"name": "Bleached",  "perk_type": "stat", "effect": {"swagger": 4}, "desc": "+4 Swagger, +20% toxicity resistance. Your body rejects the poison."},  # level 1
    {"name": "White Out", "perk_type": "activated", "effect": {"ability": "white_out"}, "desc": "3/floor. Gain 25 toxicity. +8 Swagger, -25% damage dealt for 50 turns."},  # level 2
    {"name": "Pure",  "perk_type": "stat", "effect": {"swagger": 4}, "desc": "+4 Swagger. Double XP from toxicity resisted."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
]

SKILL_PERKS["Mutation"] = [
    {"name": "Mutagen", "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 to all stats. Immediately mutate for free."},  # level 1
    {"name": "Unstable", "perk_type": "passive", "effect": None, "desc": "20% on melee hit: gain Unstable buff (20t). +5 rad on apply, +2 melee dmg, hits irradiate enemies for 10 rad."},  # level 2
    {"name": "Favorable Odds", "perk_type": "passive", "effect": None, "desc": "+50% good mutation multiplier. Mutations are more likely to be positive."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
]

SKILL_PERKS["Nuclear Research"] = [
    {"name": "Irradiated Intellect", "perk_type": "stat", "effect": {"book_smarts": 3}, "desc": "+3 Book Smarts. Radiation gained increased by Book Smarts% of amount gained."},  # level 1
    {"name": "Rad Bomb", "perk_type": "activated", "effect": {"ability": "rad_bomb"}, "desc": "Place a crystal within 2 tiles that detonates after 3 turns, dealing 15+BKS/2 damage in a 5x5 area (20+BKS at L4). 3 charges/floor. Each cast costs 25 radiation and grants 50 Nuclear Research XP. At 100+ rad, the charge is refunded (rad still spent). Passive: can't mutate below 150 rad."},  # level 2
    {"name": "Nutrient Producer", "perk_type": "grant_item", "effect": {"item_id": "nutrient_producer"}, "desc": "Gain a Nutrient Producer tool. Combine it with any consumable to convert it into a RadBar."},  # level 3
    {"name": "Isotope Junkie", "perk_type": "passive", "effect": None, "desc": "Using a consumable grants +5 radiation (pierces resistance). Rad Bomb damage upgraded to 20+BKS."},  # level 4
    _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 6-10
]

SKILL_PERKS["Deep-Frying"] = [
    {"name": "Fry Shot",     "perk_type": "activated", "effect": {"ability": "fry_shot"},    "desc": "Hurl a ball of scorching hot oil that deals burn damage in a small area."},   # level 1
    {"name": "Extra Greasy", "perk_type": "passive",   "effect": None,                       "desc": "Your fried food items restore +20% HP when eaten."},                         # level 2
    {"name": "Double Batch", "perk_type": "passive",   "effect": None,                       "desc": "20% chance a food item is not consumed when you eat it."},                   # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                # levels 4-10
]

SKILL_PERKS["Dismantling"] = [
    {"name": "+2 BKS, +2 CON",    "perk_type": "stat",    "effect": {"book_smarts": 2, "constitution": 2}, "desc": "+2 Book Smarts, +2 Constitution. You learn from taking things apart."},  # level 1
    {"name": "Chop Shop",   "perk_type": "passive", "effect": None,                                  "desc": "Destroying an item grants +5 armor and +$20 cash from salvaged parts."},   # level 2
    {"name": "Nigga Armor", "perk_type": "passive", "effect": None,                                  "desc": "Gain a stack of Nigga Armor whenever you destroy an item."},               # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 4-10
]

SKILL_PERKS["Abandoning"] = [
    {"name": "+2 All Stats", "perk_type": "stat", "effect": {"constitution": 2, "strength": 2, "street_smarts": 2, "book_smarts": 2, "tolerance": 2, "swagger": 2}, "desc": "+2 to all stats. Leaving things behind builds character."},  # level 1
    {"name": "Anotha Motha", "perk_type": "passive", "effect": None, "desc": "Receive 5 extra item drops when descending to the next floor."},                                                                                           # level 2
    {"name": "Left Behind",  "perk_type": "stat", "effect": {"constitution": 1, "strength": 1, "street_smarts": 1, "book_smarts": 1, "tolerance": 1, "swagger": 1}, "desc": "+1 all stats. On descend, gain +1 DR per item left on the floor (lasts until next floor)."},  # level 3
    {"name": "Milk From The Store", "perk_type": "activated", "effect": {"ability": "milk_from_the_store"}, "desc": "+1 all stats. Activate to double all stats for 10 turns. 3 charges/floor."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                          # levels 5-10
]

SKILL_PERKS["Smoking"] = [
    {"name": "+2 TOL, +2 CON",    "perk_type": "stat",    "effect": {"tolerance": 2, "constitution": 2},     "desc": "+2 Tolerance, +2 Constitution. Your body adapts to the abuse."},              # level 1
    {"name": "Stress Smoke",      "perk_type": "passive",  "effect": None,                                    "desc": "10% chance when hit by an attack to auto-smoke a random joint from your inventory."},  # level 2
    {"name": "Phat Cloud",        "perk_type": "passive",  "effect": None,                                    "desc": "Smoking blows a phat cloud at the nearest enemy, dealing damage based on Tolerance."},  # level 3
    {"name": "Roach Fiend",       "perk_type": "passive",  "effect": None,                                    "desc": "30% chance a joint is not consumed when smoked."},                            # level 4
    {"name": "Contact High",      "perk_type": "passive",  "effect": None,                                    "desc": "Enemies hit by joints roll twice and take the worst. Debuffs spread to all enemies within 3 tiles."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 6-10
]

SKILL_PERKS["Pyromania"] = [
    {"name": "Fire!",         "perk_type": "activated", "effect": {"ability": "place_fire", "constitution": 2},   "desc": "+2 Constitution. Spawn a line of 4 fire tiles in a cardinal direction (10 turns). 3/floor."},  # level 1
    {"name": "+3 CON",      "perk_type": "stat",      "effect": {"constitution": 3},          "desc": "+3 Constitution. Fire hardens the soul."},                                              # level 2
    {"name": "Ignite",        "perk_type": "activated", "effect": {"ability": "ignite_spell"}, "desc": "Targeted ignite spell — set a visible enemy ablaze from a distance."},                  # level 3
    {"name": "Neva Burn Out", "perk_type": "passive",   "effect": None,                        "desc": "You are completely immune to fire and burning damage."},                                 # level 4
    {"name": "Wildfire",      "perk_type": "passive",   "effect": None,                        "desc": "Ignited enemies have a 20% chance per turn to spread fire to adjacent enemies with fewer stacks."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                      # levels 6-10
]

SKILL_PERKS["Blackkk Magic"] = [
    {"name": "Curse of Ham",    "perk_type": "activated", "effect": {"ability": "curse_of_ham"},    "desc": "Curse enemies in a cone (range 3, 60°). Cursed monsters attack slower and deal 50% less damage. 3/floor."},  # level 1
    {"name": "Curse of DOT",    "perk_type": "activated", "effect": {"ability": "curse_of_dot"},    "desc": "Curse a single enemy. Each turn gains a stack and deals 1-5 damage, hitting harder at high stacks. Spreads on death. 3/floor."},  # level 2
    {"name": "Curse of COVID",  "perk_type": "activated", "effect": {"ability": "curse_of_covid"},  "desc": "Curse a single enemy. Each turn applies 20 rad or tox (capped 150). 50% to stack, 25% to spread. 3/floor."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,                                                                     # levels 4-5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                          # levels 6-10
]

SKILL_PERKS["Rolling"] = [
    {"name": "+2 SWG, +2 TOL",       "perk_type": "stat",    "effect": {"swagger": 2, "tolerance": 2}, "desc": "+2 Swagger, +2 Tolerance. Rolling builds swagger and resistance."},  # level 1
    {"name": "Spectral Paper", "perk_type": "stat",    "effect": {"tolerance": 2},                "desc": "+2 Tolerance. Gain a Spectral Paper — a reusable rolling paper that is never consumed."},  # level 2
    {"name": "Seeing Double",  "perk_type": "passive", "effect": None,                             "desc": "50% chance to roll an extra blunt when you roll one up."},           # level 3
    {"name": "Snickelfritz",  "perk_type": "passive", "effect": None,                             "desc": "25% chance to gain a bonus Snickelfritz joint when rolling. Very negative strain."},  # level 4
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
    {"name": "Slow Metabolism", "perk_type": "activated", "effect": {"ability": "slow_metabolism"},   "desc": "Double the duration of all currently active drink buffs. 2 uses per floor."},      # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                         # levels 4-10
]

SKILL_PERKS["Beating"] = [
    {"name": "+3 STR",  "perk_type": "stat",      "effect": {"strength": 3},         "desc": "+3 Strength. Beating people up makes you stronger. Simple as that."},    # level 1
    {"name": "Bash",      "perk_type": "activated",  "effect": {"ability": "bash"},    "desc": "Bash an adjacent enemy with full force, stunning them for 1 turn."},       # level 2
    {"name": "Crit+",     "perk_type": "passive",    "effect": None,                   "desc": "Increases your critical hit chance on all melee attacks."},                # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                          # levels 4-10
]

SKILL_PERKS["Stabbing"] = [
    {"name": "Gouge",     "perk_type": "activated", "effect": {"ability": "gouge"},        "desc": "Gouge a single target, dealing bonus damage and applying a bleed effect."},   # level 1
    {"name": "+2 STS",  "perk_type": "stat",      "effect": {"street_smarts": 2},        "desc": "+2 Street Smarts. You learn to read people by poking holes in them."},        # level 2
    {"name": "Windfury",  "perk_type": "passive",   "effect": None,                        "desc": "Chance to attack a second time immediately after each stab."},                # level 3
    {"name": "+4 STS, +4 STR", "perk_type": "stat", "effect": {"street_smarts": 4, "strength": 4}, "desc": "+4 Street Smarts, +4 Strength. The blade becomes an extension of your body."},  # level 4
    {"name": "Lunge",    "perk_type": "passive",   "effect": None,                        "desc": "Moving into a tile with an enemy directly ahead auto-crits them for free."},  # level 5
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                              # levels 6-10
]

SKILL_PERKS["Smartsness"] = [
    {"name": "+2 BKS",            "perk_type": "stat",      "effect": {"book_smarts": 2},           "desc": "+2 Book Smarts. Forbidden knowledge has its perks."},                    # level 1
    {"name": "Force Be With You",   "perk_type": "activated", "effect": {"ability": "force_push"},    "desc": "Force push an enemy backwards several tiles. Works through walls?"},      # level 2
    {"name": "Arcane Intelligence", "perk_type": "passive",   "effect": None,                         "desc": "All spells and abilities cost significantly less energy to use."},        # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 4-10
]

SKILL_PERKS["Smacking"] = [
    {"name": "Bitch Slap",  "perk_type": "activated", "effect": {"ability": "black_eye_slap"},         "desc": "Slap an adjacent enemy. Dmg: STR (vs females: 10 + 2×STR). 25-turn cooldown."},  # level 1
    {"name": "+3 STR, +3 CON",    "perk_type": "stat",       "effect": {"strength": 3, "constitution": 3},   "desc": "+3 Strength, +3 Constitution. Slapping builds muscle."},                                        # level 2
    {"name": "Black Eye",   "perk_type": "passive",    "effect": None,                                  "desc": "Unarmed attacks have a 10% chance to cause Black Eye: stun 2 turns, then 10 turns of dazed wandering."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                           # levels 4-10
]

SKILL_PERKS["Munching"] = [
    {"name": "Fast Food",    "perk_type": "activated", "effect": {"constitution": 2, "ability": "quick_eat"}, "desc": "+2 Constitution. Grants Quick Eat: instantly eat your next food. 1 use per floor."},  # level 1
    {"name": "+2 CON",  "perk_type": "stat",    "effect": {"constitution": 2}, "desc": "+2 Constitution. You're a unit. No cap."},                     # level 2
    {"name": "Better Later", "perk_type": "passive", "effect": None,               "desc": "Food effects last 50% longer before wearing off."},            # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                      # levels 4-10
]

SKILL_PERKS["Jaywalking"] = [
    {"name": "Air Jordans",   "perk_type": "passive",   "effect": None,                    "desc": "Movement costs -5 energy. You move like you own these streets."},     # level 1
    {"name": "Dash",          "perk_type": "activated", "effect": {"ability": "dash"},     "desc": "Dash in a direction, instantly moving 3 tiles. Great for escaping."},  # level 2
    {"name": "Airer Jordans", "perk_type": "passive",   "effect": None,                    "desc": "+10 Speed. Even fresher kicks. Even faster feet."},                    # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                               # levels 4-10
]

SKILL_PERKS["Stealing"] = [
    {"name": "Pickpocket",      "perk_type": "activated", "effect": {"ability": "pickpocket"},    "desc": "Pickpocket adjacent enemies for 1-10 + STS cash. Also grants +2 Street Smarts."},  # level 1
    {"name": "Sticky Fingers",  "perk_type": "passive",   "effect": None,                         "desc": "Chance to gain +1 Street Smarts on the first item pickup each floor."},             # level 2
    {"name": "Shakedown",      "perk_type": "passive",   "effect": None,                         "desc": "Enemies drop a bonus consumable on death. Chance: 10 + STS/3 %."},              # level 3
    {"name": "Sleight of Hand", "perk_type": "passive", "effect": None,                         "desc": "Pickpocket has min(STS*2, 60)% chance to distract the target, causing their next attack to miss. +2 Street Smarts."},  # level 4
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                      # levels 4-10
]

SKILL_PERKS["Gatting"] = [
    {"name": "Locked In", "perk_type": "passive", "effect": None, "desc": "Fast mode: consecutive shots on the same target deal +1 stacking damage. Resets on target switch, melee, or ability use."},  # level 1
    {"name": "Doin' It Sideways", "perk_type": "passive", "effect": None, "desc": "Fast mode: -10% accuracy (min 5%), -10 energy cost per shot (min 10)."},  # level 2
    {"name": "Gun Crit", "perk_type": "passive", "effect": None, "desc": "Guns can now critically hit. Crit chance scales with Street Smarts."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                          # levels 4-10
]


SKILL_PERKS["Sniping"] = [
    {"name": "Sniper's Mark", "perk_type": "activated", "effect": {"ability": "snipers_mark"}, "desc": "Mark a visible enemy (+10% damage taken, rounds up). 1 use/floor. Charge refunded on marked target's death."},  # level 1
    {"name": "Dead Eye", "perk_type": "passive", "effect": None, "desc": "Killing an enemy with an accurate gun shot grants +1 Swagger for the rest of the floor."},  # level 2
    {"name": "Mega Crit", "perk_type": "stat", "effect": {"street_smarts": 2}, "desc": "+2 Street Smarts. Unlocks gun crits. Accurate mode crits can crit again for 4x damage."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
]

SKILL_PERKS["Chemical Warfare"] = [
    {"name": "Toxic Harvest", "perk_type": "activated", "effect": {"ability": "toxic_harvest"}, "desc": "1/floor. For 10 turns, any monster kill grants +5 toxicity and refreshes this buff."},  # level 1
    {"name": "Toxic Resilience", "perk_type": "stat", "effect": {"tolerance": 5, "constitution": 3, "tox_resistance": -30}, "desc": "+5 Tolerance, +3 Constitution, -30% Toxicity Resistance. Embrace the poison."},  # level 2
    {"name": "Acid Meltdown", "perk_type": "activated", "effect": {"ability": "acid_meltdown"}, "desc": "1/floor. Cost: 25 tox. 20 turns: halve move cost. Kills explode into 3x3 acid pools."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 4-10
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


SKILL_PERKS["Glow Up"] = [
    {"name": "Radiant", "perk_type": "stat", "effect": {"tolerance": 2, "strength": 2, "rad_resistance": 30}, "desc": "+30% Rad Resistance, +2 Tolerance, +2 Strength."},  # level 1
    {"name": "Emission", "perk_type": "activated", "effect": {"ability": "emission"}, "desc": "Set all visible enemies' radiation to yours. 1 use/floor. Irradiated enemies take rad//50 damage/tick and decay 5 rad/tick."},  # level 2
    {"name": "Fallout", "perk_type": "stat", "effect": {"strength": 2}, "desc": "+2 Strength. 20% chance on dealing damage to irradiate the target (+100 rad)."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,  # levels 3-10
]

SKILL_PERKS["Arachnigga"] = [
    {"name": "Web Trail", "perk_type": "activated", "effect": {"ability": "web_trail"}, "desc": "You are immune to webs. Activate: for 5 turns, every tile you move off of gets a cobweb. 3/floor."},  # level 1
    {"name": "Summon Spider", "perk_type": "activated", "effect": {"ability": "summon_spiderling"}, "desc": "Summon a Spider Hatchling on an adjacent tile. It guards until enemies approach, then chases and bites. 5/floor."},  # level 2
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                                                  # levels 3-5
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
    {"name": "Zombie Rage", "perk_type": "activated", "effect": {"ability": "zombie_rage"}, "desc": "+2 Strength. Activate: +20% melee damage, +20 energy/tick for 10 turns. +5 infection on use and per melee kill. 40t cooldown."},  # level 2
    {"name": "Zombie Stare", "perk_type": "activated", "effect": {"ability": "zombie_stare"}, "desc": "+2 Strength. Target enemy within 3 tiles: stunned 3 turns, feared 10 turns. +5 infection. 15t cooldown."},  # level 3
    _PLACEHOLDER, _PLACEHOLDER,                                                                # levels 4-5
    _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER,                      # levels 6-10
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
    return min(0.5, 0.1 + 0.3 * math.sqrt(bksmt / 80.0))


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
