"""Run settings for the urban slope faces step.

Everything that changes between one run of this step and the next, in one short
file. `gen_urban_slope_faces.py` and `table_urban_slope_face_checks.py` take
these as arguments and hold no defaults of their own.
"""

# The extent to run over: "wlg-pilot" for the small Wellington pilot box, or
# "full" for the four territorial authorities. Name outputs with
# extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ and GNS layers for this extent. Set False to
# fetch them again.
USE_CACHED_LAYERS = True

# A GNS mapped wall or cut/fill line counts as evidence for a pif where it lies
# within this many metres of one of its points (the plan's detection check takes
# 2 m for a wall).
GNS_WALL_MATCH_M = 2.0

# A GNS break in slope counts as agreeing with a pif within this many metres
# (3 m in the plan's detection check).
GNS_BREAK_MATCH_M = 3.0

# Walls, lines and buildings further than this from a pif are not recorded as
# near it, in metres.
SEARCH_M = 50.0

# Evacuated polygons over this area, in square metres, are counted for review
# (the old pilot's largest was 2,142 m2).
LARGE_POLYGON_M2 = 2000.0
