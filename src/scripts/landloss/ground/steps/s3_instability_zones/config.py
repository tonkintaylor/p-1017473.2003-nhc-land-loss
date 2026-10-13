"""Run settings for ground step 3, the instability zones.

The pif cutting rules (bends, stray, turning, shortest piece, longest unit) and
the wall height read off each pif live here, where the pifs are first cut. They
are the walls' rules too: ground step 4 (the GNS-only candidates) and exposure
rw step 6 (the wall units) read them from here rather than holding a copy.
"""

# The extent to run over: a name from landloss.io.area_of_interest.EXTENTS
# ("wlg-pilot" for the small Wellington pilot box), or "full". Ground steps 1
# and 2 must have been run over the same extent. gen_ground.py passes its own.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ building outlines and coastline for this
# extent. Set False to fetch them again (and set REBUILD, since the step does
# not see that the layers changed).
USE_CACHED_LAYERS = True

# Whether to search the DEM again even when the last run's record matches: the
# settings, the 1 m DEM and the ground map, and the code that does the search.
# Leave False; the step skips itself in seconds when nothing has changed.
REBUILD = False

# The urban model runs within this many metres of a LINZ building outline (the
# lead, 2026-10-01, building-urban-slope-failure-and-retaining-wall-models.md;
# restored 2026-10-08): only the pips within this of a building are joined into
# pifs (the lead, 2026-10-09), a pif most of whose pips are on a building is
# dropped, and a tile with no cell within reach is skipped.
BUILDING_REACH_M = 100.0

# A 1 m DEM holding more cells than this is searched tile by tile (tiled.py
# beside this) rather than whole: 50 million cells is about 7 by 7 km at 1 m, so
# every pilot runs whole, and over Porirua the whole grid would need about
# 95 GB.
MAX_UNTILED_CELLS = 50_000_000

# The side of a tile's core, in metres.
TILE_CORE_M = 3_000.0

# The width read around each core, in metres. It has to be wider than the
# longest parent pif, so that the tile owning a pif sees it whole: the longest
# on the two pilots spans 636 m. Since 2026-10-08 the siz test is made on each
# piece (at most 50 m) with fall lines of at most 30 m, so the margin can come
# down once the tiles own pieces rather than parents (the plan, phase 2).
TILE_MARGIN_M = 750.0

# A tile is searched only on the bounds of its building outlines grown by
# BUILDING_REACH_M and this many metres more, not on its whole window (the
# lead, 2026-10-09): the pifs' fall lines, the elements grown from them and
# their catchments read past the pips. None searches the whole tile.
TILE_CROP_PAD_M = 100.0

# How many tiles are found at once, each in its own process. Each tile is
# written to disk when done and dropped from memory, and a stopped run resumes
# from the tiles not yet done. A 3 km tile with its margin is 4.5 by 4.5 km at
# 1 m; its found elements alone pickle to about 0.9 GB, so allow several GB per
# worker. Set 1 to run the tiles in order in this process.
TILE_WORKERS = 4

# No saw-tooth walls (the lead, 2026-10-06): each wall unit's line, the line
# exposure rw step 6 draws and the figures show, keeps at most WALL_MAX_BENDS
# bends, and no straight section of it is shorter than WALL_MIN_SEGMENT_M
# metres (a unit shorter than that is one straight line). Its length_m is the
# simplified line's; length_original_m keeps the members' summed length.
WALL_MAX_BENDS = 3
WALL_MIN_SEGMENT_M = 3.0

# Pifs and GNS-only walls (the lead, 2026-10-06; one rule for both,
# landloss.hazard.landslide.bend_split): a pif's spine, or a stretch of GNS
# mapped wall, is walked end to end and a new piece starts wherever following them within
# WALL_STRAY_TOLERANCE_M metres needs another bend than WALL_MAX_BENDS, or
# bends turning more than MAX_TOTAL_TURN_DEG degrees in all (the lead set 185
# on 2026-10-06, after a piece ran up, across and back down). 2 m is about the
# 90th percentile (2.4 m) of how far a pif's spine lay from its unit's line
# when the bends were not split.
WALL_STRAY_TOLERANCE_M = 2.0
MAX_TOTAL_TURN_DEG = 185.0

# Every wall unit is one line of at most WALL_MAX_BENDS bends, from
# WALL_MIN_SEGMENT_M to WALL_MAX_LENGTH_M metres long (a GNS-only piece is cut
# to it here, a pif piece at MAX_PIF_SPAN_M, also 50 m) (the lead, 2026-10-06:
# "if over 50 m, then split on bends; if no bends then split on boundaries,
# then split on evenly divide"): a wall over WALL_MAX_LENGTH_M is cut at its
# own bends, then (with no bend left) at the property boundaries it crosses,
# then into equal pieces; the pifs take the same cap at MAX_PIF_SPAN_M with no
# boundary stage. gen_wall_units refuses any unit that breaks a rule.
WALL_MAX_LENGTH_M = 50.0

# The fall direction at each end of a pif is the mean over its pips within
# this many metres of the spine end.
PIF_END_WINDOW_M = 3.0

# A pif's wall height is the WALL_HEIGHT_QUANTILE quantile, over its pips, of
# each pip's near drop: the fall to the lowest DEM cell within
# WALL_HEIGHT_REACH_M metres below the pip along its own fall direction (the
# 1 m and 3 m offsets the pip test reads). The lead, 2026-10-06: the walk to the
# foot of the face by the old landslide step 13 (now ground step 5) ran up to
# 15 m down long batters and hillsides and overstated the height (the tall face taper then hit 2,013
# pilot units), as the pif's largest pip drop (max_delta_h_m) did before it.
# The lead set the 70th percentile within 2 m on 2026-10-06: the 80th within
# 3 m put 18% of the pilot's walled units under 1.5 m and the 60th within 2 m
# 72%, against 54% in Anderson et al. Read in gen_slope_faces.py onto the
# siz table (near_drop_p80_m, named for the first setting).
WALL_HEIGHT_REACH_M = 2.0
WALL_HEIGHT_QUANTILE = 0.7

