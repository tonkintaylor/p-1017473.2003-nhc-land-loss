"""How close each address is to the places that make land worth more.

Two attributes, both measured in straight lines:

.. code-block:: text

    gravity_accessibility = sum over centres c of W_c * exp(-d_ic / L_c)
    nearest_station_m     = distance to the nearest railway station

The gravity term is what separates Kelburn from Makara inside Wellington City,
where the landform class and the terrain do not: both are hill, and both can be
equally steep. Each centre contributes its weight ``W_c`` at its own door and
decays with distance over its own length ``L_c``, so the Wellington CBD's pull
reaches well up the Hutt Valley while a local shopping street's is spent within
a few kilometres. Summing rather than taking the nearest centre is deliberate: a
Petone address gains from Jackson Street, Lower Hutt and the Wellington CBD at
once, and that is what its price reflects.

Straight lines are the cheap first stage. They overstate how close anywhere on
the far side of the harbour is -- Days Bay and Eastbourne are about 9 km from
the Wellington CBD as the crow flies and a 25 minute drive around the bay -- and
whether that matters enough to justify road-network travel times is the test
recorded in the land value step's implementation plan.

This module only measures. How the two attributes move a land value is
:func:`landloss.exposure.land.land_value.accessibility_modifier`.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.io import ASSETS_DIR

# The centres, their weights and their decay lengths, one row per centre with the
# reason for each number on its row.
CENTRES_PATH = ASSETS_DIR / "land-value-centres.csv"

# The columns the centres asset has to carry. Coordinates are WGS84 longitude and
# latitude, because that is what anyone checking a centre against a web map reads
# off it.
CENTRE_COLUMNS = ("name", "kind", "weight", "decay_length_m", "lon", "lat", "basis")

# Stations missing from the LINZ layer, added by hand, one row per station with
# the reason on its row. Wellington Station is the one that matters.
EXTRA_STATIONS_PATH = ASSETS_DIR / "land-value-extra-stations.csv"
EXTRA_STATION_COLUMNS = ("name", "lon", "lat", "basis")

# An added station this close to one the LINZ layer already carries is taken to
# be the same station, so that once LINZ adds it the hand-placed copy drops out
# rather than standing beside it. Wider than the error in placing it by hand.
DUPLICATE_STATION_M = 250.0

# The attribute columns this module produces, named here so the step script and
# the land value model agree on them.
GRAVITY_COLUMN = "gravity_accessibility"
STATION_DISTANCE_COLUMN = "nearest_station_m"


def load_centres(
    path: Path = CENTRES_PATH, crs: int | str = constants.DEFAULT_CRS
) -> gpd.GeoDataFrame:
    """Read the centres the gravity accessibility is measured against.

    Args:
        path: The CSV to read. Defaults to the packaged asset.
        crs: The coordinate reference system to return the centres in.

    Returns:
        One point per centre, in ``crs``, carrying every column of the asset.

    Raises:
        ValueError: If a column is missing, or a weight or decay length is not
            positive. A zero decay length would divide by zero, and a zero or
            negative weight is a typo rather than a centre.
    """
    centres = pd.read_csv(path)

    missing = [column for column in CENTRE_COLUMNS if column not in centres.columns]
    if missing:
        msg = f"The centres at {path} are missing column(s): {', '.join(missing)}."
        raise ValueError(msg)

    for column in ("weight", "decay_length_m"):
        bad = centres.loc[~(centres[column] > 0), "name"]
        if not bad.empty:
            msg = (
                f"The centres at {path} carry a non-positive {column} for: "
                f"{', '.join(bad)}."
            )
            raise ValueError(msg)

    return gpd.GeoDataFrame(
        centres,
        geometry=gpd.points_from_xy(centres["lon"], centres["lat"]),
        crs="EPSG:4326",
    ).to_crs(crs)


def gravity_accessibility(
    points: gpd.GeoSeries, centres: gpd.GeoDataFrame
) -> pd.Series:
    """Return each point's gravity accessibility to the centres.

    ``sum over centres c of W_c * exp(-d / L_c)``, with ``d`` the straight-line
    distance in the units of the CRS -- metres, in the study CRS.

    Computed as a dense distance matrix. At fifteen centres that is fifteen
    columns against however many addresses there are, which is cheap, and it
    keeps the formula readable in the code.

    Args:
        points: The address points, in a projected CRS in metres.
        centres: The centres from :func:`load_centres`, in the same CRS.

    Returns:
        The accessibility of each point, indexed as ``points`` is. A point with
        no geometry comes back NaN rather than zero, since zero would be read as
        remote, and so does every point when there are no centres.

    Raises:
        ValueError: If the two are in different coordinate reference systems.
    """
    if points.crs != centres.crs:
        msg = f"points are {points.crs} and centres are {centres.crs}"
        raise ValueError(msg)

    accessibility = pd.Series(np.nan, index=points.index, dtype=float)
    present = ~(points.isna() | points.is_empty)
    if centres.empty or not present.any():
        return accessibility

    located = points[present]
    distance = np.hypot(
        located.x.to_numpy()[:, None] - centres.geometry.x.to_numpy()[None, :],
        located.y.to_numpy()[:, None] - centres.geometry.y.to_numpy()[None, :],
    )
    weight = centres["weight"].to_numpy(dtype=float)
    decay = centres["decay_length_m"].to_numpy(dtype=float)

    accessibility.loc[located.index] = (weight * np.exp(-distance / decay)).sum(axis=1)
    return accessibility


def distance_to_nearest(points: gpd.GeoSeries, targets: gpd.GeoSeries) -> pd.Series:
    """Return the straight-line distance from each point to the nearest target.

    Args:
        points: The address points.
        targets: The places to measure to, in the same CRS.

    Returns:
        The distance from each point to its nearest target, indexed as
        ``points`` is. NaN everywhere if there are no targets, which the land
        value model reads as "no station premium" rather than as an error, and
        NaN for a point with no geometry.

    Raises:
        ValueError: If the two are in different coordinate reference systems.
    """
    if points.crs != targets.crs:
        msg = f"points are {points.crs} and targets are {targets.crs}"
        raise ValueError(msg)

    distance = pd.Series(np.nan, index=points.index, dtype=float)
    present = ~(points.isna() | points.is_empty)
    if targets.empty or not present.any():
        return distance

    # The spatial index answers nearest-neighbour queries without the full
    # matrix, which matters here because stations are not a short list the way
    # centres are.
    located = points[present]
    (input_positions, _), nearest = targets.sindex.nearest(
        located, return_all=False, return_distance=True
    )
    distance.loc[located.index[input_positions]] = nearest
    return distance


def load_extra_stations(
    path: Path = EXTRA_STATIONS_PATH, crs: int | str = constants.DEFAULT_CRS
) -> gpd.GeoDataFrame:
    """Read the stations added by hand to the LINZ layer.

    Args:
        path: The CSV to read. Defaults to the packaged asset.
        crs: The coordinate reference system to return the stations in.

    Returns:
        One point per station, in ``crs``, carrying ``name`` and ``basis``.

    Raises:
        ValueError: If a column is missing.
    """
    stations = pd.read_csv(path)

    missing = [c for c in EXTRA_STATION_COLUMNS if c not in stations.columns]
    if missing:
        msg = f"The stations at {path} are missing column(s): {', '.join(missing)}."
        raise ValueError(msg)

    return gpd.GeoDataFrame(
        stations[["name", "basis"]],
        geometry=gpd.points_from_xy(stations["lon"], stations["lat"]),
        crs="EPSG:4326",
    ).to_crs(crs)


def add_stations(
    fetched: gpd.GeoDataFrame,
    extra: gpd.GeoDataFrame,
    bbox: tuple[float, float, float, float],
) -> tuple[gpd.GeoDataFrame, list[str]]:
    """Add the hand-placed stations to the fetched ones.

    An added station is kept only if it falls inside ``bbox`` -- the extent the
    LINZ layer was fetched over, so the two sets cover the same ground -- and is
    more than :data:`DUPLICATE_STATION_M` from every fetched station.

    Args:
        fetched: The stations read from LINZ, carrying ``name``.
        extra: The stations from :func:`load_extra_stations`, in the same CRS.
        bbox: The extent the fetched stations were read over.

    Returns:
        The combined stations, carrying ``name`` and the geometry, and the names
        of the stations that were added, for the run to print.

    Raises:
        ValueError: If the two are in different coordinate reference systems.
    """
    if extra.crs != fetched.crs:
        msg = f"fetched stations are {fetched.crs} and added ones are {extra.crs}"
        raise ValueError(msg)

    minx, miny, maxx, maxy = bbox
    candidates = extra.cx[minx:maxx, miny:maxy]

    if not fetched.empty and not candidates.empty:
        distance = distance_to_nearest(candidates.geometry, fetched.geometry)
        candidates = candidates[distance > DUPLICATE_STATION_M]

    names = [str(name) for name in candidates["name"]]
    if candidates.empty:
        return fetched, names

    # Rebuilt from names and points rather than concatenated frame to frame, so
    # the two geometry columns never have to share a name.
    combined = gpd.GeoDataFrame(
        {"name": [*fetched["name"], *candidates["name"]]},
        geometry=[*fetched.geometry, *candidates.geometry],
        crs=fetched.crs,
    )
    return combined, names
