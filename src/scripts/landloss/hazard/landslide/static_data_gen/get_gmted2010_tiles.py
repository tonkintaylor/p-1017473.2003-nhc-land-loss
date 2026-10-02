"""Download the GMTED2010 elevation tiles the Nowicki Jessee model is built from.

Run:

    uv run --frozen python src/scripts/landloss/hazard/landslide/static_data_gen/get_gmted2010_tiles.py

Writes, below the project's SourceMaterial folder on T:, one tile per entry of
``GMTED2010_TILES`` (Wellington, and Loma Prieta for the check against the
USGS) in each of ``GMTED2010_PRODUCTS``: 7.5 arc-second median elevation,
which the model's slope comes from (~277 MB a tile), and 30 arc-second mean
elevation, which its CTI comes from (~17 MB a tile). Read back by
``landloss.io.global_datasets.get_gmted2010``.

Source: USGS EROS, public domain. Danielson & Gesch (2011), USGS Open-File
Report 2011-1073.
"""

from landloss.domain import constants
from landloss.io.global_datasets import gmted2010_source_path
from scripts.landloss.hazard.landslide.static_data_gen.downloads import (
    get_file_to_source_material,
)

BASE_URL = (
    "https://edcintl.cr.usgs.gov/downloads/sciweb1/shared/topo/downloads/GMTED/"
    "Global_tiles_GMTED"
)

# The EROS folder for each product: resolution, then statistic.
PRODUCT_FOLDERS = {"med075": "075darcsec/med", "mea300": "300darcsec/mea"}


def tile_url(tile: str, product: str) -> str:
    """Return the EROS URL of one tile, filed under its longitude band.

    Args:
        tile: The tile's south-west corner, e.g. ``"50S150E"``.
        product: ``"med075"`` or ``"mea300"``.

    Returns:
        The download URL. EROS files tile 50S150E under a folder named
        ``E150``, so the band is the longitude with its hemisphere moved to the
        front.
    """
    lon = tile[-4:]
    band = f"{lon[-1]}{lon[:-1]}"
    return (
        f"{BASE_URL}/{PRODUCT_FOLDERS[product]}/{band}/"
        f"{tile}_20101117_gmted_{product}.tif"
    )


def main():
    """Download every tile in every product."""
    for tile in constants.GMTED2010_TILES.values():
        for product in constants.GMTED2010_PRODUCTS:
            get_file_to_source_material(
                tile_url(tile, product), gmted2010_source_path(tile, product)
            )


if __name__ == "__main__":
    main()
