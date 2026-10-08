"""Run settings for the retaining wall placement QGIS project."""

# The build extent the project reads (see landloss.io.area_of_interest.EXTENTS).
EXTENT = "wlg-pilot"

# The exposure world and earthquake realisation the project shows.
WORLD_ID = 0
REALISATION_ID = 0

# The view the project opens on, in NZTM (the pilot box).
OPEN_EXTENT = (1748323.0, 5423605.0, 1751191.0, 5425337.0)

# Contours from the 3 m DEM: every CONTOUR_STEP_M, darker every CONTOUR_INDEX_M.
CONTOUR_STEP_M = 2.0
CONTOUR_INDEX_M = 10.0

# How many equal-width bins the potential walls' p_wall is coloured in. The
# builder sets them over the data's own range (about 0.07 to 1.0 on the pilot,
# 2026-10-07), so read the legend for each bin's values.
P_WALL_BINS = 10
