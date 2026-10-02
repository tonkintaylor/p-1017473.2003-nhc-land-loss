"""Tests for the address exposure population."""

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from landloss.domain import constants
from landloss.exposure import addresses as addresses_module
from landloss.exposure.addresses import (
    ADDRESS_COLUMNS,
    CURRENT_LIFECYCLE,
    LAND_FLAG,
    filter_addresses,
    get_addresses,
)


def make_addresses(
    address_ids: list[int],
    lifecycles: list[str] | None = None,
    land_flags: list[str] | None = None,
    geometries: list | None = None,
):
    """Build an address frame of current land addresses, one per address ID."""
    if lifecycles is None:
        lifecycles = [CURRENT_LIFECYCLE] * len(address_ids)
    if land_flags is None:
        land_flags = [LAND_FLAG] * len(address_ids)
    if geometries is None:
        geometries = [Point(i, i) for i, _ in enumerate(address_ids)]
    return gpd.GeoDataFrame(
        {
            "address_id": address_ids,
            "address_lifecycle": lifecycles,
            "is_land": land_flags,
            "territorial_authority": ["Wellington City"] * len(address_ids),
            "suburb_locality": ["Kelburn"] * len(address_ids),
            "town_city": ["Wellington"] * len(address_ids),
            "road_name": ["Fake Street"] * len(address_ids),
        },
        geometry=geometries,
        crs=constants.DEFAULT_CRS,
    )


# --- row filtering ------------------------------------------------------------


def test_a_non_current_address_is_dropped() -> None:
    """A retired address no longer exists on the ground, so it cannot be lost."""
    addresses = make_addresses([1, 2], lifecycles=[CURRENT_LIFECYCLE, "Retired"])

    result = filter_addresses(addresses)

    assert list(result["address_id"]) == [1]


def test_a_water_address_is_dropped() -> None:
    """A marina berth has no land to lose, so it is not part of the exposure."""
    addresses = make_addresses([1, 2], land_flags=[LAND_FLAG, "F"])

    result = filter_addresses(addresses)

    assert list(result["address_id"]) == [1]


# --- geometry -----------------------------------------------------------------


def test_empty_geometry_is_dropped() -> None:
    """An address with empty geometry cannot be sampled against a hazard."""
    addresses = make_addresses([1, 2], geometries=[Point(0, 0), Point()])

    result = filter_addresses(addresses)

    assert list(result["address_id"]) == [1]


def test_missing_geometry_is_dropped() -> None:
    """An address with no geometry at all cannot be placed, so it is removed."""
    addresses = make_addresses([1, 2], geometries=[Point(0, 0), None])

    result = filter_addresses(addresses)

    assert list(result["address_id"]) == [1]


def test_the_index_is_reset_after_dropping() -> None:
    """Dropping an address leaves a contiguous index behind."""
    addresses = make_addresses([1, 2], lifecycles=["Retired", CURRENT_LIFECYCLE])

    result = filter_addresses(addresses)

    assert list(result.index) == [0]


# --- columns ------------------------------------------------------------------


def test_only_the_declared_columns_are_kept() -> None:
    """The frames handed downstream carry the reporting columns and nothing else."""
    result = filter_addresses(make_addresses([1]))

    assert tuple(result.columns) == ADDRESS_COLUMNS


def test_a_missing_column_is_named_in_the_error() -> None:
    """A source layer that changed shape should fail loudly, naming what it lost."""
    addresses = make_addresses([1]).drop(columns=["suburb_locality"])

    with pytest.raises(ValueError, match="suburb_locality"):
        filter_addresses(addresses)


def test_the_input_is_not_modified() -> None:
    """Filtering returns a copy, leaving the caller's frame untouched."""
    addresses = make_addresses([1, 2], lifecycles=[CURRENT_LIFECYCLE, "Retired"])

    filter_addresses(addresses)

    assert len(addresses) == 2
    assert "road_name" in addresses


# --- clipping -----------------------------------------------------------------


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch):
    """Serve a fixed two-address layer in place of the LINZ read."""
    source = make_addresses([1, 2], geometries=[Point(0, 0), Point(100, 100)])
    monkeypatch.setattr(addresses_module, "get_nz_addresses", lambda **_: source.copy())
    return source


def test_without_a_clip_everything_read_is_kept(fake_source) -> None:
    """Omitting clip_to leaves the bounding box read untouched."""
    result = get_addresses()

    assert list(result["address_id"]) == [1, 2]


def test_clip_to_removes_what_falls_outside_the_boundary(fake_source) -> None:
    """A bounding box is a rectangle; clip_to cuts back to the real boundary."""
    boundary = gpd.GeoDataFrame(
        geometry=[Polygon([(-5, -5), (50, -5), (50, 50), (-5, 50)])],
        crs=constants.DEFAULT_CRS,
    )

    result = get_addresses(clip_to=boundary)

    assert list(result["address_id"]) == [1]
