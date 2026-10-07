"""Retaining wall fragility by wall type, stored as two PGA percentiles.

Confirmed by the project lead (2026-10-06). The model reads this table for
every drawn wall: :func:`wall_type_curves` gives the curve that
:func:`landloss.hazard.landslide.urban.fragility.assign_fragility` (walls on
sloping land) and :func:`landloss.vul.shaking.fragility.wall_failure_probability`
(walls on flat land) convert to PGV. It replaced the one curve per size class
and condition (``.agents/plans/assigning-retaining-wall-types.md``).

Each wall type has one curve per height class, not per size class (the lead,
2026-10-07): a wall under 2 m high is ``under_2_m`` and one 2 m or higher is
``2_m_and_over`` (:func:`height_class`; a wall whose height is not known is
``under_2_m``). Which published wall height each class takes depends on the
type. For gravity masonry, old timber pole, block or RC cantilever and
landscaper timber the published height effect is switched: taller walls of
these types are the worse, so ``under_2_m`` takes the 6 m wall and
``2_m_and_over`` the 3 m wall. Crib, new timber pole and engineered modern have
no height effect and take the 3 m wall for both. ``size_class`` stays on every
wall for pricing; only this lookup uses the height class.

Replacement is read at the **moderate** damage state, not the most severe,
because moderate damage usually leads to a full replacement in a claim (the
lead, 2026-10-06).

Each curve is stored as the PGA at which 15% and 50% of walls are replaced
(``p15`` and ``p50``) rather than as a median and dispersion, because two
points on the curve are easier to read, compare and adjust by judgement than a
log-standard deviation. They are turned back into a lognormal CDF on loading:
``theta = p50`` and ``beta = ln(p50 / p15) / -Phi^-1(0.15)``
(:func:`percentiles_to_lognormal`).

The wall's position shifts its curve. A wall retaining fill is weaker and a
wall retaining a cut is stronger, so both percentiles are scaled by
:data:`FILL_CAPACITY_FACTOR` or :data:`CUT_CAPACITY_FACTOR` (the lead,
2026-10-06). Scaling both by one factor moves the median and keeps the
dispersion. A wall whose position is not known keeps the stored curve.

The packaged rows are read out of [koutsoupaki_2023], DS2 (5% of H), each
type on one initial-condition rung and some then scaled by ``type_factor``
(1.3 for new timber pole, 1.5 for engineered modern); the README beside the
CSV says how, and ``src/scripts/landloss/vul/research/fig_rw_type_fragility.md``
sets them beside the other published curves and the Canterbury failure shares.
"""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import norm

from landloss.exposure.rw.lines import CUT, FILL
from landloss.hazard.landslide.urban.lognormal import (
    PGA_IM,
    lognormal_failure_probability,
)
from landloss.io import ASSETS_DIR

WALL_TYPE_FRAGILITY_PATH = ASSETS_DIR / "retaining-wall-type-fragility.csv"

# The proposed wall types, oldest-style first, as named in the table.
WALL_TYPES = (
    "gravity_masonry",
    "crib",
    "timber_pole_old",
    "block_rc_cantilever",
    "timber_pole_new",
    "landscaper_timber",
    "engineered_modern",
)

# The two height classes a wall's curve is chosen by (the lead, 2026-10-07),
# shorter first: below HEIGHT_CLASS_SPLIT_M, or of unknown height, and at or
# above it.
HEIGHT_CLASSES = ("under_2_m", "2_m_and_over")
HEIGHT_CLASS_SPLIT_M = 2.0

# The two stored percentiles: the probabilities of replacement they are the
# PGA for.
LOWER_PERCENTILE = 0.15
MEDIAN_PERCENTILE = 0.5

# The standard normal quantile of LOWER_PERCENTILE, about -1.036: the number of
# dispersions p15 lies below the median in log space.
LOWER_Z = float(norm.ppf(LOWER_PERCENTILE))

# How much a wall's position scales both percentiles (the lead, 2026-10-06): a
# fill wall reaches each probability at 15% less PGA, a cut wall at 15% more.
FILL_CAPACITY_FACTOR = 0.85
CUT_CAPACITY_FACTOR = 1.15
POSITION_FACTORS = {FILL: FILL_CAPACITY_FACTOR, CUT: CUT_CAPACITY_FACTOR}

