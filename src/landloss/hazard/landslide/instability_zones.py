"""Pips, pifs and sizs: the first stage of the urban slope model.

A **pip** (potential instability point) is a cell higher than the cell 1, 3 and
5 m away in the same one of eight directions, each time by more than
:data:`PIP_DROP_M`. It reads the 1 m DEM alone: no material, no other DEM. The
0.7 m keeps little blips out while still catching a wall of about that height.
Along a diagonal a cell is 1.41 m away, so the drop needed is scaled by 1.41.

A **pif** (potential instability face) joins the pips within :data:`PIF_JOIN_M`
of each other, and holds at least :data:`BETA_MIN_PIF_PIPS` of them; a smaller
cluster is not a pif (its pips stay pips, with no pif), nor is a cluster most
of whose pips lie in a building outline (:func:`exclude_pifs`): a roof's
edge or a building's wall is not ground. The step also excludes the cells
beyond reach of every building (:func:`beyond_reach`), so no pif stands more
than 100 m from one. It is tested over
every pair of its *points*, which are its pips and the cells each pip falls
to (so a vertical wall, whose pips all sit at the same height, still has a
crest and a foot to measure between). Pairs under
:data:`NEAR_PAIR_M` apart must step by the ground group's ``adjacent_step_m``
(``landslide-seed-thresholds.csv``); pairs further apart, up to
:data:`MAX_PAIR_M`, must be as steep as the group's slope threshold for the
pair's height (``landslide-slope-thresholds.csv``). A pif that passes is a
**siz** (seed instability zone). That is the pair test (:data:`PAIRS_TEST`);
the pipeline runs the fall-line test (:data:`FALL_LINE_TEST`, the lead,
2026-10-08), which reads each pip's drop down its true downhill line to the
toe of its face by the same step and angle rules, at a fraction of the cost.
Each pif is first cut into pieces no longer than :data:`MAX_PIF_SPAN_M`
(:func:`split_pifs`), and each piece is a pif of its own from there on (the
lead, 2026-10-06) and is tested on its own pips (the lead, 2026-10-08;
before then each piece took its whole pif's verdict), keeping its
``parent_pif_id``, so an element's siz, a siz table row and a wall candidate
are one piece. Ground mapped as fill is soil, not rock
(:func:`landloss.hazard.landslide.slope_elements.rasterise_ground_map`).

The sizs seed the watershed growth of
:mod:`landloss.hazard.landslide.slope_elements`, and the grown elements go to
:func:`landloss.hazard.landslide.slope_polygons.build_slope_polygons`, once with
every siz walled and once with none (:func:`with_walls`). The siz table (every
pif, with its maximum angles and delta_h and the siz flag) is also the input of
the retaining-wall workflow (:func:`gen_siz_table`), with each pif's spine
and the fall direction at its two ends (:func:`gen_pif_spines`) so that pieces
of one wall can be joined end to end.
"""

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from numpy.typing import ArrayLike, NDArray
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from landloss.domain.constants import MIN_WALL_HEIGHT_M
from landloss.hazard.landslide import bend_split
from landloss.hazard.landslide.bend_split import cut_path
from landloss.hazard.landslide.slope_elements import (
    BANK,
    BETA_FREE_FACE_GROW_TOL_DEG,
    FREE_FACE,
    GROUND_GROUPS,
    HB1995_CUT_HEIGHT_M,
    HEIGHT_BANDS_M,
    OUTSIDE,
    SEED_THRESHOLDS_PATH,
    STACK_DOMINANT_HEIGHT_M,
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
# Judgement (the lead, 2026-10-06): a pif whose spine (the longest shortest
# path through its pips) is shorter than this, in metres, is not a pif either:
# no siz table row and no wall is under 3 m, the shortest element kept and the
# walls' shortest section.
BETA_MIN_PIF_LENGTH_M = 3.0
# Judgement (the lead, 2026-10-06): a cluster of fewer pips than this is not a
# pif, so neither a siz nor a wall candidate. Three pips span about 3 m, the
# shortest element kept (BETA_MIN_ELEMENT_LENGTH_M); on the pilot a third of
# the siz pifs (median one pip) grew no element and their walls had no polygon.
BETA_MIN_PIF_PIPS = 3
# Pairs of points closer than this, in metres, are tested on the step between
# them; pairs further apart are tested on their angle.
NEAR_PAIR_M = 3.0
# Judgement: pairs further apart than this are not compared. A 16 m face at 32
# degrees runs about 26 m, and the pair count grows with the square of a pif's
# size (1.4 billion unbounded on the pilot, about 156 million at 30 m).
MAX_PAIR_M = 30.0
# Judgement: no pif piece is longer than this along its spine, in metres; each
# piece is a siz table row and seeds its own element. A cap since 2026-10-04,
# after the lead found whole hillsides growing as one element; 20 m until the
# lead's 2026-10-06 decision to cut the pifs by the wall rules (a new piece
# where following the spine needs a fourth bend, no piece under 3 m) and keep
# a hard cap of 50 m (:func:`split_pifs`).
MAX_PIF_SPAN_M = 50.0
# Points of a pif compared against the rest at a time, to bound memory.
_CHUNK = 4000

# The siz tests :func:`assess_pifs` can run. ``pairs`` compares every pair of a
# pif's points up to MAX_PAIR_M apart; ``fall_line`` reads each pip's drop down
# its own fall line out to MAX_PAIR_M, which finds the crest-to-foot lines the
# pair test's maximum comes from without the pairs along the face. A candidate
# since 2026-10-08, compared on the pilots before the pipeline switches.
PAIRS_TEST = "pairs"
FALL_LINE_TEST = "fall_line"

SIZ_PASS = "siz_pass"
# What an element built on a GNS-only wall unit's line was grown in.
WALL_LINE = "wall_line"

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
    mask: NDArray[np.bool_],
    cell_size_m: float,
    *,
    min_pips: int = BETA_MIN_PIF_PIPS,
) -> tuple[NDArray[np.int32], int]:
    """Join the pips within :data:`PIF_JOIN_M` of each other into pifs.

    A cluster of fewer than ``min_pips`` pips is not a pif: its pips are left
    at 0, and the pifs that are kept are numbered from 1 with no gaps, in the
    order of their first pip in row order.

    Args:
        mask: True on a pip.
        cell_size_m: The cell size.
        min_pips: The fewest pips a pif holds.

    Returns:
        ``(labels, n_pifs)``: a grid numbering the pifs from 1 on their pips,
        0 elsewhere (and on the pips of clusters too small to be pifs).
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
    _, component = connected_components(graph, directed=False)
    size = np.bincount(component)
    big = size >= min_pips
    number = np.zeros(size.size, dtype=np.int32)
    # connected_components numbers the clusters by their first pip in row
    # order, so the kept ones stay in that order.
    number[big] = np.arange(1, int(big.sum()) + 1, dtype=np.int32)
    labels[rows, cols] = number[component]
    return labels, int(big.sum())


def exclude_pifs(
    labels: NDArray[np.int32], mask: ArrayLike
) -> tuple[NDArray[np.int32], int, int]:
    """Drop the pifs most of whose pips lie on masked cells, and renumber.

    The step passes the LINZ building outlines as the mask (the lead,
    2026-10-06): the edge of a roof, or a building's wall against the ground
    beside it, makes pips as a retaining wall does, but it is neither a slope
    nor a wall candidate. A pif is dropped where more than half its pips are
    masked; the kept pifs are numbered from 1 with no gaps, in their order.

    Args:
        labels: The pifs on their pips' cells, from :func:`cluster_pifs`.
        mask: True on the cells to exclude, on the grid of ``labels``.

    Returns:
        ``(labels, n_kept, n_dropped)``.

    Raises:
        ValueError: If the mask is not on the grid of ``labels``.
    """
    excluded = np.asarray(mask, dtype=bool)
    if excluded.shape != labels.shape:
        msg = f"The exclusion mask is {excluded.shape}, the pif grid {labels.shape}."
        raise ValueError(msg)
    n_pifs = int(labels.max(initial=0))
    rows, cols = np.nonzero(labels)
    pif = labels[rows, cols]
    total = np.bincount(pif, minlength=n_pifs + 1)
    inside = np.bincount(pif, weights=excluded[rows, cols], minlength=n_pifs + 1)
    drop = 2.0 * inside > total
    drop[0] = False
    keep = (total > 0) & ~drop
    keep[0] = False
    number = np.zeros(n_pifs + 1, dtype=np.int32)
    number[keep] = np.arange(1, int(keep.sum()) + 1, dtype=np.int32)
    out = np.zeros_like(labels)
    out[rows, cols] = number[pif]
    return out, int(keep.sum()), int(drop.sum())


def beyond_reach(
    mask: ArrayLike, cell_size_m: float, reach_m: float
) -> NDArray[np.bool_]:
    """True on the cells further than ``reach_m`` from every masked cell.

    The step passes the LINZ building outlines as the mask, so that with
    :func:`exclude_pifs` the urban model runs only within reach of a building
    (the lead, 2026-10-01: within 100 m of a building outline). Distances are
    centre to centre; a grid with no masked cell is beyond reach everywhere.

    Args:
        mask: True on the cells to measure from.
        cell_size_m: The side of a cell, in metres.
        reach_m: How far from a masked cell a cell is still within reach.

    Returns:
        A boolean grid of the shape of ``mask``.
    """
    source = np.asarray(mask, dtype=bool)
    if not source.any():
        return np.ones(source.shape, dtype=bool)
    distance_m = ndimage.distance_transform_edt(~source, sampling=cell_size_m)
    return distance_m > reach_m


def _pif_paths(
    xy: NDArray[np.float64], *, cell_size_m: float, min_branch_m: float
) -> list[NDArray[np.float64]]:
    """A pif's pips as paths: its spine, then each branch that sticks out.

    The spine is the longest shortest path through the pips
    (:func:`_longest_geodesic_path`, on the whole graph, since a spanning
    tree's longest path folds back across a face several cells thick). Pips
    further from every path so far than twice the pif's mean thickness (its
    pips' area over its spine's length), and never under ``min_branch_m``,
    are a branch (a spur off a crest, the leg of a T): each group of them
    joined within :data:`PIF_JOIN_M` adds its own longest path, until no pip
    is that far out. The rest of a thick face is left to the nearest path.
    """
    path, length = _longest_geodesic_path(xy)
    paths = [xy[path]]
    thickness = len(xy) * cell_size_m**2 / max(length, cell_size_m)
    reach = max(min_branch_m, 2.0 * thickness)
    points = shapely.points(xy)
    while True:
        lines = shapely.MultiLineString([p for p in paths if len(p) > 1])
        far = np.flatnonzero(shapely.distance(points, lines) > reach)
        if far.size < 2:
            break
        sub = xy[far]
        pairs = cKDTree(sub).query_pairs(PIF_JOIN_M + 1e-9, output_type="ndarray")
        graph = coo_matrix(
            (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(sub),) * 2
        )
        n_parts, part = connected_components(graph, directed=False)
        added = False
        for k in range(n_parts):
            group = sub[part == k]
            if len(group) > 1:
                branch, _ = _longest_geodesic_path(group)
                paths.append(group[branch])
                added = True
        if not added:
            break
    return paths


def split_pifs(
    labels: NDArray[np.int32],
    cell_size_m: float,
    *,
    max_span_m: float,
    max_bends: int | None = None,
    stray_tolerance_m: float = 0.0,
    min_segment_m: float = 0.0,
    max_turn_deg: float = math.inf,
    counts: Counter | None = None,
) -> tuple[NDArray[np.int32], NDArray[np.int64], list[NDArray[np.float64] | None]]:
    """Cut every pif along its spine into pieces, by the wall rules.

    A pif is chained from pips 2 m apart, so a whole hillside's crest, or a
    network of gully heads, can be one pif; grown as one seed it becomes one
    element thousands of square metres across. Each pif's paths (its spine,
    the longest shortest path through its pips, then each branch that sticks
    out, :func:`_pif_paths`) are cut by the rule the walls are cut by
    (:func:`landloss.hazard.landslide.bend_split.cut_path`, the lead,
    2026-10-06): a new piece wherever following the path within
    ``stray_tolerance_m`` would need more than ``max_bends`` bends, no piece
    whose ends are under ``min_segment_m`` apart, and none longer than
    ``max_span_m`` along the path. A piece's line is the stretch of path it
    was cut on (:func:`landloss.hazard.landslide.bend_split.canonical_line`),
    so it keeps every rule by construction; its pips are the pif's pips
    nearest that stretch (ties to the first). A branch whose ends are under
    ``min_segment_m`` apart is no path of its own, and a piece whose line is
    still under ``min_segment_m`` (a pif folded on itself too tightly to cut)
    is dropped with its pips. Property boundaries play no part. The pieces
    seed their own growth, so the watershed meets them along the ground
    between rather than along a line this function draws.

    Args:
        labels: The pifs on their pips' cells, from 1; 0 elsewhere.
        cell_size_m: The cell size.
        max_span_m: The longest a piece may run along its path, in metres.
        max_bends: The most bends a piece may need; None cuts by length only.
        stray_tolerance_m: How far a piece's line may stray from its path.
        min_segment_m: The least distance between a piece's ends, and the
            shortest section of its line.
        max_turn_deg: The most a piece's line may turn in all.
        counts: Counts the pieces the length cap cut, by stage (``bends`` or
            ``even``; pifs take no boundary stage).

    Returns:
        ``(pieces, parent, lines)``: the pieces on their pips' cells, numbered
        from 1; the pif each piece came from, indexed by piece (entry 0 is
        0); and each piece's line as (row, column) points in metres, indexed
        by piece (entry 0 None).
    """
    rows, cols = np.nonzero(labels)
    pif = labels[rows, cols]
    if rows.size == 0:
        return labels.copy(), np.zeros(1, dtype=np.int64), [None]
    bends = max_bends if max_bends is not None else 10**6
    xy = np.column_stack([rows, cols]).astype(float) * cell_size_m
    order = np.argsort(pif, kind="stable")
    starts = np.flatnonzero(np.r_[True, np.diff(pif[order]) != 0])
    piece = np.zeros(rows.size, dtype=np.int64)
    parent = [0]
    lines: list[NDArray[np.float64] | None] = [None]
    for members in np.split(order, starts[1:]):
        points = xy[members]
        paths = (
            _pif_paths(points, cell_size_m=cell_size_m, min_branch_m=min_segment_m)
            if members.size > 2
            else [points]
        )
        stretches = [
            path[a : b + 1]
            for k, path in enumerate(paths)
            if k == 0 or np.hypot(*(path[-1] - path[0])) >= min_segment_m
            for a, b in cut_path(
                path,
                max_bends=max_bends,
                tolerance_m=stray_tolerance_m,
                min_segment_m=min_segment_m,
                max_length_m=max_span_m,
                max_turn_deg=max_turn_deg,
                counts=counts,
            )
            if b > a
        ]
        piece_lines = [
            bend_split.canonical_line(
                stretch,
                tolerance_m=stray_tolerance_m,
                max_bends=bends,
                min_segment_m=min_segment_m,
                max_turn_deg=max_turn_deg if max_bends is not None else math.inf,
            )
            for stretch in stretches
        ]
        if len(stretches) > 1:
            distance = shapely.distance(
                shapely.points(points)[:, None],
                np.array([shapely.LineString(t) for t in stretches], dtype=object)[
                    None, :
                ],
            )
            owner = distance.argmin(axis=1)
        else:
            owner = np.zeros(members.size, dtype=np.int64)
        for k, line in enumerate(piece_lines):
            mine = members[owner == k]
            if mine.size == 0:
                continue
            if shapely.LineString(line).length < min_segment_m - 1e-6:
                continue
            parent.append(int(pif[members[0]]))
            lines.append(line)
            piece[mine] = len(parent) - 1
    pieces = np.zeros_like(labels)
    pieces[rows, cols] = piece
    return pieces, np.array(parent, dtype=np.int64), lines


def drop_short_pifs(
    labels: NDArray[np.int32], cell_size_m: float, *, min_length_m: float
) -> tuple[NDArray[np.int32], int]:
    """Drop the pifs whose spine is shorter than ``min_length_m``, and renumber.

    The spine is the longest shortest path through the pif's pips
    (:func:`_longest_geodesic_path`). A shorter face is not a pif (the lead,
    2026-10-06, :data:`BETA_MIN_PIF_LENGTH_M`), as a cluster of fewer than
    :data:`BETA_MIN_PIF_PIPS` pips is not: its pips stay pips.

    Returns:
        ``(labels, n_dropped)``, the kept pifs numbered from 1 in their order.
    """
    rows, cols = np.nonzero(labels)
    if rows.size == 0:
        return labels.copy(), 0
    pif = labels[rows, cols]
    xy = np.column_stack([rows, cols]).astype(float) * cell_size_m
    order = np.argsort(pif, kind="stable")
    starts = np.flatnonzero(np.r_[True, np.diff(pif[order]) != 0])
    n_pifs = int(labels.max())
    keep = np.zeros(n_pifs + 1, dtype=bool)
    for members in np.split(order, starts[1:]):
        length = _longest_geodesic_path(xy[members])[1] if members.size > 1 else 0.0
        keep[pif[members[0]]] = length >= min_length_m - 1e-9
    number = np.zeros(n_pifs + 1, dtype=np.int32)
    number[keep] = np.arange(1, int(keep.sum()) + 1, dtype=np.int32)
    out = np.zeros_like(labels)
    out[rows, cols] = number[pif]
    present = np.zeros(n_pifs + 1, dtype=bool)
    present[np.unique(pif)] = True
    return out, int((present & ~keep).sum())


def gen_pif_near_drops(
    dem: ArrayLike,
    pips: Pips,
    pif_labels: NDArray[np.int32],
    cell_size_m: float,
    *,
    reach_m: float,
    quantile: float,
) -> pd.Series:
    """Each pif's wall height: a quantile of its pips' near drops.

    A pip's near drop is the fall from the pip to the lowest DEM cell within
    ``reach_m`` of it along its own fall direction (the cells 1 to 3 m below
    the pip that the pip test reads; the lead, 2026-10-06). It replaces the
    walk to the foot of the face (ground step 5), which runs on down a
    long batter or hillside and overstated the retained height. A cell off
    the grid or with no DEM is skipped; a pip with none in reach has no
    drop.

    Args:
        dem: Ground elevation in metres, NaN for nodata.
        pips: From :func:`find_pips`.
        pif_labels: The pifs on their pips' cells.
        cell_size_m: The cell size.
        reach_m: How far below the pip, along its fall, the drop is read.
        quantile: The quantile over a pif's pips (0.8 as run).

    Returns:
        The height per pif, indexed by ``pif_id``, NaN where no pip has a drop.
    """
    z = np.asarray(dem, dtype=float)
    height, width = z.shape
    rows, cols = np.nonzero(pips.mask & (pif_labels > 0))
    fall = pips.direction[rows, cols]
    lowest = np.full(rows.size, np.inf)
    max_k = max(1, int(reach_m // cell_size_m) + 1)
    for k in range(1, max_k + 1):
        reach = k * cell_size_m * np.hypot(_STEPS[fall, 0], _STEPS[fall, 1])
        r2 = rows + k * _STEPS[fall, 0]
        c2 = cols + k * _STEPS[fall, 1]
        ok = (reach <= reach_m + 1e-9) & (r2 >= 0) & (r2 < height)
        ok &= (c2 >= 0) & (c2 < width)
        below = np.full(rows.size, np.nan)
        below[ok] = z[r2[ok], c2[ok]]
        lowest = np.fmin(lowest, np.where(np.isfinite(below), below, np.inf))
    drop = np.where(np.isfinite(lowest), z[rows, cols] - lowest, np.nan)
    frame = pd.DataFrame({"pif_id": pif_labels[rows, cols], "drop": drop})
    return frame.groupby("pif_id")["drop"].quantile(quantile).rename("near_drop_p80_m")


def gen_pif_verticality(
    dem: ArrayLike,
    pips: Pips,
    pif_labels: NDArray[np.int32],
    *,
    cells: int = 3,
) -> pd.Series:
    """Each pif's verticality: how much of its drop is in the first cell.

    Per pip, the drop to the first cell along its own fall direction over the
    largest drop to any of the first ``cells`` cells (the lead, 2026-10-07):
    near 1 for a step or a wall, under 0.5 for a batter, whose fall goes on
    evenly. Per pif, the median over its pips. A cell off the grid or with no
    DEM is skipped; a pip with no drop has none.

    Returns:
        The verticality per pif, indexed by ``pif_id``, named ``verticality``.
    """
    z = np.asarray(dem, dtype=float)
    height, width = z.shape
    rows, cols = np.nonzero(pips.mask & (pif_labels > 0))
    fall = pips.direction[rows, cols]
    drops = np.full((cells, rows.size), np.nan)
    for k in range(1, cells + 1):
        r2 = rows + k * _STEPS[fall, 0]
        c2 = cols + k * _STEPS[fall, 1]
        ok = (r2 >= 0) & (r2 < height) & (c2 >= 0) & (c2 < width)
        below = np.full(rows.size, np.nan)
        below[ok] = z[r2[ok], c2[ok]]
        drops[k - 1] = z[rows, cols] - below
    with np.errstate(invalid="ignore", divide="ignore"):
        largest = np.nanmax(np.where(np.isfinite(drops), drops, -np.inf), axis=0)
        ratio = np.where(largest > 0, drops[0] / largest, np.nan)
    frame = pd.DataFrame({"pif_id": pif_labels[rows, cols], "ratio": ratio})
    return frame.groupby("pif_id")["ratio"].median().rename("verticality")


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


def _fall_line_stats(
    z: NDArray[np.float64],
    rows: NDArray[np.intp],
    cols: NDArray[np.intp],
    fall: NDArray[np.int8],
    owner: NDArray[np.int64],
    pif_group: NDArray[np.intp],
    n_pifs: int,
    cell_size_m: float,
    *,
    pif_labels: NDArray[np.int32],
    downhill: tuple[NDArray[np.float64], NDArray[np.float64]] | None = None,
) -> NDArray[np.float64]:
    """The siz statistics of every pif from its pips' fall lines.

    Each pip is read against the ground down its fall line, one cell length
    at a time out to :data:`MAX_PAIR_M`, each step rounded to the nearest
    cell. The fall line is the true downhill direction at the pip, from
    ``downhill`` (``terrain_layers``' ``downhill_row`` and ``downhill_col``,
    a unit vector per cell); where that is missing (level ground, or no
    ``downhill`` given) it is the pip's own fall direction, the nearest of
    the eight. The drop to each cell is the pip's height less the cell's, and
    its distance the straight line between their centres.

    A fall line stops at the toe of the pip's own face: it reads no further
    than the largest of :data:`PIP_OFFSETS_M` past the last cell of the pip's
    pif it crossed, the reach the pair test's support points have, so the drop
    is the face's and not the hillside's below it.

    A pif's statistics are the maxima over its pips, in the layout of
    :func:`_pair_stats`: the steepest angle over cells at least
    :data:`NEAR_PAIR_M` away whose drop is under / at least
    :data:`BAND_SPLIT_M`, the largest drop, and whether a cell under
    :data:`NEAR_PAIR_M` away is down by the pif's ground group's
    ``adjacent_step_m``. Only drops count; a cell off the DEM or up the
    slope is skipped.

    Returns:
        An array of shape ``(n_pifs, 4)``: ``max_below``, ``max_above``,
        ``max_delta_h``, ``near_pass``, one row per pif from 1.
    """
    height, width = z.shape
    steps = _STEPS[fall].astype(float)
    unit_row = steps[:, 0] / np.hypot(steps[:, 0], steps[:, 1])
    unit_col = steps[:, 1] / np.hypot(steps[:, 0], steps[:, 1])
    if downhill is not None:
        true_row = downhill[0][rows, cols]
        true_col = downhill[1][rows, cols]
        known = np.isfinite(true_row) & np.isfinite(true_col)
        unit_row = np.where(known, true_row, unit_row)
        unit_col = np.where(known, true_col, unit_col)
    reach = math.ceil(MAX_PAIR_M / cell_size_m)
    k = np.arange(1, reach + 1)
    r2 = rows[:, None] + np.rint(k[None, :] * unit_row[:, None]).astype(np.intp)
    c2 = cols[:, None] + np.rint(k[None, :] * unit_col[:, None]).astype(np.intp)
    dist = cell_size_m * np.hypot(r2 - rows[:, None], c2 - cols[:, None])
    inside = (r2 >= 0) & (r2 < height) & (c2 >= 0) & (c2 < width)
    inside &= (dist > 0) & (dist <= MAX_PAIR_M + 1e-9)
    on_face = np.zeros(r2.shape, dtype=bool)
    on_face[inside] = pif_labels[r2[inside], c2[inside]] == owner.repeat(
        inside.sum(axis=1)
    )
    last = np.maximum.accumulate(np.where(on_face, dist, 0.0), axis=1)
    inside &= dist - last <= max(PIP_OFFSETS_M) + 1e-9
    below = np.full(r2.shape, np.nan)
    below[inside] = z[r2[inside], c2[inside]]
    drop = z[rows, cols][:, None] - below
    valid = np.isfinite(drop) & (drop > 0)
    drop = np.where(valid, drop, 0.0)
    angle = np.where(
        valid, np.degrees(np.arctan2(drop, np.where(dist > 0, dist, 1.0))), 0.0
    )
    near = dist < NEAR_PAIR_M
    high = drop >= BAND_SPLIT_M
    per_pip = np.column_stack(
        [
            np.where(~near & ~high, angle, 0.0).max(axis=1),
            np.where(~near & high, angle, 0.0).max(axis=1),
            drop.max(axis=1),
            np.where(near, drop, 0.0).max(axis=1),
        ]
    )
    stats = np.zeros((n_pifs + 1, 4))
    for column in range(4):
        np.maximum.at(stats[:, column], owner, per_pip[:, column])
    step_by_pif = np.array(
        [ADJACENT_STEP_M[GROUND_GROUPS[g]] for g in pif_group], dtype=float
    )
    stats[:, 3] = stats[:, 3] >= step_by_pif
    return stats[1:]


def assess_pifs(
    dem: ArrayLike,
    pips: Pips,
    pif_labels: NDArray[np.int32],
    ground_group: ArrayLike,
    transform: Affine,
    *,
    test: str = PAIRS_TEST,
    downhill: tuple[NDArray[np.float64], NDArray[np.float64]] | None = None,
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
        test: :data:`PAIRS_TEST` to compare every pair of a pif's points, or
            :data:`FALL_LINE_TEST` to read each pip's drop down its fall line
            (:func:`_fall_line_stats`). The columns are the same either way.
        downhill: For the fall-line test, the true downhill direction of every
            cell (``terrain_layers``' ``downhill_row`` and ``downhill_col``);
            without it each pip falls along the nearest of the eight.

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
    rows, cols = np.nonzero(pips.mask & (pif_labels > 0))
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

    if test == FALL_LINE_TEST:
        stats = _fall_line_stats(
            z,
            rows,
            cols,
            fall,
            owner,
            pif_group,
            n_pifs,
            cell_size_m,
            pif_labels=pif_labels,
            downhill=downhill,
        )
    elif test == PAIRS_TEST:
        stats = np.zeros((n_pifs, 4))
        for i, pif in enumerate(index):
            lo, hi = ends[pif - 1], ends[pif]
            group = GROUND_GROUPS[pif_group[pif]]
            stats[i] = _pair_stats(
                all_xy[lo:hi], all_z[lo:hi], step_m=ADJACENT_STEP_M[group]
            )
    else:
        known = (PAIRS_TEST, FALL_LINE_TEST)
        msg = f"Unknown siz test {test!r}; choose one of {known}."
        raise ValueError(msg)
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
        pif_labels: The pifs on their pips' cells: the pieces of
            :func:`split_pifs`, each a pif of its own since 2026-10-06.
        sizs: The siz table, one row per pif piece (:func:`assess_pifs` on the pieces),
            with ``parent_pif_id``.
        n_pifs_excluded: The pifs dropped on the ``exclude`` mask of
            :func:`find_instability_zones` (building outlines).
        n_pifs_short: The pifs dropped for a spine under
            :data:`BETA_MIN_PIF_LENGTH_M`.
        pif_lines: Each pif piece's line, in map coordinates, indexed by
            ``pif_id``: the stretch of path :func:`split_pifs` cut it on.
        cap_cuts: The pieces the 50 m cap cut, by stage (``bends``,
            ``even``).
    """

    found: SlopeElements
    pips: Pips
    pif_labels: NDArray[np.int32]
    sizs: pd.DataFrame
    n_pifs_excluded: int = 0
    n_pifs_short: int = 0
    pif_lines: pd.Series | None = None
    cap_cuts: dict[str, int] | None = None


