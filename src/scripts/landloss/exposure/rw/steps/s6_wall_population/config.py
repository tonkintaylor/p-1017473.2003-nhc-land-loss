"""Run settings for the retaining wall population step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

The prevalence, height and length numbers are not here. They are the beta
stand-in for a model that does not exist yet rather than settings of a run, so
they live with the code that applies them, in
`landloss.exposure.rw.beta_population` and `landloss.exposure.rw.wall_probability`.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Must match the run of step 5 whose insured land this
# reads: the wall population is drawn over those properties.
PILOT = True

# Which modelled earthquakes to draw a population for. Walls do not move between
# realisations, but which properties carry one is a draw, so the population is
# tied to a realisation the same way the hazards are. Read by
# gen_wall_population.py.
REALISATION_IDS = [0]

# Whether to reuse an already-fetched elevation model for this extent. Set False
# to fetch it again. Read by gen_wall_probability.py.
USE_CACHED_DEM = True

# Whether to reuse the already-clipped GNS SLIDE and NLM layers for this extent.
# Set False to fetch them again. Read by gen_wall_probability.py.
USE_CACHED_LAYERS = True
