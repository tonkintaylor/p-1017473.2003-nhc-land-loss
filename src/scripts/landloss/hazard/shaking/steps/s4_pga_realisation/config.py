"""Run settings for the PGA realisation step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history.

The 10% coefficient of variation is not here. It is the beta's stand-in for the
ground motion model's own sigma rather than a setting of a run, so it lives with
the code that applies it, as `landloss.hazard.shaking.pga.BETA_PGA_COV`.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Step 2 must have been run over the same extent.
PILOT = True

# Which modelled earthquakes to draw. A realisation id is the whole event: the
# same id in the shaking, liquefaction and landslide layers is the same
# earthquake.
REALISATION_IDS = [0]

# The return period of the TS1170.5 demand, in years. One of the seven Table 3.2
# carries (landloss.io.ts1170.RETURN_PERIODS_YR).
RETURN_PERIOD_YR = 2500
