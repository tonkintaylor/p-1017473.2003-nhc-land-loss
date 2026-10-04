"""Run settings for the crossing landslide damage step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.
"""

# The extent to run over: "wlg-pilot" (the small Wellington pilot box),
# "wlg-earthworks-pilot" (Johnsonville and Newlands) or "full" (the four
# territorial authorities). Must match the runs of the landslide hazard and the
# crossing population this reads.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which exposure worlds to flag for. The combined realisation is written per
# world and earthquake; the crossing population is not drawn per world.
WORLD_IDS = [0]

# Which modelled earthquakes to flag. The crossing population is drawn per
# realisation, so each one is read against its own landslides.
REALISATION_IDS = [0]
