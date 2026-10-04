# Step 3 — Multiscale slope: method

## DEM, slope and aspect (`gen_multiscale_slope.py`)

- The step builds a DEM, a slope raster and an aspect raster at each cell size
  in `RESOLUTIONS_M` in `config.py` — 1, 3, 10, 30, 50 and 100 m — and is run
  by `gen_multiscale_slope.py`. The script takes no command line arguments;
  `config.py` is read in its `if __name__ == "__main__":` block and passed into
  `main()`.
- `EXTENT` is `"wlg-pilot"`, so runs go over `SMALL_WLG_PILOT` from
  `landloss.io.area_of_interest`. With it `"full"` the extent is the bounding box
  of the four territorial authorities from `get_study_areas()`.
- The extent is snapped outward in `snap_outward()` to a whole multiple of the
  least common multiple of the cell sizes — 300 m for 1, 3, 10, 30, 50 and 100
  — so every grid tiles it exactly and all of them share its top-left corner.
  It is padded by the same step on every side for the fetch. The padding holds
  the one cell border Horn's kernel cannot compute, and is trimmed off in
  `trim_to_extent()` before anything is written. `trim_to_extent()` selects on
  cell centres, so it never keeps a cell that only touches the box.
- The fetched DEM is cut to the padded extent before any averaging. `get_dem`
  sends the extent to LINZ in WGS84 and the rectangle grows on the round trip,
  so the DEM comes back larger than asked, with its corner off the round
  coordinate the blocks have to be counted from.
- Only the finest cell size, 1 m, is fetched, by `landloss.io.readers.get_dem`,
  which reads LINZ's STAC elevation catalogue: LiDAR where flown, the 8 m
  contour-derived model elsewhere. It carries limitation L-12, the mixed LiDAR
  vintage across the study area. Rasters are read back with nodata as NaN by
  `read_layer()`, which every other script in the step reuses.
- Every coarser DEM is the block mean of the finest, from
  `landloss.common.utils.terrain.block_mean()`. Blocks are counted from the
  grid's top-left corner, so the grids nest; part blocks along the bottom and
  right edges are dropped; and a block less than half real ground is NaN. This
  is done here rather than by asking LINZ for the coarse size, because LINZ's
  loader resamples bilinearly and would sample rather than average the ground.
  `check_resolutions()` refuses a cell size that is not a whole multiple of the
  finest.
- Slope is Horn's method, `landloss.common.utils.terrain.slope_degrees()`, the
  same as every other slope in the study, computed on each DEM at its own cell
  size. A 100 m slope is the gradient over about 300 m, not a smoothed 1 m
  slope.
- Aspect is the downhill bearing of the same Horn gradient,
  `landloss.common.utils.terrain.downhill_azimuth_degrees()`, in degrees
  clockwise from grid north and pointing downslope, NaN on level ground. It is
  the study's aspect; no separate uphill aspect is computed.
- The run prints, per cell size, the grid, its top-left origin, the elevation
  range, the slope deciles, the share of the extent in Kingsbury's slope
  classes (`SLOPE_CLASS_EDGES`), the aspect NaN count and the share facing each
  octant (`OCTANT_NAMES`).
- Outputs are `dem-<n>m.tif` (`dem_path()`), `slope-<n>m.tif` (`slope_path()`,
  band `slope_degrees`) and `aspect-<n>m.tif` (`aspect_path()`, band
  `downhill_azimuth_degrees`) under `temp/hazard/landslide/`, with the extent's
  `extent_suffix` (`-pilot` for `"wlg-pilot"`). They are working layers and are not committed.
- The slopes and aspects at every cell size are drawn side by side by
  `fig_multiscale_slope.py`, written to
  `report/hazard/landslide/multiscale-slope/fig/`.

## Terrain derivatives (`gen_terrain_derivatives.py`)

- `gen_terrain_derivatives.py` reads the 1, 3, 10, 30 and 100 m DEMs the script
  above wrote, through `dem_path()`, and fetches only the LINZ 1 m surface
  model. It reads the same `config.py`: `USE_CACHED_DSM`,
  `FACE_HEIGHT_WINDOWS_M`, `RESIDUAL_BASE_RESOLUTIONS_M`,
  `TOPOGRAPHIC_POSITION_WINDOWS_M` and `CURVATURE_RESOLUTION_M`.
- Every layer, its file and its band name are listed in `TERRAIN_LAYERS`, and
  `terrain_path(layer, extent=...)` is the one function that names a file; the
  curvature file carries the cell size it was computed on, from `config.py`.
  Outputs go under `temp/hazard/landslide/terrain/` with the extent's
  `extent_suffix`, as float32, and are not committed.
- Face height is the local relief of the 1 m DEM in a 5 m and a 10 m window,
  `landloss.common.utils.terrain.local_relief()` (`face-height-5m`,
  `face-height-10m`, band `local_relief_m`).
- The cut and fill residual is the 1 m DEM minus the 30 m and the 100 m DEM
  resampled bilinearly onto the 1 m grid,
  `landloss.common.utils.terrain.cut_fill_residual()`
  (`cut-fill-residual-30m`, `cut-fill-residual-100m`, band
  `cut_fill_residual_m`): negative where the ground was cut below the smoothed
  surface, positive where it was filled.
- Profile curvature is Zevenbergen and Thorne's 3×3 fit
  [zevenbergen_thorne_1987] on the 3 m DEM, not the 1 m one, in 1/m with the
  ArcGIS sign — negative on convex ground, positive on concave —
  `landloss.common.utils.terrain.profile_curvature()` (`profile-curvature`,
  file `profile-curvature-3m`, band `profile_curvature_per_m`). Level ground
  reads zero.
- Topographic position is `landloss.common.utils.terrain.topographic_position()`
  in a 20 m window on the 3 m DEM and a 100 m window on the 10 m DEM, so the
  wide window is 11 cells rather than 101 (`topographic-position-20m`,
  `topographic-position-100m`, band `topographic_position_m`).
- Vegetation height is the LINZ 1 m surface model minus the 1 m DEM, clipped at
  zero, `landloss.common.utils.terrain.vegetation_height()`
  (`vegetation-height`, band `vegetation_height_m`), with every cell whose
  centre lies inside a LINZ building outline set to NaN, so a roof is not read
  as canopy. The outlines are read over the same bounds with
  `landloss.io.readers.get_nz_building_outlines`. The surface model comes
  from `landloss.io.readers.get_dsm()`, fetched over the 1 m DEM's own bounds:
  it walks the `/dsm_1m/` collections of LINZ's elevation STAC catalogue,
  mosaics the tiles newest survey first, and caches under
  `koopcache_dir("dsm")`. There is no contour-derived fallback for a surface
  model, so where no LiDAR survey covers a cell the vegetation height is NaN.
  The surface model is CC BY 4.0 and anything published from it credits LINZ
  and the survey (the `Licence:` section of `get_dsm`).
- Each derivative carries a NaN border half its window wide inside the extent,
  because the DEMs on disk are already trimmed to the snapped extent when the
  windows are run; the width per layer is listed in the implementation plan.
- The run prints, per layer, the grid, the NaN count and the deciles.
- Every layer is drawn over the extent by `fig_terrain_derivatives.py`, written
  to `report/hazard/landslide/terrain-derivatives/fig/`.

Potential future improvements: see `s3_multiscale_slope_implementation_plan.md`.
