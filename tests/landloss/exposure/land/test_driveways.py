import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from landloss.exposure.land.driveways import (
    DRIVEWAY_HALF_WIDTH_M,
    MAX_INSURED_ACCESS_M,
    generate_driveways,
    main_buildings,
    merge_driveways_into_extent,
    nearest_road_points,
)

CRS = "EPSG:2193"


def road(y=0.0):
    """A road running east-west."""
    return gpd.GeoDataFrame(
        {"road_id": [1]}, geometry=[LineString([(-200, y), (200, y)])], crs=CRS
    )


def house(x=0.0, y=50.0, size=10.0, address="A-001"):
    """A square building outline, its south face `y` north of the origin."""
    return gpd.GeoDataFrame(
        {"claim_id": [address]},
        geometry=[box(x, y, x + size, y + size)],
        crs=CRS,
    )


# --- finding the road --------------------------------------------------------


def test_the_driveway_starts_at_the_closest_corner_of_the_building():
    on_building, on_road, distance = nearest_road_points(house(y=50.0), road())
    assert on_building.iloc[0].y == pytest.approx(50.0)
    assert on_road.iloc[0].y == pytest.approx(0.0)
    assert distance[0] == pytest.approx(50.0)


def test_the_nearest_of_several_roads_wins():
    roads = gpd.GeoDataFrame(
        {"road_id": [1, 2]},
        geometry=[
            LineString([(-200, 0), (200, 0)]),
            LineString([(-200, 90), (200, 90)]),
        ],
        crs=CRS,
    )
    # The house sits at y=70..80, so the road at y=90 is 10 m away.
    _, _, distance = nearest_road_points(house(y=70.0), roads)
    assert distance[0] == pytest.approx(10.0)


def test_a_crs_mismatch_is_refused():
    with pytest.raises(ValueError, match="buildings are"):
        nearest_road_points(house(), road().to_crs("EPSG:4326"))


def test_no_roads_at_all_is_refused():
    empty = gpd.GeoDataFrame({"road_id": []}, geometry=[], crs=CRS)
    with pytest.raises(ValueError, match="no roads"):
        nearest_road_points(house(), empty)


# --- the corridor ------------------------------------------------------------


def test_a_driveway_is_a_corridor_of_the_right_area():
    driveways = generate_driveways(house(y=50.0), road())
    assert len(driveways) == 1
    # 50 m long, buffered by half the width each side, flat capped.
    expected = 50.0 * DRIVEWAY_HALF_WIDTH_M * 2
    assert driveways.geometry.iloc[0].area == pytest.approx(expected, rel=0.01)
    assert driveways["driveway_length_m"].iloc[0] == pytest.approx(50.0)


def test_a_building_already_on_the_road_gets_no_driveway():
    # Its south face sits exactly on the road, so there is nothing to draw and
    # the building buffer already covers that ground.
    assert generate_driveways(house(y=0.0), road()).empty


def test_a_building_too_far_from_any_road_reaches_none():
    assert generate_driveways(house(y=50.0), road(), max_length_m=10.0).empty


def test_the_driveway_carries_its_property():
    driveways = generate_driveways(house(address="A-042"), road())
    assert driveways["claim_id"].tolist() == ["A-042"]


def test_no_buildings_gives_no_driveways():
    empty = gpd.GeoDataFrame({"claim_id": []}, geometry=[], crs=CRS)
    assert generate_driveways(empty, road()).empty


def test_buildings_without_an_identifier_are_refused():
    with pytest.raises(ValueError, match="claim_id"):
        generate_driveways(house().drop(columns=["claim_id"]), road())


# --- merging into the extent -------------------------------------------------


def test_merging_a_driveway_grows_the_insured_land():
    extent = gpd.GeoDataFrame(
        {"claim_id": ["A-001"], "area_m2": [100.0]},
        geometry=[box(0, 50, 10, 60)],
        crs=CRS,
    )
    driveways = generate_driveways(house(y=50.0), road())
    merged = merge_driveways_into_extent(extent, driveways)
    assert merged.geometry.iloc[0].area > extent.geometry.iloc[0].area


