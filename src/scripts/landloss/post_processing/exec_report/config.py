"""Run settings for the exec report figures.

`fig_exec_chain_map.py` and `fig_exec_liq_chain_map.py` beside this read these
and hold no defaults of their own.
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

# The figures `fig_exec_liq_chain_map.py` draws, by the name each is written
# under, as (the extent whose liquefaction outputs are read, the window drawn).
# A window is an NZTM box or the name of an extent in
# landloss.io.area_of_interest.EXTENTS. Porirua's is the chain map's window;
# the Hutt ones are the valley floors and two suburbs, Alicetown and Trentham,
# all read out of the whole-city runs.
LIQ_WINDOWS = {
    "porirua": ("porirua", WINDOW_NZTM),
    "lower-hutt-main-valley": ("lower-hutt", "lower-hutt-main-valley"),
    "upper-hutt-main-valley": ("upper-hutt", "upper-hutt-main-valley"),
    "lower-hutt-alicetown": ("lower-hutt", "lower-hutt-alicetown"),
    "upper-hutt-trentham": ("upper-hutt", "upper-hutt-trentham"),
}
