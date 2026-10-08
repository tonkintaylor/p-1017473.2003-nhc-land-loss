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

# How a building outline is judged a dwelling, which is what the 8 m insured
# land is buffered off.
#
# - "qv" (the default, Maxim Millen 2026-10-08): by what the QV rating roll says
#   the property it stands on is used for, whatever the building's size, so an
#   apartment block is a dwelling and a corner shop is not
#   (landloss.exposure.land.residential_use). Reads the roll from T:.
# - "footprint": the earlier rule, which needs nothing from T: -- any outline
#   LINZ has not named as a school, hospital or supermarket, up to 500 m2
#   (landloss.exposure.land.extent.drop_non_residential_buildings).
#
# Buildings LINZ names are dropped under both, and under "qv" a property the
# roll does not hold falls back on the footprint.
RESIDENTIAL_RULE = "qv"

# The largest footprint, in m2, the footprint rule takes a building to be a
# dwelling at: the whole of the "footprint" rule's size test, and the fallback
# under "qv" for land the roll does not decide. Over the pilot the outlines run
# to a median of 120 m2 and a 95th percentile of 290, so 500 sits well clear of
# a large house; over the study area 3,507 unnamed outlines exceed it, 458 of
# them on a property with two or more unit addresses, which are likely flats.
# Judgement, not a line NHC draws. (Library default:
# landloss.exposure.land.extent.MAX_DWELLING_FOOTPRINT_M2.)
MAX_DWELLING_FOOTPRINT_M2 = 500.0

# What counts as a building properly straddling a property boundary, and so
# split between the properties, rather than the outline and boundary layers
# disagreeing along a shared edge. Both have to be passed: an area in m2, so a
# small shed is not split by a large relative overhang, and a share, so a large
# building is not split by a small absolute one. (Library defaults:
# landloss.exposure.land.extent.MIN_CROSSING_AREA_M2 and MIN_CROSSING_SHARE.)
MIN_CROSSING_AREA_M2 = 5.0
MIN_CROSSING_SHARE = 0.10

# Half the width of the driveway corridor routed from the building to the
# road, in metres: a 3 m single-lane residential drive. (Library default:
# landloss.exposure.land.driveways.DRIVEWAY_HALF_WIDTH_M.)
DRIVEWAY_HALF_WIDTH_M = 1.5

# The longest straight-line route to a road, in metres, taken as a driveway; a
# building further from any road gets none. (Library default:
# landloss.exposure.land.driveways.MAX_DRIVEWAY_LENGTH_M.) The 60 m of it that
# is insured is NHC's own definition and stays in the code with the 8 m buffer.
MAX_DRIVEWAY_LENGTH_M = 300.0

# How far past the addresses' own bounding box the LINZ layers are read, in
# metres, so a property or a building belonging to an address just inside the
# box is still in the read. A property boundary is the widest of the three, and
# a rural rating unit can run a long way back from the address point on it.
FETCH_MARGIN_M = 500.0

# How wide the close-up panel of `fig_insured_land.py` is, in metres. Wide
# enough to hold a handful of neighbouring properties, narrow enough that the
# 8 metre line around each building is still a readable distance.
CLOSE_UP_M = 120.0
