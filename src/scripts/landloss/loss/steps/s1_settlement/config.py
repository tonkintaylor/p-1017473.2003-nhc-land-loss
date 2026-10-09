"""Run settings for the settlement.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

The policy settings are not here, for the reason given in the module-level
`config.py`: a scenario is a value, so comparing two of them is a loop rather
than an edit to this file.
"""

# The extent to run over: "full", or a name from
# landloss.io.area_of_interest.EXTENTS. Must match the run of step 0, whose caps
# this checks itself against.
EXTENT = "wlg-pilot"

# Which exposure worlds to settle, each a draw of the wall population.
WORLD_IDS = [0]

# Which modelled earthquakes to settle.
REALISATION_IDS = [0]
