"""The total area and volume of earthquake-triggered landsliding, Marc et al. (2016).

Marc, Hovius, Meunier, Gorum & Uchida (2016) give one number per earthquake:
the total area (their eq. 12) or total volume (eq. 11) of the landslides it
triggers, from seismological scaling rather than from a map. In this study it
calibrates the **amount** of landsliding each large model predicts. The paper,
its supporting information and a summary are in
``context/lit/landslide/marc_2016/``.

The expression, for one wave source at mean asperity depth R0 (eq. 5), is the
integral of a landslide density linear in shaking above a threshold,
P = alpha (a - a_c) with a = b S / R, over the ground where a > a_c:

    V_ps = pi alpha a_c R0^2 (b S / (R0 a_c) - 1)^2

It is summed over the L / l_asp asperities along a rupture of length L (eq. 6),
and corrected for landscape steepness and for the share of steep ground
(eqs. 11 and 12):

    V = V_ps (L / l_asp) exp(S_mod / T) A_topo

Two equations are implemented as the physics requires rather than as printed,
and both readings are checked in the tests:

- **Eq. 7, fault length** (Leonard 2010). Printed as Mo^(2/5) / (mu C1^(3/2)
  C2), which is not dimensionally a length. The 2/5 power applies to the whole
  ratio, L = (Mo / (mu C1^(3/2) C2))^(2/5), with mu = 3.3e10 Pa (the text's
  "3.3 GPa" reads as 33 GPa). Only this form reproduces the paper's own
  statement that the scaling spans about 3.5 to 225 km for Mw 5 to 8.
- **Eq. 8, strike-slip fault length** beyond the moment at which the fault
  width reaches the seismogenic thickness. As printed it does not join eq. 7
  at that moment. With the width fixed at H_s and slip scaling with the square
  root of rupture area, L = (Mo / (mu C2 H_s^(3/2)))^(2/3), which joins eq. 7
  exactly at L* = (H_s / C1)^(3/2), about 33 km.
"""

from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import pandas as pd

from landloss.io import ASSETS_DIR

# Section 3: the threshold acceleration, normalised by g.
A_C = 0.15

# Section 3.1: the saturated source acceleration times the average site term,
# in km (the paper's 4,000 m), and 30% less for normal faults.
B_SAT_S_KM = MappingProxyType({"R": 4.0, "SS": 4.0, "SS-supershear": 4.0, "N": 2.8})

# Boore & Atkinson (2008) 1 Hz source terms (eqs. 9, 10).
M_HINGE = 6.75
E5 = 0.6728
E6 = -0.1826
E7 = 0.054

# Leonard (2010) fault scaling (eqs. 7, 8), SI units.
SHEAR_MODULUS_PA = 3.3e10
C1_M = 16.5  # m^(1/3)
C2 = 3.7e-5
SEISMOGENIC_THICKNESS_M = 17_000.0

# The characteristic asperity length, km.
L_ASP_KM = 3.0

# Section 4: the landscape sensitivities and steepness scales.
ALPHA_V_M3_PER_KM2 = 4174.0
T_SV_DEG = 11.6
ALPHA_A_M2_PER_KM2 = 3445.0
T_SA_DEG = 15.8

# Section 3.3: the parameter spreads of the Monte Carlo (1 sigma).
A_C_SD = 0.02
B_SAT_SD_FRACTION = 0.1  # 4,000 +/- 400 m
M_HINGE_SD = 0.1

# Fault types Table S1 prints that are not among the caption's codes. "S" is
# read as strike-slip, the nearest code.
_FAULT_TYPE_ALIASES = MappingProxyType({"S": "SS"})

TABLE_S1_SUBEVENTS_PATH = ASSETS_DIR / "marc-2016-table-s1-subevents.csv"


def moment_from_mw(mw: np.ndarray | float) -> np.ndarray:
    """Seismic moment in N m from moment magnitude (Hanks & Kanamori 1979)."""
    return 10.0 ** (1.5 * np.asarray(mw, dtype=float) + 9.1)


def mw_from_moment(moment_nm: np.ndarray | float) -> np.ndarray:
    """Moment magnitude from seismic moment in N m, as the paper uses it."""
    return (2.0 / 3.0) * (np.log10(np.asarray(moment_nm, dtype=float)) - 9.1)


