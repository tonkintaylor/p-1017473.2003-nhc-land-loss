# Step 2 — Slope failure susceptibility: method

- The step scores earthquake-induced slope failure susceptibility on the scheme
  published by Kingsbury (1995) in WRC/PP-T-95/06 to /10, rather than deriving
  anything from Greater Wellington's layer built on that scheme, which is
  CC BY-ND. It is run by `gen_slope_susceptibility.py` and checked against the
  published layer by `fig_slope_susceptibility.py` in the same folder.
- The scheme itself — the factor classes, their values, the weightings and the
  zone bands — is `landloss.hazard.landslide.susceptibility`. All four map
  sheets covering the study area carry the identical table, so it is one scheme
  applied region wide. `tests/landloss/hazard/landslide/test_susceptibility.py`
  reproduces the worked examples Kingsbury published for moderate, high and very
  high ground; the two lowest examples reach their stated totals using factor
  values the source does not define for the factors concerned, and are not
  reproduced.
- The rating is the weighted sum of six factors, computed by
  `susceptibility_rating()`, and banded into five zones by
  `susceptibility_zone()`. The zone ranks are the published layer's own
  `SEVERITY` classes, 1 to 5, which is what lets the rebuilt and published
  zonations share a colour scale in the figure.
- What a run covers and what it is configured with is set by `config.py` beside
  the scripts, read in each script's `if __name__ == "__main__":` block and
  passed into `main()` as keyword arguments. Neither script takes command line
  arguments and neither `main()` carries a default. `EXTENT` is
  `"wlg-earthworks-pilot"`, so runs go over `WLG_EARTHWORKS_PILOT` —
  Johnsonville and Newlands — rather than the whole Wellington City earthworks
  extent (`"full"`), which `earthworks_extent()` derives
  from the records themselves. Outputs carry the extent's `extent_suffix`, so a
  pilot run writes `*-wlg-earthworks-pilot.tif`.
- `WLG_EARTHWORKS_PILOT` was added to `landloss.io.area_of_interest` for this
  step. `SMALL_WLG_PILOT`, which the rest of the project develops against, sits
  over Mt Victoria and Hataitai and contains no earthworks polygons at all, so it
  cannot exercise the modification factor.
- **Slope angle** is read from the LINZ elevation model at
  `COARSE_RESOLUTION_M`, 10 m, which is the resolution the rating is reported
  on. Horn's kernel there measures gradient over about 20 to 30 m, close to the
  20 m contour terrain model Kingsbury's class boundaries were calibrated
  against. The coarse grid is made by averaging the fine model down in
  `coarse_template()`.
- **Cut angle and face height** are read at `FINE_RESOLUTION_M`, 1 m, because a
  subdivision cut face is about one coarse cell wide and averages away to a
  gentle slope at 10 m. Kingsbury split the scales the same way — slope at
  1:25,000, cut slopes at 1:10,000 to 1:20,000 in urban areas.
- **Slope modification** is scored by `modification_factor()` inside the mapped
  Wellington City earthworks polygons only, read by
  `landloss.io.readers.get_wcc_cut_areas` and `get_wcc_fill_areas`. A cut is
  scored on the angle of its face; a sidling fill is scored at the top of the
  scale whatever its angle, because the failure is on the contact the fill was
  placed on. Where a cut and a fill polygon overlap the higher score wins.
  Everywhere outside a mapped polygon scores nil, and the run prints what share
  of the extent that leaves — nil modification means a cell cannot reach the
  high or very high zone on modification at all.
- **Face height** is the elevation range in a moving window of
  `SLOPE_HEIGHT_WINDOW_M`, 50 m, computed by
  `landloss.common.utils.terrain.local_relief`. It is a proxy for a measured toe
  to crest height. The factor is scored only where the face is steeper than 45
  degrees, following Kingsbury's own note that it does not apply to natural 35
  to 45 degree slopes such as coastal cliffs or the Wellington Fault scarp; that
  restriction lives in `slope_height_value()`.
