"""Candidate retaining wall lines: where a wall could stand.

A retaining wall inventory does not exist for the study area (**L-04**), so the
population is drawn from *candidate lines*: every piece of geometry that marks
where a wall could be, each carrying what the terrain and the ground map say
about it and no probability. ``gen_wall_lines.py`` in exposure rw step 6 writes
them; ``gen_wall_probability.py`` puts a probability on each.

The sources, in :data:`SOURCES`, are in the order they are trusted
(``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``,
section 1.1): the retaining walls GNS mapped in the SLIDE morphology layer,
visible from above and Wellington City only, so evidence a wall exists and
never that one does not [townsend_2020]; the SLIDE cut and fill lines of the
same layer; the edges of the SLIDE genesis cut slopes and fill bodies; breaks
in slope read off the urban failure candidates, the toe of a steep 1 m face
under gentler ground; and the property boundaries on sloping ground, split
into road frontages and the rest. Driveway edges are not a source in this
build.

What happens to a line, in :func:`build_wall_lines`: the mapped walls are
snapped onto the nearest candidate polygon edge within a tolerance; lines from
several sources that coincide collapse into the one of highest precedence;
every line is split at the claim property boundaries; the face height is read
along the line from the 5 m local relief; the ground map is read at the
midpoint; the wall is marked ``fill`` or ``cut`` from the cut-and-fill residual
on its uphill side, because a wall on the downhill edge of a platform holds
fill and one at the toe of a cut holds the face -- both typical Wellington
construction [monteith_2020]; the claim is assigned by the midpoint, with the
uphill or downhill neighbour taking a line that lies along a boundary; and
faces under the minimum wall height are dropped unless a wall is mapped there.
"""