def find_instability_zones(
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    *,
    categories: Mapping[str, ArrayLike] | None = None,
    core: ArrayLike | None = None,
    exclude: ArrayLike | None = None,
    max_bends: int | None = None,
    stray_tolerance_m: float = 0.0,
    min_segment_m: float = 0.0,
    max_turn_deg: float = math.inf,
    siz_test: str = FALL_LINE_TEST,
) -> InstabilityZones:
    """Find the pips, pifs and sizs on a DEM and grow the sizs into elements.

    Each siz's pips seed the watershed growth of the old free-face pass, into
    cells steeper than the siz's own threshold angle less
    :data:`~landloss.hazard.landslide.slope_elements.BETA_FREE_FACE_GROW_TOL_DEG`
    (so material enters only here). Every grown region is kept as an element
    (the lead, 2026-10-06: every siz is a wall candidate, and a wall must have
    a polygon), including one the junk filters of
    :func:`landloss.hazard.landslide.slope_elements.find_slope_elements` would
    drop (under 0.5 m high, under 3 m long, gentler overall than 18.4 degrees,
    no transect); such an element has ``kept_by_rule`` False, a height of at
    least 0.5 m and, with no transect, a run of 0
    (:func:`landloss.hazard.landslide.slope_elements._measure_regardless`).
    The siz decision is made on the pif; a grown element is not re-tested.

    Args:
        dem: Ground elevation in metres on a north-up grid of square cells,
            NaN for nodata and outside the LiDAR.
        ground_group: The ground group code of every cell, with fill as soil
            (``rasterise_ground_map(..., fill_as_soil=True)``).
        transform: The grid's affine transform.
        categories: Integer grids to take the majority of over each element.
        core: A tile's core, as in ``find_slope_elements``.
        exclude: True on cells no pif may stand on (the step passes the LINZ
            building outlines): a pif most of whose pips are on them is
            dropped before the siz test (:func:`exclude_pifs`), so it is no
            siz, element or wall candidate. Its pips stay pips.
        max_bends: The bends rule :func:`split_pifs` cuts the pifs by (the
            step passes the walls' ``WALL_MAX_BENDS``); None cuts them only
            at :data:`MAX_PIF_SPAN_M`.
        stray_tolerance_m: How far a piece's line may stray from the spine.
        min_segment_m: The shortest piece.
        max_turn_deg: The most a piece's line may turn in all.
        siz_test: The siz test each piece is put to (:func:`assess_pifs`):
            :data:`FALL_LINE_TEST`, or :data:`PAIRS_TEST` for comparison.

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
    n_excluded = 0
    if exclude is not None:
        pif_labels, _, n_excluded = exclude_pifs(pif_labels, exclude)
    pif_labels, n_short = drop_short_pifs(
        pif_labels, cell_size_m, min_length_m=BETA_MIN_PIF_LENGTH_M
    )
    # The pifs are the pieces from here on: the siz table, the elements' siz_id
    # and the wall candidates all name a piece (the lead, 2026-10-06), and each
    # piece is tested on its own pips (the lead, 2026-10-08).
    pif_labels, parent, piece_xy = split_pifs(
        pif_labels,
        cell_size_m,
        max_span_m=MAX_PIF_SPAN_M,
        max_bends=max_bends,
        stray_tolerance_m=stray_tolerance_m,
        min_segment_m=min_segment_m,
        max_turn_deg=max_turn_deg,
        counts=(cap_cuts := Counter()),
    )
    sizs = assess_pifs(
        elevation,
        pips,
        pif_labels,
        groups,
        transform,
        test=siz_test,
        downhill=(layers.downhill_row, layers.downhill_col),
    )
    sizs.insert(0, "parent_pif_id", parent[sizs.index.to_numpy()].astype(np.int64))
    pif_lines = pd.Series(
        [
            shapely.LineString(
                np.column_stack(
                    [
                        transform.c + (xy[:, 1] / cell_size_m + 0.5) * transform.a,
                        transform.f + (xy[:, 0] / cell_size_m + 0.5) * transform.e,
                    ]
                )
            )
            for xy in piece_xy[1:]
        ],
        index=pd.RangeIndex(1, len(piece_xy), name="pif_id"),
        dtype=object,
    ).reindex(sizs.index)
    breaks = {
        pif: broken
        for pif, line in pif_lines.items()
        if (
            broken := bend_split.rule_breaks(
                line,
                max_bends=max_bends if max_bends is not None else 10**6,
                min_length_m=min_segment_m,
                max_length_m=MAX_PIF_SPAN_M,
                max_turn_deg=max_turn_deg if max_bends is not None else math.inf,
            )
        )
    }
    if breaks:
        msg = (
            f"{len(breaks)} pif pieces break the line rules: {list(breaks.items())[:5]}"
        )
        raise ValueError(msg)

    band = height_band(np.nan_to_num(layers.step_height_m, nan=0.0))
    threshold = step_angle_deg(groups, band)
    exceedance = layers.slope_coarse_deg - threshold
    is_siz_piece = (
        sizs["is_siz"].astype(bool).reindex(np.arange(parent.size), fill_value=False)
    )
    siz_pieces = np.flatnonzero(is_siz_piece.to_numpy())
    n_seeds = int(siz_pieces.size)
    lookup = np.zeros(parent.size, dtype=np.int32)
    lookup[siz_pieces] = np.arange(1, n_seeds + 1, dtype=np.int32)
    seeds = lookup[pif_labels]
    if n_seeds:
        limit = np.zeros(n_seeds + 1)
        limit[1:] = (
            sizs.loc[siz_pieces, "threshold_angle_deg"].to_numpy()
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
        keep_all=True,
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
        n_pifs_excluded=n_excluded,
        n_pifs_short=n_short,
        pif_lines=pif_lines,
        cap_cuts=dict(cap_cuts),
    )


def add_line_elements(
    found: SlopeElements,
    lines: gpd.GeoSeries,
    height_m: pd.Series,
    *,
    dem: ArrayLike,
    ground_group: ArrayLike,
    transform: Affine,
    categories: Mapping[str, ArrayLike] | None = None,
) -> SlopeElements:
    """Add an element on each wall line that no siz grew one for.

    A GNS-only wall unit has no pif, and a ``low_height`` pif piece (a GNS mapped wall
    on a pif that is not a siz) seeds no growth, so no element is under either and its
    wall would have no polygon. The lead (2026-10-06): every wall gets one, so each such
    unit gets the minimum polygon along its line: its line is burnt onto the grid (every
    cell it touches that no element holds and the DEM covers) as an element of its own,
    and the polygon builder treats it as any other: its crest cells are the ones whose
    uphill neighbour is off it, so the DEM decides which side is up, and the width
    behind the crest is the floor, ``max(0.5 H, 1 m)``
    (:func:`landloss.hazard.landslide.slope_polygons.min_evacuated_width_m`).

    Its height is the unit's step height (``height_m``), never under
    :data:`~landloss.domain.constants.MIN_WALL_HEIGHT_M` (the smallest
    element's; a GNS-only piece's step is often 0.4 to 0.5 m or unread), with
    a run of 0 (a step), so its overall angle is 90 degrees. Walled, its depth
    is the wall's planar slip, ``0.5 H w`` per metre; bare, it is a bank, and
    takes the fill thickness or the cover depth of the polygon builder.

    The elements are measured again on the new grid
    (:func:`landloss.hazard.landslide.slope_elements._assemble_elements`, so
    the stack links, catchments and edge roles see the new ones), and the
    existing elements keep their labels and every column they had.

    Args:
        found: The elements from :func:`find_instability_zones`.
        lines: The wall lines, indexed by ``wall_unit_id``, in the grid's CRS.
        height_m: The step height of each line, indexed like ``lines``.
        dem: The DEM the elements were found on.
        ground_group: The ground group grid they were found with.
        transform: The grid's affine transform.
        categories: As in :func:`find_instability_zones`.

    Returns:
        The elements with one more per line that kept a cell, numbered after
        the existing ones, ``grown_in`` :data:`WALL_LINE`, ``siz_id`` 0 and
        ``wall_unit_id`` (None on the existing elements).
    """
    elevation = np.asarray(dem, dtype=float)
    groups = np.asarray(ground_group, dtype=np.int8)
    old = found.elements
    n_old = len(old)
    labels = found.labels.copy()
    burnt = np.zeros(labels.shape, dtype=np.int32)
    if len(lines):
        burnt = features.rasterize(
            [
                (geometry, n_old + 1 + k)
                for k, geometry in enumerate(lines.to_numpy())
                if geometry is not None and not geometry.is_empty
            ],
            out_shape=labels.shape,
            transform=transform,
            fill=0,
            all_touched=True,
            dtype="int32",
        )
    free = (labels == OUTSIDE) & np.isfinite(elevation)
    burnt = np.where(free, burnt, 0)
    kept = np.unique(burnt[burnt > 0]) - n_old - 1
    if kept.size == 0:
        return replace(found, elements=old.assign(wall_unit_id=None))
    number = np.zeros(n_old + len(lines) + 1, dtype=np.int32)
    number[kept + n_old + 1] = np.arange(n_old + 1, n_old + 1 + kept.size)
    labels = np.where(burnt > 0, number[burnt], labels).astype(np.int32)
    n_labels = n_old + kept.size

    seed_grid = np.where(burnt > 0, labels, OUTSIDE).astype(np.int32)
    seeded = old["seed_row"].to_numpy() >= 0
    seed_grid[
        old["seed_row"].to_numpy()[seeded], old["seed_col"].to_numpy()[seeded]
    ] = old.index.to_numpy()[seeded]
    grown_in = np.r_[
        [""], old["grown_in"].to_numpy(dtype=object), [WALL_LINE] * kept.size
    ]
    result = _assemble_elements(
        elevation,
        groups,
        transform,
        found.layers,
        labels,
        seed_grid,
        np.zeros(labels.shape),
        grown_in,
        np.full(n_labels + 1, FREE_FACE),
        np.ones(labels.shape, dtype=bool),
        categories,
        keep_all=True,
    )
    elements = result.elements.copy()
    new = elements.index > n_old
    for column in old.columns:
        if column not in elements.columns:
            elements[column] = pd.Series(np.nan, index=elements.index, dtype=object)
        elements.loc[~new, column] = old[column].to_numpy()
    height = np.fmax(
        height_m.reindex(lines.index).to_numpy(dtype=float)[kept], MIN_WALL_HEIGHT_M
    )
    band = height_band(height)
    threshold = np.asarray(
        step_angle_deg(
            elements.loc[new, "ground_group"].map(GROUND_GROUPS.index), band
        ),
        dtype=float,
    )
    elements.loc[new, "height_m"] = height
    elements.loc[new, "height_max_m"] = height
    elements.loc[new, "run_m"] = 0.0
    elements.loc[new, "overall_angle_deg"] = 90.0
    elements.loc[new, "height_band"] = band
    elements.loc[new, "threshold_angle_deg"] = threshold
    elements.loc[new, "angle_excess_deg"] = 90.0 - threshold
    elements.loc[new, "stack_dominant_cut"] = height > STACK_DOMINANT_HEIGHT_M
    elements.loc[new, "hb1995_cut"] = height > HB1995_CUT_HEIGHT_M
    elements.loc[new, "siz_id"] = 0
    elements["siz_id"] = elements["siz_id"].astype(np.int64)
    wall_unit = np.full(len(elements), None, dtype=object)
    wall_unit[new] = lines.index.to_numpy(dtype=object)[kept]
    elements["wall_unit_id"] = wall_unit
    return replace(result, elements=elements)


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
        MultiPoint of the pif's pip cell centres and ``pip_direction``: each
        pip's fall direction as an index into :data:`DIRECTIONS` (int8), in the
        same order as the MultiPoint's points.
    """
    rows, cols = np.nonzero(result.pips.mask & (result.pif_labels > 0))
    points = pd.DataFrame(
        {
            "x": transform.c + (cols + 0.5) * transform.a,
            "y": transform.f + (rows + 0.5) * transform.e,
            "pif_id": result.pif_labels[rows, cols],
            "direction": result.pips.direction[rows, cols],
        }
    )
    # groupby keeps the row order within a group, so a pif's directions line
    # up with the points of its MultiPoint.
    groups = points.groupby("pif_id")
    geometry = gpd.GeoSeries(
        {
            pif: shapely.MultiPoint(group[["x", "y"]].to_numpy())
            for pif, group in groups
        },
        crs=crs,
    ).reindex(result.sizs.index)
    pip_direction = pd.Series(
        {pif: group["direction"].to_numpy(dtype=np.int8) for pif, group in groups},
        dtype=object,
    ).reindex(result.sizs.index)
    return gpd.GeoDataFrame(
        result.sizs.assign(pip_direction=pip_direction), geometry=geometry, crs=crs
    )


