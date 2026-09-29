"""Peak ground velocity, derived from the TS1170.5 spectrum.

PGV is not generated independently. It is taken from the spectral acceleration
at a 1 second period of the same TS1170.5 demand as PGA, with the relation the
shaking module's approach states (``src/scripts/landloss/hazard/shaking/
status.md``):

    PGV (mm/s) = 750 * Sa(1.0 s) (g)

so that PGA and PGV come from one spectrum at one site class and cannot
disagree about how strong the earthquake was. The landslide models read PGV in
cm/s, the unit the Nowicki Jessee (2018) coefficients were fitted in.
"""

import numpy as np

# The relation above, in the units it is written in.
PGV_MM_S_PER_G_SA_1S = 750.0


def pgv_cm_s_from_sa_1s(sa_1s_g: np.ndarray) -> np.ndarray:
    """Convert Sa(1.0 s) to peak ground velocity.

    Args:
        sa_1s_g: Spectral acceleration at a 1 second period, in g. Works on
            anything numpy arithmetic does, an ``xarray.DataArray`` included.

    Returns:
        PGV in cm/s.
    """
    return sa_1s_g * PGV_MM_S_PER_G_SA_1S / 10.0
