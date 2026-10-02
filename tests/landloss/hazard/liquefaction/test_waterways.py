"""Tests for the waterway classification."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from landloss.domain import constants
from landloss.hazard.liquefaction import waterways as waterways_module
from landloss.hazard.liquefaction.waterways import (
    WATERWAY_TYPES,
    classify_waterways,
    get_waterways,
)


def make_waterways(names: list[str | None], geometries: list | None = None):
    """Build a watercourse frame with one feature per name."""
    if geometries is None:
        geometries = [LineString([(0, i), (10, i)]) for i, _ in enumerate(names)]
    return gpd.GeoDataFrame(
        {"name": names}, geometry=geometries, crs=constants.DEFAULT_CRS
    )


# --- classification -----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Hutt River", "river"),
        ("Korokoro Stream", "other"),
        ("Kaiwharawhara Stream", "other"),
        ("Pauatahanui Creek", "other"),
    ],
)
def test_a_name_decides_the_waterway_type(name: str, expected: str) -> None:
    """A watercourse is a river when its name says so, and otherwise is not."""
    result = classify_waterways(make_waterways([name]))

    assert result["wtype"].iloc[0] == expected


def test_the_river_match_ignores_case() -> None:
    """A lowercase name is still recognised as a river."""
    result = classify_waterways(make_waterways(["hutt river"]))

    assert result["wtype"].iloc[0] == "river"


def test_an_unnamed_feature_is_not_a_river() -> None:
    """A null name falls through to other rather than becoming NaN."""
    result = classify_waterways(make_waterways([None]))

    assert result["wtype"].iloc[0] == "other"


def test_every_type_is_one_of_the_declared_values() -> None:
    """The wtype column never holds a value outside WATERWAY_TYPES."""
    result = classify_waterways(make_waterways(["Hutt River", "Owhiro Stream", None]))

    assert set(result["wtype"]) <= set(WATERWAY_TYPES)


# --- geometry -----------------------------------------------------------------


def test_empty_geometry_is_dropped() -> None:
    """A feature with empty geometry cannot be plotted, so it is removed."""
    waterways = make_waterways(
        ["Hutt River", "Empty Stream"],
        geometries=[LineString([(0, 0), (10, 0)]), LineString()],
    )

    result = classify_waterways(waterways)

    assert list(result["name"]) == ["Hutt River"]


def test_missing_geometry_is_dropped() -> None:
    """A feature with no geometry at all is removed."""
    waterways = make_waterways(
        ["Hutt River", "Missing Stream"],
        geometries=[LineString([(0, 0), (10, 0)]), None],
    )

    result = classify_waterways(waterways)

    assert list(result["name"]) == ["Hutt River"]


def test_the_index_is_reset_after_dropping() -> None:
    """Dropping a feature leaves a contiguous index behind."""
    waterways = make_waterways(
        ["Empty Stream", "Hutt River"],
        geometries=[LineString(), LineString([(0, 0), (10, 0)])],
    )

    result = classify_waterways(waterways)

    assert list(result.index) == [0]


def test_the_input_is_not_modified() -> None:
    """Classifying returns a copy, leaving the caller's frame untouched."""
    waterways = make_waterways(["Hutt River"])

    classify_waterways(waterways)

    assert "wtype" not in waterways


# --- clipping -----------------------------------------------------------------


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch):
    """Serve a fixed two-feature layer in place of the LINZ read."""
    source = make_waterways(
        ["Inside River", "Outside River"],
        geometries=[
            LineString([(0, 0), (10, 0)]),
            LineString([(100, 100), (110, 100)]),
        ],
    )
    monkeypatch.setattr(
        waterways_module, "get_nz_river_name_lines", lambda **_: source.copy()
    )
    return source


def test_without_a_clip_everything_read_is_kept(fake_source) -> None:
    """Omitting clip_to leaves the bounding box read untouched."""
    result = get_waterways()

    assert len(result) == 2


def test_clip_to_removes_what_falls_outside_the_boundary(fake_source) -> None:
    """A bounding box is a rectangle; clip_to cuts back to the real boundary."""
    boundary = gpd.GeoDataFrame(
        geometry=[Polygon([(-5, -5), (50, -5), (50, 50), (-5, 50)])],
        crs=constants.DEFAULT_CRS,
    )

    result = get_waterways(clip_to=boundary)

    assert list(result["name"]) == ["Inside River"]
