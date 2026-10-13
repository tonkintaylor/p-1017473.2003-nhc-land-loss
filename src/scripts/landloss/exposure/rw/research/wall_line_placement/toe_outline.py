"""Option 10: the wall line along the pif's downhill outline, and the pips it holds.

The lead's method (2026-10-13), chosen from three tried on the 120 cases of
``temp/wall-line-brief/brief.md`` (option A there; the findings are in
``temp/wall-line-brief/options/findings.md``):

1. **The line** (:func:`draw_line`). The pif's cell outline (its pips and the
   cell each falls to at 1 m, as 1 m squares, :func:`cell_outline`) is walked
   every ``config.OUTLINE_STEP_M``. Each sample's outward normal is read off
   the outline ``config.NORMAL_HALF_WINDOW_M`` either side, and the local fall
   off the pips within ``config.FALL_RADIUS_M``. The longest run of samples
   whose normal is within 45° of the fall (widened to 60°, 75° or 90° only
   when no run is ``config.MIN_RUN_M`` long) is the toe; gaps in it shorter
   than a join gap are bridged, each of ``config.JOIN_GAPS_M`` tried in turn.
   Each run is regularised by :func:`fit_polyline` (0 to 3 bends, sections of
   3 m or more, no bend over 100°, at most 185° of turning; the lead: "I dont
   want a really wonky wall"), short end hooks are cut (:func:`trim_hooks`),
   and the candidate with the fewest pips beyond it downhill, with penalties
   for a poor fit, a chord across a notch and S jogs, is kept. A pif with no
   downhill run keeps option 9's line (``fallback-opt9``).
2. **The pips the wall holds** (:func:`assign`). A pip is on the wall when its
   fall, widened ``config.CONE_HALF_ANGLE_DEG`` either side and
   ``config.CONE_REACH_M`` long, meets the line. The other pips are grouped
   (up to ``config.LEFTOVER_JOIN_M`` apart, so a one-cell gap does not split
   a group); a group of more than ``config.MIN_NO_WALL_PIPS`` is a pif with no
   wall (p_wall 0), a smaller one goes back to the wall's pif, and so does
   one with more than ``config.ENCLOSED_SHARE`` of its edge on the wall's
   pif. The wall's pif must touch (8-connected, :func:`cut_off`): a group of
   wall pips within ``config.STAY_M`` of the line stays, any other joins the
   no-wall pif it touches, or is one of its own when over
   ``config.MIN_NO_WALL_PIPS`` pips.

Units are drawn in parallel by :func:`draw_units`; :func:`draw_unit` is the
worker, here rather than in the script so a spawned process can import it.
"""

import math
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np
import shapely
from scipy.optimize import least_squares
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from landloss.hazard.landslide.instability_zones import DIRECTIONS
from scripts.landloss.exposure.rw.research.wall_line_placement import config

# A step along each of the eight fall directions as (x, y) in cells: a step
# down the grid's rows is a step south.
STEP_XY = np.array([(dc, -dr) for dr, dc in DIRECTIONS], dtype=float)
UNIT_XY = STEP_XY / np.hypot(*STEP_XY.T)[:, None]
# How each pip came to its pif, as written in the pips layer.
HOW = np.array(["cone", "merged back", "cut off", "left over"], dtype=object)
HOW_CODE = {h: i for i, h in enumerate(HOW)}
# Rows of the (i, j, p) cost cube the fit computes at once, to bound memory.
PAIR_BLOCK = 48


@dataclass
class Unit:
    """What the line and the cone need of one pif unit."""

    wall_unit_id: str
    pips: np.ndarray
    fall_vectors: np.ndarray
    mean_fall: np.ndarray
    outline: shapely.Polygon
    opt9: shapely.LineString


@dataclass
class Fit:
    """A regularised line and how it was chosen."""

    line: shapely.LineString
    vertices: np.ndarray
    k: int
    rms: float
    cost: float
    costs: dict
    ok: bool


# ------------------------------------------------------------------ outline


