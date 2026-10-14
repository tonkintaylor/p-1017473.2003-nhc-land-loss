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
failed through it, or it is still standing. An older run also wrote
``absorbed`` (a larger urban failure took its polygon) and ``superseded`` (a
large-model landslide did); step 6 keeps every failed polygon since
2026-10-14, so a newer run writes neither. :data:`OUTCOME_FLAGS` maps each outcome
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
analogue of the rule that polygons touching only along an edge share no
ground.

A wall's **own** polygon (its outcome's ``slope_id``) never sets the wall's
``is_evacuated`` or ``is_inundated`` flag by geometry (the lead, 2026-10-13).
The wall's line is drawn at the toe of its own face and its evacuated polygon
is cut at the line, so the wall is that polygon's edge and its own deposit runs
on below it; its own failure is the outcome route's (``failed_with_polygon``,
the shaking flag). Polygons of other slopes still flag it.

**How much of a wall is damaged** is measured as well (T-158, the lead,
2026-10-14), because a wall clipped by a neighbour's failure is replaced over
the clipped length, not over its whole length. A wall that fails in shaking is
damaged over its whole line. A wall damaged by landslide ground is damaged only
over the length of its line inside **evacuated** ground; inundated ground
buries a wall without damaging it, and its length is kept for information.
:func:`measure_wall_damage` measures each kind of ground merged first, so
overlapping failures count a stretch once, with the same
:data:`WALL_INSIDE_TOLERANCE_M` as the flag, and over every failure other than
the wall's own polygon.

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
# whose polygon failed through it is written off by the shaking, over its whole
# length. A standing wall sets none, and no outcome sets the inundated flag:
# that comes from geometry alone. The vocabulary is landslide step 6's
# (``landloss.hazard.landslide.urban.realisation.OUTCOMES``). ``absorbed`` and
# ``superseded`` come only from a run before step 6 kept every failed polygon
# (the lead, 2026-10-14). Their polygon had failed too, its ground merely
# credited to a larger failure, so they set the shaking flag as well; flagged
# evacuated, they were measured against the larger failure's ground, which
# rarely reaches the wall's line.
OUTCOME_FLAGS = {
    FAILED_WITH_POLYGON: IS_DAMAGED_BY_SHAKING_COLUMN,
    ABSORBED: IS_DAMAGED_BY_SHAKING_COLUMN,
    SUPERSEDED: IS_DAMAGED_BY_SHAKING_COLUMN,
}

# What :func:`measure_wall_damage` writes beside the flags. The lengths are in
# metres; the damaged line is the stretch of the wall that is damaged (empty
# where none is), for vul step 10 to place on each claim's insured stretch.
EVACUATED_LENGTH_COLUMN = "evacuated_length_m"
INUNDATED_LENGTH_COLUMN = "inundated_length_m"
DAMAGED_LENGTH_COLUMN = "damaged_length_m"
DAMAGED_LINE_COLUMN = "damaged_line"
WALL_DAMAGE_COLUMNS = (
    EVACUATED_LENGTH_COLUMN,
    INUNDATED_LENGTH_COLUMN,
    DAMAGED_LENGTH_COLUMN,
    DAMAGED_LINE_COLUMN,
)

# The three contract flags a wall carries, in output order.
WALL_FLAG_COLUMNS = (
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
)

# How far inside a landslide polygon a wall's line must lie, and for how long,
# for the polygon to reach the wall, in m. A numerical tolerance, not a
# parameter: a hundredth of a 1 m DEM cell side, so a line along a polygon's
# edge, or within floating-point noise of it, is not inside the polygon.
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


def _same_slope(polygon_slope: np.ndarray, wall_slope: np.ndarray) -> np.ndarray:
    """Return where a landslide's polygon is the wall's own, pair by pair.

    A large-model landslide has no ``slope_id`` and a wall with no outcome has
    no own polygon. The realisation holds ``slope_id`` as a string column, so a
    missing one is pandas' NA, which cannot be compared to give a bool; only
    ids present on both sides are compared, and a missing one is never own.
    """
    polygon_slope = np.asarray(polygon_slope, dtype=object)
    wall_slope = np.asarray(wall_slope, dtype=object)
    known = pd.notna(polygon_slope) & pd.notna(wall_slope)
    same = np.zeros(len(polygon_slope), dtype=bool)
    same[known] = (polygon_slope[known] == wall_slope[known]).astype(bool)
    return same


