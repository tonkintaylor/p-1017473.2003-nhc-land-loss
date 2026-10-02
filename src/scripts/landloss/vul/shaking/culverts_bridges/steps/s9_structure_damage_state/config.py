"""Run settings for the culvert and bridge damage state step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

The failure probability is **not** here. It belongs to the fragility, which
lives in :mod:`landloss.vul.shaking.fragility` and is a property of the structure
and the shaking rather than a setting of the run.
"""

# The extent to run over: "wlg-pilot" (the small Wellington pilot box),
# "wlg-earthworks-pilot" (Johnsonville and Newlands) or "full" (the four
# territorial authorities). Must match the runs of the shaking hazard and the
# crossing population this reads.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which modelled earthquakes to draw damage states for.
REALISATION_IDS = [0]
