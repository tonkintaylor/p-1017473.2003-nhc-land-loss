import numpy as np
import pytest

from landloss.hazard.landslide.models.hancox_1997 import relationships as h


def test_digitised_figure_19_refits_to_the_published_regression():
    # Section 3.3: log10 A = 0.96 (+/- 0.16) M - 3.7 (+/- 1.1), SE of the
    # estimate 0.43, coefficient of determination 68%.
    points = h.get_figure_19()
    used = points[points["in_regression"]]
    m, log_a = used["magnitude"].to_numpy(), np.log10(used["area_km2"].to_numpy())
    design = np.c_[m, np.ones_like(m)]
    (slope, intercept), *_ = np.linalg.lstsq(design, log_a, rcond=None)
    residuals = log_a - design @ (slope, intercept)
    se = np.sqrt(residuals @ residuals / (len(m) - 2))
    r2 = 1 - residuals @ residuals / ((log_a - log_a.mean()) @ (log_a - log_a.mean()))
    assert len(points) == 22
    assert slope == pytest.approx(h.AREA_SLOPE, abs=0.16)
    assert intercept == pytest.approx(h.AREA_INTERCEPT, abs=1.1)
    assert se == pytest.approx(h.AREA_LOG10_SE, abs=0.05)
    assert r2 == pytest.approx(0.68, abs=0.05)


def test_area_affected_at_the_report_quoted_magnitudes():
    # The mean line, not the upper bound the report quotes in its text
    # ("about 100 km2 at M 5 ... 20,000 km2 at M 8.2").
    assert h.area_affected_km2(5.0) == pytest.approx(12.6, rel=0.01)
    assert h.area_affected_km2(8.2) == pytest.approx(14_860, rel=0.01)
    lo, hi = h.area_affected_km2(8.1, n_se=-1), h.area_affected_km2(8.1, n_se=1)
    assert lo < h.area_affected_km2(8.1) < hi
    assert hi / lo == pytest.approx(10 ** (2 * h.AREA_LOG10_SE))


def test_the_inverse_round_trips():
    # To within the rounding of the published inverse's 1.04 and 3.85.
    m = np.array([5.0, 6.5, 8.1])
    assert h.mw_from_area_affected(h.area_affected_km2(m)) == pytest.approx(m, abs=0.02)


def test_max_distance_follows_the_report_text():
    # Section 3.4: about 10 km at M 5, 30 km at M 6, 100 km at M 7 and almost
    # 300 km at M 8.2 for the smallest slides.
    d = h.max_distance_km(np.array([5.0, 6.0, 7.0, 8.2]))
    assert d == pytest.approx([10, 29, 84, 304], rel=0.03)


def test_larger_landslides_need_larger_earthquakes_and_stay_closer():
    assert h.max_distance_km(6.8, "very_large") == 0.0
    assert h.max_distance_km(7.0, "very_large") > 0.0
    assert h.max_distance_km(8.1, "extremely_large") == 100.0
    # Under the forward scenario every class is possible at 25 km.
    for size_class in h.SIZE_CLASSES:
        assert h.max_distance_km(8.1, size_class) > 25.0


def test_unknown_size_class_is_refused():
    with pytest.raises(ValueError, match="size_class"):
        h.max_distance_km(7.0, "huge")


def test_slope_shares():
    assert sum(h.SLOPE_SHARES_PRINTED.values()) == pytest.approx(1.09)
    assert sum(h.SLOPE_SHARES.values()) == pytest.approx(1.0)
    assert tuple(h.SLOPE_SHARES) == h.SLOPE_CLASSES


def test_slope_class_edges():
    classes = h.slope_class([0, 15, 16, 25, 26, 35, 36, 45, 46, 80])
    assert classes.tolist() == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
