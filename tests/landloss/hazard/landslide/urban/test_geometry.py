"""Tests for the urban failure polygon geometry.

Every case is a planar slope built by hand: square faces in NZTM with a known
downhill direction, wall lines drawn beside or across them, and a barrier box
placed where the runout has to stop. Nothing is read off a DEM, so each
expected extent can be worked out on paper.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import geometry

# An arbitrary but realistic corner in NZTM.
X0 = 1_748_000.0
Y0 = 5_425_000.0

# Every face slopes down to the south, so uphill is north (+y) and the toe is
# the southern edge.
SOUTH = 180.0

# The candidate columns of contract section 3.4 that the chain reads, with one
# value per candidate; the rest are carried through untouched.
CANDIDATE_COLUMNS = {
    "scale_m": 1,
    "slope_band": "30-45",
    "aspect_octant": 4,
    "slope_degrees": 35.0,
    "aspect_degrees": SOUTH,
    "slope_1m": 35.0,
    "slope_3m": 33.0,
    "slope_10m": 30.0,
    "slope_30m": 25.0,
    "face_height_5m": 3.0,
    "face_height_10m": 6.0,
    "cut_fill_residual_30m": 0.2,
    "cut_fill_residual_100m": 0.5,
    "profile_curvature": -0.01,
    "topographic_position_20m": 1.0,
    "topographic_position_100m": 4.0,
    "vegetation_height_m": 2.0,
    "building_distance_m": 12.0,
    "building_position": "below",
    "road_distance_m": 30.0,
    "boundary_distance_m": 4.0,
    "ground_id": "GM0000001",
    "material": "colluvium",
    "modification": "natural",
    "prior_failure": "none",
    "gw_depth_class": "well_drained",
    "gw_depth_m": 4.0,
    "fill_thickness_m": np.nan,
    "geology_value": susceptibility.GEOLOGY_COLLUVIUM_OR_ALLUVIUM,
    "relief_m": 5.0,
}

CONTRACT_COLUMNS = (
    "slope_id",
    "candidate_id",
    "piece",
    *(column for column in CANDIDATE_COLUMNS if column != "relief_m"),
    "relief_m",
    "area_m2",
    "contour_length_m",
    "wall_line_id",
    "wall_edge_length_m",
    "wall_line_ids",
    "wall_position",
    "wall_face_height_m",
    "parent_slope_id",
    "kingsbury_rating",
    "kingsbury_zone",
    "amp_factor",
    "rep_point",
    *geometry.STATE_DEPTH_COLUMNS,
    *geometry.STATE_GEOMETRY_COLUMNS,
    "geometry",
)


def square(x, y, width, height=None):
    """A box with its lower-left corner at (x, y) metres from the origin."""
    height = width if height is None else height
    return box(X0 + x, Y0 + y, X0 + x + width, Y0 + y + height)


def line(x_from, y_from, x_to, y_to):
    return LineString([(X0 + x_from, Y0 + y_from), (X0 + x_to, Y0 + y_to)])


def candidates(geometries, **overrides):
    """Synthetic step 6 candidates, one per geometry, the contract's columns."""
    rows = {
        column: [value] * len(geometries) for column, value in CANDIDATE_COLUMNS.items()
    }
    for column, values in overrides.items():
        rows[column] = list(values)
    frame = gpd.GeoDataFrame(rows, geometry=list(geometries), crs=constants.DEFAULT_CRS)
    frame.insert(0, "candidate_id", mint_ids(constants.CANDIDATE_ID_PREFIX, len(frame)))
    frame["area_m2"] = frame.geometry.area
    frame["contour_length_m"] = 0.0
    return frame


def wall_lines(geometries, positions, heights, flat=None):
    """Synthetic wall lines on sloping land, flat where ``flat`` says so."""
    flat = [False] * len(geometries) if flat is None else list(flat)
    frame = gpd.GeoDataFrame(
        {
            "wall_line_id": mint_ids(constants.WALL_LINE_ID_PREFIX, len(geometries)),
            "wall_position": list(positions),
            "face_height_m": list(heights),
            "is_flatland": np.asarray(flat, dtype=bool),
        },
        geometry=list(geometries),
        crs=constants.DEFAULT_CRS,
    )
    return frame


