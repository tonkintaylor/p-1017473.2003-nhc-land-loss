"""Readers for the global datasets the Nowicki Jessee (2018) model is built from.

GMTED2010 elevation, the GLiM lithological map, GlobCover 2009 land cover, and
the USGS ``groundfailure`` package's Loma Prieta test data. All four are public
and none is ours, so they sit under the project's ``SourceMaterial`` folder on
T: rather than in the versioned store. They get there by the ``get_`` scripts
in ``src/scripts/landloss/hazard/landslide/static_data_gen/``, which hold each
download URL; this module only reads, through ``tdrive_sync.get_source_mat``,
so the first read copies a file from T: into the local cache and every read
after that comes from disk.

The paths below ``SourceMaterial`` are the ``*_SOURCE_*`` constants in
:mod:`landloss.domain.constants`. Extents here are always
``(minx, miny, maxx, maxy)`` in degrees, EPSG:4326, because every one of these
datasets is geographic and the model is built on geographic grids.
"""

from pathlib import Path

import geopandas as gpd
import rioxarray
import xarray as xr

import tdrive_sync
from landloss.domain import constants


def _read_raster(
    path: Path | str, bbox: tuple[float, float, float, float] | None
) -> xr.DataArray:
    # Read through a context manager and load, as the other raster readers do:
    # a lazily-opened GDAL handle finalised at interpreter shutdown surfaces on
    # Windows as a bare "Error in sys.excepthook".
    with rioxarray.open_rasterio(path, masked=True) as opened:
        raster = opened.rio.clip_box(*bbox) if bbox is not None else opened
        raster = raster.squeeze(drop=True).load()
    if raster.rio.crs is None:
        raster = raster.rio.write_crs("EPSG:4326")
    return raster.astype(float)


def gmted2010_source_path(tile: str, product: str) -> str:
    """Return a GMTED2010 tile's path below SourceMaterial.

    Args:
        tile: The tile's south-west corner, e.g. ``"50S150E"`` -- see
            :data:`landloss.domain.constants.GMTED2010_TILES`.
        product: ``"med075"`` or ``"mea300"``.

    Returns:
        The path relative to SourceMaterial, as the USGS names the file.
    """
    return f"{constants.GMTED2010_SOURCE_DIR}/{tile}_20101117_gmted_{product}.tif"


