"""Run settings for the address spine step.

Everything that changes between one run of this step and the next, in one short
file. `s1_build_address_spine.py` takes these as arguments and holds no defaults
of its own, so what a run did can be established by reading this file and the
git history of it, rather than by remembering which flags were typed.
"""

# The extent to run over: "full" for the four territorial authorities, or a
# name from landloss.io.area_of_interest.EXTENTS ("wlg-pilot" for the small
# Wellington pilot box, "wlg-earthworks-pilot" for Johnsonville and Newlands).
# The pilot is the quick way to exercise the script end to end; the full read
# is a national 800 MB export that LINZ takes many minutes to build.
# Name outputs with extent_suffix(EXTENT); see landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to ignore the extent cache and re-read from the LINZ source layer.
FRESH = False

# Where to write the spine. None writes temp/exposure/address-spine.geoparquet,
# or address-spine-pilot.geoparquet when EXTENT is "wlg-pilot" (the name carries
# extent_suffix(EXTENT)), so a run over one extent cannot overwrite another's.
OUT = None
