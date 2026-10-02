"""Flag which culverts and bridges a landslide reached.

Intersects the combined landslide realisation, the large model and the urban
slope model together, against the crossing population and writes, for every
crossing, whether it sits on evacuated ground, under inundated ground, or both.

    uv run --frozen python src/scripts/landloss/vul/landslide/culverts_bridges/steps/s11_crossing_landslide_damage/gen_crossing_landslide_damage.py

The damage measure here is **a flag, not an area**. A culvert or a bridge is
not settled by how much ground a landslide took from it, as land is, but by
whether a landslide reached it at all, so the question per crossing is yes or
no. The two kinds of ground stay apart because the policy settles them
differently: evacuated ground is loss of support, inundated ground is debris
arriving from upslope.

Every crossing is written, one row each, with both flags False where no
landslide reached it. The flags are computed for culverts and bridges alike;
the split by structure kind happens at the loss handover.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd

from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    CROSSING_ID_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    REALISATION_ID_COLUMN,
)
from landloss.vul.landslide.flags import landslide_flags
from landloss.vul.loss_input import WORLD_ID_COLUMN
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population.gen_crossing_population import (
    crossing_population_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.landslide.culverts_bridges.steps.s11_crossing_landslide_damage import (
    config,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "crossing-landslide-damage"
RULE = "-" * 72


def crossing_landslide_damage_path(world_id, realisation_id, *, pilot):
    """Return the file a run writes one world and earthquake's crossing flags to.

    Args:
        world_id: The exposure world (one draw of the wall population) the file holds.
        realisation_id: The earthquake realisation the file holds.
        pilot: Whether the run covers the pilot area only, which adds a
            ``-pilot`` suffix to the file name.

    Returns:
        The parquet path under the vul work directory.
    """
    suffix = "-pilot" if pilot else ""
    return (
        WORK_DIR / f"{OUT_STEM}-w{world_id:03d}-r{realisation_id:03d}{suffix}.parquet"
    )


def describe_damage(damaged, landslides):
    """Print how many crossings each kind of damaged ground reached."""
    print(RULE)
    print(f"Landslide polygons: {len(landslides):,}")
    if damaged.empty:
        print("  no crossings over this extent")
        return
    print(f"Crossings: {len(damaged):,}")
    for column in (IS_EVACUATED_COLUMN, IS_INUNDATED_COLUMN):
        print(f"  {column}: {int(damaged[column].sum()):,}")
    both = damaged[IS_EVACUATED_COLUMN] & damaged[IS_INUNDATED_COLUMN]
    print(f"  both: {int(both.sum()):,}")


def main(*, pilot, world_ids, realisation_ids):
    """Write the landslide flags per crossing, per world and earthquake.

    Args:
        pilot: Whether to run over the pilot area only.
        world_ids: The exposure worlds to run, each one draw of the wall population.
        realisation_ids: The earthquake realisations to run in every world.
    """
    for realisation_id in realisation_ids:
        # The crossing population is drawn per earthquake, not per world: which
        # structure sits at a crossing does not depend on which walls exist.
        crossings_path = crossing_population_path(realisation_id, pilot=pilot)
        print(f"Reading the crossings from {crossings_path} ...", flush=True)
        crossings = gpd.read_parquet(crossings_path)
        if CROSSING_ID_COLUMN not in crossings.columns:
            msg = (
                f"{crossings_path} carries no {CROSSING_ID_COLUMN!r}; rerun "
                "exposure step 5 and then step 7"
            )
            raise ValueError(msg)

        for world_id in world_ids:
            print(RULE)
            print(f"World {world_id}, realisation {realisation_id}")
            slides_path = combined_realisation_path(
                world_id, realisation_id, pilot=pilot
            )
            print(f"Reading the landslides from {slides_path} ...", flush=True)
            landslides = gpd.read_parquet(slides_path)

            damaged = landslide_flags(
                crossings, landslides, id_column=CROSSING_ID_COLUMN
            )
            damaged.insert(1, CLAIM_ID_COLUMN, crossings[CLAIM_ID_COLUMN].to_numpy())
            damaged.insert(0, REALISATION_ID_COLUMN, realisation_id)
            damaged.insert(1, WORLD_ID_COLUMN, world_id)
            describe_damage(damaged, landslides)

            out_path = crossing_landslide_damage_path(
                world_id, realisation_id, pilot=pilot
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            damaged.to_parquet(out_path)
            print(f"Wrote {len(damaged):,} rows to {out_path}")


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
