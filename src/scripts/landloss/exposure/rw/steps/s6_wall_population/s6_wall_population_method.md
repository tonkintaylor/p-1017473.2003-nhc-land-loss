# Step 6 — Retaining wall population: method

The step is five scripts, run in this order by `gen_exposure.py`.
`gen_wall_age.py` puts a share per age bin on every property;
`gen_wall_units.py` builds the wall units on the pifs ground step 4 found, with
their probability and a draw per exposure world; `gen_wall_probability.py` puts
a claim on each unit; `gen_wall_population.py` draws one population per
exposure world from them, taking which units are walls from the units' draw for
that world and drawing each wall's age bin and type. `table_wall_unit_checks.py`
checks the units and is run by hand. The settings are in `config.py`, which
also re-exports the wall line rules from ground step 3 and `GNS_WALL_MATCH_M`
from ground step 4.

## The age shares of each property (`gen_wall_age.py`)

- Since 2026-10-08 `gen_exposure` runs `gen_wall_age.py` first in this step,
  before `gen_wall_units.py`, whose points read the shares (the lead's age
  points); from 2026-10-07 until then `gen_hazard` ran it. It needs only QV,
  exposure rw step 8 and the LINZ properties, none of the ground module's tables
  except the DEM bbox.

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
- **The lot second**: exposure rw step 8's own title or plan date
  (`own_lot_dates`, its `title` and `dp` rules only; a year step 8 took from the
  neighbours goes to the suburb tier instead). With no dwelling age the
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
  fetches, refuses a missing exposure rw step 8 output naming the scripts to run, and
  prints the count by `age_basis` and the mean share per bin. It has not yet
  been run on real data.

## The wall units and their draws (`gen_wall_units.py`)

Moved here from landslide step 12 on 2026-10-08, which built it from 2026-10-05
(the plan is `.agents/plans/placing-retaining-walls-on-pifs.md`; the library is
`landloss.hazard.landslide.wall_units`). It reads what the ground module wrote:
ground step 4's siz table (`siz_table_path()`, read by `read_sizs()`, which
stops and says to rerun `gen_slope_faces.py` if the spine or rateable property
columns are missing) and GNS-only candidates (`gns_only_path()`,
`read_gns_only()`), and ground step 5's pif cut and fill table
(`pif_cut_fill_path()`, `read_cut_fill()`, which stops and says to run
`gen_pif_cut_fill.py` after `gen_slope_faces.py` if the table is missing or
older than the siz table). `gen_all.py` runs the ground module before exposure.

- **Units** (the lead's model, 2026-10-07). Every candidate is its own wall
  unit, with one line, one probability and one draw: each `siz` pif piece,
  each `low_height` pif piece (a pif piece that is not a siz with a GNS mapped
  wall within 2 m) and each `gns_only` piece. Nothing is joined
  (`wall_units.gen_wall_units`). A unit's line is its member's: a pif piece's
  line, the stretch of spine it was cut on, or a GNS-only piece's line, both
  cut by `bend_split`, so every unit is one LineString of 3 to 50 m with at
  most 3 bends turning at most 185°; `gen_wall_units` refuses any that is not
  (`describe_lines()` prints the counts). `length_m` is the line's length (what
  `gen_wall_population.py` draws), `n_bends` its bends. The line rules are
  ground step 3's config (`WALL_MAX_BENDS`, `WALL_MIN_SEGMENT_M`,
  `WALL_MAX_LENGTH_M`, `MAX_TOTAL_TURN_DEG`), re-exported by this step's
  `config.py` beside `GNS_WALL_MATCH_M` from ground step 4. Until 2026-10-07
  candidates were joined into units (by GNS mapped wall feature, end to end,
  and a GNS-only piece within 5 m of a pif) and the joined lines cut again; the
  lead replaced that.
- **Properties.** `wall_units.gen_unit_properties` intersects each unit's line
  with the LINZ properties (stacked titles once): `property_lengths_m` lists
  every non-road property it enters by at least
  `BETA_MIN_WALL_LENGTH_IN_PROPERTY_M` (1 m) with the length inside it, longest
  first, and `n_properties` counts them; `property_id`, the primary, is the
  non-road property holding most of the line (ties to the lowest id), NA where
  it is on road parcels only. The primary is what the claim, the exposure draw
  and the per-unit checks use.
