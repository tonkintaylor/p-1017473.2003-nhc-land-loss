"""Whether a land structure survives the shaking, or is written off.

Retaining walls, culverts and bridges carry **two damage states: no damage, and
replace**. Repair is not modelled, because very few damaged walls are repaired
in practice, so a third state would carry almost nothing.

A fragility is therefore a **curve returning the probability of failure at a
given ground motion**, and a damage state is a draw against that probability.
The probability is what a fragility is: nominally identical structures differ in
capacity, and any one of them responds variably to the same intensity, so the
curve is the distribution of that difference rather than a capacity to compare
against. It stays a probability however well the hazard is resolved.

Two fragilities live here.

- **Retaining walls on flat land** take the published wall curve for their
  size class and initial condition, read from ``retaining-wall-fragility.csv``
  through :mod:`landloss.hazard.landslide.urban.fragility`, which owns the
  table, the lognormal form and the conversion of a PGA-based median to PGV.
  :func:`wall_failure_probability` evaluates that curve at the PGV each wall
  saw, with no topographic amplification and no rate factor (contract section
  6 of ``.agents/plans/urban-slope-build-contract.md``). Walls on sloping land
  are not drawn here: they belong to the urban failure polygon on whose edge
  they stand, and landslide step 9 decides their fate.
- **Culverts and bridges** still take :data:`BETA_FAILURE_PROBABILITY`, one
  flat probability for every structure whatever its size, condition or the
  ground motion it saw -- a fragility curve flattened to a constant, not a
  different kind of thing.

:func:`draw_damage_states` takes probabilities rather than computing them, so
either fragility drops in without it changing.
"""

import numpy as np
import pandas as pd

from landloss.hazard.landslide.urban import fragility as urban_fragility

NO_DAMAGE = "no damage"
REPLACE = "replace"
DAMAGE_STATES = (NO_DAMAGE, REPLACE)

DAMAGE_STATE_COLUMN = "damage_state"

# The beta's stand-in for a fragility curve, now for culverts and bridges only:
# every structure fails with this probability, regardless of what it is, what
# condition it is in or how hard the ground shook. Replaced by published curves,
# at which point the probability becomes a function of the structure and its
# shaking rather than a constant.
BETA_FAILURE_PROBABILITY = 0.7

# A flat-land wall stands on no slope, so no topographic amplification divides
# its median, and the urban rate setting (which scales the urban failure
# fragilities, plan section 4.4) does not reach it: both factors are 1.0, and
# theta = theta_base / WALL_AMP_FACTOR * WALL_RATE_FACTOR is theta_base.
WALL_AMP_FACTOR = 1.0
WALL_RATE_FACTOR = 1.0

# The two values of the wall table's ``im`` column (contract section 8.1): the
# intensity measure a published curve is in, defined once in the urban
# fragility module. Every evaluated fragility is on PGV, so PGV_IM is also the
# name of the PGV column the step writes.
PGA_IM = urban_fragility.PGA_IM
PGV_IM = urban_fragility.IM

# The columns the wall population carries that index the curve.
SIZE_CLASS_COLUMN = "size_class"
INITIAL_CONDITION_COLUMN = "initial_condition"

# The columns wall_failure_probability returns, in contract order
# (section 3.11), repeated on the step 9 output.
THETA_BASE_PGA_G_COLUMN = "theta_base_pga_g"
PGV_PGA_RATIO_COLUMN = "pgv_pga_ratio_m_s_per_g"
THETA_COLUMN = "theta"
BETA_COLUMN = "beta"
FRAGILITY_SOURCE_COLUMN = "fragility_source"
FAILURE_PROBABILITY_COLUMN = "failure_probability"
WALL_FRAGILITY_COLUMNS = (
    THETA_BASE_PGA_G_COLUMN,
    PGV_PGA_RATIO_COLUMN,
    THETA_COLUMN,
    BETA_COLUMN,
    FRAGILITY_SOURCE_COLUMN,
    FAILURE_PROBABILITY_COLUMN,
)


def beta_failure_probability(count: int) -> np.ndarray:
    """Return the beta's flat failure probability for a set of structures.

    Args:
        count: How many structures to return a probability for.

    Returns:
        An array of :data:`BETA_FAILURE_PROBABILITY`.

    Raises:
        ValueError: If the count is negative.
    """
    if count < 0:
        msg = f"count must not be negative, got {count}"
        raise ValueError(msg)
    return np.full(count, BETA_FAILURE_PROBABILITY)


