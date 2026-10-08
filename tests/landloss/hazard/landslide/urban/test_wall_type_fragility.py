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
        pd.Series([1.0, 1.0], index=walls.index),
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
    heights = pd.Series([1.0] * 2)

    # Act
    probability = wtf.wall_type_failure_probability(
        [row["p15"] * factor, row["p50"] * factor],
        walls,
        heights,
        pd.Series([position, position]),
        table,
    )

    # Assert
    np.testing.assert_allclose(probability, [0.15, 0.5], atol=1e-3)


def test_the_packaged_table_holds_every_type_and_height_class() -> None:
    # Act
    table = wtf.load_wall_type_fragility()

    # Assert
    assert len(table) == len(wtf.WALL_TYPES) * len(wtf.HEIGHT_CLASSES)
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
        pd.Series([1.0] * 2, index=index),
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
        pd.Series([1.0] * 3),
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
    table = table[table["wall_type"] != "crib_gabion"]

    # Act and Assert
    with pytest.raises(ValueError, match="No wall type curve"):
        wtf.wall_type_curves(
            pd.Series(["crib_gabion"]), pd.Series([1.0]), pd.Series([None]), table
        )


@pytest.mark.parametrize(
    ("height_index", "position_index"),
    [
        ([5, 5, 2], [2, 5, 9]),
        ([5, 2, 5], [5, 5, 2]),
        ([5, 5, 2], [0]),
    ],
)
def test_curves_refuse_inputs_not_on_one_index(height_index, position_index) -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()
    row = table.iloc[0]
    walls = pd.Series([row["wall_type"]] * 3, index=[5, 5, 2])
    heights = pd.Series([1.0] * 3, index=height_index)
    positions = pd.Series([CUT] * len(position_index), index=position_index)

    # Act and Assert
    with pytest.raises(ValueError, match="share one index"):
        wtf.wall_type_curves(walls, heights, positions, table)


@pytest.mark.parametrize(
    ("height_m", "expected"),
    [
        (0.5, "under_2_m"),
        (1.99, "under_2_m"),
        (2.0, "2_m_and_over"),
        (6.5, "2_m_and_over"),
        (np.nan, "under_2_m"),
    ],
)
def test_height_class_splits_at_two_metres(height_m, expected) -> None:
    # Arrange
    heights = pd.Series([height_m], index=[4])

    # Act
    classes = wtf.height_class(heights)

    # Assert
    assert classes.index.equals(heights.index)
    assert classes.iloc[0] == expected


def _medians(table: pd.DataFrame, wall_type: str) -> tuple[float, float]:
    """Return the median of a wall type under 2 m and at 2 m and over."""
    curves = wtf.wall_type_curves(
        pd.Series([wall_type] * 2),
        pd.Series([1.0, 3.0]),
        pd.Series([None, None]),
        table,
    )
    short, tall = curves["theta_pga_g"].to_numpy(dtype=float)
    return short, tall


@pytest.mark.parametrize(
    "wall_type",
    ["brick_rock", "timber_pole_pre_1992", "concrete_block", "garden_timber"],
)
def test_a_switched_type_is_weaker_when_tall(wall_type) -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()

    # Act
    short, tall = _medians(table, wall_type)

    # Assert
    assert tall < short


@pytest.mark.parametrize(
    "wall_type", ["crib_gabion", "timber_pole_post_1992", "engineered"]
)
def test_a_type_with_no_height_effect_has_one_curve(wall_type) -> None:
    # Arrange
    table = wtf.load_wall_type_fragility()

    # Act
    short, tall = _medians(table, wall_type)

    # Assert
    assert tall == pytest.approx(short)


def test_the_packaged_height_effect_names_the_curve_each_class_takes() -> None:
    # Arrange
    table = wtf.load_wall_type_fragility().set_index(list(wtf.TABLE_KEY))
    height = table["published_height_m"]

    # Act
    effect = table["height_effect"].groupby(level="wall_type").first()

    # Assert
    for wall_type, one in effect.items():
        short, tall = (
            height[(wall_type, "under_2_m")],
            height[(wall_type, "2_m_and_over")],
        )
        expected = {"switched": (6, 3), "none": (3, 3)}[one]
        assert (short, tall) == expected


def test_a_table_missing_a_height_class_is_refused(tmp_path) -> None:
    # Arrange
    table = pd.read_csv(wtf.WALL_TYPE_FRAGILITY_PATH)
    path = tmp_path / "walls.csv"
    table[table["height_class"] == "under_2_m"].to_csv(path, index=False)

    # Act and Assert
    with pytest.raises(ValueError, match="exactly once"):
        wtf.load_wall_type_fragility(path)


def test_the_packaged_wall_types_table_names_every_type_once() -> None:
    types = wtf.load_wall_types()
    assert types["wall_type"].tolist() == list(wtf.WALL_TYPES)
    assert types["label"].notna().all()
    assert types["nhc_rate_item"].notna().all()


def test_a_wall_types_table_missing_a_type_is_refused(tmp_path) -> None:
    path = tmp_path / "types.csv"
    wtf.load_wall_types().iloc[1:].to_csv(path, index=False)
    with pytest.raises(ValueError, match="not each of"):
        wtf.load_wall_types(path)
