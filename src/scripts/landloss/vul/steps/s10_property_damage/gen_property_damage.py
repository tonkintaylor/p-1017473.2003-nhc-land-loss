"""Write the four tables the vulnerability module hands to the loss module.

The contract in section 1 of ``.agents/plans/asset-pricing-approach.md`` has vul
hand loss four tables per exposure world and earthquake, each row carrying its
own asset id, the ``claim_id`` of the LINZ property it belongs to and its
coordinates:

- **land**, one row per insured land polygon, with its liquefaction land
  damage state, its landslide damaged areas and what loss values the land
  from: the footprint, property area and suburb;
- **rw**, one row per insured retaining wall for each claim whose insured land
  it supports, at the length of the wall that does, with its size, shaking
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
the urban slope outcome. A wall is then split onto the claims whose insured land
it supports, at each one's insured stretch from exposure rw step 6; length that
supports no insured land is not priced.

**Each piece also carries how much of it is damaged** (T-158), in
``rw_damaged_length``, an extra column outside the contract. A wall damaged by
shaking is damaged over its whole length. A wall damaged by landslide ground is
damaged over the part of its line inside evacuated ground (the wall landslide
step's ``damaged_line``), cut by each claim's insured stretch, so a claim takes
only the damaged length on its own stretch, and a damaged part on a boundary two
claims share is shared between them. A piece with 0.1 m or less of damage is
undamaged and loses its flags. Inundated ground does not damage a wall.

The run also prints the overlap four tables hide: how many claims carry both a
liquefaction land damage state and a retaining wall damaged by shaking. Both
are priced: the project lead ruled on 2026-10-02 that a wall replaced by
shaking on flat land and the liquefaction land damage on the same claim are not
a double count (**T-27**, retaining walls; culverts and bridges are still to be
confirmed).

**A slip's new wall is the mapped wall where there is one** (section 4 of the
property damage tweaks). For each failure no damaged wall holds, the land table
also lists, in the order of ``landslide_ids``, the height, length and source of
the wall loss builds for it (``landslide_wall_heights``,
``landslide_wall_lengths``, ``landslide_wall_sources``): the face height of the
wall unit its polygon stands on, the length of that unit's stretch on the claim
alongside the failure's evacuated ground, and ``mapped wall``; or ``slip`` where
no mapped wall can be used, and loss sizes the wall from the slip. The unit is
reached through the failure's ``slope_id`` in the realisation and the urban
slope model's ``wall_line_id``, so the wall need not have been drawn in the
world; the stretches are exposure rw step 6's ``wall-candidate-stretches``.

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
    IMMINENT_EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
    IS_DAMAGED_BY_SHAKING_COLUMN,
    IS_DAMAGED_COLUMN,
    IS_EVACUATED_COLUMN,
    IS_INUNDATED_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_WALL_SOURCES_COLUMN,
    LIQ_LD_STATE_COLUMN,
    MAPPED_WALL,
    REALISATION_ID_COLUMN,
    REINUNDATED_AREA_COLUMN,
    REINUNDATED_VOLUME_COLUMN,
    RW_DAMAGED_LENGTH_COLUMN,
    RW_ID_COLUMN,
    RW_LENGTH_COLUMN,
)
from landloss.exposure.land.extent import DWELLING_COUNT_COLUMN
from landloss.exposure.rw.population import HEIGHT_SOURCE_COLUMN, WALL_LINE_ID_COLUMN
from landloss.hazard.landslide.urban.geometry import SLOPE_ID_COLUMN
from landloss.io.area_of_interest import extent_suffix
from landloss.vul.landslide.land.damaged_area import (
    LANDSLIDE_ID_COLUMN,
    evacuated_ground_per_failure,
)
from landloss.vul.loss_input import (
    LOSS_TABLES,
    PARENT_RW_ID_COLUMN,
    WORLD_ID_COLUMN,
    build_crossing_tables,
    build_land_table,
    build_rw_table,
)
from landloss.vul.mapped_walls import attach_mapped_walls
from landloss.vul.shaking.fragility import DAMAGE_STATE_COLUMN
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    candidate_stretches_path,
    insured_stretches_path,
    wall_population_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_probability import (
    wall_probability_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
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
    if IMMINENT_EVACUATED_AREA_COLUMN in land.columns:
        # Carried for the viewer; loss settles none of it.
        print(
            f"  Imminent evacuated ground: "
            f"{land[IMMINENT_EVACUATED_AREA_COLUMN].sum():,.0f} m2; re-inundated "
            f"ground: {land[REINUNDATED_AREA_COLUMN].sum():,.0f} m2, "
            f"{land[REINUNDATED_VOLUME_COLUMN].sum():,.0f} m3 (not settled)"
        )


def describe_mapped_walls(land):
    """Print how many failures get a new wall on a mapped wall, and how many a slip."""
    if LANDSLIDE_WALL_SOURCES_COLUMN not in land.columns:
        return
    sources = [
        source for listed in land[LANDSLIDE_WALL_SOURCES_COLUMN] for source in listed
    ]
    mapped = sum(source == MAPPED_WALL for source in sources)
    print(
        f"  {mapped:,} of {len(sources):,} landslide entries have a mapped wall to "
        "build on (the rest are held by a damaged wall or sized from the slip)"
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


def describe_walls(rw, states, walls):
    """Print how the wall table splits between the two shaking routes.

    Args:
        rw: The rw table, one row per piece.
        states: The shaking step's damage states.
        walls: The world's wall population, to count the walls that give no piece.
    """
    gave_no_piece = int((~walls[RW_ID_COLUMN].isin(rw[PARENT_RW_ID_COLUMN])).sum())
    print(f"  {gave_no_piece:,} population walls give no piece (no insured stretch)")
    if rw.empty:
        return
    walls = rw.drop_duplicates(PARENT_RW_ID_COLUMN)
    with_state = walls[PARENT_RW_ID_COLUMN].isin(states[RW_ID_COLUMN])
    print(
        f"  {int(with_state.sum()):,} walls carry a shaking damage state (flat "
        f"land); {int((~with_state).sum()):,} take their shaking flag from the "
        "urban slope outcome"
    )
    pieces = rw.groupby(PARENT_RW_ID_COLUMN).size()
    split = pieces[pieces > 1]
    print(
        f"  {len(split):,} of {len(walls):,} walls support more than one claim's "
        f"insured land and are split into {int(split.sum()):,} rows, one per claim"
    )
    if RW_DAMAGED_LENGTH_COLUMN in rw.columns:
        damaged = rw[RW_DAMAGED_LENGTH_COLUMN] > 0
        shaken = rw[IS_DAMAGED_BY_SHAKING_COLUMN]
        print(
            f"  {int(damaged.sum()):,} pieces are damaged, over "
            f"{rw.loc[damaged, RW_DAMAGED_LENGTH_COLUMN].sum():,.0f} m of "
            f"{rw.loc[damaged, RW_LENGTH_COLUMN].sum():,.0f} m; "
            f"{int((damaged & ~shaken).sum()):,} by landslide ground alone, over "
            f"{rw.loc[damaged & ~shaken, RW_DAMAGED_LENGTH_COLUMN].sum():,.0f} m "
            f"of {rw.loc[damaged & ~shaken, RW_LENGTH_COLUMN].sum():,.0f} m"
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
    candidate_stretches = gpd.read_parquet(candidate_stretches_path(extent=extent))
    wall_heights = pd.read_parquet(
        wall_probability_path(extent=extent),
        columns=[WALL_LINE_ID_COLUMN, HEIGHT_SOURCE_COLUMN],
    ).set_index(WALL_LINE_ID_COLUMN)[HEIGHT_SOURCE_COLUMN]

    for world_id in world_ids:
        walls = gpd.read_parquet(wall_population_path(world_id, extent=extent))
        # The unit each polygon of the urban slope model stands on, drawn or not.
        model = pd.read_parquet(
            urban_slope_model_path(world_id, extent=extent),
            columns=[SLOPE_ID_COLUMN, WALL_LINE_ID_COLUMN],
        )
        wall_line_of_slope = model.set_index(SLOPE_ID_COLUMN)[WALL_LINE_ID_COLUMN]
        stretches = gpd.read_parquet(insured_stretches_path(world_id, extent=extent))
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
            # A wall is split onto each claim whose insured land it supports, at
            # its insured stretch there, so each settles its own share.
            rw = build_rw_table(
                walls,
                states,
                pd.read_parquet(
                    wall_landslide_damage_path(world_id, realisation_id, extent=extent)
                ),
                claims=set(insured[CLAIM_ID_COLUMN]),
                # Each claim's damaged length is its own stretch's.
                stretches=stretches,
            )
            # What each failure no damaged wall holds is built with: the mapped
            # wall where there is one, else the slip (section 4).
            landslides = gpd.read_parquet(
                combined_realisation_path(world_id, realisation_id, extent=extent)
            )
            land = attach_mapped_walls(
                land,
                rw,
                slope_ids=landslides.drop_duplicates(LANDSLIDE_ID_COLUMN).set_index(
                    LANDSLIDE_ID_COLUMN
                )[SLOPE_ID_COLUMN],
                wall_line_of_slope=wall_line_of_slope,
                height_of_wall_line=wall_heights,
                candidate_stretches=candidate_stretches,
                evacuated_ground=evacuated_ground_per_failure(
                    insured, landslides, id_column=CLAIM_ID_COLUMN
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
            describe_mapped_walls(land)
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
            describe_walls(rw, states, walls)
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
