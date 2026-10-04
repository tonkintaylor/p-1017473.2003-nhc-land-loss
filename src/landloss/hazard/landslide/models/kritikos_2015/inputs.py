"""Build the Kritikos (2015) input layers on one 60 m grid.

The paper stresses that every layer must share one resolution, and its own DEMs
are 60 m, so every layer here is on the same 60 m grid and the memberships were
fitted on that scale. The layers are:

- **Slope angle** from the DEM aggregated to 60 m, by the same Horn slope as
  the rest of the study (:func:`landloss.common.utils.terrain.slope_degrees`).
- **Slope position** from the topographic position index (TPI) of that DEM,
  classified into the paper's four classes (flat, valley, midslope, ridge)
  after Jenness et al. (2013) [jenness_2013].
- **Distance to mapped active faults**, horizontal, to the nearest mapped trace.

Modified Mercalli intensity is not built here: the study's shaking module gives
it from PGV with :func:`landloss.hazard.shaking.pgv.mmi_from_pgv`, and the
validation events read it straight from the ShakeMap
(:mod:`landloss.io.shakemap`).

Two judgements the paper does not settle, both recorded in the step's method
file and both sensitivities rather than fixed values:

- **The TPI neighbourhood.** The paper does not state it, and TPI is scale
  dependent (its own discussion). :func:`gen_slope_position` takes the window
  as an argument; the run settings choose it.
- **The classes.** Jenness et al. (2013) split standardised TPI into six
  classes. The paper keeps four, so the lower and upper slope classes are
  merged into midslope here: a cell is a valley at a standardised TPI of -1 or
  below, a ridge at +1 or above, flat if within half a standard deviation of
  zero on a slope under 5 degrees, and midslope otherwise. The thresholds are
  from the Weiss (2001) [weiss_2001] scheme Jenness's tool implements and are
  marked ``verify`` until Jenness et al. is obtained.
"""

import geopandas as gpd
import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor
import shapely
import xarray as xr
from scipy.spatial import cKDTree

from landloss.common.utils.terrain import (
    block_mean,
    cell_size,
    slope_degrees,
    topographic_position,
)
from landloss.hazard.landslide.models.kritikos_2015 import memberships

# The cell size every layer is built on, in metres.
MODEL_RESOLUTION_M = 60.0

# Standardised TPI at or beyond which a cell is a valley (below) or a ridge
# (above), and within which it is flat or midslope.
RIDGE_VALLEY_SD = 1.0
FLAT_SD = 0.5

# Slope at or below which a cell near the neighbourhood mean is flat, not a
# midslope.
FLAT_MAX_SLOPE_DEG = 5.0

# Mapped traces are densified to this spacing before distances are taken, so
# that the nearest vertex is within half of it of the nearest point on the
# trace. Small against both the 60 m cell and the 5 km fault classes.
TRACE_SPACING_M = 30.0

# Beyond this distance the fault membership is flat, so there is no need to
# find the exact distance.
FAULT_FAR_FIELD_KM = memberships.FAULT_POINTS[-1][0]


def gen_slope_60m(dem: xr.DataArray) -> tuple[xr.DataArray, xr.DataArray]:
    """Aggregate a DEM to 60 m and take its slope.

    Args:
        dem: Ground elevation in metres on a projected grid whose cell size
            divides 60 m into a whole number of cells, NaN as nodata.

    Returns:
        The 60 m DEM and its slope in degrees, on the same grid.

    Raises:
        ValueError: If the DEM's cell size does not divide 60 m exactly.
    """
    factor = MODEL_RESOLUTION_M / cell_size(dem)
    if not np.isclose(factor, round(factor)):
        msg = (
            f"A {cell_size(dem):g} m DEM cannot be block-averaged to "
            f"{MODEL_RESOLUTION_M:g} m: the cell size must divide it exactly."
        )
        raise ValueError(msg)
    dem_60m = dem if round(factor) == 1 else block_mean(dem, round(factor))
    return dem_60m, slope_degrees(dem_60m, MODEL_RESOLUTION_M)


def gen_slope_position(
    dem_60m: xr.DataArray,
    slope_deg: xr.DataArray,
    *,
    window_m: float,
    tpi_sd_m: float | None = None,
) -> xr.DataArray:
    """Classify each cell as flat, valley, midslope or ridge from its TPI.

    Args:
        dem_60m: The 60 m DEM.
        slope_deg: Slope in degrees on the same grid.
        window_m: The TPI neighbourhood width, in metres.
        tpi_sd_m: The standard deviation TPI is standardised by, in metres.
            ``None`` takes it from this grid, which makes the classes depend on
            the extent run; pass the full-study value to hold them fixed.

    Returns:
        The class codes of :mod:`.memberships` as floats, NaN where the TPI or
        slope is, which includes the border half a window wide.
    """
    tpi = topographic_position(dem_60m, MODEL_RESOLUTION_M, window_m).to_numpy()
    sd = float(np.nanstd(tpi)) if tpi_sd_m is None else tpi_sd_m
    z = tpi / sd

    slope = slope_deg.to_numpy()
    classes = np.full(tpi.shape, float(memberships.MIDSLOPE))
    classes[(np.abs(z) < FLAT_SD) & (slope <= FLAT_MAX_SLOPE_DEG)] = memberships.FLAT
    classes[z <= -RIDGE_VALLEY_SD] = memberships.VALLEY
    classes[z >= RIDGE_VALLEY_SD] = memberships.RIDGE
    classes[~np.isfinite(z) | ~np.isfinite(slope)] = np.nan
    return slope_deg.copy(data=classes).rename("slope_position_class")


def gen_fault_distance_km(
    faults: gpd.GeoDataFrame, template: xr.DataArray
) -> xr.DataArray:
    """Return the horizontal distance from each cell to the nearest mapped fault.

    Distances are to the densified trace vertices, within
    :data:`TRACE_SPACING_M` / 2 of the true distance. Faults beyond
    :data:`FAULT_FAR_FIELD_KM` are not searched, because the membership is flat
    there, and a cell with none that close comes back ``inf``.

    Args:
        faults: Mapped fault traces, in any CRS. Features beyond the grid and
            the far-field margin are ignored.
        template: A projected grid, in metres, whose cells are to be measured.
            NaN cells stay NaN.

    Returns:
        Distance in km on the template's grid.
    """
    x = template["x"].to_numpy()
    y = template["y"].to_numpy()
    reach_m = FAULT_FAR_FIELD_KM * 1000.0
    window = shapely.box(
        x.min() - reach_m, y.min() - reach_m, x.max() + reach_m, y.max() + reach_m
    )

    traces = faults.to_crs(template.rio.crs)
    traces = traces[traces.intersects(window)]
    distance = np.full(template.shape, np.inf)
    if len(traces):
        dense = shapely.segmentize(traces.geometry.to_numpy(), TRACE_SPACING_M)
        tree = cKDTree(shapely.get_coordinates(dense))
        grid_x, grid_y = np.meshgrid(x, y)
        nearest, _ = tree.query(
            np.column_stack([grid_x.ravel(), grid_y.ravel()]),
            distance_upper_bound=reach_m,
        )
        distance = nearest.reshape(template.shape) / 1000.0

    distance[np.isnan(template.to_numpy())] = np.nan
    return template.copy(data=distance).rename("fault_distance_km")