def fault_length_km(moment_nm: np.ndarray | float, fault_type: str) -> np.ndarray:
    """Rupture length from seismic moment (eqs. 7 and 8, Leonard 2010).

    Args:
        moment_nm: Seismic moment, N m.
        fault_type: ``"R"``, ``"N"``, ``"SS"`` or ``"SS-supershear"``.

    Returns:
        Rupture length in km. Strike-slip ruptures switch to eq. 8 once their
        width would exceed the seismogenic thickness.
    """
    moment = np.asarray(moment_nm, dtype=float)
    dip_slip_m = (moment / (SHEAR_MODULUS_PA * C1_M**1.5 * C2)) ** 0.4
    if fault_type.startswith("SS"):
        saturated_m = (
            moment / (SHEAR_MODULUS_PA * C2 * SEISMOGENIC_THICKNESS_M**1.5)
        ) ** (2.0 / 3.0)
        critical_length_m = (SEISMOGENIC_THICKNESS_M / C1_M) ** 1.5
        dip_slip_m = np.where(dip_slip_m > critical_length_m, saturated_m, dip_slip_m)
    return dip_slip_m / 1000.0


def source_acceleration_km(
    mw: np.ndarray | float,
    fault_type: str,
    *,
    b_sat_s_km: np.ndarray | float | None = None,
    m_hinge: np.ndarray | float = M_HINGE,
) -> np.ndarray:
    """The source term b times the site term S, in km (eqs. 9 and 10).

    Args:
        mw: Moment magnitude.
        fault_type: Fault type, which sets b_sat S (normal faults 30% lower).
        b_sat_s_km: Override of the saturated b S, for the Monte Carlo.
        m_hinge: Override of the hinge magnitude, for the Monte Carlo.

    Returns:
        b S in km: the acceleration, as a fraction of g, at 1 km from the
        source, times the site term; divided by the distance in km it gives the
        shaking a.
    """
    if b_sat_s_km is None:
        b_sat_s_km = B_SAT_S_KM[fault_type]
    dm = np.asarray(mw, dtype=float) - m_hinge
    below = np.exp(E5 * dm + E6 * dm**2)
    above = np.exp(E7 * dm)
    return b_sat_s_km * np.where(dm > 0, above, below)


def point_source_integral_km2(
    b_s_km: np.ndarray, r0_km: np.ndarray, a_c: np.ndarray | float
) -> np.ndarray:
    """Pi a_c R0^2 (b S / (R0 a_c) - 1)^2, zero where b S <= a_c R0 (eq. 5).

    The landslide-weighted area around one wave source, in km^2 per unit of
    landscape sensitivity.
    """
    ratio = b_s_km / (r0_km * a_c)
    return np.where(ratio > 1.0, np.pi * a_c * r0_km**2 * (ratio - 1.0) ** 2, 0.0)


@dataclass(frozen=True)
class Source:
    """One earthquake, or one sub-event of an earthquake sequence.

    Attributes:
        mw: Moment magnitude.
        r0_km: Mean asperity depth, km.
        fault_type: ``"R"``, ``"N"``, ``"SS"`` or ``"SS-supershear"``.
        onshore_fraction: The share of the rupture's asperities beneath land.
            The paper's events are onshore, so 1. It excluded subduction events
            because their asperities are mostly offshore; for an interface
            rupture this counts only the asperities under land.
    """

    mw: float
    r0_km: float
    fault_type: str
    onshore_fraction: float = 1.0


def _normalise_fault_type(fault_type: str) -> str:
    return _FAULT_TYPE_ALIASES.get(fault_type, fault_type)


