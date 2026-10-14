# Step 11 — Retaining wall landslide damage: method

- The step sets **the three contract flags on each insured retaining wall**,
  per exposure world and modelled earthquake: `is_damaged_by_shaking`,
  `is_evacuated` and `is_inundated`, named in `landloss.domain.loss_contract`.
  It is run by `gen_wall_landslide_damage.py`, and the flags are computed by
  `wall_flags()` in `landloss.vul.landslide.flags`.
- It reads three files, each through its own step's path function:
  - the world's wall population, exposure rw step 6's
    `wall_population_path(world_id, extent=...)`, which is the spine: every
    wall in it, on flat land or on a slope, gets one row;
  - the combined landslide realisation of the world and earthquake,
    landslide step 6's `combined_realisation_path(world_id, realisation_id, extent=...)`,
    the large model's polygons and the urban slope model's together;
  - the urban wall outcome table of the same pair, landslide step 6's
    `urban_wall_outcome_path(world_id, realisation_id, extent=...)`, one row
    per wall on sloping ground with its `slope_id` and `outcome`.
- A sloping wall has **two routes to a flag**, and the two are OR-ed
  (`wall_flags()`):
  - its urban outcome, mapped onto one flag by the dict
    `landloss.vul.landslide.flags.OUTCOME_FLAGS` (`outcome_flags()`):
    `failed_with_polygon` sets `is_damaged_by_shaking`, `absorbed` and
    `superseded` set `is_evacuated`, `standing` sets nothing;
  - its line lying inside any `evacuated land` polygon (`is_evacuated`) or
    `inundated land` polygon (`is_inundated`) of either population, except
    that the wall's own polygon (its outcome's `slope_id`) sets neither flag
    (the lead, 2026-10-13): the wall's line is drawn at the toe of its own face
    and its evacuated polygon is cut at the line, so the wall is that polygon's
    edge and its own deposit runs on below it; its own failure is the outcome
    route's (`failed_with_polygon`). Polygons of other slopes still set both
    flags. Imminent ground sets no flag.
- A polygon reaches a wall only where **a positive length of the line lies
  inside it**: more than `WALL_INSIDE_TOLERANCE_M` (0.01 m) of the line inside
  the polygon shrunk by 0.01 m (`landloss.vul.landslide.flags`). Urban
  polygons tile the ground and wall lines are their edges, so a standing wall
  is often the edge of a neighbouring polygon; a line that only runs along a
  failed neighbour's boundary, or touches it at a point, is not flagged. This
  matches the hazard side, where polygons touching only along an edge share no
  ground (`SHARED_GROUND_TOLERANCE_M2`). Culverts and bridges keep the plain
  intersection of `landslide_flags()`, boundary included.
- A flat-land wall has no outcome row and takes `is_evacuated` and
  `is_inundated` from geometry alone; its `is_damaged_by_shaking` is written
  False here, because its shaking flag is `vul/shaking/rw` step 9's damage
  state, applied when vul step 10 builds the loss table
  (`landloss.vul.loss_input.build_rw_table`). No outcome sets `is_inundated`;
  that flag is geometry's alone.
- `slope_id` and `outcome` are carried on every row from the outcome table,
  null where the wall has no outcome row (a flat-land wall) and `slope_id`
  null where the sloping wall's line drew no polygon (an outcome of
  `standing`). An outcome naming a wall not in the population stops the run.
- **How much of the wall is damaged is measured as well** (T-158, the lead,
  2026-10-14), by `measure_wall_damage()` in `landloss.vul.landslide.flags`,
  called at the end of `wall_flags()`. A wall damaged by shaking (here, by its
  urban outcome) is damaged over its whole line: `damaged_line` is the wall's
  line. A wall carrying `is_evacuated` or `is_inundated` and not that is
  measured: the length of its line inside the **merged** evacuated ground and
  inside the **merged** inundated ground of every failure **other than its own
  polygon** (overlapping failures count a stretch once), with the same
  `WALL_INSIDE_TOLERANCE_M` as the flag (the merged ground is shrunk by 0.01 m,
  so a line along an edge is not damaged and 1 cm or less inside is nothing).
  The damaged line is the part inside evacuated ground alone; **inundated
  ground does not damage a wall**, so a wall only inundated has an empty
  `damaged_line` and 0, and `is_inundated` stays on it for information. An
  `absorbed` or `superseded` wall is measured the same way, from the absorbing
  failure's ground (another polygon); one whose outcome set `is_evacuated` but
  whose line lies in no such ground has 0. A wall damaged in shaking in the
  later shaking step (a flat-land wall) is not known here and vul step 10 takes
  its whole length. A wall carrying no flag is not measured.
- The damage measure is a flag, and a damaged length for a landslide-damaged
  wall. **No cost is attached.** Either damaging flag true means one
  replacement in the loss module; the length is how much of the wall it
  replaces, plus its margin.
- Output is `temp/vul/wall-landslide-damage-w<NNN>-r<NNN>[-pilot].parquet`,
  built by `wall_landslide_damage_path(world_id, realisation_id, extent=...)`,
  one row per wall in population order with the columns `realisation_id`,
  `world_id`, `rw_id`, `claim_id`, `slope_id`, `outcome`,
  `is_damaged_by_shaking`, `is_evacuated`, `is_inundated`,
  `evacuated_length_m`, `inundated_length_m` (information only),
  `damaged_length_m` (the evacuated length, or the whole line for a wall
  damaged by shaking) and `damaged_line` (the geometry that length is of, empty
  where none; the file is a geoparquet in the wall population's CRS with
  `damaged_line` as its geometry). `claim_id` is mapped from the wall
  population on `rw_id`.
- The run prints, per world and earthquake, the realisation's polygons by
  population and land class, the walls on flat and sloping ground, the walls
  with and without an outcome row, the outcome counts, the walls whose polygon
  was not delineated, the count carrying each flag and the count carrying any
  (`describe_landslides()`, `describe_flags()`), then the walls damaged over
  their whole line and over part of it, with the damaged metres, then the walls
  flagged by an absorbed or superseded outcome and how many of those have no
  more than 0.1 m of line inside the ground, which vul s10 clears as undamaged
  (`describe_damage()`).
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/landslide/rw/test_wall_landslide_damage_step.py`.

Potential future improvements: see `s11_wall_landslide_damage_implementation_plan.md`.
