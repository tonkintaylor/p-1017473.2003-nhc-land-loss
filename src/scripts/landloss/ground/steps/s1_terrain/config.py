"""Run settings for ground step 1, the terrain (multiscale slope and derivatives).

Everything that changes between one run of this step and the next, in one short
file. `gen_multiscale_slope.py` and `gen_terrain_derivatives.py` take these as
arguments and hold no defaults of their own, so what a run did can be
established by reading this file and the git history of it rather than by
remembering which flags were typed.
"""

# The extent to run over: "full" for the four territorial authorities, or a name
# from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" is the small Wellington
# pilot box). The pilot fetch at 1 m takes a few minutes; the full study area is
# 59 by 54 km and cannot be carried at 1 m in memory, which the implementation
# plan records.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# The cell sizes to build a DEM, a slope and an aspect at, in metres. The finest
# is fetched from LINZ and every other one is block-averaged from it, so each
# has to be a whole multiple of the finest. Ground step 3 reads the 1 m DEM,
# landslide step 1 (the slope units) and step 3 (the large model) the 10 m, the QGIS projects 3 m, and the cut and
# fill residual the 30 and 100 m surfaces.
RESOLUTIONS_M = (1, 3, 10, 30, 50, 100)

# The cell sizes a slope and an aspect are built at as well, from RESOLUTIONS_M.
# Nothing in the pipeline reads the 1 m or 3 m slope or aspect (ground step 3
# finds its own slopes on the 1 m DEM, and the landslide steps read 10 m), and
# over a territorial authority the two at 1 m alone are about 9 GB, so they are
# left out (the lead, 2026-10-09). fig_multiscale_slope.py draws every cell size
# in RESOLUTIONS_M and stops with a message if one is missing: add 1 and 3 here
# and rerun gen_multiscale_slope.py to draw it.
SLOPE_RESOLUTIONS_M = (10, 30, 50, 100)

# Whether to reuse an already-fetched elevation model for this extent. Set False
# to fetch it again. Read by `gen_multiscale_slope.py` only.
USE_CACHED_DEM = True

# The smoothed surfaces the 1 m DEM is differenced against for the cut and fill
# residual, as cell sizes from RESOLUTIONS_M.
RESIDUAL_BASE_RESOLUTIONS_M = (30, 100)

# The topographic position windows, in metres, each mapped to the DEM cell size
# it is computed on, so a 100 m window is 11 cells rather than 101.
TOPOGRAPHIC_POSITION_WINDOWS_M = {100.0: 10}
