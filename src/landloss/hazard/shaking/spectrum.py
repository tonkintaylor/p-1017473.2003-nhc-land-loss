"""The TS1170.5:2025 elastic site spectrum, Sa(T), from its four parameters.

SNZ TS 1170.5:2025 does not tabulate spectral acceleration at any period.
Tables 3.1 and 3.2 give PGA, the short-period plateau Sa,s and the two corner
periods Tc and Td (read by :mod:`landloss.io.ts1170`), and clause 3.1.2 builds
the spectrum from them:

    Sa(T) = PGA                               T = 0         (Eq. 3.2)
    Sa(T) = Sa,s                              0.1 s < T < Tc (Eq. 3.3)
    Sa(T) = Sa,s * Tc / T                     Tc < T < Td    (Eq. 3.4)
    Sa(T) = Sa,s * (Tc / T) * (Td / T)**0.5   Td < T         (Eq. 3.5)

Between 0 and 0.1 s the TS takes Sa,s for the equivalent static method and
permits a linear interpolation from PGA to Sa,s for other methods. The
interpolation is used here, since this study is not designing a structure by
the equivalent static method. It only matters for periods below 0.1 s.
"""

import numpy as np

# The period the TS's constant-acceleration plateau starts at.
PLATEAU_START_S = 0.1


def ts1170_sa(
    period_s: float,
    *,
    pga_g: np.ndarray,
    sa_s_g: np.ndarray,
    tc_s: np.ndarray,
    td_s: np.ndarray,
) -> np.ndarray:
    """Evaluate the TS1170.5 spectrum at one period.

    The four parameters broadcast against each other, so they can be columns
    of a table or cells of a grid. NaN in Sa,s, Tc or Td (or in PGA, below
    0.1 s) gives NaN.

    Args:
        period_s: The period of vibration, in seconds.
        pga_g: Peak ground acceleration, in g.
        sa_s_g: The short-period spectral acceleration Sa,s, in g.
        tc_s: The spectral-acceleration-plateau corner period, in seconds.
        td_s: The spectral-velocity-plateau corner period, in seconds.

    Returns:
        Sa(T) in g.

    Raises:
        ValueError: If the period is negative.
    """
    if period_s < 0:
        msg = f"Period must not be negative, got {period_s}."
        raise ValueError(msg)

    pga_g, sa_s_g, tc_s, td_s = np.broadcast_arrays(
        *(np.asarray(v, dtype=float) for v in (pga_g, sa_s_g, tc_s, td_s))
    )
    if period_s < PLATEAU_START_S:
        return pga_g + (sa_s_g - pga_g) * period_s / PLATEAU_START_S

    # np.where evaluates every branch; a period at or above 0.1 s keeps the
    # divisions finite, so no warnings are raised for the branches not taken.
    return np.where(
        period_s < tc_s,
        sa_s_g,
        np.where(
            period_s < td_s,
            sa_s_g * tc_s / period_s,
            sa_s_g * (tc_s / period_s) * np.sqrt(td_s / period_s),
        ),
    )
