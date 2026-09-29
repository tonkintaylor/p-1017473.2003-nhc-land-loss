r"""Readers for the National Liquefaction Model's own versioned release tree.

The NLM publishes its releases to
``T:\\Auckland\\Projects\\1017473\\WorkingMaterial\\new_versioned_releases`` --
one level above this project's own ``1017473.2003`` folder, because it is
shared across every subproject that reads from it rather than owned or
versioned by this study. This is therefore a different tree from
``tdrive_sync_config.py``'s ``BASE_DIR``, which holds the data this project
derives and writes out itself.

Which release is read is ``CORE_NLM_VERSION`` in ``landloss.domain.constants``,
the single pin every part of this study reads the NLM's ``core`` release tree
at -- the scenario grids here, and the hazard, exposure and vul steps alike.
The flatland product under ``flatland`` is cut on its own schedule and carries
its own version number, pinned separately as ``FLATLAND_NLM_VERSION``.

Reads are read-only and cached locally through ``tdrive_sync.get_cached``, the
same "fetch once from T:, then read the local copy" behaviour
``landloss.io.source_material`` gets from ``tdrive_sync.get_source_mat``.
There is no save side, and local-only working mode does not apply: a release
someone else publishes has no local, disposable stand-in.
"""

from pathlib import Path

import geopandas as gpd
import rioxarray
import xarray as xr

import tdrive_sync
from landloss.domain.constants import CORE_NLM_VERSION, FLATLAND_NLM_VERSION

# The root of the NLM's own release tree, shared across every subproject under
# 1017473. Not to be confused with this project's own versioned data store
# (tdrive_sync_config.py's BASE_DIR).
NLM_RELEASES_DIR = Path(
    r"T:\Auckland\Projects\1017473\WorkingMaterial\new_versioned_releases"
)


def nlm_release_path(relative_path: str | Path, *, copy_to_local: bool = True) -> Path:
    """Resolve a file under the NLM's release tree, caching it locally.

    Args:
        relative_path: The file's path below ``NLM_RELEASES_DIR``, e.g.
            ``"core/v2026p0rc6/scenario/return_period/rp2500y_....tif"``.
        copy_to_local: Whether to mirror the file into the local cache, and
            refresh that copy when the one on T: has changed.

    Returns:
        The path to read: the local cache copy where there is one, otherwise
        the file on T:.
    """
    return tdrive_sync.get_cached(
        NLM_RELEASES_DIR / relative_path, copy_to_local=copy_to_local
    )


def get_nlm_scenario_raster(
    relative_path: str | Path, *, copy_to_local: bool = True
) -> xr.DataArray:
    """Read a single-band raster from the NLM's scenario release tree.

    Unlike ``landloss.io.source_material``'s readers, this does not clip or
    reproject: the NLM's scenario grids are read as delivered. Add that
    handling here if and when a caller needs it against a study extent.

    Args:
        relative_path: The file's path below ``NLM_RELEASES_DIR``.
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The raster, in its own native projection, cell size and nodata as
        NaN.
    """
    path = nlm_release_path(relative_path, copy_to_local=copy_to_local)
    # Read through a context manager and load into memory. A lazily-opened
    # GDAL handle is finalised during interpreter shutdown, which on Windows
    # surfaces as a bare "Error in sys.excepthook" after an otherwise clean
    # run -- and the array is small enough that holding it costs nothing.
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze(drop=True).load()


def get_nlm_scenario_rp2500y_gwd_med_p_ld_moderate_fu() -> xr.DataArray:
    """Read the NLM's RP2500y, median groundwater, moderate land damage grid.

    Source:
        National Liquefaction Model core release ``CORE_NLM_VERSION``, under
        ``scenario/return_period`` in the NLM's release tree on T:.

    Returns:
        The probability grid, as delivered.
    """
    return get_nlm_scenario_raster(
        f"core/{CORE_NLM_VERSION}/scenario/return_period/"
        "rp2500y_lsn_pl50_gwd-med_p_ld_moderate_fu.tif"
    )


def get_nlm_scenario_rp2500y_gwd_med_p_ld_major_fu() -> xr.DataArray:
    """Read the NLM's RP2500y, median groundwater, major land damage grid.

    Source:
        National Liquefaction Model core release ``CORE_NLM_VERSION``, under
        ``scenario/return_period`` in the NLM's release tree on T:.

    Returns:
        The probability grid, as delivered.
    """
    return get_nlm_scenario_raster(
        f"core/{CORE_NLM_VERSION}/scenario/return_period/"
        "rp2500y_lsn_pl50_gwd-med_p_ld_major_fu.tif"
    )


# The TS1170.5 site classes the NLM publishes its 2500-year seismic-standard
# grids at.
SITE_CLASSES = (1, 2, 3, 4, 5, 6, 7)