def cell_outline(points):
    """The union of 1 m squares centred on the points, lightly closed.

    Closed with a mitre buffer of +0.5 then -0.5 so single cell notches do not
    fragment it; the largest part, holes removed. Each row's runs of touching
    cells become one box before the union, rather than a square per cell.
    """
    xy = np.atleast_2d(points)
    cells = np.unique(np.floor(xy).astype(np.int64), axis=0)
    cells = cells[np.lexsort((cells[:, 0], cells[:, 1]))]
    new_run = np.r_[True, (np.diff(cells[:, 1]) != 0) | (np.diff(cells[:, 0]) != 1)]
    first = np.flatnonzero(new_run)
    last = np.r_[first[1:] - 1, len(cells) - 1]
    union = shapely.union_all(
        shapely.box(cells[first, 0], cells[first, 1], cells[last, 0] + 1, cells[last, 1] + 1)
    )
    closed = union.buffer(0.5, join_style="mitre").buffer(-0.5, join_style="mitre")
    if closed.is_empty:
        closed = union
    parts = list(getattr(closed, "geoms", [closed]))
    biggest = max(parts, key=lambda p: p.area)
    return shapely.Polygon(biggest.exterior)


# -------------------------------------------------------------- regulariser


def densify(xy, step=0.5):
    """An ordered polyline's points resampled every ``step`` m along it."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        return xy
    keep = np.r_[True, np.hypot(*np.diff(xy, axis=0).T) > 1e-9]
    xy = xy[keep]
    if len(xy) < 2:
        return xy
    line = shapely.LineString(xy)
    n = max(int(math.ceil(line.length / step)), 1) + 1
    return shapely.get_coordinates(
        shapely.line_interpolate_point(line, np.linspace(0, line.length, n))
    )


def turns_deg(vertices):
    """How far the line turns at each inner vertex, degrees (0 straight on)."""
    v = np.asarray(vertices, dtype=float)
    if len(v) < 3:
        return np.zeros(0)
    heading = np.arctan2(*np.diff(v, axis=0)[:, ::-1].T)
    return np.degrees(np.abs((np.diff(heading) + math.pi) % (2 * math.pi) - math.pi))


def section_lengths(vertices):
    """The length of each straight section."""
    return np.hypot(*np.diff(np.asarray(vertices, dtype=float), axis=0).T)


def _pair_costs(path, spacing, loss):
    """Cost of one section for every pair (i, j): the path between them against its chord.

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
        across = rel[:, None, :, 0] * u[:, :, None, 1] - rel[:, None, :, 1] * u[:, :, None, 0]
        beyond = np.maximum(np.maximum(-along, along - chord[a:b, :, None]), 0.0)
        dist = np.hypot(across, beyond)
        i = idx[a:b, None, None]
        inside = (idx[None, None, :] >= i) & (idx[None, None, :] <= idx[None, :, None])
        dist = np.where(inside, dist, 0.0)
        block = (dist if loss == "l1" else dist**2).sum(axis=2) * spacing
        cost[a:b] = np.where(later[a:b], block, np.inf)
    return cost, chord, heading


def _dp(cost, chord, heading, max_segments, min_seg, max_bend):
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


def _backtrack(back, j, last, m):
    """Vertex indices of the best m segment fit whose last segment is j -> last.

    ``back[level]`` was built for m = level + 2: ``arg[j, l]`` is the vertex
    before j when the section j -> l is the last.
    """
    verts = [last, j]
    for level in range(m - 2, -1, -1):
        verts.append(int(back[level][verts[-1], verts[-2]]))
    return verts[::-1]


def _path_distances(path, vertices):
    """Each path point's distance to the polyline through the vertices."""
    start, end = vertices[:-1], vertices[1:]
    run = end - start
    t = ((path[:, None, :] - start[None]) * run[None]).sum(axis=2) / np.maximum(
        (run**2).sum(axis=1), 1e-12
    )
    nearest = start[None] + np.clip(t, 0.0, 1.0)[..., None] * run[None]
    return np.hypot(*(path[:, None, :] - nearest).transpose(2, 0, 1)).min(axis=1)


def _valid(vertices, min_seg, max_bend, max_total):
    """Whether a vertex list keeps the section, bend and turning limits."""
    if len(vertices) <= 2:
        return True
    if section_lengths(vertices).min() < min_seg - 1e-9:
        return False
    t = turns_deg(vertices)
    return bool(t.max() <= max_bend + 1e-6 and t.sum() <= max_total + 1e-6)


