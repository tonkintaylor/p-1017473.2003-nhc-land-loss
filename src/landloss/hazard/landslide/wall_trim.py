"""Align a wall unit's evacuated polygons with the wall's line.

The evacuated polygon of a walled element should end at the retaining wall: it
holds no land in front of (downhill of) the wall, and leaves no gap behind it.
Landslide step 4 cuts an element's evacuated zone into segments along the
contour, each its own polygon, so a unit's polygons are aligned together
(:func:`align_unit`). Two things are done to them (the lead, 2026-10-13):

1. **Trim.** Each polygon within ``beside_m`` of the unit's line is split by
   the line, its ends projected straight on along the headings of the end
   sections (reach: the polygon's bounding box diagonal plus ``extend_pad_m``),
   and the pieces downhill of the extended line, by the pif's mean fall, are
   removed. A polygon the cut does not split, with nothing in front of the
   line, or that would lose all of itself, is kept whole.
2. **Fill.** The line is sampled every ``sample_m`` and each sample's distance
   to the union of the unit's trimmed polygons is measured. The samples within
   ``close_m`` anchor the fill. Between the first and the last anchor, every
   run of samples further than ``gap_m`` is filled; the end sections beyond
   the outer anchors are not. A ribbon runs from each sample along the line's
   normal, to the side the polygons are nearer, to where the ray meets a
   polygon, overlapping it by ``overlap_m``; each piece of ribbon joins the
   polygon its ray met. A ray is held to ``oblique_factor`` times the sample's
   distance to the polygons plus ``oblique_pad_m``, so it cannot run across a
   notch to the polygon's far edge.

Only the polygons of a walled element are aligned. An element grown from a
pif piece with no wall is its own element with no wall unit, and its polygons
stay as built.

The settings are given by the caller (:class:`WallTrimSettings`); this module
holds no values of its own.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import shapely
from shapely.geometry.base import BaseGeometry
from shapely.ops import split

FloatArray = npt.NDArray[np.float64]

HOW_LINE_CUTS = "line cuts"
HOW_PROJECTED = "projected"
HOW_NO_CUT = "no cut"
HOW_NOTHING_IN_FRONT = "nothing in front"
HOW_ALL_IN_FRONT = "all in front"
HOW_BEYOND_WALL = "beyond wall"
HOW_NO_LINE = "no line"
HOW_EMPTY = "empty"


@dataclass(frozen=True)
class WallTrimSettings:
    """The settings of the trim and fill (see the module docstring).

    Attributes:
        beside_m: A polygon further than this from the line is not beside the
            wall and is left whole.
        extend_pad_m: How far past a polygon's bounding box diagonal the line's
            ends are projected on, in metres.
        sliver_m2: Pieces smaller than this are slivers of a split and are
            ignored in the counts.
        sample_m: The line is sampled this often, in metres.
        close_m: A sample this near the polygons anchors a fill.
        gap_m: A sample further off the polygons than this leaves a gap to fill.
        ray_m: The furthest a ray looks for a polygon, in metres.
        overlap_m: The fill runs this far into the polygon so the union closes.
        oblique_factor: A ray reaches at most this times the sample's distance
            to the polygons ...
        oblique_pad_m: ... plus this, in metres.
    """

    beside_m: float
    extend_pad_m: float
    sliver_m2: float
    sample_m: float
    close_m: float
    gap_m: float
    ray_m: float
    overlap_m: float
    oblique_factor: float
    oblique_pad_m: float


@dataclass(frozen=True)
class PolygonAlignment:
    """One polygon's trim and fill.

    Attributes:
        aligned: The polygon after the trim and fill (the union of what is kept
            and the fill, made valid); empty for an empty input.
        kept: What the trim kept, before the fill.
        removed: What the trim removed (downhill of the wall); empty if none.
        fill: The new ground the fill added (the fill less what was kept).
        how: How the trim went: ``line cuts``, ``projected``, ``no cut``,
            ``nothing in front``, ``all in front``, ``beyond wall``, ``no line``
            or ``empty``.
        line_inside_share: The share of the line's length inside the polygon.
        line_to_polygon_m: The distance from the line to the polygon.
        n_pieces: The number of pieces (of at least ``sliver_m2``) the
            extended line cut the polygon into.
    """

    aligned: BaseGeometry
    kept: BaseGeometry
    removed: BaseGeometry
    fill: BaseGeometry
    how: str
    line_inside_share: float
    line_to_polygon_m: float
    n_pieces: int

    @property
    def area_removed_m2(self) -> float:
        """The area the trim removed, in square metres."""
        return float(self.removed.area)

    @property
    def area_filled_m2(self) -> float:
        """The area the fill added, in square metres."""
        return float(self.fill.area)


@dataclass(frozen=True)
class _Trim:
    """The result of trimming one polygon."""

    kept: BaseGeometry
    removed: BaseGeometry
    how: str
    line_inside_share: float
    line_to_polygon_m: float
    n_pieces: int


def mean_fall(directions: npt.ArrayLike, steps: npt.ArrayLike) -> FloatArray:
    """A pif's fall as a unit vector: the mean of its pips' falls.

    Args:
        directions: Each pip's fall direction, as an index into ``steps``.
        steps: The (x, y) step of each direction index.

    Returns:
        The mean of the pips' unit falls, as a unit vector.
    """
    step = np.asarray(steps, dtype=float)[np.asarray(directions, dtype=int)]
    fall = (step / np.hypot(*step.T)[:, None]).mean(axis=0)
    return fall / np.hypot(*fall)


def extend_line(line: shapely.LineString, reach: float) -> shapely.LineString:
    """The line with each end projected on along its end section's heading.

    Args:
        line: The line, of at least two distinct points.
        reach: How far each end is projected, in metres.

    Returns:
        The extended line.
    """
    xy = shapely.get_coordinates(line)
    head = xy[0] - xy[1]
    tail = xy[-1] - xy[-2]
    start = xy[0] + reach * head / max(np.hypot(*head), 1e-9)
    end = xy[-1] + reach * tail / max(np.hypot(*tail), 1e-9)
    return shapely.LineString(np.vstack([start, xy, end]))


def split_pieces(polygon: BaseGeometry, cutter: BaseGeometry) -> list[BaseGeometry]:
    """The polygon's parts after splitting each by the cutter.

    Args:
        polygon: A polygon or multipolygon.
        cutter: The line to split by.

    Returns:
        The pieces.
    """
    out: list[BaseGeometry] = []
    for part in getattr(polygon, "geoms", [polygon]):
        out.extend(split(part, cutter).geoms)
    return out


def is_front(piece: BaseGeometry, cut: shapely.LineString, fall: FloatArray) -> bool:
    """Whether a piece lies downhill of the cut line, by the fall.

    Args:
        piece: The piece.
        cut: The (extended) line.
        fall: The fall as a unit vector.

    Returns:
        True if the piece's representative point lies downhill of the line.
    """
    point = piece.representative_point()
    nearest = cut.interpolate(cut.project(point))
    return float(np.dot([point.x - nearest.x, point.y - nearest.y], fall)) > 0


def _whole(polygon: BaseGeometry, line: BaseGeometry, how: str) -> _Trim:
    """A polygon left as it is."""
    return _Trim(
        kept=polygon,
        removed=shapely.Polygon(),
        how=how,
        line_inside_share=0.0,
        line_to_polygon_m=float(line.distance(polygon)) if not line.is_empty else 0.0,
        n_pieces=1,
    )


def trim_polygon(
    polygon: BaseGeometry,
    line: shapely.LineString,
    fall: FloatArray,
    settings: WallTrimSettings,
) -> _Trim:
    """Cut the polygon with the line (projected on if short) and drop the downhill side.

    Args:
        polygon: The polygon, not empty.
        line: The wall's line, of at least two distinct points.
        fall: The pif's fall as a unit vector.
        settings: The trim settings.

    Returns:
        What was kept and removed and how the cut went.
    """
    inside = line.intersection(polygon).length / max(line.length, 1e-9)
    direct = split_pieces(polygon, line)
    bounds = np.reshape(polygon.bounds, (2, 2))
    reach = float(np.hypot(*np.subtract(*bounds))) + settings.extend_pad_m
    cut = extend_line(line, reach)
    parts = split_pieces(polygon, cut)
    front = [is_front(p, cut, fall) for p in parts]
    kept = shapely.union_all([p for p, f in zip(parts, front, strict=True) if not f])
    gone = shapely.union_all([p for p, f in zip(parts, front, strict=True) if f])
    n_parts = int(sum(p.area >= settings.sliver_m2 for p in parts))
    if sum(p.area >= settings.sliver_m2 for p in direct) >= 2:
        how = HOW_LINE_CUTS
    elif n_parts >= 2:
        how = HOW_PROJECTED
    else:
        how = HOW_NO_CUT
    # A polygon the cut does not split, or that lies wholly downhill of it,
    # is kept whole and flagged rather than dropped.
    if how == HOW_NO_CUT and not any(front):
        how = HOW_NOTHING_IN_FRONT
    if (
        how in (HOW_NO_CUT, HOW_NOTHING_IN_FRONT)
        or kept.is_empty
        or kept.area < settings.sliver_m2
    ):
        if how not in (HOW_NO_CUT, HOW_NOTHING_IN_FRONT):
            how = HOW_ALL_IN_FRONT
        kept, gone = polygon, shapely.Polygon()
    return _Trim(
        kept=kept,
        removed=gone,
        how=how,
        line_inside_share=float(inside),
        line_to_polygon_m=float(line.distance(polygon)),
        n_pieces=n_parts,
    )


def normals_at(line: shapely.LineString, s: FloatArray) -> FloatArray:
    """A unit normal (to the left) at each distance ``s`` along the line.

    Args:
        line: The line.
        s: Distances along the line, in metres.

    Returns:
        An (n, 2) array of unit normals.
    """
    xy = shapely.get_coordinates(line)
    along = np.r_[0.0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    seg = np.clip(np.searchsorted(along, s, side="right") - 1, 0, len(xy) - 2)
    run = xy[seg + 1] - xy[seg]
    run /= np.maximum(np.hypot(*run.T), 1e-12)[:, None]
    return np.column_stack([-run[:, 1], run[:, 0]])


def ray_hits(
    points: FloatArray,
    normals: FloatArray,
    polygons: list[BaseGeometry],
    ray_m: float,
) -> tuple[FloatArray, npt.NDArray[np.intp]]:
    """Distance up each ray to the first polygon it meets, and which one.

    Args:
        points: The (n, 2) ray origins.
        normals: The (n, 2) unit directions.
        polygons: The polygons to meet.
        ray_m: The length of each ray, in metres.

    Returns:
        The distance to the first polygon met and its index (inf and -1 if none).
    """
    rays = shapely.linestrings(np.stack([points, points + ray_m * normals], axis=1))
    reach = np.full(len(points), np.inf)
    which = np.full(len(points), -1)
    for k, poly in enumerate(polygons):
        hit = shapely.intersection(rays, poly)
        has = ~shapely.is_empty(hit)
        if not has.any():
            continue
        d = shapely.distance(shapely.points(points[has]), hit[has])
        idx = np.flatnonzero(has)
        better = d < reach[idx]
        reach[idx[better]] = d[better]
        which[idx[better]] = k
    return reach, which


def open_runs(
    gap: FloatArray, close: npt.NDArray[np.bool_], gap_m: float
) -> list[tuple[int, int]]:
    """The (start, end) sample index pairs to fill, between the outer anchors.

    The anchors are the ``close`` samples; between the first and the last of
    them every run of samples whose ``gap`` exceeds ``gap_m`` is filled, the
    pair taking in the sample at each side so the fill joins the polygon.

    Args:
        gap: Each sample's distance to the polygons, in metres.
        close: Whether each sample is an anchor.
        gap_m: The gap above which a sample is filled.

    Returns:
        The index pairs of each run to fill.
    """
    anchors = np.flatnonzero(close)
    if len(anchors) < 2:
        return []
    first, last = anchors[0], anchors[-1]
    open_ = np.zeros(len(gap), dtype=bool)
    open_[first : last + 1] = gap[first : last + 1] > gap_m
    edges = np.flatnonzero(np.diff(np.r_[0, open_.astype(int), 0]))
    return [
        (int(max(a - 1, first)), int(min(b, last)))
        for a, b in zip(edges[::2], edges[1::2], strict=True)
    ]


def fill_unit(
    line: shapely.LineString,
    polygons: list[BaseGeometry],
    settings: WallTrimSettings,
) -> list[tuple[int, BaseGeometry]]:
    """The fill pieces of one unit's polygons against its line.

    Args:
        line: The wall's line.
        polygons: The unit's trimmed polygons, none empty.
        settings: The fill settings.

    Returns:
        Each fill piece as (index of the polygon it joins, the piece).
    """
    if line.length < settings.sample_m or not polygons:
        return []
    n_steps = max(int(np.ceil(line.length / settings.sample_m)), 1)
    s = np.linspace(0.0, line.length, n_steps + 1)
    pts = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
    union = shapely.union_all(polygons)
    gap = shapely.distance(shapely.points(pts), union)
    close = gap <= settings.close_m
    pieces: list[tuple[int, BaseGeometry]] = []
    for a, b in open_runs(gap, close, settings.gap_m):
        idx = np.arange(a, b + 1)
        left = normals_at(line, s[idx])
        reach_l, which_l = ray_hits(pts[idx], left, polygons, settings.ray_m)
        reach_r, which_r = ray_hits(pts[idx], -left, polygons, settings.ray_m)
        # Each ray goes to the side the polygons are nearer.
        right = reach_r < reach_l
        normal = np.where(right[:, None], -left, left)
        reach = np.where(right, reach_r, reach_l)
        which = np.where(right, which_r, which_l)
        # A ray is held to an oblique edge's reach; one that meets nothing
        # (the polygon lies off to the side) takes that reach too.
        cap = settings.oblique_factor * gap[idx] + settings.oblique_pad_m
        reach = np.minimum(reach, cap)
        miss = which < 0
        if miss.any():
            which[miss] = [
                int(np.argmin([p.distance(shapely.Point(q)) for p in polygons]))
                for q in pts[idx][miss]
            ]
        width = reach + settings.overlap_m
        outer = pts[idx] + width[:, None] * normal
        for i in range(len(idx) - 1):
            quad = shapely.Polygon(
                [pts[idx[i]], pts[idx[i + 1]], outer[i + 1], outer[i]]
            )
            if quad.is_valid and quad.area > 0:
                pieces.append((int(which[i] if which[i] >= 0 else which[i + 1]), quad))
    return pieces


def _usable_line(line: BaseGeometry) -> bool:
    """Whether the line has two distinct points to cut and sample along."""
    if line is None or line.is_empty or line.geom_type != "LineString":
        return False
    xy = shapely.get_coordinates(line)
    return len(xy) >= 2 and bool(np.any(xy[1:] != xy[0]))


def align_unit(
    polygons: list[BaseGeometry],
    line: shapely.LineString,
    fall: npt.ArrayLike,
    settings: WallTrimSettings,
) -> list[PolygonAlignment]:
    """Trim and fill one wall unit's evacuated polygons against its line.

    Each polygon within ``beside_m`` of the line is trimmed at it; the line is
    then filled against the union of all the trimmed polygons, each piece of
    fill joining the polygon its ray met. A line that is empty or has no
    length leaves every polygon as it is (``no line``); an empty polygon
    comes back empty (``empty``).

    Args:
        polygons: The unit's evacuated polygons (polygons or multipolygons).
        line: The wall unit's line.
        fall: The pif's mean fall as a unit vector (x, y).
        settings: The trim and fill settings.

    Returns:
        One :class:`PolygonAlignment` per input polygon, in order.
    """
    fall_xy = np.asarray(fall, dtype=float)
    usable = _usable_line(line)
    trims: list[_Trim] = []
    for polygon in polygons:
        if polygon is None or polygon.is_empty:
            trims.append(_whole(shapely.Polygon(), shapely.LineString(), HOW_EMPTY))
        elif not usable:
            trims.append(_whole(polygon, shapely.LineString(), HOW_NO_LINE))
        elif line.distance(polygon) > settings.beside_m:
            trims.append(_whole(polygon, line, HOW_BEYOND_WALL))
        else:
            trims.append(trim_polygon(polygon, line, fall_xy, settings))
    members = [i for i, t in enumerate(trims) if not t.kept.is_empty]
    fills: dict[int, list[BaseGeometry]] = {i: [] for i in members}
    if usable and members:
        for k, quad in fill_unit(line, [trims[i].kept for i in members], settings):
            fills[members[k]].append(quad)
    out: list[PolygonAlignment] = []
    for i, trim in enumerate(trims):
        if i not in fills:
            out.append(_alignment(trim, shapely.Polygon(), shapely.Polygon()))
            continue
        fill = shapely.union_all(fills[i]) if fills[i] else shapely.Polygon()
        # Only what the polygon does not already hold is new ground.
        new = shapely.difference(fill, trim.kept) if not fill.is_empty else fill
        aligned = shapely.union_all([trim.kept, fill]).buffer(0)
        out.append(_alignment(trim, new, aligned))
    return out


def _alignment(
    trim: _Trim, fill: BaseGeometry, aligned: BaseGeometry
) -> PolygonAlignment:
    """Assemble one polygon's result."""
    return PolygonAlignment(
        aligned=aligned if not aligned.is_empty else trim.kept,
        kept=trim.kept,
        removed=trim.removed,
        fill=fill,
        how=trim.how,
        line_inside_share=trim.line_inside_share,
        line_to_polygon_m=trim.line_to_polygon_m,
        n_pieces=trim.n_pieces,
    )
