"""Tests for classing buildings as dwellings by the use the rating roll gives."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from landloss.domain import constants
from landloss.exposure.land.extent import (
    CLAIM_ID_COLUMN,
    UNNAMED_BUILDING_USE,
    build_claim_properties,
)
from landloss.exposure.land.residential_use import (
    LIFESTYLE,
    NON_RESIDENTIAL,
    PROPERTY_CATEGORY_COLUMN,
    RESIDENTIAL,
    RURAL,
    VACANT,
    VALUATION_REFERENCE_COLUMN,
    classify_property_category,
    drop_buildings_by_property_use,
    property_use,
)

SECTION_A = box(0, 0, 40, 40)
SECTION_B = box(40, 0, 80, 40)
HOUSE = box(15, 15, 25, 25)
# 30 x 30 m on section A's ground, 900 m2: over the 500 m2 footprint limit.
APARTMENT_BLOCK = box(5, 5, 35, 35)
SHOP = box(55, 15, 65, 25)


def make_boundaries(polygons, references, sources=None):
    """Build a property boundary frame in the shape the LINZ layer arrives in."""
    count = len(polygons)
    return gpd.GeoDataFrame(
        {
            "source": sources or ["NZ Unit of Property"] * count,
            "source_id": [f"p{index}" for index in range(count)],
            VALUATION_REFERENCE_COLUMN: references,
        },
        geometry=list(polygons),
        crs=constants.DEFAULT_CRS,
    )


def make_units(rows):
    """Build roll units: (valuation reference, property category) pairs."""
    return pd.DataFrame(
        list(rows), columns=[VALUATION_REFERENCE_COLUMN, PROPERTY_CATEGORY_COLUMN]
    )


def make_buildings(polygons, uses=None):
    """Build a building outline frame."""
    return gpd.GeoDataFrame(
        {"use": uses or [UNNAMED_BUILDING_USE] * len(polygons)},
        geometry=list(polygons),
        crs=constants.DEFAULT_CRS,
    )


@pytest.mark.parametrize(
    ("category", "use"),
    [
        ("RD", RESIDENTIAL),
        ("RF", RESIDENTIAL),
        ("rd ", RESIDENTIAL),
        ("RV", VACANT),
        ("LI", LIFESTYLE),
        ("PF", RURAL),
        ("DD", RURAL),
        ("CR", NON_RESIDENTIAL),
        ("IL", NON_RESIDENTIAL),
        ("OE", NON_RESIDENTIAL),
    ],
)
def test_a_category_is_read_by_its_letters(category, use):
    assert classify_property_category(pd.Series([category])).iloc[0] == use


def test_a_blank_category_has_no_use():
    uses = classify_property_category(pd.Series(["", None, " "]))

    assert uses.isna().all()


def test_a_property_takes_its_units_use_through_the_valuation_reference():
    boundaries = make_boundaries([SECTION_A, SECTION_B], ["1-1", "1-2"])
    units = make_units([("1-1", "RD"), ("1-2", "CR")])

    uses = property_use(boundaries, units)

    assert uses.to_dict() == {"p0": RESIDENTIAL, "p1": NON_RESIDENTIAL}


def test_a_stack_of_unit_titles_is_residential_if_any_unit_is():
    # Shops on the ground floor, flats above: three titles on one footprint,
    # which build_claim_properties makes one claim named after the lowest id.
    boundaries = make_boundaries(
        [SECTION_A, SECTION_A, SECTION_A], ["1-1-A", "1-1-B", "1-1-C"]
    )
    units = make_units([("1-1-A", "CR"), ("1-1-B", "RF"), ("1-1-C", "CR")])

    uses = property_use(boundaries, units)
    claims = build_claim_properties(boundaries)

    assert uses.to_dict() == {"p0": RESIDENTIAL}
    assert claims[CLAIM_ID_COLUMN].tolist() == ["p0"]


def test_a_property_not_on_the_roll_is_left_out():
    boundaries = make_boundaries([SECTION_A, SECTION_B], ["1-1", None])
    units = make_units([("9-9", "RD"), (None, "RD")])

    assert property_use(boundaries, units).empty


def test_road_parcels_take_no_use():
    boundaries = make_boundaries(
        [SECTION_A, SECTION_B],
        ["1-1", "1-2"],
        sources=["NZ Unit of Property", "NZ Primary Parcels - Road"],
    )
    units = make_units([("1-1", "RD"), ("1-2", "RD")])

    assert property_use(boundaries, units).to_dict() == {"p0": RESIDENTIAL}


def test_boundaries_without_a_valuation_reference_are_refused():
    boundaries = make_boundaries([SECTION_A], ["1-1"]).drop(
        columns=VALUATION_REFERENCE_COLUMN
    )

    with pytest.raises(ValueError, match="carry no"):
        property_use(boundaries, make_units([("1-1", "RD")]))


def filter_on(categories, buildings):
    """Run the filter over sections A and B used as ``categories`` say."""
    boundaries = make_boundaries([SECTION_A, SECTION_B], ["1-1", "1-2"])
    references = ["1-1", "1-2"]
    units = make_units(
        [(ref, cat) for ref, cat in zip(references, categories, strict=True) if cat]
    )
    properties = build_claim_properties(boundaries)
    return drop_buildings_by_property_use(
        buildings, properties, property_use(boundaries, units)
    )


def test_an_apartment_block_on_residential_land_is_a_dwelling():
    # The footprint rule drops it at 900 m2; the roll says the land is homes.
    kept = filter_on(["RF", "CR"], make_buildings([APARTMENT_BLOCK]))

    assert len(kept) == 1


def test_a_small_building_on_commercial_land_is_not_a_dwelling():
    # The footprint rule keeps a 100 m2 shop; the roll says the land is a shop.
    kept = filter_on(["RD", "CR"], make_buildings([HOUSE, SHOP]))

    assert [geometry.equals(HOUSE) for geometry in kept.geometry] == [True]


def test_a_named_building_is_dropped_even_on_residential_land():
    kept = filter_on(["RD", "RD"], make_buildings([HOUSE], uses=["School"]))

    assert kept.empty


def test_land_not_on_the_roll_falls_back_on_the_footprint():
    kept = filter_on([None, None], make_buildings([HOUSE, APARTMENT_BLOCK]))

    assert [geometry.equals(HOUSE) for geometry in kept.geometry] == [True]


def test_vacant_land_falls_back_on_the_footprint():
    # The roll is a snapshot: a house built since the revaluation stands on
    # land it still calls vacant, so a house there is kept, not dropped.
    kept = filter_on(["RV", None], make_buildings([HOUSE, APARTMENT_BLOCK]))

    assert [geometry.equals(HOUSE) for geometry in kept.geometry] == [True]


def test_buildings_and_properties_in_different_systems_are_refused():
    buildings = make_buildings([HOUSE]).to_crs("EPSG:4326")
    properties = build_claim_properties(make_boundaries([SECTION_A], ["1-1"]))

    with pytest.raises(ValueError, match="but the properties"):
        drop_buildings_by_property_use(buildings, properties, pd.Series(dtype=object))
