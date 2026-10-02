"""Where an insured accessway crosses a watercourse, and what carries it over.

The exposure is the **crossing**, not the structure: a culvert or a bridge
exists to take the accessway over water, so finding where the two meet finds the
population. Where an accessway crosses nothing, there is nothing to find.

Two things happen here, and only the first is observed.

**Detecting the crossing** is geometry. The accessway is intersected against
both LINZ river layers -- the name lines and the name polygons -- because a
narrow stream exists only as a centreline while a river wide enough to need a
bridge has an areal extent, and testing the lines alone would miss exactly the
crossings most likely to carry a bridge. Any watercourse counts, not only the
named rivers the liquefaction work separates out, because most accessway
crossings are of small streams.

**Choosing the structure is a draw**, because no crossing dataset exists for the
study area. A crossing takes a culvert with probability
:data:`CULVERT_PROBABILITY` and a bridge otherwise; the two are exhaustive,
since something has to carry the accessway over the water. Both figures are
engineering judgement and neither is fitted to anything, which is why they are
named here rather than buried in a script.

Note what the detection inherits from its inputs. Both LINZ layers carry
**named** watercourses only, so an unnamed stream is invisible to this test --
and unnamed streams are where most small accessway crossings are. The population
this produces is therefore a floor rather than an estimate.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

# The split between the two structures at a crossing. Exhaustive: a crossing
# carries one or the other, because the accessway has to get over the water
# somehow. Engineering judgement, fitted to nothing.
CULVERT_PROBABILITY = 0.8
BRIDGE_PROBABILITY = 1.0 - CULVERT_PROBABILITY

CULVERT = "culvert"
BRIDGE = "bridge"
STRUCTURES = (CULVERT, BRIDGE)

STRUCTURE_COLUMN = "structure"
WATERCOURSE_SOURCE_COLUMN = "watercourse_source"

# Which layer a crossing was found against, kept so the run can report what
# reading both layers earned over reading the lines alone.
FROM_LINES = "lines"
FROM_POLYGONS = "polygons"
# A crossing both layers found, where a river polygon has its centreline
# running through it, merged into one row.
FROM_BOTH = "both"
SOURCES = (FROM_LINES, FROM_POLYGONS, FROM_BOTH)


def _crossing_geometry(
    accessways: gpd.GeoDataFrame,
    water: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Return the part of each accessway lying on a watercourse."""
    if water.empty:
        return accessways.iloc[0:0].copy()
    overlay = gpd.overlay(
        accessways,
        water[[water.geometry.name]],
        how="intersection",
        keep_geom_type=False,
    )
    return overlay[~overlay.geometry.is_empty]


def _component_labels(crossings: gpd.GeoDataFrame, id_column: str) -> np.ndarray:
    """Label the groups of same-claim crossings that intersect one another.

    Args:
        crossings: The crossings found on both layers, with a default index.
        id_column: The property identifier the groups must share.

    Returns:
        One label per row; rows sharing a label are one physical crossing.
    """
    parent = np.arange(len(crossings))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    claims = crossings[id_column].to_numpy()
    left, right = crossings.sindex.query(crossings.geometry, predicate="intersects")
    for i, j in zip(left, right, strict=True):
        if i < j and claims[i] == claims[j]:
            parent[root(j)] = root(i)
    return np.array([root(i) for i in range(len(crossings))])


def _merge_shared_crossings(
    crossings: gpd.GeoDataFrame, id_column: str
) -> gpd.GeoDataFrame:
    """Merge the rows of one claim that are the same physical crossing.

    The two layers overlap where a river polygon has its centreline running
    through it, so one accessway over that river is found twice. Any rows of the
    same claim that intersect are unioned into one, so each physical crossing
    becomes one structure and one row in the loss tables.

    Args:
        crossings: The crossings found on both layers, with a default index.
        id_column: The property identifier carried onto each crossing.

    Returns:
        One row per physical crossing, in first-found order. A merged row found
        on both layers carries :data:`FROM_BOTH`.
    """
    labels = pd.Series(_component_labels(crossings, id_column), index=crossings.index)
    merged = crossings[~labels.duplicated().to_numpy()].copy()
    shared = labels[labels.duplicated(keep=False)]
    for _, members in shared.groupby(shared):
        group = crossings.loc[members.index]
        position = members.index[0]
        sources = set(group[WATERCOURSE_SOURCE_COLUMN])
        merged.loc[position, WATERCOURSE_SOURCE_COLUMN] = (
            sources.pop() if len(sources) == 1 else FROM_BOTH
        )
        merged.loc[position, merged.geometry.name] = shapely.union_all(
            group.geometry.to_numpy()
        )
    return merged.reset_index(drop=True)


