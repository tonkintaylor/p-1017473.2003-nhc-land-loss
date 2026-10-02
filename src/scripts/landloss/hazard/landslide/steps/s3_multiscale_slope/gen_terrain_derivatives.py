"""Derive the terrain layers the urban slope work reads from step 3's DEMs.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s3_multiscale_slope/gen_terrain_derivatives.py

Run ``gen_multiscale_slope.py`` first, over the same extent: this reads the 1,
3, 10, 30 and 100 m DEMs it wrote and fetches only the LINZ 1 m surface model,
which needs no API key. The run settings come from config.py beside this
script rather than from the command line.

Each layer is one function of :mod:`landloss.common.utils.terrain` applied to
one of those DEMs:

- **Face height**, the local relief in a 5 m and a 10 m window on the 1 m DEM:
  how tall the face under a cell is, which is what a wall line reads its
  height off.
- **Cut and fill residual**, the 1 m surface minus the 30 m and the 100 m
  surfaces: negative where the ground was cut below the smoothed hillside,
  positive where it was filled out from it.
- **Profile curvature** on the 3 m DEM, not the 1 m one, because curvature on
  the raw LiDAR grid is survey noise.
- **Topographic position** in a 20 m window on the 3 m DEM and a 100 m window
  on the 10 m DEM, so the wide window is 11 cells rather than 101.
- **Vegetation height**, the surface model minus the 1 m DEM. NaN wherever no
  surface model survey covers a cell.

Writes one GeoTIFF per layer under temp/hazard/landslide/terrain/, with a
``-pilot`` suffix for a pilot run. The file names and band names are in
``TERRAIN_LAYERS``; every consumer asks ``terrain_path()`` for a file rather
than spelling a name.
"""

import sys

import numpy as np

from landloss.common.utils.terrain import (
    CUT_FILL_RESIDUAL_NAME,
    LOCAL_RELIEF_NAME,
    PROFILE_CURVATURE_NAME,
    TOPOGRAPHIC_POSITION_NAME,
    VEGETATION_HEIGHT_NAME,
    cut_fill_residual,
    local_relief,
    profile_curvature,
    topographic_position,
    vegetation_height,
    write_raster,
)
from landloss.domain import constants
from landloss.io.readers import get_dsm, get_nz_building_outlines
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import config
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    DECILES,
    RULE,
    WORK_DIR,
    dem_path,
    read_layer,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TERRAIN_DIR = WORK_DIR / "terrain"

# Every layer this script writes, keyed as its consumers ask for it, mapped to
# the band name the raster carries. The keys name the window or base surface
# the layer was computed with; the band names are the terrain module's own.
TERRAIN_LAYERS = {
    "face-height-5m": LOCAL_RELIEF_NAME,
    "face-height-10m": LOCAL_RELIEF_NAME,
    "cut-fill-residual-30m": CUT_FILL_RESIDUAL_NAME,
    "cut-fill-residual-100m": CUT_FILL_RESIDUAL_NAME,
    "profile-curvature": PROFILE_CURVATURE_NAME,
    "topographic-position-20m": TOPOGRAPHIC_POSITION_NAME,
    "topographic-position-100m": TOPOGRAPHIC_POSITION_NAME,
    "vegetation-height": VEGETATION_HEIGHT_NAME,
}

# The one layer whose file name says more than its key: the curvature file
# carries the cell size it was computed on, from config.py, so that a run on
# another size cannot overwrite this one's file.
TERRAIN_FILE_STEMS = {
    "profile-curvature": f"profile-curvature-{config.CURVATURE_RESOLUTION_M:g}m",
}


def terrain_path(layer, *, pilot):
    """Return the file one terrain derivative is written to.

    Args:
        layer: A key of ``TERRAIN_LAYERS``.
        pilot: Whether the run is over the pilot box.

    Returns:
        The GeoTIFF path under ``temp/hazard/landslide/terrain/``.

    Raises:
        KeyError: If ``layer`` is not one this script writes.
    """
    if layer not in TERRAIN_LAYERS:
        msg = f"{layer!r} is not a terrain layer; choose one of {list(TERRAIN_LAYERS)}."
        raise KeyError(msg)
    suffix = "-pilot" if pilot else ""
    stem = TERRAIN_FILE_STEMS.get(layer, layer)
    return TERRAIN_DIR / f"{stem}{suffix}.tif"


