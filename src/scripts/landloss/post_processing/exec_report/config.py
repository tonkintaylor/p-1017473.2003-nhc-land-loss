"""Run settings for the exec report figures.

`fig_exec_chain_map.py` beside this reads these and holds no defaults of its
own.
"""

# The extent whose outputs the map is drawn from: a name in
# landloss.io.area_of_interest.EXTENTS. "porirua-exec-map" is the small box
# made for this figure; until the chain and the loss module have been run over
# it, "porirua" draws the same window out of the whole-Porirua run.
EXTENT = "porirua"

# The exposure world and the earthquake realisation shown.
WORLD_ID = 0
REALISATION_ID = 0

# The return period the shaking was run at, for the caption only. Must match
# RETURN_PERIOD_YR in hazard/shaking/steps/s4_pga_realisation/config.py.
RETURN_PERIOD_YR = 2500

# The window each panel shows, NZTM (min E, min N, max E, max N): 600 by 450 m,
# "window A" of temp/exec-map-brief/brief.md, picked for holding culverts,
# landslides, insured walls and liquefied ground together.
WINDOW_NZTM = (1753553.0, 5442274.0, 1754153.0, 5442724.0)
