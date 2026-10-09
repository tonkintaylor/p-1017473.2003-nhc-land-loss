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

# A 30 m cut-and-fill residual beyond this magnitude, in metres, marks the
# ground as cut (negative) or fill (positive) where no mapping reaches.
RESIDUAL_MODIFICATION_THRESHOLD_M = 1.0
