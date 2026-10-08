"""Whether a structure is caught by a landslide, shared by walls and crossings.

A retaining wall, culvert or bridge is not priced by how much ground a landslide
takes from it, as land is, but by whether a landslide reached it at all. The
flag is kept per kind of ground, because the policy settles the two differently:

- **Evacuated** -- the structure sits on ground the failure removed.
- **Inundated** -- the structure sits under ground where the debris came to rest.

A structure touching both kinds of ground carries both flags.

Retaining walls on sloping ground have a second route to a flag. The urban slope
model gives every such wall an **outcome** per world and earthquake
(``.agents/plans/urban-slope-build-contract.md`` section 5): its own polygon
failed through it, a larger urban failure absorbed it, a large-model landslide
superseded it, or it is still standing. :data:`OUTCOME_FLAGS` maps each outcome
onto one of the three contract flags, and :func:`wall_flags` ORs that mapping
with the geometric intersections. Any flag true means one replacement in
`loss`; the mapping only attributes the cause, so it lives in the one dict and
nowhere else.

A wall's geometric route asks more than :func:`landslide_flags` does of any
structure: a positive length of the wall's line must lie **inside** the
polygon (more than :data:`WALL_INSIDE_TOLERANCE_M` of it inside the polygon
shrunk by the same distance). Urban polygons tile the ground and are
reconciled so that wall lines are their edges, so a standing wall is very often
the edge of a neighbouring polygon; one that only runs along the boundary of
that neighbour's failure sits on no ground the failure took. This is the line
analogue of the hazard side's rule that polygons touching only along an edge
share no ground
(:data:`~landloss.hazard.landslide.urban.realisation.SHARED_GROUND_TOLERANCE_M2`).

This sits at the landslide level rather than under an asset submodule because it
reads no asset-specific attribute: it needs only an identifier and a geometry,
whatever the structure is.
"""

