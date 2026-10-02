"""Tests for the deterministic asset ids minted in exposure."""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from landloss.domain import constants
from landloss.exposure.asset_ids import (
    CROSSING_ID_SUFFIX,
    LAND_ID_SUFFIX,
    RW_ID_SUFFIX,
    mint_asset_ids,
    sort_by_location,
)


def test_suffixes():
    assert (LAND_ID_SUFFIX, RW_ID_SUFFIX, CROSSING_ID_SUFFIX) == ("L", "RW", "X")


def test_numbering_restarts_per_claim():
    ids = mint_asset_ids(pd.Series(["a", "a", "b", "a", "b"]), RW_ID_SUFFIX)
    assert ids.tolist() == ["a-RW01", "a-RW02", "b-RW01", "a-RW03", "b-RW02"]


@pytest.mark.parametrize("claims", [[123, 123], ["123", "123"]])
def test_integer_and_string_claims_give_string_ids(claims):
    ids = mint_asset_ids(pd.Series(claims), RW_ID_SUFFIX)
    assert ids.tolist() == ["123-RW01", "123-RW02"]
    assert ids.dtype == object
    assert all(isinstance(value, str) for value in ids)


def test_same_input_gives_same_output():
    claims = pd.Series([3, 1, 3, 2, 1])
    pd.testing.assert_series_equal(
        mint_asset_ids(claims, LAND_ID_SUFFIX), mint_asset_ids(claims, LAND_ID_SUFFIX)
    )


def test_index_is_preserved():
    claims = pd.Series([7, 7, 8], index=[10, 20, 30])
    ids = mint_asset_ids(claims, CROSSING_ID_SUFFIX)
    assert ids.index.tolist() == [10, 20, 30]
    assert ids.tolist() == ["7-X01", "7-X02", "8-X01"]


def test_null_claim_raises():
    with pytest.raises(ValueError, match="no claim id"):
        mint_asset_ids(pd.Series([1, None, 2]), RW_ID_SUFFIX)


def make_frame(claims, geometries):
    return gpd.GeoDataFrame(
        {"claim_id": claims, "label": list(range(len(claims)))},
        geometry=geometries,
        crs=constants.DEFAULT_CRS,
    )


def test_sort_orders_by_claim_then_coordinates():
    frame = make_frame(
        [2, 1, 1, 1],
        [Point(0, 0), Point(5, 1), Point(1, 9), Point(1, 2)],
    )
    result = sort_by_location(frame)
    assert result["claim_id"].tolist() == [1, 1, 1, 2]
    assert [(p.x, p.y) for p in result.geometry] == [(1, 2), (1, 9), (5, 1), (0, 0)]
    assert result.index.tolist() == [0, 1, 2, 3]
    assert list(result.columns) == list(frame.columns)


def test_sort_is_independent_of_input_order():
    frame = make_frame(
        [1, 1, 2, 2],
        [Point(3, 0), Point(1, 0), Point(2, 2), Point(2, 1)],
    )
    shuffled = frame.iloc[[3, 0, 2, 1]]
    first = sort_by_location(frame)
    second = sort_by_location(shuffled)
    assert first["label"].tolist() == second["label"].tolist()
    assert mint_asset_ids(first["claim_id"], RW_ID_SUFFIX).tolist() == (
        mint_asset_ids(second["claim_id"], RW_ID_SUFFIX).tolist()
    )


def test_sort_handles_an_empty_frame():
    frame = make_frame([], [])
    result = sort_by_location(frame)
    assert result.empty
    assert list(result.columns) == list(frame.columns)


def test_sort_handles_mixed_geometry_types():
    frame = make_frame(
        [1, 1, 1],
        [box(10, 0, 12, 2), LineString([(5, 0), (5, 4)]), Point(0, 0)],
    )
    result = sort_by_location(frame)
    assert result["label"].tolist() == [2, 1, 0]
