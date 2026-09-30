"""Draw a realisation of the retaining wall population from the probabilities.

Reads the per-property probabilities ``gen_wall_probability.py`` wrote and draws
one population per realisation: whether each property carries a wall, how tall
it is and what condition it is in. Each wall is drawn as a line lying along the
contour, carrying the claim it belongs to, its size class and its initial
condition. Only the walls that touch their own claim's insured land, buffered by
2 m, are kept, and each kept wall is given an ``rw_id``.

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_population.py

Run ``gen_wall_probability.py`` first. This script reads no elevation model and
no GNS layer, so any number of realisations draw quickly.

**The probabilities are partly a beta stand-in and none of this is evidence
about Wellington.** The real population is inferred from a model trained on the
ICNZ database, a manual mapping study, T+T SME estimates and remote sensing, and
the SME estimate of prevalence by suburb (**T-19**) is what it would be
calibrated against. What this step buys is the structure the vulnerability work
reads: a line per wall with a size class and an initial condition.

The reasoning behind every number is in `landloss.exposure.rw.wall_probability`
and `landloss.exposure.rw.beta_population`.

What it runs over, and for which realisations, comes from ``config.py`` beside
it.
"""

import sys

import geopandas as gpd
import numpy as np

from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN, RW_ID_COLUMN
from landloss.exposure.asset_ids import RW_ID_SUFFIX, mint_asset_ids, sort_by_location
from landloss.exposure.coverage import RW_COVERAGE_BUFFER_M, keep_walls_on_insured_land
from landloss.exposure.rw.beta_population import describe_population
from landloss.exposure.rw.wall_probability import draw_walls
from landloss.hazard.realisation import realisation_seed
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_probability import (
    wall_probability_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "beta-wall-population"

# The stream these draws come from. One name per module, so the walls of
# realisation 3 belong to the same modelled earthquake as its hazards.
RNG_STREAM = "exposure"

RULE = "-" * 72


def wall_population_path(realisation_id, *, pilot):
    """Return the file a run writes one realisation's walls to.

    Args:
        realisation_id: Which modelled earthquake this is.
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.geoparquet"


def describe_walls(walls, probabilities):
    """Print what was drawn, against what it was drawn from."""
    print(RULE)
    share = len(walls) / len(probabilities) if len(probabilities) else 0.0
    expected = float(np.nansum(probabilities["p_wall"].to_numpy(dtype=float)))
    print(
        f"Walls drawn: {len(walls):,} over {len(probabilities):,} properties "
        f"({share:.1%}); expected {expected:,.0f}"
    )
    if walls.empty:
        return
    print(RULE)
    print("Walls by size class and initial condition:")
    print(describe_population(walls).to_string())
    length = walls["length_m"].to_numpy(dtype=float)
    height = walls["height_m"].to_numpy(dtype=float)
    print(
        f"  length {length.min():.1f} to {length.max():.1f} m, "
        f"median {np.median(length):.1f}"
    )
    print(
        f"  retained height {height.min():.1f} to {height.max():.1f} m, "
        f"median {np.median(height):.1f}"
    )


def describe_coverage(before, after):
    """Print how many walls the insured land coverage filter kept."""
    print(RULE)
    dropped = len(before) - len(after)
    share = len(after) / len(before) if len(before) else 0.0
    print(
        f"Coverage: {len(before):,} walls drawn, {len(after):,} kept, "
        f"{dropped:,} dropped ({share:.1%} kept)"
    )
    print(
        "  a wall is kept if it touches its own claim's insured land buffered "
        f"by {RW_COVERAGE_BUFFER_M:g} m"
    )
    print(
        "  under the beta each wall is centred inside its own polygon, so nearly "
        "all are kept"
    )


def main(*, pilot, realisation_ids):
    """Draw a wall population per realisation and write each one out.

    Args:
        pilot: Whether to run over the small Wellington pilot box.
        realisation_ids: Which modelled earthquakes to draw for.
    """
    probability_path = wall_probability_path(pilot=pilot)
    print(f"Reading the wall probabilities from {probability_path} ...")
    probabilities = gpd.read_parquet(probability_path)
    properties = gpd.read_parquet(insured_land_path(pilot=pilot))

    for realisation_id in realisation_ids:
        print(RULE)
        print(f"Realisation {realisation_id}, stream {RNG_STREAM!r}")
        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        walls = draw_walls(probabilities, rng)
        describe_walls(walls, probabilities)

        # Filtered against the polygons rather than the representative points
        # the walls were placed from, and after the draw so the stream is
        # unchanged.
        kept = keep_walls_on_insured_land(walls, properties)
        describe_coverage(walls, kept)
        kept = sort_by_location(kept)
        kept.insert(
            0, RW_ID_COLUMN, mint_asset_ids(kept[CLAIM_ID_COLUMN], RW_ID_SUFFIX)
        )

        out_path = wall_population_path(realisation_id, pilot=pilot)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        kept.to_parquet(out_path)
        print(f"Wrote {len(kept):,} walls to {out_path}")

    print(RULE)
    print(
        "This population is drawn from probabilities that are partly a beta "
        "stand-in. It is not evidence about Wellington; see T-19 for what "
        "replaces it."
    )


if __name__ == "__main__":
    main(pilot=config.PILOT, realisation_ids=config.REALISATION_IDS)
