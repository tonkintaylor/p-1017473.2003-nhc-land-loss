"""Tabulate the share of each suburb's properties in each retaining wall age bin.

Reads the property ages ``gen_rwt_age.py`` wrote and writes the tables the
report carries, one row per suburb and one per territorial authority:

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s8_infer_rwt_age/table_rwt_age_by_suburb.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_rwt_age.rwt_age_path`` where that run's output went, so the table cannot
summarise a different run from the one last made.

A share is of claim properties with a dwelling, not of dwellings, because the
walls belong to the land: a block of twenty flats on one lot is one property.
The four ``p_`` columns sum to one over the dated properties; ``undated`` counts
those with nothing to date them by, which the shares leave out. The tables go
under ``report/exposure/rw/rwt-age/tab/``.

The dates come from LINZ data under CC BY 4.0, so the table in the report
credits Land Information New Zealand as the source of the titles and boundaries
it was derived from.
"""

import sys

import geopandas as gpd

from landloss.exposure.rw import age
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age import config
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.gen_rwt_age import (
    rwt_age_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic.
TAB_DIR = REPORT_DIR / "exposure" / "rw" / "rwt-age" / "tab"
SUBURB_COLUMNS = ["territorial_authority", "suburb_locality"]

RULE = "-" * 72


def table_path(level, *, extent):
    """Return the CSV a run writes one level of the table to.

    Args:
        level: ``"suburb"`` or ``"ta"``.
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The table path, under ``report/exposure/rw/rwt-age/tab/``.
    """
    suffix = extent_suffix(extent)
    return TAB_DIR / f"rwt-age-by-{level}{suffix}.csv"


def main(*, extent):
    """Write the per-suburb and per-authority age bin shares.

    Args:
        extent: The extent the ages were inferred over, a name from
            landloss.io.area_of_interest.EXTENTS or "full". Must match the
            setting the generation was run with, which is why both read it from
            the same ``config.py``.
    """
    ages_path = rwt_age_path(extent=extent)
    print(f"Reading the property ages from {ages_path} ...")
    ages = gpd.read_parquet(ages_path)

    tables = {
        "suburb": age.bin_shares(ages, SUBURB_COLUMNS),
        "ta": age.bin_shares(ages, SUBURB_COLUMNS[:1]),
    }
    for level, table in tables.items():
        out_path = table_path(level, extent=extent)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(out_path, index=False, float_format="%.3f")
        print(RULE)
        print(f"Wrote {len(table):,} rows to {out_path}")

    print(RULE)
    print(tables["ta"].to_string(index=False, float_format="%.3f"))


if __name__ == "__main__":
    main(extent=config.EXTENT)