def wall_failure_probability(
    walls: pd.DataFrame,
    pgv_m_s: np.ndarray,
    table: pd.DataFrame,
    *,
    pgv_pga_ratio: pd.Series,
) -> pd.DataFrame:
    """Evaluate each wall's published curve at the PGV it saw.

    Per wall the curve is the table row for the unnamed wall class and the
    wall's ``size_class`` and ``initial_condition``
    (:func:`urban_fragility.wall_curve`). A row published on PGA is converted to
    PGV with :func:`urban_fragility.pga_to_pgv_theta` at the wall's PGV/PGA
    ratio, which is recorded; a PGV-native row records NaN for both the PGA
    median and the ratio. The median is then :data:`WALL_AMP_FACTOR` and
    :data:`WALL_RATE_FACTOR`, both 1.0, applied as contract section 6 states,
    and the probability is the lognormal
    :func:`urban_fragility.lognormal_failure_probability` at ``pgv_m_s``.

    A wall whose PGV or converted median is NaN (off the grid, or a PGA row
    with no ratio) carries a NaN probability, which
    :func:`draw_damage_states` leaves undamaged; the step reports the count.

    Args:
        walls: One row per wall, carrying ``size_class`` and
            ``initial_condition``.
        pgv_m_s: The PGV each wall saw, in m/s, in ``walls`` order.
        table: The wall fragility table, as
            :func:`urban_fragility.load_retaining_wall_fragility` returns it.
        pgv_pga_ratio: PGV (m/s) over PGA (g) at each wall, on ``walls.index``;
            NaN where none.

    Returns:
        A frame on ``walls.index`` with the columns of
        :data:`WALL_FRAGILITY_COLUMNS`: ``theta_base_pga_g``,
        ``pgv_pga_ratio_m_s_per_g``, ``theta`` (m/s), ``beta``,
        ``fragility_source`` (the table's ``source``) and
        ``failure_probability``.

    Raises:
        ValueError: If ``pgv_m_s`` is not one value per wall, or
            ``pgv_pga_ratio`` is not on ``walls.index``; and from
            :func:`urban_fragility.wall_curve` if a wall's size class and
            condition have no row.
    """
    pgv = np.asarray(pgv_m_s, dtype=float)
    if pgv.shape != (len(walls),):
        msg = f"pgv_m_s must carry one value per wall, got {pgv.shape} for {len(walls)}"
        raise ValueError(msg)
    if not pgv_pga_ratio.index.equals(walls.index):
        msg = "pgv_pga_ratio must be indexed as walls is"
        raise ValueError(msg)
    ratio = pgv_pga_ratio.to_numpy(dtype=float)

    count = len(walls)
    published_im = np.empty(count, dtype=object)
    published_theta = np.full(count, np.nan)
    beta = np.full(count, np.nan)
    source = np.empty(count, dtype=object)

    keys = walls[[SIZE_CLASS_COLUMN, INITIAL_CONDITION_COLUMN]]
    for (size_class, initial_condition), members in keys.groupby(
        [SIZE_CLASS_COLUMN, INITIAL_CONDITION_COLUMN], sort=False
    ).indices.items():
        curve = urban_fragility.wall_curve(
            table,
            wall_class=urban_fragility.UNNAMED_WALL_CLASS,
            size_class=size_class,
            initial_condition=initial_condition,
        )
        published_im[members] = curve["im"]
        published_theta[members] = float(curve["theta"])
        beta[members] = float(curve["beta"])
        source[members] = curve["source"]

    is_pga = published_im == PGA_IM
    theta_base_pga_g = np.where(is_pga, published_theta, np.nan)
    ratio_used = np.where(is_pga, ratio, np.nan)
    theta_base = published_theta.copy()
    if is_pga.any():
        theta_base[is_pga] = urban_fragility.pga_to_pgv_theta(
            published_theta[is_pga], ratio[is_pga]
        )
    theta = theta_base / WALL_AMP_FACTOR * WALL_RATE_FACTOR

    probability = np.full(count, np.nan)
    evaluable = np.isfinite(pgv) & np.isfinite(theta) & np.isfinite(beta)
    if evaluable.any():
        probability[evaluable] = urban_fragility.lognormal_failure_probability(
            pgv[evaluable], theta[evaluable], beta[evaluable]
        )

    return pd.DataFrame(
        {
            THETA_BASE_PGA_G_COLUMN: theta_base_pga_g,
            PGV_PGA_RATIO_COLUMN: ratio_used,
            THETA_COLUMN: theta,
            BETA_COLUMN: beta,
            FRAGILITY_SOURCE_COLUMN: source,
            FAILURE_PROBABILITY_COLUMN: probability,
        },
        index=walls.index,
    )


def draw_damage_states(
    failure_probability: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw a damage state per structure against its failure probability.

    Args:
        failure_probability: The probability each structure fails, 0 to 1;
            NaN where no probability could be evaluated, which draws no damage.
        rng: The generator for this realisation's vulnerability stream.

    Returns:
        :data:`NO_DAMAGE` or :data:`REPLACE` per structure.

    Raises:
        ValueError: If a probability falls outside 0 to 1.
    """
    probability = np.asarray(failure_probability, dtype=float)
    finite = probability[np.isfinite(probability)]
    if finite.size and (finite.min() < 0 or finite.max() > 1):
        msg = "failure probabilities must lie between 0 and 1"
        raise ValueError(msg)
    fails = rng.random(probability.shape) < probability
    return np.where(fails, REPLACE, NO_DAMAGE)
