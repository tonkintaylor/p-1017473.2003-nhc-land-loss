"""Terrain derivatives computed from a digital elevation model.

Slope and topographic position are the two numbers that most of this study's
judgement hangs off. A steep section is worth less and is the one that fails in
an earthquake; a spur or a terrace standing above the land around it is worth
more and drains better than the gully beside it. Beside them sits the downhill
direction, which is what turns a failure into a footprint: it decides whose land
the debris lands on. All three are read straight off the DEM, so all three
belong here rather than beside any one model that happens to want them.

Nothing in this module knows about addresses, land value or property. That is
deliberate: the land value model in :mod:`landloss.exposure` and the earthquake
landslide extent work need the same derivatives computed the same way, and a
second implementation would eventually disagree with the first. Anything that is
specific to what a derivative is *used for* belongs in the module that uses it.

Two things are worth stating plainly before any of these numbers are quoted.

Every derivative here is a property of the grid it was computed on, not of the
land. Slope at 10 m is the average gradient across a 30 m window; slope at 1 m
is the gradient across a 3 m window, and on a terraced Wellington hillside those
are different quantities rather than the same quantity at different precisions.
A 10 m slope is not a 1 m slope smoothed, and the two should not be substituted
for one another in a model calibrated on either. See
:data:`landloss.domain.constants.DEM_RESOLUTION_M` for the resolution this study
works at and why.

And nodata is the caller's problem. These functions treat every finite cell as
real ground, so a DEM still carrying -9999 in the sea will grow cliffs around
the coastline. Mask nodata to NaN before calling; NaN then propagates through
both derivatives as it should.
"""

import math
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

# Imported for the side effect of registering the ``.rio`` accessor that
# write_raster uses; the name itself is never referenced.
import rioxarray  # noqa: F401
import xarray as xr
from rasterio import features, windows
from rasterio.enums import Resampling
from shapely.geometry.base import BaseGeometry
from ttpy.gis.raster.aggregation import get_rolling_aggregation
from ttpy.gis.raster.io import save_raster
from ttpy.gis.raster.utils import extract_point_values

# The dimension order every function here expects, and the order
# ``ttpy.gis.raster.aggregation.get_rolling_aggregation`` insists on. A raster
# read by ``ttpy.gis.raster.io.load_raster`` already arrives this way.
RASTER_DIMS = ("y", "x")

# The narrowest neighbourhood a topographic position can be measured over: one
# ring of cells around the centre.
MIN_WINDOW_CELLS = 3

# The names the returned rasters carry, so that a layer written to disk says
# what it holds without the file name having to.
SLOPE_NAME = "slope_degrees"
TOPOGRAPHIC_POSITION_NAME = "topographic_position_m"
LOCAL_RELIEF_NAME = "local_relief_m"
DOWNHILL_AZIMUTH_NAME = "downhill_azimuth_degrees"
CUT_FILL_RESIDUAL_NAME = "cut_fill_residual_m"
PROFILE_CURVATURE_NAME = "profile_curvature_per_m"
VEGETATION_HEIGHT_NAME = "vegetation_height_m"

# The reductions zonal_statistic can apply to the cells under a polygon. A mean
# of an azimuth raster is not among the things it should be asked for; that is
# what zonal_azimuth_mean is for.
ZonalStatistic = Literal["mean", "max", "min", "median"]

# A full turn, in degrees. Named because it appears both as the modulus that
# folds an azimuth into its conventional range and in the checks on one.
FULL_TURN_DEGREES = 360.0


def _check_dims(raster: xr.DataArray) -> None:
    """Raise unless a raster is two dimensional and oriented (y, x).

    Args:
        raster: The raster to check.

    Raises:
        ValueError: If the dimensions are anything other than
            :data:`RASTER_DIMS`. A band dimension left on a GeoTIFF is the usual
            cause, and squeezing it away is the usual fix.
    """
    if tuple(raster.dims) != RASTER_DIMS:
        msg = (
            f"The raster has dimensions {tuple(raster.dims)}, but the terrain "
            f"derivatives need exactly {RASTER_DIMS}. If this came from a "
            "GeoTIFF, squeeze the band dimension away first."
        )
        raise ValueError(msg)


def window_in_cells(window_m: float, resolution: float) -> int:
    """Convert a neighbourhood width in metres to an odd number of cells.

    The rolling window has to be an odd number of cells wide so that it has a
    centre cell to report against. An even request is widened by one rather than
    rejected, because the caller is expressing a length scale in metres and has
    no reason to care that the grid cannot represent it exactly.

    Args:
        window_m: The width of the neighbourhood, in metres.
        resolution: The cell size of the grid, in metres.

    Returns:
        The window width in cells, always odd and never under
        :data:`MIN_WINDOW_CELLS`.

    Raises:
        ValueError: If the requested width is under :data:`MIN_WINDOW_CELLS`
            cells. A one or two cell window has no ring of neighbours to compare
            its centre against, so the answer would be near zero everywhere;
            asking for one means the window and the resolution disagree.
    """
    cells = round(window_m / resolution)

    # Checked before the widening below, so that a two cell request fails rather
    # than being quietly rounded up into a legal three cell window.
    if cells < MIN_WINDOW_CELLS:
        msg = (
            f"A {window_m} m window is {cells} cell(s) at {resolution} m "
            f"resolution, but a topographic position needs at least "
            f"{MIN_WINDOW_CELLS} cells. Widen the window or use a finer grid."
        )
        raise ValueError(msg)

    if cells % 2 == 0:
        cells += 1

    return cells


