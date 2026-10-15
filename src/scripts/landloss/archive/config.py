"""Run settings for archiving a run to T:.

Everything that changes between one archive and the next, in one short file.
The scripts beside it take these as arguments and hold no defaults of their own.
The T: locations themselves come from ``tdrive_sync_config.py`` at the repo root
(``BASE_DIR``, ``DATA_VERSION`` and ``SOURCE_MATERIAL_DIR``), so the results land
where ``tdrive_sync.local_save`` would have put them with local mode off.
"""

from pathlib import Path

from scripts.landloss.paths import REPORT_DIR, TEMP_DIR

# Where each territorial authority's results are taken from: the ``temp`` folder
# of the run that built them. The 2026-10-14 run built Wellington City on this
# machine and the other three on the remote desktop, whose cache was copied here
# whole. That copy also holds Wellington City outputs that are out of date, so
# each authority is read from its own run's folder and nowhere else.
REMOTE_TEMP_DIR = Path(
    r"C:\Users\pegi\Projects\2026\NHC Land Loss Modelling\remote_cache_14102026\temp"
)
RESULT_SOURCES = {
    "wellington-city": TEMP_DIR,
    "lower-hutt": REMOTE_TEMP_DIR,
    "upper-hutt": REMOTE_TEMP_DIR,
    "porirua": REMOTE_TEMP_DIR,
}

# Report outputs archived alongside the results, as globs under report/: the
# loss viewer (each authority's CSV, the region's and the page) and the equity
# figures. A name holding any of REPORT_SKIP is left out (the pilot's CSV and
# the synthetic stress test).
REPORT_GLOBS = [
    "loss/viewer/loss-viewer-w000-r000-*.csv",
    "loss/viewer/loss_viewer.html",
    "loss/equity/fig/*.png",
]
REPORT_SKIP = ["pilot", "SYNTHETIC"]
REPORT_ROOT = REPORT_DIR

# The folder under SOURCE_MATERIAL_DIR the web-downloaded inputs are copied to.
WEB_INPUTS_SUBDIR = "web-downloaded-inputs"

# The territorial authorities whose DEMs are described in the inputs snapshot,
# with the folder holding each one's ``ground/dem-1m-<extent>.tif``.
DEM_SOURCES = RESULT_SOURCES
