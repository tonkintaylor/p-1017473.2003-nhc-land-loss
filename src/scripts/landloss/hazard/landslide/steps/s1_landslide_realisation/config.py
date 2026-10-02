"""Run settings for the landslide realisation step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the
git history of it, rather than by remembering which flags were typed.

Both `s1_simulate_landslides.py` and `fig_landslide_realisation.py` read from
here, which is what keeps the figure drawing the realisation the simulation
actually wrote. The placement settings are the contract's (section 3.9 of
`.agents/plans/urban-slope-build-contract.md`).
"""

# The extent to run over: "full" for the four territorial authorities, or a name
# from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" is the small Wellington
# pilot box). Steps 3 and 5 must have been run over the same extent: this step
# reads their 10 m rasters and slope units and fetches nothing.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which modelled earthquakes to draw. A realisation id is the whole event: the
# same id in the shaking, liquefaction and landslide layers is the same
# earthquake, which is what lets a property's causes be summed. The seed itself
# is project-wide -- landloss.domain.constants.BASE_SEED -- and this step does
# not carry one of its own, because two hazards seeded separately could not be
# paired.
REALISATION_IDS = [0]

# The smallest source a large-model failure can have, in square metres: the top
# of the urban size range (plan section 10.3). Failures below it belong to the
# urban model, landslide steps 6 to 9, and are not drawn here.
LARGE_MIN_SOURCE_AREA_M2 = 700.0

# The share of the calibration inventory's failed area that lies inside the
# urban size range, taken off the expected failed area before the large count
# is drawn so the two populations do not both claim it. A placeholder: a
# research script measures it from the Kaikoura source polygons
# (landloss.io.kaikoura) later. Printed by every run.
URBAN_AREA_SHARE = 0.25

# The downslope length of a source ellipse over its across-slope width. A
# placeholder for the ratio measured on the Kaikoura source polygons.
SOURCE_ASPECT_RATIO = 2.0

# How much the 100 m topographic position lifts a cell's seeding weight: a
# cell standing 10 m or more above its surroundings is weighted
# (1 + CREST_WEIGHT) times its probability, because earthquake sources favour
# crests and spurs.
CREST_WEIGHT = 0.5