def _axis_direction(coordinates: np.ndarray, axis: str) -> float:
    """Return +1 if a coordinate runs up with its index, -1 if it runs down.

    A north-up raster -- which is how a GeoTIFF is normally stored, and what
    every raster in this study arrives as -- has its y coordinate *descending*,
    so moving one row down the array moves one cell south. A raster written
    south-up has y ascending instead.

    Slope never had to care, because it is the magnitude of a gradient and comes
    out the same either way. A *direction* does care, and getting it backwards
    points every landslide uphill. So the sign is read off the coordinates
    themselves rather than assumed from a convention the file may not follow.

    Args:
        coordinates: The coordinate values along one axis, in index order.
        axis: The axis name, for the error message.

    Returns:
        +1.0 if the coordinate increases with index, -1.0 if it decreases.

    Raises:
        ValueError: If the axis has fewer than two coordinates, or its
            coordinates do not run one way. A non-monotonic axis is not a grid,
            and nothing here could be computed on it.
    """
    values = np.asarray(coordinates, dtype=float)

    if values.size < 2:
        msg = (
            f"The {axis} axis has {values.size} coordinate(s), so there is no "
            "direction to read off it."
        )
        raise ValueError(msg)

    steps = np.diff(values)
    if np.all(steps > 0):
        return 1.0
    if np.all(steps < 0):
        return -1.0

    msg = (
        f"The {axis} coordinates do not run in one direction, so this is not a "
        "regular grid and no gradient can be computed on it."
    )
    raise ValueError(msg)


