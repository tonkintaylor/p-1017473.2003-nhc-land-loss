"""Tests for the coverage filter that keeps only insured structures."""

import geopandas as gpd
import pytest
from shapely.affinity import rotate, translate
from shapely.geometry import GeometryCollection, LineString, Point, box

from landloss.domain import constants
from landloss.exposure.coverage import (
    CROSSING_COVERAGE_TOLERANCE_M,
    RW_COVERAGE_BUFFER_M,
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
