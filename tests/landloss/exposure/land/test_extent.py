"""Tests for the insured land extent built around the property boundaries."""

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from landloss.domain import constants, loss_contract
from landloss.exposure.land import driveways as driveways_module
from landloss.exposure.land import extent as extent_module
from landloss.exposure.land.extent import (
    ADDRESS_ID_COLUMN,
    AREA_COLUMN,
    BOUNDARY_ROW_COLUMN,
    BUILDING_COUNT_COLUMN,
    CLAIM_ID_COLUMN,
    DWELLING_COUNT_COLUMN,
    INSURED_LAND_BUFFER_M,
    MAX_DWELLING_FOOTPRINT_M2,
    OUTLINE_ID_COLUMN,
    PROPERTY_ADDRESS_COUNT_COLUMN,
    PROPERTY_AREA_COLUMN,
    PROPERTY_RATING_UNIT_COUNT_COLUMN,
    SECTION_AREA_COLUMN,
    UNNAMED_BUILDING_USE,
    assign_buildings_to_properties,
    build_claim_properties,
    build_insured_land_extent,
    count_dwellings,
    drop_non_residential_buildings,
    section_area_per_address,
)

# Two 40 m square sections side by side, each holding a 10 m square building in
# its middle. Small enough to work out by hand: the 8 m buffer of a building
# reaches 26 m across, so it stops well inside its own section.
SECTION_A = box(0, 0, 40, 40)
SECTION_B = box(40, 0, 80, 40)
BUILDING_A = box(15, 15, 25, 25)
BUILDING_B = box(55, 15, 65, 25)

TOLERANCE_M2 = 1.0


def make_boundaries(polygons, sources=None, ids=None, crs=constants.DEFAULT_CRS):
    """Build a property boundary frame in the shape the LINZ layer arrives in."""
    count = len(polygons)
    return gpd.GeoDataFrame(
        {
            "source": sources or ["NZ Unit of Property"] * count,
            "source_id": ids or [f"p{index}" for index in range(count)],
            "title_type": ["Freehold"] * count,
        },
        geometry=list(polygons),
        crs=crs,
    )


def make_buildings(polygons, uses=None, crs=constants.DEFAULT_CRS):
    """Build a building outline frame."""
    return gpd.GeoDataFrame(
        {
            "building_id": list(range(len(polygons))),
            "use": uses or [UNNAMED_BUILDING_USE] * len(polygons),
        },
        geometry=list(polygons),
        crs=crs,
    )


def make_addresses(points, crs=constants.DEFAULT_CRS):
    """Build an address frame with one point per (address_id, x, y) triple."""
    return gpd.GeoDataFrame(
        {ADDRESS_ID_COLUMN: [address_id for address_id, _, _ in points]},
        geometry=[Point(x, y) for _, x, y in points],
        crs=crs,
    )


def build(boundaries, buildings, addresses, **kwargs):
    """Run the whole extent for a set of inputs."""
    properties = build_claim_properties(boundaries)
    dwellings = count_dwellings(properties, addresses)
    return build_insured_land_extent(properties, buildings, dwellings, **kwargs)


def test_the_claim_id_is_the_shared_contract_name():
    assert extent_module.CLAIM_ID_COLUMN == loss_contract.CLAIM_ID_COLUMN
    assert driveways_module.CLAIM_ID_COLUMN == loss_contract.CLAIM_ID_COLUMN


def test_one_building_gives_one_buffered_polygon():
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("a", 20, 20)]),
    )

    assert list(extent[CLAIM_ID_COLUMN]) == ["p0"]
    expected = BUILDING_A.buffer(INSURED_LAND_BUFFER_M).area
    assert extent[AREA_COLUMN].iloc[0] == pytest.approx(expected, abs=TOLERANCE_M2)


def test_appurtenant_structures_are_buffered_like_the_dwelling():
    # A garage in the corner of the section is buffered exactly as the house is,
    # which is the decision recorded in the module docstring.
    garage = box(5, 5, 10, 10)
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A, garage]),
        make_addresses([("a", 20, 20)]),
    )
    house_only = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("a", 20, 20)]),
    )

    assert extent[BUILDING_COUNT_COLUMN].iloc[0] == 2
    assert extent[AREA_COLUMN].iloc[0] > house_only[AREA_COLUMN].iloc[0]


