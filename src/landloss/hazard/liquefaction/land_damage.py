"""Land damage states for the beta: expanding the NLM grids, and drawing from them.

The study reports land damage on a six state severity scale -- None, Minor,
Moderate, Major, Severe, Very Severe -- but the National Liquefaction Model
grids the beta reads carry only **Moderate** and **Major**. The rest of the
scale has to be manufactured, and this module is where that happens so the
arithmetic is testable rather than buried in a script.

Two separate things happen here, and conflating them is the error this module
exists to prevent.

**First, differencing.** The NLM grids are *exceedance* probabilities:
``p_ld_moderate_fu`` is P(damage at least Moderate), not P(damage is Moderate).
So the Moderate band is ``p_moderate - p_major`` and the None band is
``1 - p_moderate``. Reading them as band probabilities would count the Major
mass twice, which is why :func:`beta_expand_ld_probabilities` takes the exceedance
grids and differences them itself rather than trusting a caller to have done it.

**Second, subdividing.** Half the None mass becomes Minor, and the Major band
splits into Severe (a half), Very Severe (a quarter) and Major (the remaining
quarter). This subdivides rather than adds, so probability is conserved by
construction and nothing is renormalised.

The subdivision fractions are a beta shortcut with no evidence behind them. They
exist to give the chain a six state raster of the right shape; see
`.agents/plans/beta-build.md`.

**The ``beta_`` prefix marks what gets deleted.** Everything carrying it
manufactures states the NLM does not supply, and goes when the model produces
the full scale itself. :func:`exceedance_to_bands` and :func:`draw_ld_states`
carry no prefix because differencing an exceedance pair and drawing a state from
a set of probabilities are both correct whatever supplies the bands.
"""

import numpy as np
import xarray as xr

# The six states, in severity order. The index into this tuple plus one is the
# ``ld_state`` value written to the raster, so the order is load-bearing.
LD_STATES = ("None", "Minor", "Moderate", "Major", "Severe", "Very Severe")

# How the two derived bands are subdivided. Each entry is the share of the named
# band that becomes that state; each band's shares sum to one, which is what
# conserves probability.
BETA_NONE_SHARES = {"None": 0.5, "Minor": 0.5}
BETA_MAJOR_SHARES = {"Major": 0.25, "Severe": 0.5, "Very Severe": 0.25}

# Floating point accumulation over millions of cells, not a tolerance for a grid
# that is genuinely wrong. A grid in per cent, or a pair the wrong way round,
# misses by far more than this.
SUM_TOLERANCE = 1e-6


def _check_shares(shares: dict[str, float], label: str) -> None:
    """Raise if a set of subdivision shares does not sum to one."""
    total = sum(shares.values())
    if abs(total - 1.0) > SUM_TOLERANCE:
        msg = (
            f"{label} shares sum to {total}, not 1; probability would not be conserved"
        )
        raise ValueError(msg)


def exceedance_to_bands(
    moderate_or_worse: xr.DataArray,
    major_or_worse: xr.DataArray,
) -> dict[str, xr.DataArray]:
    """Difference a pair of exceedance grids into the three bands they imply.

    Args:
        moderate_or_worse: P(land damage at least Moderate), per cell.
        major_or_worse: P(land damage at least Major), per cell.

    Returns:
        The ``None``, ``Moderate`` and ``Major`` band probabilities.

    Raises:
        ValueError: If either grid leaves [0, 1], or if the Major grid exceeds
            the Moderate grid anywhere -- which would mean the two are not an
            exceedance pair, most likely because they have been swapped.
    """
    for grid, label in ((moderate_or_worse, "moderate"), (major_or_worse, "major")):
        if not grid.size:
            continue
        if not np.any(np.isfinite(grid.values)):
            msg = (
                f"the {label} grid holds no finite values. A clip that missed the "
                "layer, or a nodata fill, looks like this."
            )
            raise ValueError(msg)
        low = float(np.nanmin(grid.values))
        high = float(np.nanmax(grid.values))
        if low < -SUM_TOLERANCE or high > 1.0 + SUM_TOLERANCE:
            msg = (
                f"{label} exceedance runs {low:.4f} to {high:.4f}, outside [0, 1]. "
                "A grid in per cent or one carrying a nodata marker looks like this."
            )
            raise ValueError(msg)

    difference = moderate_or_worse - major_or_worse
    if difference.size:
        worst = float(np.nanmin(difference.values))
        if worst < -SUM_TOLERANCE:
            msg = (
                f"P(at least Major) exceeds P(at least Moderate) by {-worst:.4f}. "
                "These are not an exceedance pair; the arguments may be swapped."
            )
            raise ValueError(msg)

    return {
        "None": 1.0 - moderate_or_worse,
        "Moderate": difference,
        "Major": major_or_worse,
    }


