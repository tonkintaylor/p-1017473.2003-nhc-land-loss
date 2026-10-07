# Step 8 — Urban slope fragility: method

- The step gives every urban failure polygon its fragility for one exposure
  world: a lognormal on PGV in m/s, `P(fail | PGV) = Phi(ln(PGV / theta) / beta)`,
  one row per `slope_id`. It is run by `gen_urban_slope_fragility.py`; the
  medians are tabulated by `table_urban_slope_model.py`, written to
  `report/hazard/landslide/urban-slope-model/tab/`, and mapped by
  `fig_urban_slope_model.py`, written to
  `report/hazard/landslide/urban-slope-model/fig/`.
- What a run does is set by `config.py` in the step folder — `EXTENT`,
  `WORLD_IDS`, `URBAN_RATE` and `RETURN_PERIOD_YR` — read in each script's
  `if __name__ == "__main__":` block and passed into `main()` as keyword
  arguments. No script takes command line arguments and no `main()` carries a
  default. `WORLD_IDS` is imported from exposure rw step 6's `config.py`,
  as landslide step 12 imports it, and `RETURN_PERIOD_YR` from shaking step
  3's, rather than repeated, so the step always reads the worlds step 12
  zoned and the PGV grid step 3 wrote. The figure and the table draw each
  world's model, the pipeline's drawn walls; the two whole-scenario bounds,
  every candidate walled and none, are drawn by step 12's
  `fig_urban_slope_wall_zones.py` (its `FIG_ZONE_SCENARIOS`).
