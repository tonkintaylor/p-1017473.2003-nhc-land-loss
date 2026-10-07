"""Decide which flat-land retaining walls the shaking wrote off.

Reads one exposure world's wall population and one earthquake's PGV field,
keeps the walls on flat land, evaluates each wall's type fragility curve at
the PGV it saw, and draws a damage state per wall against that probability.

    uv run --frozen python src/scripts/landloss/vul/shaking/rw/steps/s9_wall_damage_state/gen_wall_damage_state.py

Run exposure rw step 6 (``gen_wall_population.py``), shaking steps 2, 3 and 5
(``gen_site_class.py``, ``gen_pgv.py``, ``gen_pgv_realisations.py``) first,
over the same extent.

**Flat-land walls only.** A wall on sloping land stands on the edge of an urban
failure polygon, and whether it fails is decided with that polygon by landslide
step 9 (``s9_urban_slope_realisation``); drawing it here as well would fail it
twice. A wall on NLM flat land has no polygon, so it is drawn here, on its
wall type curve, and nowhere else.

Two damage states only, **no damage** and **replace**. Repair is not modelled
because very few damaged walls are repaired in practice, so the state is a coin
weighted by the fragility rather than a position on a scale. The fragility
returns a **probability of failure at the ground motion the wall saw**, which is
what a fragility curve is, and the state is a draw against it.

The curve is the ``retaining-wall-type-fragility.csv`` row for the wall's type
and height class (under 2 m, or 2 m and over, from its ``height_m``; the lead,
2026-10-07), its PGA median scaled by the wall's position (0.85 retaining
fill, 1.15 retaining a cut, unchanged where unknown). It is converted from PGA
to PGV at the wall's own PGV/PGA ratio: step
3's PGV grid over the unscaled TS1170.5 PGA grid at ``RETURN_PERIOD_YR``, both
on the step 2 site class grid, sampled at the wall's midpoint. The ratio does
not depend on the realisation, because steps 4 and 5 scale PGA and PGV by one
factor, and it is written on every row so the conversion is on the record.

**No cost is attached.** The loss module prices a written-off wall from its
undepreciated value, so what this writes is the state, not the money.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import pandas as pd
import rioxarray

from landloss.common.utils.terrain import sample_at_points
from landloss.domain import constants
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    REALISATION_ID_COLUMN,
    RW_ID_COLUMN,
)
from landloss.exposure.rw.wall_type import AGE_BIN_COLUMN
from landloss.hazard.landslide.urban import fragility as urban_fragility
from landloss.hazard.landslide.urban.wall_type_fragility import (
    height_class,
    load_wall_type_fragility,
)
from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.site_class import demand_on_site_class_grid
from landloss.io.area_of_interest import extent_suffix
from landloss.io.ts1170 import get_ts1170_pga
from landloss.vul.shaking.fragility import (
    DAMAGE_STATE_COLUMN,
    FAILURE_PROBABILITY_COLUMN,
    HEIGHT_M_COLUMN,
    PGV_IM,
    PGV_PGA_RATIO_COLUMN,
    REPLACE,
    SIZE_CLASS_COLUMN,
    THETA_BASE_PGA_G_COLUMN,
    THETA_COLUMN,
    WALL_FRAGILITY_COLUMNS,
    WALL_POSITION_COLUMN,
    WALL_TYPE_COLUMN,
    draw_damage_states,
    wall_failure_probability,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    read_site_class,
    site_class_path,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.vul.shaking.rw.steps.s9_wall_damage_state import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "vul"
OUT_STEM = "wall-damage-state"

# One stream for the whole vulnerability module, so that adding a hazard or an
# asset class does not shift the draws of the ones already there. The world is
# appended to the seed, so two worlds' populations draw independently.
RNG_STREAM = "vulnerability"

ASSET = "retaining wall"
ASSET_COLUMN = "asset"
WORLD_ID_COLUMN = "world_id"
IS_FLATLAND_COLUMN = "is_flatland"
PGV_COLUMN = PGV_IM
SITE_CLASS_COLUMN = "site_class"

# The population columns carried through unchanged, in output order.
POPULATION_COLUMNS = [
    RW_ID_COLUMN,
    CLAIM_ID_COLUMN,
    SIZE_CLASS_COLUMN,
    WALL_TYPE_COLUMN,
    AGE_BIN_COLUMN,
    WALL_POSITION_COLUMN,
    HEIGHT_M_COLUMN,
    "length_m",
    IS_FLATLAND_COLUMN,
]

OUT_COLUMNS = [
    REALISATION_ID_COLUMN,
    WORLD_ID_COLUMN,
    *POPULATION_COLUMNS[:2],
    ASSET_COLUMN,
    *POPULATION_COLUMNS[2:],
    PGV_COLUMN,
    SITE_CLASS_COLUMN,
    *WALL_FRAGILITY_COLUMNS,
    DAMAGE_STATE_COLUMN,
]

RULE = "-" * 72


def wall_damage_state_path(world_id, realisation_id, *, extent):
    """Return the file a run writes one world's and earthquake's wall states to.

    Args:
        world_id: Which exposure world the walls were drawn in.
        realisation_id: Which modelled earthquake this is.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/vul/``.
    """
    suffix = extent_suffix(extent)
    return (
        WORK_DIR
        / f"{OUT_STEM}-w{world_id:03d}-r{realisation_id:03d}{suffix}.geoparquet"
    )


def read_grid(path):
    """Read one raster a shaking step wrote, nodata masked to NaN."""
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def flat_land_walls(walls):
    """Keep the walls on NLM flat land, in population order."""
    return walls[walls[IS_FLATLAND_COLUMN].to_numpy(dtype=bool)]


def midpoints(walls):
    """Return the point each wall is sampled at.

    A wall is a line; it is sampled at its midpoint, which is within a few
    metres of either end at these lengths and well inside one cell of the
    100 m shaking grids.
    """
    return walls.geometry.interpolate(0.5, normalized=True)


def sample_site_class(points, *, extent):
    """Read the TS1170.5 site class at each point, null off the grid."""
    sampled = sample_at_points(site_class_path(extent=extent), points)
    return sampled.round().astype("Int64")


def build_states(
    walls, *, world_id, realisation_id, pgv_m_s, site_class, pgv_pga_ratio, table
):
    """Evaluate the curves and draw the states for one world and earthquake.

    Args:
        walls: The flat-land walls of the world, in population order.
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        pgv_m_s: The PGV sampled at each wall's midpoint, on ``walls.index``.
        site_class: The site class at each midpoint, on ``walls.index``.
        pgv_pga_ratio: The PGV/PGA ratio at each midpoint, on ``walls.index``.
        table: The wall fragility table.

    Returns:
        The states frame with the columns of :data:`OUT_COLUMNS` and the wall
        line as geometry.
    """
    fragility = wall_failure_probability(
        walls, pgv_m_s.to_numpy(dtype=float), table, pgv_pga_ratio=pgv_pga_ratio
    )
    # Rows stay in population order, which step 6 sorts by claim and location,
    # so each wall's draw is tied to its rw_id.
    rng = realisation_seed(
        constants.BASE_SEED, realisation_id, RNG_STREAM, world_id=world_id
    )
    states = gpd.GeoDataFrame(
        {
            REALISATION_ID_COLUMN: realisation_id,
            WORLD_ID_COLUMN: world_id,
            **{column: walls[column].to_numpy() for column in POPULATION_COLUMNS[:2]},
            ASSET_COLUMN: ASSET,
            **{column: walls[column].to_numpy() for column in POPULATION_COLUMNS[2:]},
            PGV_COLUMN: pgv_m_s.to_numpy(dtype=float),
            SITE_CLASS_COLUMN: pd.array(site_class.to_numpy(), dtype="Int64"),
            **{
                column: fragility[column].to_numpy()
                for column in WALL_FRAGILITY_COLUMNS
            },
            DAMAGE_STATE_COLUMN: draw_damage_states(
                fragility[FAILURE_PROBABILITY_COLUMN].to_numpy(), rng
            ),
        },
        # The wall line rides through so the loss table carries coordinates.
        geometry=walls.geometry.to_numpy(),
        crs=walls.crs,
    )
    return states[[*OUT_COLUMNS, "geometry"]]


def describe_population(walls, flat):
    """Print how many of the world's walls are on flat land, and so drawn here."""
    print(RULE)
    share = len(flat) / len(walls) if len(walls) else 0.0
    print(
        f"Walls in the population: {len(walls):,}; on flat land {len(flat):,} "
        f"({share:.1%}), drawn here. The rest are drawn with their polygon by "
        "landslide step 9."
    )


