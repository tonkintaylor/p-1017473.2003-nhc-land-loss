"""Equations 8 and 9 of Nowicki Jessee et al. (2018), on grids already aligned.

The model is evaluated cell by cell, so everything here works on arrays of one
shape: building and aligning the inputs is :mod:`.inputs`'s job, not this
module's. Keeping the two apart is what lets the same equations be checked
against the USGS reference implementation on the USGS's own input rasters,
independently of whether our rebuilt rasters match theirs.

Two variants are available through ``operational``:

- ``operational=False`` is the paper: equation 8, the logistic function, and
  equation 9, with nothing else.
- ``operational=True`` adds the settings the USGS runs the model with in its
  Ground Failure product (:data:`.coefficients.USGS_OPERATIONAL`): the raised
  unconsolidated sediment coefficient, the CTI clip, the slope and PGA masks,
  and rounding. This is the variant the USGS reference output was made with.
"""

from dataclasses import dataclass

import numpy as np

from landloss.hazard.landslide.models.nowicki_2018 import coefficients as c


@dataclass(frozen=True)
class NowickiResult:
    """The model's output for one set of inputs.

    Attributes:
        logit: The linear predictor ``t`` of equation 8.
        relative_hazard: ``P = 1 / (1 + e^-t)``. Not a probability of anything:
            the model was fitted on a sample balanced 1:1 between landslide and
            non-landslide points, which inflates it. Use ``coverage``.
        coverage: Equation 9, the fraction of each cell expected to be covered
            by landslides -- source and runout together, since the training
            inventories did not separate them. Between 0.0005 and 0.256.
        coverage_std: The standard deviation of ``coverage`` by the delta
            method, where PGV uncertainty was supplied; otherwise None.
    """

    logit: np.ndarray
    relative_hazard: np.ndarray
    coverage: np.ndarray
    coverage_std: np.ndarray | None


def logit(
    *,
    pgv_cm_s: np.ndarray,
    slope_deg: np.ndarray,
    rock_coefficient: np.ndarray,
    landcover_coefficient: np.ndarray,
    cti: np.ndarray,
) -> np.ndarray:
    """Evaluate equation 8, the linear predictor.

    Args:
        pgv_cm_s: Peak ground velocity in cm/s.
        slope_deg: Slope in degrees, measured the way the model was fitted --
            from ~250 m median elevation, not from a fine DEM.
        rock_coefficient: Each cell's lithology coefficient, already looked up
            from :data:`.coefficients.GLIM_COEFFICIENTS`.
        landcover_coefficient: Each cell's land cover coefficient, already
            looked up from :data:`.coefficients.GLOBCOVER_COEFFICIENTS`.
        cti: Compound topographic index at ~1 km.

    Returns:
        ``t``, of the inputs' common shape.
    """
    ln_pgv = np.log(pgv_cm_s)
    return (
        c.INTERCEPT
        + c.LN_PGV * ln_pgv
        + c.SLOPE * slope_deg
        + rock_coefficient
        + landcover_coefficient
        + c.CTI * cti
        + c.LN_PGV_X_SLOPE * ln_pgv * slope_deg
    )


def relative_hazard(t: np.ndarray) -> np.ndarray:
    """The logistic function of the linear predictor.

    Args:
        t: The linear predictor from :func:`logit`.

    Returns:
        ``P``, the paper's relative hazard, between 0 and 1.
    """
    return 1.0 / (1.0 + np.exp(-t))


def areal_coverage(p: np.ndarray) -> np.ndarray:
    """Equation 9: convert relative hazard to areal coverage.

    Args:
        p: Relative hazard from :func:`relative_hazard`.

    Returns:
        The fraction of each cell expected to be covered by landslides.
    """
    return np.exp(
        c.COVERAGE_A + c.COVERAGE_B * p + c.COVERAGE_C * p**2 + c.COVERAGE_D * p**3
    )


