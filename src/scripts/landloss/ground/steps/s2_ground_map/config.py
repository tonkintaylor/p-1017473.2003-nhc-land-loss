"""Run settings for ground step 2, the ground map.

Everything that changes between one run of this step and the next, in one short
file. ``gen_ground_map.py`` and ``fig_ground_map.py`` take these as arguments
and hold no defaults of their own, so what a run did can be established by
reading this file and the git history of it rather than by remembering which
flags were typed.
"""

# The extent to run over: "full" for the four territorial authorities, or a name
# from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" is the small Wellington
# pilot box).
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse the on-disk cache of every polygon layer read. Set False to
# fetch them again.
USE_CACHED_LAYERS = True

# The depth to groundwater assumed off the NLM groundwater model's flat-land
# footprint, in metres below ground: the same value landslide step 7 assumes there, which
# puts hill country in the well drained class.
DEFAULT_GROUNDWATER_DEPTH_M = 4.0

# The tolerance, in metres, the groundwater class polygons are simplified to as
# a coverage (shapely.coverage_simplify, so a shared edge stays shared; D8). The
# NLM grid is 100 m, so the class edges are staircases of 100 m steps whose
# corners sit at least 70 m off any chord; 10 m therefore removes next to
# nothing there, and is kept so the groundwater polygons are cut the same way
# as the residual's. Not the residual's tolerance, because that grid is 10 m.
GROUNDWATER_SIMPLIFY_M = 10.0

# A 30 m cut-and-fill residual beyond this magnitude, in metres, marks the
# ground as cut (negative) or fill (positive) where no mapping reaches.
RESIDUAL_MODIFICATION_THRESHOLD_M = 1.0

# The cell, in metres, the 30 m residual is averaged to and classed on. The
# residual is the 1 m DEM less a 30 m smoothed surface, so it cannot carry
# detail much finer than that surface does; 10 m, a third of the smoothing,
# keeps what it supports. The residual is read already averaged to this cell,
# so the 1 m grid, a billion cells over Upper Hutt, is never held in memory
# (reworking-the-ground-map-polygons.md, D2). A whole multiple of the 1 m grid.
RESIDUAL_CLASS_CELL_M = 10.0

# The smallest cut or fill patch the residual keeps, in square metres: one 30 m
# cell of the smoothed surface, 900 m2 (nine classing cells), which is the area
# the residual cannot resolve. A smaller patch is sieved to the class of its
# largest neighbour, which is not always natural (D7). The lead agreed 900 m2 on
# 2026-10-10 as the start; a sweep of 100, 900 and 2,500 m2 follows for the
# record (D3).
RESIDUAL_MIN_PATCH_M2 = 900.0

# The tolerance, in metres, the residual patches are simplified to as a coverage
# (shapely.coverage_simplify, so a shared edge stays shared; D8). One classing
# cell, 10 m: it takes the 10 m staircase off an outline and moves an edge by
# under a cell, where 30 m would move a boundary across a building. The lead
# agreed 10 m on 2026-10-10, pending the same sweep against 5 m (D3).
RESIDUAL_SIMPLIFY_M = 10.0

# The most cells one strip of the fill thickness pass holds. The 100 m residual
# is a 1 m grid written in one-row strips, so a strip is the raster's full width
# and as many whole rows as fit, which reads each row once; 25 million cells is
# 100 MB as float32, and holds memory to that however large the extent.
THICKNESS_STRIP_CELLS = 25_000_000
