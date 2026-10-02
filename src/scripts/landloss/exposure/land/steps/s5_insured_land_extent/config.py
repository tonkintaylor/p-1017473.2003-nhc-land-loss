"""Run settings for the insured land extent step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

Both `gen_insured_land.py` and `fig_insured_land.py` read from here, which is
what keeps the figure drawing the extent the generation actually wrote.

The 8 metre buffer is not here. It is NHC's own definition of insured land
rather than a setting of this run, so it lives with the code that applies it, as
`landloss.exposure.land.extent.INSURED_LAND_BUFFER_M`.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Leave this on "wlg-pilot" while the model is being changed: the building
# outline layer is 3.2 million polygons nationally, and the first run over a new
# extent downloads and clips it.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse the already-clipped building outlines for this extent. Set
# False to clip them again from the downloaded layer.
USE_CACHED_EXTENT = True

# How wide the close-up panel of `fig_insured_land.py` is, in metres. Wide
# enough to hold a handful of neighbouring properties, narrow enough that the
# 8 metre line around each building is still a readable distance.
CLOSE_UP_M = 120.0
