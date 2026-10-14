# Landslide step 6 — Urban slope realisation: method

- The step draws the urban slope failures of one modelled earthquake in one
  exposure world and writes them beside the large-model landslides of that
  earthquake. It is run by `gen_urban_slope_realisation.py`, with the extent,
  worlds and earthquakes set in `config.py`; every pair of a world and an
  earthquake is run.
- **The inputs are read in `read_inputs()`**: the model file landslide step 5 wrote for
  the world (`gen_urban_slope_fragility.urban_slope_model_path`), the wall
  population for the world (`gen_wall_population.wall_population_path`), the
  site PGA field shaking step 4 wrote for the earthquake (`gen_pga_realisations.pga_path`) and the
  large-model realisation landslide step 3 wrote for it
  (`s1_simulate_landslides.realisation_path`).
- **The polygons are landslide step 4's zones of the world's wall draw**
  (since 2026-10-06; see the step 5 method file), not the removed old step 7's
  polygons. A model
  row's "wall line" is its wall unit: `wall_line_id` is the unit's id, the
  id exposure rw step 6 writes on the world's walls, and `wall_line_ids`
  lists that one unit on a walled row. Nothing in this step changed with
  it: the grouping, the outcome join and the geometry read the same columns.
  A unit carries every segment of its element and every element of its
  pifs, so all the polygons on one unit share one uniform and fail together.
  The figure draws each world's realisation, the pipeline's walls; the
  every-walled and none-walled bounds are landslide step 4's
  `fig_wall_zones.py`.
- **The rate setting** landslide step 5 built the model at is printed with its factor
  from the model file's `rate_setting` and `rate_factor` columns
  (`describe_rate_setting()`), so a run log shows which setting produced the
  failures; a model file carrying more than one setting is refused.
- **Site PGA is sampled at each polygon's representative point** by
  `landloss.hazard.landslide.urban.realisation.sample_pga`, the `rep_point`
  column of the model file against the PGA raster; a point off the grid reads
  NaN. Every curve in the model file is on site PGA in g (the project lead,
  2026-10-12; PGV from shaking step 5 until then, with the same outcomes on
  the Porirua pilot, as shaking steps 4 and 5 scale by one factor).
- **Each row's fragility is evaluated and drawn against** in
  `realisation.draw_failures`: the lognormal of contract section 6 on the
  row's own `theta` and `beta` at the sampled PGA, evaluated by
  `landloss.hazard.landslide.urban.fragility.lognormal_failure_probability`,
  gives `p_fail`, and one
  uniform per row is drawn in the model file's order on
  `realisation_seed(BASE_SEED, realisation_id, "urban", world_id=world_id)`.
  A row fails where its uniform is below `p_fail`. A row with no PGA, or
  with no fragility median (`theta` NaN, as on a polygon the fragility step
  could not attach a curve to), has `p_fail` NaN and does not fail; the run
  counts the two causes separately.
- **One uniform per wall line** (contract decision 34). After the per-row
  draw, every row whose `wall_state` is not `no_wall` takes the uniform of
  the first row in model order sharing a wall line with it: a row's lines are
  the model's `wall_line_ids` (the wall unit on a landslide step 4 polygon; on the old step
  7's polygons every line on its edge that drew a wall), and rows are grouped
  by any line they share, transitively. Rows without a wall, or with no line,
  keep their own uniform, so their draws are unchanged. A wall line sits on the edges of polygons at several scales,
  each carrying the same published wall curve; with a uniform each the wall
  would fail through some polygon with probability 1 − Π(1 − p_i) rather
  than the published p (p = 0.3 on four scales gives about 0.76). With one
  shared uniform the wall's polygons fail or stand together where their
  curves agree. The key is the line, not
  `rw_id`, because an uninsured wall has no `rw_id` and is still one wall.
