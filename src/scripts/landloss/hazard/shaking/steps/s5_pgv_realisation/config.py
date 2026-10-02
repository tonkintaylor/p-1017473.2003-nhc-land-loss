"""Run settings for the PGV realisation step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history.

The 10% coefficient of variation is not here. It is the beta's stand-in for the
ground motion model's own sigma rather than a setting of a run, so it lives with
the code that applies it, as `landloss.hazard.shaking.pga.BETA_PGA_COV`; this
step draws against it exactly as step 4 does.

`RETURN_PERIOD_YR` is taken from step 3's own `config.py` rather than repeated
here. This step scales the PGV grid step 3 wrote at that return period, so a
second copy of the setting would only ever send it to look for a file step 3
never wrote, or read a stale one.
"""

from scripts.landloss.hazard.shaking.steps.s3_pgv import config as pgv_config

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Step 3 must have been run over the same extent.
PILOT = True

# Which modelled earthquakes to draw. A realisation id is the whole event: the
# same id in the shaking, liquefaction and landslide layers is the same
# earthquake, and the same id here and in step 4 takes the same factor.
REALISATION_IDS = [0]

# The return period of the TS1170.5 demand, in years: the PGV grid step 3 wrote
# at this return period is the one scaled. Change it in step 3's config.py;
# this step follows.
RETURN_PERIOD_YR = pgv_config.RETURN_PERIOD_YR
