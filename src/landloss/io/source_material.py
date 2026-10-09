"""Readers for the rasters other organisations have supplied to this project.

Source material is data somebody else built and we were given: it lives
read-only under the project's ``SourceMaterial`` folder on T:, it is not
versioned by us, and it is not ours to publish. ``tdrive_sync.get_source_mat``
resolves a file there and mirrors it into a local cache, so a script reads from
T: once and from disk every time after that.

This module is the raster counterpart to :mod:`landloss.io.readers`, which reads
vector layers from Koordinates. The two are kept apart because the failure modes
are different. A Koordinates layer is fetched by ID against a live API and
carries a licence we have to honour in anything published; a source material
raster is a file on a network drive that may be in any projection, at any cell
size, with any nodata convention, supplied with whatever metadata came with the
email. So everything here is explicit about what it found rather than trusting
what it expected: the projection is read off the file, and a grid that is not in
the caller's coordinate reference system is reprojected rather than quietly
returned in its own.

Nothing in here downloads. If T: is unreachable and the file has not been cached
locally yet, the read fails -- which is the right outcome, because the
alternative is a model that silently runs on nothing.
"""

from pathlib import Path

import rioxarray
import xarray as xr
from pyproj import CRS
from rasterio.enums import Resampling
from rioxarray.exceptions import NoDataInBounds, OneDimensionalRaster

import tdrive_sync
from landloss.common.utils.raster import bbox_in_crs
from landloss.domain import constants

# The dimension order the terrain derivatives in
# :mod:`landloss.common.utils.terrain` insist on, and what every raster read
# here is squeezed down to.
RASTER_DIMS = ("y", "x")


def source_material_path(
    relative_path: str | Path, *, copy_to_local: bool = True
) -> Path:
    """Resolve a file under the project's SourceMaterial folder, caching it locally.

    A path is returned rather than the file's contents because not every source
    material file is a raster, and because a caller that wants to open one with
    something other than rioxarray should not have to go round this module.

    Args:
        relative_path: The file's path below ``SOURCE_MATERIAL_DIR``, as
            configured in ``tdrive_sync_config.py`` at the repository root.
            Forward slashes work on Windows and keep the constants readable.
        copy_to_local: Whether to mirror the file into the local cache, and
            refresh that copy when the one on T: has changed.

    Returns:
        The path to read: the local cache copy where there is one, otherwise the
        file on T:.
    """
    return tdrive_sync.get_source_mat(relative_path, copy_to_local=copy_to_local)


