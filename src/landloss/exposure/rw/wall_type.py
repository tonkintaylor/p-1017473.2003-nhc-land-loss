"""Drawing each retaining wall's type from its age, height and road frontage.

Wall type in Wellington tracks the era a wall was built in, its height and
whether it stands on a road frontage (meeting with Nick Peters), and in
Canterbury failure tracked type far more than anything else [anderson_2015].
Each wall draws one age bin from its age shares
(:mod:`landloss.exposure.rw.wall_age`), may move one bin later because it was
rebuilt since the house (:data:`BETA_WALL_REBUILT_SHARE`), and then draws its
type from the row of :data:`BETA_WALL_TYPE_SHARES_PATH` for that bin and its
height band, with the road frontage multipliers applied where it stands on a
frontage (``.agents/plans/assigning-retaining-wall-types.md``, section 2).

The height bands break at 1.5 m, the consent threshold, which is what changes
the type, and at 2.5 m, so they differ from the size classes on purpose.

The type fractions, the frontage multipliers and the rebuilt share are
judgement placeholders from the project lead (2026-10-06) for Nick Peters to
revise, hence their ``beta`` names.
"""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from landloss.domain import constants
from landloss.exposure.rw.age import AGE_BINS
from landloss.exposure.rw.beta_population import MEDIUM_MAX_HEIGHT_M
from landloss.exposure.rw.wall_age import AGE_SHARE_COLUMNS
from landloss.hazard.landslide.urban.wall_type_fragility import WALL_TYPES
from landloss.io import ASSETS_DIR

BETA_WALL_TYPE_SHARES_PATH = ASSETS_DIR / "beta-retaining-wall-type-shares.csv"
BETA_FRONTAGE_MULTIPLIERS_PATH = (
    ASSETS_DIR / "beta-retaining-wall-frontage-multipliers.csv"
)

# The height bands the type fractions are read in, lowest first.
HEIGHT_BANDS = ("under_1_5_m", "1_5_to_2_5_m", "over_2_5_m")

# The chance a wall was rebuilt since the house and so belongs to the next age
# bin. Judgement (the lead, 2026-10-06).
BETA_WALL_REBUILT_SHARE = 0.2

# The named random stream the type draw takes, apart from the wall draw's.
WALL_TYPE_STREAM = "wall_type"

AGE_BIN_COLUMN = "age_bin"
HEIGHT_BAND_COLUMN = "height_band"
WALL_TYPE_COLUMN = "wall_type"
FRONTAGE_MULTIPLIER_COLUMN = "road_frontage_multiplier"
HEIGHT_COLUMN = "height_m"
ROAD_FRONTAGE_COLUMN = "on_road_frontage"

# How far a row of shares may stray from summing to one.
SHARE_SUM_TOLERANCE = 1e-9


def height_band(height_m: npt.ArrayLike) -> np.ndarray:
    """Return the height band each wall's type is drawn in.

    Args:
        height_m: Retained height in metres; NaN where it is not known.

    Returns:
        One of :data:`HEIGHT_BANDS` per wall. A wall of unknown height falls
        in the lowest band.
    """
    heights = np.asarray(height_m, dtype=float)
    return np.select(
        [
            np.isnan(heights) | (heights < constants.UNCONSENTED_WALL_HEIGHT_M),
            heights < MEDIUM_MAX_HEIGHT_M,
        ],
        [HEIGHT_BANDS[0], HEIGHT_BANDS[1]],
        default=HEIGHT_BANDS[2],
    )


