---
name: Transformation / Corruption Meter Research
description: 10-game survey of corruption/infection/transformation meters (Bloodborne Beasthood, DD stress, VtM Frenzy, DCSS transmutations, DS3 Hollowing, ER Frenzy, PoE Vaal, Qud mutations, CDDA thresholds, Hades 2 Magick) with 3 L6 Infected perk proposals
type: reference
---

Research covering corruption/transformation meters across 10 games, applied to NIGRL Infected skill tree L6 perk design.

## Key Design Patterns Found

1. **Meter-as-Slider** (Bloodborne Beasthood): Continuous scaling where meter fill = damage dealt multiplier AND damage taken multiplier. +70% damage at full meter, +70% damage taken. Decays on inaction. Turn-based adaptation: decay on non-attack turns.

2. **Threshold Moment** (Darkest Dungeon): At 100 stress, 75% Affliction (devastating debuff) vs 25% Virtue (powerful buff). Dual outcomes make approaching the threshold exciting rather than purely scary. Key numbers: Affliction = -25% stats, Virtue = +25-33% stats.

3. **Spend-the-Corruption** (PoE Vaal Skills): Build meter from kills, spend for massive one-shot. Vaal Haste: 36 kills for +36% speed 6s. Vaal RF: 36 kills for +161% MORE spell damage 4s. Creates "spend now or build higher?" tension. Boss fights penalize soul gain by 50%.

4. **Sustained Transformation** (VtM Frenzy, DCSS Transmutations): Enter altered state with different rules. VtM Frenzy: +2 all physical stats but can't use most abilities, attacks nearest target. DCSS Blade Hands: huge damage but can't read scrolls. Key: transformation REMOVES access to something important.

5. **Permanent Threshold** (CDDA mutation thresholds): 5-7 mutations from one category locks you into that category permanently, grants unique threshold bonus. Irreversible commitment creates dramatic moment.

## Three L6 Proposals

**A. Undying (recommended)**: Activate to set infection=100, enter 12-turn transformation. No infection tick damage, +50% melee, cleave attacks, can't Purge. Lose 15% current HP/2 turns. Kill = heal 20% enemy max HP. Post-expiry: infection drops to 40, -30 energy/tick 8 turns. 1/floor or 40t cooldown. DNA: Bloodborne Beast + DD threshold moment.

**B. Ghoul Rush**: Spend all infection for burst lunge attack. Damage = infection*STR/5. Range = 3+infection/20. At 50+: stun. At 80+: free Rage stack. At 100: execute <30% HP. 15t cooldown. DNA: PoE Vaal skills.

**C. Revenant**: Toggle mode. Infection tiers grant passive bonuses (up to +50% melee, +40 energy, +6 DR at 100). Healing inversion: all healing damages you instead. Only heal via melee lifesteal scaled by infection%. 20-turn minimum lock. DNA: VtM Humanity + Bloodborne sustained transformation.

## Key Balance Numbers from Precedents
- Bloodborne Beasthood: +70% damage / +70% damage taken at full
- DD Affliction/Virtue: 75/25 split, +/-25% stats
- PoE Vaal RF: +161% MORE spell for 4s, costs 30% max life
- VtM Frenzy: +2 all physical, can't use most abilities
- DCSS Blade Hands: 22+STR/2 damage, can't read scrolls
- Elden Ring Madness: 15% max HP + 100 flat damage, 30% FP loss on proc
