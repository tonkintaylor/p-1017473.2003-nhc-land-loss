"""The Hancox et al. (1997) and Hancox (2010) New Zealand landslide relationships.

Every relationship here is empirical, from 22 historical New Zealand
earthquakes, all of them shallow crustal events. Distances are **epicentral**,
because the report could not define the rupture geometry of most of its
events (its section 3.4).

- **Area affected** (section 3.3, Figure 19): the area *within which*
  landslides occurred, drawn as a boundary around the reported landslide
  localities. It is not the area that slid, so it constrains extent only.
- **Maximum epicentral distance** by landslide size (section 3.4, Figures 20.1
  and 20.2).
- **Intensity thresholds** (section 1.2 and the abstract).
- **Slope-class shares** of historical earthquake-induced landslides (Hancox
  2010, Table 2).

The digitised Figure 19 points are packaged as
``src/landloss/io/assets/hancox-1997-figure-19-area-affected.csv``. Refitting
them with the report's two smallest events left out (Peria 1963 and Waiotapu
1983) returns log10 A = 0.97 M - 3.72, standard error 0.45, R² 0.67, against
the published 0.96 M - 3.7, 0.43 and 68%; see the tests.
"""

from types import MappingProxyType

import numpy as np
import numpy.typing as npt
import pandas as pd

from landloss.io import ASSETS_DIR

FIGURE_19_PATH = ASSETS_DIR / "hancox-1997-figure-19-area-affected.csv"

# Section 3.3: log10 A = 0.96 (+/- 0.16) M - 3.7 (+/- 1.1), A in km², with a
# standard error of the estimate of log10 A of 0.43.
AREA_SLOPE = 0.96
AREA_INTERCEPT = -3.7
AREA_LOG10_SE = 0.43
# Section 3.3, the published inverse: M = 1.04 log10 A + 3.85.
MAGNITUDE_SLOPE = 1.04
MAGNITUDE_INTERCEPT = 3.85

# Figure 20.1: the solid "approximate upper bound of NZ data" line, digitised
# from context/lit/landslide/hancox_1997/figures/page-076.png as
# log10 D = 0.464 M - 1.32, D in km. It gives 10, 29, 84 and 304 km at M 5, 6,
# 7 and 8.2, against the text's "about 10 km for M 5, 30 km for M 6, 100 km
# for M 7, and almost 300 km for M 8.2".
DISTANCE_SLOPE = 0.464
DISTANCE_INTERCEPT = -1.32

# Section 3.4 and Figure 20.1: the smallest magnitude at which each landslide
# size class has occurred in New Zealand, and the largest epicentral distance
# at which it has occurred, in km, where that is less than the upper-bound
# line. Volumes in m³ are the report's size terms.
#
# - Very small to small (up to 1e4 m³): the upper-bound line throughout, from
#   the smallest event plotted, Waiotapu 1983 at M 4.6.
# - Moderate to large (1e4 to 1e6 m³): "only occur at magnitudes greater than
#   6 to 6.5 at epicentral distances of about 5 km (MM8) to 70 km (MM7)". The
#   smallest plotted is Arthur's Pass 1994 at M 6.6.
# - Very large (1 to 50 x 1e6 m³) and extremely large (over 50 x 1e6 m³):
#   "only occur at magnitudes greater than about M 6.9 and 7.1 respectively",
#   within "almost 100 km".
SIZE_CLASSES = ("small", "moderate_large", "very_large", "extremely_large")
SIZE_CLASS_MIN_MAGNITUDE = MappingProxyType(
    {"small": 4.6, "moderate_large": 6.5, "very_large": 6.9, "extremely_large": 7.1}
)
SIZE_CLASS_MAX_DISTANCE_KM = MappingProxyType(
    {
        "small": np.inf,
        "moderate_large": 70.0,
        "very_large": 100.0,
        "extremely_large": 100.0,
    }
)

# Intensity below which no significant landsliding occurs: MM7 in the
# Wellington Region (Hancox et al. 1994, restated in section 1.2 and
# attributed there to greywacke), MM6 elsewhere in New Zealand (abstract).
MM_THRESHOLD_WELLINGTON = 7
MM_THRESHOLD_NZ = 6

