# Ground step 2 — Ground map: method

- The step builds one non-probabilistic polygon map of the ground over the
  extent, run by `gen_ground_map.py` ("s2, ground map" in `gen_ground.py`) and
  drawn by `fig_ground_map.py` in the same folder. What a run covers and what it is configured with is set by
  `config.py` beside the scripts, read in each script's
  `if __name__ == "__main__":` block and passed into `main()` as keyword
  arguments; neither script takes command line arguments and neither `main()`
  carries a default. `EXTENT` is `"wlg-pilot"`, so runs go over `SMALL_WLG_PILOT`;
  the full extent (`"full"`) is the bounding box of the four territorial authorities, resolved
  by ground step 1's `gen_multiscale_slope.resolve_extent()`.
- The vocabulary of the map — `MATERIALS`, `MODIFICATIONS`, `PRIOR_FAILURES`,
  `GW_DEPTH_CLASSES` and `CONFIDENCES` — and the mapping of each source's
  classes onto it live in `landloss.hazard.landslide.ground_map`. Each mapper
  (`material_from_slide()`, `material_from_geology()`, `material_from_nlm()`,
  `modification_from_slide()`, `modification_from_genesis()`,
  `modification_from_wcc()`,
  `modification_from_residual()`, `prior_failure_from_genesis()`) lists every
  class of its source and raises on one it has no rule for, so a source that
  gains a class stops the run rather than being defaulted. The source classes
  were read off the layers on 1 October 2026: fourteen SLIDE material types,
  seventy-four 1:50,000 unit codes, the thirteen NLM `l3_yp` classes
  susceptibility already scores, and fifteen genesis types.
- SLIDE's five mixed fill classes ("Mixed fill/rock", "Mixed fill/colluvium",
  "Mixed fill/colluvium/rock", "Mixed fill/talus" and "Old alluvium (mixed
  fill)") take their natural material as the material and record the fill as
  the modification, so the two are read separately: "Mixed fill/rock" is
  `rock`, the two colluvium classes and "Mixed fill/talus" are `colluvium`,
  and "Old alluvium (mixed fill)" is `alluvium`; colluvium wins where a class
  names both colluvium and rock, because Wellington fills fail on the buried
  colluvium at their base [brown_larkin_2005; lyndsell_2019; monteith_2020].
  "Fill" stays `fill_uncontrolled`, since the layer does not say whether it
  was engineered. A mixed class is a map unit, not a statement that the whole
  polygon is fill [townsend_2020]. Accepted by the lead on 2026-10-02 and
  built the same day; before it, every mixed class was `fill_uncontrolled`,
  which made 71% of the pilot's mapped ground fill in the 2026-10-02 run. The
  pilot has not yet been rerun with the new mapping.
- The sources are read in `gen_ground_map.main()`: `get_slide_interpreted_materials`,
  `get_wellington_urban_geology`, `get_nlm_geomorphology`, `get_slide_genesis`,
  `get_wcc_cut_areas` and `get_wcc_fill_areas` from `landloss.io.readers`, the
  NLM flatland from `landloss.io.nlm.get_nlm_flatland` reprojected to
  `DEFAULT_CRS`, the NLM median groundwater depth grid from
  `get_gwd_median_depth`, and the 30 m and 100 m cut-and-fill residual rasters
  ground step 1 writes, located by `residual_path()` through its `terrain_path()`.
  QMAP is not read, and NZGD boreholes are not read.
- Each source becomes a `GroundSource` naming the attribute it supplies and
  one confidence. The SLIDE materials are split by their own `confidence`
  field into three sources, high then medium then low
  (`slide_material_sources()`), so each piece carries the confidence of the
  polygon it read; `slide_confidence()` folds the layer's qualified high
  entries onto `high`. The genesis layer is filtered to the claiming types
  before each source is built (`genesis_sources()`): cut slope, fill body and
  landfill claim the modification at high confidence, dams at low, and the
  landslide and rockfall polygons claim the prior failure at low. The two WCC
  layers claim the modification at medium (`wcc_sources()`). The SLIDE
  materials polygons of a fill type (`SLIDE_FILL_TYPES`: "Fill" and the five
  mixed classes) claim the modification `fill` as well, split by their own
  confidence as the material sources are (`slide_modification_sources()`).
- The two rasters become polygon sources before the overlay. `polygonise_groundwater()`
  cuts the national groundwater grid to the extent, classes the depth with
  `gw_depth_class_from_depth()` (saturated above 1 m, poorly drained from 1 m to
  3 m, well drained from 3 m down; a depth on a break takes the deeper class, as
  `groundwater_value()` does; the breaks are held in
  `landloss.hazard.landslide.susceptibility`), polygonises the class codes with
  `rasterio.features.shapes`, one polygon per body of one class, simplifies the
  polygons as a coverage with `shapely.coverage_simplify` at
  `GROUNDWATER_SIMPLIFY_M` so shared edges stay shared (on the NLM's 100 m grid
  the tolerance removes next to nothing), then clips them to the
  flat land, keeping only polygons: where a class polygon only touches the
  flat land the clip leaves a line or a point, which is not ground. The map
  carries the class only: the depth is not kept, because
  nothing downstream reads more than the class.