- **If any polygon on a wall fails, the wall has failed and every polygon on
  it fails** (the project lead's rule, 2026-10-02), by
  `realisation._fail_with_the_wall` on the groups `realisation._wall_groups`
  builds. The polygons on one wall differ only in the amplification their
  median is divided by, so with one uniform the wall fails exactly when its
  weakest polygon, the one with the strongest amplification, would. `p_fail` and `uniform` stay each row's own,
  so a row failed through its wall can carry a uniform above its `p_fail`.
- **Every failed polygon is kept** (the project lead, 2026-10-14). There is no
  absorption between urban polygons and no supersession by a large-model
  landslide: the large model's rules apply to urban polygons unchanged, so
  ground two failures share is written twice and counted once downstream, where
  vul landslide land step 3 measures areas on the union of the failures. Until
  then the step absorbed 514 of 2,980 failed Wellington polygons into a larger
  one they overlapped by a median of 4% of their area, and lost 94% of the
  absorbed ground. A polygon that did not fail is `standing` whatever a large
  landslide does around it (contract decision 35): a wall the large landslide
  actually reaches is flagged by vul step 11's intersection of the wall line
  with the combined realisation's `evacuated land`. Landslide step 4's forced
  polygons, which can overlap others, go through the same rule.
  `gen_urban_slope_realisation.realise()` is the draw and nothing more.
- **`realisation.to_landslide_rows`** writes three rows per failed polygon from
  the model file's fixed geometry, one per land class of
  `landloss.hazard.landslide.land_class`: `evacuated land` at
  `depth_evacuated_m`, `inundated land` at `depth_inundated_m` and
  `imminent land` with no depth. `landslide_id` is the `slope_id`,
  `population` is `urban`, `volume_m3` is the evacuated depth times the
  evacuated area and `source_area_m2` the evacuated area; each row carries
  the site PGA (`pga_g`), `p_fail` and the uniform it was drawn with.
- **The combined realisation** is built by `realisation.combine_with_large`:
  the urban rows beside every landslide step 3 row in one schema, the contract columns
  first and landslide step 3's simulation columns after them (null on urban rows),
  sorted by `landslide_id` then `land_class`, with `world_id` and
  `realisation_id` on every row. It is written to
  `temp/hazard/landslide/landslide-realisation-wNNN-rNNN[-pilot].geoparquet`
  from `combined_realisation_path()`. Evacuated polygons may overlap, within the urban population and across the
  two; the run prints how much evacuated ground is covered more than once.
- **The wall outcome table** is built by `realisation.wall_outcomes`, spined
  on the world's wall population filtered to `is_flatland` false and
  left-joined on `wall_line_id` to every model row carrying the wall's line
  in its `wall_line_ids`, so every line of a wall split at a property
  boundary takes the outcome of the polygon on whose edge it lies, and
  `rw_id`, `claim_id` and `wall_line_id` come from the population. A wall whose polygon failed is
  `failed_with_polygon`; otherwise `standing`,
  including a wall whose line's polygon was not delineated, which has
  `slope_id` null and is counted by the run. A wall whose line sits on
  polygons at several scales is `failed_with_polygon` if any of its polygons
  failed (`realisation.OUTCOME_RANK`). `absorbed` and `superseded` stay in
  `realisation.OUTCOMES` so an outcome file from an older run still reads, and
  the `taken_by` column went with them (2026-10-14). It is written to
  `temp/hazard/landslide/urban-wall-outcome-wNNN-rNNN[-pilot].parquet` from
  `urban_wall_outcome_path()`.
- The run prints the world and earthquake ids, the rate setting, the polygons by wall state, the
  polygons not drawn split into those with no fragility median and those off
  the PGA grid (`describe_draw()`), the failed count, the summed, dissolved and overlapping
  areas by population and land class with the evacuated ground covered more
  than once, and the wall outcome counts.
- The draw of one pair is mapped by outcome in the figure produced by
  `fig_urban_slope_realisation.py`, which reads the two files the run wrote
  through `combined_realisation_path()` and `urban_wall_outcome_path()`
  (`read_outputs()`, `outcome_layers()`): the failed urban evacuated
  polygons and the large-model evacuated outlines from the combined
  realisation, over the model file's faces.
  It stops if the run wrote a `slope_id` the model file no longer carries.
  It writes to `report/hazard/landslide/urban-slope-realisation/fig/`.
- `hazard/gen_hazard.py` runs this step last in `main()`, after landslide
  steps 4 and 5, because the urban chain reads the exposure module's wall
  population; `gen_all.py` runs the hazard module in one pass after the ground
  and exposure modules.

Potential future improvements: see `s6_urban_slope_realisation_implementation_plan.md`.
