"""How much of a liquefied property is evacuated and how much is inundated.

A land damage state says how badly a property liquefied, but an NHC claim
report says what ground was lost: land **evacuated** -- cracked, opened or
spread, measured in square metres -- and land **inundated** under ejecta,
measured as a share of the insured land. This module draws both per property
from ranges set for each state (**T-55**), so that `loss` can cost liquefaction
the way it costs a landslide, from areas rather than from a lookup per property.

Three things about the draw shape how it is used.

**The ranges are judgement** (**L-39**), read off the MBIE descriptions of each
state on 2026-09-30. They are held by the caller -- the step's ``config.py`` --
rather than here, because they are to be tuned against the Canterbury cost
table along with the repair rates they multiply (**T-57**).

**Evacuated is an area, inundated a share.** A Major state cracks a few square
metres whatever the section's size, but ejecta spreads over a fraction of it.
So the evacuated draw is in m² and the inundated draw is scaled by the insured
area. Each is capped at the insured area; the two may still sum to more than
it, because they overlap.

**The damaged area adds them less the overlap, and never exceeds the insured
land** (**T-56**). The share of the evacuated land taken to lie under the
inundated land is an assumption -- 30% for now (**L-44**) -- held by the
caller. The overlap cannot exceed the inundated land itself, and the total is
capped at the insured area, so a property both wholly inundated and evacuated
is damaged over its whole insured land and no more. That damaged area is what
the land cover cap is valued over.

**One pair of uniform numbers is drawn per property, whatever its state**, so a
changed range, or the hazard grid's reach, does not reshuffle the draws of the
other properties.
"""

from collections.abc import Mapping

import numpy as np

EVACUATED_AREA_COLUMN = "evacuated_area_m2"
INUNDATED_AREA_COLUMN = "inundated_area_m2"
DAMAGED_AREA_COLUMN = "damaged_area_m2"

# The land damage states a range must be given for: 1 None to 6 Very severe.
STATES = tuple(range(1, 7))

Ranges = Mapping[int, tuple[float, float]]


def check_ranges(ranges: Ranges, *, name: str, upper: float | None = None) -> None:
    """Check a range table covers every state with a valid low and high.

    Args:
        ranges: ``(low, high)`` per land damage state, 1 to 6.
        name: What the ranges are of, for the error message.
        upper: The largest value a range may reach, if there is one.

    Raises:
        ValueError: If a state is missing or unknown, a bound is negative or
            above ``upper``, or a low exceeds its high.
    """
    keys = set(ranges)
    if keys != set(STATES):
        msg = (
            f"{name} ranges are given for states {sorted(keys)}, "
            f"expected {list(STATES)}"
        )
        raise ValueError(msg)
    bad = {
        state: bounds
        for state, bounds in ranges.items()
        if not 0.0 <= bounds[0] <= bounds[1]
        or (upper is not None and bounds[1] > upper)
    }
    if bad:
        limit = "" if upper is None else f" and at most {upper}"
        msg = f"{name} ranges must run low to high, from 0{limit}; got {bad}"
        raise ValueError(msg)


def _uniform_within(
    states: np.ndarray, known: np.ndarray, ranges: Ranges, u: np.ndarray
) -> np.ndarray:
    low = np.zeros(states.shape)
    high = np.zeros(states.shape)
    low[known] = [ranges[int(state)][0] for state in states[known]]
    high[known] = [ranges[int(state)][1] for state in states[known]]
    return low + u * (high - low)


def draw_damaged_areas(
    states: np.ndarray,
    insured_area_m2: np.ndarray,
    evacuated_m2: Ranges,
    inundated_share: Ranges,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Draw the evacuated and inundated area of each property.

    Args:
        states: The land damage state per property, 1 to 6, NaN where the
            property has no state (off the liquefaction grid).
        insured_area_m2: The insured land area per property.
        evacuated_m2: ``(low, high)`` evacuated area in m² per state.
        inundated_share: ``(low, high)`` share of the insured land inundated
            per state, 0 to 1.
        rng: The generator to draw from, two uniform numbers per property.

    Returns:
        The evacuated and the inundated area per property in m², each drawn
        uniformly within its state's range and capped at the insured area.
        Zero where the property has no state.

    Raises:
        ValueError: If a range table is invalid, a state outside 1 to 6 is
            given, or the inputs differ in length.
    """
    check_ranges(evacuated_m2, name="evacuated area")
    check_ranges(inundated_share, name="inundated share", upper=1.0)
    values = np.asarray(states, dtype=float)
    area = np.asarray(insured_area_m2, dtype=float)
    if values.shape != area.shape:
        msg = f"{values.shape[0]} states against {area.shape[0]} insured areas"
        raise ValueError(msg)
    known = np.isfinite(values)
    unknown = sorted(set(np.unique(values[known]).tolist()) - set(STATES))
    if unknown:
        msg = f"no damaged area range for land damage state {unknown}; expected 1 to 6"
        raise ValueError(msg)

    # Drawn for every property, not just those with a state, so the numbers a
    # property draws do not depend on how many before it sit on the grid.
    u = rng.random((2, *values.shape))
    evacuated = _uniform_within(values, known, evacuated_m2, u[0])
    inundated = _uniform_within(values, known, inundated_share, u[1]) * area
    return np.minimum(evacuated, area), np.minimum(inundated, area)


def liquefied_area_m2(
    evacuated_m2: np.ndarray,
    inundated_m2: np.ndarray,
    insured_area_m2: np.ndarray,
    overlap_share: float,
) -> np.ndarray:
    """Return the insured land damaged by liquefaction, counting overlap once.

    Args:
        evacuated_m2: The evacuated area per property.
        inundated_m2: The inundated area per property.
        insured_area_m2: The insured land area per property.
        overlap_share: The share of the evacuated land taken to lie under the
            inundated land, 0 to 1.

    Returns:
        ``evacuated + inundated - overlap`` per property, where the overlap is
        ``overlap_share`` of the evacuated land but no more than the inundated
        land, capped at the insured area.

    Raises:
        ValueError: If ``overlap_share`` is outside 0 to 1, or an area is
            negative.
    """
    if not 0.0 <= overlap_share <= 1.0:
        msg = f"overlap_share must lie between 0 and 1, got {overlap_share}"
        raise ValueError(msg)
    evacuated = np.asarray(evacuated_m2, dtype=float)
    inundated = np.asarray(inundated_m2, dtype=float)
    area = np.asarray(insured_area_m2, dtype=float)
    if (evacuated < 0).any() or (inundated < 0).any() or (area < 0).any():
        msg = "areas must not be negative"
        raise ValueError(msg)
    overlap = np.minimum(overlap_share * evacuated, inundated)
    return np.minimum(evacuated + inundated - overlap, area)
