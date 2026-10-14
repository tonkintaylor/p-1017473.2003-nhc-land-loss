"""Tests for the coverage filter that keeps only insured structures."""

import geopandas as gpd
import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import GeometryCollection, LineString, Point, box

from landloss.domain import constants
from landloss.exposure.coverage import (
    CROSSING_COVERAGE_TOLERANCE_M,
    RW_COVERAGE_BUFFER_M,
    cut_walls_to_insured_stretches,
    insured_support_regions,
    keep_crossings_within_insured_land,
    keep_walls_on_insured_land,
)

# Two claims' insured land side by side, with a 20 m gap between them.
INSURED_A = box(0, 0, 20, 20)
INSURED_B = box(40, 0, 60, 20)

BOTH_FILTERS = [keep_walls_on_insured_land, keep_crossings_within_insured_land]


def make_insured(crs=constants.DEFAULT_CRS):
    return gpd.GeoDataFrame(
        {"claim_id": [1, 2]}, geometry=[INSURED_A, INSURED_B], crs=crs
    )


def make_assets(claims, geometries, crs=constants.DEFAULT_CRS):
    return gpd.GeoDataFrame(
        {"claim_id": claims, "label": [f"s{i}" for i in range(len(claims))]},
        geometry=geometries,
        crs=crs,
    )


def test_buffer_is_two_metres():
    assert RW_COVERAGE_BUFFER_M == 2.0


def test_wall_one_metre_outside_is_kept():
    walls = make_assets([1], [LineString([(21, 0), (21, 20)])])
    assert len(keep_walls_on_insured_land(walls, make_insured())) == 1


def test_wall_three_metres_outside_is_dropped():
    walls = make_assets([1], [LineString([(23, 0), (23, 20)])])
    assert keep_walls_on_insured_land(walls, make_insured()).empty


def test_wall_crossing_its_polygon_is_kept():
    walls = make_assets([1], [LineString([(10, -5), (10, 25)])])
    assert len(keep_walls_on_insured_land(walls, make_insured())) == 1


def test_wall_on_another_claims_land_is_dropped():
    walls = make_assets([1], [LineString([(50, 5), (50, 15)])])
    assert keep_walls_on_insured_land(walls, make_insured()).empty


def test_wall_of_a_claim_without_insured_land_is_dropped():
    walls = make_assets([1, 99], [LineString([(5, 5), (5, 15)])] * 2)
    result = keep_walls_on_insured_land(walls, make_insured())
    assert result["claim_id"].tolist() == [1]
    assert list(result.columns) == list(walls.columns)


def test_crossing_inside_is_kept():
    crossings = make_assets([2], [LineString([(45, 5), (55, 5)])])
    assert len(keep_crossings_within_insured_land(crossings, make_insured())) == 1


def test_crossing_onto_the_road_reserve_is_dropped():
    crossings = make_assets([1], [LineString([(10, 5), (10, -3)])])
    assert keep_crossings_within_insured_land(crossings, make_insured()).empty


def test_polygon_crossing_fully_inside_is_kept():
    crossings = make_assets([1], [box(5, 5, 8, 15)])
    assert len(keep_crossings_within_insured_land(crossings, make_insured())) == 1


def test_geometry_collection_fully_inside_is_kept():
    collection = GeometryCollection([Point(2, 2), LineString([(3, 3), (6, 6)])])
    crossings = make_assets([1], [collection])
    assert len(keep_crossings_within_insured_land(crossings, make_insured())) == 1


def test_crossing_on_another_claims_land_is_dropped():
    crossings = make_assets([2, 1], [box(5, 5, 8, 15), Point(10, 10)])
    result = keep_crossings_within_insured_land(crossings, make_insured())
    assert result["label"].tolist() == ["s1"]


@pytest.mark.parametrize("keep", BOTH_FILTERS)
def test_empty_input_returns_an_empty_frame(keep):
    assets = make_assets([], [])
    result = keep(assets, make_insured())
    assert result.empty
    assert list(result.columns) == list(assets.columns)
    assert result.crs == assets.crs