def load_beta_wall_type_shares(path: Path = BETA_WALL_TYPE_SHARES_PATH) -> pd.DataFrame:
    """Read the share of each wall type by age bin and height band.

    Args:
        path: The CSV to read; the packaged table by default.

    Returns:
        One row per ``(age_bin, height_band)`` in :data:`AGE_BINS` by
        :data:`HEIGHT_BANDS` order, one column per wall type in
        :data:`WALL_TYPES` order.

    Raises:
        ValueError: If a column is missing or unknown, an age bin or height
            band is unknown, a pair repeats or is missing, a share is negative
            or not a number, or a row does not sum to one.
    """
    table = pd.read_csv(path)
    key = [AGE_BIN_COLUMN, HEIGHT_BAND_COLUMN]
    expected_columns = [*key, *WALL_TYPES]
    missing = [column for column in expected_columns if column not in table.columns]
    unknown = [column for column in table.columns if column not in expected_columns]
    if missing or unknown:
        msg = (
            f"The wall type shares table is missing the columns {missing} or has "
            f"unknown columns {unknown}."
        )
        raise ValueError(msg)
    unknown_bins = sorted(set(table[AGE_BIN_COLUMN]) - set(AGE_BINS))
    unknown_bands = sorted(set(table[HEIGHT_BAND_COLUMN]) - set(HEIGHT_BANDS))
    if unknown_bins or unknown_bands:
        msg = (
            f"Unknown age bins {unknown_bins} or height bands {unknown_bands} in "
            "the wall type shares table."
        )
        raise ValueError(msg)
    expected = pd.MultiIndex.from_product([AGE_BINS, HEIGHT_BANDS], names=key)
    held = pd.MultiIndex.from_frame(table[key])
    if held.has_duplicates or not expected.isin(held).all():
        msg = (
            "The wall type shares table must hold each (age_bin, height_band) pair "
            "exactly once."
        )
        raise ValueError(msg)
    shares = table.set_index(key).reindex(expected)[list(WALL_TYPES)].astype(float)
    values = shares.to_numpy()
    if not (np.isfinite(values).all() and (values >= 0).all()):
        msg = "Every wall type share must be a non-negative number."
        raise ValueError(msg)
    if not np.allclose(values.sum(axis=1), 1.0, rtol=0, atol=SHARE_SUM_TOLERANCE):
        msg = "Each row of the wall type shares table must sum to one."
        raise ValueError(msg)
    return shares


def load_beta_frontage_multipliers(
    path: Path = BETA_FRONTAGE_MULTIPLIERS_PATH,
) -> pd.Series:
    """Read the multiplier each wall type's share takes on a road frontage.

    Args:
        path: The CSV to read; the packaged table by default.

    Returns:
        The multipliers, indexed by wall type in :data:`WALL_TYPES` order.

    Raises:
        ValueError: If a column is missing, a wall type is unknown, repeated or
            missing, or a multiplier is not a positive number.
    """
    table = pd.read_csv(path)
    missing = [
        column
        for column in (WALL_TYPE_COLUMN, FRONTAGE_MULTIPLIER_COLUMN)
        if column not in table.columns
    ]
    if missing:
        msg = f"The frontage multipliers table is missing the columns {missing}."
        raise ValueError(msg)
    types = table[WALL_TYPE_COLUMN]
    unknown = sorted(set(types) - set(WALL_TYPES))
    if unknown or types.duplicated().any() or not set(WALL_TYPES) <= set(types):
        msg = (
            "The frontage multipliers table must hold each wall type in "
            f"{list(WALL_TYPES)} exactly once; unknown types {unknown}."
        )
        raise ValueError(msg)
    multipliers = (
        table.set_index(WALL_TYPE_COLUMN)[FRONTAGE_MULTIPLIER_COLUMN]
        .reindex(list(WALL_TYPES))
        .astype(float)
    )
    values = multipliers.to_numpy()
    if not (np.isfinite(values).all() and (values > 0).all()):
        msg = "Every road frontage multiplier must be a positive number."
        raise ValueError(msg)
    return multipliers


def _inverse_cdf(weights: np.ndarray, uniforms: np.ndarray) -> np.ndarray:
    """Return the column each row's uniform falls in, by its row of weights.

    Args:
        weights: Non-negative weights, one row per draw, each row positive in
            total.
        uniforms: One uniform on ``[0, 1)`` per row.

    Returns:
        The index of the column drawn per row. A column of zero weight is
        never drawn.
    """
    cdf = np.cumsum(weights, axis=1)
    cdf /= cdf[:, -1:]
    return (cdf <= uniforms[:, None]).sum(axis=1)