def no_lines():
    return wall_lines([], [], [])


def no_barriers():
    return gpd.GeoSeries([], crs=constants.DEFAULT_CRS)


# --- Reconciling the edges -------------------------------------------------


def test_a_candidate_straddling_a_line_is_split_into_two_pieces_sharing_the_line():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 6, 15, 6)], ["cut"], [1.0])

    pieces = geometry.split_by_lines(face, lines)

    assert len(pieces) == 2
    assert sorted(pieces["piece"]) == [1, 2]
    assert set(pieces["candidate_id"]) == {"UC0000001"}
    assert pieces.geometry.area.sum() == pytest.approx(100.0)
    shared = pieces.geometry.iloc[0].intersection(pieces.geometry.iloc[1])
    assert shared.length == pytest.approx(10.0)
    assert shared.distance(lines.geometry.iloc[0]) == pytest.approx(0.0)


def test_a_line_ending_inside_a_candidate_does_not_split_it():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 6, 4, 6)], ["cut"], [1.0])

    pieces = geometry.split_by_lines(face, lines)

    assert len(pieces) == 1
    assert pieces["piece"].iloc[0] == 0


def test_a_sliver_a_line_shaves_off_is_merged_back():
    face = candidates([square(0, 0, 10)])
    # Across the corner, cutting off a triangle of 0.125 m2.
    lines = wall_lines([line(-1, 0.5, 0.5, -1)], ["cut"], [1.0])

    pieces = geometry.split_by_lines(face, lines)

    assert len(pieces) == 1
    assert pieces.geometry.iloc[0].area == pytest.approx(100.0)


def test_an_edge_within_the_tolerance_moves_onto_the_line():
    face = candidates([square(0, 0, 10)])
    # One metre north of the top edge, which is within the 3 m tolerance.
    lines = wall_lines([line(-5, 11, 15, 11)], ["fill"], [2.0])

    snapped = geometry.snap_edges_to_lines(face, lines, tolerance_m=3.0)

    minx, miny, maxx, maxy = snapped.geometry.iloc[0].bounds
    assert maxy == pytest.approx(Y0 + 11)
    assert miny == pytest.approx(Y0)
    assert (minx, maxx) == pytest.approx((X0, X0 + 10))
    assert (snapped["piece"] == 0).all()


def test_an_edge_beyond_the_tolerance_stays_where_it_was():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 15, 15, 15)], ["fill"], [2.0])

    snapped = geometry.snap_edges_to_lines(face, lines, tolerance_m=3.0)

    assert snapped.geometry.iloc[0].equals(face.geometry.iloc[0])


def test_a_small_patch_does_not_collapse_onto_a_line_beside_it():
    face = candidates([square(0, 0, 3)])
    lines = wall_lines([line(-5, 4, 15, 4)], ["fill"], [2.0])

    snapped = geometry.snap_edges_to_lines(face, lines, tolerance_m=3.0)

    assert snapped.geometry.iloc[0].area >= 0.5 * 9.0


def test_the_wall_sharing_the_longest_edge_becomes_the_wall_on_the_edge():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines(
        [line(-5, 10, 15, 10), line(10, 2, 10, 6)], ["fill", "cut"], [2.0, 1.0]
    )

    on_edge = geometry.wall_line_on_edge(face, lines, tolerance_m=3.0)

    assert on_edge["wall_line_id"].iloc[0] == "WL0000001"
    assert on_edge["wall_edge_length_m"].iloc[0] == pytest.approx(16.0)
    # The short line lies along the east edge, so it is on the edge too.
    assert on_edge["wall_line_ids"].iloc[0] == ["WL0000001", "WL0000002"]


