"""Draw the urban slope failures of one earthquake in one exposure world.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s6_urban_slope_realisation/gen_urban_slope_realisation.py

Run first, over the same extent: landslide step 5 (the model file for each
world, on landslide step 4's zones of that world's wall draw), the wall
population for each world (exposure rw step 6, the same draw), shaking step 4
(the site class PGA field for each earthquake) and landslide step 3 (the large-model
realisation for each earthquake).

For each world ``w`` and earthquake ``r``, following plan section 5.1:

1. Reads the model file for ``w`` and the site PGA field for ``r``, and
   samples PGA at each polygon's representative point.
2. Evaluates each row's fragility at that PGA and draws a uniform against it
   from the ``"urban"`` stream seeded on ``r`` and ``w``. A fragility is a
   probability of failure at a level of shaking, and the draw is what decides
   whether each polygon fails. Rows stay in model-file order, sorted by
   ``slope_id``, so a polygon's uniform is tied to its id; every polygon with
   a wall then takes the uniform of the first polygon sharing its wall (the
   wall unit, written as ``wall_line_id``), so a wall under several polygons
   (the segments of its element, or the elements of its unit) fails or stands
   once, at the published rate (contract decision 34). The run prints the rate
   setting the model file was built at.
3. Keeps every failed polygon (the project lead's decision, 2026-10-14). There
   is no absorption between urban polygons and no supersession by a
   large-model landslide, so the same rules as the urban model apply
   throughout. Ground two failures share is written twice and counted once
   downstream, where vul landslide land step 3 measures areas on the union of
   the failures. A polygon that did not fail is standing whatever a large
   landslide does around it (contract decision 35); a wall a large landslide
   reaches is flagged by vul step 11's line intersection.
4. Writes the evacuated, inundated and imminent polygons of the failed urban
   polygons from their fixed geometry beside the large-model polygons, as one
   combined realisation carrying both ids.
5. Writes the outcome of every wall of world ``w`` on sloping land: standing,
   or failed with its polygon. A wall takes the outcome of every polygon on its
   wall unit, a failure first.

The run prints the area of evacuated ground summed and dissolved by population,
so how much of it overlaps stays visible.

The library behind it is :mod:`landloss.hazard.landslide.urban.realisation`.
What it runs over, and for which worlds and earthquakes, comes from
``config.py`` beside it.
"""

import sys

import geopandas as gpd
import pandas as pd

