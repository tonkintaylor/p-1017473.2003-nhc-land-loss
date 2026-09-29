"""Download GlobCover 2009, the land cover the Nowicki Jessee model uses.

Run:

    uv run --frozen python src/scripts/landloss/hazard/landslide/static_data_gen/get_globcover2009.py

Downloads ESA's delivery zip (~381 MB) beside ``GLOBCOVER2009_SOURCE_PATH``
below the project's SourceMaterial folder on T:, then extracts the class raster
to that path, and the legend and read-me -- which carry the terms of use --
beside it. Read back by ``landloss.io.global_datasets.get_globcover2009``.

Source: ESA and UCLouvain, GlobCover 2009 v2.3 (Arino et al. 2012).
"""

from pathlib import PurePosixPath

from landloss.domain import constants
from scripts.landloss.hazard.landslide.static_data_gen.downloads import (
    extract_member_to_source_material,
    get_file_to_source_material,
)

URL = "http://due.esrin.esa.int/files/Globcover2009_V2.3_Global_.zip"

# The files kept from the zip, besides the class raster itself.
COMPANIONS = ("Globcover2009_Legend.xls", "GlobCover2009_ReadMe.pdf")


def main():
    """Download the zip and extract the raster and its companions."""
    raster = PurePosixPath(constants.GLOBCOVER2009_SOURCE_PATH)
    archive = get_file_to_source_material(
        URL, str(raster.parent / PurePosixPath(URL).name)
    )
    extract_member_to_source_material(
        archive, raster.name, constants.GLOBCOVER2009_SOURCE_PATH
    )
    for member in COMPANIONS:
        extract_member_to_source_material(archive, member, str(raster.parent / member))


if __name__ == "__main__":
    main()
