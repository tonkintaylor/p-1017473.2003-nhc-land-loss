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

# ---- Option 10 (the lead, 2026-10-13): the line along the pif's downhill
# outline, and the pips it holds (``toe_outline.py``). Settled on the 120
# cases of ``temp/wall-line-brief/brief.md``, where it was option A.

# The outline is walked every OUTLINE_STEP_M; each sample's outward normal is
# read off the outline this far either side, and the local fall off the pips
# within FALL_RADIUS_M.
OUTLINE_STEP_M = 0.5
NORMAL_HALF_WINDOW_M = 1.5
FALL_RADIUS_M = 3.0
# A sample is on the toe when its normal is within this angle of the fall:
# the first angle that gives a run MIN_RUN_M long (degrees).
MAX_NORMAL_ANGLES_DEG = (45.0, 60.0, 75.0, 90.0)
MIN_RUN_M = 4.0
# Gaps in the toe run bridged, each tried in turn, the first line with few
# pips beyond it kept (metres).
JOIN_GAPS_M = (6.0, 3.0, 1.5, 9.0, 12.0)
# The run is cut to this length (the wall line rule is 50 m) and fitted on
# samples this far apart: 2 m let a short end jog through on WU0001293 and
# was dropped (the lead, 2026-10-13).
OUTLINE_MAX_LENGTH_M = 49.0
FIT_STEP_M = 1.0
# The regulariser: each bend costs this (m2 of area between path and line)
# times 1 + length / BEND_LENGTH_SCALE_M; the vertex polish takes at most
# REFINE_MAX_NFEV evaluations.
BEND_PENALTY_M2 = 2.5
BEND_LENGTH_SCALE_M = 25.0
REFINE_MAX_NFEV = 20
# An end section shorter than HOOK_M, or than HOOK_SHARP_M when it turns more
# than HOOK_SHARP_DEG, is a corner hook and is cut off.
HOOK_M = 4.0
HOOK_SHARP_M = 5.0
HOOK_SHARP_DEG = 60.0
# The candidates' score: the share of pips more than BEYOND_M past the line
# downhill (a score under BEYOND_OK ends the search), plus penalties for a
# fit further than RMS_OK_M from its run, a line leaving its run by more than
# CHORD_OK_M (a chord across a notch), each bend, and an S jog (opposite turns
# with a section under JOG_M between).
BEYOND_M = 0.75
BEYOND_OK = 0.1
RMS_OK_M = 1.0
RMS_WEIGHT = 0.25
CHORD_OK_M = 1.5
CHORD_WEIGHT = 0.15
BEND_SCORE = 0.03
JOG_M = 8.0
JOG_SCORE = 0.15

# A pip is on the wall when its fall, widened this far either side (degrees)
# and this long (metres), meets the line (the lead, 2026-10-13).
CONE_HALF_ANGLE_DEG = 45.0
CONE_REACH_M = 200.0
CONE_ARC_N = 9
# Pips the wall does not hold, up to LEFTOVER_JOIN_M apart (a one-cell gap
# does not split them), are a pif with no wall when more than
# MIN_NO_WALL_PIPS; fewer go back to the wall's pif, as does a group with more
# than ENCLOSED_SHARE of its edge on it (within EDGE_BUFFER_M).
LEFTOVER_JOIN_M = 2.1
MIN_NO_WALL_PIPS = 5
ENCLOSED_SHARE = 0.5
EDGE_BUFFER_M = 0.5
# The wall's pif must touch (8-connected, WALL_JOIN_M): a group of wall pips
# within STAY_M of the line stays, any other leaves it.
WALL_JOIN_M = 1.5
STAY_M = 3.0

# Units are drawn in this many processes, CHUNK_UNITS at a time (1: in the
# script's own process).
N_WORKERS = 16
CHUNK_UNITS = 25

__all__ = [
    "BEND_LENGTH_SCALE_M",
    "BEND_PENALTY_M2",
    "BEND_SCORE",
    "BEYOND_M",
    "BEYOND_OK",
    "CHORD_OK_M",
    "CHORD_WEIGHT",
    "CHUNK_UNITS",
    "CONE_ARC_N",
    "CONE_HALF_ANGLE_DEG",
    "CONE_REACH_M",
    "EDGE_BUFFER_M",
    "ENCLOSED_SHARE",
    "END_REACH_M",
    "END_SECTOR_DEG",
    "EXTENT",
    "FALL_RADIUS_M",
    "FIT_LOSS_SCALE_M",
    "FIT_STEP_M",
    "HOOK_M",
    "HOOK_SHARP_DEG",
    "HOOK_SHARP_M",
    "HULL_RATIO",
    "JOG_M",
    "JOG_SCORE",
    "JOIN_GAPS_M",
    "LEFTOVER_JOIN_M",
    "MAX_BEND_DEG",
    "MAX_NORMAL_ANGLES_DEG",
    "MAX_REACH_M",
    "MAX_TOTAL_TURN_DEG",
    "MIN_NO_WALL_PIPS",
    "MIN_RUN_M",
    "NORMAL_HALF_WINDOW_M",
    "N_WORKERS",
    "OFFSET_M",
    "OUTLINE_MAX_LENGTH_M",
    "OUTLINE_STEP_M",
    "REFINE_MAX_NFEV",
    "RMS_OK_M",
    "RMS_WEIGHT",
    "STAY_M",
    "TOE_ANGLE_DEG",
    "TOE_LOOK_M",
    "USE_CACHED_LAYERS",
    "WALL_JOIN_M",
    "WALL_MAX_BENDS",
    "WALL_MAX_LENGTH_M",
    "WALL_MIN_SEGMENT_M",
]
