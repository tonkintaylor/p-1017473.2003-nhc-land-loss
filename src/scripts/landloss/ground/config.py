"""Run settings for running the whole ground module end to end.

`gen_ground.py` beside this runs the module's steps in order. The extent here
overrides each step's own `config.py`, so the whole module runs over one
extent; everything else a step reads, such as whether to reuse a cached layer
or to force the instability zones to be searched again, still comes from that
step's own `config.py`.
"""

# The extent to run over: a name from landloss.io.area_of_interest.EXTENTS
# ("wlg-pilot" for the small Wellington pilot box), or "full".
EXTENT = "wlg-pilot"
