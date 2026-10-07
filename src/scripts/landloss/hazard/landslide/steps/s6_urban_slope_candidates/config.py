"""Run settings for the urban slope candidate step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own, so what a run did can be established by reading this file and its git
history.

The slope bands, the aspect octants and the snap tolerance are fixed by the
method rather than by a run, so they live in
`landloss.hazard.landslide.urban.delineation` (contract section 10).
"""

from landloss.domain import constants

# The extent to run over: "wlg-pilot" for the small Wellington pilot box,
# "wlg-earthworks-pilot" for the Johnsonville and Newlands box, or "full" for
# the four territorial authorities.
# Steps 3 and 4 must have been run over the same extent.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse the cached building outlines, roads and property boundaries
# for this extent. Set False to fetch them again.
USE_CACHED_LAYERS = True

# The cell sizes the candidates are delineated at, in metres. Taken from the
# constants rather than retyped, so this step and the nesting downstream agree.
SCALES_M = constants.URBAN_SCALES_M

# How far from a building outline the urban domain reaches, in metres.
BUILDING_DISTANCE_M = constants.URBAN_BUILDING_DISTANCE_M

# The smallest patch kept as it is, in cells, at every scale: a 3 by 3 block,
# so 9, 81, 900 and 8,100 square metres across the four scales. A patch under
# this joins the neighbour it shares the most cell edges with. This is the one
# definition of the minimum patch; the library takes it as an argument.
MIN_PATCH_CELLS = 9

# The longest a patch may run along the contour before it is cut into equal
# pieces, in metres: the mean GNS SLIDE wall segment length, 280 km over 11,288
# segments. To be replaced by failure widths from the rainfall inventory when
# it is supplied.
MAX_PATCH_LENGTH_M = 25.0

# A scale whose slope grid holds more cells than this is delineated tile by
# tile (landloss.common.utils.tiles) rather than whole, so a territorial
# authority's 1 m grid does not exhaust memory. 50 million cells is about
# 7 by 7 km at 1 m: every pilot box runs whole, as it always has, and over
# Porirua only the 1 m scale is tiled.
MAX_UNTILED_CELLS = 50_000_000

# The side of a tile's core, in metres.
TILE_CORE_M = 3_000.0

# The width read around each core, in metres. It has to be wider than the
# largest candidate, so that a candidate is seen whole by the tile that owns
# it: the largest 1 m candidate on the two pilot boxes is 231 m across.
TILE_MARGIN_M = 300.0
