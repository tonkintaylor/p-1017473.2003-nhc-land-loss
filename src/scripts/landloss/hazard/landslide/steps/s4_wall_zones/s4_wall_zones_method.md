# Landslide step 4 — Wall zones: method

- The step builds the evacuated, imminent and inundated zones of the urban
  slope elements, once as two bounds and once per exposure world. It is run by
  `gen_wall_zones.py` (named "landslide s4, wall zones per world" in `gen_hazard.py`),
  after exposure, with the settings in `config.py` beside it; `WORLD_IDS` is
  read from exposure rw step 6's `config.py`, so the zones follow the worlds it
  draws. Its output is under `temp/hazard/landslide/`, with
  `extent_suffix(extent)` on each name.
- It reads the found elements ground step 3 kept (`urban-slope-found.pkl`,
  `read_found()`), stored without their terrain layers, and rebuilds them on
  the same sea-masked DEM, whole or tile by tile
  (`slope_elements.restore_elements`); the 1 m DEM of ground step 1 and the ground map of ground
  step 2, the siz table of ground step 4, and the wall units and the draws of
  exposure rw step 6 (`wall_units_path()`, `wall_draws_path()`). It refuses to
  run if the found elements or the siz table are newer than the wall units,
  which would then name other pifs, and if a world in `WORLD_IDS` was not drawn.
  How the elements are found is in `s3_instability_zones_method.md`; how the
  units and draws are made is in `s6_wall_population_method.md` of exposure rw.
- `gen_wall_zones.py` first gives every unit with no grown element an element
  along its line (`units_without_element`): the GNS-only units and, since
  2026-10-06, the units of `low_height` pifs, a GNS mapped wall on a pif that is
  not a siz. A low-height pif's unit takes a line element rather than growth
  from its pips: its pif failed the siz test, so growth at the siz threshold
  would keep little but its own pips and measure a face the test called not
  steep enough, while the line takes the unit's own wall height and the same
  width floor as every wall (`instability_zones.add_line_elements`, the lead,
  2026-10-06): the line is burnt onto the grid, every cell it touches that no
  element holds, as an element of its own with `wall_unit_id` set, `grown_in`
  `wall_line`, `siz_id` 0, its height the unit's step height but never under
  `MIN_WALL_HEIGHT_M` (0.5 m), and a run of 0 (a step, 90 degrees). The elements
  are measured again so the edge roles, stack links and catchments see the new
  ones, and the old keep their labels and columns.
