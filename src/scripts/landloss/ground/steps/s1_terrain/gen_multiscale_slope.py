"""Ground step 1: build a DEM, a slope and an aspect raster at each of several cell sizes.

    uv run --frozen python src/scripts/landloss/ground/steps/s1_terrain/gen_multiscale_slope.py

Needs ``LINZ_API_KEY`` in ``.env`` for the elevation fetch. The run settings --
the extent, the cell sizes, and whether to reuse the
cached DEM -- come from config.py beside this script rather than from the
command line.

Slope is a property of the length it is measured over, and the models this
study leans on were calibrated at different ones: Kingsbury's slope classes
against a 20 m contour model, the global earthquake-induced landslide models
against 30 m and coarser grids, and the urban faces are found on the 1 m DEM.
So the slope is built at each cell size in config.py
rather than at one and reused.

Only the finest DEM, 1 m, is fetched from LINZ. Every coarser one is the block
mean of it, from :func:`landloss.common.utils.terrain.block_mean`, because
LINZ's loader resamples bilinearly and, asked for 100 m straight from the 1 m
LiDAR, reads a handful of points per cell rather than the ground the cell
covers. Averaging also makes every grid nest inside the finest, so a 100 m cell
is exactly the ten thousand 1 m cells under it.

Slope at each size is Horn's method, from
:func:`landloss.common.utils.terrain.slope_degrees`, the same as every other
slope in this study, and the aspect is the downhill bearing of the same
gradient, from :func:`landloss.common.utils.terrain.downhill_azimuth_degrees`.
The extent is snapped outward to a whole number of the least common multiple of
the cell sizes -- 300 m for 1, 3, 10, 30, 50 and 100 -- so that every grid
tiles it exactly, and fetched with that much margin on every side, so the one
cell border Horn's kernel loses falls in the margin and is trimmed off, rather
than showing up as NaN along the edges.

The fetched DEM is cut back to the padded extent before anything is averaged.
LINZ's loader comes back larger than asked, because the extent goes to it in
WGS84 and the rectangle grows on the round trip, so without the cut the blocks
would be counted from wherever the loader's corner happened to land rather than
from a round coordinate.

Writes, per cell size, ``dem-<n>m.tif``, ``slope-<n>m.tif`` and
``aspect-<n>m.tif`` under temp/ground/, with the extent's
``extent_suffix`` (``-pilot`` for the small Wellington pilot) on a run that is
not over the full study area.
"""

import itertools
import math
import sys
import time

import numpy as np
import rioxarray

from landloss.common.utils.terrain import (
    block_mean,
    cell_size,
    downhill_azimuth_degrees,
    slope_degrees,
    write_raster,
)
from landloss.domain import constants
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.readers import get_dem
from scripts.landloss.ground.steps.s1_terrain import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. These are working layers, rebuildable from the elevation
# model, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "ground"

# The slope classes the run reports the share of the extent in. Kingsbury's
# slope angle boundaries, so that the effect of the cell size on the classes the
# susceptibility step scores is visible straight off the run.
SLOPE_CLASS_EDGES = (0, 15, 20, 25, 30, 35, 45, 90)

# The eight compass octants the run reports the aspect share in, each 45 degrees
# wide and centred on its cardinal or intercardinal bearing.
OCTANT_NAMES = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

DECILES = (0.1, 0.5, 0.9, 0.99)

RULE = "-" * 72


