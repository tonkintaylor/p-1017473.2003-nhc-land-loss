"""Run settings for the retaining wall population step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

The probabilities are not here. They are judgement standing in for the claim
report extraction rather than settings of a run, so they live with the code
that applies them, in `landloss.exposure.rw.wall_probability`.

The wall line rules the wall units are checked against (bends, shortest
straight, longest unit, turning) are ground step 3's, where the pifs are first
cut (`ground/steps/s3_instability_zones/config.py`), and are read from there.
"""

from scripts.landloss.ground.steps.s3_instability_zones.config import (
    MAX_TOTAL_TURN_DEG,
    WALL_MAX_BENDS,
    WALL_MAX_LENGTH_M,
    WALL_MIN_SEGMENT_M,
)
from scripts.landloss.ground.steps.s4_slope_faces.config import GNS_WALL_MATCH_M

__all__ = [
    "AGE_EXTENT",
    "CLAIM_HOLDOUT_SEED",
    "CLAIM_HOLDOUT_SHARE",
    "EXTENT",
    "GNS_WALL_MATCH_M",
    "MAX_TOTAL_TURN_DEG",
    "USE_CACHED_LAYERS",
    "WALL_MAX_BENDS",
    "WALL_MAX_LENGTH_M",
    "WALL_MIN_SEGMENT_M",
    "WORLD_IDS",
]

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Must match the run of ground steps 3 and 4 whose siz table gen_wall_units.py
# reads, and the run of land step 5 whose insured land gen_wall_population.py
# filters on.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which exposure worlds to draw a population for. A world is one draw of which
# candidate walls exist, seeded on EXPOSURE_BASE_SEED and the world id and
# not on any earthquake, so a few worlds pair with many hazard realisations.
# Which wall units are walled is drawn per world by gen_wall_units.py, and the
# landslide wall zones (landslide step 4) read WORLD_IDS from here too. Read by
# gen_wall_units.py and gen_wall_population.py.
WORLD_IDS = [0]

# Whether to reuse the already-clipped LINZ layers for this extent. Set False
# to fetch them again. Read by gen_wall_probability.py for the LINZ property
# boundaries it ties each wall unit to a claim with.
USE_CACHED_LAYERS = True

# The extent exposure step 8 was run over, whose property ages
# (gen_rwt_age.py) and per-suburb age table (table_rwt_age_by_suburb.py)
# gen_wall_age.py reads. Exposure rw step 8 is run over the full extent and a smaller
# extent's walls are found in it by claim id, so this need not match EXTENT.
AGE_EXTENT = "full"

# The share of claimed properties held out of the claim update for the
# cross-validation, and the seed that picks them.
CLAIM_HOLDOUT_SHARE = 0.3
CLAIM_HOLDOUT_SEED = 2003
