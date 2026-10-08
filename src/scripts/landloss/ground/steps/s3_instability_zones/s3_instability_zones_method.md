# Ground step 3 — Instability zones: method

- The step finds the pips, the pifs and their pieces, tests each piece for a
  siz and grows the sizs into elements, once per extent, with
  `landloss.hazard.landslide.instability_zones.find_instability_zones`, run by
  `gen_instability_zones.py` (named "s3, instability zones" in `gen_ground.py`)
  with the settings in `config.py` beside it. That `config.py` also holds the
  pif cutting rules and the wall height rules that the walls share
  (`WALL_MAX_BENDS`, `WALL_STRAY_TOLERANCE_M`, `WALL_MIN_SEGMENT_M`,
  `MAX_TOTAL_TURN_DEG`, `WALL_MAX_LENGTH_M`, `PIF_END_WINDOW_M`,
  `WALL_HEIGHT_REACH_M`, `WALL_HEIGHT_QUANTILE`); ground step 4's and exposure
  rw step 6's configs re-export them. The rules and thresholds of the search
  are in `.agents/plans/building-pip-pif-siz-slope-polygons.md` and the two CSV
  files `landslide-slope-thresholds.csv` and `landslide-seed-thresholds.csv` in
  `landloss/io/assets/` that the library reads.
- It reads the 1 m DEM of ground step 1 (`dem_path`) with every cell outside the
  LINZ NZ Coastlines and Islands Polygons set to no data (`get_dem()`, which
  ground step 5 reads the DEM through too), the ground map of ground step 2
  rasterised to ground groups with fill read as soil (`get_inputs()`), and the
  LINZ building outlines rasterised by cell centre (`building_mask()`).
- **The siz test** (the lead, 2026-10-08) is made on each piece, after the
  split, on its own pips (`assess_pifs` with `FALL_LINE_TEST`). Each pip is
  read down its true downhill line (`terrain_layers`' `downhill_row` and
  `downhill_col`, the nearest of the eight directions where the ground is
  level), one cell length at a time, stopping 5 m past the last cell of its
  own piece, so the drop is the face's and not the hillside's below it. A
  piece is a siz when a cell under `NEAR_PAIR_M` (3 m) down is lower by the
  ground group's `adjacent_step_m`, or a cell 3 to 30 m down is as steep as
  the group's angle for the drop's band (`landslide-slope-thresholds.csv`);
  its `max_angle_below_deg`, `max_angle_above_deg` and `max_delta_h_m` are
  the maxima over its pips. Until 2026-10-08 the test compared every pair of
  a pif's points up to 30 m apart (`PAIRS_TEST`, still in the library) on the
  whole pif, and every piece took the whole pif's verdict; that test was 70%
  of the step's time and let one steep stretch make every piece of a long
  pif a siz. On the pilots the new test gives the same soil sizs and about
  10% fewer weak rock ones, all borderline or the gentle ends of rock faces
  (`hazard/landslide/research/siz_fall_line/siz_fall_line.md`).
