# Ground step 1 — Terrain: implementation plan

**Status:** Phase 1 complete over the pilot: `dem-<n>m-pilot.tif`,
`slope-<n>m-pilot.tif` and `aspect-<n>m-pilot.tif` at every cell size are on
disk under `temp/ground/`. Phase 4 ran over the pilot in the
whole-chain run of 2026-10-02: the eight layers then written are under
`temp/ground/terrain/`, but neither figure has been drawn. Since
2026-10-08 the step writes only three of them (phase 4, note); the other five
went with the old candidate method. Phase 5 is what the faces plan
needs from this step. The full study area has not been run, and cannot be at
1 m without tiling (phase 2). The step was landslide step 3 until 2026-10-08,
when it moved into the ground module; `gen_ground.py` runs it.

## Background

Slope is a property of the length it is measured over, and the models the
landslide hazard draws on were calibrated at different ones: Kingsbury's slope
classes against a 20 m contour model, the global earthquake-induced landslide
models against 30 m and coarser grids, and the old urban slope failure
candidates were delineated at 1, 3, 10 and 30 m (`constants.URBAN_SCALES_M`,
removed 2026-10-08 with the old landslide step 6). This step
builds the DEM, the slope and the aspect at 1, 3, 10, 30, 50 and 100 m so the
hazard work can read whichever its calibration needs, and derives from those
DEMs the terrain layers the urban slope build read: face height, the cut and
fill residual, profile curvature, topographic position and vegetation height
(`.agents/plans/urban-slope-build-contract.md`, section 3.1). Only the cut
and fill residuals and the 100 m topographic position are still derived.

The coarse DEMs are block means of the 1 m fetch rather than separate fetches
from LINZ, because LINZ's elevation loader resamples bilinearly and reads a
handful of points per 100 m cell rather than the ground under it.

## Phase 1 — Build the DEM, slope and aspect at each cell size (complete)

- [x] Add `block_mean()` to `landloss.common.utils.terrain`, averaging whole
      blocks and masking blocks under half real ground.
- [x] Fetch the finest DEM once over the extent, snapped to the least common
      multiple of the cell sizes and padded by one, and block-average it to
      every coarser size.
- [x] Compute Horn's slope at each cell size, trim the margin, and write the DEM
      and slope per cell size.
- [x] Print the grid, the slope deciles and the share in Kingsbury's slope
      classes per cell size.
- [x] Fetch at 1 m and build 1, 3, 10, 30, 50 and 100 m (`RESOLUTIONS_M`).
- [x] Write the aspect per cell size, as the downhill azimuth of the same Horn
      gradient (`aspect-<n>m.tif`, band `downhill_azimuth_degrees`), and print
      the share of the extent facing each octant.
- [x] Path wrappers `dem_path()`, `slope_path()` and `aspect_path()`, so no
      consumer spells a layer kind.

## Phase 2 — Full study area

- [ ] Run with `EXTENT = "full"` over the four territorial authorities. At 1 m
      the study area bounding box is about 3.2 billion cells, which neither the
      fetch nor the Horn kernel can carry in memory; the step has to be tiled
      over the snapped 300 m grid, with each tile fetched padded by one cell
      size and the derivatives written as a mosaic, before the full extent is
      launched. The project lead launches the full run.
- [ ] Decide whether the 10 m DEM here should replace the one the land value
      step fetches separately, so the study holds one 10 m DEM rather than two
      over slightly different extents.

## Phase 3 — Comparison

- [x] A `fig_multiscale_slope.py` figure of the slopes side by side over the
      extent, with the aspects under them.
- [ ] Decide which cell size each hazard consumer reads — the susceptibility
      step's slope factor, the realisation step's failure probability — and
      record it in their method documents. The urban slope contract fixed the
      candidates at 1, 3, 10 and 30 m, the slope units at 10 m, and the wall
      lines at 3 m with a 10 m sloping-ground test (the candidates and wall
      lines were removed 2026-10-08).

## Phase 4 — Terrain derivatives (built; pilot run outstanding)

Removed 2026-10-08 with the old candidate method: `face-height-5m`,
`face-height-10m`, `profile-curvature`, `topographic-position-20m` and
`vegetation-height` (and the DSM fetch and building mask behind the last), the
config `FACE_HEIGHT_WINDOWS_M`, `CURVATURE_RESOLUTION_M` and `USE_CACHED_DSM`,
and `profile_curvature`, `vegetation_height`, `zonal_statistic` and
`zonal_azimuth_mean` in `landloss.common.utils.terrain`. Only
`cut-fill-residual-30m`, `cut-fill-residual-100m` and
`topographic-position-100m` remain. The items below are history.

