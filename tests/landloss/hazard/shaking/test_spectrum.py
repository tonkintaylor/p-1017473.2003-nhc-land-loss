"""Tests for the TS1170.5:2025 spectrum, Sa(T), of clause 3.1.2."""

import numpy as np
import pytest

from landloss.hazard.shaking.spectrum import ts1170_sa

# Wellington's grid point (-41.3, 174.8), 1/2500, Site Class IV.
PARAMS = {"pga_g": 1.27, "sa_s_g": 2.93, "tc_s": 0.81, "td_s": 2.8}


def test_zero_period_is_pga() -> None:
    """Eq. 3.2."""
    assert ts1170_sa(0.0, **PARAMS) == pytest.approx(1.27)


def test_below_the_plateau_interpolates_from_pga() -> None:
    """Between 0 and 0.1 s, halfway in period is halfway from PGA to Sa,s."""
    assert ts1170_sa(0.05, **PARAMS) == pytest.approx((1.27 + 2.93) / 2)


def test_plateau_is_sa_s() -> None:
    """Eq. 3.3."""
    assert ts1170_sa(0.5, **PARAMS) == pytest.approx(2.93)


def test_between_the_corners_falls_as_one_over_t() -> None:
    """Eq. 3.4: Sa(1.0 s) = Sa,s * Tc when Tc < 1 s < Td."""
    assert ts1170_sa(1.0, **PARAMS) == pytest.approx(2.93 * 0.81)


def test_beyond_td_falls_faster() -> None:
    """Eq. 3.5."""
    expected = 2.93 * (0.81 / 4.0) * (2.8 / 4.0) ** 0.5
    assert ts1170_sa(4.0, **PARAMS) == pytest.approx(expected)


def test_the_spectrum_is_continuous_at_the_corners() -> None:
    """Each equation meets the next at Tc and Td."""
    for corner in (0.81, 2.8):
        below = ts1170_sa(corner - 1e-9, **PARAMS)
        above = ts1170_sa(corner + 1e-9, **PARAMS)
        assert below == pytest.approx(above)


def test_parameters_broadcast_and_carry_nan() -> None:
    """Arrays of parameters give one Sa each; a NaN parameter gives NaN."""
    result = ts1170_sa(
        1.0,
        pga_g=1.0,
        sa_s_g=np.array([2.64, 2.93, np.nan]),
        tc_s=np.array([1.1, 0.81, 0.5]),
        td_s=2.8,
    )

    assert result[:2] == pytest.approx([2.64, 2.93 * 0.81])
    assert np.isnan(result[2])


def test_negative_period_is_refused() -> None:
    """A period below zero is not a period."""
    with pytest.raises(ValueError, match="negative"):
        ts1170_sa(-0.1, **PARAMS)
