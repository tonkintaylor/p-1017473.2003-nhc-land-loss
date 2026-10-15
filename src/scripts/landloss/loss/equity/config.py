"""Run settings for the loss module's equity figures.

Everything that changes between one run of these scripts and the next, in one
short file. The scripts beside it take these as arguments and hold no defaults
of their own.
"""

# The extents whose settlements are pooled, each a name from
# landloss.io.area_of_interest.EXTENTS. Loss step 1 must have been run over each.
EXTENTS = ["wellington-city", "lower-hutt", "porirua", "upper-hutt"]

# The exposure world and modelled earthquake the settlements are read for.
WORLD_ID = 0
REALISATION_ID = 0

# The capital value bands claims are grouped in, per dwelling, indexed to the
# common valuation date: the upper edge of each band but the last, in dollars.
# Round figures rather than quantiles, so a band reads as a kind of house; the
# study's median is about $830,000 a dwelling.
CV_BAND_EDGES_NZD = [500_000, 750_000, 1_000_000, 1_500_000]

# The fixed land cap the Act's cover is compared against, excluding GST: it
# replaces the land cover cap -- land value and the sub-caps -- so a claim is
# paid its repair cost up to it, less the excess. The loss viewer's "replace"
# mode, per dwelling. The settlement, coverage, unpaid and limits figures are drawn
# against it.
FIXED_CAP_NZD = 100_000.0

# The fixed land caps NHC is weighing (set 2026-10-09, as the loss viewer's),
# lowest first, all drawn side by side in the scenarios figure. At most four:
# the figure's ramp has four steps.
CAP_SCENARIOS_NZD = [30_000.0, 65_000.0, 100_000.0, 150_000.0]
