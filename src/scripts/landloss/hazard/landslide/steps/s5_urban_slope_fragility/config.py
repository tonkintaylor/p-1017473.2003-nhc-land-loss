"""Run settings for the urban slope fragility step.

Everything that changes between one run of this step and the next, in one short
file. `gen_urban_slope_fragility.py`, `fig_urban_slope_model.py` and
`table_urban_slope_model.py` take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the
git history of it rather than by remembering which flags were typed.

The fragility numbers are not here. The wall curves are the packaged
``retaining-wall-type-fragility.csv`` (one per wall type and height class) and
the localised curve is the packaged ``urban-localised-fragility.csv`` (two
p15/p50 points on site PGA), because they are the model, not a setting of a
run.

`WORLD_IDS` is taken from exposure rw step 6's `config.py`, as landslide step
4 takes it: exposure rw step 6 draws those worlds' walls and landslide step 4 zones
them, so a second copy could only ask for a world neither wrote.

The step reads no shaking demand: every curve is on site PGA (the lead,
2026-10-12), and landslide step 6 samples each earthquake's PGA from shaking
step 4. It reads only shaking step 2's site class grid, to record it.
"""

from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    config as wall_population_config,
)

# The extent to run over: "wlg-pilot" for the small Wellington pilot box,
# "wlg-earthworks-pilot" for the Johnsonville and Newlands box, or "full" for
# the four territorial authorities.
# Must match the run of landslide step 4 whose per-world zones and elements this
# step reads, the run of exposure rw step 6 whose wall units and drawn walls
# it joins, and the run of shaking step 2 whose site class grid is read.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which exposure worlds to build a model file for. One file per world: landslide
# step 4's zones of the walls that world drew, joined to the same walls as
# exposure rw step 6 drew them. Change them in that step's config.py.
#
# Figure mode: fig_urban_slope_model.py and table_urban_slope_model.py draw
# each world's model, the pipeline's drawn walls. The two whole-scenario
# bounds, every candidate walled and none walled, are drawn by landslide step
# 4's fig_wall_zones.py (FIG_ZONE_SCENARIOS in its config.py).
WORLD_IDS = wall_population_config.WORLD_IDS

# The rate setting of plan section 4.4: one of the keys of
# URBAN_RATE_FACTORS in landloss.domain.constants, low, medium or high,
# multiplying every urban fragility median. "medium" is 1.0 by definition; a
# "low" failure rate is a higher median. Written into the model file and
# printed by every run.
URBAN_RATE = "medium"