def describe_states(states):
    """Print how the flat-land walls split, and what they were drawn against."""
    print(RULE)
    print(f"Flat-land retaining walls: {len(states):,}")
    if states.empty:
        return

    counts = states[DAMAGE_STATE_COLUMN].value_counts()
    for state, count in counts.items():
        print(f"  {state}: {count:,} ({100 * count / len(states):.1f}%)")

    pgv = states[PGV_COLUMN]
    outside = int(pgv.isna().sum())
    if outside:
        print(f"  {outside:,} walls fall outside the PGV field")
    if pgv.notna().any():
        print(f"  PGV {pgv.min():.3f} to {pgv.max():.3f} m/s over the walls")
    unevaluated = int(states[FAILURE_PROBABILITY_COLUMN].isna().sum())
    if unevaluated:
        print(
            f"  {unevaluated:,} walls carry no failure probability (no PGV or no "
            "PGV/PGA ratio at the midpoint) and draw no damage"
        )

    converted = states[states[THETA_BASE_PGA_G_COLUMN].notna()]
    ratio = converted[PGV_PGA_RATIO_COLUMN]
    ratio_range = (
        f"{ratio.min():.3f} to {ratio.max():.3f} m/s per g"
        if ratio.notna().any()
        else "NaN"
    )
    print(
        f"  {len(converted):,} walls on PGA curves, converted at a "
        f"PGV/PGA ratio of {ratio_range}"
    )
    print("  median theta (m/s) by wall type and height class:")
    by_curve = states.groupby(
        [states[WALL_TYPE_COLUMN], height_class(states[HEIGHT_M_COLUMN])]
    )
    print(by_curve[THETA_COLUMN].median().to_string())

    replaced = states[states[DAMAGE_STATE_COLUMN] == REPLACE]
    print(
        f"  {replaced[CLAIM_ID_COLUMN].nunique():,} properties carry at least one "
        "wall to replace"
    )


