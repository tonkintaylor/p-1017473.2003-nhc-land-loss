"""The cost of liquefaction land damage, per property, per damage state.

Reads the packaged Canterbury rates: what NHC actually settled for land damage
after the 2010 and 2011 earthquakes, grouped by the damage state surveyed on the
ground. Nothing here models a cost; it looks one up.

Three properties of the source shape everything that uses it.

**The rates are per property, not per square metre.** A property assessed at
Moderate cost what it cost, whatever its size. So the quantity this module
returns is one per property, and an area never multiplies it. Deriving a rate per
square metre by dividing by the property's own area would invent a basis the
Canterbury data never had, and would make a large section cost more than the
ILVR ever paid.

**The percentile is a scenario, not a distribution.** The 15th, 50th and 85th are
the spread of settled costs *between* Canterbury properties assessed at the same
state, not a confidence interval on an estimate. The 85th runs two to four times
the median, so the choice moves the liquefaction component by more than most
modelling decisions in the study. It is carried as a run-level parameter -- one
scalar, the model run once per value -- because ``min(repair, cap)`` is
non-linear: a settlement computed from a median cost is not the median
settlement, so the cost has to vary before the cap truncates, not after.

**States 5 and 6 carry identical costs**, both read from the source band
"5 or 6". They are one estimate wearing two hats, so the spread at the severe end
is thinner evidence than the file's six rows suggest.

**The rates include properties that never claimed, at $0.** They average over
every damaged property in a state, not just those that lodged a claim (Q-17), so
the drop-out is already inside them. :data:`COSTS_INCLUDE_NON_CLAIMANTS` records
that, and the liquefaction land damage step reads it to leave its own drop-out
draw off rather than count it twice. Claimant-only rates are to replace these
(T-66).

The rates are 2010/2011 dollars excluding GST (**L-23**, **L-24**), cover
categories 1 to 7 and so exclude ILV and IFV (**L-25**), and apply to flat land
only -- they must not be used for hill land or for landslide damage.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
COSTS_PATH = ASSETS_DIR / "costs_liq_ld_refined_states_2011.csv"

STATE_COLUMN = "LD_refined_state"
STATE_NAME_COLUMN = "state_name"

# The percentiles the file carries, and the column each lives in.
PERCENTILE_COLUMNS = {
    15: "cost_15th_percentile_nzd",
    50: "cost_50th_percentile_nzd",
    85: "cost_85th_percentile_nzd",
}

# The year the costs are stated in. Carried onto every row rather than assumed,
# because land values are indexed to a different date and a loss table that
# mixes vintages with nothing to tell them apart is a silent error.
COST_YEAR = 2011

# Whether the packaged rates average over all damaged properties, non-claimants
# counted at $0, rather than over claimants only. A fact about the file, not a
# run choice: set it False only when the CSV is replaced with claimant-only
# rates (T-66), which is what switches the drop-out draw back on.
COSTS_INCLUDE_NON_CLAIMANTS = True

# What the cost is a quantity of. Named so a reader of the vul output can tell
# it from the per-square-metre rates the landslide work uses.
RATE_BASIS = "per_property"


def load_ld_costs(path: Path = COSTS_PATH) -> pd.DataFrame:
    """Read the packaged land damage cost rates.

    Args:
        path: The CSV to read, defaulting to the packaged asset.

    Returns:
        One row per land damage state, indexed by the state number.

    Raises:
        ValueError: If the file does not carry all six states, or a percentile
            column is missing.
    """
    # keep_default_na=False because the least severe state is literally named
    # "None", which pandas otherwise reads as a missing value -- silently
    # unlabelling a sixth of the portfolio and dropping it out of any summary
    # grouped on the name. The file carries no blanks, so nothing is lost.
    costs = pd.read_csv(path, keep_default_na=False, na_values=[])
    missing = [
        column
        for column in (STATE_COLUMN, STATE_NAME_COLUMN, *PERCENTILE_COLUMNS.values())
        if column not in costs.columns
    ]
    if missing:
        msg = f"{path.name} is missing {missing}"
        raise ValueError(msg)

    states = set(costs[STATE_COLUMN])
    expected = set(range(1, 7))
    if states != expected:
        msg = (
            f"{path.name} carries states {sorted(states)}, expected {sorted(expected)}"
        )
        raise ValueError(msg)
    return costs.set_index(STATE_COLUMN).sort_index()


def ld_cost_nzd(
    states: np.ndarray,
    percentile: int,
    costs: pd.DataFrame | None = None,
) -> np.ndarray:
    """Return the cost per property for each land damage state.

    Args:
        states: The land damage state per property, 1 to 6. NaN where the state
            is not known.
        percentile: Which percentile of the settled costs to use, one of the
            keys of :data:`PERCENTILE_COLUMNS`. A run-level choice.
        costs: The rate table, read from the packaged asset when not given.

    Returns:
        The cost per property in 2010/2011 NZD excluding GST, NaN where the
        state was not known.

    Raises:
        ValueError: If the percentile is not one the file carries, or a state
            outside 1 to 6 is asked for.
    """
    if percentile not in PERCENTILE_COLUMNS:
        msg = (
            f"percentile must be one of {sorted(PERCENTILE_COLUMNS)}, "
            f"got {percentile}. "
            "The file carries three settled-cost percentiles, not a distribution."
        )
        raise ValueError(msg)

    table = load_ld_costs() if costs is None else costs
    values = np.asarray(states, dtype=float)
    known = np.isfinite(values)

    asked = np.unique(values[known]).astype(int) if known.any() else np.array([], int)
    unknown = sorted(set(asked.tolist()) - set(table.index))
    if unknown:
        msg = f"no cost for land damage state {unknown}; the file carries 1 to 6"
        raise ValueError(msg)

    lookup = table[PERCENTILE_COLUMNS[percentile]]
    out = np.full(values.shape, np.nan)
    out[known] = lookup.reindex(values[known].astype(int)).to_numpy()
    return out