def _coverage_std(
    *,
    t: np.ndarray,
    p: np.ndarray,
    slope_deg: np.ndarray,
    ln_pgv_std: np.ndarray,
    logit_std: np.ndarray | float,
) -> np.ndarray:
    """Propagate PGV and model uncertainty to coverage by the delta method.

    The same propagation the USGS package uses: the variance of ``t`` is the
    PGV term's sensitivity squared times the ShakeMap's ln(PGV) variance, plus
    the model's own variance; it passes through the logistic function and then
    equation 9 by their first derivatives.
    """
    dt_dlnpgv = c.LN_PGV + c.LN_PGV_X_SLOPE * slope_deg
    var_t = dt_dlnpgv**2 * ln_pgv_std**2 + np.asarray(logit_std) ** 2
    dp_dt = np.exp(-t) / (np.exp(-t) + 1.0) ** 2
    var_p = dp_dt**2 * var_t
    dlp_dp = areal_coverage(p) * (
        c.COVERAGE_B + 2.0 * c.COVERAGE_C * p + 3.0 * c.COVERAGE_D * p**2
    )
    return np.sqrt(dlp_dp**2 * var_p)


def run(
    *,
    pgv_cm_s: np.ndarray,
    slope_deg: np.ndarray,
    rock_coefficient: np.ndarray,
    landcover_coefficient: np.ndarray,
    cti: np.ndarray,
    pga_pct_g: np.ndarray | None = None,
    ln_pgv_std: np.ndarray | None = None,
    logit_std: np.ndarray | float | None = None,
    operational: bool,
) -> NowickiResult:
    """Run the model on aligned input grids.

    Args:
        pgv_cm_s: Peak ground velocity in cm/s.
        slope_deg: Slope in degrees at the model's own ~250 m.
        rock_coefficient: Lithology coefficient per cell.
        landcover_coefficient: Land cover coefficient per cell.
        cti: Compound topographic index at ~1 km, resampled to the grid.
        pga_pct_g: Peak ground acceleration in %g. Only read by the operational
            variant, which blanks cells below 2 %g; required when
            ``operational`` is True.
        ln_pgv_std: The standard deviation of ln(PGV), as a ShakeMap
            ``uncertainty.xml`` gives it. Where supplied, coverage uncertainty
            is propagated and returned.
        logit_std: The model's own standard deviation in logit units, for the
            uncertainty. Defaults to the USGS package's 0.03 when ``ln_pgv_std``
            is given and this is not.
        operational: Whether to apply the USGS operational settings on top of
            the paper; see the module docstring.

    Returns:
        The logit, relative hazard, coverage and, where PGV uncertainty was
        supplied, coverage standard deviation. Cells with any NaN input are NaN
        in every output.

    Raises:
        ValueError: If ``operational`` is True and ``pga_pct_g`` is not given.
    """
    ops = c.USGS_OPERATIONAL
    if operational:
        if pga_pct_g is None:
            msg = "The operational variant masks on PGA, so pga_pct_g is required."
            raise ValueError(msg)
        rock_coefficient = np.where(
            rock_coefficient <= c.GLIM_COEFFICIENTS["su"] + 0.01,
            ops["unconsolidated_coefficient"],
            rock_coefficient,
        )
        cti = np.clip(cti, *ops["cti_clip"])

    t = logit(
        pgv_cm_s=pgv_cm_s,
        slope_deg=slope_deg,
        rock_coefficient=rock_coefficient,
        landcover_coefficient=landcover_coefficient,
        cti=cti,
    )
    p = relative_hazard(t)
    if operational:
        p = np.where(pga_pct_g < ops["pga_min_pct_g"], np.nan, p)

    coverage_std = None
    if ln_pgv_std is not None:
        if logit_std is None:
            logit_std = ops["default_logit_std"]
        coverage_std = _coverage_std(
            t=t, p=p, slope_deg=slope_deg, ln_pgv_std=ln_pgv_std, logit_std=logit_std
        )

    coverage = areal_coverage(p)
    if operational:
        on_slope = (slope_deg > ops["slope_min_deg"]) & (
            slope_deg <= ops["slope_max_deg"]
        )
        coverage = np.round(coverage * on_slope, ops["round_decimals"])

    return NowickiResult(
        logit=t, relative_hazard=p, coverage=coverage, coverage_std=coverage_std
    )