def _check_candidates(candidates: pd.DataFrame) -> None:
    """Refuse candidates the type draw cannot read.

    Args:
        candidates: The walls to draw a type for.

    Raises:
        ValueError: If a column is missing, a frontage flag is null, or a row
            of age shares is not non-negative and summing to one.
    """
    required = [HEIGHT_COLUMN, ROAD_FRONTAGE_COLUMN, *AGE_SHARE_COLUMNS]
    missing = [column for column in required if column not in candidates.columns]
    if missing:
        msg = f"The wall type draw is missing the columns {missing}."
        raise ValueError(msg)
    if candidates[ROAD_FRONTAGE_COLUMN].isna().any():
        msg = f"Every wall needs a {ROAD_FRONTAGE_COLUMN} flag."
        raise ValueError(msg)
    shares = candidates[list(AGE_SHARE_COLUMNS)].to_numpy(dtype=float)
    if not (
        np.isfinite(shares).all()
        and (shares >= 0).all()
        and np.allclose(shares.sum(axis=1), 1.0, rtol=0, atol=1e-6)
    ):
        msg = "Each wall's age shares must be non-negative and sum to one."
        raise ValueError(msg)


def draw_wall_types(
    candidates: pd.DataFrame,
    rng: np.random.Generator,
    shares: pd.DataFrame,
    multipliers: pd.Series,
    *,
    rebuilt_share: float = BETA_WALL_REBUILT_SHARE,
) -> pd.DataFrame:
    """Draw each wall's age bin and type.

    Three uniforms are drawn per wall in row order, so a wall's draw depends
    only on its own row and on the rows before it, never on rows added after.
    The first picks the age bin from the wall's age shares, the second moves it
    one bin later with probability ``rebuilt_share`` (``2005_on`` stays), and
    the third picks the type from the shares row for that bin and the wall's
    :func:`height_band`, times ``multipliers`` where the wall stands on a road
    frontage, renormalised.

    Args:
        candidates: One row per wall, with ``height_m`` (NaN allowed),
            ``on_road_frontage`` and the age shares in
            :data:`~landloss.exposure.rw.wall_age.AGE_SHARE_COLUMNS`.
        rng: The world's generator on :data:`WALL_TYPE_STREAM`.
        shares: The table :func:`load_beta_wall_type_shares` returns.
        multipliers: The series :func:`load_beta_frontage_multipliers`
            returns.
        rebuilt_share: The chance a wall moves to the next age bin.

    Returns:
        ``age_bin`` and ``wall_type`` per wall, on the candidates' index.

    Raises:
        ValueError: If the candidates cannot be read, ``rebuilt_share`` is not
            a probability, or the shares or multipliers do not cover every
            age bin, height band and wall type.
    """
    _check_candidates(candidates)
    if not 0 <= rebuilt_share <= 1:
        msg = f"rebuilt_share must lie in [0, 1], not {rebuilt_share}."
        raise ValueError(msg)
    expected = pd.MultiIndex.from_product([AGE_BINS, HEIGHT_BANDS])
    type_shares = shares.reindex(index=expected, columns=list(WALL_TYPES))
    factors = multipliers.reindex(list(WALL_TYPES)).to_numpy(dtype=float)
    if type_shares.isna().any().any() or np.isnan(factors).any():
        msg = (
            "The wall type shares and frontage multipliers must cover every age "
            "bin, height band and wall type."
        )
        raise ValueError(msg)

    uniforms = rng.random((len(candidates), 3))
    age_shares = candidates[list(AGE_SHARE_COLUMNS)].to_numpy(dtype=float)
    age_index = _inverse_cdf(age_shares, uniforms[:, 0])
    rebuilt = uniforms[:, 1] < rebuilt_share
    age_index = np.minimum(age_index + rebuilt, len(AGE_BINS) - 1)

    band_index = pd.Index(HEIGHT_BANDS).get_indexer(
        height_band(candidates[HEIGHT_COLUMN].to_numpy(dtype=float))
    )
    weights = type_shares.to_numpy(dtype=float)[
        age_index * len(HEIGHT_BANDS) + band_index
    ]
    on_frontage = candidates[ROAD_FRONTAGE_COLUMN].to_numpy(dtype=bool)
    weights[on_frontage] *= factors
    type_index = _inverse_cdf(weights, uniforms[:, 2])

    return pd.DataFrame(
        {
            AGE_BIN_COLUMN: np.array(AGE_BINS, dtype=object)[age_index],
            WALL_TYPE_COLUMN: np.array(WALL_TYPES, dtype=object)[type_index],
        },
        index=candidates.index,
    )
