import numpy as np
import pytest

from landloss.vul.liquefaction.costs import (
    COST_YEAR,
    PERCENTILE_COLUMNS,
    ld_cost_nzd,
    load_ld_costs,
)


def test_the_packaged_file_carries_all_six_states():
    costs = load_ld_costs()
    assert sorted(costs.index) == [1, 2, 3, 4, 5, 6]


def test_cost_rises_with_severity():
    costs = load_ld_costs()
    median = costs[PERCENTILE_COLUMNS[50]].to_numpy()
    assert np.all(np.diff(median) >= 0)


def test_the_severe_states_share_one_estimate():
    # States 5 and 6 both read the source band "5 or 6", so they are one
    # estimate wearing two hats rather than two independent ones.
    costs = load_ld_costs()
    for column in PERCENTILE_COLUMNS.values():
        assert costs.loc[5, column] == costs.loc[6, column]


def test_a_state_maps_to_its_own_cost():
    costs = load_ld_costs()
    got = ld_cost_nzd(np.array([1, 3, 6]), percentile=50)
    expected = costs.loc[[1, 3, 6], PERCENTILE_COLUMNS[50]].to_numpy()
    assert np.array_equal(got, expected)


def test_a_higher_percentile_costs_more():
    states = np.array([2, 3, 4, 5])
    low = ld_cost_nzd(states, percentile=15)
    high = ld_cost_nzd(states, percentile=85)
    assert np.all(high > low)


def test_the_eighty_fifth_is_several_times_the_median():
    # The reason the percentile is a run-level scenario rather than a detail:
    # it moves the liquefaction component more than most modelling choices.
    states = np.array([2, 3, 4, 5, 6])
    ratio = ld_cost_nzd(states, percentile=85) / ld_cost_nzd(states, percentile=50)
    assert np.all(ratio >= 2.0)


def test_an_unknown_state_costs_nothing_known():
    got = ld_cost_nzd(np.array([np.nan, 3.0]), percentile=50)
    assert np.isnan(got[0])
    assert np.isfinite(got[1])


def test_a_percentile_the_file_does_not_carry_is_refused():
    with pytest.raises(ValueError, match="not a distribution"):
        ld_cost_nzd(np.array([3]), percentile=90)


def test_a_state_outside_the_scale_is_refused():
    with pytest.raises(ValueError, match="the file carries 1 to 6"):
        ld_cost_nzd(np.array([9]), percentile=50)


def test_the_cost_year_is_the_canterbury_one():
    # Land values are indexed to 2025-09, so the two vintages must stay
    # distinguishable all the way into the loss table.
    assert COST_YEAR == 2011


def test_the_none_state_keeps_its_name():
    # "None" is in pandas' default NA values, so read carelessly the least
    # severe state comes back unlabelled and vanishes from any summary grouped
    # on the name -- while its cost stays in the total, so nothing looks wrong.
    costs = load_ld_costs()
    assert costs.loc[1, "state_name"] == "None"
    assert costs["state_name"].notna().all()
