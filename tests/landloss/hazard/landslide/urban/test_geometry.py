"""Tests for the urban failure polygon rules: the topographic amplification and
the Kingsbury factors a polygon's fragility is scored from.
"""

import numpy as np
import pandas as pd
import pytest

from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import geometry

# An arbitrary but realistic corner in NZTM.
X0 = 1_748_000.0
Y0 = 5_425_000.0

# Every face slopes down to the south, so uphill is north (+y) and the toe is
# the southern edge.
SOUTH = 180.0


# --- Reconciling the edges -------------------------------------------------


# --- Nesting and ids ---------------------------------------------------------


# --- The fixed geometries ---------------------------------------------------


# --- Scoring -----------------------------------------------------------------


def test_the_amplification_factor_reaches_the_maximum_on_a_crest_or_a_steep_face():
    tpi = np.array([0.0, 10.0, 5.0, np.nan, 0.0])
    slope = np.array([20.0, 20.0, 20.0, 60.0, 45.0])

    factor = geometry.amplification_factor(tpi, slope)

    expected = [1.0, 1.5, 1.25, 1.5, 1.25]
    np.testing.assert_allclose(factor, expected)


def test_the_kingsbury_factors_follow_the_polygon_attributes():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0, 50.0, 10.0],
            "modification": ["cut", "fill", "natural"],
            "face_height_10m": [12.0, 12.0, 12.0],
            "geology_value": [4.0, 10.0, np.nan],
            "prior_failure": ["none", "relict", "recent"],
            "gw_depth_m": [4.0, 2.0, 0.5],
        }
    )

    factors = geometry.kingsbury_factors(polygons)

    np.testing.assert_allclose(factors["slope"], [8.0, 8.0, 0.0])
    np.testing.assert_allclose(factors["modification"], [8.0, 10.0, 0.0])
    np.testing.assert_allclose(factors["height"], [8.0, 8.0, 0.0])
    np.testing.assert_allclose(factors["landslides"], [0.0, 5.0, 10.0])
    np.testing.assert_allclose(factors["groundwater"], [0.0, 5.0, 10.0])
    rating = susceptibility.susceptibility_rating(**factors)
    assert rating[0] == pytest.approx(4 * 8 + 4 * 8 + 2 * 8 + 2 * 4)
    assert np.isnan(rating[2])


def test_an_unknown_prior_failure_is_refused():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0],
            "modification": ["cut"],
            "face_height_10m": [12.0],
            "geology_value": [4.0],
            "prior_failure": ["ancient"],
            "gw_depth_m": [4.0],
        }
    )
    with pytest.raises(ValueError, match="ancient"):
        geometry.kingsbury_factors(polygons)


# --- The step's library chain end to end -------------------------------------
