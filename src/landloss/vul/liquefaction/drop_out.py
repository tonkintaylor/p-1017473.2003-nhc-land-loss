"""Which liquefied properties go on to make a land claim.

Every flat land property the hazard grid reaches carries a land damage state,
but not every owner of a damaged property claims. A property showing a few
cracks may never be reported; a property buried in ejecta always is. The
**drop-out rate** is the share of properties in a state that do not claim, and
this module draws, per property, whether it is one of them.

Three things about the draw shape how it is used.

**It is a draw, not a weight.** A property either claims, at its full cost, or
does not, at none. Scaling every property's cost by its claim rate instead would
give the same expected repair cost, but the loss module then applies an excess
and ``min(repair, cap)``, both non-linear, so the expected settlement would be
wrong -- and a small cost on every property would mostly vanish into the excess.

**One uniform number is drawn per property, whatever its state.** The draws
line up with the property order rather than with the properties that happen to
carry a state, so changing a rate, or the hazard grid's reach, does not reshuffle
which of the other properties claim.

**The rates are a tuning parameter, not evidence.** They are held by the caller
-- the step's ``config.py`` -- rather than here, because the values in use are
placeholders awaiting Virginie Lacrosse's table (**T-64**, **Q-16**). Whether the
Canterbury costs they are paired with already include non-claimants as $0 decides
whether the rates should be applied at all (see
``src/scripts/landloss/vul/liquefaction/land/status.md``).
"""

from collections.abc import Mapping

import numpy as np

# The land damage states a rate must be given for: 1 None to 6 Very severe.
STATES = tuple(range(1, 7))


def check_drop_out_rates(rates: Mapping[int, float]) -> None:
    """Check a drop-out rate table covers every state with a valid share.

    Args:
        rates: The share of properties in each land damage state that do not
            claim, keyed on the state, 1 to 6.

    Raises:
        ValueError: If a state is missing or unknown, or a rate falls outside
            0 to 1.
    """
    keys = set(rates)
    if keys != set(STATES):
        msg = (
            f"drop-out rates are given for states {sorted(keys)}, "
            f"expected {list(STATES)}"
        )
        raise ValueError(msg)
    bad = {state: rate for state, rate in rates.items() if not 0.0 <= rate <= 1.0}
    if bad:
        msg = f"drop-out rates must lie between 0 and 1, got {bad}"
        raise ValueError(msg)


def draw_claims(
    states: np.ndarray,
    rates: Mapping[int, float],
    rng: np.random.Generator,
) -> np.ndarray:
    """Draw which properties make a liquefaction land claim.

    Args:
        states: The land damage state per property, 1 to 6, NaN where the
            property has no state (off the liquefaction grid).
        rates: The drop-out rate per state, as :func:`check_drop_out_rates`
            accepts.
        rng: The generator to draw from, one uniform number per property.

    Returns:
        A boolean per property: True where it claims. A property with no state
        never claims; a property in a state with a drop-out rate of 0 always
        does.

    Raises:
        ValueError: If the rates are invalid, or a state outside 1 to 6 is
            given.
    """
    check_drop_out_rates(rates)
    values = np.asarray(states, dtype=float)
    known = np.isfinite(values)
    unknown = sorted(set(np.unique(values[known]).tolist()) - set(STATES))
    if unknown:
        msg = f"no drop-out rate for land damage state {unknown}; expected 1 to 6"
        raise ValueError(msg)

    drop_out = np.ones(values.shape)
    drop_out[known] = [rates[int(state)] for state in values[known]]
    # Drawn for every property, not just those with a state, so the number a
    # property draws does not depend on how many before it sit on the grid.
    return rng.random(values.shape) >= drop_out
