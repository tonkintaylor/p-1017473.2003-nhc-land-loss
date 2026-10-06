# Step 6 — Retaining wall population: method

The step is four scripts. `gen_wall_lines.py` writes the candidate wall
lines, which landslide step 7 reads. `gen_wall_probability.py` reads the wall
units landslide step 12 builds on the pifs, with their probability, and puts a
claim on each; `gen_wall_age.py` puts a share per age bin on every property;
`gen_wall_population.py` draws one population per exposure world from them,
taking which units are walls from step 12's draw for that world and drawing
each wall's age bin and type.

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
  `dwelling_age_decade` is null on every line and nothing reads it.
- The run prints the line count and length by source, size class and wall
  position, the share with a claim and the share on flat land, and
  `fig_wall_lines.py` draws the lines by source with the length per source by
  size class, to `report/exposure/rw/wall-lines/fig/`.

## The probability on each wall unit (`gen_wall_probability.py`)

- `gen_wall_probability.py` reads the wall unit table landslide step 12 wrote
  (`gen_urban_slope_wall_units.wall_units_path()`) and stops, saying to run
  that step's `gen_urban_slope_faces.py` and `gen_urban_slope_wall_units.py`
  first, where it is missing. No orchestrator runs step 12. It reads the LINZ
  property boundaries on the bbox of step 12's DEM
  (`gen_urban_slope_wall_units.dem_bbox()`), so their cache is shared, and
  writes one row per unit to `temp/exposure/wall-probability[-pilot].geoparquet`
  from `wall_probability_path()` through
  `landloss.exposure.rw.wall_probability.gen_unit_probability_table`.
- A unit's `p_wall` and `p_wall_basis` are step 12's: the prior, the GNS floor
  and the claim and NZMM update (the step 12 method file). Its `wall_line_id`
  is its `wall_unit_id`. Its `claim_id` comes from `claim_of_properties`: the
  property's boundary maps to the claim of `build_claim_properties` with
  exactly its geometry, so every title of a stacked unit-title block maps to
  the block's claim, and a unit with no rateable property, or on a road or
  hydro parcel, has none.
- `face_height_m` is the unit's `height_m` (the highest face of a pif member,
  or the step the DEM makes across a GNS-only piece) and `size_class` is
  `classify_wall_size` of it, except that a unit with no height is `small`.
  `wall_position` is `fill` where the unit is on fill (`is_fill`: a fill
  material on the ground map or a SLIDE fill body), else `cut`. `is_flatland`
  is False throughout, `source` is the `unit_source` (`pif` or `gns_only`) and
  `material` the ground map material of its longest member.
- Over the pilot on 2026-10-05: 7,248 units, 3,458 expected walls, 6,821
  units (3,203 expected walls) on a claim; 713 small, 2,483 medium and 4,052
  large; 6,578 cut and 670 fill.
- The probability on the earlier candidate lines stays in the library
  (`wall_probability_table`), read by the urban slope chain test and by no
  script:
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
- No condition is put on a unit or a line: the wall type, drawn per world in
  `gen_wall_population.py`, carries it
  (`.agents/plans/assigning-retaining-wall-types.md`).
- The count bounds hook was removed on 2026-10-05: the walls a claim report
  lists update the wall units' probabilities in landslide step 12 instead.
- Every number in `wall_probability.py` and `wall_units.py` carries a `BETA_`
  prefix because it is judgement standing in for the claim report extraction.
  The run prints the expected number of walls, `p_wall` quantiles, the units
  and expected walls on a claim, and the unit count and expected walls by
  source, by `p_wall_basis` and by size class, and the count by wall
  position, and ends by saying plainly that the result is not evidence about
  Wellington.

## The age shares of each property (`gen_wall_age.py`)