TABLE_COLUMNS = (
    "wall_type",
    "height_class",
    "im",
    "p15",
    "p50",
    "published_height_m",
    "published_fs",
    "type_factor",
    "height_effect",
    "damage_state",
    "source",
    "basis",
)
TABLE_KEY = ("wall_type", "height_class")


def height_class(height_m: pd.Series) -> pd.Series:
    """Return each wall's height class, the key its curve is looked up by.

    Args:
        height_m: Each wall's height in metres; null where it is not known.

    Returns:
        ``under_2_m`` below :data:`HEIGHT_CLASS_SPLIT_M` or where the height is
        not known, ``2_m_and_over`` at or above it, on the index of
        ``height_m``.
    """
    heights = pd.to_numeric(height_m, errors="coerce").to_numpy(dtype=float)
    shorter, taller = HEIGHT_CLASSES
    return pd.Series(
        np.where(heights >= HEIGHT_CLASS_SPLIT_M, taller, shorter),
        index=height_m.index,
        name="height_class",
    )


def percentiles_to_lognormal(
    p15: npt.ArrayLike, p50: npt.ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """Return the lognormal median and dispersion through two percentiles.

    Args:
        p15: The intensity at which 15% of walls are replaced.
        p50: The intensity at which half are, above ``p15``.

    Returns:
        ``(theta, beta)``: the median, which is ``p50``, and the dispersion.

    Raises:
        ValueError: If a percentile is not positive or ``p15`` is not below
            ``p50``.
    """
    lower = np.asarray(p15, dtype=float)
    median = np.asarray(p50, dtype=float)
    if np.any(~(lower > 0)) or np.any(~(lower < median)):
        msg = "Each p15 must be positive and below its p50."
        raise ValueError(msg)
    return median, np.log(lower / median) / LOWER_Z


def lognormal_to_percentiles(
    theta: npt.ArrayLike, beta: npt.ArrayLike
) -> tuple[np.ndarray, np.ndarray]:
    """Return the intensities at which 15% and 50% of walls are replaced.

    The inverse of :func:`percentiles_to_lognormal`, for turning a published
    median and dispersion into the stored form.

    Args:
        theta: The lognormal median.
        beta: The lognormal dispersion, positive.

    Returns:
        ``(p15, p50)``.
    """
    median = np.asarray(theta, dtype=float)
    return median * np.exp(LOWER_Z * np.asarray(beta, dtype=float)), median


def position_factor(wall_position: pd.Series) -> np.ndarray:
    """Return the factor each wall's position scales its percentiles by.

    Args:
        wall_position: ``fill``, ``cut``, or null where it is not known.

    Returns:
        :data:`FILL_CAPACITY_FACTOR`, :data:`CUT_CAPACITY_FACTOR`, or 1.

    Raises:
        ValueError: If a position is neither fill, cut nor null.
    """
    known = wall_position.dropna()
    unknown = sorted(set(known) - set(POSITION_FACTORS))
    if unknown:
        msg = f"Unknown wall position {unknown}; expected {sorted(POSITION_FACTORS)}."
        raise ValueError(msg)
    return wall_position.map(POSITION_FACTORS).fillna(1.0).to_numpy(dtype=float)


def load_wall_type_fragility(path: Path = WALL_TYPE_FRAGILITY_PATH) -> pd.DataFrame:
    """Read the wall type fragility, with its lognormal form added.

    Args:
        path: The CSV to read; the packaged table by default.

    Returns:
        One row per ``(wall_type, height_class)``, carrying the stored columns
        and ``theta`` and ``beta`` from :func:`percentiles_to_lognormal`.

    Raises:
        ValueError: If a column is missing, a pair repeats or is missing, a
            wall type or height class is unknown, an ``im`` is not PGA, or the
            percentiles are not ordered.
    """
    table = pd.read_csv(path)
    missing = [column for column in TABLE_COLUMNS if column not in table.columns]
    if missing:
        msg = f"The wall type fragility table is missing the columns {missing}."
        raise ValueError(msg)
    unknown_types = sorted(set(table["wall_type"]) - set(WALL_TYPES))
    unknown_heights = sorted(set(table["height_class"]) - set(HEIGHT_CLASSES))
    if unknown_types or unknown_heights:
        msg = (
            f"Unknown wall types {unknown_types} or height classes "
            f"{unknown_heights} in the wall type fragility table."
        )
        raise ValueError(msg)
    expected = pd.MultiIndex.from_product([WALL_TYPES, HEIGHT_CLASSES])
    held = pd.MultiIndex.from_frame(table[list(TABLE_KEY)])
    if held.has_duplicates or not expected.isin(held).all():
        msg = (
            "The wall type fragility table must hold each "
            "(wall_type, height_class) pair exactly once."
        )
        raise ValueError(msg)
    if not (table["im"] == PGA_IM).all():
        msg = f"Every curve in the wall type fragility table must be on {PGA_IM}."
        raise ValueError(msg)
    table["theta"], table["beta"] = percentiles_to_lognormal(table["p15"], table["p50"])
    return table


def wall_type_curves(
    wall_type: pd.Series,
    height_m: pd.Series,
    wall_position: pd.Series,
    table: pd.DataFrame,
) -> pd.DataFrame:
    """Return each wall's lognormal curve on PGA, shifted by its position.

    Args:
        wall_type: Each wall's type, one of :data:`WALL_TYPES`.
        height_m: Each wall's height in metres, on the same index; put in its
            height class by :func:`height_class` (null is ``under_2_m``).
        wall_position: ``fill``, ``cut`` or null, scaling the median
            (:func:`position_factor`), on the same index.
        table: The table :func:`load_wall_type_fragility` returns.

    Returns:
        One row per wall on the index of ``wall_type``: ``theta_pga_g``, the
        table's median times the position factor, ``beta`` and ``source``.

    Raises:
        ValueError: If ``height_m`` or ``wall_position`` is not on the index
            of ``wall_type``, or a wall's ``(wall_type, height_class)`` is not
            in the table.
    """
    # The three are paired by position below, so a different index (or a
    # length-1 series that would broadcast) would put a curve on the wrong wall.
    if not (
        wall_type.index.equals(height_m.index)
        and wall_type.index.equals(wall_position.index)
    ):
        msg = (
            "wall_type, height_m and wall_position must share one index to be "
            "paired wall by wall."
        )
        raise ValueError(msg)
    curves = table.set_index(list(TABLE_KEY))
    keys = pd.MultiIndex.from_arrays(
        [wall_type.to_numpy(), height_class(height_m).to_numpy()]
    )
    absent = ~keys.isin(curves.index)
    if absent.any():
        msg = f"No wall type curve for {sorted(set(keys[absent]))}."
        raise ValueError(msg)
    picked = curves.loc[keys]
    theta = picked["theta"].to_numpy(dtype=float) * position_factor(wall_position)
    return pd.DataFrame(
        {
            "theta_pga_g": theta,
            "beta": picked["beta"].to_numpy(dtype=float),
            "source": picked["source"].to_numpy(),
        },
        index=wall_type.index,
    )


def wall_type_failure_probability(
    pga_g: npt.ArrayLike,
    wall_type: pd.Series,
    height_m: pd.Series,
    wall_position: pd.Series,
    table: pd.DataFrame,
) -> np.ndarray:
    """Return each wall's probability of replacement at the PGA it saw.

    Args:
        pga_g: The free-field PGA at each wall, in g.
        wall_type: Each wall's type, one of :data:`WALL_TYPES`.
        height_m: Each wall's height in metres, put in its height class by
            :func:`height_class`.
        wall_position: ``fill``, ``cut`` or null, scaling the curve
            (:func:`position_factor`).
        table: The table :func:`load_wall_type_fragility` returns.

    Returns:
        The probabilities, aligned to the inputs.

    Raises:
        ValueError: If the three series do not share one index, or a wall's
            ``(wall_type, height_class)`` is not in the table.
    """
    curves = wall_type_curves(wall_type, height_m, wall_position, table)
    return lognormal_failure_probability(
        np.asarray(pga_g, dtype=float),
        curves["theta_pga_g"].to_numpy(dtype=float),
        curves["beta"].to_numpy(dtype=float),
    )
