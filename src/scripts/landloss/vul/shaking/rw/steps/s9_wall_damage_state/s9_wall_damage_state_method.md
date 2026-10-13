# Step 9 — Retaining wall damage state: method

- The step decides **which flat-land retaining walls the shaking wrote off**,
  one damage state per wall per exposure world and modelled earthquake. It is
  run by `gen_wall_damage_state.py`, and the fragility is in
  `landloss.vul.shaking.fragility`.
- Walls come from the world's population written by exposure rw step 6, read
  through its `wall_population_path(world_id, extent=...)`. Step 6 has already
  kept only the walls on insured land and sorted them by claim and location,
  so every row arrives with its `rw_id`.
- **Only walls with `is_flatland` true are drawn here** (`flat_land_walls()`).
  A wall on sloping land stands on the edge of an urban failure polygon and is
  drawn with that polygon by landslide step 6 (`s6_urban_slope_realisation`),
  so drawing it here too would fail it twice; a flat-land wall has no polygon
  and is drawn here and nowhere else. The run prints the flat-land share of the
  population.
- **`rw_id` and `claim_id` are carried unchanged** from the population, under
  the names `RW_ID_COLUMN` and `CLAIM_ID_COLUMN` from
  `landloss.domain.loss_contract`. Rows stay in population order, so the draw a
  wall receives is fixed by its position in step 6's sorted output.
- **Two damage states only, no damage and replace.** Repair is not modelled
  because very few damaged walls are repaired in practice, so a third state
  would carry almost nothing.
- A damage state is a **draw against a probability of failure**, never a
  threshold on ground motion. The fragility returns that probability because
  that is what a fragility curve is: nominally identical walls differ in
  capacity and respond variably to the same shaking, and the curve is the
  distribution of that difference.
- **The intensity measure is site PGA** (the project lead, 2026-10-12, as
  for the urban slope model; PGV until then). The earthquake's field is
  shaking step 4's `pga_path(realisation_id, extent=...)`, sampled at each
  wall's **midpoint** (`midpoints()`,
  `landloss.common.utils.terrain.sample_at_points`) and written as `pga_g`.
- **The curve is the wall type curve** for the wall's `wall_type` and height
  class, `under_2_m` (`height_m` below 2.0 m, or unknown) or `2_m_and_over`
  (the lead, 2026-10-07; `size_class` until then, still carried for pricing),
  read from `retaining-wall-type-fragility.csv` through
  `landloss.hazard.landslide.urban.wall_type_fragility.load_wall_type_fragility()`
  and looked up by `wall_type_curves()`, which scales the PGA median by the
  wall's `wall_position`: 0.85 for a wall retaining fill, 1.15 for a cut, and
  unchanged where the position is unknown. `wall_failure_probability()` in
  `landloss.vul.shaking.fragility` evaluates it as a lognormal CDF on site
  PGA, the measure the curves are published on, with
  no topographic amplification and no rate factor (`WALL_AMP_FACTOR` and
  `WALL_RATE_FACTOR`, both 1.0): a flat-land wall stands on no slope and the
  urban rate setting does not reach it.
- **No conversion is made.** The position-scaled PGA median is written as
  `theta_base`, and the site class at the midpoint (`sample_site_class()`,
  from `gen_site_class.site_class_path`) as `site_class` (nullable integer,
  null off the grid), for the record.
- A wall with no PGA at its midpoint carries a NaN `failure_probability` and draws no damage; the
  run prints how many.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "vulnerability", world_id=world_id)` — the vulnerability module's one
  stream, with the world appended, so two worlds' populations draw
  independently and the culverts and bridges step's draws are untouched.
- **The wall line is kept as the geometry**, in the population's CRS
  (EPSG:2193), so the loss table can carry coordinates.
- Output is `temp/vul/wall-damage-state-w<NNN>-r<NNN>[-pilot].geoparquet`
  (`wall_damage_state_path(world_id, realisation_id, extent=...)`), written
  with `GeoDataFrame.to_parquet()`. Columns, in order, are `realisation_id`,
  `world_id`, `rw_id`, `claim_id`, `asset`, `size_class`, `wall_type`,
  `age_bin`, `wall_position`, `height_m`, `length_m`, `is_flatland` (always
  true), `pga_g`, `site_class`, `theta_base`, `theta`,
  `beta`, `fragility_source` (the table's `source`, a `doc/references.bib`
  key), `failure_probability`, `damage_state` and `geometry`.
- The run prints, per world and earthquake, the state split, the site PGA
  range, the walls off the grid or without a probability, the median `theta`
  by wall type and height class,
  and the properties carrying a wall to replace.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/shaking/test_wall_damage_state_step.py`.

Potential future improvements: see `s9_wall_damage_state_implementation_plan.md`.
