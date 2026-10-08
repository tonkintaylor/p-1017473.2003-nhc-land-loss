# Culverts and bridges, landslide: status

**Status:** The step that flags each crossing per exposure world and
earthquake against the combined large and urban realisation is built and has
run only in its tests, on synthetic inputs; no real combined realisation exists
yet for it to run against. Nothing is priced here: the flags are what the loss
module prices.

**Updated:** 2026-10-02

## Approach

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Flag each insured crossing `is_evacuated` or `is_inundated` where it
  intersects the hazard module's evacuated or inundated polygons, since a
  structure is settled on whether a landslide reached it rather than on an area.

## Loss contract

What this module owes the culvert and bridge tables `loss` reads, as set in
`.agents/plans/asset-pricing-approach.md` section 1.

Marks: `[x]` done, `[~]` partly done, `[>]` next, `[ ]` planned.

- [x] Supply `is_evacuated`. Written for culverts as well as bridges; culverts
  carry it as an extra column pending **Q-09**.
- [x] Supply `is_inundated`.
- [x] Key on `crossing_id` and carry `claim_id`; the split into `culvert_id` and
  `bridge_id` happens at vul step 10.

## Where it is now

- `steps/s11_crossing_landslide_damage/` reads the crossing population per
  earthquake and landslide step 6's combined realisation per exposure world and
  earthquake, and writes both flags for every crossing to
  `temp/vul/crossing-landslide-damage-wNNN-rNNN[-pilot].parquet`. The crossing
  population stays keyed on the earthquake in this build. It has not been run
  against a regenerated crossing population, and the pilot box currently
  carries no crossings.

## Next

1. Rerun exposure steps 5 and 7, then this step after landslide step 6.
2. Move the crossing population onto exposure worlds, a later item of the urban
   build.

## Validation

Not yet defined.

## Open decisions

- **Q-09** — whether the contract leaving `is_evacuated` off culverts, while
  bridges carry it, is deliberate.

Step-level detail lives in each step's implementation plan and method file under
`steps/`.
