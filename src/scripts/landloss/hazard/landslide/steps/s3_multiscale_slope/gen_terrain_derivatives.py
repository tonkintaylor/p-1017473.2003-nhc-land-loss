"""Derive the terrain layers the landslide chain reads from step 3's DEMs.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s3_multiscale_slope/gen_terrain_derivatives.py

Run ``gen_multiscale_slope.py`` first, over the same extent: this reads the 1,
10, 30 and 100 m DEMs it wrote. The run settings come from config.py beside
this script rather than from the command line.

Each layer is one function of :mod:`landloss.common.utils.terrain` applied to
one of those DEMs:

- **Cut and fill residual**, the 1 m surface minus the 30 m and the 100 m
  surfaces: negative where the ground was cut below the smoothed hillside,
  positive where it was filled out from it. The ground map reads both.
- **Topographic position** in a 100 m window on the 10 m DEM, so the window
  is 11 cells rather than 101. The large model and landslide step 8 read it.

The face heights, profile curvature, 20 m topographic position and vegetation
height this script once wrote were read only by landslide step 6 and the
candidate wall lines, and were removed with them on 2026-10-08.

Writes one GeoTIFF per layer under temp/hazard/landslide/terrain/, with the
extent's ``extent_suffix`` (``-pilot`` for the small Wellington pilot) on a run
that is not over the full study area. The file names and band names are in
``TERRAIN_LAYERS``; every consumer asks ``terrain_path()`` for a file rather
than spelling a name.
"""

import sys

import numpy as np

from landloss.common.utils.terrain import (
    CUT_FILL_RESIDUAL_NAME,
    TOPOGRAPHIC_POSITION_NAME,
    cut_fill_residual,
    topographic_position,
    write_raster,
)
from landloss.io.area_of_interest import extent_suffix, is_full_extent
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
    "cut-fill-residual-30m": CUT_FILL_RESIDUAL_NAME,
    "cut-fill-residual-100m": CUT_FILL_RESIDUAL_NAME,
    "topographic-position-100m": TOPOGRAPHIC_POSITION_NAME,
}


def terrain_path(layer, *, extent):
    """Return the file one terrain derivative is written to.

    Args:
        layer: A key of ``TERRAIN_LAYERS``.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The GeoTIFF path under ``temp/hazard/landslide/terrain/``.

    Raises:
        KeyError: If ``layer`` is not one this script writes.
    """
    if layer not in TERRAIN_LAYERS:
        msg = f"{layer!r} is not a terrain layer; choose one of {list(TERRAIN_LAYERS)}."
        raise KeyError(msg)
    suffix = extent_suffix(extent)
    return TERRAIN_DIR / f"{layer}{suffix}.tif"


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


def write_layer(key, layer, *, extent):
    """Check a layer carries the band name promised for its key, then write it."""
    assert layer.name == TERRAIN_LAYERS[key], (key, layer.name)
    describe_layer(key, layer)
    return write_raster(layer.astype("float32"), terrain_path(key, extent=extent))


def main(*, extent, residual_base_resolutions_m, topographic_position_windows_m):
    """Derive every terrain layer from step 3's DEMs.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        residual_base_resolutions_m: The cell sizes of the smoothed surfaces
            the 1 m DEM is differenced against.
        topographic_position_windows_m: Window in metres mapped to the DEM
            cell size it is computed on.
    """
    print(RULE)
    print(f"Extent    : {'full study area' if is_full_extent(extent) else extent}")
    print(f"Reading   : {dem_path(1, extent=extent)}")
    dem_1m = read_layer(dem_path(1, extent=extent))

    written = []
    for resolution_m in residual_base_resolutions_m:
        base = read_layer(dem_path(resolution_m, extent=extent))
        layer = cut_fill_residual(dem_1m, base)
        written.append(
            write_layer(f"cut-fill-residual-{resolution_m:g}m", layer, extent=extent)
        )

    for window_m, resolution_m in topographic_position_windows_m.items():
        dem = read_layer(dem_path(resolution_m, extent=extent))
        layer = topographic_position(dem, resolution_m, window_m)
        written.append(
            write_layer(f"topographic-position-{window_m:g}m", layer, extent=extent)
        )

    print(RULE)
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        residual_base_resolutions_m=config.RESIDUAL_BASE_RESOLUTIONS_M,
        topographic_position_windows_m=config.TOPOGRAPHIC_POSITION_WINDOWS_M,
    )
