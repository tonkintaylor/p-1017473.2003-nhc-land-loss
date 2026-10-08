"""Repair rates for liquefied land, fitted to Canterbury.

The Canterbury rates are a cost per property per land damage state. To cost
liquefaction the way a claim report does -- from the ground lost -- the model
needs a rate per square metre of **inundated** land (clearing ejecta), a rate
per square metre of **evacuated** land (repairing cracked and spread ground),
and a **fixed cost per claim**, chosen so that the modelled cost per state
roughly reproduces the Canterbury table (**T-57**).

Five things about the fit shape what its rates are worth.

**Three parameters against six states.** The fit is least squares on the mean
cost per state, optionally weighted (by claim count, in step 3), with all three
held non-negative. It cannot be exact, and how far each state misses is the
test of whether the evacuated and inundated ranges per state (**L-39**) are in
proportion with what Canterbury paid. The fixed cost is there because None and
Minor lose little or no ground, so no rate per square metre can price them; it
stands for what any claim costs -- assessment, getting a crew to site, small
reinstatement -- whatever its area. None, with no ground lost, anchors it.

**The target is the claimant-only cost per state**
(:func:`landloss.vul.liquefaction.costs.load_claimant_costs`, since 2026-10-08,
**T-65**). Before that it was estimated from the 50th and 85th percentiles of a
table averaging over non-claimants at $0, by :func:`lognormal_mean`, which is
kept for comparison.

**The basis is whatever the target's is**: 2010/2011 dollars excluding GST,
before the excess, per claim. Claimant-only, so the rates pair with the
drop-out on.

**The per-claim cost varies between claims; the rates do not.** Canterbury's
claims are right-skewed within every state -- the median well below the mean --
and None claims, which lose no ground, still run from about $470 to $1,030
between the quartiles. Ground lost cannot carry that, so each claim's fixed cost
is multiplied by a lognormal draw with a mean of one, whose sigma is fitted to
the Canterbury quartiles (:func:`fit_per_claim_sigma`) after the rates are
fitted to the means. A mean of one leaves the means where the rates put them.
The quartiles are a calibration target only, never an input (Maxim Millen,
2026-10-08): the model draws from its own lognormal, not from Canterbury's
claims.

**The inundated rate carries the Student Volunteer Army.** Canterbury's ejecta
was largely cleared by volunteers at no charge (**L-40**), so a rate fitted to
it understates clearing without them. :func:`area_repair_cost_nzd` takes a
multiplier on the inundated rate for that case, the no-SVA flag.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import norm

# The standard normal quantile at the 85th percentile, so a lognormal's sigma
# is ln(p85 / p50) over this.
Z_85 = 1.0364333894937898

# Three parameters need at least three states to be fitted against.
MIN_STATES = 3

# The quartiles the spread of the per-claim cost is fitted to, as fractions.
QUARTILES = (0.25, 0.5, 0.75)
# How many points of the standard normal stand in for the per-claim draw when
# the modelled quartiles are worked out: evenly spaced in probability, so the
# fit is deterministic and needs no generator.
QUANTILE_POINTS = 401
# The widest spread the fit may choose. A sigma of 3 puts the median per-claim
# cost at 1% of its mean, far past anything Canterbury paid.
MAX_SIGMA = 3.0


@dataclass(frozen=True)
class RepairRates:
    """What liquefied land costs to repair, on the basis of the fit's target.

    Attributes:
        inundated_nzd_per_m2: Clearing ejecta, per m² of inundated land.
        evacuated_nzd_per_m2: Repairing cracked and spread ground, per m².
        per_claim_nzd: Charged once on every claim, whatever its area: the
            mean of the per-claim cost.
        per_claim_sigma: The spread of the per-claim cost between claims, the
            sigma of the lognormal multiplier with a mean of one it is drawn
            with. Zero charges every claim exactly ``per_claim_nzd``.
    """

    inundated_nzd_per_m2: float
    evacuated_nzd_per_m2: float
    per_claim_nzd: float
    per_claim_sigma: float = 0.0

    def __post_init__(self) -> None:
        """Refuse a negative rate or spread.

        Raises:
            ValueError: If any rate, or the spread, is negative.
        """
        lowest = min(
            self.inundated_nzd_per_m2,
            self.evacuated_nzd_per_m2,
            self.per_claim_nzd,
            self.per_claim_sigma,
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
    weights: Mapping[int, float] | None = None,
) -> RepairRates:
    """Fit the repair rates to a mean cost per land damage state.

    Minimises ``sum over states of w * (r_i * inundated + r_e * evacuated +
    fixed - target)**2`` with all three non-negative.

    Args:
        inundated_m2: The mean inundated area of a claim, per state.
        evacuated_m2: The mean evacuated area of a claim, per state.
        target_nzd: The mean cost of a claim to reproduce, per state.
        weights: How much each state counts, such as its claim count. None
            weights every state the same.

    Returns:
        The fitted rates, on the target's basis.

    Raises:
        ValueError: If the three mappings do not cover the same states, fewer
            than three states are given, no state carries any area, or a weight
            is negative or missing.
    """
    states = sorted(target_nzd)
    if set(inundated_m2) != set(states) or set(evacuated_m2) != set(states):
        msg = "inundated, evacuated and target must cover the same states"
        raise ValueError(msg)
    if weights is not None and set(weights) != set(states):
        msg = "weights must cover the same states as the target"
        raise ValueError(msg)
    if len(states) < MIN_STATES:
        msg = f"three parameters need at least {MIN_STATES} states, got {states}"
        raise ValueError(msg)
    a = np.array([[inundated_m2[s], evacuated_m2[s], 1.0] for s in states], dtype=float)
    b = np.array([target_nzd[s] for s in states], dtype=float)
    if not (a[:, :2] > 0).any():
        msg = "no state carries any inundated or evacuated area to fit against"
        raise ValueError(msg)
    if weights is not None:
        w = np.array([weights[s] for s in states], dtype=float)
        if (w < 0).any():
            msg = f"weights must not be negative, got {dict(weights)}"
            raise ValueError(msg)
        # Weighted least squares: scale each row by the root of its weight.
        root = np.sqrt(w)
        a, b = a * root[:, None], b * root
    inundated, evacuated, fixed = _nnls(a, b)
    return RepairRates(float(inundated), float(evacuated), float(fixed))


def lognormal_multiplier(z: np.ndarray, sigma: float) -> np.ndarray:
    """Return the lognormal multiplier with a mean of one at standard normals.

    Args:
        z: Standard normal values, drawn or chosen.
        sigma: The spread, non-negative.

    Returns:
        ``exp(sigma * z - sigma**2 / 2)``, whose mean over the normal is one.
    """
    return np.exp(sigma * np.asarray(z, dtype=float) - sigma**2 / 2)


def modelled_quartiles(
    area_cost_nzd: np.ndarray, per_claim_nzd: float, per_claim_sigma: float
) -> np.ndarray:
    """Return the quartiles of the cost of a set of claims, the draw integrated.

    Each claim's cost is its area cost plus the per-claim cost times the
    lognormal multiplier. The multiplier is stood in for by
    :data:`QUANTILE_POINTS` points of the normal evenly spaced in probability,
    so the answer is the same every time.

    Args:
        area_cost_nzd: The cost of each claim's ground lost, before the
            per-claim cost.
        per_claim_nzd: The mean per-claim cost.
        per_claim_sigma: Its spread.

    Returns:
        The lower quartile, median and upper quartile, in that order.
    """
    probabilities = (np.arange(QUANTILE_POINTS) + 0.5) / QUANTILE_POINTS
    per_claim = per_claim_nzd * lognormal_multiplier(
        norm.ppf(probabilities), per_claim_sigma
    )
    costs = np.asarray(area_cost_nzd, dtype=float)[:, None] + per_claim[None, :]
    return np.quantile(costs, QUARTILES)


def fit_per_claim_sigma(
    area_cost_nzd: Mapping[int, np.ndarray],
    per_claim_nzd: float,
    target_quartiles: Mapping[int, np.ndarray],
    weights: Mapping[int, float] | None = None,
) -> float:
    """Fit the spread of the per-claim cost to quartiles of cost per state.

    Minimises ``sum over states of w * sum over quartiles of
    ln(modelled / target)**2``: in logs, so a miss in the lower quartile counts
    as much as the same proportional miss in the upper. The spread has a mean
    of one, so the fit does not move the mean cost of any state.

    Args:
        area_cost_nzd: The cost of the ground lost by each modelled claim, per
            state.
        per_claim_nzd: The mean per-claim cost, already fitted.
        target_quartiles: The lower quartile, median and upper quartile to
            reproduce, per state.
        weights: How much each state counts, such as its claim count. None
            weights every state the same.

    Returns:
        The fitted sigma, from 0 to :data:`MAX_SIGMA`.

    Raises:
        ValueError: If the mappings do not cover the same states, a state has
            no claims, or a target quartile is not positive.
    """
    states = sorted(target_quartiles)
    if set(area_cost_nzd) != set(states):
        msg = "area costs and target quartiles must cover the same states"
        raise ValueError(msg)
    if weights is not None and set(weights) != set(states):
        msg = "weights must cover the same states as the target"
        raise ValueError(msg)
    if any(len(area_cost_nzd[s]) == 0 for s in states):
        msg = "every state fitted needs at least one modelled claim"
        raise ValueError(msg)
    targets = {s: np.asarray(target_quartiles[s], dtype=float) for s in states}
    if any((t <= 0).any() for t in targets.values()):
        msg = "target quartiles must be positive"
        raise ValueError(msg)
    w = {s: 1.0 if weights is None else float(weights[s]) for s in states}

    def miss(sigma: float) -> float:
        total = 0.0
        for s in states:
            modelled = modelled_quartiles(area_cost_nzd[s], per_claim_nzd, sigma)
            total += w[s] * float(np.sum(np.log(modelled / targets[s]) ** 2))
        return total

    result = minimize_scalar(miss, bounds=(0.0, MAX_SIGMA), method="bounded")
    return float(result.x)


def area_repair_cost_nzd(
    evacuated_m2: np.ndarray,
    inundated_m2: np.ndarray,
    claimed: np.ndarray,
    rates: RepairRates,
    *,
    inundated_multiplier: float = 1.0,
    rng: np.random.Generator | None = None,
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
        rng: Draws each claim's per-claim cost when the rates carry a spread.
            Needed only then.

    Returns:
        ``evacuated * r_e + inundated * r_i * multiplier + fixed * m`` per
        claim, ``m`` the lognormal multiplier with a mean of one (one where
        there is no spread), and zero where there is no claim, on the rates'
        basis.

    Raises:
        ValueError: If the multiplier is negative, or the rates carry a spread
            and no generator is given.
    """
    if inundated_multiplier < 0:
        msg = f"inundated_multiplier must not be negative, got {inundated_multiplier}"
        raise ValueError(msg)
    if rates.per_claim_sigma > 0 and rng is None:
        msg = "the per-claim cost has a spread, so a generator is needed to draw it"
        raise ValueError(msg)
    evacuated = np.asarray(evacuated_m2, dtype=float)
    inundated = np.asarray(inundated_m2, dtype=float)
    per_claim = np.full(evacuated.shape, rates.per_claim_nzd)
    if rates.per_claim_sigma > 0:
        per_claim *= lognormal_multiplier(
            rng.standard_normal(evacuated.shape), rates.per_claim_sigma
        )
    cost = (
        evacuated * rates.evacuated_nzd_per_m2
        + inundated * rates.inundated_nzd_per_m2 * inundated_multiplier
        + per_claim
    )
    return np.where(np.asarray(claimed, dtype=bool), cost, 0.0)
