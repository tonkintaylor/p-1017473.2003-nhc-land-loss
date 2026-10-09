# Landslide step 1 — Slope units: method

- The step cuts one polygon per hillslope facet, from a drainage line at the
  bottom to the ridge at the top with one broad aspect, over the whole extent,
  and is run by `gen_slope_units.py`. The script takes no command line
  arguments; `config.py` is read in its `if __name__ == "__main__":` block and
  passed into `main()`.
- `EXTENT` is `"wlg-pilot"`, so runs go over `SMALL_WLG_PILOT`, the extent ground steps 1 and
  2 wrote. The inputs are the 10 m DEM, slope and downhill azimuth ground step 1
  wrote (`gen_multiscale_slope.dem_path(10, ...)`, `slope_path(10, ...)`,
  `aspect_path(10, ...)`) and the ground step 2 ground map
  (`gen_ground_map.ground_map_path(...)`), resolved in `input_paths()`.
- The delineation is `landloss.hazard.landslide.slope_units.delineate_slope_units()`,
  the `r.slopeunits` logic of [alvioli_2016] without GRASS, in this order:
  - **Routing.** `landloss.common.utils.hydrology.route_grid()`: priority
    flood, D8 receivers on the filled surface, and the accumulation of cell
    area. pysheds is not used (see the plan).
  - **Channels.** `channel_cells()` marks every cell whose upstream area
    reaches `CHANNEL_THRESHOLD_HA`; `channel_links()` labels each reach between
    junctions, the junction cell starting the downstream link.
  - **Catchments.** `link_catchments()` gives every cell the link it drains to,
    walking the flood order downstream first. A cell whose flow leaves the grid
    before reaching a channel, as a coastal slope draining into the sea does,
    takes the catchment of the nearest labelled cell, so no part of the extent
    is outside every unit. Where no cell reaches the threshold at all, every
    valid cell is basin 1, so a small extent or a high threshold gives one
    unit rather than none.
  - **Half-basins.** `split_half_basins()` puts each cell on the left or right
    bank of its link by the sign of the cross product of the link's chord, head
    to tail, and the vector from the nearest link cell to the cell. A cell on
    the link itself takes the side its own downhill azimuth points to; a basin
    with no link (the no-channel case above) goes wholly left. The cells of
    each link and each catchment are grouped once per grid by one stable sort
    (`_cells_by_label()`), not by a scan of the grid per link.
  - **Polygons.** `units_to_polygons()` polygonises the half-basin labels with
    4-connectivity, one row per connected piece, so every unit is a plain
    polygon.
  - **Merge.** `merge_similar_aspect()` first absorbs every unit under
    `MIN_UNIT_AREA_HA` into the edge neighbour whose circular mean aspect is
    closest to its own, smallest first, then repeatedly merges the adjacent
    pair whose mean aspects differ least while that difference is under
    `ASPECT_MERGE_TOLERANCE_DEG` and the merged area is under
    `MAX_UNIT_AREA_HA`. A merged unit keeps the `basin_id` and `side` of the
    larger of the two.
  - **Split.** `split_by_aspect_variance()` halves every unit over
    `MAX_UNIT_AREA_HA` by k-means (k = 2, seeded) on its cells' aspect unit
    vectors. A unit facing one way, where the k-means finds only noise, is
    halved by position instead. Each connected piece becomes a unit, and the
    pass repeats until none is over the maximum; each unit is worked in its
    own bounding window of the grid. The split and the merge then alternate
    up to three times, because absorbing a fragment can push a unit back over
    the maximum.
- The unit attributes are read off the three rasters by rasterising the final
  polygons back onto the grid and grouping the cells by unit once: `area_m2`
  is the polygon's area; `mean_slope_degrees` is the mean of the 10 m slope;
  `mean_aspect_degrees` and `aspect_sd_degrees` are
  `landloss.common.utils.terrain.mean_azimuth_degrees()` and
  `azimuth_sd_degrees()` of the 10 m downhill azimuth, so the mean is in
  [0, 360) and NaN where the azimuths cancel exactly; `min_elevation_m`,
  `max_elevation_m` and `relief_m` come from the 10 m DEM. The merge keeps
  area-weighted resultant vectors between merges and reads their bearing with
  the same fold of 360 to 0.
- Units are cut over the whole extent and none is dropped. `flatland_share`,
  from `flatland_share()` in `gen_slope_units.py`, is the share of each unit's
  area inside the union of the ground map polygons flagged `is_flatland`; the
  realisation step places failures only where its coverage raster carries a
  value.
- `unit_id` is `SU` and seven digits, minted by location with
  `landloss.common.utils.ids.sort_by_point` and `mint_ids`: the units are
  sorted by representative point x then y and numbered from 1, so the same
  inputs and settings give the same ids and a changed extent renumbers.
- The run cuts the units once per threshold in `CHANNEL_THRESHOLDS_TRIED_HA`
  and prints the unit count, the median and the largest unit area at each, in
  `sensitivity_table()`; the layer written is the one at
  `CHANNEL_THRESHOLD_HA`. It also prints the unit count, the area deciles, the
  count per side and the flatland share, in `describe_units()`.
- The output is `temp/hazard/landslide/slope-units[-pilot].geoparquet` from
  `slope_units_path()`, one row per `unit_id` with the columns of contract
  section 3.3 in `OUTPUT_COLUMNS`, in EPSG:2193. It is a working layer and is
  not committed.
- The units, coloured by mean aspect on a cyclic colour map with their
  outlines, are mapped over the extent in the figure produced by
  `fig_slope_units.py`, written to `report/hazard/landslide/slope-units/fig/`.
- The tests in `tests/landloss/hazard/landslide/test_slope_units.py` cut a
  synthetic V-shaped valley into two half-basins of opposite aspect, merge them
  at a wide tolerance, split them at a small maximum with no cell dropped, and
  run `main()` on rasters and a ground map written to a temporary directory.
  `tests/landloss/common/utils/test_hydrology.py` covers `route_grid()`.

Potential future improvements: see `s1_slope_units_implementation_plan.md`.