- The polygons are landslide step 12's zones of each world's wall draw, not
  step 7's polygons, which the pipeline no longer builds (2026-10-06). Step
  12 draws per world which wall units are walled and builds that world's
  zones with them (`urban-slope-zones-wNNN`); exposure rw step 6 writes the
  same draw as its drawn walls, each wall's `wall_line_id` the unit's id. So
  the wall that holds a slope in the hazard is the wall that is exposed, and
  the old edge-line join, which matched step 7's line ids and none of the
  units, is gone. `read_polygons()` reads a world's zones and turns them into
  one row per polygon with
  `landloss.hazard.landslide.urban.face_polygons.face_polygons()`:
  - the polygon's wall unit is the unit whose `member_pif_ids` holds its
    element's pif (`siz_id`), written as `wall_line_id` and as the one-entry
    `wall_line_ids`; a polygon whose pif is in no unit has neither;
  - `wall_position` is `fill` where the unit `is_fill`, else `cut`;
  - the geometry is the world's own: `evacuated` (also the row's geometry),
    `imminent` and `inundated` (None where the polygon has none), with
    `depth_evacuated_m` the zone's depth and `depth_inundated_m` the
    evacuated volume over the inundated area;
  - the Kingsbury rating is scored by `kingsbury_factors()` with the slope
    the element's `overall_angle_deg`, the height the polygon's `height_m`
    (in the contract's `face_height_10m` column), and the modification,
    geology, prior failure and groundwater of the ground map piece under
    most of the element; an element off the ground map, or on a piece with
    no geology, takes `BETA_OFF_MAP_GROUND` (natural weathered rock, no prior
    failure, 4 m to groundwater; 15% of the pilot's elements);
  - a polygon whose representative point lies outside the extent's box
    (`get_area_of_interest(extent)`) is left out before the ids are minted:
    step 12 grows its elements on a DEM read about 200 m wider than the
    extent, so a face at the edge grows whole, but the site class, PGA and
    PGV grids stop at the extent, so a polygon in that margin has no demand
    (1,406 of world 0's 9,258 pilot polygons on 6 October 2026, which had
    left 1,212 polygons with no failure probability). The full extent keeps
    every polygon, as its DEM stops at the study area;
  - `scale_m` is 1, the grid cell, for every polygon, and the `slope_id` is
    minted per world by location, as each world's zones are built anew;
  - `with_amplification()` reads step 3's 100 m topographic position
    (`terrain_path("topographic-position-100m")`) at the representative
    point into the placeholder amplification.
- Before the join, `face_polygons.check_zones_match_walls()` checks that the
  zones and the drawn walls are one draw: a polygon is walled in the zones
  (its element a `free_face`) exactly where its unit is among the world's
  drawn sloping-land walls. A walled polygon whose unit drew no wall, a bare
  one whose unit did, or a walled one in no unit stops the run with the
  counts and the scripts to rerun, rather than give walled ground a
  localised median or bare ground a wall curve. It replaces the guard that
  stopped the run while the drawn walls named units and the polygons named
  step 7's lines.
- The other inputs are read in `gen_urban_slope_fragility.main()`: step 12's
  elements, wall units and the step 4 ground map once
  (`read_step12_inputs()`), each world's drawn walls from
  exposure step 6's `gen_wall_population.drawn_walls_path()` (every wall the
  world drew, before the claim and coverage filters, with `rw_id` null on
  the uninsured ones; the run prints how many are insured), the wall curves from
  the packaged `retaining-wall-type-fragility.csv` through
  `landloss.hazard.landslide.urban.wall_type_fragility.load_wall_type_fragility()`,
  the site class grid from shaking step 2's `read_site_class()`, step 3's PGV
  grid from `gen_pgv.output_path("pgv", ...)` at `RETURN_PERIOD_YR`, and the
  unscaled TS1170.5 PGA on the same grid built as shaking step 4 builds it
  (`demand_on_site_class_grid(get_ts1170_pga, ...)`). The anchor table is not
  read: the localised median's constants live in the library.
- The fragility rules live in `landloss.hazard.landslide.urban.fragility`, one
  named function per rule, assembled per world by `assign_fragility()`.
- The wall state of a polygon is set by `wall_state()`: a polygon whose
  wall unit drew a sloping-land wall in the world (`drawn_edge_walls()`,
  joined to the drawn walls on `wall_line_id`, at most one wall per unit) is
  in the `fill_wall` or `cut_wall` state of its unit's `wall_position`;
  every other polygon is `no_wall`. The polygon takes the `rw_id`, wall type
  and size class of its unit's wall, written as the model's `wall_line_id`,
  and the unit is written to the model's `wall_line_ids` (empty on a
  `no_wall` row), so step 9 gives the wall the outcome of every polygon on
  it. The same functions still read step 7's polygons, whose edge can carry
  several lines and every state's geometry, for the library tests. Whether a polygon has a wall is
  a match on the edge lines, not a non-null `rw_id`: the claim and coverage filters
  decide what is insured, not whether a wall holds the slope, so an
  uninsured wall (a council or road-reserve wall, or one beyond its claim's
  insured land) gives its polygon the wall state, the wall curve and the
  state's geometry with `rw_id` null (decision 36 of the build contract).
  Step 9 then fails it with its polygon but writes it no wall outcome row,
  because its outcome table spines on the insured population. `sloping_walls()` drops the flat-land walls
  (`is_flatland` true) before the join, so a flat-land wall whose line lies
  on a polygon edge (often along the flatland boundary of the urban domain)
  leaves that polygon `no_wall` with a null `rw_id`: vul shaking rw step 9
  draws a flat-land wall and nowhere else does (contract sections 3.11 and
  5.1); step 7 already records sloping-land lines only, so such a wall is
  never on an edge; the wall units are faces of sloping ground and none is
  flat land. `gen_urban_slope_fragility.describe_flatland_walls()` prints how
  many were left out and how many of those were a polygon's unit, which
  should be zero. The `evacuated`, `inundated` and `imminent` geometry and the
  two depths are the polygon's own, already the world's
  (`fragility._pick_state()` takes a single column where the polygons carry
  one, and the state's column of step 7's polygons otherwise).
