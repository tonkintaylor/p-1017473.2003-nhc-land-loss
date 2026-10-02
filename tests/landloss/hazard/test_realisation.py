import numpy as np
import pytest

from landloss.hazard.realisation import realisation_seed, stream_entropy

BASE = 1017473


def draws(base, realisation_id, stream, n=8):
    return realisation_seed(base, realisation_id, stream).random(n)


def test_the_same_three_inputs_always_give_the_same_draws():
    assert np.array_equal(
        draws(BASE, 0, "liquefaction"), draws(BASE, 0, "liquefaction")
    )


def test_a_stream_name_hashes_the_same_in_every_process():
    # Not Python's salted hash(), or a run would not reproduce tomorrow.
    assert stream_entropy("liquefaction") == stream_entropy("liquefaction")
    assert stream_entropy("liquefaction") != stream_entropy("landslide")


def test_two_hazards_in_one_realisation_draw_different_numbers():
    assert not np.array_equal(draws(BASE, 0, "shaking"), draws(BASE, 0, "landslide"))


def test_two_realisations_of_one_hazard_draw_different_numbers():
    assert not np.array_equal(draws(BASE, 0, "shaking"), draws(BASE, 1, "shaking"))


def test_adding_a_stream_does_not_shift_an_existing_one():
    # The property that keeps last week's run reproducible when a fourth hazard
    # is added: a stream's name only ever feeds its own sequence.
    before = draws(BASE, 3, "shaking")
    draws(BASE, 3, "a-hazard-invented-later")
    assert np.array_equal(before, draws(BASE, 3, "shaking"))


def test_a_negative_realisation_is_refused():
    with pytest.raises(ValueError, match="zero or more"):
        realisation_seed(BASE, -1, "shaking")


def test_an_unnamed_stream_is_refused():
    with pytest.raises(ValueError, match="non-empty"):
        realisation_seed(BASE, 0, "")


# --- exposure worlds ---------------------------------------------------------


def world_draws(base, realisation_id, stream, world_id, n=8):
    return realisation_seed(base, realisation_id, stream, world_id=world_id).random(n)


def test_no_world_id_reproduces_the_draw_from_before_worlds_existed():
    # The entropy without a world id is exactly what it was, so every existing
    # stream -- shaking, liquefaction, landslide -- draws the same numbers.
    expected = np.random.default_rng(
        np.random.SeedSequence([BASE, 3, stream_entropy("shaking")])
    ).random(8)
    assert np.array_equal(draws(BASE, 3, "shaking"), expected)
    assert np.array_equal(
        realisation_seed(BASE, 3, "shaking", world_id=None).random(8), expected
    )


def test_the_same_four_inputs_always_give_the_same_draws():
    assert np.array_equal(
        world_draws(BASE, 3, "urban", 0), world_draws(BASE, 3, "urban", 0)
    )


def test_a_world_id_changes_the_draw_for_the_same_earthquake_and_stream():
    assert not np.array_equal(
        world_draws(BASE, 3, "urban", 0), world_draws(BASE, 3, "urban", 1)
    )
    assert not np.array_equal(world_draws(BASE, 3, "urban", 0), draws(BASE, 3, "urban"))


def test_a_negative_world_is_refused():
    with pytest.raises(ValueError, match="world_id must be zero or more"):
        realisation_seed(BASE, 0, "urban", world_id=-1)
