"""Cut a path into pieces of few bends: the one rule for pifs and walls.

The lead's rules (2026-10-06), used twice: on each pif's spine before the
siz table and the element growth
(:func:`landloss.hazard.landslide.instability_zones.split_pifs`), and on the
chained members of each joined wall
(:func:`landloss.hazard.landslide.wall_units.gen_unit_lines`):

1. A new piece starts wherever following the path within a stray tolerance
   would need more than ``max_bends`` bends, or bends turning more than
   ``max_turn_deg`` in all (Douglas-Peucker on the path, :func:`bend_ranges`).
2. A piece whose ends are under ``min_segment_m`` apart joins the piece
   before it, or after it for the first (:func:`merge_short_ranges`).
3. A piece whose line is longer than ``max_length_m`` is cut (the lead,
   2026-10-06: "if over 50 m, then split on bends; if no bends then split
   on boundaries, then split on evenly divide", :func:`cap_ranges`): first
   at its line's own bends, the fewest cuts that bring every part under the
   cap, the most even of those; a part with no bend left at the property
   boundaries it crosses (walls only, through ``boundary_cuts``); and what
   is still over the cap into equal parts.

A pif or a joined wall can branch (a T in a mapped wall, a spur off a
crest), so it is walked as several paths first: its tree's longest path and
then each branch off it (:func:`tree_paths`).

A piece is a range of the path's points, ``(start, end)`` inclusive, and
neighbouring pieces share their end point. :func:`canonical_line` turns a
piece into its line: the piece's ends, at most ``max_bends`` bends turning
no more than ``max_turn_deg``, no section shorter than ``min_segment_m``, so
never shorter than the piece's ends are apart nor longer than the piece.
:func:`rule_breaks` checks a line against the rules.
"""

import math
from collections import Counter
from collections.abc import Callable
from itertools import combinations, pairwise

import numpy as np
import shapely
from numpy.typing import NDArray
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

Range = tuple[int, int]
BoundaryCuts = Callable[[shapely.LineString], list[float]]


def _farthest_path(graph: csr_matrix, start: int) -> tuple[list[int], float]:
    """The path from ``start`` to the node farthest from it, and its length."""
    dist, previous = dijkstra(
        graph, directed=False, indices=start, return_predecessors=True
    )
    far = int(np.argmax(np.where(np.isfinite(dist), dist, -1.0)))
    path = [far]
    while path[-1] != start:
        path.append(int(previous[path[-1]]))
    return path[::-1], float(dist[far])


def _sticks_out(
    points: NDArray[np.float64], paths: list[NDArray[np.float64]], reach_m: float
) -> bool:
    """Whether any point lies ``reach_m`` or more from every path so far."""
    lines = shapely.MultiLineString([p for p in paths if len(p) > 1])
    return bool((shapely.distance(shapely.points(points), lines) >= reach_m).any())


