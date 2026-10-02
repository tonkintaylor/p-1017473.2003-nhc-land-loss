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

A driveway is taken as the **straight line from the property's main building to
the nearest point on the nearest road**, given a width, and **only its first
60 m is insured land**.

Both limits are the Act's. Land cover extends to the main access way, so a
property has one: it is routed from the property's largest building, taken as
the main dwelling, and a garage, a shed or a second dwelling on the same
property adds none. And the access way is covered within 60 m of the dwelling,
measured in a straight horizontal line from it (the dwelling, not the boundary),
so a route longer than that is cut at 60 m. Whether a second dwelling on the
same property earns an access way of its own is register question Q-15, put to
John Leeves; until it is answered, one per property.

The route is still measured to the road in full, and carried as
:data:`DRIVEWAY_LENGTH_COLUMN`, because how far the dwelling is from a road is
what the loss module's construction access rating reads. The insured part is
:data:`INSURED_DRIVEWAY_LENGTH_COLUMN`, and it is the part the corridor covers.

The straight route is the shortest path in the plane, which is what the approach
says, and it is worth being clear about what it therefore is not:

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

# The Act's limit: the main access way is insured land within 60 m of the
# dwelling, in a straight horizontal line from it.
MAX_INSURED_ACCESS_M = 60.0

# The full route from the main building to the road, and the insured part of it.
DRIVEWAY_LENGTH_COLUMN = "driveway_length_m"
INSURED_DRIVEWAY_LENGTH_COLUMN = "insured_driveway_length_m"


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


def main_buildings(
    buildings: gpd.GeoDataFrame, *, id_column: str = CLAIM_ID_COLUMN
) -> gpd.GeoDataFrame:
    """Return each property's main building: its largest.

    The main access way runs to the dwelling, and on a residential section the
    dwelling is the largest building; a garage, a shed or a sleep-out is smaller.
    On a property with two houses this picks the larger, which is the one access
    way the Act covers until Q-15 says otherwise.

    Args:
        buildings: The building parts, carrying ``id_column``.
        id_column: The property identifier.

    Returns:
        One building per property, the largest by footprint area, ties going to
        the first.
    """
    if buildings.empty:
        return buildings
    # By position rather than label, so a frame whose index repeats -- parts
    # concatenated from several sources -- cannot return more than one per id.
    indexed = buildings.reset_index(drop=True)
    largest = indexed.geometry.area.groupby(indexed[id_column]).idxmax()
    return indexed.loc[largest.to_numpy()]


def generate_driveways(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    half_width_m: float = DRIVEWAY_HALF_WIDTH_M,
    max_length_m: float = MAX_DRIVEWAY_LENGTH_M,
    insured_length_m: float = MAX_INSURED_ACCESS_M,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Generate one main access way per property.

    Routed from the property's main building (:func:`main_buildings`) to the
    nearest road, and cut at ``insured_length_m`` from the building: the part
    of the access way the Act insures.

    Args:
        buildings: The building outlines, already attached to a property and
            carrying ``id_column``. Every building of a property may be passed;
            only the main one is routed.
        roads: The road centrelines over the same extent.
        half_width_m: Half the width of the driveway corridor.
        max_length_m: Beyond this, a building is taken to have no road to reach.
        insured_length_m: How much of the route, from the building, is insured.
        id_column: The property identifier carried onto each driveway.

    Returns:
        At most one row per property, carrying ``id_column``,
        :data:`DRIVEWAY_LENGTH_COLUMN` (the full route to the road),
        :data:`INSURED_DRIVEWAY_LENGTH_COLUMN` (the part within
        ``insured_length_m``) and the corridor polygon over the insured part. A
        main building already touching a road gets a corridor of zero length
        and so no polygon; those rows are dropped, because the building buffer
        already covers that ground.

    Raises:
        ValueError: If the buildings carry no ``id_column``.
    """
    if id_column not in buildings.columns:
        msg = f"buildings carry no {id_column!r} column"
        raise ValueError(msg)
    empty = gpd.GeoDataFrame(
        {id_column: [], DRIVEWAY_LENGTH_COLUMN: [], INSURED_DRIVEWAY_LENGTH_COLUMN: []},
        geometry=gpd.GeoSeries([], crs=buildings.crs),
        crs=buildings.crs,
    )
    if buildings.empty:
        return empty

    buildings = main_buildings(buildings, id_column=id_column)
    on_building, on_road, distance = nearest_road_points(buildings, roads)

    # A building already on a road has nothing to draw, and one too far from any
    # road is taken not to reach one at all.
    reaches = (distance > 0) & (distance <= max_length_m)
    if not reaches.any():
        return empty

    # Cut at the insured length, measured from the building along the straight
    # route, which is a straight horizontal line from the dwelling.
    insured = np.minimum(distance[reaches], insured_length_m)
    lines = [
        LineString([start, LineString([start, end]).interpolate(length)])
        for start, end, length in zip(
            on_building[reaches], on_road[reaches], insured, strict=True
        )
    ]
    corridors = gpd.GeoSeries(lines, crs=buildings.crs).buffer(
        half_width_m, cap_style="flat"
    )

    return gpd.GeoDataFrame(
        {
            id_column: buildings.loc[reaches, id_column].to_numpy(),
            DRIVEWAY_LENGTH_COLUMN: distance[reaches],
            INSURED_DRIVEWAY_LENGTH_COLUMN: insured,
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
        attached: How many properties with a building they were generated for:
            one main access way is routed per property.

    Returns:
        The count, the share of those properties that reached a road, the share
        whose route was cut at the insured length, and the route length
        quartiles in metres.
    """
    lengths = driveways[DRIVEWAY_LENGTH_COLUMN].to_numpy(dtype=float)
    if lengths.size == 0:
        return pd.Series({"driveways": 0, "share of properties": 0.0})
    quartiles = np.percentile(lengths, [0, 25, 50, 75, 100])
    cut = (
        driveways[INSURED_DRIVEWAY_LENGTH_COLUMN].to_numpy(dtype=float) < lengths
        if INSURED_DRIVEWAY_LENGTH_COLUMN in driveways.columns
        else np.zeros(len(lengths), dtype=bool)
    )
    return pd.Series(
        {
            "driveways": len(lengths),
            "share of properties": len(lengths) / attached if attached else 0.0,
            "share cut at the insured length": float(cut.mean()),
            "min length m": quartiles[0],
            "25% length m": quartiles[1],
            "median length m": quartiles[2],
            "75% length m": quartiles[3],
            "max length m": quartiles[4],
        }
    )