- A polygon with a wall takes the curve of the wall's `wall_type` and height
  class (`wall_type_fragility.wall_type_curves()`, given the drawn wall's
  `height_m`): `under_2_m` below 2.0 m or where the height is unknown,
  `2_m_and_over` at 2.0 m and above (the lead, 2026-10-07; until then the
  curve was keyed on `size_class`, which the model file still carries for
  pricing). The median and dispersion run through the stored 15% and 50% PGA
  of `retaining-wall-type-fragility.csv`, read from [koutsoupaki_2023] as the
  asset README records them: gravity masonry, old timber pole, block or RC
  cantilever and landscaper timber take the published height effect switched
  (6 m curve under 2 m, 3 m curve at 2 m and over), and crib, new timber pole
  and engineered modern the 3 m curve for both. The PGA median is scaled by the wall's own
  `wall_position`, 0.85 for a wall retaining fill and 1.15 for a cut
  (`FILL_CAPACITY_FACTOR`, `CUT_CAPACITY_FACTOR`); the wall's position is
  read from the drawn wall, not the polygon's, which sets the wall state and
  can come from another edge line. The scaled median is converted to PGV by
  `pga_to_pgv_theta()` with the PGV/PGA ratio at the polygon's representative
  point, and the scaled PGA median and the ratio are written to
  `theta_base_pga_g` and `pgv_pga_ratio_m_s_per_g`. A drawn wall whose type
  is not in `WALL_TYPES`, or whose type and size have no curve, stops the
  run.
- The ratio is `pgv_pga_ratio_m_s_per_g()`: step 3's PGV grid over the
  unscaled TS1170.5 PGA grid, cell by cell on the site class grid, read at the
  cell each representative point falls in; NaN off the grid. It is
  realisation-free because shaking steps 4 and 5 scale PGA and PGV by one
  factor. The site class at the point is read by `sample_site_class()`
  through `landloss.common.utils.terrain.sample_at_points` and written as a
  nullable integer.
- A polygon without a wall takes the localised median
  `localised_theta_base_m_s()` from its `continuous_rating`: a log-linear fall
  from `LOCALISED_THETA_AT_ZERO_RATING_M_S` at a rating of 0 to
  `LOCALISED_THETA_AT_MAX_RATING_M_S` at the top of the scale, so gentle
  ground takes a very high median rather than being dropped. The two constants
  are placeholders until the anchoring sets them. Its dispersion is
  `landloss.domain.constants.LOCALISED_FRAGILITY_BETA`, and its
  `fragility_source` is `localised:<continuous_rating>`.
- Every median is adjusted by `polygon_theta()`: divided by the polygon's
  `amp_factor` (`with_amplification()`) and multiplied by the rate factor of the run's
  `URBAN_RATE` (`rate_factor()`, from
  `landloss.domain.constants.URBAN_RATE_FACTORS`). The setting and the factor
  are written on every row, and the run prints them.
- The output is written under `temp/hazard/landslide/` to the path
  `urban_slope_model_path()` returns, `urban-slope-model-wNNN-pilot.geoparquet`
  when `EXTENT` is `"wlg-pilot"` and `urban-slope-model-wNNN.geoparquet` when it is `"full"`, with
  the contract's columns in order, `wall_line_ids` after `wall_line_id`, and
  `world_id` inserted after `slope_id` (`add_world_id()`), sorted by `slope_id` with a fresh index, which step 9
  relies on. Every run prints the rate setting and factor, the counts by wall
  state and basis, the median `theta` by zone and state, and the ranges of
  the amplification factor and the ratio (`describe_model()`).
- `table_urban_slope_model.py` groups the model by Kingsbury zone, wall state
  and basis and writes the polygon count, the median base and adjusted
  medians, the median amplification factor, the rate factor and the median
  dispersion (`medians_by_zone_and_state()`); a polygon with no zone is
  grouped under `none`.
- The rules are covered without the network by
  `tests/landloss/hazard/landslide/urban/test_fragility.py`, which also checks
  `face_polygons` and its draw check, and runs the three scripts end to end
  on synthetic step 12 zones, elements and wall units, drawn walls and grids
  in a temporary directory with the basemap tiles faked, and by
  `test_chain_end_to_end.py`, which runs the chain from step 12's files to
  the loss input tables. The TS1170.5 reader in
  `main()` is faked there too.

Potential future improvements: see `s8_urban_slope_fragility_implementation_plan.md`.
