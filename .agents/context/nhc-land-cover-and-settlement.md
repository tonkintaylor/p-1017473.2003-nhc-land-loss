# How NHC land cover and settlement works

Background captured from the kick-off meeting on 16 September 2026, largely from
John Leeves, who holds the policy knowledge in the team. This is working
understanding, not a legal reading: the exact land cover wording still has to be
confirmed with NHC, and the policy settings NHC wants tested have not yet been
supplied. Treat anything here as provisional until that confirmation lands.

## What the cover attaches to

Cover is triggered by the property owner holding a fire insurance policy on their
dwelling, so it arrives via the dwelling. The cover itself is wider than the
dwelling and extends over the whole property, which is why the model works at
property level rather than dwelling level. A property can carry several dwellings;
insurance still generally responds at the property.

This is the reason the LINZ property ID was preferred as the unique identifier.
It is not the identifier the NHC loss modelling team would choose — they work at
claim level — but it is stable and simple, and it matches the unit that is
actually insured.

## Insured land

Insured land is defined by NHC's current policy and, in practice for this study,
by the 8 metre line from the dwelling. Whether a landslide falls inside that
insured area is one of the key variables, and whether a landslide takes the whole
property or only a corner of it makes a large difference to the cost that
follows.

Driveways matter here out of proportion to their area, because they are where most
retaining walls sit. They are not identified in the LINZ data. The saving grace is
that many properties in the study area are small enough that the 8 metre line
reaches the boundary regardless.

## Retaining walls

The treatment of retaining walls changed between the two Acts, and the change
matters for this study:

- Under the **EQC Act**, walls were settled on an indemnity basis — the
  depreciated value of the wall.
- Under the **NHC Act**, walls are settled on **undepreciated value — what it
  would have cost to build the same wall new, with no deduction for age —
  subject to a sub-cap of $50,000 + GST per dwelling.** An earlier draft of this
  file quoted a flat $25,000; that was wrong. See `### The caps` below and
  `nhi-act-land-cover-explainer.md` for how the sub-cap enters the settlement,
  which is as the lesser of undepreciated value and the sub-cap rather than as a
  ceiling on what is paid.

The consequence is that the physical condition of a wall no longer affects the
settlement. It still affects the probability of failure, and many walls in the
study area are old and would not take much shaking to fail. So condition enters
the model on the hazard side, not the cost side.

Wellington City Council maintains a retaining wall database, but it covers council
walls rather than the privately owned walls this study is concerned with. Council
walls are not irrelevant, though: in the last round of landslides, failures of
council walls supporting roads inundated private property below. That damage is
driven by the cost of clean-up and remediation rather than by land value, which
does not fit the value-based cost logic used elsewhere in the tool.

## Settling damaged land: value or repair, not both

Added from the "Wgtn Land Model" meeting, 21 September 2026.

A damaged-land claim is settled one of two ways, and the choice is made for the
claim as a whole:

- **On value** — the area of damaged or evacuated land multiplied by its market
  value per square metre.
- **On repair** — the cost of bringing the land back to its original state.

**The two routes cannot be mixed within a single claim**: a claimant cannot have
part of the damage repaired and then settle the evacuated land on value. The
model has to make the election per claim rather than per piece of damage.
Whether one property can carry *several* claims, each making its own election,
is not known (**Q-01**).

### The caps

| What | Sub-cap |
| --- | --- |
| Bridges and culverts | $25,000 + GST per dwelling |
| Retaining walls | $50,000 + GST per dwelling |

**Both are exclusive of GST, so GST has to be added to them.**

The multiplier is the **number of dwellings in the residential building** — not
the number of walls, not the number of owners, and not the number of dwellings
on the property. A property with several walls and one dwelling shares one cap;
a site with two residential buildings has **two** caps, worked out separately.

