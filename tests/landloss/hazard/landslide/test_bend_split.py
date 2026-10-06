"""Tests for the one bends rule the pifs and the walls are cut by."""

import math

import numpy as np
import pytest
import shapely

from landloss.hazard.landslide import bend_split


def _steps(n_turns, leg_m=10.0, spacing_m=1.0):
    """Points every ``spacing_m`` along square steps east and north."""
    xy = [(0.0, 0.0)]
    for k in range(n_turns + 1):
        for _ in range(int(leg_m / spacing_m)):
            x, y = xy[-1]
            xy.append((x + spacing_m, y) if k % 2 == 0 else (x, y + spacing_m))
    return np.array(xy)


def test_a_path_within_the_bends_is_one_piece():
    xy = _steps(3)
    assert bend_split.cut_path(xy, max_bends=3, tolerance_m=2.0, min_segment_m=3.0) == [
        (0, len(xy) - 1)
    ]


def test_a_path_needing_more_bends_is_cut_and_the_pieces_meet():
    xy = _steps(7)
    ranges = bend_split.cut_path(xy, max_bends=3, tolerance_m=2.0, min_segment_m=3.0)
    assert len(ranges) == 2
    assert ranges[0][0] == 0
    assert ranges[-1][1] == len(xy) - 1
    assert ranges[0][1] == ranges[1][0]


def test_a_short_piece_joins_its_neighbour():
    xy = np.array([[0.0, 0], [10, 0], [12, 0], [30, 0]])
    merged = bend_split.merge_short_ranges(xy, [(0, 1), (1, 2), (2, 3)], 3.0)
    assert merged == [(0, 2), (2, 3)]


@pytest.mark.parametrize(("length", "n_parts"), [(40.0, 1), (60.0, 2), (120.0, 3)])
def test_the_cap_cuts_a_long_piece_into_equal_parts(length, n_parts):
    xy = np.column_stack([np.arange(0.0, length + 0.5, 1.0), np.zeros(int(length) + 1)])
    ranges = bend_split.cap_ranges(
        xy, [(0, len(xy) - 1)], max_length_m=50.0, line_of=lambda t: t[[0, -1]]
    )
    assert len(ranges) == n_parts
    sizes = [xy[b, 0] - xy[a, 0] for a, b in ranges]
    assert max(sizes) <= 50.0
    assert sum(sizes) == pytest.approx(length)


def test_no_bends_rule_cuts_by_the_cap_only():
    xy = _steps(7)
    ranges = bend_split.cut_path(
        xy, max_bends=None, tolerance_m=0.0, min_segment_m=0.0, max_length_m=50.0
    )
    assert len(ranges) == math.ceil(80.0 / 50.0)


def test_a_line_is_simplified_to_the_bends_and_loses_short_sections():
    xy = np.array([[0.0, 0], [10, 0], [10, 1], [20, 1], [20, 10]])
    line = bend_split.simplify_within(xy, tolerance_m=0.5, max_bends=1)
    assert len(line) - 2 <= 1
    kept = bend_split.drop_short_sections(xy, 3.0)
    assert (np.hypot(*np.diff(kept, axis=0).T) >= 3.0).all()


def test_a_line_keeps_the_rules_even_on_a_small_loop():
    # A triangle 8 m round whose ends meet 2.8 m apart: the line is the
    # straight one between its points furthest apart.
    xy = np.array([[0.0, 0], [1, -4], [5, -3], [3, -1]])
    line = bend_split.canonical_line(
        xy, tolerance_m=2.0, max_bends=3, min_segment_m=3.0
    )
    assert not bend_split.rule_breaks(
        shapely.LineString(line), max_bends=3, min_length_m=3.0, max_length_m=50.0
    )


def test_rule_breaks_names_each_rule():
    rules = {"max_bends": 3, "min_length_m": 3.0, "max_length_m": 50.0}
    assert bend_split.rule_breaks(shapely.LineString([(0, 0), (10, 0)]), **rules) == []
    assert bend_split.rule_breaks(shapely.LineString([(0, 0), (2, 0)]), **rules) == [
        "short"
    ]
    assert bend_split.rule_breaks(shapely.LineString([(0, 0), (60, 0)]), **rules) == [
        "long"
    ]
    zigzag = shapely.LineString([(0, 0), (5, 0), (5, 5), (10, 5), (10, 10), (15, 10)])
    assert bend_split.rule_breaks(zigzag, **rules) == ["bends"]
    multi = shapely.MultiLineString([[(0, 0), (5, 0)], [(6, 0), (9, 0)]])
    assert bend_split.rule_breaks(multi, **rules) == ["multipart"]


def test_the_total_turning_sums_the_bend_angles():
    assert bend_split.total_turn_deg(np.array([[0.0, 0], [10, 0], [10, 10]])) == (
        pytest.approx(90.0)
    )
    assert bend_split.total_turn_deg(
        np.array([[0.0, 0], [10, 0], [10, 10], [0, 10], [0, 3]])
    ) == pytest.approx(270.0)
    turning = shapely.LineString([(0, 0), (10, 0), (10, 10), (0, 10), (0, 3)])
    assert bend_split.rule_breaks(
        turning, max_bends=3, min_length_m=3.0, max_length_m=50.0, max_turn_deg=185.0
    ) == ["turning"]


def test_the_cap_cuts_at_the_fewest_bends_most_evenly():
    # A Z of 30, 30 and 30 m (90 m): one cut leaves 60 m, two cuts are needed,
    # at both bends.
    line = np.array([[0.0, 0], [30, 0], [30, 30], [60, 30]])
    stage, cuts = bend_split.cap_positions(line, 50.0, None)
    assert stage == "bends"
    assert cuts == pytest.approx([30.0, 60.0])
    # 40 + 20 m: one cut at the bend.
    stage, cuts = bend_split.cap_positions(
        np.array([[0.0, 0], [40, 0], [40, 20]]), 50.0, None
    )
    assert (stage, cuts) == ("bends", [40.0])
    # Straight, no boundaries: even.
    stage, cuts = bend_split.cap_positions(np.array([[0.0, 0], [120, 0]]), 50.0, None)
    assert stage == "even"
    assert cuts == pytest.approx([40.0, 80.0])
