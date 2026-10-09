"""Measure the sea view, the distance to the sea and the winter sun of every address.

Fetches the LINZ elevation model over the address spine's extent buffered by the
casting distance, decides which of its cells are sea, casts rays from every
address and writes the share of directions in which the sea is visible and the
distance to the nearest sea cell along any of them:

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/s3_build_amenity.py

The run settings -- the extent (a pilot box or the full study area), whether to
ignore the caches, and the input and output paths -- come from config.py beside
this script rather than from the command line. How the view is measured -- the
eye height, the casting distance, how many directions and what counts as sea --
are rows of the land value factors asset, because they decide what a share means
and so belong beside the premium that is paid on it.

This is s3 of the land value step: amenity is the third of the attributes the
step attaches before s4 values the addresses, after terrain (s1) and
accessibility (s2). As with those, s4 runs without it and says so.

The DEM is the slow part, as in s1, and it is fetched over a larger extent than
s1's: every address needs the full casting distance around it, so the extent is
buffered by the casting distance rather than by half a topographic window. The
ray casting itself is a few minutes over the full study area.

Sea is a DEM cell outside the study area's land -- the territorial authority
polygons, which are land only -- and no higher than the configured elevation,
or one the DEM has no value for. The run prints the share of the DEM it took as
sea, which over a Wellington extent should be a large share of the harbour and
the strait and none of the hills.

Requires LINZ_API_KEY in .env if the address spine has to be rebuilt.
"""

import sys
import time
from pathlib import Path

import geopandas as gpd
from ttpy.gis.raster.io import load_raster

from landloss.domain import constants
from landloss.exposure.land.amenity import (
    COAST_DISTANCE_COLUMN,
    SEA_VIEW_COLUMN,
    WINTER_SUN_COLUMN,
    WinterSun,
    measure_sea,
    sea_mask,
)
from landloss.exposure.land.land_value import load_factors
from landloss.io.area_of_interest import extent_suffix, get_study_areas
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.exposure.land.steps.s2_land_value.s1_build_terrain_attributes import (
    describe_extent,
    fetch_dem,
    get_spine,
    mask_nodata,
    resolve_extent,
)
from scripts.landloss.paths import TEMP_DIR

# Suburb names are macronised, which the default cp1252 Windows console cannot
# encode. See the note in s4_estimate_land_value.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# temp/ is gitignored. These are working layers, rebuildable from the source and
# the packaged assets, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "exposure"
# Each name carries extent_suffix(extent), so runs over different extents sit
# side by side.
SPINE_STEM = "address-spine"
OUT_STEM = "amenity-by-address"

# The rows of the land value factors asset that say how the view is measured.
EYE_HEIGHT_PARAMETER = "sea_view_eye_height_m"
MAX_DISTANCE_PARAMETER = "sea_view_max_distance_m"
DIRECTIONS_PARAMETER = "sea_view_directions"
MAX_SEA_ELEVATION_PARAMETER = "sea_view_max_sea_elevation_m"
SUN_EYE_HEIGHT_PARAMETER = "winter_sun_eye_height_m"
SUN_FIRST_DAY_PARAMETER = "winter_sun_first_day_of_year"
SUN_LAST_DAY_PARAMETER = "winter_sun_last_day_of_year"
SUN_DAYS_PARAMETER = "winter_sun_days_sampled"
SUN_MINUTES_PARAMETER = "winter_sun_minutes_step"

# The join key every other step in the exposure model hangs off.
ID_COLUMN = "address_id"
OUT_COLUMNS = (ID_COLUMN, SEA_VIEW_COLUMN, COAST_DISTANCE_COLUMN, WINTER_SUN_COLUMN)

# The distances the coast distance is summarised at.
COAST_BANDS_M = (100, 250, 500, 1000)

DECILES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
SUBURB_LIMIT = 15
RULE = "-" * 72


def resolve_paths(*, extent, spine, out):
    """Return where the spine is read from and where the attributes are written.

    Resolved here rather than as config defaults, so that a pilot run cannot
    overwrite the full outputs.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        spine: The address spine path from config.py, or None for the default.
        out: The amenity attributes path from config.py, or None for the
            default.

    Returns:
        The spine path and the output path.
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
    return spine_path, out_path


def dem_bbox(spine, max_distance_m, resolution):
    """Return the spine's extent buffered by the casting distance and one cell."""
    buffer_m = max_distance_m + resolution
    minx, miny, maxx, maxy = (float(value) for value in spine.total_bounds)
    return (minx - buffer_m, miny - buffer_m, maxx + buffer_m, maxy + buffer_m)


def describe_sea(sea):
    """Print the share of the DEM taken as sea."""
    print(RULE)
    print(f"Sea cells: {sea.mean():.1%} of the DEM")


def describe_shares(measured):
    """Print the share of addresses with any view, and the deciles, per TA."""
    print(RULE)
    print("Sea view share, per territorial authority")
    header = "".join(f"{f'p{100 * q:.0f}':>6}" for q in DECILES)
    print(f"  {'Territorial authority':<22}{'Any':>7}{header}")

    for ta_name, rows in measured.groupby("territorial_authority", sort=True):
        share = rows[SEA_VIEW_COLUMN].dropna()
        cells = "".join(f"{value:>6.2f}" for value in share.quantile(DECILES))
        print(f"  {ta_name:<22}{(share > 0).mean():>6.0%} {cells}")

    missing = int(measured[SEA_VIEW_COLUMN].isna().sum())
    if missing:
        print(f"\n  {missing:,} address(es) fell off the DEM and have no share.")