- [x] `cut_fill_residual()`, `profile_curvature()`, `vegetation_height()`,
      `mean_azimuth_degrees()`, `azimuth_sd_degrees()`, `zonal_statistic()` and
      `zonal_azimuth_mean()` added to `landloss.common.utils.terrain`, with
      tests.
- [x] `landloss.io.readers.get_dsm()`, fetching the LINZ 1 m surface model by
      walking the `/dsm_1m/` collections of the elevation STAC catalogue and
      mosaicking the tiles newest survey first, cached under
      `koopcache_dir("dsm")`.
- [x] `gen_terrain_derivatives.py` writing the eight layers of
      `TERRAIN_LAYERS` under `temp/ground/terrain/`, with
      `terrain_path()` as the one path function.
- [x] `fig_terrain_derivatives.py` drawing every layer over the extent.
- [~] Run `gen_terrain_derivatives.py` over the pilot so the eight layers of
      `TERRAIN_LAYERS` exist under `temp/ground/terrain/`, then draw
      `fig_multiscale_slope.py` and `fig_terrain_derivatives.py`. The layers
      were written in the whole-chain run of 2026-10-02; the figures are not
      drawn, and the vegetation height is rewritten with the building mask on
      the next run.
- [ ] The border of each derivative is NaN by half its window (two and five
      1 m cells for the face heights, one 3 m cell for the curvature, three
      3 m cells and five 10 m cells for the topographic positions), because
      the DEMs on disk are trimmed to the snapped extent before the windows are
      run. Harmless over the pilot, whose snapped extent is wider than the
      pilot box; to remove it, keep the padded DEMs and trim after the
      windows, as the slope script already does for Horn's kernel.
- [x] Mask the building outlines out of the vegetation height, so a roof is
      not read as canopy (2026-10-02). Tested on a synthetic roof; the pilot
      layer is rebuilt on the next run of `gen_terrain_derivatives.py`.

## Phase 5 — What the faces layer needs (from the literature review, 2026-10-02)

`.agents/plans/building-face-based-urban-slope-polygons.md` builds the faces
from this step's 1 m DEM. Reviewed against `temp/gns_review/` on 2026-10-02.

- [ ] **DEM source and survey year per cell.** `get_dem` mosaics LiDAR where
      flown and the 8 m contour model elsewhere (L-12). Write a source raster
      beside the 1 m DEM, LiDAR or contour, and the survey year, so the faces
      are found only on LiDAR and a wall built after the flight is known to be
      missing. The 1 m LiDAR model is already coarse for site work
      [nzgs_2025_recognition] (`nzgs2025-u2-F23`), and a map should not be
      shown at a scale markedly finer than its data [de_vilder_2024]
      (`devilder2024-F28`); a face drawn on the contour model would be both.
      LiDAR slope maps do pick up most of Wellington City's cut slopes
      [hancox_2013_slope_types] (`sr2013-058-F03`), which is the case for the
      approach where LiDAR exists.
- [ ] **One extent**, from `run_extent(name)` (faces plan, phase 0), so ground steps
      1 and 2 cover the same ground.
- [x] **Retire `face-height-5m` and `face-height-10m`** once the wall lines
      read the faces (done 2026-10-08, with the lines): local relief reads high on any hillside, wall or not,
      and the faces' step height replaces it.
- [~] Keep the 20 m and 100 m topographic position (only the 100 m one is
      kept; the 20 m layer was removed 2026-10-08): a landform proxy for the
      weathering grade (ground step 2 plan, phase 3) would read them
      [nzgs_2025_torlesse] (`nzgs2025-u7c2-F01`).

- [x] Build the slope and the aspect only at `SLOPE_RESOLUTIONS_M` (10 m and
      coarser); the DEM is still built at every size (2026-10-09).

## Potential future improvements

- Tile the full-extent run (phase 2) rather than carrying 1 m grids whole.
- Keep the padded DEMs through the derivatives so no derivative carries a NaN
  border inside the extent.
- `linz_stac_utils` offers no surface model product; if it gains one,
  `get_dsm` can take the same route as `get_dem` and drop the catalogue walk.
- `landloss.io.elevation.find_dem_collections` and `readers.find_dsm_tiles`
  walk the same catalogue for different path markers; a `path_marker`
  argument on the former would let the latter reuse it.
