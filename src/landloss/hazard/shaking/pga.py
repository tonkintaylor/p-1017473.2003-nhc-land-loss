r"""Turning one PGA grid into a realisation of shaking.

The shaking step builds one peak ground acceleration grid per return period:
TS1170.5 PGA per 100 m cell, at each cell's own site class from the Foster et al.
(2019) Vs30 model (``scripts/landloss/hazard/shaking/steps/s4_pga_realisation``).
That is one number per cell, with no spread around it. A loss model that reads
it as delivered has no uncertainty in its shaking at all, so every realisation
would shake every property identically and the only variation in the answer
would come from the other hazards.

The beta puts a spread back on with a **10% coefficient of variation**, applied
as a lognormal multiplier. PGA is conventionally treated as lognormal, so a
multiplicative perturbation keeps it positive and keeps the distribution the
right shape without anything having to be clipped.

**The multiplier is one draw for the whole grid**, not one per cell. That is a
deliberate choice and the most important thing to know about this module:

- Drawing per cell would destroy the spatial pattern the grid carries, and
  would average almost entirely away across a portfolio -- a thousand properties
  each nudged independently sum to very nearly the unperturbed total, so the
  loss distribution would come out far too narrow.
- Drawing once per realisation scales the whole field together, which preserves
  the pattern and gives the widest spread a 10% CoV can produce.

Real ground motion is neither: it is spatially correlated, strongly over
hundreds of metres and weakly over tens of kilometres. The fully correlated
choice is the conservative end of that, and replacing it with a correlated
random field is what the real version does.

Everything here carries a ``beta`` name because the real version takes its
spread from the ground motion model's own sigma rather than from a figure chosen
for the beta.
"""

import numpy as np
import xarray as xr

# The coefficient of variation put on PGA for the beta. Not from a ground motion
# model: a round number chosen to give the chain a spread to carry.
BETA_PGA_COV = 0.10


def beta_scale_factor(rng: np.random.Generator, cov: float = BETA_PGA_COV) -> float:
    """Draw one lognormal multiplier for a realisation's shaking.

    The multiplier has a mean of one, so a realisation is neither systematically
    stronger nor weaker than the grid it came from, and the spread of many draws
    is ``cov``.

    Args:
        rng: The generator for this realisation's shaking stream.
        cov: The coefficient of variation to draw against.

    Returns:
        A positive multiplier.

    Raises:
        ValueError: If the coefficient of variation is negative.
    """
    if cov < 0:
        msg = f"cov must not be negative, got {cov}"
        raise ValueError(msg)
    if cov == 0:
        return 1.0
    # sigma of the underlying normal, and the offset that puts the mean of the
    # lognormal at one rather than at exp(sigma^2 / 2).
    sigma = np.sqrt(np.log(1.0 + cov**2))
    return float(np.exp(rng.normal(-(sigma**2) / 2.0, sigma)))


def beta_pga_realisation(
    pga: xr.DataArray,
    rng: np.random.Generator,
    cov: float = BETA_PGA_COV,
) -> tuple[xr.DataArray, float]:
    """Return one realisation of the PGA field, and the factor that made it.

    Args:
        pga: The supplied PGA grid, in g.
        rng: The generator for this realisation's shaking stream.
        cov: The coefficient of variation to draw against.

    Returns:
        The scaled grid, named ``pga_g``, and the multiplier applied to it. The
        factor is returned so a run can print it: it is the whole difference
        between one realisation and the next, and is otherwise invisible.

    Raises:
        ValueError: If the grid holds a negative acceleration.
    """
    values = pga.values
    if np.any(values[np.isfinite(values)] < 0):
        msg = "the PGA grid holds a negative acceleration, which is not a ground motion"
        raise ValueError(msg)

    factor = beta_scale_factor(rng, cov)
    return (pga * factor).rename("pga_g"), factor
