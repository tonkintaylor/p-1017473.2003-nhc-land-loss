"""Write the numbers the technical report's insured land section quotes.

    uv run --frozen python src/scripts/landloss/exposure/land/report/gen_report_numbers.py

Every number the section states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has five parts:

- ``meta``: when and from which commit it was written.
- ``settings``: the values the insured land and the land value are set with,
  read from the constants and the committed factors asset that set them.
- ``land_value``: the land value over the extent the land value step was last
  run for (the four territorial authorities), with its calibration against
  QV's published averages and the suburb ranking check
  ``validations/check_land_value_totals.py`` makes.
- ``insured_land``: the claims, dwellings, areas and driveways over the extent
  the insured land step was last run for (the pilot until the full build,
  T-68).
- ``figures``: which of the section's figures exist, so the section can show a
  placeholder rather than fail when one has not been drawn.

Written to ``report/exposure/land/tab/report-numbers.yaml``. It reads only the
outputs under ``temp/`` and the committed assets, never the T: drive.
"""

import datetime as dt
import subprocess
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml

from landloss.domain.gst import GST_RATE
from landloss.exposure.land.driveways import (
    DRIVEWAY_HALF_WIDTH_M,
    MAX_DRIVEWAY_LENGTH_M,
    MAX_INSURED_ACCESS_M,
)
from landloss.exposure.land.extent import (
    INSURED_LAND_BUFFER_M,
    MAX_DWELLING_FOOTPRINT_M2,
    MIN_CROSSING_AREA_M2,
    MIN_CROSSING_SHARE,
)
from landloss.exposure.land.land_value import (
    COMMON_VALUATION_DATE,
    index_base_rates,
    load_base_rates,
    load_factors,
    ta_mean_land_value,
)
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.land.steps.s2_land_value import (
    config as land_value_config,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    config as insured_config,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    driveway_path,
    insured_land_path,
)
from scripts.landloss.exposure.land.validations.check_land_value_totals import (
    check_suburb_ranking,
    rank_suburbs,
)
from scripts.landloss.exposure.steps.s1_address_spine.s1_build_address_spine import (
    OUT_STEM as SPINE_STEM,
)
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR, TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "exposure" / "land" / "tab" / "report-numbers.yaml"
LAND_DIR = REPORT_DIR / "exposure" / "land"
HECTARE_M2 = 10_000
# The factors the section quotes, by their row in the factors asset.
QUOTED_FACTORS = (
    "landform_factor_hill",
    "landform_factor_flat",
    "landform_factor_elevated_flat",
    "elevated_flat_min_topographic_position_m",
    "topographic_position_window_m",
    "rate_clip_min_multiple",
    "rate_clip_max_multiple",
    "sea_view_premium",
    "coast_premium",
    "coast_decay_length_m",
    "winter_sun_premium",
    "rail_station_premium",
    "rail_station_decay_length_m",
    "accessibility_elasticity",
)


