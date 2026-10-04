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
  default. `RETURN_PERIOD_YR` is imported from shaking step 3's `config.py`
  rather than repeated, so the step always reads the PGV grid step 3 wrote.
- The inputs are read in `gen_urban_slope_fragility.main()`: the polygons from
  step 7's `urban_slope_polygons_path()`, each world's drawn walls from
  exposure step 6's `gen_wall_population.drawn_walls_path()` (every wall the
  world drew, before the claim and coverage filters, with `rw_id` null on
  the uninsured ones; the run prints how many are insured), the wall curves from
  the packaged `retaining-wall-fragility.csv` through
  `landloss.hazard.landslide.urban.fragility.load_retaining_wall_fragility()`,
  the site class grid from shaking step 2's `read_site_class()`, step 3's PGV
  grid from `gen_pgv.output_path("pgv", ...)` at `RETURN_PERIOD_YR`, and the
  unscaled TS1170.5 PGA on the same grid built as shaking step 4 builds it
  (`demand_on_site_class_grid(get_ts1170_pga, ...)`). The anchor table is not
  read: the localised median's constants live in the library.
- The fragility rules live in `landloss.hazard.landslide.urban.fragility`, one
  named function per rule, assembled per world by `assign_fragility()`.
- The wall state of a polygon is set by `wall_state()`: a polygon any of whose
  edge lines (step 7's `wall_line_ids`, longest shared edge first) drew a
  sloping-land wall in the world (`drawn_edge_walls()`, joined to the drawn
  walls on `wall_line_id`, at most one wall per line) is in the `fill_wall`
  or `cut_wall` state of its own `wall_position` (the line sharing its
  longest edge, whose geometry step 7 fixed); every other polygon is
  `no_wall`. The lines are split at property boundaries and the polygons are
  not, so one wall along an edge is often several lines, and any of them
  drawing a wall gives the polygon its wall. The polygon takes the `rw_id`,
  size class and condition of the first such line in edge order, written as
  the model's `wall_line_id`, and every edge line that drew a wall is written
  to the model's `wall_line_ids` (empty on a `no_wall` row), so step 9 gives
  each of those walls the polygon's outcome. Whether a polygon has a wall is
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
  never on an edge. `gen_urban_slope_fragility.describe_flatland_walls()`
  prints how many were left out and how many of those sat on an edge, which
  should be zero. The state picks the
  `evacuated`, `inundated` and `imminent` geometry and the
  `depth_evacuated_m` and `depth_inundated_m` off the polygon's state
  columns.
- A polygon with a wall takes the wall curve of the wall's `size_class` and
  `initial_condition` under the one `unnamed` class (`wall_curve()`): the
  published median and dispersion of [koutsoupaki_2023] as the asset README
  records them. A median published on PGA is converted to PGV by
  `pga_to_pgv_theta()` with the PGV/PGA ratio at the polygon's representative
  point, and the published median and the ratio are written to
  `theta_base_pga_g` and `pgv_pga_ratio_m_s_per_g`.
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
  `amp_factor` from step 7 and multiplied by the rate factor of the run's
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
  `tests/landloss/hazard/landslide/urban/test_fragility.py`, which also runs
  the three scripts end to end on synthetic polygons, walls and grids in a
  temporary directory with the basemap tiles faked. The TS1170.5 reader in
  `main()` is faked there too.

Potential future improvements: see `s8_urban_slope_fragility_implementation_plan.md`.
