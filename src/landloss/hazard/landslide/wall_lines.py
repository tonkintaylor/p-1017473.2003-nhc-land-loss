"""The wall line along a pif's downhill outline, and the pips the wall holds.

The lead's method (2026-10-13, "option 10", settled on 120 cases and the
wlg-pilot), in two parts:

1. **The line** (:func:`wall_line`). The pif's cell outline (its pips and the
   cell each falls to at 1 m, as 1 m squares, :func:`cell_outline`) is walked
   every ``outline_step_m``. Each sample's outward normal is read off the
   outline ``normal_half_window_m`` either side, and the local fall off the
   pips within ``fall_radius_m``. The longest run of samples whose normal is
   within 45 degrees of the fall (widened to 60, 75 or 90 only when no run is
   ``min_run_m`` long) is the toe; gaps in it shorter than a join gap are
   bridged, each of ``join_gaps_m`` tried in turn. Each run is regularised by
   :func:`fit_polyline` (0 to ``max_bends`` bends, sections of
   ``min_segment_m`` or more, no bend over ``max_bend_deg``, at most
   ``max_total_turn_deg`` of turning), short end hooks are cut
   (:func:`trim_hooks`), and the candidate with the fewest pips beyond it
   downhill, with penalties for a poor fit, a chord across a notch, bends and S
   jogs, is kept. A pif with no downhill run keeps the fallback line.
2. **The pips the wall holds** (:func:`wall_pieces`). A pip is on the wall when
   its fall, widened ``cone_half_angle_deg`` either side and ``cone_reach_m``
   long, meets the line. The other pips are grouped (up to
   ``leftover_join_m`` apart, so a one-cell gap does not split a group); a
   group of more than ``min_no_wall_pips`` is a pif with no wall, a smaller
   one goes back to the wall's pif, and so does one with more than
   ``enclosed_share`` of its edge on the wall's pif. The wall's pif must touch
   (8-connected, :func:`cut_off`): a group of wall pips within ``stay_m`` of
   the line stays, any other joins the no-wall pif it touches, or is one of
   its own when over ``min_no_wall_pips`` pips.

Every setting is a field of :class:`WallLineSettings`; the values live in
ground step 3's config and are passed in, so this module holds no default.
"""

import math
from dataclasses import dataclass

import numpy as np
import shapely
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from landloss.hazard.landslide.directions import STEP_XY

# A step along each of the eight fall directions as (x, y) in cells: a step
# down the grid's rows is a step south.
UNIT_XY = STEP_XY / np.hypot(*STEP_XY.T)[:, None]

# Rows of the (i, j, p) cost cube the fit computes at once, to bound memory.
PAIR_BLOCK = 48
# Distances and lengths under this are zero.
_EPS = 1e-9
# The angle above which the line's method is "outline-wide".
_NARROW_ANGLE_DEG = 60.0
# The label of the pips the wall holds.
WALL_LABEL = 0
# What the pips of a unit with no downhill run are told.
_NO_RUN_NOTE = "no downhill run on the outline"

METHOD_OUTLINE = "outline"
METHOD_OUTLINE_WIDE = "outline-wide"
METHOD_FALLBACK = "fallback"

HOW_CONE = "cone"
HOW_MERGED_BACK = "merged back"
HOW_CUT_OFF = "cut off"
HOW_LEFT_OVER = "left over"


