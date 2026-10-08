import numpy as np
import pytest

from landloss.vul.liquefaction.repair_rates import (
    QUARTILES,
    RepairRates,
    area_repair_cost_nzd,
    fit_per_claim_sigma,
    fit_repair_rates,
    lognormal_mean,
    lognormal_multiplier,
    modelled_quartiles,
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


def test_weights_pull_the_fit_towards_the_heavier_state():
    # Three parameters, four states that no one set of rates fits exactly.
    inundated = {1: 0.0, 2: 0.0, 3: 100.0, 4: 200.0}
    evacuated = {1: 0.0, 2: 1.0, 3: 1.0, 4: 10.0}
    target = {1: 1_000.0, 2: 1_400.0, 3: 1_500.0, 4: 3_000.0}

    def miss(rates, state):
        modelled = (
            inundated[state] * rates.inundated_nzd_per_m2
            + evacuated[state] * rates.evacuated_nzd_per_m2
            + rates.per_claim_nzd
        )
        return abs(modelled - target[state])

    even = fit_repair_rates(inundated, evacuated, target)
    heavy = fit_repair_rates(
        inundated, evacuated, target, weights={1: 1.0, 2: 1.0, 3: 1_000.0, 4: 1.0}
    )
    assert miss(heavy, 3) < miss(even, 3)


def test_equal_weights_give_the_unweighted_fit():
    inundated = {2: 0.0, 3: 180.0, 4: 230.0, 5: 300.0}
    evacuated = {2: 1.0, 3: 1.0, 4: 6.0, 5: 25.0}
    target = {2: 1_200.0, 3: 2_500.0, 4: 3_600.0, 5: 5_000.0}
    even = fit_repair_rates(inundated, evacuated, target)
    weighted = fit_repair_rates(
        inundated, evacuated, target, weights=dict.fromkeys(target, 7.0)
    )
    assert weighted.inundated_nzd_per_m2 == pytest.approx(even.inundated_nzd_per_m2)
    assert weighted.evacuated_nzd_per_m2 == pytest.approx(even.evacuated_nzd_per_m2)
    assert weighted.per_claim_nzd == pytest.approx(even.per_claim_nzd)


def test_weights_must_cover_the_target_states():
    with pytest.raises(ValueError, match="weights"):
        fit_repair_rates(
            {2: 0.0, 3: 1.0, 4: 1.0},
            {2: 1.0, 3: 1.0, 4: 2.0},
            {2: 1.0, 3: 2.0, 4: 3.0},
            weights={2: 1.0, 3: 1.0},
        )


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


def test_a_negative_spread_is_refused():
    with pytest.raises(ValueError, match="negative"):
        RepairRates(10.0, 20.0, 1_000.0, per_claim_sigma=-0.1)


def test_a_spread_needs_a_generator_to_draw_it():
    rates = RepairRates(10.0, 20.0, 1_000.0, per_claim_sigma=0.5)
    with pytest.raises(ValueError, match="generator"):
        area_repair_cost_nzd(np.zeros(3), np.zeros(3), np.ones(3, bool), rates)


def test_the_spread_varies_the_per_claim_cost_around_its_mean():
    # A mean of one: the draw spreads the claims without moving their mean,
    # which is what lets the spread be fitted after the rates.
    rates = RepairRates(10.0, 20.0, 1_000.0, per_claim_sigma=1.0)
    n = 200_000
    cost = area_repair_cost_nzd(
        np.zeros(n), np.zeros(n), np.ones(n, bool), rates, rng=np.random.default_rng(1)
    )
    assert cost.std() > 0
    assert cost.mean() == pytest.approx(1_000.0, rel=0.02)
    assert np.median(cost) < cost.mean()


def test_a_claim_with_no_spread_ignores_the_generator():
    rates = RepairRates(10.0, 20.0, 1_000.0)
    cost = area_repair_cost_nzd(
        np.array([5.0]),
        np.array([100.0]),
        np.array([True]),
        rates,
        rng=np.random.default_rng(1),
    )
    assert cost.tolist() == [5 * 20.0 + 100 * 10.0 + 1_000.0]


def test_the_multiplier_has_a_mean_of_one():
    z = np.random.default_rng(2).standard_normal(400_000)
    assert lognormal_multiplier(z, 0.8).mean() == pytest.approx(1.0, rel=0.01)


def test_with_no_spread_the_quartiles_are_those_of_the_area_cost():
    area = np.array([0.0, 100.0, 200.0, 300.0, 400.0])
    got = modelled_quartiles(area, 1_000.0, 0.0)
    assert got == pytest.approx(np.quantile(area, QUARTILES) + 1_000.0)


def test_the_fit_recovers_the_spread_that_generated_the_quartiles():
    area = {
        1: np.zeros(5),
        2: np.array([0.0, 50.0, 100.0]),
        3: np.array([200.0, 400.0]),
    }
    truth = 0.9
    target = {s: modelled_quartiles(a, 1_000.0, truth) for s, a in area.items()}
    assert fit_per_claim_sigma(area, 1_000.0, target) == pytest.approx(truth, abs=1e-3)


def test_the_spread_fit_needs_matching_states():
    with pytest.raises(ValueError, match="same states"):
        fit_per_claim_sigma(
            {1: np.zeros(2)}, 1_000.0, {1: [1.0, 2.0, 3.0], 2: [1.0, 2.0, 3.0]}
        )
