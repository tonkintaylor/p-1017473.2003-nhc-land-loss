"""Run settings for the landslide QGIS project."""

# The build extent the project reads (see landloss.io.area_of_interest.EXTENTS).
EXTENT = "wlg-pilot"

# The exposure world and earthquake realisation the project shows.
WORLD_ID = 0
REALISATION_ID = 0

# The view the project opens on, in NZTM (the pilot box).
OPEN_EXTENT = (1748323.0, 5423605.0, 1751191.0, 5425337.0)

# Contours drawn from the 3 m DEM: every CONTOUR_STEP_M, darker every
# CONTOUR_INDEX_M.
CONTOUR_STEP_M = 5.0
CONTOUR_INDEX_M = 25.0
