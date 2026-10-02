"""Run settings for the multiscale slope step.

Everything that changes between one run of this step and the next, in one short
file. `gen_multiscale_slope.py` and `gen_terrain_derivatives.py` take these as
arguments and hold no defaults of their own, so what a run did can be
established by reading this file and the git history of it rather than by
remembering which flags were typed.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. The pilot fetch at 1 m takes a few minutes; the full
# study area is 59 by 54 km and cannot be carried at 1 m in memory, which the
# implementation plan records.
PILOT = True

# The cell sizes to build a DEM, a slope and an aspect at, in metres. The finest
# is fetched from LINZ and every other one is block-averaged from it, so each
# has to be a whole multiple of the finest. The urban failure candidates are
# delineated at 1, 3, 10 and 30 m (`constants.URBAN_SCALES_M`); 100 m stays
# because the cut and fill residual reads the 100 m surface.
RESOLUTIONS_M = (1, 3, 10, 30, 50, 100)

# Whether to reuse an already-fetched elevation model for this extent. Set False
# to fetch it again. Read by `gen_multiscale_slope.py` only.
USE_CACHED_DEM = True

# Whether to reuse an already-fetched surface model for this extent. Read by
# `gen_terrain_derivatives.py`, which reads the DEMs the script above wrote and
# fetches only the DSM.
USE_CACHED_DSM = True

# The windows, in metres, the face height (local relief on the 1 m DEM) is
# measured over: one for a single wall or cutting, one for a taller face.
FACE_HEIGHT_WINDOWS_M = (5.0, 10.0)

# The smoothed surfaces the 1 m DEM is differenced against for the cut and fill
# residual, as cell sizes from RESOLUTIONS_M.
RESIDUAL_BASE_RESOLUTIONS_M = (30, 100)

# The topographic position windows, in metres, each mapped to the DEM cell size
# it is computed on, so a 100 m window is 11 cells rather than 101.
TOPOGRAPHIC_POSITION_WINDOWS_M = {20.0: 3, 100.0: 10}

# The cell size the profile curvature is computed on. Not 1 m: curvature on the
# raw LiDAR grid is survey noise.
CURVATURE_RESOLUTION_M = 3
