import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from landloss.hazard.realisation import realisation_seed
from landloss.vul.shaking.fragility import (
    BETA_FAILURE_PROBABILITY,
    DAMAGE_STATES,
    NO_DAMAGE,
    PGA_IM,
    REPLACE,
    WALL_AMP_FACTOR,
    WALL_FRAGILITY_COLUMNS,
    WALL_RATE_FACTOR,
    beta_failure_probability,
    draw_damage_states,
    wall_failure_probability,
)


def rng(realisation_id=0):
    return realisation_seed(1, realisation_id, "vulnerability")


def wall_table():
    """Six unnamed-class rows: the small ones on PGA, the rest PGV-native."""
    rows = []
    for size_class, theta, im in (
        ("small", 0.5, PGA_IM),
        ("medium", 0.8, "pgv_m_s"),
        ("large", 1.0, "pgv_m_s"),
    ):
        for initial_condition, shift in (("modern", 1.0), ("poor", 0.7)):
            rows.append(
                {
                    "wall_class": "unnamed",
                    "size_class": size_class,
                    "initial_condition": initial_condition,
                    "im": im,
                    "theta": theta * shift,
                    "beta": 0.5,
                    "published_height_m": 2.0,
                    "damage_state": "collapse",
                    "source": f"test_{size_class}_{initial_condition}",
                    "basis": "synthetic",
                }
            )
    return pd.DataFrame(rows)


def walls(index=None):
    frame = pd.DataFrame(
        {
            "size_class": ["small", "medium", "small", "large"],
            "initial_condition": ["modern", "poor", "poor", "modern"],
        }
    )
    if index is not None:
        frame.index = index
    return frame


# --- the beta constant, kept for crossings ------------------------------------


def test_the_beta_probability_is_flat_across_every_structure():
    assert np.all(beta_failure_probability(50) == BETA_FAILURE_PROBABILITY)


def test_a_state_is_always_one_of_the_two():
    states = draw_damage_states(beta_failure_probability(500), rng())
    assert set(states) <= set(DAMAGE_STATES)


def test_the_share_replaced_tracks_the_probability():
    states = draw_damage_states(beta_failure_probability(5000), rng())
    share = (states == REPLACE).mean()
    assert abs(share - BETA_FAILURE_PROBABILITY) < 0.02


def test_certain_failure_replaces_everything():
    assert np.all(draw_damage_states(np.ones(100), rng()) == REPLACE)


def test_certain_survival_replaces_nothing():
    assert np.all(draw_damage_states(np.zeros(100), rng()) == NO_DAMAGE)


def test_assets_differ_within_one_realisation():
    # The point of drawing rather than thresholding: every asset reads the same
    # PGA, so without the draw the portfolio would be all or nothing.
    states = draw_damage_states(beta_failure_probability(200), rng())
    assert NO_DAMAGE in states
    assert REPLACE in states


def test_the_same_realisation_draws_the_same_states():
    first = draw_damage_states(beta_failure_probability(100), rng(2))
    second = draw_damage_states(beta_failure_probability(100), rng(2))
    assert np.array_equal(first, second)


def test_two_realisations_draw_differently():
    first = draw_damage_states(beta_failure_probability(200), rng(0))
    second = draw_damage_states(beta_failure_probability(200), rng(1))
    assert not np.array_equal(first, second)


def test_no_structures_draws_nothing():
    assert draw_damage_states(beta_failure_probability(0), rng()).size == 0


def test_a_probability_outside_zero_to_one_is_refused():
    with pytest.raises(ValueError, match="between 0 and 1"):
        draw_damage_states(np.array([1.5]), rng())


def test_a_nan_probability_draws_no_damage():
    states = draw_damage_states(np.array([np.nan, np.nan, 1.0]), rng())
    assert list(states) == [NO_DAMAGE, NO_DAMAGE, REPLACE]


def test_a_negative_count_is_refused():
    with pytest.raises(ValueError, match="must not be negative"):
        beta_failure_probability(-1)


# --- the wall curve on PGV -----------------------------------------------------


def test_the_flat_land_factors_are_both_one():
    assert WALL_AMP_FACTOR == 1.0
    assert WALL_RATE_FACTOR == 1.0