@dataclass(frozen=True)
class WallLineSettings:
    """Every setting of the wall line and of the pips it holds.

    The values are ground step 3's (``config.py``); see there for what each
    does. Lengths are metres and angles degrees unless the name says otherwise.

    Attributes:
        outline_step_m: Spacing of the samples walked round the outline.
        normal_half_window_m: Distance either side the outward normal is read.
        fall_radius_m: Radius of the pips whose falls give a sample's fall.
        normal_angles_deg: Angles a normal may be off the fall, tried in turn.
        min_run_m: The shortest toe run.
        join_gaps_m: Gaps in the run bridged, each tried in turn.
        max_length_m: The longest run kept.
        fit_step_m: Spacing of the samples the line is fitted on.
        max_bends: Most bends the line may have.
        min_segment_m: Shortest straight section (a straight line is exempt).
        max_bend_deg: The sharpest bend.
        max_total_turn_deg: The most turning in all.
        bend_penalty_m2: The cost of a bend, in m2 of area off the path.
        bend_length_scale_m: Length that doubles the cost of a bend.
        fit_loss_scale_m: Scale of the polish's soft L1 loss.
        refine_reach_m: The furthest the polish moves a vertex.
        refine_max_nfev: Evaluations the polish may take.
        hook_m: An end section shorter than this is a hook.
        hook_sharp_m: An end section shorter than this and turning more than
            ``hook_sharp_deg`` is a hook.
        hook_sharp_deg: See ``hook_sharp_m``.
        beyond_m: A pip further than this past the line, downhill, is beyond.
        beyond_ok: A score at or under this ends the search.
        rms_ok_m: A fit's rms from its run is free up to this.
        rms_weight: Score per metre of rms beyond ``rms_ok_m``.
        chord_ok_m: A line's deviation from its run is free up to this.
        chord_weight: Score per metre of deviation beyond ``chord_ok_m``.
        bend_score: Score per bend.
        jog_m: An S jog has a middle section shorter than this.
        jog_score: Score per S jog.
        cone_half_angle_deg: How far either side of its fall a pip's cone opens.
        cone_reach_m: The length of a pip's cone.
        cone_arc_n: Vertices on a cone's arc.
        leftover_join_m: Leftover pips this close are one group.
        min_no_wall_pips: A leftover group needs more pips than this to be a
            pif with no wall.
        enclosed_share: A group with more than this share of its edge on the
            wall's pif goes back to it.
        edge_buffer_m: How close an edge must be to lie on a pif.
        wall_join_m: Wall pips this close are one group.
        stay_m: A group of wall pips this close to the line stays.
    """

    outline_step_m: float
    normal_half_window_m: float
    fall_radius_m: float
    normal_angles_deg: tuple[float, ...]
    min_run_m: float
    join_gaps_m: tuple[float, ...]
    max_length_m: float
    fit_step_m: float
    max_bends: int
    min_segment_m: float
    max_bend_deg: float
    max_total_turn_deg: float
    bend_penalty_m2: float
    bend_length_scale_m: float
    fit_loss_scale_m: float
    refine_reach_m: float
    refine_max_nfev: int
    hook_m: float
    hook_sharp_m: float
    hook_sharp_deg: float
    beyond_m: float
    beyond_ok: float
    rms_ok_m: float
    rms_weight: float
    chord_ok_m: float
    chord_weight: float
    bend_score: float
    jog_m: float
    jog_score: float
    cone_half_angle_deg: float
    cone_reach_m: float
    cone_arc_n: int
    leftover_join_m: float
    min_no_wall_pips: int
    enclosed_share: float
    edge_buffer_m: float
    wall_join_m: float
    stay_m: float


@dataclass
class _Unit:
    """What the line and the cones need of one pif piece."""

    pips: np.ndarray
    fall_vectors: np.ndarray
    mean_fall: np.ndarray


@dataclass
class Fit:
    """A regularised line and how it was chosen.

    Attributes:
        line: The fitted line.
        vertices: Its vertices.
        k: Its number of bends.
        rms: Root mean square distance of the path to the line.
        cost: The chosen option's cost, bend penalty included.
        costs: Fit cost by bend count (inf where the limits could not be kept).
        ok: False where no fit kept the limits and a straight line was returned.
    """

    line: shapely.LineString
    vertices: np.ndarray
    k: int
    rms: float
    cost: float
    costs: dict[int, float]
    ok: bool


def _unit(pips: np.ndarray, pip_direction: np.ndarray) -> _Unit:
    """The pips with their fall vectors and the mean fall."""
    fall = UNIT_XY[np.asarray(pip_direction, dtype=int)]
    mean = fall.mean(axis=0)
    return _Unit(np.asarray(pips, dtype=float), fall, mean / np.hypot(*mean))


# ------------------------------------------------------------------ outline