- The fine factors are aggregated onto the coarse grid by **maximum**, in
  `to_coarse_maximum()`, following the source's statement that a steep component
  controls the stability of the whole slope it sits on. One steep fine cell
  therefore lifts its whole coarse cell.
- **Geology** is read from the National Liquefaction Model's geomorphology
  polygons by `geology_factor()`, which maps the **`l3_yp` material class** to a
  factor value through `NLM_MATERIAL_GEOLOGY_VALUES` and burns it onto the
  coarse grid. `l3_yp` is the field read, not the coarser `l2_geomorphology` and
  not `main_rock`; the constant's comment says why. Open water is mapped to NaN
  and left unscored rather than given a value. In substance the mapping is still
  binary — basement rock takes the highly to completely weathered greywacke
  class, everything unconsolidated takes colluvium and alluvium — because the
  model maps neither weathering nor shearing, so two of Kingsbury's four classes
  are never reached whatever field is read. A material with no class assigned
  raises rather than defaulting. The extent is taken from the grid rather than
  passed in, so the working margin is scored too.
- **Groundwater** is read from the National Liquefaction Model's median depth
  grid by `groundwater_factor()`, and converted to a factor value by
  `groundwater_value()`. The depth thresholds are this study's, not the
  source's, and the reasoning is in the comment on
  `GROUNDWATER_SATURATED_DEPTH_M`: a water table inside the one to two metre
  colluvium layer the booklets say fails is the saturated case, one just below
  it the poorly drained case, one well below it drains. This is the only factor
  that scores lower as its measurement rises.
- The groundwater grid **covers flat land only**, about a third of the pilot
  extent and 7% of its own cells nationally. Off that footprint the depth is
  filled with `DEFAULT_GROUNDWATER_DEPTH_M`, 4 m, which puts hill country in the
  well drained class; the alternative, carrying NaN through, would leave every
  hillside unscored. It is resampled by nearest neighbour rather than bilinear,
  because the edge of the modelled footprint is a hard boundary and
  interpolating across it would spread NaN inland.
- Both NLM layers are project data from the same team that built this study, so
  they are read without an attribution or permission step; the layers themselves
  stay inside T+T. The readers say so.
- **The landslide factor is the only constant left**, at zero, because no
  inventory is held. `describe_landslide_constant()` says so on every run; it
  removes up to 20 of the 150 points.
- `describe_baseline()` prints what a cell scores before any terrain is read.
  Over the pilot that is 8 to 25 points, median 8, and about nine tenths of the
  extent starts below the 20 point band — so the very low zone is reachable,
  which it was not while geology and groundwater were held constant.
- The 1995 generalisation rules are not applied. The published product is
  generalised polygons — steep facets expanded to the whole slope, a downslope
  runout allowance added, every modified slope forced into the high or very high
  zone — and this step produces a scored grid instead. The rebuilt grid is
  consequently less severe at the top of the scale, and both scripts say so in
  their output.
- Outputs are two GeoTIFFs under `temp/hazard/landslide/`, the rating and the
  banded zone, at paths given by `rating_path()` and `zone_path()`. The figure
  script calls those functions rather than rebuilding the names, which is what
  keeps it drawing the run that was made. `temp/` is gitignored; the layers are
  rebuildable from the elevation model and the earthworks records.
- The comparison against the published layer is the figure produced by
  `fig_slope_susceptibility.py`, written to
  `report/hazard/landslide/slope-failure-susceptibility/fig/`. Both panels use
  the palette in `landloss.common.utils.colors.GWRC_SEVERITY_COLOURS`, and the
  published layer is drawn unchanged, which is what its licence permits. The
  script prints the share of the extent in each zone for both, and does not
  compute a rank correlation between them, because a generalised polygon map and
  a scored grid would disagree mostly about that difference.

Potential future improvements: see `s2_slope_failure_susceptibility_implementation_plan.md`.
