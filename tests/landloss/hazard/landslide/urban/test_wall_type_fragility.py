"""Tests for the wall type fragility stored as two PGA percentiles."""

import numpy as np
import pandas as pd
import pytest

from landloss.exposure.rw.lines import CUT, FILL
from landloss.hazard.landslide.urban import wall_type_fragility as wtf


def test_percentiles_round_trip_through_the_lognormal() -> None:
    # Arrange
    theta, beta = np.array([1.1126, 0.6729]), np.array([0.654, 0.6296])

    # Act
    p15, p50 = wtf.lognormal_to_percentiles(theta, beta)
    theta_back, beta_back = wtf.percentiles_to_lognormal(p15, p50)

    # Assert
    np.testing.assert_allclose(theta_back, theta)
    np.testing.assert_allclose(beta_back, beta)


def test_the_curve_passes_through_its_stored_percentiles() -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[[0]]
    walls = pd.concat([row["wall_type"]] * 2)

    # Act
    probability = wtf.wall_type_failure_probability(
        [row["p15"].item(), row["p50"].item()],
        walls,
        pd.concat([row["size_class"]] * 2),
        pd.Series([None, None], index=walls.index),
        table,
    )

    # Assert
    np.testing.assert_allclose(probability, [0.15, 0.5], atol=1e-3)


@pytest.mark.parametrize(
    ("position", "factor"),
    [(FILL, wtf.FILL_CAPACITY_FACTOR), (CUT, wtf.CUT_CAPACITY_FACTOR), (None, 1.0)],
)
def test_a_wall_position_scales_both_percentiles(position, factor) -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[0]
    walls = pd.Series([row["wall_type"]] * 2)
    sizes = pd.Series([row["size_class"]] * 2)

    # Act
    probability = wtf.wall_type_failure_probability(
        [row["p15"] * factor, row["p50"] * factor],
        walls,
        sizes,
        pd.Series([position, position]),
        table,
    )

    # Assert
    np.testing.assert_allclose(probability, [0.15, 0.5], atol=1e-3)


def test_the_packaged_table_holds_every_type_and_size() -> None:
    # Act
    table = wtf.load_wall_type_fragility()

    # Assert
    assert len(table) == len(wtf.WALL_TYPES) * 3
    assert (table["p15"] < table["p50"]).all()


def test_an_unknown_wall_position_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown wall position"):
        wtf.position_factor(pd.Series(["toe"]))


def test_unordered_percentiles_are_refused() -> None:
    with pytest.raises(ValueError, match="below its p50"):
        wtf.percentiles_to_lognormal([0.8], [0.6])


def test_curves_carry_the_table_median_dispersion_and_source() -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[0]
    index = pd.Index([7, 3])

    # Act
    curves = wtf.wall_type_curves(
        pd.Series([row["wall_type"]] * 2, index=index),
        pd.Series([row["size_class"]] * 2, index=index),
        pd.Series([None, None], index=index),
        table,
    )

    # Assert
    assert list(curves.columns) == ["theta_pga_g", "beta", "source"]
    assert curves.index.equals(index)
    np.testing.assert_allclose(curves["theta_pga_g"], [row["theta"]] * 2)
    np.testing.assert_allclose(curves["beta"], [row["beta"]] * 2)
    assert (curves["source"] == row["source"]).all()


def test_curves_scale_the_median_by_position_and_keep_the_dispersion() -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[0]

    # Act
    curves = wtf.wall_type_curves(
        pd.Series([row["wall_type"]] * 3),
        pd.Series([row["size_class"]] * 3),
        pd.Series([FILL, CUT, None]),
        table,
    )

    # Assert
    np.testing.assert_allclose(
        curves["theta_pga_g"],
        np.array([wtf.FILL_CAPACITY_FACTOR, wtf.CUT_CAPACITY_FACTOR, 1.0])
        * row["theta"],
    )
    np.testing.assert_allclose(curves["beta"], [row["beta"]] * 3)


def test_curves_refuse_a_pair_missing_from_the_table() -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    table = table[table["wall_type"] != "crib"]

    # Act and Assert
    with pytest.raises(ValueError, match="No wall type curve"):
        wtf.wall_type_curves(
            pd.Series(["crib"]), pd.Series(["small"]), pd.Series([None]), table
        )


@pytest.mark.parametrize(
    ("size_index", "position_index"),
    [
        ([5, 5, 2], [2, 5, 9]),
        ([5, 2, 5], [5, 5, 2]),
        ([5, 5, 2], [0]),
    ],
)
def test_curves_refuse_inputs_not_on_one_index(size_index, position_index) -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[0]
    walls = pd.Series([row["wall_type"]] * 3, index=[5, 5, 2])
    sizes = pd.Series([row["size_class"]] * 3, index=size_index)
    positions = pd.Series([CUT] * len(position_index), index=position_index)

    # Act and Assert
    with pytest.raises(ValueError, match="share one index"):
        wtf.wall_type_curves(walls, sizes, positions, table)
