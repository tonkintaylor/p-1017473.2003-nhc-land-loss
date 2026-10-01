"""Measure how accessible every address in the spine is.

Attaches the two accessibility attributes the land value model reads -- the
straight-line gravity accessibility to the main centres, and the distance to the
nearest railway station -- and writes one row per address.

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s2_land_value/s2_build_accessibility.py

The run settings -- the pilot box or the full study area, whether to ignore the
caches, and the input and output paths -- come from config.py beside this script
rather than from the command line.

This is s2 of the land value step: accessibility is the second of the attributes
the step attaches before s4 values the addresses. As with terrain, s4 runs
without it and says so, so the two can be run in either order.

The centres, their weights and their decay lengths are the packaged asset read
by ``landloss.exposure.land.accessibility.load_centres``, and are drawn on a map
by fig_town_centres.py so that they can be checked by eye. The stations are the
LINZ Topo50 layer, fetched over the spine's extent buffered by
``STATION_BUFFER_M``, so an address near the edge of the extent is measured to
a station just outside it rather than to the nearest one inside.

The LINZ layer carries every suburban station but not Wellington Station, the
terminus, so the stations in the packaged extra stations asset (read by
``landloss.exposure.land.accessibility.load_extra_stations``) are added to it,
and the run says which were. An added station within ``DUPLICATE_STATION_M`` of
one LINZ already carries is dropped, so a copy never stands beside the real one
once LINZ adds it.

The run prints the station names it found. Topo50 describes a station as a point
used for passengers or freight, so the list is worth reading once for stations
that no longer take passengers before the premium is trusted.

Requires LINZ_API_KEY in .env for the stations, and to rebuild the address
spine if it is not on disk.
"""

import sys
from pathlib import Path

import geopandas as gpd

from landloss.domain import constants
from landloss.exposure.land.accessibility import (
    GRAVITY_COLUMN,
    STATION_DISTANCE_COLUMN,
    add_stations,
    distance_to_nearest,
    gravity_accessibility,
    load_centres,
    load_extra_stations,
)
from landloss.io.area_of_interest import get_study_areas
from landloss.io.readers import get_nz_rail_stations
from scripts.landloss.exposure.land.steps.s2_land_value import config
from scripts.landloss.exposure.land.steps.s2_land_value.s1_build_terrain_attributes import (
    describe_extent,
    get_spine,
    resolve_extent,
)
from scripts.landloss.paths import TEMP_DIR

# Suburb and station names are macronised, which the default cp1252 Windows
# console cannot encode. See the note in s4_estimate_land_value.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# temp/ is gitignored. These are working layers, rebuildable from the source and
# the packaged assets, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "exposure"
SPINE_NAME = "address-spine.geoparquet"
PILOT_SPINE_NAME = "address-spine-pilot.geoparquet"
OUT_NAME = "accessibility-by-address.geoparquet"
PILOT_OUT_NAME = "accessibility-by-address-pilot.geoparquet"

# How far beyond the spine's extent stations are fetched. Five of the plan's
# 400 m decay lengths, beyond which the station premium is under one percent of
# itself, so a station further out than this could not change anybody's value.
STATION_BUFFER_M = 2000.0

# The join key every other step in the exposure model hangs off.
ID_COLUMN = "address_id"
OUT_COLUMNS = (ID_COLUMN, GRAVITY_COLUMN, STATION_DISTANCE_COLUMN)

# Deciles rather than a mean, for the same reason the terrain step uses them:
# gravity is heavily skewed towards the CBD, and the shape is what is checked.
DECILES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

# The walking distances the station distance is summarised at.
WALK_BANDS_M = (400, 800, 1600)

RULE = "-" * 72


def resolve_paths(*, pilot, spine, out):
    """Return where the spine is read from and where the attributes are written.

    Resolved here rather than as config defaults, so that a pilot run cannot
    overwrite the full outputs. The figure script calls this too, so that it
    draws what this script wrote.

    Args:
        pilot: Whether the run is over the pilot box.
        spine: The address spine path from config.py, or None for the default.
        out: The accessibility attributes path from config.py, or None for the
            default.

    Returns:
        The spine path and the output path.
    """
    spine_path = (
        Path(spine)
        if spine is not None
        else WORK_DIR / (PILOT_SPINE_NAME if pilot else SPINE_NAME)
    )
    out_path = (
        Path(out)
        if out is not None
        else WORK_DIR / (PILOT_OUT_NAME if pilot else OUT_NAME)
    )
    return spine_path, out_path


