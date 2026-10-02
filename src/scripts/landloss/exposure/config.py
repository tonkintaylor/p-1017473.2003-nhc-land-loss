"""Run settings for running the whole exposure module end to end.

`gen_exposure.py` beside this runs every step of the module in order. The
settings here override each step's own `config.py`, so the whole module runs
over one extent, one set of exposure worlds and one set of realisations.
Everything else a step reads, such as whether to reuse a cached download, still
comes from that step's own `config.py`.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities.
PILOT = True

# Which exposure worlds to draw the retaining wall population for. A world is
# one draw of which candidate lines are walls, seeded on EXPOSURE_BASE_SEED and
# the world id, so a few worlds pair with many hazard realisations.
WORLD_IDS = [0]

# Which modelled earthquakes to run. The crossing population is still drawn
# per realisation under the shared seed stream.
REALISATION_IDS = [0]
