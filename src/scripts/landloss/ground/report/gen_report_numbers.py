"""Write the numbers the ground model appendix quotes.

    uv run --frozen python src/scripts/landloss/ground/report/gen_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has four parts:

- ``meta``: when and from which commit it was written, and the date each
  territorial authority's ground map was written.
- ``settings``: the terrain grids and the cut and fill, groundwater and
  default settings of the ground map, read from the step configs and the
  modules that set them.
- ``study_area``: over the four territorial authorities, the share of land in
  each material, modification and groundwater class, the share each source
  supplies, and the fill thickness.
- ``by_authority``: the same shares for each territorial authority.

Each authority's ground map covers its bounding box, which takes in the edges
of its neighbours and the sea, so each map is clipped to its own authority and
shares are of the land within it. Reads the outputs under ``temp/`` and the
committed assets only, never the T: drive. Written to
``report/ground/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import geopandas as gpd
import pandas as pd
import yaml

from landloss.domain import constants
from landloss.hazard.landslide import ground_map, susceptibility
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from scripts.landloss.ground.steps.s1_terrain import config as s1_config
from scripts.landloss.ground.steps.s2_ground_map import config as s2_config
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import ground_map_path
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "ground" / "tab" / "report-numbers.yaml"
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
M2_PER_KM2 = 1_000_000.0
RESIDUAL_SOURCE = "residual_30m"


def settings():
    """Return the values the terrain grids and the ground map are built with."""
    return {
        "dem_resolutions_m": list(s1_config.RESOLUTIONS_M),
        "slope_resolutions_m": list(s1_config.SLOPE_RESOLUTIONS_M),
        "residual_bases_m": list(s1_config.RESIDUAL_BASE_RESOLUTIONS_M),
        "tpi_windows_m": [float(k) for k in s1_config.TOPOGRAPHIC_POSITION_WINDOWS_M],
        "residual_threshold_m": s2_config.RESIDUAL_MODIFICATION_THRESHOLD_M,
        "residual_class_cell_m": s2_config.RESIDUAL_CLASS_CELL_M,
        "residual_min_patch_m2": s2_config.RESIDUAL_MIN_PATCH_M2,
        "residual_simplify_m": s2_config.RESIDUAL_SIMPLIFY_M,
        "groundwater_simplify_m": s2_config.GROUNDWATER_SIMPLIFY_M,
        "default_groundwater_depth_m": s2_config.DEFAULT_GROUNDWATER_DEPTH_M,
        "saturated_depth_m": susceptibility.GROUNDWATER_SATURATED_DEPTH_M,
        "poorly_drained_depth_m": susceptibility.GROUNDWATER_POORLY_DRAINED_DEPTH_M,
        "groundwater_values": {
            str(k): float(v) for k, v in susceptibility.GROUNDWATER_CLASS_VALUES.items()
        },
        "geology_values": {
            k: (None if pd.isna(v) else float(v))
            for k, v in ground_map.MATERIAL_GEOLOGY_VALUES.items()
        },
        "materials": list(ground_map.MATERIALS),
    }


def shares(frame, column):
    """Return each class's share of the area, largest first."""
    by_class = frame.groupby(column)["area"].sum() / frame["area"].sum()
    return {
        str(k): round(float(v), 3)
        for k, v in by_class.sort_values(ascending=False).items()
    }


def summary(ground):
    """Return the class and source shares and fill thickness for one area."""
    fill = ground[ground["modification"] == "fill"]
    return {
        "land_km2": round(float(ground["area"].sum()) / M2_PER_KM2, 1),
        "pieces": len(ground),
        "material": shares(ground, "material"),
        "material_source": shares(ground, "material_source"),
        "modification": shares(ground, "modification"),
        "modification_source": shares(ground, "modification_source"),
        "residual_share_of_modification": round(
            float(
                ground.loc[
                    ground["modification_source"] == RESIDUAL_SOURCE, "area"
                ].sum()
                / ground["area"].sum()
            ),
            3,
        ),
        "gw_depth_class": shares(ground, "gw_depth_class"),
        "gw_source": shares(ground, "gw_source"),
        "flatland_share": round(
            float(
                ground.loc[ground["is_flatland"], "area"].sum() / ground["area"].sum()
            ),
            3,
        ),
        "prior_failure": shares(ground, "prior_failure"),
        "fill_thickness_m": {
            "median": round(float(fill["fill_thickness_m"].median()), 1),
            "p90": round(float(fill["fill_thickness_m"].quantile(0.9)), 1),
        },
    }


def written(path):
    """Return the date a file was written."""
    return (
        dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().date().isoformat()
    )


def main():
    """Compute the numbers and write the YAML."""
    authorities = get_study_areas(constants.DEFAULT_CRS)
    parts, by_authority, runs = [], {}, {}
    for extent in AUTHORITY_EXTENTS:
        path = ground_map_path(extent=extent)
        name = get_area_of_interest(extent).name
        boundary = authorities.loc[authorities["name"] == name]
        ground = gpd.read_parquet(path).to_crs(constants.DEFAULT_CRS)
        ground = gpd.clip(ground, boundary)
        ground["area"] = ground.area
        by_authority[name] = summary(ground)
        runs[extent] = written(path)
        parts.append(ground)
    ground = pd.concat(parts, ignore_index=True)
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "runs": runs,
        },
        "settings": settings(),
        "study_area": summary(ground),
        "by_authority": by_authority,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(
        yaml.safe_dump(
            {k: numbers[k] for k in ("study_area", "by_authority")}, sort_keys=False
        )
    )
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
