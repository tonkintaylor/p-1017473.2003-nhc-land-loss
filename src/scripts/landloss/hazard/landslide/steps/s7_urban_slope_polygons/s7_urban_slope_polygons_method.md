# Step 7 — Urban slope polygons: method

- **Superseded in the pipeline (2026-10-06).** Landslide steps 8 and 9 read
  step 12's zones of each world's wall draw instead of these polygons, and
  `gen_hazard.main_urban` no longer runs this step: its polygons are reconciled
  to the exposure wall lines, which no longer carry the walls exposure rw step 6
  draws. The scripts stay until step 12's plan, phase 5, removes them.
- The step turns the step 6 failure candidates and the exposure wall lines
  into the failure polygons of the urban model, one row per `slope_id`, each
  carrying the wall on its edge and the fixed geometry of every state it can
  be in. It is run by `gen_urban_slope_polygons.py`, and the figure it is
  checked against is produced by `fig_urban_slope_polygons.py` in the same
  folder, written to `report/hazard/landslide/urban-slope-polygons/fig/`.
- What a run does is set by `config.py` in the step folder — `EXTENT`,
  `USE_CACHED_LAYERS` and `ROAD_HALF_WIDTH_M` — read in each script's
  `if __name__ == "__main__":` block and passed into `main()` as keyword
  arguments. Neither script takes command line arguments and neither `main()`
  carries a default. `EXTENT` is `"wlg-pilot"`, so runs go over `SMALL_WLG_PILOT`; the
  full extent is the bounding box of the four territorial authorities,
  resolved by step 3's `gen_multiscale_slope.resolve_extent()`.
- The inputs are read in `gen_urban_slope_polygons.main()`: the candidates
  from step 6's `urban_slope_candidates_path()`, the wall lines from the
  exposure step's `gen_wall_lines.wall_lines_path()`, the 1 m DEM from step
  3's `dem_path(1, ...)`, and the LINZ building outlines and road centrelines
  from `landloss.io.readers`. The building outlines and the road centrelines
  buffered by `ROAD_HALF_WIDTH_M` are the runout barriers
  (`runout_barriers()`). The ground map is not read: its attributes are
  already on the candidates.
- The geometry rules live in `landloss.hazard.landslide.urban.geometry`, one
  named function per rule with its source cited in the docstring, and the
  snap tolerance is `landloss.hazard.landslide.urban.delineation.SNAP_TOLERANCE_M`,
  shared with the wall lines.
