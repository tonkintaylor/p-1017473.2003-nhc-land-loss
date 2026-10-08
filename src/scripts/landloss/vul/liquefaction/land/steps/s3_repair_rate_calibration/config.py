"""Run settings for the liquefaction repair rate calibration.

Everything that changes between one run of this step and the next, in one short
file. The script beside it takes these as arguments and holds no defaults of its
own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.
"""

# The extent to fit over, a name from landloss.io.area_of_interest.EXTENTS or
# "full". Must match the run of step 2 this reads.
EXTENT = "wlg-pilot"

# Which realisations of step 2 to pool the claims of. More realisations give
# steadier mean areas per state; the areas do not depend on the shaking.
REALISATION_IDS = [0]

# The land damage states the rates are fitted against: all six. None loses no
# ground, so its claims cost the fixed cost alone, which is what anchors it.
FIT_STATES = [1, 2, 3, 4, 5, 6]

# Whether each state counts in the fit by its Canterbury claim count, so the
# 11,838 Moderate claims weigh more than the 43 Very severe ones. False weights
# every state the same.
WEIGHT_BY_CLAIMS = True
