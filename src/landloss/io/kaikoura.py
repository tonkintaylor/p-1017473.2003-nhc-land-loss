r"""Readers for GNS's Kaikōura earthquake landslide inventory, version 3.0.

31,623 landslide source area polygons and 26,559 debris trail polygons mapped
from the Mw 7.8, 14 November 2016 Kaikōura earthquake, both in NZTM
(EPSG:2193). This is the calibration dataset the
``estimating-eq-landslide-extent-wellington`` plan fits the model's size
distribution and reach-angle relationship against (see
``.agents/plans/estimating-eq-landslide-extent-wellington.md`` and the
Kaikōura-derived ``GAMMA``/``ALPHA`` in
:mod:`landloss.hazard.landslide.geometry`), because Wellington has no
earthquake-induced landslide inventory of its own to fit against.

This is not this project's own data, and it does not live under this project's
``BASE_DIR`` or ``SOURCE_MATERIAL_DIR``. Another T+T project (the "Computer
vision of landslides from aerials" micro-initiative, job YYYTTNZ.0730) fetched
it from GNS/DesignSafe and holds it under that project's own ``SourceMaterial``
folder on T:, so it is read the same way :mod:`landloss.io.nlm` reads the
National Liquefaction Model's release tree: an arbitrary absolute T: path
outside this project's own tree, resolved through ``tdrive_sync.get_cached``
rather than ``get_source_mat``.

Source:
    Jones, K., Massey, C., Townsend, D., Rosser, B., Morgenstern, R., Lukovic,
    B., Davidson, J., Lyndsell, B., Singeisen, C., Tamsen, D., Carey, J.,
    Villeneuve, M., Mason, D., Wolter, A., Gasston, C. (2024). Version 3.0 of
    the landslide inventory for the Mw 7.8 14 November 2016, Kaikōura
    Earthquake [Data set]. GNS Science. https://doi.org/10.21420/WX2X-H603

Licence:
    Creative Commons Attribution 4.0 International (CC BY 4.0). GNS Science's
    own metadata asks that anything using the data in a figure carry
    "© GNS Science 2024", and that anything citing it in a reference list use
    the citation above -- both have to travel with any figure or table this
    study derives from the data, not just live in this docstring.

The delivery also carries a ``CSV`` folder with a plain-text attribute table for
each shapefile, with no geometry. Checked against the shapefiles: the CSVs
carry the same rows and the same values under friendlier, un-truncated column
names -- a shapefile's DBF field names are capped at ten characters, which is
why the source area shapefile's ``Method`` is the CSV's "Ensemble Method", and
its ``Volume`` the CSV's "Source Area Volume m3". So the CSVs are not read
separately here; their headers are only used below to give the shapefiles' own
truncated columns readable names.
"""

from pathlib import Path

import geopandas as gpd

import tdrive_sync

# The root of the delivery, on another T+T project's own SourceMaterial folder
# rather than this project's. The \\?\ prefix is load-bearing, not decoration:
# the path is already past 200 characters before a file name is added, which is
# beyond Windows' 260 character MAX_PATH -- without the prefix, neither
# Path.exists() nor open() can see these files at all.
KAIKOURA_V3_SHAPEFILES_DIR = Path(
    r"\\?\T:\Auckland\Projects\YYYTTNZ\YYYTTNZ.0730\General"
    r"\6. CoTE Micro-Initiatives\009 Computer vision of landslides from aerials"
    r"\SourceMaterial\landslide-data\Kiak2026landslidesV3_via_GNS_PRJ-5827"
    r"\Mission-V3\data\Shapefiles"
)

# Renames the source area shapefile's DBF-truncated columns to the names its
# companion CSV attribute table gives them, snake_cased and, where the CSV
# names a unit, carrying it.
_SOURCE_AREA_COLUMNS = {
    "Source_ID": "source_id",
    "GeolCode": "geol_code",
    "Method": "ensemble_method",
    "Volume": "source_area_volume_m3",
    "Vol_p1SD": "volume_p1sd_m3",
    "Vol_m1SD": "volume_m1sd_m3",
    "Note": "note",
    "Reference": "reference",
    "Shape_Leng": "shape_length_m",
    "Shape_Area": "source_area_m2",
}

# Same idea for the debris trail shapefile, which carries far fewer columns.
_DEBRIS_TRAIL_COLUMNS = {
    "Debris_ID": "debris_id",
    "Shape_Leng": "shape_length_m",
    "Shape_Area": "debris_area_m2",
}


