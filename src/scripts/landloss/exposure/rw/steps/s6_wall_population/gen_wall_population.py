"""Draw one exposure world's retaining wall population from the line probabilities.

Reads the per-line probabilities ``gen_wall_probability.py`` wrote and draws
one population per exposure world: which candidate lines are walls and the
condition of each. A wall is the line that drew it, carrying the line's id,
its DEM face height and size class, its length, whether it holds fill or a cut
face, and the claim it belongs to. Lines with no claim are dropped, because
council and road-reserve walls are out of scope (**I-05**); the walls that
touch their own claim's insured land, buffered by 2 m, are kept; and each kept
wall is given an ``rw_id``. That insured population is what vul and loss read.

The two filters decide what is insured, not whether a wall stands: a road
retaining wall above a property, or a wall at the back of a section beyond
the buffer, still holds its slope. So the script also writes every wall the
world drew, before either filter, with the minted ``rw_id`` where the wall was
kept and null where it was not. Landslide step 8 builds the urban slope model
on that file, so an uninsured wall shapes the hazard without entering the
loss tables (decision 36 of the build contract).

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_population.py

Run ``gen_wall_probability.py`` first, and land step 5 for the insured land.
This script reads no elevation model and no GNS layer, so any number of worlds
draw quickly.

A world is seeded on ``EXPOSURE_BASE_SEED`` and its own id, not on any
earthquake: whether a wall exists is a fact we do not know, not something the
earthquake decides, so the same world is paired with every hazard realisation
(`landloss.hazard.realisation`). The draw is in
`landloss.exposure.rw.population`; the probabilities and the reasoning behind
every number are in `landloss.exposure.rw.wall_probability`.

What it runs over, and for which worlds, comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np

from landloss.domain import constants
from landloss.domain.loss_contract import CLAIM_ID_COLUMN, RW_ID_COLUMN
from landloss.exposure.asset_ids import RW_ID_SUFFIX, mint_asset_ids, sort_by_location
from landloss.exposure.coverage import RW_COVERAGE_BUFFER_M, keep_walls_on_insured_land
from landloss.exposure.rw.beta_population import SIZE_CLASSES, describe_population
from landloss.exposure.rw.population import (
    WALL_LINE_ID_COLUMN,
    attach_rw_ids,
    draw_wall_population,
)
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
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
OUT_STEM = "wall-population"
DRAWN_STEM = "drawn-walls"

# The stream the world's draws come from, under EXPOSURE_BASE_SEED.
RNG_STREAM = "exposure"

WORLD_ID_COLUMN = "world_id"

RULE = "-" * 72


def wall_population_path(world_id, *, extent):
    """Return the file a run writes one world's walls to.

    Args:
        world_id: Which exposure world this is.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}-w{world_id:03d}{suffix}.geoparquet"