def cell_outline(points: np.ndarray) -> shapely.Polygon:
    """The union of 1 m squares centred on the points, lightly closed.

    Closed with a mitre buffer of +0.5 then -0.5 so single cell notches do not
    fragment it; the largest part, holes removed. Each row's runs of touching
    cells become one box before the union, rather than a square per cell.

    Args:
        points: ``(n, 2)`` cell centres (x, y).

    Returns:
        The outline polygon.
    """
    xy = np.atleast_2d(points)
    cells = np.unique(np.floor(xy).astype(np.int64), axis=0)
    cells = cells[np.lexsort((cells[:, 0], cells[:, 1]))]
    new_run = np.r_[True, (np.diff(cells[:, 1]) != 0) | (np.diff(cells[:, 0]) != 1)]
    first = np.flatnonzero(new_run)
    last = np.r_[first[1:] - 1, len(cells) - 1]
    union = shapely.union_all(
        shapely.box(
            cells[first, 0], cells[first, 1], cells[last, 0] + 1, cells[last, 1] + 1
        )
    )
    closed = union.buffer(0.5, join_style="mitre").buffer(-0.5, join_style="mitre")
    if closed.is_empty:
        closed = union
    parts = list(getattr(closed, "geoms", [closed]))
    biggest = max(parts, key=lambda p: p.area)
    return shapely.Polygon(biggest.exterior)


# -------------------------------------------------------------- regulariser


def densify(xy: np.ndarray, step: float = 0.5) -> np.ndarray:
    """An ordered polyline's points resampled every ``step`` m along it.

    Args:
        xy: ``(n, 2)`` ordered points.
        step: The spacing.

    Returns:
        The resampled points (the input when it has fewer than two distinct points).
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        return xy
    keep = np.r_[True, np.hypot(*np.diff(xy, axis=0).T) > _EPS]
    xy = xy[keep]
    if len(xy) < 2:
        return xy
    line = shapely.LineString(xy)
    n = max(math.ceil(line.length / step), 1) + 1
    return shapely.get_coordinates(
        shapely.line_interpolate_point(line, np.linspace(0, line.length, n))
    )


def turns_deg(vertices: np.ndarray) -> np.ndarray:
    """How far the line turns at each inner vertex, degrees (0 straight on)."""
    v = np.asarray(vertices, dtype=float)
    if len(v) < 3:
        return np.zeros(0)
    heading = np.arctan2(*np.diff(v, axis=0)[:, ::-1].T)
    return np.degrees(np.abs((np.diff(heading) + math.pi) % (2 * math.pi) - math.pi))


def section_lengths(vertices: np.ndarray) -> np.ndarray:
    """The length of each straight section."""
    return np.hypot(*np.diff(np.asarray(vertices, dtype=float), axis=0).T)


def _pair_costs(
    path: np.ndarray, spacing: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cost of one section for every pair (i, j): the path against its chord.

    Vectorised over (i, j, p) in blocks of ``PAIR_BLOCK`` start samples.
    """
    n = len(path)
    d = path[None, :, :] - path[:, None, :]  # d[i, j] = path[j] - path[i]
    chord = np.hypot(d[..., 0], d[..., 1])
    heading = np.arctan2(d[..., 1], d[..., 0])
    unit = d / np.maximum(chord, 1e-12)[..., None]
    idx = np.arange(n)
    later = idx[None, :] > idx[:, None]
    chord = np.where(later, chord, 0.0)
    heading = np.where(later, heading, 0.0)
    cost = np.full((n, n), np.inf)
    for a in range(0, n, PAIR_BLOCK):
        b = min(a + PAIR_BLOCK, n)
        rel = d[a:b]  # rel[i, p] = path[p] - path[i]
        u = unit[a:b]
        along = np.einsum("ipk,ijk->ijp", rel, u)
        across = (
            rel[:, None, :, 0] * u[:, :, None, 1]
            - rel[:, None, :, 1] * u[:, :, None, 0]
        )
        beyond = np.maximum(np.maximum(-along, along - chord[a:b, :, None]), 0.0)
        dist = np.hypot(across, beyond)
        i = idx[a:b, None, None]
        inside = (idx[None, None, :] >= i) & (idx[None, None, :] <= idx[None, :, None])
        dist = np.where(inside, dist, 0.0)
        block = dist.sum(axis=2) * spacing
        cost[a:b] = np.where(later[a:b], block, np.inf)
    return cost, chord, heading


