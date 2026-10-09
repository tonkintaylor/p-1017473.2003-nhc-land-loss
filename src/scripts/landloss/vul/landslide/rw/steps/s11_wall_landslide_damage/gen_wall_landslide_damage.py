"""Set the three contract flags on each retaining wall, per world and earthquake.

Reads the wall population of an exposure world, the combined landslide
realisation (the large model and the urban slope model together) and the urban
wall outcome table for that world and earthquake, and writes whether each wall
was written off by its own slope failing, sits on evacuated ground, or sits
under inundated ground.

    uv run --frozen python src/scripts/landloss/vul/landslide/rw/steps/s11_wall_landslide_damage/gen_wall_landslide_damage.py

A wall is not measured by how much ground a landslide took from it, as land is,
but by whether a landslide reached it at all, so this step writes flags rather
than areas. A sloping wall has two routes to a flag: the urban slope model's
outcome for its polygon (failed through the wall, absorbed by a larger urban
failure, superseded by a large landslide, or standing), mapped onto a flag by
``landloss.vul.landslide.flags.OUTCOME_FLAGS``, and the geometric intersection
of its line with any evacuated or inundated polygon of either population. The
two are OR-ed. A flat-land wall has no outcome row and takes its flags from
geometry alone; its shaking flag is the shaking step's, applied when the loss
tables are built.

**No cost is attached.** The flags are what the loss module prices, and any
flag true means one replacement; which flag is set only attributes the cause.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import pandas as pd

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
)
from landloss.hazard.landslide.land_class import LAND_CLASS_COLUMN
from landloss.io.area_of_interest import extent_suffix
from landloss.vul.landslide.flags import (
    OUTCOME_COLUMN,
    SLOPE_ID_COLUMN,
    WALL_FLAG_COLUMNS,
    wall_flags,
)
from landloss.vul.loss_input import WORLD_ID_COLUMN
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
    urban_wall_outcome_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "wall-landslide-damage"
POPULATION_COLUMN = "population"
IS_FLATLAND_COLUMN = "is_flatland"
RULE = "-" * 72


def wall_landslide_damage_path(world_id, realisation_id, *, extent):
    """Return the file a run writes one world and earthquake's wall flags to.

    Args:
        world_id: The exposure world (one draw of the wall population) the file holds.
        realisation_id: The earthquake realisation the file holds.
        extent: The extent the run covers, a name from
            landloss.io.area_of_interest.EXTENTS or "full". It sets the
            file name suffix through ``extent_suffix``.

    Returns:
        The parquet path under the vul work directory.
    """
    suffix = extent_suffix(extent)
    return (
        WORK_DIR / f"{OUT_STEM}-w{world_id:03d}-r{realisation_id:03d}{suffix}.parquet"
    )


def describe_landslides(landslides):
    """Print the realisation's polygons by population and land class."""
    print(RULE)
    print(f"Landslide polygons: {len(landslides):,}")
    if landslides.empty:
        return
    by = [POPULATION_COLUMN, LAND_CLASS_COLUMN]
    if POPULATION_COLUMN not in landslides.columns:
        by = [LAND_CLASS_COLUMN]
    for keys, count in landslides.groupby(by, sort=True).size().items():
        label = keys if isinstance(keys, str) else ", ".join(map(str, keys))
        print(f"  {label}: {count:,}")


def describe_flags(flags, walls, outcomes):
    """Print the outcomes and how many walls carry each flag."""
    print(RULE)
    print(f"Walls: {len(flags):,}")
    if IS_FLATLAND_COLUMN in walls.columns:
        flat = int(walls[IS_FLATLAND_COLUMN].sum())
        print(f"  on flat land: {flat:,}; on sloping ground: {len(walls) - flat:,}")
    print(f"  with an outcome row: {len(outcomes):,}")
    print(f"  without one: {int(flags[OUTCOME_COLUMN].isna().sum()):,}")
    if len(outcomes):
        print("Outcomes:")
        for outcome, count in flags[OUTCOME_COLUMN].value_counts().items():
            print(f"  {outcome}: {count:,}")
        print(
            f"  with no polygon (slope_id null): "
            f"{int(flags[SLOPE_ID_COLUMN].isna().sum() - flags[OUTCOME_COLUMN].isna().sum()):,}"
        )
    print("Flags:")
    for column in WALL_FLAG_COLUMNS:
        print(f"  {column}: {int(flags[column].sum()):,}")
    any_flag = flags[list(WALL_FLAG_COLUMNS)].any(axis=1)
    print(f"  any flag, so one replacement in loss: {int(any_flag.sum()):,}")


def main(*, extent, world_ids, realisation_ids):
    """Write the three contract flags per wall, per world and earthquake.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: The exposure worlds to run, each one draw of the wall population.
        realisation_ids: The earthquake realisations to run in every world.
    """
    for world_id in world_ids:
        walls_path = wall_population_path(world_id, extent=extent)
        print(f"Reading the walls of world {world_id} from {walls_path} ...")
        walls = gpd.read_parquet(walls_path)
        claims = walls.set_index(RW_ID_COLUMN)[CLAIM_ID_COLUMN]

        for realisation_id in realisation_ids:
            print(RULE)
            print(f"World {world_id}, realisation {realisation_id}")
            slides_path = combined_realisation_path(
                world_id, realisation_id, extent=extent
            )
            print(f"Reading the landslides from {slides_path} ...", flush=True)
            landslides = gpd.read_parquet(slides_path)
            outcomes_path = urban_wall_outcome_path(
                world_id, realisation_id, extent=extent
            )
            print(f"Reading the wall outcomes from {outcomes_path} ...", flush=True)
            outcomes = pd.read_parquet(outcomes_path)

            flags = wall_flags(walls, landslides, outcomes, id_column=RW_ID_COLUMN)
            flags.insert(0, REALISATION_ID_COLUMN, realisation_id)
            flags.insert(1, WORLD_ID_COLUMN, world_id)
            flags.insert(3, CLAIM_ID_COLUMN, flags[RW_ID_COLUMN].map(claims))
            describe_landslides(landslides)
            describe_flags(flags, walls, outcomes)

            out_path = wall_landslide_damage_path(
                world_id, realisation_id, extent=extent
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            flags.to_parquet(out_path)
            print(f"Wrote {len(flags):,} rows to {out_path}")

    print(RULE)
    print("Flags only. Nothing here is priced.")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
