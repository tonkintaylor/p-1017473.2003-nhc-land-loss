"""Write the four tables the vulnerability module hands to the loss module.

The contract in section 1 of ``.agents/plans/asset-pricing-approach.md`` has vul
hand loss four tables per exposure world and earthquake, each row carrying its
own asset id, the ``claim_id`` of the LINZ property it belongs to and its
coordinates:

- **land**, one row per insured land polygon, with its liquefaction land
  damage state, its landslide damaged areas and what loss values the land
  from: the footprint, property area and suburb;
- **rw**, one row per insured retaining wall, with its size, length, shaking
  damage and landslide flags;
- **culverts** and **bridges**, split from the detected crossings by structure
  kind, with their shaking damage and landslide flags.

This step builds them from the earlier vul steps' outputs:

    uv run --frozen python src/scripts/landloss/vul/steps/s10_property_damage/gen_property_damage.py

It adds **no modelling**. The assembly lives in :mod:`landloss.vul.loss_input`
and every number it writes was decided by the step it came from. The geometry,
in EPSG:2193, supplies the coordinates, and each table carries a
``realisation_id`` and a ``world_id``.

The retaining wall table is spined on the world's wall population, so a wall on
sloping ground, which the shaking step never sees, appears beside the flat-land
walls it does; its shaking flag comes from the wall landslide step's reading of
the urban slope outcome.

The run also prints the overlap four tables hide: how many claims carry both a
liquefaction land damage state and a retaining wall damaged by shaking. Both
are priced: the project lead ruled on 2026-10-02 that a wall replaced by
shaking on flat land and the liquefaction land damage on the same claim are not
a double count (**T-27**, retaining walls; culverts and bridges are still to be
confirmed).

**Nothing is settled.** Caps, excesses, GST and pricing belong to the loss
module, which this step does not touch.

What it runs over comes from ``config.py`` beside it.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from landloss.domain.constants import DEFAULT_CRS
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_DAMAGED_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LIQ_LD_STATE_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
)
from landloss.exposure.land.extent import DWELLING_COUNT_COLUMN
from landloss.io.area_of_interest import extent_suffix
from landloss.vul.loss_input import (
    LOSS_TABLES,
    WORLD_ID_COLUMN,
    build_crossing_tables,
    build_land_table,
    build_rw_table,
)
from landloss.vul.shaking.fragility import DAMAGE_STATE_COLUMN
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.landslide.culverts_bridges.steps.s11_crossing_landslide_damage.gen_crossing_landslide_damage import (
    crossing_landslide_damage_path,
)
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage.gen_landslide_land_damage import (
    landslide_land_damage_path,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage.gen_wall_landslide_damage import (
    wall_landslide_damage_path,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage.gen_liq_land_damage import (
    AREA_COST_COLUMN,
    liq_land_damage_path,
)
from scripts.landloss.vul.shaking.culverts_bridges.steps.s9_structure_damage_state.gen_structure_damage_state import (
    structure_damage_state_path,
)
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state.gen_wall_damage_state import (
    wall_damage_state_path,
)
from scripts.landloss.vul.steps.s10_property_damage import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "loss-input"

RULE = "-" * 72


def world_loss_input_path(
    table: str, world_id: int, realisation_id: int, *, extent: str
) -> Path:
    """Return the file a run writes one world and earthquake's contract table to.

    Every vul caller reads and writes the four tables through this function.
    ``world_id`` is positional with no default, so no caller can fall back on a
    world silently.

    Args:
        table: The contract table, one of ``LOSS_TABLES``.
        world_id: The exposure world (one draw of the wall population) the file holds.
        realisation_id: The earthquake realisation the file holds.
        extent: The extent the run covers, a name from
            landloss.io.area_of_interest.EXTENTS or "full". It sets the
            file name suffix through ``extent_suffix``.

    Returns:
        The geoparquet path under the vul work directory.

    Raises:
        ValueError: If ``table`` is not one of the four contract tables.
    """
    if table not in LOSS_TABLES:
        msg = f"unknown loss table {table!r}, expected one of {LOSS_TABLES}"
        raise ValueError(msg)
    suffix = extent_suffix(extent)
    return (
        WORK_DIR / f"{OUT_STEM}-{table}-w{world_id:03d}-r{realisation_id:03d}"
        f"{suffix}.geoparquet"
    )


def in_default_crs(table: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    """Return ``table`` in EPSG:2193, refusing one with no CRS at all."""
    if table.crs is None:
        msg = f"the {name} table has no CRS, so its coordinates cannot be trusted"
        raise ValueError(msg)
    return table if table.crs == DEFAULT_CRS else table.to_crs(DEFAULT_CRS)


def describe_land(land):
    """Print the land table's polygons, claims, states and landslide areas."""
    print(RULE)
    if land.empty:
        print("Land: no insured land polygons.")
        return
    print(
        f"Land: {len(land):,} polygons on {land[CLAIM_ID_COLUMN].nunique():,} "
        f"claims, {int(land[DWELLING_COUNT_COLUMN].sum()):,} dwellings"
    )
    states = land[LIQ_LD_STATE_COLUMN].dropna()
    if states.empty:
        print("  No liquefaction land damage state on any polygon")
    else:
        print(f"  {len(states):,} polygons carry a liquefaction land damage state:")
        for state, polygons in states.value_counts().sort_index().items():
            print(f"    {state}: {polygons:,}")

    # The contract takes the union of evacuated and inundated ground, so ground
    # both evacuated and buried is counted once. The gap below is what adding
    # the two would have double counted.
    union = land[LANDSLIDE_AREA_COLUMN].sum()
    added = land[EVACUATED_AREA_COLUMN].sum() + land[INUNDATED_AREA_COLUMN].sum()
    reached = int((land[LANDSLIDE_AREA_COLUMN] > 0).sum())
    print(
        f"  Landslide damaged ground: {union:,.0f} m2 on {reached:,} polygons, "
        f"against {added:,.0f} m2 if evacuated and inundated were added "
        f"({added - union:,.0f} m2 not double counted)"
    )


