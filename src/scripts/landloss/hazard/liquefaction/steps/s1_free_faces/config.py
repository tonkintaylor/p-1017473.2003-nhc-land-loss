"""Run settings for the free-face step.

Everything that changes between one run of this step and the next, in one short
file, read at the bottom of ``gen_liq_free_faces.py`` and passed into its
``main``. What a run did can then be read off this file and its git history.
"""

# The extent to run over: "full" for the four territorial authorities, a name
# from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small Wellington
# pilot box), or "lower-hutt" for the lower Hutt Valley pilot box, which only
# this step runs over -- for checking the layer, since the small pilot box holds
# no waterways, only coast. Step 2 reads the free faces for its own EXTENT, and
# gen_hazard.py passes the same extent to both.
EXTENT = "wlg-pilot"
