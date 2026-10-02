"""Tests for the location-ordered ids minted in common."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, box

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants

PREFIXES = (
    constants.WALL_LINE_ID_PREFIX,
    constants.SLOPE_ID_PREFIX,
    constants.CANDIDATE_ID_PREFIX,
    constants.GROUND_ID_PREFIX,
    constants.UNIT_ID_PREFIX,
    constants.LARGE_LANDSLIDE_ID_PREFIX,
)


def make_frame(geometries, **columns):
    return gpd.GeoDataFrame(
        {"label": list(range(len(geometries))), **columns},
        geometry=geometries,
        crs=constants.DEFAULT_CRS,
    )


def test_mint_ids_numbers_from_one_over_seven_digits():
    assert mint_ids("UC", 3).tolist() == ["UC0000001", "UC0000002", "UC0000003"]


def test_mint_ids_takes_the_width():
    assert mint_ids("X", 2, width=2).tolist() == ["X01", "X02"]


def test_mint_ids_are_strings_on_a_range_index():
    ids = mint_ids(constants.SLOPE_ID_PREFIX, 2)
    assert ids.dtype == object
    assert all(isinstance(value, str) for value in ids)
    assert ids.index.tolist() == [0, 1]


def test_mint_ids_of_nothing_is_empty():
    ids = mint_ids("GM", 0)
    assert ids.empty
    assert ids.dtype == object


@pytest.mark.parametrize("prefix", PREFIXES)
def test_every_constant_prefix_mints_two_letters_and_seven_digits(prefix):
    ids = mint_ids(prefix, 1)
    assert ids.tolist() == [f"{prefix}0000001"]
    assert len(ids[0]) == 9


def test_mint_ids_refuses_a_negative_count():
    with pytest.raises(ValueError, match="cannot mint"):
        mint_ids("UC", -1)


def test_mint_ids_refuses_more_than_the_width_can_number():
    assert mint_ids("UC", 99, width=2).tolist()[-1] == "UC99"
    with pytest.raises(ValueError, match="do not fit"):
        mint_ids("UC", 100, width=2)


def test_sort_orders_by_x_then_y():
    frame = make_frame([Point(5, 1), Point(1, 9), Point(1, 2), Point(0, 0)])
    result = sort_by_point(frame)
    assert [(p.x, p.y) for p in result.geometry] == [(0, 0), (1, 2), (1, 9), (5, 1)]
    assert result.index.tolist() == [0, 1, 2, 3]
    assert list(result.columns) == list(frame.columns)


def test_a_descending_by_column_sorts_descending_before_position():
    frame = make_frame(
        [Point(0, 0), Point(1, 0), Point(2, 0), Point(3, 0)],
        scale_m=[1, 10, 3, 10],
    )
    result = sort_by_point(frame, by=("scale_m",), ascending=(False,))
    assert result["scale_m"].tolist() == [10, 10, 3, 1]
    assert result["label"].tolist() == [1, 3, 2, 0]


def test_one_flag_applies_to_every_by_column():
    frame = make_frame(
        [Point(0, 0)] * 4, scale_m=[1, 3, 1, 3], band=["b", "a", "a", "b"]
    )
    result = sort_by_point(frame, by=("scale_m", "band"), ascending=False)
    pairs = list(zip(result["scale_m"], result["band"], strict=True))
    assert pairs == [(3, "b"), (3, "a"), (1, "b"), (1, "a")]


def test_a_single_by_column_may_be_a_string():
    frame = make_frame([Point(0, 0), Point(1, 0)], scale_m=[1, 3])
    result = sort_by_point(frame, by="scale_m", ascending=False)
    assert result["scale_m"].tolist() == [3, 1]


def test_ties_keep_their_incoming_order():
    frame = make_frame([Point(1, 1)] * 3, scale_m=[3, 3, 3])
    result = sort_by_point(frame, by=("scale_m",), ascending=(False,))
    assert result["label"].tolist() == [0, 1, 2]
    reversed_frame = frame.iloc[::-1]
    result = sort_by_point(reversed_frame, by=("scale_m",))
    assert result["label"].tolist() == [2, 1, 0]


def test_sort_is_independent_of_input_order():
    frame = make_frame([Point(3, 0), Point(1, 0), Point(2, 2), Point(2, 1)])
    shuffled = frame.iloc[[3, 0, 2, 1]]
    first = sort_by_point(frame)["label"].tolist()
    second = sort_by_point(shuffled)["label"].tolist()
    assert first == second == [1, 3, 2, 0]


def test_sort_then_mint_gives_the_same_id_to_the_same_row():
    frame = make_frame([Point(3, 0), Point(1, 0), Point(2, 2)])
    shuffled = frame.iloc[[2, 0, 1]]
    first = sort_by_point(frame)
    second = sort_by_point(shuffled)
    first["id"] = mint_ids(constants.UNIT_ID_PREFIX, len(first))
    second["id"] = mint_ids(constants.UNIT_ID_PREFIX, len(second))
    by_label = first.set_index("label")["id"].to_dict()
    assert by_label == second.set_index("label")["id"].to_dict()
    assert by_label == {1: "SU0000001", 2: "SU0000002", 0: "SU0000003"}


def test_sort_handles_an_empty_frame():
    frame = make_frame([])
    result = sort_by_point(frame)
    assert result.empty
    assert list(result.columns) == list(frame.columns)


def test_sort_handles_mixed_geometry_types():
    frame = make_frame([box(10, 0, 12, 2), LineString([(5, 0), (5, 4)]), Point(0, 0)])
    assert sort_by_point(frame)["label"].tolist() == [2, 1, 0]


def test_sort_refuses_mismatched_flags():
    frame = make_frame([Point(0, 0)], scale_m=[1])
    with pytest.raises(ValueError, match="flags"):
        sort_by_point(frame, by=("scale_m",), ascending=(False, True))


def test_sort_refuses_a_geographic_system():
    frame = gpd.GeoDataFrame(
        {"label": [0]}, geometry=[Point(174.8, -41.3)], crs="EPSG:4326"
    )
    with pytest.raises(ValueError, match="geographic"):
        sort_by_point(frame)
