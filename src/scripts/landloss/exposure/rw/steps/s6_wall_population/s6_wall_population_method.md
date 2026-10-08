# Step 6 — Retaining wall population: method

The step is three scripts. `gen_wall_probability.py` reads the wall
units landslide step 12 builds on the pifs, with their probability, and puts a
claim on each; `gen_wall_age.py` puts a share per age bin on every property;
`gen_wall_population.py` draws one population per exposure world from them,
taking which units are walls from step 12's draw for that world and drawing
each wall's age bin and type.

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
- A unit's `p_wall` and `p_wall_basis` are step 12's: the points prior, the
  GNS floor and the claim update (the step 12 method file). Its `wall_line_id`
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
- The candidate wall lines of 2026-10-02, with their per-line probability
  (`line_wall_probability`, `wall_probability_table`) and `wall-lines*.geoparquet`,
  were removed on 2026-10-08. The units are the only candidates.
- **The mapping is one-sided.** GNS mapped only the walls visible from above
  and only in Wellington City [townsend_2020], so a mapped wall raises a unit's
  probability and the absence of one changes nothing. Slope, height, wall
  position and subdivision age do not enter `p_wall` in this build.
- No condition is put on a unit: the wall type, drawn per world in
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

- Since 2026-10-07 `gen_hazard` runs `gen_wall_age.py` before landslide
  step 12's wall units, whose points read the shares (the lead's age points),
  and `gen_exposure` no longer runs it. It needs only QV, exposure step 8 and
  the LINZ properties, none of step 12.

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
  `wall_line_id`, which the wall carries (the unit's `wall_unit_id`) so landslide
  step 8 can find the wall of each of step 12's zones.
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
  unit ids, which step 8 joins to step 12's zones.
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
- `gen_exposure.py` runs `gen_wall_probability.py` then `gen_wall_population.py`
  after the insured land and dwellings steps, over `exposure/config.py`'s
  `EXTENT` and `WORLD_IDS`; both read landslide step 12's wall units, so the
  hazard module runs first (`gen_hazard.main` runs step 12 and `gen_wall_age.py`).
  Exposure step 8, whose property ages `gen_wall_age.py` reads, is run by hand.

Potential future improvements: see `s6_wall_population_implementation_plan.md`.
