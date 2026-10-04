"""Run settings for the free-face step.

Everything that changes between one run of this step and the next, in one short
file, read at the bottom of ``gen_liq_free_faces.py`` and passed into its
``main``. What a run did can then be read off this file and its git history.
"""

# The extent to run over: "pilot" for the small Wellington pilot box, "study"
# for the four territorial authorities, or "lower hutt" for the lower Hutt Valley
# pilot box, which only this step runs over -- for checking the layer, since the
# small pilot box holds no waterways, only coast. Step 2 reads "pilot" or
# "study" to match its own PILOT, and gen_hazard.py passes that itself.
EXTENT = "pilot"
