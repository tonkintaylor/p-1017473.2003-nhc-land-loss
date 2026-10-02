"""Turn Site Search exports into the claims lists the report fetch works from.

    uv run --frozen python src/scripts/landloss/vul/static_data_gen/gen_claims_lists.py \\
        --list kaikoura-2016 path/to/export.json [--list seddon-2013 path/to/other.json ...]

**Why a list at all.** Walking a project on T: and copying every report costs
about 4 MB a report, mostly photographs, and most of them are claims this study
does not need. Site Search already knows every subproject's name, start date and
coordinates, so the claims can be chosen before anything is copied. The fetch
step then takes the chosen subprojects with ``--subprojects``.

**Where the exports come from.** Site Search is reachable only through its
claude.ai connector, not from a script, so each export is the saved result of a
``search_project_metadata`` query run from Claude. The queries behind the lists
in the repo are recorded in ``claims-lists/README.md`` so they can be rerun.

**What each claim is tagged with.** The territorial authority it falls in, from
the study area boundaries in ``landloss.io.area_of_interest``, so
``in_study_area`` is a point-in-polygon answer rather than a bounding box: a
box around Wellington would take in parts of Kapiti and the Wairarapa. Also any
event hint in the subproject's own name -- ``EQC13``, ``EQC2013``, ``JULY13``,
``EQC2016`` -- which some offices used. The hint is a clue, not a finding: the
same programmes carry storm claims from the same months, and the report's own
event sentence, read at extraction, is what settles which event a claim was.

Each list is written to
``src/landloss/common/assets/claim_reports/claims-lists/<name>.csv``.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from landloss.io.area_of_interest import get_study_areas
from scripts.landloss.paths import CLAIM_REPORTS_ASSETS_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LISTS_DIR = CLAIM_REPORTS_ASSETS_DIR / "claims-lists"
WGS84 = "EPSG:4326"

# Event hints some offices put in the subproject name.
NAME_HINTS = {
    "2013": re.compile(r"EQC ?(?:JULY|AUG)?\s*(?:20)?13\b", re.IGNORECASE),
    "2016": re.compile(r"EQC ?(?:20)?16\b", re.IGNORECASE),
}

# Projects a query picks up that hold no house claims. 1001154 is the Kaikoura
# earthquake response umbrella -- EQC response management, the funding
# deficit, the response portal, port and roading work -- and sits in the event
# window only because its point is in Kaikoura.
NOT_CLAIMS = {"1001154"}

COLUMNS = [
    "project_number_full",
    "programme",
    "subproject",
    "project_name",
    "project_long_name",
    "client",
    "start_date",
    "owning_office",
    "project_manager",
    "lon",
    "lat",
    "ta_name",
    "in_study_area",
    "name_event_hint",
]


def read_export(path: Path) -> pd.DataFrame:
    """Return a Site Search ``search_project_metadata`` export as a frame.

    Args:
        path: The saved JSON, ``{"status": ..., "data": [...]}``.

    Returns:
        One row per subproject, with the first of its points split into
        ``lon`` and ``lat``. A subproject with no point keeps blank ones.
    """
    rows = json.loads(path.read_text(encoding="utf-8"))["data"]
    frame = pd.DataFrame(rows)
    points = frame.get("points", pd.Series([None] * len(frame)))
    frame["lon"] = [p[0][0] if p else None for p in points]
    frame["lat"] = [p[0][1] if p else None for p in points]
    return frame


def folder_name(project_number_full: str) -> str:
    """Return a subproject as its folder is named on T: -- no leading zeros.

    ``0085650.3847`` is filed as ``85650.3847``; ``1502000.0005`` is unchanged.
    """
    project, _, sub = project_number_full.partition(".")
    return f"{int(project)}.{sub[:4]}"


def name_hint(name: str) -> str:
    """Return the event year a subproject's name hints at, or blank."""
    for year, pattern in NAME_HINTS.items():
        if pattern.search(name or ""):
            return year
    return ""


def tag_study_area(frame: pd.DataFrame, study_areas: gpd.GeoDataFrame) -> pd.Series:
    """Return the study-area territorial authority each claim falls in, or blank."""
    located = frame.dropna(subset=["lon", "lat"])
    points = gpd.GeoDataFrame(
        index=located.index,
        geometry=gpd.points_from_xy(located["lon"], located["lat"]),
        crs=WGS84,
    ).to_crs(study_areas.crs)
    joined = gpd.sjoin(points, study_areas[["name", "geometry"]], predicate="within")
    # A point on a shared boundary can match two authorities; keep the first.
    names = joined["name"][~joined.index.duplicated()]
    return names.reindex(frame.index).fillna("")


def build(frame: pd.DataFrame, study_areas: gpd.GeoDataFrame) -> pd.DataFrame:
    """Return a claims list from one export."""
    out = frame.copy()
    out["programme"] = out["project_number_full"].str.slice(0, 7)
    out = out[~out["programme"].isin(NOT_CLAIMS)]
    out["subproject"] = out["project_number_full"].map(folder_name)
    out["ta_name"] = tag_study_area(out, study_areas)
    out["in_study_area"] = out["ta_name"] != ""
    out["name_event_hint"] = out["project_name"].map(name_hint)
    out["start_date"] = out["start_date"].str.slice(0, 10)
    for column in COLUMNS:
        if column not in out:
            out[column] = ""
    return (
        out[COLUMNS]
        .drop_duplicates("project_number_full")
        .sort_values(["start_date", "project_number_full"])
        .reset_index(drop=True)
    )


def main(argv: list[str] | None = None) -> int:
    """Write one claims list per ``--list NAME EXPORT`` pair."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list",
        nargs=2,
        action="append",
        metavar=("NAME", "EXPORT"),
        required=True,
        help="a list name and the Site Search export it is built from",
    )
    args = parser.parse_args(argv)
    study_areas = get_study_areas()
    LISTS_DIR.mkdir(parents=True, exist_ok=True)
    for name, export in args.list:
        claims = build(read_export(Path(export)), study_areas)
        out = LISTS_DIR / f"{name}.csv"
        claims.to_csv(out, index=False)
        inside = int(claims["in_study_area"].sum())
        print(
            f"{name}: {len(claims):,} claims, {inside:,} in the study area, "
            f"{(claims['name_event_hint'] != '').sum():,} with an event hint in "
            f"the name -> {out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