def _dp(
    cost: np.ndarray,
    chord: np.ndarray,
    heading: np.ndarray,
    max_segments: int,
    min_seg: float,
    max_bend: float,
) -> dict[int, tuple[float, list[int]]]:
    """Best cost per segment count, with vertex index lists (exact DP)."""
    n = len(cost)
    valid = np.where(chord >= min_seg, cost, np.inf)
    best = {1: (cost[0, n - 1], [0, n - 1])}  # one segment is exempt from the minimum
    # f[i, j]: best cost of m segments from sample 0 ending with the segment i -> j.
    f = np.full((n, n), np.inf)
    f[0, :] = valid[0, :]
    # bar[i, j, l]: inf where the bend at j from section i -> j to j -> l is
    # too sharp, read off the cosine between the two sections' headings. f is
    # inf unless i < j and valid unless j < l, so the cube needs no masking.
    unit = np.stack([np.cos(heading), np.sin(heading)], axis=-1)
    cos_turn = np.einsum("ijk,jlk->ijl", unit, unit)
    bar = np.where(cos_turn >= math.cos(math.radians(max_bend)) - 1e-12, 0.0, np.inf)
    back = []
    for m in range(2, max_segments + 1):
        cand = f[:, :, None] + bar
        arg = np.argmin(cand, axis=0)
        g = np.take_along_axis(cand, arg[None], axis=0)[0] + valid
        back.append(arg)
        f = g
        col = f[:, n - 1]
        if np.isfinite(col).any():
            j = int(np.argmin(col))
            best[m] = (float(col[j]), _backtrack(back, j, n - 1, m))
    return best


def _backtrack(back: list[np.ndarray], j: int, last: int, m: int) -> list[int]:
    """Vertex indices of the best m segment fit whose last segment is j -> last.

    ``back[level]`` was built for m = level + 2: ``arg[j, l]`` is the vertex
    before j when the section j -> l is the last.
    """
    verts = [last, j]
    for level in range(m - 2, -1, -1):
        verts.append(int(back[level][verts[-1], verts[-2]]))
    return verts[::-1]