def get_gmted2010(
    tile: str,
    product: str,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read GMTED2010 elevation for one tile.

    Source:
        Danielson, J.J. & Gesch, D.B. (2011). Global Multi-resolution Terrain
        Elevation Data 2010 (GMTED2010). USGS Open-File Report 2011-1073.
        Downloaded from the USGS EROS tile service.

    Licence:
        USGS data, public domain. Cite the report above.

    Args:
        tile: The tile's south-west corner, e.g. ``"50S150E"``.
        product: ``"med075"`` (7.5 arc-second median) or ``"mea300"`` (30
            arc-second mean).
        bbox: The extent to read, in degrees, or None for the whole tile.
        copy_to_local: Whether to mirror the tile into the local cache.

    Returns:
        Elevation in metres, EPSG:4326. The tiles carry no nodata: the sea is
        held at exactly 0 m, which is why the CTI build treats elevation at or
        below 0 m as sea.
    """
    path = tdrive_sync.get_source_mat(
        gmted2010_source_path(tile, product), copy_to_local=copy_to_local
    )
    return _read_raster(path, bbox)


def get_glim(
    *, bbox: tuple[float, float, float, float], copy_to_local: bool = True
) -> gpd.GeoDataFrame:
    """Read the GLiM lithology polygons over an extent.

    Source:
        Hartmann, J. & Moosdorf, N. (2012). The new global lithological map
        database GLiM: a representation of rock properties at the Earth
        surface. *G3* 13, Q12004. doi:10.1029/2012GC004370. This is the 2015
        CCGM edition, distributed through the University of Hamburg's GLiM
        page.

    Licence:
        Not stated on the distribution page. The 0.5 degree version on PANGAEA
        is CC BY 3.0; treat the vector as needing attribution to Hartmann &
        Moosdorf (2012) at least, and check before redistributing it.

    Args:
        bbox: The extent to read, in degrees.
        copy_to_local: Whether to mirror the geodatabase zip into the local
            cache.

    Returns:
        The polygons intersecting the extent, as delivered, in the
        geodatabase's own CRS. The two-letter top-level class code is in the
        ``xx`` column.
    """
    path = tdrive_sync.get_source_mat(
        constants.GLIM_SOURCE_PATH, copy_to_local=copy_to_local
    )
    source = f"zip://{Path(path).as_posix()}!{Path(path).stem}"
    crs = gpd.read_file(source, rows=1).crs
    minx, miny, maxx, maxy = (
        gpd.GeoSeries.from_xy([bbox[0], bbox[2]], [bbox[1], bbox[3]], crs="EPSG:4326")
        .to_crs(crs)
        .total_bounds
    )
    return gpd.read_file(source, bbox=(minx, miny, maxx, maxy))


def get_globcover2009(
    *, bbox: tuple[float, float, float, float], copy_to_local: bool = True
) -> xr.DataArray:
    """Read GlobCover 2009 land cover classes over an extent.

    Source:
        Arino, O., Ramos Perez, J.J., Kalogirou, V., Bontemps, S., Defourny, P.
        & Van Bogaert, E. (2012). Global Land Cover Map for 2009 (GlobCover
        2009). European Space Agency and Université catholique de Louvain.
        Downloaded from ESA's GlobCover distribution.

    Licence:
        Free to use; acknowledge ESA and UCLouvain as the source in anything
        derived from it. The terms travel with the delivery as
        ``GlobCover2009_ReadMe.pdf``, which the get_ script keeps beside the
        raster.

    Args:
        bbox: The extent to read, in degrees.
        copy_to_local: Whether to mirror the raster into the local cache.

    Returns:
        The class values (11, 14, 20, ..., 230) at 1/360 degree, EPSG:4326,
        with the delivery's 0 nodata as NaN.
    """
    path = tdrive_sync.get_source_mat(
        constants.GLOBCOVER2009_SOURCE_PATH, copy_to_local=copy_to_local
    )
    return _read_raster(path, bbox)


def usgs_groundfailure_loma_prieta_path(
    relative_path: str, *, copy_to_local: bool = True
) -> Path:
    """Resolve a file of the USGS groundfailure package's Loma Prieta test data.

    Source:
        Allstadt, K.E., Thompson, E.M., Hearne, M. & Biegel, K. (2018).
        groundfailure v1.0. USGS Software Release. doi:10.5066/P91G4NS4. Test
        data at tag :data:`landloss.domain.constants.USGS_GROUNDFAILURE_TAG`.

    Licence:
        Public domain, with a CC0 waiver worldwide.

    Args:
        relative_path: The file's path below the test data's ``loma_prieta``
            folder, e.g. ``"grid.xml"`` or ``"model_inputs/GLIM_replace.tif"``.
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The path to read.
    """
    return tdrive_sync.get_source_mat(
        f"{constants.USGS_GROUNDFAILURE_LOMA_PRIETA_DIR}/{relative_path}",
        copy_to_local=copy_to_local,
    )


def get_usgs_groundfailure_loma_prieta_raster(
    relative_path: str, *, copy_to_local: bool = True
) -> xr.DataArray:
    """Read a raster of the USGS Loma Prieta test data.

    Several of these files carry no CRS; all are geographic, so EPSG:4326 is
    written where none is declared. The ``targets/*.grd`` files are GMT netCDF
    grids that GDAL reads without georeferencing, so they are read with xarray
    instead and their ``x``/``y`` coordinates kept.

    Args:
        relative_path: The raster's path below the ``loma_prieta`` folder.
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The raster, EPSG:4326, nodata as NaN.
    """
    path = usgs_groundfailure_loma_prieta_path(
        relative_path, copy_to_local=copy_to_local
    )
    if relative_path.startswith("targets/"):
        with xr.open_dataset(path, engine="scipy") as ds:
            grid = ds["z"].load()
        return grid.rio.write_crs("EPSG:4326").astype(float)
    return _read_raster(path, None)