def test_every_line_of_a_wall_split_at_a_property_boundary_is_on_the_edge():
    # A 20 m square whose crest wall is split at x = 12 into WL0000001 (12 m)
    # and WL0000002 (8 m): the polygon records both, longest first.
    face = candidates([square(0, 0, 20)])
    lines = wall_lines(
        [line(0, 20, 12, 20), line(12, 20, 20, 20)], ["fill", "fill"], [2.0, 2.0]
    )

    on_edge = geometry.wall_line_on_edge(face, lines, tolerance_m=3.0)

    assert on_edge["wall_line_id"].iloc[0] == "WL0000001"
    assert on_edge["wall_edge_length_m"].iloc[0] == pytest.approx(12.0)
    assert on_edge["wall_line_ids"].iloc[0] == ["WL0000001", "WL0000002"]


def test_a_line_running_across_the_edge_is_not_on_it():
    # A line ending against the crest from uphill, and one crossing the east
    # edge: both meet the buffered boundary, neither runs along it.
    face = candidates([square(0, 0, 20)])
    lines = wall_lines(
        [line(10, 20, 10, 40), line(15, 10, 30, 10)], ["fill", "cut"], [2.0, 1.0]
    )

    on_edge = geometry.wall_line_on_edge(face, lines, tolerance_m=3.0)

    assert on_edge["wall_line_id"].iloc[0] is None
    assert on_edge["wall_line_ids"].iloc[0] == []


def test_a_flat_land_line_never_shadows_a_sloping_line_on_the_edge():
    # The toe of the face meets the NLM flatland: a long flat-land line along
    # the toe and a shorter sloping line on the same edge. The polygon takes
    # the sloping line and never records the flat-land one.
    face = candidates([square(0, 0, 20)])
    lines = wall_lines(
        [line(-5, 0, 25, 0), line(2, 0, 10, 0)],
        ["cut", "cut"],
        [2.0, 1.5],
        flat=[True, False],
    )

    polygons = geometry.reconcile_candidates(face, lines, tolerance_m=3.0)

    assert polygons["wall_line_id"].iloc[0] == "WL0000002"
    assert polygons["wall_line_ids"].iloc[0] == ["WL0000002"]
    assert polygons["wall_face_height_m"].iloc[0] == 1.5


def test_reconciling_lines_without_the_flat_land_flag_is_refused():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 11, 15, 11)], ["fill"], [2.0]).drop(
        columns="is_flatland"
    )

    with pytest.raises(ValueError, match="is_flatland"):
        geometry.reconcile_candidates(face, lines, tolerance_m=3.0)


def test_a_polygon_with_no_line_nearby_has_no_wall_on_its_edge():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 20, 15, 20)], ["fill"], [2.0])

    on_edge = geometry.wall_line_on_edge(face, lines, tolerance_m=3.0)

    assert on_edge["wall_line_id"].iloc[0] is None
    assert on_edge["wall_edge_length_m"].iloc[0] == 0.0
    assert on_edge["wall_line_ids"].iloc[0] == []


def test_reconciling_carries_the_line_attributes_and_recomputes_the_measures():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 11, 15, 11)], ["fill"], [2.0])

    polygons = geometry.reconcile_candidates(face, lines, tolerance_m=3.0)

    assert polygons["wall_position"].iloc[0] == "fill"
    assert polygons["wall_face_height_m"].iloc[0] == 2.0
    assert polygons["area_m2"].iloc[0] == pytest.approx(110.0)
    assert polygons["contour_length_m"].iloc[0] == pytest.approx(10.0)


def test_reconciling_with_no_lines_leaves_every_candidate_whole():
    faces = candidates([square(0, 0, 10), square(20, 0, 10)])

    polygons = geometry.reconcile_candidates(faces, no_lines(), tolerance_m=3.0)

    assert len(polygons) == 2
    assert (polygons["piece"] == 0).all()
    assert polygons["wall_line_id"].isna().all()
    assert polygons["wall_position"].isna().all()
    assert polygons["wall_face_height_m"].isna().all()


def test_frames_in_different_systems_are_refused():
    face = candidates([square(0, 0, 10)])
    lines = wall_lines([line(-5, 11, 15, 11)], ["fill"], [2.0]).to_crs("EPSG:4326")

    with pytest.raises(ValueError, match="reproject"):
        geometry.reconcile_candidates(face, lines, tolerance_m=3.0)


# --- Nesting and ids ---------------------------------------------------------


