"""Run settings for the landslide land damage step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

No repair rates are here, or anywhere else yet: the T+T landslip remediation
schedule is not packaged, so this step stops at damaged area and depth and the
pricing is left to the loss module once the schedule lands.
"""

# Whether to run over the small Wellington pilot box. Must match the runs of the
# landslide hazard and the insured land extent this reads.
PILOT = True

# Which exposure worlds to measure. The combined realisation is written per
# world and earthquake, because the urban failures depend on which walls the
# world drew.
WORLD_IDS = [0]

# Which modelled earthquakes to measure.
REALISATION_IDS = [0]
