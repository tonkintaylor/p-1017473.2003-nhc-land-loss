"""Run settings for running the whole pipeline end to end.

`gen_all.py` beside this runs hazard, exposure, the hazard module's urban pass
and vul in that order, each through its own `gen_<module>.py`. The three
settings here override every module's own, so the whole pipeline runs over one
extent, one set of exposure worlds and one set of realisations and ends at the
tables the loss module reads.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities.
PILOT = True

# Which exposure worlds to run. A world is one draw of the wall population,
# seeded apart from the earthquakes because whether a wall exists is not
# something the earthquake decides. World 0 is the same population in every
# module.
WORLD_IDS = [0]

# Which modelled earthquakes to run. The seed stream is shared across the
# hazards, so realisation 3 is the same earthquake in every module.
REALISATION_IDS = [0]