def test_the_smallest_coarser_polygon_covering_the_child_is_its_parent():
    faces = candidates(
        [square(2, 2, 3), square(0, 0, 10), square(-10, -10, 40)],
        scale_m=[1, 10, 30],
    )
    faces["slope_id"] = ["SP0000003", "SP0000002", "SP0000001"]

    parents = geometry.nest_parents(faces)

    assert parents.tolist() == ["SP0000002", "SP0000001", None]


def test_a_coarser_polygon_covering_too_little_is_not_a_parent():
    faces = candidates([square(0, 0, 10), square(5, 0, 10)], scale_m=[1, 10])
    faces["slope_id"] = ["SP0000002", "SP0000001"]

    parents = geometry.nest_parents(faces)

    assert parents.tolist() == [None, None]


def mint(polygons):
    ordered = sort_by_point(polygons, by=("scale_m",), ascending=(False,))
    ordered["slope_id"] = mint_ids(constants.SLOPE_ID_PREFIX, len(ordered)).to_numpy()
    return ordered


def test_ids_are_stable_under_row_order():
    faces = candidates(
        [square(0, 0, 10), square(20, 0, 10), square(-10, -10, 40)],
        scale_m=[1, 1, 10],
    )
    lines = wall_lines([line(-5, 5, 15, 5)], ["cut"], [1.0])

    forward = mint(geometry.reconcile_candidates(faces, lines, tolerance_m=3.0))
    shuffled = faces.iloc[[2, 0, 1]].reset_index(drop=True)
    backward = mint(geometry.reconcile_candidates(shuffled, lines, tolerance_m=3.0))

    key = ["candidate_id", "piece"]
    assert forward.set_index(key)["slope_id"].equals(
        backward.set_index(key)["slope_id"]
    )
    # Coarsest first, then west to east.
    assert forward["scale_m"].tolist() == [10, 1, 1, 1]
    assert forward["slope_id"].iloc[0] == "SP0000001"


# --- The fixed geometries ---------------------------------------------------


def test_the_headscarp_band_is_a_metre_above_thirty_degrees():
    assert geometry.headscarp_band_m(20.0) == 0.5
    assert geometry.headscarp_band_m(30.0) == 1.0
    assert geometry.headscarp_band_m(45.0) == 1.0


def test_the_crest_faces_uphill_and_the_toe_downhill():
    face = square(0, 0, 10)

    crest = geometry.crest_line(face, SOUTH)
    toe = geometry.toe_line(face, SOUTH)

    assert crest.length == pytest.approx(10.0)
    assert set(np.asarray(crest.coords)[:, 1]) == {Y0 + 10}
    assert toe.length == pytest.approx(10.0)
    assert set(np.asarray(toe.coords)[:, 1]) == {Y0}


def test_the_evacuated_no_wall_geometry_is_the_face_plus_the_band_above_the_crest():
    face = square(0, 0, 10)

    evacuated = geometry.evacuated_no_wall(face, SOUTH, 35.0)
    imminent = geometry.imminent_no_wall(face, SOUTH, 35.0)

    assert evacuated.area == pytest.approx(110.0)
    assert evacuated.bounds[3] == pytest.approx(Y0 + 11)
    assert imminent.area == pytest.approx(10.0)
    assert imminent.bounds[1] == pytest.approx(Y0 + 11)
    assert imminent.bounds[3] == pytest.approx(Y0 + 12)


def test_the_fill_wedge_on_a_planar_slope_has_area_length_times_height():
    wall = line(0, 10, 10, 10)

    wedge = geometry.fill_wedge(wall, SOUTH, 2.0)
    imminent = geometry.imminent_fill_wall(wall, SOUTH, 2.0)

    assert wedge.area == pytest.approx(20.0)
    assert wedge.bounds[1] == pytest.approx(Y0 + 10)
    assert wedge.bounds[3] == pytest.approx(Y0 + 12)
    assert imminent.area == pytest.approx(20.0)
    assert imminent.bounds[1] == pytest.approx(Y0 + 12)


