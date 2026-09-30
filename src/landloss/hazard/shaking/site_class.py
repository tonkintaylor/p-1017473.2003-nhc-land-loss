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
- Where the Vs30 model has no value, :func:`fill_site_class_gaps` takes the
  class of the nearest classed cell within :data:`GAP_FILL_MAX_DISTANCE_M`. The
  Foster model leaves such gaps along the harbour edge, where the class is
  assumed to carry on from the ground beside it.
"""

from collections.abc import Callable, Mapping

import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from rasterio.enums import Resampling

# The upper Vs30 bound of each class, in m/s, from the softest up; a site with
# Vs30 above the last bound is Class I. Each bound is inclusive: Vs30 = 750 m/s
# is Class II.
VS30_UPPER_BOUNDS_M_S = {6: 200.0, 5: 250.0, 4: 300.0, 3: 450.0, 2: 750.0}
ROCK_SITE_CLASS = 1

# How far a cell without a Vs30 value may take its class from, in metres,
# between cell centres. Two 100 m cells: far enough to reach the walls along the
# harbour edge that the Foster model leaves unclassed (60 to 194 m from a
# classed cell over the pilot), near enough that the class it takes is the
# ground next to it rather than across a valley.
GAP_FILL_MAX_DISTANCE_M = 200.0


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


def fill_site_class_gaps(
    site_class: xr.DataArray, *, max_distance_m: float = GAP_FILL_MAX_DISTANCE_M
) -> tuple[xr.DataArray, xr.DataArray]:
    """Give unclassed cells the class of the nearest classed cell nearby.

    Distance is between cell centres. Where two classed cells are equally near
    and differ, the softer class (the higher number) is taken: the gaps this
    fills sit along the harbour edge, which is mostly soft or reclaimed ground.

    Args:
        site_class: The site class per cell, NaN where there is none, on a grid
            of square cells.
        max_distance_m: The furthest a cell may take its class from. Cells with
            no classed cell that near stay NaN.

    Returns:
        The filled site class grid, and a boolean grid of the same shape that is
        True where a cell was filled.
    """
    classes = site_class.values
    filled = classes.copy()
    cell_m = float(abs(site_class.x.values[1] - site_class.x.values[0]))
    reach = int(max_distance_m // cell_m)
    # Every offset within reach, nearest first; at equal distance the softer
    # neighbour is chosen below, so the order within a distance does not matter.
    offsets = sorted(
        (
            (dy, dx)
            for dy in range(-reach, reach + 1)
            for dx in range(-reach, reach + 1)
            if 0 < np.hypot(dy, dx) * cell_m <= max_distance_m
        ),
        key=lambda offset: np.hypot(*offset),
    )

    rows, cols = classes.shape
    for row, col in zip(*np.nonzero(np.isnan(classes)), strict=True):
        best_distance, best_class = None, np.nan
        for dy, dx in offsets:
            distance = np.hypot(dy, dx)
            if best_distance is not None and distance > best_distance:
                break
            r, c = row + dy, col + dx
            if 0 <= r < rows and 0 <= c < cols and np.isfinite(classes[r, c]):
                best_distance = distance
                best_class = np.fmax(best_class, classes[r, c])
        filled[row, col] = best_class

    was_filled = np.isnan(classes) & np.isfinite(filled)
    return (
        site_class.copy(data=filled),
        site_class.copy(data=was_filled).rename("site_class_filled"),
    )


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


def demand_on_site_class_grid(
    read_grid: Callable[[int, int], xr.DataArray],
    site_class: xr.DataArray,
    *,
    return_period_yr: int,
) -> xr.DataArray:
    """Put a per-site-class demand on the site class grid, cell by cell.

    Reads the demand grid of each site class present, puts each on the site
    class grid by nearest neighbour, and takes per cell the one for that cell's
    class. The TS1170.5 demand grids are about 9,930 m a cell against the site
    class grid's 100 m, so nearest neighbour is a lookup of the demand cell each
    site class cell falls in, not an interpolation.

    Args:
        read_grid: Reads one demand grid, called as
            ``read_grid(return_period_yr, site_class)`` -- for example
            ``landloss.io.ts1170.get_ts1170_pga``.
        site_class: The site class per cell, with a CRS.
        return_period_yr: The return period of the demand.

    Returns:
        The demand per cell of ``site_class``; NaN where the class is NaN or the
        demand grid carries no value.
    """
    present = sorted({int(c) for c in np.unique(site_class.values) if np.isfinite(c)})
    grids = {
        cls: read_grid(return_period_yr, cls).rio.reproject_match(
            site_class, resampling=Resampling.nearest
        )
        for cls in present
    }
    return select_by_site_class(site_class, grids)
