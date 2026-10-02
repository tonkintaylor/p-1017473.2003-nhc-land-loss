# Step 6 — Retaining wall population: method

The step is three scripts run in order: `gen_wall_lines.py` writes the
candidate wall lines, `gen_wall_probability.py` puts a probability on each,
and `gen_wall_population.py` draws one population per exposure world.

## The candidate lines (`gen_wall_lines.py`)

- `gen_wall_lines.py` writes the **candidate wall lines**, one row per place a
  wall could stand and no probability, to `temp/exposure/wall-lines[-pilot].geoparquet`
  from `wall_lines_path()`. The rules are in `landloss.exposure.rw.lines` and
  run in `build_wall_lines()`; the ids are minted in `mint_wall_line_ids()` by
  location (`sort_by_point`, `mint_ids`, prefix `WALL_LINE_ID_PREFIX`), so a
  rerun over the same extent reproduces them and a changed extent renumbers.
- The sources, in the precedence order of `lines.SOURCES`: the GNS SLIDE
  mapped retaining walls (`mapped_wall_lines`, `Type` `MAPPED_WALL_TYPE`), the
  SLIDE cut/fill lines (`slide_cut_fill_lines`, `CUT_FILL_LINE_TYPE`), the
  edges of the SLIDE genesis cut slopes and fill bodies (`genesis_edge_lines`),
  terrain breaks (`terrain_break_lines`: the downhill shared edge between a
  finest-scale urban slope candidate in a band at or above
  `TERRAIN_BREAK_STEEP_DEG` with `face_height_5m` of at least
  `MIN_WALL_HEIGHT_M` and a neighbour in a band at or below
  `TERRAIN_BREAK_GENTLE_DEG`), and the claim property boundaries
  (`boundary_lines`, noded and merged so a shared boundary is one line) split
  into road frontages within `config.ROAD_FRONTAGE_DISTANCE_M` of a road
  centreline and the rest, kept only where the 10 m slope at the midpoint is at
  least `MIN_SLOPING_GROUND_DEG` and within `URBAN_BUILDING_DISTANCE_M` of a
  building outline. Driveway edges are not a source.
- The GNS SLIDE and LINZ layers are read in `read_layers()` over the extent
  from `gen_multiscale_slope.resolve_extent` grown by `LAYER_MARGIN_M` on every
  side, so a property or wall across the edge of the extent is split at its
  real boundary rather than at the box. After `build_wall_lines()` returns,
  `drop_off_extent()` drops every line whose midpoint lies outside that extent,
  where landslide steps 3, 4 and 6 wrote nothing, and the run prints how many
  went.
- The mapped walls are snapped vertex by vertex onto the nearest candidate
  polygon edge within `delineation.SNAP_TOLERANCE_M` (`snap_to_candidate_edges`);
  the run prints how many moved. Lines from several sources within that
  tolerance of one another over more than half their length collapse into the
  one of highest precedence, which is marked `is_mapped_wall` where any member
  was a mapped wall (`collapse_coincident`). Every line is then split where it
  crosses a claim property boundary (`split_at_boundaries`); a line running
  along a boundary is not cut by it.
