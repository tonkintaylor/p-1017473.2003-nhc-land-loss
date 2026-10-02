"""Run settings for the land value step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and the git
history of it, rather than by remembering which flags were typed.

`s1_build_terrain_attributes.py`, `s2_build_accessibility.py`,
`s3_build_amenity.py`, `s4_estimate_land_value.py` and `fig_town_centres.py`
read from here. Sharing
`EXTENT`, `TERRAIN` and `ACCESSIBILITY` is what keeps the valuation reading the
attributes the earlier scripts actually wrote.

Every path below is None by default, which means the standard location under
temp/exposure/, with the extent_suffix(EXTENT) suffix (`-pilot` for
"wlg-pilot") so a run over one extent cannot overwrite another's outputs.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Leave this on "wlg-pilot" while the model is being changed: the DEM for the
# full study area is a long background job measured in tens of minutes, while
# the pilot finishes in a couple of them.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to ignore the caches and re-fetch the DEM, the flatland layer and, if
# it has to be rebuilt, the address spine.
FRESH = False

# The address spine from step 1. None reads temp/exposure/address-spine.geoparquet.
# Rebuilt from LINZ if it is not there.
SPINE = None

# The terrain attributes: where s1 writes them and where s4 reads them. None is
# temp/exposure/terrain-by-address.geoparquet. If the file is not there, s4
# falls back to valuing on landform class alone.
TERRAIN = None

# The accessibility attributes: where s2 writes them and where s4 and
# fig_town_centres.py read them. None is
# temp/exposure/accessibility-by-address.geoparquet. If the file is not there,
# s4 values without the accessibility modifier.
ACCESSIBILITY = None

# The amenity attributes: where s3 writes them and where s4 reads them. None is
# temp/exposure/amenity-by-address.geoparquet. If the file is not there, s4
# values without the sea view modifier.
AMENITY = None

# Where s4 writes the valued addresses. None is
# temp/exposure/land-value-by-address.geoparquet.
LAND_VALUE_OUT = None

# Where s4 writes the per-suburb cohort table. None is
# temp/exposure/land-value-by-suburb.csv.
COHORTS_OUT = None

# Override for the topographic position neighbourhood width s1 uses, in metres.
# None takes the topographic_position_window_m row of the land value factors
# asset. The elevated flat threshold in that same asset only means anything
# against the window it was tuned at, so an override here is for looking rather
# than for producing an input to the valuation.
WINDOW_M = None
