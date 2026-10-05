"""Run settings for the pif cut and fill step.

Everything that changes between one run of this step and the next, in one short
file. `gen_pif_cut_fill.py` and `table_pif_cut_fill_checks.py` take these as
arguments and hold no defaults of their own. The method's thresholds are fixed
in `landloss.hazard.landslide.pif_cut_fill`, not here.
"""

# The extent to run over: the one landslide step 12 was last run over, since
# this step classes its pifs. Name outputs with extent_suffix(EXTENT); see
# landloss.io.area_of_interest.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ coastline and GNS layers for this extent.
USE_CACHED_LAYERS = True

# The checks report the pifs of at least this many pips on their own as well,
# as one- or two-pip pifs are mostly noise on the class.
CHECK_MIN_PIPS = 10
