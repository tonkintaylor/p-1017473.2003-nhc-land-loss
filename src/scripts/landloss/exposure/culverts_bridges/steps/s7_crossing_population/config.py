"""Run settings for the culvert and bridge crossing step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

The 80/20 split between a culvert and a bridge is not here. It is engineering
judgement about the world rather than a setting of a run, so it lives with the
code that applies it, as
`landloss.exposure.culverts_bridges.crossings.CULVERT_PROBABILITY`.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Must match the run of step 5 whose driveways and insured land this reads:
# the crossings are detected against those accessways and kept only where they
# lie wholly inside that insured land.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Which modelled earthquakes to draw a population for. Which structure sits at a
# crossing is a draw, so the population is tied to a realisation the same way the
# hazards are.
REALISATION_IDS = [0]

# Whether to reuse the already-clipped river layers for this extent. Set False to
# clip them again from the downloaded layers.
USE_CACHED_EXTENT = True
