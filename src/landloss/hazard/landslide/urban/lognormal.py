"""The lognormal fragility shared by the urban and wall type curves.

What belongs here: the PGA intensity measure name and the lognormal failure
probability. They sit apart from :mod:`landloss.hazard.landslide.urban.fragility`
so that it and :mod:`landloss.hazard.landslide.urban.wall_type_fragility` can
both import them without importing each other.
"""

import numpy as np
import numpy.typing as npt
from scipy.stats import norm

# The intensity measure a published wall curve is on.
PGA_IM = "pga_g"


def lognormal_failure_probability(
    im: npt.NDArray[np.floating],
    theta: npt.NDArray[np.floating],
    beta: npt.NDArray[np.floating],
) -> npt.NDArray[np.floating]:
    """Evaluate a lognormal fragility, ``Phi(ln(im / theta) / beta)``.

    Args:
        im: The demand, in the median's units. Zero or below gives 0.
        theta: The median demand.
        beta: The lognormal dispersion, positive.

    Returns:
        The probability of failure, the broadcast shape of the inputs; NaN
        where the median is NaN.

    Raises:
        ValueError: If any dispersion is zero or below.
    """
    demand = np.asarray(im, dtype=float)
    median = np.asarray(theta, dtype=float)
    dispersion = np.asarray(beta, dtype=float)
    if np.any(dispersion <= 0):
        msg = "A lognormal dispersion must be positive."
        raise ValueError(msg)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = np.log(demand / median) / dispersion
    probability = norm.cdf(z)
    return np.where(demand <= 0, 0.0, probability)