def station_bbox(spine):
    """Return the spine's extent buffered by :data:`STATION_BUFFER_M`."""
    minx, miny, maxx, maxy = (float(value) for value in spine.total_bounds)
    return (
        minx - STATION_BUFFER_M,
        miny - STATION_BUFFER_M,
        maxx + STATION_BUFFER_M,
        maxy + STATION_BUFFER_M,
    )


def describe_stations(stations, added):
    """Print the stations found, by name, so a closed one can be spotted."""
    print(RULE)
    print(f"Railway stations within {STATION_BUFFER_M:,.0f} m of the extent: ")
    print(f"  {len(stations):,}")
    if added:
        print(f"  of which added by hand, missing from LINZ: {', '.join(added)}")

    if "name" in stations.columns:
        names = sorted(str(name) for name in stations["name"].dropna())
        for start in range(0, len(names), 4):
            print("  " + ", ".join(names[start : start + 4]))
    else:
        print(
            f"  The layer carries no name column; its columns are "
            f"{', '.join(stations.columns)}."
        )


def describe_gravity(measured):
    """Print the deciles of gravity accessibility per territorial authority.

    Per authority because that is the scale the land value model compares at:
    the normalising constant holds each authority's mean, so an Upper Hutt
    address is never priced against a Thorndon one.
    """
    print(RULE)
    print("Gravity accessibility, deciles per territorial authority")
    header = "".join(f"{f'p{100 * q:.0f}':>7}" for q in DECILES)
    print(f"  {'Territorial authority':<22}{header}")

    for ta_name, rows in measured.groupby("territorial_authority", sort=True):
        values = rows[GRAVITY_COLUMN].dropna().quantile(DECILES)
        cells = "".join(f"{value:>7.3f}" for value in values)
        print(f"  {ta_name:<22}{cells}")


def describe_station_distance(measured):
    """Print the share of addresses within each walking band of a station."""
    distance = measured[STATION_DISTANCE_COLUMN]

    print(RULE)
    print("Distance to the nearest railway station")
    if distance.isna().all():
        print("  No address has a station distance: no station was found.")
        return

    for band in WALK_BANDS_M:
        share = 100 * float((distance <= band).mean())
        print(f"  Within {band:>5,} m : {share:5.1f}% of addresses")
    print(f"  Median      : {float(distance.median()):,.0f} m")


def write_outputs(measured, out):
    """Write the accessibility attributes and print what was written."""
    out.parent.mkdir(parents=True, exist_ok=True)
    measured.to_parquet(out)

    print(RULE)
    print(f"Wrote {out}")
    print(f"  Rows    : {len(measured):,}")
    print(f"  Columns : {', '.join(measured.columns)}")


def main(*, pilot, fresh, spine, out):
    """Measure gravity accessibility and station distance for every address.

    Args:
        pilot: Use the small Wellington pilot box instead of the full study area.
        fresh: Ignore the caches and re-fetch the stations and the address spine.
        spine: The address spine from step 1. None reads the standard location
            under temp/exposure/, with a pilot name when ``pilot`` is True.
            Rebuilt from LINZ if it is not there.
        out: Where to write the attributes. None writes to the standard location
            under temp/exposure/, with a pilot name when ``pilot`` is True.

    Raises:
        ValueError: If the address spine is empty, or LINZ_API_KEY is not set.
    """
    spine_path, out = resolve_paths(pilot=pilot, spine=spine, out=out)

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox, clip_to, extent_name = resolve_extent(study_areas, pilot=pilot)
    describe_extent(extent_name, bbox)

    addresses = get_spine(spine_path, bbox, clip_to, use_cache=not fresh)
    if addresses.empty:
        msg = (
            f"The address spine at {spine_path} is empty; there is nothing to measure."
        )
        raise ValueError(msg)
    print(f"Addresses in the spine: {len(addresses):,}")

    centres = load_centres(crs=addresses.crs)
    print(f"Centres: {len(centres):,}, drawn by fig_town_centres.py")

    print("\nReading the LINZ railway stations ...")
    fetch_bbox = station_bbox(addresses)
    fetched = get_nz_rail_stations(
        bbox=fetch_bbox, crs=addresses.crs, use_cache=not fresh
    )
    stations, added = add_stations(
        fetched, load_extra_stations(crs=addresses.crs), fetch_bbox
    )
    describe_stations(stations, added)

    measured = addresses.copy().reset_index(drop=True)
    measured[GRAVITY_COLUMN] = gravity_accessibility(measured.geometry, centres)
    measured[STATION_DISTANCE_COLUMN] = distance_to_nearest(
        measured.geometry, stations.geometry
    )

    describe_gravity(measured)
    describe_station_distance(measured)

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
        pilot=config.PILOT,
        fresh=config.FRESH,
        spine=config.SPINE,
        out=config.ACCESSIBILITY,
    )
