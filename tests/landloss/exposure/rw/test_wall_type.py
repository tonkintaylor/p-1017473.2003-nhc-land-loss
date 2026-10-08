"""Tests for drawing each retaining wall's type."""

import numpy as np
import pandas as pd
import pytest

from landloss.exposure.rw import wall_type as wt
from landloss.exposure.rw.age import AGE_BINS
from landloss.exposure.rw.wall_age import AGE_SHARE_COLUMNS
from landloss.hazard.landslide.urban.wall_type_fragility import WALL_TYPES


def candidates(
    n: int,
    *,
    height_m: float = 2.0,
    on_road_frontage: bool = False,
    age_shares: tuple[float, ...] = (0.25, 0.25, 0.25, 0.25),
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {"height_m": np.full(n, height_m), "on_road_frontage": on_road_frontage}
    )
    for column, share in zip(AGE_SHARE_COLUMNS, age_shares, strict=True):
        frame[column] = share
    return frame


def one_bin(age_bin: str) -> tuple[float, ...]:
    return tuple(float(name == age_bin) for name in AGE_BINS)


@pytest.mark.parametrize(
    ("height", "band"),
    [
        (np.nan, "under_1_5_m"),
        (0.0, "under_1_5_m"),
        (1.49, "under_1_5_m"),
        (1.5, "1_5_to_2_5_m"),
        (2.49, "1_5_to_2_5_m"),
        (2.5, "over_2_5_m"),
        (6.0, "over_2_5_m"),
    ],
    ids=["nan", "zero", "below-1.5", "at-1.5", "below-2.5", "at-2.5", "tall"],
)
def test_a_height_falls_in_its_band(height: float, band: str) -> None:
    # Act
    result = wt.height_band([height])

    # Assert
    assert result.tolist() == [band]


def test_the_packaged_shares_cover_every_bin_and_band_and_sum_to_one() -> None:
    # Act
    shares = wt.load_beta_wall_type_shares()

    # Assert
    assert shares.shape == (len(AGE_BINS) * len(wt.HEIGHT_BANDS), len(WALL_TYPES))
    assert list(shares.columns) == list(WALL_TYPES)
    np.testing.assert_allclose(shares.sum(axis=1), 1.0)
    assert (
        shares.loc[("pre_1970", "over_2_5_m"), "reinforced_concrete_pre_1992"] == 0.60
    )


def test_the_packaged_multipliers_cover_every_type() -> None:
    # Act
    multipliers = wt.load_beta_frontage_multipliers()

    # Assert
    assert list(multipliers.index) == list(WALL_TYPES)
    assert multipliers["brick_rock"] == 1.5
    assert multipliers["garden_timber"] == 0.3


def packaged_shares_frame() -> pd.DataFrame:
    return pd.read_csv(wt.BETA_WALL_TYPE_SHARES_PATH)


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda t: t.drop(columns="crib_gabion"), "missing the columns"),
        (lambda t: t.assign(extra=0.0), "unknown columns"),
        (lambda t: t.replace({"age_bin": {"pre_1970": "old"}}), "Unknown age bins"),
        (lambda t: t.iloc[1:], "exactly once"),
        (lambda t: pd.concat([t, t.iloc[[0]]]), "exactly once"),
        (lambda t: t.assign(crib_gabion=-0.05), "non-negative"),
        (lambda t: t.assign(crib_gabion=t["crib_gabion"] + 0.01), "sum to one"),
    ],
    ids=["missing", "extra", "bin", "absent", "doubled", "negative", "sum"],
)
def test_a_bad_shares_table_is_refused(tmp_path, edit, match) -> None:
    # Arrange
    path = tmp_path / "shares.csv"
    edit(packaged_shares_frame()).to_csv(path, index=False)

    # Act / Assert
    with pytest.raises(ValueError, match=match):
        wt.load_beta_wall_type_shares(path)


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda t: t.drop(columns="road_frontage_multiplier"), "missing"),
        (lambda t: t.iloc[1:], "exactly once"),
        (lambda t: pd.concat([t, t.iloc[[0]]]), "exactly once"),
        (lambda t: t.replace({"wall_type": {"crib_gabion": "wattle"}}), "exactly once"),
        (lambda t: t.assign(road_frontage_multiplier=0.0), "positive"),
    ],
    ids=["missing", "absent", "doubled", "unknown", "zero"],
)
def test_a_bad_multipliers_table_is_refused(tmp_path, edit, match) -> None:
    # Arrange
    path = tmp_path / "multipliers.csv"
    edit(pd.read_csv(wt.BETA_FRONTAGE_MULTIPLIERS_PATH)).to_csv(path, index=False)

    # Act / Assert
    with pytest.raises(ValueError, match=match):
        wt.load_beta_frontage_multipliers(path)


def draw(walls: pd.DataFrame, seed: int = 0, **kwargs) -> pd.DataFrame:
    return wt.draw_wall_types(
        walls,
        np.random.default_rng(seed),
        wt.load_beta_wall_type_shares(),
        wt.load_beta_frontage_multipliers(),
        **kwargs,
    )


def test_the_same_generator_reproduces_the_draw_on_the_candidates_index() -> None:
    # Arrange
    walls = candidates(50).set_axis(range(100, 150))

    # Act
    first, second = draw(walls), draw(walls)

    # Assert
    pd.testing.assert_frame_equal(first, second)
    assert list(first.columns) == [wt.AGE_BIN_COLUMN, wt.WALL_TYPE_COLUMN]
    assert first.index.equals(walls.index)


