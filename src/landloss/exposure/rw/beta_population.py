"""The size classes and initial conditions a retaining wall is carried in.

Every wall the chain reads carries a size class, from its retained height on
the agreed boundaries, and an initial condition, modern or poor. The boundaries
are set by what the costing can tell apart rather than by engineering
interest: above the sub-cap the settlement stops depending on height, so a
three metre and a six metre wall settle the same and do not need separating
(``.agents/plans/asset-pricing-approach.md``, section 1.1).

The module keeps its ``beta`` name for the one judgement left in it,
:data:`BETA_POOR_SHARE`, the share of walls in poor condition where nothing
better is known. The slope-driven stand-in population that used to live here
is gone: the population is now drawn line by line from
:mod:`landloss.exposure.rw.wall_probability` by
:mod:`landloss.exposure.rw.population`, and the height of each wall is read
off the DEM by :mod:`landloss.exposure.rw.lines` rather than manufactured.
"""

import numpy as np
import pandas as pd

# The size class boundaries, in metres of retained height.
SMALL_MAX_HEIGHT_M = 1.0
MEDIUM_MAX_HEIGHT_M = 2.5
SIZE_CLASSES = ("small", "medium", "large")

# The two initial condition classes, and the share of walls in the poor one
# where neither the dwelling age nor the height says otherwise. Judgement: the
# real share comes from the claim report extraction (T-50).
INITIAL_CONDITIONS = ("modern", "poor")
BETA_POOR_SHARE = 0.5

# The range of retained heights the beta wall population once drew, in metres.
# The population no longer draws heights (each is read off the DEM), but the
# loss module's pricing tests still read these two as the range its set height
# per size class has to sit inside, and the loss module is owned elsewhere, so
# they stay until its owner moves that test onto MIN_WALL_HEIGHT_M.
BETA_MIN_HEIGHT_M = 0.4
BETA_MAX_HEIGHT_M = 3.0


def classify_wall_size(height_m: np.ndarray | float) -> np.ndarray:
    """Return the size class of a wall from its retained height.

    Args:
        height_m: Retained height in metres.

    Returns:
        ``"small"``, ``"medium"`` or ``"large"`` per wall.
    """
    heights = np.asarray(height_m, dtype=float)
    return np.select(
        [heights < SMALL_MAX_HEIGHT_M, heights < MEDIUM_MAX_HEIGHT_M],
        [SIZE_CLASSES[0], SIZE_CLASSES[1]],
        default=SIZE_CLASSES[2],
    )


def describe_population(walls: pd.DataFrame) -> pd.DataFrame:
    """Return the wall count by size class and initial condition.

    Args:
        walls: The drawn wall population.

    Returns:
        A table of counts, one row per size class, one column per condition.
    """
    if walls.empty:
        return pd.DataFrame(index=list(SIZE_CLASSES), columns=list(INITIAL_CONDITIONS))
    counts = walls.pivot_table(
        index="size_class",
        columns="initial_condition",
        values="height_m",
        aggfunc="size",
        fill_value=0,
    )
    return counts.reindex(index=list(SIZE_CLASSES), fill_value=0)
