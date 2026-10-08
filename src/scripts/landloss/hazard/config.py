"""Run settings for running the whole hazard module end to end.

`gen_hazard.py` beside this runs the module's steps in one pass, after the
ground and exposure modules (`gen_all.py` holds that order). The three
settings here override each step's own `config.py`, so the whole module runs
over one extent, one set of realisations and one set of exposure worlds.
Everything else a step reads, such as whether to reuse a cached elevation model
or the urban rate setting, still comes from that step's own `config.py`.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS, such as "wlg-pilot" for the
# small Wellington pilot box.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which modelled earthquakes to run. The seed stream is shared across the
# hazards, so realisation 3 is the same earthquake in every module.
REALISATION_IDS = [0]

# Which exposure worlds to run the urban slope chain for. A world is one draw
# of the wall population, seeded apart from the earthquakes because whether a
# wall exists is not something the earthquake decides; the urban failures of
# earthquake 3 are drawn once per world.
WORLD_IDS = [0]
