"""Run settings for the liquefaction repair rate calibration.

Everything that changes between one run of this step and the next, in one short
file. The script beside it takes these as arguments and holds no defaults of its
own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.
"""

# The standard section the rates are back-calculated on, in m² of insured land
# (Perrie Gilbert, 2026-10-12): it loses the middle of each state's evacuated
# range and of its inundated share of this.
SECTION_M2 = 500.0

# How much of each site's ejecta the Student Volunteer Army cleared for nothing
# in Canterbury (Perrie Gilbert, 2026-10-12): about 250 m², enough that a
# Moderate site, given about 240 m² of ejecta, cost no more than a Minor one
# with none -- as Canterbury's medians show. The inundated rate is fitted to the
# ejecta beyond it, which is what claims paid for; without volunteers all of it
# is paid. JUDGEMENT: the medians fit about as well from 200 m² to 300 m².
VOLUNTEER_CLEARED_M2 = 250.0

# The land damage states the rates are fitted against: Minor to Very severe.
# None is left out: it has no damage, so it costs nothing, fixed cost included
# (2026-10-12).
FIT_STATES = [2, 3, 4, 5, 6]

# Whether each state counts in the fit by its Canterbury claim count, so the
# 11,838 Moderate claims weigh more than the 43 Very severe ones. False weights
# every state the same.
WEIGHT_BY_CLAIMS = True

# The run the rates are checked against: each claim step 2 drew there, priced
# from its own ground, against the Canterbury quartiles in today's dollars.
COMPARE_EXTENT = "lower-hutt"
COMPARE_REALISATION_IDS = [0]
