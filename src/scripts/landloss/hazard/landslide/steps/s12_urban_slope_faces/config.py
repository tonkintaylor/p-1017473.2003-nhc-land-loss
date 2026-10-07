"""Run settings for the urban slope faces step.

Everything that changes between one run of this step and the next, in one short
file. `gen_urban_slope_faces.py`, `table_urban_slope_face_checks.py`,
`gen_urban_slope_wall_units.py`, `gen_urban_slope_wall_zones.py` and
`table_urban_slope_wall_checks.py` take these as arguments and hold no
defaults of their own. The wall probability weights are not here: they are
`BETA_` judgement in `landloss.domain.constants`.

`WORLD_IDS` is taken from exposure rw step 6's own `config.py` rather than
repeated here: that step populates the worlds whose wall units this step
draws, so a second copy could only draw worlds it never reads, or miss one.
"""

from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    config as wall_population_config,
)

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

# The fall direction at each end of a pif is the mean over its pips within
# this many metres of the spine end.
PIF_END_WINDOW_M = 3.0

# Evacuated polygons over this area, in square metres, are counted for review
# (the old pilot's largest was 2,142 m2).
LARGE_POLYGON_M2 = 2000.0

# Wall candidates (the lead, 2026-10-07): every siz pif piece, every other pif
# piece with a GNS mapped wall within GNS_WALL_MATCH_M (class low_height), and
# every stretch of GNS mapped wall further than that from every pip, cut by the
# line rules below (class gns_only). Each is an independent wall unit: nothing
# is joined.

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

# A pif's wall height is the WALL_HEIGHT_QUANTILE quantile, over its pips, of
# each pip's near drop: the fall to the lowest DEM cell within
# WALL_HEIGHT_REACH_M metres below the pip along its own fall direction (the
# 1 m and 3 m offsets the pip test reads). The lead, 2026-10-06: landslide
# step 13's walk to the foot of the face ran up to 15 m down long batters and
# hillsides and overstated the height (the tall face taper then hit 2,013
# pilot units), as the pif's largest pip drop (max_delta_h_m) did before it.
# The lead set the 70th percentile within 2 m on 2026-10-06: the 80th within
# 3 m put 18% of the pilot's walled units under 1.5 m and the 60th within 2 m
# 72%, against 54% in Anderson et al. Read in gen_urban_slope_faces.py onto the
# siz table (near_drop_p80_m, named for the first setting).
WALL_HEIGHT_REACH_M = 2.0
WALL_HEIGHT_QUANTILE = 0.7

# A 1 m DEM holding more cells than this is searched for faces, and its wall
# zones built, tile by tile (tiled.py) rather than whole, as landslide step 6
# delineates (its MAX_UNTILED_CELLS). Every pilot runs whole; over Porirua the
# whole grid would need about 95 GB.
MAX_UNTILED_CELLS = 50_000_000

# The side of a tile's core, in metres.
TILE_CORE_M = 3_000.0

# The width read around each core, in metres. It has to be wider than the
# longest parent pif, so that the tile owning a pif sees it whole and cuts it
# into the pieces the whole grid would: the longest on the two pilots spans
# 636 m.
TILE_MARGIN_M = 750.0

# The share of claimed properties held out of the claim update for the
# cross-validation, and the seed that picks them.
CLAIM_HOLDOUT_SHARE = 0.3
CLAIM_HOLDOUT_SEED = 2003

# The wall probability is the lead's points scale (2026-10-07): the points
# table is landloss/io/assets/wall-probability-points.csv and the base and the
# points per doubling are BETA_ constants in landloss.domain.constants. NHC's
# land attributes flag is points, not an update.

# The exposure worlds to draw the wall units for: the worlds exposure rw step 6
# populates. Change them in that step's config.py; this step follows.
WORLD_IDS = wall_population_config.WORLD_IDS

# Figure mode of fig_urban_slope_wall_zones.py: the zone files drawn side by
# side at each pilot site, one panel each. "walled" (every siz walled) and
# "bare" (none walled) are the two whole-scenario bounds gen_urban_slope_faces.py
# writes, for seeing what the walls change; "w000" and so on are one world's
# drawn walls (gen_urban_slope_wall_zones.py), the zones the pipeline (steps 8
# and 9) reads. The bounds are never read by the pipeline.
FIG_ZONE_SCENARIOS = ("walled", "bare")

# The pilot sites the figure draws, each a window 2 * half_size_m a side
# centred on an NZTM point: the stage D2 sites of the slope elements research
# (research/slope_elements/config.py, where each is described), repeated here
# because a step may not import research code. Keep the two lists alike.
FIG_SITES = (
    {"name": "01-wall-soil", "x": 1748714.0, "y": 5424998.0, "half_size_m": 60.0},
    {"name": "02-wall-tall", "x": 1750089.0, "y": 5424544.0, "half_size_m": 60.0},
    {"name": "03-wall-flat", "x": 1750441.0, "y": 5425145.0, "half_size_m": 60.0},
    {"name": "04-road-cut", "x": 1748398.0, "y": 5425070.0, "half_size_m": 70.0},
    {"name": "05-excavated-toe", "x": 1749009.0, "y": 5423918.0, "half_size_m": 70.0},
    {"name": "06-fill-platform", "x": 1749449.0, "y": 5423734.0, "half_size_m": 70.0},
    {"name": "07-fill-gully", "x": 1748600.0, "y": 5424461.0, "half_size_m": 90.0},
    {
        "name": "08-adjacent-catchments",
        "x": 1749472.0,
        "y": 5424360.0,
        "half_size_m": 60.0,
    },
    {"name": "09-seawall", "x": 1750555.0, "y": 5424878.0, "half_size_m": 80.0},
    {"name": "10-steep-bank", "x": 1749520.0, "y": 5424724.0, "half_size_m": 60.0},
    {"name": "11-mapped-failure", "x": 1749417.0, "y": 5424214.0, "half_size_m": 60.0},
    {"name": "12-gentle-control", "x": 1750665.0, "y": 5423785.0, "half_size_m": 60.0},
)
