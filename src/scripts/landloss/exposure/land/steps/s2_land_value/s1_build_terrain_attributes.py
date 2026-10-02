"""Sample slope and topographic position onto every address in the spine.

Fetches the LINZ elevation model over the address spine's extent, derives the
two terrain attributes the land value model reads -- slope in degrees, and
metres above the mean elevation of the neighbourhood around the address -- and
writes one row per address.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/s1_build_terrain_attributes.py

The run settings -- the extent (a pilot box or the full study area), whether to
ignore the caches, the input and output paths and the window override -- come
from config.py beside this script rather than from the command line.

This is s1 of the land value step: terrain is the first of the four attributes
the step attaches, and s4 is the valuation that reads them. The two are
deliberately runnable on their own. The valuation falls back to Phase 1
behaviour when this file is absent, so a first pass over a new extent can skip
the DEM entirely and still produce a land value.

The DEM is the slow part. The pilot box took about 82 s to assemble from the
source tiles, and the full study area is 59 x 54 km against the pilot's 2.9 x
1.7 km -- so a full run is a long background job measured in tens of minutes,
while a pilot run finishes in a couple of them. Both cache, keyed on the extent, so
a second run over the same extent skips the fetch entirely.

The DEM is fetched over the spine's extent *buffered* by half the topographic
position window. A rolling window has no answer within half a window of the edge
of its grid, so without the buffer the addresses around the outside of the
extent -- a quarter of a kilometre of them at the 500 m window this study uses
-- would sample NaN purely because of where the extent was drawn.

Any address that still samples NaN fell outside the DEM or on a nodata cell, and
the run says so per territorial authority rather than passing it quietly
downstream. The land value model reads a NaN terrain value as "nothing is known
to distinguish this address from its cohort", which is the right default but is
not a result anybody should discover by accident.

One thing about the LINZ elevation model is worth knowing before these numbers
are read. Over the pilot box it comes back with no holes at all: it declares NaN
as its nodata marker but writes none, and the harbour arrives as real elevations
either side of zero rather than as nodata. So a waterfront address is measured
against a sea surface at about 0 m, which is the right comparison to make and is
why nothing here sampled NaN. It also means a nodata hole, if one turns up in a
part of the full study area with no LiDAR flown, will be a genuinely different
case rather than the normal one -- which is what the NaN reporting is for.

Requires LINZ_API_KEY in .env if the address spine has to be rebuilt.
"""

import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from ttpy.gis.raster.io import load_raster

from landloss.common.utils.terrain import (
    sample_at_points,
    slope_degrees,
    topographic_position,
    window_in_cells,
    write_raster,
)
from landloss.domain import constants
from landloss.exposure.addresses import get_addresses
from landloss.exposure.land.land_value import (
    SLOPE_COLUMN,
    TOPOGRAPHIC_POSITION_COLUMN,
    load_factors,
)
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.readers import get_dem
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.paths import REPO_ROOT, TEMP_DIR

# Wellington suburb names are macronised -- Owhiro Bay, Pauatahanui -- which the
# default cp1252 Windows console cannot encode, so printing one raises. Ask for
# UTF-8 rather than stripping the macrons, because the names are worth getting
# right.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# temp/ is gitignored. These are working layers, rebuildable from the source and
# the packaged assets, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "exposure"
# Each name carries extent_suffix(extent), so runs over different extents sit
# side by side.
SPINE_STEM = "address-spine"
OUT_STEM = "terrain-by-address"

# The derivative rasters are kept as well as the sampled points. They are what a
# surprising address gets checked against, and recomputing them means fetching
# the DEM again.
SLOPE_RASTER_STEM = "terrain-slope"
POSITION_RASTER_STEM = "terrain-position"

# The parameter carrying the neighbourhood the topographic position is measured
# over. It lives in the land value factors asset rather than here, because the
# elevated flat threshold that is compared against the result is only meaningful
# against this window and the two have to move together.
WINDOW_PARAMETER = "topographic_position_window_m"

