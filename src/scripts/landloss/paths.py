"""Filesystem paths to assets and outputs shared across the landloss scripts."""

from pathlib import Path

# Repo root, from src/scripts/landloss/ -- three levels up. Resolved here once
# rather than as a parents[N] count in every script, because the scripts sit at
# several different depths under their module's submodules and a miscounted N
# silently writes an output somewhere nobody looks for it.
REPO_ROOT = Path(__file__).resolve().parents[3]

# Report outputs. Any directory named fig is gitignored, so figures are
# regenerated rather than committed and the script is the record of how each one
# was made. Both mirror the module path of the script that writes them.
REPORT_DIR = REPO_ROOT / "report"
RESEARCH_DIR = REPO_ROOT / "research"

# Working layers, rebuildable from the source data. temp/ is gitignored.
TEMP_DIR = REPO_ROOT / "temp"

ASSETS_DIR = Path(__file__).resolve().parent / "vul" / "assets"

NHI_ACT_LAND_CLAIMS_COHORT_CSV = ASSETS_DIR / "NHI_Act_Land claims cohort modelling.csv"
NHI_ACT_SETTLED_LAND_CLAIMS_CSV = (
    ASSETS_DIR / "NHI_Act_Settled_Land_Claims - 20260916.csv"
)

# Claim reports fetched off T: and what is extracted from them, one folder per
# T+T project number. The reports themselves are cached by tdrive_sync under
# the gitignored .tdrivecache/, never here: only the index of what was fetched
# and the figures read out of it are committed.
CLAIM_REPORTS_ASSETS_DIR = (
    REPO_ROOT / "src" / "landloss" / "common" / "assets" / "claim_reports"
)

IAG_1502000_REPORT_PATHS_CSV = ASSETS_DIR / "claims-report-paths-iag-1502000.csv"
IAG_1502000_LANDSLIDE_SUMMARY_CSV = (
    ASSETS_DIR / "claims-landslide-summary-iag-1502000.csv"
)
