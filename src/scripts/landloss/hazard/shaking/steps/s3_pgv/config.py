"""Run settings for the PGV step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history.
"""

# Whether to clip to the small Wellington pilot box rather than the four
# territorial authorities.
PILOT = True

# The return period of the TS1170.5 demand, in years. One of the seven Table 3.2
# carries (landloss.io.ts1170.RETURN_PERIODS_YR).
RETURN_PERIOD_YR = 2500
