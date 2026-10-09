"""Tests for the named study extents."""

import pytest
from shapely.geometry import Point

from landloss.domain import constants
from landloss.io.area_of_interest import (
    CHRISTCHURCH,
    EXTENTS,
    FULL_EXTENT,
    SMALL_WLG_PILOT,
    WGS84,
    AreaOfInterest,
    extent_suffix,
    get_area_of_interest,
    get_study_area,
    get_study_areas,
    study_area_bbox,
)

# The corners the pilot extent was defined from, as (latitude, longitude).
NORTH_WEST = (-41.309796, 174.772318)
SOUTH_EAST = (-41.32486560367306, 174.80616774743507)


def test_wgs84_bbox_round_trips_the_defined_corners() -> None:
    """The extent in WGS84 is exactly what it was defined from."""
    minx, miny, maxx, maxy = SMALL_WLG_PILOT.bbox(WGS84)

    assert minx == pytest.approx(NORTH_WEST[1])
    assert maxy == pytest.approx(NORTH_WEST[0])
    assert maxx == pytest.approx(SOUTH_EAST[1])
    assert miny == pytest.approx(SOUTH_EAST[0])


def test_defaults_to_nztm() -> None:
    """Asking for the bbox without a CRS gives NZTM, as the model works in it."""
    minx, miny, maxx, maxy = SMALL_WLG_PILOT.bbox()

    # Central Wellington sits near 1_749_000E 5_424_000N in NZTM.
    assert 1_740_000 < minx < 1_760_000
    assert 5_415_000 < miny < 5_430_000
    assert maxx > minx
    assert maxy > miny


def test_the_pilot_is_a_few_square_kilometres() -> None:
    """The pilot is small enough to iterate on, which is its whole purpose."""
    area_km2 = SMALL_WLG_PILOT.polygon().area / 1e6

    assert 3 < area_km2 < 7


def test_bounds_are_ordered_min_then_max() -> None:
    """The bbox follows the (minx, miny, maxx, maxy) order readers expect."""
    minx, miny, maxx, maxy = SMALL_WLG_PILOT.bbox()

    assert minx < maxx
    assert miny < maxy


def test_geoseries_carries_the_requested_crs() -> None:
    """The GeoSeries is tagged with the CRS, so geopandas can transform it."""
    series = SMALL_WLG_PILOT.to_geoseries(constants.DEFAULT_CRS)

    assert series.crs.to_string() == constants.DEFAULT_CRS
    assert len(series) == 1


def test_polygon_matches_the_bbox() -> None:
    """The polygon and the bbox describe the same extent."""
    polygon_bounds = SMALL_WLG_PILOT.polygon().bounds

    assert polygon_bounds == pytest.approx(SMALL_WLG_PILOT.bbox())


def test_an_area_of_interest_is_immutable() -> None:
    """Extents are constants; accidentally reassigning one should fail."""
    aoi = AreaOfInterest(name="test", west=1.0, south=2.0, east=3.0, north=4.0)

    with pytest.raises(AttributeError):
        aoi.west = 99.0  # type: ignore[misc]


def test_the_pilot_is_named() -> None:
    """The name is used in outputs and file names, so it must not be empty."""
    assert SMALL_WLG_PILOT.name


# --- packaged study area boundaries -------------------------------------------


def test_the_four_territorial_authorities_are_present() -> None:
    """The study area is exactly the four authorities agreed at kick-off."""
    study_areas = get_study_areas()

    assert sorted(study_areas["name"]) == [
        "Lower Hutt City",
        "Porirua City",
        "Upper Hutt City",
        "Wellington City",
    ]


def test_each_authority_is_a_separate_row() -> None:
    """The boundaries are kept separate rather than dissolved into one extent."""
    study_areas = get_study_areas()

    assert len(study_areas) == 4
    assert study_areas["ta_code"].is_unique


def test_the_boundaries_default_to_nztm() -> None:
    """The packaged asset comes back in the CRS the model works in."""
    assert get_study_areas().crs.to_string() == constants.DEFAULT_CRS


def test_the_boundaries_reproject() -> None:
    """A caller can ask for another CRS without losing rows."""
    reprojected = get_study_areas("EPSG:4326")

    assert reprojected.crs.to_string() == "EPSG:4326"
    assert len(reprojected) == 4


def test_geometries_are_valid_and_non_empty() -> None:
    """A boundary that failed to write would otherwise fail silently later."""
    study_areas = get_study_areas()

    assert study_areas.geometry.is_valid.all()
    assert not study_areas.geometry.is_empty.any()


def test_land_areas_are_plausible() -> None:
    """Guards against the wrong authorities being picked up by a code change."""
    areas = get_study_areas().set_index("name")["land_area_sq_km"]

    assert areas["Porirua City"] == pytest.approx(174.8, abs=1)
    assert areas["Wellington City"] == pytest.approx(289.9, abs=1)
    assert areas["Upper Hutt City"] == pytest.approx(539.9, abs=1)
    assert areas["Lower Hutt City"] == pytest.approx(376.4, abs=1)


