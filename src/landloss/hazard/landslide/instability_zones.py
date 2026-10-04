"""Pips, pifs and sizs: the first stage of the urban slope model.

A **pip** (potential instability point) is a cell higher than the cell 1, 3 and
5 m away in the same one of eight directions, each time by more than
:data:`PIP_DROP_M`. It reads the 1 m DEM alone: no material, no other DEM. The
0.7 m keeps little blips out while still catching a wall of about that height.
Along a diagonal a cell is 1.41 m away, so the drop needed is scaled by 1.41.

A **pif** (potential instability face) joins the pips within :data:`PIF_JOIN_M`
of each other. It is tested over every pair of its *points*, which are its pips
and the cells each pip falls to (so a vertical wall, whose pips all sit at the
same height, still has a crest and a foot to measure between). Pairs under
:data:`NEAR_PAIR_M` apart must step by the ground group's ``adjacent_step_m``
(``landslide-seed-thresholds.csv``); pairs further apart, up to
:data:`MAX_PAIR_M`, must be as steep as the group's slope threshold for the
pair's height (``landslide-slope-thresholds.csv``). A pif that passes is a
**siz** (seed instability zone). Ground mapped as fill is soil, not rock
(:func:`landloss.hazard.landslide.slope_elements.rasterise_ground_map`).

The sizs seed the watershed growth of
:mod:`landloss.hazard.landslide.slope_elements`, and the grown elements go to
:func:`landloss.hazard.landslide.slope_polygons.build_slope_polygons`, once with
every siz walled and once with none (:func:`with_walls`). The siz table (every
pif, with its maximum angles and delta_h and the siz flag) is also the input of
the retaining-wall workflow (:func:`gen_siz_table`).
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike, NDArray
from rasterio.transform import Affine
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from landloss.hazard.landslide.slope_elements import (
    BANK,
    BETA_FREE_FACE_GROW_TOL_DEG,
    FREE_FACE,
    GROUND_GROUPS,
    HEIGHT_BANDS_M,
    OUTSIDE,
    SEED_THRESHOLDS_PATH,
    STEP_ANGLE_DEG,
    SlopeElements,
    _absorb_rounded_edges,
    _assemble_elements,
    _cell_size,
    _cost,
    _grow_by_limit,
    _relabel,
    height_band,
    step_angle_deg,
    terrain_layers,
)

# The drop, in metres, a pip has to make at each of the offsets: the lead's
# rule (2026-10-04), to keep blips of a few tenths out and walls of about 0.7 m in.
PIP_DROP_M = 0.7
# How far along the direction the drop has to hold, in metres.
PIP_OFFSETS_M = (1.0, 3.0, 5.0)
# Pips within this distance, in metres, are one pif.
PIF_JOIN_M = 2.0
# Pairs of points closer than this, in metres, are tested on the step between
# them; pairs further apart are tested on their angle.
NEAR_PAIR_M = 3.0
# Judgement: pairs further apart than this are not compared. A 16 m face at 32
# degrees runs about 26 m, and the pair count grows with the square of a pif's
# size (1.4 billion unbounded on the pilot, about 156 million at 30 m).
MAX_PAIR_M = 30.0
# Judgement (2026-10-04, after the lead found whole hillsides growing as one
# element): a pif spanning more than this, in metres, is cut into pieces before
# growth (:func:`split_pifs`); each piece seeds its own element.
MAX_PIF_SPAN_M = 20.0
# Points of a pif compared against the rest at a time, to bound memory.
_CHUNK = 4000

SIZ_PASS = "siz_pass"

# The eight directions as (row, column) steps, cardinals first so that a tie
# in the drop goes to a cardinal, and each one's bearing in degrees.
DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1), (-1, 1), (1, 1), (1, -1), (-1, -1))
_STEPS = np.array(DIRECTIONS)
BEARING_DEG = np.array([0.0, 90.0, 180.0, 270.0, 45.0, 135.0, 225.0, 315.0])


def load_adjacent_step_thresholds(
    path: Path = SEED_THRESHOLDS_PATH,
) -> dict[str, float]:
    """Read the step, in metres, that makes two points under 3 m apart a siz.

    Args:
        path: The seed thresholds CSV, with the column ``adjacent_step_m`` and
            one row per ground group.

    Returns:
        The step by ground group.

    Raises:
        ValueError: If the column or a group is missing, or a step is not
            above zero.
    """
    table = pd.read_csv(path)
    if "adjacent_step_m" not in table.columns or sorted(
        table["ground_group"]
    ) != sorted(GROUND_GROUPS):
        msg = f"{path.name} needs the column adjacent_step_m and one row per group."
        raise ValueError(msg)
    steps = table.set_index("ground_group")["adjacent_step_m"]
    if not (steps > 0).all():
        msg = f"{path.name}: every adjacent_step_m must be above zero."
        raise ValueError(msg)
    return {group: float(steps[group]) for group in GROUND_GROUPS}


# The step between two points under NEAR_PAIR_M apart that makes a siz, by
# ground group (landslide-seed-thresholds.csv, adjacent_step_m): 0.7 m on soil
# keeps retaining walls of that height; 3 m in rock keeps 1-2 m rock walls out.
ADJACENT_STEP_M = load_adjacent_step_thresholds()

if len(HEIGHT_BANDS_M) != 2:
    _msg = "landslide-slope-thresholds.csv needs exactly two height bands."
    raise ValueError(_msg)
# The height, in metres, at which the steeper angles give way to the gentler.
BAND_SPLIT_M = HEIGHT_BANDS_M[1]


@dataclass(frozen=True)
class Pips:
    """The pips of a DEM.

    Attributes:
        mask: True on a pip.
        direction: Per cell, the index into :data:`DIRECTIONS` the pip falls
            in (the direction of its largest drop at the furthest offset), -1
            where there is no pip.
    """

    mask: NDArray[np.bool_]
    direction: NDArray[np.int8]


def _shifted(grid: NDArray[np.float64], dr: int, dc: int, k: int) -> NDArray:
    """The grid read ``k`` cells away along ``(dr, dc)``, NaN off the grid."""
    out = np.full_like(grid, np.nan)
    height, width = grid.shape
    r0, r1 = max(0, -k * dr), min(height, height - k * dr)
    c0, c1 = max(0, -k * dc), min(width, width - k * dc)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = grid[r0 + k * dr : r1 + k * dr, c0 + k * dc : c1 + k * dc]
    return out


def offset_cells(cell_size_m: float) -> tuple[int, ...]:
    """The pip offsets in whole cells, each at least one."""
    return tuple(max(1, round(offset / cell_size_m)) for offset in PIP_OFFSETS_M)


def find_pips(dem: ArrayLike, cell_size_m: float) -> Pips:
    """Find the pips on a DEM.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        cell_size_m: The cell size.

    Returns:
        The pips and the direction each falls in.
    """
    z = np.asarray(dem, dtype=float)
    offsets = offset_cells(cell_size_m)
    best = np.full(z.shape, -np.inf)
    direction = np.full(z.shape, -1, dtype=np.int8)
    for index, (dr, dc) in enumerate(DIRECTIONS):
        need = PIP_DROP_M * math.hypot(dr, dc)
        with np.errstate(invalid="ignore"):
            passes = np.ones(z.shape, dtype=bool)
            for k in offsets:
                passes &= (z - _shifted(z, dr, dc, k)) > need
            drop = z - _shifted(z, dr, dc, offsets[-1])
            better = passes & (drop > best)
        best = np.where(better, drop, best)
        direction = np.where(better, index, direction).astype(np.int8)
    return Pips(mask=direction >= 0, direction=direction)


def cluster_pifs(
    mask: NDArray[np.bool_], cell_size_m: float
) -> tuple[NDArray[np.int32], int]:
    """Join the pips within :data:`PIF_JOIN_M` of each other into pifs.

    Args:
        mask: True on a pip.
        cell_size_m: The cell size.

    Returns:
        ``(labels, n_pifs)``: a grid numbering the pifs from 1 on their pips,
        0 elsewhere.
    """
    rows, cols = np.nonzero(mask)
    labels = np.zeros(mask.shape, dtype=np.int32)
    if rows.size == 0:
        return labels, 0
    tree = cKDTree(np.column_stack([rows, cols]) * cell_size_m)
    pairs = tree.query_pairs(PIF_JOIN_M + 1e-9, output_type="ndarray")
    graph = coo_matrix(
        (np.ones(len(pairs), dtype=np.int8), (pairs[:, 0], pairs[:, 1])),
        shape=(rows.size, rows.size),
    )
    n_pifs, component = connected_components(graph, directed=False)
    labels[rows, cols] = component + 1
    return labels, int(n_pifs)


def split_pifs(
    labels: NDArray[np.int32], cell_size_m: float, *, max_span_m: float
) -> tuple[NDArray[np.int32], NDArray[np.int64]]:
    """Cut every pif longer than ``max_span_m`` into pieces no longer than it.

    A pif is chained from pips 2 m apart, so a whole hillside's crest, or a
    network of gully heads, can be one pif; grown as one seed it becomes one
    element thousands of square metres across. Each long pif is cut in two at
    the middle of its span along its principal axis, and each half again, until
    no piece spans more than ``max_span_m``. The pieces seed their own growth,
    so the watershed meets them along the ground between (the crests and
    channels the cost follows) rather than along a line this function draws.

    Args:
        labels: The pifs on their pips' cells, from 1; 0 elsewhere.
        cell_size_m: The cell size.
        max_span_m: The longest a piece may span, in metres, along its
            principal axis.

    Returns:
        ``(pieces, parent)``: the pieces on their pips' cells, numbered from 1,
        and the pif each piece came from, indexed by piece (entry 0 is 0).
    """
    rows, cols = np.nonzero(labels)
    pif = labels[rows, cols]
    if rows.size == 0:
        return labels.copy(), np.zeros(1, dtype=np.int64)
    xy = np.column_stack([rows, cols]).astype(float) * cell_size_m
    order = np.argsort(pif, kind="stable")
    starts = np.flatnonzero(np.r_[True, np.diff(pif[order]) != 0])
    groups = np.split(order, starts[1:])
    piece = np.zeros(rows.size, dtype=np.int64)
    parent = [0]
    for members in groups:
        stack = [members]
        while stack:
            part = stack.pop()
            points = xy[part]
            span = 0.0
            if part.size > 1:
                centred = points - points.mean(axis=0)
                axis = np.linalg.svd(centred, full_matrices=False)[2][0]
                along = centred @ axis
                span = float(along.max() - along.min())
            if span <= max_span_m:
                parent.append(int(pif[part[0]]))
                piece[part] = len(parent) - 1
                continue
            low = along < (along.max() + along.min()) / 2
            stack.extend((part[low], part[~low]))
    pieces = np.zeros_like(labels)
    pieces[rows, cols] = piece
    return pieces, np.array(parent, dtype=np.int64)


def _pair_stats(
    xy: NDArray[np.float64], z: NDArray[np.float64], *, step_m: float
) -> tuple[float, float, float, bool]:
    """The pair statistics of one pif's points, in metres.

    Returns:
        ``(max_below, max_above, max_delta_h, near_pass)``: the steepest angle
        in degrees over pairs at least :data:`NEAR_PAIR_M` apart (and within
        :data:`MAX_PAIR_M`) whose delta_h is under / at least
        :data:`BAND_SPLIT_M`, the largest delta_h of any pair, and whether a
        pair under :data:`NEAR_PAIR_M` apart steps by ``step_m``.
    """
    max_below = max_above = max_dh = 0.0
    near_pass = False
    tree = cKDTree(xy)
    for start in range(0, len(xy), _CHUNK):
        chunk = cKDTree(xy[start : start + _CHUNK])
        pairs = chunk.sparse_distance_matrix(tree, MAX_PAIR_M, output_type="ndarray")
        dist = pairs["v"]
        dh = z[pairs["i"] + start] - z[pairs["j"]]
        valid = dh > 0
        if not valid.any():
            continue
        dist, dh = dist[valid], dh[valid]
        near = dist < NEAR_PAIR_M
        near_pass = near_pass or bool((dh[near] >= step_m).any())
        max_dh = max(max_dh, float(dh.max()))
        angle = np.degrees(np.arctan2(dh, dist))
        high = dh >= BAND_SPLIT_M
        for selected, current in ((~near & ~high, "below"), (~near & high, "above")):
            if selected.any():
                value = float(angle[selected].max())
                if current == "below":
                    max_below = max(max_below, value)
                else:
                    max_above = max(max_above, value)
    return max_below, max_above, max_dh, near_pass


def assess_pifs(
    dem: ArrayLike,
    pips: Pips,
    pif_labels: NDArray[np.int32],
    ground_group: ArrayLike,
    transform: Affine,
) -> pd.DataFrame:
    """Test every pif over all pairs of its points and flag the sizs.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        pips: From :func:`find_pips`.
        pif_labels: From :func:`cluster_pifs`.
        ground_group: The ground group code of every cell
            (:func:`landloss.hazard.landslide.slope_elements.rasterise_ground_map`
            with ``fill_as_soil=True``).
        transform: The grid's affine transform, north-up with square cells.

    Returns:
        One row per pif, indexed by ``pif_id``: all pifs, not only the sizs.
        Columns: ``ground_group`` (the majority at its pips), ``n_pips``,
        ``x``, ``y`` (its pips' centre), ``crest_z_m``, ``toe_z_m``,
        ``fall_bearing_deg``, ``max_delta_h_m`` (the largest delta_h of any
        pair), ``max_angle_below_deg`` and ``max_angle_above_deg`` (the steepest
        pair at least 3 m apart whose delta_h is under / at least 3.5 m, 0 if
        none), ``threshold_angle_deg`` (the group's angle for the band of
        ``max_delta_h_m``), ``near_step_pass``, ``far_angle_pass`` and
        ``is_siz`` (either test passed).
    """
    z = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    cell_size_m = _cell_size(transform)
    n_pifs = int(pif_labels.max())
    columns = [
        "ground_group",
        "n_pips",
        "x",
        "y",
        "crest_z_m",
        "toe_z_m",
        "fall_bearing_deg",
        "max_delta_h_m",
        "max_angle_below_deg",
        "max_angle_above_deg",
        "threshold_angle_deg",
        "near_step_pass",
        "far_angle_pass",
        "is_siz",
    ]
    if n_pifs == 0:
        return pd.DataFrame(columns=columns).rename_axis("pif_id")
    height, width = z.shape
    rows, cols = np.nonzero(pips.mask)
    owner = pif_labels[rows, cols].astype(np.int64)
    fall = pips.direction[rows, cols]

    # The points of a pif: its pips, and the cells they fall to at each offset.
    point_rows, point_cols, point_owner = [rows], [cols], [owner]
    for k in offset_cells(cell_size_m):
        r2 = rows + k * _STEPS[fall, 0]
        c2 = cols + k * _STEPS[fall, 1]
        inside = (r2 >= 0) & (r2 < height) & (c2 >= 0) & (c2 < width)
        inside[inside] = np.isfinite(z[r2[inside], c2[inside]])
        point_rows.append(r2[inside])
        point_cols.append(c2[inside])
        point_owner.append(owner[inside])
    all_rows = np.concatenate(point_rows)
    all_cols = np.concatenate(point_cols)
    all_owner = np.concatenate(point_owner)
    key = all_owner * height * width + all_rows * width + all_cols
    _, first = np.unique(key, return_index=True)
    all_rows, all_cols, all_owner = all_rows[first], all_cols[first], all_owner[first]
    order = np.lexsort((all_cols, all_rows, all_owner))
    all_rows, all_cols, all_owner = all_rows[order], all_cols[order], all_owner[order]
    all_z = z[all_rows, all_cols]
    all_xy = np.column_stack([all_rows, all_cols]) * cell_size_m
    ends = np.cumsum(np.bincount(all_owner, minlength=n_pifs + 1))

    n_groups = len(GROUND_GROUPS)
    by_group = np.bincount(
        owner * n_groups + groups[rows, cols], minlength=(n_pifs + 1) * n_groups
    ).reshape(-1, n_groups)
    pif_group = by_group.argmax(axis=1)
    index = np.arange(1, n_pifs + 1)
    sin = np.bincount(owner, np.sin(np.radians(BEARING_DEG[fall])), n_pifs + 1)
    cos = np.bincount(owner, np.cos(np.radians(BEARING_DEG[fall])), n_pifs + 1)
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e

    table = pd.DataFrame(index=pd.Index(index, name="pif_id"))
    table["ground_group"] = np.asarray(GROUND_GROUPS)[pif_group[index]]
    table["n_pips"] = np.bincount(owner, minlength=n_pifs + 1)[index]
    table["x"] = ndimage.mean(x, owner, index)
    table["y"] = ndimage.mean(y, owner, index)
    table["crest_z_m"] = ndimage.maximum(z[rows, cols], owner, index)
    table["toe_z_m"] = ndimage.minimum(all_z, all_owner, index)
    table["fall_bearing_deg"] = np.degrees(np.arctan2(sin[index], cos[index])) % 360.0

    stats = np.zeros((n_pifs, 4))
    for i, pif in enumerate(index):
        lo, hi = ends[pif - 1], ends[pif]
        group = GROUND_GROUPS[pif_group[pif]]
        stats[i] = _pair_stats(
            all_xy[lo:hi], all_z[lo:hi], step_m=ADJACENT_STEP_M[group]
        )
    table["max_delta_h_m"] = stats[:, 2]
    table["max_angle_below_deg"] = stats[:, 0]
    table["max_angle_above_deg"] = stats[:, 1]
    below = np.array([STEP_ANGLE_DEG[g][0] for g in table["ground_group"]])
    above = np.array([STEP_ANGLE_DEG[g][1] for g in table["ground_group"]])
    table["threshold_angle_deg"] = np.where(stats[:, 2] >= BAND_SPLIT_M, above, below)
    table["near_step_pass"] = stats[:, 3].astype(bool)
    table["far_angle_pass"] = (stats[:, 0] >= below) | (stats[:, 1] >= above)
    table["is_siz"] = table["near_step_pass"] | table["far_angle_pass"]
    return table


@dataclass(frozen=True)
class InstabilityZones:
    """The elements grown from the sizs, with the stage 1 results they came from.

    Attributes:
        found: The elements (all walled; see :func:`with_walls`), in the form
            :func:`landloss.hazard.landslide.slope_polygons.build_slope_polygons`
            takes.
        pips: The pips.
        pif_labels: The pifs on their pips' cells.
        sizs: The siz table, one row per pif (see :func:`assess_pifs`).
    """

    found: SlopeElements
    pips: Pips
    pif_labels: NDArray[np.int32]
    sizs: pd.DataFrame


def find_instability_zones(
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    *,
    categories: Mapping[str, ArrayLike] | None = None,
    core: ArrayLike | None = None,
) -> InstabilityZones:
    """Find the pips, pifs and sizs on a DEM and grow the sizs into elements.

    Each siz's pips seed the watershed growth of the old free-face pass, into
    cells steeper than the siz's own threshold angle less
    :data:`~landloss.hazard.landslide.slope_elements.BETA_FREE_FACE_GROW_TOL_DEG`
    (so material enters only here), and the grown regions go through the junk
    filters of :func:`landloss.hazard.landslide.slope_elements.find_slope_elements`
    (under 0.5 m high, under 3 m long, gentler overall than 18.4 degrees, no
    transect). The siz decision is made on the pif; a grown element is not
    re-tested.

    Args:
        dem: Ground elevation in metres on a north-up grid of square cells,
            NaN for nodata and outside the LiDAR.
        ground_group: The ground group code of every cell, with fill as soil
            (``rasterise_ground_map(..., fill_as_soil=True)``).
        transform: The grid's affine transform.
        categories: Integer grids to take the majority of over each element.
        core: A tile's core, as in ``find_slope_elements``.

    Returns:
        The elements, pips, pifs and the siz table.

    Raises:
        ValueError: If the grids do not share a shape.
    """
    elevation = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    if groups.shape != elevation.shape:
        msg = f"The ground group grid is {groups.shape}, the DEM {elevation.shape}."
        raise ValueError(msg)
    core_grid = np.ones(elevation.shape, dtype=bool)
    if core is not None:
        core_grid = np.asarray(core, dtype=bool)
        if core_grid.shape != elevation.shape:
            msg = f"The core grid is {core_grid.shape}, the DEM {elevation.shape}."
            raise ValueError(msg)
    cell_size_m = _cell_size(transform)
    layers = terrain_layers(elevation, cell_size_m)

    pips = find_pips(elevation, cell_size_m)
    pif_labels, _ = cluster_pifs(pips.mask, cell_size_m)
    sizs = assess_pifs(elevation, pips, pif_labels, groups, transform)

    band = height_band(np.nan_to_num(layers.step_height_m, nan=0.0))
    threshold = step_angle_deg(groups, band)
    exceedance = layers.slope_coarse_deg - threshold
    pieces, parent = split_pifs(pif_labels, cell_size_m, max_span_m=MAX_PIF_SPAN_M)
    is_siz_piece = sizs["is_siz"].astype(bool).reindex(parent, fill_value=False)
    siz_pieces = np.flatnonzero(is_siz_piece.to_numpy())
    n_seeds = int(siz_pieces.size)
    lookup = np.zeros(parent.size, dtype=np.int32)
    lookup[siz_pieces] = np.arange(1, n_seeds + 1, dtype=np.int32)
    seeds = lookup[pieces]
    if n_seeds:
        limit = np.zeros(n_seeds + 1)
        limit[1:] = (
            sizs.loc[parent[siz_pieces], "threshold_angle_deg"].to_numpy()
            - BETA_FREE_FACE_GROW_TOL_DEG
        )
        grown = _grow_by_limit(
            seeds,
            n_seeds,
            _cost(exceedance),
            slope=np.nan_to_num(layers.slope_fine_deg, nan=-np.inf),
            finite=np.isfinite(elevation) & np.isfinite(layers.slope_fine_deg),
            limit=limit,
            cell_limit=np.nan_to_num(
                threshold - BETA_FREE_FACE_GROW_TOL_DEG, nan=np.inf
            ),
        )
        grown = _absorb_rounded_edges(grown, layers)
        present = np.bincount(grown.ravel(), minlength=n_seeds + 1) > 0
        labels = _relabel(grown, present)
        seed_grid = _relabel(seeds, present)
    else:
        labels = np.zeros(elevation.shape, dtype=np.int32)
        seed_grid = labels
    seed_grid = np.where(labels > OUTSIDE, seed_grid, OUTSIDE).astype(np.int32)
    n_labels = int(labels.max())
    found = _assemble_elements(
        elevation,
        groups,
        transform,
        layers,
        labels,
        seed_grid,
        exceedance,
        np.full(n_labels + 1, SIZ_PASS),
        np.full(n_labels + 1, FREE_FACE),
        core_grid,
        categories,
    )
    elements = found.elements.copy()
    seeded = elements["seed_row"].to_numpy() >= 0
    siz_id = np.zeros(len(elements), dtype=np.int64)
    siz_id[seeded] = pif_labels[
        elements["seed_row"].to_numpy()[seeded],
        elements["seed_col"].to_numpy()[seeded],
    ]
    elements["siz_id"] = siz_id
    for column, source in (
        ("siz_threshold_angle_deg", "threshold_angle_deg"),
        ("siz_max_angle_below_deg", "max_angle_below_deg"),
        ("siz_max_angle_above_deg", "max_angle_above_deg"),
        ("siz_max_delta_h_m", "max_delta_h_m"),
    ):
        elements[column] = sizs[source].reindex(siz_id).to_numpy()
    return InstabilityZones(
        found=replace(found, elements=elements),
        pips=pips,
        pif_labels=pif_labels,
        sizs=sizs,
    )


def with_walls(found: SlopeElements, walled: bool | pd.Series) -> SlopeElements:  # noqa: FBT001
    """Set which elements carry a retaining wall.

    The polygon builder reads a ``free_face`` as a wall (the active wedge
    behind the crest) and a ``bank`` as no wall (the headscarp band behind the
    crest, or the fill bank rule).

    Args:
        found: The elements, from :func:`find_instability_zones`.
        walled: One flag for every element, or a Series of flags indexed by
            element label (missing elements are not walled).

    Returns:
        The elements with ``element_type`` set.
    """
    index = found.elements.index
    flags = (
        pd.Series(walled, index=index)
        if isinstance(walled, bool)
        else walled.reindex(index, fill_value=False)
    )
    element_type = np.where(flags.to_numpy(dtype=bool), FREE_FACE, BANK)
    return replace(found, elements=found.elements.assign(element_type=element_type))


def gen_siz_table(
    result: InstabilityZones, transform: Affine, *, crs: int
) -> gpd.GeoDataFrame:
    """The siz table with each pif's pips as geometry, for the RW workflow.

    Args:
        result: From :func:`find_instability_zones`.
        transform: The grid's affine transform.
        crs: The EPSG code of the grid.

    Returns:
        The siz table (every pif; ``is_siz`` says which are sizs) with a
        MultiPoint of the pif's pip cell centres.
    """
    rows, cols = np.nonzero(result.pips.mask)
    points = pd.DataFrame(
        {
            "x": transform.c + (cols + 0.5) * transform.a,
            "y": transform.f + (rows + 0.5) * transform.e,
            "pif_id": result.pif_labels[rows, cols],
        }
    )
    geometry = gpd.GeoSeries(
        {
            pif: shapely.MultiPoint(group[["x", "y"]].to_numpy())
            for pif, group in points.groupby("pif_id")
        },
        crs=crs,
    ).reindex(result.sizs.index)
    return gpd.GeoDataFrame(result.sizs, geometry=geometry, crs=crs)


def write_siz_table(table: gpd.GeoDataFrame, path: Path) -> None:
    """Write the siz table as GeoParquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)


def read_siz_table(path: Path) -> gpd.GeoDataFrame:
    """Read a siz table written by :func:`write_siz_table`."""
    return gpd.read_parquet(path)
