"""Run settings for the slope elements research scripts.

Everything that changes between one run of ``fig_toy_slope_elements.py`` and
the next, in one short file. The script takes these as arguments and holds no
defaults of its own, so what a run did can be read here and in git history.

The growth and polygon rules themselves (the step-test table, the grow angles,
the widths behind the crest) are fixed in the library modules
``landloss.hazard.landslide.slope_elements`` and
``landloss.hazard.landslide.slope_polygons``, not here.
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