SPINE_COLUMNS = (
    "spine",
    "spine_length_m",
    "end_a_x",
    "end_a_y",
    "end_b_x",
    "end_b_y",
    "end_a_fall_deg",
    "end_b_fall_deg",
    "fall_resultant",
)


def _longest_geodesic_path(
    xy: NDArray[np.float64],
) -> tuple[NDArray[np.int64], float]:
    """The longest shortest path through three or more pips, end to end.

    The graph joins pips within :data:`PIF_JOIN_M`, the radius
    :func:`cluster_pifs` used, so a pif is one component; if it is not, the
    largest component is kept. The two ends are found by a double sweep on the
    graph's geodesic distance: the pip furthest from the lowest (x, y) pip,
    then the pip furthest from that; the path is the shortest between them.
    The sweep is run on the whole graph rather than on a spanning tree,
    because on a face two or more cells thick the grid's many equal edge
    weights make the tree comb-like, and its longest path folds back down the
    next row with both ends at one end of the face.

    Returns:
        ``(path, length)``: the pips along the path, in order, and its length.
    """
    pairs = cKDTree(xy).query_pairs(PIF_JOIN_M + 1e-9, output_type="ndarray")
    weight = np.hypot(*(xy[pairs[:, 0]] - xy[pairs[:, 1]]).T)
    graph = coo_matrix(
        (
            np.r_[weight, weight],
            (np.r_[pairs[:, 0], pairs[:, 1]], np.r_[pairs[:, 1], pairs[:, 0]]),
        ),
        shape=(len(xy), len(xy)),
    ).tocsr()
    n_parts, part = connected_components(graph, directed=False)
    nodes = np.arange(len(xy))
    if n_parts > 1:
        nodes = np.flatnonzero(part == np.bincount(part).argmax())
    start = nodes[np.lexsort((xy[nodes, 1], xy[nodes, 0]))[0]]
    dist = dijkstra(graph, directed=False, indices=start)
    end_a = int(np.argmax(np.where(np.isfinite(dist), dist, -1.0)))
    dist, predecessors = dijkstra(
        graph, directed=False, indices=end_a, return_predecessors=True
    )
    end_b = int(np.argmax(np.where(np.isfinite(dist), dist, -1.0)))
    path = [end_b]
    while path[-1] != end_a:
        path.append(int(predecessors[path[-1]]))
    return np.array(path[::-1], dtype=np.int64), float(dist[end_b])


