import numpy as np
import pytest
import xarray as xr

from landloss.hazard.liquefaction.land_damage import (
    LD_STATES,
    beta_expand_ld_probabilities,
    draw_ld_states,
    exceedance_to_bands,
)
from landloss.hazard.realisation import realisation_seed


def grid(values):
    return xr.DataArray(np.array(values, dtype=float), dims=("y", "x"))


def cell(value):
    """A one-cell grid, for checking the arithmetic on a single value."""
    return grid([[value]])


def bands_of(moderate_or_worse, major_or_worse):
    return exceedance_to_bands(cell(moderate_or_worse), cell(major_or_worse))


def expand(moderate_or_worse, major_or_worse):
    """Expand from exceedance grids, the shape the NLM supplies."""
    return beta_expand_ld_probabilities(
        grid([moderate_or_worse]), grid([major_or_worse])
    )


def rng():
    return realisation_seed(1, 0, "liquefaction")


# --- differencing the exceedance pair ---------------------------------------


def test_the_moderate_band_is_the_difference_of_the_two_exceedances():
    # P(>=Moderate) = 0.5 and P(>=Major) = 0.2 means the Moderate band is 0.3.
    bands = bands_of(0.5, 0.2)
    assert bands["Moderate"].values == pytest.approx(0.3)
    assert bands["Major"].values == pytest.approx(0.2)
    assert bands["None"].values == pytest.approx(0.5)


def test_reading_the_grids_as_bands_would_have_double_counted_major():
    # The bug this differencing exists to prevent: treating P(>=Moderate) as the
    # Moderate band leaves the Major mass inside it as well.
    bands = bands_of(0.5, 0.2)
    assert bands["Moderate"].values != pytest.approx(0.5)


def test_a_swapped_pair_is_refused():
    with pytest.raises(ValueError, match="swapped"):
        bands_of(0.2, 0.5)


def test_a_grid_outside_zero_to_one_is_refused():
    # A grid in per cent, or one carrying an undeclared nodata marker.
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        bands_of(55.0, 20.0)


# --- subdividing into the six states ----------------------------------------


def test_the_six_states_sum_to_one_everywhere():
    expanded = expand([0.0, 0.5, 0.95], [0.0, 0.2, 0.9])
    assert np.allclose(sum(expanded.values()).values, 1.0)


def test_none_splits_in_half_into_none_and_minor():
    expanded = expand([0.4], [0.2])
    # None band is 1 - 0.4 = 0.6, half of it to Minor.
    assert expanded["None"].values == pytest.approx(0.3)
    assert expanded["Minor"].values == pytest.approx(0.3)


def test_major_splits_into_severe_very_severe_and_a_quarter_left_as_major():
    expanded = expand([0.4], [0.4])
    assert expanded["Major"].values == pytest.approx(0.1)
    assert expanded["Severe"].values == pytest.approx(0.2)
    assert expanded["Very Severe"].values == pytest.approx(0.1)


def test_the_moderate_band_passes_through_the_subdivision_untouched():
    expanded = expand([0.5], [0.2])
    assert expanded["Moderate"].values == pytest.approx(0.3)


def test_a_cell_with_no_liquefaction_is_all_none_and_minor():
    expanded = expand([0.0], [0.0])
    assert expanded["None"].values == pytest.approx(0.5)
    assert expanded["Minor"].values == pytest.approx(0.5)
    assert expanded["Moderate"].values == pytest.approx(0.0)


# --- drawing states ----------------------------------------------------------


def test_a_drawn_state_is_always_one_of_the_six():
    expanded = expand([0.5] * 50, [0.2] * 50)
    states = draw_ld_states(expanded, rng())
    assert set(np.unique(states.values)) <= set(range(1, len(LD_STATES) + 1))


def test_a_certain_cell_always_draws_that_state():
    # P(>=Moderate) = 1 and P(>=Major) = 0 puts all the mass on Moderate.
    expanded = expand([1.0] * 20, [0.0] * 20)
    assert np.all(draw_ld_states(expanded, rng()).values == 3)


def test_the_same_realisation_draws_the_same_states():
    expanded = expand([0.5] * 40, [0.2] * 40)
    assert np.array_equal(
        draw_ld_states(expanded, rng()).values,
        draw_ld_states(expanded, rng()).values,
    )


def test_a_cell_with_no_data_stays_missing_rather_than_becoming_no_damage():
    expanded = expand([np.nan, 0.5], [np.nan, 0.2])
    states = draw_ld_states(expanded, rng())
    assert np.isnan(states.values[0][0])
    assert not np.isnan(states.values[0][1])


def test_a_cell_missing_only_the_major_grid_is_not_drawn_as_undamaged():
    # The bands the missing grid does not feed -- None and Minor -- are finite,
    # so accumulating and letting NaN propagate would hand this cell state 1 or
    # 2 and write unknown ground into the raster as undamaged.
    moderate = grid([[0.4] * 200])
    major = grid([[np.nan] * 100 + [0.2] * 100])
    states = draw_ld_states(beta_expand_ld_probabilities(moderate, major), rng())
    unknown, known = states.values[0][:100], states.values[0][100:]
    assert np.all(np.isnan(unknown))
    assert not np.any(np.isnan(known))


def test_a_grid_holding_no_finite_values_is_refused():
    # A clip that missed the layer, or a nodata fill, rather than a real grid.
    with pytest.raises(ValueError, match="no finite values"):
        exceedance_to_bands(grid([[np.nan, np.nan]]), grid([[0.1, 0.2]]))


def test_a_missing_state_is_refused():
    expanded = expand([0.5], [0.2])
    del expanded["Severe"]
    with pytest.raises(ValueError, match="Severe"):
        draw_ld_states(expanded, rng())
