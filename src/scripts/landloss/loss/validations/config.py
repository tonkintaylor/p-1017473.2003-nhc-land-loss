"""Run settings for the loss module's validations.

Everything that changes between one run of these scripts and the next, in one
short file. The scripts beside it take these as arguments and hold no defaults
of their own, so what a run did can be established by reading this file and the
git history of it, rather than by remembering which flags were typed.
"""

# The extent the QV land value tier factors are drawn over, a name from
# landloss.io.area_of_interest.EXTENTS or "full". Exposure step 5 must have been
# run over it since 2026-10-11, so its insured land carries the footprint area.
QV_TIER_EXTENT = "wlg-pilot"

# The fewest claim properties a suburb needs for its median factor to be shown,
# so no suburb's figure stands for a handful of roll records.
QV_TIER_MIN_SUBURB_PROPERTIES = 20

# Whether to write the per-property layer as well as the suburb one. It carries
# rates derived from each property's own QV land value, which is close to the
# roll re-tabulated, so it stays under temp/ and is not shared.
QV_TIER_WRITE_PROPERTY_LAYER = True

# Whether to write the tier layer: each claim property cut into its footprint,
# the rest of its insured land and its uninsured remainder, each with the QV
# rate per m2 it is valued at. Derived from each property's QV land value, so
# sensitive, like the property layer. Reads the LINZ property boundaries from
# exposure step 5's cache.
QV_TIER_WRITE_TIER_LAYER = True

# The extents the average QV land rate histograms are drawn over, one per
# territorial authority, and how the figures name them.
QV_RATE_EXTENTS = ["wellington-city", "lower-hutt", "porirua", "upper-hutt"]
QV_RATE_EXTENT_NAMES = ["Wellington City", "Lower Hutt", "Porirua", "Upper Hutt"]

# The rates the histograms span, $/m2 before GST, the same for every rate so
# they compare; a property beyond is counted in the end bin, so no lone
# property's rate can be read off a figure.
QV_RATE_RANGE_NZD_PER_M2 = (10.0, 20_000.0)

# The property area bands the third histogram is stacked by, in m2. The last
# is the Act's 4,000 m2 minimum-sized site.
QV_RATE_AREA_BANDS_M2 = [500, 800, 1_500, 4_000]

# The correction factors the tier factor histograms span; a property beyond is
# counted in the end bin.
QV_FACTOR_RANGE = (0.9, 100.0)
