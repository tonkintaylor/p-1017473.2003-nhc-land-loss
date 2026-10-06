# Step 9 — Urban slope realisation: method

- The step draws the urban slope failures of one modelled earthquake in one
  exposure world and writes them beside the large-model landslides of that
  earthquake. It is run by `gen_urban_slope_realisation.py`, with the extent,
  worlds and earthquakes set in `config.py`; every pair of a world and an
  earthquake is run.
- **The inputs are read in `read_inputs()`**: the model file step 8 wrote for
  the world (`gen_urban_slope_fragility.urban_slope_model_path`), the wall
  population for the world (`gen_wall_population.wall_population_path`), the
  PGV field shaking step 5 wrote for the earthquake (`gen_pgv_realisations.pgv_path`) and the
  large-model realisation step 1 wrote for it
  (`s1_simulate_landslides.realisation_path`).
- **The polygons are landslide step 12's zones of the world's wall draw**
  (since 2026-10-06; step 8 method file), not step 7's polygons. A model
  row's "wall line" is its wall unit: `wall_line_id` is the unit's id, the
  id exposure rw step 6 writes on the world's walls, and `wall_line_ids`
  lists that one unit on a walled row. Nothing in this step changed with
  it: the grouping, the outcome join and the geometry read the same columns.
  A unit carries every segment of its element and every element of its
  pifs, so all the polygons on one unit share one uniform and fail together.
  The figure draws each world's realisation, the pipeline's walls; the
  every-walled and none-walled bounds are step 12's
  `fig_urban_slope_wall_zones.py`.
- **The rate setting** step 8 built the model at is printed with its factor
  from the model file's `rate_setting` and `rate_factor` columns
  (`describe_rate_setting()`), so a run log shows which setting produced the
  failures; a model file carrying more than one setting is refused.
- **PGV is sampled at each polygon's representative point** by
  `landloss.hazard.landslide.urban.realisation.sample_pgv`, the `rep_point`
  column of the model file against the PGV raster; a point off the grid reads
  NaN.
- **Each row's fragility is evaluated and drawn against** in
  `realisation.draw_failures`: the lognormal of contract section 6 on the
  row's own `theta` and `beta` at the sampled PGV, evaluated by
  `landloss.hazard.landslide.urban.fragility.lognormal_failure_probability`,
  gives `p_fail`, and one
  uniform per row is drawn in the model file's order on
  `realisation_seed(BASE_SEED, realisation_id, "urban", world_id=world_id)`.
  A row fails where its uniform is below `p_fail`. A row with no PGV, or
  with no fragility median (`theta` NaN, as on a polygon the fragility step
  could not attach a curve to), has `p_fail` NaN and does not fail; the run
  counts the two causes separately.
- **One uniform per wall line** (contract decision 34). After the per-row
  draw, every row whose `wall_state` is not `no_wall` takes the uniform of
  the first row in model order sharing a wall line with it: a row's lines are
  the model's `wall_line_ids` (the wall unit on a step 12 polygon; on step
  7's polygons every line on its edge that drew a wall), and rows are grouped
  by any line they share, transitively. Rows without a wall, or with no line,
  keep their own uniform, so their draws are unchanged. A wall line sits on the edges of polygons at several scales,
  each carrying the same published wall curve; with a uniform each the wall
  would fail through some polygon with probability 1 − Π(1 − p_i) rather
  than the published p (p = 0.3 on four scales gives about 0.76). With one
  shared uniform the wall's polygons fail or stand together where their
  curves agree, and absorption keeps the largest. The key is the line, not
  `rw_id`, because an uninsured wall has no `rw_id` and is still one wall.
- **If any polygon on a wall fails, the wall has failed and every polygon on
  it fails** (the project lead's rule, 2026-10-02), by
  `realisation._fail_with_the_wall` on the groups `realisation._wall_groups`
  builds. The polygons on one wall differ only in the amplification their
  median is divided by, so with one uniform the wall fails exactly when its
  weakest polygon, the one with the strongest amplification, would; absorption
  then keeps the largest of them. `p_fail` and `uniform` stay each row's own,
  so a row failed through its wall can carry a uniform above its `p_fail`.
- **Two polygons share ground** where their intersection has an area above
  `realisation.SHARED_GROUND_TOLERANCE_M2` (0.01 m2, a numerical tolerance
  against floating-point slivers). Polygons that only touch along an edge or
  at a corner, as neighbouring candidates of one scale always do, share none,
  so contact alone neither absorbs nor supersedes.
- **Supersession is resolved first, on the failed polygons only** (contract
  decision 35). Every failed polygon whose `evacuated` geometry shares ground
  with an `evacuated land` row of the step 1 realisation is superseded by
  `realisation.supersede_by_large`; where several share ground with it, the
  one sharing the most takes it. The result is mapped onto every model row,
  none where the row did not fail. A polygon that did not fail is `standing`
  whatever a large landslide does around it: a wall the large landslide
  actually reaches is flagged `is_evacuated` by vul step 11's intersection of
  the wall line with the combined realisation's `evacuated land`, so a wall is
  replaced only where its line is reached, not where a large slide grazes its
  polygon's headscarp band.
- Step 12's forced polygons (a wall's minimum polygon drawn from its line
  where the label grid could not hold it, 2026-10-07) can overlap other
  polygons; they go through the same rules, so one that fails sharing ground
  with a larger failed polygon is absorbed into it, and the dissolved land
  totals count the shared ground once.
