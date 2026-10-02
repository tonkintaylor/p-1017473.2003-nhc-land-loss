"""The geometry of an urban failure polygon and its fixed state geometries.

What belongs here: reconciling a candidate's edges to the wall lines, and the
evacuated, inundated and imminent geometry of each wall state (no wall, fill
wall, cut wall): the headscarp band, the fill wedge, the crest and toe lines,
and the depth rules. Each rule is a named function whose docstring cites its
source by ``doc/references.bib`` key or GNS finding id. The polygons are built
by landslide step 7 (``s7_urban_slope_polygons``).

The rules are the starting points of plan section 7
(``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``),
fixed where that plan gave a range by section 7.6 of the build contract
(``.agents/plans/urban-slope-build-contract.md``). Each is to be researched
and justified in the report; the constants at the top of this module are
where a researched number replaces a starting point.

Every geometry is planar and in a projected system, and the downhill
direction of a polygon is its ``aspect_degrees``, degrees clockwise from grid
north pointing downslope, the convention of
:func:`landloss.common.utils.terrain.downhill_azimuth_degrees`. "Uphill" is
that azimuth plus 180 degrees throughout.
"""

import itertools
import math
from collections.abc import Iterable

import geopandas as gpd
import numpy as np
import numpy.typing as npt
import pandas as pd
import shapely
from shapely import STRtree
from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import linemerge
from shapely.ops import split as split_geometry

from landloss.domain.constants import (
    MIN_WALL_HEIGHT_M,
    TOPOGRAPHIC_AMPLIFICATION_MAX,
)
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.geometry import landslide_volume_m3, mean_depth_m
from landloss.hazard.landslide.urban.delineation import contour_length_m

# The wall states a polygon can be in, and the three fixed geometries each
# state carries. A state geometry column is named ``<kind>_<state>`` and its
# depth ``depth_<kind>_<state>_m`` (depths for evacuated and inundated only).
WALL_STATES = ("no_wall", "fill_wall", "cut_wall")
GEOMETRY_KINDS = ("evacuated", "inundated", "imminent")
NO_WALL, FILL_WALL, CUT_WALL = WALL_STATES
EVACUATED, INUNDATED, IMMINENT = GEOMETRY_KINDS

# The wall positions a wall line carries, from ``landloss.exposure.rw.lines``.
CUT = "cut"
FILL = "fill"

# The headscarp band above the crest of a failure without a wall: half a metre,
# or a metre on slopes at or over HEADSCARP_STEEP_SLOPE_DEG. Plan section 7
# (T-44) on tension cracks 150 to 200 mm wide behind cut failures
# (sr1995-005-F19, F21), retreat by further small failures over months (F18)
# and crest cracking in the Port Hills (sr2015-016-F19, F20). Both widths are
# placeholders until T-44 is agreed with the project lead.
BETA_HEADSCARP_BAND_M = 0.5
BETA_HEADSCARP_BAND_STEEP_M = 1.0
HEADSCARP_STEEP_SLOPE_DEG = 30.0

# The wedge behind a failed fill wall reaches this many retained heights back
# into the platform. The active wedge of the earth pressure argument is about
# half a height [nzgs_mbie_2017]; loose fill with a sloping backfill reaches
# one or two (plan section 7). One height is the contract's starting point, a
# placeholder until the geometry-rule research (phase 3 of the step 7 plan)
# sets it against the Wellington fill evidence.
BETA_FILL_WEDGE_HEIGHT_MULTIPLE = 1.0

# Reach angle H/L of dry earthquake debris avalanches against volume, from
# [de_vilder_2022]: a median of about 0.9 at 100 m3 and 0.8 at 10,000 m3
# (sr2019-038-F03, F04), log-linear in volume between and held flat outside.
# H and L are measured from the crest to the toe of the deposit.
DRY_REACH_ANGLE_HL = ((100.0, 0.9), (10_000.0, 0.8))

# Reach angle of fill flow slides, the Hong Kong and Wellington median of about
# 0.38 at 1,000 m3 (sr2019-038-F20, F21, F23) [de_vilder_2022]; the primary
# for fill and cut runout is [hunter_fell_2003]. About twice as far as dry.
FILL_REACH_ANGLE_HL = 0.38

# Depth of the ground that leaves a failure without a wall: the thin surface
# layer of colluvium, 1 to 2 m, that Kingsbury puts earthquake-induced
# surficial failures in [kingsbury_1995]. The middle of that range.
COLLUVIUM_DEPTH_M = 1.5

# Above this area the depth falls back on the volume-area relation of
# :mod:`landloss.hazard.landslide.geometry` [massey_2020] where it is deeper
# than the colluvium, because a polygon this size is a slope, not a face.
LARGE_POLYGON_AREA_M2 = 500.0

# A piece of a split candidate under this area is merged into its neighbour
# (contract section 7.6): a sliver a line shaved off a polygon's corner is not
# a failure polygon.
MIN_PIECE_AREA_M2 = 1.0

# The shortest inundated strip. The reach angle rule gives no runout past the
# toe on ground gentler than about 40 degrees, because the face is already
# longer than H/L allows, and a barrier can stand at the toe itself; the
# debris still lies at the toe, so the strip is never shorter than one metre,
# the DEM cell. A placeholder, like the rules it protects, until the
# geometry-rule research (phase 3 of the step 7 plan) sets it.
BETA_MIN_RUNOUT_M = 1.0

# A snap that would lose more than this share of a candidate's area is not
# applied: a patch a few cells wide with a line along one side would otherwise
# collapse onto the line when every vertex is within the tolerance.
MAX_SNAP_AREA_LOSS = 0.5

# A wall line is on a polygon's edge only along the part of it, within the
# tolerance of the boundary, that runs within this angle of the boundary. A line
# crossing the boundary or ending against it meets the buffered boundary over up
# to twice the tolerance, but it runs across the edge, not along it, so it is
# not a wall on that edge (the step 7 plan, phase 3). A numerical rule for
# reading the geometry, not a parameter for the research to set.
EDGE_ALIGNMENT_MAX_DEG = 30.0

# How far either side of a point on the boundary its direction is read over, in
# metres: well under the 1 m cell of the finest candidates, so the direction is
# the one of the boundary segment the point is on.
_TANGENT_STEP_M = 0.1

# Ground map materials on which the evacuated depth reads the fill thickness.
FILL_MATERIALS = ("fill_engineered", "fill_uncontrolled")

# Kingsbury's existing-landslide factor against the ground map's prior failure
# vocabulary (contract section 7.6).
PRIOR_FAILURE_LANDSLIDE_VALUES = {
    "none": susceptibility.LANDSLIDES_NONE,
    "relict": susceptibility.LANDSLIDES_OLD,
    "recent": susceptibility.LANDSLIDES_ACTIVE,
}

# Column names shared with the step and the tests.
CANDIDATE_ID_COLUMN = "candidate_id"
SLOPE_ID_COLUMN = "slope_id"
PIECE_COLUMN = "piece"
WALL_LINE_ID_COLUMN = "wall_line_id"
WALL_LINE_IDS_COLUMN = "wall_line_ids"
WALL_EDGE_LENGTH_COLUMN = "wall_edge_length_m"
WALL_POSITION_COLUMN = "wall_position"
WALL_FACE_HEIGHT_COLUMN = "wall_face_height_m"
PARENT_SLOPE_ID_COLUMN = "parent_slope_id"
REP_POINT_COLUMN = "rep_point"
SCALE_COLUMN = "scale_m"
AREA_COLUMN = "area_m2"
CONTOUR_LENGTH_COLUMN = "contour_length_m"
ASPECT_COLUMN = "aspect_degrees"
SLOPE_COLUMN = "slope_degrees"
RELIEF_COLUMN = "relief_m"
MATERIAL_COLUMN = "material"
FILL_THICKNESS_COLUMN = "fill_thickness_m"