def test_the_dry_reach_angle_falls_log_linearly_with_volume():
    assert geometry.dry_reach_angle(100.0) == pytest.approx(0.9)
    assert geometry.dry_reach_angle(1_000.0) == pytest.approx(0.85)
    assert geometry.dry_reach_angle(10_000.0) == pytest.approx(0.8)
    assert geometry.dry_reach_angle(1.0) == pytest.approx(0.9)
    assert geometry.dry_reach_angle(1e6) == pytest.approx(0.8)


def test_runout_on_a_planar_slope_reaches_relief_over_hl_from_the_crest():
    # A 10 m face dropping 9 m: the deposit toe lies 9 / 0.9 = 10 m from the
    # crest, which is at the face's own toe, so nothing runs past it.
    assert geometry.runout_length_m(9.0, 0.9, 10.0) == pytest.approx(0.0)
    # Dropping 18 m, the reach is 20 m from the crest: 10 m past the toe.
    assert geometry.runout_length_m(18.0, 0.9, 10.0) == pytest.approx(10.0)


def test_the_inundated_strip_runs_downhill_from_the_toe():
    toe = geometry.toe_line(square(0, 0, 10), SOUTH)

    inundated = geometry.inundated_polygon(toe, SOUTH, 12.0, barriers=no_barriers())

    assert inundated.bounds[1] == pytest.approx(Y0 - 12)
    assert inundated.bounds[3] == pytest.approx(Y0)
    assert inundated.area == pytest.approx(120.0)


def test_a_barrier_truncates_the_runout():
    toe = geometry.toe_line(square(0, 0, 10), SOUTH)
    house = gpd.GeoSeries([square(0, -8, 10, 3)], crs=constants.DEFAULT_CRS)

    inundated = geometry.inundated_polygon(toe, SOUTH, 12.0, barriers=house)

    assert inundated.bounds[1] == pytest.approx(Y0 - 5)
    assert inundated.area == pytest.approx(50.0)


def test_a_barrier_at_the_toe_leaves_the_minimum_strip():
    toe = geometry.toe_line(square(0, 0, 10), SOUTH)
    house = gpd.GeoSeries([square(0, -2, 10, 2)], crs=constants.DEFAULT_CRS)

    inundated = geometry.inundated_polygon(toe, SOUTH, 12.0, barriers=house)

    assert inundated.area == pytest.approx(10.0 * geometry.BETA_MIN_RUNOUT_M)


def test_the_evacuated_depth_rules():
    assert (
        geometry.evacuated_depth_m(50.0, "colluvium", np.nan)
        == geometry.COLLUVIUM_DEPTH_M
    )
    assert geometry.evacuated_depth_m(50.0, "fill_uncontrolled", 2.5) == 2.5
    assert (
        geometry.evacuated_depth_m(50.0, "fill_uncontrolled", 0.5)
        == geometry.COLLUVIUM_DEPTH_M
    )
    assert (
        geometry.evacuated_depth_m(50.0, "colluvium", 4.0) == geometry.COLLUVIUM_DEPTH_M
    )
    large = geometry.evacuated_depth_m(5_000.0, "colluvium", np.nan)
    assert large >= geometry.COLLUVIUM_DEPTH_M
    assert geometry.fill_wall_depth_m(2.0) == 1.0


def test_the_no_wall_state_is_always_filled_and_the_others_only_with_a_wall():
    states = geometry.state_geometries(
        square(0, 0, 10),
        aspect_degrees=SOUTH,
        slope_degrees=35.0,
        relief_m=5.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=None,
        wall_position=None,
        wall_height_m=None,
        barriers=no_barriers(),
    )

    for kind in geometry.GEOMETRY_KINDS:
        assert states[f"{kind}_no_wall"].area > 0
        assert states[f"{kind}_fill_wall"] is None
        assert states[f"{kind}_cut_wall"] is None
    assert states["depth_evacuated_no_wall_m"] == geometry.COLLUVIUM_DEPTH_M
    assert np.isnan(states["depth_evacuated_fill_wall_m"])
    # Volume is conserved: nothing stops the debris, so it spreads at least as
    # thin as the ground that left.
    assert states["depth_inundated_no_wall_m"] <= states["depth_evacuated_no_wall_m"]


