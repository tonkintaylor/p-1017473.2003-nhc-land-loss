"""Write the numbers the bridges and culverts appendix quotes.

    uv run --frozen python src/scripts/landloss/exposure/culverts_bridges/report/gen_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has four parts:

- ``meta``: when and from which commit it was written, the realisation, and the
  step 7 run read for each territorial authority with the date it was written.
- ``settings``: the chance a crossing is a culvert.
- ``study_area``: the crossings over the four territorial authorities, by
  structure and by the river layer that found them, and per authority.
- ``figures``: which of the appendix's figures exist, so the appendix can show
  a placeholder rather than fail when one has not been drawn.

Each authority's run covers its bounding box, which takes in the edges of its
neighbours, so a crossing is counted only in the authority it lies in. Reads
step 7's outputs under ``temp/`` only, never the T: drive. Written to
``report/exposure/culverts_bridges/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import geopandas as gpd
import pandas as pd
import yaml

from landloss.domain import constants
from landloss.exposure.culverts_bridges.crossings import (
    CULVERT_PROBABILITY,
    STRUCTURE_COLUMN,
    WATERCOURSE_SOURCE_COLUMN,
)
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from scripts.landloss.exposure.culverts_bridges.steps.s7_crossing_population.gen_crossing_population import (
    crossing_population_path,
)
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPO_ROOT, REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "exposure" / "culverts_bridges" / "tab" / "report-numbers.yaml"
FIG_DIR = REPORT_DIR / "exposure" / "culverts_bridges" / "fig"
FIGURES = {"map": FIG_DIR / "crossings-study-area.png"}
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
REALISATION_ID = 0
AUTHORITY_COLUMN = "territorial_authority"


def read_crossings(realisation_id, extents=AUTHORITY_EXTENTS):
    """Return the crossings of each authority's run that lie in that authority.

    Raises:
        FileNotFoundError: If step 7 has not been run for an authority.
    """
    authorities = get_study_areas(constants.DEFAULT_CRS)
    frames = []
    for extent in extents:
        path = crossing_population_path(realisation_id, extent=extent)
        if not path.exists():
            msg = f"No step 7 run for {extent}: run gen_crossing_population.py for it"
            raise FileNotFoundError(msg)
        name = get_area_of_interest(extent).name
        boundary = authorities.loc[authorities["name"] == name].union_all()
        crossings = gpd.read_parquet(path).to_crs(constants.DEFAULT_CRS)
        inside = crossings.representative_point().within(boundary)
        frames.append(crossings[inside].assign(**{AUTHORITY_COLUMN: name}))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)


def counts(crossings, column):
    """Return how many crossings take each value of a column."""
    return {str(k): int(v) for k, v in crossings[column].value_counts().items()}


def main(*, realisation_id):
    """Compute the numbers and write the YAML."""
    crossings = read_crossings(realisation_id)
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "realisation_id": realisation_id,
            "runs": {
                extent: dt.datetime.fromtimestamp(
                    crossing_population_path(realisation_id, extent=extent)
                    .stat()
                    .st_mtime
                )
                .astimezone()
                .date()
                .isoformat()
                for extent in AUTHORITY_EXTENTS
            },
        },
        "settings": {"culvert_probability": CULVERT_PROBABILITY},
        "study_area": {
            "crossings": len(crossings),
            "claims": int(crossings["claim_id"].nunique()),
            "by_structure": counts(crossings, STRUCTURE_COLUMN),
            "by_source": counts(crossings, WATERCOURSE_SOURCE_COLUMN),
            "by_authority": {
                name: {"crossings": len(rows), **counts(rows, STRUCTURE_COLUMN)}
                for name, rows in crossings.groupby(AUTHORITY_COLUMN)
            },
        },
        "figures": {
            key: path.relative_to(REPO_ROOT).as_posix() if path.exists() else None
            for key, path in FIGURES.items()
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(yaml.safe_dump(numbers["study_area"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(realisation_id=REALISATION_ID)