def seismic_term_km2(sources: list[Source]) -> float:
    """The shaking part of eqs. 11 and 12, summed over an earthquake's sources.

    Each source contributes its point-source integral (eq. 5) times its number
    of asperities (eq. 6). Multiplying by the landscape sensitivity, the
    steepness correction and A_topo gives the total; dividing an observed total
    by it isolates the landscape part, which is how the sensitivity is fitted.

    Args:
        sources: The earthquake, or each sub-event of a sequence.

    Returns:
        The seismic term, km^2 per unit of landscape sensitivity.
    """
    total = 0.0
    for source in sources:
        fault = _normalise_fault_type(source.fault_type)
        b_s = source_acceleration_km(source.mw, fault)
        integral = point_source_integral_km2(b_s, source.r0_km, A_C)
        length = fault_length_km(moment_from_mw(source.mw), fault)
        total += float(integral * length / L_ASP_KM * source.onshore_fraction)
    return total


def total_landsliding(
    sources: list[Source],
    *,
    modal_slope_deg: float,
    a_topo: float,
    quantity: str,
) -> float:
    """Total landslide area (km^2) or volume (km^3) for an earthquake (eqs. 11, 12).

    Args:
        sources: The earthquake, or each sub-event of a sequence; the paper sums
            the landsliding of sub-events with more than 30% of the main
            shock's moment.
        modal_slope_deg: The modal slope of the shaken landscape, from 30 m
            slope within 1 km^2 cells, ignoring cells with a modal slope below
            8 degrees.
        a_topo: The share of the predicted landsliding that falls on cells with
            a modal slope of 8 degrees or more.
        quantity: ``"area"`` or ``"volume"``.

    Returns:
        Total area in km^2 or volume in km^3, at the paper's central parameter
        values.
    """
    alpha, t_deg, to_output = _quantity_constants(quantity)
    steepness = np.exp(modal_slope_deg / t_deg)
    return seismic_term_km2(sources) * alpha * steepness * a_topo * to_output


def fit_sensitivity(
    observed: np.ndarray,
    seismic_km2: np.ndarray,
    a_topo: np.ndarray,
    modal_slope_deg: np.ndarray,
    *,
    quantity: str,
) -> tuple[float, float]:
    """Refit the landscape sensitivity and steepness scale (section 4).

    The paper fits ln(observed / (seismic term x A_topo)) against modal slope
    by orthogonal least squares. Refitting on the paper's own events is the
    check that this implementation matches theirs; refitting on New Zealand
    events gives a New Zealand sensitivity.

    Args:
        observed: Observed total area (km^2) or volume (km^3) per earthquake.
        seismic_km2: :func:`seismic_term_km2` per earthquake.
        a_topo: A_topo per earthquake.
        modal_slope_deg: Modal slope per earthquake.
        quantity: ``"area"`` or ``"volume"``, for the units of the result.

    Returns:
        The sensitivity alpha (m^2 or m^3 per km^2) and the steepness scale T
        (degrees).
    """
    _, _, to_output = _quantity_constants(quantity)
    y = np.log(
        np.asarray(observed)
        / to_output
        / (np.asarray(seismic_km2) * np.asarray(a_topo))
    )
    x = np.asarray(modal_slope_deg, dtype=float)
    centred = np.vstack([x - x.mean(), y - y.mean()])
    eigenvectors = np.linalg.svd(centred @ centred.T)[0]
    slope = eigenvectors[1, 0] / eigenvectors[0, 0]
    intercept = y.mean() - slope * x.mean()
    return float(np.exp(intercept)), float(1.0 / slope)


def _quantity_constants(quantity: str) -> tuple[float, float, float]:
    """The sensitivity, steepness scale and unit conversion for a quantity."""
    if quantity == "area":
        return ALPHA_A_M2_PER_KM2, T_SA_DEG, 1.0e-6  # m2 to km2
    if quantity == "volume":
        return ALPHA_V_M3_PER_KM2, T_SV_DEG, 1.0e-9  # m3 to km3
    msg = f"quantity must be 'area' or 'volume', not {quantity!r}."
    raise ValueError(msg)