def tree_paths(
    tree: csr_matrix, xy: NDArray[np.float64], *, min_branch_m: float
) -> list[NDArray[np.float64]]:
    """A spanning tree's points as paths: its longest, then each branch.

    The first path is the tree's longest (a double sweep from the point with
    the lowest (x, y)), so its ends are the two far ends. Each branch left off
    it is then a path of its own from the point it joins at, the longest first,
    until every point is on a path. A branch makes no path, its points left
    to the nearest path, where it is shorter than ``min_branch_m`` or none of
    its points lies ``min_branch_m`` or more from the paths so far: the
    width of a face several cells thick is not a branch. A tree in several
    parts gives each part its own paths.

    Args:
        tree: A symmetric spanning tree (or forest) over ``xy``, its weights
            the edge lengths.
        xy: The points, in metres.
        min_branch_m: The shortest branch that is a path of its own.

    Returns:
        The paths as arrays of points, the first the longest.
    """
    tree = csr_matrix(tree)
    start = int(np.lexsort((xy[:, 1], xy[:, 0]))[0])
    end_a = _farthest_path(tree, start)[0][-1]
    main, _ = _farthest_path(tree, end_a)
    paths = [xy[main]]
    covered = np.zeros(len(xy), dtype=bool)
    covered[main] = True
    while not covered.all():
        rest = np.flatnonzero(~covered)
        sub = tree[rest][:, rest]
        n_parts, part = connected_components(sub, directed=False)
        for k in range(n_parts):
            nodes = rest[part == k]
            edges = tree[nodes].tocoo()
            joins = covered[edges.col]
            join_m = float(edges.data[joins][0]) if joins.any() else 0.0
            total_m = sub[part == k].sum() / 2.0 + join_m
            if joins.any() and total_m < min_branch_m:
                covered[nodes] = True
                continue
            local = {node: i for i, node in enumerate(nodes)}
            inner = int(nodes[edges.row[joins][0]]) if joins.any() else int(nodes[0])
            anchor = [int(edges.col[joins][0])] if joins.any() else []
            branch, length = _farthest_path(tree[nodes][:, nodes], local[inner])
            covered[nodes[branch]] = True
            if not anchor and len(branch) > 1:
                paths.append(xy[nodes[branch]])
            elif length + join_m >= min_branch_m and _sticks_out(
                xy[nodes[branch]], paths, min_branch_m
            ):
                paths.append(xy[[*anchor, *nodes[branch]]])
    return paths


def total_turn_deg(xy: NDArray[np.float64]) -> float:
    """The sum of a line's bend angles, each the turn between its sections."""
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 3:
        return 0.0
    step = np.diff(xy, axis=0)
    heading = np.degrees(np.arctan2(step[:, 1], step[:, 0]))
    return float(np.abs((np.diff(heading) + 180.0) % 360.0 - 180.0).sum())


def _fits(
    xy: NDArray[np.float64], tolerance_m: float, max_bends: int, max_turn_deg: float
) -> bool:
    """Whether a path is followed within the tolerance by few enough bends."""
    line = np.asarray(
        shapely.simplify(
            shapely.LineString(xy), tolerance_m, preserve_topology=False
        ).coords
    )
    return len(line) <= max_bends + 2 and total_turn_deg(line) <= max_turn_deg


def _along(xy: NDArray[np.float64]) -> NDArray[np.float64]:
    """The distance along the path at each point."""
    return np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]


def bend_ranges(
    xy: NDArray[np.float64],
    *,
    max_bends: int,
    tolerance_m: float,
    max_turn_deg: float = math.inf,
) -> list[Range]:
    """Cut a path where following it within the tolerance needs another bend.

    From the start, each piece runs as far along the path as Douglas-Peucker
    at ``tolerance_m`` still follows it with at most ``max_bends`` bends,
    turning no more than ``max_turn_deg`` in all (a binary search on the
    end); the next piece starts where it ends.
    """
    ranges = []
    start, n = 0, len(xy)
    while start < n - 1:
        if _fits(xy[start:], tolerance_m, max_bends, max_turn_deg):
            end = n - 1
        else:
            low, high = start + 1, n - 1
            while high - low > 1:
                middle = (low + high) // 2
                if _fits(xy[start : middle + 1], tolerance_m, max_bends, max_turn_deg):
                    low = middle
                else:
                    high = middle
            end = low
        ranges.append((start, end))
        start = end
    return ranges or [(0, max(n - 1, 0))]


def _chord(xy: NDArray[np.float64], piece: Range) -> float:
    """The straight distance between a piece's two end points."""
    a, b = piece
    return float(np.hypot(*(xy[b] - xy[a])))


