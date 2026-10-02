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
"""

import geopandas as gpd

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

# A wall can support the insured land from just outside it and still count.
RW_COVERAGE_BUFFER_M = 2.0

# A crossing shares its edges with the insured land wherever that boundary is
# the driveway corridor, and the overlay that cuts it rounds those shared points
# to a hair either side. A millimetre absorbs the rounding without letting a
# crossing that genuinely runs off the land through.
CROSSING_COVERAGE_TOLERANCE_M = 1e-3


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