def _path_distances(path: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    """Each path point's distance to the polyline through the vertices."""
    start, end = vertices[:-1], vertices[1:]
    run = end - start
    t = ((path[:, None, :] - start[None]) * run[None]).sum(axis=2) / np.maximum(
        (run**2).sum(axis=1), 1e-12
    )
    nearest = start[None] + np.clip(t, 0.0, 1.0)[..., None] * run[None]
    return np.hypot(*(path[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)


def _valid(
    vertices: np.ndarray, min_seg: float, max_bend: float, max_total: float
) -> bool:
    """Whether a vertex list keeps the section, bend and turning limits."""
    if len(vertices) <= 2:
        return True
    if section_lengths(vertices).min() < min_seg - _EPS:
        return False
    t = turns_deg(vertices)
    return bool(t.max() <= max_bend + 1e-6 and t.sum() <= max_total + 1e-6)


def fit_polyline(
    path: np.ndarray, settings: WallLineSettings, *, refine: bool = True
) -> Fit:
    """The cleanest polyline through an ordered path of candidate toe points.

    Exact dynamic programming over the path's samples (the line's ends are the
    first and last sample, inner vertices are samples): for 0 to ``max_bends``
    bends the best piecewise linear fit, cost the area between path and line,
    every section's chord at least ``min_segment_m`` (a straight line exempt),
    no bend over ``max_bend_deg``, total turning at most
    ``max_total_turn_deg``. The bend count minimises ``cost + k *
    bend_penalty_m2 * (1 + length / bend_length_scale_m)``. With ``refine`` the
    inner vertices are then polished by robust least squares (within
    ``refine_reach_m``, kept only if the limits still hold).

    Args:
        path: ``(n, 2)`` ordered path.
        settings: The run's settings.
        refine: Whether to polish the inner vertices.

    Returns:
        The fit; ``ok`` is False where no fit kept the limits and a straight
        line was returned.

    Raises:
        ValueError: If the path has fewer than two points.
    """
    path = np.asarray(path, dtype=float)
    if len(path) < 2:
        msg = "a path needs at least two distinct points"
        raise ValueError(msg)
    if np.hypot(*(path[-1] - path[0])) < _EPS:
        # A closed or looping path: the line between its two points furthest apart.
        gaps = np.hypot(*(path[:, None] - path[None]).transpose(2, 0, 1))
        i, j = np.unravel_index(int(np.argmax(gaps)), gaps.shape)
        path = path[[min(i, j), max(i, j)]]
    min_seg = settings.min_segment_m
    max_bend = settings.max_bend_deg
    max_total = settings.max_total_turn_deg
    spacing = float(np.hypot(*np.diff(path, axis=0).T).mean())
    length = float(np.hypot(*np.diff(path, axis=0).T).sum())
    cost, chord, heading = _pair_costs(path, spacing)
    best = _dp(cost, chord, heading, settings.max_bends + 1, min_seg, max_bend)
    penalty = settings.bend_penalty_m2 * (1.0 + length / settings.bend_length_scale_m)
    costs: dict[int, float] = {}
    options = []
    for m, (c, seq) in best.items():
        k = m - 1
        vertices = path[seq]
        costs[k] = (
            float(c) if _valid(vertices, min_seg, max_bend, max_total) else math.inf
        )
        if math.isfinite(costs[k]):
            options.append((costs[k] + k * penalty, k, seq))
    if not options:
        seq = [0, len(path) - 1]
        options = [(cost[0, -1], 0, seq)]
        ok = False
    else:
        ok = True
    score, k, seq = min(options)
    vertices = path[seq]
    if refine and k > 0:
        vertices = _refine(path, vertices, settings)
    dist = _path_distances(path, vertices)
    return Fit(
        line=shapely.LineString(vertices),
        vertices=vertices,
        k=k,
        rms=float(np.sqrt((dist**2).mean())),
        cost=float(score),
        costs=costs,
        ok=ok,
    )


def _refine(
    path: np.ndarray, vertices: np.ndarray, settings: WallLineSettings
) -> np.ndarray:
    """Polish the inner vertices by robust least squares, keeping the limits."""
    start, end, seed = vertices[0], vertices[-1], vertices[1:-1]
    reach = settings.refine_reach_m

    def gaps(flat: np.ndarray) -> np.ndarray:
        v = np.vstack([start, flat.reshape(-1, 2), end])
        return _path_distances(path, v)

    fitted = least_squares(
        gaps,
        seed.ravel(),
        loss="soft_l1",
        f_scale=settings.fit_loss_scale_m,
        bounds=(seed.ravel() - reach, seed.ravel() + reach),
        # A polish, not a search: a few iterations settle the vertices.
        max_nfev=settings.refine_max_nfev,
    )
    refined = np.vstack([start, fitted.x.reshape(-1, 2), end])
    if _valid(
        refined,
        settings.min_segment_m,
        settings.max_bend_deg,
        settings.max_total_turn_deg,
    ):
        return refined
    return vertices


# --------------------------------------------------------------------- line


def ring_samples(
    outline: shapely.Polygon, settings: WallLineSettings
) -> tuple[np.ndarray, np.ndarray]:
    """The outline's counter-clockwise ring resampled, with smoothed outward normals.

    Args:
        outline: The pif's cell outline.
        settings: The run's settings.

    Returns:
        The sample points and their unit outward normals, both ``(n, 2)``.
    """
    oriented = shapely.geometry.polygon.orient(outline, 1.0)
    xy = densify(shapely.get_coordinates(oriented.exterior), settings.outline_step_m)[
        :-1
    ]
    n = len(xy)
    w = max(round(settings.normal_half_window_m / settings.outline_step_m), 1)
    idx = np.arange(n)
    tangent = xy[(idx + w) % n] - xy[(idx - w) % n]
    tangent /= np.maximum(np.hypot(*tangent.T), _EPS)[:, None]
    normal = np.column_stack([tangent[:, 1], -tangent[:, 0]])  # right of CCW
    return xy, normal


def local_fall(unit: _Unit, xy: np.ndarray, settings: WallLineSettings) -> np.ndarray:
    """Inverse distance mean of the pip falls near each sample, as unit vectors."""
    radius = settings.fall_radius_m
    pairs = cKDTree(xy).sparse_distance_matrix(
        cKDTree(unit.pips), radius, output_type="ndarray"
    )
    near = pairs["v"] < radius
    wgt = 1.0 / (pairs["v"][near] + 0.5)
    fall = np.zeros_like(xy)
    np.add.at(
        fall, pairs["i"][near], wgt[:, None] * unit.fall_vectors[pairs["j"][near]]
    )
    norm = np.hypot(*fall.T)
    bad = norm < 1e-6
    fall[bad] = unit.mean_fall
    norm[bad] = 1.0
    return fall / norm[:, None]


def circular_runs(keep: np.ndarray, max_gap: int) -> list[np.ndarray]:
    """Index lists of True runs on a ring, joining gaps up to ``max_gap`` samples."""
    n = len(keep)
    keep = keep.copy()
    if keep.all():
        return [np.arange(n)]
    if not keep.any():
        return []
    start = int(np.argmin(keep))  # a False sample: rotate to begin there
    order = (np.arange(n) + start) % n
    k = keep[order]
    edges = np.flatnonzero(np.diff(np.r_[0, k.astype(int), 0]))
    runs = list(zip(edges[::2], edges[1::2], strict=True))
    merged: list[tuple[int, int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [order[a:b] for a, b in merged]


def beyond_share(unit: _Unit, line: shapely.LineString, beyond_m: float) -> float:
    """Share of pips more than ``beyond_m`` beyond the line, on its downhill side."""
    q = shapely.get_coordinates(
        shapely.line_interpolate_point(
            line, shapely.line_locate_point(line, shapely.points(unit.pips))
        )
    )
    along = np.einsum("ij,ij->i", unit.pips - q, unit.fall_vectors)
    return float((along > beyond_m).mean())


def trim_hooks(
    path: np.ndarray, fit: Fit, settings: WallLineSettings
) -> tuple[np.ndarray, Fit]:
    """Refit with the path cut at a short end section's vertex (a corner hook)."""
    for _ in range(2):
        lengths = section_lengths(fit.vertices)
        if fit.k == 0:
            break
        turns = np.abs(turns_deg(fit.vertices))
        head = lengths[0] < settings.hook_m or (
            lengths[0] < settings.hook_sharp_m and turns[0] > settings.hook_sharp_deg
        )
        tail = lengths[-1] < settings.hook_m or (
            lengths[-1] < settings.hook_sharp_m and turns[-1] > settings.hook_sharp_deg
        )
        if not (head or tail):
            break
        cut_a = int(np.argmin(np.hypot(*(path - fit.vertices[1]).T))) if head else 0
        cut_b = (
            int(np.argmin(np.hypot(*(path - fit.vertices[-2]).T)))
            if tail
            else len(path) - 1
        )
        new = path[cut_a : cut_b + 1]
        if len(new) < 3:
            break
        if shapely.LineString(new).length < settings.min_run_m:
            break
        path = new
        fit = fit_polyline(path, settings)
    return path, fit


def jog_penalty(vertices: np.ndarray, settings: WallLineSettings) -> float:
    """Score added for each bend and for an S jog (opposite turns close together)."""
    v = np.asarray(vertices)
    if len(v) < 3:
        return 0.0
    d = np.diff(v, axis=0)
    head = np.arctan2(d[:, 1], d[:, 0])
    turn = (np.diff(head) + np.pi) % (2 * np.pi) - np.pi
    lengths = np.hypot(*d.T)
    cost = settings.bend_score * len(turn)
    for i in range(len(turn) - 1):
        if turn[i] * turn[i + 1] < 0 and lengths[i + 1] < settings.jog_m:
            cost += settings.jog_score
    return cost


@dataclass
class _Candidate:
    """One line for a join gap."""

    line: shapely.LineString
    note: str
    angle: float
    penalty: float


def _candidate(
    join_m: float,
    cos: np.ndarray,
    xy: np.ndarray,
    seen: dict[tuple[float, int, int], tuple[shapely.LineString, str, float]],
    settings: WallLineSettings,
) -> _Candidate | None:
    """One line for a join gap, or None when the outline has no downhill run.

    ``seen`` maps a run already fitted for this unit to its result: different
    join gaps often give the same run, and the fit is the same.
    """
    step = settings.outline_step_m
    for angle in settings.normal_angles_deg:
        runs = circular_runs(cos >= np.cos(np.radians(angle)), int(join_m / step))
        if runs and len(max(runs, key=len)) * step >= settings.min_run_m:
            run = max(runs, key=len)
            break
    else:
        return None
    key = (angle, int(run[0]), len(run))
    if key in seen:
        line, note, penalty = seen[key]
        return _Candidate(
            line, f"angle {angle:.0f}; join {join_m:.0f} m; {note}", angle, penalty
        )
    path = xy[run]
    while len(path) > 2 and shapely.LineString(path).length > settings.max_length_m:
        path = path[1:-1]
    path = densify(path, settings.fit_step_m)
    fit = fit_polyline(path, settings)
    path, fit = trim_hooks(path, fit, settings)
    note = f"run {len(run) * step:.1f} m; k {fit.k}; rms {fit.rms:.2f}"
    if not fit.ok:
        note += "; fit not ok"
    dev = float(shapely.distance(shapely.points(path), fit.line).max())
    penalty = (
        settings.rms_weight * max(fit.rms - settings.rms_ok_m, 0.0)
        + settings.chord_weight * max(dev - settings.chord_ok_m, 0.0)
        + jog_penalty(fit.vertices, settings)
    )
    seen[key] = (fit.line, note, penalty)
    return _Candidate(
        fit.line, f"angle {angle:.0f}; join {join_m:.0f} m; {note}", angle, penalty
    )


def wall_line(
    pips: np.ndarray,
    pip_direction: np.ndarray,
    fallback: shapely.LineString,
    settings: WallLineSettings,
) -> tuple[shapely.LineString, str, str]:
    """The wall line of one pif piece, its method and notes.

    The join gaps are tried in order, keeping the first line with few pips
    beyond it, otherwise the one with the fewest (penalties added).

    Args:
        pips: ``(n, 2)`` pip coordinates (x, y), cell centres.
        pip_direction: ``(n,)`` index into ``DIRECTIONS`` of each pip's fall.
        fallback: The line kept when the outline has no downhill run (the
            piece's own cut line).
        settings: The run's settings.

    Returns:
        The line, its method (``outline``, ``outline-wide`` for a normal more
        than 60 degrees off the fall, or ``fallback``) and notes on how it was
        chosen.
    """
    unit = _unit(pips, pip_direction)
    outline = cell_outline(
        np.vstack(
            [unit.pips, unit.pips + STEP_XY[np.asarray(pip_direction, dtype=int)]]
        )
    )
    xy, normal = ring_samples(outline, settings)
    cos = np.einsum("ij,ij->i", normal, local_fall(unit, xy, settings))
    seen: dict[tuple[float, int, int], tuple[shapely.LineString, str, float]] = {}
    best = None
    for join_m in settings.join_gaps_m:
        cand = _candidate(join_m, cos, xy, seen, settings)
        if cand is None:
            continue
        share = beyond_share(unit, cand.line, settings.beyond_m) + cand.penalty
        if best is None or share < best[0] - _EPS:
            best = (share, cand)
        if share <= settings.beyond_ok:
            break
    if best is None:
        return fallback, METHOD_FALLBACK, _NO_RUN_NOTE
    share, cand = best
    method = METHOD_OUTLINE if cand.angle <= _NARROW_ANGLE_DEG else METHOD_OUTLINE_WIDE
    return cand.line, method, f"{cand.note}; score {share:.2f}"


# --------------------------------------------------------------------- cone


def cones(
    pips: np.ndarray, falls: np.ndarray, settings: WallLineSettings
) -> np.ndarray:
    """A sector polygon per pip: apex at the pip, opening about its fall."""
    head = np.arctan2(falls[:, 1], falls[:, 0])
    spread = np.radians(
        np.linspace(
            -settings.cone_half_angle_deg,
            settings.cone_half_angle_deg,
            settings.cone_arc_n,
        )
    )
    ang = head[:, None] + spread[None, :]
    arc = pips[:, None, :] + settings.cone_reach_m * np.stack(
        [np.cos(ang), np.sin(ang)], axis=-1
    )
    return shapely.polygons(
        np.concatenate([pips[:, None, :], arc, pips[:, None, :]], axis=1)
    )


def groups(xy: np.ndarray, join: float) -> np.ndarray:
    """Labels of groups of pips, those up to ``join`` apart being one group."""
    if len(xy) == 0:
        return np.zeros(0, dtype=int)
    pairs = cKDTree(xy).query_pairs(join, output_type="ndarray")
    graph = coo_matrix(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(xy), len(xy))
    )
    return connected_components(graph, directed=False)[1]


def edge_of(pips: np.ndarray) -> shapely.LineString:
    """The edge of ``pips``' cells."""
    return shapely.boundary(cell_outline(pips))


def zone_of(pips: np.ndarray, settings: WallLineSettings) -> shapely.Polygon:
    """``pips``' cells grown by ``edge_buffer_m``: an edge inside it lies on them."""
    return shapely.buffer(cell_outline(pips), settings.edge_buffer_m)


def on_length(edge: shapely.LineString, zone: shapely.Polygon) -> float:
    """Length of an edge lying in a zone."""
    return float(shapely.intersection(edge, zone).length)


def wall_pieces(
    pips: np.ndarray,
    pip_direction: np.ndarray,
    line: shapely.LineString,
    settings: WallLineSettings,
) -> tuple[np.ndarray, np.ndarray]:
    """Label per pip (0 the wall's pif, 1.. a no-wall pif) and how it got there.

    Args:
        pips: ``(n, 2)`` pip coordinates (x, y), cell centres.
        pip_direction: ``(n,)`` index into ``DIRECTIONS`` of each pip's fall.
        line: The piece's wall line (:func:`wall_line`).
        settings: The run's settings.

    Returns:
        ``(label, how)``: the piece of each pip (0 holds the wall, 1.. are pifs
        with no wall), and how it got there: ``cone`` (on the wall),
        ``merged back`` (a small or enclosed leftover group), ``cut off``
        (wall pips cut off from the wall's pif) or ``left over``.
    """
    unit = _unit(pips, pip_direction)
    n = len(unit.pips)
    on = shapely.intersects(cones(unit.pips, unit.fall_vectors, settings), line)
    how = np.where(on, HOW_CONE, HOW_LEFT_OVER).astype(object)
    label = np.zeros(n, dtype=int)
    rest = np.flatnonzero(~on)
    g = groups(unit.pips[rest], settings.leftover_join_m)
    sizes = np.bincount(g) if len(rest) else np.zeros(0, int)
    keep = [k for k in np.argsort(-sizes) if sizes[k] > settings.min_no_wall_pips]
    how[rest[~np.isin(g, keep)]] = HOW_MERGED_BACK
    # Each outline is built once: a group's edge never changes, and the
    # wall's zone only when a group goes back.
    edges = {k: edge_of(unit.pips[rest[g == k]]) for k in keep}
    changed = True
    while changed and keep:
        changed = False
        zone = zone_of(unit.pips[how != HOW_LEFT_OVER], settings)
        for k in list(keep):
            share = on_length(edges[k], zone) / max(edges[k].length, _EPS)
            if share > settings.enclosed_share:
                keep.remove(k)
                how[rest[g == k]] = HOW_MERGED_BACK
                changed = True
                break
    for i, k in enumerate(keep, start=1):
        label[rest[g == k]] = i
    cut_off(unit, line, label, how, settings)
    return label, how.astype(str)


def cut_off(
    unit: _Unit,
    line: shapely.LineString,
    label: np.ndarray,
    how: np.ndarray,
    settings: WallLineSettings,
) -> None:
    """Move wall pips cut off from the line out of the wall's pif (in place)."""
    wall = np.flatnonzero(label == WALL_LABEL)
    if len(wall) == 0:
        return
    g = groups(unit.pips[wall], settings.wall_join_m)
    gap = np.full(g.max() + 1, np.inf)
    np.minimum.at(gap, g, shapely.distance(shapely.points(unit.pips[wall]), line))
    stay = set(np.flatnonzero(gap <= settings.stay_m)) or {int(np.argmin(gap))}
    zones: dict[int, shapely.Polygon] = {}  # each no-wall pif's zone, built when needed
    for k in np.argsort(-np.bincount(g)):
        if k in stay:
            continue
        idx = wall[g == k]
        edge = edge_of(unit.pips[idx])
        shares = {}
        for m in range(1, label.max() + 1):
            if m not in zones:
                zones[m] = zone_of(unit.pips[label == m], settings)
            shares[m] = on_length(edge, zones[m])
        touching = {m: v for m, v in shares.items() if v > 0}
        if touching:
            label[idx] = max(touching, key=touching.get)
        elif len(idx) > settings.min_no_wall_pips:
            label[idx] = label.max() + 1
        else:
            continue
        zones.pop(int(label[idx[0]]), None)
        how[idx] = HOW_CUT_OFF
