"""Peak ground velocity, derived from the TS1170.5 spectrum.

PGV is not generated independently. It is taken from the spectral acceleration
at a 1 second period of the same TS1170.5 demand as PGA, with the relation the
shaking module's approach states (``src/scripts/landloss/hazard/shaking/
status.md``):

    PGV (mm/s) = 750 * Sa(1.0 s) (g)

so that PGA and PGV come from one spectrum at one site class and cannot
disagree about how strong the earthquake was. The shaking layers carry PGV in
m/s; the landslide models read it in cm/s, the unit the Nowicki Jessee (2018)
coefficients were fitted in.

A realisation of PGV is the grid scaled by **the same lognormal factor as the
realisation's PGA** (:func:`landloss.hazard.shaking.pga.beta_scale_factor`, the
first and only draw :func:`~landloss.hazard.shaking.pga.beta_pga_realisation`
makes on the shaking stream), so one modelled earthquake's two measures agree:
:func:`beta_pgv_realisation` draws that factor from a generator seeded exactly
as the PGA step seeds it.
"""

import numpy as np
import xarray as xr

from landloss.hazard.shaking.pga import BETA_PGA_COV, beta_scale_factor

# The relation above, in the units it is written in.
PGV_MM_S_PER_G_SA_1S = 750.0

# The name the PGV rasters carry, in the unit the shaking layers are written in.
PGV_NAME = "pgv_m_s"


def pgv_cm_s_from_sa_1s(sa_1s_g: np.ndarray) -> np.ndarray:
    """Convert Sa(1.0 s) to peak ground velocity.

    Args:
        sa_1s_g: Spectral acceleration at a 1 second period, in g. Works on
            anything numpy arithmetic does, an ``xarray.DataArray`` included.

    Returns:
        PGV in cm/s.
    """
    return sa_1s_g * PGV_MM_S_PER_G_SA_1S / 10.0


def pgv_m_s_from_sa_1s(sa_1s_g: np.ndarray) -> np.ndarray:
    """Convert Sa(1.0 s) to peak ground velocity, in m/s.

    Args:
        sa_1s_g: Spectral acceleration at a 1 second period, in g. Works on
            anything numpy arithmetic does, an ``xarray.DataArray`` included.

    Returns:
        PGV in m/s.
    """
    return sa_1s_g * PGV_MM_S_PER_G_SA_1S / 1000.0


def beta_pgv_realisation(
    pgv: xr.DataArray,
    rng: np.random.Generator,
    cov: float = BETA_PGA_COV,
) -> tuple[xr.DataArray, float]:
    """Return one realisation of the PGV field, and the factor that made it.

    The factor is the one draw :func:`landloss.hazard.shaking.pga.beta_scale_factor`
    makes, so a generator seeded as the PGA step seeds it -- the same base
    seed, realisation id and ``"shaking"`` stream -- gives PGV the factor PGA
    took, and the two fields of one modelled earthquake agree.

    Args:
        pgv: The supplied PGV grid, in m/s.
        rng: The generator for this realisation's shaking stream, fresh: the
            factor is its first draw.
        cov: The coefficient of variation to draw against.

    Returns:
        The scaled grid, named ``pgv_m_s``, and the multiplier applied to it.

    Raises:
        ValueError: If the grid holds a negative velocity.
    """
    values = pgv.values
    if np.any(values[np.isfinite(values)] < 0):
        msg = "the PGV grid holds a negative velocity, which is not a ground motion"
        raise ValueError(msg)

    factor = beta_scale_factor(rng, cov)
    return (pgv * factor).rename(PGV_NAME), factor
