"""Draw the urban slope failures of one earthquake in one exposure world.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s9_urban_slope_realisation/gen_urban_slope_realisation.py

Run first, over the same extent: step 8 (the model file for each world), the
wall population for each world, shaking step 5 (the PGV field for each
earthquake) and step 1 (the large-model realisation for each earthquake).

For each world ``w`` and earthquake ``r``, following plan section 5.1:

1. Reads the model file for ``w`` and the PGV field for ``r``, and samples PGV
   at each polygon's representative point.
2. Evaluates each row's fragility at that PGV and draws a uniform against it
   from the ``"urban"`` stream seeded on ``r`` and ``w``. A fragility is a
   probability of failure at a level of shaking, and the draw is what decides
   whether each polygon fails. Rows stay in model-file order, sorted by
   ``slope_id``, so a polygon's uniform is tied to its id; every polygon with
   a wall then takes the uniform of the first polygon sharing a wall line
   with it, so a wall on polygons at several scales fails or stands once, at
   the published rate (contract decision 34). The run prints the rate
   setting the model file was built at.
3. Reads the large-model realisation for ``r``. A failed urban polygon whose
   evacuated polygon shares ground with a large-model evacuated polygon is
   superseded: its ground counts once, in the large polygon. A polygon that
   did not fail is never superseded (contract decision 35); a wall a large
   landslide reaches is flagged by vul step 11's line intersection.
4. Resolves nesting largest first among the failed polygons that were not
   superseded: a failed polygon whose evacuated polygon shares ground with a
   larger surviving one is absorbed, as step 1's ``drop_overlapping`` does.
   Supersession comes first so every absorber is a survivor written to the
   combined realisation; otherwise a polygon absorbed by a superseded absorber
   outside the large landslide would be counted nowhere.
5. Writes the evacuated, inundated and imminent polygons of the surviving
   urban failures from their fixed geometry beside the large-model polygons,
   as one combined realisation carrying both ids.
6. Writes the outcome of every wall of world ``w`` on sloping land: standing,
   failed with its polygon, absorbed, or superseded, with the id of the
   polygon that took it. A wall takes the outcome of every polygon whose edge
   carries its line, so a wall split at a property boundary into several
   lines along one polygon edge fails with that polygon on every line.

Two polygons share ground where their intersection has an area above
``realisation.SHARED_GROUND_TOLERANCE_M2``; polygons that only touch along an
edge, as neighbouring candidates of one scale always do, share none.

The library behind it is :mod:`landloss.hazard.landslide.urban.realisation`.
What it runs over, and for which worlds and earthquakes, comes from
``config.py`` beside it.
"""

