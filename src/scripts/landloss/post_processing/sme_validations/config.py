"""Run settings for the SME validations in this folder.

Each script beside this reads these and holds no defaults of its own. The tests
and their verdicts are listed in ``sme_statements.md``.
"""

from scripts.landloss.paths import REPORT_DIR

# Where the figures are written.
FIG_DIR = REPORT_DIR / "post_processing" / "sme_validations" / "fig"

# The model run the tests read: its extent, exposure world and earthquake.
# "wlg-pilot" until the full build is run (T-68), then "full".
EXTENT = "wlg-pilot"
WORLD_ID = 0
REALISATION_ID = 0

# Test 3 reads the age table exposure step 8 writes over the full study area,
# because the statement names suburbs across the region.
AGE_TABLE_EXTENT = "full"

# Test 3: the suburbs the statement names, and what experience expects of each.
# A share is the expected share of properties built before 1970; None where the
# statement gives a period rather than a share.
AGE_SUBURBS = {
    "Kingston": ("Wellington City", 0.8, "about 80% from 1900 to the 1960s"),
    "Kelburn": ("Wellington City", 0.8, "about 80% from 1900 to the 1960s"),
    "Karori": ("Wellington City", 0.8, "about 80% from 1900 to the 1960s"),
    "Khandallah": ("Wellington City", 0.8, "about 80% from 1900 to the 1960s"),
    "Tītahi Bay": ("Porirua City", None, "a 1950s to 1970s subdivision"),
    "Whitby": ("Porirua City", None, "mostly under 30 years old"),
}

# Test 1: the share of hill properties experience expects to have a wall.
EXPECTED_HILL_WALLED = (1 / 3, 1 / 2)

# Test 2: the heights owners build to without consent, and the median retained
# height of the walls in the claim reports (claim_reports_status.md,
# 2026-10-06 analysis).
CONSENT_BAND_M = (1.0, 1.5)
CLAIMS_WALL_HEIGHT_MEDIAN_M = 1.2

# Test 4: how close a wall has to come to its claim's insured land to count as
# meeting it, allowing for the two layers' digitising.
TOUCH_TOLERANCE_M = 0.5

# Test 5: how far above or below the dwelling a failure has to sit to count as
# behind or in front of it, rather than level with it.
LEVEL_TOLERANCE_M = 0.5

# Test 6: the median evacuated area per claim in the claim reports, by cause
# (claim_reports_status.md, 2026-10-01 analysis).
CLAIMS_EVACUATED_MEDIAN_M2 = {"earthquake": 7.5, "rain": 3.0}