A sub-cap limits the structure's **contribution to the land cover cap**, not the
settlement. The contribution is the *lesser* of the structure's undepreciated
value and the sub-cap, so a modest wall worth less than $50,000 to rebuild
contributes its undepreciated value and the sub-cap never binds. See
`nhi-act-land-cover-explainer.md`, which works three examples.

The **total cap** over the sub-caps should be carried as a variable of the
study rather than a fixed number, since it is one of the policy settings under
test. How the sub-caps interact where a property carries more than one is not
known (**Q-02**).

`nhi-act-land-cover-explainer.md` carries the fuller picture and came from
Bridget Attwood at NHC, so it can be treated as the authoritative account
rather than as working understanding.

### Bridges and culverts

Added from the "Costing tool demo" meeting, 21 September 2026.

For a bridge to be covered at all, **the entire bridge including its abutments
has to sit inside the property**. John Leeves was explicit that this is the
property boundary, not the insured land: if one abutment falls outside the
property, the bridge is not covered even where the span itself is inside.

Damage states are **none or full replacement**, with no partial repair between
them. John's reasoning was that almost every bridge caps out against the
$25,000 sub-cap anyway, so resolving intermediate states would not change the
answer, and there are few enough bridges that the choice barely moves the total.
Bridges on residential property are unusual, and the team expected more culverts
than the area appears to have, there being few large streams (**T-39**).

### Evacuated and inundated land are both damaged land

When land moves downslope it leaves **evacuated** land where it came from and
creates **inundated** land where it comes to rest. Both count, and the damaged
area is the **total footprint** of the two — meaning the union of the two
polygons, not the sum of two areas calculated independently. Where the
evacuated and inundated areas overlap, that ground is counted once.

Repair cost for inundated land is represented by two rates per square metre —
one for volumes a shovel and a truck can clear, one for volumes needing an
excavator — varied by whether the site has access (**L-28**). For the largest
landslides the cost is expected to be over the cap regardless, so the precision
stops mattering.

**Imminent risk is claimable**, and like the total cap it should be carried as a
variable of the study rather than as a fixed rule. How it is represented is
still being worked through (**T-35**).

The "Costing tool demo" meeting on 21 September 2026 settled *why* it has to be
separable. NHC are considering removing the imminent damage provision as part of
moving to a land cap, so they will want to see what removing it does. John
Leeves was clear the study has to carry it for the current scheme to be
comparable with the new one. The conclusion on the call was to model it as its
own line item entering the costing, both so its contribution can be reported and
because the logic for costing it may differ, while starting from the baseline
evacuated and inundated rates.

There are three forms of it, all following the same principle as evacuated and
inundated land: imminent damage of **evacuation**, of **inundation**, and of
**re-inundation**. For evacuation, John expected the study to apply a general
rule rather than model it — the working suggestion was that the scarp regresses
another half a metre on average, or a metre on slopes steeper than 30 degrees,
with the rules to be agreed (**T-44**). Maxim noted from an NHC report that a
site under imminent risk had needed an excavator to peel back the head scarp,
which suggests the cost is higher than for damage that has already occurred.

The settlement logic as a whole is to be written out as pseudo-logic and run
past John Leeves (**T-34**).

## Sub-caps and multiple insured interests

Where a property has multiple land structures, multiple sub-caps apply, and where
several insured interests share land — multi-unit buildings, cross-lease and
shared land — a settlement has to be split between them. NHC asked for this to be
represented because it demonstrates how the policy settings play out in the
hardest cases.

The team has excluded it from the current study on the basis that these properties
are a small proportion of the population, perhaps under 5%, and that no two
multi-unit developments settle the same way. This is a real narrowing of the
brief. The agreed mitigation is to quantify what proportion of the population
falls into the category so the exclusion is evidenced, and to park a dedicated
sub-study for later.

## Open questions

- The exact interpretation of the NHC Act and the land cover wording, to be led by
  John Leeves with Bridget Attwood.
- The specific policy settings NHC wants compared.
