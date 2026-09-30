"""TS1170.5:2025 site class from Vs30, and picking a per-class grid per cell.

SNZ TS 1170.5:2025 Table 3.3 classes a site from I to VII. Its Vs30 bounds are:

    Vs30 > 750 m/s          I
    450 < Vs30 <= 750       II
    300 < Vs30 <= 450       III
    250 < Vs30 <= 300       IV
    200 < Vs30 <= 250       V
    150 < Vs30 <= 200       VI
    Vs30 <= 150             VII

Classes are returned as the integers 1 to 6, the convention of
:mod:`landloss.io.ts1170` and :mod:`landloss.io.nlm`.

Limitations -- the classification is on Vs30 alone:

- Table 3.3 also sets criteria on the profile that a Vs30 value does not carry.
  Class I needs no more than 3 m of soil or highly weathered rock over the
  bedrock, and nothing slower than 600 m/s below it; a site with Vs30 above
  750 m/s that fails either is Class II. Class II falls to III if it is
  underlain by material slower than 300 m/s, and Class V becomes VI where the
  top 20 m holds more than 10 m of very soft or loose soils. None of that is
  checked here, so, for example, rock under weathered cover with Vs30 above
  750 m/s is classed I.
- Class VII is returned as VI. The TS requires a site-specific response
  analysis for VII, floored at the VI spectrum (clause 3.1.3.2), and Table 3.2
  carries no VII parameters; the floor is used without the analysis.
- One class per cell, from the Vs30 central estimate. The multiple site
  classes of clause 3.1.3.4, for a Vs30 range spanning more than one class, are
  not considered.
"""

from collections.abc import Mapping

import numpy as np
import xarray as xr

# The upper Vs30 bound of each class, in m/s, from the softest up; a site with
# Vs30 above the last bound is Class I. Each bound is inclusive: Vs30 = 750 m/s
# is Class II.
VS30_UPPER_BOUNDS_M_S = {6: 200.0, 5: 250.0, 4: 300.0, 3: 450.0, 2: 750.0}
ROCK_SITE_CLASS = 1


def ts1170_site_class_from_vs30(
    vs30: np.ndarray | xr.DataArray,
) -> np.ndarray | xr.DataArray:
    """Assign the TS1170.5 site class from Vs30 alone.

    See the module docstring for what Vs30 alone cannot capture. Vs30 at or
    below 150 m/s (Class VII) is returned as Class VI.

    Args:
        vs30: Vs30 in m/s. An ``xarray.DataArray`` keeps its coordinates and
            CRS.

    Returns:
        The site class, 1 to 6, as floats so that NaN Vs30 stays NaN; same type
        and shape as ``vs30``.
    """
    values = np.asarray(vs30, dtype=float)
    site_class = np.full(values.shape, float(ROCK_SITE_CLASS))
    # Walk from the stiffest bound down, so each softer class overwrites the
    # cells at or below its own bound.
    for cls, upper in sorted(
        VS30_UPPER_BOUNDS_M_S.items(), key=lambda item: item[1], reverse=True
    ):
        site_class[values <= upper] = cls
    site_class[np.isnan(values)] = np.nan

    if isinstance(vs30, xr.DataArray):
        return vs30.copy(data=site_class).rename("site_class")
    return site_class


def select_by_site_class(
    site_class: xr.DataArray, grids_by_class: Mapping[int, xr.DataArray]
) -> xr.DataArray:
    """Pick, per cell, the value of the grid for that cell's site class.

    The grids are matched to ``site_class`` by position, not by coordinate, so
    each must already be on its grid (``rio.reproject_match``). Matching by
    coordinate would let a floating-point difference in the cell centres drop
    cells silently.

    Args:
        site_class: The site class per cell, e.g. from
            :func:`ts1170_site_class_from_vs30`.
        grids_by_class: One grid per site class, each the shape of
            ``site_class``.

    Returns:
        A copy of ``site_class``, coordinates and CRS included, carrying the
        selected values; NaN where the class is NaN.

    Raises:
        ValueError: If a class present in ``site_class`` has no grid, or a grid
            is not the shape of ``site_class``.
    """
    classes = site_class.values
    present = {int(c) for c in np.unique(classes) if np.isfinite(c)}
    missing = present - set(grids_by_class)
    if missing:
        msg = f"No grid given for site class(es) {sorted(missing)}."
        raise ValueError(msg)

    selected = np.full(classes.shape, np.nan)
    for cls, grid in grids_by_class.items():
        if grid.shape != classes.shape:
            msg = f"The site class {cls} grid is {grid.shape}, not {classes.shape}."
            raise ValueError(msg)
        selected = np.where(classes == cls, grid.values, selected)

    return site_class.copy(data=selected)
