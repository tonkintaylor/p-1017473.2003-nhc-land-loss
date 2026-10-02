"""Cut the slope units the large landslide model places its failures in.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s5_slope_units/gen_slope_units.py

The run settings -- the extent, the channel threshold and the thresholds the
sensitivity is reported over, the aspect merge tolerance and the unit area
bounds -- come from config.py beside this script rather than from the command
line.

A slope unit is one hillslope facet, from a drainage line at the bottom to the
ridge at the top, with one broad aspect, of the order of 1 to 100 ha. It is the
unit a large failure is placed in by landslide step 1, not the unit the large
models are fitted on. The delineation is the ``r.slopeunits`` logic of
[alvioli_2016], run by :func:`landloss.hazard.landslide.slope_units.delineate_slope_units`
on the 10 m DEM, slope and aspect step 3 wrote: flow routing, a channel network
at the threshold, the sub-basin of each channel link split into a left and a
right half-basin, neighbours of similar aspect merged, and anything over the
maximum area split by the variance of its aspect. Units are cut over the whole
extent and none is dropped: each carries the share of its area on the National
Liquefaction Model flatland, read from the step 4 ground map, and the
realisation step places failures only where its coverage raster has a value.

The run cuts the units once per threshold in ``CHANNEL_THRESHOLDS_TRIED_HA`` and
prints the unit count and median area at each, so the choice of threshold is
reported with every run; the layer written is the one at ``CHANNEL_THRESHOLD_HA``.

Writes ``slope-units{extent_suffix}.geoparquet`` under temp/hazard/landslide/, one row
per ``unit_id``, with the columns of contract section 3.3.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.hazard.landslide.slope_units import M2_PER_HA, delineate_slope_units
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_multiscale_slope,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s5_slope_units import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. The units are a working layer, rebuilt from step 3's
# rasters and step 4's ground map, so they have no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "slope-units"

# The cell size of the step 3 rasters the units are cut on.
RESOLUTION_M = 10

# The ground map column that marks the NLM flatland.
FLATLAND_COLUMN = "is_flatland"

# The columns of the written layer, in order (contract section 3.3).
OUTPUT_COLUMNS = [
    "unit_id",
    "basin_id",
    "side",
    "area_m2",
    "mean_slope_degrees",
    "mean_aspect_degrees",
    "aspect_sd_degrees",
    "min_elevation_m",
    "max_elevation_m",
    "relief_m",
    "flatland_share",
    "channel_threshold_ha",
    "geometry",
]

DECILES = (0.1, 0.5, 0.9)

RULE = "-" * 72


def slope_units_path(*, extent):
    """Return the file the slope units are written to."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def input_paths(*, extent):
    """Return the step 3 rasters and the step 4 ground map this step reads."""
    return {
        "dem": gen_multiscale_slope.dem_path(RESOLUTION_M, extent=extent),
        "slope": gen_multiscale_slope.slope_path(RESOLUTION_M, extent=extent),
        "aspect": gen_multiscale_slope.aspect_path(RESOLUTION_M, extent=extent),
        "ground_map": ground_map_path(extent=extent),
    }


def read_grid(path):
    """Read one raster step 3 wrote, nodata as NaN, as a 2D array."""
    with rioxarray.open_rasterio(path, masked=True) as opened:
        grid = opened.squeeze("band", drop=True).load()
    grid.encoding.pop("_FillValue", None)
    return grid.rio.write_nodata(np.nan)


def flatland_share(units, ground_map):
    """Return the share of each unit's area on the NLM flatland, 0 to 1.

    The flatland is the union of the ground map polygons flagged
    ``is_flatland``; the share is the area of each unit inside it over the
    unit's own area.
    """
    flat = ground_map.loc[ground_map[FLATLAND_COLUMN].astype(bool)]
    if flat.empty:
        return pd.Series(0.0, index=units.index)
    inside = units.geometry.intersection(flat.geometry.union_all()).area
    return (inside / units.geometry.area).clip(0.0, 1.0)


