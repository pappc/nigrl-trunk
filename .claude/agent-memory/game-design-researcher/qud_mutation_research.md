---
name: Caves of Qud Mutation System Research
description: Complete 48-mutation survey (24 physical, 24 mental) with 6 design patterns extracted for NIGRL mutation overhaul — slot tradeoffs, gameplay verbs, environment interaction, threshold scaling, power-cost, defects-as-choices
type: reference
---

Full reference at: nigrl-ideas/caves-of-qud-mutation-reference.txt

## Core Design Insight
Every Qud mutation creates a *mechanically unique* interaction. Zero mutations are just "+2 STR." Even the simplest (Thick Fur = cold resist + minor AV) provides a specific defensive niche rather than generic stat inflation.

## 6 Key Patterns for NIGRL

1. **Equipment Slot Tradeoffs**: Carapace (+AV, blocks body slot), Stinger (occupies limb), Beak (replaces face). NIGRL has weapon/sidearm/rings/neck/feet/hat — mutations could block slots for power.

2. **New Gameplay Verbs**: Burrowing Claws = dig walls. Wings = fly over terrain. Domination = possess enemies. Force Wall = create terrain. Mutations should grant abilities via existing AbilityDef system.

3. **Environment Interaction**: Flaming Hands sets tiles on fire, Freezing Hands freezes water, Electrical Generation chains through water, Corrosive Gas corrodes equipment. NIGRL has tox/rad/grease tiles to interact with.

4. **Threshold Scaling**: Mutations gain NEW capabilities at level breakpoints, not just bigger numbers. Burrowing Claws L5 = dig metal (previously only dirt). Telepathy L8 = see inventory.

5. **Power-Has-A-Cost (Glimmer)**: Esper morphotype accumulates Glimmer (danger meter) from mental mutations, attracting psychic assassin hunters. More power = more danger.

6. **Defects as Choices**: Narcolepsy (random sleep in combat), Evil Twin (nemesis hunts you), Amnesia (fog of war returns). Bad mutations should create interesting constraints, not just stat penalties.

## Most NIGRL-Applicable Mutations
- Carapace: DR + blocked slot (implementable now)
- Quills: Passive thorns + activated burst (dual-mode template)
- Adrenal Control: Temporary speed burst (energy system synergy)
- Force Wall: Terrain creation (tactical depth)
- Echolocation/Telepathy: See enemies through walls (FOV extension)
- Corrosive Gas: Equipment degradation (new mechanic)
- Domination: Possess enemies (ambitious but iconic)
- Precognition: Save-state revert (extremely powerful, may be too complex)

## NIGRL's Current System Weakness
Current mutations.py is entirely stat buff/debuff rolls (+/-N to stats, resistance, DR, skill points, lose equipment). No new gameplay verbs, no environmental interaction, no interesting constraints. The proposed overhaul moves toward Qud's model.