- A unit whose line finds no free cell (every cell it touches already another
  element's, or off the DEM) gets its minimum polygon drawn as geometry from its
  line instead, overlapping what it must (`forced_polygons`, the lead,
  2026-10-07: "force all walls to have that minimum polygon even if it
  overlaps"): the band `max(0.5 H, 1 m)` on the uphill side of the whole line,
  the side read off the DEM 1.5 m either side (centred on the line, and
  `side_unknown`, where the DEM is missing or level); the same depth and volume
  as a line element; an imminent band to where a 35° line from the toe meets
  level ground, never under the 1 m T-45 band; and an inundated strip in front
  to `H / (H/L)` at the dry reach angle on its volume, held to the builder's
  caps (`slope_polygons.inundated_length_m`; no imminent or inundated zone where
  the side is unknown). Its element (label after the line elements, `grown_in`
  `forced`) goes in the elements file with the band as geometry, and its zones
  follow the built ones in every zones file (`forced` True), so landslide steps
  5 and 6 treat it as any other polygon (`with_forced`). Kept this way, rather
  than drawing every GNS-only and low-height polygon as geometry, because a line
  element on free cells gets the polygon builder's full treatment (its rays,
  runout down the real fall line, stacks and the contest for shared ground);
  only the units the label grid cannot hold are forced. The elements with these
  added are written to `urban-slope-wall-elements.parquet`
  (`wall_elements_path()`), which landslide step 5 reads, and the bounds are
  built from them.
- **The zones** are built by `landloss.hazard.landslide.slope_polygons.build_slope_polygons`,
  whose module docstring holds the rules (6 and 7 for the runout). The width
  behind every polygon's crest, walled or not, is at least
  `BETA_MIN_EVACUATED_WIDTH_H` (0.5) of the element's height and never under
  `BETA_MIN_EVACUATED_WIDTH_M` (1 m), along its whole crest
  (`slope_polygons.min_evacuated_width_m`, the lead, 2026-10-06). It is applied
  to every polygon, not only walled ones: a bank on a siz is as steep as a
  wall's face, and the T-44 band of 0.5 to 1 m left the bare polygon of a tall
  siz narrower than its walled one. The floor governs wherever it is wider than
  the type's rule: the wall's wedge on fill's 42° (0.45 H) and the fill bank
  (0.45 H) always, the half-metre headscarp band always, and the one-metre band
  above 2 m high. `width_rule` stays the type's rule and `width_floored` says
  where the floor set the width.
- Fill and its thickness are read onto each element by `fill_by_element()` from
  the element's majority ground map row. A fill bank (no wall) is cut on the
  same slip plane as a wall's face, from its toe to the back of its width, each
  cell no deeper than the fill thickness (`slope_polygons.element_depth_m` and
  `_set_planar_depths`, the lead, 2026-10-08): with the whole thickness, 56% of
  the pilot's fill banks were deeper than their height and their debris spread
  back over their scars. A rising back slope deepens the plane through the DEM
  at the back of the width. Sidelong fill, which can fail on its base
  [monteith_2020], is not yet flagged.
- The zones are drawn smoothed (`slope_polygons.polygon_geometries`,
  `smooth_cell_outline`, the lead, 2026-10-08): each zone's cells are outlined
  through the midpoints between cell centres (the marching squares outline at
  one half: straight runs stay on the cell edges, single-cell steps become a
  diagonal, corners are cut at 45 degrees), then `BETA_ZONE_SMOOTHING_PASSES`
  (2) passes of Chaikin's corner cutting round the rest. The evacuated and
  inundated zones are smoothed on their own; the imminent zone is its cells and
  the evacuated cells smoothed together less the smoothed evacuated zone, so its
  inner edge is the evacuated outline and the two meet with no gap (the lead,
  2026-10-08). `zone_polygons()` (`drawn_areas`) sets `area_m2`,
  `imminent_area_m2` and `inundated_area_m2` to the drawn areas and `depth_m` to
  the volume (the cells' depths summed) over the drawn evacuated area. Pilot
  world 0 against the cell outlines: evacuated −0.5%, inundated −1.6%; imminent
  −12.5% when smoothed on its own (most imminent bands are one cell wide, and
  17,998 m² of gaps were left between it and the evacuated outline), +0.4%
  against the evacuated outline (measured on the world 0 cells; the pilot has
  not been rerun with it).
- The imminent and inundated zones are one width and one length per polygon, the
  median of its rays' reach (`slope_polygons.imminent_width_m` and
  `inundated_length_m`), swept along every ray of the polygon. The runout ends
  where a line from the crest at Hunter and Fell's travel angle meets the ground
  (`slope_polygons.reach_ratio`, the lead, 2026-10-07, in place of the dry debris
  avalanche reach angle): where the ground below the toe, read along each ray
  over `BETA_DOWNSLOPE_WINDOW_H` (1.5) heights and at least 2 m
  (`_downslope_angle_deg`, the median of the rays as `downslope_angle_deg`), is
  at or steeper than `BETA_STEEP_DOWNSLOPE_DEG` (20°), `0.77 tan a2 + 0.087`
  (`style` `downslope`), flatter than the ground, so debris runs on down a steep
  slope; otherwise `0.78 (tan a_cut)^0.5` (`cut_slope`) on the element's angle
  with the cell of run the 1 m DEM adds taken off, `atan(H / max(run - 1, 0))`
  and no steeper than 80° (`slope_polygons.source_angle_deg`, the lead,
  2026-10-08: the pilot's 2 to 3 m faces read 44° at the median). Because the
  march measures from the DEM's crest and toe, a cell further apart than the
  face's, a cut polygon's run past its toe is the longer of the march's and
  `H (1 / (H/L) - 1 / tan a)` read off the face (`cut_reach_past_toe_m`), at most
  about 0.4 H. Its runout is held to 2, 3 or 4 heights past the toe where the
  ground below is under 20°, 20° to 35°, or steeper (`max_runout_h`, the lead,
  2026-10-08), after the seismic distance of its Kingsbury zone is added to the
  travel run (`BETA_SEISMIC_RUNOUT_M`: 0.5 m very low and low, 1 m moderate, 2 m
  high, 3 m very high; the lead, 2026-10-08, set loosely for a Mw 7.5, 0.7 g
  earthquake, in place of the 1 m strip of 2026-10-07). Only the travel run is
  held to the length that holds its volume at `BETA_MIN_DEPOSIT_DEPTH_M` (0.3 m).
  The zone is scored before the runout, as landslide step 5 scores it
  (`urban.geometry.kingsbury_score` on the element's angle, the polygon's height
  and `urban.face_polygons.ground_of_elements`), passed to
  `build_slope_polygons` as `element_ground` and to the forced polygons as
  `ground`; the zones carry `kingsbury_rating`, `kingsbury_zone` and
  `seismic_runout_m`. Where that strip would carry the volume deeper than
  `BETA_MAX_DEPOSIT_DEPTH_H` (1) heights or `BETA_MAX_DEPOSIT_DEPTH_SOURCE` (2)
  times the polygon's own evacuated depth, whichever is less, the inundated zone
  spreads back over the polygon's own evacuated ground, the lowest cells first,
  until it does not (`deposit_overlap_m2`), so a polygon's inundated and
  evacuated zones can overlap. Before the spread back is sized, a piece of a
  polygon's strip of one cell, or two side by side, touching none of its other
  cells along a row or column is dropped (`_drop_specks`, the lead,
  2026-10-08), so the volume it held spreads back over the scar instead; a
  polygon whose strip is only such pieces keeps them. Its imminent band to where
  the 35° repose line from the toe meets level ground.
- The evacuated ground loses its specks the same way, straight after the
  contest for shared ground and the one-cell gap filling, and before anything
  is read off it (`_drop_specks`, the lead, 2026-10-08): the polygon's area,
  volume, depth and realised width, the cells it shares with other polygons
  (`_recount_overlaps` drops a pair left sharing nothing and counts the rest
  again), and the imminent band and runout, which leave out the polygon's own
  evacuated ground. A dropped cell goes to no polygon. Before the change, world
  0 of the pilot carried 275 such pieces in 203 of its 5,766 polygons, 224 m²
  drawn. No barrier grid is passed, so buildings and
  roads do not stop the runout.
- `build_slope_polygons` builds the zones twice as the bounds, with `with_walls`
  setting every element walled (`walled`) or none (`bare`), and once per exposure
  world: an element is walled where its pif is a member of a walled unit of that
  world's draw, or its line is a walled unit's (`gen_element_walls`). Since
  2026-10-06 the bounds are built here, not by ground step 4, because they
  include the elements on the GNS-only units' lines, which exist only once the
  wall units do. `zone_polygons()` writes one row per polygon and zone to
  `urban-slope-zones-<scenario>.parquet` (`zones_path()`), `walled`, `bare` and
  `wNNN` (`world_scenario()`) per world. The world zones are what landslide
  steps 5 and 6 read, in place of the old step 7 polygons (2026-10-06, removed
  2026-10-08): each polygon's wall is its element's wall unit, the id exposure rw
  step 6 writes as the drawn wall's `wall_line_id`, so the hazard and the
  exposure share one draw. The bounds are never read downstream.
- **Alignment with the wall line** (the lead, 2026-10-13: the walled element's
  evacuated polygons end at the wall; see `s6_wall_population_method.md` for the
  wall line they are aligned to). After a scenario's zones are built, and for
  the tiled run after they are stitched (so a unit's polygons are seen together
  whichever tile built them), `gen_wall_zones.align_scenario()` calls
  `zone_tiles.align_walled_zones()`, which runs
  `zone_alignment.align_zones()` and then `drawn_areas()`.
  - Which polygons: the evacuated polygon of a built element whose pif is a
    member of a wall unit that is walled in the scenario (`walled`: every unit,
    `bare`: none, a world: its draw, the same units `gen_element_walls` flags).
    Not aligned: line elements (`siz_id` 0, the GNS-only and low-height units,
    which have no pips and so no fall), forced polygons (drawn from the line
    already), and the elements of a pif piece with no wall (in no unit, so not
    walled; their polygons stay as built).
  - The unit's line is `units.geometry`; its fall is the mean fall of its first
    member pif's pips (`zone_alignment.unit_falls()`, `pip_direction` of the siz
    table).
  - The trim and fill are `wall_trim.align_unit()`, with the settings in
    `config.WALL_TRIM_*` (`zone_tiles.wall_trim_settings()`): the polygon within
    2 m of the line is cut by the line extended along its end sections, the
    pieces downhill are removed, then the gaps between the polygons and the
    line are filled by ribbons along the line's normal. How each polygon went
    is written on its evacuated rows (`wall_trim_how`, `wall_trim_removed_m2`,
    `wall_trim_filled_m2`; "" where not aligned).
  - Imminent and inundated zones are left as built (the lead chose a rule for the
    evacuated polygon only, 2026-10-13). No rule for them has been chosen, so a
    band can still overlap or leave a gap against an aligned outline. Ask the
    lead before adding one.
  - `volume_m3` is unchanged; `area_m2` and `depth_m` of an aligned evacuated
    polygon are redrawn from the geometry (`drawn_areas`), so the depth is the
    same volume over the new area.
  - A walled polygon whose unit has no fall is left as built and marked
    `wall_trim_how` = `no fall`; the step prints the count and stops if more than
    `MAX_NO_FALL_SHARE` (5%) of the walled polygons have no fall.
  - The `walled` bound walls every unit through `gen_element_walls`, so the
    elements of a no-wall pif piece stay bare in it, as in every world.
  - Smoke test on the existing pilot world 0 zones with the research lines: 2,637
    polygons aligned, 24,743 m2 trimmed and 4,595 m2 filled, in 16 s (run when
    the imminent and inundated zones were also altered; since removed).
- `fig_wall_zones.py` draws, at each site of `FIG_SITES` (the stage D2 pilot
  sites), one panel per zone file in `FIG_ZONE_SCENARIOS`: the evacuated zones
  coloured by whether the element is walled, the imminent and inundated zones at
  their true shape over a hillshade, and the wall units. Set to
  `("walled", "bare")` it shows what the walls change; a world (`"w000"`) shows
  the pipeline's zones, its walled units solid. Written to
  `report/hazard/landslide/wall-zones/fig/`.
- Counts are printed per scenario. Over the `wlg-pilot` extent (rerun
  2026-10-07 with independent candidates): 943 of the 948 units with no grown
  element given a line element; 664,919 m² evacuated walled, 657,131 m² bare and
  663,401 m² in world 0. Forced polygons (2026-10-07): 5 units on the pilot
  (WU0000758, WU0001383, WU0001432, WU0002002, 3 to 4 m GNS leftovers inside siz
  elements, and WU0005568, 18 m at the DEM edge), 1 with the side unknown, 4
  overlapping a built polygon; every candidate has a polygon, and the 21 insured
  walls with none in landslide step 6 all lie in the DEM margin outside the
  shaking extent. Walled units under 1.5 m are 63% (55% without the GNS-only
  units), against 54% in Anderson et al.

## Tiles

Over an extent whose 1 m DEM holds more than ground step 3's
`config.MAX_UNTILED_CELLS` cells (every territorial authority; no pilot) the
zones are built tile by tile (`build_tiled()` in `gen_wall_zones.py`, on
`tiled.zones_tile` in ground step 3), and the tiling of the grid pass is
described in `s3_instability_zones_method.md`:

- A line or forced element is keyed by its wall unit and belongs to the tile
  whose core holds the unit's line; a zone polygon belongs to its element's
  tile. Polygons are renumbered across tiles, built ones first, forced after.
- The pass computes the lineless units over the whole extent, then per tile adds
  the line and forced elements of the units reaching it and builds every
  scenario with the walls flagged through the global pif ids.

The tiled zones are not yet identical to the whole grid's; see the plan's
phase 3 for the comparison on the Porirua pilot.

### Workers, kept tiles and the resume

Implemented 2026-10-11 from `doc/specs/optimise-landslide-s4-wall-zones/spec.md`
(FR-001 to FR-007); the settings are `TILE_WORKERS` and `REBUILD` in `config.py`.

- **Workers.** `run_tiles()` builds the tiles in a `ProcessPoolExecutor`, at most
  `TILE_WORKERS` at once, as ground step 3 does; 1 builds them in order in the
  console's own process. Each worker reads the layers every tile reads once, in
  `zone_tiles.start_worker()` (the ground map from its file, and the coastline,
  building outlines, wall units, the lineless units, the scenarios' walled flags
  and the found index as arguments). The tile builder, `zone_tiles.build_zone_tile()`,
  and the functions it passes to `tiled.zones_tile` (`fill_by_element`,
  `ground_rows`, `with_forced`, `zone_polygons`, `drawn_areas`) are in
  `zone_tiles.py`, importable, so a worker on Windows can run them although
  `gen_wall_zones.py` is run as a script; `gen_wall_zones.py` imports them back
  for the whole-extent pass.
- **Kept tiles.** Each tile's `tiled.TileZones` is pickled to a temporary file and
  renamed (`zone_tiles.write_tile_zones()`), and dropped from memory, under
  `temp/hazard/landslide/urban-slope-zones-tiles{extent_suffix}/tile-RR-CC.pkl`.
  A tile file existing means the tile is done, so a killed run leaves no half
  tile; a tile that fails leaves the others kept.
- **Stitch.** `read_kept_tiles()` reads the kept tiles in the found index's tile
  order, so the element and polygon numbers, and the rule that the first tile
  claims a shared element, do not depend on which worker finished first.
  `tiled.label_keys`, `stitch_elements` and `stitch_zones` are unchanged.
- **Record.** The folder holds `built-from.json` (`built_from()`): the SHA-256 of
  the found index, the wall units file and the draws file; the size and time
  modified of the 1 m DEM, the ground map, the elements file and each tile's
  found elements; the scenarios, world ids and the fill modification name
  (`tile_settings()`); and the SHA-256 of the source of every module and function
  that builds a tile (`TILE_CODE`: `zone_tiles`, `tiled`, `tiles`, `wall_trim` and
  `zone_alignment` (the alignment is run after the stitch, so they are listed for
  the record's sake and a change to them builds the tiles again), the landslide
  library modules the tile reads, including `geometry`, `susceptibility`,
  `ground_map`, `pif_cut_fill`, `wall_candidates`, `urban.fragility` and
  `domain.constants`, ground step 3's `grid`, and the lineless and world
  helpers). A run with the same record builds only the tiles not kept; a
  different record, `REBUILD`, `USE_CACHED_LAYERS` False (the LINZ layers are not
  in the record) or a record file cut short by a killed run clears the folder and
  builds every tile (`keep_or_clear_tiles()`, which writes the record through a
  temporary file). The scenario sharing swaps `tiled.build_slope_polygons` for the
  length of a tile and puts it back, whatever happens
  (`sharing_between_scenarios()`). `TILE_WORKERS` is not in the record: it does not
  change the result.
- **Progress.** One line per finished tile: its number of the tiles to build, its
  row and column, its own elements, its own time and the time in all.
- **Check.** On the Porirua pilot in four 1.65 km tiles the wall elements and
  every scenario's zones were identical (attributes equal, geometries within
  1e-6 m) on 1 worker, on 3 workers, and on 2 workers after two kept tiles were
  deleted and the step run again. Over Porirua (39 tiles of 3 km, 4 workers)
  the step took 582 s against about 3.7 hours one tile after another, and its
  outputs were identical to the one-process run's. The peak memory of a worker over Upper Hutt
  (SC-004) is not yet measured.

### Less work per tile

A profile of one-worker Porirua pilot tiles (cProfile) put three quarters of a
tile in `polygon_geometries`, drawing and smoothing every polygon of every
scenario, a fifth in `build_slope_polygons` and a tenth in `restore_elements`.
Each change below leaves the outputs as they were (the pilot comparison against
the earlier run passed for every file on 1 and on 3 workers):

- **Draw only what the tile keeps.** `zone_tiles.with_forced(skip=...)` does not
  draw the polygons of grown elements whose pif another tile owns
  (`build_zone_tile` names them from the found tile's keys); the tile threw
  their zones away after drawing them. The forced polygons are still numbered
  after every built polygon.
- **Draw a cell set once.** `polygon_geometries(cache=...)` keeps each outline by
  its cells (and, for the imminent band, the evacuated cells), so a polygon whose
  cells are the same under another scenario, as most are, is not drawn again,
  and the evacuated outline the imminent band is cut from is the one just drawn.
  `zone_polygons(outlines=...)` passes one dict through a tile's scenarios.
  The outline is a function of the cells alone, so the geometry is unchanged.
- **One GDAL environment per zone.** `polygon_geometries` draws its polygons
  inside one `rasterio.Env`, rather than opening one per polygon.
- **Share the rays.** `build_slope_polygons(shared=...)` keeps the rays set out
  from the crest cells and each cell's distance below its crest, which do not
  read `element_type`, so the scenarios of a tile (which differ only by
  `with_walls`) work them out once. `zone_tiles.sharing_between_scenarios()`
  passes the dict for the length of a tile by swapping the builder `tiled.zones_tile`
  calls, because `zones_tile` is ground step 3's code and a change to it would
  change that step's record.

Own time of each Porirua pilot tile on one worker, before and after (s):

| Tile | Elements | Before | After |
| --- | --- | --- | --- |
| 0,0 | 250 | 27 | 9 |
| 0,1 | 345 | 36 | 10 |
| 1,0 | 378 | 33 | 10 |
| 1,1 | 775 | 45 | 16 |

The step takes 46 s on one worker (144 s before) and 30 s on three (76 s before).

Building only the margin elements an owned zone needs (FR-008) is not done. On
every pilot tile, in the bare and the walled scenario, the owned elements'
evacuated, imminent and inundated cells and their polygon attributes were
identical when the margin elements were left out altogether, so what the margin
adds is time (about 1.5 times the owned elements' build) and not zones. It is
not done because it is not provably exact and saves little: see the plan.

Potential future improvements: see `s4_wall_zones_implementation_plan.md`.
