# Step 9 — Retaining wall damage state: method

- The step decides **which flat-land retaining walls the shaking wrote off**,
  one damage state per wall per exposure world and modelled earthquake. It is
  run by `gen_wall_damage_state.py`, and the fragility is in
  `landloss.vul.shaking.fragility`.
- Walls come from the world's population written by exposure rw step 6, read
  through its `wall_population_path(world_id, pilot=...)`. Step 6 has already
  kept only the walls on insured land and sorted them by claim and location,
  so every row arrives with its `rw_id`.
- **Only walls with `is_flatland` true are drawn here** (`flat_land_walls()`).
  A wall on sloping land stands on the edge of an urban failure polygon and is
  drawn with that polygon by landslide step 9 (`s9_urban_slope_realisation`),
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
- **The intensity measure is PGV.** The earthquake's field is shaking step 5's
  `pgv_path(realisation_id, pilot=...)`, sampled at each wall's **midpoint**
  (`midpoints()`, `landloss.common.utils.terrain.sample_at_points`) and
  written as `pgv_m_s`.
- **The curve is the published wall curve** for the wall's `size_class` and
  `initial_condition`, under the one `unnamed` wall class, read from
  `retaining-wall-fragility.csv` through
  `landloss.hazard.landslide.urban.fragility.load_retaining_wall_fragility()`
  and looked up by `wall_curve()`. `wall_failure_probability()` in
  `landloss.vul.shaking.fragility` evaluates it as a lognormal CDF on PGV with
  no topographic amplification and no rate factor (`WALL_AMP_FACTOR` and
  `WALL_RATE_FACTOR`, both 1.0): a flat-land wall stands on no slope and the
  urban rate setting does not reach it.
- **A curve published on PGA is converted to PGV at the wall's own PGV/PGA
  ratio** (`pga_to_pgv_theta()`): shaking step 3's PGV grid
  (`gen_pgv.output_path("pgv", ...)`) over the unscaled TS1170.5 PGA grid at
  `config.RETURN_PERIOD_YR`, built on the step 2 site class grid exactly as
  shaking step 4 builds it (`demand_on_site_class_grid(get_ts1170_pga, ...)`),
  and sampled at the midpoint by
  `landloss.hazard.landslide.urban.fragility.pgv_pga_ratio_m_s_per_g()`. The
  ratio is the same whichever factor a realisation scaled the grids by, so it
  is built once per run. The site class at the midpoint
  (`sample_site_class()`, from `gen_site_class.site_class_path`) and the ratio
  are written on every row, as `site_class` (nullable integer, null off the
  grid) and `pgv_pga_ratio_m_s_per_g`; a PGV-native curve records NaN for the
  ratio and for `theta_base_pga_g`.
- A wall with no PGV at its midpoint, or on a PGA-published curve with no
  ratio there, carries a NaN `failure_probability` and draws no damage; the
  run prints how many.
- The draw is seeded by `realisation_seed(BASE_SEED, realisation_id,
  "vulnerability", world_id=world_id)` — the vulnerability module's one
  stream, with the world appended, so two worlds' populations draw
  independently and the culverts and bridges step's draws are untouched.
- **The wall line is kept as the geometry**, in the population's CRS
  (EPSG:2193), so the loss table can carry coordinates.
- Output is `temp/vul/wall-damage-state-w<NNN>-r<NNN>[-pilot].geoparquet`
  (`wall_damage_state_path(world_id, realisation_id, pilot=...)`), written
  with `GeoDataFrame.to_parquet()`. Columns, in order, are `realisation_id`,
  `world_id`, `rw_id`, `claim_id`, `asset`, `size_class`, `initial_condition`,
  `height_m`, `length_m`, `is_flatland` (always true), `pgv_m_s`,
  `site_class`, `theta_base_pga_g`, `pgv_pga_ratio_m_s_per_g`, `theta`,
  `beta`, `fragility_source` (the table's `source`, a `doc/references.bib`
  key), `failure_probability`, `damage_state` and `geometry`.
- The run prints, per world and earthquake, the state split, the PGV range,
  the walls off the grid or without a probability, the count of converted
  curves and the ratio range, the median `theta` by size class and condition,
  and the properties carrying a wall to replace.
- The step is exercised end to end on synthetic inputs by
  `tests/landloss/vul/shaking/test_wall_damage_state_step.py`.

Potential future improvements: see `s9_wall_damage_state_implementation_plan.md`.