- **A property boundary, a road frontage, a SLIDE cut/fill line or a SLIDE
  cut or fill edge is a candidate only where the 1 m DEM steps across it**
  (the project lead's rule of 2026-10-02; `STEP_TESTED_SOURCES`). A boundary
  is where a wall often is and an earthwork edge is where ground was cut or
  filled, but only a step says a wall is there. The GNS mapped walls are
  observed and not tested, and the terrain breaks are steps by construction.
  The step at a sample (`step_height_m()`, `_station_steps()`) is the rise
  across 3 m (`STEP_NEAR_M` each side) against the rise across 9 m
  (`STEP_FAR_M`), `(3 x short - long) / 2`, square to the line, which is zero
  on an even hillside and the height of a step at the line; samples are
  `FACE_SAMPLE_SPACING_M` apart. `keep_stepped_parts()` then **trims each
  tested line to the stretches where the step reaches `MIN_WALL_HEIGHT_M`**,
  bridging any dip no longer than `MAX_STEP_GAP_M` and keeping stretches of
  at least `MIN_STEP_RUN_M`, both 3 m, the width of the short span. Each
  stretch is a line of its own and its face height is its median step. A
  boundary stepped along half its length keeps that half.
- Over the pilot on 2026-10-02 (rerun into a scratch folder, not yet through
  the chain), by source:

  | Source | No step test | Whole line, median step | Trimmed (as built) |
  | --- | --- | --- | --- |
  | Property boundary | 4,540 lines, 110 km | 1,574, 34.3 km | 4,494, 47.5 km |
  | Road frontage | 226 | 76, 2.4 km | 290, 3.6 km |
  | SLIDE cut edge | 380, 19.2 km | not tested | 658, 12.7 km |
  | SLIDE fill edge | 315, 12.1 km | not tested | 466, 6.3 km |
  | SLIDE cut/fill line | 104, 3.2 km | not tested | 147, 1.9 km |
  | All candidates | 8,342 | 5,226, 99.3 km | 8,832, 100.0 km |

  Most sloping boundaries step somewhere along their length, so trimming
  keeps more boundary length than the whole-line median did, in shorter
  pieces (median 8 m). A 1 m gap and a 2 m run gave 6,574 boundary lines, 28%
  under 3 m: one wall broken into several wherever its height dipped. The
  claims with a candidate carry three on average, two at the median. With the
  whole-line test, the share of sloping boundaries running along the contour
  rose from 37% to 49%.
- `face_height_m` on every other line is the median of the `face-height-5m`
  terrain derivative read every `FACE_SAMPLE_SPACING_M` along it
  (`face_height_m()`); local relief reads high on any hillside, wall or not,
  which is why the boundaries and edges take the step instead. Lines under
  `MIN_WALL_HEIGHT_M` are dropped below unless a wall is mapped there. And
  `size_class` follows from it by `classify_wall_size` on the boundaries in
  `landloss.exposure.rw.beta_population` (small below `SMALL_MAX_HEIGHT_M`,
  medium below `MEDIUM_MAX_HEIGHT_M`, large above). `slope_degrees` and
  `aspect_degrees` are the 3 m slope and downhill azimuth at the midpoint.
- `wall_position` is `fill` where the `cut-fill-residual-30m` derivative read
  `POSITION_PROBE_DISTANCE_M` uphill of the midpoint is at or above zero and
  `cut` otherwise (`wall_position()`).
- `claim_id` is the claim property (`build_claim_properties` on the LINZ
  property boundaries, read in `read_layers()`) containing the midpoint. A line
  lying along a boundary takes the property on its uphill side for a fill wall
  and its downhill side for a cut wall, read twice the snap tolerance from the
  midpoint along the azimuth (`assign_claim`). It is null on road reserve and
  outside every claim property; `gen_wall_population.py` is what drops those.
- `ground_id`, `material`, `modification` and `is_flatland` are the ground map
  polygon at the midpoint; `is_rock_cut` is a `lines.ROCK_MATERIALS` material
  with `modification` `cut`. Off the ground map the material and modification
  are `unknown` and the line is not on flat land.
- Lines whose face is under `MIN_WALL_HEIGHT_M` are dropped, except where a
  GNS mapped wall lies along them, which are kept and classed `small`: the 1 m
  grid cannot resolve a sub-metre wall and the mapping is evidence one exists.
  `dwelling_age_decade` is null on every line, because no age source is held.
- The run prints the line count and length by source, size class and wall
  position, the share with a claim and the share on flat land, and
  `fig_wall_lines.py` draws the lines by source with the length per source by
  size class, to `report/exposure/rw/wall-lines/fig/`.

## The probability on each line (`gen_wall_probability.py`)

- `gen_wall_probability.py` reads the lines from `wall_lines_path()` and
  nothing else: no elevation model, no GNS layer, no dwelling age parquet (none
  is held) and no count bounds (**T-50**, not yet held). It writes every line
  column plus `p_wall`, `p_wall_basis`, `p_poor` and `p_poor_basis`
  (`wall_probability.PROBABILITY_COLUMNS`) to
  `temp/exposure/wall-probability[-pilot].geoparquet` from
  `wall_probability_path()`, one row per `wall_line_id`, through
  `landloss.exposure.rw.wall_probability.wall_probability_table`.
- `p_wall` is set by `line_wall_probability` in this order: the prior of the
  line's source, `BETA_SOURCE_PROBABILITY`, highest for a mapped wall and
  lowest for a property boundary; multiplied by `BETA_ROCK_CUT_FACTOR` where
  `is_rock_cut`, because a rock cut stands unsupported and is claimed for
  spalling or slides rather than wall failure; capped at
  `BETA_FLATLAND_MAX_PROBABILITY` where `is_flatland`; and raised to at least
  `BETA_MAPPED_WALL_PROBABILITY` where `is_mapped_wall`. `p_wall_basis` is the
  last rule that changed the value: `source_prior`, `rock_cut`,
  `flatland_cap` or `mapped`.
- **The mapping is one-sided.** GNS mapped only the walls visible from above
  and only in Wellington City [townsend_2020], so a mapped wall raises a line's
  probability and the absence of one changes nothing. Slope, height, wall
  position and subdivision age do not enter `p_wall` in this build.
- `p_poor` is set by `poor_condition_probability`: `BETA_POOR_SHARE` by
  default (`p_poor_basis` `default`); `BETA_UNCONSENTED_POOR_SHARE` where
  `face_height_m` is under `UNCONSENTED_WALL_HEIGHT_M`, because such walls
  are often built without consent (`height`); and where `dwelling_age_decade`
  is held it overrides both, `BETA_PRE_1990_POOR_SHARE` for a decade before
  `BUILDING_ACT_DECADE` and `BETA_POST_1990_POOR_SHARE` from it on (`age`).
  No age is held in this build, so every line's basis is `default` or
  `height`. Wall type is not known on a line and does not enter.
- The count bounds hook is `apply_count_bounds`: given a minimum and maximum
  number of walls per claim, it scales the probabilities inside each claim by
  one factor so the expected count sits within the bounds, never above 1 per
  line, with lines at zero sharing the minimum equally. No bounds file is read,
  so the script does not call it.
- Every number in `wall_probability.py` carries a `BETA_` prefix because it is
  judgement standing in for the claim report extraction. The run prints the
  expected number of walls, `p_wall` quantiles, and the line count and
  expected walls by source, by `p_wall_basis`, by size class and by
  `p_poor_basis`, and ends by saying plainly that the result is not evidence
  about Wellington.

## The draw per exposure world (`gen_wall_population.py`)

- `gen_wall_population.py` reads the probabilities from
  `wall_probability_path()` and the insured land from step 5's
  `insured_land_path()`, and writes one file per world,
  `temp/exposure/wall-population-wNNN[-pilot].geoparquet` from
  `wall_population_path(world_id, pilot=...)`. The worlds come from
  `config.WORLD_IDS`.
- Each world is seeded by `realisation_seed(EXPOSURE_BASE_SEED, world_id,
  "exposure")`: on the exposure seed and the world id, not on any earthquake,
  because whether a wall exists is not something the earthquake decides, so
  one world pairs with every hazard realisation
  (`landloss.hazard.realisation`).
- `landloss.exposure.rw.population.draw_wall_population` draws two uniforms
  per line in line order, the first against `p_wall` and the second against
  `p_poor`: a wall exists where the first is below `p_wall` and is `poor`
  where the second is below `p_poor`, else `modern`. A wall is the line that
  drew it: `height_m` is the line's `face_height_m`, and `size_class`,
  `length_m`, `wall_position`, `is_flatland`, `source`, `material` and the
  geometry are copied from the line (`population.POPULATION_COLUMNS`).
  Nothing is placed or sized in the draw.
- After the draw, so the random stream is the same whatever is kept: lines
  with no `claim_id` are dropped, because council and road-reserve walls are
  out of scope (**I-05**); then
  `landloss.exposure.coverage.keep_walls_on_insured_land` keeps a wall only
  if its line intersects its own claim's insured land polygon buffered by
  `RW_COVERAGE_BUFFER_M` (2 m). Lying on another claim's land does not count.
- **Each kept wall gets an `rw_id`** of the form `<claim_id>-RW<nn>`, numbered
  from 01 within its claim, by `landloss.exposure.asset_ids.mint_asset_ids`
  with `RW_ID_SUFFIX`, on walls ordered by `sort_by_location` (claim, then the
  x and y of the line's representative point), so it is stable within a world
  and does not depend on row order. `world_id` is written beside
  `wall_line_id`, which the wall carries so the urban slope polygons of
  landslide step 7 can find the wall on their edge.
- The output columns are `rw_id`, `claim_id`, `wall_line_id`, `world_id`,
  `size_class`, `initial_condition`, `height_m`, `length_m`, `wall_position`,
  `is_flatland`, `source`, `material` and the line geometry. `height_m` is the
  DEM face height from `MIN_WALL_HEIGHT_M` upward and unbounded above, so the
  size ranges are 0.5–1.0, 1.0–2.5 and 2.5+ m; the set heights the loss
  module prices at stand until the loss owner re-confirms them (**I-14**), and
  `height_m` is not handed to `loss` in this build.
- **Every drawn wall is written too.** The claim and coverage filters decide
  what is insured, not whether a wall stands: a council or road-reserve wall
  above or below a property, or a wall at the back of a section more than
  `RW_COVERAGE_BUFFER_M` from the insured land, still holds its slope in the
  world. So in the same world loop, after `rw_id` is minted,
  `landloss.exposure.rw.population.attach_rw_ids` joins the minted `rw_id`
  back onto every wall `draw_wall_population` returned, by `wall_line_id`,
  and the run writes the result to
  `temp/exposure/drawn-walls-wNNN[-pilot].geoparquet` from
  `drawn_walls_path(world_id, pilot=...)`: one row per line that drew a wall,
  in line order, `wall_line_id` unique, with the population file's columns in
  the same order and `rw_id` and `claim_id` nullable. `rw_id` is null for a
  claimless wall and for one off its claim's insured land. The draw and the
  stream are unchanged, and `wall_population_path()` stays the insured subset
  that vul and loss read; landslide step 8 reads the drawn walls and nothing
  else does (decision 36 of the build contract).
- The run prints the world id and stream, the walls drawn over the lines
  offered against the expected count, the claim and coverage counts kept and
  dropped, `describe_population()` by size class and condition, the share on
  flat land, the count by wall position and the height deciles by size class,
  the count of drawn walls and how many carry an `rw_id`
  (`describe_drawn_walls()`), and ends by saying plainly that the result is
  not evidence about Wellington.
- `gen_exposure.py` runs the three scripts in this order after the insured
  land and dwellings steps, over `exposure/config.py`'s `PILOT` and
  `WORLD_IDS`; the lines read landslide steps 3, 4 and 6, so the hazard module
  runs first.

Potential future improvements: see `s6_wall_population_implementation_plan.md`.