def test_a_wall_drawn_earlier_does_not_depend_on_walls_added_after_it() -> None:
    # Arrange
    walls = candidates(200)
    walls["height_m"] = np.linspace(0.5, 4.0, 200)

    # Act
    short = draw(walls.iloc[:50])
    long = draw(walls)

    # Assert
    pd.testing.assert_frame_equal(short, long.iloc[:50])


def test_the_drawn_mix_matches_the_shares_row() -> None:
    # Arrange
    n = 20_000
    walls = candidates(n, height_m=3.0, age_shares=one_bin("1970_1991"))
    expected = wt.load_beta_wall_type_shares().loc[("1970_1991", "over_2_5_m")]

    # Act
    drawn = draw(walls, rebuilt_share=0.0)

    # Assert
    observed = drawn["wall_type"].value_counts(normalize=True)
    observed = observed.reindex(list(WALL_TYPES), fill_value=0.0)
    np.testing.assert_allclose(observed, expected, atol=0.015)


def test_the_drawn_bins_follow_the_age_shares() -> None:
    # Arrange
    shares = (0.1, 0.2, 0.3, 0.4)
    walls = candidates(20_000, age_shares=shares)

    # Act
    drawn = draw(walls, rebuilt_share=0.0)

    # Assert
    observed = drawn["age_bin"].value_counts(normalize=True).reindex(list(AGE_BINS))
    np.testing.assert_allclose(observed, shares, atol=0.015)


def test_a_road_frontage_shifts_the_mix_by_the_multipliers() -> None:
    # Arrange
    n = 20_000
    walls = candidates(n, height_m=1.0, age_shares=one_bin("pre_1970"))
    frontage = candidates(
        n, height_m=1.0, on_road_frontage=True, age_shares=one_bin("pre_1970")
    )
    row = wt.load_beta_wall_type_shares().loc[("pre_1970", "under_1_5_m")]
    weighted = row * wt.load_beta_frontage_multipliers()
    expected = weighted / weighted.sum()

    # Act
    plain = draw(walls, rebuilt_share=0.0)["wall_type"].value_counts(normalize=True)
    shifted = draw(frontage, rebuilt_share=0.0)["wall_type"].value_counts(
        normalize=True
    )

    # Assert
    shifted = shifted.reindex(list(WALL_TYPES), fill_value=0.0)
    np.testing.assert_allclose(shifted, expected, atol=0.015)
    assert shifted["brick_rock"] > plain["brick_rock"]
    assert shifted["garden_timber"] < plain["garden_timber"]


def test_no_rebuild_keeps_every_bin_where_it_was_drawn() -> None:
    # Arrange
    walls = pd.concat(
        [candidates(100, age_shares=one_bin(name)) for name in AGE_BINS],
        ignore_index=True,
    )

    # Act
    drawn = draw(walls, rebuilt_share=0.0)

    # Assert
    assert drawn["age_bin"].tolist() == np.repeat(AGE_BINS, 100).tolist()


def test_a_certain_rebuild_moves_every_bin_one_later_and_keeps_the_last() -> None:
    # Arrange
    walls = pd.concat(
        [candidates(100, age_shares=one_bin(name)) for name in AGE_BINS],
        ignore_index=True,
    )
    later = [*AGE_BINS[1:], AGE_BINS[-1]]

    # Act
    drawn = draw(walls, rebuilt_share=1.0)

    # Assert
    assert drawn["age_bin"].tolist() == np.repeat(later, 100).tolist()


@pytest.mark.parametrize("on_road_frontage", [False, True], ids=["plain", "frontage"])
def test_a_type_with_no_share_is_never_drawn(on_road_frontage: bool) -> None:
    # Arrange
    walls = candidates(
        5_000,
        height_m=3.0,
        on_road_frontage=on_road_frontage,
        age_shares=one_bin("2005_on"),
    )

    # Act
    drawn = draw(walls)

    # Assert
    assert set(drawn["wall_type"]) <= {
        "crib_gabion",
        "concrete_block",
        "timber_pole_post_1992",
        "reinforced_concrete_post_1992",
    }


def test_a_wall_of_unknown_height_draws_in_the_lowest_band() -> None:
    # Arrange
    walls = candidates(2_000, height_m=np.nan, age_shares=one_bin("2005_on"))

    # Act
    drawn = draw(walls, rebuilt_share=0.0)

    # Assert
    assert "garden_timber" in set(drawn["wall_type"])
    assert "reinforced_concrete_post_1992" not in set(drawn["wall_type"])


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        (lambda c: c.drop(columns="on_road_frontage"), "missing the columns"),
        (lambda c: c.assign(on_road_frontage=None), "flag"),
        (lambda c: c.assign(p_pre_1970=0.5), "sum to one"),
    ],
    ids=["missing", "null-frontage", "shares"],
)
def test_unreadable_candidates_are_refused(edit, match) -> None:
    # Arrange
    walls = edit(candidates(3))

    # Act / Assert
    with pytest.raises(ValueError, match=match):
        draw(walls)


def test_a_rebuilt_share_outside_zero_to_one_is_refused() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="rebuilt_share"):
        draw(candidates(3), rebuilt_share=1.5)
