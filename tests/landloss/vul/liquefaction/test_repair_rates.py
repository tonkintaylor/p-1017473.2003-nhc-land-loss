import numpy as np
import pytest

from landloss.vul.liquefaction.repair_rates import (
    RepairRates,
    area_repair_cost_nzd,
    fit_repair_rates,
    lognormal_mean,
)


def test_a_lognormal_with_no_spread_has_its_median_as_its_mean():
    assert lognormal_mean(500.0, 500.0) == pytest.approx(500.0)


def test_a_right_skewed_spread_puts_the_mean_above_the_median():
    # The 85th at twice the median: sigma = ln 2 / 1.036, mean = median x 1.25.
    assert lognormal_mean(4_000.0, 8_000.0) == pytest.approx(5_002.45, rel=1e-4)


@pytest.mark.parametrize(("p50", "p85"), [(0.0, 100.0), (500.0, 200.0)])
def test_an_impossible_pair_of_percentiles_is_refused(p50, p85):
    with pytest.raises(ValueError, match="p50"):
        lognormal_mean(p50, p85)


def test_the_fit_recovers_rates_that_generated_the_targets():
    inundated = {2: 0.0, 3: 180.0, 4: 230.0, 5: 300.0}
    evacuated = {2: 1.0, 3: 1.0, 4: 6.0, 5: 25.0}
    truth = RepairRates(10.0, 20.0, 1_000.0)
    target = {s: inundated[s] * 10.0 + evacuated[s] * 20.0 + 1_000.0 for s in inundated}
    fitted = fit_repair_rates(inundated, evacuated, target)
    assert fitted.inundated_nzd_per_m2 == pytest.approx(truth.inundated_nzd_per_m2)
    assert fitted.evacuated_nzd_per_m2 == pytest.approx(truth.evacuated_nzd_per_m2)
    assert fitted.per_claim_nzd == pytest.approx(truth.per_claim_nzd)


def test_no_rate_is_fitted_negative():
    # Unconstrained, these would want a negative evacuated rate: the state with
    # the most evacuated land costs the least.
    inundated = {2: 100.0, 3: 200.0, 4: 300.0}
    evacuated = {2: 1.0, 3: 50.0, 4: 100.0}
    target = {2: 3_000.0, 3: 2_000.0, 4: 2_500.0}
    fitted = fit_repair_rates(inundated, evacuated, target)
    assert fitted.inundated_nzd_per_m2 >= 0
    assert fitted.evacuated_nzd_per_m2 >= 0
    assert fitted.per_claim_nzd >= 0


def test_mismatched_states_are_refused():
    with pytest.raises(ValueError, match="same states"):
        fit_repair_rates({2: 0.0, 3: 1.0, 4: 1.0}, {2: 1.0, 3: 1.0}, {2: 1, 3: 2, 4: 3})


def test_three_parameters_need_three_states():
    with pytest.raises(ValueError, match="at least 3"):
        fit_repair_rates({2: 0.0, 3: 1.0}, {2: 1.0, 3: 1.0}, {2: 1.0, 3: 2.0})


def test_a_negative_rate_is_refused():
    with pytest.raises(ValueError, match="negative"):
        RepairRates(-1.0, 20.0, 1_000.0)


def test_the_cost_adds_both_areas_and_the_fixed_cost_on_a_claim_only():
    rates = RepairRates(10.0, 20.0, 1_000.0)
    cost = area_repair_cost_nzd(
        np.array([5.0, 5.0]), np.array([100.0, 100.0]), np.array([True, False]), rates
    )
    assert cost.tolist() == [5 * 20.0 + 100 * 10.0 + 1_000.0, 0.0]


def test_the_no_sva_multiplier_raises_only_the_inundated_part():
    rates = RepairRates(10.0, 20.0, 1_000.0)
    args = (np.array([5.0]), np.array([100.0]), np.array([True]), rates)
    plain = area_repair_cost_nzd(*args)
    no_sva = area_repair_cost_nzd(*args, inundated_multiplier=1.5)
    assert no_sva[0] - plain[0] == pytest.approx(0.5 * 100 * 10.0)