def total_landsliding_percentiles(
    sources: list[Source],
    *,
    mw_sd: list[float],
    r0_sd_km: list[float],
    modal_slope_deg: float,
    a_topo: float,
    quantity: str,
    samples: int = 50_000,
    seed: int = 1017473,
) -> tuple[float, float, float]:
    """The 25th, 50th and 75th percentiles of total landsliding (section 3.3).

    Samples moment magnitude and asperity depth from each source's stated
    uncertainty, and a_c, b_sat S and the hinge magnitude from the paper's own
    distributions, all normal. The paper also lists a rupture velocity
    (2,000 +/- 200 m/s) among the sampled parameters, but it enters none of the
    equations it prints, so it is not sampled here.

    Args:
        sources: The earthquake or its sub-events.
        mw_sd: One standard deviation of Mw per source.
        r0_sd_km: One standard deviation of R0 per source, km.
        modal_slope_deg: As for :func:`total_landsliding`.
        a_topo: As for :func:`total_landsliding`.
        quantity: ``"area"`` or ``"volume"``.
        samples: Monte Carlo sample size; the paper used 50,000.
        seed: Random seed, so a run reproduces.

    Returns:
        The 25th, 50th and 75th percentiles: the paper's minimum, preferred and
        maximum predictions.
    """
    rng = np.random.default_rng(seed)
    alpha, t_deg, to_output = _quantity_constants(quantity)
    a_c = rng.normal(A_C, A_C_SD, samples).clip(min=0.01)
    m_hinge = rng.normal(M_HINGE, M_HINGE_SD, samples)
    b_scale = rng.normal(1.0, B_SAT_SD_FRACTION, samples).clip(min=0.1)
    total = np.zeros(samples)
    for source, sd_mw, sd_r0 in zip(sources, mw_sd, r0_sd_km, strict=True):
        fault = _normalise_fault_type(source.fault_type)
        mw = rng.normal(source.mw, sd_mw, samples)
        r0 = rng.normal(source.r0_km, sd_r0, samples).clip(min=0.5)
        b_s = source_acceleration_km(
            mw, fault, b_sat_s_km=B_SAT_S_KM[fault] * b_scale, m_hinge=m_hinge
        )
        asperities = (
            fault_length_km(moment_from_mw(mw), fault)
            / L_ASP_KM
            * source.onshore_fraction
        )
        total += point_source_integral_km2(b_s, r0, a_c) * asperities
    total *= alpha * np.exp(modal_slope_deg / t_deg) * a_topo * to_output
    p25, p50, p75 = np.percentile(total, [25, 50, 75])
    return float(p25), float(p50), float(p75)


def get_table_s1() -> pd.DataFrame:
    """Read Marc et al. (2016) Table S1, one row per earthquake or sub-event.

    Source:
        Supporting information to Marc et al. (2016), doi:10.1002/2015JF003732,
        packaged as ``src/landloss/io/assets/marc-2016-table-s1-subevents.csv``
        by ``src/landloss/io/one_offs/gen_marc_2016_table_s1.py``; see the
        assets README for its columns and codes.

    Returns:
        The parsed table.
    """
    return pd.read_csv(TABLE_S1_SUBEVENTS_PATH)


def sources_from_table_s1(
    event: pd.DataFrame,
) -> tuple[list[Source], list[float], list[float]]:
    """Build the sources of one Table S1 earthquake, with their uncertainties.

    Where Table S1 gives R0 as unknown ("?" with a range), R0 is set as the
    paper's methods set it for less constrained cases: at half the hypocentral
    depth where the earthquake exceeds Mw 7.5, otherwise at the hypocentre, with
    a standard deviation of a quarter of the published range.

    Args:
        event: The rows of one earthquake from :func:`get_table_s1`.

    Returns:
        The sources, one standard deviation of Mw per source (from the
        table's 2 sigma on moment), and one standard deviation of R0 per
        source.
    """
    sources, mw_sd, r0_sd = [], [], []
    for _, row in event.iterrows():
        r0 = row["r0_km"]
        sd = row["r0_sd_km"]
        if np.isnan(r0):
            r0 = row["hypocentral_depth_km"] / (2.0 if row["mw"] > 7.5 else 1.0)
            sd = (row["r0_max_km"] - row["r0_min_km"]) / 4.0
        moment_sd = row["moment_2sd_nm"] / 2.0
        mw_upper = mw_from_moment(row["moment_nm"] + moment_sd)
        sources.append(
            Source(mw=float(row["mw"]), r0_km=float(r0), fault_type=row["fault_type"])
        )
        mw_sd.append(float(mw_upper - row["mw"]))
        r0_sd.append(float(sd))
    return sources, mw_sd, r0_sd
