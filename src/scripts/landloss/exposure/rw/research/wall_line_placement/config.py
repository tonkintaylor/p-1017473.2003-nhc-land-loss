"""Run settings for the wall line placement research script.

Everything that changes between one run of ``gen_wall_line_options.py`` and the
next. The line rules (bends, turning, length) are ground step 3's, imported
from its config, so a redrawn line is held to the rules every unit's line is.
"""

from scripts.landloss.ground.steps.s3_instability_zones.config import (
    MAX_TOTAL_TURN_DEG,
    WALL_MAX_BENDS,
    WALL_MAX_LENGTH_M,
    WALL_MIN_SEGMENT_M,
)

EXTENT = "wlg-pilot"

# A toe point (the lead, 2026-10-12, option 7) is a pif point (a pip, or the
# cell a pip falls to at 1 m) with no pip of its pif in its own downhill
# direction: within this angle either side of its fall (degrees; 45 left toe
# points uphill of other toe points), out to this many metres (the lead's
# extension of the pip test's furthest offset, 5 m).
TOE_ANGLE_DEG = 60.0
TOE_LOOK_M = 8.0

# The lead's offset (2026-10-12, 0.4 m to option 7, 0.5 m from option 8):
# every toe point moves this far down its own
# fall before the line is fitted. A pip is a cell centre; on a sharp step the
# step is 0.5 m past the lowest pip's centre (0.71 m on a diagonal).
OFFSET_M = 0.5

# Each end of the line (the lead, 2026-10-12, option 9) is the moved toe point
# on the lowest ground (1 m DEM) seen from the spine's end within
# END_SECTOR_DEG either side of the perpendicular to the spine's end segment,
# on its downhill side, and END_REACH_M of the end. Option 7 took the toe point
# nearest the spine's end, which on a straight spine could be a corner of the
# pif on the uphill side; option 8 projected the end down the pif's mean fall
# and took the furthest downhill within 1 m of that line.
END_SECTOR_DEG = 45.0
END_REACH_M = 10.0

# No bend of the line may turn back more than this (degrees; the lead,
# 2026-10-12): 0 is straight on, 180 a hairpin.
MAX_BEND_DEG = 100.0

# The line has the spine's bend count. The fit minimises a robust (soft L1)
# sum of the moved toe points' distances to the line, with this scale in
# metres.
FIT_LOSS_SCALE_M = 0.5

# The furthest an inner vertex may move from its seed (the spine's vertex), in
# metres: a vertex no toe point pulls on would otherwise wander off.
MAX_REACH_M = 6.0

# The outline drawn round each pif's points (the lead, 2026-10-12, to tell
# which pips belong to which pif): a concave hull with this ratio (shapely's,
# 0 the tightest, 1 the convex hull), grown by half a cell so it takes in the
# cells and not just their centres.
HULL_RATIO = 0.05

USE_CACHED_LAYERS = True

__all__ = [
    "END_SECTOR_DEG",
    "END_REACH_M",
    "EXTENT",
    "FIT_LOSS_SCALE_M",
    "HULL_RATIO",
    "MAX_BEND_DEG",
    "MAX_REACH_M",
    "MAX_TOTAL_TURN_DEG",
    "OFFSET_M",
    "TOE_ANGLE_DEG",
    "TOE_LOOK_M",
    "USE_CACHED_LAYERS",
    "WALL_MAX_BENDS",
    "WALL_MAX_LENGTH_M",
    "WALL_MIN_SEGMENT_M",
]