def fit_polyline(
    path,
    *,
    bend_penalty_m2=config.BEND_PENALTY_M2,
    length_scale_m=config.BEND_LENGTH_SCALE_M,
    min_segment_m=config.WALL_MIN_SEGMENT_M,
    max_bend_deg=config.MAX_BEND_DEG,
    max_total_turn_deg=config.MAX_TOTAL_TURN_DEG,
    max_bends=config.WALL_MAX_BENDS,
    loss="l1",
    refine=True,
):
    """The cleanest polyline through an ordered path of candidate toe points.

    Exact dynamic programming over the path's samples (the line's ends are the
    first and last sample, inner vertices are samples): for 0 to ``max_bends``
    bends the best piecewise linear fit, cost the area between path and line
    (``loss="l1"``) or the squared distances (``"l2"``), every section's chord
    at least ``min_segment_m`` (a straight line exempt), no bend over
    ``max_bend_deg``, total turning at most ``max_total_turn_deg``. The bend
    count minimises ``cost + k * bend_penalty_m2 * (1 + length /
    length_scale_m)``. With ``refine`` the inner vertices are then polished by
    robust least squares (within 1.5 m, kept only if the limits still hold).
    ``ok`` is False where no fit kept the limits and a straight line was
    returned.
    """
    path = np.asarray(path, dtype=float)
    if len(path) < 2 or np.hypot(*(path[-1] - path[0])) < 1e-9:
        if len(path) >= 2:
            # A closed or looping path: the line between its two points furthest apart.
            gaps = np.hypot(*(path[:, None] - path[None]).transpose(2, 0, 1))
            i, j = np.unravel_index(int(np.argmax(gaps)), gaps.shape)
            path = path[[min(i, j), max(i, j)]]
        else:
            msg = "a path needs at least two distinct points"
            raise ValueError(msg)
    spacing = float(np.hypot(*np.diff(path, axis=0).T).mean())
    length = float(np.hypot(*np.diff(path, axis=0).T).sum())
    cost, chord, heading = _pair_costs(path, spacing, loss)
    best = _dp(cost, chord, heading, max_bends + 1, min_segment_m, max_bend_deg)
    penalty = bend_penalty_m2 * (1.0 + length / length_scale_m)
    costs, options = {}, []
    for m, (c, seq) in best.items():
        k = m - 1
        vertices = path[seq]
        costs[k] = (
            float(c)
            if _valid(vertices, min_segment_m, max_bend_deg, max_total_turn_deg)
            else math.inf
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
        vertices = _refine(
            path, vertices, min_segment_m, max_bend_deg, max_total_turn_deg, loss
        )
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


def _refine(path, vertices, min_seg, max_bend, max_total, loss, reach=1.5):
    """Polish the inner vertices by robust least squares, keeping the limits."""
    start, end, seed = vertices[0], vertices[-1], vertices[1:-1]

    def gaps(flat):
        v = np.vstack([start, flat.reshape(-1, 2), end])
        return _path_distances(path, v)

    fitted = least_squares(
        gaps,
        seed.ravel(),
        loss="soft_l1" if loss == "l1" else "linear",
        f_scale=0.5,
        bounds=(seed.ravel() - reach, seed.ravel() + reach),
        # A polish, not a search: a few iterations settle the vertices.
        max_nfev=config.REFINE_MAX_NFEV,
    )
    refined = np.vstack([start, fitted.x.reshape(-1, 2), end])
    if _valid(refined, min_seg, max_bend, max_total):
        return refined
    return vertices


# --------------------------------------------------------------------- line


def ring_samples(unit):
    """The outline's counter-clockwise ring resampled, with smoothed outward normals."""
    outline = shapely.geometry.polygon.orient(unit.outline, 1.0)
    xy = densify(shapely.get_coordinates(outline.exterior), config.OUTLINE_STEP_M)[:-1]
    n = len(xy)
    w = max(int(round(config.NORMAL_HALF_WINDOW_M / config.OUTLINE_STEP_M)), 1)
    idx = np.arange(n)
    tangent = xy[(idx + w) % n] - xy[(idx - w) % n]
    tangent /= np.maximum(np.hypot(*tangent.T), 1e-9)[:, None]
    normal = np.column_stack([tangent[:, 1], -tangent[:, 0]])  # right of CCW
    return xy, normal


def local_fall(unit, xy):
    """Inverse distance mean of the pip falls near each sample."""
    pairs = cKDTree(xy).sparse_distance_matrix(
        cKDTree(unit.pips), config.FALL_RADIUS_M, output_type="ndarray"
    )
    near = pairs["v"] < config.FALL_RADIUS_M
    wgt = 1.0 / (pairs["v"][near] + 0.5)
    fall = np.zeros_like(xy)
    np.add.at(fall, pairs["i"][near], wgt[:, None] * unit.fall_vectors[pairs["j"][near]])
    norm = np.hypot(*fall.T)
    bad = norm < 1e-6
    fall[bad] = unit.mean_fall
    norm[bad] = 1.0
    return fall / norm[:, None]


def circular_runs(keep, max_gap):
    """Index lists of True runs on a ring, joining gaps up to max_gap samples."""
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
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [order[a:b] for a, b in merged]


def beyond_share(unit, line):
    """Share of pips more than ``config.BEYOND_M`` beyond the line, on its downhill side."""
    q = shapely.get_coordinates(
        shapely.line_interpolate_point(line, shapely.line_locate_point(line, shapely.points(unit.pips)))
    )
    along = np.einsum("ij,ij->i", unit.pips - q, unit.fall_vectors)
    return float((along > config.BEYOND_M).mean())


def trim_hooks(path, fit):
    """Refit with the path cut at a short end section's vertex (a corner hook)."""
    for _ in range(2):
        lengths = section_lengths(fit.vertices)
        if fit.k == 0:
            break
        turns = np.abs(turns_deg(fit.vertices))
        head = lengths[0] < config.HOOK_M or (
            lengths[0] < config.HOOK_SHARP_M and turns[0] > config.HOOK_SHARP_DEG
        )
        tail = lengths[-1] < config.HOOK_M or (
            lengths[-1] < config.HOOK_SHARP_M and turns[-1] > config.HOOK_SHARP_DEG
        )
        if not (head or tail):
            break
        cut_a = int(np.argmin(np.hypot(*(path - fit.vertices[1]).T))) if head else 0
        cut_b = int(np.argmin(np.hypot(*(path - fit.vertices[-2]).T))) if tail else len(path) - 1
        new = path[cut_a : cut_b + 1]
        if len(new) < 3:
            break
        if shapely.LineString(new).length < config.MIN_RUN_M:
            break
        path = new
        fit = fit_polyline(path)
    return path, fit


def jog_penalty(vertices):
    """Score added for each bend and for an S jog (opposite turns close together)."""
    v = np.asarray(vertices)
    if len(v) < 3:
        return 0.0
    d = np.diff(v, axis=0)
    head = np.arctan2(d[:, 1], d[:, 0])
    turn = (np.diff(head) + np.pi) % (2 * np.pi) - np.pi
    lengths = np.hypot(*d.T)
    cost = config.BEND_SCORE * len(turn)
    for i in range(len(turn) - 1):
        if turn[i] * turn[i + 1] < 0 and lengths[i + 1] < config.JOG_M:
            cost += config.JOG_SCORE
    return cost


def candidate(join_m, cos, xy, seen):
    """One line for a join gap: (line, note, path, angle, penalty) or None.

    ``seen`` maps a run already fitted for this unit to its result: different
    join gaps often give the same run, and the fit is the same.
    """
    for angle in config.MAX_NORMAL_ANGLES_DEG:
        runs = circular_runs(cos >= np.cos(np.radians(angle)), int(join_m / config.OUTLINE_STEP_M))
        if runs and len(max(runs, key=len)) * config.OUTLINE_STEP_M >= config.MIN_RUN_M:
            run = max(runs, key=len)
            break
    else:
        return None
    key = (angle, int(run[0]), len(run))
    if key in seen:
        line, note, path, penalty = seen[key]
        return line, f"angle {angle:.0f}; join {join_m:.0f} m; {note}", path, angle, penalty
    path = xy[run]
    while len(path) > 2 and shapely.LineString(path).length > config.OUTLINE_MAX_LENGTH_M:
        path = path[1:-1]
    path = densify(path, config.FIT_STEP_M)
    fit = fit_polyline(path)
    path, fit = trim_hooks(path, fit)
    note = f"run {len(run) * config.OUTLINE_STEP_M:.1f} m; k {fit.k}; rms {fit.rms:.2f}"
    if not fit.ok:
        note += "; fit not ok"
    dev = float(shapely.distance(shapely.points(path), fit.line).max())
    penalty = (
        config.RMS_WEIGHT * max(fit.rms - config.RMS_OK_M, 0.0)
        + config.CHORD_WEIGHT * max(dev - config.CHORD_OK_M, 0.0)
        + jog_penalty(fit.vertices)
    )
    seen[key] = (fit.line, note, path, penalty)
    return fit.line, f"angle {angle:.0f}; join {join_m:.0f} m; {note}", path, angle, penalty


def draw_line(unit):
    """The unit's line, its method (``outline``, ``outline-wide`` or ``fallback-opt9``) and notes.

    The join gaps are tried in order, keeping the first line with few pips
    beyond it, otherwise the one with the fewest (penalties added).
    """
    best = None
    xy, normal = ring_samples(unit)
    cos = np.einsum("ij,ij->i", normal, local_fall(unit, xy))
    seen = {}
    for join_m in config.JOIN_GAPS_M:
        cand = candidate(join_m, cos, xy, seen)
        if cand is None:
            continue
        share = beyond_share(unit, cand[0]) + cand[4]
        if best is None or share < best[0] - 1e-9:
            best = (share, *cand[:4])
        if share <= config.BEYOND_OK:
            break
    if best is None:
        return unit.opt9, "fallback-opt9", "no downhill run on the outline"
    share, line, note, _, angle = best
    method = "outline" if angle <= 60 else "outline-wide"
    return line, method, f"{note}; score {share:.2f}"


# --------------------------------------------------------------------- cone


def cones(pips, falls):
    """A sector polygon per pip: apex at the pip, ``config.CONE_HALF_ANGLE_DEG`` about its fall."""
    head = np.arctan2(falls[:, 1], falls[:, 0])
    spread = np.radians(np.linspace(-config.CONE_HALF_ANGLE_DEG, config.CONE_HALF_ANGLE_DEG, config.CONE_ARC_N))
    ang = head[:, None] + spread[None, :]
    arc = pips[:, None, :] + config.CONE_REACH_M * np.stack([np.cos(ang), np.sin(ang)], axis=-1)
    return shapely.polygons(np.concatenate([pips[:, None, :], arc, pips[:, None, :]], axis=1))


def groups(xy, join):
    """Labels of groups of pips, those up to ``join`` apart being one group."""
    if len(xy) == 0:
        return np.zeros(0, dtype=int)
    pairs = cKDTree(xy).query_pairs(join, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(xy), len(xy)))
    return connected_components(graph, directed=False)[1]


