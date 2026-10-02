# Step 3 — Landslide land damage: implementation plan

**Status:** Phases 1, 1a and 1b complete. The quantity is measured per world
and earthquake; nothing is priced. The pilot has not been run since the
combined realisation landed.

## Phase 1 — Damaged area and depth per property (complete)

- [x] Intersect the realisation's landslide polygons with the insured land.
- [x] Keep evacuated and inundated ground apart, as the policy does.
- [x] Union the inundated pieces per property rather than summing them, so
      ground two landslides both reached is counted once.
- [x] Carry the depth of the material, weighted by how much of the property
      each landslide contributed.
- [x] Check no property carries more damaged ground of either kind than it has
      insured land, and report it on every run.

## Phase 1a — Loss contract keys and union (complete)

- [x] Key rows on `land_id` from exposure step 5 and carry `claim_id` beside it.
- [x] Write the union of evacuated and inundated ground as `landslide_area_m2`,
      the contract's `land_slide_total_insured_land_area` (**Q-06**).
- [x] Print the union total and the double count the sum would have made.

## Phase 1b — The combined realisation, per world and earthquake (complete)

Contract `.agents/plans/urban-slope-build-contract.md` sections 3.13 and 7.13.

- [x] Read landslide step 9's combined realisation
      (`combined_realisation_path(world_id, realisation_id, extent=...)`), the
      large model's polygons and the urban slope model's together, in place of
      step 1's large-model file.
- [x] Take the land classes from `landloss.hazard.landslide.land_class`
      through `damaged_area`, and ignore the urban model's third class,
      `imminent land`, until **T-45** decides how it is settled
      (`IGNORED_LAND_CLASSES`).
- [x] Loop over `WORLD_IDS` as well as `REALISATION_IDS`, and name the output
      on both, `landslide-land-damage-w<NNN>-r<NNN>[-pilot].parquet`, with
      `world_id` after `realisation_id`.
- [x] Run the step end to end on synthetic inputs in
      `tests/landloss/vul/landslide/land/test_landslide_land_damage_step.py`.
- [ ] Rerun the pilot once exposure step 5 and landslide steps 1 to 9 have
      been run for world 0, and record the counts in the method document.

## Phase 2 — Pricing

- [ ] Obtain the T+T landslip remediation schedule (**L-28**) and attach a rate.
      Volume, not area, is expected to select the rate — a shovel-scale repair
      and an excavator-scale one are different jobs on the same footprint.
- [ ] Decide whether evacuated and inundated ground are priced by the same
      schedule. Reinstating support and clearing debris are different works.
- [ ] Settle how a property carrying both kinds is settled, given they overlap.
- [ ] Settle **T-45**: whether imminent ground behind an urban headscarp is a
      claimable loss, and if so what this step measures for it.

## Phase 3 — Once the hazard is calibrated

- [ ] Rerun when the large landslide size distribution is refitted. The
      realisation currently produces far less damaged ground than the ESNZ
      grid's own expectation, because the size power law is sampled far below
      the scale it was fitted at. Everything this step reports scales directly
      with that, so the areas here are structurally right and numerically not
      to be quoted.
- [ ] Take the large model's inundated footprint from a runout model rather
      than the source ellipse moved downhill, at which point its evacuated and
      inundated depths stop being equal.

## Potential future improvements

- Report the share of each property's insured land that was damaged, not only
  the area. The settlement compares against the value of the damaged land, so
  the fraction is what the loss module ultimately wants.
- Report the damaged area by population (large, urban) as well as in total, so
  the two models' contributions to the land loss can be read apart.
