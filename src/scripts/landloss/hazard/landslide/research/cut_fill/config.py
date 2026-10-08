"""Run settings for the pif cut and fill research scripts.

Everything that changes between one run of ``gen_pif_cut_fill.py`` or
``fig_pif_cross_sections.py`` and the next, in one short file. The scripts take
these as arguments and hold no defaults of their own.
"""

# The extent the pifs come from: the one ground step 4 was last run over.
EXTENT = "wlg-pilot"

# Whether to reuse the cached LINZ and GNS layers.
USE_CACHED_LAYERS = True

# ---------------------------------------------------------------------------
# The two simpler natural surfaces compared with ground step 5's anchor surface
# ---------------------------------------------------------------------------

# The rolling mean: the 1 m DEM averaged over a square window this many metres
# a side. Wider than a house platform and its batter, so a single terrace is
# averaged out, and narrow enough to follow the hill.
ROLLING_WINDOW_M = 30.0

# The local polynomial: a quadratic surface fitted, by least squares, to every
# DEM cell within this many metres of any of the pif's points.
FIT_RADIUS_M = 15.0

# The anchor surface, the walk to the foot of each face and the class
# thresholds are ground step 5's, fixed in landloss.hazard.landslide.pif_cut_fill
# (FIT_RADIUS_M, FACE_BUFFER_M, ROBUST_ITERATIONS, SCALE_K, FOOT_SLOPE_DEG,
# FOOT_MAX_M, EXCESS_DROP_M, POSITION_SPLIT), so the research and the step
# cannot drift apart.

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

# The method the figure draws: its natural surface, the cut and fill it reads
# off each face, and its class on the pips ("rolling", "poly" or "anchor").
FIGURE_CLASS_METHOD = "anchor"
