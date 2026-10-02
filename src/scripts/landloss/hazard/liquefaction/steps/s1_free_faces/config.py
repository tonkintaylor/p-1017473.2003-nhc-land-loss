"""Run settings for the free-face step.

Everything that changes between one run of this step and the next, in one short
file, read at the bottom of ``gen_liq_free_faces.py`` and passed into its
``main``. What a run did can then be read off this file and its git history.
"""

# The extent to run over: "lower hutt" for the lower Hutt Valley pilot box,
# "pilot" for the small Wellington pilot box, or "study" for the four
# territorial authorities. The lower Hutt is the default while the layer is
# being checked: the small pilot box holds almost no waterways.
EXTENT = "lower hutt"
