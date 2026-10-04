"""Run settings for the slope elements research scripts.

Everything that changes between one run of ``fig_toy_slope_elements.py`` and
the next, in one short file. The script takes these as arguments and holds no
defaults of its own, so what a run did can be read here and in git history.

The growth and polygon rules themselves (the step-test table, the grow angles,
the widths behind the crest) are fixed in the library modules
``landloss.hazard.landslide.slope_elements`` and
``landloss.hazard.landslide.slope_polygons``, not here.

The first block is stage D1 (toy terrain, ``fig_toy_slope_elements.py``); the
block after it is stage D2 (real pilot examples,
``fig_pilot_example_slope_elements.py``).
"""

from landloss.hazard.landslide.synthetic_terrain import BETA_LIDAR_NOISE_SD_M

# The standard deviation of the LiDAR-like noise on the noisy copy of every toy
# case, in metres. Taken from the library rather than retyped.
NOISE_SD_M = BETA_LIDAR_NOISE_SD_M

# The noise seed the figures and the observed-outcome tables use. The same seed
# the regression tests use by default, so the figure shows the tested draw.
FIGURE_SEED = 7

# The noise seeds every case is rerun with to count how often its expected
# outcome holds under noise.
NOISE_SEEDS = tuple(range(30))

# The cases whose walls stand on fill (the plan's case 1 says so; cases 2 and 5
# are the same walls). Their free-faces are on fill and any ground rising
# behind them natural; every other case is cut or natural ground.
FILL_CASES = ("01", "02", "05")

# The contour intervals the plan views may use, in metres; each figure takes
# the smallest that draws no more than MAX_CONTOURS lines.
CONTOUR_INTERVALS_M = (0.1, 0.25, 0.5, 1.0, 2.0)
MAX_CONTOURS = 25

# The timing grid: case 10 mirrored end to end so the ground is continuous,
# repeated this many times down and across (rows, mirrored pairs), which gives
# a 1,000 by 1,100 cell grid, the size of a 1 km tile.
SPEED_TILES = (25, 10)

# ---------------------------------------------------------------------------
# Stage D2: real examples from the pilot
# ---------------------------------------------------------------------------

# The extent the examples are drawn from; the DEM and the ground map are the
# ones landslide steps 3 and 4 wrote for it. "wlg-pilot" is Mt Victoria and
# Hataitai.
PILOT_EXTENT = "wlg-pilot"

# The contour intervals the example plans may use, in metres; each site takes
# the smallest that draws no more than PILOT_MAX_CONTOURS lines.
PILOT_CONTOUR_INTERVALS_M = (1.0, 2.0, 5.0, 10.0)
PILOT_MAX_CONTOURS = 30

# The sea is masked with the LINZ NZ Coastlines and Islands Polygons (Topo 1:50k)
# land polygons: every cell outside them is set to no data before the library
# runs, as the DEM carries the sea as a flat surface.

# A GNS line or a SLIDE edge counts as agreeing with an element where it lies
# within this many metres of it (the plan's detection check, phase 4, takes 2 m
# for a wall and 3 m for a break in slope).
GNS_WALL_MATCH_M = 2.0
GNS_BREAK_MATCH_M = 3.0

