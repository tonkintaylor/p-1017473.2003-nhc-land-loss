"""Tests for the size classes a wall is carried in."""

import numpy as np
import pandas as pd
import pytest

from landloss.exposure.rw import beta_population
from landloss.exposure.rw.beta_population import (
    MEDIUM_MAX_HEIGHT_M,
    SIZE_CLASSES,
    SMALL_MAX_HEIGHT_M,
    classify_wall_size,
    describe_population,
)

# --- size classes ------------------------------------------------------------


def test_the_size_classes_split_on_the_agreed_heights():
    classes = classify_wall_size(
        np.array([0.5, SMALL_MAX_HEIGHT_M, 2.0, MEDIUM_MAX_HEIGHT_M, 4.0])
    )
    assert list(classes) == ["small", "medium", "medium", "large", "large"]


def test_every_class_is_one_of_the_three():
    classes = classify_wall_size(np.linspace(0.1, 6.0, 50))
    assert set(classes) <= set(SIZE_CLASSES)


def test_a_scalar_height_classes_too():
    assert str(classify_wall_size(15.0)) == "large"


# --- conditions --------------------------------------------------------------


def test_the_initial_condition_axis_is_retired():
    # The wall type carries what the condition did, so neither is left behind.
    assert not hasattr(beta_population, "INITIAL_CONDITIONS")
    assert not hasattr(beta_population, "BETA_POOR_SHARE")


# --- the summary -------------------------------------------------------------


def test_describe_population_counts_every_class_and_wall_type():
    walls = pd.DataFrame(
        {
            "size_class": ["small", "small", "large"],
            "wall_type": ["crib_gabion", "garden_timber", "crib_gabion"],
            "height_m": [0.6, 0.7, 3.0],
        }
    )
    counts = describe_population(walls)
    assert counts.index.tolist() == list(SIZE_CLASSES)
    assert counts.loc["small", "crib_gabion"] == 1
    assert counts.loc["small", "garden_timber"] == 1
    assert counts.loc["medium"].sum() == 0
    assert counts.loc["large", "crib_gabion"] == 1


def test_describe_population_on_no_walls_keeps_the_size_classes():
    counts = describe_population(
        pd.DataFrame(columns=["size_class", "wall_type", "height_m"])
    )
    assert counts.index.tolist() == list(SIZE_CLASSES)
    assert counts.empty


@pytest.mark.parametrize("height", [0.5, 1.0, 2.5])
def test_the_boundaries_are_inclusive_above(height):
    expected = {0.5: "small", 1.0: "medium", 2.5: "large"}[height]
    assert str(classify_wall_size(height)) == expected
