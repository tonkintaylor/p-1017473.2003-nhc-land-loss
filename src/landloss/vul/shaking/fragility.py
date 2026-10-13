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
  under 2 m, its PGA median scaled by the wall's height (0.85 at 2 m and
  over) and fill or cut position,
  from :func:`landloss.hazard.landslide.urban.wall_type_fragility.wall_type_curves`
  (``retaining-wall-type-fragility.csv``).
  :func:`wall_failure_probability` evaluates that curve at the site PGA each
  wall saw, with no topographic amplification and no rate factor (contract
  section 6 of ``.agents/plans/urban-slope-build-contract.md``; on PGA since
  2026-10-12, as the urban slope model is). Walls on sloping land
  are not drawn here: they belong to the urban failure polygon on whose edge
  they stand, and landslide step 6 decides their fate.
- **Culverts and bridges** take the chance for their property's liquefaction
  land damage state, :func:`crossing_failure_probability` (T-36): nought on
  land that did not liquefy and off the liquefaction grid, rising to 40% at the
  worst states. Shaking alone does not break a buried crossing; the ground
  moving around it does. Landslides break them separately, in vul step 11.

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

# The beta's stand-in for a fragility curve: every structure fails with this
# probability, regardless of what it is, what condition it is in or how hard
# the ground shook. Culverts and bridges took it until T-36 replaced it with
# CROSSING_REPLACEMENT_BY_LD_STATE; it is kept as the plainest probability to
# test draw_damage_states against.
BETA_FAILURE_PROBABILITY = 0.7

# The chance a culvert or bridge on flat land is fully replaced, by its
# property's liquefaction land damage state (T-36, John Leeves and Virginie
# Lacrosse, 2026-10-13). A buried crossing is broken by the ground moving
# around it -- lateral spreading towards the channel it crosses, settlement,
# flotation -- rather than by the shaking itself, so the land damage state is
# what its chance follows. State 1, no land damage, cannot break it.
CROSSING_REPLACEMENT_BY_LD_STATE = {
    1: 0.0,
    2: 0.01,
    3: 0.05,
    4: 0.20,
    5: 0.40,
    6: 0.40,
}

# A flat-land wall stands on no slope, so no topographic amplification divides
# its median, and the urban rate setting (which scales the urban failure
# fragilities, plan section 4.4) does not reach it: both factors are 1.0, and
# theta = theta_base / WALL_AMP_FACTOR * WALL_RATE_FACTOR is theta_base.
WALL_AMP_FACTOR = 1.0
WALL_RATE_FACTOR = 1.0

# The intensity measure the wall type curves are published on and every
# evaluated fragility is on, site PGA in g, defined once in the urban
# fragility module. It is also the name of the PGA column the step writes.
PGA_IM = urban_fragility.IM

# The columns the wall population carries that pick and shift the curve:
# the type picks it, the height (wall_type_fragility.height_factor) and the
# position shift it. The size
# class is carried through for pricing and no longer picks the curve.
SIZE_CLASS_COLUMN = "size_class"
HEIGHT_M_COLUMN = "height_m"
WALL_TYPE_COLUMN = "wall_type"
WALL_POSITION_COLUMN = "wall_position"

# The columns wall_failure_probability returns, in contract order
# (section 3.11), repeated on the step 9 output.
THETA_BASE_COLUMN = "theta_base"
THETA_COLUMN = "theta"
BETA_COLUMN = "beta"
FRAGILITY_SOURCE_COLUMN = "fragility_source"
FAILURE_PROBABILITY_COLUMN = "failure_probability"
WALL_FRAGILITY_COLUMNS = (
    THETA_BASE_COLUMN,
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


def crossing_failure_probability(ld_state: np.ndarray | pd.Series) -> np.ndarray:
    """Return each culvert or bridge's chance of replacement, from its land.

    The chance for its property's liquefaction land damage state, from
    :data:`CROSSING_REPLACEMENT_BY_LD_STATE`. A crossing with no state stands
    on land off the liquefaction grid -- hill land -- and liquefaction cannot
    break it, so its chance is nought; a landslide can still, which vul step 11
    flags on its own.

    Args:
        ld_state: The land damage state, 1 to 6, missing off the grid.

    Returns:
        The probability per crossing.

    Raises:
        ValueError: If a state is outside 1 to 6.
    """
    states = pd.Series(ld_state, dtype="Float64")
    known = states.notna()
    unknown = sorted(
        set(states[known].astype(int)) - set(CROSSING_REPLACEMENT_BY_LD_STATE)
    )
    if unknown:
        msg = f"land damage states must be 1 to 6, got {unknown}"
        raise ValueError(msg)
    probability = states.map(CROSSING_REPLACEMENT_BY_LD_STATE, na_action="ignore")
    return probability.fillna(0.0).to_numpy(dtype=float)


def wall_failure_probability(
    walls: pd.DataFrame,
    pga_g: np.ndarray,
    table: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate each wall's type curve at the site PGA it saw.

    Per wall the curve is the table row for its ``wall_type``, the PGA
    median scaled by its ``height_m``
    (:func:`wall_type_fragility.height_factor`) and its ``wall_position`` (0.85 for
    fill, 1.15 for cut, 1 where unknown;
    :func:`wall_type_fragility.wall_type_curves`), recorded as
    ``theta_base``. The median is then :data:`WALL_AMP_FACTOR` and
    :data:`WALL_RATE_FACTOR`, both 1.0, applied as contract section 6 states,
    and the probability is the lognormal
    :func:`urban_fragility.lognormal_failure_probability` at ``pga_g``.

    A wall whose PGA is NaN (off the grid) carries a NaN probability, which
    :func:`draw_damage_states` leaves undamaged; the step reports the count.

    Args:
        walls: One row per wall, carrying ``wall_type``, ``height_m`` and
            ``wall_position``.
        pga_g: The site PGA each wall saw, in g, in ``walls`` order.
        table: The wall type fragility table, as
            :func:`wall_type_fragility.load_wall_type_fragility` returns it.

    Returns:
        A frame on ``walls.index`` with the columns of
        :data:`WALL_FRAGILITY_COLUMNS`: ``theta_base`` and ``theta`` (g),
        ``beta``,
        ``fragility_source`` (the table's ``source``) and
        ``failure_probability``.

    Raises:
        ValueError: If ``pga_g`` is not one value per wall; and from
            :func:`wall_type_fragility.wall_type_curves` if a wall's type has
            no row or its position is neither fill, cut nor null.
    """
    pga = np.asarray(pga_g, dtype=float)
    if pga.shape != (len(walls),):
        msg = f"pga_g must carry one value per wall, got {pga.shape} for {len(walls)}"
        raise ValueError(msg)

    count = len(walls)
    curves = wall_type_fragility.wall_type_curves(
        walls[WALL_TYPE_COLUMN],
        walls[HEIGHT_M_COLUMN],
        walls[WALL_POSITION_COLUMN],
        table,
    )
    theta_base = curves["theta_pga_g"].to_numpy(dtype=float)
    beta = curves["beta"].to_numpy(dtype=float)
    source = curves["source"].to_numpy(dtype=object)
    theta = theta_base / WALL_AMP_FACTOR * WALL_RATE_FACTOR

    probability = np.full(count, np.nan)
    evaluable = np.isfinite(pga) & np.isfinite(theta) & np.isfinite(beta)
    if evaluable.any():
        probability[evaluable] = urban_fragility.lognormal_failure_probability(
            pga[evaluable], theta[evaluable], beta[evaluable]
        )

    return pd.DataFrame(
        {
            THETA_BASE_COLUMN: theta_base,
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