@pytest.mark.parametrize("keep", BOTH_FILTERS)
def test_crs_mismatch_raises(keep):
    assets = make_assets([1], [Point(5, 5)], crs="EPSG:3857")
    with pytest.raises(ValueError, match="reproject"):
        keep(assets, make_insured())


@pytest.mark.parametrize("keep", BOTH_FILTERS)
def test_geographic_crs_raises(keep):
    assets = make_assets([1], [Point(5, 5)], crs="EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        keep(assets, make_insured(crs="EPSG:4326"))


def _rotated_crossing_case(angle_deg, offset):
    """A crossing cut from the corridor the insured land is built from.

    Mirrors step 5 and step 7 at NZTM scale: a rotated property, a building
    buffer unioned with a 1.5 m driveway corridor and clipped to the property,
    and a stream crossing the unclipped corridor wholly inside the property.
    """
    origin = (1_748_912.37 + offset, 5_427_503.81 - offset)
    parcel = rotate(box(0, 0, 23.7, 41.3), angle_deg, origin=(0, 0))
    building = rotate(box(6.1, 24.9, 17.3, 35.2), angle_deg, origin=(0, 0))
    driveway = rotate(
        LineString([(11.7, 24.9), (11.7, -8.4)]), angle_deg, origin=(0, 0)
    )
    stream = rotate(
        LineString([(-5.3, 9.7 + offset / 100), (30.1, 13.9)]), angle_deg, origin=(0, 0)
    )
    parcel, building, driveway, stream = (
        translate(g, *origin) for g in (parcel, building, driveway, stream)
    )
    corridor = driveway.buffer(1.5, cap_style="flat")
    insured = building.buffer(3.0).union(corridor).intersection(parcel)
    crossing = gpd.overlay(
        gpd.GeoDataFrame(
            {"claim_id": [1]}, geometry=[corridor], crs=constants.DEFAULT_CRS
        ),
        gpd.GeoDataFrame(geometry=[stream], crs=constants.DEFAULT_CRS),
        how="intersection",
        keep_geom_type=False,
    )
    return crossing, insured


def test_a_crossing_sharing_the_corridor_edge_at_nztm_scale_is_kept():
    # The overlay rounds the crossing's ends, which sit on the corridor edge and
    # so on the insured boundary, a hair either side of it. An exact covered_by
    # test drops a large share of these; the tolerance must keep every one.
    cases = [(a, o) for a in (13.0, 27.4, 41.9, 58.3, 77.1, 102.6) for o in range(8)]
    for angle, offset in cases:
        crossing, insured = _rotated_crossing_case(angle, offset)
        insured_frame = gpd.GeoDataFrame(
            {"claim_id": [1]}, geometry=[insured], crs=constants.DEFAULT_CRS
        )
        kept = keep_crossings_within_insured_land(crossing, insured_frame)
        assert len(kept) == 1, (angle, offset)


def test_the_tolerance_does_not_keep_a_crossing_off_the_land():
    crossings = make_assets([1], [LineString([(10, 5), (10, -0.01)])])
    assert CROSSING_COVERAGE_TOLERANCE_M < 0.01
    assert keep_crossings_within_insured_land(crossings, make_insured()).empty


# The WU0017745 shape in metres: a 39.7 m wall with 32.1 m on parcel A, whose
# insured land is 15.65 m away, and 7.6 m on parcel B, which touches B's land.
PARCEL_A = box(-10, -10, 32.1, 30)
PARCEL_B = box(32.1, -10, 80, 30)
STRETCH_INSURED_A = box(0, 15.65, 20, 25)
STRETCH_INSURED_B = box(35, 0, 60, 20)


def make_parcels(ids, geometries, crs=constants.DEFAULT_CRS):
    return gpd.GeoDataFrame({"claim_id": ids}, geometry=geometries, crs=crs)


def make_regions(parcels=None, insured=None):
    parcels = (
        parcels
        if parcels is not None
        else make_parcels(["A", "B"], [PARCEL_A, PARCEL_B])
    )
    insured = (
        insured
        if insured is not None
        else make_parcels(["A", "B"], [STRETCH_INSURED_A, STRETCH_INSURED_B])
    )
    return insured_support_regions(parcels, insured)


def make_lines(geometries, crs=constants.DEFAULT_CRS):
    return gpd.GeoDataFrame(
        {"wall_line_id": [f"W{i}" for i in range(len(geometries))]},
        geometry=geometries,
        crs=crs,
    )


def cut(lines, regions=None, min_length_m=1.0):
    return cut_walls_to_insured_stretches(
        lines,
        make_regions() if regions is None else regions,
        wall_id_column="wall_line_id",
        min_length_m=min_length_m,
    )


def test_region_is_the_parcel_clipped_to_the_buffered_land():
    regions = make_regions()
    assert list(regions.columns) == ["claim_id", "geometry"]
    expected = PARCEL_B.intersection(STRETCH_INSURED_B.buffer(RW_COVERAGE_BUFFER_M))
    region_b = regions.set_index("claim_id").geometry["B"]
    assert region_b.symmetric_difference(expected).area == pytest.approx(0, abs=1e-6)


def test_claim_with_no_parcel_has_no_region():
    parcels = make_parcels(["A"], [PARCEL_A])
    regions = make_regions(parcels=parcels)
    assert "B" not in set(regions["claim_id"])


def test_invalid_parcel_is_repaired():
    bowtie = gpd.GeoSeries.from_wkt(
        ["POLYGON ((30 0, 50 20, 50 0, 30 20, 30 0))"], crs=constants.DEFAULT_CRS
    ).iloc[0]
    parcels = make_parcels(["B"], [bowtie])
    insured = make_parcels(["B"], [box(30, 0, 50, 20)])
    regions = insured_support_regions(parcels, insured)
    assert regions.geometry.is_valid.all()
    assert not regions.empty


def test_duplicate_claim_ids_raise():
    parcels = make_parcels(["A", "B"], [PARCEL_A, PARCEL_B])
    insured = make_parcels(["A", "B"], [STRETCH_INSURED_A, STRETCH_INSURED_B])
    twice = make_parcels(["A", "A"], [PARCEL_A, PARCEL_B])
    with pytest.raises(ValueError, match="repeats"):
        insured_support_regions(twice, insured)
    with pytest.raises(ValueError, match="repeats"):
        insured_support_regions(parcels, twice)


def test_wu0017745_is_insured_on_the_neighbour_at_its_supporting_stretch():
    wall = LineString([(0, 0), (39.7, 0)])
    stretches = cut(make_lines([wall]))
    assert list(stretches["claim_id"]) == ["B"]
    assert stretches["length_m"].iloc[0] == pytest.approx(6.7)
    assert stretches.geometry.iloc[0].equals_exact(
        LineString([(33, 0), (39.7, 0)]), tolerance=1e-6
    )
    old = keep_walls_on_insured_land(
        make_assets(["A"], [wall]),
        make_parcels(["A", "B"], [STRETCH_INSURED_A, STRETCH_INSURED_B]),
    )
    assert old.empty


def test_land_within_two_metres_on_a_neighbours_parcel_gives_nothing():
    parcels = make_parcels(["A", "N"], [box(0, 0, 20, 20), box(20, 0, 40, 20)])
    insured = make_parcels(["A"], [box(0, 0, 19, 20)])
    # 1 m past A's land but on N's parcel, which has no insured land.
    wall = LineString([(20.5, 2), (20.5, 18)])
    assert cut(make_lines([wall]), make_regions(parcels, insured)).empty


def test_wall_over_two_supported_parcels_gives_two_rows_longest_first():
    parcels = make_parcels(["A", "B"], [box(0, 0, 20, 20), box(20, 0, 40, 20)])
    insured = make_parcels(["A", "B"], [box(0, 0, 20, 20), box(20, 0, 40, 20)])
    wall = LineString([(10, 10), (30, 10)])
    stretches = cut(make_lines([wall]), make_regions(parcels, insured))
    assert list(stretches["claim_id"]) == ["A", "B"]
    assert list(stretches["length_m"]) == pytest.approx([10, 10])
    wall = LineString([(5, 10), (30, 10)])
    stretches = cut(make_lines([wall]), make_regions(parcels, insured))
    assert list(stretches["claim_id"]) == ["A", "B"]
    assert list(stretches["length_m"]) == pytest.approx([15, 10])
    stretches = cut(
        make_lines([LineString([(15, 10), (30, 10)])]), make_regions(parcels, insured)
    )
    assert list(stretches["claim_id"]) == ["B", "A"]


def test_stretch_under_one_metre_is_dropped_and_one_metre_kept():
    parcels = make_parcels(["A"], [box(0, 0, 20, 20)])
    insured = make_parcels(["A"], [box(0, 0, 20, 20)])
    regions = make_regions(parcels, insured)
    short = LineString([(19.2, 10), (30, 10)])
    exact = LineString([(19.0, 10), (30, 10)])
    assert cut(make_lines([short]), regions).empty
    assert len(cut(make_lines([exact]), regions)) == 1


def test_wall_leaving_and_reentering_a_region_is_one_multiline_row():
    parcels = make_parcels(["A"], [box(0, 0, 40, 20)])
    insured = make_parcels(["A"], [box(0, 0, 10, 20).union(box(20, 0, 40, 20))])
    regions = make_regions(parcels, insured)
    wall = LineString([(0, 10), (40, 10)])
    stretches = cut(make_lines([wall]), regions)
    assert len(stretches) == 1
    assert stretches.geometry.iloc[0].geom_type == "MultiLineString"
    # 12 m from the first block, then 20 + 2 m from the second.
    assert stretches["length_m"].iloc[0] == pytest.approx(12 + 22)


def test_many_walls_keep_their_own_stretches_when_some_pairs_clip_to_nothing():
    regions = make_regions(
        make_parcels(["A"], [box(0, 0, 10, 1000)]),
        make_parcels(["A"], [box(0, 0, 10, 1000)]),
    )
    walls = []
    for index in range(200):
        y = 4 * index
        # Every third wall only touches the region at a point, so its pair
        # clips to a point and leaves a gap among the pairs that give lines.
        walls.append(
            LineString([(12, y), (10, y)])
            if index % 3 == 0
            else LineString([(0, y), (2 + index % 5, y)])
        )
    stretches = cut(make_lines(walls), regions)
    expected = {f"W{i}": 2 + i % 5 for i in range(200) if i % 3}
    assert dict(
        zip(stretches["wall_line_id"], stretches["length_m"], strict=False)
    ) == {key: pytest.approx(value) for key, value in expected.items()}


BOUNDARY_PARCELS = make_parcels(["A", "B"], [box(0, 0, 20, 20), box(20, 0, 40, 20)])


def boundary_regions(insured_ids=("A", "B")):
    land = {"A": box(0, 0, 20, 20), "B": box(20, 0, 40, 20)}
    insured = make_parcels(list(insured_ids), [land[i] for i in insured_ids])
    return make_regions(BOUNDARY_PARCELS, insured)


def shares(stretches):
    return dict(zip(stretches["claim_id"], stretches["length_m"], strict=True))


def test_a_wall_on_a_shared_boundary_is_split_equally():
    wall = LineString([(20, 5), (20, 15)])
    stretches = cut(make_lines([wall]), boundary_regions())
    assert shares(stretches) == {"A": pytest.approx(5.0), "B": pytest.approx(5.0)}
    # The line is the claim's whole stretch; only length_m is the share.
    for line in stretches.geometry:
        assert line.length == pytest.approx(10.0)


def test_a_partly_shared_wall_shares_only_the_boundary_part():
    # 6 m on the boundary, then 4 m inside parcel A alone.
    wall = LineString([(20, 2), (20, 8), (16, 8)])
    stretches = cut(make_lines([wall]), boundary_regions())
    assert shares(stretches) == {"A": pytest.approx(7.0), "B": pytest.approx(3.0)}


def test_a_boundary_wall_with_insured_land_on_one_side_only_goes_to_that_side():
    wall = LineString([(20, 5), (20, 15)])
    stretches = cut(make_lines([wall]), boundary_regions(["A"]))
    assert shares(stretches) == {"A": pytest.approx(10.0)}
    stretches = cut(make_lines([wall]), boundary_regions(["B"]))
    assert shares(stretches) == {"B": pytest.approx(10.0)}


def test_the_minimum_length_applies_to_the_shared_length():
    # 1.6 m on the boundary is 0.8 m each, under the 1 m minimum.
    short = LineString([(20, 5), (20, 6.6)])
    assert cut(make_lines([short]), boundary_regions()).empty
    # 2 m is 1 m each, which is kept.
    exact = LineString([(20, 5), (20, 7)])
    assert shares(cut(make_lines([exact]), boundary_regions())) == {
        "A": pytest.approx(1.0),
        "B": pytest.approx(1.0),
    }


def test_a_walls_shares_never_exceed_its_length():
    walls = [
        LineString([(20, 5), (20, 15)]),
        LineString([(20, 2), (20, 8), (16, 8)]),
        LineString([(5, 10), (30, 10)]),
        LineString([(15, 3), (25, 3)]),
        LineString([(20, 1), (20, 19)]),
    ]
    lines = make_lines(walls)
    stretches = cut(lines, boundary_regions())
    total = stretches.groupby("wall_line_id")["length_m"].sum()
    length = lines.set_index("wall_line_id").geometry.length
    assert (total <= length.reindex(total.index) + 1e-9).all()


def test_overlapping_stretches_cut_off_the_grid_are_shared_not_doubled():
    # Overlapping parcels cut a diagonal wall at off-grid points, so the two
    # stretches over the overlap differ by float noise. Unsnapped, the union
    # kept both copies and the shares summed to 24.6 m on a 19.3 m wall
    # (WU0000893 in the Wellington pilot, 2026-10-14).
    parcels = make_parcels(["A", "B"], [box(-1, -1, 10, 20), box(5.3, -1, 30, 20)])
    wall = LineString([(0.123456, 0.987654), (17.31, 9.77)])
    stretches = cut(make_lines([wall]), make_regions(parcels, parcels))
    assert stretches["length_m"].sum() == pytest.approx(wall.length, abs=1e-6)
    overlap = wall.intersection(box(5.3, -1, 10, 20)).length
    alone_a = wall.intersection(box(-1, -1, 5.3, 20)).length
    assert shares(stretches)["A"] == pytest.approx(alone_a + overlap / 2, abs=1e-6)


def test_wall_supporting_nothing_gives_no_row():
    wall = LineString([(0, 0), (10, 0)])
    assert cut(make_lines([wall])).empty


def test_empty_walls_give_an_empty_frame_with_the_columns():
    stretches = cut(make_lines([]))
    assert stretches.empty
    assert list(stretches.columns) == [
        "wall_line_id",
        "claim_id",
        "length_m",
        "geometry",
    ]
    assert stretches.crs == constants.DEFAULT_CRS


def test_stretch_cut_crs_mismatch_raises():
    with pytest.raises(ValueError, match="reproject"):
        cut(make_lines([LineString([(0, 0), (1, 1)])], crs=4326))


def test_stretch_cut_geographic_crs_raises():
    regions = make_regions().set_crs(4326, allow_override=True)
    lines = make_lines([LineString([(0, 0), (1, 1)])], crs=4326)
    with pytest.raises(ValueError, match="geographic"):
        cut(lines, regions)
