"""Run settings for the retaining wall damage state step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

The fragility is **not** here. It belongs to the wall type curve table
``retaining-wall-type-fragility.csv`` and :mod:`landloss.vul.shaking.fragility`,
and is a property of the wall and the shaking rather than a setting of the run.
"""

# The extent to run over: "wlg-pilot" (the small Wellington pilot box),
# "wlg-earthworks-pilot" (Johnsonville and Newlands) or "full" (the four
# territorial authorities). Must match the runs of the shaking hazard and the
# wall population this reads.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which exposure worlds to read the wall population of. A world is one draw of
# which candidate lines carry a wall; the earthquake does not decide it.
WORLD_IDS = [0]

# Which modelled earthquakes to draw damage states for. The same id in the
# shaking, liquefaction and landslide layers is the same earthquake.
REALISATION_IDS = [0]
