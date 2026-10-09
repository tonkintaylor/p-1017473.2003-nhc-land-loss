"""Draw one land damage state per cell, and write a raster per realisation.

Step 2 leaves six probability grids over the study extent. A probability is not
something the vulnerability model can read: a claim needs the state its land is
in, not the chance of each. This step draws one:

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/steps/s3_ld_states/gen_liq_ld_states.py

Which realisations to draw comes from ``config.py`` beside it, read at the
bottom of this file and passed into :func:`main`. Change it there rather than
passing flags, so that what a run did can be read off the source.

The draw itself is one uniform variate per cell compared against the cumulative
probability across the states in severity order, in
:func:`landloss.hazard.liquefaction.land_damage.draw_ld_states`. Two properties
of it matter more than the arithmetic.

- **The generator is the realisation's, not the script's.** It comes from
  :func:`landloss.hazard.realisation.realisation_seed` with the project seed,
  the realisation id and the stream name ``liquefaction``. A realisation is one
  modelled earthquake, and the same id has to mean the same event in every
  hazard layer or a claim's causes cannot be summed. Seeding here instead would
  produce a raster that reproduces and yet belongs to no event.
- **Cells are drawn independently.** Liquefaction is spatially correlated --
  neighbouring cells sit on the same deposit, at the same depth to
  groundwater -- and nothing here reproduces that. The realised share of each
  state comes out right; the size of the patches does not.

The run prints the realised share of each state beside the mean probability it
was drawn from. The two columns track each other to within the sampling noise of
however many cells the extent holds, so a state whose share is plainly adrift is
the draw putting a band boundary in the wrong place.

The output is one GeoTIFF per realisation under ``temp/hazard/liquefaction/``,
holding ``ld_state`` values 1 to 6 with the states in the order of
:data:`landloss.hazard.liquefaction.land_damage.LD_STATES`. Cells the NLM knows
nothing about come through as NaN rather than as state 1, because "nothing known
here" is not "no damage".

Reads only what step 2 wrote, so it does not need the T: drive.
"""

import numpy as np
import rioxarray

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.liquefaction.land_damage import LD_STATES, draw_ld_states
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    beta_probability_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states import config
from scripts.landloss.paths import TEMP_DIR

# temp/ is gitignored. A realisation is rebuildable from step 2's grids and its
# own id, so it has no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "liquefaction"

OUT_PREFIX = "ld-state"

# One stream name per hazard, not per script: liquefaction's steps belong to the
# same draw. See landloss.hazard.realisation for why this is a name rather than
# a number.
STREAM = "liquefaction"

# The name the written raster carries, so a file says what it holds without the
# file name having to. It is the field name the beta build contract uses.
LD_STATE_NAME = "ld_state"

RULE = "-" * 72


def ld_state_path(realisation_id, *, extent):
    """Return the file a run writes one realisation's states to.

    The realisation id is in the name rather than in a folder, so a directory
    listing of ``temp/hazard/liquefaction/`` shows which events have been drawn.
    ``fig_ld_states.py`` calls this too, which is what keeps the figure drawing
    the realisation the run actually wrote.

    No ``beta_`` prefix, unlike step 2's grids: a raster of ``ld_state`` is what
    the full version emits as well, and only the probabilities behind it are
    manufactured.

    Args:
        realisation_id: Which modelled earthquake this is, counting from zero.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/hazard/liquefaction/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_PREFIX}-r{realisation_id:03d}{suffix}.tif"


def read_probabilities(*, extent):
    """Read the six state probability grids step 2 wrote.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        One grid per state, keyed by the names in
        :data:`landloss.hazard.liquefaction.land_damage.LD_STATES`.

    Raises:
        ValueError: If the six grids are not all on the same grid. They are
            written by one run over one extent, so this means the folder holds
            grids from two different runs.
    """
    probabilities = {}
    for state in LD_STATES:
        path = beta_probability_path(state, extent=extent)
        # Loaded rather than left lazy: an open GDAL handle finalised during
        # interpreter shutdown surfaces as a bare "Error in sys.excepthook"
        # after an otherwise clean run.
        with rioxarray.open_rasterio(path, masked=True) as opened:
            probabilities[state] = opened.squeeze(drop=True).load()

    shapes = {state: grid.shape for state, grid in probabilities.items()}
    if len(set(shapes.values())) > 1:
        msg = (
            f"The six probability grids are not all the same shape: {shapes}. "
            "They come from one run of step 2 over one extent, so this folder "
            "holds the leftovers of two. Re-run step 2 before drawing from them."
        )
        raise ValueError(msg)

    return probabilities


def describe_draw(probabilities, states):
    """Print the realised share of each state beside the probability it came from.

    The two columns are the check this step has. The realised share converges on
    the mean probability as the extent grows, so the gap to expect is the
    sampling noise of the cell count printed above it -- a percent or so of a
    rare state over a pilot box, far less over the study area. A state whose
    share is adrift by much more than that means the cumulative comparison in
    :func:`landloss.hazard.liquefaction.land_damage.draw_ld_states` has put a
    band boundary in the wrong place.
    """
    values = states.to_numpy()
    drawn = np.isfinite(values)
    total = int(drawn.sum())

    print(f"Cells carrying a state: {total:,} of {values.size:,}")
    if not total:
        print("  Nothing was drawn, so there is no share to report.")
        return

    print(f"  {'state':<12} {'drawn':>12} {'share':>8} {'probability':>12}")
    for index, state in enumerate(LD_STATES, start=1):
        count = int((values == index).sum())
        share = count / total
        mean = float(np.nanmean(probabilities[state].to_numpy()))
        print(f"  {state:<12} {count:>12,} {share:>8.4f} {mean:>12.4f}")


def main(*, extent, realisation_ids):
    """Draw a land damage state per cell for each realisation and write it out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: The modelled earthquakes to draw, one raster each.
    """
    print("Reading the land damage probability grids step 2 wrote ...", flush=True)
    probabilities = read_probabilities(extent=extent)

    for realisation_id in realisation_ids:
        rng = realisation_seed(constants.BASE_SEED, realisation_id, STREAM)
        states = draw_ld_states(probabilities, rng)

        print(RULE)
        print(f"Realisation {realisation_id}, stream {STREAM!r}")
        describe_draw(probabilities, states)

        # The projection is written back explicitly rather than relied on to
        # survive the draw, because write_raster refuses a grid without one.
        # NaN is declared as no data so a cell off the grid is not read as a
        # state: QGIS's paletted renderer draws an undeclared NaN as state 1.
        grid = (
            states.rename(LD_STATE_NAME)
            .rio.write_crs(constants.DEFAULT_CRS)
            .rio.write_nodata(np.nan)
        )
        path = write_raster(grid, ld_state_path(realisation_id, extent=extent))
        print(f"Wrote {path}")

    print(RULE)
    print(
        f"Seeded from BASE_SEED {constants.BASE_SEED}; re-run with the same "
        "realisation ids to reproduce these exactly."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT, realisation_ids=config.REALISATION_IDS)
