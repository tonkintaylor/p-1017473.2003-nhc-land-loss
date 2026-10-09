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