def edge_of(pips):
    """The edge of ``pips``' cells."""
    return shapely.boundary(cell_outline(pips))


def zone_of(pips):
    """``pips``' cells grown by ``config.EDGE_BUFFER_M``: an edge inside it lies on them."""
    return shapely.buffer(cell_outline(pips), config.EDGE_BUFFER_M)


def on_length(edge, zone):
    """Length of an edge lying in a zone."""
    return shapely.intersection(edge, zone).length


def assign(unit, line):
    """Label per pip (0 the wall's pif, 1.. a no-wall pif) and how it got there.

    ``how`` is ``cone``, ``merged back`` (a small or enclosed leftover group),
    ``cut off`` (wall pips cut off from the wall's pif) or ``left over``.
    """
    n = len(unit.pips)
    on = shapely.intersects(cones(unit.pips, unit.fall_vectors), line)
    how = np.where(on, "cone", "left over").astype(object)
    label = np.zeros(n, dtype=int)
    rest = np.flatnonzero(~on)
    g = groups(unit.pips[rest], config.LEFTOVER_JOIN_M)
    sizes = np.bincount(g) if len(rest) else np.zeros(0, int)
    keep = [k for k in np.argsort(-sizes) if sizes[k] > config.MIN_NO_WALL_PIPS]
    how[rest[~np.isin(g, keep)]] = "merged back"
    # Each outline is built once: a group's edge never changes, and the
    # wall's zone only when a group goes back.
    edges = {k: edge_of(unit.pips[rest[g == k]]) for k in keep}
    changed = True
    while changed and keep:
        changed = False
        zone = zone_of(unit.pips[how != "left over"])
        for k in list(keep):
            if on_length(edges[k], zone) / max(edges[k].length, 1e-9) > config.ENCLOSED_SHARE:
                keep.remove(k)
                how[rest[g == k]] = "merged back"
                changed = True
                break
    for i, k in enumerate(keep, start=1):
        label[rest[g == k]] = i
    cut_off(unit, line, label, how)
    return label, how


