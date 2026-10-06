"""Run settings for the urban slope fragility step.

Everything that changes between one run of this step and the next, in one short
file. `gen_urban_slope_fragility.py`, `fig_urban_slope_model.py` and
`table_urban_slope_model.py` take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the
git history of it rather than by remembering which flags were typed.

The fragility numbers are not here. The wall curves are the packaged
``retaining-wall-type-fragility.csv`` (one per wall type and size class) and
the localised median's constants live in
`landloss.hazard.landslide.urban.fragility`, because they are the model, not a
setting of a run.

`WORLD_IDS` is taken from exposure rw step 6's `config.py`, as landslide step
12 takes it: step 12 draws and zones those worlds and rw step 6 populates
them, so a second copy could only ask for a world neither wrote.

`RETURN_PERIOD_YR` is taken from shaking step 3's own `config.py` rather than
repeated here. This step reads the PGV grid step 3 wrote at that return period,
so a second copy of the setting would only ever send it to look for a file step
3 never wrote, or read a stale one.
"""

from scripts.landloss.exposure.rw.steps.s6_wall_population import (
    config as wall_population_config,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv import config as pgv_config

# The extent to run over: "wlg-pilot" for the small Wellington pilot box,
# "wlg-earthworks-pilot" for the Johnsonville and Newlands box, or "full" for
# the four territorial authorities.
# Must match the run of landslide step 12 whose per-world zones, elements and
# wall units this step reads, the run of exposure rw step 6 whose drawn walls
# it joins, and the run of shaking steps 2 and 3 whose grids the PGV/PGA ratio
# is read from.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which exposure worlds to build a model file for. One file per world: step
# 12's zones of the walls that world drew, joined to the same walls as
# exposure rw step 6 drew them. Change them in that step's config.py.
#
# Figure mode: fig_urban_slope_model.py and table_urban_slope_model.py draw
# each world's model, the pipeline's drawn walls. The two whole-scenario
# bounds, every candidate walled and none walled, are drawn by landslide step
# 12's fig_urban_slope_wall_zones.py (FIG_ZONE_SCENARIOS in its config.py).
WORLD_IDS = wall_population_config.WORLD_IDS

# The rate setting of plan section 4.4: one of the keys of
# URBAN_RATE_FACTORS in landloss.domain.constants, low, medium or high,
# multiplying every urban fragility median. "medium" is 1.0 by definition; a
# "low" failure rate is a higher median. Written into the model file and
# printed by every run.
URBAN_RATE = "medium"

# The return period of the TS1170.5 demand the PGV/PGA ratio is read at: step
# 3's PGV grid over the unscaled PGA grid, both at this return period. Change
# it in shaking step 3's config.py; this step follows.
RETURN_PERIOD_YR = pgv_config.RETURN_PERIOD_YR
