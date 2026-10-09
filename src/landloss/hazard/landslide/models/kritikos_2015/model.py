"""Combine the four memberships into the Kritikos relative landslide hazard.

Each factor is turned to a 0 to 1 membership with the digitised average curves
of :mod:`.memberships`, and the four are combined cell by cell with the fuzzy
gamma operator, the paper's equation 4. The operator is the product of the
fuzzy product and the fuzzy sum, each raised to a power set by gamma:

    H = (prod mu_i) ** (1 - gamma) * (1 - prod (1 - mu_i)) ** gamma

Gamma of 0 is the fuzzy product alone and gamma of 1 the fuzzy sum alone. The
paper adopts 0.9: it gives marginally higher hazard at known landslide pixels,
and when working to a scenario over-estimating is preferred to under-estimating
[kritikos_2015]. Gamma of 0.8 changed the Wenchuan AUC by 0.005 only, so it is
a sensitivity, not a decision.

The result is a relative hazard, not a probability or a coverage.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from landloss.hazard.landslide.models.kritikos_2015 import memberships

# The paper's gamma.
GAMMA = 0.9

# Below this slope a cell is reported but flagged: the paper scores its
# success rate both with and without the cells under 5 degrees, because
# Northridge's large areas of gentle ground flatter the whole-area figure.
GENTLE_SLOPE_DEG = 5.0


@dataclass(frozen=True)
class KritikosResult:
    """The relative hazard and the cells flagged as gentle ground."""

    hazard: np.ndarray
    gentle: np.ndarray


def fuzzy_gamma(values: Sequence[npt.ArrayLike], gamma: float = GAMMA) -> np.ndarray:
    """Combine memberships with the fuzzy gamma operator.

    Args:
        values: Two or more membership arrays, each in 0 to 1, that broadcast
            to one shape. NaN in any of them gives NaN.
        gamma: The gamma parameter, 0 to 1.

    Returns:
        The combined membership on the broadcast shape.

    Raises:
        ValueError: If fewer than two memberships are given, gamma is outside
            0 to 1, or a finite membership is outside 0 to 1.
    """
    if len(values) < 2:
        msg = "the fuzzy gamma operator combines at least two memberships"
        raise ValueError(msg)
    if not 0.0 <= gamma <= 1.0:
        msg = f"gamma must be between 0 and 1, not {gamma}"
        raise ValueError(msg)

    arrays = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in values))
    stacked = np.stack(arrays)
    finite = stacked[np.isfinite(stacked)]
    if finite.size and (finite.min() < 0.0 or finite.max() > 1.0):
        msg = "memberships must lie between 0 and 1"
        raise ValueError(msg)

    product = np.prod(stacked, axis=0)
    fuzzy_sum = 1.0 - np.prod(1.0 - stacked, axis=0)
    return product ** (1.0 - gamma) * fuzzy_sum**gamma


def run(
    *,
    mm: npt.ArrayLike,
    slope_deg: npt.ArrayLike,
    fault_distance_km: npt.ArrayLike,
    slope_position: npt.ArrayLike,
    gamma: float = GAMMA,
) -> KritikosResult:
    """Return the Kritikos relative hazard on aligned cells.

    Args:
        mm: Modified Mercalli intensity per cell.
        slope_deg: Slope angle per cell, in degrees, on the 60 m grid.
        fault_distance_km: Horizontal distance to the nearest mapped active
            fault, in km. Pass ``inf`` to hold the fault term at its far-field
            value, which is how the fault term is switched off.
        slope_position: Slope position class per cell, as the codes in
            :mod:`.memberships`, NaN where unclassified.
        gamma: The gamma of the fuzzy gamma operator.

    Returns:
        The relative hazard, 0 to 1, NaN wherever an input is, and the cells
        under :data:`GENTLE_SLOPE_DEG`.
    """
    slope = np.asarray(slope_deg, dtype=float)
    hazard = fuzzy_gamma(
        [
            memberships.mm_membership(mm),
            memberships.slope_membership(slope),
            memberships.fault_membership(fault_distance_km),
            memberships.slope_position_membership(slope_position),
        ],
        gamma,
    )
    gentle = np.broadcast_to(slope < GENTLE_SLOPE_DEG, hazard.shape).copy()
    return KritikosResult(hazard=hazard, gentle=gentle)
