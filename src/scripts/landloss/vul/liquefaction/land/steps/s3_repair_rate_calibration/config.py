"""Run settings for the liquefaction repair rate calibration.

Everything that changes between one run of this step and the next, in one short
file. The script beside it takes these as arguments and holds no defaults of its
own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.
"""

# Whether to fit against the small Wellington pilot box. Must match the run of
# step 2 this reads.
PILOT = True

# Which realisations of step 2 to pool the claims of. More realisations give
# steadier mean areas per state; the areas do not depend on the shaking.
REALISATION_IDS = [0]

# The land damage states the rates are fitted against. State 1, None, is left
# out: it loses no ground, so the fit could only price it at the fixed cost per
# claim, and it should be priced by the drop-out instead.
FIT_STATES = [2, 3, 4, 5, 6]
