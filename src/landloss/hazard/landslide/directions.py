"""The eight fall directions a pip can have, shared by the modules that read them.

Kept in a module of its own so that :mod:`landloss.hazard.landslide.wall_lines`
and :mod:`landloss.hazard.landslide.instability_zones` can each import it
without importing the other.
"""

import numpy as np

# The eight directions as (row, column) steps, cardinals first so that a tie
# in the drop goes to a cardinal. Index 0 is north, then east, south, west,
# then the diagonals.
DIRECTIONS = ((-1, 0), (0, 1), (1, 0), (0, -1), (-1, 1), (1, 1), (1, -1), (-1, -1))

# The (x, y) step of each direction: DIRECTIONS are (row, column) steps and the
# map's y runs against the rows.
STEP_XY = np.array([(dc, -dr) for dr, dc in DIRECTIONS], dtype=float)