def kaikoura_shapefile_path(fname: str, *, copy_to_local: bool = False) -> Path:
    r"""Resolve one file of the Kaikōura V3 shapefile delivery.

    Args:
        fname: The file's name below :data:`KAIKOURA_V3_SHAPEFILES_DIR`, e.g.
            ``"GNS_2016KaikouraEQ_LandslideSourceArea_Version3.shp"``.
        copy_to_local: Whether to mirror the file into the local cache. Unlike
            :mod:`landloss.io.nlm`'s equivalent, this defaults to False: the
            source tree is nested deep enough that reconstructing it under the
            local cache overflows Windows' path length limit even with the
            ``\\?\`` prefix in place -- ``mkdir`` fails partway up the tree
            with WinError 206, "The filename or extension is too long",
            because there is no length budget left once the cache root is
            added in front of it. Pass True only if the cache root is shallow
            enough to leave that budget.

    Returns:
        The path to read: the local cache copy where one exists and
        ``copy_to_local`` is True, otherwise the file on T:.
    """
    return tdrive_sync.get_cached(
        KAIKOURA_V3_SHAPEFILES_DIR / fname, copy_to_local=copy_to_local
    )


def get_kaikoura_landslide_source_areas(
    *, copy_to_local: bool = False
) -> gpd.GeoDataFrame:
    """Read the Kaikōura V3 landslide source area polygons.

    One polygon per mapped landslide's source (evacuated) area. GNS's own
    volume estimate travels with each polygon as ``source_area_volume_m3``,
    with a +/-1 SD bound either side; this is GNS's estimate, not one this
    study derives.

    ``geol_code`` is supplied as a bare integer with no code table in the
    delivery's metadata. The plan's filter to Pahau terrane greywacke needs it,
    so confirm what each value maps to (the delivery's own
    ``Planning/data/*_Description.docx`` is the next place to check) before
    using it, rather than guessing from the number alone.

    Source:
        GNS Science's Kaikōura earthquake landslide inventory v3.0 -- see the
        module docstring for the full citation and its CC BY 4.0 licence.

    Args:
        copy_to_local: Whether to mirror the shapefile into the local cache.
            See :func:`kaikoura_shapefile_path` for why this defaults to
            False here.

    Returns:
        A GeoDataFrame of 31,623 polygons in EPSG:2193, carrying ``source_id``,
        ``geol_code``, ``ensemble_method``, ``source_area_volume_m3``,
        ``volume_p1sd_m3``, ``volume_m1sd_m3``, ``note``, ``reference``,
        ``shape_length_m`` and ``source_area_m2`` (matching ``geometry.area``
        to the column, since the source is already projected in metres). As
        delivered: nothing here filters, reprojects or fits anything.
    """
    path = kaikoura_shapefile_path(
        "GNS_2016KaikouraEQ_LandslideSourceArea_Version3.shp",
        copy_to_local=copy_to_local,
    )
    return gpd.read_file(path).rename(columns=_SOURCE_AREA_COLUMNS)


def get_kaikoura_landslide_debris_trails(
    *, copy_to_local: bool = False
) -> gpd.GeoDataFrame:
    """Read the Kaikōura V3 landslide debris trail polygons.

    One polygon per mapped landslide's debris trail (runout) footprint -- the
    population the plan's runout step samples a reach angle (H/L) from once
    each trail is paired with the volume of the source it ran out from.
    Debris trails carry no ``source_id`` of their own in this delivery, so
    that pairing is a spatial join a caller has to do, not something read off
    the attributes.

    Source:
        GNS Science's Kaikōura earthquake landslide inventory v3.0 -- see the
        module docstring for the full citation and its CC BY 4.0 licence.

    Args:
        copy_to_local: Whether to mirror the shapefile into the local cache.
            See :func:`kaikoura_shapefile_path` for why this defaults to
            False here.

    Returns:
        A GeoDataFrame of 26,559 polygons in EPSG:2193, carrying ``debris_id``,
        ``shape_length_m`` and ``debris_area_m2``. As delivered: nothing here
        filters, reprojects or fits anything.
    """
    path = kaikoura_shapefile_path(
        "GNS_2016KaikouraEQ_LandslideDebrisTrails_Version3.shp",
        copy_to_local=copy_to_local,
    )
    return gpd.read_file(path).rename(columns=_DEBRIS_TRAIL_COLUMNS)