def test_the_extent_never_leaves_its_own_property():
    # A building hard against the boundary would buffer onto the neighbour, and
    # that ground is not covered by this claim.
    extent = build(
        make_boundaries([SECTION_A, SECTION_B]),
        make_buildings([box(32, 15, 40, 25), BUILDING_B]),
        make_addresses([("a", 20, 20), ("b", 60, 20)]),
    )

    first = extent[extent[CLAIM_ID_COLUMN] == "p0"].geometry.iloc[0]
    assert first.within(SECTION_A.buffer(1e-6))


def test_neighbouring_extents_do_not_overlap():
    extent = build(
        make_boundaries([SECTION_A, SECTION_B]),
        make_buildings([box(32, 15, 40, 25), box(40, 15, 48, 25)]),
        make_addresses([("a", 20, 20), ("b", 60, 20)]),
    )

    first, second = extent.geometry.to_numpy()
    assert first.intersection(second).area == pytest.approx(0.0, abs=1e-6)
    assert extent[AREA_COLUMN].sum() == pytest.approx(
        extent.geometry.union_all().area, abs=TOLERANCE_M2
    )


def test_the_address_points_count_the_dwellings():
    # The count NHC multiplies both sub-caps and the excess by, so it is what
    # sets the retaining wall cap.
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("unit_1", 18, 20), ("unit_2", 22, 20)]),
    )

    assert list(extent[DWELLING_COUNT_COLUMN]) == [2]


def test_addresses_on_one_coordinate_still_count_separately():
    # LINZ places the units of a block on one point. Under the address-keyed
    # model they could not be told apart and all but one was lost; counted
    # inside a property they simply add up.
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("unit_1", 20, 20), ("unit_2", 20, 20), ("unit_3", 20, 20)]),
    )

    assert list(extent[DWELLING_COUNT_COLUMN]) == [3]


def test_a_property_with_no_address_carries_no_insured_land():
    # Cover follows a residential building, and no address point is the model
    # saying it cannot see one.
    extent = build(
        make_boundaries([SECTION_A, SECTION_B]),
        make_buildings([BUILDING_A, BUILDING_B]),
        make_addresses([("a", 20, 20)]),
    )

    assert list(extent[CLAIM_ID_COLUMN]) == ["p0"]


def test_roads_and_water_are_not_claims():
    boundaries = make_boundaries(
        [SECTION_A, SECTION_B],
        sources=["NZ Unit of Property", "NZ Primary Parcels - Road"],
    )

    properties = build_claim_properties(boundaries)

    assert list(properties[CLAIM_ID_COLUMN]) == ["p0"]


def test_titles_stacked_on_one_footprint_are_one_claim():
    # A unit-titled block carries one boundary per unit on a single footprint.
    # Left alone each would claim the whole block's insured land.
    boundaries = make_boundaries(
        [SECTION_A, SECTION_A, SECTION_A], ids=["p2", "p0", "p1"]
    )

    properties = build_claim_properties(boundaries)

    assert len(properties) == 1
    # The lowest identifier represents the footprint, so the answer does not
    # depend on the order the rows arrived in.
    assert properties[CLAIM_ID_COLUMN].iloc[0] == "p0"
    assert properties[BOUNDARY_ROW_COLUMN].iloc[0] == 3


def test_a_building_properly_straddling_a_boundary_is_split():
    # A semi detached pair captured as one outline is two buildings on two
    # properties. Half of it is well past both thresholds.
    terrace = box(30, 15, 50, 25)
    properties = build_claim_properties(make_boundaries([SECTION_A, SECTION_B]))

    parts = assign_buildings_to_properties(make_buildings([terrace]), properties)

    assert sorted(parts[CLAIM_ID_COLUMN]) == ["p0", "p1"]
    assert parts[OUTLINE_ID_COLUMN].nunique() == 1
    assert parts.geometry.area.sum() == pytest.approx(terrace.area, abs=TOLERANCE_M2)


def test_a_small_overhang_is_dropped_as_a_boundary_error():
    # 0.2 m of a 10 m wide house across the line is the outline layer and the
    # boundary layer disagreeing, not a building on two titles.
    overhanging = box(30, 15, 40.2, 25)
    properties = build_claim_properties(make_boundaries([SECTION_A, SECTION_B]))

    parts = assign_buildings_to_properties(make_buildings([overhanging]), properties)

    assert list(parts[CLAIM_ID_COLUMN]) == ["p0"]


