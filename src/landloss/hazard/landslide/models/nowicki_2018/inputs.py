"""Build the Nowicki Jessee (2018) input layers from their raw public sources.

Every layer is rebuilt here, from the datasets the paper names, to the paper's
own specification -- not taken from the USGS's pre-processed rasters. That is a
project decision (see the landslide rebuild note, "The USGS software"): the
whole pipeline stays under our control, and the USGS rasters are used only to
check it (``src/scripts/landloss/hazard/landslide/validations/``).

All grids are geographic (EPSG:4326), because every source is, and because the
model's coefficients are tied to the sources' own resolutions:

- **Slope** from GMTED2010 7.5 arc-second *median* elevation, resampled onto
  the model grid and differentiated there by central differences in metres
  (the paper computed it with GMT). The model grid is 7.5 arc-seconds,
  registered to whole multiples of the cell size as the USGS's global slope
  layer is (:func:`gen_model_grid`), and every other layer is brought onto it,
  as the USGS package does with its slope layer as the base layer.
- **Lithology** from GLiM's top-level classes, rasterised onto the model grid
  and looked up in Table 3.
- **Land cover** from GlobCover 2009 at its native 1/360 degree, looked up in
  Table 3, then nearest-neighbour resampled.
- **CTI** as ``ln(A / tan b)`` from 30 arc-second elevation, with ``A`` the
  upstream area in km^2 -- HYDRO1k's convention on its ~1 km cells, which is
  what the model was fitted on -- then bilinear resampled.
- **Shaking** bilinear resampled from whatever grid it arrives on.
"""

from typing import TYPE_CHECKING

import numpy as np
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import Affine

from landloss.common.utils.hydrology import (
    d8_receivers,
    flow_accumulation,
    priority_flood,
)
from landloss.hazard.landslide.models.nowicki_2018 import coefficients as c

if TYPE_CHECKING:
    import geopandas as gpd

# The CRS every layer here is built in.
GEOGRAPHIC_CRS = "EPSG:4326"

# The Earth radius for converting degrees to metres. GMT's default mean radius.
EARTH_RADIUS_M = 6_371_008.7714

# The smallest tan(slope) CTI is computed with, so a filled flat does not give
# an infinite index. 0.001 is a 1 m fall over 1 km.
CTI_MIN_TAN_SLOPE = 1.0e-3

# GMTED2010 holds the sea at exactly 0 m rather than as nodata. For flow
# routing the sea has to be nodata, so that the coast is an outlet; cells at or
# below this elevation are taken as sea. On the Loma Prieta check this
# reproduces the USGS CTI raster's own nodata almost cell for cell.
SEA_MAX_ELEVATION_M = 0.0


def _check_geographic(raster: xr.DataArray) -> None:
    if raster.rio.crs is None or raster.rio.crs.to_epsg() != 4326:
        msg = (
            f"Expected a raster in {GEOGRAPHIC_CRS}, got {raster.rio.crs}. The "
            "model's inputs are all built on geographic grids."
        )
        raise ValueError(msg)


def _resolution_deg(raster: xr.DataArray) -> tuple[float, float]:
    """Return the (x, y) cell size in degrees, from the coordinates."""
    return (
        float(abs(np.diff(raster["x"].to_numpy()).mean())),
        float(abs(np.diff(raster["y"].to_numpy()).mean())),
    )


def _transform(raster: xr.DataArray) -> Affine:
    """Return a north-up grid's affine transform, built from its coordinates.

    Built here rather than asked of rioxarray, which derives it from the
    coordinates through a deprecated affine operator whenever no transform is
    stored on the array.
    """
    dx, dy = _resolution_deg(raster)
    x0 = float(raster["x"][0]) - dx / 2
    y0 = float(raster["y"][0]) + dy / 2
    return Affine(dx, 0.0, x0, 0.0, -dy, y0)


def cell_spacing_m(raster: xr.DataArray) -> tuple[np.ndarray, float]:
    """Return the east-west spacing per row and the north-south spacing, in m."""
    lat = np.deg2rad(raster["y"].to_numpy())
    dlon, dlat = _resolution_deg(raster)
    dx_m = EARTH_RADIUS_M * np.cos(lat) * np.deg2rad(dlon)
    dy_m = EARTH_RADIUS_M * np.deg2rad(dlat)
    return dx_m, float(dy_m)