# The file names of those grids below ``scenario/return_period/seismic_standard``
# in the NLM's release tree, one per site class. The PGA name is the one the
# shaking step has read since it was written. The Sa(1.0 s) name follows the same
# pattern and is not yet confirmed against the release folder: if a read fails
# with a missing file, correct it here.
SEISMIC_STANDARD_FILENAMES = {
    "pga": "pga_2500yr_site_class_{site_class}.tif",
    "sa_t1": "sa_t1_2500yr_site_class_{site_class}.tif",
}


def nlm_seismic_standard_path(measure: str, site_class: int) -> str:
    """Return a 2500-year seismic-standard grid's path below the release tree.

    Args:
        measure: ``"pga"`` or ``"sa_t1"``, a key of
            :data:`SEISMIC_STANDARD_FILENAMES`.
        site_class: The TS1170.5 site class, one of :data:`SITE_CLASSES`.

    Returns:
        The path relative to ``NLM_RELEASES_DIR`` at ``CORE_NLM_VERSION``.

    Raises:
        ValueError: If the measure or site class is not one the NLM publishes.
    """
    if measure not in SEISMIC_STANDARD_FILENAMES:
        msg = f"No seismic-standard grid for {measure!r}; expected one of "
        msg += f"{sorted(SEISMIC_STANDARD_FILENAMES)}."
        raise ValueError(msg)
    if site_class not in SITE_CLASSES:
        msg = f"Site class {site_class!r} is not one of {SITE_CLASSES}."
        raise ValueError(msg)
    name = SEISMIC_STANDARD_FILENAMES[measure].format(site_class=site_class)
    return f"core/{CORE_NLM_VERSION}/scenario/return_period/seismic_standard/{name}"


def get_nlm_scenario_pga_2500yr(site_class: int) -> xr.DataArray:
    """Read the NLM's RP2500y peak ground acceleration grid at one site class.

    Source:
        National Liquefaction Model core release ``CORE_NLM_VERSION``, under
        ``scenario/return_period/seismic_standard`` in the NLM's release tree
        on T:. The TS1170.5 demand, built in the NLM repository
        (``p-1017473-nlm-loss-modelling``).

    Args:
        site_class: The TS1170.5 site class, 1 to 7.

    Returns:
        The PGA grid in g, as delivered.
    """
    return get_nlm_scenario_raster(nlm_seismic_standard_path("pga", site_class))


def get_nlm_scenario_sa_t1_2500yr(site_class: int) -> xr.DataArray:
    """Read the NLM's RP2500y Sa(1.0 s) grid at one site class.

    The spectral acceleration at a 1 second period, which the shaking module
    converts to PGV (``landloss.hazard.shaking.pgv``).

    Source:
        National Liquefaction Model core release ``CORE_NLM_VERSION``, under
        ``scenario/return_period/seismic_standard`` in the NLM's release tree
        on T:. The TS1170.5 demand, built in the NLM repository
        (``p-1017473-nlm-loss-modelling``).

    Args:
        site_class: The TS1170.5 site class, 1 to 7.

    Returns:
        The Sa(1.0 s) grid in g, as delivered.
    """
    return get_nlm_scenario_raster(nlm_seismic_standard_path("sa_t1", site_class))


def get_nlm_scenario_pga_2500yr_site_class_5() -> xr.DataArray:
    """Read the NLM's RP2500y, site class 5 peak ground acceleration grid.

    Kept for the shaking step, which reads site class 5; equivalent to
    ``get_nlm_scenario_pga_2500yr(5)``.

    Source:
        National Liquefaction Model core release ``CORE_NLM_VERSION``, under
        ``scenario/return_period/seismic_standard`` in the NLM's release tree
        on T:.

    Returns:
        The PGA grid, as delivered.
    """
    return get_nlm_scenario_pga_2500yr(5)


def get_nlm_flatland(*, copy_to_local: bool = True) -> gpd.GeoDataFrame:
    """Read the NLM's flatland polygons from its own release tree.

    This is the flatland product's own delivery under ``flatland`` in the NLM's
    release tree, smoothed to a 200 m spatial length -- distinct from
    ``landloss.exposure.land.landform.get_flatland``, which reads the mirror of
    an (earlier) flatland cut published to Koordinates as
    ``landloss.domain.constants.NLM_FLATLAND_LAYER_ID``.

    Source:
        National Liquefaction Model flatland release
        :data:`landloss.domain.constants.FLATLAND_NLM_VERSION`, under
        ``flatland`` in the NLM's release tree on T:.

    Args:
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The flat land polygons, as delivered, in their native CRS.
    """
    path = nlm_release_path(
        f"flatland/{FLATLAND_NLM_VERSION}/_v0p5_slen200m_smoothed.gpkg",
        copy_to_local=copy_to_local,
    )
    return gpd.read_file(path)
