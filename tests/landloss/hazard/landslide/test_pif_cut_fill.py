"""Tests for the cut and fill class of each pif."""

import math

import numpy as np
import pytest
from affine import Affine

from landloss.hazard.landslide import pif_cut_fill as pcf
from landloss.hazard.landslide.instability_zones import find_pips

CELL = 1.0
TRANSFORM = Affine(CELL, 0.0, 0.0, 0.0, -CELL, 200.0)
# The natural slope, falling east at this gradient.
GRADIENT = 0.2
SIZE = (80, 120)


def _slope():
    """A plane falling east, 80 rows by 120 columns."""
    _, cols = np.indices(SIZE)
    return 100.0 - GRADIENT * (cols + 0.5)


def _classify_dem(dem):
    """Find the pips of a DEM and class them all as one pif."""
    pips = find_pips(dem, CELL)
    rows, cols = np.nonzero(pips.mask)
    return pcf.gen_pif_cut_fill(
        dem,
        TRANSFORM,
        np.ones(rows.size, dtype=int),
        rows,
        cols,
        pips.direction[rows, cols],
    )


def test_face_feet_walks_down_a_wall_to_its_foot():
    dem = _slope()
    dem[:, 60:] -= 2.0  # a 2 m wall between columns 59 and 60
    walk = pcf.face_feet(
        dem, np.array([40]), np.array([59]), np.array([1]), CELL
    )  # direction 1 is east
    assert (walk.rows[0], walk.cols[0]) == (40, 60)
    assert walk.face[40, 59]
    assert walk.face[40, 60]
    assert walk.face.sum() == 2


def test_face_feet_stops_after_the_longest_walk():
    dem = 100.0 - 5.0 * np.indices(SIZE)[1]  # far steeper than the foot slope
    walk = pcf.face_feet(dem, np.array([40]), np.array([10]), np.array([1]), CELL)
    assert walk.cols[0] - 10 == math.floor(pcf.FOOT_MAX_M / CELL)


def test_face_mask_grows_by_the_buffer():
    face = np.zeros((9, 9), dtype=bool)
    face[4, 4] = True
    grown = pcf.face_mask(face, CELL)
    assert grown.sum() == (2 * round(pcf.FACE_BUFFER_M / CELL) + 1) ** 2


def test_fit_quadratic_recovers_a_plane_and_its_scale():
    dem = _slope()
    coefficients, centre, scale = pcf.fit_quadratic(
        dem,
        TRANSFORM,
        np.array([40]),
        np.array([60]),
        radius_m=10.0,
        robust_iterations=pcf.ROBUST_ITERATIONS,
    )
    surface = pcf.eval_quadratic(
        coefficients, centre, 10.0, [60.5, 65.5], [159.5, 159.5]
    )
    assert surface == pytest.approx(dem[40, [60, 65]])
    assert scale == pytest.approx(0.0, abs=1e-9)


def test_fit_quadratic_skips_excluded_and_sparse_ground():
    dem = _slope()
    exclude = np.ones(SIZE, dtype=bool)
    coefficients, _, scale = pcf.fit_quadratic(
        dem, TRANSFORM, np.array([40]), np.array([60]), radius_m=10.0, exclude=exclude
    )
    assert coefficients is None
    assert math.isnan(scale)


def test_fit_quadratic_bisquare_ignores_a_platform():
    dem = _slope()
    dem[30:50, 55:60] += 3.0  # a raised block well off the trend
    coefficients, centre, _ = pcf.fit_quadratic(
        dem,
        TRANSFORM,
        np.array([40]),
        np.array([60]),
        radius_m=15.0,
        robust_iterations=pcf.ROBUST_ITERATIONS,
    )
    surface = pcf.eval_quadratic(coefficients, centre, 15.0, [57.5], [159.5])
    assert surface[0] == pytest.approx(_slope()[40, 57], abs=0.05)


def test_a_platform_cut_into_the_slope_is_cut():
    dem = _slope()
    # Ground lowered to the slope's level at column 66 from column 60 on.
    dem[:, 60:66] = 100.0 - GRADIENT * 66.5
    result = _classify_dem(dem)
    row = result.pifs.loc[1]
    assert row["cut_fill_class"] == pcf.CUT
    assert row["foot_residual_m"] < -1.0
    assert abs(row["crest_residual_m"]) < 0.5


def test_a_pad_filled_out_from_the_slope_is_fill():
    dem = _slope()
    # Ground raised to the slope's level at column 50 out to column 60.
    dem[:, 50:60] = 100.0 - GRADIENT * 50.5
    result = _classify_dem(dem)
    row = result.pifs.loc[1]
    assert row["cut_fill_class"] == pcf.FILL
    assert row["crest_residual_m"] > 1.0
    assert abs(row["foot_residual_m"]) < 0.5


def test_classify_sorts_the_excess_drop_and_position():
    crest = np.array([2.0, 0.0, 1.0, 0.3, 1.0, np.nan])
    foot = np.array([0.0, -2.0, -1.0, 0.0, -1.0, 0.0])
    uncertain = np.array([0.0, 0.0, 0.0, 0.0, 3.0, 0.0])
    excess, position, classes = pcf.classify(crest, foot, uncertain_m=uncertain)
    assert list(classes) == [
        pcf.FILL,
        pcf.CUT,
        pcf.CUT_AND_FILL,
        pcf.NATURAL,
        pcf.UNCERTAIN,
        pcf.UNKNOWN,
    ]
    assert excess[:3] == pytest.approx([2.0, 2.0, 2.0])
    assert position[:3] == pytest.approx([1.0, -1.0, 0.0])
