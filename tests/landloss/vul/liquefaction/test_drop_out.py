import numpy as np
import pytest

from landloss.vul.liquefaction.drop_out import check_drop_out_rates, draw_claims

RATES = {1: 0.95, 2: 0.75, 3: 0.4, 4: 0.15, 5: 0.0, 6: 0.0}


def test_a_zero_drop_out_rate_always_claims():
    states = np.full(1_000, 5.0)
    claimed = draw_claims(states, RATES, np.random.default_rng(0))
    assert claimed.all()


def test_a_drop_out_rate_of_one_never_claims():
    rates = {**RATES, 1: 1.0}
    claimed = draw_claims(np.full(1_000, 1.0), rates, np.random.default_rng(0))
    assert not claimed.any()


def test_a_property_off_the_grid_never_claims():
    states = np.array([np.nan, 6.0, np.nan])
    claimed = draw_claims(states, RATES, np.random.default_rng(0))
    assert claimed.tolist() == [False, True, False]


def test_the_claim_share_follows_the_rate():
    states = np.full(20_000, 3.0)
    claimed = draw_claims(states, RATES, np.random.default_rng(0))
    assert claimed.mean() == pytest.approx(1 - RATES[3], abs=0.02)


def test_a_rate_change_does_not_reshuffle_other_states():
    # One number per property, so moving state 2's rate leaves every other
    # property's draw where it was.
    states = np.tile([1.0, 2.0, 3.0, 4.0], 500)
    before = draw_claims(states, RATES, np.random.default_rng(7))
    after = draw_claims(states, {**RATES, 2: 0.1}, np.random.default_rng(7))
    untouched = states != 2.0
    assert np.array_equal(before[untouched], after[untouched])


def test_the_same_seed_gives_the_same_claims():
    states = np.tile([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, np.nan], 100)
    first = draw_claims(states, RATES, np.random.default_rng(3))
    second = draw_claims(states, RATES, np.random.default_rng(3))
    assert np.array_equal(first, second)


@pytest.mark.parametrize(
    "rates",
    [
        {1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.0},
        {**RATES, 7: 0.0},
        {**RATES, 3: 1.5},
        {**RATES, 4: -0.1},
    ],
)
def test_an_invalid_rate_table_is_refused(rates):
    with pytest.raises(ValueError, match="drop-out rates"):
        check_drop_out_rates(rates)


def test_a_state_outside_one_to_six_is_refused():
    with pytest.raises(ValueError, match="state"):
        draw_claims(np.array([7.0]), RATES, np.random.default_rng(0))
