"""Run settings for the urban fragility area calibration.

Read by ``table_urban_area_calibration.py`` and ``fig_urban_area_calibration.py``.
The fitted numbers are not here: they are the model, and live in
``landloss.hazard.landslide.urban.fragility`` (the median pair) and
``landloss.domain.constants.LOCALISED_FRAGILITY_BETA`` (the dispersion).
"""

from scripts.landloss.hazard.shaking.steps.s3_pgv import config as pgv_config

# The extent whose landslide step 12 bare zones, step 4 ground map, step 3
# topographic position and shaking steps 2 and 3 grids are read. Name outputs
# with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# The exposure world whose step 8 model gives the walled polygons the wall
# curves are compared on (check iv). Step 8 must have written it.
WORLD_ID = 0

# The return period of the TS1170.5 grids the site PGV per g of rock PGA is
# read at: shaking step 3's PGV grid over the site class I PGA. Change it in
# shaking step 3's config.py; this follows.
RETURN_PERIOD_YR = pgv_config.RETURN_PERIOD_YR
