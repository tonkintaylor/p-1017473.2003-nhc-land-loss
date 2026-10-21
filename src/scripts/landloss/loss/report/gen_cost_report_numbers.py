"""Write the numbers the cost estimation appendix quotes.

    uv run --frozen python src/scripts/landloss/loss/report/gen_cost_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. Almost all of them are
settings, read from the constants that set them, so a changed rate changes the
appendix on the next run. The YAML has seven parts:

- ``meta``: when and from which commit it was written.
- ``walls``: the retaining wall rates, the wall type each is used for, the
  timber pile bands, the site difficulty markups and the proxies that set them,
  the replacement uplift and the length rule.
- ``landslide``: the spoil clearing rate and the wall a slip needs.
- ``crossings``: the bridge and culvert replacement and clearing costs.
- ``on_costs``: the professional fees, establishment, project management and
  contingency.
- ``liquefaction``: the repair rates, the volunteer allowance, the escalation,
  and the calibration against the Canterbury claim costs, read from the
  outputs ``s3_repair_rate_calibration`` last wrote. Left out if they have not
  been written.
- ``policy``: GST, the sub-caps and the excess, for the appendix's account of
  how a repair cost is settled.

Reads only committed assets and the calibration outputs under ``temp/``, never
the T: drive. Written to ``report/loss/costs/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import numpy as np
import pandas as pd
import yaml

from landloss.io import ASSETS_DIR
from landloss.loss import policy, pricing
from landloss.vul.liquefaction.costs import COST_YEAR
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    config as liq_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s3_repair_rate_calibration import (
    config as calibration_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s3_repair_rate_calibration.gen_repair_rate_calibration import (
    calibration_path,
    comparison_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "loss" / "costs" / "tab" / "report-numbers.yaml"
WALL_TYPES_PATH = ASSETS_DIR / "retaining-wall-types.csv"


def plain_number(value):
    """Return a value YAML can write: plain floats and lists, inf as None."""
    if isinstance(value, float) and np.isinf(value):
        return None
    return float(value)


def walls():
    """Return the retaining wall rates and the rules that price a wall."""
    rates = pricing.WALL_RATE_EXCL_GST_NZD_PER_M2
    types = pd.read_csv(WALL_TYPES_PATH)
    return {
        "rates_as_at": pricing.WALL_RATES_AS_AT,
        "types": [
            {
                "label": row.label,
                "rate_item": row.nhc_rate_item,
                "rate": rates.get(row.nhc_rate_item),
                "replaced_in_kind": row.wall_type in pricing.REPLACED_IN_KIND,
            }
            for row in types.itertuples()
        ],
        "timber_bands": [
            {"below_m": plain_number(height), "item": item, "rate": rates[item]}
            for height, item in pricing.TIMBER_POLE_HEIGHT_BANDS_M
        ],
        "spec_uplift": policy.REPLACEMENT_SPEC_UPLIFT,
        "markup": dict(pricing.RATING_MARKUP),
        "max_site_multiplier": pricing.MAX_SITE_MULTIPLIER,
        "access_driveway_m": [
            pricing.EASY_ACCESS_MAX_DRIVEWAY_M,
            pricing.MODERATE_ACCESS_MAX_DRIVEWAY_M,
        ],
        "constructability_slope_deg": [
            pricing.EASY_CONSTRUCTABILITY_MAX_SLOPE_DEG,
            pricing.MODERATE_CONSTRUCTABILITY_MAX_SLOPE_DEG,
        ],
        "earthworks_m3": [
            pricing.EASY_INUNDATION_MAX_VOLUME_M3,
            pricing.MODERATE_INUNDATION_MAX_VOLUME_M3,
        ],
        "margin_m": pricing.LANDSLIDE_WALL_MARGIN_M,
        "min_length_m": pricing.MIN_LANDSLIDE_WALL_LENGTH_M,
    }


def landslide():
    """Return the spoil clearing rate and the rules for the wall a slip needs."""
    return {
        "spoil_rate_per_m3": pricing.INUNDATION_REMOVAL_RATE_EXCL_GST_NZD_PER_M3,
        "spoil_line_item": pricing.INUNDATION_REMOVAL_LINE_ITEM,
        "size_class_height_m": dict(pricing.BETA_SIZE_CLASS_HEIGHT_M),
        "size_area_m2": [
            pricing.SMALL_LANDSLIDE_MAX_AREA_M2,
            pricing.MEDIUM_LANDSLIDE_MAX_AREA_M2,
        ],
        "size_volume_m3": [
            pricing.SMALL_LANDSLIDE_MAX_VOLUME_M3,
            pricing.MEDIUM_LANDSLIDE_MAX_VOLUME_M3,
        ],
        "aspect_ratio": pricing.LANDSLIDE_WALL_ASPECT_RATIO,
    }


def crossings():
    """Return what a bridge or culvert costs to replace or to clear."""
    return {
        "rate_per_m": pricing.CROSSING_RATE_EXCL_GST_NZD_PER_M,
        "default_span_m": pricing.CROSSING_DEFAULT_SPAN_M,
        "clearing": pricing.CROSSING_CLEARING_EXCL_GST_NZD,
    }


def on_costs():
    """Return the claim-level costs added to the works."""
    return {
        "fees": dict(pricing.PROFESSIONAL_FEES_EXCL_GST_NZD),
        "fees_total": pricing.PROFESSIONAL_FEES_TOTAL_EXCL_GST_NZD,
        "fees_share": pricing.PROFESSIONAL_FEES_SHARE,
        "mob_demob_share": pricing.MOB_DEMOB_SHARE,
        "mob_demob_min": pricing.MOB_DEMOB_MIN_EXCL_GST_NZD,
        "project_management_share": pricing.PROJECT_MANAGEMENT_SHARE,
        "contingency_share": pricing.CONTINGENCY_SHARE,
    }


def rows(path, columns):
    """Return a calibration output's rows as plain dicts, or None if unwritten."""
    if not path.exists():
        return None
    table = pd.read_csv(path, index_col=0)
    return [
        {
            column: (str(v) if column == "state_name" else float(v))
            for column, v in row.items()
        }
        for _, row in table[columns].iterrows()
    ]