from collections.abc import Iterable, Sequence
from itertools import pairwise
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree
from shapely.geometry import (
    LinearRing,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

from landloss.common.utils.terrain import azimuth_offsets, sample_at_points
from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from landloss.exposure.rw.beta_population import classify_wall_size
from landloss.hazard.landslide.ground_map import ROCK_MATERIALS

# The line sources in precedence order: where lines from two sources coincide,
# the earlier one is kept.
SOURCES = (
    "gns_mapped_wall",
    "slide_cut_fill_line",
    "slide_cut_edge",
    "slide_fill_edge",
    "terrain_break",
    "road_frontage",
    "property_boundary",
)

# The GNS SLIDE morphology ``Type`` that is a retaining wall [townsend_2020].
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"

# The GNS SLIDE morphology ``Type`` that marks the line between a cut and a fill
# [townsend_2020]; 2,421 lines, about 240 km, over Wellington City.
CUT_FILL_LINE_TYPE = "Cut/fill line"

# The SLIDE genesis ``Type`` values whose polygon edges are candidate lines, and
# the source each edge is recorded as.
GENESIS_EDGE_SOURCES = {"Cut slope": "slide_cut_edge", "Fill body": "slide_fill_edge"}

# A terrain break is the toe of a candidate patch in a slope band at or above
# the steep angle, where it meets a lower neighbour in a band below the gentle
# angle: the terrace-and-face signature of a cut, a fill or a wall.
TERRAIN_BREAK_STEEP_DEG = 45.0
TERRAIN_BREAK_GENTLE_DEG = 20.0

# A property boundary or road frontage is a candidate only where the 10 m slope
# at its midpoint is at least this: a wall on flat ground is a garden edge.
MIN_SLOPING_GROUND_DEG = 5.0

# How often the face height raster is read along a line.
FACE_SAMPLE_SPACING_M = 1.0

# How far uphill of the midpoint the cut-and-fill residual is read to decide
# whether the wall holds fill or a cut face.
POSITION_PROBE_DISTANCE_M = 3.0

# The two wall positions. A fill wall holds the platform above it; a cut wall
# holds the face behind it.
WALL_POSITIONS = ("fill", "cut")
FILL, CUT = WALL_POSITIONS

# What the ground map columns read at the midpoint are when no polygon covers
# it; the map is a planar partition of the extent, so this is off the extent.
UNKNOWN = "unknown"

SOURCE_COLUMN = "source"
MAPPED_COLUMN = "is_mapped_wall"

# The columns build_wall_lines returns, in order: section 3.5 of the contract
# minus wall_line_id, which the script mints.
COLUMNS = (
    SOURCE_COLUMN,
    MAPPED_COLUMN,
    CLAIM_ID_COLUMN,
    "face_height_m",
    "size_class",
    "wall_position",
    "is_flatland",
    "ground_id",
    "material",
    "modification",
    "is_rock_cut",
    "slope_degrees",
    "aspect_degrees",
    "dwelling_age_decade",
    "length_m",
    "geometry",
)

# The ground map columns read onto each line at its midpoint.
GROUND_COLUMNS = ("ground_id", "material", "modification", "is_flatland")

# A split point closer than this to a line's end is the end, not a cut.
_END_TOLERANCE_M = 1e-6

# The share of a line's length that has to lie within tolerance of another for
# the two to count as the same line, and of the boundaries for the line to
# count as lying along one.
_COINCIDENT_SHARE = 0.5


def _check_frames(*frames: gpd.GeoDataFrame | gpd.GeoSeries) -> None:
    """Refuse frames in different systems, or in a geographic one.

    Args:
        *frames: The frames being combined.

    Raises:
        ValueError: If two frames are in different coordinate reference
            systems, or if the system is geographic, where a tolerance of 3
            would be 3 degrees.
    """
    crs = frames[0].crs
    for frame in frames[1:]:
        if frame.crs != crs:
            msg = (
                f"The frames are in {crs} and {frame.crs}. Reproject one onto "
                "the other before building the wall lines."
            )
            raise ValueError(msg)
    if crs is not None and crs.is_geographic:
        msg = (
            f"{crs} is a geographic system, so a tolerance in metres would be "
            "that many degrees. Work in a projected system such as NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def _require(frame: pd.DataFrame, columns: Sequence[str], name: str) -> None:
    """Raise if a frame lacks a column the rule reads.

    Args:
        frame: The frame to check.
        columns: The columns it has to carry.
        name: What the frame is, for the message.

    Raises:
        ValueError: If a column is missing.
    """
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        msg = f"{name} is missing {missing}"
        raise ValueError(msg)


def _line_parts(geometry: BaseGeometry | None) -> list[LineString]:
    """Return the LineStrings a geometry is made of, polygon edges included.

    Args:
        geometry: Any geometry, or None.

    Returns:
        Every non-empty line part: a line as itself, a ring as a line, a
        polygon as the parts of its boundary, a collection as its parts.
        Points are dropped.
    """
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, LinearRing):
        return [LineString(geometry.coords)]
    if isinstance(geometry, LineString):
        return [geometry] if geometry.length > 0 else []
    if isinstance(geometry, Polygon | MultiPolygon):
        return _line_parts(geometry.boundary)
    if hasattr(geometry, "geoms"):
        return [part for member in geometry.geoms for part in _line_parts(member)]
    return []


def _point_parts(geometry: BaseGeometry | None) -> list[Point]:
    """Return the Points a geometry is made of; lines and polygons are dropped.

    Args:
        geometry: Any geometry, or None.

    Returns:
        Every point part.
    """
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Point):
        return [geometry]
    if isinstance(geometry, MultiPoint) or (
        hasattr(geometry, "geoms") and not isinstance(geometry, MultiLineString)
    ):
        return [part for member in geometry.geoms for part in _point_parts(member)]
    return []


def _lines_frame(
    geometries: Iterable[BaseGeometry | None], source: str, crs: object
) -> gpd.GeoDataFrame:
    """Wrap geometries as one line per part with a source.

    Args:
        geometries: The geometries to explode into lines.
        source: The source name every part carries.
        crs: The coordinate reference system of the geometries.

    Returns:
        A frame of ``source`` and ``geometry`` (LineString), fresh index.
    """
    parts = [part for geometry in geometries for part in _line_parts(geometry)]
    return gpd.GeoDataFrame(
        {SOURCE_COLUMN: pd.Series([source] * len(parts), dtype=object)},
        geometry=gpd.GeoSeries(parts, crs=crs),
        crs=crs,
    )


def _concat_lines(frames: Sequence[gpd.GeoDataFrame], crs: object) -> gpd.GeoDataFrame:
    """Stack line frames on a fresh index, keeping the CRS when every one is empty.

    Args:
        frames: The frames to stack.
        crs: The coordinate reference system to give an empty result.

    Returns:
        One frame of ``source`` and ``geometry``.
    """
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return _lines_frame([], SOURCES[0], crs).iloc[0:0]
    stacked = pd.concat(non_empty, ignore_index=True)
    return gpd.GeoDataFrame(stacked, geometry="geometry", crs=crs)


