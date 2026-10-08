"""Run settings for the end-to-end QGIS build.

`gen_qgis_e2e_build.py` beside this reads one extent's outputs from every
module (hazard, exposure, vul and loss) and writes one QGIS project over them.
Match these to the run being looked at: `scripts.landloss.config` for hazard,
exposure and vul, and `scripts.landloss.loss.config` for loss.
"""

# The extent to show: a name in landloss.io.area_of_interest.EXTENTS, or "full".
# The project opens on this extent's box.
EXTENT = "porirua-pilot"

# The exposure world and earthquake realisation the project shows.
WORLD_ID = 0
REALISATION_ID = 0

# Contours drawn from the 3 m DEM: every CONTOUR_STEP_M, brighter every
# CONTOUR_INDEX_M.
CONTOUR_STEP_M = 5.0
CONTOUR_INDEX_M = 25.0
