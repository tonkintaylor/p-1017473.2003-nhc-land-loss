"""Driveways, generated as the shortest path from a building to a road.

The insured land is the ground around the dwelling **and the driveway**, so an
extent built from building outlines alone is short of NHC's own definition.
Driveways matter out of proportion to their area because they are where most
retaining walls sit, and because a driveway is often the piece of a property
that a landslide takes.

No driveway dataset exists for the study area, and none is obtainable within
this engagement, so they are generated. This resolves **I-10**, which proposed
mapping them by remote sensing: the geometry here is free and immediate, where
remote sensing would be neither.

A driveway is taken as the **straight line from the building to the nearest
point on the nearest road**, given a width. That is the shortest path in the
plane, which is what the approach says, and it is worth being clear about what
it therefore is not:

- A real driveway bends around the house, the bank and the neighbour's fence,
  so a generated one is shorter than the real thing and in the wrong place along
  most of its length.
- It ignores gradient entirely. A route straight up a face too steep to drive is
  drawn exactly like a flat one, and whether such a route should be rejected --
  and what then happens to a building with no drivable route at all -- is an
  open decision on this step.
- It ignores which road the property is actually addressed off, taking the
  nearest instead. On a corner section those differ.

None of that moves the area much, which is what the loss model reads, but all of
it matters if anyone asks where a particular driveway runs.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString
from shapely.ops import nearest_points

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

# Half the width of the driveway corridor, in metres. A driveway wide enough for
# one car is about 3 m, so the line is buffered by half that to give the strip of
# ground the insured extent covers.
DRIVEWAY_HALF_WIDTH_M = 1.5

# Beyond this a building is taken to have no road to reach, rather than being
# joined to one implausibly far away. Generous, because a long rural driveway is
# a real thing and this study's extent includes some.
MAX_DRIVEWAY_LENGTH_M = 300.0

DRIVEWAY_LENGTH_COLUMN = "driveway_length_m"


def nearest_road_points(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
) -> tuple[gpd.GeoSeries, gpd.GeoSeries, np.ndarray]:
    """Return the closest pair of points between each building and the roads.

    Args:
        buildings: The building outlines, in a projected CRS.
        roads: The road centrelines, in the same CRS.

    Returns:
        The point on each building, the point on the road it is closest to, and
        the distance between them in metres.

    Raises:
        ValueError: If the two frames disagree on their CRS, or the roads are
            empty.
    """
    if buildings.crs != roads.crs:
        msg = f"buildings are {buildings.crs} and roads are {roads.crs}"
        raise ValueError(msg)
    if roads.empty:
        msg = "no roads to route to"
        raise ValueError(msg)

    network = roads.geometry.union_all()
    pairs = [nearest_points(outline, network) for outline in buildings.geometry]
    on_building = gpd.GeoSeries(
        [pair[0] for pair in pairs], index=buildings.index, crs=buildings.crs
    )
    on_road = gpd.GeoSeries(
        [pair[1] for pair in pairs], index=buildings.index, crs=buildings.crs
    )
    return on_building, on_road, on_building.distance(on_road).to_numpy()


def generate_driveways(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    half_width_m: float = DRIVEWAY_HALF_WIDTH_M,
    max_length_m: float = MAX_DRIVEWAY_LENGTH_M,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Generate a driveway corridor per building.

    Args:
        buildings: The building outlines, already attached to an address and
            carrying ``id_column``.
        roads: The road centrelines over the same extent.
        half_width_m: Half the width of the driveway corridor.
        max_length_m: Beyond this, a building is taken to have no road to reach.
        id_column: The address identifier carried onto each driveway.

    Returns:
        One row per building that reached a road, carrying ``id_column``,
        :data:`DRIVEWAY_LENGTH_COLUMN` and the corridor polygon. A building
        already touching a road gets a corridor of zero length and so no
        polygon; those rows are dropped, because the building buffer already
        covers that ground.

    Raises:
        ValueError: If the buildings carry no ``id_column``.
    """
    if id_column not in buildings.columns:
        msg = f"buildings carry no {id_column!r} column"
        raise ValueError(msg)
    if buildings.empty:
        return gpd.GeoDataFrame(
            {id_column: [], DRIVEWAY_LENGTH_COLUMN: []},
            geometry=gpd.GeoSeries([], crs=buildings.crs),
            crs=buildings.crs,
        )

    on_building, on_road, distance = nearest_road_points(buildings, roads)

    # A building already on a road has nothing to draw, and one too far from any
    # road is taken not to reach one at all.
    reaches = (distance > 0) & (distance <= max_length_m)
    if not reaches.any():
        return gpd.GeoDataFrame(
            {id_column: [], DRIVEWAY_LENGTH_COLUMN: []},
            geometry=gpd.GeoSeries([], crs=buildings.crs),
            crs=buildings.crs,
        )

    lines = [
        LineString([start, end])
        for start, end in zip(on_building[reaches], on_road[reaches], strict=True)
    ]
    corridors = gpd.GeoSeries(lines, crs=buildings.crs).buffer(
        half_width_m, cap_style="flat"
    )

    return gpd.GeoDataFrame(
        {
            id_column: buildings.loc[reaches, id_column].to_numpy(),
            DRIVEWAY_LENGTH_COLUMN: distance[reaches],
        },
        geometry=corridors.to_numpy(),
        crs=buildings.crs,
    )


def merge_driveways_into_extent(
    extent: gpd.GeoDataFrame,
    driveways: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Add each property's driveways to its insured land polygon.

    The driveway is unioned into the polygon rather than kept beside it, because
    the insured land is one extent per property and the hazard modules intersect
    against it as one shape.

    Args:
        extent: One insured land polygon per property.
        driveways: The driveway corridors, keyed on the same identifier.
        id_column: The property identifier both are keyed on.

    Returns:
        The extent with driveways merged in, on the same columns. A property
        with no driveway is returned unchanged.

    Raises:
        ValueError: If the two frames disagree on their CRS.
    """
    if driveways.empty:
        return extent
    if extent.crs != driveways.crs:
        msg = f"extent is {extent.crs} and driveways are {driveways.crs}"
        raise ValueError(msg)

    joined = driveways.dissolve(by=id_column).geometry
    merged = extent.copy()
    additions = merged[id_column].map(joined)
    has_driveway = additions.notna()
    merged.loc[has_driveway, merged.geometry.name] = [
        polygon.union(addition)
        for polygon, addition in zip(
            merged.loc[has_driveway, merged.geometry.name],
            additions[has_driveway],
            strict=True,
        )
    ]
    return merged


def describe_driveways(
    driveways: gpd.GeoDataFrame,
    attached: int,
) -> pd.Series:
    """Return the driveway length distribution, for a run to print.

    Args:
        driveways: The generated corridors.
        attached: How many attached outlines they were generated from. One
            outline shared between several addresses is routed once per address,
            so this is a count of building-address pairs and not of buildings.

    Returns:
        The count, the share of attached outlines that reached a road, and the
        length quartiles in metres.
    """
    lengths = driveways[DRIVEWAY_LENGTH_COLUMN].to_numpy(dtype=float)
    if lengths.size == 0:
        return pd.Series({"driveways": 0, "share of attached outlines": 0.0})
    quartiles = np.percentile(lengths, [0, 25, 50, 75, 100])
    return pd.Series(
        {
            "driveways": len(lengths),
            "share of attached outlines": len(lengths) / attached if attached else 0.0,
            "min length m": quartiles[0],
            "25% length m": quartiles[1],
            "median length m": quartiles[2],
            "75% length m": quartiles[3],
            "max length m": quartiles[4],
        }
    )
