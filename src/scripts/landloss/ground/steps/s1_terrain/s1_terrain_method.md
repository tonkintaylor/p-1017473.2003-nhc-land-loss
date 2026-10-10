# Ground step 1 — Terrain: method

## DEM, slope and aspect (`gen_multiscale_slope.py`)

- The step builds a DEM at each cell size in `RESOLUTIONS_M` in `config.py` —
  1, 3, 10, 30, 50 and 100 m — and a slope raster and an aspect raster at each
  in `SLOPE_RESOLUTIONS_M` — 10, 30, 50 and 100 m. The 1 m and 3 m slope and
  aspect are not built (the lead, 2026-10-09): nothing in the pipeline reads
  them, and over Upper Hutt the two at 1 m alone were 8.8 GB.
  `fig_multiscale_slope.py` draws every size in `RESOLUTIONS_M` and stops with
  a message naming `SLOPE_RESOLUTIONS_M` if one is missing. The step is run
  by `gen_multiscale_slope.py`, which `gen_ground.py` runs first ("s1, multiscale
  slope and aspect"). The script takes no command line arguments;
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
  `downhill_azimuth_degrees`) under `temp/ground/`, with the extent's
  `extent_suffix` (`-pilot` for `"wlg-pilot"`). They are working layers and are
  not committed.
- The slopes and aspects at every cell size are drawn side by side by
  `fig_multiscale_slope.py`, written to
  `report/ground/multiscale-slope/fig/`.

## Terrain derivatives (`gen_terrain_derivatives.py`)

- `gen_terrain_derivatives.py` ("s1, terrain derivatives" in `gen_ground.py`) reads the 1, 10, 30 and 100 m DEMs the script
  above wrote, through `dem_path()`, and fetches nothing. It reads the same
  `config.py`: `RESIDUAL_BASE_RESOLUTIONS_M` and
  `TOPOGRAPHIC_POSITION_WINDOWS_M`.
- Every layer, its file and its band name are listed in `TERRAIN_LAYERS`, and
  `terrain_path(layer, extent=...)` is the one function that names a file.
  Outputs go under `temp/ground/terrain/` with the extent's
  `extent_suffix`, as float32, and are not committed.
- The cut and fill residual is the 1 m DEM minus the 30 m and the 100 m DEM
  resampled bilinearly onto the 1 m grid,
  `landloss.common.utils.terrain.cut_fill_residual()`
  (`cut-fill-residual-30m`, `cut-fill-residual-100m`, band
  `cut_fill_residual_m`): negative where the ground was cut below the smoothed
  surface, positive where it was filled.
- Topographic position is `landloss.common.utils.terrain.topographic_position()`
  in a 100 m window on the 10 m DEM, so the window is 11 cells rather than 101
  (`topographic-position-100m`, band `topographic_position_m`).
- Only these three layers are written. The face heights, profile curvature,
  20 m topographic position and vegetation height (with the LINZ surface model
  fetch and the building mask it needed) were read only by the old landslide
  step 6 and exposure rw step 6's candidate wall lines, and were removed with
  them on 2026-10-08. `landloss.io.readers.get_dsm()` stays as a general reader.
- Each derivative carries a NaN border half its window wide inside the extent,
  because the DEMs on disk are already trimmed to the snapped extent when the
  windows are run; the width per layer is listed in the implementation plan.
- The run prints, per layer, the grid, the NaN count and the deciles.
- Every layer is drawn over the extent by `fig_terrain_derivatives.py`, written
  to `report/ground/terrain-derivatives/fig/`.

Potential future improvements: see `s1_terrain_implementation_plan.md`.
