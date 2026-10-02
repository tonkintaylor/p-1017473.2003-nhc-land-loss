"""Run settings for the retaining wall landslide damage step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.
"""

# Whether to run over the small Wellington pilot box. Must match the runs of
# every step this reads: the wall population, the combined landslide
# realisation and the urban wall outcomes.
PILOT = True

# Which exposure worlds to flag walls for. A world is one draw of the wall
# population; the wall outcomes and the combined realisation are written per
# world and earthquake.
WORLD_IDS = [0]

# Which modelled earthquakes to flag walls for.
REALISATION_IDS = [0]