- `gen_wall_age.py` writes one row per claimable LINZ property in the extent
  to `temp/exposure/wall-age[-pilot].parquet` from `wall_age_path()`, indexed
  by `property_id` (the boundary's `source_id`), carrying `p_pre_1970`,
  `p_1970_1991`, `p_1992_2004` and `p_2005_on` (`wall_age.AGE_SHARE_COLUMNS`,
  the bins of `landloss.exposure.rw.age.AGE_BINS`) and `age_basis`, the rule
  that set them. The rules are in `landloss.exposure.rw.wall_age`.
- **The dwelling first** (`qv`): the QV rating roll's `building_age_indicator`
  (`get_qv_rating_roll`, read from T:), joined to the property on its
  valuation reference (`property_qv_ages`; a missing reference joins
  nothing). A three-digit decade code is binned whole, the 1990s into
  `1992_2004`, and the 2000s split half and half between `1992_2004` and
  `2005_on` (`qv_age_shares`); `PRE` is `pre_1970`; `XXX`, `MIX` and the like
  are not read. Where several rating units map to one property the oldest is
  taken.
- **The lot second**: exposure step 8's own title or plan date
  (`own_lot_dates`, its `title` and `dp` rules only; a year step 8 took from
  the neighbours goes to the suburb tier instead). With no dwelling age the
  lot's bin stands alone (`title`). Where the lot is
  `BETA_LOT_OLDER_GAP_YEARS` (20) or more older than the dwelling's decade
  midpoint, half the share goes to the lot's bin, because the original walls
  of a rebuilt section may have stayed (`qv_and_lot`). Otherwise the dwelling
  stands (`qv`).
- **Neither held**: the property's suburb's shares from step 8's per-suburb
  table (`suburb`), and with no suburb the extent's, the mean of the suburbs
  the extent's properties fall in weighted by their dated properties
  (`extent`).
- The run reads the LINZ boundaries from the cache `gen_wall_probability.py`
  fetches, refuses a missing step 8 output naming the scripts to run, and
  prints the count by `age_basis` and the mean share per bin. It has not yet
  been run on real data.

## The draw per exposure world (`gen_wall_population.py`)

- `gen_wall_population.py` reads the probabilities from
  `wall_probability_path()`, landslide step 12's per-world draws of which units
  are walled (`gen_urban_slope_wall_units.wall_draws_path()`), the property
  age shares from `gen_wall_age.wall_age_path()` (a missing file stops the run
  and names `gen_wall_age.py`), each unit's `on_road_frontage` from step 12's
  `wall_units_path()` and the insured land from step 5's
  `insured_land_path()`, and writes one file per world,
  `temp/exposure/wall-population-wNNN[-pilot].geoparquet` from
  `wall_population_path(world_id, extent=...)`. The worlds come from
  `config.WORLD_IDS`.
- Each world is seeded by `realisation_seed(EXPOSURE_BASE_SEED, world_id,
  "exposure")`: on the exposure seed and the world id, not on any earthquake,
  because whether a wall exists is not something the earthquake decides, so
  one world pairs with every hazard realisation
  (`landloss.hazard.realisation`).
- **The type draw** comes first, over every candidate in table order, on its
  own generator, `realisation_seed(EXPOSURE_BASE_SEED, world_id,
  "wall_type")` (`wall_type.WALL_TYPE_STREAM`), so a wall's type does not
  change with which candidates are walled. `type_candidates()` gives each
  candidate its `face_height_m`, its unit's `on_road_frontage` (False where
  step 12's table does not carry the unit) and its property's age shares; a
  candidate with no property, or on a property `gen_wall_age.py` did not age,
  takes the extent default (`extent_default_shares()`: the mean of the rows
  with `age_basis` `extent`, else of every row, rescaled to sum to 1).
  `landloss.exposure.rw.wall_type.draw_wall_types` then draws three uniforms
  per candidate: the age bin from its shares; a move to the next bin with
  probability `BETA_WALL_REBUILT_SHARE` (0.2; `2005_on` stays), for a wall
  rebuilt since the house; and the type from the row of
  `beta-retaining-wall-type-shares.csv` for that bin and its height band
  (under 1.5 m, 1.5 to 2.5 m, over 2.5 m), times
  `beta-retaining-wall-frontage-multipliers.csv` on a road frontage,
  renormalised. The fractions and multipliers are judgement placeholders for
  Nick Peters to revise.
- `landloss.exposure.rw.population.draw_wall_population` draws two uniforms
  per line in line order and compares the first against `p_wall`: a wall
  exists where it is below. The second drew the retired condition and is
  still drawn, so which lines are walls is the same as in earlier worlds. The
  script passes step 12's draw for the world as `walled`, which replaces the
  comparison, so the walls that shape the hazard are the walls that are
  exposed. Each drawn wall takes its `wall_type` and `age_bin` from the type
  draw by `wall_line_id`; a drawn wall with none stops the run. A world
  missing from the draws, or a unit not drawn in it, stops the run and says to
  add the world to step 12's `WORLD_IDS`. A wall is the line that drew it: `height_m` is the line's `face_height_m`, and `size_class`,
  `length_m`, `wall_position`, `is_flatland`, `source`, `material` and the
  geometry are copied from the line (`population.POPULATION_COLUMNS`).
  Nothing is placed or sized in the draw. Since 2026-10-06 the line is the
  wall unit's simplified line (at most `WALL_MAX_BENDS` bends, no section
  under `WALL_MIN_SEGMENT_M`, landslide step 12 config; a MultiLineString of
  such lines for the unit of a pif too long to follow with one) and
  `length_m` is its length. A unit can cross property boundaries: it is drawn once, on its
  primary property (`property_id`, the non-road property holding most of
  its line), and the wall also carries `property_lengths_m` (each non-road
  property it enters by at least 1 m and its length there) and
  `n_properties` (`population.OPTIONAL_COLUMNS`), for the loss side to count
  it on each property later (vul rw status files, Next).
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
  `size_class`, `wall_type`, `age_bin`, `height_m`, `length_m`, `wall_position`,
  `is_flatland`, `source`, `material`, `property_id`, `property_lengths_m`,
  `n_properties` and the line geometry. `height_m` is the
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
  `drawn_walls_path(world_id, extent=...)`: one row per line that drew a wall,
  in line order, `wall_line_id` unique, with the population file's columns in
  the same order and `rw_id` and `claim_id` nullable. `rw_id` is null for a
  claimless wall and for one off its claim's insured land. The draw and the
  stream are unchanged, and `wall_population_path()` stays the insured subset
  that vul and loss read; landslide step 8 reads the drawn walls and nothing
  else does (decision 36 of the build contract). The drawn walls carry wall
  unit ids, so step 8's join on the step 7 line ids finds none of them.
- The run prints the candidates on a road frontage and on the extent's age
  shares, then per world the world id and stream, the type count over every
  candidate, the walls drawn over the lines
  offered against the expected count, the claim and coverage counts kept and
  dropped, `describe_population()` by size class and wall type, the count by
  age bin, the share on
  flat land, the count by wall position and the height deciles by size class,
  the count of drawn walls and how many carry an `rw_id`
  (`describe_drawn_walls()`), and ends by saying plainly that the result is
  not evidence about Wellington.
- Over the pilot on 2026-10-05, world 0, before the type draw: 3,466 walls
  drawn of the 7,248 units (3,458 expected), 3,213 on a claim and 2,019 kept
  on the insured land (277 small, 895 medium and 847 large; 1,896 cut and 123
  fill). The type draw has not been run on real data.
- `gen_exposure.py` runs the four scripts in this order after the insured
  land and dwellings steps, over `exposure/config.py`'s `EXTENT` and
  `WORLD_IDS`; the lines read landslide steps 3, 4 and 6, so the hazard module
  runs first. Landslide step 12 is in no orchestrator, so it is run by hand
  before them, as is exposure step 8, whose property ages `gen_wall_age.py`
  reads.

Potential future improvements: see `s6_wall_population_implementation_plan.md`.