- The 30 m residual is read, thresholded, sieved and simplified before it is
  polygonised, so the polygons follow bodies of cut and fill rather than the
  1 m cells. `read_residual()` averages the 1 m raster up to
  `RESIDUAL_CLASS_CELL_M` blocks (10 m) strip by strip, so the 1 m grid is
  never held whole: a block is the mean of its cells that hold a value, NaN only
  where none does, and cells short of a whole block at the south and east edge
  are not read. `polygonise_residual()` classes the blocks to the codes of
  `ground_map.MODIFICATION_CODES` (natural 0, cut 1, fill 2) with
  `modification_codes_from_residual()` at `RESIDUAL_MODIFICATION_THRESHOLD_M`,
  and sieves the codes with `rasterio.features.sieve` so no patch is smaller than
  `RESIDUAL_MIN_PATCH_M2` (the area in cells, rounded up; the minimum holds on
  the sieved raster, before simplification, which cuts the staircase corners and
  can leave a polygon a little under it and move the total area a little). The
  sieve runs once
  over all three classes, so **a sieved patch takes the class of its largest
  neighbour, not natural**: a natural pocket inside a fill body becomes fill, and
  a fill speckle inside a cut becomes cut. Cells with no residual are left out
  of the sieve and the polygons. The cut and fill cells are then polygonised
  (natural is the default anyway) and simplified as a coverage with
  `shapely.coverage_simplify` at `RESIDUAL_SIMPLIFY_M`, so an edge a cut and a
  fill patch share stays one edge and the patches leave no gap or overlap.
- `build_ground_map()` takes the sources in precedence order — SLIDE materials,
  1:50,000 geology, NLM `l3_yp` for the material; SLIDE genesis, WCC areas,
  SLIDE materials fill types, residual for the modification; SLIDE genesis for the prior failure; NLM
  groundwater for the groundwater class — unions every source's boundaries and the
  flatland's into one planar partition of the extent with `shapely.polygonize`
  (the boundaries of each geometry's polygonal parts, so a polygon that a clip
  returned inside a GeometryCollection still cuts the map; read whole, the
  collection has no boundary and the pieces either side of it would merge),
  and attributes each piece from the first source whose polygon contains the
  piece's representative point. Where no source reaches it writes `unknown`,
  `natural`, `none` and the class of the configured `DEFAULT_GROUNDWATER_DEPTH_M`
  (well drained at 4 m), taken in `build_ground_map()` with
  `gw_depth_class_from_depth()` and nowhere else, with
  `gw_source` of `assumed`, with `assumed` as the source and `low` as the
  confidence of every other default. Pieces whose only material source says
  water are dropped: open water is not ground. `is_flatland` is whether the
  representative point lies in an NLM flatland polygon, and
  `flatland_version` is `constants.FLATLAND_NLM_VERSION`.
- The Kingsbury groundwater factor reads the class through
  `susceptibility.groundwater_value_from_class()`; the Kingsbury geology value
  follows from the material by `kingsbury_geology_value()` through
  `MATERIAL_GEOLOGY_VALUES` [kingsbury_1995]; and the strength set follows
  from the material by `strength_from_material()`, which maps the material to
  a weathering grade through `MATERIAL_STRENGTH_GRADE` and picks one row of
  that grade from `wellington-greywacke-strength.csv` (read through
  `ASSETS_DIR` at `STRENGTH_TABLE_PATH`): among the rows carrying all of
  `c_eff_kpa`, `phi_eff_deg` and `unit_weight_kn_m3`, `check` false before
  true, then published before the rest, then file order, unless
  `STRENGTH_GRADE_PICKS` names the row. `FILL` is named: it reads S52, the set
  GNS supplied for modelling the Priscilla and Orchy Crescent fills (22 kN/m³,
  c′ 2 kPa, φ′ 42°) [monteith_2020], rather than S48, which the rule would
  pick, a maximum from one densifying Orchy Crescent sample [lyndsell_2019]
  (the lead, 2026-10-02). The picks on the committed table are asserted in
  `tests/landloss/hazard/landslide/test_ground_map.py`.
- Fill thickness is the mean of the positive 100 m residual over each piece
  whose modification is `fill`, computed by `mean_positive_residual()` in
  `gen_ground_map.py`, which reads the 1 m residual in
  full-width strips of at most `THICKNESS_STRIP_CELLS` cells (the residual is
  written in one-row strips, so each row is then decoded once), burns each
  strip's fill pieces onto it and carries the sums and counts per piece from
  strip to strip, so the 1 m grid is never held whole; it is NaN elsewhere.
- `finish()` sorts the pieces by location with `landloss.common.utils.ids.sort_by_point`,
  mints `ground_id` as `GM<7 digits>` with `mint_ids`, measures `area_m2` and
  orders the columns as `COLUMNS` lists them. An id is stable as long as the
  inputs and parameters are; a changed extent renumbers.
- The output is `temp/ground/ground-map[-pilot].geoparquet`, at the
  path `ground_map_path()` returns, one row per `ground_id` in `EPSG:2193`.
  The run prints the area share by material, modification, prior failure,
  groundwater class and flat land, by source for each, and the strength row
  chosen per grade.
- The material and modification over the extent are shown in the figure
  produced by `fig_ground_map.py`, written to
  `report/ground/ground-map/fig/`, with the flat land hatched over
  both panels.

Potential future improvements: see `s2_ground_map_implementation_plan.md`.