# The wall line column that marks a line on NLM flat land (contract section
# 3.5). A flat-land wall is drawn by vul shaking rw step 9 and has no polygon
# (contract section 5.1), so no polygon records a flat-land line on its edge.
IS_FLATLAND_COLUMN = "is_flatland"

# The line columns the polygon copies, keyed by the polygon's name for them.
LINE_COLUMNS = {
    WALL_POSITION_COLUMN: "wall_position",
    WALL_FACE_HEIGHT_COLUMN: "face_height_m",
}

STATE_GEOMETRY_COLUMNS = tuple(
    f"{kind}_{state}" for state in WALL_STATES for kind in GEOMETRY_KINDS
)
STATE_DEPTH_COLUMNS = tuple(
    f"depth_{kind}_{state}_m"
    for state in WALL_STATES
    for kind in (EVACUATED, INUNDATED)
)


def _geometry_column(kind: str, state: str) -> str:
    return f"{kind}_{state}"


def _depth_column(kind: str, state: str) -> str:
    return f"depth_{kind}_{state}_m"


def _check_frames(polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame) -> None:
    """Refuse frames in different systems, or in a geographic one.

    Args:
        polygons: The failure polygons or candidates.
        lines: The wall lines.

    Raises:
        ValueError: If the two systems differ, or the shared one is geographic.
    """
    if polygons.crs != lines.crs:
        msg = (
            f"the polygons are in {polygons.crs} but the lines are in {lines.crs}; "
            "reproject one onto the other first"
        )
        raise ValueError(msg)
    _check_projected(polygons)


