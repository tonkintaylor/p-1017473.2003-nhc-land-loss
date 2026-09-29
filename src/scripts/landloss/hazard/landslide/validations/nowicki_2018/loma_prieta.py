"""The 1989 Loma Prieta case both Nowicki Jessee checks are run on.

The USGS ``groundfailure`` package tests its implementation of the model on
Loma Prieta, and ships that test's inputs and expected output. This module
loads them, and builds our own rebuilt inputs over the same ground, so the two
check scripts beside it compare like with like:

- ``fig_nowicki_2018_loma_prieta_model.py`` runs our equations on the USGS's
  inputs, which tests the implementation alone.
- ``fig_nowicki_2018_loma_prieta_layers.py`` compares our rebuilt layers with
  the USGS's, and runs the model on ours, which tests the layer build.

Everything is evaluated on the USGS target's own grid: GMTED2010's 7.5
arc-second cells inside the ShakeMap's extent, which is the grid the USGS
package resamples every layer onto.

Requires the static data on T: -- run the ``get_`` scripts in
``src/scripts/landloss/hazard/landslide/static_data_gen/`` first.
"""

import numpy as np
import xarray as xr
from rasterio.enums import Resampling

from landloss.domain import constants
from landloss.hazard.landslide.models.nowicki_2018 import inputs, model
from landloss.io.global_datasets import (
    get_glim,
    get_globcover2009,
    get_gmted2010,
    get_usgs_groundfailure_loma_prieta_raster,
    usgs_groundfailure_loma_prieta_path,
)
from landloss.io.shakemap import get_shakemap_grid

TILE = constants.GMTED2010_TILES["loma_prieta"]

# How far beyond the model extent the 30 arc-second DEM is read for CTI, so that
# every catchment draining into the extent is routed in full.
CTI_BUFFER_DEG = 1.5

# The GLiM column holding the two-letter top-level class code.
GLIM_CLASS_COLUMN = "xx"

LAYERS = ("slope_deg", "rock_coefficient", "landcover_coefficient", "cti")


def _north_up(raster: xr.DataArray) -> xr.DataArray:
    return raster.sortby("y", ascending=False)


def get_target() -> xr.DataArray:
    """Read the USGS's expected coverage, north-up, on its own grid."""
    return _north_up(
        get_usgs_groundfailure_loma_prieta_raster("targets/jessee_2018.grd")
    )


def get_target_std() -> xr.DataArray:
    """Read the USGS's expected coverage standard deviation."""
    return _north_up(
        get_usgs_groundfailure_loma_prieta_raster("targets/jessee_2018_std.grd")
    )


def interior(grid: xr.DataArray) -> np.ndarray:
    """Mask off the outer row and column of a grid.

    The target grid's outermost cells lie half a cell beyond the ShakeMap's
    last nodes. The USGS leaves them empty; GDAL's bilinear resampling fills
    them. That is a difference in extrapolation, not in the model, so the
    comparisons leave them out.
    """
    mask = np.ones(grid.shape, dtype=bool)
    mask[0, :] = mask[-1, :] = mask[:, 0] = mask[:, -1] = False
    return mask


def get_shaking(template: xr.DataArray) -> xr.Dataset:
    """Bring the Loma Prieta ShakeMap and its uncertainty onto the grid."""
    shake = get_shakemap_grid(usgs_groundfailure_loma_prieta_path("grid.xml"))
    unc = get_shakemap_grid(usgs_groundfailure_loma_prieta_path("uncertainty.xml"))
    return xr.Dataset(
        {
            "pgv": inputs.resample_to(
                shake["pgv"], template, resampling=Resampling.bilinear
            ),
            "pga": inputs.resample_to(
                shake["pga"], template, resampling=Resampling.bilinear
            ),
            "stdpgv": inputs.resample_to(
                unc["stdpgv"], template, resampling=Resampling.bilinear
            ),
        }
    )


def get_usgs_inputs(template: xr.DataArray) -> xr.Dataset:
    """Read the USGS's prepared inputs onto the grid, as the USGS resamples them.

    Slope arrives as a gradient and is converted to degrees; lithology and land
    cover as coefficient rasters, nearest-neighbour; CTI bilinear.
    """

    def read(name, resampling):
        raster = get_usgs_groundfailure_loma_prieta_raster(f"model_inputs/{name}")
        return inputs.resample_to(raster, template, resampling=resampling)

    return xr.Dataset(
        {
            "slope_deg": inputs.gradient_to_degrees(
                read("global_grad.tif", Resampling.nearest)
            ),
            "rock_coefficient": read("GLIM_replace.tif", Resampling.nearest),
            "landcover_coefficient": read("globcover_replace.tif", Resampling.nearest),
            "cti": read("global_cti_fil.grd", Resampling.bilinear),
            "logit_std": read("jessee_standard_deviation.tif", Resampling.bilinear),
        }
    )


def gen_rebuilt_inputs(template: xr.DataArray) -> xr.Dataset:
    """Rebuild every input from the raw public sources, onto the grid.

    Built by :func:`landloss.hazard.landslide.models.nowicki_2018.gen_model_inputs`
    straight onto the target grid, each layer from its own source grid. Slope
    is computed on GMTED2010's native 7.5 arc-second cells -- which sit 0.5
    arc-seconds off the USGS's -- and bilinear resampled.
    """
    minx, miny, maxx, maxy = template.rio.bounds()
    pad = 0.02
    extent = (minx - pad, miny - pad, maxx + pad, maxy + pad)
    buffered = (
        minx - CTI_BUFFER_DEG,
        miny - CTI_BUFFER_DEG,
        maxx + CTI_BUFFER_DEG,
        maxy + CTI_BUFFER_DEG,
    )
    return inputs.gen_model_inputs(
        dem_7p5s=get_gmted2010(TILE, "med075", bbox=extent),
        dem_30s=get_gmted2010(TILE, "mea300", bbox=buffered),
        glim=get_glim(bbox=extent),
        globcover=get_globcover2009(bbox=extent),
        glim_class_column=GLIM_CLASS_COLUMN,
        template=template,
    )


def run_operational(layers: xr.Dataset, shaking: xr.Dataset) -> model.NowickiResult:
    """Run the operational variant, as the USGS target was made."""
    logit_std = layers["logit_std"].to_numpy() if "logit_std" in layers else None
    return model.run(
        pgv_cm_s=shaking["pgv"].to_numpy(),
        pga_pct_g=shaking["pga"].to_numpy(),
        ln_pgv_std=shaking["stdpgv"].to_numpy(),
        logit_std=logit_std,
        slope_deg=layers["slope_deg"].to_numpy(),
        rock_coefficient=layers["rock_coefficient"].to_numpy(),
        landcover_coefficient=layers["landcover_coefficient"].to_numpy(),
        cti=layers["cti"].to_numpy(),
        operational=True,
    )


def cell_area_km2(grid: xr.DataArray) -> np.ndarray:
    """Return each cell's area in km^2 on a geographic grid."""
    dx_m, dy_m = inputs.cell_spacing_m(grid)
    return np.broadcast_to((dx_m * dy_m / 1.0e6)[:, None], grid.shape)


def landslide_area_km2(coverage: np.ndarray, grid: xr.DataArray, mask) -> float:
    """Total expected landslide area: coverage times cell area, over ``mask``."""
    area = cell_area_km2(grid)
    return float(np.nansum(np.where(mask, coverage * area, 0.0)))