def _band_bounds(labels: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Return the lower and upper angle of each slope band label.

    Args:
        labels: Band labels such as ``"30-45"`` or ``"60+"``.

    Returns:
        The lower bound and the upper bound in degrees; an open band's upper
        bound is infinite.

    Raises:
        ValueError: If a label is not ``<lower>-<upper>`` or ``<lower>+``.
    """
    lower = np.empty(len(labels))
    upper = np.empty(len(labels))
    for position, label in enumerate(labels.astype(str)):
        try:
            if label.endswith("+"):
                lower[position] = float(label[:-1])
                upper[position] = np.inf
            else:
                low, high = label.split("-")
                lower[position] = float(low)
                upper[position] = float(high)
        except ValueError as error:
            msg = f"{label!r} is not a slope band label such as '30-45' or '60+'"
            raise ValueError(msg) from error
    return lower, upper


def mapped_wall_lines(morphology: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the GNS-mapped retaining walls as candidate lines.

    Args:
        morphology: The GNS SLIDE morphology lines, with a ``Type`` column.

    Returns:
        One ``gns_mapped_wall`` line per part of every wall feature.

    Raises:
        ValueError: If the morphology carries no ``Type`` column.
    """
    _require(morphology, ("Type",), "morphology")
    walls = morphology.loc[morphology["Type"] == MAPPED_WALL_TYPE]
    return _lines_frame(walls.geometry, SOURCES[0], morphology.crs)


def slide_cut_fill_lines(morphology: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the GNS-mapped cut and fill lines as candidate lines.

    Args:
        morphology: The GNS SLIDE morphology lines, with a ``Type`` column.

    Returns:
        One ``slide_cut_fill_line`` line per part of every such feature.

    Raises:
        ValueError: If the morphology carries no ``Type`` column.
    """
    _require(morphology, ("Type",), "morphology")
    lines = morphology.loc[morphology["Type"] == CUT_FILL_LINE_TYPE]
    return _lines_frame(lines.geometry, SOURCES[1], morphology.crs)


def genesis_edge_lines(genesis: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the edges of the SLIDE cut slopes and fill bodies as candidate lines.

    Args:
        genesis: The GNS SLIDE genesis polygons, with a ``Type`` column.

    Returns:
        One line per boundary part, ``slide_cut_edge`` for a cut slope and
        ``slide_fill_edge`` for a fill body, in that order.

    Raises:
        ValueError: If the genesis layer carries no ``Type`` column.
    """
    _require(genesis, ("Type",), "genesis")
    frames = [
        _lines_frame(genesis.loc[genesis["Type"] == kind].geometry, source, genesis.crs)
        for kind, source in GENESIS_EDGE_SOURCES.items()
    ]
    return _concat_lines(frames, genesis.crs)


def terrain_break_lines(
    candidates: gpd.GeoDataFrame,
    *,
    steep_deg: float,
    gentle_deg: float,
    min_face_height_m: float,
) -> gpd.GeoDataFrame:
    """Return the toes of steep candidate patches as candidate lines.

    A terrain break is the edge a patch in a band at or above ``steep_deg``
    shares with a neighbour in a band whose top is at or below ``gentle_deg``,
    where the steep patch's ``face_height_5m`` is at least
    ``min_face_height_m``. Only the downhill edge counts: the shared edge's
    midpoint has to lie downhill of the steep patch's representative point
    along its ``aspect_degrees``, so the crest of the face is not a line. A
    steep patch with no aspect keeps every such edge.

    Args:
        candidates: The urban failure candidates at one scale, carrying
            ``slope_band``, ``face_height_5m`` and ``aspect_degrees``.
        steep_deg: The lowest band edge that counts as the face.
        gentle_deg: The highest band edge that counts as the ground below it.
        min_face_height_m: The least 5 m relief the face has to carry.

    Returns:
        One ``terrain_break`` line per merged shared edge.

    Raises:
        ValueError: If a required column is missing or a band label is
            unreadable.
    """
    _require(
        candidates, ("slope_band", "face_height_5m", "aspect_degrees"), "candidates"
    )
    crs = candidates.crs
    lower, upper = _band_bounds(candidates["slope_band"])
    face = candidates["face_height_5m"].to_numpy(dtype=float)
    steep = candidates.loc[(lower >= steep_deg) & (face >= min_face_height_m)]
    gentle = candidates.loc[upper <= gentle_deg]
    if steep.empty or gentle.empty:
        return _lines_frame([], SOURCES[4], crs)

    pairs = gpd.sjoin(
        steep[["aspect_degrees", "geometry"]],
        gentle[["geometry"]],
        how="inner",
        predicate="intersects",
    )
    lines = []
    for steep_geometry, aspect, gentle_label in zip(
        pairs.geometry, pairs["aspect_degrees"], pairs["index_right"], strict=True
    ):
        shared = steep_geometry.boundary.intersection(
            gentle.geometry.loc[gentle_label].boundary
        )
        parts = _line_parts(shared)
        if not parts:
            continue
        merged = shapely.line_merge(MultiLineString(parts))
        anchor = steep_geometry.representative_point()
        east, north = azimuth_offsets(aspect, 1.0)
        for edge in _line_parts(merged):
            middle = edge.interpolate(0.5, normalized=True)
            downhill = (middle.x - anchor.x) * east + (middle.y - anchor.y) * north
            if not np.isfinite(downhill) or downhill > 0:
                lines.append(edge)
    return _lines_frame(lines, SOURCES[4], crs)


def _boundary_pieces(properties: gpd.GeoDataFrame) -> list[LineString]:
    """Return the property boundaries as noded, merged linework.

    Shared boundaries appear once, and each piece runs between junctions.

    Args:
        properties: The claim property polygons.

    Returns:
        The boundary pieces.
    """
    if properties.empty:
        return []
    linework = shapely.union_all(properties.boundary.to_numpy())
    return _line_parts(shapely.line_merge(linework))


def boundary_lines(
    properties: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    *,
    road_distance_m: float,
    slope_path: Path,
    min_slope_deg: float,
) -> gpd.GeoDataFrame:
    """Return the property boundaries on sloping ground as candidate lines.

    The boundaries are noded and merged so a boundary two properties share is
    one line running between junctions. A piece within ``road_distance_m`` of
    a road centreline is a ``road_frontage``; any other is a
    ``property_boundary``. Both are kept only where the slope at the piece's
    midpoint, read from ``slope_path``, is at least ``min_slope_deg``; a
    midpoint off the raster reads NaN and is dropped.

    Args:
        properties: The claim property polygons.
        roads: The road centrelines.
        road_distance_m: How near a road a piece has to be to front it.
        slope_path: The slope raster the midpoints are read from, in degrees:
            the 10 m slope, so a boundary is judged on the ground around it
            rather than on one cell.
        min_slope_deg: The least slope a piece is kept on.

    Returns:
        One line per kept piece, ``road_frontage`` before ``property_boundary``.
    """
    _check_frames(properties, roads)
    crs = properties.crs
    pieces = _boundary_pieces(properties)
    if not pieces:
        return _lines_frame([], SOURCES[6], crs)

    segments = gpd.GeoSeries(pieces, crs=crs)
    slope = sample_at_points(slope_path, segments.interpolate(0.5, normalized=True))
    # NaN compares False, so a midpoint off the raster is dropped.
    segments = segments.loc[(slope >= min_slope_deg).to_numpy()]
    if segments.empty:
        return _lines_frame([], SOURCES[6], crs)

    near_road = np.zeros(len(segments), dtype=bool)
    if not roads.empty:
        tree = STRtree(roads.geometry.to_numpy())
        left, _ = tree.query(
            segments.to_numpy(), predicate="dwithin", distance=road_distance_m
        )
        near_road[np.unique(left)] = True

    frontages = _lines_frame(segments.loc[near_road], SOURCES[5], crs)
    boundaries = _lines_frame(segments.loc[~near_road], SOURCES[6], crs)
    return _concat_lines([frontages, boundaries], crs)


def snap_to_candidate_edges(
    lines: gpd.GeoDataFrame, candidates: gpd.GeoDataFrame, *, tolerance_m: float
) -> gpd.GeoDataFrame:
    """Move lines onto the nearest candidate polygon edge within a tolerance.

    Each line is matched to the candidate boundary nearest to it, if one lies
    within ``tolerance_m``; every vertex of the line within ``tolerance_m`` of
    that boundary is moved to its nearest point on it, and the rest stay. A
    line with no boundary within reach is returned as it was, as is one the
    move would collapse to nothing.

    Args:
        lines: The lines to snap, usually the mapped walls.
        candidates: The urban failure candidates, polygons.
        tolerance_m: How far a vertex is moved at most.

    Returns:
        A copy of ``lines`` with the snapped geometry.
    """
    _check_frames(lines, candidates)
    snapped = lines.copy()
    if lines.empty or candidates.empty:
        return snapped

    edges = shapely.boundary(candidates.geometry.to_numpy())
    tree = STRtree(edges)
    moved = []
    for line in lines.geometry:
        hits = tree.query_nearest(line, max_distance=tolerance_m)
        if len(hits) == 0:
            moved.append(line)
            continue
        edge = edges[hits[0]]
        coordinates = []
        for coordinate in line.coords:
            vertex = Point(coordinate[:2])
            if edge.distance(vertex) <= tolerance_m:
                vertex = edge.interpolate(edge.project(vertex))
            coordinates.append((vertex.x, vertex.y))
        candidate = LineString(coordinates)
        moved.append(candidate if candidate.length > 0 else line)
    snapped.geometry = gpd.GeoSeries(moved, index=lines.index, crs=lines.crs)
    return snapped


def collapse_coincident(
    lines: gpd.GeoDataFrame, *, tolerance_m: float
) -> gpd.GeoDataFrame:
    """Collapse lines from several sources that mark the same wall into one.

    Lines are taken in :data:`SOURCES` order, stable within a source. A line
    collapses into a line already kept when more than half its length lies
    within ``tolerance_m`` of it. The kept line is marked ``is_mapped_wall``
    where it, or any line collapsed into it, is a GNS mapped wall.

    Args:
        lines: The candidate lines, with ``source``.
        tolerance_m: How far apart two lines may be and still be one wall.

    Returns:
        The kept lines in precedence order on a fresh index, with
        ``is_mapped_wall`` appended.

    Raises:
        ValueError: If a ``source`` is not in :data:`SOURCES`.
    """
    _require(lines, (SOURCE_COLUMN,), "lines")
    _check_frames(lines)
    rank = lines[SOURCE_COLUMN].map({source: n for n, source in enumerate(SOURCES)})
    if rank.isna().any():
        unknown = sorted(set(lines.loc[rank.isna(), SOURCE_COLUMN]))
        msg = f"sources {unknown} are not in SOURCES {list(SOURCES)}"
        raise ValueError(msg)
    order = np.argsort(rank.to_numpy(dtype=float), kind="mergesort")
    ordered = lines.iloc[order].reset_index(drop=True)
    mapped = (ordered[SOURCE_COLUMN] == SOURCES[0]).to_numpy(dtype=bool).copy()
    kept = np.zeros(len(ordered), dtype=bool)
    if ordered.empty:
        return ordered.assign(**{MAPPED_COLUMN: mapped})

    geometries = ordered.geometry.to_numpy()
    tree = STRtree(geometries)
    corridors: dict[int, BaseGeometry] = {}
    for position, line in enumerate(geometries):
        neighbours = tree.query(line, predicate="dwithin", distance=tolerance_m)
        neighbours = np.sort(neighbours[(neighbours < position) & kept[neighbours]])
        target = -1
        for neighbour in neighbours:
            corridor = corridors.setdefault(
                int(neighbour), geometries[neighbour].buffer(tolerance_m)
            )
            share = line.intersection(corridor).length / line.length
            if share > _COINCIDENT_SHARE:
                target = int(neighbour)
                break
        if target < 0:
            kept[position] = True
        else:
            mapped[target] |= mapped[position]
    result = ordered.loc[kept].reset_index(drop=True)
    return result.assign(**{MAPPED_COLUMN: mapped[kept]})


def split_at_boundaries(
    lines: gpd.GeoDataFrame, properties: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Split every line where it crosses a property boundary.

    A line is cut at each point where it crosses a boundary piece, so that no
    line belongs to two properties. A line running along a boundary is not
    cut by it, and a line touching one at its end is not either.

    Args:
        lines: The candidate lines.
        properties: The claim property polygons.

    Returns:
        The pieces on a fresh index, each carrying its parent's columns.
    """
    _check_frames(lines, properties)
    pieces = _boundary_pieces(properties)
    if lines.empty or not pieces:
        return lines.reset_index(drop=True).copy()

    tree = STRtree(pieces)
    parents: list[int] = []
    geometries: list[LineString] = []
    for position, line in enumerate(lines.geometry):
        distances: set[float] = set()
        for hit in tree.query(line, predicate="intersects"):
            for point in _point_parts(line.intersection(pieces[hit])):
                along = line.project(point)
                if _END_TOLERANCE_M < along < line.length - _END_TOLERANCE_M:
                    distances.add(along)
        if not distances:
            parents.append(position)
            geometries.append(line)
            continue
        for start, end in pairwise([0.0, *sorted(distances), line.length]):
            piece = substring(line, start, end)
            if isinstance(piece, LineString) and piece.length > 0:
                parents.append(position)
                geometries.append(piece)
    split = lines.iloc[parents].reset_index(drop=True)
    split.geometry = gpd.GeoSeries(geometries, crs=lines.crs)
    return split


def face_height_m(
    lines: gpd.GeoSeries, face_height_path: Path, *, spacing_m: float
) -> pd.Series:
    """Read the face height along each line as the median of regular samples.

    Args:
        lines: The lines, in a projected system.
        face_height_path: The local relief raster, in metres.
        spacing_m: How far apart the samples are along the line, from its
            start. A line shorter than this is read at its midpoint.

    Returns:
        The median sampled relief per line, on ``lines.index``; NaN where
        every sample fell off the raster.
    """
    if lines.empty:
        return pd.Series(np.empty(0), index=lines.index, dtype=float)
    owners: list[object] = []
    points: list[Point] = []
    for label, line in lines.items():
        length = line.length
        if length < spacing_m:
            distances = np.array([length / 2.0])
        else:
            distances = np.arange(0.0, length + _END_TOLERANCE_M, spacing_m)
        for distance in distances:
            owners.append(label)
            points.append(line.interpolate(float(distance)))
    sampled = sample_at_points(face_height_path, gpd.GeoSeries(points, crs=lines.crs))
    values = pd.Series(sampled.to_numpy(dtype=float), index=owners)
    # A pandas median skips NaN, and an all-NaN group is NaN.
    return values.groupby(level=0, sort=False).median().reindex(lines.index)


def _midpoints(lines: gpd.GeoSeries) -> gpd.GeoSeries:
    """Return the midpoint of each line along its length."""
    return lines.interpolate(0.5, normalized=True)


def _offset_points(
    points: gpd.GeoSeries, azimuth_degrees: np.ndarray, distance_m: float
) -> gpd.GeoSeries:
    """Move each point along a bearing; a point with no bearing stays put."""
    east, north = azimuth_offsets(azimuth_degrees, distance_m)
    east = np.where(np.isfinite(east), east, 0.0)
    north = np.where(np.isfinite(north), north, 0.0)
    moved = shapely.points(points.x.to_numpy() + east, points.y.to_numpy() + north)
    return gpd.GeoSeries(moved, index=points.index, crs=points.crs)


def wall_position(
    lines: gpd.GeoSeries,
    aspect_degrees: pd.Series,
    residual_path: Path,
    *,
    probe_m: float,
) -> pd.Series:
    """Decide whether each line holds fill or a cut face.

    The cut-and-fill residual is read ``probe_m`` uphill of the midpoint,
    against the downhill azimuth: ground above the smoothed surface there is a
    platform of fill the wall holds (``fill``); anything else is a face cut
    into the hill (``cut``). A line with no azimuth reads the residual at the
    midpoint itself, and a probe off the raster reads NaN and is ``cut``.

    Args:
        lines: The lines, in a projected system.
        aspect_degrees: The downhill azimuth at each line, on ``lines.index``.
        residual_path: The 30 m cut-and-fill residual raster, in metres,
            negative for cut and positive for fill.
        probe_m: How far uphill of the midpoint the residual is read.

    Returns:
        ``fill`` or ``cut`` per line, on ``lines.index``.
    """
    if lines.empty:
        return pd.Series(np.empty(0, dtype=object), index=lines.index, dtype=object)
    uphill = aspect_degrees.to_numpy(dtype=float) + 180.0
    probes = _offset_points(_midpoints(lines), uphill, probe_m)
    residual = sample_at_points(residual_path, probes).to_numpy(dtype=float)
    position = np.where(residual >= 0.0, FILL, CUT)
    return pd.Series(position, index=lines.index, dtype=object)


def _lookup(
    points: gpd.GeoSeries, polygons: gpd.GeoDataFrame, columns: Sequence[str]
) -> pd.DataFrame:
    """Read polygon columns at each point, the first polygon where several cover it.

    Args:
        points: The points to read at.
        polygons: The polygons carrying ``columns``.
        columns: The columns to read.

    Returns:
        A frame of ``columns`` on ``points.index``, object dtype with None
        where no polygon covers the point.
    """
    frame = gpd.GeoDataFrame(
        {"_position": np.arange(len(points))},
        geometry=points.to_numpy(),
        crs=points.crs,
    )
    joined = gpd.sjoin(
        frame, polygons[[*columns, "geometry"]], how="left", predicate="within"
    )
    first = joined.drop_duplicates("_position").set_index("_position")
    read = first[list(columns)].reindex(np.arange(len(points))).astype(object)
    read = read.where(read.notna(), None)
    read.index = points.index
    return read


def assign_claim(
    lines: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    wall_position: pd.Series,
    aspect_degrees: pd.Series,
    tolerance_m: float,
) -> pd.Series:
    """Give each line the claim whose property it belongs to.

    The claim is the property containing the line's midpoint. A line lying
    along a boundary -- within ``tolerance_m`` of the property boundaries for
    more than half its length -- instead takes the property on its uphill side
    for a fill wall and its downhill side for a cut wall, read at twice
    ``tolerance_m`` from the midpoint along the azimuth, because the owner of
    the fill platform built the fill wall and the owner who cut into the hill
    built the cut wall. A line with no azimuth keeps the midpoint's claim.

    Args:
        lines: The candidate lines.
        properties: The claim property polygons, carrying ``claim_id``.
        wall_position: ``fill`` or ``cut`` per line, on ``lines.index``.
        aspect_degrees: The downhill azimuth per line, on ``lines.index``.
        tolerance_m: How near a boundary a line is to lie along it.

    Returns:
        The claim id per line, on ``lines.index``; None on road reserve or
        outside every claim property.

    Raises:
        ValueError: If the properties carry no ``claim_id``.
    """
    _check_frames(lines, properties)
    _require(properties, (CLAIM_ID_COLUMN,), "properties")
    if lines.empty:
        return pd.Series(np.empty(0, dtype=object), index=lines.index, dtype=object)

    middle = _midpoints(lines.geometry)
    claim = _lookup(middle, properties, (CLAIM_ID_COLUMN,))[CLAIM_ID_COLUMN]

    pieces = _boundary_pieces(properties)
    if not pieces:
        return claim
    tree = STRtree(pieces)
    along = np.zeros(len(lines), dtype=bool)
    for position, line in enumerate(lines.geometry):
        hits = tree.query(line, predicate="dwithin", distance=tolerance_m)
        if len(hits) == 0:
            continue
        corridor = shapely.union_all([pieces[hit] for hit in hits]).buffer(tolerance_m)
        along[position] = (
            line.intersection(corridor).length > _COINCIDENT_SHARE * line.length
        )

    aspect = aspect_degrees.to_numpy(dtype=float)
    uphill = wall_position.to_numpy() == FILL
    bearing = np.where(uphill, aspect + 180.0, aspect)
    sided = along & np.isfinite(bearing)
    if sided.any():
        probes = _offset_points(middle.loc[sided], bearing[sided], 2.0 * tolerance_m)
        side_claim = _lookup(probes, properties, (CLAIM_ID_COLUMN,))[CLAIM_ID_COLUMN]
        claim = claim.copy()
        claim.loc[sided] = side_claim.to_numpy()
    return claim


def build_wall_lines(
    *,
    morphology: gpd.GeoDataFrame,
    genesis: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    candidates: gpd.GeoDataFrame,
    ground_map: gpd.GeoDataFrame,
    face_height_path: Path,
    residual_path: Path,
    slope_3m_path: Path,
    slope_10m_path: Path,
    aspect_path: Path,
    snap_tolerance_m: float,
    road_distance_m: float,
    min_slope_deg: float,
    min_wall_height_m: float,
) -> gpd.GeoDataFrame:
    """Build the candidate wall lines from every source, attributed, no ids.

    In order: the mapped walls are snapped to the candidate edges; the lines
    of every source are stacked and coincident ones collapsed; every line is
    split at the property boundaries; the face height is read along each
    line, the slope and azimuth at its midpoint, the ground map at its
    midpoint; the wall position and then the claim are decided; lines with a
    face under ``min_wall_height_m`` are dropped unless a wall is mapped
    there, in which case they are kept and classed small, because the 1 m grid
    cannot resolve a sub-metre wall and a mapped wall is evidence one exists.

    The property boundaries and road frontages are limited to within
    :data:`~landloss.domain.constants.URBAN_BUILDING_DISTANCE_M` of a building
    outline, the urban domain the candidates are delineated in, so a rural
    boundary draws no line.

    Args:
        morphology: The GNS SLIDE morphology lines, with ``Type``.
        genesis: The GNS SLIDE genesis polygons, with ``Type``.
        properties: The claim properties, one polygon per claim with
            ``claim_id``.
        roads: The road centrelines.
        buildings: The building outlines.
        candidates: The urban failure candidates at every scale; the finest
            scale present supplies the terrain breaks.
        ground_map: The ground map, carrying :data:`GROUND_COLUMNS`.
        face_height_path: The 5 m local relief raster.
        residual_path: The 30 m cut-and-fill residual raster.
        slope_3m_path: The 3 m slope raster, read at the midpoint.
        slope_10m_path: The 10 m slope raster, read by :func:`boundary_lines`.
        aspect_path: The 3 m downhill azimuth raster, read at the midpoint.
        snap_tolerance_m: The snap and coincidence tolerance.
        road_distance_m: How near a road a boundary piece fronts it.
        min_slope_deg: The least 10 m slope a boundary piece is kept on.
        min_wall_height_m: The least face height an unmapped line is kept at.

    Returns:
        One row per line carrying :data:`COLUMNS`, on a fresh index, in
        precedence order; ``wall_line_id`` is minted by the caller.

    Raises:
        ValueError: If the frames disagree on their coordinate reference
            system, or a required column is missing.
    """
    _check_frames(
        morphology, genesis, properties, roads, buildings, candidates, ground_map
    )
    _require(ground_map, GROUND_COLUMNS, "ground_map")
    _require(candidates, ("scale_m",), "candidates")
    crs = properties.crs

    mapped = snap_to_candidate_edges(
        mapped_wall_lines(morphology), candidates, tolerance_m=snap_tolerance_m
    )
    finest = candidates.loc[candidates["scale_m"] == candidates["scale_m"].min()]
    breaks = terrain_break_lines(
        finest,
        steep_deg=TERRAIN_BREAK_STEEP_DEG,
        gentle_deg=TERRAIN_BREAK_GENTLE_DEG,
        min_face_height_m=min_wall_height_m,
    )
    boundaries = boundary_lines(
        properties,
        roads,
        road_distance_m=road_distance_m,
        slope_path=slope_10m_path,
        min_slope_deg=min_slope_deg,
    )
    if not boundaries.empty and not buildings.empty:
        tree = STRtree(buildings.geometry.to_numpy())
        near, _ = tree.query(
            boundaries.geometry.to_numpy(),
            predicate="dwithin",
            distance=constants.URBAN_BUILDING_DISTANCE_M,
        )
        boundaries = boundaries.iloc[np.unique(near)].reset_index(drop=True)
    elif not boundaries.empty:
        boundaries = boundaries.iloc[0:0]

    stacked = _concat_lines(
        [
            mapped,
            slide_cut_fill_lines(morphology),
            genesis_edge_lines(genesis),
            breaks,
            boundaries,
        ],
        crs,
    )
    collapsed = collapse_coincident(stacked, tolerance_m=snap_tolerance_m)
    lines = split_at_boundaries(collapsed, properties)

    middle = _midpoints(lines.geometry)
    face = face_height_m(
        lines.geometry, face_height_path, spacing_m=FACE_SAMPLE_SPACING_M
    )
    slope = sample_at_points(slope_3m_path, middle)
    aspect = sample_at_points(aspect_path, middle)
    position = wall_position(
        lines.geometry, aspect, residual_path, probe_m=POSITION_PROBE_DISTANCE_M
    )
    claim = assign_claim(
        lines,
        properties,
        wall_position=position,
        aspect_degrees=aspect,
        tolerance_m=snap_tolerance_m,
    )
    ground = _lookup(middle, ground_map, GROUND_COLUMNS)
    material = ground["material"].where(ground["material"].notna(), UNKNOWN)
    modification = ground["modification"].where(ground["modification"].notna(), UNKNOWN)
    flat = ground["is_flatland"].where(ground["is_flatland"].notna(), other=False)

    face_values = face.to_numpy(dtype=float)
    is_mapped = lines[MAPPED_COLUMN].to_numpy(dtype=bool)
    keep = (face_values >= min_wall_height_m) | is_mapped
    # A mapped wall with no readable face is kept and classed small.
    size = classify_wall_size(np.where(np.isfinite(face_values), face_values, 0.0))

    built = gpd.GeoDataFrame(
        {
            SOURCE_COLUMN: lines[SOURCE_COLUMN].to_numpy(),
            MAPPED_COLUMN: is_mapped,
            CLAIM_ID_COLUMN: claim.to_numpy(),
            "face_height_m": face_values,
            "size_class": size,
            "wall_position": position.to_numpy(),
            "is_flatland": flat.to_numpy(dtype=bool),
            "ground_id": ground["ground_id"].to_numpy(),
            "material": material.to_numpy(),
            "modification": modification.to_numpy(),
            "is_rock_cut": material.isin(ROCK_MATERIALS).to_numpy()
            & (modification.to_numpy() == "cut"),
            "slope_degrees": slope.to_numpy(dtype=float),
            "aspect_degrees": aspect.to_numpy(dtype=float),
            "dwelling_age_decade": pd.array([pd.NA] * len(lines), dtype="Int64"),
            "length_m": lines.geometry.length.to_numpy(dtype=float),
        },
        geometry=lines.geometry.to_numpy(),
        crs=crs,
    )
    return built.loc[keep, list(COLUMNS)].reset_index(drop=True)
