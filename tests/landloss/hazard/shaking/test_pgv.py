import numpy as np
import pytest

from landloss.hazard.shaking.pgv import pgv_cm_s_from_sa_1s, pgv_m_s_from_sa_1s


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
