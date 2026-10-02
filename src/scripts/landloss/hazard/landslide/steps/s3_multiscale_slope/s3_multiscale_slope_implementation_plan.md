# Step 3 — Multiscale slope: implementation plan

**Status:** Phase 1 complete over the pilot: `dem-<n>m-pilot.tif`,
`slope-<n>m-pilot.tif` and `aspect-<n>m-pilot.tif` at every cell size are on
disk under `temp/hazard/landslide/`. Phase 4 is built and tested but has not
been run over the pilot: `temp/hazard/landslide/terrain/` does not exist and
neither figure has been drawn. The full study area has not been run, and cannot
be at 1 m without tiling (phase 2).

## Background

Slope is a property of the length it is measured over, and the models the
landslide hazard draws on were calibrated at different ones: Kingsbury's slope
classes against a 20 m contour model, the global earthquake-induced landslide
models against 30 m and coarser grids, and the urban slope failure candidates
are delineated at 1, 3, 10 and 30 m (`constants.URBAN_SCALES_M`). This step
builds the DEM, the slope and the aspect at 1, 3, 10, 30, 50 and 100 m so the
hazard work can read whichever its calibration needs, and derives from those
DEMs the terrain layers the urban slope build reads: face height, the cut and
fill residual, profile curvature, topographic position and vegetation height
(`.agents/plans/urban-slope-build-contract.md`, section 3.1).

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

- [ ] Run with `PILOT = False` over the four territorial authorities. At 1 m
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
      record it in their method documents. The urban slope contract fixes the
      candidates at 1, 3, 10 and 30 m, the slope units at 10 m, and the wall
      lines at 3 m with a 10 m sloping-ground test.

## Phase 4 — Terrain derivatives (built; pilot run outstanding)

- [x] `cut_fill_residual()`, `profile_curvature()`, `vegetation_height()`,
      `mean_azimuth_degrees()`, `azimuth_sd_degrees()`, `zonal_statistic()` and
      `zonal_azimuth_mean()` added to `landloss.common.utils.terrain`, with
      tests.
- [x] `landloss.io.readers.get_dsm()`, fetching the LINZ 1 m surface model by
      walking the `/dsm_1m/` collections of the elevation STAC catalogue and
      mosaicking the tiles newest survey first, cached under
      `koopcache_dir("dsm")`.
- [x] `gen_terrain_derivatives.py` writing the eight layers of
      `TERRAIN_LAYERS` under `temp/hazard/landslide/terrain/`, with
      `terrain_path()` as the one path function.
- [x] `fig_terrain_derivatives.py` drawing every layer over the extent.
- [ ] Run `gen_terrain_derivatives.py` over the pilot so the eight layers of
      `TERRAIN_LAYERS` exist under `temp/hazard/landslide/terrain/`, then draw
      `fig_multiscale_slope.py` and `fig_terrain_derivatives.py`. Tick this
      only once those files are on disk; steps 4 to 7 and the wall lines read
      them, so the chain has not been run past phase 1 until it is.
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

## Potential future improvements

- Tile the full-extent run (phase 2) rather than carrying 1 m grids whole.
- Keep the padded DEMs through the derivatives so no derivative carries a NaN
  border inside the extent.
- `linz_stac_utils` offers no surface model product; if it gains one,
  `get_dsm` can take the same route as `get_dem` and drop the catalogue walk.
- `landloss.io.elevation.find_dem_collections` and `readers.find_dsm_tiles`
  walk the same catalogue for different path markers; a `path_marker`
  argument on the former would let the latter reuse it.