def liquefaction():
    """Return the liquefaction repair rates and their calibration."""
    extent = calibration_config.COMPARE_EXTENT
    return {
        "rates": dict(liq_config.REPAIR_RATES),
        "no_sva": liq_config.NO_SVA,
        "cost_year": COST_YEAR,
        "escalation": pricing.LIQ_COST_ESCALATION,
        "escalation_source": pricing.LIQ_COST_ESCALATION_SOURCE,
        "section_m2": calibration_config.SECTION_M2,
        "calibration": rows(
            calibration_path(extent=extent),
            [
                "state_name",
                "canterbury_claims",
                "section_inundated_m2",
                "section_evacuated_m2",
                "canterbury_p50_nzd",
                "section_p50_nzd",
            ],
        ),
        "comparison_extent": extent,
        "comparison": rows(
            comparison_path(extent=extent),
            [
                "state_name",
                "claims",
                "modelled_p50_nzd",
                "canterbury_p50_nzd",
                "modelled_over_canterbury_p50",
            ],
        ),
    }


def main():
    """Collect the numbers and write the YAML."""
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
        },
        "walls": walls(),
        "landslide": landslide(),
        "crossings": crossings(),
        "on_costs": on_costs(),
        "liquefaction": liquefaction(),
        "policy": {
            "gst_rate": policy.GST_RATE,
            "wall_sub_cap": policy.RETAINING_WALL_SUB_CAP_NZD,
            "crossing_sub_cap": policy.BRIDGE_CULVERT_SUB_CAP_NZD,
            "excess_per_dwelling": policy.LAND_EXCESS_PER_DWELLING_NZD,
            "excess_max": policy.LAND_EXCESS_MAX_NZD,
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(yaml.safe_dump(numbers["liquefaction"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
