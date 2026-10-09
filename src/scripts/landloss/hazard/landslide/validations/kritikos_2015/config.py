"""Run settings for the Kritikos (2015) reproduction of the paper's AUCs."""

# The events to reproduce, from event_inputs.EVENTS. Chi-Chi is not here: the
# GFDB holds only its liquefaction, not the Dadson et al. landslide inventory.
EVENTS = ["northridge", "wenchuan"]

# The base case is the landslide step 8 setting, so the paper's numbers are reproduced by
# the model the Wellington run uses.
GAMMA = 0.9
TPI_WINDOW_M = 600.0

# Sensitivities run beside the base case. The paper gives no TPI neighbourhood,
# and says gamma of 0.8 changed Wenchuan's AUC by 0.005.
TPI_SENSITIVITY_WINDOWS_M = [300.0, 1200.0]
GAMMA_SENSITIVITY = 0.8

# The paper does not define its study area, and it moves the AUC more than
# anything else: flat ground far from any landslide scores as easy negatives.
# The base case is the inventory's bounding box; these widen it.
STUDY_AREA_MARGINS_M = [5000.0, 15000.0]

# Reuse downloaded inputs and the per-event GFDB cache.
USE_CACHE = True
