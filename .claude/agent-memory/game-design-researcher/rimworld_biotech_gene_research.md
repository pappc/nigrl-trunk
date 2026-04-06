---
name: RimWorld Biotech Gene System Research
description: Comprehensive survey of RimWorld Biotech DLC gene/mutation system — 100+ genes across 7 categories, 11 xenotypes, metabolic/complexity balance currency, archite tier, ability genes, and body modification genes. Research for NIGRL mutation overhaul.
type: reference
---

## System Architecture

RimWorld Biotech uses a dual-currency balance system for gene packages:
- **Metabolic Efficiency**: Range [-5, +5]. Baseline human = 0 (100% hunger). Positive = eat less, negative = eat more. Good genes cost metabolic efficiency (increase hunger), bad genes grant it (decrease hunger). Floor of -5 = 225% hunger rate.
- **Complexity**: Determines infrastructure needed to assemble a xenogerm. Base gene assembler handles complexity 6; each gene processor adds +2 capacity. Max 18 complexity.

Genes split into two inheritance types:
- **Endogenes** (germline): Inherited naturally through reproduction
- **Xenogenes** (implanted): Installed via xenogerm, suppress conflicting endogenes

## 7 Archite Genes (Ultra-Tier)
Require rare archite capsules. Found on Sanguophages:
1. Deathless — Cannot die unless brain destroyed; enters regenerative coma instead
2. Ageless — Stops aging at 18
3. Non-senescent — Prevents all age-related conditions
4. Scarless (Total Healing) — Heals one scar/chronic condition every 15-30 days
5. Perfect Immunity — Total immunity to infections, diseases
6. Disease Free — No chronic age diseases (cancer, dementia, etc.)
7. Archite Metabolism — +6 metabolic efficiency, effectively a budget to add more genes

## 9 Ability Genes
Grant activated abilities:
1. Fire Spew — Flammable bile breath, large AOE, 5-day cooldown
2. Acid Spray — Sticky acid spit, ranged, DOT
3. Foam Spray — Fire-retardant foam, extinguishes fires
4. Longjump Legs — Hemogen-powered jump to distant tile
5. Piercing Spine — Keratin spine projectile, massive damage, long range
6. Coagulate — Instant wound tending via hand glands, hemogen cost
7. Bloodfeed — Drain blood from target, refill hemogen
8. Animal Warcall — Psychic summon of wild animal to fight
9. Xenogerm Reimplanter — Implant copy of own xenogerm into another

## Key Spectrum/Scaling Genes (Paired Positive/Negative)
Each pair has a good and bad version; bad grants metabolic efficiency:

**Movement**: Very Quick Runner / Quick Runner / Slow Runner
**Melee**: Strong Melee Damage (+50%) / Weak Melee Damage
**Durability**: Robust (take 25% less damage) / Delicate (take more)
**Learning**: Fast Learning / Slow Learning
**Beauty**: Very Beautiful / Pretty / Ugly / Very Ugly
**Sleep**: Never Sleep / Low Sleep / Sleepy / Very Sleepy
**Pain**: Reduced Pain / Extra Pain
**Immunity**: Super Strong Immunity / Strong Immunity / Weak Immunity
**Healing**: Superfast Wound Healing (4x) / Fast Wound Healing (2x) / Slow Wound Healing
**Temperature**: Heat/Cold Super-Tolerant / Tolerant / Weakness
**Mood**: Sanguine / Optimist / Pessimist / Depressive
**Aggression**: Dead Calm / Aggressive / Hyper-Aggressive
**Libido**: High Libido / Low Libido
**Psychic**: Super Psychically Sensitive / Psychically Enhanced / Psychically Dull / Psychically Deaf

## Miscellaneous Passive Genes
- Unstoppable — Not slowed when taking damage
- Fire Resistant — 75% fire damage reduction, reduced ignition chance
- Kill Thirst — Need to kill in melee combat periodically or mood penalty
- Kind Instinct — Never starts social fights, gives mood buffs to others
- Naked Speed — Faster naked, slower clothed
- Nearsighted — Reduced long-range accuracy (good for melee-only builds)
- Pollution Rush — Speed/cognition buff from pollution exposure
- Psychic Bonding — Permanent psychic bond with lover (mood bonuses together, penalties apart)
- Robust Digestion — Equal nutrition from raw and cooked food
- Strong Stomach — Immune to food poisoning
- Dark Vision — No darkness penalties to work speed or mood
- Cave Dweller — No "cooped up" outdoors need
- Violence Disabled — Cannot engage in violence at all
- Inbred — Reduced fertility, immunity, and mental capacity