- **Height from the siz table, class from ground step 5.** A pif's `height_m`
  is the siz table's `near_drop_p80_m` (the lead, 2026-10-06), written by
  ground step 3 (`grid_table()`, `instability_zones.gen_pif_near_drops`): the
  `WALL_HEIGHT_QUANTILE` (0.7) quantile over its pips of each pip's near drop,
  the fall to the lowest DEM cell within `WALL_HEIGHT_REACH_M` (2 m) below it
  along its own fall direction (1 and 2 cells; 1 cell on a diagonal). The lead
  set 0.7 within 2 m on 2026-10-06, after 0.8 within 3 m put 18% of walled
  units under 1.5 m and 0.6 within 2 m put 72%. Ground step 5's walk to the
  foot of the face, used until then, ran up to 15 m down long batters and
  hillsides and overstated the height, as `max_delta_h_m`, the largest drop of
  any pip pair, did before it (kept only for reference). Each GNS-only piece's
  height is the step the 1 m DEM makes across it
  (`landloss.exposure.rw.lines.step_height_m`). A unit takes the
  `cut_fill_class` of its longest pif; where pifs tie for the longest, the tied
  class most of its pifs hold, then the lowest pif id. A GNS-only unit is
  `unknown`.
- **Probability (points, the lead, 2026-10-07).** `gen_wall_points` scores each
  candidate in points from the table
  `src/landloss/io/assets/wall-probability-points.csv` (every row judgement;
  the plan is `.agents/plans/wall-probability-points.md`), and the total sets
  the prior on a logistic scale: `BETA_WALL_POINTS_PER_DOUBLING` (20) points
  double the odds from `BETA_WALL_BASE_P` at 0 points (a low-height candidate
  from `BETA_LOW_HEIGHT_WALL_PRIOR`), so no prior reaches 0 or 1. The
  attributes:
  - `verticality`, the siz table's (`instability_zones.gen_pif_verticality`):
    per pip, the drop to the first cell along its fall over the largest drop
    within 3 cells; per pif piece, the median. Under 0.4 (a batter) −20, 0.4 to
    0.5 −5, 0.5 and over (a step) +10. A GNS-only candidate has none and scores
    0.
  - `height_m`: under 1.0 m −5, 1.0 to 2.5 m 0, 2.5 to 5 m +5, 5 to 8 m −20,
    8 m and over −60 (replacing the tall face taper).
  - `length_m`: under 5 m −5.
  - `building_m`: under 2 m +10, 2 to 5 m +5, 5 to 20 m 0, 20 m and over (or
    none within the search distance) −20.
  - Setting (`wall_units.gen_unit_boundary_flags`): at least half the line
    within `BETA_WALL_BOUNDARY_DISTANCE_M` (2 m) of a road parcel's boundary
    +20, else of a non-road property boundary +10.
  - Ground step 5's class: `fill` and `cut_and_fill` +5, `natural` −15.
  - A `cut` on rock (not highly or completely weathered or crushed) with
    `height_m` over 2.0 m −20; a `cut` in soil (alluvium, loess, colluvium, the
    fill materials, `rock_hw_cw`, `rock_crushed`) +10.
  - Age: the share-weighted points of the primary property's wall age shares
    (`gen_wall_age.py`, `read_age_shares()`): pre-1970 −10, 1970 to 1991 −5,
    1992 to 2004 0, 2005 on +10. A missing file prints a loud warning and every
    candidate scores 0; so does a property with no shares (counted in the run's
    output). `gen_exposure` runs `gen_wall_age.py` before this script.
  - NHC land attributes (NZMM) flags the primary property: +5. It is no longer
    an update (its yes/no has no count and agrees with GNS no better than
    chance, kappa 0.03).
- The unit table carries `wall_points`, `p_prior`, `p_prior_basis` (`points`,
  or `gns_only`), `wall_points_explain` (the bins that scored, e.g.
  `verticality 0.5 and over +10; setting road_frontage +20`), `age_points`,
  `has_age` and the flags `is_fill`, `is_natural`, `is_rock_cut`,
  `is_soil_cut`, `is_property_boundary`, `is_road_frontage`. The ground map's
  fill and the SLIDE fill bodies do not set the prior. `gen_gns_floor` lifts a
  unit with a GNS mapped wall to `BETA_GNS_WALL_UNIT_FLOOR` and sets a GNS-only
  unit at `BETA_GNS_ONLY_WALL_PROBABILITY` (0.95 and 0.70; the floor was 0.80
  for part of 2026-10-07), with the base (`BETA_WALL_BASE_P`, 0.458) solved so
  the pilot's expected walls are 3,357: the lead's 40% increase on the interim
  2,398 after the review.
