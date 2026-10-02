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

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Steps 3 and 4 must have been run over the same extent.
PILOT = True

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
