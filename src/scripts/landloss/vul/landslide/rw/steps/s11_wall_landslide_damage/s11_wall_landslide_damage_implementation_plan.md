# Step 11 — Retaining wall landslide damage: implementation plan

**Status:** Phases 1 and 2 complete. Every wall carries the three contract
flags per world and earthquake; nothing is priced. The pilot has not been run
since the urban slope chain landed.

## Phase 1 — Evacuated and inundated flags per wall (complete)

- [x] Read the insured wall population from exposure step 6 and the landslide
      realisation from hazard step 1, each through its own step's path function.
- [x] Intersect each wall with the realisation's evacuated and inundated
      polygons and flag it for each kind of ground separately.
- [x] Key the output on `rw_id` and carry `claim_id` from the wall population.
- [x] Print the count of walls, evacuated, inundated and both on every run.

## Phase 2 — The urban slope outcome and the three contract flags (complete)

Contract `.agents/plans/urban-slope-build-contract.md` sections 3.12, 5.2 and
7.13; plan section 5.2.

- [x] Read the wall population per exposure world
      (`wall_population_path(world_id, extent=...)`) and the combined
      realisation and urban wall outcome table per world and earthquake from
      landslide step 9.
- [x] Map each sloping wall's outcome onto a flag by the one dict
      `landloss.vul.landslide.flags.OUTCOME_FLAGS` (`outcome_flags()`), and
      OR it with the geometric intersections (`wall_flags()`).
- [x] Write `is_damaged_by_shaking` from the outcome alone, False for
      flat-land walls, whose shaking flag the loss table takes from
      `vul/shaking/rw` step 9.
- [x] Carry `slope_id` and `outcome` on every row, null where the wall has no
      outcome row.
- [x] Name the output on world and earthquake,
      `wall-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`, with `world_id`
      after `realisation_id`.
- [x] Run the step end to end on synthetic inputs in
      `tests/landloss/vul/landslide/rw/test_wall_landslide_damage_step.py`.
- [x] Flag a wall geometrically only where more than
      `WALL_INSIDE_TOLERANCE_M` of its line lies inside the polygon, so a
      standing wall that is only the edge of a failed neighbouring polygon is
      not replaced (contract section 5.2, plan section 5.2 "the line inside
      any evacuated polygon"); tested in
      `tests/landloss/vul/landslide/test_flags.py`.

## Phase 3 — Run on the pilot

- [ ] Run over the pilot once exposure rw step 6 and landslide steps 7 to 9
      have been run for world 0, and record the outcome and flag counts in
      the method document.

## Potential future improvements

- Flag a wall by the share of its length inside the landslide rather than by
  any intersection, so a wall clipped at one end is not written off whole.
- Record which polygon reached a flat-land wall (the `landslide_id` of the
  intersecting polygon), as the outcome table's `taken_by` does for sloping
  walls, so a flag can be traced to its cause on the map.
