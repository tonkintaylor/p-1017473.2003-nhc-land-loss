# Step 1 — Settlement: method

- The step writes **what NHC pays on each claim**, per realisation, to
  `temp/loss/settlement-r<nnn>[-pilot].parquet`. Step 0 builds the cap; this
  step builds the repair cost and calls `landloss.loss.settlement.settle()`,
  which pays `min(repair cost, cap)` less the excess.
- It re-derives the cap through `settle()` and **checks it against step 0's**,
  printing the worst disagreement. Two independent paths to the same number is
  cheaper than trusting one.

## Where the repair cost comes from

Every line rests on an assumption, and each is named here rather than buried.

- **A damaged retaining wall** is replaced: rate × face area × (1 + site
  multiplier) × (1 + specification uplift). It is rebuilt as a timber pole wall
  on the pile its height calls for, whatever failed -- brick, stone, stacked
  blocks, crib, old poured concrete, garden timber -- except that a concrete
  block wall goes back as concrete block (**T-122**, 2026-10-07 and
  2026-10-12). Sprayed concrete would also go back in kind, but no wall type is
  sprayed concrete yet (**T-119**). Face area is `rw_height` by `rw_length`, or
  the taller and longer wall a slip on the claim needs. Undepreciated value, in
  step 0, stays at the failed type's rate.
- **One wall per slip** (**T-124**, 2026-10-13). `vul` lists each landslide
  that reached a property, and the retaining wall it failed with, if any. A
  slip that came with a wall is held by that wall's replacement; **every other
  slip gets a new wall of its own**, even on a property whose wall failed
  elsewhere, because two separate failures want two walls. The same slip is
  never charged both a replacement and a new wall — doing so priced one
  structure twice (2026-09-29). A slip across two of a claim's polygons is one
  slip. A wall split across properties holds its slip on each property it
  stands on. A land table from before the lists were written pools each
  claim's ground as one slip, held as before: by the claim's largest damaged
  wall, or by one new wall.
- **A replacement is never smaller than the wall it replaces, but its slip
  can make it larger** (2026-09-30). The wall the slip would need is sized as
  below, and the replacement takes the larger size class and the longer length
  of the two. Each wall is sized against its own slip only. Concrete stays
  concrete; a timber wall takes the pile its new height calls for. UDV stays on
  the wall as it was.
- **A slip no damaged wall holds** is repaired by building a wall that was
  never there. Its size comes from
  `classify_landslide_wall_size()`, on the damaged area and — where an
  inundated depth makes one available — the volume, taking the **larger** of
  the two classes. Its length follows the **width of the failure**: ground goes
  as a strip twice as wide as it is deep, plus a 2 m margin at each end, floored
  at a 5 m minimum below which nobody mobilises
  (`MIN_LANDSLIDE_WALL_LENGTH_M`). That floor is what stops the
  pilot's many small slips -- a median of 17 m2 -- pricing at almost nothing.
  The size bands were set at 10 m2 and 100 m2 on the reasoning that ground which
  has failed is not retained by a garden edge.
- **Liquefaction land damage** carries its own Canterbury settled cost, which
  `vul` now sends through the contract as `Liq_LD_cost_excl_gst_nzd`. It is
  grossed up for GST here and added on top, being a different mechanism from
  the ground a landslide took.
- **A damaged culvert or bridge** is priced on its own, and a claim's are summed
  (John Leeves, 2026-10-13; `landloss.loss.claims.crossing_costs_by_claim`):
  - **replaced** at $15,000 a lineal metre of span, over a 5 m default since no
    span is supplied ($75,000 excluding GST), where liquefaction broke it (vul
    step 9, T-36) or a landslide took the ground it stands on;
  - **cleared** for $1,000 excluding GST where a landslide only buried it. A
    crossing both broken and buried is replaced, which includes the clearing.
  - Culverts and bridges are priced alike. Its undepreciated value is its
    replacement cost, which goes to the cap through the $25,000 sub-cap, so a
    cleared crossing's $1,000 is always within its cover. Every crossing `vul`
    sends is wholly inside insured land.

## The invented wall is a cost, never an asset

A wall that never existed has no undepreciated value, so it reaches the repair
cost and **never the cap**. The undepreciated value handed to `settle()` is the
real walls' alone, taken from what step 0 priced. Adding the invented wall to
the cap as well would raise the ceiling using the very thing being paid for.

## The three site ratings are proxies

None of the three is measured. All are defined in `landloss.loss.pricing` with
their bands marked as invented.

| Rating | Proxy | Taken as |
| --- | --- | --- |
| `construction_access` | driveway length (exposure) | the **longest** driveway on the claim |
| `constructability_reinstatement` | ground slope (exposure) | the **steepest** address on the claim |
| `earthworks_required` | inundated volume (contract) | summed over the claim's polygons |

- The worst case is taken where a claim has several driveways or addresses.
- **A claim with no driveway routed and no address matched rates easy on both**,
  which flatters it; nothing distinguishes that from a genuinely easy site.
- Slope is sampled at the address, not at the wall.
- What bounds the risk: each rating adds at most 0.10 to the multiplier and the
  three cap at 0.30, so the whole proxy can move a wall's cost by 30% at the
  outside — against the factor of 21 the construction type spans. A test
  asserts that ceiling.

## Reading the output

- **`capped` is true of almost every claim with no damaged land, by
  construction.** There the cap is the wall's undepreciated value and the repair
  cost is that same value times one plus the multiplier, so the cap is below it
  whenever the multiplier is above zero. The run prints the split; read the
  count *with* damaged land as the real one.
- Claims whose damage is entirely taken by the excess are counted rather than
  silently settled at zero.

## Known wrongness, carried deliberately

- **The liquefied land the cap values is drawn, not observed.** Its evacuated
  and inundated areas come from judgement ranges per state (**L-39**) and their
  overlap from an assumption (**L-44**). It replaced the whole insured area on
  2026-10-02 (**T-56**), which valued a whole section for a $500 Minor repair.
  The cap still rarely binds on liquefaction, because the Canterbury costs it
  is compared against run $200 to $4,000 a property.
- **The Canterbury costs are 2010/2011 dollars and are not inflated**, only
  grossed up for GST. They are compared against land values and wall rates in
  today's dollars. Nothing in the repository supplies an index to correct it.
- Each wall type's costing tool row is a mapping, two of whose rows await the
  lead, and the timber pole height bands are assumed.
- **T-27**: the Canterbury rates may already include retaining wall damage, in
  which case a claim carrying both a liquefaction state and a damaged wall is
  charged for the wall twice. 107 pilot claims carry both.
