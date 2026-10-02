"""Run settings for the four tables vul hands to loss.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

Nothing here selects a cost or a fragility. This step assembles what the earlier
vul steps already decided and adds no modelling of its own, so the only settings
are which run to assemble. They must match the runs of every step this reads:
exposure steps 5 and 6, vul steps 2 and 3, both step 9 shaking steps and both
step 11 landslide steps (retaining walls, and culverts and bridges).
"""

# Whether to run over the small Wellington pilot box. Must match the runs of
# every step this reads.
PILOT = True

# Which exposure worlds to assemble. The wall population, the wall damage
# states, the landslide land damage and both landslide flag files are read per
# world; the liquefaction and structure files are per earthquake only.
WORLD_IDS = [0]

# Which modelled earthquakes to assemble.
REALISATION_IDS = [0]
