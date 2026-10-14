"""A slip's new wall, built on the wall the ground needs where one is mapped.

Loss gives every slip no damaged wall holds a new wall of its own (T-124),
sized from the slip. Where the slip's polygon stands on a wall unit, the wall
the ground needs has already been mapped, drawn in this world or not: exposure
rw step 6 cuts every candidate wall into the stretches that support each claim's
insured land (``wall-candidate-stretches``), and the urban slope model names the
unit each polygon stands on. This module makes the join (section 4 of
``.agents/plans/tweaks-to-property-damage.md``) and hands loss, on the land
table, what to build each slip with:

- **the height** is the mapped unit's DEM face height (4.1: the unit's wall type
  is not used, loss prices a new wall as timber pole on the pile that height
  calls for);
- **the length** is the part of the unit's stretch on the failure's claim
  alongside the failure's **evacuated** ground (4.4): the stretch line within
  :data:`~landloss.exposure.coverage.RW_COVERAGE_BUFFER_M` of that ground, shared
  between claims on a boundary the way the stretch itself is. Loss adds its
  margin;
- **the source** is ``mapped wall``, or ``slip`` where there is no mapped wall
  to use (4.3): the failure is a large-model landslide with no ``slope_id``, its
  polygon's pif is in no wall unit, its unit has no stretch on the claim, or
  under a metre of that stretch lies alongside its evacuated ground (the
  shortest stretch exposure keeps, ``BETA_MIN_WALL_LENGTH_IN_PROPERTY_M``).

Two failures on one unit and claim share one wall (T-124 keeps one wall per
failure, and a wall is not built twice over the same stretch): the failure with
the most evacuated ground takes the union of their cut stretches and the others
take 0, because loss builds a wall only for a failure that evacuated ground on
the claim. A failure
a damaged wall holds is ``slip`` with no height or length, since loss builds
nothing for it.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_EVACUATED_COLUMN,
    LANDSLIDE_IDS_COLUMN,
    LANDSLIDE_RW_IDS_COLUMN,
    LANDSLIDE_WALL_COLUMNS,
    MAPPED_WALL,
    RW_ID_COLUMN,
    SLIP_WALL,
)
from landloss.exposure.coverage import RW_COVERAGE_BUFFER_M, shared_lengths
from landloss.exposure.rw.population import WALL_LINE_ID_COLUMN
from landloss.hazard.landslide.wall_units import BETA_MIN_WALL_LENGTH_IN_PROPERTY_M
from landloss.vul.loss_input import PARENT_RW_ID_COLUMN


def held_failure_keys(rw: pd.DataFrame) -> set:
    """Return the ``(claim, wall)`` pairs of the damaged walls that hold a slip.

    The rule loss settles with (``attach_failures_to_walls`` in loss step 1): a
    slip that came with a wall is held by that wall's damaged piece on the same
    claim. A piece is damaged when ``is_damaged_by_shaking`` or ``is_evacuated``
    is set, and is matched to the failure's whole-wall id by ``parent_rw_id``.

    Args:
        rw: The contract's retaining wall table, after vul's own damaged-length
            rule has cleared the flags of a sliver.

    Returns:
        A set of ``(claim_id, parent wall id)``.
    """
    damaged = rw[IS_DAMAGED_BY_SHAKING_COLUMN].to_numpy(dtype=bool) | rw[
        IS_EVACUATED_COLUMN
    ].to_numpy(dtype=bool)
    parents = rw[PARENT_RW_ID_COLUMN if PARENT_RW_ID_COLUMN in rw else RW_ID_COLUMN]
    return set(
        zip(
            rw[CLAIM_ID_COLUMN].to_numpy(dtype=object)[damaged],
            parents.to_numpy(dtype=object)[damaged],
            strict=True,
        )
    )


def _line_parts(geometries: np.ndarray) -> np.ndarray:
    """Return each geometry as its lines alone, merged, or an empty line."""
    out = np.empty(len(geometries), dtype=object)
    for position, geometry in enumerate(geometries):
        parts = shapely.get_parts(geometry)
        lines = parts[(shapely.get_type_id(parts) == 1) & ~shapely.is_empty(parts)]
        out[position] = (
            shapely.line_merge(shapely.multilinestrings(lines))
            if len(lines)
            else shapely.LineString()
        )
    return out


def alongside_length(
    stretches: gpd.GeoDataFrame, claim: object, ground: shapely.Geometry
) -> float:
    """Return how much of a claim's stretch lies alongside some ground, in metres.

    The stretch lines of every claim on the wall unit are cut to the part within
    :data:`~landloss.exposure.coverage.RW_COVERAGE_BUFFER_M` of ``ground``, and
    a part lying in k claims' stretches, as a wall along a shared boundary does,
    gives each 1/k of its length
    (:func:`~landloss.exposure.coverage.shared_lengths`), as the stretch itself
    was shared.

    Args:
        stretches: The unit's candidate stretches, one row per claim, carrying
            ``claim_id`` and the stretch line.
        claim: The claim whose length is wanted.
        ground: The evacuated ground, or the union of several failures'.

    Returns:
        The length in metres, 0 where the claim has none alongside.
    """
    near = shapely.buffer(ground, RW_COVERAGE_BUFFER_M)
    cut = _line_parts(shapely.intersection(stretches.geometry.to_numpy(), near))
    has_length = shapely.length(cut) > 0
    mine = (stretches[CLAIM_ID_COLUMN].to_numpy(dtype=object) == claim) & has_length
    if not mine.any():
        return 0.0
    cut = cut[has_length]
    shares = shared_lengths(
        pd.Series(np.zeros(len(cut), dtype=int)), pd.Series(cut, dtype=object)
    )
    return float(shares[mine[has_length]].sum())


def attach_mapped_walls(
    land: pd.DataFrame,
    rw: pd.DataFrame,
    *,
    slope_ids: pd.Series,
    wall_line_of_slope: pd.Series,
    height_of_wall_line: pd.Series,
    candidate_stretches: gpd.GeoDataFrame,
    evacuated_ground: dict,
) -> pd.DataFrame:
    """Return the land table with each failure's mapped wall listed beside it.

    Adds :data:`~landloss.domain.loss_contract.LANDSLIDE_WALL_COLUMNS`, three
    lists in the order of ``landslide_ids``. A failure held by no damaged wall
    takes its polygon's unit's height and its stretch alongside its evacuated
    ground (see the module docstring); every other failure is ``slip`` with no
    height or length. A land table without the failure lists is returned as it
    is, and loss then sizes every new wall from the slip.

    A failure on two polygons of one claim is one failure: its values are on its
    first polygon, and its later entries carry the same height and source with
    length 0, so loss, which adds a failure's entries, builds it once.

    Args:
        land: The land table, carrying the failure lists of
            :data:`~landloss.domain.loss_contract.LANDSLIDE_FAILURE_COLUMNS`.
        rw: The contract's retaining wall table, to tell which failures a
            damaged wall holds.
        slope_ids: The ``slope_id`` of each landslide, by ``landslide_id``: null
            for a large-model landslide.
        wall_line_of_slope: The model's ``wall_line_id`` of each ``slope_id``,
            null where the polygon's pif is in no wall unit.
        height_of_wall_line: ``face_height_m`` by ``wall_line_id``
            (``wall-probability``).
        candidate_stretches: Exposure rw step 6's ``wall-candidate-stretches``.
        evacuated_ground: ``{(claim_id, landslide_id): evacuated ground}`` from
            :func:`~landloss.vul.landslide.land.damaged_area.evacuated_ground_per_failure`.

    Returns:
        A copy of ``land`` with the three lists added.
    """
    if LANDSLIDE_IDS_COLUMN not in land.columns:
        return land
    held = held_failure_keys(rw)
    by_line = dict(list(candidate_stretches.groupby(WALL_LINE_ID_COLUMN, sort=False)))

    # First pass: each unheld failure's own wall, once per claim and failure.
    own: dict[tuple, tuple[str, float, str]] = {}
    for claim, ids, walls in zip(
        land[CLAIM_ID_COLUMN],
        land[LANDSLIDE_IDS_COLUMN],
        land[LANDSLIDE_RW_IDS_COLUMN],
        strict=True,
    ):
        for failure, wall in zip(list(ids), list(walls), strict=True):
            key = (claim, failure)
            if key in own or (wall is not None and (claim, wall) in held):
                continue
            line = _mapped_line(failure, slope_ids, wall_line_of_slope)
            ground = evacuated_ground.get(key)
            if (
                line is None
                or line not in by_line
                or line not in height_of_wall_line.index
                or ground is None
                or ground.is_empty
                or ground.area <= 0
            ):
                continue
            length = alongside_length(by_line[line], claim, ground)
            height = float(height_of_wall_line[line])
            # No usable height: the slip sizes the wall.
            if (
                length >= BETA_MIN_WALL_LENGTH_IN_PROPERTY_M
                and np.isfinite(height)
                and height > 0
            ):
                own[key] = (line, length, height)

    # Failures on one unit and claim share a wall: the union of their cut
    # stretches on the one with the most evacuated ground (loss builds for a
    # failure only where it evacuated ground), none for the rest.
    groups: dict[tuple, list] = {}
    for key, (line, _, _) in own.items():
        groups.setdefault((key[0], line), []).append(key)
    length_of = {key: length for key, (_, length, _) in own.items()}
    for (claim, line), keys in groups.items():
        if len(keys) == 1:
            continue
        ranked = sorted(keys, key=lambda key: -evacuated_ground[key].area)
        ground = shapely.union_all([evacuated_ground[key] for key in ranked])
        length_of[ranked[0]] = alongside_length(by_line[line], claim, ground)
        for key in ranked[1:]:
            length_of[key] = 0.0

    placed: set = set()
    heights, lengths, sources = [], [], []
    for claim, ids in zip(
        land[CLAIM_ID_COLUMN], land[LANDSLIDE_IDS_COLUMN], strict=True
    ):
        row_heights, row_lengths, row_sources = [], [], []
        for failure in list(ids):
            key = (claim, failure)
            if key not in own:
                row_heights.append(None)
                row_lengths.append(None)
                row_sources.append(SLIP_WALL)
                continue
            row_heights.append(own[key][2])
            row_lengths.append(0.0 if key in placed else length_of[key])
            row_sources.append(MAPPED_WALL)
            placed.add(key)
        heights.append(row_heights)
        lengths.append(row_lengths)
        sources.append(row_sources)

    out = land.copy()
    for column, values in zip(
        LANDSLIDE_WALL_COLUMNS, (heights, lengths, sources), strict=True
    ):
        out[column] = pd.Series(values, index=out.index, dtype=object)
    if "geometry" in out.columns:
        # The geometry stays last, as the land table has it.
        out = out[[*(c for c in out.columns if c != "geometry"), "geometry"]]
    return out


def _mapped_line(
    failure: object, slope_ids: pd.Series, wall_line_of_slope: pd.Series
) -> str | None:
    """Return the wall unit a failure's polygon stands on, or None."""
    slope = slope_ids.get(failure)
    if slope is None or pd.isna(slope):
        return None
    line = wall_line_of_slope.get(slope)
    return None if line is None or pd.isna(line) else line
