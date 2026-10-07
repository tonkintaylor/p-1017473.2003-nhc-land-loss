# Step 6 — Urban slope candidates: method

- The step writes one row per candidate urban failure polygon at each scale in
  `config.SCALES_M` (1, 3, 10 and 30 m, from `URBAN_SCALES_M`). It is run by
  `gen_urban_slope_candidates.py`, with the extent and the segmentation
  settings in `config.py`. It reads the slope, aspect and 1 m DEM rasters and
  the terrain derivatives landslide step 3 wrote (through `slope_path`,
  `aspect_path`, `dem_path` and `terrain_path`) and the ground map step 4
  wrote (through `ground_map_path`), and fetches the LINZ building outlines,
  road centrelines and property boundaries and the NLM flatland for the
  extent. Walls are not read.
- **The domain** is the union of the building outlines buffered by
  `config.BUILDING_DISTANCE_M` less the NLM flatland, built by
  `landloss.hazard.landslide.urban.delineation.urban_domain`. No insured land
  mask is applied (plan §8.1).
- **The segmentation** at each scale is `delineation.delineate_candidates`,
  the banded connected components of plan §8.2: cells whose centres fall
  outside the domain are set aside; the slope is classed into the bands of
  `delineation.SLOPE_BANDS_DEG` (a value on a break falls in the band above)
  and the downhill azimuth into the eight octants of
  `delineation.ASPECT_OCTANTS`, centred on the compass points; cells of one
  band and one octant that share an edge form a patch
  (`delineation.label_patches`, 4-connected); a level run in the gentlest
  band, which has no octant, joins the gentlest-band neighbour it shares the
  most edges with. Every band produces candidates, the gentlest included.
- **Tiling.** A scale whose slope grid holds more than
  `config.MAX_UNTILED_CELLS` cells (50 million, about 7 by 7 km at 1 m) is
  delineated tile by tile by `delineate_tiled()`, on
  `landloss.common.utils.tiles`: cores of `config.TILE_CORE_M` (3 km) read
  with a margin of `config.TILE_MARGIN_M` (300 m), each delineated against
  the whole domain, and a candidate kept by the tile whose core holds its
  representative point. Every part of the segmentation reads only the cells
  near a patch, so a candidate narrower than the margin comes out as it would
  from the whole grid; the largest 1 m candidate on the two pilots is 231 m
  across. The pilots run whole. Over Porirua only the 1 m scale is tiled.
- **Small patches** under `config.MIN_PATCH_CELLS` (9 cells, a 3 by 3 block at
  every scale) are merged into the neighbouring patch sharing the most cell
  edges, repeatedly, by `delineation.merge_small_patches`. A small patch with
  no neighbour at all is kept.
- **The contour split** cuts a patch wider than `config.MAX_PATCH_LENGTH_M`
  (25 m) across the slope into the fewest equal pieces that each fit, along
  lines parallel to the patch's mean aspect (`delineation.split_long_patches`,
  with `delineation.contour_length_m` measuring the extent perpendicular to
  the aspect). The pieces carry the whole patch's `slope_degrees` and
  `aspect_degrees`. A level patch, whose aspect is NaN, is not cut and has no
  contour length.
- The patch's `slope_band` and `aspect_octant` are the most common among its
  cells, `slope_degrees` is the mean slope and `aspect_degrees` the circular
  mean downhill azimuth of its cells, at the patch's own scale
  (`delineation._patch_statistics`). `aspect_degrees` is in [0, 360): a
  resultant a rounding error west of north reads 0.0, not 360.0. A level
  patch, whose cells have no downhill direction, carries `aspect_octant` of
  `delineation.NO_CLASS` (-1, the value contract section 10 gives a flat
  cell) and NaN `aspect_degrees`; no octant is borrowed from its neighbours.
  The polygons are then trimmed to the domain, so a polygon on the domain
  edge is not a whole cell.
- A scale at which no candidate is found gives an empty frame with the dtypes
  of `delineation.CANDIDATE_DTYPES`, so stacking the scales in
  `delineate_at_scales()` keeps `scale_m` and `aspect_octant` as `int64`
  and `slope_band` as text.
- **Terrain attributes** are read onto each candidate by
  `read_terrain_attributes()`: the mean slope at every scale (`slope_1m` to
  `slope_30m`), the layers and statistics in `TERRAIN_ATTRIBUTES` (the largest
  face height in each window, the mean residual, curvature, topographic
  position and vegetation height), and `relief_m` as the 1 m DEM's maximum
  less its minimum inside the patch. Each is
  `landloss.common.utils.terrain.zonal_statistic` over the polygon, and where
  no cell centre of a coarse raster falls inside a fine patch the value at the
  representative point is taken instead (`read_zonal()`).
  `vegetation_height_m` is NaN where step 3 had no DSM.
- **Distances** to the nearest building outline, road centreline and property
  boundary (the polygons' boundaries) are measured by `nearest()` with
  `geopandas.sjoin_nearest`; `road_distance_m` is to the centreline, with no
  road width taken off. `building_position` is `above`, `below` or `beside`
  from the candidate centroid's 1 m elevation against the nearest outline's
  centroid elevation, `beside` within `BESIDE_TOLERANCE_M` (1 m) either way
  (`building_position()`).
- **The ground map** attributes in `GROUND_COLUMNS` are copied from the ground
  map polygon under the candidate's representative point by
  `read_ground_attributes()`; null where no polygon is there.
- **Ids**: the rows are sorted by `scale_m` descending and then by the
  representative point's x and y (`landloss.common.utils.ids.sort_by_point`)
  and `candidate_id` is minted `UC` plus seven digits from 1
  (`ids.mint_ids`, prefix `CANDIDATE_ID_PREFIX`). An id is stable while the
  inputs and settings are; a changed extent renumbers.
- The output is `temp/hazard/landslide/urban-slope-candidates[-pilot].geoparquet`
  from `urban_slope_candidates_path()`, in EPSG:2193, with the columns of
  `OUTPUT_COLUMNS` in contract order (section 3.4). Rows of different scales
  overlap; nothing chooses between scales here.
- The run prints the candidate count and area by scale and slope band, and
  the nesting depth distribution per scale (how many coarser scales hold a
  candidate over each row's representative point, `nesting_depth()`).
- The candidates per scale, coloured by slope band, are mapped in the figure
  produced by `fig_urban_slope_candidates.py`, written to
  `report/hazard/landslide/urban-slope-candidates/fig/`.
- The snap tolerance the wall lines and step 7 share is
  `delineation.SNAP_TOLERANCE_M` (3 m); this step does not use it.
- The 1 m grid cannot resolve sub-metre faces (limitation **I-03**) and the
  DEM is of mixed survey vintage (**L-12**); both carry through to the
  candidates.

Potential future improvements: see `s6_urban_slope_candidates_implementation_plan.md`.
