"""Run settings for the end-to-end QGIS build.

`gen_qgis_e2e_build.py` beside this reads one extent's outputs from every
module (hazard, exposure, vul and loss) and writes one QGIS project over them.
Match these to the run being looked at: `scripts.landloss.config` for hazard,
exposure and vul, and `scripts.landloss.loss.config` for loss.
"""

# The extent to show: a name in landloss.io.area_of_interest.EXTENTS, or "full".
# The project opens on this extent's box.
EXTENT = "wlg-pilot"

# The exposure world and earthquake realisation the project shows.
WORLD_ID = 0
REALISATION_ID = 0

# A copy of a run's outputs to build over, such as
# "U:/<user>/land-loss/results/porirua", or None for the files each step wrote.
# Each layer is the file of the same name anywhere under this folder, and the
# project is written into it, with its derived layers in qgis/ beside it.
RESULTS_DIR = None

# Contours drawn from the 3 m DEM: every CONTOUR_STEP_M, brighter every
# CONTOUR_INDEX_M.
CONTOUR_STEP_M = 5.0
CONTOUR_INDEX_M = 25.0
