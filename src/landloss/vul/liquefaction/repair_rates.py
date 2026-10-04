"""Repair rates for liquefied land, fitted to Canterbury.

The Canterbury rates are a cost per property per land damage state. To cost
liquefaction the way a claim report does -- from the ground lost -- the model
needs a rate per square metre of **inundated** land (clearing ejecta), a rate
per square metre of **evacuated** land (repairing cracked and spread ground),
and a **fixed cost per claim**, chosen so that the modelled cost per state
roughly reproduces the Canterbury table (**T-57**).

Four things about the fit shape what its rates are worth.

**Three parameters against the damaging states.** The fit is least squares on
the mean cost per state, unweighted, with all three held non-negative. It
cannot be exact, and how far each state misses is the test of whether the
evacuated and inundated ranges per state (**L-39**) are in proportion with what
Canterbury paid. The fixed cost is there because Minor has 1 m² evacuated and
nothing inundated, so no rate per square metre can price it; it stands for what
any claim costs -- assessment, getting a crew to site, small reinstatement --
whatever its area. State 1, None, is left out of the fit by the caller: it has
no ground lost, and would be priced at the fixed cost alone.

**The target is a mean, estimated from percentiles.** The packaged table carries
the 15th, 50th and 85th percentiles, not the mean. :func:`lognormal_mean` fits
a lognormal through the 50th and 85th and returns its mean. The 15th is left
out: it is $0 for state 1, and it is where the non-claimants' $0s pull the
table down. Mean costs from the source would replace the estimate (**T-66**).

**The basis is whatever the target's is.** Fitted against the current table the
rates are 2010/2011 dollars excluding GST, averaged over damaged properties with
non-claimants at $0 (**Q-17**). They are only consistent with the drop-out off;
refitted against claimant-only costs, they pair with the drop-out on.

**The inundated rate carries the Student Volunteer Army.** Canterbury's ejecta
was largely cleared by volunteers at no charge (**L-40**), so a rate fitted to
it understates clearing without them. :func:`area_repair_cost_nzd` takes a
multiplier on the inundated rate for that case, the no-SVA flag.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations

import numpy as np

# The standard normal quantile at the 85th percentile, so a lognormal's sigma
# is ln(p85 / p50) over this.
Z_85 = 1.0364333894937898

# Three parameters need at least three states to be fitted against.
MIN_STATES = 3


@dataclass(frozen=True)
class RepairRates:
    """What liquefied land costs to repair, on the basis of the fit's target.

    Attributes:
        inundated_nzd_per_m2: Clearing ejecta, per m² of inundated land.
        evacuated_nzd_per_m2: Repairing cracked and spread ground, per m².
        per_claim_nzd: Charged once on every claim, whatever its area.
    """

    inundated_nzd_per_m2: float
    evacuated_nzd_per_m2: float
    per_claim_nzd: float

    def __post_init__(self) -> None:
        """Refuse a negative rate.

        Raises:
            ValueError: If any rate is negative.
        """
        lowest = min(
            self.inundated_nzd_per_m2, self.evacuated_nzd_per_m2, self.per_claim_nzd
        )
        if lowest < 0:
            msg = f"repair rates must not be negative, got {self}"
            raise ValueError(msg)


def lognormal_mean(p50: float, p85: float) -> float:
    """Return the mean of the lognormal through a median and an 85th percentile.

    Args:
        p50: The median, positive.
        p85: The 85th percentile, at least the median.

    Returns:
        ``p50 * exp(sigma**2 / 2)``, where ``sigma = ln(p85 / p50) / z_85``.

    Raises:
        ValueError: If the median is not positive or the 85th is below it.
    """
    if p50 <= 0 or p85 < p50:
        msg = f"need 0 < p50 <= p85, got p50={p50}, p85={p85}"
        raise ValueError(msg)
    sigma = np.log(p85 / p50) / Z_85
    return float(p50 * np.exp(sigma**2 / 2))


def _nnls(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Solve least squares with every coefficient non-negative, exhaustively.

    Tries the unconstrained solution on every subset of the columns and keeps
    the best that comes out non-negative. Exact, and cheap for three columns.
    """
    best = np.zeros(a.shape[1])
    best_error = float(np.sum(b**2))
    for size in range(1, a.shape[1] + 1):
        for subset in combinations(range(a.shape[1]), size):
            columns = list(subset)
            x, *_ = np.linalg.lstsq(a[:, columns], b, rcond=None)
            if (x < 0).any():
                continue
            candidate = np.zeros(a.shape[1])
            candidate[columns] = x
            error = float(np.sum((a @ candidate - b) ** 2))
            if error < best_error:
                best, best_error = candidate, error
    return best


def fit_repair_rates(
    inundated_m2: Mapping[int, float],
    evacuated_m2: Mapping[int, float],
    target_nzd: Mapping[int, float],
) -> RepairRates:
    """Fit the repair rates to a mean cost per land damage state.

    Minimises ``sum over states of (r_i * inundated + r_e * evacuated + fixed -
    target)**2`` with all three non-negative.

    Args:
        inundated_m2: The mean inundated area of a claim, per state.
        evacuated_m2: The mean evacuated area of a claim, per state.
        target_nzd: The mean cost of a claim to reproduce, per state.

    Returns:
        The fitted rates, on the target's basis.

    Raises:
        ValueError: If the three mappings do not cover the same states, fewer
            than three states are given, or no state carries any area.
    """
    states = sorted(target_nzd)
    if set(inundated_m2) != set(states) or set(evacuated_m2) != set(states):
        msg = "inundated, evacuated and target must cover the same states"
        raise ValueError(msg)
    if len(states) < MIN_STATES:
        msg = f"three parameters need at least {MIN_STATES} states, got {states}"
        raise ValueError(msg)
    a = np.array([[inundated_m2[s], evacuated_m2[s], 1.0] for s in states], dtype=float)
    b = np.array([target_nzd[s] for s in states], dtype=float)
    if not (a[:, :2] > 0).any():
        msg = "no state carries any inundated or evacuated area to fit against"
        raise ValueError(msg)
    inundated, evacuated, fixed = _nnls(a, b)
    return RepairRates(float(inundated), float(evacuated), float(fixed))


def area_repair_cost_nzd(
    evacuated_m2: np.ndarray,
    inundated_m2: np.ndarray,
    claimed: np.ndarray,
    rates: RepairRates,
    *,
    inundated_multiplier: float = 1.0,
) -> np.ndarray:
    """Return the repair cost of liquefied land from the ground it lost.

    Args:
        evacuated_m2: The evacuated area per property.
        inundated_m2: The inundated area per property.
        claimed: Whether each property makes a liquefaction claim; the fixed
            cost is charged only where it does.
        rates: The repair rates.
        inundated_multiplier: Applied to the inundated rate; above 1 where
            ejecta is cleared without volunteer labour (the no-SVA flag).

    Returns:
        ``evacuated * r_e + inundated * r_i * multiplier + fixed`` per claim,
        and zero where there is no claim, on the rates' basis.

    Raises:
        ValueError: If the multiplier is negative.
    """
    if inundated_multiplier < 0:
        msg = f"inundated_multiplier must not be negative, got {inundated_multiplier}"
        raise ValueError(msg)
    evacuated = np.asarray(evacuated_m2, dtype=float)
    inundated = np.asarray(inundated_m2, dtype=float)
    cost = (
        evacuated * rates.evacuated_nzd_per_m2
        + inundated * rates.inundated_nzd_per_m2 * inundated_multiplier
        + rates.per_claim_nzd
    )
    return np.where(np.asarray(claimed, dtype=bool), cost, 0.0)