def merge_short_ranges(
    xy: NDArray[np.float64],
    ranges: list[Range],
    min_length_m: float,
    *,
    max_length_m: float = math.inf,
) -> list[Range]:
    """Join every piece whose ends are under ``min_length_m`` apart to a neighbour.

    The ends' straight distance, not the length along the path, so the piece's
    line (which keeps the path's ends) is never shorter than
    ``min_length_m``. The shortest goes first, into the neighbour before it
    (after it, for the first) or, where that would make a piece longer than
    ``max_length_m`` along the path, the other neighbour; a piece neither
    can take stays.
    """
    along = _along(xy)
    ranges = list(ranges)
    stuck: set[Range] = set()
    while len(ranges) > 1:
        chords = [_chord(xy, r) if r not in stuck else math.inf for r in ranges]
        i = int(np.argmin(chords))
        if chords[i] >= min_length_m:
            break
        for j in (i - 1, i + 1) if i > 0 else (i + 1,):
            if not 0 <= j < len(ranges):
                continue
            low, high = min(i, j), max(i, j)
            joined = (ranges[low][0], ranges[high][1])
            if along[joined[1]] - along[joined[0]] <= max_length_m:
                ranges[low] = joined
                del ranges[high]
                break
        else:
            stuck.add(ranges[i])
    return ranges


def cap_positions(
    line: NDArray[np.float64],
    max_length_m: float,
    boundary_cuts: BoundaryCuts | None,
) -> tuple[str, list[float]]:
    """Where to cut a line over the cap, and by which rule.

    Returns:
        ``(stage, positions)``: ``bends`` (at the fewest of its bends that
        bring every part under the cap, the most even such set; or, where no
        set does, at the one bend that splits it most evenly),
        ``boundaries`` (where it crosses property boundaries) or ``even``
        (equal parts), and the cuts as distances along the line.
    """
    length = float(shapely.LineString(line).length)
    inner = [float(d) for d in _along(line)[1:-1]]
    if inner:
        for k in range(1, len(inner) + 1):
            best: tuple[float, tuple[float, ...]] | None = None
            for cut in combinations(inner, k):
                longest = float(np.diff([0.0, *cut, length]).max())
                if longest <= max_length_m + 1e-9 and (
                    best is None or longest < best[0]
                ):
                    best = (longest, cut)
            if best is not None:
                return "bends", list(best[1])
        middle = min(inner, key=lambda d: max(d, length - d))
        return "bends", [middle]
    if boundary_cuts is not None:
        cuts = [
            d
            for d in boundary_cuts(shapely.LineString(line))
            if 1e-6 < d < length - 1e-6
        ]
        if cuts:
            return "boundaries", cuts
    n_parts = math.ceil(length / max_length_m)
    return "even", [length * k / n_parts for k in range(1, n_parts)]


