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

# Wall units (gen_urban_slope_wall_units.py). Members of one GNS mapped wall
# feature, within GNS_WALL_MATCH_M of it, are one unit. Elsewhere two pifs on
# one property join end to end where the gap between their facing ends is
# within WALL_JOIN_GAP_M, the ends are offset along their fall by no more than
# WALL_JOIN_MAX_OFFSET_M (so terraces stacked down a slope stay apart) and
# their end falls differ by no more than WALL_JOIN_BEARING_TOL_DEG. A corner
# joins where the ends are within WALL_CORNER_GAP_M and turn by more than
# WALL_JOIN_BEARING_TOL_DEG and no more than WALL_CORNER_MAX_ANGLE_DEG. Start values from the plan
# (.agents/plans/placing-retaining-walls-on-pifs.md), open until T-50.
WALL_JOIN_GAP_M = 5.0
WALL_JOIN_MAX_OFFSET_M = 1.5
WALL_JOIN_BEARING_TOL_DEG = 30.0
WALL_CORNER_GAP_M = 3.0
WALL_CORNER_MAX_ANGLE_DEG = 90.0

# A GNS-only piece within this many metres of a candidate pif on the same
# property joins its unit whatever its direction, so one wall is not counted
# twice (about 17% of the mapped wall length is 2 to 5 m from a pip).
GNS_ONLY_MERGE_M = 5.0

# A pif's wall height is this quantile, over its pips, of the drop from each
# pip to the foot of its face (landslide step 13's pip table). The pif's
# largest pip drop (max_delta_h_m) overstated the retained height: on the pilot
# 29% of walled units were under 1.5 m against 54% in Anderson et al. (2015).
# The lead set the 80th percentile on 2026-10-06.
WALL_HEIGHT_QUANTILE = 0.8

# GNS mapped wall segments within this many metres of each other are one
# mapped wall feature.
GNS_FEATURE_SNAP_M = 0.5

# The share of claimed properties held out of the claim update for the
# cross-validation, and the seed that picks them.
CLAIM_HOLDOUT_SHARE = 0.3
CLAIM_HOLDOUT_SEED = 2003

# Whether the wall probability takes the NZMM update (has_retaining_wall true
# read as BETA_NZMM_MIN_WALLS walls, applied at BETA_NZMM_UPDATE_WEIGHT of the
# full update). Both versions are written either way; NZMM is flagged
# unreliable (kappa 0.03 against GNS, provenance unknown).
USE_NZMM_UPDATE = True

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
