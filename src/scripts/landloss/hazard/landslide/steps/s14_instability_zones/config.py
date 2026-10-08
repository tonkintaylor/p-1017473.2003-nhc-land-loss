"""Run settings for landslide step 14, the instability zones.

The pif cutting rules (bends, stray, turning, shortest piece) and the wall
height read off each pif are the walls' rules too, so they stay in step 12's
config.py and are read from there; what is here is particular to this step.
"""

# The extent to run over: a name from landloss.io.area_of_interest.EXTENTS
# ("wlg-pilot" for the small Wellington pilot box), or "full". Steps 3 and 4
# must have been run over the same extent. gen_hazard.py passes its own extent.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ building outlines and coastline for this
# extent. Set False to fetch them again (and set REBUILD, since the step does
# not see that the layers changed).
USE_CACHED_LAYERS = True

# Whether to search the DEM again even when the last run's record matches: the
# settings, the 1 m DEM and the ground map, and the code that does the search.
# Leave False; the step skips itself in seconds when nothing has changed.
REBUILD = False

# A 1 m DEM holding more cells than this is searched tile by tile (step 12's
# tiled.py) rather than whole: 50 million cells is about 7 by 7 km at 1 m, so
# every pilot runs whole, and over Porirua the whole grid would need about
# 95 GB.
MAX_UNTILED_CELLS = 50_000_000

# The side of a tile's core, in metres.
TILE_CORE_M = 3_000.0

# The width read around each core, in metres. It has to be wider than the
# longest parent pif, so that the tile owning a pif sees it whole: the longest
# on the two pilots spans 636 m. Since 2026-10-08 the siz test is made on each
# piece (at most 50 m) with fall lines of at most 30 m, so the margin can come
# down once the tiles own pieces rather than parents (the plan, phase 2).
TILE_MARGIN_M = 750.0