from collections.abc import Callable

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.domain.loss_contract import (
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.landslide.urban.realisation import (
    ABSORBED,
    FAILED_WITH_POLYGON,
    OUTCOME_COLUMN,
    OUTCOMES,
    SLOPE_ID_COLUMN,
    SUPERSEDED,
)

# Which flag each kind of damaged ground sets.
FLAG_COLUMNS = {
    EVACUATED: IS_EVACUATED_COLUMN,
    INUNDATED: IS_INUNDATED_COLUMN,
}

# Which contract flag each urban outcome sets, contract section 5.2. A wall
# whose polygon failed through it is written off by the shaking; one whose
# polygon was taken by a larger failure, urban or large, sits on evacuated
# ground. A standing wall sets none, and no outcome sets the inundated flag:
# that comes from geometry alone. The vocabulary is landslide step 9's
# (``landloss.hazard.landslide.urban.realisation.OUTCOMES``).
OUTCOME_FLAGS = {
    FAILED_WITH_POLYGON: IS_DAMAGED_BY_SHAKING_COLUMN,
    ABSORBED: IS_EVACUATED_COLUMN,
    SUPERSEDED: IS_EVACUATED_COLUMN,
}

# The three contract flags a wall carries, in output order.
WALL_FLAG_COLUMNS = (
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)

# How far inside a landslide polygon a wall's line must lie, and for how long,
# for the polygon to reach the wall, in m. A numerical tolerance, not a
# parameter: a hundredth of a 1 m DEM cell side, the length analogue of
# realisation.SHARED_GROUND_TOLERANCE_M2, so a line along a polygon's edge, or
# within floating-point noise of it, is not inside the polygon.
WALL_INSIDE_TOLERANCE_M = 0.01


def _caught_ids(
    assets: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    land_class: str,
    id_column: str,
) -> pd.Index:
    """Return the ids of the assets any landslide of one kind intersects."""
    slides = landslides[landslides[LAND_CLASS_COLUMN] == land_class]
    if slides.empty:
        return pd.Index([])
    joined = gpd.sjoin(
        assets[[id_column, assets.geometry.name]],
        slides[[slides.geometry.name]],
        predicate="intersects",
        how="inner",
    )
    return pd.Index(joined[id_column].unique())


def _lines_inside_ids(
    walls: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    land_class: str,
    id_column: str,
) -> pd.Index:
    """Return the ids of the walls whose line lies inside a landslide of one kind.

    A wall is caught where more than :data:`WALL_INSIDE_TOLERANCE_M` of its
    line lies inside some polygon shrunk by :data:`WALL_INSIDE_TOLERANCE_M`, so
    a line that only runs along the polygon's boundary, or touches it at a
    point, is not.
    """
    slides = landslides[landslides[LAND_CLASS_COLUMN] == land_class]
    if slides.empty:
        return pd.Index([])
    shrunk = slides.geometry.buffer(-WALL_INSIDE_TOLERANCE_M)
    interiors = gpd.GeoDataFrame(
        geometry=shrunk[~shrunk.is_empty].to_numpy(), crs=slides.crs
    )
    if interiors.empty:
        return pd.Index([])
    lines = walls[[id_column, walls.geometry.name]].reset_index(drop=True)
    joined = gpd.sjoin(lines, interiors, predicate="intersects", how="inner")
    if joined.empty:
        return pd.Index([])
    inside = shapely.intersection(
        lines.geometry.to_numpy()[joined.index.to_numpy()],
        interiors.geometry.to_numpy()[joined["index_right"].to_numpy()],
    )
    reached = shapely.length(inside) > WALL_INSIDE_TOLERANCE_M
    return pd.Index(joined.loc[reached, id_column].unique())


def _check_unique_ids(frame: pd.DataFrame, id_column: str, *, what: str) -> None:
    """Refuse a frame whose ids repeat."""
    repeated = frame[id_column][frame[id_column].duplicated()].unique()
    if len(repeated):
        msg = f"{what} ids repeat: {sorted(map(str, repeated))}"
        raise ValueError(msg)


def landslide_flags(
    assets: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str,
) -> pd.DataFrame:
    """Return whether each asset is caught by evacuated or inundated ground.

    An asset is caught where it intersects a polygon of that kind, its
    boundary included. Retaining walls are flagged by :func:`wall_flags`
    instead, which asks for a length of line inside the polygon.

    Args:
        assets: One row per structure, carrying ``id_column``. Any geometry type
            works, lines, polygons and collections alike.
        landslides: The hazard module's polygons, carrying
            :data:`~landloss.hazard.landslide.land_class.LAND_CLASS_COLUMN`.
            Imminent ground
            (:data:`~landloss.hazard.landslide.land_class.IMMINENT`) sets no
            flag.
        id_column: The asset identifier, unique per row.

    Returns:
        One row per asset in the order given, carrying ``id_column`` and the
        boolean :data:`~landloss.domain.loss_contract.IS_EVACUATED_COLUMN` and
        :data:`~landloss.domain.loss_contract.IS_INUNDATED_COLUMN`. An asset no
        landslide reached is present with both flags False.

    Raises:
        ValueError: If the landslides carry no land class, the asset ids repeat,
            or the frames disagree on their coordinate reference system.
    """
    return _geometric_flags(assets, landslides, id_column=id_column, caught=_caught_ids)


def _geometric_flags(
    assets: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str,
    caught: Callable[[gpd.GeoDataFrame, gpd.GeoDataFrame, str, str], pd.Index],
) -> pd.DataFrame:
    """Return the evacuated and inundated flags, with ``caught`` as the test.

    Args:
        assets: As :func:`landslide_flags` takes them.
        landslides: As :func:`landslide_flags` takes them.
        id_column: The asset identifier, unique per row.
        caught: Returns the ids of the assets one land class reaches, given
            ``(assets, landslides, land_class, id_column)``.

    Returns:
        As :func:`landslide_flags` returns.

    Raises:
        ValueError: As :func:`landslide_flags` raises.
    """
    if LAND_CLASS_COLUMN not in landslides.columns:
        msg = f"landslides carry no {LAND_CLASS_COLUMN!r} column"
        raise ValueError(msg)
    _check_unique_ids(assets, id_column, what="asset")
    if not landslides.empty and not assets.empty and assets.crs != landslides.crs:
        msg = f"assets are {assets.crs} and landslides are {landslides.crs}"
        raise ValueError(msg)

    flags = pd.DataFrame({id_column: assets[id_column].to_numpy()})
    for land_class, column in FLAG_COLUMNS.items():
        if assets.empty:
            flags[column] = pd.Series([], dtype=bool)
            continue
        reached = caught(assets, landslides, land_class, id_column)
        flags[column] = flags[id_column].isin(reached).astype(bool)
    return flags


def _nullable(values: pd.Series) -> pd.Series:
    """Return ``values`` as an object Series with every missing entry ``None``.

    The Series is built with an explicit object dtype and a fresh index, so a
    frame assembled from it keeps ``None`` rather than inferring a string
    dtype whose missing value is NaN.
    """
    objects = values.astype(object).where(values.notna(), None)
    return pd.Series(objects.to_numpy(), dtype=object)


def outcome_flags(outcomes: pd.DataFrame, *, id_column: str) -> pd.DataFrame:
    """Return the contract flags each urban wall outcome sets.

    Args:
        outcomes: Landslide step 9's wall outcome table, one row per wall on
            sloping ground, carrying ``id_column``, :data:`SLOPE_ID_COLUMN` and
            :data:`OUTCOME_COLUMN`.
        id_column: The wall identifier, unique per row.

    Returns:
        One row per outcome row in the order given: ``id_column``,
        :data:`SLOPE_ID_COLUMN`, :data:`OUTCOME_COLUMN`, then the three
        boolean :data:`WALL_FLAG_COLUMNS` set by :data:`OUTCOME_FLAGS`. A
        wall whose outcome is
        :data:`~landloss.hazard.landslide.urban.realisation.STANDING` carries
        every flag False, and no outcome sets
        :data:`~landloss.domain.loss_contract.IS_INUNDATED_COLUMN`.

    Raises:
        ValueError: If a required column is missing, the wall ids repeat, or an
            outcome is not one of
            :data:`~landloss.hazard.landslide.urban.realisation.OUTCOMES`.
    """
    missing = [
        column
        for column in (id_column, SLOPE_ID_COLUMN, OUTCOME_COLUMN)
        if column not in outcomes.columns
    ]
    if missing:
        msg = f"the wall outcomes carry no {missing} column(s)"
        raise ValueError(msg)
    _check_unique_ids(outcomes, id_column, what="wall outcome")
    strangers = outcomes.loc[~outcomes[OUTCOME_COLUMN].isin(OUTCOMES), OUTCOME_COLUMN]
    if len(strangers):
        msg = (
            f"unknown wall outcomes {sorted(map(str, strangers.unique()))}; "
            f"expected one of {OUTCOMES}"
        )
        raise ValueError(msg)

    flags = pd.DataFrame(
        {
            id_column: outcomes[id_column].to_numpy(),
            # A wall whose polygon was not delineated has a null slope_id; kept
            # as None rather than NaN whatever dtype the table arrived with.
            SLOPE_ID_COLUMN: _nullable(outcomes[SLOPE_ID_COLUMN]),
            OUTCOME_COLUMN: outcomes[OUTCOME_COLUMN].to_numpy(),
        }
    )
    for column in WALL_FLAG_COLUMNS:
        flags[column] = np.zeros(len(flags), dtype=bool)
    for outcome, column in OUTCOME_FLAGS.items():
        flags.loc[flags[OUTCOME_COLUMN] == outcome, column] = True
    return flags


def wall_flags(
    walls: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    outcomes: pd.DataFrame,
    *,
    id_column: str,
) -> pd.DataFrame:
    """Return the three contract flags per retaining wall.

    The geometric flags are OR-ed with the outcome mapping of
    :func:`outcome_flags`, contract section 5.2: ``is_evacuated`` and
    ``is_inundated`` are set by either route, and ``is_damaged_by_shaking`` by
    the outcome alone (a flat-land wall's shaking flag is the shaking step's,
    set when the loss tables are built). A polygon sets a geometric flag only
    where more than :data:`WALL_INSIDE_TOLERANCE_M` of the wall's line lies
    inside it, so a standing wall that is only the edge of a neighbouring
    failure is not flagged; the frames are otherwise checked as
    :func:`landslide_flags` checks them.

    Args:
        walls: The world's wall population, one row per wall carrying
            ``id_column`` and the line geometry. Flat-land and sloping walls
            alike.
        landslides: The combined realisation, large and urban rows together,
            carrying :data:`~landloss.hazard.landslide.land_class.LAND_CLASS_COLUMN`.
        outcomes: The wall outcome table for the same world and earthquake,
            as :func:`outcome_flags` reads it. Walls with no row (flat-land
            walls) take their flags from geometry alone.
        id_column: The wall identifier, unique per row of ``walls`` and of
            ``outcomes``.

    Returns:
        One row per wall in the order of ``walls``: ``id_column``,
        :data:`SLOPE_ID_COLUMN` and :data:`OUTCOME_COLUMN` (``None`` where the
        wall has no outcome row), then the boolean :data:`WALL_FLAG_COLUMNS`.

    Raises:
        ValueError: If an outcome names a wall not in ``walls``, or on anything
            :func:`landslide_flags` or :func:`outcome_flags` refuses.
    """
    geometric = _geometric_flags(
        walls, landslides, id_column=id_column, caught=_lines_inside_ids
    )
    from_outcome = outcome_flags(outcomes, id_column=id_column)
    strangers = from_outcome.loc[
        ~from_outcome[id_column].isin(geometric[id_column]), id_column
    ]
    if len(strangers):
        msg = (
            f"{len(strangers)} wall outcomes name walls not in the population, "
            f"for example {strangers.iloc[0]!r}"
        )
        raise ValueError(msg)

    by_wall = from_outcome.set_index(id_column)
    ids = geometric[id_column]
    flags = pd.DataFrame(
        {
            id_column: ids.to_numpy(),
            SLOPE_ID_COLUMN: _nullable(ids.map(by_wall[SLOPE_ID_COLUMN])),
            OUTCOME_COLUMN: _nullable(ids.map(by_wall[OUTCOME_COLUMN])),
        }
    )
    for column in WALL_FLAG_COLUMNS:
        set_by_outcome = ids.isin(by_wall.index[by_wall[column]]).to_numpy()
        set_by_geometry = (
            geometric[column].to_numpy()
            if column in geometric.columns
            else np.zeros(len(flags), dtype=bool)
        )
        flags[column] = set_by_outcome | set_by_geometry
    return flags