from landloss.domain import constants
from landloss.hazard.landslide.land_class import EVACUATED, LAND_CLASS_COLUMN
from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.realisation import realisation_seed
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation.s1_simulate_landslides import (
    realisation_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation import config
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    pga_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
COMBINED_STEM = "landslide-realisation"
OUTCOME_STEM = "urban-wall-outcome"

# The model file columns that record the rate setting landslide step 5 ran at (contract
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


def realise(model, pga, rng):
    """Draw the failures of one pair; every failed polygon survives.

    Args:
        model: The world's model file, in its own order.
        pga: Site PGA at each row's representative point, on ``model.index``.
        rng: The urban stream of the pair.

    Returns:
        The draws: ``pga_g``, ``p_fail``, ``uniform`` and ``failed`` on
        ``model.index``.
    """
    return urban.draw_failures(model, pga, rng)


def read_inputs(world_id, realisation_id, *, extent):
    """Read the four inputs of one pair, in the order the step reads them.

    Args:
        world_id: The exposure world.
        realisation_id: The modelled earthquake.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        ``(model, walls, pga_g, large)``: the model file, the wall
        population, the site PGA sampled at each polygon's representative point,
        and the large-model realisation.
    """
    model = gpd.read_parquet(urban_slope_model_path(world_id, extent=extent))
    walls = gpd.read_parquet(wall_population_path(world_id, extent=extent))
    pga = urban.sample_pga(
        gpd.GeoSeries(model[urban.REP_POINT_COLUMN]),
        pga_path(realisation_id, extent=extent),
    )
    large = gpd.read_parquet(
        realisation_path(extent=extent, realisation_id=realisation_id)
    )
    return model, walls, pga, large


def describe_draw(model, draws):
    """Print what the draw did to the polygons."""
    print(RULE)
    print("Polygons by wall state:")
    print(model[urban.WALL_STATE_COLUMN].value_counts().to_string())
    failed = draws[urban.FAILED_COLUMN].to_numpy(dtype=bool)
    p_fail = draws[urban.P_FAIL_COLUMN]
    no_pga = draws[urban.PGA_COLUMN].isna()
    no_median = model[urban.THETA_COLUMN].isna()
    print(RULE)
    print(f"Failed: {int(failed.sum()):,} of {len(model):,} polygons, all kept")
    if p_fail.isna().any():
        print(f"  not drawn (p_fail NaN): {int(p_fail.isna().sum()):,}")
        print(f"    with no fragility median: {int(no_median.sum()):,}")
        print(f"    off the PGA grid: {int((no_pga & ~no_median).sum()):,}")


def describe_areas(combined):
    """Print the summed and dissolved areas by population and land class."""
    print(RULE)
    print("Area by population and land class (m2): summed, then dissolved")
    print("  (summed above dissolved is ground more than one polygon covers)")
    rows = []
    for (population, land_class), group in combined.groupby(
        [urban.POPULATION_COLUMN, LAND_CLASS_COLUMN], sort=True
    ):
        summed = float(group.geometry.area.sum())
        dissolved = float(group.geometry.union_all().area)
        rows.append(
            {
                "population": population,
                "land_class": land_class,
                "polygons": len(group),
                "summed_m2": summed,
                "dissolved_m2": dissolved,
                "overlap_m2": summed - dissolved,
            }
        )
    if rows:
        print(pd.DataFrame(rows).to_string(index=False, float_format="{:,.0f}".format))
        evacuated = combined.loc[combined[LAND_CLASS_COLUMN] == EVACUATED].geometry
        summed = float(evacuated.area.sum())
        overlap = summed - float(evacuated.union_all().area)
        share = overlap / summed if summed else 0.0
        print(
            f"Evacuated ground covered more than once, both populations: "
            f"{overlap:,.0f} m2 ({share:.1%} of the summed area)"
        )
    else:
        print("  nothing: neither population wrote a polygon")


def describe_outcomes(outcomes):
    """Print the wall outcome counts."""
    print(RULE)
    counts = (
        outcomes[urban.OUTCOME_COLUMN]
        .value_counts()
        .reindex((urban.STANDING, urban.FAILED_WITH_POLYGON), fill_value=0)
    )
    print(f"Wall outcomes over {len(outcomes):,} sloping-land walls:")
    print(counts.to_string())
    without = int(outcomes[urban.SLOPE_ID_COLUMN].isna().sum())
    print(
        f"  walls whose line's polygon was not delineated (slope_id null): {without:,}"
    )


def describe_rate_setting(model):
    """Print the rate setting landslide step 5 built the model at, refusing a mixed file.

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
            f"({', '.join(sorted(map(str, settings)))}); landslide step 5 writes one per run."
        )
        raise ValueError(msg)
    factors = model[RATE_FACTOR_COLUMN].dropna().unique()
    setting = settings[0] if len(settings) else None
    factor = ", ".join(f"{value:.4f}" for value in sorted(factors)) or "none"
    print(f"Rate setting {setting!r}, factor {factor} (from the model file)")


def run_pair(world_id, realisation_id, *, extent):
    """Draw and write one world and earthquake pair."""
    print(RULE)
    print(
        f"World {world_id}, earthquake {realisation_id}, stream {urban.URBAN_STREAM!r}"
    )
    model, walls, pga, large = read_inputs(world_id, realisation_id, extent=extent)
    describe_rate_setting(model)
    rng = realisation_seed(
        constants.BASE_SEED, realisation_id, urban.URBAN_STREAM, world_id=world_id
    )
    draws = realise(model, pga, rng)
    describe_draw(model, draws)

    urban_rows = urban.to_landslide_rows(model, draws)
    urban_rows[urban.REALISATION_ID_COLUMN] = realisation_id
    combined = urban.combine_with_large(urban_rows, large)
    combined[urban.WORLD_ID_COLUMN] = world_id
    describe_areas(combined)

    outcomes = urban.wall_outcomes(model, walls, draws)
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
