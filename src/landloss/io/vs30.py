r"""Readers for the Foster et al. (2019) Vs30 model of New Zealand, version 18.12.

The time-averaged shear-wave velocity over the top 30 m, Vs30, mapped across New
Zealand. Per the paper's abstract, it is a weighted combination of a
geology-based and a terrain-based model, each updated with local Vs30
measurements and interpolated around them with a multivariate normal (MVN)
approach -- the "AhdiYongWeightedMVN" in the file names. The shaking hazard
reads it to assign a TS1170.5 site class per cell
(``landloss.hazard.shaking.site_class``).

Two layers, both on one grid:

- ``..._Vs30.tif``: Vs30 in m/s.
- ``..._sigma.tif``: its uncertainty, as the standard deviation of ln(Vs30).

The grid is NZTM (EPSG:2193), 100 m cells on bounds that are multiples of
100 m (1,000,000 to 2,126,400 E, 4,700,000 to 6,338,400 N), 16,384 by 11,264
float32 cells. That is about 740 MB a layer in memory, so pass ``bbox``: the
window is cut before anything is read, and only it is loaded.

Held on the cross-project data library and read through
``tdrive_sync.get_cached``, as :mod:`landloss.io.ts1170` reads TS1170.5 Table
3.2. The local copy lives at
``.tdrivecache/DataLibrary/210.16_Vs30_NZ_Foster2019/v1_ref_Foster_v18.12/``.
Per the folder's README, the folder was supplied by Kevin Foster directly.

Source:
    Foster, K.M., Bradley, B.A., McGann, C.R. and Wotherspoon, L.M. (2019). A
    VS30 map for New Zealand based on geologic and terrain proxy variables and
    field measurements. Earthquake Spectra. https://doi.org/10.1193/121118EQS281M
    A copy of the paper sits beside the layers on the data library
    (``FosterEtAl_2019_EQS.pdf``).
"""

from pathlib import Path

import rioxarray
import xarray as xr

import tdrive_sync

FOSTER_2019_DIR = Path(r"R:\DataLibrary\210.16_Vs30_NZ_Foster2019\v1_ref_Foster_v18.12")

FOSTER_2019_VS30_FNAME = "VERSION18.12_AhdiYongWeightedMVN_nTcrp1.5_Vs30.tif"
FOSTER_2019_SIGMA_FNAME = "VERSION18.12_AhdiYongWeightedMVN_nTcrp1.5_sigma.tif"


def foster_2019_path(fname: str, *, copy_to_local: bool = True) -> Path:
    """Resolve one file of the Foster Vs30 model against its local cache mirror.

    Args:
        fname: The file's name below :data:`FOSTER_2019_DIR`.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The path to read: the local cache copy where one exists, otherwise the
        file on ``R:``.
    """
    return tdrive_sync.get_cached(FOSTER_2019_DIR / fname, copy_to_local=copy_to_local)


def _read_window(
    fname: str,
    bbox: tuple[float, float, float, float] | None,
    *,
    copy_to_local: bool,
) -> xr.DataArray:
    """Read one layer, cut to a window before it is loaded."""
    path = foster_2019_path(fname, copy_to_local=copy_to_local)
    # Loaded inside a context manager for the reason given in
    # landloss.io.nlm.get_nlm_scenario_raster: a lazily-opened GDAL handle
    # finalised at interpreter shutdown fails noisily on Windows.
    with rioxarray.open_rasterio(path, masked=True) as raster:
        if bbox is not None:
            raster = raster.rio.clip_box(*bbox, allow_one_dimensional_raster=True)
        return raster.squeeze("band", drop=True).load()


def get_foster_2019_vs30(
    bbox: tuple[float, float, float, float] | None = None,
    *,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read the Foster et al. (2019) Vs30 grid.

    Source:
        Foster et al. (2019) Vs30 model, version 18.12, on the T+T data
        library -- see the module docstring.

    Args:
        bbox: An optional (minx, miny, maxx, maxy) window in EPSG:2193. Omit it
            only if the whole of New Zealand (about 740 MB) is wanted.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        Vs30 in m/s on the model's 100 m NZTM grid, nodata as NaN.
    """
    return _read_window(FOSTER_2019_VS30_FNAME, bbox, copy_to_local=copy_to_local)


def get_foster_2019_vs30_sigma(
    bbox: tuple[float, float, float, float] | None = None,
    *,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read the Foster et al. (2019) Vs30 uncertainty grid.

    Source:
        Foster et al. (2019) Vs30 model, version 18.12, on the T+T data
        library -- see the module docstring.

    Args:
        bbox: An optional (minx, miny, maxx, maxy) window in EPSG:2193. Omit it
            only if the whole of New Zealand (about 740 MB) is wanted.
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The standard deviation of ln(Vs30), dimensionless, on the same grid as
        :func:`get_foster_2019_vs30`, nodata as NaN.
    """
    return _read_window(FOSTER_2019_SIGMA_FNAME, bbox, copy_to_local=copy_to_local)
