"""Tabulate the fragility medians by Kingsbury zone and wall state for review.

Reads the model file ``gen_urban_slope_fragility.py`` writes for each world
and writes the table the project lead reviews the medians in:

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_urban_slope_fragility/table_urban_slope_model.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_urban_slope_fragility.urban_slope_model_path`` where that run's output
went, so the table cannot summarise a different run from the one last made.

One row per Kingsbury zone and wall state: the polygon count, the median
``theta`` and ``theta_base`` in m/s, the median amplification factor and the
rate factor, so the three parts of every adjusted median can be checked
against plan section 4 side by side. The table goes under
``report/hazard/landslide/urban-slope-model/tab/``.
"""

import sys

import geopandas as gpd

from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import fragility
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import config
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic.
TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-model" / "tab"
TAB_STEM = "urban-slope-model-medians"

ZONE_COLUMN = "kingsbury_zone"
NO_ZONE = "none"

TABLE_COLUMNS = (
    ZONE_COLUMN,
    "zone_label",
    fragility.STATE_COLUMN,
    "fragility_basis",
    "polygons",
    "median_theta_base_m_s",
    "median_amp_factor",
    "rate_factor",
    "median_theta_m_s",
    "median_beta",
)

RULE = "-" * 72


def table_path(world_id, *, extent):
    """Return the CSV a run writes one world's medians to.

    Args:
        world_id: The exposure world the model was built for.
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The table path, under ``report/hazard/landslide/urban-slope-model/tab/``.
    """
    suffix = extent_suffix(extent)
    return TAB_DIR / f"{TAB_STEM}-w{world_id:03d}{suffix}.csv"


def medians_by_zone_and_state(model):
    """Summarise the model's medians per Kingsbury zone and wall state.

    A polygon with no zone (``unknown`` material, so no rating) is grouped
    under ``none`` rather than dropped, because its median is still drawn
    against.
    """
    grouped = model.assign(
        **{
            ZONE_COLUMN: model[ZONE_COLUMN]
            .astype(object)
            .where(model[ZONE_COLUMN].notna(), NO_ZONE)
        }
    ).groupby([ZONE_COLUMN, fragility.STATE_COLUMN, "fragility_basis"], sort=True)
    table = grouped.agg(
        polygons=("theta", "size"),
        median_theta_base_m_s=("theta_base", "median"),
        median_amp_factor=("amp_factor", "median"),
        rate_factor=("rate_factor", "first"),
        median_theta_m_s=("theta", "median"),
        median_beta=("beta", "median"),
    ).reset_index()
    table.insert(
        1,
        "zone_label",
        [
            susceptibility.ZONE_LABELS.get(zone, "no rating")
            for zone in table[ZONE_COLUMN]
        ],
    )
    return table[list(TABLE_COLUMNS)]


def main(*, extent, world_ids):
    """Write the medians table for each world's model file.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
            Must match the setting the generation was run with.
        world_ids: Which worlds' model files to summarise.
    """
    for world_id in world_ids:
        model_path = urban_slope_model_path(world_id, extent=extent)
        print(f"Reading the model from {model_path} ...")
        model = gpd.read_parquet(model_path)
        table = medians_by_zone_and_state(model)

        out_path = table_path(world_id, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_path, index=False, float_format="%.4f")
        print(RULE)
        print(table.to_string(index=False))
        print(RULE)
        print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, world_ids=config.WORLD_IDS)
