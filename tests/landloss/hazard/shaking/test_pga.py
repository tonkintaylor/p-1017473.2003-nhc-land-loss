import numpy as np
import pytest
import xarray as xr

from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.pga import (
    BETA_PGA_COV,
    beta_pga_realisation,
    beta_scale_factor,
)


def rng(realisation_id=0):
    return realisation_seed(1, realisation_id, "shaking")


def grid(values):
    return xr.DataArray(np.array(values, dtype=float), dims=("y", "x"))


# --- the multiplier ----------------------------------------------------------


def test_many_draws_average_to_one():
    # Mean one, so a realisation is neither systematically stronger nor weaker
    # than the grid it came from. The lognormal offset is what buys this.
    draws = np.array([beta_scale_factor(rng(i)) for i in range(4000)])
    assert draws.mean() == pytest.approx(1.0, abs=0.01)


def test_the_spread_of_many_draws_is_the_coefficient_of_variation():
    draws = np.array([beta_scale_factor(rng(i)) for i in range(4000)])
    assert draws.std() / draws.mean() == pytest.approx(BETA_PGA_COV, abs=0.01)


def test_a_multiplier_is_always_positive():
    draws = np.array([beta_scale_factor(rng(i), cov=0.5) for i in range(500)])
    assert np.all(draws > 0)


def test_no_spread_leaves_the_field_alone():
    assert beta_scale_factor(rng(), cov=0.0) == 1.0


def test_a_negative_spread_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        beta_scale_factor(rng(), cov=-0.1)


# --- the field ---------------------------------------------------------------


def test_the_whole_field_moves_by_one_factor():
    # The point of the module: the spatial pattern survives, because every cell
    # takes the same multiplier. Drawing per cell would destroy it.
    pga = grid([[0.1, 0.4], [0.9, 1.6]])
    scaled, factor = beta_pga_realisation(pga, rng())
    ratio = scaled.values / pga.values
    assert np.allclose(ratio, factor)


def test_the_pattern_is_preserved_in_relative_terms():
    pga = grid([[0.2, 0.8]])
    scaled, _ = beta_pga_realisation(pga, rng())
    assert scaled.values[0][1] / scaled.values[0][0] == pytest.approx(4.0)


def test_the_result_is_named_for_what_it_is():
    scaled, _ = beta_pga_realisation(grid([[0.3]]), rng())
    assert scaled.name == "pga_g"


def test_two_realisations_shake_differently():
    pga = grid([[0.5]])
    first, first_factor = beta_pga_realisation(pga, rng(0))
    second, second_factor = beta_pga_realisation(pga, rng(1))
    assert first_factor != second_factor
    assert first.values != second.values


def test_the_same_realisation_shakes_the_same():
    pga = grid([[0.5]])
    _, first = beta_pga_realisation(pga, rng(3))
    _, second = beta_pga_realisation(pga, rng(3))
    assert first == second


def test_a_cell_with_no_data_stays_missing():
    scaled, _ = beta_pga_realisation(grid([[np.nan, 0.4]]), rng())
    assert np.isnan(scaled.values[0][0])
    assert np.isfinite(scaled.values[0][1])


def test_a_negative_acceleration_is_refused():
    with pytest.raises(ValueError, match="not a ground motion"):
        beta_pga_realisation(grid([[-0.1, 0.4]]), rng())


def test_the_factor_is_the_first_and_only_draw_on_the_stream():
    # Shaking step 5 recomputes step 4's factor as beta_scale_factor on a
    # generator seeded the same way, rather than reading a file step 4 does
    # not write. This is what holds the PGA and PGV of one realisation
    # together, so beta_pga_realisation must make exactly that one draw.
    _, factor = beta_pga_realisation(grid([[0.5, 1.2]]), rng(7))
    assert factor == beta_scale_factor(rng(7))