def cut_off(unit, line, label, how):
    """Move groups of wall pips cut off from the line out of the wall's pif (in place)."""
    wall = np.flatnonzero(label == 0)
    if len(wall) == 0:
        return
    g = groups(unit.pips[wall], config.WALL_JOIN_M)
    gap = np.full(g.max() + 1, np.inf)
    np.minimum.at(gap, g, shapely.distance(shapely.points(unit.pips[wall]), line))
    stay = set(np.flatnonzero(gap <= config.STAY_M)) or {int(np.argmin(gap))}
    zones = {}  # each no-wall pif's zone, built when first needed and when it grows
    for k in np.argsort(-np.bincount(g)):
        if k in stay:
            continue
        idx = wall[g == k]
        edge = edge_of(unit.pips[idx])
        shares = {}
        for m in range(1, label.max() + 1):
            if m not in zones:
                zones[m] = zone_of(unit.pips[label == m])
            shares[m] = on_length(edge, zones[m])
        touching = {m: v for m, v in shares.items() if v > 0}
        if touching:
            label[idx] = max(touching, key=touching.get)
        elif len(idx) > config.MIN_NO_WALL_PIPS:
            label[idx] = label.max() + 1
        else:
            continue
        zones.pop(int(label[idx[0]]), None)
        how[idx] = "cut off"