def describe_layer(key, layer):
    """Print one layer's grid, its NaN count and its deciles."""
    values = layer.to_numpy()
    present = values[np.isfinite(values)]
    rows, columns = layer.shape
    print(RULE)
    print(f"{key} ({layer.name})")
    print(f"  Grid    : {rows:,} rows x {columns:,} columns")
    print(f"  NaN     : {values.size - present.size:,} of {values.size:,} cells")
    if present.size == 0:
        print("  No cell carries a value.")
        return
    quantiles = np.quantile(present, DECILES)
    print(
        "  Deciles : "
        + ", ".join(
            f"p{100 * q:g} {v:.3g}" for q, v in zip(DECILES, quantiles, strict=True)
        )
    )


def write_layer(key, layer, *, pilot):
    """Check a layer carries the band name promised for its key, then write it."""
    assert layer.name == TERRAIN_LAYERS[key], (key, layer.name)
    describe_layer(key, layer)
    return write_raster(layer.astype("float32"), terrain_path(key, pilot=pilot))


def main(
    *,
    pilot,
    use_cached_dsm,
    face_height_windows_m,
    residual_base_resolutions_m,
    topographic_position_windows_m,
    curvature_resolution_m,
):
    """Derive every terrain layer from step 3's DEMs and the LINZ surface model.

    Args:
        pilot: Whether the DEMs were built over the pilot box.
        use_cached_dsm: Whether to reuse an already-fetched surface model.
        face_height_windows_m: The windows the face height is measured over,
            in metres, on the 1 m DEM.
        residual_base_resolutions_m: The cell sizes of the smoothed surfaces
            the 1 m DEM is differenced against.
        topographic_position_windows_m: Window in metres mapped to the DEM
            cell size it is computed on.
        curvature_resolution_m: The cell size the profile curvature is
            computed on.
    """
    print(RULE)
    print(f"Extent    : {'pilot' if pilot else 'full study area'}")
    print(f"Reading   : {dem_path(1, pilot=pilot)}")
    dem_1m = read_layer(dem_path(1, pilot=pilot))

    written = []
    for window_m in face_height_windows_m:
        layer = local_relief(dem_1m, 1, window_m)
        written.append(write_layer(f"face-height-{window_m:g}m", layer, pilot=pilot))

    for resolution_m in residual_base_resolutions_m:
        base = read_layer(dem_path(resolution_m, pilot=pilot))
        layer = cut_fill_residual(dem_1m, base)
        written.append(
            write_layer(f"cut-fill-residual-{resolution_m:g}m", layer, pilot=pilot)
        )

    dem = read_layer(dem_path(curvature_resolution_m, pilot=pilot))
    layer = profile_curvature(dem, curvature_resolution_m)
    written.append(write_layer("profile-curvature", layer, pilot=pilot))

    for window_m, resolution_m in topographic_position_windows_m.items():
        dem = read_layer(dem_path(resolution_m, pilot=pilot))
        layer = topographic_position(dem, resolution_m, window_m)
        written.append(
            write_layer(f"topographic-position-{window_m:g}m", layer, pilot=pilot)
        )

    bbox = tuple(float(value) for value in dem_1m.rio.bounds())
    print(RULE)
    print("Fetching the LINZ surface model at 1 m ...", flush=True)
    dsm = read_layer(get_dsm(bbox, resolution=1, use_cache=use_cached_dsm))
    print("Reading the LINZ building outlines, masked out of the vegetation ...")
    buildings = get_nz_building_outlines(bbox, constants.DEFAULT_CRS).geometry
    layer = vegetation_height(dsm, dem_1m, buildings)
    written.append(write_layer("vegetation-height", layer, pilot=pilot))

    print(RULE)
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        use_cached_dsm=config.USE_CACHED_DSM,
        face_height_windows_m=config.FACE_HEIGHT_WINDOWS_M,
        residual_base_resolutions_m=config.RESIDUAL_BASE_RESOLUTIONS_M,
        topographic_position_windows_m=config.TOPOGRAPHIC_POSITION_WINDOWS_M,
        curvature_resolution_m=config.CURVATURE_RESOLUTION_M,
    )
