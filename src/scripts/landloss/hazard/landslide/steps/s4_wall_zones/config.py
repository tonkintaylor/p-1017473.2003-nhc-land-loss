"""Run settings for landslide step 4, the zones of each world's walls.

`gen_wall_zones.py` and `fig_wall_zones.py` take these as arguments and hold no
defaults of their own.

`WORLD_IDS` is taken from exposure rw step 6's own `config.py` rather than
repeated here: that step draws which wall units are walled in each world, and
this step builds the zones of those draws.
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

# Whether to build every tile again even when the kept tiles' record matches:
# the found elements, the wall units and draws, the scenarios and worlds, and the
# code that builds a tile. Leave False; a stopped run resumes from the tiles
# already kept. Set True after a change the record cannot see, such as replacing
# a cached LINZ layer by hand. USE_CACHED_LAYERS False rebuilds every tile by
# itself, since fetching the layers again may change them. Only an extent ground step 3
# searched in tiles keeps tiles.
REBUILD = False

# How many tiles are built at once, each in its own process, over an extent
# ground step 3 searched in tiles. Each worker reads the ground map, the
# coastline and the building outlines once, and holds one tile's zones at a
# time, which it writes to disk when done; allow several GB per worker (the
# ground map alone is about 4.6 GB over Upper Hutt). Set 1 to build the tiles in
# order in this process. It does not change the result.
TILE_WORKERS = 4

# The exposure worlds to build the zones for: the worlds exposure rw step 6
# draws. Change them in that step's config.py; this step follows.
WORLD_IDS = wall_population_config.WORLD_IDS

# Figure mode of fig_wall_zones.py: the zone files drawn side by
# side at each pilot site, one panel each. "walled" (every siz walled) and
# "bare" (none walled) are the two whole-scenario bounds gen_wall_zones.py
# writes, for seeing what the walls change; "w000" and so on are one world's
# drawn walls (gen_wall_zones.py), the zones the pipeline (landslide
# steps 5 and 6) reads. The bounds are never read by the pipeline.
FIG_ZONE_SCENARIOS = ("walled", "bare")

# Aligning each walled element's evacuated polygons with its wall's line (the
# lead, 2026-10-13; landloss.hazard.landslide.wall_trim.WallTrimSettings). Trim:
# a polygon within WALL_TRIM_BESIDE_M of its wall's line is cut by the line, its
# ends projected on along the end sections (past the polygon's bounding box
# diagonal by WALL_TRIM_EXTEND_PAD_M), and the pieces downhill are removed;
# pieces under WALL_TRIM_SLIVER_M2 are slivers and ignored in the counts.
WALL_TRIM_BESIDE_M = 2.0
WALL_TRIM_EXTEND_PAD_M = 5.0
WALL_TRIM_SLIVER_M2 = 0.5
# Fill: the line is sampled every WALL_TRIM_SAMPLE_M; samples within
# WALL_TRIM_CLOSE_M of the trimmed polygons anchor a fill, and between the
# outer anchors every run of samples further than WALL_TRIM_GAP_M off the
# polygons is filled. Rays go along the line's normal up to WALL_TRIM_RAY_M, held
# to WALL_TRIM_OBLIQUE_FACTOR times the sample's distance plus
# WALL_TRIM_OBLIQUE_PAD_M so they cannot cross a notch; the fill runs
# WALL_TRIM_OVERLAP_M into the polygon so the union closes.
WALL_TRIM_SAMPLE_M = 0.25
WALL_TRIM_CLOSE_M = 0.5
WALL_TRIM_GAP_M = 0.02
WALL_TRIM_RAY_M = 20.0
WALL_TRIM_OVERLAP_M = 0.05
WALL_TRIM_OBLIQUE_FACTOR = 2**0.5
WALL_TRIM_OBLIQUE_PAD_M = 0.25

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