def test_a_fill_wall_fills_the_fill_state_and_a_cut_wall_copies_no_wall():
    wall = line(0, 10, 10, 10)
    fill = geometry.state_geometries(
        square(0, 0, 10),
        aspect_degrees=SOUTH,
        slope_degrees=35.0,
        relief_m=5.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=wall,
        wall_position="fill",
        wall_height_m=2.0,
        barriers=no_barriers(),
    )
    cut = geometry.state_geometries(
        square(0, 0, 10),
        aspect_degrees=SOUTH,
        slope_degrees=35.0,
        relief_m=5.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=line(0, 0, 10, 0),
        wall_position="cut",
        wall_height_m=1.0,
        barriers=no_barriers(),
    )

    assert fill["evacuated_fill_wall"].area == pytest.approx(20.0)
    assert fill["depth_evacuated_fill_wall_m"] == 1.0
    assert fill["inundated_fill_wall"].area > 0
    assert fill["evacuated_cut_wall"] is None
    assert cut["evacuated_cut_wall"].equals(cut["evacuated_no_wall"])
    assert cut["depth_inundated_cut_wall_m"] == cut["depth_inundated_no_wall_m"]
    assert cut["evacuated_fill_wall"] is None


def test_a_fill_wall_with_no_height_read_builds_the_minimum_wedge():
    # A GNS mapped wall is kept whatever its face reads (contract section
    # 3.5), and its face height is NaN when every sample fell off the raster.
    states = geometry.state_geometries(
        square(0, 0, 10),
        aspect_degrees=SOUTH,
        slope_degrees=35.0,
        relief_m=5.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=line(0, 10, 10, 10),
        wall_position="fill",
        wall_height_m=np.nan,
        barriers=no_barriers(),
    )

    assert states["evacuated_fill_wall"].area == pytest.approx(
        10.0 * constants.MIN_WALL_HEIGHT_M
    )
    assert states["depth_evacuated_fill_wall_m"] == constants.MIN_WALL_HEIGHT_M / 2
    assert states["inundated_fill_wall"].area > 0


def test_a_fill_wall_with_a_height_of_none_is_refused():
    with pytest.raises(ValueError, match="height"):
        geometry.state_geometries(
            square(0, 0, 10),
            aspect_degrees=SOUTH,
            slope_degrees=35.0,
            relief_m=5.0,
            material="colluvium",
            fill_thickness_m=np.nan,
            wall_line=line(0, 10, 10, 10),
            wall_position="fill",
            wall_height_m=None,
            barriers=no_barriers(),
        )


def test_a_level_polygon_with_no_direction_takes_a_band_around_its_edge():
    # Step 6 keeps a level run with no gentle neighbour as a patch of its own,
    # with a NaN aspect; its ground leaves, and the debris lies all round it.
    face = square(0, 0, 10)
    states = geometry.state_geometries(
        face,
        aspect_degrees=np.nan,
        slope_degrees=0.0,
        relief_m=0.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=None,
        wall_position=None,
        wall_height_m=None,
        barriers=no_barriers(),
    )

    assert states["evacuated_no_wall"].equals(face)
    imminent = states["imminent_no_wall"]
    assert imminent.is_valid
    assert not imminent.is_empty
    assert imminent.bounds == pytest.approx((X0 - 0.5, Y0 - 0.5, X0 + 10.5, Y0 + 10.5))
    assert imminent.intersection(face).area == pytest.approx(0.0)
    inundated = states["inundated_no_wall"]
    assert inundated.is_valid
    assert not inundated.is_empty
    assert inundated.intersection(face).area == pytest.approx(0.0)
    # The band holds the evacuated ground at its own depth or thinner.
    assert states["depth_evacuated_no_wall_m"] == geometry.COLLUVIUM_DEPTH_M
    assert np.isfinite(states["depth_inundated_no_wall_m"])
    assert states["depth_inundated_no_wall_m"] <= states["depth_evacuated_no_wall_m"]
    for kind in geometry.GEOMETRY_KINDS:
        assert states[f"{kind}_fill_wall"] is None
        assert states[f"{kind}_cut_wall"] is None


