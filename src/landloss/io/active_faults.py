r"""Reader for the New Zealand Active Faults Database, 1:250,000 scale (AF250).

The mapped traces of New Zealand's active faults, the fault map the Kritikos et
al. (2015) landslide model reads its distance-to-fault factor from (see
``.agents/plans/building-kritikos-2015-landslide-model.md``). Allstadt et al.
(2018) could not run that model globally only for want of a global fault map;
this database removes that obstacle for New Zealand.

Held on the cross-project data library, version 1, downloaded 2026-09-30 from
the GNS Science WFS layer ``gns:af250_download``, and read through
``tdrive_sync.get_cached`` as :mod:`landloss.io.vs30` is: a static published
dataset with utility beyond this study, so it lives in the library and not
under this project's own ``BASE_DIR``. The local copy lives at
``.tdrivecache/DataLibrary/210.20_active_faults_NZ_NZAFD_AF250/``.

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

import tdrive_sync
from landloss.domain import constants

AF250_DIR = Path(r"R:\DataLibrary\210.20_active_faults_NZ_NZAFD_AF250\v1\data")

# The delivery holds the same 9,978 traces as GeoJSON (EPSG:2193) and as a
# zipped shapefile; the GeoJSON is read.
AF250_FNAME = "NZAFD_AF250.geojson"


def active_faults_path(*, copy_to_local: bool = True) -> Path:
    """Resolve the AF250 GeoJSON against its local cache mirror.

    Args:
        copy_to_local: Whether to refresh the local cache from ``R:`` when it
            is missing or stale.

    Returns:
        The path to read: the local cache copy under
        ``.tdrivecache/DataLibrary/210.20_active_faults_NZ_NZAFD_AF250/``
        where one exists, otherwise the file on ``R:``.
    """
    return tdrive_sync.get_cached(AF250_DIR / AF250_FNAME, copy_to_local=copy_to_local)


def get_active_faults(
    *,
    bbox: tuple[float, float, float, float] | None = None,
    crs: str = constants.DEFAULT_CRS,
    copy_to_local: bool = True,
) -> gpd.GeoDataFrame:
    """Read the mapped active fault traces.

    Args:
        bbox: An optional (minx, miny, maxx, maxy) filter, in ``crs``. Traces
            that intersect the box are kept whole.
        crs: The CRS to return the traces in.
        copy_to_local: Passed to :func:`active_faults_path`.

    Returns:
        The fault traces as the database delivers them, reprojected to ``crs``.
    """
    faults = gpd.read_file(active_faults_path(copy_to_local=copy_to_local)).to_crs(crs)
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        faults = faults.cx[minx:maxx, miny:maxy]
    return faults