- `reconcile_candidates()` reconciles each candidate to the lines: every
  vertex within the tolerance of a line is projected onto it and the line's
  own vertices are inserted into the edge (`snap_edges_to_lines()`; a snap
  that would lose more than `MAX_SNAP_AREA_LOSS` of the candidate's area is
  not applied); a candidate a line crosses from boundary to boundary is split
  along it with pieces under `MIN_PIECE_AREA_M2` merged into their neighbour
  (`split_by_lines()`; a line ending inside a candidate does not split it).
  The snap and the split read every line. The walls on the polygon's edge
  are then read from the lines on sloping land only (`sloping_lines()`,
  `is_flatland` false), because a flat-land wall has no polygon and would
  otherwise shadow a sloping line on the same edge (`wall_line_on_edge()`):
  a line is on the edge along the part of it within the tolerance of the
  boundary that runs within `EDGE_ALIGNMENT_MAX_DEG` (30 degrees) of the
  boundary's direction, so a line crossing the boundary or ending against it
  is not. Every line on the edge is recorded in `wall_line_ids`, longest
  shared edge first, because the wall lines are split at property boundaries
  and the polygons are not, so one wall along an edge is often several
  lines. The line sharing the longest edge is `wall_line_id`, with that
  length as `wall_edge_length_m`, and its `wall_position` and
  `face_height_m` are copied onto the polygon as `wall_position` and
  `wall_face_height_m`. `area_m2` and `contour_length_m`
  (by step 6's `delineation.contour_length_m()`) are recomputed on the
  reconciled geometry; every other candidate column is carried, with
  `candidate_id` and `piece` (0 where the candidate was not split, 1 to n in
  order of location where it was).
- `relief_m` is recomputed on the reconciled geometry as the maximum less the
  minimum 1 m elevation under the polygon (`recompute_relief()`, through
  `landloss.common.utils.terrain.zonal_statistic`); a piece too thin to hold
  a cell centre keeps the relief its candidate carried.
- `slope_id` is minted by `mint_slope_ids()`: the polygons are sorted by
  `scale_m` descending and then representative point x and y with
  `landloss.common.utils.ids.sort_by_point` and numbered from 1 with
  `mint_ids` behind `SLOPE_ID_PREFIX`. The id depends only on the inputs and
  the parameters, so a changed extent renumbers.
- `parent_slope_id` is the smallest coarser-scale polygon covering at least
  90% of the polygon's area (`nest_parents()`), null where none does.
- `kingsbury_rating` is `susceptibility.susceptibility_rating()` on the six
  factors `kingsbury_factors()` scores from the polygon's own attributes:
  slope from `slope_degrees`; modification from the cut angle where
  `modification` is `cut`, the sidling fill value where `fill`, else 0;
  height from `face_height_10m` and `slope_degrees`; geology from the ground
  map's `geology_value`; landslides from `prior_failure`; groundwater from
  `gw_depth_m`. `kingsbury_zone` is `susceptibility_zone()`, written as a
  nullable integer because a polygon on `unknown` material has no geology
  value and so no rating. `continuous_rating` is
  `landloss.hazard.landslide.urban.fragility.continuous_rating()` on the same
  factors with the slope in degrees, and `amp_factor` is
  `amplification_factor()` (a placeholder until phase 3 of the plan) from
  `topographic_position_100m` and
  `slope_degrees` (`score_ground()`).
- The fixed geometries are computed per polygon by `state_geometries()` and
  attached by `attach_state_geometries()`, which hands each polygon the part
  of its `wall_line_id` line within the tolerance of its boundary; the other
  lines of `wall_line_ids` shape no geometry, so a polygon carries one wall
  state geometry whichever of its edge lines draws the wall. The crest and the
  toe are the boundary segments facing uphill and downhill (`crest_line()`,
  `toe_line()`), uphill being `aspect_degrees` plus 180.
- The no-wall state is filled on every polygon: evacuated is the face plus a
  headscarp band above the crest of `headscarp_band_m()` (half a metre, a
  metre at or over 30 degrees: `BETA_HEADSCARP_BAND_M` and
  `BETA_HEADSCARP_BAND_STEEP_M`, placeholders until T-44 is agreed with the
  project lead), built by `evacuated_no_wall()`; imminent is a
  second band of the same width behind it (`imminent_no_wall()`); the
  evacuated depth is `evacuated_depth_m()` (the colluvium depth, the ground
  map's fill thickness on fill materials where deeper, and the volume-area
  relation of `landloss.hazard.landslide.geometry` where deeper on polygons
  over `LARGE_POLYGON_AREA_M2`).
- A polygon with a cut wall on its edge carries the cut-wall state equal to
  its no-wall state. A polygon with a fill wall carries the fill-wall state:
  evacuated is the wedge one retained height back from the wall
  (`BETA_FILL_WEDGE_HEIGHT_MULTIPLE`, a placeholder until the phase 3
  research; `fill_wedge()`, the height floored at `MIN_WALL_HEIGHT_M`, and taken as
  that floor where the line's `face_height_m` is NaN because every sample
  fell off the face-height raster), imminent is one further height behind it
  (`imminent_fill_wall()`), and the evacuated depth is half the height
  (`fill_wall_depth_m()`). The other state's geometries are `None` and its
  depths NaN, so no row carries three states.
- A polygon with no downhill direction (`aspect_degrees` NaN: a level patch
  step 6 kept as a candidate of its own) takes the no-wall state of
  `no_direction_states()`: evacuated is the face, imminent is the band of
  `headscarp_band_m()` around its whole edge, and inundated is the band around
  the edge wide enough to hold the evacuated ground at its own depth, never
  narrower than `BETA_MIN_RUNOUT_M` and not cut at barriers. A wall on such a
  polygon's edge, fill or cut, copies that state. The run prints how many
  polygons have no direction (`describe_result()`).
- Inundated is a strip swept downhill from the toe (`inundated_polygon()`),
  cut at the first building outline or buffered road it meets. Its length is
  the larger of `runout_length_m()` — the relief over the reach angle less the
  face's extent along the aspect, with `dry_reach_angle()` at the evacuated
  volume for the no-wall and cut-wall states and `FILL_REACH_ANGLE_HL` for
  the fill-wall state — and `spread_runout_m()`, the length that gives the
  strip the evacuated area; it is never shorter than `BETA_MIN_RUNOUT_M`. The
  inundated depth is the evacuated volume over the inundated area.
- `rep_point` is the polygon's representative point, where the fragility step
  samples PGV.
- The output is written under `temp/hazard/landslide/` to the path
  `urban_slope_polygons_path()` returns, `urban-slope-polygons-pilot.geoparquet`
  when `EXTENT` is `"wlg-pilot"` and `urban-slope-polygons.geoparquet` when it is `"full"`, with
  the columns in the order `order_columns()` sets: `slope_id`, `candidate_id`,
  `piece`, the candidate columns, then the wall (`wall_line_id`,
  `wall_edge_length_m`, `wall_line_ids`, `wall_position`,
  `wall_face_height_m`), parent, rating,
  amplification, representative point, depth and state geometry columns, and
  the face as `geometry`. Every run prints the polygon count by scale, the
  share with a wall edge, the count with more than one wall line on the edge
  and the split by position, the zone distribution,
  the area and `amp_factor` deciles, and the count of empty or invalid state
  geometries (`describe_result()`).
- The rules are covered without the network by
  `tests/landloss/hazard/landslide/urban/test_geometry.py`, on planar
  synthetic faces and lines, including the library chain end to end writing
  a file with the contract's columns to a temporary directory. The reading
  and writing in `main()` is not covered.

Potential future improvements: see `s7_urban_slope_polygons_implementation_plan.md`.
