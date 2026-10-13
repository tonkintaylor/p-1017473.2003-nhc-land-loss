"""Tests for the wall line along a pif's downhill outline and the pips it holds."""

import numpy as np
import shapely

from landloss.hazard.landslide import wall_lines

# Indices into DIRECTIONS: rows grow southward, so 2 is south, 1 east, 0 north.
NORTH, EAST, SOUTH, SOUTH_EAST = 0, 1, 2, 5
MAX_BENDS = 3
MIN_SEGMENT_M = 3.0
MAX_BEND_DEG = 100.0
MAX_TOTAL_TURN_DEG = 185.0
FALLBACK = shapely.LineString([(0.0, 100.0), (10.0, 100.0)])


def _block(x0: int, x1: int, y0: int, y1: int, direction: int):
    """Pips (cell centres) over the cells x0..x1 by y0..y1, all falling one way."""
    xy = np.array(
        [(x + 0.5, y + 0.5) for y in range(y0, y1) for x in range(x0, x1)], dtype=float
    )
    return xy, np.full(len(xy), direction)


def _join(*blocks):
    return np.vstack([b[0] for b in blocks]), np.concatenate([b[1] for b in blocks])


def _assert_rules(line: shapely.LineString) -> None:
    vertices = shapely.get_coordinates(line)
    assert len(vertices) - 2 <= MAX_BENDS
    if len(vertices) > 2:
        assert wall_lines.section_lengths(vertices).min() >= MIN_SEGMENT_M - 1e-6
        turns = wall_lines.turns_deg(vertices)
        assert turns.max() <= MAX_BEND_DEG + 1e-6
        assert turns.sum() <= MAX_TOTAL_TURN_DEG + 1e-6


def test_straight_band_gives_a_straight_line_on_its_downhill_edge(settings):
    pips, direction = _block(0, 40, 0, 5, SOUTH)
    line, method, _ = wall_lines.wall_line(pips, direction, FALLBACK, settings)
    vertices = shapely.get_coordinates(line)
    assert method == wall_lines.METHOD_OUTLINE
    assert len(vertices) == 2
    # The downhill edge of the cells the pips fall to is y = -1.
    assert np.all(np.abs(vertices[:, 1] + 1.0) <= 0.5)
    assert line.length >= 38.0
    _assert_rules(line)


def test_l_shaped_band_gives_one_bend(settings):
    pips, direction = _join(
        _block(0, 20, 0, 5, SOUTH),
        _block(20, 25, 0, 5, SOUTH_EAST),
        _block(20, 25, 5, 20, EAST),
    )
    line, method, _ = wall_lines.wall_line(pips, direction, FALLBACK, settings)
    vertices = shapely.get_coordinates(line)
    assert method == wall_lines.METHOD_OUTLINE
    assert len(vertices) == 3
    assert np.allclose(vertices[1], (26.0, -1.0), atol=1.0)
    _assert_rules(line)


def test_lobe_falling_away_from_the_line_splits_off_a_no_wall_piece(settings):
    wall = _block(0, 30, 0, 4, SOUTH)
    lobe = _block(0, 15, 4, 8, NORTH)
    pips, direction = _join(wall, lobe)
    line, _, _ = wall_lines.wall_line(pips, direction, FALLBACK, settings)
    label, how = wall_lines.wall_pieces(pips, direction, line, settings)
    assert label.max() == 1
    assert np.array_equal(
        np.flatnonzero(label == 1), np.arange(len(wall[0]), len(pips))
    )
    assert (how[label == 1] == wall_lines.HOW_LEFT_OVER).all()
    assert (how[label == 0] == wall_lines.HOW_CONE).all()


def test_small_leftover_goes_back_to_the_wall_piece(settings):
    wall = _block(0, 30, 0, 4, SOUTH)
    lobe = _block(0, 5, 4, 5, NORTH)  # five pips: not more than the minimum
    pips, direction = _join(wall, lobe)
    line, _, _ = wall_lines.wall_line(pips, direction, FALLBACK, settings)
    label, how = wall_lines.wall_pieces(pips, direction, line, settings)
    assert label.max() == 0
    assert (how[len(wall[0]) :] == wall_lines.HOW_MERGED_BACK).all()


def test_pif_with_no_downhill_run_uses_the_fallback(settings):
    pips, direction = _block(0, 1, 0, 1, SOUTH)
    line, method, _ = wall_lines.wall_line(pips, direction, FALLBACK, settings)
    assert method == wall_lines.METHOD_FALLBACK
    assert line.equals_exact(FALLBACK, 0)