def _check_projected(frame: gpd.GeoDataFrame | gpd.GeoSeries) -> None:
    if frame.crs is not None and frame.crs.is_geographic:
        msg = (
            f"{frame.crs} is a geographic system, so a tolerance in metres would "
            "be degrees. Work in a projected system such as NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def _unit_vector(azimuth_degrees: float) -> npt.NDArray[np.floating]:
    """Return the unit vector of an azimuth, degrees clockwise from grid north."""
    radians = math.radians(azimuth_degrees)
    return np.array([math.sin(radians), math.cos(radians)])


def _polygon_parts(geometry: shapely.Geometry) -> list[Polygon]:
    """Return the polygonal parts of any geometry, empty parts dropped."""
    parts = shapely.get_parts(geometry)
    return [
        part
        for part in parts
        if isinstance(part, Polygon) and not part.is_empty and part.area > 0
    ]


def _largest_polygon(geometry: shapely.Geometry) -> Polygon:
    """Return the largest polygonal part of a geometry, or an empty polygon."""
    parts = _polygon_parts(shapely.make_valid(geometry))
    if not parts:
        return Polygon()
    return max(parts, key=lambda part: part.area)


def _translate(
    geometry: shapely.Geometry, azimuth_degrees: float, distance_m: float
) -> shapely.Geometry:
    """Move a geometry a distance along an azimuth."""
    dx, dy = _unit_vector(azimuth_degrees) * distance_m
    return shapely.transform(geometry, lambda coords: coords + np.array([dx, dy]))


def _extent_along(geometry: shapely.Geometry, azimuth_degrees: float) -> float:
    """Return how far a geometry's vertices spread along an azimuth, in metres."""
    coords = shapely.get_coordinates(geometry)
    if coords.size == 0:
        return 0.0
    projected = coords @ _unit_vector(azimuth_degrees)
    return float(projected.max() - projected.min())


def _project_vertices_onto_lines(
    polygon: Polygon, lines: STRtree, *, tolerance_m: float
) -> Polygon:
    """Move each vertex within the tolerance of a line to the nearest point on it."""

    def moved(coords: npt.NDArray[np.floating]) -> npt.NDArray[np.floating]:
        points = shapely.points(coords)
        pairs = lines.query_nearest(points, max_distance=tolerance_m, all_matches=False)
        if pairs.size == 0:
            return coords
        vertex, line = pairs
        nearest = shapely.shortest_line(points[vertex], lines.geometries[line])
        coords = coords.copy()
        coords[vertex] = shapely.get_coordinates(shapely.get_point(nearest, 1))
        return coords

    return shapely.transform(polygon, moved)


def snap_edges_to_lines(
    polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float
) -> gpd.GeoDataFrame:
    """Move candidate edges within a tolerance of a wall line onto the line.

    Plan section 1.2: an edge within a tolerance of a line is moved onto it,
    so that a wall becomes the polygon's edge rather than running beside it.
    Contract section 7.6: ``shapely.snap`` to the lines then ``make_valid``.
    ``shapely.snap`` moves a vertex only onto a line's *vertices*, so each
    vertex within the tolerance is first projected onto the nearest point of
    the nearest line, and the snap then inserts the line's own vertices into
    the edge. A snap that would lose more than :data:`MAX_SNAP_AREA_LOSS` of
    the candidate's area, or leave no polygon, is not applied.

    Args:
        polygons: The candidates, carrying ``candidate_id``.
        lines: The wall lines.
        tolerance_m: How far an edge may be from a line and still move onto
            it, ``delineation.SNAP_TOLERANCE_M``.

    Returns:
        The candidates with their geometry snapped, every other column kept,
        and ``piece`` set to 0 (nothing is split here).

    Raises:
        ValueError: If the frames are in different systems or a geographic one.
    """
    _check_frames(polygons, lines)
    snapped = polygons.copy()
    snapped[PIECE_COLUMN] = 0
    if lines.empty or polygons.empty:
        return snapped

    tree = STRtree(lines.geometry.to_numpy())
    geometries = []
    for geometry in polygons.geometry:
        near = tree.query(geometry.buffer(tolerance_m), predicate="intersects")
        if near.size == 0:
            geometries.append(geometry)
            continue
        near_lines = shapely.union_all(tree.geometries[near])
        moved = _project_vertices_onto_lines(geometry, tree, tolerance_m=tolerance_m)
        moved = shapely.snap(moved, near_lines, tolerance_m)
        moved = _largest_polygon(moved)
        if moved.area < (1.0 - MAX_SNAP_AREA_LOSS) * geometry.area:
            moved = geometry
        geometries.append(moved)
    snapped.geometry = gpd.GeoSeries(geometries, index=polygons.index, crs=polygons.crs)
    return snapped


def _merge_small_pieces(pieces: list[Polygon], *, min_area_m2: float) -> list[Polygon]:
    """Merge each piece under the minimum into its best-connected neighbour."""
    pieces = list(pieces)
    while len(pieces) > 1:
        small = [i for i, piece in enumerate(pieces) if piece.area < min_area_m2]
        if not small:
            break
        index = small[0]
        piece = pieces.pop(index)
        shared = [
            piece.boundary.intersection(other.boundary).length for other in pieces
        ]
        if max(shared) > 0:
            target = int(np.argmax(shared))
        else:
            target = int(np.argmin([piece.distance(other) for other in pieces]))
        pieces[target] = _largest_polygon(shapely.union(pieces[target], piece))
    return pieces


def _split_one(polygon: Polygon, lines: npt.NDArray[np.object_]) -> list[Polygon]:
    """Split one polygon by every line that crosses it, smallest pieces merged."""
    pieces = [polygon]
    for line in lines:
        cut = []
        for piece in pieces:
            cut.extend(_polygon_parts(split_geometry(piece, line)))
        pieces = cut
    return _merge_small_pieces(pieces, min_area_m2=MIN_PIECE_AREA_M2)


def split_by_lines(
    polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Split every candidate that straddles a wall line along that line.

    Plan section 1.2: a candidate straddling a line is split along it, so that
    the ground on each side of a wall is its own polygon. Contract section 7.6:
    ``shapely.ops.split`` by each intersecting line, pieces under
    :data:`MIN_PIECE_AREA_M2` merged into their neighbour. A line that ends
    inside a candidate does not split it, because ``split`` cuts only where
    the line crosses the polygon from boundary to boundary.

    Args:
        polygons: The (snapped) candidates, carrying ``candidate_id``.
        lines: The wall lines.

    Returns:
        One row per piece, every candidate column repeated onto each of its
        pieces, with ``piece`` 0 where the candidate was not split and 1 to n
        in order of location where it was; fresh index.

    Raises:
        ValueError: If the frames are in different systems or a geographic one.
    """
    _check_frames(polygons, lines)
    if lines.empty or polygons.empty:
        out = polygons.copy()
        out[PIECE_COLUMN] = 0
        return out.reset_index(drop=True)

    tree = STRtree(lines.geometry.to_numpy())
    positions: list[int] = []
    numbers: list[int] = []
    geometries: list[Polygon] = []
    for position, geometry in enumerate(polygons.geometry):
        hits = np.sort(tree.query(geometry, predicate="intersects"))
        pieces = (
            [geometry]
            if hits.size == 0
            else _split_one(geometry, tree.geometries[hits])
        )
        if len(pieces) == 1:
            positions.append(position)
            numbers.append(0)
            geometries.append(pieces[0])
            continue
        points = [piece.representative_point() for piece in pieces]
        order = sorted(range(len(pieces)), key=lambda i: (points[i].x, points[i].y))
        for number, i in enumerate(order, start=1):
            positions.append(position)
            numbers.append(number)
            geometries.append(pieces[i])

    out = polygons.iloc[positions].reset_index(drop=True)
    out[PIECE_COLUMN] = np.asarray(numbers, dtype=np.int64)
    out.geometry = gpd.GeoSeries(geometries, crs=polygons.crs)
    return out


def _line_segments(
    geometry: shapely.Geometry,
) -> tuple[npt.NDArray[np.floating], npt.NDArray[np.floating]]:
    """Return the start and end of every straight segment of a geometry's lines."""
    starts: list[npt.NDArray[np.floating]] = []
    ends: list[npt.NDArray[np.floating]] = []
    for part in shapely.get_parts(geometry):
        if isinstance(part, LineString) and not part.is_empty:
            coords = shapely.get_coordinates(part)
            starts.append(coords[:-1])
            ends.append(coords[1:])
        elif part.geom_type in {"MultiLineString", "GeometryCollection"}:
            more_starts, more_ends = _line_segments(part)
            starts.append(more_starts)
            ends.append(more_ends)
    if not starts:
        return np.empty((0, 2)), np.empty((0, 2))
    return np.vstack(starts), np.vstack(ends)


def _aligned_length(boundary: shapely.Geometry, piece: shapely.Geometry) -> float:
    """Return the length of ``piece`` that runs along ``boundary``.

    A segment of the piece runs along the boundary when its direction is within
    :data:`EDGE_ALIGNMENT_MAX_DEG` of the boundary's direction at the boundary
    point nearest its midpoint.
    """
    starts, ends = _line_segments(piece)
    vectors = ends - starts
    lengths = np.hypot(vectors[:, 0], vectors[:, 1])
    keep = lengths > 0
    if not keep.any():
        return 0.0
    starts, ends = starts[keep], ends[keep]
    vectors, lengths = vectors[keep], lengths[keep]
    along = shapely.line_locate_point(boundary, shapely.points((starts + ends) / 2.0))
    before = shapely.get_coordinates(
        shapely.line_interpolate_point(boundary, along - _TANGENT_STEP_M)
    )
    after = shapely.get_coordinates(
        shapely.line_interpolate_point(boundary, along + _TANGENT_STEP_M)
    )
    tangents = after - before
    tangent_lengths = np.hypot(tangents[:, 0], tangents[:, 1])
    with np.errstate(invalid="ignore", divide="ignore"):
        cosine = np.abs(np.sum(vectors * tangents, axis=1)) / (
            lengths * tangent_lengths
        )
    aligned = np.nan_to_num(cosine, nan=0.0) >= math.cos(
        math.radians(EDGE_ALIGNMENT_MAX_DEG)
    )
    return float(lengths[aligned].sum())


def wall_line_on_edge(
    polygons: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float
) -> pd.DataFrame:
    """Find every wall line on each polygon's edge, and the one sharing the most.

    Contract sections 3.6 and 7.6: a line's shared edge is its intersection
    with the polygon's boundary buffered by the tolerance, and the wall on the
    edge is the line sharing the longest edge. As built, only the part of that
    intersection running within :data:`EDGE_ALIGNMENT_MAX_DEG` of the boundary
    counts, so a line crossing the boundary or ending against it is not on the
    edge; and every line with a shared edge is recorded, longest first, because
    the wall lines are split at property boundaries and the polygons are not,
    so one wall along an edge is often several lines and each must belong to
    the polygon (``wall_line_ids``).

    Args:
        polygons: The failure polygons.
        lines: The wall lines, carrying ``wall_line_id``.
        tolerance_m: How far from the boundary a line still counts as on it.

    Returns:
        A frame on ``polygons.index`` with ``wall_line_id`` (the line sharing
        the longest edge, ``None`` where no line is on the edge),
        ``wall_edge_length_m`` (its shared length, 0 where none) and
        ``wall_line_ids`` (a list of every line on the edge, longest first,
        ties in line order; empty where none).

    Raises:
        ValueError: If the frames are in different systems or a geographic one.
    """
    _check_frames(polygons, lines)
    ids: list[str | None] = [None] * len(polygons)
    lengths = np.zeros(len(polygons))
    on_edge: list[list[str]] = [[] for _ in range(len(polygons))]
    if not lines.empty and not polygons.empty:
        tree = STRtree(lines.geometry.to_numpy())
        line_ids = lines[WALL_LINE_ID_COLUMN].to_numpy()
        for position, geometry in enumerate(polygons.geometry):
            boundary = geometry.boundary
            band = boundary.buffer(tolerance_m)
            hits = np.sort(tree.query(band, predicate="intersects"))
            if hits.size == 0:
                continue
            pieces = shapely.intersection(tree.geometries[hits], band)
            shared = np.array([_aligned_length(boundary, piece) for piece in pieces])
            order = np.argsort(-shared, kind="stable")
            order = order[shared[order] > 0]
            if order.size == 0:
                continue
            on_edge[position] = [str(line_ids[hits[i]]) for i in order]
            ids[position] = on_edge[position][0]
            lengths[position] = shared[order[0]]
    return pd.DataFrame(
        {
            WALL_LINE_ID_COLUMN: pd.Series(ids, index=polygons.index, dtype=object),
            WALL_EDGE_LENGTH_COLUMN: pd.Series(lengths, index=polygons.index),
            WALL_LINE_IDS_COLUMN: pd.Series(
                on_edge, index=polygons.index, dtype=object
            ),
        }
    )


def edge_line_ids(value: Iterable[object] | str | float | None) -> tuple[str, ...]:
    """Read one ``wall_line_ids`` cell as a tuple of ids.

    The cell is a list as :func:`wall_line_on_edge` builds it and a numpy array
    once read back from parquet; a missing cell is no line.

    Args:
        value: The cell.

    Returns:
        The ids in the cell's order, empty where there are none.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def sloping_lines(lines: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep the wall lines a polygon may record on its edge: those on sloping land.

    A flat-land line's wall is drawn by vul shaking rw step 9 and has no
    polygon (contract section 5.1), so a polygon recording it would shadow a
    sloping line on the same edge and then lose it to
    :func:`landloss.hazard.landslide.urban.fragility.sloping_walls`.

    Args:
        lines: The wall lines, carrying ``is_flatland``.

    Returns:
        The rows with ``is_flatland`` false, on their own index.

    Raises:
        ValueError: If the lines carry no ``is_flatland``.
    """
    if IS_FLATLAND_COLUMN not in lines.columns:
        msg = (
            f"The wall lines carry no {IS_FLATLAND_COLUMN!r}, so a flat-land line "
            "cannot be kept off the polygon edges (contract section 3.5)."
        )
        raise ValueError(msg)
    flat = lines[IS_FLATLAND_COLUMN].fillna(value=False).to_numpy(dtype=bool)
    return lines[~flat]


def nest_parents(polygons: gpd.GeoDataFrame, *, min_cover: float = 0.9) -> pd.Series:
    """Find each polygon's parent: the smallest coarser polygon covering it.

    Contract section 10: the nesting parent is the smallest polygon of a
    coarser scale (larger ``scale_m``) covering at least ``min_cover`` of the
    child's area. Nesting across scales is what lets a 1 m face be a row
    inside the 10 m bank that contains it (plan section 1.2).

    Args:
        polygons: The failure polygons, carrying ``slope_id`` and ``scale_m``.
        min_cover: The share of the child's area the parent must cover.

    Returns:
        The parent's ``slope_id`` on ``polygons.index``, ``None`` where no
        coarser polygon covers enough of the child.
    """
    _check_projected(polygons)
    parents = pd.Series([None] * len(polygons), index=polygons.index, dtype=object)
    parents.name = PARENT_SLOPE_ID_COLUMN
    if polygons.empty:
        return parents

    frame = polygons[[SLOPE_ID_COLUMN, SCALE_COLUMN, "geometry"]].reset_index(drop=True)
    tree = STRtree(frame.geometry.to_numpy())
    child, candidate = tree.query(frame.geometry.to_numpy(), predicate="intersects")
    scales = frame[SCALE_COLUMN].to_numpy()
    coarser = scales[candidate] > scales[child]
    child, candidate = child[coarser], candidate[coarser]
    if child.size == 0:
        return parents

    geometries = frame.geometry.to_numpy()
    covered = shapely.area(
        shapely.intersection(geometries[child], geometries[candidate])
    )
    share = covered / shapely.area(geometries[child])
    enough = share >= min_cover
    pairs = pd.DataFrame(
        {
            "child": child[enough],
            "parent": candidate[enough],
            "parent_area": shapely.area(geometries[candidate[enough]]),
            "parent_id": frame[SLOPE_ID_COLUMN].to_numpy()[candidate[enough]],
        }
    )
    pairs = pairs.sort_values(["child", "parent_area", "parent_id"], kind="mergesort")
    best = pairs.drop_duplicates("child", keep="first")
    parents.iloc[best["child"].to_numpy()] = best["parent_id"].to_numpy()
    return parents


def _boundary_facing(
    face: Polygon, azimuth_degrees: float
) -> LineString | MultiLineString:
    """Return the part of a face's outer boundary that faces an azimuth.

    A boundary segment faces the azimuth when its outward normal has a
    positive component along it. On a rectangle aligned with its aspect this
    is the one edge the vertex rule of contract section 7.6 picks; on the
    staircase outline a raster patch has at a diagonal aspect, it is the two
    stepped sides that look that way, where the vertex rule would also take
    the side vertices and sweep wing-shaped strips off them.
    """
    direction = _unit_vector(azimuth_degrees)
    coords = np.asarray(shapely.orient_polygons(face).exterior.coords)
    segments = coords[1:] - coords[:-1]
    lengths = np.hypot(segments[:, 0], segments[:, 1])
    # The outward normal of a counter-clockwise ring is the segment turned right.
    outward = np.stack([segments[:, 1], -segments[:, 0]], axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        cosine = (outward @ direction) / lengths
    facing = np.flatnonzero((lengths > 0) & (cosine > 1e-9))
    if facing.size == 0:
        return LineString()
    lines = [LineString([coords[i], coords[i + 1]]) for i in facing]
    merged = linemerge(lines) if len(lines) > 1 else lines[0]
    return merged


def crest_line(face: Polygon, aspect_degrees: float) -> LineString | MultiLineString:
    """Return the crest of a face: its boundary facing uphill.

    Geometric, not from the DEM (contract section 7.6): the boundary
    segments whose outward normal points uphill (``aspect_degrees`` + 180),
    merged into a line running across the slope. See
    :func:`_boundary_facing` for why segments rather than the vertices
    above the centroid.

    Args:
        face: The failure polygon.
        aspect_degrees: Its downhill azimuth, degrees clockwise from north.

    Returns:
        The crest; a multi-part line where the uphill-facing boundary is not
        contiguous, as on a concave face.
    """
    return _boundary_facing(face, aspect_degrees + 180.0)


def toe_line(face: Polygon, aspect_degrees: float) -> LineString | MultiLineString:
    """Return the toe of a face: its boundary facing downhill.

    The counterpart of :func:`crest_line`: the boundary segments whose
    outward normal points downhill (contract section 7.6).

    Args:
        face: The failure polygon.
        aspect_degrees: Its downhill azimuth, degrees clockwise from north.

    Returns:
        The toe; a multi-part line where the downhill-facing boundary is not
        contiguous.
    """
    return _boundary_facing(face, aspect_degrees)


def offset_strip(line: LineString, azimuth_degrees: float, width_m: float) -> Polygon:
    """Sweep a line a distance along an azimuth and return the ground it covers.

    The strip is the union of the quadrilateral each segment sweeps, so a bent
    line gives one valid polygon rather than a self-intersecting ring. Used
    for the headscarp bands, the fill wedge and the inundated strip.

    Args:
        line: The line to sweep; a multi-part line sweeps each part.
        azimuth_degrees: The direction to sweep in, degrees clockwise from
            grid north.
        width_m: How far to sweep.

    Returns:
        The swept polygon.

    Raises:
        ValueError: If the width is not positive.
    """
    if width_m <= 0:
        msg = f"width_m must be positive, not {width_m}"
        raise ValueError(msg)
    shift = _unit_vector(azimuth_degrees) * width_m
    quads = []
    for part in shapely.get_parts(line):
        coords = shapely.get_coordinates(part)
        for start, end in itertools.pairwise(coords):
            # Absolute, not np.allclose: at NZTM magnitudes a relative
            # tolerance calls two points 10 m apart equal.
            if np.hypot(*(end - start)) < 1e-9:
                continue
            quads.append(Polygon([start, end, end + shift, start + shift]))
    if not quads:
        return Polygon()
    return _largest_polygon(
        shapely.union_all([shapely.make_valid(quad) for quad in quads])
    )


def headscarp_band_m(slope_degrees: float) -> float:
    """Return the width of the headscarp band above a failure's crest.

    Plan section 7 (T-44): half a metre, or a metre on slopes over 30 degrees,
    from tension cracks 150 to 200 mm wide behind cut failures
    (sr1995-005-F19, F21) and crest retreat by further small failures (F18;
    sr2015-016-F19, F20). A slope on the break takes the wider band, as a
    value on a break falls in the class above throughout this study.

    Args:
        slope_degrees: The face's slope.

    Returns:
        :data:`BETA_HEADSCARP_BAND_STEEP_M` at or over
        :data:`HEADSCARP_STEEP_SLOPE_DEG`, else :data:`BETA_HEADSCARP_BAND_M`.
    """
    if slope_degrees >= HEADSCARP_STEEP_SLOPE_DEG:
        return BETA_HEADSCARP_BAND_STEEP_M
    return BETA_HEADSCARP_BAND_M


def evacuated_no_wall(
    face: Polygon, aspect_degrees: float, slope_degrees: float
) -> Polygon:
    """Return the ground that leaves when a face without a wall fails.

    Plan section 7: the face, plus a headscarp band above the crest
    (:func:`headscarp_band_m`). The band is :func:`offset_strip` of the
    :func:`crest_line` uphill.

    Args:
        face: The failure polygon.
        aspect_degrees: Its downhill azimuth.
        slope_degrees: Its slope, which sets the band width.

    Returns:
        The evacuated polygon.
    """
    band = offset_strip(
        crest_line(face, aspect_degrees),
        aspect_degrees + 180.0,
        headscarp_band_m(slope_degrees),
    )
    return _largest_polygon(shapely.union(face, band))


def imminent_no_wall(
    face: Polygon, aspect_degrees: float, slope_degrees: float
) -> Polygon:
    """Return the ground at imminent risk behind a failed face without a wall.

    Plan section 7 (T-45): a second band of the same width behind the
    headscarp band, cracked but standing.

    Args:
        face: The failure polygon.
        aspect_degrees: Its downhill azimuth.
        slope_degrees: Its slope, which sets the band width.

    Returns:
        The imminent polygon.
    """
    band = headscarp_band_m(slope_degrees)
    uphill = aspect_degrees + 180.0
    crest = _translate(crest_line(face, aspect_degrees), uphill, band)
    return offset_strip(crest, uphill, band)


def fill_wedge(
    wall_line: LineString,
    aspect_degrees: float,
    height_m: float,
    *,
    multiple: float = BETA_FILL_WEDGE_HEIGHT_MULTIPLE,
) -> Polygon:
    """Return the wedge of fill that leaves when a fill wall fails.

    Plan section 7: the wedge behind the wall, a multiple of the retained
    height back into the platform; at least the active wedge of about half the
    height [nzgs_mbie_2017], up to one or two heights for loose fill with a
    sloping backfill. The Wellington fill evidence is Priscilla Crescent, a
    scarp up to 15 m high with the moving layer 5 to 8 m thick (sr2019-051-F08,
    F22, F25), and Orchy Crescent's surface running through the weak colluvium
    at the fill base and behind the break in slope at the top (F23).

    Args:
        wall_line: The wall on the polygon's edge.
        aspect_degrees: The polygon's downhill azimuth; the wedge lies uphill.
        height_m: The retained height.
        multiple: How many heights back the wedge reaches.

    Returns:
        The wedge as a polygon, ``multiple * height_m`` wide behind the wall.
    """
    return offset_strip(wall_line, aspect_degrees + 180.0, multiple * height_m)


def imminent_fill_wall(
    wall_line: LineString, aspect_degrees: float, height_m: float
) -> Polygon:
    """Return the platform at imminent risk behind a failed fill wall's wedge.

    Plan section 7: the platform behind the wedge, cracked but standing, taken
    as one further retained height behind the :func:`fill_wedge`.

    Args:
        wall_line: The wall on the polygon's edge.
        aspect_degrees: The polygon's downhill azimuth.
        height_m: The retained height.

    Returns:
        The imminent polygon, ``height_m`` wide behind the wedge.
    """
    uphill = aspect_degrees + 180.0
    back = _translate(wall_line, uphill, BETA_FILL_WEDGE_HEIGHT_MULTIPLE * height_m)
    return offset_strip(back, uphill, height_m)


def dry_reach_angle(volume_m3: float) -> float:
    """Return the reach angle H/L of a dry debris avalanche of a volume.

    [de_vilder_2022] fits H/L against volume by failure style: dry earthquake
    debris avalanches below 100,000 m3 have a median of about 0.9 at 100 m3
    and 0.8 at 10,000 m3 (sr2019-038-F03, F04), with scatter of 0.08 to 0.1
    in log10 (F05) fixed at the median here. Log-linear in volume between
    the two points of :data:`DRY_REACH_ANGLE_HL`, held flat outside them.

    Args:
        volume_m3: The volume that leaves the source.

    Returns:
        H/L, the drop over the horizontal reach from the crest.
    """
    (low_volume, low_hl), (high_volume, high_hl) = DRY_REACH_ANGLE_HL
    volume = float(volume_m3)
    if not np.isfinite(volume) or volume < low_volume:
        volume = low_volume
    return float(
        np.interp(
            math.log10(volume),
            [math.log10(low_volume), math.log10(high_volume)],
            [low_hl, high_hl],
        )
    )


def runout_length_m(
    relief_m: float, reach_angle_hl: float, face_length_m: float
) -> float:
    """Return how far past the toe the debris runs.

    H/L in [de_vilder_2022] is measured from the crest to the toe of the
    deposit, so the horizontal reach from the crest is ``relief_m /
    reach_angle_hl`` and the run past the toe is that less the face's own
    horizontal length, floored at zero (contract section 7.6).

    Args:
        relief_m: The drop from the crest to the toe.
        reach_angle_hl: H/L, from :func:`dry_reach_angle` or
            :data:`FILL_REACH_ANGLE_HL`.
        face_length_m: The face's extent along the aspect.

    Returns:
        The runout past the toe, in metres, never negative.

    Raises:
        ValueError: If the reach angle is not positive.
    """
    if reach_angle_hl <= 0:
        msg = f"reach_angle_hl must be positive, not {reach_angle_hl}"
        raise ValueError(msg)
    if not np.isfinite(relief_m) or not np.isfinite(face_length_m):
        msg = f"relief_m {relief_m} and face_length_m {face_length_m} must be finite"
        raise ValueError(msg)
    return max(float(relief_m) / reach_angle_hl - float(face_length_m), 0.0)


def spread_runout_m(evacuated_area_m2: float, toe_length_m: float) -> float:
    """Return the runout that spreads the evacuated ground at its own depth.

    The reach angle rule measures L from the crest, so on a face gentler than
    about 40 degrees it leaves no run past the toe at all, and a strip of
    :data:`BETA_MIN_RUNOUT_M` would then carry the whole volume at an implausible
    depth. The debris still has to lie somewhere: the inundated strip is at
    least long enough for a footprint equal to the source, the rule step 1's
    runout already uses (:mod:`landloss.hazard.landslide.geometry`), so the
    inundated depth never exceeds the evacuated depth where nothing stops the
    debris. A starting point, decided by this build, not a sourced rule.

    Args:
        evacuated_area_m2: The area of the evacuated polygon.
        toe_length_m: The length of the toe the debris leaves over.

    Returns:
        The runout, in metres, that gives the strip the evacuated area; 0
        where the toe has no length.
    """
    if toe_length_m <= 0:
        return 0.0
    return float(evacuated_area_m2) / float(toe_length_m)


def inundated_polygon(
    toe: LineString,
    aspect_degrees: float,
    runout_m: float,
    *,
    barriers: gpd.GeoSeries,
) -> Polygon:
    """Return the ground the debris lands on: a strip downhill from the toe.

    Plan section 7: runout from the toe, clipped at the next building outline
    or road, because debris from a cut behind a house stops at the house. The
    strip is :func:`offset_strip` of the toe downhill by the runout, cut at
    the first barrier it meets (the nearest barrier point to the toe inside
    the strip). It is never shorter than :data:`BETA_MIN_RUNOUT_M`.

    Args:
        toe: The face's :func:`toe_line`.
        aspect_degrees: The downhill azimuth.
        runout_m: The run past the toe, from :func:`runout_length_m`.
        barriers: Building outlines and buffered road centrelines.

    Returns:
        The inundated polygon.
    """
    length = max(float(runout_m), BETA_MIN_RUNOUT_M)
    strip = offset_strip(toe, aspect_degrees, length)
    if strip.is_empty or barriers.empty:
        return strip
    hits = barriers.sindex.query(strip, predicate="intersects")
    if hits.size == 0:
        return strip
    inside = shapely.intersection(barriers.to_numpy()[hits], strip)
    first = float(np.min(shapely.distance(inside, toe)))
    cut = max(first, BETA_MIN_RUNOUT_M)
    if cut < length:
        strip = offset_strip(toe, aspect_degrees, cut)
    return strip


def evacuated_depth_m(area_m2: float, material: str, fill_thickness_m: float) -> float:
    """Return the depth of ground that leaves a failure without a wall.

    Plan section 7: 1 to 2 m, the colluvium thickness Kingsbury gives
    [kingsbury_1995] (:data:`COLLUVIUM_DEPTH_M`); deeper on fill bodies, from
    the fill thickness in the ground map where known; and for a polygon over
    :data:`LARGE_POLYGON_AREA_M2` the larger of that and the volume-area
    relation of :mod:`landloss.hazard.landslide.geometry` [massey_2020], from
    outside Wellington (A-06).

    Args:
        area_m2: The evacuated area.
        material: The ground map material under the polygon.
        fill_thickness_m: The ground map fill thickness, NaN where unknown.

    Returns:
        The evacuated depth in metres.
    """
    depth = COLLUVIUM_DEPTH_M
    if (
        material in FILL_MATERIALS
        and fill_thickness_m is not None
        and np.isfinite(fill_thickness_m)
    ):
        depth = max(depth, float(fill_thickness_m))
    if area_m2 > LARGE_POLYGON_AREA_M2:
        depth = max(depth, float(mean_depth_m(landslide_volume_m3(area_m2), area_m2)))
    return depth


def fill_wall_depth_m(height_m: float) -> float:
    """Return the mean depth of the wedge that leaves when a fill wall fails.

    Plan section 7: the retained height at the wall, tapering to zero at the
    back of the wedge, so the mean over the wedge is half the height.

    Args:
        height_m: The retained height.

    Returns:
        ``height_m / 2``.
    """
    return float(height_m) / 2.0


def _inundated_depth(volume_m3: float, inundated: Polygon) -> float:
    """Spread a volume over the inundated polygon: volume conserved."""
    return float(mean_depth_m(volume_m3, inundated.area))


def _ring(face: Polygon, width_m: float) -> Polygon:
    """Return the band of ground a width out from a face's edge all round."""
    return _largest_polygon(face.buffer(width_m).difference(face))


def no_direction_states(
    face: Polygon,
    *,
    slope_degrees: float,
    material: str,
    fill_thickness_m: float,
) -> dict[str, Polygon | float]:
    """Compute the no-wall state of a polygon that has no downhill direction.

    Step 6 keeps a level run with no gentle neighbour as a candidate of its
    own (contract sections 7.5 and 10: a hydro-flattened pond, or a platform
    whose rim lies outside the domain), and such a patch carries a NaN
    ``aspect_degrees``. With no direction there is no crest, no toe and no
    run: the ground that leaves is the face itself, the ground at imminent
    risk is the band of :func:`headscarp_band_m` around its whole edge, and
    the debris lies in a band around the edge wide enough to hold the
    evacuated ground at its own depth (the rule of :func:`spread_runout_m`
    with the whole perimeter as the toe), never narrower than
    :data:`BETA_MIN_RUNOUT_M`. The band is not cut at barriers, because there is
    no run direction to cut it along. A rule of this build, not a sourced
    one; the step's plan lists it for the lead.

    Args:
        face: The failure polygon.
        slope_degrees: Its slope, which sets the imminent band width.
        material: The ground map material under it.
        fill_thickness_m: The ground map fill thickness, NaN where unknown.

    Returns:
        The three ``<kind>_no_wall`` geometries and the two
        ``depth_<kind>_no_wall_m`` depths, keyed by column name.
    """
    depth = evacuated_depth_m(face.area, material, fill_thickness_m)
    volume = face.area * depth
    width = max(spread_runout_m(face.area, face.exterior.length), BETA_MIN_RUNOUT_M)
    inundated = _ring(face, width)
    return {
        _geometry_column(EVACUATED, NO_WALL): face,
        _geometry_column(INUNDATED, NO_WALL): inundated,
        _geometry_column(IMMINENT, NO_WALL): _ring(
            face, headscarp_band_m(slope_degrees)
        ),
        _depth_column(EVACUATED, NO_WALL): depth,
        _depth_column(INUNDATED, NO_WALL): _inundated_depth(volume, inundated),
    }


def _copy_state(
    out: dict[str, Polygon | float | None],
    no_wall: dict[str, Polygon | float],
    state: str,
) -> None:
    """Fill a wall state with the no-wall geometries and depths."""
    for kind in GEOMETRY_KINDS:
        out[_geometry_column(kind, state)] = no_wall[_geometry_column(kind, NO_WALL)]
    for kind in (EVACUATED, INUNDATED):
        out[_depth_column(kind, state)] = no_wall[_depth_column(kind, NO_WALL)]


def state_geometries(
    face: Polygon,
    *,
    aspect_degrees: float,
    slope_degrees: float,
    relief_m: float,
    material: str,
    fill_thickness_m: float,
    wall_line: LineString | None,
    wall_position: str | None,
    wall_height_m: float | None,
    barriers: gpd.GeoSeries,
) -> dict[str, Polygon | float | None]:
    """Compute the fixed geometry and depth of every state a polygon can be in.

    Plan section 7 and contract section 7.6. The no-wall state is always
    filled. With a wall line on the edge, the state matching its position is
    filled too: the cut-wall state equals the no-wall state (the face above
    the wall plus the headscarp band), and the fill-wall state is the
    :func:`fill_wedge` behind the wall with the fill flow slide reach angle
    :data:`FILL_REACH_ANGLE_HL`. The other state's geometries are ``None``
    and its depths NaN. Inundated depth is the evacuated volume over the
    inundated area, so volume is conserved through the runout.

    A polygon with a NaN ``aspect_degrees`` (a level patch step 6 kept, with
    no downhill direction) takes the no-wall state of
    :func:`no_direction_states`, and a wall on its edge, fill or cut, copies
    that state, because neither a wedge nor a run can be placed without a
    direction.

    A fill wall's wedge height is floored at ``MIN_WALL_HEIGHT_M`` (contract
    section 3.5 keeps a GNS mapped wall whatever its face reads), and a NaN
    height, from a line whose every face-height sample fell off the raster,
    takes the floor outright.

    Args:
        face: The failure polygon.
        aspect_degrees: Its downhill azimuth, NaN where it has none.
        slope_degrees: Its slope.
        relief_m: Its drop from crest to toe.
        material: The ground map material under it.
        fill_thickness_m: The ground map fill thickness, NaN where unknown.
        wall_line: The wall on its edge, or ``None``.
        wall_position: That wall's ``fill`` or ``cut``, or ``None``.
        wall_height_m: That wall's face height, NaN where it read none, or
            ``None`` where no wall is on the edge.
        barriers: Building outlines and buffered road centrelines.

    Returns:
        The nine ``<kind>_<state>`` geometries and six ``depth_<kind>_<state>_m``
        depths, keyed by column name.

    Raises:
        ValueError: If a wall line comes with a position that is not ``fill``
            or ``cut``, or a fill wall with a height of ``None``.
    """
    out: dict[str, Polygon | float | None] = dict.fromkeys(STATE_GEOMETRY_COLUMNS)
    out.update({column: float("nan") for column in STATE_DEPTH_COLUMNS})
    has_direction = bool(np.isfinite(aspect_degrees))

    if has_direction:
        face_length = _extent_along(face, aspect_degrees)
        toe = toe_line(face, aspect_degrees)
        evacuated = evacuated_no_wall(face, aspect_degrees, slope_degrees)
        depth = evacuated_depth_m(evacuated.area, material, fill_thickness_m)
        volume = evacuated.area * depth
        runout = max(
            runout_length_m(relief_m, dry_reach_angle(volume), face_length),
            spread_runout_m(evacuated.area, toe.length),
        )
        inundated = inundated_polygon(toe, aspect_degrees, runout, barriers=barriers)
        no_wall: dict[str, Polygon | float] = {
            _geometry_column(EVACUATED, NO_WALL): evacuated,
            _geometry_column(INUNDATED, NO_WALL): inundated,
            _geometry_column(IMMINENT, NO_WALL): imminent_no_wall(
                face, aspect_degrees, slope_degrees
            ),
            _depth_column(EVACUATED, NO_WALL): depth,
            _depth_column(INUNDATED, NO_WALL): _inundated_depth(volume, inundated),
        }
    else:
        no_wall = no_direction_states(
            face,
            slope_degrees=slope_degrees,
            material=material,
            fill_thickness_m=fill_thickness_m,
        )
    out.update(no_wall)

    if wall_line is None:
        return out
    if wall_position not in (FILL, CUT):
        msg = (
            f"wall_position must be {FILL!r} or {CUT!r} with a wall line, "
            f"not {wall_position!r}"
        )
        raise ValueError(msg)
    if wall_position == CUT:
        _copy_state(out, no_wall, CUT_WALL)
        return out
    if not has_direction:
        _copy_state(out, no_wall, FILL_WALL)
        return out
    if wall_height_m is None:
        msg = "a fill wall needs a height to build its wedge"
        raise ValueError(msg)

    height = (
        MIN_WALL_HEIGHT_M
        if not np.isfinite(wall_height_m)
        else max(float(wall_height_m), MIN_WALL_HEIGHT_M)
    )
    wedge = fill_wedge(wall_line, aspect_degrees, height)
    depth = fill_wall_depth_m(height)
    volume = wedge.area * depth
    runout = max(
        runout_length_m(relief_m, FILL_REACH_ANGLE_HL, face_length),
        spread_runout_m(wedge.area, toe.length),
    )
    inundated = inundated_polygon(toe, aspect_degrees, runout, barriers=barriers)
    out[_geometry_column(EVACUATED, FILL_WALL)] = wedge
    out[_geometry_column(INUNDATED, FILL_WALL)] = inundated
    out[_geometry_column(IMMINENT, FILL_WALL)] = imminent_fill_wall(
        wall_line, aspect_degrees, height
    )
    out[_depth_column(EVACUATED, FILL_WALL)] = depth
    out[_depth_column(INUNDATED, FILL_WALL)] = _inundated_depth(volume, inundated)
    return out


def amplification_factor(
    topographic_position_m: npt.NDArray[np.floating],
    slope_degrees: npt.NDArray[np.floating],
    *,
    max_factor: float = TOPOGRAPHIC_AMPLIFICATION_MAX,
) -> npt.NDArray[np.floating]:
    """Return the topographic amplification factor a fragility median is divided by.

    Contract section 7.6, a placeholder: phase 3 of the step 7 plan
    (``s7_urban_slope_polygons_implementation_plan.md``, "The researched
    rules") replaces it with a factor bracketed against sr2019-051-F35.
    Until then it is ``1 + (max_factor - 1) * max(clip(tpi / 10, 0, 1),
    clip((slope - 30) / 30, 0, 1))``, so a crest 10 m or more above its 100 m
    neighbourhood, or a face at 60 degrees, reaches the maximum. A NaN input
    contributes nothing, so a polygon with no position reads no
    amplification from it.

    Args:
        topographic_position_m: The 100 m topographic position, metres above
            the neighbourhood mean.
        slope_degrees: The polygon's slope.
        max_factor: The factor at a crest or a face over 60 degrees.

    Returns:
        The factor, 1.0 to ``max_factor``, the shape of the inputs.
    """
    tpi = np.nan_to_num(np.asarray(topographic_position_m, dtype=float), nan=0.0)
    slope = np.nan_to_num(np.asarray(slope_degrees, dtype=float), nan=0.0)
    crest = np.clip(tpi / 10.0, 0.0, 1.0)
    steep = np.clip((slope - 30.0) / 30.0, 0.0, 1.0)
    return 1.0 + (max_factor - 1.0) * np.maximum(crest, steep)


def kingsbury_factors(polygons: pd.DataFrame) -> dict[str, npt.NDArray[np.floating]]:
    """Score the six Kingsbury factors from a polygon's own attributes.

    Contract section 7.6, for :func:`susceptibility.susceptibility_rating`
    [kingsbury_1995]: slope from ``slope_angle_value(slope_degrees)``;
    modification ``cut_angle_value(slope_degrees)`` where ``modification`` is
    ``cut``, ``SIDLING_FILL_VALUE`` where ``fill``, else 0; height
    ``slope_height_value(face_height_10m, slope_degrees)``; geology the
    ground map's ``geology_value``; landslides from ``prior_failure``;
    groundwater ``groundwater_value(gw_depth_m)``.

    Args:
        polygons: Rows carrying ``slope_degrees``, ``modification``,
            ``face_height_10m``, ``geology_value``, ``prior_failure`` and
            ``gw_depth_m``.

    Returns:
        The six factor arrays, keyed by the rating function's argument names.

    Raises:
        ValueError: If a ``prior_failure`` value is not in the vocabulary.
    """
    slope = polygons[SLOPE_COLUMN].to_numpy(dtype=float)
    modification = polygons["modification"].to_numpy()
    modification_value = np.where(
        modification == CUT,
        susceptibility.cut_angle_value(slope),
        np.where(modification == FILL, susceptibility.SIDLING_FILL_VALUE, 0.0),
    )
    prior = polygons["prior_failure"]
    unknown = set(prior.dropna().unique()) - set(PRIOR_FAILURE_LANDSLIDE_VALUES)
    if unknown:
        msg = (
            f"No landslide class is assigned for prior_failure "
            f"{', '.join(repr(value) for value in sorted(unknown))}. Known: "
            f"{', '.join(repr(value) for value in PRIOR_FAILURE_LANDSLIDE_VALUES)}"
        )
        raise ValueError(msg)
    return {
        "slope": susceptibility.slope_angle_value(slope),
        "modification": modification_value,
        "height": susceptibility.slope_height_value(
            polygons["face_height_10m"].to_numpy(dtype=float), slope
        ),
        "geology": polygons["geology_value"].to_numpy(dtype=float),
        "landslides": prior.map(PRIOR_FAILURE_LANDSLIDE_VALUES).to_numpy(dtype=float),
        "groundwater": susceptibility.groundwater_value(
            polygons["gw_depth_m"].to_numpy(dtype=float)
        ),
    }


def reconcile_candidates(
    candidates: gpd.GeoDataFrame, lines: gpd.GeoDataFrame, *, tolerance_m: float
) -> gpd.GeoDataFrame:
    """Reconcile the candidates to the wall lines and record the wall on each edge.

    The chain of :func:`snap_edges_to_lines`, :func:`split_by_lines` and
    :func:`wall_line_on_edge`, then the line's ``wall_position`` and
    ``face_height_m`` copied onto the polygon and ``area_m2`` and
    ``contour_length_m`` (by step 6's own
    :func:`landloss.hazard.landslide.urban.delineation.contour_length_m`)
    recomputed on the reconciled geometry (contract section 3.6). Ids are not
    minted here: the step sorts and mints.

    The snap and the split read every line, because the ground on either side
    of any wall is its own polygon; only the lines on sloping land
    (:func:`sloping_lines`) are recorded on an edge, so a flat-land line never
    shadows a sloping one.

    Args:
        candidates: The step 6 candidates.
        lines: The wall lines, carrying ``wall_line_id``, ``wall_position``,
            ``face_height_m`` and ``is_flatland``.
        tolerance_m: The snap tolerance, ``delineation.SNAP_TOLERANCE_M``.

    Returns:
        One row per piece with every candidate column, ``piece``,
        ``wall_line_id``, ``wall_edge_length_m``, ``wall_line_ids``,
        ``wall_position`` and ``wall_face_height_m``; fresh index.

    Raises:
        ValueError: If the lines carry no ``is_flatland``.
    """
    on_sloping_land = sloping_lines(lines)
    snapped = snap_edges_to_lines(candidates, lines, tolerance_m=tolerance_m)
    pieces = split_by_lines(snapped, lines)
    on_edge = wall_line_on_edge(pieces, on_sloping_land, tolerance_m=tolerance_m)
    pieces[WALL_LINE_ID_COLUMN] = on_edge[WALL_LINE_ID_COLUMN]
    pieces[WALL_EDGE_LENGTH_COLUMN] = on_edge[WALL_EDGE_LENGTH_COLUMN]
    pieces[WALL_LINE_IDS_COLUMN] = on_edge[WALL_LINE_IDS_COLUMN]

    by_line = lines.set_index(WALL_LINE_ID_COLUMN) if not lines.empty else None
    for column, line_column in LINE_COLUMNS.items():
        if by_line is None:
            values = pd.Series([None] * len(pieces), index=pieces.index, dtype=object)
        else:
            values = pieces[WALL_LINE_ID_COLUMN].map(by_line[line_column])
        if column == WALL_FACE_HEIGHT_COLUMN:
            pieces[column] = values.astype(float)
        else:
            pieces[column] = pd.Series(
                [value if pd.notna(value) else None for value in values],
                index=pieces.index,
                dtype=object,
            )

    pieces[AREA_COLUMN] = pieces.geometry.area
    pieces[CONTOUR_LENGTH_COLUMN] = contour_length_m(
        pieces.geometry, pieces[ASPECT_COLUMN].to_numpy(dtype=float)
    )
    return pieces


def attach_state_geometries(
    polygons: gpd.GeoDataFrame,
    lines: gpd.GeoDataFrame,
    *,
    barriers: gpd.GeoSeries,
    tolerance_m: float,
) -> gpd.GeoDataFrame:
    """Add the representative point and every state's geometry and depth.

    Runs :func:`state_geometries` per polygon. The wall line handed to it is
    the part of the polygon's ``wall_line_id`` line within the tolerance of
    the polygon's boundary, so a long line's wedge is built along the shared
    edge only.

    Args:
        polygons: The reconciled polygons, carrying the columns
            :func:`state_geometries` reads and ``wall_line_id``.
        lines: The wall lines, carrying ``wall_line_id``.
        barriers: Building outlines and buffered road centrelines, in the
            polygons' system.
        tolerance_m: The snap tolerance.

    Returns:
        The polygons with ``rep_point``, the nine state geometry columns and
        the six depth columns appended.
    """
    _check_frames(polygons, lines)
    by_line = lines.set_index(WALL_LINE_ID_COLUMN).geometry if not lines.empty else None
    records = []
    for row in polygons.itertuples(index=False):
        wall_line = None
        line_id = getattr(row, WALL_LINE_ID_COLUMN)
        if line_id is not None and by_line is not None:
            band = row.geometry.boundary.buffer(tolerance_m)
            shared = by_line[line_id].intersection(band)
            wall_line = shared if not shared.is_empty else by_line[line_id]
        records.append(
            state_geometries(
                row.geometry,
                aspect_degrees=float(getattr(row, ASPECT_COLUMN)),
                slope_degrees=float(getattr(row, SLOPE_COLUMN)),
                relief_m=float(getattr(row, RELIEF_COLUMN)),
                material=getattr(row, MATERIAL_COLUMN),
                fill_thickness_m=float(getattr(row, FILL_THICKNESS_COLUMN)),
                wall_line=wall_line,
                wall_position=getattr(row, WALL_POSITION_COLUMN),
                wall_height_m=getattr(row, WALL_FACE_HEIGHT_COLUMN),
                barriers=barriers,
            )
        )
    states = pd.DataFrame(records, index=polygons.index)
    out = polygons.copy()
    out[REP_POINT_COLUMN] = polygons.geometry.representative_point()
    for column in STATE_DEPTH_COLUMNS:
        out[column] = states[column].astype(float) if len(states) else np.nan
    for column in STATE_GEOMETRY_COLUMNS:
        values = states[column].tolist() if len(states) else []
        out[column] = gpd.GeoSeries(values, index=polygons.index, crs=polygons.crs)
    return out