def test_a_wall_on_a_level_polygon_copies_the_no_wall_state():
    face = square(0, 0, 10)
    fill = geometry.state_geometries(
        face,
        aspect_degrees=np.nan,
        slope_degrees=0.0,
        relief_m=0.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=line(0, 10, 10, 10),
        wall_position="fill",
        wall_height_m=2.0,
        barriers=no_barriers(),
    )
    cut = geometry.state_geometries(
        face,
        aspect_degrees=np.nan,
        slope_degrees=0.0,
        relief_m=0.0,
        material="colluvium",
        fill_thickness_m=np.nan,
        wall_line=line(0, 0, 10, 0),
        wall_position="cut",
        wall_height_m=1.0,
        barriers=no_barriers(),
    )

    for kind in geometry.GEOMETRY_KINDS:
        assert fill[f"{kind}_fill_wall"].equals(fill[f"{kind}_no_wall"])
        assert fill[f"{kind}_cut_wall"] is None
        assert cut[f"{kind}_cut_wall"].equals(cut[f"{kind}_no_wall"])
        assert cut[f"{kind}_fill_wall"] is None
    assert fill["depth_inundated_fill_wall_m"] == fill["depth_inundated_no_wall_m"]
    assert cut["depth_evacuated_cut_wall_m"] == cut["depth_evacuated_no_wall_m"]


def test_a_level_candidate_passes_through_the_chain_with_filled_states():
    # One sloping face and one level patch (NaN aspect, octant -1) through
    # reconcile and attach, as step 7 runs them.
    faces = candidates(
        [square(0, 0, 10), square(20, 0, 10)],
        aspect_degrees=[SOUTH, np.nan],
        aspect_octant=[4, -1],
        slope_band=["30-45", "0-10"],
        slope_degrees=[35.0, 0.0],
        relief_m=[5.0, 0.0],
    )
    lines = wall_lines([line(15, 11, 35, 11)], ["fill"], [np.nan])

    polygons = geometry.reconcile_candidates(faces, lines, tolerance_m=3.0)
    polygons = geometry.attach_state_geometries(
        polygons, lines, barriers=no_barriers(), tolerance_m=3.0
    )

    level = polygons[polygons["aspect_degrees"].isna()]
    assert len(level) == 1
    assert np.isnan(level["contour_length_m"].iloc[0])
    assert level["wall_line_id"].iloc[0] == "WL0000001"
    for column in geometry.STATE_GEOMETRY_COLUMNS:
        filled = polygons[column].dropna()
        assert not filled.is_empty.any()
        assert filled.is_valid.all()
    assert polygons["evacuated_no_wall"].notna().all()
    assert level["evacuated_fill_wall"].notna().all()
    assert np.isfinite(polygons["depth_inundated_no_wall_m"]).all()


def test_a_wall_with_an_unknown_position_is_refused():
    with pytest.raises(ValueError, match="wall_position"):
        geometry.state_geometries(
            square(0, 0, 10),
            aspect_degrees=SOUTH,
            slope_degrees=35.0,
            relief_m=5.0,
            material="colluvium",
            fill_thickness_m=np.nan,
            wall_line=line(0, 10, 10, 10),
            wall_position="sideways",
            wall_height_m=2.0,
            barriers=no_barriers(),
        )


# --- Scoring -----------------------------------------------------------------


def test_the_amplification_factor_reaches_the_maximum_on_a_crest_or_a_steep_face():
    tpi = np.array([0.0, 10.0, 5.0, np.nan, 0.0])
    slope = np.array([20.0, 20.0, 20.0, 60.0, 45.0])

    factor = geometry.amplification_factor(tpi, slope)

    expected = [1.0, 1.5, 1.25, 1.5, 1.25]
    np.testing.assert_allclose(factor, expected)


