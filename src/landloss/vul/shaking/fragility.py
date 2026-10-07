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

- **Retaining walls on flat land** take the wall type curve for their type
  and height class (under 2 m, or 2 m and over), its PGA median scaled by
  the wall's fill or cut position,
  from :func:`landloss.hazard.landslide.urban.wall_type_fragility.wall_type_curves`
  (``retaining-wall-type-fragility.csv``), converted to PGV by
  :func:`landloss.hazard.landslide.urban.fragility.pga_to_pgv_theta`.
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
from landloss.hazard.landslide.urban import wall_type_fragility

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

# The intensity measure the wall type curves are published on, and the one
# every evaluated fragility is on, defined once in the urban fragility module.
# PGV_IM is also the name of the PGV column the step writes.
PGA_IM = urban_fragility.PGA_IM
PGV_IM = urban_fragility.IM

# The columns the wall population carries that pick and shift the curve:
# the type and height (put in its height class by
# wall_type_fragility.height_class) pick it, the position shifts it. The size
# class is carried through for pricing and no longer picks the curve.
SIZE_CLASS_COLUMN = "size_class"
HEIGHT_M_COLUMN = "height_m"
WALL_TYPE_COLUMN = "wall_type"
WALL_POSITION_COLUMN = "wall_position"

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
    """Evaluate each wall's type curve at the PGV it saw.

    Per wall the curve is the table row for its ``wall_type`` and the height
    class of its ``height_m`` (:func:`wall_type_fragility.height_class`), the
    PGA median scaled by its ``wall_position`` (0.85 for
    fill, 1.15 for cut, 1 where unknown;
    :func:`wall_type_fragility.wall_type_curves`). The scaled PGA median is
    recorded and converted to PGV with :func:`urban_fragility.pga_to_pgv_theta`
    at the wall's PGV/PGA ratio, which is recorded too. The median is then
    :data:`WALL_AMP_FACTOR` and :data:`WALL_RATE_FACTOR`, both 1.0, applied as
    contract section 6 states, and the probability is the lognormal
    :func:`urban_fragility.lognormal_failure_probability` at ``pgv_m_s``.

    A wall whose PGV or converted median is NaN (off the grid, or no ratio)
    carries a NaN probability, which :func:`draw_damage_states` leaves
    undamaged; the step reports the count.

    Args:
        walls: One row per wall, carrying ``wall_type``, ``height_m`` and
            ``wall_position``.
        pgv_m_s: The PGV each wall saw, in m/s, in ``walls`` order.
        table: The wall type fragility table, as
            :func:`wall_type_fragility.load_wall_type_fragility` returns it.
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
            :func:`wall_type_fragility.wall_type_curves` if a wall's type and
            height class have no row or its position is neither fill, cut nor
            null.
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
    curves = wall_type_fragility.wall_type_curves(
        walls[WALL_TYPE_COLUMN],
        walls[HEIGHT_M_COLUMN],
        walls[WALL_POSITION_COLUMN],
        table,
    )
    theta_base_pga_g = curves["theta_pga_g"].to_numpy(dtype=float)
    beta = curves["beta"].to_numpy(dtype=float)
    source = curves["source"].to_numpy(dtype=object)
    theta_base = urban_fragility.pga_to_pgv_theta(theta_base_pga_g, ratio)
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
            PGV_PGA_RATIO_COLUMN: ratio,
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