# The sites, each a window of 2 * half_size_m metres a side centred on an NZTM
# point, with the reason it was picked and what it should show. The ground map
# only covers 1,748,323 to 1,751,191 E and 5,423,605 to 5,425,336 N, so a site
# outside that would be drawn on the off-map default ground.
PILOT_SITES = (
    {
        "name": "01-wall-soil",
        "x": 1748714.0,
        "y": 5424998.0,
        "half_size_m": 60.0,
        "category": "GNS mapped wall of measured height",
        "reason": "A 72 m free-face 2.9 m high with a GNS mapped wall under it "
        "(0.05 m away), on soil-like ground, clear of any SLIDE cut or fill.",
        "expect": "One free-face along the wall, its crest and toe on the wall, "
        "and the wall's wedge behind it.",
    },
    {
        "name": "02-wall-tall",
        "x": 1750089.0,
        "y": 5424544.0,
        "half_size_m": 60.0,
        "category": "GNS mapped wall of measured height",
        "reason": "A 69 m free-face 4.2 m high (7 m in the window) with a GNS wall "
        "1.2 m from it, on weak rock, the tallest wall that is not in a cut.",
        "expect": "A free-face on the wall, taller than 01, so a wider wedge "
        "and a longer run-out.",
    },
    {
        "name": "03-wall-flat",
        "x": 1750441.0,
        "y": 5425145.0,
        "half_size_m": 60.0,
        "category": "Stacked terraces, wall on flat ground",
        "reason": "GNS wall 875 (133 m) on a 2 m step with flat ground below and "
        "a 9.5 m slope above it; the ground map's stack chain of ten "
        "elements ends here.",
        "expect": "A stack polygon from the slope above, and a short wedge "
        "at the wall that does not reach far over the flat ground.",
    },
    {
        "name": "04-road-cut",
        "x": 1748398.0,
        "y": 5425070.0,
        "half_size_m": 70.0,
        "category": "Road cut in weak rock",
        "reason": "The pilot's tallest free-face, 15.9 m at 56 degrees on weak rock, "
        "inside a SLIDE cut slope, with the road at its toe.",
        "expect": "A stack-dominant cut taking the benches above it; a wide "
        "evacuated zone and a run-out onto the road.",
    },
    {
        "name": "05-excavated-toe",
        "x": 1749009.0,
        "y": 5423918.0,
        "half_size_m": 70.0,
        "category": "Excavated toe under a natural slope",
        "reason": "An 11 m free-face on weak rock in a SLIDE cut slope, with a "
        "GNS wall 17 m away and natural slope above it.",
        "expect": "The free-face in the cut and the bank above it, and the "
        "polygon retrogressing from the cut up into the bank.",
    },
    {
        "name": "06-fill-platform",
        "x": 1749449.0,
        "y": 5423734.0,
        "half_size_m": 70.0,
        "category": "SLIDE fill body (platform)",
        "reason": "A 2.9 ha SLIDE fill body, a flat platform some 100 m across "
        "with steep batters on its eastern and northern rims.",
        "expect": "No element on the flat platform and fill-flow-slide polygons "
        "from the batters only.",
    },
    {
        "name": "07-fill-gully",
        "x": 1748600.0,
        "y": 5424461.0,
        "half_size_m": 90.0,
        "category": "SLIDE fill body (large)",
        "reason": "The pilot's biggest SLIDE fill body, 38 ha and 72 m of relief, "
        "at the edge of a deep cut in its south-west corner.",
        "expect": "Elements on the cut's walls and the fill's rim, and "
        "nothing across the fill's flat platform.",
    },
    {
        "name": "08-adjacent-catchments",
        "x": 1749472.0,
        "y": 5424360.0,
        "half_size_m": 60.0,
        "category": "Two adjacent catchments",
        "reason": "Elements 4879 and 4930, the only pair in the pilot whose "
        "polygons overlap and whose catchments are disjoint, either side of "
        "a walled terrace.",
        "expect": "Each polygon keeps its own evacuated ground, apart from the "
        "two cells it shares with its neighbour.",
    },
    {
        "name": "09-seawall",
        "x": 1750555.0,
        "y": 5424878.0,
        "half_size_m": 80.0,
        "category": "Long edge with no wall mapped",
        "reason": "The pilot's longest free-face, 428 m at 1.8 m high, along the "
        "harbour edge, where the DEM's water surface is flat.",
        "expect": "A long straight free-face on the harbour edge, with no failure "
        "into the sea: the LINZ water mask removes the DEM's flat surface.",
    },
    {
        "name": "10-steep-bank",
        "x": 1749520.0,
        "y": 5424724.0,
        "half_size_m": 60.0,
        "category": "Steep bank with no wall",
        "reason": "A 7.6 m weak rock bank at 35 degrees with no GNS wall within "
        "19 m, outside any SLIDE cut or fill.",
        "expect": "A headscarp-band polygon where it is steep, and none "
        "where the ground is gentler.",
    },
    {
        "name": "11-mapped-failure",
        "x": 1749417.0,
        "y": 5424214.0,
        "half_size_m": 60.0,
        "category": "The mapped failure",
        "reason": "The only SLIDE 'landslide recent' source area in the pilot "
        "(3.5 m2) sits on a 5 m free-face of the cut below it.",
        "expect": "A polygon whose crest takes the mapped scar.",
    },
    {
        "name": "12-gentle-control",
        "x": 1750665.0,
        "y": 5423785.0,
        "half_size_m": 60.0,
        "category": "Negative control",
        "reason": "Gentle ground (about 4 degrees) of the few windows with no "
        "element within 20 m, which is most of the pilot's ground above "
        "8 degrees; the model should say nothing here.",
        "expect": "No element, no polygon.",
    },
)
