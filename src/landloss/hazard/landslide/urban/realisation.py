"""One realisation of the urban slope failure model.

What belongs here: sampling site PGA at each polygon's representative point, the
failure draw against each polygon's fragility, the rows the failed polygons
write beside the large model's, and the wall outcome table. Used by landslide
step 6 (``s6_urban_slope_realisation``); contract sections 5 and 7.11 of
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
weakest polygon does: it reads the strongest amplification along it. A
polygon's edge can carry several lines that drew a wall (``wall_line_ids``: one
wall split at property boundaries), so polygons are grouped by any line they
share, transitively. Polygons without a wall keep their own uniform and fail
on their own.

Every failed polygon survives and writes its fixed geometry (the project lead's
decision, 2026-10-14). Failed urban polygons are not absorbed into one another
and are not superseded by a large-model landslide, so ground that two failures
share is written twice; it is counted once downstream, because vul landslide
land step 3 measures areas on the union of the failures. A polygon that did not
fail is standing whatever a large landslide does around it (contract decision
35): a wall the large landslide actually reaches is flagged by vul step 11's
intersection of the wall line with the combined realisation's ``evacuated
land``.
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd

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
# Step 6 no longer writes ABSORBED or SUPERSEDED (2026-10-14: every failed urban
# polygon survives); they are kept so an outcome file from an older run still
# reads.
ABSORBED = "absorbed"
SUPERSEDED = "superseded"
OUTCOMES = (STANDING, FAILED_WITH_POLYGON, ABSORBED, SUPERSEDED)
# The precedence a wall on polygons at several scales resolves by, lowest rank
# wins: failed with its polygon, then standing (see :func:`wall_outcomes`;
# contract section 3.10). The two retired outcomes keep their old ranks.
OUTCOME_RANK = {SUPERSEDED: 0, FAILED_WITH_POLYGON: 1, ABSORBED: 2, STANDING: 3}

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
PGA_COLUMN = "pga_g"
P_FAIL_COLUMN = "p_fail"
UNIFORM_COLUMN = "uniform"
FAILED_COLUMN = "failed"

# The combined realisation columns (contract section 3.10), in order. The
# large rows keep every column landslide step 3 wrote after these.
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
    PGA_COLUMN,
    P_FAIL_COLUMN,
    UNIFORM_COLUMN,
    "geometry",
)

# The wall outcome columns (contract section 3.10) that this module writes; the
# step inserts ``world_id`` and ``realisation_id`` before them.
OUTCOME_COLUMN = "outcome"
OUTCOME_COLUMNS = (
    RW_ID_COLUMN,
    WALL_LINE_ID_COLUMN,
    CLAIM_ID_COLUMN,
    SLOPE_ID_COLUMN,
    OUTCOME_COLUMN,
)

# The land class each state geometry column writes, with the depth column it
# carries (``None`` for imminent ground, whose depth is NaN).
_STATE_ROWS = (
    (EVACUATED, EVACUATED_GEOMETRY_COLUMN, DEPTH_EVACUATED_COLUMN),
    (INUNDATED, INUNDATED_GEOMETRY_COLUMN, DEPTH_INUNDATED_COLUMN),
    (IMMINENT, IMMINENT_GEOMETRY_COLUMN, None),
)


def sample_pga(points: gpd.GeoSeries, pga_path: Path) -> pd.Series:
    """Read the earthquake's site PGA at each polygon's representative point.

    Args:
        points: The representative points, one per polygon of the model file.
        pga_path: The site class PGA raster shaking step 4 wrote for the
            earthquake, in g.

    Returns:
        PGA in g on ``points.index``, NaN off the grid.
    """
    return sample_at_points(pga_path, points).rename(PGA_COLUMN)


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
    model: gpd.GeoDataFrame, pga_g: pd.Series, rng: np.random.Generator
) -> pd.DataFrame:
    """Draw which polygons fail, one uniform per wall line or wall-less row.

    Each row's fragility is the lognormal of contract section 6 on its own
    ``theta`` and ``beta``, evaluated by
    :func:`landloss.hazard.landslide.urban.fragility.lognormal_failure_probability`
    (a PGA at or below zero gives 0, a NaN PGA off the grid gives NaN so the
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
    together where their curves agree. The key is the line, not ``rw_id``,
    because an uninsured wall has
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
        pga_g: Site PGA at each row's representative point, on ``model.index``.
        rng: The urban stream of the earthquake and world.

    Returns:
        A frame on ``model.index`` with ``pga_g``, ``p_fail``, ``uniform``
        and ``failed``. ``failed`` is false where ``p_fail`` is NaN.
    """
    pga = pga_g.reindex(model.index).to_numpy(dtype=float)
    p_fail = lognormal_failure_probability(
        pga,
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
            PGA_COLUMN: pga,
            P_FAIL_COLUMN: p_fail,
            UNIFORM_COLUMN: uniform,
            FAILED_COLUMN: failed,
        },
        index=model.index,
    )


def _polygon_outcomes(model: gpd.GeoDataFrame, draws: pd.DataFrame) -> pd.DataFrame:
    """Name what happened to each model polygon: it failed, or it stands."""
    failed = draws[FAILED_COLUMN].reindex(model.index).to_numpy(dtype=bool)
    outcome = np.where(failed, FAILED_WITH_POLYGON, STANDING).astype(object)
    return pd.DataFrame(
        {
            WALL_LINE_IDS_COLUMN: _row_lines(model, walled_only=False),
            SLOPE_ID_COLUMN: model[SLOPE_ID_COLUMN].to_numpy(dtype=object),
            OUTCOME_COLUMN: outcome,
        }
    )


def wall_outcomes(
    model: gpd.GeoDataFrame, walls: gpd.GeoDataFrame, draws: pd.DataFrame
) -> pd.DataFrame:
    """Write what happened to every wall of the world on sloping land.

    Spined on the wall population filtered to ``is_flatland`` false and
    left-joined on ``wall_line_id`` to every model row carrying the wall's
    line among its ``wall_line_ids`` (the lines on its edge that drew a wall),
    so a wall split at a property boundary into several lines on one polygon
    edge takes that polygon's outcome on every line. ``rw_id``, ``claim_id``
    and ``wall_line_id`` come from the population, and a wall whose line is on
    no model row still has a row: ``standing`` with ``slope_id`` null.
    A wall whose polygon failed is ``failed_with_polygon``; otherwise
    ``standing``, whatever a large landslide does around a polygon that did not
    fail (contract decision 35; vul step 11 flags a wall whose line a large
    landslide reaches). Where a wall's line sits on polygons at several scales
    a failed one wins, and the row that reached it supplies ``slope_id``; ties
    keep the model's order.

    Args:
        model: The world's model file, in its own order, carrying
            ``wall_line_ids``.
        walls: The world's wall population, carrying ``rw_id``,
            ``wall_line_id``, ``claim_id`` and ``is_flatland``.
        draws: :func:`draw_failures` on ``model``.

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

    per_polygon = _polygon_outcomes(model, draws)
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
    outcomes[SLOPE_ID_COLUMN] = (
        outcomes[SLOPE_ID_COLUMN]
        .astype(object)
        .where(outcomes[SLOPE_ID_COLUMN].notna(), None)
    )
    return outcomes[list(OUTCOME_COLUMNS)].reset_index(drop=True)


def to_landslide_rows(model: gpd.GeoDataFrame, draws: pd.DataFrame) -> gpd.GeoDataFrame:
    """Write the fixed geometry of every failed polygon as landslide rows.

    Overlapping failures are all written; downstream counts shared ground once.
    Three rows per failed polygon, one per land class: the evacuated polygon at its
    evacuated depth, the inundated polygon at its inundated depth, and the
    imminent polygon with no depth. ``landslide_id`` is the ``slope_id``;
    ``volume_m3`` is the evacuated depth times the evacuated area, and
    ``source_area_m2`` the evacuated area. A state geometry that is missing or
    empty writes no row.

    Args:
        model: The world's model file.
        draws: :func:`draw_failures` on ``model``.

    Returns:
        The urban rows with the columns of :data:`COMBINED_COLUMNS` less the
        two ids, in the model's order then by land class.
    """
    failed = draws[FAILED_COLUMN].reindex(model.index).to_numpy(dtype=bool)
    kept = model.loc[failed]
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
                PGA_COLUMN: kept_draws[PGA_COLUMN].to_numpy(dtype=float),
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
    the large rows carry (landslide step 3's simulation columns), null on the
    urban rows;
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
        msg = (
            f"the large-model rows miss {missing}; "
            "run landslide step 3 (s1_simulate_landslides.py)"
        )
        raise ValueError(msg)

    extra = [column for column in large_rows.columns if column not in COMBINED_COLUMNS]
    columns = [*COMBINED_COLUMNS, *extra]
    aligned = [frame.reindex(columns=columns) for frame in (urban_rows, large_rows)]
    combined = pd.concat(aligned, ignore_index=True)
    combined = combined.sort_values(
        [LANDSLIDE_ID_COLUMN, LAND_CLASS_COLUMN], kind="mergesort"
    ).reset_index(drop=True)
    return gpd.GeoDataFrame(combined, geometry="geometry", crs=urban_rows.crs)