def get_source_material_raster(
    relative_path: str | Path,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    resampling: Resampling = Resampling.nearest,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read a raster supplied as source material, in the caller's own projection.

    Nodata is resolved to NaN on the way in, so a grid carrying -9999 outside its
    real coverage does not arrive as a very negative, very real-looking value.
    Every consumer in this study treats NaN as "nothing is known here", and a
    nodata marker left in place is the most common way a raster quietly poisons
    a model.

    Source:
        Supplied to Tonkin & Taylor for this project and held under the
        project's ``SourceMaterial`` folder on T:. Not open data: check with the
        supplier before reproducing it outside this study.

    Args:
        relative_path: The file's path below ``SOURCE_MATERIAL_DIR``.
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``, or None
            for the whole grid. The clip happens in the raster's own projection
            and before any reprojection, so a small extent stays cheap.
        crs: The coordinate reference system to return the raster in.
        resampling: How to resample if the raster has to be reprojected. The
            default is nearest neighbour, which is right for the probabilities
            and classes this study receives as source material; a continuous
            surface such as elevation wants bilinear instead.
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The raster, with dimensions :data:`RASTER_DIMS`, in ``crs``, and nodata
        as NaN.

    Raises:
        ValueError: If the file is not a single band raster, or carries no
            coordinate reference system, so nothing can be located against it;
            or if ``bbox`` does not overlap the grid at all, which is nearly
            always a study extent and a supplied grid that were never meant to
            meet.
    """
    path = source_material_path(relative_path, copy_to_local=copy_to_local)

    # masked=True is what turns the file's declared nodata into NaN. It also
    # forces the array to float, which is wanted here: an integer class grid
    # with a nodata hole has no integer left to put in the hole.
    # Read through a context manager and load into memory. A lazily-opened
    # GDAL handle is finalised during interpreter shutdown, which on Windows
    # surfaces as a bare "Error in sys.excepthook" after an otherwise clean
    # run -- and the array is small enough that holding it costs nothing.
    with rioxarray.open_rasterio(path, masked=True) as opened:
        raster = opened.squeeze(drop=True).load()

    if tuple(raster.dims) != RASTER_DIMS:
        msg = (
            f"{path.name} has dimensions {tuple(raster.dims)} after squeezing, "
            f"but only a single band raster oriented {RASTER_DIMS} can be read "
            "here. A multi-band file has to have its band chosen explicitly."
        )
        raise ValueError(msg)

    if raster.rio.crs is None:
        msg = (
            f"{path.name} carries no coordinate reference system, so nothing "
            "can be located against it. Ask the supplier which projection it "
            "is in, and set one with DataArray.rio.write_crs before using it."
        )
        raise ValueError(msg)

    if bbox is not None:
        try:
            # allow_one_dimensional_raster, because a window one cell wide is a
            # degenerate read rather than a mistaken one, and rioxarray's
            # refusal of it is a RuntimeError that no caller thinks to catch.
            # Anything downstream that cannot work with a single row says so
            # itself, in its own terms.
            raster = raster.rio.clip_box(
                *bbox_in_crs(bbox, crs, raster.rio.crs),
                allow_one_dimensional_raster=True,
            )
        except (NoDataInBounds, OneDimensionalRaster) as exc:
            bounds = tuple(float(value) for value in raster.rio.bounds())
            msg = (
                f"The requested extent does not overlap {path.name}, whose own "
                f"extent is {bounds} in {raster.rio.crs}. Check that the extent "
                "and the raster are meant to cover the same ground."
            )
            raise ValueError(msg) from exc

    if CRS(raster.rio.crs) != CRS(crs):
        raster = raster.rio.reproject(crs, resampling=resampling)

    return raster


def get_eil_landslide_probability(
    *,
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    copy_to_local: bool = True,
) -> xr.DataArray:
    """Read the supplied earthquake-induced landslide probability grid.

    One value per cell: the probability that the cell fails by slope failure at
    the shaking level the grid is conditioned on. It is the base rate the
    landslide realisation is sampled from -- see the landslide hazard module's
    ``status.md`` for how it sits against the alternatives, and
    :data:`landloss.domain.constants.EIL_PROBABILITY_SOURCE_PATH` for what is
    and is not known about the file itself.

    Two things about it have to travel with any result quoted from it. The
    probabilities are per cell and carry no statement about how failures cluster,
    so summing them over a neighbourhood gives an expected count and nothing
    more. And the shaking level is fixed by whichever file was supplied rather
    than chosen here, so a result is a result *at that level of shaking*, not a
    rate per year.

    Source:
        Supplied to this project as source material and held on T: under
        ``SourceMaterial``. Not open data.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``, or None
            for the whole grid.
        crs: The coordinate reference system to return the grid in.
        copy_to_local: Whether to mirror the file into the local cache.

    Returns:
        The probability grid, with dimensions :data:`RASTER_DIMS`, in ``crs``,
        and nodata as NaN. The values come back exactly as supplied and are
        deliberately not rescaled or clipped: a grid that turns out to be in
        percent, or to carry probabilities above one, is a conversation with the
        supplier rather than something to paper over here.
    """
    return get_source_material_raster(
        constants.EIL_PROBABILITY_SOURCE_PATH,
        bbox=bbox,
        crs=crs,
        copy_to_local=copy_to_local,
    )
