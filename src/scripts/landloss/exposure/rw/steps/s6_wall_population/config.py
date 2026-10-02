"""Run settings for the retaining wall population step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

The probabilities are not here. They are judgement standing in for the claim
report extraction rather than settings of a run, so they live with the code
that applies them, in `landloss.exposure.rw.wall_probability`.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Must match the run of landslide steps 3, 4 and 6
# whose rasters, ground map and candidates gen_wall_lines.py reads, and the
# run of step 5 whose insured land gen_wall_population.py filters on.
PILOT = True

# Which exposure worlds to draw a population for. A world is one draw of which
# candidate lines are walls, seeded on EXPOSURE_BASE_SEED and the world id and
# not on any earthquake, so a few worlds pair with many hazard realisations.
# Read by gen_wall_population.py.
WORLD_IDS = [0]

# Whether to reuse the already-clipped GNS SLIDE and LINZ layers for this
# extent. Set False to fetch them again. Read by gen_wall_lines.py only:
# gen_wall_probability.py reads the lines it wrote and fetches nothing.
USE_CACHED_LAYERS = True

# How near a road centreline a property boundary piece has to lie to count as
# a road frontage rather than a boundary between neighbours. Read by
# gen_wall_lines.py.
ROAD_FRONTAGE_DISTANCE_M = 5.0
