# Step 11 — Retaining wall landslide damage: implementation plan

**Status:** Phases 1 and 2 complete. Every wall carries the three contract
flags per world and earthquake; nothing is priced. The pilot has not been run
since the urban slope chain landed.

## Phase 1 — Evacuated and inundated flags per wall (complete)

- [x] Read the insured wall population from exposure step 6 and the landslide
      realisation from landslide step 3, each through its own step's path function.
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
      landslide step 6.
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

## Phase 2a — How much of the wall is damaged (complete)

Plan `.agents/plans/tweaks-to-property-damage.md` section 6 (T-158).

- [x] Measure, for each wall carrying `is_evacuated` or `is_inundated` and not
      damaged by shaking, the line inside the merged evacuated and merged
      inundated ground of every failure other than its own polygon
      (`measure_wall_damage()`).
- [x] Write `evacuated_length_m`, `inundated_length_m`, `damaged_length_m` and
      `damaged_line`; a wall damaged by shaking takes its whole line, a wall
      only inundated an empty line and 0.
- [x] Measure `absorbed` and `superseded` walls from the absorbing failure's
      ground, as any other.
- [x] Print how many walls flagged by an absorbed or superseded outcome have no
      more than 0.1 m of line inside the ground (`describe_damage()`), to read
      against the walls replaced before, since vul s10 clears them as undamaged.
- [ ] Check after the rerun that the double count against the slip's own new
      wall is not significant (T-158, plan 6.4, a post-rerun check run with
      `research/table_clipped_wall_double_count.py`).

## Phase 3 — Run on the pilot

- [ ] Run over the pilot once exposure rw step 6 and landslide steps 4 to 6
      have been run for world 0, and record the outcome and flag counts in
      the method document.

## Potential future improvements

- Record which polygon reached a flat-land wall (the `landslide_id` of the
  intersecting polygon), as the outcome table's `taken_by` does for sloping
  walls, so a flag can be traced to its cause on the map.