def main(*, extent, world_ids, realisation_ids, return_period_yr):
    """Write a damage state per flat-land wall, per world and earthquake.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        world_ids: Which exposure worlds to read the wall population of.
        realisation_ids: Which modelled earthquakes to draw states for.
        return_period_yr: The return period of the TS1170.5 demand the PGV/PGA
            ratio is taken at.
    """
    table = load_wall_type_fragility()

    # The ratio is realisation-free: step 3's PGV over the unscaled PGA, both on
    # the site class grid, so it is built once for every world and earthquake.
    site_class = read_site_class(extent=extent)
    print(f"Reading the TS1170.5 PGA grids at {return_period_yr} years ...")
    pga = demand_on_site_class_grid(
        get_ts1170_pga, site_class, return_period_yr=return_period_yr
    )
    pgv_grid = read_grid(
        output_path("pgv", return_period_yr=return_period_yr, extent=extent)
    )

    for world_id in world_ids:
        walls = gpd.read_parquet(wall_population_path(world_id, extent=extent))
        flat = flat_land_walls(walls)
        describe_population(walls, flat)
        points = midpoints(flat)
        site_class_at = sample_site_class(points, extent=extent)
        ratio = urban_fragility.pgv_pga_ratio_m_s_per_g(pgv_grid, pga, points)

        for realisation_id in realisation_ids:
            raster = pgv_path(realisation_id, extent=extent)
            print(RULE)
            print(
                f"World {world_id}, realisation {realisation_id}, stream "
                f"{RNG_STREAM!r}; reading the PGV field from {raster}"
            )
            states = build_states(
                flat,
                world_id=world_id,
                realisation_id=realisation_id,
                pgv_m_s=sample_at_points(raster, points),
                site_class=site_class_at,
                pgv_pga_ratio=ratio,
                table=table,
            )
            describe_states(states)

            out_path = wall_damage_state_path(world_id, realisation_id, extent=extent)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            states.to_parquet(out_path)
            print(f"Wrote {len(states):,} rows to {out_path}")

    print(RULE)
    print(
        "States only, for walls on flat land. Walls on sloping land are drawn "
        "with their polygon by landslide step 9, and a written-off wall is "
        "priced from its undepreciated value in the loss module."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
