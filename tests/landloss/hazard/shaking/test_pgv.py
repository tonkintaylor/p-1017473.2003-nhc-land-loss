import numpy as np
import pytest
import xarray as xr

from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.pga import beta_pga_realisation, beta_scale_factor
from landloss.hazard.shaking.pgv import (
    PGV_NAME,
    beta_pgv_realisation,
    mmi_from_pgv,
    pgv_cm_s_from_sa_1s,
    pgv_m_s_from_sa_1s,
)


def rng(realisation_id=0):
    return realisation_seed(1, realisation_id, "shaking")


def grid(values):
    return xr.DataArray(np.array(values, dtype=float), dims=("y", "x"))


def test_one_g_at_one_second_is_75_cm_s():
    # 750 mm/s per g of Sa(1.0 s), the relation the shaking status states.
    assert pgv_cm_s_from_sa_1s(1.0) == pytest.approx(75.0)


def test_the_conversion_is_linear_elementwise():
    sa = np.array([0.1, 0.5, 1.2])
    assert np.allclose(pgv_cm_s_from_sa_1s(sa), [7.5, 37.5, 90.0])


def test_pgv_in_m_s_is_the_same_relation() -> None:
    """1 g of Sa(1.0 s) is 750 mm/s, whichever unit it is written in."""
    assert pgv_m_s_from_sa_1s(1.0) == pytest.approx(0.75)
    assert pgv_m_s_from_sa_1s(2.0) == pytest.approx(pgv_cm_s_from_sa_1s(2.0) / 100)


def test_mmi_from_pgv_follows_worden_2012():
    pgv_cm_s = 10 ** np.array([0.0, 0.53, 1.0])
    expected = [
        3.78,
        3.78 + 1.47 * 0.53,
        2.89 + 3.16,
    ]
    assert mmi_from_pgv(pgv_cm_s) == pytest.approx(expected)


def test_mmi_from_pgv_handles_no_shaking_and_caps_at_ten():
    assert mmi_from_pgv([0.0, 1e4]).tolist() == [0.0, 10.0]


def test_mmi_from_pgv_refuses_negative_velocity():
    with pytest.raises(ValueError, match="negative"):
        mmi_from_pgv([-0.1, 1.0])


# --- a realisation of PGV ----------------------------------------------------


def test_pgv_takes_the_factor_pga_took_for_the_same_realisation():
    # The point of the function: one modelled earthquake's two measures move
    # by one factor, drawn once from one seed.
    _, pga_factor = beta_pga_realisation(grid([[0.5, 1.2]]), rng(3))
    _, pgv_factor = beta_pgv_realisation(grid([[0.9, 1.4]]), rng(3))
    assert pgv_factor == pga_factor
    assert pgv_factor == beta_scale_factor(rng(3))


def test_the_whole_field_moves_by_one_factor():
    pgv = grid([[0.8, 1.1], [1.4, 2.1]])
    scaled, factor = beta_pgv_realisation(pgv, rng())
    assert np.allclose(scaled.values / pgv.values, factor)


def test_the_result_is_named_for_what_it_is():
    scaled, _ = beta_pgv_realisation(grid([[1.0]]), rng())
    assert scaled.name == PGV_NAME == "pgv_m_s"


def test_two_realisations_shake_differently():
    _, first = beta_pgv_realisation(grid([[1.0]]), rng(0))
    _, second = beta_pgv_realisation(grid([[1.0]]), rng(1))
    assert first != second


def test_a_cell_with_no_data_stays_missing():
    scaled, _ = beta_pgv_realisation(grid([[np.nan, 1.2]]), rng())
    assert np.isnan(scaled.values[0][0])
    assert np.isfinite(scaled.values[0][1])


def test_a_negative_velocity_is_refused():
    with pytest.raises(ValueError, match="not a ground motion"):
        beta_pgv_realisation(grid([[-0.1, 1.2]]), rng())
