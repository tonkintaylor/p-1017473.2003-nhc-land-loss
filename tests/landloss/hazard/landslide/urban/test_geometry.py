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


def test_the_amplification_factor_is_one_value_off_flatland_and_one_on_it():
    factor = geometry.amplification_factor(np.array([False, True, False]))

    np.testing.assert_allclose(factor, [1.3, 1.0, 1.3])
    assert geometry.amplification_factor(np.array([False]), factor=1.1)[0] == 1.1


def test_the_kingsbury_factors_follow_the_polygon_attributes():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0, 50.0, 10.0],
            "modification": ["cut", "fill", "natural"],
            "face_height_10m": [12.0, 12.0, 12.0],
            "geology_value": [4.0, 10.0, np.nan],
            "prior_failure": ["none", "relict", "recent"],
            "gw_depth_class": ["well_drained", "poorly_drained", "saturated"],
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
            "gw_depth_class": ["well_drained"],
        }
    )
    with pytest.raises(ValueError, match="ancient"):
        geometry.kingsbury_factors(polygons)


def test_an_unknown_groundwater_class_is_refused():
    polygons = pd.DataFrame(
        {
            "slope_degrees": [50.0],
            "modification": ["cut"],
            "face_height_10m": [12.0],
            "geology_value": [4.0],
            "prior_failure": ["none"],
            "gw_depth_class": ["boggy"],
        }
    )
    with pytest.raises(ValueError, match="boggy"):
        geometry.kingsbury_factors(polygons)


# --- The step's library chain end to end -------------------------------------