# Hancox (2010) Table 2, slope angles of historical earthquake-induced
# landslides in New Zealand, as printed: 1% gentle (0-15 deg), 9% moderate
# (16-25 deg), 39% steep (26-35 deg) and 60% very steep (over 35 deg), the
# last split as 40% for 36-45 deg and 20% above 45 deg. It sums to 109%.
SLOPE_CLASS_EDGES_DEG = (0.0, 15.5, 25.5, 35.5, 45.5, 90.0)
SLOPE_CLASSES = ("gentle", "moderate", "steep", "very_steep", "extremely_steep")
SLOPE_SHARES_PRINTED = MappingProxyType(
    {
        "gentle": 0.01,
        "moderate": 0.09,
        "steep": 0.39,
        "very_steep": 0.40,
        "extremely_steep": 0.20,
    }
)
# The shares adopted. Counting the landslides plotted in the 1997 report's
# Figure 22.1 (about 145, from six earthquakes) by slope angle gives about 4%,
# 14%, 39% and 43% for the four printed classes, so the 39% for steep slopes
# stands and the very-steep 60% is what over-runs. The very-steep share is
# therefore the remainder, 51%, split 2:1 above and below 45 deg as printed.
SLOPE_SHARES = MappingProxyType(
    {
        "gentle": 0.01,
        "moderate": 0.09,
        "steep": 0.39,
        "very_steep": 0.34,
        "extremely_steep": 0.17,
    }
)


def area_affected_km2(mw: npt.ArrayLike, n_se: float = 0.0) -> np.ndarray:
    """The area within which an earthquake triggers landslides, in km².

    Args:
        mw: Magnitude, scalar or array. The report mixes ML, MS and Mw.
        n_se: Standard errors of the estimate to add to log10 A: 0 for the
            mean line, -1 and 1 for the band either side of it.

    Returns:
        The area affected, in km², shaped like ``mw``.
    """
    return 10.0 ** (
        AREA_SLOPE * np.asarray(mw, dtype=float) + AREA_INTERCEPT + n_se * AREA_LOG10_SE
    )


def mw_from_area_affected(area_km2: npt.ArrayLike) -> np.ndarray:
    """The magnitude implied by an area affected, the report's published inverse.

    Args:
        area_km2: Area affected by landsliding, km².

    Returns:
        The magnitude, shaped like ``area_km2``.
    """
    return MAGNITUDE_SLOPE * np.log10(np.asarray(area_km2, dtype=float)) + (
        MAGNITUDE_INTERCEPT
    )


def max_distance_km(mw: npt.ArrayLike, size_class: str = "small") -> np.ndarray:
    """The largest epicentral distance at which a size of landslide has occurred.

    The Figure 20.1 upper-bound line, capped for the larger size classes at the
    distance the report gives for them, and zero below the smallest magnitude
    at which the class has occurred.

    Args:
        mw: Magnitude, scalar or array.
        size_class: One of :data:`SIZE_CLASSES`.

    Returns:
        The distance in km, shaped like ``mw``.

    Raises:
        ValueError: If ``size_class`` is not one of :data:`SIZE_CLASSES`.
    """
    if size_class not in SIZE_CLASSES:
        msg = f"size_class must be one of {SIZE_CLASSES}, not {size_class!r}"
        raise ValueError(msg)
    mw = np.asarray(mw, dtype=float)
    line = 10.0 ** (DISTANCE_SLOPE * mw + DISTANCE_INTERCEPT)
    capped = np.minimum(line, SIZE_CLASS_MAX_DISTANCE_KM[size_class])
    return np.where(mw >= SIZE_CLASS_MIN_MAGNITUDE[size_class], capped, 0.0)


def slope_class(slope_deg: npt.ArrayLike) -> np.ndarray:
    """The Hancox (2010) Table 2 slope class of each slope angle.

    Args:
        slope_deg: Slope angle in degrees, scalar or array.

    Returns:
        The index into :data:`SLOPE_CLASSES`, shaped like ``slope_deg``.
    """
    edges = np.asarray(SLOPE_CLASS_EDGES_DEG[1:-1])
    return np.digitize(np.asarray(slope_deg, dtype=float), edges)


def get_figure_19() -> pd.DataFrame:
    """Read the digitised Figure 19 points, one row per earthquake.

    Digitised from ``context/lit/landslide/hancox_1997/figures/page-075.png``
    by locating each filled dot against the axis ticks. ``number`` and
    ``name`` follow the report's Table 2, and ``in_regression`` is false for
    the two smallest events, which the report says it left out.

    Returns:
        The table, with ``magnitude`` and ``area_km2`` as read off the figure.
    """
    return pd.read_csv(FIGURE_19_PATH)
