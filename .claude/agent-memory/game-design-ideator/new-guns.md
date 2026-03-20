---
name: New Gun Concepts (12 guns)
description: Mechanical details, new fields, new effects, and balance notes for the 12 new gun designs in nigrl-ideas/new-gun-concepts.txt
type: project
---

# New Gun Concepts — Design Reference

Full design doc: `nigrl-ideas/new-gun-concepts.txt`
Date designed: 2026-03-12

## Zone Drop Summary

Crack Den only: Cold Shoulder (fl3-4), Ghost Nine (fl2-4), Sick Stick (fl1-3),
  Favor Card (fl2-4), Last Word (fl1-3 both zones)
Both zones: Cold Shoulder (Meth fl1-3), Ghost Nine (Meth fl1-2),
  Favor Card (Meth fl1-3), Breadwinner (Meth fl2-4), Last Word (both)
Meth Lab only: Batch Burner (all floors), Drum Run (fl2-4), Yellow Rain (fl3-4),
  Hot Wire (fl2-4)
Crack Den late/boss only: Crowbar 12 (fl4), Empty Sermon (fl3-4)

## New Gun Entity Fields

  is_revolver: bool                (Cold Shoulder — per-round reload routing)
  suppressed: bool                 (Ghost Nine — suppressed alert radius)
  inverse_scaling: bool            (Empty Sermon — damage scales as mag empties)
  fear_gun: bool                   (Sick Stick — rattled on-hit, broke on crit)
  is_charge_gun: bool              (Crowbar 12 — charge level gates firing)
  charge_level: int = 0            (Crowbar 12 — max 3; resets on fire or damage taken)
  is_kill_scaling: bool            (Favor Card — floor kill counter)
  floor_kills: int = 0             (Favor Card — resets on floor change)
  reminder_pending: bool = False   (Favor Card — bonus shot on threshold)
  auto_reload_on_kill: int = 0     (Breadwinner — rounds auto-loaded on kill)
  manual_reload_penalizes: bool    (Breadwinner — Jammed Up debuff on manual reload)
  alert_radius_mult: float = 1.0   (Breadwinner — 2.0 = double alert range)
  tox_per_shot: int = 0            (Batch Burner — drains player tox instead of ammo)
  shots_remaining: int = 0         (Batch Burner — internal shot counter, max 10)
  is_cloud_gun: bool               (Drum Run — deploys toxic_cloud hazard, no direct dmg)
  is_rad_gun: bool                 (Hot Wire — damage scales with player_rad)

## New Effects Needed

  shaken      — debuff, 3t, -20 energy/tick. Slam Fire proc (Cold Shoulder).
  broke       — debuff, 8t, 55% skip-turn + flee. Sick Stick crit upgrade from rattled.
  magnetized  — debuff, 3t, -20 energy/tick, flavor only. Crowbar 12 charge 2-3.
  condemned   — debuff, 6t, -3 defense + 3 bleed/turn. Empty Sermon Last Rites.
  corroded    — debuff, 5t, stacking acid DOT (+2 per stack). Batch Burner on-hit.
                Spread: when corroded target dies → Chebyshev(1) enemies get 1 stack.
  irradiated  — debuff, 8t, 5 dmg/turn + 25% splash to adjacents. Hot Wire line hit.
  weakened    — debuff, 10t, +25% incoming damage multiplier. Yellow Rain 3-turn zone.
  jammed_up   — player debuff, 3t, forces fast mode -10% hit. Breadwinner manual reload.

## New Engine Fields

  player_rad: int = 0              (radiation meter, parallel to player_tox)
  toxic_cloud_entities: list       (Drum Run FIFO cap 3)
  shaken_gun_active: bool          (Favor Card 10-kill milestone)

## New Hazard Types

  "toxic_cloud"  — char '#' green (100,200,60), blocks_fov=True, dur=5
                   8-12 tox + 3 dmg/turn to all in Chebyshev(1). Max 3 active.
  "rad_zone"     — char '^' yellow-green (180,255,60), does NOT block fov, dur=8
                   20 rad/turn to Chebyshev(2); monster rad dmg: rad//8, player: rad//10

## New Item

  "last_word"        — consumable, charges=2, 0 energy cost on use, holdout pistol
                       auto-targets nearest visible enemy in range 4. Not a gun slot item.
                       max 1 in inventory. Exempt from gun_jammed effect.
  "toxic_canister"   — ammo category, used only by Drum Run.

## Key Design Rules Established

- Last Word is NOT a gun (no equipment slot, no skill tree interaction, 0 energy cost).
  This is intentional — it is an emergency consumable that bypasses the gun system.
- Batch Burner and Drum Run are Meth Lab zone exclusives (no Crack Den drops).
- Yellow Rain and Hot Wire require player_rad field — this is separate from player_tox.
- Tox resistance gear provides 40% of its tox_resistance value as rad_resistance too
  (design intent for dual-use Meth Lab gear in radiation builds).
- Corroded effect uses stacking model similar to IgniteEffect (list of independent timers)
  but with amount increment on stack rather than pure timer list.
- Crowbar 12 has no fast mode — is_charge_gun gates fire action, fast mode keybind blocked.
- Empty Sermon: inverse_scaling bonus formula = int((mag_size - current_ammo)/mag_size * 18)
  Applied AFTER defense subtraction (not a defense bypass).
- Favor Card: Reign of Terror (15 kill milestone) sets non-chasing visible enemies
  within 10 tiles to FLEEING for 4 turns.
- Ghost Nine: suppressed flag gates alert propagation — only alerts currently visible
  enemies on shot (not through walls). Ambush bonus: +50% dmg vs IDLE/WANDERING targets.

## Balance Notes

- Cold Shoulder: per-round reload at 40 energy/round is intentionally slow. 6-round cap.
  Slam Fire +8 flat makes the last round ~26-32 effective dmg — matches Crowbar 12 Charge 1.
- Empty Sermon: max bonus at empty = +18 flat. Full mag 8-14, empty 26-32. Competes with
  HV Express consecutive_bonus but trades for vulnerability window.
- Crowbar 12: Charge 3 = 50-90 dmg. This is intentionally near RPG territory (40-50 direct)
  but requires 3 uninterrupted turns vs RPG's single shot. High ceiling, hard to achieve.
- Batch Burner: 15 tox/shot at natural tox decay rate of max(1, tox//50)/20 turns means
  self-sustaining tox level requires approximately 300+ ambient tox. Below that: net drain.
- Yellow Rain: player_rad scales damage taken at rad//10/turn. At rad 200 (Hot Wire
  Irradiated Mode threshold): 20 dmg/turn to self from rad alone. High stakes.
