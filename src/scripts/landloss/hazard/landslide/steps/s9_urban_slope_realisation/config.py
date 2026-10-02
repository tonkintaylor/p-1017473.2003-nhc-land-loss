"""Run settings for the urban slope realisation step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history.

The seed is not here. The draw is seeded from
`landloss.domain.constants.BASE_SEED` with the earthquake id, the `"urban"`
stream and the world id (`landloss.hazard.realisation.realisation_seed`), so a
pair of ids reproduces exactly and no step carries a seed of its own.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Step 8, shaking step 5, step 1 and the wall
# population must have been run over the same extent.
PILOT = True

# Which exposure worlds to draw for. A world is one draw of the wall population
# (`exposure/rw/steps/s6_wall_population/gen_wall_population.py`), and step 8's
# model file for that world is what this step reads.
WORLD_IDS = [0]

# Which modelled earthquakes to draw. A realisation id is the whole event: the
# same id in the shaking, liquefaction and landslide layers is the same
# earthquake, so the urban failures of earthquake 3 shake under the PGV field
# and beside the large landslides of earthquake 3.
REALISATION_IDS = [0]