def describe_structures(name, table, flags):
    """Print how many structures one table holds and how many carry each flag."""
    if table.empty:
        print(f"{name}: none")
        return
    counts = ", ".join(f"{int(table[flag].sum()):,} {flag}" for flag in flags)
    print(
        f"{name}: {len(table):,} on {table[CLAIM_ID_COLUMN].nunique():,} claims, {counts}"
    )


def describe_walls(rw, states):
    """Print how the wall table splits between the two shaking routes."""
    if rw.empty:
        return
    with_state = rw[RW_ID_COLUMN].isin(states[RW_ID_COLUMN])
    print(
        f"  {int(with_state.sum()):,} walls carry a shaking damage state (flat "
        f"land); {int((~with_state).sum()):,} take their shaking flag from the "
        "urban slope outcome"
    )


def describe_overlap(land, rw):
    """Print how many claims carry both a liquefaction state and a wall to replace.

    Printed for information. The project lead ruled on 2026-10-02 that a wall
    replaced by shaking on flat land and the liquefaction land damage on the
    same claim are not a double count (**T-27**, retaining walls), so both are
    priced.
    """
    with_state = set(land.loc[land[LIQ_LD_STATE_COLUMN].notna(), CLAIM_ID_COLUMN])
    with_wall = set(rw.loc[rw[IS_DAMAGED_BY_SHAKING_COLUMN], CLAIM_ID_COLUMN])
    both = len(with_state & with_wall)
    print(RULE)
    print(
        f"{both:,} claims carry both a liquefaction land damage state and a wall "
        "damaged by shaking; both are priced, which is not a double count "
        "(T-27, the project lead, 2026-10-02)"
    )
    print(
        "Nothing here is settled. Caps, excesses, GST and the market value of "
        "the damaged land belong to the loss module."
    )


def main(*, extent, world_ids, realisation_ids):
    """Write the four contract tables, per world and earthquake.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: The exposure worlds to run, each one draw of the wall population.
        realisation_ids: The earthquake realisations to run in every world.
    """
    insured = gpd.read_parquet(insured_land_path(extent=extent))

    for world_id in world_ids:
        walls = gpd.read_parquet(wall_population_path(world_id, extent=extent))
        for realisation_id in realisation_ids:
            print(RULE)
            print(f"Assembling world {world_id}, realisation {realisation_id} ...")
            land = build_land_table(
                insured,
                pd.read_parquet(liq_land_damage_path(realisation_id, extent=extent)),
                pd.read_parquet(
                    landslide_land_damage_path(world_id, realisation_id, extent=extent)
                ),
                # The liquefaction cost settled is the one priced from the ground
                # each claim lost, at rates fitted to the Canterbury claimant-only
                # means (T-57, T-65), not the per-state percentile lookup.
                ld_cost_column=AREA_COST_COLUMN,
            )
            states = pd.read_parquet(
                wall_damage_state_path(world_id, realisation_id, extent=extent),
                columns=[RW_ID_COLUMN, DAMAGE_STATE_COLUMN],
            )
            rw = build_rw_table(
                walls,
                states,
                pd.read_parquet(
                    wall_landslide_damage_path(world_id, realisation_id, extent=extent)
                ),
            )
            culverts, bridges = build_crossing_tables(
                gpd.read_parquet(
                    structure_damage_state_path(realisation_id, extent=extent)
                ),
                pd.read_parquet(
                    crossing_landslide_damage_path(
                        world_id, realisation_id, extent=extent
                    )
                ),
            )
            tables = dict(zip(LOSS_TABLES, (land, rw, culverts, bridges), strict=True))

            describe_land(land)
            print(RULE)
            describe_structures(
                "Retaining walls",
                rw,
                (
                    IS_DAMAGED_BY_SHAKING_COLUMN,
                    IS_EVACUATED_COLUMN,
                    IS_INUNDATED_COLUMN,
                ),
            )
            describe_walls(rw, states)
            describe_structures(
                "Culverts",
                culverts,
                (IS_DAMAGED_COLUMN, IS_EVACUATED_COLUMN, IS_INUNDATED_COLUMN),
            )
            describe_structures(
                "Bridges",
                bridges,
                (
                    IS_DAMAGED_BY_SHAKING_COLUMN,
                    IS_EVACUATED_COLUMN,
                    IS_INUNDATED_COLUMN,
                ),
            )
            describe_overlap(land, rw)

            for name, table in tables.items():
                table = in_default_crs(table, name)
                table.insert(0, REALISATION_ID_COLUMN, realisation_id)
                table.insert(1, WORLD_ID_COLUMN, world_id)
                out_path = world_loss_input_path(
                    name, world_id, realisation_id, extent=extent
                )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                table.to_parquet(out_path)
                print(f"Wrote {len(table):,} {name} rows to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