def test_the_kingsbury_factors_follow_the_polygon_attributes():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0, 50.0, 10.0],
            "modification": ["cut", "fill", "natural"],
            "face_height_10m": [12.0, 12.0, 12.0],
            "geology_value": [4.0, 10.0, np.nan],
            "prior_failure": ["none", "relict", "recent"],
            "gw_depth_m": [4.0, 2.0, 0.5],
        }
    )

    factors = geometry.kingsbury_factors(polygons)

    np.testing.assert_allclose(factors["slope"], [8.0, 8.0, 0.0])
    np.testing.assert_allclose(factors["modification"], [8.0, 10.0, 0.0])
    np.testing.assert_allclose(factors["height"], [8.0, 8.0, 0.0])
    np.testing.assert_allclose(factors["landslides"], [0.0, 5.0, 10.0])
    np.testing.assert_allclose(factors["groundwater"], [0.0, 5.0, 10.0])
    rating = susceptibility.susceptibility_rating(**factors)
    assert rating[0] == pytest.approx(4 * 8 + 4 * 8 + 2 * 8 + 2 * 4)
    assert np.isnan(rating[2])


def test_an_unknown_prior_failure_is_refused():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0],
            "modification": ["cut"],
            "face_height_10m": [12.0],
            "geology_value": [4.0],
            "prior_failure": ["ancient"],
            "gw_depth_m": [4.0],
        }
    )
    with pytest.raises(ValueError, match="ancient"):
        geometry.kingsbury_factors(polygons)


# --- The step's library chain end to end -------------------------------------


def test_the_chain_writes_a_file_with_the_contract_columns(tmp_path):
    faces = candidates(
        [square(0, 0, 10), square(20, 0, 10), square(-10, -10, 40)],
        scale_m=[1, 1, 10],
    )
    lines = wall_lines(
        [line(-5, 11, 15, 11), line(15, 5, 35, 5)], ["fill", "cut"], [2.0, 1.0]
    )
    barriers = gpd.GeoSeries([square(0, -30, 60, 5)], crs=constants.DEFAULT_CRS)

    polygons = mint(geometry.reconcile_candidates(faces, lines, tolerance_m=3.0))
    polygons["parent_slope_id"] = geometry.nest_parents(polygons)
    factors = geometry.kingsbury_factors(polygons)
    polygons["kingsbury_rating"] = susceptibility.susceptibility_rating(**factors)
    polygons["kingsbury_zone"] = pd.Series(
        susceptibility.susceptibility_zone(polygons["kingsbury_rating"].to_numpy())
    ).astype("Int64")
    polygons["amp_factor"] = geometry.amplification_factor(
        polygons["topographic_position_100m"].to_numpy(),
        polygons["slope_degrees"].to_numpy(),
    )
    polygons = geometry.attach_state_geometries(
        polygons, lines, barriers=barriers, tolerance_m=3.0
    )
    polygons = polygons[list(CONTRACT_COLUMNS)]
    out_path = tmp_path / "urban-slope-polygons-pilot.geoparquet"
    polygons.to_parquet(out_path)

    written = gpd.read_parquet(out_path)
    assert list(written.columns) == list(CONTRACT_COLUMNS)
    assert written.crs == constants.DEFAULT_CRS
    # The 1 m candidate on the cut line is split in two; the line ends inside
    # the 30 m candidate, so that one stays whole.
    assert len(written) == 4
    assert written["slope_id"].is_unique
    assert written["slope_id"].str.match(r"^SP\d{7}$").all()
    assert written["kingsbury_zone"].dtype == "Int64"
    for column in geometry.STATE_GEOMETRY_COLUMNS:
        filled = written[column].dropna()
        assert not filled.is_empty.any()
        assert filled.is_valid.all()
    # Every row has its no-wall state; no row carries three states.
    assert written["evacuated_no_wall"].notna().all()
    both = (
        written["evacuated_fill_wall"].notna() & written["evacuated_cut_wall"].notna()
    )
    assert not both.any()
    fill = written[written["wall_position"] == "fill"]
    assert len(fill) == 1
    assert fill["evacuated_fill_wall"].notna().all()
    assert fill["evacuated_cut_wall"].isna().all()
    # The three 1 m polygons all nest in the 30 m one.
    assert written["parent_slope_id"].notna().sum() == 3
    assert written["parent_slope_id"].dropna().unique().tolist() == ["SP0000001"]