def detect_crossings(
    accessways: gpd.GeoDataFrame,
    river_lines: gpd.GeoDataFrame,
    river_polygons: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Find where the accessways cross a watercourse.

    Args:
        accessways: The driveway corridors, carrying ``id_column``.
        river_lines: The river name lines over the same extent.
        river_polygons: The river name polygons over the same extent.
        id_column: The property identifier carried onto each crossing.

    Returns:
        One row per physical crossing, carrying ``id_column``,
        :data:`WATERCOURSE_SOURCE_COLUMN` and the crossing geometry. Crossings
        of the same property that intersect, such as a river found on both
        layers, are merged into one row. A property whose accessway crosses
        nothing has no row.

    Raises:
        ValueError: If the frames disagree on their coordinate reference system,
            or the accessways carry no ``id_column``.
    """
    if id_column not in accessways.columns:
        msg = f"accessways carry no {id_column!r} column"
        raise ValueError(msg)
    for name, frame in (
        ("river_lines", river_lines),
        ("river_polygons", river_polygons),
    ):
        if not frame.empty and frame.crs != accessways.crs:
            msg = f"accessways are {accessways.crs} and {name} are {frame.crs}"
            raise ValueError(msg)

    found = []
    for source, water in ((FROM_LINES, river_lines), (FROM_POLYGONS, river_polygons)):
        crossings = _crossing_geometry(accessways, water)
        if crossings.empty:
            continue
        crossings = crossings[[id_column, crossings.geometry.name]].copy()
        crossings[WATERCOURSE_SOURCE_COLUMN] = source
        found.append(crossings)

    if not found:
        return gpd.GeoDataFrame(
            {id_column: [], WATERCOURSE_SOURCE_COLUMN: []},
            geometry=gpd.GeoSeries([], crs=accessways.crs),
            crs=accessways.crs,
        )

    combined = pd.concat(found, ignore_index=True)
    combined = gpd.GeoDataFrame(
        combined, geometry=combined.geometry.name, crs=accessways.crs
    )
    return _merge_shared_crossings(combined, id_column)


def sample_structures(
    crossings: gpd.GeoDataFrame,
    rng: np.random.Generator,
) -> gpd.GeoDataFrame:
    """Draw a culvert or a bridge at each crossing.

    Args:
        crossings: The detected crossings, as :func:`detect_crossings` returns.
        rng: The generator for this realisation's exposure stream.

    Returns:
        A copy carrying :data:`STRUCTURE_COLUMN`, one of :data:`STRUCTURES`.
    """
    drawn = crossings.copy()
    if drawn.empty:
        drawn[STRUCTURE_COLUMN] = pd.Series(dtype="object")
        return drawn
    drawn[STRUCTURE_COLUMN] = np.where(
        rng.random(len(drawn)) < CULVERT_PROBABILITY, CULVERT, BRIDGE
    )
    return drawn


def describe_crossings(crossings: gpd.GeoDataFrame, accessways: int) -> pd.Series:
    """Return what was found, for a run to print.

    Args:
        crossings: The drawn crossing population.
        accessways: How many accessways were tested.

    Returns:
        The counts by structure and by which layer found the crossing, and the
        share of accessways that cross anything.
    """
    summary = {
        "accessways tested": accessways,
        "crossings found": len(crossings),
        "share of accessways": len(crossings) / accessways if accessways else 0.0,
    }
    if crossings.empty:
        return pd.Series(summary)
    for structure in STRUCTURES:
        summary[structure] = int((crossings[STRUCTURE_COLUMN] == structure).sum())
    for source in SOURCES:
        summary[f"found on {source}"] = int(
            (crossings[WATERCOURSE_SOURCE_COLUMN] == source).sum()
        )
    return pd.Series(summary)
