"""Run settings for the retaining wall dataset comparison.

Read by ``gen_rw_dataset_properties.py`` and the ``table_`` and ``fig_``
scripts beside it, which take no arguments, so what a run did can be read off
this file and its git history.
"""

from scripts.landloss.paths import (
    CLAIM_REPORTS_EXTRACTED_DIR,  # noqa: F401 -- read as config.CLAIM_REPORTS_EXTRACTED_DIR
    REPORT_DIR,
    TEMP_DIR,
)

# The claim report extraction (the CSVs extract_claim_reports.py writes, one
# folder per claims list) is read from CLAIM_REPORTS_EXTRACTED_DIR, the one
# copy on Maxim Millen's U: drive that the extraction writes to, whoever runs
# this. Every claims list with an extraction is read; allianz-1509000 is left
# out, since its one claim has no report and so no extraction folder.
CLAIMS_LISTS = (
    "iag-1502000",
    "suncorp-1501000",
    "kaikoura-2016",
    "seddon-2013",
    "loss-adjusters-1502100",
    "tower-1503000",
    "fmg-1504000",
    "mas-1505000",
    "ando-1506000",
    "chubb-1507000",
    "qbe-1508000",
)

# Whether to reuse the already-clipped LINZ and GNS layers. Set False to fetch
# them again.
USE_CACHED_LAYERS = True

# How far outside a property a GNS mapped wall may lie and still count as that
# property's. Walls are commonly mapped on or just over a boundary, so a wall on
# a shared boundary counts for both neighbours. TOLERANCE_M is the one every
# table and figure uses; the rest are only for the sensitivity table.
TOLERANCE_M = 1.0
TOLERANCES_M = (0.0, 1.0, 2.0, 5.0)

# The shortest piece of mapped wall that marks a property, so a wall clipping
# a corner of the buffered property does not.
MIN_WALL_LENGTH_M = 1.0

# How far a claim's geocoded point may lie from a property, where it falls in a
# road, and still be placed on the nearest one.
CLAIM_SNAP_DISTANCE_M = 15.0

# The side of a hexagon in the density maps, and the fewest properties (or
# claims) a hexagon must hold to be drawn, so no hexagon can describe a single
# property of a sensitive dataset.
HEX_SIDE_M = 300.0
MIN_HEX_PROPERTIES = 10
MIN_HEX_CLAIMS = 5

# The per-property layer: derived from the NHC NZMM extract and the claim
# reports, so it is as sensitive as they are. temp/ is gitignored; destroy it
# with the NZMM extract at the end of the project.
WORK_DIR = TEMP_DIR / "exposure" / "rw" / "validations"
PROPERTIES_PATH = WORK_DIR / "rw-datasets-by-property.geoparquet"
GNS_WALLS_PATH = WORK_DIR / "rw-datasets-gns-walls.geoparquet"
GNS_COVERAGE_PATH = WORK_DIR / "rw-datasets-gns-coverage.geoparquet"

# Figures are gitignored (any fig/ directory); tables are aggregates only.
OUT_DIR = REPORT_DIR / "exposure" / "rw" / "rw-datasets"
FIG_DIR = OUT_DIR / "fig"
TAB_DIR = OUT_DIR / "tab"
