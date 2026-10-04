"""Run settings for the land damage state step.

Everything that changes between one run of this step and the next, in one short
file. Both `gen_liq_ld_states.py` and `fig_ld_states.py` beside it read from
here, which is what keeps the figure drawing the realisation the draw actually
wrote.

`EXTENT` is taken from step 2's own `config.py` rather than repeated here. This
step reads the probability rasters step 2 wrote, so a second copy of the setting
would only ever be a way of sending it to look for a file that is not there.
"""

from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities import (
    config as probabilities_config,
)

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS. Change it in step 2's
# config.py; this step follows.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = probabilities_config.EXTENT

# Which realisations to draw. A realisation is one modelled earthquake, and its
# id is what ties this raster to the shaking and landslide layers of the same
# event. The beta runs one, because its purpose is the data structure rather
# than a distribution.
REALISATION_IDS = [0]
