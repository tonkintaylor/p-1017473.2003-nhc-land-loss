"""The average fuzzy membership curves of Kritikos et al. (2015), Figure 5.

The paper publishes its membership functions only as plots, so these tables
are **digitised** from the dashed "Average" curve of each panel of Figure 5
(journal p. 721), which the authors built to be applied beyond the two
training earthquakes. The curves were read from the figure embedded in the PDF
by locating each dash of the black curve against the panel's own gridlines and
interpolating between dashes; the points are also held, with the class each
belongs to, in ``context/lit/landslide/kritikos_2015/figures/
figure-5-average-membership-points.csv``. Reading error is about 0.02 in
membership. Phase 4 of the plan checks the whole digitisation by reproducing
the paper's own success-rate AUCs [kritikos_2015].

Between points a membership is linearly interpolated, and beyond the plotted
range it is held flat, as the plan sets out.

Two judgements about reading the figure:

- Panels b to e plot membership against *classes*, not a continuous axis, with
  the curve drawn between class centres. Slope angle has even 5 degree classes,
  so its points sit at class centres and edges in degrees. Fault distance has
  classes of unequal width (0-5, 5-10, 10-20, 20-30, 30-40, 40-50 and >50 km),
  and the curve is drawn evenly across class positions, so the points are
  placed at each class centre and at the midpoint between neighbouring centres
  in kilometres, and a distance is interpolated between them.
- The open-ended last class of each axis (>50 degrees, >50 km, >2.5 km) is
  placed one half class beyond the last bounded class.

Distance to streams is tabulated for the record only. The paper drops it from
the final four-factor model.
"""

import numpy as np
import numpy.typing as npt

# MM intensity, from panel (a). The curve is plotted over MM 5 to 9.
MM_POINTS = (
    (5.00, 0.010),
    (5.25, 0.017),
    (5.50, 0.024),
    (5.75, 0.031),
    (6.00, 0.038),
    (6.25, 0.088),
    (6.50, 0.138),
    (6.75, 0.200),
    (7.00, 0.277),
    (7.25, 0.377),
    (7.50, 0.495),
    (7.75, 0.613),
    (8.00, 0.709),
    (8.25, 0.779),
    (8.50, 0.834),
    (8.75, 0.882),
    (9.00, 0.920),
)

# Slope angle in degrees, from panel (b). Class centres 2.5 to 52.5, with the
# class edges between them.
SLOPE_POINTS = (
    (2.5, 0.020),
    (5.0, 0.081),
    (7.5, 0.142),
    (10.0, 0.204),
    (12.5, 0.265),
    (15.0, 0.326),
    (17.5, 0.387),
    (20.0, 0.452),
    (22.5, 0.517),
    (25.0, 0.579),
    (27.5, 0.627),
    (30.0, 0.682),
    (32.5, 0.723),
    (35.0, 0.758),
    (37.5, 0.786),
    (40.0, 0.813),
    (42.5, 0.835),
    (45.0, 0.854),
    (47.5, 0.870),
    (50.0, 0.884),
    (52.5, 0.905),
)

# Distance to the nearest mapped active fault in km, from panel (c).
FAULT_POINTS = (
    (2.5, 1.000),
    (5.0, 0.864),
    (7.5, 0.712),
    (11.25, 0.460),
    (15.0, 0.224),
    (20.0, 0.114),
    (25.0, 0.058),
    (30.0, 0.029),
    (35.0, 0.016),
    (40.0, 0.014),
    (45.0, 0.012),
    (50.0, 0.011),
    (55.0, 0.010),
)

# Distance to the nearest stream in km, from panel (d). Not used by the model.
STREAM_POINTS = (
    (0.25, 1.000),
    (0.75, 0.919),
    (1.25, 0.607),
    (1.75, 0.245),
    (2.25, 0.086),
    (2.75, 0.046),
)

# Slope position classes, from panel (e), in the codes the inputs write.
FLAT = 0
VALLEY = 1
MIDSLOPE = 2
RIDGE = 3
SLOPE_POSITION_MEMBERSHIP = (0.025, 0.342, 0.751, 0.915)


def _interpolate(
    x: npt.ArrayLike, points: tuple[tuple[float, float], ...]
) -> np.ndarray:
    """Interpolate a table of (x, membership) points, flat beyond the ends."""
    xs, ys = zip(*points, strict=True)
    return np.interp(np.asarray(x, dtype=float), xs, ys)


def mm_membership(mm: npt.ArrayLike) -> np.ndarray:
    """Return the membership of Modified Mercalli intensity, 0 to 1.

    Args:
        mm: Modified Mercalli intensity. NaN stays NaN.

    Returns:
        The membership, shaped like ``mm``. Held at the MM 5 and MM 9 values
        beyond them, so intensity above IX adds nothing.
    """
    return _interpolate(mm, MM_POINTS)


def slope_membership(slope_deg: npt.ArrayLike) -> np.ndarray:
    """Return the membership of slope angle, 0 to 1.

    Args:
        slope_deg: Slope angle in degrees. NaN stays NaN.

    Returns:
        The membership, shaped like ``slope_deg``.
    """
    return _interpolate(slope_deg, SLOPE_POINTS)


def fault_membership(distance_km: npt.ArrayLike) -> np.ndarray:
    """Return the membership of distance to the nearest mapped active fault.

    Args:
        distance_km: Horizontal distance to the nearest mapped trace, in km.
            ``inf`` means no fault anywhere near, and gives the far-field
            value. NaN stays NaN.

    Returns:
        The membership, shaped like ``distance_km``.
    """
    return _interpolate(distance_km, FAULT_POINTS)


def stream_membership(distance_km: npt.ArrayLike) -> np.ndarray:
    """Return the membership of distance to the nearest stream.

    Kept for the record: the paper drops this factor from its final model.

    Args:
        distance_km: Distance to the nearest stream, in km. NaN stays NaN.

    Returns:
        The membership, shaped like ``distance_km``.
    """
    return _interpolate(distance_km, STREAM_POINTS)


def slope_position_membership(position_class: npt.ArrayLike) -> np.ndarray:
    """Return the membership of slope position.

    Args:
        position_class: Slope position as the codes :data:`FLAT`,
            :data:`VALLEY`, :data:`MIDSLOPE` and :data:`RIDGE`, as floats so
            that a cell with no class can be NaN.

    Returns:
        The membership, shaped like ``position_class``, NaN where it has none.

    Raises:
        ValueError: If a finite value is not one of the four codes.
    """
    classes = np.asarray(position_class, dtype=float)
    known = np.isfinite(classes)
    if not np.isin(classes[known], (FLAT, VALLEY, MIDSLOPE, RIDGE)).all():
        msg = "slope position classes must be 0 (flat), 1, 2 or 3 (ridge)"
        raise ValueError(msg)
    result = np.full(classes.shape, np.nan)
    result[known] = np.asarray(SLOPE_POSITION_MEMBERSHIP)[classes[known].astype(int)]
    return result
