"""One realisation of the urban slope failure model.

What belongs here: sampling PGV at each polygon's representative point, the
failure draw against each polygon's fragility, resolving overlaps among the
failed polygons (absorption), supersession by the large model's evacuated
polygons, the rows the surviving failures write beside the large model's, and
the wall outcome table. Used by landslide step 9
(``s9_urban_slope_realisation``); contract sections 5 and 7.11 of
``.agents/plans/urban-slope-build-contract.md``.

The draw is one uniform per polygon of the model file, in the file's own order
(sorted by ``slope_id``, contract section 3.8), on the ``"urban"`` stream of the
earthquake seeded on the exposure world as well:
``realisation_seed(BASE_SEED, realisation_id, URBAN_STREAM, world_id=world_id)``.
A fragility is a probability of failure at a level of shaking, so the draw is
what decides whether the polygon fails; two worlds of the same earthquake draw
different uniforms because their wall populations, and so their fragilities,
differ.

A wall line sits on the edges of polygons at several scales, and each of them
carries the same published wall curve. So every polygon with a wall takes the
uniform of the first polygon in model order sharing a wall line with it (a
common random number, contract decision 34), and **if any polygon on a wall
fails, the wall has failed and every polygon on it fails** (the project lead's
rule, 2026-10-02). The polygons on one wall differ only in the amplification
their median is divided by, so with one uniform the wall fails exactly when its
weakest polygon does: it reads the strongest amplification along it, and the
largest of its failed polygons then survives the overlap resolution below. A
polygon's edge can carry several lines that drew a wall (``wall_line_ids``: one
wall split at property boundaries), so polygons are grouped by any line they
share, transitively. Polygons without a wall keep their own uniform and fail
on their own.

Three things can happen to a polygon that failed. It can survive and write its
fixed geometry; it can be **superseded** by a large-model landslide whose
evacuated polygon shares ground with its own, in which case its ground counts
once, in the large polygon; or it can be **absorbed** by a larger surviving
urban failure whose evacuated polygon shares ground with its own, resolved
largest first exactly as the large model's ``drop_overlapping`` does. A polygon
that did not fail is standing whatever a large landslide does around it
(contract decision 35): a wall the large landslide actually reaches is flagged
by vul step 11's intersection of the wall line with the combined realisation's
``evacuated land``. Supersession is tested first, on the failed polygons;
absorption is then resolved only among the failed polygons that were not
superseded, so every absorber is a survivor written to the combined realisation
and an absorbed polygon's ground is never lost with a superseded absorber.

Two polygons **share ground** where their intersection has an area above
:data:`SHARED_GROUND_TOLERANCE_M2`. Polygons that only touch along an edge or
at a corner do not: the candidates tile the domain at each scale, so
neighbouring failures always touch, and touching is neither nesting nor lying
inside a large landslide.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import shapely
from shapely import STRtree

from landloss.common.utils.terrain import sample_at_points
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    IMMINENT,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from landloss.hazard.landslide.urban.fragility import lognormal_failure_probability
from landloss.hazard.landslide.urban.geometry import NO_WALL, edge_line_ids

# The random stream the urban draw comes from: one name for the hazard, seeded
# on the earthquake and the exposure world together.
URBAN_STREAM = "urban"

# The two landslide populations the combined realisation carries.
POPULATION_COLUMN = "population"
LARGE = "large"
URBAN = "urban"
POPULATIONS = (LARGE, URBAN)

# What happened to a wall on sloping land: the vocabulary of contract section
# 5.1, in the order the contract lists it. A wall with polygons at several
# scales resolves to one outcome by OUTCOME_RANK below, not by this order.
STANDING = "standing"
FAILED_WITH_POLYGON = "failed_with_polygon"
ABSORBED = "absorbed"
SUPERSEDED = "superseded"
OUTCOMES = (STANDING, FAILED_WITH_POLYGON, ABSORBED, SUPERSEDED)
# The precedence a wall on polygons at several scales resolves by, lowest rank
# wins: superseded, then failed with its polygon, then absorbed, then standing
# (see :func:`wall_outcomes`; contract section 3.10).
OUTCOME_RANK = {SUPERSEDED: 0, FAILED_WITH_POLYGON: 1, ABSORBED: 2, STANDING: 3}

# No absorber and no superseder, in the position arrays the resolvers return.
NONE = -1

# The intersection area above which two polygons share ground, in m2. A
# numerical tolerance, not a parameter for the anchoring to set: a hundredth of
# the finest 1 m candidate cell (constants.URBAN_SCALES_M), so the floating-point
# slivers left along an edge two polygons share do not count as shared ground.
SHARED_GROUND_TOLERANCE_M2 = 0.01

# The model file columns this module reads (contract section 3.8).
SLOPE_ID_COLUMN = "slope_id"
RW_ID_COLUMN = "rw_id"
WALL_LINE_ID_COLUMN = "wall_line_id"
WALL_LINE_IDS_COLUMN = "wall_line_ids"
CLAIM_ID_COLUMN = "claim_id"
WALL_STATE_COLUMN = "wall_state"
THETA_COLUMN = "theta"
BETA_COLUMN = "beta"
REP_POINT_COLUMN = "rep_point"
EVACUATED_GEOMETRY_COLUMN = "evacuated"
INUNDATED_GEOMETRY_COLUMN = "inundated"
IMMINENT_GEOMETRY_COLUMN = "imminent"
DEPTH_EVACUATED_COLUMN = "depth_evacuated_m"
DEPTH_INUNDATED_COLUMN = "depth_inundated_m"
IS_FLATLAND_COLUMN = "is_flatland"

# The draw columns, on the model's index.
PGV_COLUMN = "pgv_m_s"
P_FAIL_COLUMN = "p_fail"
UNIFORM_COLUMN = "uniform"
FAILED_COLUMN = "failed"

# The combined realisation columns (contract section 3.10), in order. The
# large rows keep every column step 1 wrote after these.
LANDSLIDE_ID_COLUMN = "landslide_id"
UNIT_ID_COLUMN = "unit_id"
DEPTH_COLUMN = "depth_m"
VOLUME_COLUMN = "volume_m3"
SOURCE_AREA_COLUMN = "source_area_m2"
REALISATION_ID_COLUMN = "realisation_id"
WORLD_ID_COLUMN = "world_id"
COMBINED_COLUMNS = (
    REALISATION_ID_COLUMN,
    WORLD_ID_COLUMN,
    LANDSLIDE_ID_COLUMN,
    POPULATION_COLUMN,
    SLOPE_ID_COLUMN,
    UNIT_ID_COLUMN,
    LAND_CLASS_COLUMN,
    DEPTH_COLUMN,
    VOLUME_COLUMN,
    SOURCE_AREA_COLUMN,
    WALL_STATE_COLUMN,
    RW_ID_COLUMN,
    PGV_COLUMN,
    P_FAIL_COLUMN,
    UNIFORM_COLUMN,
    "geometry",
)

# The wall outcome columns (contract section 3.10) that this module writes; the
# step inserts ``world_id`` and ``realisation_id`` before them.
OUTCOME_COLUMN = "outcome"
TAKEN_BY_COLUMN = "taken_by"
OUTCOME_COLUMNS = (
    RW_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    CLAIM_ID_COLUMN,
    SLOPE_ID_COLUMN,
    OUTCOME_COLUMN,
    TAKEN_BY_COLUMN,
)

# The land class each state geometry column writes, with the depth column it
# carries (``None`` for imminent ground, whose depth is NaN).
_STATE_ROWS = (
    (EVACUATED, EVACUATED_GEOMETRY_COLUMN, DEPTH_EVACUATED_COLUMN),
    (INUNDATED, INUNDATED_GEOMETRY_COLUMN, DEPTH_INUNDATED_COLUMN),
    (IMMINENT, IMMINENT_GEOMETRY_COLUMN, None),
)


def _check_projected(frame: gpd.GeoDataFrame | gpd.GeoSeries, role: str) -> None:
    """Refuse a geographic frame: every area and intersection here is in metres."""
    if frame.crs is None or frame.crs.is_geographic:
        msg = f"{role} must be in a projected CRS, got {frame.crs}"
        raise ValueError(msg)


def _shared_area(
    geometry: object, others: npt.NDArray[np.object_]
) -> npt.NDArray[np.floating]:
    """Return the area ``geometry`` shares with each of ``others``, in m2."""
    return shapely.area(shapely.intersection(geometry, others))


def sample_pgv(points: gpd.GeoSeries, pgv_path: Path) -> pd.Series:
    """Read the earthquake's PGV at each polygon's representative point.

    Args:
        points: The representative points, one per polygon of the model file.
        pgv_path: The PGV raster shaking step 5 wrote for the earthquake, in
            m/s.

    Returns:
        PGV in m/s on ``points.index``, NaN off the grid.
    """
    return sample_at_points(pgv_path, points).rename(PGV_COLUMN)


def _row_lines(model: gpd.GeoDataFrame, *, walled_only: bool) -> list[tuple[str, ...]]:
    """Return the wall lines of each model row.

    A row's lines are its ``wall_line_ids`` (every line on its edge that drew a
    wall), with its own ``wall_line_id`` first where that list leaves it out,
    so a hand-built row naming one line is read as that line. With
    ``walled_only`` a ``no_wall`` row has none.
    """
    states = model[WALL_STATE_COLUMN].to_numpy(dtype=object)
    own = model[WALL_LINE_ID_COLUMN].to_numpy(dtype=object)
    cells = model[WALL_LINE_IDS_COLUMN].to_numpy(dtype=object)
    out: list[tuple[str, ...]] = []
    for state, line, cell in zip(states, own, cells, strict=True):
        if walled_only and state == NO_WALL:
            out.append(())
            continue
        lines = list(edge_line_ids(cell))
        if line is not None and not pd.isna(line) and line not in lines:
            lines.insert(0, str(line))
        out.append(tuple(lines))
    return out


def _wall_groups(model: gpd.GeoDataFrame) -> list[str | None]:
    """Return the wall group of each row, or None for a row without a wall.

    Rows are grouped by the wall lines they carry, transitively: two rows
    sharing any line are one group, named by a root line. A ``no_wall`` row,
    or a walled row naming no line, has no group.
    """
    lines_of = _row_lines(model, walled_only=True)
    parent: dict[str, str] = {}

    def root(line: str) -> str:
        while parent[line] != line:
            parent[line] = parent[parent[line]]
            line = parent[line]
        return line

    for lines in lines_of:
        for line in lines:
            parent.setdefault(line, line)
        for line in lines[1:]:
            parent[root(line)] = root(lines[0])

    return [root(lines[0]) if lines else None for lines in lines_of]


def _share_uniform_per_wall_line(
    groups: list[str | None], uniform: npt.NDArray[np.floating]
) -> npt.NDArray[np.floating]:
    """Give every walled row the uniform of the first row in its wall group.

    Args:
        groups: Each row's wall group from :func:`_wall_groups`, None for a
            row without a wall.
        uniform: One uniform per row, in model order.

    Returns:
        The uniforms, with every walled row reading its group's first.
    """
    shared = uniform.copy()
    first_of_group: dict[str, int] = {}
    for position, group in enumerate(groups):
        if group is None:
            continue
        first = first_of_group.setdefault(group, position)
        shared[position] = uniform[first]
    return shared


def _fail_with_the_wall(
    groups: list[str | None], failed: npt.NDArray[np.bool_]
) -> npt.NDArray[np.bool_]:
    """Fail every row of a wall group in which any row failed.

    A polygon with a wall fails with the wall and only with it, so once any
    polygon on a wall has failed the wall has failed, and every polygon it
    holds up fails with it. Rows without a wall are left as drawn.

    Args:
        groups: Each row's wall group from :func:`_wall_groups`.
        failed: Whether each row failed on its own fragility.

    Returns:
        ``failed``, with every row of a group that failed anywhere set true.
    """
    failed_groups = {
        group
        for group, row_failed in zip(groups, failed, strict=True)
        if group is not None and row_failed
    }
    out = failed.copy()
    for position, group in enumerate(groups):
        if group is not None and group in failed_groups:
            out[position] = True
    return out


def draw_failures(
    model: gpd.GeoDataFrame, pgv_m_s: pd.Series, rng: np.random.Generator
) -> pd.DataFrame:
    """Draw which polygons fail, one uniform per wall line or wall-less row.

    Each row's fragility is the lognormal of contract section 6 on its own
    ``theta`` and ``beta``, evaluated by
    :func:`landloss.hazard.landslide.urban.fragility.lognormal_failure_probability`
    (a PGV at or below zero gives 0, a NaN PGV off the grid gives NaN so the
    row is visibly undrawn rather than silently standing); a fragility is a
    probability of failure at a level of shaking, and the uniform drawn
    against it is what decides whether the polygon fails. One uniform is drawn
    per row for the whole frame in row order, so a polygon's uniform is tied to
    its position in the model file, which is sorted by ``slope_id``.

    Then every row whose ``wall_state`` is not ``no_wall`` takes the uniform
    of the first row in model order sharing a wall line with it (contract
    decision 34), read from ``wall_line_ids`` (every line on the row's edge
    that drew a wall) and grouped transitively. A wall line sits on polygons
    at several scales, each with the same wall curve, so with a uniform each
    the wall would fail through some polygon far more often than the
    published curve says; with one shared uniform the wall's polygons fail
    together where their curves agree, and :func:`resolve_overlaps` keeps the
    largest. The key is the line, not ``rw_id``, because an uninsured wall has
    no ``rw_id`` and is still one wall. Rows without a wall, or with no line,
    keep their own uniform.

    Last, if any row of a wall group failed, every row of the group fails: the
    wall has failed, and it takes all the ground it holds up with it (the
    project lead's rule, 2026-10-02). With one uniform per group this means
    the wall fails where its weakest polygon, the one with the strongest
    amplification, would. ``p_fail`` and ``uniform`` stay each row's own, so a
    row failed through its wall can carry a uniform above its ``p_fail``.

    Args:
        model: The world's model file (contract section 3.8), carrying
            ``wall_state``, ``wall_line_id`` and ``wall_line_ids``.
        pgv_m_s: PGV at each row's representative point, on ``model.index``.
        rng: The urban stream of the earthquake and world.

    Returns:
        A frame on ``model.index`` with ``pgv_m_s``, ``p_fail``, ``uniform``
        and ``failed``. ``failed`` is false where ``p_fail`` is NaN.
    """
    pgv = pgv_m_s.reindex(model.index).to_numpy(dtype=float)
    p_fail = lognormal_failure_probability(
        pgv,
        model[THETA_COLUMN].to_numpy(dtype=float),
        model[BETA_COLUMN].to_numpy(dtype=float),
    )
    groups = _wall_groups(model)
    uniform = _share_uniform_per_wall_line(groups, rng.random(len(model)))
    with np.errstate(invalid="ignore"):
        failed = uniform < p_fail
    failed = _fail_with_the_wall(groups, failed)
    return pd.DataFrame(
        {
            PGV_COLUMN: pgv,
            P_FAIL_COLUMN: p_fail,
            UNIFORM_COLUMN: uniform,
            FAILED_COLUMN: failed,
        },
        index=model.index,
    )


def resolve_overlaps(
    polygons: gpd.GeoSeries, areas: npt.NDArray[np.floating]
) -> npt.NDArray[np.int64]:
    """Absorb each failed polygon into the largest failed polygon sharing its ground.

    ``s1_simulate_landslides.drop_overlapping`` generalised: worked largest
    first, stable on ties, and a polygon that has been absorbed absorbs
    nothing, so one large failure cannot clear a hole wider than itself
    through a chain of failures none of which happened. Two polygons that only
    touch along an edge or at a corner share no ground and neither absorbs the
    other (see :data:`SHARED_GROUND_TOLERANCE_M2`). Run on the evacuated
    geometry of the failed polygons that no large-model landslide superseded,
    so every absorber is a survivor.

    Args:
        polygons: The evacuated geometry of the failed, unsuperseded polygons.
        areas: The area ranking the polygons by, one per polygon.

    Returns:
        For each polygon, the position in ``polygons`` of the one that absorbed
        it, or :data:`NONE` where it survived.
    """
    areas = np.asarray(areas, dtype=float)
    if len(polygons) != areas.size:
        msg = f"{len(polygons)} polygons against {areas.size} areas"
        raise ValueError(msg)
    absorbed_by = np.full(areas.size, NONE, dtype=np.int64)
    if areas.size == 0:
        return absorbed_by
    _check_projected(polygons, "polygons")

    geometries = polygons.to_numpy()
    tree = STRtree(geometries)
    for index in np.argsort(-areas, kind="stable"):
        if absorbed_by[index] != NONE:
            continue
        candidates = tree.query(geometries[index], predicate="intersects")
        candidates = candidates[
            (candidates != index) & (absorbed_by[candidates] == NONE)
        ]
        if candidates.size == 0:
            continue
        shared = _shared_area(geometries[index], geometries[candidates])
        absorbed_by[candidates[shared > SHARED_GROUND_TOLERANCE_M2]] = index
    return absorbed_by


def supersede_by_large(
    evacuated: gpd.GeoSeries, large_evacuated: gpd.GeoSeries
) -> npt.NDArray[np.int64]:
    """Find the large-model evacuated polygon that takes each failed urban polygon.

    A failed urban polygon whose evacuated polygon shares ground with a
    large-model evacuated polygon is superseded: its ground counts once, in the
    large polygon. Only failed polygons are passed in (contract decision 35);
    the caller maps the result onto every model row, :data:`NONE` where the row
    did not fail. One that only touches a large polygon along an edge or at a
    corner shares no ground and is not superseded (see
    :data:`SHARED_GROUND_TOLERANCE_M2`). Where several large polygons share
    ground with it, the one sharing the most takes it, ties to the earlier
    row.

    Args:
        evacuated: The evacuated geometry of the failed urban polygons.
        large_evacuated: The ``evacuated land`` rows of the large-model
            realisation.

    Returns:
        For each urban polygon, the position in ``large_evacuated`` of the
        polygon that supersedes it, or :data:`NONE`.
    """
    superseded_by = np.full(len(evacuated), NONE, dtype=np.int64)
    if len(evacuated) == 0 or len(large_evacuated) == 0:
        return superseded_by
    _check_projected(evacuated, "evacuated")
    _check_projected(large_evacuated, "large_evacuated")

    urban = evacuated.to_numpy()
    large = large_evacuated.to_numpy()
    tree = STRtree(large)
    urban_positions, large_positions = tree.query(urban, predicate="intersects")
    if urban_positions.size == 0:
        return superseded_by

    shared = shapely.area(
        shapely.intersection(urban[urban_positions], large[large_positions])
    )
    # Pairs that only touch share no ground and supersede nothing.
    sharing = shared > SHARED_GROUND_TOLERANCE_M2
    urban_positions = urban_positions[sharing]
    large_positions = large_positions[sharing]
    shared = shared[sharing]
    # Largest shared ground first, ties to the earlier large row; the first
    # entry seen per urban polygon wins.
    order = np.lexsort((large_positions, -shared))
    for pair in order:
        u = urban_positions[pair]
        if superseded_by[u] == NONE:
            superseded_by[u] = large_positions[pair]
    return superseded_by


def _polygon_outcomes(
    model: gpd.GeoDataFrame,
    draws: pd.DataFrame,
    absorbed_by: npt.NDArray[np.int64],
    superseded_by: npt.NDArray[np.int64],
    large_ids: pd.Series,
) -> pd.DataFrame:
    """Name what happened to each model polygon, with who took it.

    Only a failed polygon can be absorbed or superseded (contract decision 35),
    so a position set on a row that did not fail is ignored and that polygon is
    ``standing``.
    """
    slope_ids = model[SLOPE_ID_COLUMN].to_numpy(dtype=object)
    failed = draws[FAILED_COLUMN].reindex(model.index).to_numpy(dtype=bool)
    outcome = np.full(len(model), STANDING, dtype=object)
    taken_by = np.full(len(model), None, dtype=object)

    outcome[failed] = FAILED_WITH_POLYGON

    absorbed = failed & (absorbed_by != NONE)
    outcome[absorbed] = ABSORBED
    taken_by[absorbed] = slope_ids[absorbed_by[absorbed]]

    superseded = failed & (superseded_by != NONE)
    outcome[superseded] = SUPERSEDED
    taken_by[superseded] = large_ids.to_numpy(dtype=object)[superseded_by[superseded]]

    return pd.DataFrame(
        {
            WALL_LINE_IDS_COLUMN: _row_lines(model, walled_only=False),
            SLOPE_ID_COLUMN: slope_ids,
            OUTCOME_COLUMN: outcome,
            TAKEN_BY_COLUMN: taken_by,
        }
    )


def wall_outcomes(
    model: gpd.GeoDataFrame,
    walls: gpd.GeoDataFrame,
    draws: pd.DataFrame,
    absorbed_by: npt.NDArray[np.int64],
    superseded_by: npt.NDArray[np.int64],
    large_ids: pd.Series,
) -> pd.DataFrame:
    """Write what happened to every wall of the world on sloping land.

    Spined on the wall population filtered to ``is_flatland`` false and
    left-joined on ``wall_line_id`` to every model row carrying the wall's
    line among its ``wall_line_ids`` (the lines on its edge that drew a wall),
    so a wall split at a property boundary into several lines on one polygon
    edge takes that polygon's outcome on every line. ``rw_id``, ``claim_id``
    and ``wall_line_id`` come from the population, and a wall whose line is on
    no model row still has a row: ``standing`` with ``slope_id`` null.
    A wall whose polygon failed and shares ground with a large-model evacuated
    polygon is ``superseded``; whose polygon failed and survived is
    ``failed_with_polygon``; whose polygon failed but was absorbed by a larger
    surviving urban failure is ``absorbed``; otherwise ``standing``, whatever a
    large landslide does around a polygon that did not fail (contract decision
    35; vul step 11 flags a wall whose line a large landslide reaches). Where a
    wall's line sits on polygons at several scales the outcomes rank in that
    order, ``superseded`` first, and the row that reached it supplies
    ``slope_id`` and ``taken_by``; ties keep the model's order.

    Args:
        model: The world's model file, in its own order, carrying
            ``wall_line_ids``.
        walls: The world's wall population, carrying ``rw_id``,
            ``wall_line_id``, ``claim_id`` and ``is_flatland``.
        draws: :func:`draw_failures` on ``model``.
        absorbed_by: :func:`resolve_overlaps` mapped onto every model row,
            :data:`NONE` where the row did not fail, was superseded, or
            survived.
        superseded_by: :func:`supersede_by_large` on the failed rows, mapped
            onto every model row, :data:`NONE` where the row did not fail or
            no large polygon took it.
        large_ids: The ``landslide_id`` of each large evacuated polygon, in
            the order ``superseded_by`` indexes.

    Returns:
        One row per sloping-land wall with the columns of
        :data:`OUTCOME_COLUMNS`, in the population's order.
    """
    sloping = walls.loc[~walls[IS_FLATLAND_COLUMN].to_numpy(dtype=bool)]
    spine = pd.DataFrame(
        {
            RW_ID_COLUMN: sloping[RW_ID_COLUMN].to_numpy(dtype=object),
            WALL_LINE_ID_COLUMN: sloping[WALL_LINE_ID_COLUMN].to_numpy(dtype=object),
            CLAIM_ID_COLUMN: sloping[CLAIM_ID_COLUMN].to_numpy(dtype=object),
        }
    )

    per_polygon = _polygon_outcomes(model, draws, absorbed_by, superseded_by, large_ids)
    per_line = (
        per_polygon.explode(WALL_LINE_IDS_COLUMN)
        .rename(columns={WALL_LINE_IDS_COLUMN: WALL_LINE_ID_COLUMN})
        .dropna(subset=[WALL_LINE_ID_COLUMN])
    )
    per_line = per_line.assign(_rank=per_line[OUTCOME_COLUMN].map(OUTCOME_RANK))
    per_wall = (
        per_line.sort_values("_rank", kind="mergesort")
        .drop_duplicates(WALL_LINE_ID_COLUMN, keep="first")
        .drop(columns="_rank")
    )

    outcomes = spine.merge(
        per_wall, on=WALL_LINE_ID_COLUMN, how="left", validate="many_to_one"
    )
    outcomes[OUTCOME_COLUMN] = outcomes[OUTCOME_COLUMN].fillna(STANDING)
    for column in (SLOPE_ID_COLUMN, TAKEN_BY_COLUMN):
        outcomes[column] = (
            outcomes[column].astype(object).where(outcomes[column].notna(), None)
        )
    return outcomes[list(OUTCOME_COLUMNS)].reset_index(drop=True)


def to_landslide_rows(
    model: gpd.GeoDataFrame, draws: pd.DataFrame, survivors: npt.NDArray[np.bool_]
) -> gpd.GeoDataFrame:
    """Write the fixed geometry of the surviving failures as landslide rows.

    Three rows per survivor, one per land class: the evacuated polygon at its
    evacuated depth, the inundated polygon at its inundated depth, and the
    imminent polygon with no depth. ``landslide_id`` is the ``slope_id``;
    ``volume_m3`` is the evacuated depth times the evacuated area, and
    ``source_area_m2`` the evacuated area. A state geometry that is missing or
    empty writes no row.

    Args:
        model: The world's model file.
        draws: :func:`draw_failures` on ``model``.
        survivors: One flag per model row, true where the failure survived
            absorption and supersession.

    Returns:
        The urban rows with the columns of :data:`COMBINED_COLUMNS` less the
        two ids, in the model's order then by land class.
    """
    survivors = np.asarray(survivors, dtype=bool)
    if survivors.size != len(model):
        msg = f"{survivors.size} survivor flags against {len(model)} model rows"
        raise ValueError(msg)
    kept = model.loc[survivors]
    kept_draws = draws.loc[kept.index]
    evacuated_area = gpd.GeoSeries(kept[EVACUATED_GEOMETRY_COLUMN]).area.to_numpy(
        dtype=float
    )
    depth_evacuated = kept[DEPTH_EVACUATED_COLUMN].to_numpy(dtype=float)

    pieces = []
    for land_class, geometry_column, depth_column in _STATE_ROWS:
        depth = (
            np.full(len(kept), np.nan)
            if depth_column is None
            else kept[depth_column].to_numpy(dtype=float)
        )
        rows = gpd.GeoDataFrame(
            {
                LANDSLIDE_ID_COLUMN: kept[SLOPE_ID_COLUMN].to_numpy(dtype=object),
                POPULATION_COLUMN: URBAN,
                SLOPE_ID_COLUMN: kept[SLOPE_ID_COLUMN].to_numpy(dtype=object),
                UNIT_ID_COLUMN: None,
                LAND_CLASS_COLUMN: land_class,
                DEPTH_COLUMN: depth,
                VOLUME_COLUMN: depth_evacuated * evacuated_area,
                SOURCE_AREA_COLUMN: evacuated_area,
                WALL_STATE_COLUMN: kept[WALL_STATE_COLUMN].to_numpy(dtype=object),
                RW_ID_COLUMN: kept[RW_ID_COLUMN].to_numpy(dtype=object),
                PGV_COLUMN: kept_draws[PGV_COLUMN].to_numpy(dtype=float),
                P_FAIL_COLUMN: kept_draws[P_FAIL_COLUMN].to_numpy(dtype=float),
                UNIFORM_COLUMN: kept_draws[UNIFORM_COLUMN].to_numpy(dtype=float),
            },
            geometry=gpd.GeoSeries(kept[geometry_column]).to_numpy(),
            crs=model.crs,
            index=kept.index,
        )
        present = rows.geometry.notna() & ~rows.geometry.is_empty
        pieces.append(rows.loc[present.to_numpy()])

    urban_rows = pd.concat(pieces)
    position = pd.Series(np.arange(len(kept)), index=kept.index)
    order = np.lexsort(
        (
            urban_rows[LAND_CLASS_COLUMN].to_numpy(dtype=object),
            position.reindex(urban_rows.index).to_numpy(),
        )
    )
    return gpd.GeoDataFrame(
        urban_rows.iloc[order].reset_index(drop=True),
        geometry="geometry",
        crs=model.crs,
    )


def combine_with_large(
    urban_rows: gpd.GeoDataFrame, large_rows: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Put the urban rows beside the large-model rows in one schema.

    The contract columns come first in their order, then every further column
    the large rows carry (step 1's simulation columns), null on the urban rows;
    large rows carry null in the urban-only columns. Sorted by
    ``landslide_id`` then ``land_class``.

    Args:
        urban_rows: :func:`to_landslide_rows`, with ``realisation_id`` and
            ``world_id`` set by the caller.
        large_rows: The large-model realisation of the same earthquake, with
            ``population`` of ``large``.

    Returns:
        The combined realisation, fresh index, in the urban rows' CRS.

    Raises:
        ValueError: If the two frames are in different CRSs, or the large
            rows miss a contract column.
    """
    if urban_rows.crs != large_rows.crs:
        msg = f"urban rows in {urban_rows.crs} against large rows in {large_rows.crs}"
        raise ValueError(msg)
    required = (LANDSLIDE_ID_COLUMN, POPULATION_COLUMN, LAND_CLASS_COLUMN)
    missing = [column for column in required if column not in large_rows.columns]
    if missing:
        msg = f"the large-model rows miss {missing}; run the reworked step 1"
        raise ValueError(msg)

    extra = [column for column in large_rows.columns if column not in COMBINED_COLUMNS]
    columns = [*COMBINED_COLUMNS, *extra]
    aligned = [frame.reindex(columns=columns) for frame in (urban_rows, large_rows)]
    combined = pd.concat(aligned, ignore_index=True)
    combined = combined.sort_values(
        [LANDSLIDE_ID_COLUMN, LAND_CLASS_COLUMN], kind="mergesort"
    ).reset_index(drop=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=urban_rows.crs)