- **Nested failures are then absorbed largest first** by
  `realisation.resolve_overlaps`, on the `evacuated` geometry of the failed
  polygons that were not superseded: worked in descending area, stable on
  ties, a failed polygon sharing ground with a larger surviving one is
  absorbed, and an absorbed polygon absorbs nothing.
  `gen_urban_slope_realisation.realise()` runs the two in that order and maps
  the result back onto every model row. Because a superseded polygon absorbs
  nothing, every absorber is a survivor written to the combined realisation,
  and an absorbed polygon's `taken_by` always names a `landslide_id` that file
  carries.
- **The survivors** are the failed polygons neither absorbed nor superseded.
  `realisation.to_landslide_rows` writes three rows per survivor from the
  model file's fixed geometry, one per land class of
  `landloss.hazard.landslide.land_class`: `evacuated land` at
  `depth_evacuated_m`, `inundated land` at `depth_inundated_m` and
  `imminent land` with no depth. `landslide_id` is the `slope_id`,
  `population` is `urban`, `volume_m3` is the evacuated depth times the
  evacuated area and `source_area_m2` the evacuated area; each row carries
  the PGV, `p_fail` and the uniform it was drawn with.
- **The combined realisation** is built by `realisation.combine_with_large`:
  the urban rows beside every step 1 row in one schema, the contract columns
  first and step 1's simulation columns after them (null on urban rows),
  sorted by `landslide_id` then `land_class`, with `world_id` and
  `realisation_id` on every row. It is written to
  `temp/hazard/landslide/landslide-realisation-wNNN-rNNN[-pilot].geoparquet`
  from `combined_realisation_path()`. Evacuated polygons never overlap across
  the two populations; inundated and imminent polygons may.
- **The wall outcome table** is built by `realisation.wall_outcomes`, spined
  on the world's wall population filtered to `is_flatland` false and
  left-joined on `wall_line_id` to every model row carrying the wall's line
  in its `wall_line_ids`, so every line of a wall split at a property
  boundary takes the outcome of the polygon on whose edge it lies, and
  `rw_id`, `claim_id` and `wall_line_id` come from the population. A wall whose polygon failed and was superseded by a
  large-model landslide is `superseded`; whose polygon failed and survived is
  `failed_with_polygon`;
  whose polygon failed and was absorbed is `absorbed`; otherwise `standing`,
  including a wall whose line's polygon was not delineated, which has
  `slope_id` null and is counted by the run. `taken_by` is the `landslide_id`
  of the polygon that absorbed or superseded it. A wall whose line sits on
  polygons at several scales takes the first of those outcomes any of its
  polygons reached, in that order (`realisation.OUTCOME_RANK`). It is written to
  `temp/hazard/landslide/urban-wall-outcome-wNNN-rNNN[-pilot].parquet` from
  `urban_wall_outcome_path()`.
- The run prints the world and earthquake ids, the rate setting, the polygons by wall state, the
  polygons not drawn split into those with no fragility median and those off
  the PGV grid (`describe_draw()`), the failed, absorbed, superseded and
  surviving counts, the summed and dissolved areas by population and land
  class, and the wall outcome counts.
- The draw of one pair is mapped by outcome in the figure produced by
  `fig_urban_slope_realisation.py`, which reads the two files the run wrote
  through `combined_realisation_path()` and `urban_wall_outcome_path()`
  (`read_outputs()`, `outcome_layers()`): the surviving urban evacuated
  polygons and the large-model evacuated outlines from the combined
  realisation, and the evacuated polygons of the walls' polygons recorded as
  absorbed or superseded from the outcome table, over the model file's faces.
  It stops if the run wrote a `slope_id` the model file no longer carries.
  It writes to `report/hazard/landslide/urban-slope-realisation/fig/`.
- `hazard/gen_hazard.py` runs this step last in `main_urban()`, after steps 7
  and 8, because the urban chain reads the exposure module's wall population;
  `gen_all.py` runs `main_urban()` after the exposure module, and running
  `gen_hazard.py` on its own runs only the first pass, `main()`.

Potential future improvements: see `s9_urban_slope_realisation_implementation_plan.md`.
