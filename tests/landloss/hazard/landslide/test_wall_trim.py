"""Tests for aligning evacuated polygons with their wall's line."""

import numpy as np
import pytest
import shapely
from shapely import LineString, MultiPolygon, Point, Polygon, box

from landloss.hazard.landslide import wall_trim
from landloss.hazard.landslide.wall_trim import WallTrimSettings, align_unit

SETTINGS = WallTrimSettings(
    beside_m=2.0,
    extend_pad_m=5.0,
    sliver_m2=0.5,
    sample_m=0.25,
    close_m=0.5,
    gap_m=0.02,
    ray_m=20.0,
    overlap_m=0.05,
    oblique_factor=2**0.5,
    oblique_pad_m=0.25,
)
SOUTH = np.array([0.0, -1.0])


def _line(x0: float, x1: float, y: float = 0.0) -> LineString:
    return LineString([(x0, y), (x1, y)])


def test_line_across_polygon_removes_downhill_side() -> None:
    polygon = box(0, 0, 10, 6)
    (result,) = align_unit([polygon], _line(-1, 11, 3), SOUTH, SETTINGS)
    assert result.how == "line cuts"
    assert result.removed.area == pytest.approx(30.0)
    assert result.kept.area == pytest.approx(30.0)
    assert result.aligned.bounds[1] == pytest.approx(3.0)
    assert result.area_removed_m2 == pytest.approx(30.0)


def test_short_line_is_projected_and_still_cuts() -> None:
    polygon = box(0, 0, 10, 6)
    (result,) = align_unit([polygon], _line(2, 8, 3), SOUTH, SETTINGS)
    assert result.how == "projected"
    assert result.removed.area == pytest.approx(30.0)
    assert result.aligned.bounds[1] == pytest.approx(3.0)


def test_polygon_wholly_uphill_and_touching_is_untouched() -> None:
    polygon = box(0, 3, 10, 6)
    (result,) = align_unit([polygon], _line(0, 10, 3), SOUTH, SETTINGS)
    assert result.how == "nothing in front"
    assert result.removed.is_empty
    assert result.aligned.symmetric_difference(polygon).area == pytest.approx(0.0)


def test_polygon_far_from_line_is_left_whole() -> None:
    polygon = box(0, 10, 10, 16)
    (result,) = align_unit([polygon], _line(-1, 11, 3), SOUTH, SETTINGS)
    assert result.how == "beyond wall"
    assert result.removed.is_empty
    assert result.fill.is_empty
    assert result.aligned.symmetric_difference(polygon).area == pytest.approx(0.0)


def _wavy() -> Polygon:
    """Anchored (0.3 m off the line) at both ends, 1 m off in the middle."""
    return Polygon(
        [(0, 0.3), (5, 0.3), (5, 1), (15, 1), (15, 0.3), (20, 0.3), (20, 6), (0, 6)]
    )


def test_wavy_edge_is_filled_up_to_the_line_and_never_past_it() -> None:
    (result,) = align_unit([_wavy()], _line(0, 20), SOUTH, SETTINGS)
    assert result.how == "nothing in front"
    assert result.aligned.bounds[1] == pytest.approx(0.0, abs=1e-9)
    assert result.aligned.contains(Point(10, 0.5))
    assert result.aligned.contains(Point(2.5, 0.1))
    assert result.fill.area > 0.0
    assert result.fill.bounds[1] >= -1e-9


def test_end_section_open_to_the_line_end_is_not_filled() -> None:
    polygon = box(5, 0.3, 15, 6)
    (result,) = align_unit([polygon], _line(0, 20), SOUTH, SETTINGS)
    assert result.fill.area > 0.0
    assert result.aligned.bounds[0] > 4.0
    assert result.aligned.bounds[2] < 16.0
    assert not result.aligned.contains(Point(2, 0.2))
    assert not result.aligned.contains(Point(18, 0.2))


def test_notch_is_not_crossed() -> None:
    polygon = Polygon(
        [(0, 0.3), (8, 0.3), (8, 10), (12, 10), (12, 0.3), (20, 0.3), (20, 16), (0, 16)]
    )
    (result,) = align_unit([polygon], _line(0, 20), SOUTH, SETTINGS)
    assert result.aligned.bounds[1] == pytest.approx(0.0, abs=1e-9)
    assert not result.aligned.contains(Point(10, 5))
    notch = shapely.intersection(result.fill, box(8, 0, 12, 12))
    assert notch.bounds[3] < 4.0


def test_side_by_side_polygons_both_anchor_the_fill_between_them() -> None:
    left = box(0, 0.3, 9, 6)
    right = box(11, 0.3, 20, 6)
    a, b = align_unit([left, right], _line(0, 20), SOUTH, SETTINGS)
    assert a.fill.area > 0.0
    assert b.fill.area > 0.0
    joined = shapely.union_all([a.aligned, b.aligned])
    assert joined.contains(Point(10, 0.2))
    assert joined.bounds[1] == pytest.approx(0.0, abs=1e-9)


def test_degenerate_inputs() -> None:
    polygon = box(0, 0, 10, 6)
    empty = Polygon()
    results = align_unit(
        [empty, polygon], LineString([(3, 3), (3, 3)]), SOUTH, SETTINGS
    )
    assert [r.how for r in results] == ["empty", "no line"]
    assert results[0].aligned.is_empty
    assert results[1].aligned.symmetric_difference(polygon).area == pytest.approx(0.0)
    assert align_unit([polygon], LineString(), SOUTH, SETTINGS)[0].how == "no line"
    assert align_unit([], _line(0, 1), SOUTH, SETTINGS) == []


def test_multipolygon_is_trimmed_part_by_part() -> None:
    polygon = MultiPolygon([box(0, 0, 4, 6), box(6, 0, 10, 6)])
    (result,) = align_unit([polygon], _line(-1, 11, 3), SOUTH, SETTINGS)
    assert result.removed.area == pytest.approx(24.0)
    assert result.kept.area == pytest.approx(24.0)


def test_mean_fall_is_a_unit_vector() -> None:
    steps = [(0.0, 1.0), (1.0, 0.0), (0.0, -1.0)]
    fall = wall_trim.mean_fall([1, 2, 2], steps)
    assert np.hypot(*fall) == pytest.approx(1.0)
    assert fall[1] < 0