def cut_units(
    dem, slope, aspect, *, thresholds_ha, tolerance_deg, min_area_ha, max_area_ha
):
    """Cut the units once per threshold and return them keyed on it."""
    units = {}
    for threshold_ha in thresholds_ha:
        print(
            f"\nCutting units at a {threshold_ha:g} ha channel threshold ...",
            flush=True,
        )
        units[threshold_ha] = delineate_slope_units(
            dem,
            slope,
            aspect,
            channel_threshold_ha=threshold_ha,
            aspect_tolerance_deg=tolerance_deg,
            min_area_ha=min_area_ha,
            max_area_ha=max_area_ha,
        )
        print(f"  {len(units[threshold_ha]):,} units")
    return units


def sensitivity_table(units_by_threshold):
    """Tabulate the unit count and median area at each threshold tried."""
    rows = [
        {
            "channel_threshold_ha": threshold_ha,
            "unit_count": len(units),
            "median_area_ha": float(units["area_m2"].median()) / M2_PER_HA,
            "max_area_ha": float(units["area_m2"].max()) / M2_PER_HA,
        }
        for threshold_ha, units in sorted(units_by_threshold.items())
    ]
    return pd.DataFrame(rows)


def describe_units(units):
    """Print the unit count, the area deciles, the sides and the flatland share."""
    area_ha = units["area_m2"] / M2_PER_HA
    print(RULE)
    print(f"Units     : {len(units):,}")
    print(f"  Area    : {area_ha.sum():,.1f} ha in all")
    quantiles = area_ha.quantile(DECILES)
    print(
        "  Deciles : "
        + ", ".join(f"p{100 * q:g} {v:.2f} ha" for q, v in quantiles.items())
    )
    sides = units["side"].value_counts()
    print(
        "  Sides   : " + ", ".join(f"{side} {count:,}" for side, count in sides.items())
    )
    on_flat = units["flatland_share"]
    print(
        f"  Flatland: {on_flat.mean():.1%} of unit area on average, "
        f"{(on_flat > 0.5).sum():,} units mostly flat"
    )


def main(
    *,
    extent,
    channel_threshold_ha,
    channel_thresholds_tried_ha,
    aspect_merge_tolerance_deg,
    min_unit_area_ha,
    max_unit_area_ha,
):
    """Cut the slope units over the extent and write them.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        channel_threshold_ha: The channel threshold the written layer uses.
        channel_thresholds_tried_ha: The thresholds the sensitivity is
            reported over.
        aspect_merge_tolerance_deg: Neighbours whose mean aspects differ by
            less than this are merged.
        min_unit_area_ha: Units under this are absorbed into a neighbour.
        max_unit_area_ha: Units over this are split.
    """
    paths = input_paths(extent=extent)
    print(RULE)
    print(f"Extent    : {extent}")
    for name, path in paths.items():
        print(f"  {name:<10}: {path}")

    dem = read_grid(paths["dem"])
    slope = read_grid(paths["slope"])
    aspect = read_grid(paths["aspect"])
    ground_map = gpd.read_parquet(paths["ground_map"])

    thresholds = sorted(
        {float(channel_threshold_ha), *map(float, channel_thresholds_tried_ha)}
    )
    units_by_threshold = cut_units(
        dem,
        slope,
        aspect,
        thresholds_ha=thresholds,
        tolerance_deg=aspect_merge_tolerance_deg,
        min_area_ha=min_unit_area_ha,
        max_area_ha=max_unit_area_ha,
    )

    print(RULE)
    print("Sensitivity to the channel threshold:")
    print(sensitivity_table(units_by_threshold).to_string(index=False))

    units = units_by_threshold[float(channel_threshold_ha)]
    units["flatland_share"] = flatland_share(units, ground_map)
    units = sort_by_point(units)
    units.insert(0, "unit_id", mint_ids(constants.UNIT_ID_PREFIX, len(units)))
    units = units[OUTPUT_COLUMNS]
    describe_units(units)

    path = slope_units_path(extent=extent)
    path.parent.mkdir(parents=True, exist_ok=True)
    units.to_parquet(path)
    print(RULE)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        channel_threshold_ha=config.CHANNEL_THRESHOLD_HA,
        channel_thresholds_tried_ha=config.CHANNEL_THRESHOLDS_TRIED_HA,
        aspect_merge_tolerance_deg=config.ASPECT_MERGE_TOLERANCE_DEG,
        min_unit_area_ha=config.MIN_UNIT_AREA_HA,
        max_unit_area_ha=config.MAX_UNIT_AREA_HA,
    )
