"""Download GLiM, the global lithological map the Nowicki Jessee model uses.

Run:

    uv run --frozen python src/scripts/landloss/hazard/landslide/static_data_gen/get_glim.py

Writes the zipped file geodatabase (~1.1 GB) to ``GLIM_SOURCE_PATH`` below the
project's SourceMaterial folder on T:. Read back, still zipped, by
``landloss.io.global_datasets.get_glim``.

Source: Hartmann & Moosdorf (2012), the 2015 CCGM edition, through the Dropbox
link on the University of Hamburg's GLiM page
(https://www.geo.uni-hamburg.de/en/geologie/forschung/aquatische-geochemie/glim.html).
The licence of the vector is not stated there; see the reader's docstring.
"""

from landloss.domain import constants
from scripts.landloss.hazard.landslide.static_data_gen.downloads import (
    get_file_to_source_material,
)

# dl=1 makes Dropbox serve the file rather than its preview page.
URL = "https://www.dropbox.com/s/9vuowtebp9f1iud/LiMW_GIS%202015.gdb.zip?dl=1"


def main():
    """Download the geodatabase."""
    get_file_to_source_material(URL, constants.GLIM_SOURCE_PATH)


if __name__ == "__main__":
    main()
