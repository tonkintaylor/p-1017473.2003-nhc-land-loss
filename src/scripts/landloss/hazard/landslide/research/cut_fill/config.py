"""Run settings for the pif cut and fill research scripts.

Everything that changes between one run of ``gen_pif_cut_fill.py`` or
``fig_pif_cross_sections.py`` and the next, in one short file. The scripts take
these as arguments and hold no defaults of their own.
"""

# The extent the pifs come from: the one landslide step 12 was last run over.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ and GNS layers.
USE_CACHED_LAYERS = True

# ---------------------------------------------------------------------------
# The natural ground surface, two ways
# ---------------------------------------------------------------------------

# The rolling mean: the 1 m DEM averaged over a square window this many metres
# a side. Wider than a house platform and its batter, so a single terrace is
# averaged out, and narrow enough to follow the hill.
ROLLING_WINDOW_M = 30.0

# The local polynomial: a quadratic surface fitted, by least squares, to every
# DEM cell within this many metres of any of the pif's points.
FIT_RADIUS_M = 15.0

# ---------------------------------------------------------------------------
# The face of each pif and its class
# ---------------------------------------------------------------------------

# The foot of the face below each pip: the walk down the pip's fall direction
# stops at the first step flatter than this, or after FOOT_MAX_M.
FOOT_SLOPE_DEG = 20.0
FOOT_MAX_M = 15.0

# A pif whose drop, crest to foot, is no more than this many metres larger than
# the natural surface's drop over the same points is natural ground.
EXCESS_DROP_M = 1.0

# Where the excess drop sits against the natural surface, from -1 (all below
# it: cut) to +1 (all above it: fill). Beyond plus or minus this the pif is a
# fill or a cut; between, it straddles the natural surface and is cut and fill.
POSITION_SPLIT = 1.0 / 3.0

# ---------------------------------------------------------------------------
# The cross-section figure
# ---------------------------------------------------------------------------

# The pif the sections were set up around; its pips are drawn in their own colour.
SECTION_PIF_ID = 8220

# Each section's centre (NZTM) and bearing, in degrees from north, pointing
# downhill; uphill is on the left of each section. Section 1 crosses the north
# end of 8220, 20 m north of where it first sat; section 2 the middle of 8220;
# section 3 runs east-west 18 m south of 8220's southern end, across the faces
# that run north-south there.
SECTIONS = (
    {"x": 1749923.5, "y": 5424063.5, "bearing_deg": 60.0},
    {"x": 1749934.5, "y": 5424024.5, "bearing_deg": 112.0},
    {"x": 1749933.5, "y": 5424000.0, "bearing_deg": 90.0},
)

# The length of each section, in metres, centred on its centre.
SECTION_LENGTH_M = 100.0

# A pip within this many metres of a section line is drawn on it.
SECTION_PIP_BUFFER_M = 1.0

# The method whose class colours the pips ("rolling" or "poly"); the labels
# carry both.
FIGURE_CLASS_METHOD = "rolling"
