# Zone Design Notes

## Zone 2: Meth Lab

### Source
Confirmed in: enemies.py ZONE_SPAWN_TABLES, loot.py ZONE_LOOT_CONFIG,
version_history_and_features.txt "Future Features" section,
nigrl-ideas/meth_lab_weapons.txt

### Planned Mechanics (from version_history_and_features.txt)
- Radiation and mutation system
- Toxicity system
- Each mechanic has its own suite of items and stats
- Two cartel factions: Aldor and Scryer

### Weapons Designed (nigrl-ideas/meth_lab_weapons.txt)
40 weapons total — 20 ghetto/street weapons, 20 classic fantasy weapons
New status effects introduced for this zone (not yet implemented):
  expose, root, silence, corrode, barbed, tether, magnetize, doom,
  petrify, mark, charm, warp, jinx, momentum, vengeance, reflect

Notable street weapons:
- Rusty Stop Sign (expose), Dog Chain (root), Zip Gun (one-shot ranged),
  Floorboard with Nails (bleed+glass_shards), Coiled Mattress Spring (barbed),
  Bottle Cap Glove (guaranteed bleed), Dumpster Hook (tether),
  Car Jack Handle (expose), Electrical Tape Bat (momentum),
  Junkyard Magnet on Chain (magnetize+shocked), Sawed-Off Broom Handle (silence),
  Stripped Gear Shaft (corrode), Bent TV Antenna (reach 3, shocked),
  Rusty Crowbar with Sock (silence+stun, grants pry), Fire Poker (ignite),
  Coiled Barbed Wire (barbed+bleed), Broken Neon Sign Tube (shocked+glass_shards),
  Hubcap (expose+stun), Stripped Hydraulic Hose (AOE blast 30%), Chain Padlock (root+expose)

Notable fantasy weapons:
- Doom Mace (10-turn kill countdown), Spirit Lash (20% current HP per hit),
  Charm Rod (charm 20%), Warp Blade (warp 35%), Hex Knife (stacking mark),
  Vengeance Club (stores last 3 hits taken), Mirror Shard (reflect 15% passive),
  Jinx Stick (guaranteed miss for 2 turns)

### Enemy Spawn Table
Currently empty — ZONE_SPAWN_TABLES["meth_lab"] = [] in enemies.py

### Loot Tables
All empty stubs in loot.py — ZONE_CONSUMABLE/MATERIAL/TOOL/FOOD/EQUIPMENT tables
