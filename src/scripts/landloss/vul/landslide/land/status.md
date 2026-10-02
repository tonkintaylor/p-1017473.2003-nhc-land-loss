# Landslide vulnerability, land: status

**Status:** Damaged area and depth per property now run end to end, and are
moved onto the combined large and urban realisation per exposure world and
earthquake, not yet rerun since. Nothing is priced: the repair schedule is not
in the repository.

**Updated:** 2026-10-02

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Read the hazard module's source and runout polygons **separately** and produce
  an outcome per cause, because loss of support and runout are settled
  differently.
- [x] Read the large and urban landslides alike, from landslide step 9's
  combined realisation per exposure world and earthquake, and leave the urban
  model's imminent land unmeasured until **T-45** is decided.
- [x] Work per property against the **insured land polygon**, the 8 m line from the
  dwelling, since that is the extent NHC settles on. The chain runs on
  `claim_id`, the LINZ property from exposure step 5, and each insured land
  polygon carries its own `land_id`.
- [>] Cost the repair from the T+T landslip remediation schedule prepared for EQC
  (`EQCcostestimatesRev10.xlsx`, Rev10, 4 December 2023) rather than from a
  damage ratio alone. The schedule is held in `vul` rather than `loss` so that
  the repair scheme stays beside the landslide geometry that sizes it.
- [ ] Size the works from geometry: wall face area from crown length × scarp height
  within the insured polygon, spoil and backfill volume from the slip volume the
  hazard module already derives by `V = αA^γ`, and reinstatement from the runout
  area.
- [ ] Select the repair scheme as the **cheapest of those feasible** for the
  retained height and slope, so the scheme is a checkable output rather than an
  input assumption.
- [ ] Interpolate between the schedule's "easy" and "difficult" columns on a
  composite index of slope, access distance, distance to a town centre and
  neighbouring buildings — the schedule defines its two ends in those terms.
- [ ] Apply the schedule's per-job items — survey, geotechnical investigation,
  consents, inspections — **once per landslide** and apportion them across the
  claims it crosses. Charged per claim they would dominate every small slip.
- [ ] Settle each claim at the lower of repair cost and insured land value, so land
  that costs more to repair than it is worth is written off rather than repaired.


## Beta build

The damage measure for landslide on land is **geometric, not a damage state**:
intersect the hazard module's evacuated and inundated polygons with the insured
land polygon and keep **the two areas separately**, each carrying the depth of
its parent landslide. Those areas are what the repair cost is computed from.

Inundated polygons can overlap one another today, so this intersect has to
dissolve or otherwise resolve them before summing area, or a property under two
landslides is charged twice. See `.agents/plans/beta-build.md`.

## Loss contract

What this module owes the land table `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply `inundated_insured_area` and `inundated_mean_depth`, written as
  `inundated_area_m2` (unioned) and `inundated_depth_m` (area-weighted).
- [x] Supply `evacuated_area`, written as `evacuated_area_m2`.
- [x] Supply `land_slide_total_insured_land_area`, the union of evacuated and
  inundated ground in the polygon (**Q-06**): vul supplies the union as
  `landslide_area_m2`.
- [x] Carry `claim_id` and coordinates. Step 3 rows carry `land_id` and
  `claim_id`; coordinates come via the s10 land table.

## Where it is now

- `steps/s3_landslide_land_damage/` intersects the combined realisation's
  evacuated and inundated polygons, large and urban, with the insured land and
  writes the area and depth of each kind of damaged ground per property, to
  `temp/vul/landslide-land-damage-wNNN-rNNN[-pilot].parquet`. Inundated
  pieces are unioned rather than summed, so ground two landslides both
  reached is counted once, and the run
  checks that neither kind exceeds the property's own insured area. Rows are
  keyed on `land_id` with `claim_id`, and the union of the two kinds is written
  as `landslide_area_m2`.
- Vul step 10 writes the loss tables per exposure world and earthquake, and
  keeps the deprecated `loss_input_path` resolving world 0 (contract section
  3.15, decision 37, built), so the loss module, which asks per earthquake
  only, reads world 0. Moving its five calls onto worlds is register task
  **T-65**.
- Over the Wellington pilot 37 properties of 4,764 are reached. That number is
  not to be quoted: the hazard realisation currently produces about two orders
  of magnitude less damaged ground than the ESNZ grid's own expectation, because
  the size power law is sampled far below the scale it was fitted at. The shape
  of the output is right and the quantity is not. That run predates the step 1
  rework and the urban model; the step is tested on synthetic inputs since and
  has not been rerun.
- Nothing is priced. The rate schedule has not been brought into the repository;
  it is still a workbook held outside it, alongside the Toka Tū Ake EQC Costing
  Tool v10.42 that applies a different set of square-metre rates to the same
  work.

## Next

1. Flatten Rev10 into a packaged CSV asset under `src/landloss/io/assets/` with
   a reader, cleaning the text-valued cells and the inverted notified resource
   consent row.
2. Confirm the rate basis — Rev10, or the square-metre retaining wall rates in
   the companion costing tool, which do not agree with it.
3. Hold escalation from the December 2023 base and a regional factor off the
   Auckland base as named constants.
4. Refit the landslide size distribution in the hazard module, which everything
   this module reports scales directly with.
5. Add the scheme feasibility table and the cheapest-feasible selection.
6. Add the repair-against-value settlement test, reading the land value rate
   from the exposure module.
7. Rerun over the pilot once landslide step 9 has written the combined
   realisation.

## Validation

- Modelled repair cost against the settled NHC land claims held in
  `vul/assets/`. `vul/research/fig_settled_land_claims.py` already plots
  settlement against cost to repair for that cohort, which is the comparison to
  make. A script under `validations/`.
- The selected repair scheme mapped across the study area, as the check that the
  feasibility rules behave rather than collapsing onto one scheme.

## Open decisions

- **L-15** — land whose settlement is driven by cost of repair rather than land
  value does not fit the value-based cost model. The repair costing above is
  what closes it; it is not closed yet.
- **L-11** — the claim-level identifier. Superseded: the chain runs on the
  upstream `claim_id` from exposure step 5, and `land_id` is per polygon.
- **T-17**, **T-18** — NHC land damage claim costs, needed to validate modelled
  repair costs against settled ones.
- **T-45** — imminent-risk land. The urban model writes it and this step does
  not measure it until the decision is made.
- Holding the cost model in `vul` departs from the module split in
  `.agents/context/code-structure.md`, which puts money in `loss`. This was
  agreed deliberately so the repair scheme stays with the geometry that sizes
  it, and `code-structure.md` needs updating to match.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
