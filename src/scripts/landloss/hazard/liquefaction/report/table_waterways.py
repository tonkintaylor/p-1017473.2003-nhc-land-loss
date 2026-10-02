"""Export the study area waterways as a CSV table.

A one-off companion to fig_waterway_map.py, for looking at the same watercourses
as rows rather than as a picture -- checking how the named rivers were picked
out, or handing the attributes to someone who does not run Python.

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/table_waterways.py

Reads the same extent, clip and classification as the figure, so the row count
matches the feature count the figure reports. Geometry is left out by default,
because a linestring per row makes the file large and unreadable in a
spreadsheet; pass --wkt to include it.

Requires LINZ_API_KEY in .env.
"""

import argparse
import sys
from pathlib import Path

from landloss.domain import constants
from landloss.hazard.liquefaction.waterways import get_waterways
from landloss.io.area_of_interest import get_study_areas
from scripts.landloss.paths import REPORT_DIR

# Watercourse names are macronised, which the default cp1252 Windows console
# cannot encode. See the note in fig_waterway_map.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TAB_DIR = REPORT_DIR / "hazard" / "liquefaction" / "tab"
TAB_NAME = "waterways.csv"

# Source columns worth keeping, in the order they are most useful to read.
COLUMNS = [
    "id",
    "river_section_id",
    "wtype",
    "feat_type",
    "name",
    "name_ascii",
    "macronated",
]
RULE = "-" * 72


def build_table(waterways, *, wkt=False):
    """Turn the waterways frame into a flat table, ordered for reading."""
    table = waterways[[c for c in COLUMNS if c in waterways]].copy()

    # Length is the one thing worth deriving here: it is what makes a row
    # interpretable without the geometry, and it is what a reader reaches for
    # when asking which watercourses actually matter.
    table["length_m"] = waterways.geometry.length.round(1)

    if wkt:
        table["geometry_wkt"] = waterways.geometry.to_wkt()

    # Named rivers first, then longest first, so the head of the file is the
    # part anyone opening it actually wants to see.
    return table.sort_values(
        ["wtype", "length_m"], ascending=[True, False]
    ).reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wkt",
        action="store_true",
        help="Include the geometry as a WKT column.",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore the extent cache and re-read from the source layer.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=TAB_DIR / TAB_NAME,
        help="Where to write the CSV.",
    )
    args = parser.parse_args()

    study_areas = get_study_areas(constants.DEFAULT_CRS)
    bbox = tuple(float(value) for value in study_areas.total_bounds)

    print(f"Extent: {', '.join(study_areas['name'])}")
    print("Reading the LINZ river name lines layer ...")

    waterways = get_waterways(bbox=bbox, clip_to=study_areas, use_cache=not args.fresh)

    if waterways.empty:
        print("\nNo watercourses found within the extent.")
        return 1

    table = build_table(waterways, wkt=args.wkt)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel on Windows opens the macronised names correctly rather
    # than mangling them; plain utf-8 is read as cp1252 on a double click.
    table.to_csv(args.out, index=False, encoding="utf-8-sig")

    print(RULE)
    print(f"Wrote {args.out}")
    print(f"  Rows    : {len(table):,}")
    print(f"  Columns : {', '.join(table.columns)}")
    for wtype, count in table["wtype"].value_counts().items():
        total_km = table.loc[table["wtype"] == wtype, "length_m"].sum() / 1000
        print(f"  {wtype:<8}: {count:>6,} features, {total_km:>8,.1f} km")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
