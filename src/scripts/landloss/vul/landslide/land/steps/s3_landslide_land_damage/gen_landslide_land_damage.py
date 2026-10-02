"""Measure how much of each property's insured land a landslide took.

Intersects the combined landslide realisation, the large model and the urban
slope model together, against the insured land extent and writes the evacuated
and inundated area on every insured land polygon it reached, each with the
depth of the material involved, and the area of their union. Rows are keyed on
``land_id`` and carry the ``claim_id`` the polygon belongs to.

    uv run --frozen python src/scripts/landloss/vul/landslide/land/steps/s3_landslide_land_damage/gen_landslide_land_damage.py

The damage measure here is **geometric, not a damage state**. A landslide either
covers part of a property or it does not, and how much it covers is the whole
question, so this step produces areas where the liquefaction step produces a
state.

The two kinds of ground stay apart because the policy settles them differently:
evacuated ground is loss of support, inundated ground is somebody else's
hillside arriving. Inundated area is measured on the union of the landslides
that reached a property rather than summed across them, because inundated
polygons may overlap and ground buried twice is buried once. For the same
reason the two kinds are also measured together on their union, which is the
loss contract's ``land_slide_total_insured_land_area``.

The urban model also writes **imminent** ground, left standing behind a
headscarp. It is ignored here until the register decides how it is settled
(**T-45**).

**No cost is attached.** The T+T landslip remediation schedule is not packaged,
so the money is left to the loss module. What this writes is the quantity the
pricing will multiply.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd

from landloss.domain import constants
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    LAND_ID_COLUMN,
    REALISATION_ID_COLUMN,
)
from landloss.hazard.landslide.land_class import LAND_CLASS_COLUMN
from landloss.vul.landslide.land.damaged_area import (
    AREA_COLUMNS,
    IGNORED_LAND_CLASSES,
    UNION_AREA_COLUMN,
    check_within_insured_area,
    damaged_area_per_property,
)
from landloss.vul.loss_input import WORLD_ID_COLUMN
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "landslide-land-damage"
POPULATION_COLUMN = "population"
RULE = "-" * 72


def landslide_land_damage_path(world_id, realisation_id, *, pilot):
    """Return the file a run writes one world and earthquake's damaged areas to.

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
    ignored = int(landslides[LAND_CLASS_COLUMN].isin(IGNORED_LAND_CLASSES).sum())
    if ignored:
        print(f"  {ignored:,} polygons are {IGNORED_LAND_CLASSES} and measure nothing")


def describe_damage(damaged, insured):
    """Print what the landslides reached, and check it fits inside the land."""
    print(RULE)
    print(f"Land polygons reached: {len(damaged):,} of {len(insured):,}")
    if damaged.empty:
        return
    class_total = 0.0
    for kind, column in AREA_COLUMNS.items():
        area = damaged[column]
        hit = area > 0
        class_total += area.sum()
        print(
            f"  {kind}: {int(hit.sum()):,} polygons, {area.sum():,.0f} m2 total, "
            f"median {area[hit].median():,.1f} m2 where present"
        )
    union_total = damaged[UNION_AREA_COLUMN].sum()
    print(
        f"  union of both: {union_total:,.0f} m2 total; summing the two would "
        f"have counted {class_total - union_total:,.0f} m2 twice"
    )
    over = check_within_insured_area(damaged, insured, id_column=LAND_ID_COLUMN)
    if over.empty:
        print("  no polygon carries more damaged ground than it has insured land")
    else:
        print(f"  {len(over):,} polygons carry more damage than insured land")


def main(*, pilot, world_ids, realisation_ids):
    """Write the landslide damaged area per insured land polygon.

    One file is written per world and earthquake.

    Args:
        pilot: Whether to run over the pilot area only.
        world_ids: The exposure worlds to run, each one draw of the wall population.
        realisation_ids: The earthquake realisations to run in every world.
    """
    insured = gpd.read_parquet(insured_land_path(pilot=pilot))
    claim_of_land = insured.set_index(LAND_ID_COLUMN)[CLAIM_ID_COLUMN]

    for world_id in world_ids:
        for realisation_id in realisation_ids:
            print(RULE)
            print(f"World {world_id}, realisation {realisation_id}")
            slides_path = combined_realisation_path(
                world_id, realisation_id, pilot=pilot
            )
            print(f"Reading the landslides from {slides_path} ...", flush=True)
            landslides = gpd.read_parquet(slides_path)

            damaged = damaged_area_per_property(
                insured, landslides, id_column=LAND_ID_COLUMN
            )
            damaged.insert(
                1, CLAIM_ID_COLUMN, damaged[LAND_ID_COLUMN].map(claim_of_land)
            )
            damaged.insert(0, REALISATION_ID_COLUMN, realisation_id)
            damaged.insert(1, WORLD_ID_COLUMN, world_id)
            damaged["cause_evacuated"] = str(constants.Cause.LANDSLIDE_EVACUATED)
            damaged["cause_inundated"] = str(constants.Cause.LANDSLIDE_INUNDATED)
            describe_landslides(landslides)
            describe_damage(damaged, insured)

            out_path = landslide_land_damage_path(world_id, realisation_id, pilot=pilot)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            damaged.to_parquet(out_path)
            print(f"Wrote {len(damaged):,} rows to {out_path}")

    print(RULE)
    print(
        "Area and depth only. The remediation schedule is not packaged, so "
        "nothing here is priced."
    )


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