def test_a_building_smaller_than_the_crossing_threshold_is_kept_whole():
    # The thresholds decide what counts as a crossing, not what counts as a
    # building. A 4 m2 shed wholly inside a section is still a building.
    shed = box(20, 20, 22, 22)
    properties = build_claim_properties(make_boundaries([SECTION_A]))

    parts = assign_buildings_to_properties(make_buildings([shed]), properties)

    assert list(parts[CLAIM_ID_COLUMN]) == ["p0"]
    assert parts.geometry.area.sum() == pytest.approx(shed.area, abs=1e-6)


def test_the_property_area_is_carried_for_comparison():
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("a", 20, 20)]),
    )

    assert extent[PROPERTY_AREA_COLUMN].iloc[0] == pytest.approx(
        SECTION_A.area, abs=TOLERANCE_M2
    )
    assert extent[AREA_COLUMN].iloc[0] < extent[PROPERTY_AREA_COLUMN].iloc[0]


def test_driveways_are_clipped_to_the_property_like_everything_else():
    # A driveway runs to the road, which is beyond the boundary, and the part on
    # the road reserve is not the claimant's land.
    driveway = gpd.GeoDataFrame(
        {CLAIM_ID_COLUMN: ["p0"]},
        geometry=[box(19, 0, 21, 60)],
        crs=constants.DEFAULT_CRS,
    )
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([BUILDING_A]),
        make_addresses([("a", 20, 20)]),
        driveways=driveway,
    )

    assert extent.geometry.iloc[0].within(SECTION_A.buffer(1e-6))


def test_no_buildings_gives_an_empty_extent():
    extent = build(
        make_boundaries([SECTION_A]),
        make_buildings([]),
        make_addresses([("a", 20, 20)]),
    )

    assert extent.empty
    assert CLAIM_ID_COLUMN in extent.columns


def test_mismatched_crs_is_refused():
    properties = build_claim_properties(make_boundaries([SECTION_A]))
    buildings = make_buildings([BUILDING_A], crs="EPSG:2134")
    dwellings = count_dwellings(properties, make_addresses([("a", 20, 20)]))

    with pytest.raises(ValueError, match="Reproject"):
        build_insured_land_extent(properties, buildings, dwellings)


def test_geographic_crs_is_refused():
    # Refused at the first function that touches the geometry, rather than at
    # the buffer, because an area in square degrees is just as wrong as a
    # buffer in degrees and comes first.
    with pytest.raises(ValueError, match="geographic"):
        build_claim_properties(make_boundaries([SECTION_A], crs="EPSG:4326"))


def test_boundaries_without_a_source_are_refused():
    boundaries = make_boundaries([SECTION_A]).drop(columns="source")

    with pytest.raises(ValueError, match="carry no"):
        build_claim_properties(boundaries)


def test_a_named_building_is_not_a_dwelling():
    # The use column names institutions and says nothing about a house, so the
    # filter has to rule out rather than rule in.
    buildings = make_buildings(
        [BUILDING_A, BUILDING_B], uses=[UNNAMED_BUILDING_USE, "School"]
    )

    kept = drop_non_residential_buildings(buildings)

    assert len(kept) == 1
    assert kept.geometry.iloc[0].equals(BUILDING_A)


def test_a_use_linz_adds_later_is_dropped_without_editing_the_filter():
    buildings = make_buildings([BUILDING_A, BUILDING_B], uses=["Church", None])

    kept = drop_non_residential_buildings(buildings)

    assert len(kept) == 1
    assert kept.geometry.iloc[0].equals(BUILDING_B)


def test_a_school_site_carries_no_insured_land():
    boundaries = make_boundaries([SECTION_A, SECTION_B])
    buildings = make_buildings(
        [BUILDING_A, BUILDING_B], uses=[UNNAMED_BUILDING_USE, "School"]
    )
    addresses = make_addresses([("a", 20, 20), ("b", 60, 20)])

    extent = build(boundaries, drop_non_residential_buildings(buildings), addresses)

    assert extent[CLAIM_ID_COLUMN].tolist() == ["p0"]


def test_building_outlines_without_a_use_are_refused():
    buildings = make_buildings([BUILDING_A]).drop(columns="use")

    with pytest.raises(ValueError, match="carry no"):
        drop_non_residential_buildings(buildings)


def test_a_footprint_too_large_for_a_house_is_dropped():
    # 30 x 30 m is 900 m2, well over the threshold; the 10 m squares are not.
    warehouse = box(0, 0, 30, 30)
    buildings = make_buildings([BUILDING_A, warehouse])

    kept = drop_non_residential_buildings(buildings)

    assert len(kept) == 1
    assert kept.geometry.iloc[0].equals(BUILDING_A)