def output_path(kind, resolution_m, *, extent):
    """Return the file one layer at one cell size is written to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{kind}-{resolution_m:g}m{suffix}.tif"


def dem_path(resolution_m, *, extent):
    """Return the file the DEM at one cell size is written to."""
    return output_path("dem", resolution_m, extent=extent)


def slope_path(resolution_m, *, extent):
    """Return the file the slope at one cell size is written to."""
    return output_path("slope", resolution_m, extent=extent)


def aspect_path(resolution_m, *, extent):
    """Return the file the aspect (downhill azimuth) at one cell size is written to."""
    return output_path("aspect", resolution_m, extent=extent)


def read_layer(path):
    """Read one raster this step wrote, or fetched, with nodata as NaN.

    A masked read leaves the file's fill value in the encoding as well as
    declaring NaN on the attributes, and writing a grid that carries both
    fails. NaN on the attributes is the one that describes the array now.
    """
    with rioxarray.open_rasterio(path, masked=True) as opened:
        layer = opened.squeeze("band", drop=True).load()
    layer.encoding.pop("_FillValue", None)
    return layer.rio.write_nodata(np.nan)


def check_resolutions(resolutions_m):
    """Return the finest cell size, and each cell size's block factor from it.

    Raises:
        ValueError: If a cell size is not a whole multiple of the finest, which
            would leave a coarse cell straddling a fine one.
    """
    finest = min(resolutions_m)
    factors = {}
    for resolution in sorted(resolutions_m):
        factor = resolution / finest
        if not math.isclose(factor, round(factor)):
            msg = (
                f"{resolution} m is not a whole multiple of the finest cell "
                f"size, {finest} m, so it cannot be block-averaged from it."
            )
            raise ValueError(msg)
        factors[resolution] = round(factor)
    return finest, factors


def resolve_extent(*, extent):
    """Return the bounding box and name of the extent to run over."""
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        return aoi.bbox(constants.DEFAULT_CRS), aoi.name

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox = tuple(float(value) for value in study_areas.total_bounds)
    return bbox, ", ".join(study_areas["name"])


def snap_outward(bbox, step_m):
    """Widen a bounding box so every edge falls on a whole multiple of a step."""
    minx, miny, maxx, maxy = bbox
    return (
        math.floor(minx / step_m) * step_m,
        math.floor(miny / step_m) * step_m,
        math.ceil(maxx / step_m) * step_m,
        math.ceil(maxy / step_m) * step_m,
    )


def fetch_dem(bbox, resolution_m, *, use_cache):
    """Fetch the finest DEM over an extent, with nodata as NaN."""
    print(
        f"\nFetching the LINZ elevation model at {resolution_m:g} m ...\n"
        "  The pilot takes a few minutes; the full study area does not fit\n"
        "  in memory at 1 m. It caches, so a repeat is instant.",
        flush=True,
    )
    started = time.perf_counter()
    dem_path = get_dem(bbox, resolution=resolution_m, use_cache=use_cache)
    print(f"  {dem_path}")
    print(f"  Took    : {time.perf_counter() - started:,.1f} s")
    return read_layer(dem_path)


def trim_to_extent(grid, bbox):
    """Cut a grid to the cells whose centres fall inside a bounding box.

    Selected on the cell centres rather than with ``rio.clip_box``, which keeps a
    cell that only touches the box and so hands back a row or a column more than
    the box holds.
    """
    minx, miny, maxx, maxy = bbox
    # y runs north to south in a north-up raster, so its slice runs top first.
    return grid.sel(x=slice(minx, maxx), y=slice(maxy, miny))


def describe_extent(name, bbox):
    """Print the extent being built, so a mistaken study area is obvious at once."""
    minx, miny, maxx, maxy = bbox
    print(RULE)
    print(f"Extent    : {name}")
    print(f"  NZTM    : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size    : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")


def describe_slope(slope, dem, resolution_m):
    """Print the grid, the slope deciles and the share in each slope class."""
    values = slope.to_numpy()
    present = values[np.isfinite(values)]
    rows, columns = slope.shape
    left, _bottom, _right, top = slope.rio.bounds()

    print(RULE)
    print(f"{resolution_m:g} m")
    print(f"  Grid    : {rows:,} rows x {columns:,} columns")
    print(f"  Origin  : {left:,.0f} E, {top:,.0f} N (top left)")
    print(
        f"  Elev.   : {float(dem.min()):,.1f} to {float(dem.max()):,.1f} m, "
        f"{int(dem.isnull().sum()):,} cells NaN"
    )
    print(f"  Slope NaN cells: {values.size - present.size:,}")

    if present.size == 0:
        print("  No cell carries a slope.")
        return

    quantiles = np.quantile(present, DECILES)
    print(
        "  Slope   : "
        + ", ".join(
            f"p{100 * q:g} {v:.1f}" for q, v in zip(DECILES, quantiles, strict=True)
        )
        + " degrees"
    )

    counts, _ = np.histogram(present, bins=SLOPE_CLASS_EDGES)
    shares = counts / present.size
    edges = itertools.pairwise(SLOPE_CLASS_EDGES)
    print(
        "  Classes : "
        + ", ".join(
            f"{low}-{high} {share:.1%}"
            for (low, high), share in zip(edges, shares, strict=True)
        )
    )


def describe_aspect(aspect):
    """Print the aspect NaN count and the share of the extent facing each octant."""
    values = aspect.to_numpy()
    present = values[np.isfinite(values)]
    print(f"  Aspect NaN cells: {values.size - present.size:,} (level ground included)")

    if present.size == 0:
        print("  No cell carries an aspect.")
        return

    # Octant 0 is centred on north, so the first bin straddles 0/360: rotate the
    # bearings by half an octant before binning so each octant is one bin.
    octant_width = 360 / len(OCTANT_NAMES)
    octants = np.floor(((present + octant_width / 2) % 360) / octant_width).astype(int)
    counts = np.bincount(octants, minlength=len(OCTANT_NAMES))
    print(
        "  Octants : "
        + ", ".join(
            f"{name} {count / present.size:.1%}"
            for name, count in zip(OCTANT_NAMES, counts, strict=True)
        )
    )


def main(*, extent, resolutions_m, use_cached_dem):
    """Build a DEM, a slope and an aspect at each cell size over the extent.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        resolutions_m: The cell sizes to build at, in metres. Each has to be a
            whole multiple of the finest.
        use_cached_dem: Whether to reuse an already-fetched elevation model.
    """
    finest, factors = check_resolutions(resolutions_m)
    # The step every grid tiles exactly. The coarsest cell alone is not enough:
    # 100 m snapping leaves a 2,900 m side that 30 m cells cannot fill.
    step = math.lcm(*(int(resolution) for resolution in resolutions_m))

    bbox, extent_name = resolve_extent(extent=extent)
    snapped = snap_outward(bbox, step)
    describe_extent(extent_name, snapped)

    minx, miny, maxx, maxy = snapped
    padded = (minx - step, miny - step, maxx + step, maxy + step)
    fine_dem = trim_to_extent(
        fetch_dem(padded, finest, use_cache=use_cached_dem), padded
    )

    written = []
    for resolution_m, factor in factors.items():
        print(f"\nBuilding {resolution_m:g} m ...", flush=True)
        dem = fine_dem if factor == 1 else block_mean(fine_dem, factor)
        slope = slope_degrees(dem, cell_size(dem))
        aspect = downhill_azimuth_degrees(dem, cell_size(dem))

        dem = trim_to_extent(dem, snapped)
        slope = trim_to_extent(slope, snapped)
        aspect = trim_to_extent(aspect, snapped)
        describe_slope(slope, dem, resolution_m)
        describe_aspect(aspect)

        written.append(write_raster(dem, dem_path(resolution_m, extent=extent)))
        written.append(write_raster(slope, slope_path(resolution_m, extent=extent)))
        written.append(write_raster(aspect, aspect_path(resolution_m, extent=extent)))

    print(RULE)
    for path in written:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        resolutions_m=config.RESOLUTIONS_M,
        use_cached_dem=config.USE_CACHED_DEM,
    )
