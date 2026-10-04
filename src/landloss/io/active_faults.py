r"""Reader for the New Zealand Active Faults Database, 1:250,000 scale (AF250).

The mapped traces of New Zealand's active faults, the fault map the Kritikos et
al. (2015) landslide model reads its distance-to-fault factor from (see
``.agents/plans/building-kritikos-2015-landslide-model.md``). Allstadt et al.
(2018) could not run that model globally only for want of a global fault map;
this database removes that obstacle for New Zealand.

Held on the cross-project data library, version 1, downloaded 2026-09-30 from
the GNS Science WFS layer ``gns:af250_download``, and read directly off ``R:``
in the same way as :mod:`landloss.io.gfdb`: a static published dataset with
utility beyond this study, so it lives in the library and not under this
project's own ``BASE_DIR``. The data folder is expected to hold one vector file;
:func:`get_active_faults` finds it rather than naming it, and raises if there is
not exactly one, so a change to the delivery fails loudly. ``R:`` is read by the
project lead's runs.

Source:
    GNS Science (2016). New Zealand Active Faults Database 1:250,000 scale.
    doi:10.21420/R1QN-BM52. [langridge_2016] Langridge, R.M., Ries, W.F.,
    Litchfield, N.J.,
    Villamor, P., Van Dissen, R.J., Barrell, D.J.A., Rattenbury, M.S.,
    Heron, D.W., Haubrock, S., Townsend, D.B., Lee, J.M., Berryman, K.R.,
    Nicol, A., Cox, S.C. and Stirling, M.W. (2016). The New Zealand Active
    Faults Database. *New Zealand Journal of Geology and Geophysics* 59(1),
    86-96. doi:10.1080/00288306.2015.1112818.

Licence:
    CC BY 3.0 NZ, as the GNS WFS service states it. Attribution is required:
    credit GNS Science and the database in any figure, table or layer derived
    from it and published. The licence is not re-read from layer metadata here,
    because the delivery is a WFS download rather than a Koordinates layer.
"""

from pathlib import Path

import geopandas as gpd

from landloss.domain import constants

AF250_DIR = Path(r"R:\DataLibrary\210.20_active_faults_NZ_NZAFD_AF250\v1\data")

# The vector formats a delivery can come in, in the order they are looked for.
VECTOR_SUFFIXES = (".gpkg", ".shp", ".geojson", ".json")


def _find_vector_file(directory: Path) -> Path:
    """Return the one vector file in a data folder.

    Raises:
        ValueError: If the folder holds none, or more than one.
    """
    files = sorted(
        path
        for suffix in VECTOR_SUFFIXES
        for path in directory.glob(f"*{suffix}")
        if path.is_file()
    )
    if len(files) != 1:
        msg = (
            f"Expected exactly one vector file in {directory}, found "
            f"{[path.name for path in files]}."
        )
        raise ValueError(msg)
    return files[0]


def get_active_faults(
    *,
    bbox: tuple[float, float, float, float] | None = None,
    crs: str = constants.DEFAULT_CRS,
) -> gpd.GeoDataFrame:
    """Read the mapped active fault traces.

    Args:
        bbox: An optional (minx, miny, maxx, maxy) filter, in ``crs``. Traces
            that intersect the box are kept whole.
        crs: The CRS to return the traces in.

    Returns:
        The fault traces as the database delivers them, reprojected to ``crs``.
    """
    faults = gpd.read_file(_find_vector_file(AF250_DIR)).to_crs(crs)
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        faults = faults.cx[minx:maxx, miny:maxy]
    return faults
