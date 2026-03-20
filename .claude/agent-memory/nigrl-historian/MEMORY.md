# NIGRL Historian — Persistent Memory

## Zone Progression (confirmed from codebase)
- Zone 1: crack_den (4 floors, fully implemented)
- Zone 2: meth_lab (confirmed name, 0 content implemented — stub entries only in enemies.py, loot.py)
- Zone 3: casino_botanical (stub only)
- Zone 4: the_underprison (stub only)
- See `zone-design.md` for full Meth Lab design notes

## Skill Trees — Implementation Status
See `skill-trees.md` for full breakdown.
- 17 total skill trees in SKILL_NAMES (skills.py line 23)
- 6 trees have partial perk content (L1-L3 designed): Smoking, Rolling, Pyromania, Stabbing, Alcoholism, Munching
- 2 trees have partial content NOT reflected in skills_and_perks_table.txt: Deep-Frying (Fry Shot/Extra Greasy/Double Batch), Dismantling (Stat Up!/Chop Shop/Nigga Armor), Abandoning (Anotha Motha), Pyromania (Fire!/Ignite spells at L1/L3), Drinking (Liquid Bandage/One More Sip/Slow Metabolism), Beating (Bash/Crit+), Blackkk Magic (Force Be With You/Arcane Intelligence), Smacking (Bitch Slap/Black Eye), Jaywalking (Air Jordans/Dash/Airer Jordans), Stealing (Street Smarter/Pickpocket/Sticky Fingers)
- Truly empty (all placeholder): Negromancy, Meth-Head
- skills_and_perks_table.txt is OUTDATED — skills.py has significantly more content than the doc reflects

## Key File Paths
- skills.py: SKILL_NAMES list (line 23), SKILL_PERKS dict (line 51+)
- enemies.py: MONSTER_REGISTRY, ZONE_SPAWN_TABLES (line 672)
- loot.py: ZONE_LOOT_CONFIG (line 22), all zone table stubs
- config.py: ZONE_JAYWALK_MULT, ZONE_BLACKK_MAGIC_MULT
- nigrl-ideas/: meth_lab_weapons.txt, skills_and_perks_table.txt, xp_skill_concepts.txt
- version_history_and_features.txt: dev changelog and future features list

## Naming Conventions (confirmed)
- Zone keys: snake_case strings ("crack_den", "meth_lab")
- Skill tree names: Title Case with hyphens allowed ("Blackkk Magic", "Deep-Frying", "Meth-Head")
- Enemy keys: snake_case ("jungle_boyz", "baby_momma")
- Item keys: snake_case ("hot_cheetos", "instant_ramen")
- Ability keys: snake_case ("throw_bottle", "black_eye_slap")
