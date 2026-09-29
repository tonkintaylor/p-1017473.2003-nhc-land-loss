"""Download the USGS groundfailure Loma Prieta test data the model is checked on.

Run:

    uv run --frozen python src/scripts/landloss/hazard/landslide/static_data_gen/get_usgs_groundfailure_loma_prieta.py

Fetches, from the USGS ``groundfailure`` repository at tag
``USGS_GROUNDFAILURE_TAG``, the files of its 1989 Loma Prieta test case that
the Nowicki Jessee model needs: the ShakeMap and its uncertainty, the USGS's
own prepared input rasters, and the expected outputs. Written below
``USGS_GROUNDFAILURE_LOMA_PRIETA_DIR`` in the project's SourceMaterial folder
on T: (a few MB in all), keeping the repository's own layout. Read back by
``landloss.io.global_datasets`` and used by
``src/scripts/landloss/hazard/landslide/validations/nowicki_2018/``.

Source: Allstadt, Thompson, Hearne & Biegel (2018), groundfailure, USGS
Software Release, doi:10.5066/P91G4NS4. Public domain, CC0.
"""

from landloss.domain import constants
from scripts.landloss.hazard.landslide.static_data_gen.downloads import (
    get_file_to_source_material,
)

RAW_URL = (
    "https://code.usgs.gov/ghsc/esi/groundfailure/groundfailure/-/raw/"
    f"{constants.USGS_GROUNDFAILURE_TAG}/tests/data/loma_prieta"
)

FILES = (
    "grid.xml",
    "uncertainty.xml",
    "model_inputs/global_grad.tif",
    "model_inputs/GLIM_replace.tif",
    "model_inputs/globcover_replace.tif",
    "model_inputs/global_cti_fil.grd",
    "model_inputs/jessee_standard_deviation.tif",
    "targets/jessee_2018.grd",
    "targets/jessee_2018_std.grd",
)


def main():
    """Download each file."""
    for name in FILES:
        get_file_to_source_material(
            f"{RAW_URL}/{name}",
            f"{constants.USGS_GROUNDFAILURE_LOMA_PRIETA_DIR}/{name}",
        )


if __name__ == "__main__":
    main()