## Health Genes
- Superclotting — Rapid wound closure
- Tox Resistant (50%) / Tox Immune (100%)
- Fertile / Sterile

## Cosmetic/Body Modification Genes
- Furskin — Full body fur, cold protection, removes naked penalty
- Tail (Furry / Smooth) — Appearance + minor cold or dexterity
- Ears (Cat / Floppy / Pig / Pointed)
- Horns (Center Horn / Mini Horns)
- Heavy Jaw, Pig Nose, Heavy Brow, Facial Ridges
- Pig Hands (reduced manipulation) / Elongated Fingers (improved manipulation)
- Body Type (Fat / Hulk / Thin / Standard)
- Voice (Pig / Roar / Human)
- 12+ skin colors (blue, green, purple, deep red, orange, ink black, etc.)
- Hair genes, beard genes, eye colors (gray, red)

## Sanguophage-Specific Mechanics
- **Hemogen**: Resource pool (max 100, +more via hemopumps). Drains 2/day base + 8/day from Hemogen Drain gene = 10/day total. Refilled via Bloodfeed. Running out = -50% consciousness, +15% pain, -20 mood.
- **Deathrest**: Required every ~30 days. Lasts 2.5-4 days depending on buildings. Skipping causes escalating health/mood penalties.
- **Fire Terror**: Mental break risk near fire
- **Fire Weakness**: 4x fire damage taken

## Drug Dependency Genes
One per drug type (psychite, go-juice, wake-up, etc.). Grants +4 metabolic efficiency but pawn must consume drug every 5 days or suffer escalating penalties (mood -> coma at 30 days -> death at 60 days). Grants addiction/overdose immunity for that drug.

## 11 Xenotypes (Pre-Built Gene Packages)
1. **Hussar** (17 complexity, +2 met) — Super-soldier. Fast runner, pain reduction, unstoppable, great shooting/melee, superfast healing. Dependent on go-juice.
2. **Sanguophage** (57 complexity, 0 met) — Vampire. 7 archite genes, hemogen abilities, fire weakness, deathrest, ageless/deathless.
3. **Genie** (11 complexity) — Intellectual/crafter. Great crafting/intellectual, dead calm, delicate, slow runner. Peaceful genius.
4. **Highmate** (16 complexity, 0 met) — Companion. Psychic bonding, beautiful, violence disabled, high libido. Mood support.
5. **Neanderthal** (12 complexity, +2 met) — Tank. Robust, strong immunity, pain reduction, strong melee. Slow learner, aggressive.
6. **Impid** — Speedster. Very fast runner, fire spew, heat tolerance. Weak immunity, poor melee, pessimist.
7. **Waster** — Toxic survivor. Tox immune, disease immune, psychite dependency. Aggressive, grey skin.
8. **Yttakin** — Beast-kin. Furskin, animal warcall, robust, cold tolerance, roaring voice. Slow healing, aggressive, sleepy.
9. **Dirtmole** — Underground. Dark vision, great mining, strong melee, fast healing. Slow runner, nearsighted, intense UV sensitivity.
10. **Pigskin** — Omnivore. Robust digestion, strong stomach, strong immunity. Pig hands (reduced manipulation), nearsighted, pig features.
11. **Starjack** (Odyssey DLC) — Space-adapted. Vacuum resistant, low gravity adapted. Weaker on ground.

## Design Philosophy: Key Takeaways for NIGRL
1. **Dual currency prevents min-maxing**: metabolic efficiency means you can't stack only good genes without paying hunger costs
2. **Paired genes create meaningful choices**: Robust vs Delicate aren't just good/bad — Delicate gives metabolic budget to spend elsewhere
3. **Ability genes are the most exciting**: Fire Spew, Longjump, Piercing Spine create new verbs, not just stat changes
4. **Xenotypes prove that curated packages create identity**: Each xenotype feels distinct because of 3-4 signature genes, not 15 minor ones
5. **Drug dependency is a novel tradeoff**: +4 metabolic efficiency but requires ongoing drug supply — a different axis than "stat good/bad"
6. **Cosmetic genes matter for identity**: Furskin, tails, horns, skin colors make xenotypes visually distinct and memorable