def git_commit():
    """Return the short hash of the commit the numbers were written from."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return result.stdout.strip() or "unknown"


def settings():
    """Return the values the insured land and the land value are set with."""
    factors = load_factors()
    return {
        "buffer_m": INSURED_LAND_BUFFER_M,
        "insured_access_m": MAX_INSURED_ACCESS_M,
        "max_driveway_m": MAX_DRIVEWAY_LENGTH_M,
        "driveway_width_m": 2 * DRIVEWAY_HALF_WIDTH_M,
        "max_dwelling_footprint_m2": MAX_DWELLING_FOOTPRINT_M2,
        "min_crossing_area_m2": MIN_CROSSING_AREA_M2,
        "min_crossing_share": MIN_CROSSING_SHARE,
        "gst_rate": GST_RATE,
        "valuation_date": COMMON_VALUATION_DATE,
        "factors": {name: float(factors[name]) for name in QUOTED_FACTORS},
    }


def land_value(extent):
    """Return the land value over an extent, its calibration and ranking check."""
    path = (
        TEMP_DIR
        / "exposure"
        / f"land-value-by-address{extent_suffix(extent)}.geoparquet"
    )
    valued = gpd.read_parquet(path)
    indexed = index_base_rates(load_base_rates()).set_index("ta_name")
    modelled = ta_mean_land_value(valued)
    by_ta = {}
    for ta, rows in valued.groupby("territorial_authority"):
        published = indexed.loc[ta]
        by_ta[ta] = {
            "addresses": len(rows),
            "valuation_date": str(published["valuation_date"]),
            "published_mean_nzd": float(published["avg_land_value_nzd"]),
            "indexed_mean_nzd": float(published["indexed_land_value_nzd"]),
            "modelled_mean_nzd": float(modelled.loc[ta]),
            "median_rate_nzd_per_m2": {
                str(form): float(group["land_rate_nzd_per_m2"].median())
                for form, group in rows.groupby("landform_class")
            },
        }
    ranked = rank_suburbs(valued)
    rows, met, considered, total = check_suburb_ranking(ranked)
    return {
        "extent": extent,
        "addresses": len(valued),
        "landform_share": {
            str(form): float(share)
            for form, share in valued["landform_class"]
            .value_counts(normalize=True)
            .items()
        },
        "by_ta": by_ta,
        "suburb_ranking": {
            "suburbs_ranked": int(total),
            "expectations_met": int(met),
            "expectations_considered": int(considered),
            "out_of_place": [row[0] for row in rows if row[-1] == "OUT OF PLACE"],
        },
    }


def insured_land(extent):
    """Return the claims, dwellings, areas and driveways over an extent."""
    insured = gpd.read_parquet(insured_land_path(extent=extent))
    driveways = pd.read_parquet(driveway_path(extent=extent))
    spine = TEMP_DIR / "exposure" / f"{SPINE_STEM}{extent_suffix(extent)}.geoparquet"
    addresses = len(gpd.read_parquet(spine))
    share_of_property = insured["area_m2"] / insured["property_area_m2"]
    full_length = driveways["driveway_length_m"].to_numpy()
    return {
        "extent": extent,
        "claims": len(insured),
        "dwellings_covered": int(insured["dwelling_count"].sum()),
        "addresses": addresses,
        "area_ha": float(insured["area_m2"].sum() / HECTARE_M2),
        "median_area_m2": float(insured["area_m2"].median()),
        "p90_area_m2": float(insured["area_m2"].quantile(0.9)),
        "median_share_of_property": float(share_of_property.median()),
        "driveways": len(driveways),
        "median_driveway_m": float(np.median(full_length)),
        "share_cut_at_insured_access": float(
            np.mean(full_length > MAX_INSURED_ACCESS_M)
        ),
    }


def figures(insured_extent, value_extent):
    """Return each figure's path if it has been drawn, else None."""
    paths = {
        "insured_land": LAND_DIR
        / "insured-land"
        / "fig"
        / f"insured-land{extent_suffix(insured_extent)}.png",
        "land_value": LAND_DIR
        / "land-value"
        / "fig"
        / f"land-value-rate{extent_suffix(value_extent)}.png",
    }
    return {
        key: path.relative_to(REPO_ROOT).as_posix() if path.exists() else None
        for key, path in paths.items()
    }


def main(*, value_extent, insured_extent, figure_value_extent):
    """Compute the numbers and write the YAML."""
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
        },
        "settings": settings(),
        "land_value": land_value(value_extent),
        "insured_land": insured_land(insured_extent),
        "figures": figures(insured_extent, figure_value_extent),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(yaml.safe_dump(numbers["insured_land"], sort_keys=False))
    print(yaml.safe_dump(numbers["land_value"]["suburb_ranking"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(
        # The land value has been run over the whole study area; the insured
        # land and both figures so far over the pilot.
        value_extent="full",
        insured_extent=insured_config.EXTENT,
        figure_value_extent=land_value_config.EXTENT,
    )
