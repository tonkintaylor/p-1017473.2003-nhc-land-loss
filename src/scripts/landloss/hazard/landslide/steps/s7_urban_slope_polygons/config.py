"""Run settings for the urban slope polygons step.

Everything that changes between one run of this step and the next, in one short
file. `gen_urban_slope_polygons.py` and `fig_urban_slope_polygons.py` take these
as arguments and hold no defaults of their own, so what a run did can be
established by reading this file and the git history of it rather than by
remembering which flags were typed.
"""

# Whether to run over the small Wellington pilot box rather than the four
# territorial authorities. Leave this True while the model is being changed.
PILOT = True

# Whether to reuse the cached LINZ building outlines and road centrelines for
# this extent. Set False to fetch them again.
USE_CACHED_LAYERS = True

# Half the width of a road, in metres: the road centreline is buffered by this
# to make the runout barrier a failure's debris stops at.
ROAD_HALF_WIDTH_M = 5.0