def test_load_a_single_authority_by_name() -> None:
    """One authority can be pulled out for per-territory reporting."""
    wellington = get_study_area("Wellington City")

    assert len(wellington) == 1
    assert wellington["ta_code"].iloc[0] == "047"


def test_a_single_authority_is_matched_case_insensitively() -> None:
    """Callers should not have to match the source's capitalisation."""
    assert get_study_area("wellington city")["name"].iloc[0] == "Wellington City"


def test_an_unknown_authority_lists_the_available_ones() -> None:
    """A typo should say what is available rather than return nothing."""
    with pytest.raises(KeyError, match="Wellington City"):
        get_study_area("Kapiti Coast District")


def test_the_study_area_bbox_covers_every_authority() -> None:
    """The combined bbox contains each individual boundary."""
    minx, miny, maxx, maxy = study_area_bbox()
    study_areas = get_study_areas()

    for bounds in study_areas.geometry.bounds.itertuples():
        assert bounds.minx >= minx
        assert bounds.miny >= miny
        assert bounds.maxx <= maxx
        assert bounds.maxy <= maxy


def test_the_pilot_sits_inside_wellington_city() -> None:
    """The pilot extent should be within the study area it previews."""
    wellington = get_study_area("Wellington City").geometry.iloc[0]

    assert wellington.intersects(SMALL_WLG_PILOT.polygon())


# --- Christchurch -------------------------------------------------------------

# The corners the Christchurch extent was defined from, as (longitude, latitude).
CHCH_NORTH_WEST = (172.22727348821033, -43.28668860936209)
CHCH_SOUTH_EAST = (172.92244713169507, -43.669039807974436)


def test_the_christchurch_bbox_round_trips_the_defined_corners() -> None:
    """The extent in WGS84 is exactly what it was defined from."""
    minx, miny, maxx, maxy = CHRISTCHURCH.bbox(WGS84)

    assert minx == pytest.approx(CHCH_NORTH_WEST[0])
    assert maxy == pytest.approx(CHCH_NORTH_WEST[1])
    assert maxx == pytest.approx(CHCH_SOUTH_EAST[0])
    assert miny == pytest.approx(CHCH_SOUTH_EAST[1])


def test_christchurch_city_is_inside_the_extent() -> None:
    """The extent exists to hold the Canterbury earthquake sequence evidence."""
    cathedral_square = Point(172.6376, -43.5309)

    assert CHRISTCHURCH.to_geoseries(WGS84).iloc[0].contains(cathedral_square)


def test_the_christchurch_extent_is_a_city_and_its_plains() -> None:
    """Roughly 56 by 42 km: the city plus the flat land around it, not the region."""
    area_km2 = CHRISTCHURCH.polygon().area / 1e6

    assert 2_000 < area_km2 < 3_000


def test_the_full_extent_keeps_plain_file_names() -> None:
    """A full study build writes the names it always has, with no suffix."""
    assert extent_suffix(FULL_EXTENT) == ""
    assert get_area_of_interest(FULL_EXTENT) is None


def test_the_wellington_pilot_keeps_its_legacy_suffix() -> None:
    """Pilot builds made under the old boolean setting are still found."""
    assert extent_suffix("wlg-pilot") == "-pilot"
    assert get_area_of_interest("wlg-pilot") is SMALL_WLG_PILOT


def test_every_extent_has_its_own_suffix() -> None:
    """Two extents never share output names, so neither overwrites the other."""
    suffixes = [extent_suffix(name) for name in [FULL_EXTENT, *EXTENTS]]
    assert len(set(suffixes)) == len(suffixes)


def test_an_unknown_extent_is_refused() -> None:
    """A typo in a run setting fails loudly rather than naming a new build."""
    with pytest.raises(KeyError, match="not a known extent"):
        extent_suffix("wlg-pliot")


def test_the_porirua_pilot_sits_inside_porirua_city() -> None:
    """The Porirua pilot box is over Porirua City, so it tests the non-WCC path."""
    porirua = get_study_area("Porirua City").geometry.iloc[0]
    pilot = get_area_of_interest("porirua-pilot")

    assert extent_suffix("porirua-pilot") == "-porirua-pilot"
    assert porirua.contains(pilot.polygon(constants.DEFAULT_CRS).centroid)


def test_the_porirua_box_covers_porirua_city() -> None:
    """The Porirua extent holds the whole of the Porirua City boundary."""
    porirua = get_study_area("Porirua City").geometry.iloc[0]
    extent = get_area_of_interest("porirua").polygon(constants.DEFAULT_CRS)

    assert extent.contains(porirua)


def test_the_upper_hutt_box_covers_upper_hutt_city() -> None:
    """The Upper Hutt extent holds the whole of the Upper Hutt City boundary."""
    upper_hutt = get_study_area("Upper Hutt City").geometry.iloc[0]
    extent = get_area_of_interest("upper-hutt").polygon(constants.DEFAULT_CRS)

    assert extent_suffix("upper-hutt") == "-upper-hutt"
    assert extent.contains(upper_hutt)