def test_the_size_test_is_inclusive_of_the_threshold():
    # 25 x 20 m is exactly 500 m2, and exactly in floating point too, so this
    # tests the boundary rather than the rounding.
    assert MAX_DWELLING_FOOTPRINT_M2 == 500.0
    buildings = make_buildings([box(0, 0, 25, 20)])

    assert len(drop_non_residential_buildings(buildings)) == 1


def test_the_size_threshold_can_be_moved():
    buildings = make_buildings([box(0, 0, 30, 30)])

    assert len(drop_non_residential_buildings(buildings, max_area_m2=1000)) == 1


def test_a_geographic_crs_is_refused_by_the_building_filter():
    # Areas in square degrees would put every building under any threshold.
    buildings = make_buildings([BUILDING_A], crs="EPSG:4326")

    with pytest.raises(ValueError, match="geographic"):
        drop_non_residential_buildings(buildings)


# --- section area per address -------------------------------------------------


def test_a_lone_address_takes_its_whole_property():
    """One house on a 40 m square section is valued on all 1,600 m2."""
    properties = build_claim_properties(make_boundaries([SECTION_A]))

    areas = section_area_per_address(properties, make_addresses([("a", 20, 20)]))

    assert areas[SECTION_AREA_COLUMN].tolist() == pytest.approx([1600.0])


def test_addresses_on_one_property_each_take_its_whole_area():
    """A land value is for the property, so its area is not split among addresses.

    Splitting it three ways doubled the rate of a three-address Newtown property.
    """
    properties = build_claim_properties(make_boundaries([SECTION_A]))
    flats = make_addresses([(f"unit_{n}", 20, 20) for n in range(3)])

    areas = section_area_per_address(properties, flats)

    assert areas[SECTION_AREA_COLUMN].tolist() == pytest.approx([1600.0] * 3)


def test_each_address_takes_its_own_property():
    """Side by side sections of different sizes give different areas."""
    small = box(40, 0, 60, 40)
    properties = build_claim_properties(make_boundaries([SECTION_A, small]))
    addresses = make_addresses([("a", 20, 20), ("b", 50, 20)])

    areas = section_area_per_address(properties, addresses).set_index(ADDRESS_ID_COLUMN)

    assert areas.loc["a", SECTION_AREA_COLUMN] == pytest.approx(1600.0)
    assert areas.loc["b", SECTION_AREA_COLUMN] == pytest.approx(800.0)


def test_an_address_outside_every_property_is_absent():
    """It falls back to the assumed lot downstream, so it must not be invented."""
    properties = build_claim_properties(make_boundaries([SECTION_A]))
    addresses = make_addresses([("in", 20, 20), ("out", 500, 500)])

    areas = section_area_per_address(properties, addresses)

    assert areas[ADDRESS_ID_COLUMN].tolist() == ["in"]


def test_section_areas_refuse_a_geographic_crs():
    """In degrees the area would be a tiny fraction and every value would shrink."""
    properties = build_claim_properties(make_boundaries([SECTION_A])).to_crs(
        "EPSG:4326"
    )

    with pytest.raises(ValueError, match="geographic"):
        section_area_per_address(properties, make_addresses([("a", 174.7, -41.3)]))


def test_each_address_carries_how_many_share_its_property():
    """The land value model counts the property once, so it needs the count."""
    properties = build_claim_properties(make_boundaries([SECTION_A, SECTION_B]))
    addresses = make_addresses([("a1", 20, 20), ("a2", 20, 20), ("b", 60, 20)])

    areas = section_area_per_address(properties, addresses).set_index(ADDRESS_ID_COLUMN)

    assert areas.loc[["a1", "a2", "b"], PROPERTY_ADDRESS_COUNT_COLUMN].tolist() == [
        2,
        2,
        1,
    ]


def test_a_unit_titled_block_carries_one_rating_unit_per_stacked_title():
    """LINZ stacks one boundary per unit on a block's footprint; each is a unit."""
    boundaries = make_boundaries(
        [SECTION_A] * 3 + [SECTION_B], ids=["u1", "u2", "u3", "house"]
    )
    properties = build_claim_properties(boundaries)
    addresses = make_addresses([("flat", 20, 20), ("house", 60, 20)])

    areas = section_area_per_address(properties, addresses).set_index(ADDRESS_ID_COLUMN)

    assert areas.loc["flat", PROPERTY_RATING_UNIT_COUNT_COLUMN] == 3
    assert areas.loc["house", PROPERTY_RATING_UNIT_COUNT_COLUMN] == 1
