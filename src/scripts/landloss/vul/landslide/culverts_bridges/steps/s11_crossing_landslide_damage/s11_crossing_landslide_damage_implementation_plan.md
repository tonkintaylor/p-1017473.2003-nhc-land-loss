# Step 11 — Crossing landslide damage: implementation plan

**Status:** Phases 1 and 1a complete. The flags are written per world and
earthquake; the pilot has not been rerun against the regenerated crossing
population or the combined realisation.

## Phase 1 — Landslide flags per crossing (complete)

- [x] Read the crossing population and the landslide realisation per
      realisation.
- [x] Flag each crossing `is_evacuated` and `is_inundated` by intersection with
      the evacuated and inundated polygons, through
      `landloss.vul.landslide.flags.landslide_flags()`.
- [x] Key the output on `crossing_id` and carry `claim_id`, for the split into
      culverts and bridges at vul step 10.
- [x] Write an empty file with the full columns when there are no crossings.

## Phase 1a — The combined realisation, per world and earthquake (complete)

Contract `.agents/plans/urban-slope-build-contract.md` section 3.14.

- [x] Read landslide step 6's combined realisation
      (`combined_realisation_path(world_id, realisation_id, extent=...)`) in
      place of landslide step 3's large-model file, so urban failures reach crossings
      too.
- [x] Keep the crossing population keyed on the earthquake alone
      (`crossing_population_path(realisation_id, extent=...)`); moving it to
      worlds is a later item (contract decision 17).
- [x] Loop over `WORLD_IDS` as well as `REALISATION_IDS`, and name the output
      on both, `crossing-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`, with
      `world_id` after `realisation_id`.
- [x] Run the step end to end on synthetic inputs in
      `tests/landloss/vul/landslide/culverts_bridges/test_crossing_landslide_damage_step.py`.

## Phase 2 — Run on regenerated inputs

- [ ] Rerun exposure steps 5 and 7 and landslide steps 1 to 6, then this step,
      and record the counts flagged over the pilot and the full extent.
- [ ] Settle **Q-09**: whether culverts leaving out `is_evacuated` is
      deliberate, and so whether `is_evacuated` stays on the culvert table.

## Potential future improvements

- Flag a crossing only where a meaningful length of it is reached, rather than
  on any intersection, once the landslide footprints are calibrated.
- Draw the crossing population per exposure world, as the walls are, so a
  world is one draw of every structure and the crossing file is keyed on
  `w` like the rest.
