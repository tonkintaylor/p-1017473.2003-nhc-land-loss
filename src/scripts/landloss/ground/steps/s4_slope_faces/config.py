"""Run settings for ground step 4, the slope faces (the wall evidence on each pif).

`gen_slope_faces.py` and `table_slope_face_checks.py` take these as arguments
and hold no defaults of their own. The pif and wall line rules that cut the
GNS-only candidates are ground step 3's (`s3_instability_zones/config.py`),
read from there so that the pifs and the GNS-only walls are cut alike.
"""

from scripts.landloss.ground.steps.s3_instability_zones.config import (
    MAX_TOTAL_TURN_DEG,
    WALL_MAX_BENDS,
    WALL_MAX_LENGTH_M,
    WALL_STRAY_TOLERANCE_M,
)

__all__ = [
    "EXTENT",
    "GNS_BREAK_MATCH_M",
    "GNS_ONLY_MIN_LENGTH_M",
    "GNS_WALL_MATCH_M",
    "LARGE_POLYGON_M2",
    "MANUAL_WALL_DUPLICATE_M",
    "MAX_TOTAL_TURN_DEG",
    "SEARCH_M",
    "USE_CACHED_LAYERS",
    "WALL_MAX_BENDS",
    "WALL_MAX_LENGTH_M",
    "WALL_STRAY_TOLERANCE_M",
]

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

# T+T's manually mapped walls (Koordinates 125317, pilot only) join the GNS
# mapped walls and are used exactly as they are; a manual wall within this many
# metres of a GNS wall is dropped first as the same wall mapped twice (the
# lead, 2026-10-08).
MANUAL_WALL_DUPLICATE_M = 2.0

# A GNS break in slope counts as agreeing with a pif within this many metres
# (3 m in the plan's detection check).
GNS_BREAK_MATCH_M = 3.0

# Walls, lines and buildings further than this from a pif are not recorded as
# near it, in metres.
SEARCH_M = 50.0

# A stretch of GNS mapped wall with no pip within GNS_WALL_MATCH_M becomes a
# candidate of its own only if it is at least this long, in metres.
GNS_ONLY_MIN_LENGTH_M = 3.0

# Evacuated polygons over this area, in square metres, are counted for review
# (the old pilot's largest was 2,142 m2).
LARGE_POLYGON_M2 = 2000.0

# Wall candidates (the lead, 2026-10-07): every siz pif piece, every other pif
# piece with a GNS mapped wall within GNS_WALL_MATCH_M (class low_height), and
# every stretch of GNS mapped wall further than that from every pip, cut by the
# line rules of ground step 3 (class gns_only). Each is an independent wall
# unit: nothing is joined.