import sys
from typing import NamedTuple

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, LAND_CLASS_COLUMN
from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation.s1_simulate_landslides import (
    realisation_path,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation import config
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
COMBINED_STEM = "landslide-realisation"
OUTCOME_STEM = "urban-wall-outcome"

# The model file columns that record the rate setting step 8 ran at (contract
# section 3.8), printed by every run.
RATE_SETTING_COLUMN = "rate_setting"
RATE_FACTOR_COLUMN = "rate_factor"

RULE = "-" * 72


def _ids_suffix(world_id, realisation_id, *, extent):
    """The ``-wNNN-rNNN{extent_suffix}`` part every output of a pair carries."""
    suffix = extent_suffix(extent)
    return f"-w{world_id:03d}-r{realisation_id:03d}{suffix}"


def combined_realisation_path(world_id, realisation_id, *, extent):
    """Return the file a run writes the combined realisation of a pair to.

    Args:
        world_id: The exposure world the urban failures were drawn in.
        realisation_id: The modelled earthquake.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    return WORK_DIR / (
        f"{COMBINED_STEM}{_ids_suffix(world_id, realisation_id, extent=extent)}.geoparquet"
    )


def urban_wall_outcome_path(world_id, realisation_id, *, extent):
    """Return the file a run writes the wall outcome table of a pair to.

    Args:
        world_id: The exposure world the walls belong to.
        realisation_id: The modelled earthquake.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    return WORK_DIR / (
        f"{OUTCOME_STEM}{_ids_suffix(world_id, realisation_id, extent=extent)}.parquet"
    )


class Realised(NamedTuple):
    """What one pair's draw resolved to, one entry per model row where indexed."""

    draws: pd.DataFrame
    absorbed_by: np.ndarray
    superseded_by: np.ndarray
    survivors: np.ndarray
    large_evacuated: gpd.GeoDataFrame


def realise(model, pgv, large, rng):
    """Draw the failures of one pair and resolve supersession, then absorption.

    Supersession is found first, on the failed rows only, and mapped onto
    every model row, ``NONE`` where the row did not fail (contract decision
    35). Absorption is then resolved only among the failed rows that were not
    superseded, so every absorber is a survivor and ``taken_by`` always names a
    ``landslide_id`` the combined realisation carries.

    Args:
        model: The world's model file, in its own order.
        pgv: PGV at each row's representative point, on ``model.index``.
        large: The large-model realisation of the earthquake.
        rng: The urban stream of the pair.

    Returns:
        The draws and the resolution of every row, as a :class:`Realised`.
    """
    draws = urban.draw_failures(model, pgv, rng)
    failed = draws[urban.FAILED_COLUMN].to_numpy(dtype=bool)
    evacuated = gpd.GeoSeries(model[urban.EVACUATED_GEOMETRY_COLUMN])

    # Supersession first, on the failed rows only: a polygon that did not fail
    # is standing whatever a large landslide does around it. Mapped back onto
    # every model row so the arrays line up with the file.
    large_evacuated = large[large[LAND_CLASS_COLUMN] == EVACUATED].reset_index(
        drop=True
    )
    failed_rows = np.flatnonzero(failed)
    superseded_by = np.full(len(model), urban.NONE, dtype=np.int64)
    superseded_by[failed_rows] = urban.supersede_by_large(
        evacuated.iloc[failed_rows], large_evacuated.geometry
    )

    # Absorption among the failed rows no large landslide took, so a superseded
    # polygon absorbs nothing; mapped back onto every model row so the arrays
    # line up with the file.
    contenders = np.flatnonzero(failed & (superseded_by == urban.NONE))
    among_contenders = urban.resolve_overlaps(
        evacuated.iloc[contenders],
        evacuated.iloc[contenders].area.to_numpy(dtype=float),
    )
    absorbed_by = np.full(len(model), urban.NONE, dtype=np.int64)
    taken = among_contenders != urban.NONE
    absorbed_by[contenders[taken]] = contenders[among_contenders[taken]]

    survivors = failed & (absorbed_by == urban.NONE) & (superseded_by == urban.NONE)
    return Realised(draws, absorbed_by, superseded_by, survivors, large_evacuated)


def read_inputs(world_id, realisation_id, *, extent):
    """Read the four inputs of one pair, in the order the step reads them.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        ``(model, walls, pgv_m_s, large)``: the model file, the wall
        population, the PGV sampled at each polygon's representative point,
        and the large-model realisation.
    """
    model = gpd.read_parquet(urban_slope_model_path(world_id, extent=extent))
    walls = gpd.read_parquet(wall_population_path(world_id, extent=extent))
    pgv = urban.sample_pgv(
        gpd.GeoSeries(model[urban.REP_POINT_COLUMN]),
        pgv_path(realisation_id, extent=extent),
    )
    large = gpd.read_parquet(
        realisation_path(extent=extent, realisation_id=realisation_id)
    )
    return model, walls, pgv, large


def describe_draw(model, realised):
    """Print what the draw did to the polygons."""
    print(RULE)
    print("Polygons by wall state:")
    print(model[urban.WALL_STATE_COLUMN].value_counts().to_string())
    failed = realised.draws[urban.FAILED_COLUMN].to_numpy(dtype=bool)
    absorbed = realised.absorbed_by != urban.NONE
    superseded = realised.superseded_by != urban.NONE
    p_fail = realised.draws[urban.P_FAIL_COLUMN]
    no_pgv = realised.draws[urban.PGV_COLUMN].isna()
    no_median = model[urban.THETA_COLUMN].isna()
    print(RULE)
    print(f"Failed: {int(failed.sum()):,} of {len(model):,} polygons")
    print(f"  absorbed by a larger failed polygon: {int(absorbed.sum()):,}")
    print(f"  superseded by a large-model landslide: {int(superseded.sum()):,}")
    print(f"  surviving: {int(realised.survivors.sum()):,}")
    if p_fail.isna().any():
        print(f"  not drawn (p_fail NaN): {int(p_fail.isna().sum()):,}")
        print(f"    with no fragility median: {int(no_median.sum()):,}")
        print(f"    off the PGV grid: {int((no_pgv & ~no_median).sum()):,}")


def describe_areas(combined):
    """Print the summed and dissolved areas by population and land class."""
    print(RULE)
    print("Area by population and land class (m2): summed, then dissolved")
    rows = []
    for (population, land_class), group in combined.groupby(
        [urban.POPULATION_COLUMN, LAND_CLASS_COLUMN], sort=True
    ):
        rows.append(
            {
                "population": population,
                "land_class": land_class,
                "polygons": len(group),
                "summed_m2": float(group.geometry.area.sum()),
                "dissolved_m2": float(group.geometry.union_all().area),
            }
        )
    if rows:
        print(pd.DataFrame(rows).to_string(index=False, float_format="{:,.0f}".format))
    else:
        print("  nothing: neither population wrote a polygon")


def describe_outcomes(outcomes):
    """Print the wall outcome counts."""
    print(RULE)
    counts = (
        outcomes[urban.OUTCOME_COLUMN]
        .value_counts()
        .reindex(urban.OUTCOMES, fill_value=0)
    )
    print(f"Wall outcomes over {len(outcomes):,} sloping-land walls:")
    print(counts.to_string())
    without = int(outcomes[urban.SLOPE_ID_COLUMN].isna().sum())
    print(
        f"  walls whose line's polygon was not delineated (slope_id null): {without:,}"
    )


def describe_rate_setting(model):
    """Print the rate setting step 8 built the model at, refusing a mixed file.

    Args:
        model: The world's model file, carrying ``rate_setting`` and
            ``rate_factor``.

    Raises:
        ValueError: If the file carries more than one rate setting.
    """
    settings = model[RATE_SETTING_COLUMN].dropna().unique()
    if len(settings) > 1:
        msg = (
            f"The model file carries {len(settings)} rate settings "
            f"({', '.join(sorted(map(str, settings)))}); step 8 writes one per run."
        )
        raise ValueError(msg)
    factors = model[RATE_FACTOR_COLUMN].dropna().unique()
    setting = settings[0] if len(settings) else None
    factor = ", ".join(f"{value:.4f}" for value in sorted(factors)) or "none"
    print(f"Rate setting {setting!r}, factor {factor} (from the model file)")


def run_pair(world_id, realisation_id, *, extent):
    """Draw, resolve and write one world and earthquake pair."""
    print(RULE)
    print(
        f"World {world_id}, earthquake {realisation_id}, stream {urban.URBAN_STREAM!r}"
    )
    model, walls, pgv, large = read_inputs(world_id, realisation_id, extent=extent)
    describe_rate_setting(model)
    rng = realisation_seed(
        constants.BASE_SEED, realisation_id, urban.URBAN_STREAM, world_id=world_id
    )
    realised = realise(model, pgv, large, rng)
    describe_draw(model, realised)

    urban_rows = urban.to_landslide_rows(model, realised.draws, realised.survivors)
    urban_rows[urban.REALISATION_ID_COLUMN] = realisation_id
    combined = urban.combine_with_large(urban_rows, large)
    combined[urban.WORLD_ID_COLUMN] = world_id
    describe_areas(combined)

    outcomes = urban.wall_outcomes(
        model,
        walls,
        realised.draws,
        realised.absorbed_by,
        realised.superseded_by,
        realised.large_evacuated[urban.LANDSLIDE_ID_COLUMN],
    )
    outcomes.insert(0, urban.REALISATION_ID_COLUMN, realisation_id)
    outcomes.insert(0, urban.WORLD_ID_COLUMN, world_id)
    describe_outcomes(outcomes)

    combined_path = combined_realisation_path(world_id, realisation_id, extent=extent)
    combined_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(combined_path)
    print(f"Wrote {len(combined):,} polygons to {combined_path}")
    outcome_path = urban_wall_outcome_path(world_id, realisation_id, extent=extent)
    outcomes.to_parquet(outcome_path, index=False)
    print(f"Wrote {len(outcomes):,} wall outcomes to {outcome_path}")


def main(*, extent, world_ids, realisation_ids):
    """Draw the urban failures of every world and earthquake pair.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        world_ids: Which exposure worlds to draw for.
        realisation_ids: Which modelled earthquakes to draw for.
    """
    for world_id in world_ids:
        for realisation_id in realisation_ids:
            run_pair(world_id, realisation_id, extent=extent)

    print(RULE)
    print(
        f"Seed {constants.BASE_SEED}, stream {urban.URBAN_STREAM!r}, keyed on the "
        "earthquake and the world; the same pair reproduces exactly."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_ids=config.WORLD_IDS,
        realisation_ids=config.REALISATION_IDS,
    )