def test_a_pga_curve_is_converted_at_the_walls_ratio():
    frame = walls()
    pgv = np.array([0.6, 0.56, 0.42, 1.0])
    ratio = pd.Series([1.2, 1.2, 1.2, 1.2], index=frame.index)

    result = wall_failure_probability(frame, pgv, wall_table(), pgv_pga_ratio=ratio)

    assert list(result.columns) == list(WALL_FRAGILITY_COLUMNS)
    assert result.index.equals(frame.index)
    # Small, modern, published 0.5 g, at 1.2 m/s per g: 0.6 m/s, and PGV == theta
    # is the median of the lognormal.
    assert result.loc[0, "theta_base_pga_g"] == 0.5
    assert result.loc[0, "pgv_pga_ratio_m_s_per_g"] == 1.2
    assert result.loc[0, "theta"] == pytest.approx(0.6)
    assert result.loc[0, "failure_probability"] == pytest.approx(0.5)
    assert result.loc[0, "fragility_source"] == "test_small_modern"
    # Small, poor: 0.35 g -> 0.42 m/s.
    assert result.loc[2, "theta"] == pytest.approx(0.42)
    assert result.loc[2, "failure_probability"] == pytest.approx(0.5)


def test_a_pgv_native_curve_records_no_conversion():
    frame = walls()
    pgv = np.array([0.6, 0.4, 0.42, 1.0])
    ratio = pd.Series([1.2, 1.2, 1.2, 1.2], index=frame.index)

    result = wall_failure_probability(frame, pgv, wall_table(), pgv_pga_ratio=ratio)

    # Medium, poor: 0.8 * 0.7 = 0.56 m/s, used as published.
    assert np.isnan(result.loc[1, "theta_base_pga_g"])
    assert np.isnan(result.loc[1, "pgv_pga_ratio_m_s_per_g"])
    assert result.loc[1, "theta"] == pytest.approx(0.56)
    assert result.loc[1, "beta"] == 0.5
    expected = norm.cdf(np.log(0.4 / 0.56) / 0.5)
    assert result.loc[1, "failure_probability"] == pytest.approx(expected)
    # Large, modern at its median.
    assert result.loc[3, "failure_probability"] == pytest.approx(0.5)


def test_a_wall_off_the_grid_carries_no_probability():
    frame = walls()
    pgv = np.array([np.nan, 0.4, 0.42, 1.0])
    ratio = pd.Series([1.2, 1.2, np.nan, 1.2], index=frame.index)

    result = wall_failure_probability(frame, pgv, wall_table(), pgv_pga_ratio=ratio)

    # No PGV: the curve is there but nothing to evaluate it at.
    assert result.loc[0, "theta"] == pytest.approx(0.6)
    assert np.isnan(result.loc[0, "failure_probability"])
    # A PGA curve with no ratio cannot be converted.
    assert np.isnan(result.loc[2, "theta"])
    assert np.isnan(result.loc[2, "failure_probability"])
    assert np.isfinite(result.loc[[1, 3], "failure_probability"]).all()


def test_the_result_keeps_the_walls_own_index():
    frame = walls(index=pd.Index([10, 20, 30, 40]))
    ratio = pd.Series(1.0, index=frame.index)

    result = wall_failure_probability(
        frame, np.ones(4), wall_table(), pgv_pga_ratio=ratio
    )

    assert result.index.equals(frame.index)
    assert result.loc[10, "fragility_source"] == "test_small_modern"


def test_a_ratio_on_another_index_is_refused():
    frame = walls()
    ratio = pd.Series([1.0, 1.0, 1.0, 1.0], index=[1, 2, 3, 4])
    with pytest.raises(ValueError, match="indexed as walls"):
        wall_failure_probability(frame, np.ones(4), wall_table(), pgv_pga_ratio=ratio)


def test_a_pgv_of_the_wrong_length_is_refused():
    frame = walls()
    ratio = pd.Series(1.0, index=frame.index)
    with pytest.raises(ValueError, match="one value per wall"):
        wall_failure_probability(frame, np.ones(3), wall_table(), pgv_pga_ratio=ratio)


def test_a_wall_with_no_curve_is_refused():
    frame = walls()
    frame.loc[0, "size_class"] = "huge"
    ratio = pd.Series(1.0, index=frame.index)
    with pytest.raises(ValueError, match="huge"):
        wall_failure_probability(frame, np.ones(4), wall_table(), pgv_pga_ratio=ratio)


def test_no_walls_gives_an_empty_frame_with_the_columns():
    frame = walls().iloc[:0]
    ratio = pd.Series(dtype=float, index=frame.index)
    result = wall_failure_probability(
        frame, np.array([]), wall_table(), pgv_pga_ratio=ratio
    )
    assert result.empty
    assert list(result.columns) == list(WALL_FRAGILITY_COLUMNS)