def _mean_fall_deg(sin: NDArray[np.float64], cos: NDArray[np.float64]) -> float:
    """The circular mean of fall directions, in degrees from north."""
    return float(np.degrees(np.arctan2(sin.sum(), cos.sum())) % 360.0)


def gen_pif_spines(
    sizs: gpd.GeoDataFrame,
    *,
    cell_size_m: float,
    end_window_m: float,
    lines: pd.Series | None = None,
) -> pd.DataFrame:
    """The spine of every pif and the fall direction at each of its ends.

    One bearing per pif (``fall_bearing_deg``) means nothing on an L-shaped or
    curved pif and cancels on a U around a platform, so pieces of one wall
    cannot be joined end to end on it. The spine is the longest shortest path
    through the pif's pips, joined within :data:`PIF_JOIN_M`, found by a double
    sweep (:func:`_longest_geodesic_path`); its two ends, and the mean fall
    direction of the pips near each, are what joining compares. Bearings are
    degrees from north (0 is north, the sine is east), as in
    :func:`assess_pifs`.

    Args:
        sizs: The siz table from :func:`gen_siz_table`: a MultiPoint of pip
            centres and ``pip_direction``.
        cell_size_m: The cell size; a one-pip pif's spine is one cell long,
            across its fall.
        lines: Each pif's line, indexed like ``sizs``
            (:attr:`InstabilityZones.pif_lines`): where given, the spine is
            that line, the stretch of path the piece was cut on, not a path
            found again through its pips.
        end_window_m: The fall direction at an end is the mean over the pips
            within this many metres of it.

    Returns:
        A frame indexed like ``sizs`` with ``spine`` (a LineString, in the CRS
        of ``sizs``), ``spine_length_m``, ``end_a_x``, ``end_a_y``, ``end_b_x``,
        ``end_b_y`` (end a is the end with the smaller (x, y)),
        ``end_a_fall_deg``, ``end_b_fall_deg`` and ``fall_resultant`` (the mean
        resultant length of the pips' fall vectors: 1 for a straight face,
        lower the more it bends).

    Raises:
        ValueError: If ``pip_direction`` does not have one entry per pip.
    """
    geometries = sizs.geometry.to_numpy()
    xy = shapely.get_coordinates(geometries)
    counts = shapely.get_num_geometries(geometries)
    directions = [np.asarray(d, dtype=np.int64) for d in sizs["pip_direction"]]
    if any(len(d) != k for d, k in zip(directions, counts, strict=True)):
        msg = "pip_direction needs one direction per pip of every pif."
        raise ValueError(msg)
    direction = np.concatenate([np.zeros(0, dtype=np.int64), *directions])
    theta = np.radians(BEARING_DEG[direction])
    sin, cos = np.sin(theta), np.cos(theta)

    n = len(sizs)
    spines = [None] * n
    values = np.full((n, len(SPINE_COLUMNS) - 1), np.nan)
    starts = np.r_[0, np.cumsum(counts)]
    for i in range(n):
        lo, hi = starts[i], starts[i + 1]
        k = hi - lo
        if k == 0:
            continue
        pts, s, c = xy[lo:hi], sin[lo:hi], cos[lo:hi]
        given = None if lines is None else lines.get(sizs.index[i])
        if given is not None and not shapely.is_empty(given):
            line = np.asarray(given.coords)
            length = float(given.length)
        elif k == 1:
            # One cell long, across the fall: the fall is (sin, cos), so
            # (cos, -sin) runs along the face.
            across = np.array([c[0], -s[0]]) * 0.5 * cell_size_m
            line, length = np.array([pts[0] - across, pts[0] + across]), cell_size_m
        elif k == 2:
            line, length = pts, float(np.hypot(*(pts[1] - pts[0])))
        else:
            path, length = _longest_geodesic_path(pts)
            line = pts[path]
        if tuple(line[-1]) < tuple(line[0]):
            line = line[::-1]
        falls = []
        for end in (line[0], line[-1]):
            gap = np.hypot(*(pts - end).T)
            near = gap <= end_window_m
            if k == 1:
                near[:] = True
            if not near.any():
                near = gap == gap.min()
            falls.append(_mean_fall_deg(s[near], c[near]))
        spines[i] = shapely.LineString(line)
        values[i] = [
            length,
            *line[0],
            *line[-1],
            *falls,
            np.hypot(s.sum(), c.sum()) / k,
        ]

    frame = pd.DataFrame(values, index=sizs.index, columns=list(SPINE_COLUMNS[1:]))
    frame.insert(0, "spine", gpd.GeoSeries(spines, index=sizs.index, crs=sizs.crs))
    return frame


def write_siz_table(table: gpd.GeoDataFrame, path: Path) -> None:
    """Write the siz table as GeoParquet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(path)


def read_siz_table(path: Path) -> gpd.GeoDataFrame:
    """Read a siz table written by :func:`write_siz_table`."""
    return gpd.read_parquet(path)