# The join key every other step in the exposure model hangs off.
ID_COLUMN = "address_id"
OUT_COLUMNS = (ID_COLUMN, SLOPE_COLUMN, TOPOGRAPHIC_POSITION_COLUMN)

# The quantiles the two distributions are described at. Deciles rather than a
# mean and a standard deviation, because neither derivative is symmetric --
# slope has a floor at zero and a long tail up the hillside -- and the shape is
# the thing worth looking at.
DECILES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

RULE = "-" * 72


def get_spine(path, bbox, clip_to, *, use_cache):
    """Read the address spine from disk, or build it from LINZ if it is absent.

    Args:
        path: The geoparquet step 1 writes.
        bbox: The extent to read, if the spine has to be rebuilt.
        clip_to: The boundary to cut a rebuilt spine back to.
        use_cache: Whether to use the extent cache when rebuilding.

    Returns:
        The address spine.
    """
    if path.exists():
        print(f"Reading the address spine from {path} ...")
        return gpd.read_parquet(path)

    # Rebuilt rather than refused, so that this script runs on a clean checkout.
    # It is written back out to the step 1 path, so the next run of any script
    # in the exposure model finds it there.
    print(f"No address spine at {path}; rebuilding it from LINZ ...")
    spine = get_addresses(
        bbox=bbox, crs=constants.DEFAULT_CRS, clip_to=clip_to, use_cache=use_cache
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    spine.to_parquet(path)
    print(f"Wrote the rebuilt spine to {path}")
    return spine


def read_spine(path, bbox, clip_to, *, use_cache):
    """Read or rebuild the spine, or print why it could not be had and return None."""
    try:
        return get_spine(path, bbox, clip_to, use_cache=use_cache)
    except ValueError as exc:
        # Raised by resolve_api_key when LINZ_API_KEY is missing.
        print(f"\nCould not build the address spine: {exc}")
        return None
    except requests.exceptions.RequestException as exc:
        print(f"\nThe request to LINZ failed: {exc}")
        return None


def dem_bbox(spine, window_m, resolution):
    """Return the extent to fetch the DEM over, buffered for the rolling window.

    The buffer is half the topographic position window plus one cell. Half the
    window is what the rolling mean needs on every side to have an answer at the
    outermost address; the extra cell covers the one-cell border the slope
    kernel loses as well, so neither derivative comes back NaN purely because of
    where the extent was drawn.

    Args:
        spine: The addresses the DEM has to cover.
        window_m: The topographic position neighbourhood width, in metres.
        resolution: The DEM cell size, in metres.

    Returns:
        The buffered bounding box (minx, miny, maxx, maxy), and the buffer width
        in metres so that the run can print what it added.
    """
    buffer_m = window_m / 2 + resolution
    minx, miny, maxx, maxy = (float(value) for value in spine.total_bounds)
    fetch_bbox = (minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)
    return fetch_bbox, buffer_m


def mask_nodata(dem):
    """Turn the DEM's nodata marker into NaN.

    The terrain derivatives treat every finite cell as real ground, so a DEM
    still carrying -9999 over the harbour would grow a cliff around the whole
    coastline and hand every waterfront address a slope in the eighties. The
    marker is read off the raster rather than assumed, because the value LINZ
    happens to write is not part of this study's contract with it.

    Args:
        dem: The DEM as loaded, with dimensions (y, x).

    Returns:
        The DEM with nodata cells set to NaN, and a description of what was done
        for the run to print. The three cases read differently and it is worth
        being able to tell them apart: a raster that declared no marker at all is
        one where a sentinel elevation could still be sitting in the sea
        unannounced.
    """
    nodata = dem.rio.nodata

    if nodata is None:
        return dem, "none declared"

    # A marker that is already NaN needs nothing done to it, and a comparison
    # against NaN would mask nothing anyway. Compared to itself rather than with
    # math.isnan, because rio.nodata comes back as a numpy scalar.
    if nodata != nodata:  # noqa: PLR0124
        return dem, "NaN, so already excluded"

    return dem.where(dem != nodata), f"{nodata} -> NaN"


def fetch_dem(bbox, resolution, *, use_cache):
    """Fetch the DEM for an extent and print what it cost.

    Args:
        bbox: The extent to fetch (minx, miny, maxx, maxy), in the study CRS.
        resolution: The cell size in metres.
        use_cache: Whether to reuse an already-fetched DEM for the same extent.

    Returns:
        The path the DEM is on disk at.
    """
    print("\nFetching the LINZ elevation model ...")
    print(
        "  The DEM is assembled from the source LiDAR tiles, which took about\n"
        "  82 s for the pilot box; the full study area is many times that, so a\n"
        "  full run belongs in the background. It caches, so a repeat is instant."
    )

    started = time.perf_counter()
    dem_path = get_dem(bbox, resolution=resolution, use_cache=use_cache)
    elapsed = time.perf_counter() - started

    print(f"  Took    : {elapsed:,.1f} s")
    return dem_path


def describe_dem(dem_path, dem, resolution, window_m, nodata_note):
    """Print the grid the derivatives are about to be computed on.

    The window in cells is printed beside the window in metres because it is the
    number that actually gets used: a 500 m window is 51 cells at 10 m, and it
    is the 51 cells that decide how wide the NaN border is.
    """
    rows = int(dem.sizes["y"])
    columns = int(dem.sizes["x"])
    cells = window_in_cells(window_m, resolution)
    border_m = (cells // 2) * resolution

    print(RULE)
    print(f"DEM       : {dem_path}")
    print(f"  Grid    : {rows:,} rows x {columns:,} columns at {resolution} m")
    print(
        f"  Covers  : {columns * resolution / 1000:.1f} x "
        f"{rows * resolution / 1000:.1f} km"
    )
    print(f"  CRS     : {dem.rio.crs}")
    print(f"  Nodata  : {nodata_note}")
    print(
        f"  Window  : {window_m:,.0f} m = {cells} cells, so the outer "
        f"{border_m:,.0f} m of the\n            grid has no topographic position"
    )


def describe_distribution(values, label, unit):
    """Print the deciles of one sampled derivative.

    Deciles rather than a mean and a standard deviation, because what is being
    checked is whether the derivative separates addresses at all. A slope column
    whose 10th and 90th percentiles are the same number cannot break any tie,
    however sensible its mean looks.

    Args:
        values: The sampled derivative.
        label: What it is, for the heading.
        unit: The unit it is in, for the heading.
    """
    present = values.dropna()

    print(RULE)
    print(f"{label} ({unit})")
    print(f"  over the {len(present):,} addresses that sampled a value")

    if present.empty:
        print("  No address sampled a value, so there is no distribution to show.")
        return

    for fraction, value in present.quantile(DECILES).items():
        print(f"  p{100 * fraction:>5.0f}{value:>12.2f}")


def describe_missing(sampled):
    """Print the addresses that sampled NaN, per territorial authority.

    NaN here is not a small data quality note. It means the address fell outside
    the DEM or on a nodata cell, and the land value model reads a NaN terrain
    value as "nothing distinguishes this address from its cohort" -- which is the
    honest default but is also silent. If the count is anything more than a
    handful, the DEM extent or the nodata handling is wrong rather than the
    addresses being unusual.

    Args:
        sampled: The addresses with both derivatives attached, carrying
            ``territorial_authority``.

    Returns:
        The number of addresses missing at least one derivative.
    """
    missing = sampled[SLOPE_COLUMN].isna() | sampled[TOPOGRAPHIC_POSITION_COLUMN].isna()
    total = int(missing.sum())

    print(RULE)
    print(f"Addresses that sampled NaN: {total:,} of {len(sampled):,}")

    if not total:
        print("  Every address sampled both derivatives.")
        return total

    print(
        "\n  These fell outside the DEM or on a nodata cell. The land value model\n"
        "  will treat each as sitting at the middle of its cohort, so none is\n"
        "  dropped -- but none of them carries any terrain signal either."
    )
    print(f"\n  {'Territorial authority':<24}{'Missing':>10}{'Of':>10}{'Share':>10}")

    for ta_name, rows in sampled.groupby("territorial_authority", sort=True):
        in_ta = (
            rows[SLOPE_COLUMN].isna() | rows[TOPOGRAPHIC_POSITION_COLUMN].isna()
        ).sum()
        share = 100 * int(in_ta) / len(rows) if len(rows) else 0.0
        print(f"  {ta_name:<24}{int(in_ta):>10,}{len(rows):>10,}{share:>9.1f}%")

    return total


def resolve_outputs(*, extent, spine, out):
    """Choose where the spine is read from and where the outputs are written.

    Resolved here rather than as config defaults, so that a pilot run cannot
    overwrite the full outputs with a few streets of Wellington and leave
    everything downstream reading them without noticing.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        spine: The address spine path from config.py, or None for the default.
        out: The terrain attributes path from config.py, or None for the default.

    Returns:
        The spine path, the output path, and the two derivative raster paths.
    """
    suffix = extent_suffix(extent)
    spine_path = (
        Path(spine)
        if spine is not None
        else WORK_DIR / f"{SPINE_STEM}{suffix}.geoparquet"
    )
    out_path = (
        Path(out) if out is not None else WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"
    )
    slope_raster = WORK_DIR / f"{SLOPE_RASTER_STEM}{suffix}.tif"
    position_raster = WORK_DIR / f"{POSITION_RASTER_STEM}{suffix}.tif"
    return spine_path, out_path, slope_raster, position_raster


def resolve_extent(study_areas, *, extent):
    """Return the bounding box, clip boundary and name of the extent to run over.

    The clip matters as much as the box. The four authorities sit in a rectangle
    that also contains most of the Wairarapa, so the full run is cut back to the
    real boundaries; a pilot is a rectangle already and needs no clip.
    """
    aoi = get_area_of_interest(extent)
    if aoi is not None:
        return aoi.bbox(constants.DEFAULT_CRS), None, aoi.name

    bbox = tuple(float(value) for value in study_areas.total_bounds)
    return bbox, study_areas, ", ".join(study_areas["name"])


def describe_extent(name, bbox):
    """Print the extent being read, so a mistaken study area is obvious at once."""
    minx, miny, maxx, maxy = bbox

    print(RULE)
    print(f"Repo root : {REPO_ROOT}")
    print(f"Extent    : {name}")
    print(f"  NZTM    : {minx:,.0f}, {miny:,.0f} to {maxx:,.0f}, {maxy:,.0f}")
    print(f"  Size    : {(maxx - minx) / 1000:.1f} x {(maxy - miny) / 1000:.1f} km")
    print()


def build_derivatives(dem, resolution, window_m, slope_raster, position_raster):
    """Compute both derivatives, write them out, and print the progress.

    Written to disk rather than sampled straight out of memory because the
    sampling helper reads from a file, and because a surprising address has to
    be checkable against the surface it came from.

    Args:
        dem: The masked DEM, with dimensions (y, x).
        resolution: The cell size in metres.
        window_m: The topographic position neighbourhood width in metres.
        slope_raster: Where to write the slope.
        position_raster: Where to write the topographic position.

    Returns:
        The two paths written.
    """
    print("\nComputing slope ...")
    started = time.perf_counter()
    slope_path = write_raster(slope_degrees(dem, resolution), slope_raster)
    print(f"  Wrote {slope_path} in {time.perf_counter() - started:,.1f} s")

    print(f"Computing topographic position over a {window_m:,.0f} m window ...")
    started = time.perf_counter()
    position_path = write_raster(
        topographic_position(dem, resolution, window_m), position_raster
    )
    print(f"  Wrote {position_path} in {time.perf_counter() - started:,.1f} s")

    return slope_path, position_path


def write_outputs(terrain, out):
    """Write the terrain attributes and print what was written."""
    out.parent.mkdir(parents=True, exist_ok=True)
    terrain.to_parquet(out)

    print(RULE)
    # The EPSG code rather than the CRS object, because a geoparquet round trip
    # brings the projection back as its full PROJJSON and printing that buries
    # everything above it in two thousand characters of WKT.
    epsg = terrain.crs.to_epsg()

    print(f"Wrote {out}")
    print(f"  Rows    : {len(terrain):,}")
    print(f"  Columns : {', '.join(terrain.columns)}")
    print(f"  CRS     : {terrain.crs.name} (EPSG:{epsg})")


def main(*, extent, fresh, spine, out, window):
    """Sample slope and topographic position onto every address in the spine.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        fresh: Ignore the caches and re-fetch the DEM and the address spine.
        spine: The address spine from step 1. None reads the standard location
            under temp/exposure/, named with ``extent_suffix(extent)``.
            Rebuilt from LINZ if it is not there.
        out: Where to write the terrain attributes. None writes to the standard
            location under temp/exposure/, named with ``extent_suffix(extent)``.
        window: Override for the topographic position neighbourhood width, in
            metres. None takes the ``topographic_position_window_m`` row of the
            land value factors asset.

    Returns:
        1 if the spine or the DEM could not be had, otherwise None.
    """
    spine_path, out, slope_raster, position_raster = resolve_outputs(
        extent=extent, spine=spine, out=out
    )

    factors = load_factors()
    window_m = window if window is not None else factors[WINDOW_PARAMETER]
    resolution = constants.DEM_RESOLUTION_M

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox, clip_to, extent_name = resolve_extent(study_areas, extent=extent)
    describe_extent(extent_name, bbox)

    addresses = read_spine(spine_path, bbox, clip_to, use_cache=not fresh)
    if addresses is None:
        return 1
    if addresses.empty:
        print("\nThe address spine is empty; there is no terrain to sample.")
        return 1

    print(f"Addresses in the spine: {len(addresses):,}")

    fetch_bbox, buffer_m = dem_bbox(addresses, window_m, resolution)
    print(
        f"The DEM extent is the spine's own extent buffered by {buffer_m:,.0f} m, "
        f"so that\nthe {window_m:,.0f} m window has an answer at the outermost "
        "address."
    )

    try:
        dem_path = fetch_dem(fetch_bbox, resolution, use_cache=not fresh)
    except (OSError, ValueError, requests.exceptions.RequestException) as exc:
        print(f"\nCould not fetch the elevation model: {exc}")
        return 1

    # squeeze() drops the single band dimension a GeoTIFF carries; the terrain
    # derivatives want exactly (y, x) and say so loudly if they do not get it.
    dem = load_raster(dem_path, validate_crs=constants.DEFAULT_CRS).squeeze()
    dem, nodata_note = mask_nodata(dem)
    describe_dem(dem_path, dem, resolution, window_m, nodata_note)

    slope_path, position_path = build_derivatives(
        dem, resolution, window_m, slope_raster, position_raster
    )

    sampled = addresses.copy().reset_index(drop=True)
    sampled[SLOPE_COLUMN] = sample_at_points(slope_path, sampled.geometry)
    sampled[TOPOGRAPHIC_POSITION_COLUMN] = sample_at_points(
        position_path, sampled.geometry
    )

    describe_distribution(sampled[SLOPE_COLUMN], "Slope", "degrees")
    describe_distribution(
        sampled[TOPOGRAPHIC_POSITION_COLUMN],
        "Topographic position",
        f"metres above the mean of a {window_m:,.0f} m neighbourhood",
    )
    describe_missing(sampled)

    write_outputs(sampled[[*OUT_COLUMNS, sampled.geometry.name]], out)
    return None


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        fresh=config.FRESH,
        spine=config.SPINE,
        out=config.TERRAIN,
        window=config.WINDOW_M,
    )