def _lines_inside_ids(
    walls: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    land_class: str,
    id_column: str,
    own: pd.Series | None = None,
) -> pd.Index:
    """Return the ids of the walls whose line lies inside a landslide of one kind.

    A wall is caught where more than :data:`WALL_INSIDE_TOLERANCE_M` of its
    line lies inside some polygon shrunk by :data:`WALL_INSIDE_TOLERANCE_M`, so
    a line that only runs along the polygon's boundary, or touches it at a
    point, is not. With ``own`` (each wall's own ``slope_id``, by wall id), a
    polygon of the wall's own slope does not catch it; landslides with no
    :data:`SLOPE_ID_COLUMN` have no own polygon.
    """
    slides = landslides[landslides[LAND_CLASS_COLUMN] == land_class]
    if slides.empty:
        return pd.Index([])
    shrunk = slides.geometry.buffer(-WALL_INSIDE_TOLERANCE_M)
    keep = ~shrunk.is_empty
    slope_ids = (
        slides[SLOPE_ID_COLUMN].to_numpy()[keep.to_numpy()]
        if SLOPE_ID_COLUMN in slides.columns
        else np.full(int(keep.sum()), None, dtype=object)
    )
    interiors = gpd.GeoDataFrame(
        {SLOPE_ID_COLUMN: slope_ids}, geometry=shrunk[keep].to_numpy(), crs=slides.crs
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
    if own is not None:
        polygon_slope = joined[SLOPE_ID_COLUMN].to_numpy()
        wall_slope = joined[id_column].map(own).to_numpy()
        reached &= ~_same_slope(polygon_slope, wall_slope)
    return pd.Index(joined.loc[reached, id_column].unique())


def _inside_lines(
    walls: gpd.GeoDataFrame,
    landslides: gpd.GeoDataFrame,
    land_class: str,
    own: np.ndarray,
) -> list:
    """Return each wall's line inside one kind of other failures' merged ground.

    The polygons of the kind that touch a wall, bar the wall's own polygon, are
    merged, then shrunk by :data:`WALL_INSIDE_TOLERANCE_M`, so a line along the
    edge of the ground is not inside it and ground that overlaps is counted
    once. A line with no more than the tolerance inside is not inside, as the
    flag has it.

    Args:
        walls: The walls to measure, one per row, in line geometry.
        landslides: The combined realisation, carrying
            :data:`~landloss.hazard.landslide.land_class.LAND_CLASS_COLUMN`.
        land_class: The kind of ground to measure inside.
        own: Each wall's own ``slope_id``, in the order of ``walls``, ``None``
            where it has no polygon.

    Returns:
        One entry per wall in order: the line inside the ground as a (multi)
        line, or an empty line where none is.
    """
    lines = walls.geometry.to_numpy()
    inside = np.full(len(lines), None, dtype=object)
    inside[:] = [shapely.LineString() for _ in lines]
    slides = landslides[landslides[LAND_CLASS_COLUMN] == land_class]
    if slides.empty or len(lines) == 0:
        return list(inside)
    ground = slides.geometry.to_numpy()
    slope_ids = (
        slides[SLOPE_ID_COLUMN].to_numpy(dtype=object)
        if SLOPE_ID_COLUMN in slides.columns
        else np.full(len(slides), None, dtype=object)
    )
    wall_at, slide_at = shapely.STRtree(ground).query(lines, predicate="intersects")
    own_slope = np.asarray(own, dtype=object)
    is_own = _same_slope(slope_ids[slide_at], own_slope[wall_at])
    wall_at, slide_at = wall_at[~is_own], slide_at[~is_own]
    for wall in np.unique(wall_at):
        merged = shapely.union_all(ground[slide_at[wall_at == wall]])
        shrunk = shapely.buffer(merged, -WALL_INSIDE_TOLERANCE_M)
        parts = shapely.get_parts(shapely.intersection(lines[wall], shrunk))
        parts = parts[shapely.get_type_id(parts) == 1]
        if shapely.length(parts).sum() > WALL_INSIDE_TOLERANCE_M:
            inside[wall] = shapely.line_merge(shapely.multilinestrings(parts))
    return list(inside)


def measure_wall_damage(
    walls: gpd.GeoDataFrame,
    flags: pd.DataFrame,
    landslides: gpd.GeoDataFrame,
    *,
    id_column: str,
) -> pd.DataFrame:
    """Return how much of each wall's line a landslide damages.

    A wall damaged by shaking (``is_damaged_by_shaking`` in ``flags``, the
    urban outcome's) is damaged over its whole line. A wall carrying
    ``is_evacuated`` or ``is_inundated`` and not that is measured: the length
    of its line inside the evacuated ground and inside the inundated ground of
    every failure other than its own polygon, each kind merged first
    (:func:`_inside_lines`). Its **damaged** line is the part inside evacuated
    ground alone, because inundated ground does not damage a wall. A wall that
    is only inundated has an empty damaged line and length 0. A wall carrying
    no flag is not measured.

    A wall damaged by shaking in the later shaking step (a flat-land wall) is
    not known here; vul step 10 takes its whole length.

    Args:
        walls: The world's wall population, carrying ``id_column`` and the line
            geometry.
        flags: :func:`wall_flags`' flags, one row per wall in the order of
            ``walls``, carrying :data:`SLOPE_ID_COLUMN`.
        landslides: The combined realisation, as :func:`wall_flags` takes it.
        id_column: The wall identifier.

    Returns:
        One row per wall in the order of ``walls``: ``id_column``, then
        :data:`EVACUATED_LENGTH_COLUMN` and :data:`INUNDATED_LENGTH_COLUMN`
        (information only; 0 for a wall not measured),
        :data:`DAMAGED_LENGTH_COLUMN` (the evacuated length, or the whole line
        for a shaking-damaged wall) and :data:`DAMAGED_LINE_COLUMN` (the line
        that length is of, empty where none).
    """
    lines = walls.geometry.to_numpy()
    shaken = flags[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy(dtype=bool)
    caught = (
        flags[IS_EVACUATED_COLUMN].to_numpy(dtype=bool)
        | flags[IS_INUNDATED_COLUMN].to_numpy(dtype=bool)
    ) & ~shaken
    measured = walls[caught]
    own = flags[SLOPE_ID_COLUMN].to_numpy(dtype=object)[caught]

    def measure(land_class: str) -> np.ndarray:
        found = np.full(len(walls), None, dtype=object)
        found[:] = [shapely.LineString() for _ in lines]
        found[caught] = _inside_lines(measured, landslides, land_class, own)
        return found

    evacuated = measure(EVACUATED)
    inundated = measure(INUNDATED)
    damaged_line = np.where(shaken, lines, evacuated)
    return pd.DataFrame(
        {
            id_column: walls[id_column].to_numpy(),
            EVACUATED_LENGTH_COLUMN: shapely.length(evacuated),
            INUNDATED_LENGTH_COLUMN: shapely.length(inundated),
            DAMAGED_LENGTH_COLUMN: shapely.length(damaged_line),
            DAMAGED_LINE_COLUMN: pd.Series(damaged_line, dtype=object),
        }
    )


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
        outcomes: Landslide step 6's wall outcome table, one row per wall on
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
    failure is not flagged, and the wall's own polygon (its outcome's
    ``slope_id``) sets neither geometric flag (see the module docstring); the
    frames are otherwise checked as :func:`landslide_flags` checks them.

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
        wall has no outcome row), then the boolean :data:`WALL_FLAG_COLUMNS`,
        then the damaged lengths and line of :func:`measure_wall_damage`
        (:data:`WALL_DAMAGE_COLUMNS`).

    Raises:
        ValueError: If an outcome names a wall not in ``walls``, or on anything
            :func:`landslide_flags` or :func:`outcome_flags` refuses.
    """
    from_outcome = outcome_flags(outcomes, id_column=id_column)
    own = from_outcome.set_index(id_column)[SLOPE_ID_COLUMN]

    def caught(
        assets: gpd.GeoDataFrame,
        slides: gpd.GeoDataFrame,
        land_class: str,
        ids: str,
    ) -> pd.Index:
        """The walls a land class reaches, a wall's own polygon not counting."""
        return _lines_inside_ids(assets, slides, land_class, ids, own=own)

    geometric = _geometric_flags(walls, landslides, id_column=id_column, caught=caught)
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
    damage = measure_wall_damage(walls, flags, landslides, id_column=id_column)
    return flags.merge(damage, on=id_column, how="left", validate="one_to_one")