def winter_sun_settings(factors):
    """Build the winter sun sampling from the factors asset."""
    first = int(factors[SUN_FIRST_DAY_PARAMETER])
    last = int(factors[SUN_LAST_DAY_PARAMETER])
    days = int(factors[SUN_DAYS_PARAMETER])
    return WinterSun(
        eye_height_m=factors[SUN_EYE_HEIGHT_PARAMETER],
        days_of_year=tuple(round(day) for day in _spread(first, last, days)),
        minutes_step=factors[SUN_MINUTES_PARAMETER],
    )


def _spread(first, last, count):
    """Return ``count`` evenly spaced values from ``first`` to ``last``."""
    if count <= 1:
        return [first]
    return [first + (last - first) * index / (count - 1) for index in range(count)]


def describe_sun(measured):
    """Print the deciles of winter sun per territorial authority."""
    print(RULE)
    print("Winter sun share, per territorial authority")
    header = "".join(f"{f'p{100 * q:.0f}':>6}" for q in DECILES)
    print(f"  {'Territorial authority':<22}{header}")
    for ta_name, rows in measured.groupby("territorial_authority", sort=True):
        share = rows[WINTER_SUN_COLUMN].dropna()
        print(
            f"  {ta_name:<22}" + "".join(f"{v:>6.2f}" for v in share.quantile(DECILES))
        )


def describe_coast(measured):
    """Print the share of addresses within each distance of the coast."""
    distance = measured[COAST_DISTANCE_COLUMN]

    print(RULE)
    print("Distance to the coast")
    for band in COAST_BANDS_M:
        print(f"  Within {band:>5,} m : {(distance <= band).mean():5.1%} of addresses")


def describe_suburbs(measured, limit=SUBURB_LIMIT):
    """Print the suburbs with the widest median view, as a check by eye."""
    medians = (
        measured.groupby(["territorial_authority", "suburb_locality"])[SEA_VIEW_COLUMN]
        .median()
        .sort_values(ascending=False)
        .head(limit)
    )
    print(RULE)
    print(f"Top {limit} suburbs by median sea view share")
    for (ta_name, suburb), share in medians.items():
        print(f"  {suburb!s:<28}{ta_name:<20}{share:>6.2f}")


def write_outputs(measured, out):
    """Write the amenity attributes and print what was written."""
    out.parent.mkdir(parents=True, exist_ok=True)
    measured.to_parquet(out)

    print(RULE)
    print(f"Wrote {out}")
    print(f"  Rows    : {len(measured):,}")
    print(f"  Columns : {', '.join(measured.columns)}")


def main(*, extent, fresh, spine, out):
    """Measure the sea view share of every address and write it out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        fresh: Ignore the caches and re-fetch the DEM and the address spine.
        spine: The address spine from step 1. None reads the standard location
            under temp/exposure/, named with ``extent_suffix(extent)``.
        out: Where to write the attributes. None writes to the standard location
            under temp/exposure/, named with ``extent_suffix(extent)``.

    Raises:
        ValueError: If the address spine is empty.
    """
    spine_path, out = resolve_paths(extent=extent, spine=spine, out=out)
    factors = load_factors()
    max_distance_m = factors[MAX_DISTANCE_PARAMETER]
    resolution = constants.DEM_RESOLUTION_M

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox, clip_to, extent_name = resolve_extent(study_areas, extent=extent)
    describe_extent(extent_name, bbox)

    addresses = get_spine(spine_path, bbox, clip_to, use_cache=not fresh)
    if addresses.empty:
        msg = (
            f"The address spine at {spine_path} is empty; there is nothing to measure."
        )
        raise ValueError(msg)
    print(f"Addresses in the spine: {len(addresses):,}")

    fetch_bbox = dem_bbox(addresses, max_distance_m, resolution)
    print(
        f"The DEM extent is the spine's own buffered by {max_distance_m:,.0f} m, the "
        "casting distance."
    )
    dem_path = fetch_dem(fetch_bbox, resolution, use_cache=not fresh)
    dem = load_raster(dem_path, validate_crs=constants.DEFAULT_CRS).squeeze()
    dem, nodata_note = mask_nodata(dem)
    print(f"  Nodata  : {nodata_note}")

    sea = sea_mask(dem, study_areas, factors[MAX_SEA_ELEVATION_PARAMETER])
    describe_sea(sea)

    print("\nCasting rays ...", flush=True)
    started = time.perf_counter()
    measured = addresses.copy().reset_index(drop=True)
    sea_attributes = measure_sea(
        dem,
        sea,
        measured.geometry,
        eye_height_m=factors[EYE_HEIGHT_PARAMETER],
        max_distance_m=max_distance_m,
        n_directions=int(factors[DIRECTIONS_PARAMETER]),
        step_m=resolution,
        winter_sun=winter_sun_settings(factors),
    )
    measured[WINTER_SUN_COLUMN] = sea_attributes[WINTER_SUN_COLUMN]
    measured[SEA_VIEW_COLUMN] = sea_attributes[SEA_VIEW_COLUMN]
    measured[COAST_DISTANCE_COLUMN] = sea_attributes[COAST_DISTANCE_COLUMN]
    print(f"  Took    : {time.perf_counter() - started:,.1f} s")

    describe_shares(measured)
    describe_coast(measured)
    describe_sun(measured)
    describe_suburbs(measured)

    write_outputs(
        gpd.GeoDataFrame(
            measured[[*OUT_COLUMNS, measured.geometry.name]],
            geometry=measured.geometry.name,
            crs=measured.crs,
        ),
        out,
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT, fresh=config.FRESH, spine=config.SPINE, out=config.AMENITY
    )