def _horn_gradients(
    dem: xr.DataArray, resolution: float
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the eastward and northward components of the terrain gradient.

    Horn's 3x3 kernel, fitted through the eight neighbours of every cell,
    weighting the four that share an edge twice as heavily as the four that
    share only a corner. This is the shared core of :func:`slope_degrees` and
    :func:`downhill_azimuth_degrees`: the steepness and the bearing are the
    magnitude and the direction of the same vector, and computing them twice
    over is how the two would eventually come to disagree.

    The components are returned in *map* orientation -- east and north positive
    -- not in array orientation, so the caller never has to know which way the
    rows of this particular raster run.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres.

    Returns:
        ``(eastward, northward)``, each the rate of change of elevation in
        metres per metre on the same grid as ``dem``. Positive eastward means
        the ground rises towards the east. The one cell border has no complete
        3x3 window and is NaN in both, as is any cell that is itself nodata.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``resolution`` is
            not positive.
    """
    _check_dims(dem)

    if resolution <= 0:
        msg = f"The cell size has to be positive, but {resolution} was given."
        raise ValueError(msg)

    elevation = np.asarray(dem.to_numpy(), dtype=float)
    eastward = np.full(elevation.shape, np.nan)
    northward = np.full(elevation.shape, np.nan)

    rows, columns = elevation.shape
    if rows < MIN_WINDOW_CELLS or columns < MIN_WINDOW_CELLS:
        return eastward, northward

    # The eight neighbours of every interior cell at once, named by where they
    # sit in the *array* -- lower means the next row along, which is south on a
    # north-up raster and north on a south-up one. The two direction factors
    # below are what turn these back into east and north.
    upper_left = elevation[:-2, :-2]
    upper = elevation[:-2, 1:-1]
    upper_right = elevation[:-2, 2:]
    left = elevation[1:-1, :-2]
    right = elevation[1:-1, 2:]
    lower_left = elevation[2:, :-2]
    lower = elevation[2:, 1:-1]
    lower_right = elevation[2:, 2:]

    rise_across_columns = (upper_right + 2 * right + lower_right) - (
        upper_left + 2 * left + lower_left
    )
    rise_down_rows = (lower_left + 2 * lower + lower_right) - (
        upper_left + 2 * upper + upper_right
    )

    run = 8 * resolution
    x_direction = _axis_direction(dem["x"].to_numpy(), "x")
    y_direction = _axis_direction(dem["y"].to_numpy(), "y")

    # Horn's kernel gives the centre cell no weight, so a cell that is itself
    # nodata would otherwise come back with a perfectly reasonable gradient
    # interpolated across the hole. There is no ground there to have one, so it
    # is masked out -- which is what GDAL does too.
    centre = elevation[1:-1, 1:-1]
    hole = np.isnan(centre)

    eastward[1:-1, 1:-1] = np.where(
        hole, np.nan, x_direction * rise_across_columns / run
    )
    northward[1:-1, 1:-1] = np.where(hole, np.nan, y_direction * rise_down_rows / run)

    return eastward, northward


def slope_degrees(dem: xr.DataArray, resolution: float) -> xr.DataArray:
    """Compute slope in degrees by Horn's method.

    Horn's 3x3 kernel is the one GDAL, ArcGIS and the National Liquefaction
    Model all use, so a slope from here is comparable with a slope quoted from
    any of them. It fits a plane through the eight neighbours of a cell,
    weighting the four that share an edge twice as heavily as the four that
    share only a corner::

        dz/dx = ((ne + 2e + se) - (nw + 2w + sw)) / (8 * resolution)
        dz/dy = ((sw + 2s + se) - (nw + 2n + ne)) / (8 * resolution)
        slope = degrees(arctan(hypot(dz/dx, dz/dy)))

    Written out in numpy rather than taken from a library, because every
    packaged implementation reachable from here pulls in numba, and numba forces
    a numpy downgrade that the rest of this project will not tolerate.

    Slope is a property of the cell size it is computed at. This is the average
    gradient over 30 m when ``resolution`` is 10 m, and over 3 m when it is 1 m
    -- a 10 m slope is not a 1 m slope smoothed, and the two are not
    interchangeable.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres. Passed explicitly
            rather than read off the transform, so that the answer cannot
            silently change with how the raster happened to be loaded.

    Returns:
        Slope in degrees on the same grid as ``dem``, from 0 (flat) to 90
        (vertical). The one cell border has no complete 3x3 window and comes
        back as NaN rather than as a one-sided gradient, which would read as a
        plausible small number and quietly flatten every edge of the study area.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``resolution`` is
            not positive.
    """
    eastward, northward = _horn_gradients(dem, resolution)

    # Only the magnitude of the gradient is wanted, so which way either axis
    # runs does not matter: a raster stored south-up gives the same slope.
    slope = np.degrees(np.arctan(np.hypot(eastward, northward)))

    return _as_derivative(dem, slope, SLOPE_NAME)


def downhill_azimuth_degrees(dem: xr.DataArray, resolution: float) -> xr.DataArray:
    """Compute which way each cell faces downhill, as a compass bearing.

    The direction of steepest descent, taken from the same Horn gradient
    :func:`slope_degrees` measures, and reported the way a bearing is quoted on
    a map: degrees clockwise from grid north, so 0 runs north, 90 east, 180
    south and 270 west. This is the aspect GDAL and ArcGIS report, which points
    downslope, rather than the uphill direction some texts use.

    A landslide travels this way. Anything that has to say where displaced
    material ends up needs both this and the slope, and they have to be the same
    gradient or the debris will leave at an angle to the hillside it came off.

    The bearing is a grid bearing, not a true one: it is measured against the
    grid north of the raster's projection, which in New Zealand Transverse
    Mercator differs from true north by up to about a degree and a half across
    the country. Nothing in this study is sensitive to that, but a bearing
    quoted to a surveyor would be.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres.

    Returns:
        The downhill bearing in degrees, in [0, 360), on the same grid as
        ``dem``. NaN on the one cell border, on nodata, and on genuinely level
        ground -- flat land has no downhill direction, and reporting one
        (GDAL reports -9999) would send material off in whichever direction the
        floating point arithmetic happened to round towards.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``resolution`` is
            not positive.
    """
    eastward, northward = _horn_gradients(dem, resolution)

    # Downhill is the direction the gradient points away from, and a compass
    # bearing is measured from north towards east -- which is arctan2 with its
    # arguments the other way round from the mathematical convention.
    azimuth = np.degrees(np.arctan2(-eastward, -northward)) % FULL_TURN_DEGREES

    # A comparison against NaN is False, so this masks the level cells without
    # disturbing the border and the nodata holes, which are NaN already.
    azimuth = np.where(np.hypot(eastward, northward) == 0, np.nan, azimuth)

    return _as_derivative(dem, azimuth, DOWNHILL_AZIMUTH_NAME)


def azimuth_offsets(
    azimuth_degrees: np.ndarray | float, distance: np.ndarray | float
) -> tuple[np.ndarray, np.ndarray]:
    """Convert a bearing and a distance into eastward and northward offsets.

    The counterpart to :func:`downhill_azimuth_degrees`: that says which way a
    landslide runs, this says where it gets to. Kept beside it because the pair
    only agree if they share the same convention, and a second implementation of
    the sine and cosine a few files away is where that agreement gets lost.

    Args:
        azimuth_degrees: The bearing, in degrees clockwise from north.
        distance: How far to travel along it, in the grid's own units.

    Returns:
        ``(eastward, northward)`` offsets, in the same units as ``distance``,
        broadcast against one another. NaN in the bearing carries through to
        both, so a cell with no downhill direction cannot be moved by accident.
    """
    radians = np.radians(np.asarray(azimuth_degrees, dtype=float))
    distance = np.asarray(distance, dtype=float)
    return distance * np.sin(radians), distance * np.cos(radians)


def cell_size(raster: xr.DataArray) -> float:
    """Return the cell size of a raster, in the units of its projection.

    Every derivative in this module takes its resolution as an argument rather
    than reading it off the raster, so that the answer cannot silently change
    with how the file happened to be loaded. That is still the right default for
    a DEM fetched at a resolution the caller chose. It is the wrong one for a
    grid that arrives from somebody else at whatever cell size they built it at,
    where the only honest resolution is the one the grid actually has -- so this
    reads it, once, and hands it to the derivative explicitly.

    Args:
        raster: The raster to measure, carrying a spatial reference.

    Returns:
        The cell size, as a positive number. The sign rioxarray reports on the y
        resolution is a statement about which way the rows run, not about the
        size of a cell, and is dropped here.

    Raises:
        ValueError: If the cells are not square. Every derivative here assumes
            one run length in both directions, and would report a hillside as
            steeper across than along it.
    """
    x_resolution, y_resolution = raster.rio.resolution()

    if not np.isclose(abs(x_resolution), abs(y_resolution)):
        msg = (
            f"The raster has {abs(x_resolution)} by {abs(y_resolution)} cells, "
            "but the terrain derivatives assume square ones. Resample it to a "
            "square grid first."
        )
        raise ValueError(msg)

    return float(abs(x_resolution))


def _as_derivative(dem: xr.DataArray, values: np.ndarray, name: str) -> xr.DataArray:
    """Wrap a computed array back onto its DEM's grid.

    ``copy(data=...)`` keeps the coordinates, and with them the spatial
    reference, so the result can be written straight back out. The fill value is
    dropped on the way through: the DEM's nodata marker is an elevation, and
    leaving it on a raster of degrees would one day blank out a real value that
    happened to match it.

    Args:
        dem: The DEM the values were computed from.
        values: The computed values, on the same grid.
        name: The name the derivative carries.

    Returns:
        The values as a georeferenced raster.
    """
    result = dem.copy(data=values)
    result.attrs.pop("_FillValue", None)
    result.name = name
    return result


def topographic_position(
    dem: xr.DataArray, resolution: float, window_m: float
) -> xr.DataArray:
    """Compute how far each cell stands above or below the land around it.

    The topographic position index is elevation minus the mean elevation of a
    square neighbourhood centred on the cell, in metres. It is positive on
    ridges, spurs and terraces, negative in gullies and on valley floors, and
    near zero both on a plain and on the even part of a uniform hillside -- a
    constant slope has as much ground above it as below it, so it has no
    position to report.

    The window is the whole parameter. A narrow one picks out the local
    micro-terrace; a wide one picks out where the cell sits in the valley.
    Choose it for the landform being looked for, and quote it with the result.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres.
        window_m: The width of the neighbourhood to compare against, in metres.
            Converted to an odd number of cells by :func:`window_in_cells`.

    Returns:
        Metres above (positive) or below (negative) the neighbourhood mean, on
        the same grid as ``dem``. The border half a window wide has no complete
        neighbourhood and comes back as NaN.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``window_m`` is
            narrower than :data:`MIN_WINDOW_CELLS` cells.
    """
    _check_dims(dem)

    window_cells = window_in_cells(window_m, resolution)
    neighbourhood_mean = get_rolling_aggregation(
        dem, aggregate_func="mean", window_size=window_cells
    )

    # Subtracting drops the DEM's attributes, which is what is wanted here: the
    # elevation units and the nodata marker do not describe a difference.
    result = dem - neighbourhood_mean
    result.name = TOPOGRAPHIC_POSITION_NAME
    return result


def local_relief(dem: xr.DataArray, resolution: float, window_m: float) -> xr.DataArray:
    """Compute the elevation range within a neighbourhood of every cell.

    The highest ground in the window minus the lowest, in metres. Where
    :func:`topographic_position` says whether a cell stands above or below what
    is around it, this says how much ground there is between the top and the
    bottom of the neighbourhood at all -- which on a steep face is a reading of
    how tall that face is.

    It is a proxy for a measured toe-to-crest height, not a substitute for one.
    A window wider than the face takes in ground beyond it and overstates the
    height; a window narrower than the face never reaches the crest and
    understates it. Choose the window for the feature being measured, and quote
    it with the result.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres.
        window_m: The width of the neighbourhood, in metres. Converted to an odd
            number of cells by :func:`window_in_cells`.

    Returns:
        The elevation range in metres, on the same grid as ``dem``, never
        negative. The border half a window wide has no complete neighbourhood
        and comes back as NaN.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``window_m`` is
            narrower than :data:`MIN_WINDOW_CELLS` cells.
    """
    _check_dims(dem)

    window_cells = window_in_cells(window_m, resolution)
    highest = get_rolling_aggregation(
        dem, aggregate_func="max", window_size=window_cells
    )
    lowest = get_rolling_aggregation(
        dem, aggregate_func="min", window_size=window_cells
    )

    # Subtracting drops the DEM's attributes, which is right here: the elevation
    # units and the nodata marker do not describe a range.
    result = highest - lowest
    result.name = LOCAL_RELIEF_NAME
    return result


def block_mean(
    dem: xr.DataArray, factor: int, *, min_valid_share: float = 0.5
) -> xr.DataArray:
    """Coarsen a DEM by averaging whole blocks of cells.

    Each coarse cell is the mean elevation of the ``factor`` by ``factor`` block
    of fine cells it covers, so it stands for all the ground inside it. That is
    the point of doing it here rather than asking for a coarse grid from the
    source: LINZ's elevation loader resamples bilinearly, which going from 1 m to
    100 m reads a handful of points per cell and hands back an aliased surface
    whose slope is noise.

    Blocks are counted from the grid's top-left corner, so every coarse cell edge
    falls on a fine cell edge and coarse grids built from the same fine grid by
    factors that divide one another nest exactly. Rows and columns left over at
    the bottom and right that do not fill a whole block are dropped rather than
    averaged over part of a block.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS` and
            a spatial reference.
        factor: How many fine cells along each side one coarse cell spans.
        min_valid_share: The share of a block that must be real ground for the
            block to carry a mean. Anything less comes back as NaN, because a
            mean of the one land cell in a block of nodata is not the elevation
            of that block.

    Returns:
        The coarsened DEM, carrying the same coordinate reference system and a
        transform recomputed for the coarse cell size.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``factor`` is under
            one.
    """
    _check_dims(dem)

    if factor < 1:
        msg = f"A block has to span at least one cell, not {factor}."
        raise ValueError(msg)

    blocks = {"y": factor, "x": factor}
    mean = dem.coarsen(blocks, boundary="trim").mean(skipna=True)
    valid_share = np.isfinite(dem).coarsen(blocks, boundary="trim").mean()
    result = mean.where(valid_share >= min_valid_share)

    # coarsen averages the coordinates as well, which puts each one on the
    # centre of its block. The transform cached on the spatial reference still
    # describes the fine grid, so it is recomputed from those coordinates rather
    # than trusted.
    result = result.rio.write_crs(dem.rio.crs)
    result = result.rio.write_transform(result.rio.transform(recalc=True))
    result.attrs.pop("_FillValue", None)
    result.name = dem.name
    return result


def _check_crs(raster: xr.DataArray, role: str) -> None:
    """Raise unless a raster carries a coordinate reference system.

    Args:
        raster: The raster to check.
        role: What the raster is, for the error message.

    Raises:
        ValueError: If the raster has no CRS. Nothing can be resampled onto, or
            from, a grid whose position on the ground is unknown.
    """
    if raster.rio.crs is None:
        msg = (
            f"The {role} carries no coordinate reference system, so it cannot be "
            "placed against the other grid. Set one with DataArray.rio.write_crs."
        )
        raise ValueError(msg)


def _match_grid(source: xr.DataArray, target: xr.DataArray) -> xr.DataArray:
    """Resample one raster bilinearly onto another's grid.

    Args:
        source: The raster to resample.
        target: The raster whose grid is wanted.

    Returns:
        ``source`` on ``target``'s grid, NaN wherever ``source`` had nothing to
        interpolate from.
    """
    # The fill value is named outright: a raster read with ``masked=True`` may
    # carry NaN on its attributes but nothing in its encoding, and rioxarray
    # otherwise has to guess which of the two describes the array.
    return source.rio.reproject_match(
        target, resampling=Resampling.bilinear, nodata=np.nan
    )


def cut_fill_residual(dem: xr.DataArray, base: xr.DataArray) -> xr.DataArray:
    """Compute how far the ground sits above or below a smoothed version of itself.

    ``dem`` minus ``base``, where ``base`` is a coarser surface of the same
    ground resampled bilinearly onto ``dem``'s grid. A terrace cut into a
    hillside sits below the smooth hillside that was there before it, so it
    reads negative; a platform filled out from it sits above and reads
    positive. The base surface is the whole parameter: against a 30 m surface
    the residual picks out single platforms and cuttings, against a 100 m one
    whole modified hillsides.

    The sign is the reading of a modification, not a proof of one. A natural
    bench reads as fill and a natural gully as cut, which is why the ground map
    uses the residual only where no mapping reaches.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS` and
            a spatial reference.
        base: The smoothed surface, typically :func:`block_mean` of ``dem``, on
            any grid that covers it, with a spatial reference.

    Returns:
        Metres above (positive, fill) or below (negative, cut) the base surface,
        on ``dem``'s grid, named :data:`CUT_FILL_RESIDUAL_NAME`. NaN wherever
        either surface has no value.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if either raster
            carries no coordinate reference system.
    """
    _check_dims(dem)
    _check_crs(dem, "DEM")
    _check_crs(base, "base surface")

    residual = dem.to_numpy() - _match_grid(base, dem).to_numpy()
    return _as_derivative(
        dem, np.asarray(residual, dtype=float), CUT_FILL_RESIDUAL_NAME
    )


def profile_curvature(dem: xr.DataArray, resolution: float) -> xr.DataArray:
    """Compute the curvature of the ground along the direction of steepest descent.

    Zevenbergen and Thorne's partial quartic surface fitted through the 3x3
    window around every cell [zevenbergen_thorne_1987], with the nine cells
    numbered row by row from the top left::

        Z1 Z2 Z3
        Z4 Z5 Z6
        Z7 Z8 Z9

        D = ((Z4 + Z6) / 2 - Z5) / L**2
        E = ((Z2 + Z8) / 2 - Z5) / L**2
        F = (-Z1 + Z3 + Z7 - Z9) / (4 * L**2)
        G = (-Z4 + Z6) / (2 * L)
        H = (Z2 - Z8) / (2 * L)

        profile = 2 * (D * G**2 + E * H**2 + F * G * H) / (G**2 + H**2)

    The sign follows the ArcGIS profile curvature convention: negative where
    the ground is convex along the fall line -- a crest, the lip of a cut --
    and positive where it is concave -- a gully, the toe of a slope. At the
    vertex of a parabola ``z = a * s**2`` along the fall line it equals
    ``2 * a``, the second derivative, so the units are 1/m; ArcGIS reports the
    same quantity scaled by 100.

    The orientation of the raster does not matter: flipping the rows negates
    ``F`` and ``H`` together, which leaves every term unchanged.

    Args:
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`.
        resolution: The cell size of ``dem``, in metres.

    Returns:
        The profile curvature in 1/m on the same grid as ``dem``, named
        :data:`PROFILE_CURVATURE_NAME`. Zero on level ground, where there is
        no fall line to measure along. The one cell border has no complete
        window and comes back as NaN, as does any cell that is itself nodata.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if ``resolution`` is
            not positive.
    """
    _check_dims(dem)

    if resolution <= 0:
        msg = f"The cell size has to be positive, but {resolution} was given."
        raise ValueError(msg)

    elevation = np.asarray(dem.to_numpy(), dtype=float)
    curvature = np.full(elevation.shape, np.nan)

    rows, columns = elevation.shape
    if rows < MIN_WINDOW_CELLS or columns < MIN_WINDOW_CELLS:
        return _as_derivative(dem, curvature, PROFILE_CURVATURE_NAME)

    z1 = elevation[:-2, :-2]
    z2 = elevation[:-2, 1:-1]
    z3 = elevation[:-2, 2:]
    z4 = elevation[1:-1, :-2]
    z5 = elevation[1:-1, 1:-1]
    z6 = elevation[1:-1, 2:]
    z7 = elevation[2:, :-2]
    z8 = elevation[2:, 1:-1]
    z9 = elevation[2:, 2:]

    length_squared = resolution**2
    d = ((z4 + z6) / 2 - z5) / length_squared
    e = ((z2 + z8) / 2 - z5) / length_squared
    f = (-z1 + z3 + z7 - z9) / (4 * length_squared)
    g = (-z4 + z6) / (2 * resolution)
    h = (z2 - z8) / (2 * resolution)

    gradient_squared = g**2 + h**2
    with np.errstate(divide="ignore", invalid="ignore"):
        profile = 2 * (d * g**2 + e * h**2 + f * g * h) / gradient_squared

    # Level ground has no fall line, so the ratio above is 0/0 there. Zero is
    # the honest value -- there is no bend along a direction that does not
    # exist -- and it is what ArcGIS reports. A window with a hole in it stays
    # NaN: gradient_squared is NaN there, and the comparison is False.
    profile = np.where(gradient_squared == 0, 0.0, profile)
    curvature[1:-1, 1:-1] = profile

    return _as_derivative(dem, curvature, PROFILE_CURVATURE_NAME)


def vegetation_height(
    dsm: xr.DataArray,
    dem: xr.DataArray,
    buildings: gpd.GeoSeries | None = None,
) -> xr.DataArray:
    """Compute the height of whatever stands on the ground, from a surface model.

    The digital surface model minus the bare-earth DEM, with the surface model
    resampled bilinearly onto the DEM's grid first. Over a hillside that is
    tree canopy; over a building it is the roof. Given ``buildings``, every
    cell whose centre lies in an outline is NaN, so what is left is
    vegetation and other structures rather than rooftops.

    Args:
        dsm: The surface elevation in metres, on any grid covering ``dem``,
            with a spatial reference.
        dem: Ground elevation in metres, with dimensions :data:`RASTER_DIMS`
            and a spatial reference.
        buildings: Building outlines in the DEM's system, masked out. None
            keeps every cell.

    Returns:
        Metres of surface above the ground on ``dem``'s grid, named
        :data:`VEGETATION_HEIGHT_NAME`, never negative: a surface model below
        the ground is survey noise, not a hole, and is clipped to zero. NaN
        wherever either model has no value, which is every cell outside the
        surveys the surface model was flown over.

    Raises:
        ValueError: If ``dem`` is not oriented (y, x), or if either raster
            carries no coordinate reference system.
    """
    _check_dims(dem)
    _check_crs(dem, "DEM")
    _check_crs(dsm, "surface model")

    height = _match_grid(dsm, dem).to_numpy() - dem.to_numpy()
    height = np.asarray(height, dtype=float)
    height = np.where(np.isnan(height), np.nan, np.maximum(height, 0.0))
    if buildings is not None and not buildings.empty:
        roofs = features.geometry_mask(
            buildings.to_numpy(),
            out_shape=height.shape,
            transform=dem.rio.transform(),
            invert=True,
        )
        height = np.where(roofs, np.nan, height)
    return _as_derivative(dem, height, VEGETATION_HEIGHT_NAME)


def _unit_vector_mean(azimuth_degrees: np.ndarray) -> tuple[float, float]:
    """Return the bearing of the mean unit vector of a set of bearings, and its length.

    Args:
        azimuth_degrees: Bearings in degrees clockwise from north. NaN is
            skipped.

    Returns:
        ``(mean_bearing, resultant_length)``: the bearing of the mean vector
        in [0, 360) and the length of that vector, 1 where every bearing
        agrees and 0 where they cancel. Both NaN when nothing is finite.
    """
    values = np.asarray(azimuth_degrees, dtype=float).ravel()
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan, np.nan

    radians = np.radians(values)
    # Bearings run clockwise from north, so the sine is the eastward component
    # and the cosine the northward one, as azimuth_offsets has them.
    eastward = float(np.mean(np.sin(radians)))
    northward = float(np.mean(np.cos(radians)))
    mean_bearing = np.degrees(np.arctan2(eastward, northward)) % FULL_TURN_DEGREES
    # A bearing a rounding error short of north comes out of the modulus as
    # 360.0 rather than 0.0, which is outside the range a bearing lives in.
    if mean_bearing >= FULL_TURN_DEGREES:
        mean_bearing = 0.0
    return float(mean_bearing), float(np.hypot(eastward, northward))


def mean_azimuth_degrees(azimuth_degrees: np.ndarray) -> float:
    """Compute the circular mean of a set of bearings.

    An arithmetic mean of 350 and 10 degrees is 180, due south, when the two
    bearings are both a few degrees off due north. The circular mean is the
    bearing of the sum of the unit vectors, which is 0 for that pair, and it is
    what any statement about which way a patch of hillside faces has to use.

    Args:
        azimuth_degrees: Bearings in degrees clockwise from north, any shape.
            NaN is skipped.

    Returns:
        The mean bearing in [0, 360). NaN when nothing is finite, and NaN when
        the bearings cancel exactly, which leaves no mean direction.
    """
    mean_bearing, length = _unit_vector_mean(azimuth_degrees)
    if np.isfinite(length) and np.isclose(length, 0.0):
        return np.nan
    return mean_bearing


def azimuth_sd_degrees(azimuth_degrees: np.ndarray) -> float:
    """Compute the circular standard deviation of a set of bearings.

    ``sqrt(-2 ln R)`` in radians, converted to degrees, where ``R`` is the
    length of the mean unit vector: 0 when every bearing agrees, growing
    without bound as they spread. It is how a slope unit says whether it faces
    one way or wraps around a spur.

    Args:
        azimuth_degrees: Bearings in degrees clockwise from north, any shape.
            NaN is skipped.

    Returns:
        The circular standard deviation in degrees. NaN when nothing is finite;
        infinite when the bearings cancel exactly.
    """
    _mean_bearing, length = _unit_vector_mean(azimuth_degrees)
    if not np.isfinite(length):
        return np.nan
    if np.isclose(length, 0.0):
        return np.inf
    return float(np.degrees(np.sqrt(-2.0 * np.log(min(length, 1.0)))))


def _polygon_cells(
    source: rasterio.DatasetReader, geometry: BaseGeometry
) -> np.ndarray:
    """Read the finite raster cells whose centres fall inside one polygon.

    Args:
        source: The open raster.
        geometry: The polygon, in the raster's coordinate reference system.

    Returns:
        The finite values of the cells inside the polygon, as a flat array;
        empty when no cell centre falls inside it.
    """
    minx, miny, maxx, maxy = geometry.bounds
    bounds = windows.from_bounds(minx, miny, maxx, maxy, transform=source.transform)
    # Widened to whole cells so that a boundary running through a cell still
    # reads that cell, then clipped to the raster so the read never falls off
    # the edge. Done by hand because rasterio's own intersection raises on an
    # empty window, and a polygon off the raster is an answer, not an error.
    col_start = max(0, math.floor(bounds.col_off))
    row_start = max(0, math.floor(bounds.row_off))
    col_stop = min(source.width, math.ceil(bounds.col_off + bounds.width))
    row_stop = min(source.height, math.ceil(bounds.row_off + bounds.height))
    if col_stop <= col_start or row_stop <= row_start:
        return np.empty(0)
    window = windows.Window(
        col_start, row_start, col_stop - col_start, row_stop - row_start
    )

    values = source.read(1, window=window, masked=True).filled(np.nan)
    values = np.asarray(values, dtype=float)
    inside = ~features.geometry_mask(
        [geometry],
        out_shape=values.shape,
        transform=windows.transform(window, source.transform),
        all_touched=False,
    )
    selected = values[inside]
    return selected[np.isfinite(selected)]


def _zonal_reduce(
    raster_path: Path | str,
    polygons: gpd.GeoSeries,
    reduce: Callable[[np.ndarray], float],
) -> pd.Series:
    """Apply one reduction to the cells of a raster under each polygon.

    Args:
        raster_path: The raster to read, as a GeoTIFF on disk.
        polygons: The polygons to read under.
        reduce: A function from a flat array of finite values to one number.

    Returns:
        One value per polygon, on ``polygons.index``; NaN where no finite cell
        centre falls inside the polygon or its geometry is empty.
    """
    with rasterio.open(raster_path) as source:
        if source.crs is not None and polygons.crs != source.crs:
            polygons = polygons.to_crs(source.crs)

        result = np.full(len(polygons), np.nan)
        for position, geometry in enumerate(polygons.geometry):
            if geometry is None or geometry.is_empty:
                continue
            cells = _polygon_cells(source, geometry)
            if cells.size:
                result[position] = reduce(cells)

    return pd.Series(result, index=polygons.index, dtype=float)


def zonal_statistic(
    raster_path: Path | str,
    polygons: gpd.GeoSeries,
    *,
    statistic: ZonalStatistic = "mean",
) -> pd.Series:
    """Reduce the raster cells under each polygon to one number.

    A cell belongs to a polygon when its centre falls inside it, as
    ``rasterio.features.geometry_mask`` decides, so a sliver thinner than a
    cell may hold no cells at all and reads as NaN rather than as the value
    of whichever cell it happens to touch. The companion to
    :func:`sample_at_points` for the patches and units the landslide work
    reads terrain onto.

    An azimuth raster must not be reduced here: the arithmetic mean of 350 and
    10 degrees is due south. Use :func:`zonal_azimuth_mean` for one.

    Args:
        raster_path: The raster to read, as a GeoTIFF on disk.
        polygons: The polygons to read under. Reprojected to the raster's
            coordinate reference system if they are not already in it.
        statistic: Which reduction to apply over the finite cells.

    Returns:
        One value per polygon, indexed as ``polygons`` is. NaN where no finite
        cell centre falls inside a polygon, or its geometry is empty.

    Raises:
        ValueError: If ``statistic`` is not one of the reductions offered.
    """
    reductions: dict[str, Callable[[np.ndarray], float]] = {
        "mean": np.mean,
        "max": np.max,
        "min": np.min,
        "median": np.median,
    }
    if statistic not in reductions:
        msg = f"Unknown statistic {statistic!r}; choose one of {', '.join(reductions)}."
        raise ValueError(msg)

    return _zonal_reduce(raster_path, polygons, reductions[statistic])


def zonal_azimuth_mean(raster_path: Path | str, polygons: gpd.GeoSeries) -> pd.Series:
    """Compute the circular mean bearing of an azimuth raster under each polygon.

    :func:`zonal_statistic` with :func:`mean_azimuth_degrees` as the
    reduction, kept as its own function so that a caller reading an aspect
    raster onto patches cannot reach for the arithmetic mean by habit.

    Args:
        raster_path: The azimuth raster to read, in degrees clockwise from
            north, as a GeoTIFF on disk.
        polygons: The polygons to read under. Reprojected to the raster's
            coordinate reference system if they are not already in it.

    Returns:
        The mean bearing in [0, 360) per polygon, indexed as ``polygons`` is.
        NaN where no finite cell centre falls inside a polygon.
    """
    return _zonal_reduce(raster_path, polygons, mean_azimuth_degrees)


def sample_at_points(raster_path: Path | str, points: gpd.GeoSeries) -> pd.Series:
    """Read a raster value at each of a set of points.

    A thin wrapper over :func:`ttpy.gis.raster.utils.extract_point_values`,
    which returns a bare list. Every caller wants to assign the result onto the
    frame the points came from, and a list aligns by position -- which is the
    same as aligning by label right up until the frame has been filtered, at
    which point it is silently wrong. Returning a Series on the caller's own
    index removes that failure mode.

    Args:
        raster_path: The raster to read, as a GeoTIFF on disk.
        points: The points to sample at. Reprojected to the raster's coordinate
            reference system if they are not already in it.

    Returns:
        The sampled values, indexed as ``points`` is. NaN where a point falls
        outside the raster, on a nodata cell, or has empty geometry.
    """
    values = extract_point_values(Path(raster_path), points)
    return pd.Series(values, index=points.index, dtype=float)


def write_raster(raster: xr.DataArray, path: Path | str) -> Path:
    """Write a raster to disk, creating the directory it goes in.

    Creating the directory is the point. These derivatives get written and then
    immediately sampled, and a caller that has to make the parent directory
    itself before every write will one day forget to.

    Args:
        raster: The raster to write.
        path: Where to write it. The suffix chooses the format, and
            :func:`ttpy.gis.raster.io.save_raster` accepts ``.tif``, ``.tiff``
            and ``.zarr``.

    Returns:
        The path written to, so that a caller can write and then sample in one
        expression.

    Raises:
        ValueError: If the raster carries no coordinate reference system. It
            would still write, but nothing could be sampled against it
            afterwards, and that failure would surface a long way from here.
    """
    if raster.rio.crs is None:
        msg = (
            f"The raster bound for {path} has no coordinate reference system, "
            "so nothing could be sampled against it once written. Set one with "
            "DataArray.rio.write_crs before writing."
        )
        raise ValueError(msg)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_raster(raster, path)
    return path
