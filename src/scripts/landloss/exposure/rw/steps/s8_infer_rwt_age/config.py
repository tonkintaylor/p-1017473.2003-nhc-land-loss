"""Run settings for the retaining wall age step.

Everything that changes between one run of this step and the next, in one short
file. The scripts beside it take these as arguments and hold no defaults of
their own.

The dating rules are not here. They were set against Christchurch rather than
chosen per run, so they live with the code that applies them, in
`landloss.exposure.rw.age`.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# Must match the run of exposure step 3 whose claim properties and address
# mapping gen_rwt_age.py reads. "full", because the per-suburb table this step
# exists for is wanted over the whole study area.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "full"

# Whether to reuse the already-clipped LINZ property boundaries for this
# extent. Set False to fetch them again. Read by gen_rwt_age.py, and by the
# Christchurch validation for its own extent.
USE_CACHED_EXTENT = True