def test_a_property_with_no_driveway_is_unchanged():
    extent = gpd.GeoDataFrame(
        {"claim_id": ["A-999"], "area_m2": [100.0]},
        geometry=[box(0, 50, 10, 60)],
        crs=CRS,
    )
    driveways = generate_driveways(house(address="A-001"), road())
    merged = merge_driveways_into_extent(extent, driveways)
    assert merged.geometry.iloc[0].equals(extent.geometry.iloc[0])


def test_merging_nothing_returns_the_extent_untouched():
    extent = gpd.GeoDataFrame(
        {"claim_id": ["A-001"]}, geometry=[Point(0, 0).buffer(5)], crs=CRS
    )
    empty = gpd.GeoDataFrame(
        {"claim_id": [], "driveway_length_m": []},
        geometry=gpd.GeoSeries([], crs=CRS),
        crs=CRS,
    )
    assert merge_driveways_into_extent(extent, empty) is extent


# --- one main access way per property, insured to 60 m ------------------------


def two_buildings(main_y=50.0, shed_y=20.0, address="A-001"):
    """A 10 m house and a 4 m shed on one property; the shed nearer the road."""
    return gpd.GeoDataFrame(
        {"claim_id": [address, address]},
        geometry=[box(0, main_y, 10, main_y + 10), box(30, shed_y, 34, shed_y + 4)],
        crs=CRS,
    )


def test_a_property_gets_one_driveway_however_many_buildings_it_has():
    """The Act covers the main access way, not one per building or dwelling."""
    driveways = generate_driveways(two_buildings(), road())

    assert len(driveways) == 1


def test_the_driveway_runs_from_the_main_building_not_the_shed():
    """The house is the larger building; the shed nearer the road adds nothing."""
    driveways = generate_driveways(two_buildings(main_y=50.0, shed_y=20.0), road())

    assert driveways["driveway_length_m"].iloc[0] == pytest.approx(50.0)


def test_the_main_building_is_the_largest_on_its_property():
    buildings = pd.concat([two_buildings(address="A"), house(address="B")])

    main = main_buildings(buildings)

    assert sorted(main["claim_id"]) == ["A", "B"]
    assert main.loc[main["claim_id"] == "A"].geometry.area.iloc[0] == pytest.approx(
        100.0
    )


def test_two_properties_still_get_a_driveway_each():
    buildings = pd.concat([house(x=0.0, address="A"), house(x=50.0, address="B")])

    driveways = generate_driveways(buildings, road())

    assert sorted(driveways["claim_id"]) == ["A", "B"]


def test_only_the_first_60_m_of_a_long_route_is_insured():
    """A dwelling 150 m from the road is insured for 60 m of its access way."""
    driveways = generate_driveways(house(y=150.0), road())

    row = driveways.iloc[0]
    assert row["driveway_length_m"] == pytest.approx(150.0)
    assert row["insured_driveway_length_m"] == pytest.approx(MAX_INSURED_ACCESS_M)
    expected = MAX_INSURED_ACCESS_M * DRIVEWAY_HALF_WIDTH_M * 2
    assert row.geometry.area == pytest.approx(expected, rel=0.01)


def test_the_insured_part_runs_from_the_dwelling():
    """Measured from the dwelling, so the corridor touches the house, not the road."""
    corridor = generate_driveways(house(y=150.0), road()).geometry.iloc[0]

    assert corridor.bounds[3] == pytest.approx(150.0)
    assert corridor.bounds[1] == pytest.approx(150.0 - MAX_INSURED_ACCESS_M)


def test_a_short_route_is_insured_whole():
    row = generate_driveways(house(y=40.0), road()).iloc[0]

    assert row["insured_driveway_length_m"] == pytest.approx(40.0)


def test_the_insured_limit_is_the_acts_60_m():
    assert MAX_INSURED_ACCESS_M == 60.0
