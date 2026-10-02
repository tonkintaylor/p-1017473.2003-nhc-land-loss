"""Run settings for the dwellings per property step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Must match the run of the land value step this reads its addresses from.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse already-fetched LINZ layers for this extent.
USE_CACHED_EXTENT = True