def cap_ranges(
    xy: NDArray[np.float64],
    ranges: list[Range],
    *,
    max_length_m: float,
    line_of: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    boundary_cuts: BoundaryCuts | None = None,
    counts: Counter | None = None,
) -> list[Range]:
    """Cut every piece whose line is over ``max_length_m`` until none is.

    Each piece's line (``line_of`` its stretch of path) over the cap is cut
    where :func:`cap_positions` says, each cut taken to the path point
    nearest it, and the parts are checked again; ``counts`` adds one per cut
    piece under its stage. A piece of two points is left whole.
    """
    if not math.isfinite(max_length_m):
        return list(ranges)
    out = []
    todo = list(ranges)
    while todo:
        a, b = todo.pop(0)
        line = line_of(xy[a : b + 1])
        shape = shapely.LineString(line)
        if shape.length <= max_length_m + 1e-9 or b - a < 2:
            out.append((a, b))
            continue
        stage, positions = cap_positions(line, max_length_m, boundary_cuts)
        inside = shapely.points(xy[a + 1 : b])
        cuts = sorted(
            {
                a + 1 + int(np.argmin(shapely.distance(inside, shape.interpolate(d))))
                for d in positions
            }
        )
        if not cuts:
            stage, cuts = "even", [(a + b) // 2]
        if counts is not None:
            counts[stage] += 1
        todo[:0] = list(pairwise([a, *cuts, b]))
    return out


def cut_path(
    xy: NDArray[np.float64],
    *,
    max_bends: int | None,
    tolerance_m: float,
    min_segment_m: float,
    max_length_m: float = math.inf,
    max_turn_deg: float = math.inf,
    boundary_cuts: BoundaryCuts | None = None,
    counts: Counter | None = None,
) -> list[Range]:
    """Cut a path by the bends rule, merge short pieces, then cap the length.

    Args:
        xy: The path's points, in order, in metres.
        max_bends: The most bends a piece may need; None skips the bends and
            turning rule.
        tolerance_m: How far a piece's line may stray from the path.
        min_segment_m: The least straight distance between a piece's ends
            (so its line is never shorter).
        max_length_m: The longest a piece's line may be (:func:`cap_ranges`).
        max_turn_deg: The most a piece's line may turn in all.
        boundary_cuts: Where a line crosses property boundaries, as
            distances along it (walls only); None skips that stage of the cap.
        counts: Counts the pieces the cap cut, by stage.

    Returns:
        The pieces as inclusive point ranges, in order along the path.
    """
    xy = np.asarray(xy, dtype=float)
    if len(xy) < 2:
        return [(0, max(len(xy) - 1, 0))]
    bends = max_bends if max_bends is not None else 10**6
    turn = max_turn_deg if max_bends is not None else math.inf
    ranges = (
        [(0, len(xy) - 1)]
        if max_bends is None
        else bend_ranges(
            xy, max_bends=max_bends, tolerance_m=tolerance_m, max_turn_deg=turn
        )
    )
    ranges = merge_short_ranges(xy, ranges, min_segment_m)
    ranges = cap_ranges(
        xy,
        ranges,
        max_length_m=max_length_m,
        # With no bends rule a piece's line is its chord, so the cap divides
        # it evenly.
        line_of=(lambda stretch: stretch[[0, -1]])
        if max_bends is None
        else (
            lambda stretch: canonical_line(
                stretch,
                tolerance_m=tolerance_m,
                max_bends=bends,
                min_segment_m=min_segment_m,
                max_turn_deg=turn,
            )
        ),
        boundary_cuts=boundary_cuts,
        counts=counts,
    )
    ranges = merge_short_ranges(xy, ranges, min_segment_m, max_length_m=max_length_m)
    return [part for piece in ranges for part in _unfold(xy, piece, min_segment_m)]


def _unfold(xy: NDArray[np.float64], piece: Range, min_length_m: float) -> list[Range]:
    """A piece folded back on itself, cut at its point furthest from its start.

    A piece whose ends are under ``min_length_m`` apart but that runs out and
    back (a horseshoe round a knoll) is cut in two where it turns, if both
    halves' ends are then far enough apart; otherwise it is left whole.
    """
    a, b = piece
    if _chord(xy, piece) >= min_length_m or b - a < 2:
        return [piece]
    turn = a + int(np.argmax(np.hypot(*(xy[a : b + 1] - xy[a]).T)))
    halves = [(a, turn), (turn, b)]
    if a < turn < b and all(_chord(xy, h) >= min_length_m for h in halves):
        return halves
    return [piece]


def canonical_line(
    xy: NDArray[np.float64],
    *,
    tolerance_m: float,
    max_bends: int,
    min_segment_m: float,
    max_turn_deg: float = math.inf,
) -> NDArray[np.float64]:
    """The line of one piece of a path: its ends, few bends, little turning.

    Douglas-Peucker at the tolerance (doubled until at most ``max_bends``
    bends turning no more than ``max_turn_deg`` in all,
    :func:`simplify_within`), every section shorter than ``min_segment_m``
    merged into its neighbours (:func:`drop_short_sections`, which never adds
    turning), and a line whose ends are under ``min_segment_m`` apart made
    straight. Every step keeps the path's two ends, so the line is no shorter
    than its ends' straight distance and no longer than the path; where those
    ends are still under ``min_segment_m`` apart (a stretch folded into a
    small loop), the line is the straight one between the stretch's two
    points furthest apart.
    """
    line = drop_short_sections(
        simplify_within(
            xy, tolerance_m=tolerance_m, max_bends=max_bends, max_turn_deg=max_turn_deg
        ),
        min_segment_m,
    )
    if np.hypot(*(line[-1] - line[0])) < min_segment_m:
        line = line[[0, -1]]
    if np.hypot(*(line[-1] - line[0])) < min_segment_m and len(xy) > 2:
        # A stretch folded back on itself (a small loop): the straight line
        # between its two points furthest apart, if that is long enough.
        gaps = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
        i, j = np.unravel_index(int(np.argmax(gaps)), gaps.shape)
        if gaps[i, j] > np.hypot(*(line[-1] - line[0])):
            line = xy[[min(i, j), max(i, j)]]
    return line


def rule_breaks(
    line: object,
    *,
    max_bends: int,
    min_length_m: float,
    max_length_m: float,
    max_turn_deg: float = math.inf,
) -> list[str]:
    """The rules a line breaks: one part, its bends and turning, its length.

    Returns:
        The names of the rules broken (``multipart``, ``bends``, ``turning``,
        ``short``, ``long``); empty where it keeps them all.
    """
    if line.geom_type != "LineString":
        return ["multipart"]
    broken = []
    if len(line.coords) - 2 > max_bends:
        broken.append("bends")
    if total_turn_deg(np.asarray(line.coords)) > max_turn_deg + 1e-6:
        broken.append("turning")
    if line.length < min_length_m - 1e-6:
        broken.append("short")
    if line.length > max_length_m + 1e-6:
        broken.append("long")
    return broken


def simplify_within(
    xy: NDArray[np.float64],
    *,
    tolerance_m: float,
    max_bends: int,
    max_turn_deg: float = math.inf,
) -> NDArray[np.float64]:
    """Douglas-Peucker at the tolerance, doubled until the line fits.

    A piece of :func:`cut_path` fits at the tolerance (at most ``max_bends``
    bends, turning no more than ``max_turn_deg``) unless a short piece was
    merged into it; then the tolerance is doubled until it fits (a straight
    line always does).
    """
    tolerance = tolerance_m
    line = shapely.simplify(shapely.LineString(xy), tolerance, preserve_topology=False)
    while (
        len(line.coords) > max_bends + 2
        or total_turn_deg(np.asarray(line.coords)) > max_turn_deg
    ):
        tolerance *= 2.0
        line = shapely.simplify(line, tolerance, preserve_topology=False)
    return np.asarray(line.coords)


def drop_short_sections(
    xy: NDArray[np.float64], min_segment_m: float
) -> NDArray[np.float64]:
    """Merge every section shorter than ``min_segment_m`` into its neighbours.

    The shortest section goes first. An end section loses its inner vertex
    (the line's ends stay); an inner one loses whichever of its two vertices
    lies nearer the line joining that vertex's neighbours, so the line moves
    least. Repeated until every section is long enough or one is left.
    Dropping a vertex never adds to the line's total turning.
    """
    xy = np.asarray(xy, dtype=float)
    while len(xy) > 2:
        lengths = np.hypot(*np.diff(xy, axis=0).T)
        i = int(np.argmin(lengths))
        if lengths[i] >= min_segment_m:
            break
        if i == 0:
            drop = 1
        elif i == len(lengths) - 1:
            drop = len(xy) - 2
        else:
            offsets = [
                shapely.distance(
                    shapely.Point(xy[k]), shapely.LineString([xy[k - 1], xy[k + 1]])
                )
                for k in (i, i + 1)
            ]
            drop = i if offsets[0] <= offsets[1] else i + 1
        xy = np.delete(xy, drop, axis=0)
    return xy
