"""Tests for cross-section geometry and watercourse crossings."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString

from landloss.domain import constants
from landloss.hazard.cross_sections import (
    CrossSection,
    find_crossings,
    sample_elevation,
    sections_to_geodataframe,
)

CENTRE = (1760000.0, 5438000.0)


def make_section(bearing: float = 90.0, length_m: float = 1000.0) -> CrossSection:
    """Build a section for testing."""
    return CrossSection(name="Test", centre=CENTRE, bearing=bearing, length_m=length_m)


# --- geometry -----------------------------------------------------------------


def test_the_line_has_the_requested_length() -> None:
    """A section's line is as long as its length_m."""
    assert make_section(length_m=2500.0).line.length == pytest.approx(2500.0)


def test_the_line_is_centred_on_the_centre() -> None:
    """The midpoint of the line is the section's centre."""
    line = make_section().line

    midpoint = line.interpolate(0.5, normalized=True)

    assert (midpoint.x, midpoint.y) == pytest.approx(CENTRE)


def test_a_bearing_of_zero_runs_north() -> None:
    """Bearings are clockwise from grid north, so 0 degrees changes northing only."""
    start, end = make_section(bearing=0.0).line.coords

    assert end[0] - start[0] == pytest.approx(0.0, abs=1e-6)
    assert end[1] - start[1] == pytest.approx(1000.0)


def test_a_bearing_of_ninety_runs_east() -> None:
    """90 degrees changes easting only, transposing the maths convention."""
    start, end = make_section(bearing=90.0).line.coords

    assert end[0] - start[0] == pytest.approx(1000.0)
    assert end[1] - start[1] == pytest.approx(0.0, abs=1e-6)


# --- perpendicularity ---------------------------------------------------------


@pytest.mark.parametrize("bearing", [0.0, 37.0, 127.0, 305.0])
def test_the_perpendicular_is_a_right_angle_away(bearing: float) -> None:
    """A perpendicular section is 90 degrees from its parent, whatever the bearing."""
    section = make_section(bearing=bearing)

    other = section.perpendicular("Other")

    assert (other.bearing - section.bearing) % 360 == pytest.approx(90.0)


def test_the_perpendicular_actually_meets_at_right_angles() -> None:
    """The two lines cross at 90 degrees, which is the point of building them."""
    section = make_section(bearing=127.0)
    other = section.perpendicular("Other")

    (ax0, ay0), (ax1, ay1) = section.line.coords
    (bx0, by0), (bx1, by1) = other.line.coords
    dot = (ax1 - ax0) * (bx1 - bx0) + (ay1 - ay0) * (by1 - by0)

    assert dot == pytest.approx(0.0, abs=1e-6)


def test_the_perpendicular_shares_the_centre() -> None:
    """Rotating a section does not move it."""
    section = make_section(bearing=42.0)

    assert section.perpendicular("Other").centre == section.centre


def test_the_perpendicular_keeps_the_length_unless_told_otherwise() -> None:
    """Length carries over by default and is overridden when given."""
    section = make_section(length_m=3000.0)

    assert section.perpendicular("A").length_m == pytest.approx(3000.0)
    assert section.perpendicular("B", length_m=500.0).length_m == pytest.approx(500.0)


# --- sampling guards ----------------------------------------------------------


def test_a_zero_length_section_is_rejected() -> None:
    """Sampling a section of no length would divide by zero, so it raises early."""
    with pytest.raises(ValueError, match="zero length"):
        sample_elevation(make_section(length_m=0.0))


# --- crossings ----------------------------------------------------------------


@pytest.fixture
def waterways() -> gpd.GeoDataFrame:
    """Two watercourses, one crossing the test section and one clear of it."""
    return gpd.GeoDataFrame(
        {
            "name": ["Crossing Stream", "Distant Stream"],
            "wtype": ["other", "other"],
        },
        geometry=[
            # Runs north-south through the centre, so it cuts an east-west section.
            LineString([(CENTRE[0], CENTRE[1] - 500), (CENTRE[0], CENTRE[1] + 500)]),
            LineString(
                [(CENTRE[0] + 9000, CENTRE[1]), (CENTRE[0] + 9000, CENTRE[1] + 1)]
            ),
        ],
        crs=constants.DEFAULT_CRS,
    )


def test_a_crossing_is_found_at_the_right_distance(
    waterways: gpd.GeoDataFrame,
) -> None:
    """A stream through the centre is reported at the midpoint of the section."""
    result = find_crossings(make_section(), waterways)

    assert len(result) == 1
    assert result["distance_m"].iloc[0] == pytest.approx(500.0)
    assert result["name"].iloc[0] == "Crossing Stream"


def test_a_watercourse_clear_of_the_section_is_not_reported(
    waterways: gpd.GeoDataFrame,
) -> None:
    """Only watercourses the line actually meets are returned."""
    result = find_crossings(make_section(), waterways)

    assert "Distant Stream" not in set(result["name"])


def test_no_crossings_gives_an_empty_frame_with_the_right_columns() -> None:
    """An empty result is still a frame the caller can use without special casing."""
    empty = gpd.GeoDataFrame(
        {"name": [], "wtype": []}, geometry=[], crs=constants.DEFAULT_CRS
    )

    result = find_crossings(make_section(), empty)

    assert result.empty
    assert list(result.columns) == ["distance_m", "name", "wtype"]


# --- geodataframe -------------------------------------------------------------


def test_sections_become_a_geodataframe_in_nztm() -> None:
    """The locality map needs the sections as geometry, in the project CRS."""
    sections = [make_section(bearing=0.0), make_section(bearing=90.0)]

    result = sections_to_geodataframe(sections)

    assert len(result) == 2
    assert result.crs.to_string() == constants.DEFAULT_CRS
    assert list(result.columns) == [
        "name",
        "bearing",
        "length_m",
        "description",
        "geometry",
    ]