def beta_expand_ld_probabilities(
    moderate_or_worse: xr.DataArray,
    major_or_worse: xr.DataArray,
) -> dict[str, xr.DataArray]:
    """Expand the two supplied exceedance grids into six state probabilities.

    The grids are differenced into bands first, then the None and Major bands
    are subdivided. Both steps happen here so that neither can be skipped.

    Args:
        moderate_or_worse: P(land damage at least Moderate), per cell.
        major_or_worse: P(land damage at least Major), per cell.

    Returns:
        One probability grid per state, keyed by the names in :data:`LD_STATES`.

    Raises:
        ValueError: If the exceedance pair is invalid, or if the six expanded
            bands do not sum to one.
    """
    _check_shares(BETA_NONE_SHARES, "None")
    _check_shares(BETA_MAJOR_SHARES, "Major")

    bands = exceedance_to_bands(moderate_or_worse, major_or_worse)
    none, major = bands["None"], bands["Major"]

    expanded = {
        "None": none * BETA_NONE_SHARES["None"],
        "Minor": none * BETA_NONE_SHARES["Minor"],
        "Moderate": bands["Moderate"],
        "Major": major * BETA_MAJOR_SHARES["Major"],
        "Severe": major * BETA_MAJOR_SHARES["Severe"],
        "Very Severe": major * BETA_MAJOR_SHARES["Very Severe"],
    }

    total = sum(expanded.values())
    worst = float(np.nanmax(np.abs(total.values - 1.0))) if total.size else 0.0
    if worst > SUM_TOLERANCE:
        msg = f"expanded probabilities miss 1 by up to {worst}, which is not rounding"
        raise ValueError(msg)
    return expanded


def draw_ld_states(
    probabilities: dict[str, xr.DataArray],
    rng: np.random.Generator,
) -> xr.DataArray:
    """Draw one land damage state per cell.

    A single uniform draw per cell is compared against the cumulative
    probability across the states in severity order, so a cell's state is the
    first band its draw falls inside.

    Args:
        probabilities: One grid per state, as :func:`beta_expand_ld_probabilities`
            returns.
        rng: The generator for this realisation's liquefaction stream.

    Returns:
        A grid of ``ld_state`` values, 1 to 6, named ``ld_state``. Cells where
        any input is missing come back as NaN rather than as state 1, because
        "nothing known here" is not "no damage".

    Raises:
        ValueError: If a state is missing from the mapping.
    """
    missing = [state for state in LD_STATES if state not in probabilities]
    if missing:
        msg = f"no probability grid for {missing}"
        raise ValueError(msg)

    template = probabilities[LD_STATES[0]]
    draw = rng.random(template.shape)

    # A cell is usable only where every state is known. Accumulating the bands
    # and letting NaN propagate is not enough: the cumulative only goes NaN from
    # the missing state onwards, so a cell with a known None band and a missing
    # Major band would be handed None or Minor and written out as undamaged.
    # Unknown Major probability is not no damage.
    known = ~np.any(
        [np.isnan(probabilities[state].values) for state in LD_STATES], axis=0
    )

    states = np.full(template.shape, np.nan)
    cumulative = np.zeros(template.shape)
    for index, state in enumerate(LD_STATES, start=1):
        cumulative = cumulative + np.nan_to_num(probabilities[state].values)
        landed = known & np.isnan(states) & (draw < cumulative)
        states[landed] = index

    # The bands sum to one only to within SUM_TOLERANCE, so a draw can land in
    # the sliver past the top of the last band. That cell is known, not missing,
    # and belongs in the most severe state rather than coming back as nodata.
    states[known & np.isnan(states)] = len(LD_STATES)

    return template.copy(data=states).rename("ld_state")