def drawn_walls_path(world_id, *, extent):
    """Return the file a run writes every wall one world drew to.

    The walls before the claim and coverage filters, with ``rw_id`` null on
    the ones those filters dropped. Landslide step 8 reads it; nothing else
    does.

    Args:
        world_id: Which exposure world this is.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{DRAWN_STEM}-w{world_id:03d}{suffix}.geoparquet"


def insert_world_id(walls, world_id):
    """Write the world id beside ``wall_line_id``, as the contract orders it."""
    walls.insert(
        walls.columns.get_loc(WALL_LINE_ID_COLUMN) + 1,
        WORLD_ID_COLUMN,
        np.full(len(walls), world_id, dtype=np.int64),
    )
    return walls


def describe_drawn_walls(drawn):
    """Print how many drawn walls there are and how many of them are insured."""
    insured = int(drawn[RW_ID_COLUMN].notna().sum())
    print(
        f"Drawn walls: {len(drawn):,} in the world, {insured:,} carrying an rw_id, "
        f"{len(drawn) - insured:,} uninsured (they shape the urban slope model "
        "and write no loss row)"
    )


def describe_draw(walls, probabilities):
    """Print what was drawn, against what it was drawn from."""
    print(RULE)
    share = len(walls) / len(probabilities) if len(probabilities) else 0.0
    expected = float(np.nansum(probabilities["p_wall"].to_numpy(dtype=float)))
    print(
        f"Walls drawn: {len(walls):,} over {len(probabilities):,} candidate lines "
        f"({share:.1%}); expected {expected:,.0f}"
    )


def describe_claims(before, after):
    """Print how many drawn walls had a claim to belong to."""
    dropped = len(before) - len(after)
    print(
        f"Claims: {len(after):,} walls on a claim property, {dropped:,} dropped "
        "on road reserve or outside every claim (I-05)"
    )


def describe_coverage(before, after):
    """Print how many walls the insured land coverage filter kept."""
    dropped = len(before) - len(after)
    share = len(after) / len(before) if len(before) else 0.0
    print(
        f"Coverage: {len(before):,} walls with a claim, {len(after):,} kept, "
        f"{dropped:,} dropped ({share:.1%} kept)"
    )
    print(
        "  a wall is kept if it touches its own claim's insured land buffered "
        f"by {RW_COVERAGE_BUFFER_M:g} m"
    )


def describe_walls(walls):
    """Print the kept population by size, condition, position and ground."""
    print(RULE)
    print("Walls by size class and initial condition:")
    print(describe_population(walls).to_string())
    if walls.empty:
        return
    flat = walls["is_flatland"].to_numpy(dtype=bool)
    print(f"On flat land: {int(flat.sum()):,} ({flat.mean():.1%})")
    print("By wall position:")
    print(walls["wall_position"].value_counts().to_string())
    print("Height (m) by size class, deciles 10/50/90:")
    for size in SIZE_CLASSES:
        height = walls.loc[walls["size_class"] == size, "height_m"].to_numpy(
            dtype=float
        )
        height = height[np.isfinite(height)]
        if height.size == 0:
            print(f"  {size}: none")
            continue
        low, mid, high = np.percentile(height, [10, 50, 90])
        print(f"  {size}: {low:.2f}  {mid:.2f}  {high:.2f}  ({height.size:,} walls)")


def main(*, extent, world_ids):
    """Draw a wall population per exposure world and write each one out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: Which exposure worlds to draw.
    """
    probability_path = wall_probability_path(extent=extent)
    print(f"Reading the wall probabilities from {probability_path} ...")
    probabilities = gpd.read_parquet(probability_path)
    insured = gpd.read_parquet(insured_land_path(extent=extent))

    for world_id in world_ids:
        print(RULE)
        print(f"World {world_id}, stream {RNG_STREAM!r} on EXPOSURE_BASE_SEED")
        rng = realisation_seed(constants.EXPOSURE_BASE_SEED, world_id, RNG_STREAM)
        drawn = draw_wall_population(probabilities, rng)
        describe_draw(drawn, probabilities)

        # Filtered after the draw, so the stream is the same whatever is kept.
        with_claim = drawn.loc[drawn[CLAIM_ID_COLUMN].notna()].reset_index(drop=True)
        describe_claims(drawn, with_claim)
        kept = keep_walls_on_insured_land(with_claim, insured)
        describe_coverage(with_claim, kept)

        kept = sort_by_location(kept)
        kept.insert(
            0, RW_ID_COLUMN, mint_asset_ids(kept[CLAIM_ID_COLUMN], RW_ID_SUFFIX)
        )
        kept = insert_world_id(kept, world_id)
        describe_walls(kept)

        out_path = wall_population_path(world_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        kept.to_parquet(out_path)
        print(f"Wrote {len(kept):,} walls to {out_path}")

        # Every drawn wall, insured or not, for the urban slope model.
        every_wall = insert_world_id(attach_rw_ids(drawn, kept), world_id)
        describe_drawn_walls(every_wall)
        drawn_path = drawn_walls_path(world_id, extent=extent)
        every_wall.to_parquet(drawn_path)
        print(f"Wrote {len(every_wall):,} drawn walls to {drawn_path}")

    print(RULE)
    print(
        "This population is drawn from probabilities that are judgement standing "
        "in for the claim report extraction (T-50); it is not evidence about "
        "Wellington."
    )


if __name__ == "__main__":
    main(extent=config.EXTENT, world_ids=config.WORLD_IDS)