# ----------------------------------------------------------------- parallel


def draw_unit(task):
    """The line and the pips' pieces for one unit, with the time each took.

    ``task`` is ``(wall_unit_id, pips, pip directions, option 9's line as WKB)``.
    Returns ``(wall_unit_id, line as WKB, method, notes, label, how code,
    line seconds, cone seconds)``, ``how`` coded by ``HOW``.
    """
    unit_id, pips, direction, opt9 = task
    t0 = time.perf_counter()
    fall = UNIT_XY[direction]
    mean = fall.mean(axis=0)
    unit = Unit(
        unit_id,
        pips,
        fall,
        mean / np.hypot(*mean),
        cell_outline(np.vstack([pips, pips + STEP_XY[direction]])),
        shapely.from_wkb(opt9),
    )
    line, method, notes = draw_line(unit)
    t1 = time.perf_counter()
    label, how = assign(unit, line)
    t2 = time.perf_counter()
    code = np.array([HOW_CODE[h] for h in how], dtype=np.int8)
    return unit_id, shapely.to_wkb(line), method, notes, label.astype(np.int16), code, t1 - t0, t2 - t1


def _draw_chunk(chunk):
    """``draw_unit`` over a list of tasks: one round trip to a worker."""
    return [draw_unit(t) for t in chunk]


def draw_units(tasks, workers):
    """``draw_unit`` over every task, in ``workers`` processes (one: in this one).

    The biggest pifs go first, so the last chunks to finish are small.
    """
    tasks = sorted(tasks, key=lambda t: -len(t[1]))
    if workers <= 1:
        return [draw_unit(t) for t in tasks]
    chunks = [tasks[i : i + config.CHUNK_UNITS] for i in range(0, len(tasks), config.CHUNK_UNITS)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return [r for part in pool.map(_draw_chunk, chunks) for r in part]
