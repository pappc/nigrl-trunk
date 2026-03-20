# Gun Skill Trees — Detailed Memory

## Three Standard Trees (nigrl-ideas/skill-gun-trees.txt)

Three trees sharing one XP source (gun damage dealt):

  Gang Violence — spray-and-pray; raw firepower + intimidation
    Stat identity: Swagger + Strength + Tolerance
    L1: +2 SWG, +1 STR (stat)
    L2: Full Auto Mentality — kill → Reload Rush charge (max 2), next shot fires
        60% bonus bullet. Passive.
    L3: Spray Pattern — pellet_chance = min(60, swagger*6)%; hits random adjacent
        enemy for 40% of primary damage. Passive.
    L4: Clip Dumper — first shot per floor fires 3 times. 3rd hit applies Shook
        (3t, -30 energy/tick). Passive.
    L5: Drive-By — SELF, PER_FLOOR 1. 4-turn frenzy: free bonus shot (swagger+str
        dmg) before each action; 25% → Bloodied (2 dmg/turn, 4t). Expire →
        Exposed (-3 defense, 2t). +3 SWG on unlock.

  Trigger Discipline — precision CC; patient methodical shooter
    Stat identity: Swagger + Street Smarts + Book Smarts
    L1: +2 flat gun dmg; ranged crits deal +50% on top of crit_multiplier. Passive.
    L2: Kneecap Shot — SINGLE_LOS, INFINITE (CD 12). Dmg = swagger + strsmt//2 -
        def. Applies Kneecapped (6t: -40 energy, cardinal movement only). Activated.
    L3: Double Tap — ranged kill → free bonus shot at nearest other visible enemy.
        Full damage, crit eligible. No chain. Passive.
    L4: Read The Room — 2 turns standing still → Overwatch (+4 flat gun dmg + free
        0-dmg Pinned shot on approaching enemies). Broken by movement/melee hit. Passive.
    L5: One in the Chamber — SINGLE_LOS, ONCE per run. Dmg = (swg*3)+(strsmt*2)+20,
        bypasses defense, forced crit. Marks target (+4 incoming dmg, 10t). Kill →
        Terrifies all visible enemies within 8 tiles (4t flee). +2 STS, +2 SWG on unlock.

  Corner Store Hustler — ammo efficiency + scavenging
    Stat identity: Tolerance + Book Smarts + Swagger
    Requires ammo system on gun items (ammo_current / ammo_max).
    L1: Every Bullet Counts — (10 + tolerance)% chance not to consume ammo on shot.
        Hard cap 25%. Passive.
    L2: Loot the Body — ranged kill → (20 + book_smarts)% chance to find 1-3 ammo.
        Named/elite kills always +1 ammo. Passive.
    L3: Field Strip — SELF, PER_FLOOR 2. Consume 1 material from inventory → restore
        3/5/8 ammo (common/uncommon/rare by item value). Activated.
    L4: No Waste — L1 chance +10%, new hard cap 40%. Gun hits 0 ammo → free snap
        reload (3 + tolerance//2 ammo, once/floor, no turn cost). Passive.
    L5: The Plug — SELF, PER_FLOOR 1. Full reload + spawn 1-2 ammo cache items nearby
        + 5t Plugged In buff (doubles L1 and L2 proc chances). +2 TOL, +1 BKS on unlock.

New effects (standard gun trees):
  drive_by_mode — player buff 4t; fires bonus ranged shot before each action
  kneecapped    — -40 energy/tick, cardinal movement only, 6t
  marked        — +4 incoming damage from all sources, 10t
  terrified     — -40 energy/tick + flee behavior, 4t
  pinned        — cannot move closer to player, 3t
  overwatch     — player buff, display only; logic in engine.py
  bloodied      — BleedingEffect subclass, amount=2, 4t
  exposed       — +3 incoming damage, 2t
  plugged_in    — player buff 5t; engine checks for it on L1/L2 proc rolls

New abilities (standard gun trees):
  drive_by           — SELF, PER_FLOOR 1 (Gang Violence L5)
  kneecap_shot       — SINGLE_LOS, INFINITE CD 12 (Trigger Discipline L2)
  one_in_the_chamber — SINGLE_LOS, ONCE (Trigger Discipline L5)
  field_strip        — SELF, PER_FLOOR 2 (Corner Store Hustler L3)
  the_plug           — SELF, PER_FLOOR 1 (Corner Store Hustler L5)

Engine flags needed (standard gun trees):
  reload_rush_charges: int = 0        (reset each floor if desired)
  opening_volley_available: bool      (reset True on floor change)
  overwatch_turns_standing: int = 0   (reset on move/hit)
  in_overwatch: bool = False
  snap_reload_available: bool = True  (reset True on floor change)

Mixed perk effect dict note: L5 Corner Store Hustler uses
  {"ability": "the_plug", "tolerance": 2, "book_smarts": 1}
  Engine perk application must handle stat keys alongside "ability" key.
  Same pattern applies to Munching L1 (already does this with constitution+ability).


## Two Firing Mode Trees (nigrl-ideas/skill-gun-firing-modes.txt)

FAST mode: 3 shots/burst at 60% damage, 25% miss chance (default).
ACCURATE mode: 1 shot, full damage, no inherent miss, +1 energy cost.
Toggle is free (e.g., Tab key). Mode stored as gun_entity.fire_mode.

  Mag Rat — FAST mode specialist; volume, streak, mobility
    Stat identity: Strength + Tolerance + Swagger
    L1: Bump and Dump — FAST mode 4 shots/burst, miss chance 25%→15%. Passive.
    L2: Hot Barrel — consecutive burst turns build streak (cap 3), +1/+2/+3
        flat per shot. Broken by non-ranged action. Passive.
    L3: Strafe — after FAST burst, free 1-tile move (doesn't break Hot Barrel
        streak). Passive/free action.
    L4: Hollow Tips — each FAST hit: (STR*5)% chance to apply Rattled (3t:
        40% skip-turn chance per enemy turn). Passive.
    L5: Mag Dump — SELF, PER_FLOOR 1. 5-turn frenzy: 6 shots/burst, 0% miss.
        Expire → gun_jammed (1t). +2 TOL, +1 STR on unlock.

  Dead Eye — ACCURATE mode specialist; crits, patience, setup kills
    Stat identity: Swagger + Street Smarts + Book Smarts
    L1: Iron Sights — ACCURATE crits +10% flat crit chance; crit deals
        +BkSmt flat post-crit. Passive.
    L2: Patience — idle turns in ACCURATE mode build stacks (cap 3). On fire:
        consume stacks for +15%/+30%/+50% dmg (stack 3: also bypass 3 armor).
        Lost on move, mode switch, or taking damage. Passive.
    L3: Skull Tap — ACCURATE crits apply Skull Tapped (4t: stun 1t + -2 enemy
        dmg remaining turns). Passive.
    L4: Weak Point — "Read Target" action (costs a turn) marks one enemy.
        ACCURATE shots vs that target: bypass BkSmt//2 armor + BkSmt*2% crit.
        Mark consumed on shot. Passive + new action.
    L5: The Long Game — SELF, PER_FLOOR 1. 6-turn guaranteed crit stance.
        Patience builds 2x fast. First kill → free guaranteed-crit follow-up
        shot → stance ends. +2 BKS, +1 SWG on unlock.

New effects (firing mode trees):
  mag_dump_mode — player buff 5t; 6 shots/burst, 0% miss (engine checks)
  gun_jammed    — player debuff 1t; blocks ranged attack that turn
  rattled       — enemy debuff 3t; 40% skip-turn chance per enemy turn
  skull_tapped  — enemy debuff 4t; stun 1t on apply + -2 enemy dmg turns 2-4
  weak_point    — enemy debuff 999t; cleared by shot/death/mode/FOV
  long_game_mode — player buff 6t; forced crits + 2x Patience gain

New abilities (firing mode trees):
  mag_dump      — SELF, PER_FLOOR 1 (Mag Rat L5)
  the_long_game — SELF, PER_FLOOR 1 (Dead Eye L5)

Engine flags needed (firing mode trees):
  mag_rat_burst_streak: int = 0           (reset each floor)
  mag_rat_strafe_pending: bool = False
  dead_eye_patience_stacks: int = 0       (reset each floor)
  player_was_hit_last_turn: bool = False  (reset each player turn)
  dead_eye_weak_point_target: Entity|None = None
  long_game_kill_fired: bool = False      (reset on ability use/floor)

Prerequisite system needed: gun_entity.fire_mode: str ("accurate"|"fast").
Firing mode toggle is a free action (no turn cost).