def gen_gradient(dem: xr.DataArray) -> xr.DataArray:
    """Compute the slope gradient (rise over run) of a geographic DEM.

    Central differences, one-sided at the edges, with spacing converted from
    degrees to metres row by row -- the scheme GMT's ``grdgradient`` uses, which
    is what the paper computed its GMTED2010 slope with.

    Args:
        dem: Elevation in metres on a geographic grid, NaN as nodata.

    Returns:
        The gradient magnitude, dimensionless, on the DEM's grid.
    """
    _check_geographic(dem)
    dx_m, dy_m = cell_spacing_m(dem)
    z = dem.to_numpy().astype(float)
    dz_drow, dz_dcol = np.gradient(z)
    gradient = np.hypot(dz_dcol / dx_m[:, None], dz_drow / dy_m)
    return dem.copy(data=gradient).rename("gradient")


def gradient_to_degrees(gradient: xr.DataArray) -> xr.DataArray:
    """Convert a gradient to slope in degrees, as the model's slope term wants."""
    return np.degrees(np.arctan(gradient)).rename("slope_deg")


def gen_rock_coefficient(
    glim: "gpd.GeoDataFrame",
    template: xr.DataArray,
    *,
    class_column: str,
) -> xr.DataArray:
    """Rasterise GLiM onto the model grid as Table 3 lithology coefficients.

    Args:
        glim: GLiM polygons, in any CRS, carrying the two-letter top-level class
            code (``"ss"``, ``"mt"``, ...) in ``class_column``.
        template: The model grid, geographic.
        class_column: The column holding the top-level class code.

    Returns:
        The coefficient per cell of ``template``. A class without a Table 3
        coefficient -- the evaporite reference category, ice, water -- is 0, as
        in the USGS's own raster; a cell no polygon covers is NaN.
    """
    _check_geographic(template)
    glim = glim.to_crs(GEOGRAPHIC_CRS)
    codes = glim[class_column].str.strip().str.lower()
    values = codes.map(c.GLIM_COEFFICIENTS).fillna(0.0).to_numpy()
    shapes = zip(glim.geometry, values, strict=True)
    out = rasterize(
        shapes,
        out_shape=template.shape,
        transform=_transform(template),
        fill=np.nan,
        dtype="float64",
    )
    return template.copy(data=out).rename("rock_coefficient")


def gen_landcover_coefficient(globcover: xr.DataArray) -> xr.DataArray:
    """Look up GlobCover 2009 classes as Table 3 land cover coefficients.

    Args:
        globcover: The GlobCover class grid, geographic, with its native class
            values (11, 14, 20, ..., 230).

    Returns:
        The coefficient per cell, on GlobCover's own grid. A class without a
        Table 3 coefficient -- the class 11 reference, saline flooded forest,
        water -- is 0, as in the USGS's own raster; nodata stays NaN.
    """
    _check_geographic(globcover)
    classes = globcover.to_numpy()
    out = np.zeros(classes.shape)
    for value, coefficient in c.GLOBCOVER_COEFFICIENTS.items():
        out[classes == value] = coefficient
    out[np.isnan(classes)] = np.nan
    return globcover.copy(data=out).rename("landcover_coefficient")


def gen_cti(dem_30s: xr.DataArray) -> xr.DataArray:
    """Compute the compound topographic index from a ~1 km geographic DEM.

    ``CTI = ln(A / tan b)``, with ``A`` the upstream contributing area in km^2
    (each cell's own area included) from D8 routing on the depression-filled
    DEM, and ``b`` the slope from :func:`gen_gradient` on the same filled DEM,
    floored at :data:`CTI_MIN_TAN_SLOPE`. Area in km^2 matches HYDRO1k, whose
    CTI counted 1 km^2 cells; the index is dimensionally loose, and the model's
    0.03 coefficient is only meaningful in those units.

    The DEM must extend over every catchment that drains into the area of
    interest, or upstream area near the edge is truncated. Cells beside nodata,
    such as the sea, are outlets.

    Args:
        dem_30s: 30 arc-second elevation in metres, geographic, NaN as nodata.

    Returns:
        The index on the DEM's grid, NaN where the DEM is.
    """
    _check_geographic(dem_30s)
    dx_m, dy_m = cell_spacing_m(dem_30s)
    filled, order, parent = priority_flood(dem_30s.to_numpy())
    receiver = d8_receivers(filled, parent, dx_m, dy_m)
    cell_area_km2 = np.broadcast_to((dx_m * dy_m / 1.0e6)[:, None], filled.shape)
    cell_area_km2 = np.where(np.isnan(filled), np.nan, cell_area_km2)
    upstream_km2 = flow_accumulation(receiver, order, cell_area_km2)
    # The slope of a coastal cell is taken against the sea at sea level rather
    # than lost to its nodata neighbour, or every cell beside the sea would
    # have no CTI.
    at_sea_level = np.where(np.isnan(filled), SEA_MAX_ELEVATION_M, filled)
    tan_slope = gen_gradient(dem_30s.copy(data=at_sea_level)).to_numpy()
    tan_slope = np.maximum(tan_slope, CTI_MIN_TAN_SLOPE)
    cti = np.log(upstream_km2 / tan_slope)
    return dem_30s.copy(data=cti).rename("cti")