- **The claim update.** The claim layer
  (`exposure/rw/validations/config.PROPERTIES_PATH`, built from every claims
  list in that folder's `CLAIMS_LISTS`: since 2026-10-06 the Tower, FMG, MAS,
  Ando, Chubb, QBE and loss adjusters' lists as well as IAG, Suncorp, Kaikōura
  and Seddon) is refused by `check_records_current` if it is older than any
  list's `reports.csv`, so a list added since is never silently left out. It is
  read onto each LINZ property by the smallest record polygon holding its
  representative point (`gen_property_wall_records`), and
  `gen_wall_unit_probability` updates each property's units on the walls its
  claim report lists (`p_claims`), with the Poisson-binomial
  (`gen_count_update`). A unit is a wall on every property in its
  `property_lengths_m`: each property is updated over all the units on it, each
  from its floor, and a unit on several keeps the highest of its updates (each
  is conditioned on a record of that property and none lowers a probability);
  `n_units` in the candidates missing table counts every unit on the property.
  `CLAIM_HOLDOUT_SHARE` of the claimed properties, picked with
  `CLAIM_HOLDOUT_SEED` (both in this step's `config.py`), are never updated.
  `p_wall` is `p_claims`; `p_wall_basis` carries the rule that set it
  (`points`, `gns_floor`, `gns_only`, `claims`).
- **Draws.** `gen_wall_draws` draws each unit walled, for each world in
  `WORLD_IDS` (this step's `config.py`, which the landslide wall zones also
  read), on the `wall_units` stream under `EXPOSURE_BASE_SEED`.
- Written under `temp/exposure/`: the unit table
  (`urban-slope-wall-units.geoparquet`, `wall_units_path()`), the draws
  (`urban-slope-wall-draws.parquet`, `wall_draws_path()`), the properties whose
  units cannot hold their listed walls
  (`urban-slope-wall-candidates-missing.parquet`) and the records on each
  property with the hold-out (`urban-slope-wall-property-records.parquet`). The
  last two are per property and stay under `temp/`. The file names are the ones
  landslide step 12 wrote under `temp/hazard/landslide/`.
- Over the `wlg-pilot` extent when this ran as landslide step 12 (2026-10-07,
  independent candidates; not rerun here yet): 6,220 pif pieces (4,884 siz, 91
  `low_height`) and 857 GNS-only pieces (10,454 m of the 30,676 m of mapped
  wall) make 5,832 units, one member and one line each, none breaking a rule
  (4,168 straight, 1,133 with one bend, 413 with two, 118 with three); 3,997
  expected walls; world 0 draws 3,991 walls, with 63% of the walled units under
  1.5 m (55% without the GNS-only units) against 54% in Canterbury
  [anderson_2015]. The earlier reruns of 2026-10-05 and 2026-10-06, on the old
  joined units and the 20 m and 50 m cuts, are in the git history of the
  landslide step 12 method file (tag `pre-ground-refactor`).

## The probability on each wall unit (`gen_wall_probability.py`)

- `gen_wall_probability.py` reads the wall unit table `gen_wall_units.py` wrote
  (`gen_wall_units.wall_units_path()`) and stops, saying to run ground steps 4
  and 5 and then `gen_wall_units.py` first, where it is missing. `gen_all.py`
  runs them in that order. It reads the LINZ property boundaries on the bbox of
  the ground DEM (`dem_bbox()`, ground step 3), so their cache is shared, and
  writes one row per unit to `temp/exposure/wall-probability[-pilot].geoparquet`
  from `wall_probability_path()` through
  `landloss.exposure.rw.wall_probability.gen_unit_probability_table`.
- A unit's `p_wall` and `p_wall_basis` are the ones `gen_wall_units.py` set: the
  points prior, the GNS floor and the claim update (above). Its `wall_line_id`
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
  lists update the wall units' probabilities in `gen_wall_units.py` instead.
- Every number in `wall_probability.py` and `wall_units.py` carries a `BETA_`
  prefix because it is judgement standing in for the claim report extraction.
  The run prints the expected number of walls, `p_wall` quantiles, the units
  and expected walls on a claim, and the unit count and expected walls by
  source, by `p_wall_basis` and by size class, and the count by wall
  position, and ends by saying plainly that the result is not evidence about
  Wellington.

## The draw per exposure world (`gen_wall_population.py`)

- `gen_wall_population.py` reads the probabilities from
  `wall_probability_path()`, the per-world draws of which units are walled
  (`gen_wall_units.wall_draws_path()`), the property age shares from
  `gen_wall_age.wall_age_path()` (a missing file stops the run and names
  `gen_wall_age.py`), each unit's `on_road_frontage` from
  `gen_wall_units.wall_units_path()` and the insured land from step 5's
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
  candidate its `face_height_m`, its unit's `on_road_frontage` (False where the
  wall unit table does not carry the unit) and its property's age shares; a
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
  script passes the units' draw for the world as `walled`, which replaces the
  comparison, so the walls that shape the hazard are the walls that are
  exposed. Each drawn wall takes its `wall_type` and `age_bin` from the type
  draw by `wall_line_id`; a drawn wall with none stops the run. A world
  missing from the draws, or a unit not drawn in it, stops the run and says to
  add the world to `WORLD_IDS` in `config.py` and rerun `gen_wall_units.py`. A wall is the line that drew it: `height_m` is the line's `face_height_m`, and `size_class`,
  `length_m`, `wall_position`, `is_flatland`, `source`, `material` and the
  geometry are copied from the line (`population.POPULATION_COLUMNS`).
  Nothing is placed or sized in the draw. Since 2026-10-06 the line is the
  wall unit's simplified line (at most `WALL_MAX_BENDS` bends, no section
  under `WALL_MIN_SEGMENT_M`, ground step 3 config; a MultiLineString of
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
  `wall_line_id`, which the wall carries (the unit's `wall_unit_id`) so
  landslide step 5 can find the wall of each of landslide step 4's zones.
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
  that vul and loss read; landslide step 5 reads the drawn walls and nothing
  else does (decision 36 of the build contract). The drawn walls carry wall unit
  ids, which landslide step 5 joins to landslide step 4's zones.
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
- `gen_exposure.py` runs "rw s6, wall age", "rw s6, wall units", "rw s6, wall
  probability" and "rw s6, wall population" after the insured land and dwellings
  steps, over `exposure/config.py`'s `EXTENT` and `WORLD_IDS`. The wall units
  read the ground module's tables, so `gen_all.py` runs the ground module first,
  and the hazard module's landslide step 4 reads the wall draws written here, so
  it runs after. Exposure rw step 8, whose property ages `gen_wall_age.py`
  reads, is run by hand.

## The checks on the wall units (`table_wall_unit_checks.py`)

- `table_wall_unit_checks.py` writes four aggregate tables to
  `report/exposure/rw/wall-units/tab/`: `wall-gns-recall.csv` (mapped wall
  length within 2 m of a member's footprint), `wall-claims-holdout.csv` (the
  floor and both updates on the held-out claimed properties), `wall-strata.csv`
  (modelled and recorded wall shares by council, NZMM slope class and the age
  bin of exposure rw step 8, with `below_recorded` where the share of
  properties more likely than not to have a wall is below the largest recorded
  share; the age bin is one `not available` row, with its reason, where
  exposure rw step 8 has not been run for the extent) and
  `wall-pilot-counts.csv` (units, expected walls, and per world the walled
  share of the sizs, the evacuated area against the two bounds and the share of
  drawn walls under 1.5 m). The pif recall in `wall-gns-recall.csv` is computed
  from the siz table the way `table_slope_face_checks.py` in ground step 4
  computes it, not copied. Any value over fewer than `MIN_HEX_CLAIMS`
  properties is blanked and named in `suppressed`. The checks are one-sided: a
  dataset with no wall is not evidence of no wall, and nothing is calibrated on
  them.
- On the pilot of 2026-10-05 the records reach 5,411 LINZ properties, 70
  claimed (21 held out) and 19 listing a wall; on the 21 held-out claimed
  properties the mean expected walls is 0.46 against 0.19 listed, and most
  other claim values fall under the suppression limit.

Potential future improvements: see `s6_wall_population_implementation_plan.md`.
