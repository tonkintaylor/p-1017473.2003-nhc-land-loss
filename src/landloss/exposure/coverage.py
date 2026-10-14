"""Keep only the structures that the insured land of their claim covers.

The retaining wall and crossing detections find structures near a claim, not
structures the claim's cover pays for. This module applies the coverage rule, so
only insured assets reach the vulnerability and loss modules:

- **A retaining wall is kept if it touches its claim's insured land buffered by**
  :data:`RW_COVERAGE_BUFFER_M`. A wall can hold up the insured land from just
  outside the extent and still be covered.
- **A culvert or bridge is kept only if it lies wholly inside its claim's
  insured land.** A crossing that runs out onto the road reserve or a
  neighbour's section is not part of this claim's cover. The test allows
  :data:`CROSSING_COVERAGE_TOLERANCE_M` of floating-point slack, because a
  crossing is cut from the same driveway corridor the insured land is built
  from and so shares its boundary.

Each asset is tested against its own claim's polygon only; lying on another
claim's insured land does not count.

A wall is also cut into the stretches that support each claim's insured land
(:func:`cut_walls_to_insured_stretches`): the line inside the claim's property
and within :data:`RW_COVERAGE_BUFFER_M` of its insured land. That is the rule
exposure rw step 6 insures a wall by, so a wall holding up a neighbour's land is
insured on the neighbour. Ground that lies in the stretches of several claims,
as a wall along a shared property boundary does, is shared equally between them.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

# A wall can support the insured land from just outside it and still count.
RW_COVERAGE_BUFFER_M = 2.0

# A crossing shares its edges with the insured land wherever that boundary is
# the driveway corridor, and the overlay that cuts it rounds those shared points
# to a hair either side. A millimetre absorbs the rounding without letting a
# crossing that genuinely runs off the land through.
CROSSING_COVERAGE_TOLERANCE_M = 1e-3
# How near a stretch's midpoint may lie to another claim's stretch of the same
# wall for the two to count as the same ground, in metres: coordinate noise on
# a wall lying along a shared boundary, not a distance a wall is ever off by.
SHARED_STRETCH_TOLERANCE_M = 0.01


def _check_frames(assets: gpd.GeoDataFrame, insured: gpd.GeoDataFrame) -> None:
    """Refuse frames in different systems, or in a geographic one.

    Args:
        assets: The structures to filter.
        insured: The insured land polygons.

    Raises:
        ValueError: If the two systems differ, or the shared one is geographic.
    """
    if assets.crs != insured.crs:
        msg = (
            f"the assets are in {assets.crs} but the insured land is in "
            f"{insured.crs}; reproject one onto the other first"
        )
        raise ValueError(msg)
    if assets.crs is not None and assets.crs.is_geographic:
        msg = (
            f"{assets.crs} is a geographic system, so a buffer of "
            f"{RW_COVERAGE_BUFFER_M} would be that many degrees. Work in a "
            "projected system such as NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def _claim_polygon(
    assets: gpd.GeoDataFrame, insured: gpd.GeoDataFrame, id_column: str
) -> gpd.GeoSeries:
    """Look up each asset's own insured land polygon.

    Args:
        assets: The structures, carrying ``id_column``.
        insured: The insured land polygons, one row per claim.
        id_column: The claim id column shared by both frames.

    Returns:
        The polygon of each asset's claim, aligned to ``assets.index``, with
        ``None`` where the claim has no insured land.
    """
    lookup = insured.set_index(id_column).geometry.to_dict()
    polygons = [lookup.get(claim) for claim in assets[id_column]]
    return gpd.GeoSeries(polygons, index=assets.index, crs=assets.crs)


def keep_walls_on_insured_land(
    walls: gpd.GeoDataFrame,
    insured: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    buffer_m: float = RW_COVERAGE_BUFFER_M,
) -> gpd.GeoDataFrame:
    """Keep the walls that touch their own claim's buffered insured land.

    Args:
        walls: The retaining wall lines, carrying ``id_column``.
        insured: The insured land polygons, one row per claim.
        id_column: The claim id column shared by both frames.
        buffer_m: How far outside the insured land a wall may lie and still
            count, in metres.

    Returns:
        A copy of the kept walls with their original columns. A wall whose
        claim has no insured land is dropped.

    Raises:
        ValueError: If the two frames are in different systems, or a
            geographic one.
    """
    _check_frames(walls, insured)
    if walls.empty:
        return walls.copy()
    polygons = _claim_polygon(walls, insured, id_column)
    keep = walls.geometry.intersects(polygons.buffer(buffer_m), align=False)
    return walls[keep.to_numpy()].copy()


def keep_crossings_within_insured_land(
    crossings: gpd.GeoDataFrame,
    insured: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    tolerance_m: float = CROSSING_COVERAGE_TOLERANCE_M,
) -> gpd.GeoDataFrame:
    """Keep the crossings that lie wholly inside their own claim's insured land.

    A crossing on the boundary of the insured land counts as inside, so a
    culvert running up to the edge of the extent is kept. The polygon is grown
    by ``tolerance_m`` before the test, so a shared boundary point the overlay
    rounded just outside still counts as on it.

    Args:
        crossings: The culvert and bridge geometries, of any type, carrying
            ``id_column``.
        insured: The insured land polygons, one row per claim.
        id_column: The claim id column shared by both frames.
        tolerance_m: How far outside the insured land a crossing's points may
            fall and still count as inside, in metres.

    Returns:
        A copy of the kept crossings with their original columns. A crossing
        whose claim has no insured land is dropped.

    Raises:
        ValueError: If the two frames are in different systems, or a
            geographic one.
    """
    _check_frames(crossings, insured)
    if crossings.empty:
        return crossings.copy()
    polygons = _claim_polygon(crossings, insured, id_column)
    keep = crossings.geometry.covered_by(polygons.buffer(tolerance_m), align=False)
    return crossings[keep.to_numpy()].copy()


def _repeated_ids(frame: gpd.GeoDataFrame, id_column: str, name: str) -> None:
    """Refuse a frame that is not one row per claim."""
    repeated = frame[id_column].duplicated()
    if repeated.any():
        ids = frame.loc[repeated, id_column].unique().tolist()
        msg = f"{name} repeats {id_column} {ids[:5]}"
        raise ValueError(msg)


def insured_support_regions(
    parcels: gpd.GeoDataFrame,
    insured: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    buffer_m: float = RW_COVERAGE_BUFFER_M,
) -> gpd.GeoDataFrame:
    """Return, per claim, the ground where a wall supports its insured land.

    That is the claim's property clipped to its insured land buffered by
    ``buffer_m``. Clipping to the property is what stops a neighbour's ground
    within the buffer from counting.

    Args:
        parcels: The claim properties, one row per claim carrying ``id_column``.
        insured: The insured land polygons, one row per claim.
        id_column: The claim id column shared by both frames.
        buffer_m: How far outside the insured land a wall may lie and still
            support it, in metres.

    Returns:
        ``id_column`` and the geometry, one row per claim that has a property
        and a non-empty region, on a fresh index.

    Raises:
        ValueError: If the two frames are in different systems, or a
            geographic one, or either repeats a claim id.
    """
    _check_frames(parcels, insured)
    _repeated_ids(parcels, id_column, "the parcels")
    _repeated_ids(insured, id_column, "the insured land")
    parcel_of = parcels.set_index(id_column).geometry
    has_parcel = insured[id_column].isin(parcel_of.index).to_numpy()
    land = insured[has_parcel]
    claim_parcels = parcel_of.reindex(land[id_column]).to_numpy()
    invalid = ~shapely.is_valid(claim_parcels)
    claim_parcels[invalid] = shapely.make_valid(claim_parcels[invalid])
    regions = shapely.intersection(
        claim_parcels, land.geometry.buffer(buffer_m).to_numpy()
    )
    out = gpd.GeoDataFrame(
        {id_column: land[id_column].to_numpy()}, geometry=regions, crs=insured.crs
    )
    return out[~out.geometry.is_empty].reset_index(drop=True)


def _shared_lengths(wall_position: pd.Series, lines: pd.Series) -> np.ndarray:
    """Return each stretch's length, with ground in several stretches shared.

    A wall's stretches are noded together, so each piece lies wholly in one or
    more of them, and a piece in k stretches gives each 1/k of its length. A
    wall with one stretch is its length and does not go through the loop.

    Args:
        wall_position: The wall each stretch is of.
        lines: The stretch lines, one per row.

    Returns:
        The share of each stretch, in the order of ``lines``.
    """
    geoms = lines.to_numpy()
    lengths = shapely.length(geoms)
    positions = wall_position.to_numpy()
    walls, counts = np.unique(positions, return_counts=True)
    for wall in walls[counts > 1]:
        rows = np.flatnonzero(positions == wall)
        noded = shapely.get_parts(shapely.union_all(geoms[rows]))
        noded = noded[shapely.get_type_id(noded) == 1]
        pieces = shapely.length(noded)
        middles = shapely.line_interpolate_point(noded, 0.5, normalized=True)
        within = shapely.dwithin(
            middles[:, None], geoms[rows][None, :], SHARED_STRETCH_TOLERANCE_M
        )
        sharers = np.maximum(within.sum(axis=1), 1)
        lengths[rows] = (pieces[:, None] * within / sharers[:, None]).sum(axis=0)
    return lengths


def cut_walls_to_insured_stretches(
    walls: gpd.GeoDataFrame,
    regions: gpd.GeoDataFrame,
    *,
    wall_id_column: str,
    min_length_m: float,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Cut each wall into the stretches that support each claim's insured land.

    Args:
        walls: The wall lines, carrying ``wall_id_column``.
        regions: :func:`insured_support_regions`' output.
        wall_id_column: The column naming each wall.
        min_length_m: The shortest stretch kept, in metres.
        id_column: The claim id column of ``regions``.

    Returns:
        ``wall_id_column``, ``id_column``, ``length_m`` and the stretch line,
        one row per wall and claim, in wall order and, within a wall, longest
        stretch first (ties by claim id). A wall that leaves and re-enters a
        region is one row holding both parts. Lengths are planar, in the
        frames' metres.

        Any part of a wall that lies in the stretches of k claims, as a wall
        along a shared property boundary does (a closed polygon holds its own
        boundary, so both neighbours' regions hold the line), is shared
        equally: each claim's ``length_m`` takes 1/k of that part. The line is
        the claim's full stretch, so on a shared boundary the line is shared
        and ``length_m`` is the claim's share. A wall's ``length_m`` rows
        therefore never sum to more than the wall. ``min_length_m`` applies to
        the share. Anything that cuts the stretch lines further, such as
        damaged lengths, must share a boundary the same way.

    Raises:
        ValueError: If the two frames are in different systems, or a
            geographic one.
    """
    _check_frames(walls, regions)
    columns = [wall_id_column, id_column, "length_m", "geometry"]
    line_geoms = walls.geometry.to_numpy()
    region_geoms = regions.geometry.to_numpy()
    owner, region = regions.sindex.query(line_geoms, predicate="intersects")
    if len(owner) == 0:
        return gpd.GeoDataFrame(
            {
                wall_id_column: pd.Series(dtype=object),
                id_column: pd.Series(dtype=regions[id_column].dtype),
                "length_m": pd.Series(dtype="float64"),
            },
            geometry=gpd.GeoSeries([], crs=walls.crs),
            crs=walls.crs,
        )[columns]
    clipped = shapely.intersection(line_geoms[owner], region_geoms[region])
    parts, part_of = shapely.get_parts(clipped, return_index=True)
    is_line = shapely.get_type_id(parts) == 1
    stretches = np.full(len(clipped), None, dtype=object)
    if is_line.any():
        has_line, dense = np.unique(part_of[is_line], return_inverse=True)
        stretches[has_line] = shapely.line_merge(
            shapely.multilinestrings(parts[is_line], indices=dense)
        )
    out = pd.DataFrame(
        {
            "wall_position": owner,
            wall_id_column: walls[wall_id_column].to_numpy(dtype=object)[owner],
            id_column: regions[id_column].to_numpy()[region],
            "geometry": stretches,
        }
    )
    out = out[out["geometry"].notna()]
    out["length_m"] = _shared_lengths(out["wall_position"], out["geometry"])
    out = out[out["length_m"] >= min_length_m]
    out = out.sort_values(
        ["wall_position", "length_m", id_column], ascending=[True, False, True]
    )
    return gpd.GeoDataFrame(
        out[columns].reset_index(drop=True), geometry="geometry", crs=walls.crs
    )