# ---- The wall line and the pips it holds (the lead, 2026-10-13, "option 10",
# settled on 120 cases and the wlg-pilot; landloss.hazard.landslide.wall_lines
# reads these through WallLineSettings and holds no default of its own). The
# line is drawn along each pif piece's downhill outline; the bends, section
# length and total turning it keeps are WALL_MAX_BENDS, WALL_MIN_SEGMENT_M and
# MAX_TOTAL_TURN_DEG above.

# The outline is walked every WALL_LINE_OUTLINE_STEP_M; each sample's outward
# normal is read off the outline this far either side, and the local fall off
# the pips within WALL_LINE_FALL_RADIUS_M.
WALL_LINE_OUTLINE_STEP_M = 0.5
WALL_LINE_NORMAL_HALF_WINDOW_M = 1.5
WALL_LINE_FALL_RADIUS_M = 3.0

# A sample is on the toe when its normal is within this angle of the fall: the
# first angle that gives a run WALL_LINE_MIN_RUN_M long (degrees).
WALL_LINE_NORMAL_ANGLES_DEG = (45.0, 60.0, 75.0, 90.0)
WALL_LINE_MIN_RUN_M = 4.0

# Gaps in the toe run bridged, each tried in turn, the first line with few pips
# beyond it kept (metres).
WALL_LINE_JOIN_GAPS_M = (6.0, 3.0, 1.5, 9.0, 12.0)

# The run is cut to this length (the wall line rule is 50 m) and fitted on
# samples this far apart: 2 m let a short end jog through on WU0001293 and was
# dropped (the lead, 2026-10-13).
WALL_LINE_MAX_LENGTH_M = 49.0
WALL_LINE_FIT_STEP_M = 1.0

# No bend of the line may turn back more than this (degrees; the lead,
# 2026-10-12): 0 is straight on, 180 a hairpin.
WALL_MAX_BEND_DEG = 100.0

# The regulariser: each bend costs this (m2 of area between path and line) times
# 1 + length / WALL_LINE_BEND_LENGTH_SCALE_M; the vertex polish (a soft L1
# least squares, scale WALL_LINE_FIT_LOSS_SCALE_M) moves each inner vertex at
# most WALL_LINE_REFINE_REACH_M and takes at most WALL_LINE_REFINE_MAX_NFEV
# evaluations.
WALL_LINE_BEND_PENALTY_M2 = 2.5
WALL_LINE_BEND_LENGTH_SCALE_M = 25.0
WALL_LINE_FIT_LOSS_SCALE_M = 0.5
WALL_LINE_REFINE_REACH_M = 1.5
WALL_LINE_REFINE_MAX_NFEV = 20

# An end section shorter than WALL_LINE_HOOK_M, or than WALL_LINE_HOOK_SHARP_M
# when it turns more than WALL_LINE_HOOK_SHARP_DEG, is a corner hook and is cut
# off.
WALL_LINE_HOOK_M = 4.0
WALL_LINE_HOOK_SHARP_M = 5.0
WALL_LINE_HOOK_SHARP_DEG = 60.0

# The candidates' score: the share of pips more than WALL_LINE_BEYOND_M past
# the line downhill (a score under WALL_LINE_BEYOND_OK ends the search), plus
# penalties for a fit further than WALL_LINE_RMS_OK_M from its run, a line
# leaving its run by more than WALL_LINE_CHORD_OK_M (a chord across a notch),
# each bend, and an S jog (opposite turns with a section under
# WALL_LINE_JOG_M between).
WALL_LINE_BEYOND_M = 0.75
WALL_LINE_BEYOND_OK = 0.1
WALL_LINE_RMS_OK_M = 1.0
WALL_LINE_RMS_WEIGHT = 0.25
WALL_LINE_CHORD_OK_M = 1.5
WALL_LINE_CHORD_WEIGHT = 0.15
WALL_LINE_BEND_SCORE = 0.03
WALL_LINE_JOG_M = 8.0
WALL_LINE_JOG_SCORE = 0.15

# A pip is on the wall when its fall, widened this far either side (degrees) and
# this long (metres), meets the line (the lead, 2026-10-13); the sector is a
# polygon of WALL_LINE_CONE_ARC_N arc vertices.
WALL_LINE_CONE_HALF_ANGLE_DEG = 45.0
WALL_LINE_CONE_REACH_M = 200.0
WALL_LINE_CONE_ARC_N = 9

# Pips the wall does not hold, up to WALL_LINE_LEFTOVER_JOIN_M apart (a
# one-cell gap does not split them), are a pif with no wall when more than
# WALL_LINE_MIN_NO_WALL_PIPS; fewer go back to the wall's pif, as does a group
# with more than WALL_LINE_ENCLOSED_SHARE of its edge on it (within
# WALL_LINE_EDGE_BUFFER_M). Raised from 5 to 7 to make fewer small no-wall pifs
# (the lead, 2026-10-13).
WALL_LINE_LEFTOVER_JOIN_M = 2.1
WALL_LINE_MIN_NO_WALL_PIPS = 7
WALL_LINE_ENCLOSED_SHARE = 0.5
WALL_LINE_EDGE_BUFFER_M = 0.5

# The wall's pif must touch (8-connected, WALL_LINE_WALL_JOIN_M): a group of
# wall pips within WALL_LINE_STAY_M of the line stays, any other leaves it.
WALL_LINE_WALL_JOIN_M = 1.5
WALL_LINE_STAY_M = 3.0
