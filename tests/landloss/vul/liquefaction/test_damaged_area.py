import numpy as np
import pytest

from landloss.vul.liquefaction.damaged_area import check_ranges, draw_damaged_areas

EVACUATED = {
    1: (0.0, 0.0),
    2: (1.0, 1.0),
    3: (1.0, 1.0),
    4: (1.0, 10.0),
    5: (10.0, 40.0),
    6: (40.0, 100.0),
}
INUNDATED = {
    1: (0.0, 0.0),
    2: (0.0, 0.0),
    3: (0.25, 0.70),
    4: (0.30, 1.00),
    5: (0.30, 1.00),
    6: (0.30, 1.00),
}


def draw(states, areas, seed=0, evacuated=EVACUATED, inundated=INUNDATED):
    return draw_damaged_areas(
        np.asarray(states, dtype=float),
        np.asarray(areas, dtype=float),
        evacuated,
        inundated,
        np.random.default_rng(seed),
    )


@pytest.mark.parametrize("state", [1, 2, 3, 4, 5, 6])
def test_each_draw_falls_within_its_states_range(state):
    n = 2_000
    evacuated, inundated = draw(np.full(n, state), np.full(n, 1_000.0))
    low, high = EVACUATED[state]
    assert np.all((evacuated >= low) & (evacuated <= high))
    low, high = INUNDATED[state]
    share = inundated / 1_000.0
    assert np.all((share >= low) & (share <= high))


def test_inundated_scales_with_the_insured_area_and_evacuated_does_not():
    evacuated_small, inundated_small = draw([5.0], [200.0], seed=4)
    evacuated_large, inundated_large = draw([5.0], [2_000.0], seed=4)
    assert evacuated_small == pytest.approx(evacuated_large)
    assert inundated_large == pytest.approx(10 * inundated_small)


def test_neither_area_exceeds_the_insured_land():
    # A 30 m2 sliver in Very severe would otherwise lose 40 to 100 m2.
    evacuated, inundated = draw(np.full(500, 6.0), np.full(500, 30.0))
    assert np.all(evacuated <= 30.0)
    assert np.all(inundated <= 30.0)


def test_a_property_off_the_grid_loses_no_ground():
    evacuated, inundated = draw([np.nan, 6.0], [500.0, 500.0])
    assert evacuated[0] == 0.0
    assert inundated[0] == 0.0
    assert evacuated[1] > 0.0


def test_a_range_change_does_not_reshuffle_other_states():
    states = np.tile([3.0, 4.0, 5.0, 6.0], 200)
    areas = np.full(states.shape, 600.0)
    before = draw(states, areas, seed=9)
    after = draw(states, areas, seed=9, evacuated={**EVACUATED, 4: (2.0, 3.0)})
    untouched = states != 4.0
    for b, a in zip(before, after, strict=True):
        assert np.array_equal(b[untouched], a[untouched])


@pytest.mark.parametrize(
    ("ranges", "upper"),
    [
        ({k: v for k, v in INUNDATED.items() if k != 6}, 1.0),
        ({**INUNDATED, 3: (0.7, 0.25)}, 1.0),
        ({**INUNDATED, 4: (0.3, 1.2)}, 1.0),
        ({**EVACUATED, 2: (-1.0, 1.0)}, None),
    ],
)
def test_an_invalid_range_table_is_refused(ranges, upper):
    with pytest.raises(ValueError, match="ranges"):
        check_ranges(ranges, name="test", upper=upper)


def test_mismatched_inputs_are_refused():
    with pytest.raises(ValueError, match="insured areas"):
        draw([3.0, 4.0], [500.0])
