"""Tests for the shared lognormal fragility."""

import numpy as np
import pytest
from scipy.stats import norm

from landloss.hazard.landslide.urban import lognormal


def test_the_median_gives_one_half() -> None:
    # Act
    probability = lognormal.lognormal_failure_probability(
        np.array([0.4]), np.array([0.4]), np.array([0.6])
    )

    # Assert
    np.testing.assert_allclose(probability, [0.5])


def test_one_dispersion_above_the_median_gives_phi_of_one() -> None:
    # Arrange
    theta, beta = 0.5, 0.6

    # Act
    probability = lognormal.lognormal_failure_probability(
        np.array([theta * np.exp(beta)]), np.array([theta]), np.array([beta])
    )

    # Assert
    np.testing.assert_allclose(probability, [norm.cdf(1.0)])


def test_zero_demand_gives_zero_and_a_nan_median_gives_nan() -> None:
    # Act
    probability = lognormal.lognormal_failure_probability(
        np.array([0.0, 0.3]), np.array([0.5, np.nan]), np.array([0.6, 0.6])
    )

    # Assert
    assert probability[0] == 0.0
    assert np.isnan(probability[1])


def test_a_dispersion_not_above_zero_is_refused() -> None:
    with pytest.raises(ValueError, match="dispersion must be positive"):
        lognormal.lognormal_failure_probability(
            np.array([0.3]), np.array([0.5]), np.array([0.0])
        )


def test_the_intensity_measure_is_pga_in_g() -> None:
    assert lognormal.PGA_IM == "pga_g"