- **The pifs are the pieces** (the lead, 2026-10-06). `split_pifs` cuts each
  pif along its spine by the rule the walls are cut by, one implementation for
  both (`landloss.hazard.landslide.bend_split.cut_path`): a new piece wherever
  following the spine within `WALL_STRAY_TOLERANCE_M` (2 m) would need more
  than `WALL_MAX_BENDS` (3) bends or bends turning more than
  `MAX_TOTAL_TURN_DEG` (185°) in all, no piece shorter than
  `WALL_MIN_SEGMENT_M` (3 m) along it (a shorter one joins a neighbour), and
  none longer than `MAX_PIF_SPAN_M`, 50 m (20 m until this decision; a cap
  since 2026-10-04, when whole hillsides grew as one element). A piece whose
  line is over 50 m is cut first at its line's own bends (the fewest cuts that
  bring every part under 50 m, the most even of those) and what is still over
  50 m into equal parts; pifs take no boundary stage
  (`bend_split.cap_ranges`, the lead, 2026-10-06). The spine is the pif's
  longest shortest path; a branch sticking out from it by more than twice the
  pif's mean thickness (and 3 m) is a path of its own, so a spur or the leg of
  a T is cut too, while the width of a thick face is not a branch; each pip
  goes to the piece whose stretch of path is nearest. Property boundaries play
  no part (the 50 m boundary cut is the walls' alone). A piece's ends are at
  least 3 m apart (a shorter piece joins a neighbour; one folded into a
  horseshoe is cut where it turns), and its line, the siz table's `spine`, is
  the stretch of path it was cut on (`bend_split.canonical_line`), not a path
  found again through its pips: so every piece is 3 to 50 m long with at most
  3 bends turning at most 185° by construction, and `find_instability_zones`
  refuses any that is not (`bend_split.rule_breaks`). Before any of this a pif
  whose spine is under `BETA_MIN_PIF_LENGTH_M` (3 m) is dropped, as one of
  under three pips is (`drop_short_pifs`, the lead, 2026-10-06). Each piece is
  a pif of its own: its own `pif_id`, pips, spine and end falls, with
  `parent_pif_id` kept for reference. Each siz piece grows one element, so an
  element's `siz_id` is a siz table row, and a long face can be shared between
  walls.
- A pif holds at least `BETA_MIN_PIF_PIPS` (3) pips (the lead, 2026-10-06,
  matching the 3 m shortest element): `cluster_pifs` leaves a smaller cluster
  at 0 and numbers the pifs it keeps from 1 with no gaps, so such pips are in
  no pif, no siz and no wall candidate.
- Pifs most of whose pips lie in a LINZ building outline are dropped before
  the siz test (the lead, 2026-10-06), so a roof's edge or a building's wall
  is never a pif, siz, element or wall candidate. `building_mask()` rasterises
  the outlines onto the DEM by cell centre and `search_whole()` passes the grid
  as `exclude` to `find_instability_zones`, which drops a pif with more than
  half its pips on it (`instability_zones.exclude_pifs`) right after
  `cluster_pifs` and renumbers the rest; the library stays on rasters. The
  count is printed by `describe()`.
- Every siz is a wall candidate and a wall must have a polygon (the lead,
  2026-10-06), so every region a siz pif piece grows is kept as an element
  (`_assemble_elements(..., keep_all=True)`), even where the keep rule of
  `find_slope_elements` (at least 0.5 m high and 3 m long, no gentler than the
  18.4° grow angle, crossed by a transect) would drop it. `kept_by_rule`
  records which passed. A short or gentle element is measured as it is; one
  under 0.5 m high is raised to 0.5 m (a siz's pips each drop more than 0.7 m,
  so a lower reading is a transect artefact), and one no transect crosses
  takes a run of 0 (a step the DEM cannot resolve, as a one-interval
  transect is read) and its elevation range as height
  (`slope_elements._measure_regardless`), so its width, depth and volume can
  be built.
- The siz table's grid columns are read off the grid by `grid_table()`:
  `gen_siz_table` (every pif, the pips as a MultiPoint), `pip_direction` (each
  pip's fall direction, an index into `DIRECTIONS`, in the order of the
  MultiPoint's points), `near_drop_p80_m` (`instability_zones.gen_pif_near_drops`,
  the wall height: the `WALL_HEIGHT_QUANTILE` (0.7) quantile over a pif's pips
  of each pip's near drop, the fall to the lowest DEM cell within
  `WALL_HEIGHT_REACH_M` (2 m) below it along its own fall direction, 1 and 2
  cells, 1 cell on a diagonal; the lead set 0.7 within 2 m on 2026-10-06, after
  0.8 within 3 m put 18% of walled units under 1.5 m and 0.6 within 2 m put
  72%; `max_delta_h_m`, the largest drop of any pip pair, is kept only for
  reference), `verticality` (`instability_zones.gen_pif_verticality`: per pip,
  the drop to the first cell along its fall over the largest drop within 3
  cells; per pif piece, the median), and from `instability_zones.gen_pif_spines`
  the pif's `spine` (the stretch of path the piece was cut on),
  `spine_length_m`, the two spine ends (`end_a_x`, `end_a_y`, `end_b_x`,
  `end_b_y`), the mean fall direction of the pips within `PIF_END_WINDOW_M` of
  each end (`end_a_fall_deg`, `end_b_fall_deg`) and `fall_resultant` (1 for a
  straight face).
- An extent whose 1 m DEM holds more than `config.MAX_UNTILED_CELLS` cells is
  searched tile by tile (`tiled.py`, through `find_tiled`, on
  `landloss.common.utils.tiles`), with cores of `config.TILE_CORE_M` and
  margins of `config.TILE_MARGIN_M`; every pilot is searched whole
  (`search_whole()`). See Tiles below.
- It writes, under `temp/ground/` with `extent_suffix(extent)` on each name, the
  found elements to `found_path` (`urban-slope-found.pkl`, with one pickle per
  tile on a tiled run), the element polygons to `elements_path`
  (`urban-slope-elements.parquet`), and the siz table's grid columns to
  `grid_sizs_path` (`urban-slope-grid-sizs.parquet`). Ground step 4 reads the
  wall evidence onto that table; landslide step 4 reads the found elements.
- Each run writes a record of what it was built from
  (`urban-slope-instability-zones{suffix}.json`, `built_from()`): the
  settings, the size and modification time of the 1 m DEM and the ground map,
  and a hash of the source of the search code (`SEARCH_CODE`). A rerun whose
  record matches and whose outputs all exist is skipped (`is_current()`);
  `config.REBUILD` forces a search. A refreshed LINZ layer does not make a run
  stale.
- Counts and timings are printed by `describe()`. Over the `wlg-pilot` extent
  (2026-10-06, with the three-pip pif, the kept siz elements and the minimum
  width): 353,740 pips, 6,892 pifs, 4,953 sizs (4,447 of 4,447 soil pifs and
  506 of 2,445 weak rock) and 8,729 elements in 30.3 s, 164 of them kept only
  because a siz grew them (19 with no transect); every siz pif grows an
  element. Rerun since with the pieces and the building exclusion (2026-10-06,
  before the fall-line test): 6,220 pieces, 4,884 of them sizs, each piece line
  3 to 50 m; the pilot has not been counted again with the fall-line test.
- `gen_ground.py` runs the step after the ground map and before ground step 4.

## Tiles

Over an extent whose 1 m DEM holds more than `config.MAX_UNTILED_CELLS` cells
(every territorial authority; no pilot) this step and landslide step 4's wall
zones script run their grid work tile by tile (`tiled.py`, on
`landloss.common.utils.tiles`), and everything after it runs once on the
stitched tables:

- Tiles are `config.TILE_CORE_M` (3 km) cores read with a `config.TILE_MARGIN_M`
  (750 m) margin, rounded to whole 3 m blocks so each tile's catchment grid
  sits on the whole grid's. Each tile masks the sea, burns the ground map and
  the building outlines on its own window and runs `find_instability_zones` and
  the grid columns of the siz table (`grid_table()`); its elements are pickled
  per tile under `urban-slope-found{suffix}-tiles/`, and
  `urban-slope-found{suffix}.pkl` holds a `tiled.TiledFound` index instead of
  the elements.
- A pif belongs to the tile whose core holds the centre of its parent's pips
  (`tiled.owned_parents`), so a parent and its pieces come from the one tile
  that saw it whole: the longest parent on the pilots spans 636 m. Global pif
  ids follow the tiles in order; a pif seen in another tile's margin is
  matched to its global id by its pip cells (`tiled.pip_keys`), and one cut
  short by a margin's edge matches nothing.
- A parent longer than the margin is seen whole by no tile, and each tile's
  cut of it can centre in its own core; a piece two tiles both claim is kept
  from the first (`tiled.globalise_found`). Over Porirua 85 parents are longer
  than 750 m (the longest 4.5 km, on rural cliffs and the coast), and 31 of
  their pieces were claimed twice. Where two tiles cut such a parent into
  different pieces, both are kept, so its pips near the seam can be counted
  twice.
- A grown element takes the ownership and the global id of its pif. The tiling
  of the line and forced elements and of the zone polygons is landslide step 4's
  (`s4_wall_zones_method.md`).

Potential future improvements: see `s3_instability_zones_implementation_plan.md`.