def resample_to(
    raster: xr.DataArray, template: xr.DataArray, *, resampling: Resampling
) -> xr.DataArray:
    """Bring a layer onto the model grid.

    Args:
        raster: The layer, geographic.
        template: The model grid, geographic.
        resampling: Bilinear for continuous layers, nearest for classes and
            class coefficients.

    Returns:
        The layer on ``template``'s grid, NaN where it has no data.
    """
    _check_geographic(raster)
    raster = raster.astype(float).rio.write_nodata(np.nan, encoded=False)
    out = raster.rio.reproject_match(template, resampling=resampling)
    return out.where(np.isfinite(out))


# The model grid's cell size: 7.5 arc-seconds, GMTED2010's, with cell edges on
# whole multiples of it from 0 degrees -- the registration of the USGS's own
# global slope raster, which sits 0.5 arc-seconds off GMTED2010's native tiles.
MODEL_GRID_DEG = 7.5 / 3600


def gen_model_grid(bbox: tuple[float, float, float, float]) -> xr.DataArray:
    """Return the model grid over an extent, registered as the USGS's is.

    Args:
        bbox: The extent (minx, miny, maxx, maxy) in degrees. The grid covers
            every cell it touches.

    Returns:
        An all-NaN template, north-up, EPSG:4326, with 7.5 arc-second cells
        whose edges fall on whole multiples of the cell size.
    """
    minx, miny, maxx, maxy = bbox
    step = MODEL_GRID_DEG
    x_edges = np.arange(np.floor(minx / step), np.ceil(maxx / step)) * step
    y_edges = np.arange(np.ceil(maxy / step), np.floor(miny / step), -1) * step
    x = x_edges + step / 2
    y = y_edges - step / 2
    grid = xr.DataArray(
        np.full((y.size, x.size), np.nan), coords={"y": y, "x": x}, dims=("y", "x")
    )
    return grid.rio.write_crs(GEOGRAPHIC_CRS)


def gen_model_inputs(
    *,
    dem_7p5s: xr.DataArray,
    dem_30s: xr.DataArray,
    glim: "gpd.GeoDataFrame",
    globcover: xr.DataArray,
    glim_class_column: str,
    template: xr.DataArray,
) -> xr.Dataset:
    """Build every non-shaking input of the model on the model grid.

    Each layer is brought onto the model grid once, from its own source grid.
    The DEM is bilinear resampled onto the grid and slope computed there, which
    is the processing that reproduces the USGS's own slope layer: computing
    slope on GMTED2010's native tile grid and resampling the slope instead
    leaves it 0.17 degrees steeper and total landslide area 5% higher at Loma
    Prieta (``validations/nowicki_2018/``). Lithology is rasterised directly,
    land cover nearest-neighbour resampled directly, and CTI computed at 30
    arc-seconds and bilinear resampled. Resampling a class layer twice through
    an intermediate grid misassigns cells along every class boundary, which is
    why there is no intermediate grid.

    Args:
        dem_7p5s: GMTED2010 7.5 arc-second median elevation over the area to be
            modelled, with a margin of a cell or two beyond ``template``.
        dem_30s: GMTED2010 30 arc-second elevation over the area and every
            catchment draining into it, for CTI.
        glim: GLiM polygons covering the area.
        globcover: GlobCover 2009 classes covering the area.
        glim_class_column: GLiM's top-level class code column.
        template: The model grid, from :func:`gen_model_grid` -- or, as the
            check against the USGS does, the USGS's own grid.

    Returns:
        ``slope_deg``, ``rock_coefficient``, ``landcover_coefficient`` and
        ``cti`` on the model grid. Sea cells, taken from
        :data:`SEA_MAX_ELEVATION_M` on the 30 arc-second DEM, are NaN in
        ``cti`` and so drop out of the model.
    """
    dem = resample_to(dem_7p5s, template, resampling=Resampling.bilinear)
    slope_deg = gradient_to_degrees(gen_gradient(dem))
    rock = gen_rock_coefficient(glim, template, class_column=glim_class_column)
    landcover = resample_to(
        gen_landcover_coefficient(globcover), template, resampling=Resampling.nearest
    )
    land_30s = dem_30s.where(dem_30s > SEA_MAX_ELEVATION_M)
    cti = resample_to(gen_cti(land_30s), template, resampling=Resampling.bilinear)
    return xr.Dataset(
        {
            "slope_deg": slope_deg,
            "rock_coefficient": rock,
            "landcover_coefficient": landcover,
            "cti": cti,
        }
    )
