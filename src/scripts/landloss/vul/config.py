"""Run settings for running the whole vulnerability module end to end.

`gen_vul.py` beside this runs every step of the module in order. The three
settings here override each step's own `config.py`, so the whole module runs
over one extent, one set of exposure worlds and one set of realisations.
Everything else a step reads, such as the cost percentile, still comes from
that step's own `config.py`.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities.
PILOT = True

# Which exposure worlds to run. A world is one draw of the wall population;
# each must already have been run through the exposure module and the hazard
# module's urban pass.
WORLD_IDS = [0]

# Which modelled earthquakes to run. Each must already have been run through
# the exposure and hazard modules.
REALISATION_IDS = [0]
