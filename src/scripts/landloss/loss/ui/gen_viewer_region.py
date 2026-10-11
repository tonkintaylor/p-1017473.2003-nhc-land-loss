"""Combine the four territorial authorities' viewer CSVs into one for the region.

    uv run --frozen python src/scripts/landloss/loss/ui/gen_viewer_region.py

Reads each authority's ``loss-viewer-w<NNN>-r<NNN>-<extent>.csv`` from
``report/loss/viewer/``, as ``gen_viewer_data.py`` writes it, and writes
``loss-viewer-w<NNN>-r<NNN>-wellington-region.csv`` beside them, with the page.
Each authority's CSV already holds only the claims inside that authority
(``gen_viewer_data.within_territorial_authority``), so stacking them counts
every claim once; the viewer then shows the region or any one authority.

**The four must come from one run of the code.** The page reads the version
stamp and the liquefaction pricing method off the first row only, so a region
stacked from CSVs built at different commits would show one stamp over rows it
does not describe. They are checked to agree, along with their columns, and a
claim in two authorities is refused, before anything is written.
"""

import sys

import pandas as pd

from landloss.io.area_of_interest import get_area_of_interest
from scripts.landloss.loss.ui.gen_viewer_data import (
    OUT_DIR,
    viewer_version,
    write_viewer,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# The four territorial authorities of the study, by extent name.
REGION_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
REGION_NAME = "wellington-region"
WORLD_ID = 0
REALISATION_ID = 0

# What the combined CSV adds: the authority each claim is in, which the page's
# territorial authority filter reads.
TA_COLUMN = "territorial_authority"
CLAIM_COLUMN = "claim_id"
VERSION_COLUMN = "built_with"
METHOD_COLUMN = "liq_method"


def viewer_csv_path(extent: str, *, world_id: int, realisation_id: int):
    """Return the viewer CSV ``gen_viewer_data.py`` writes for one extent."""
    return OUT_DIR / (f"loss-viewer-w{world_id:03d}-r{realisation_id:03d}-{extent}.csv")


def _commit(version: str) -> str:
    """Return the commit part of a version stamp, ``v1a2b3c``."""
    return str(version).split(",")[0]


def combine_viewer_rows(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return the authorities' viewer rows stacked, each labelled with its own.

    Args:
        frames: Each authority's viewer rows, keyed by the authority's name.

    Returns:
        The rows of every frame in the order given, with :data:`TA_COLUMN`
        added after the claim id.

    Raises:
        ValueError: If the frames differ in their columns, were built at
            different commits or priced liquefaction differently, or a claim
            appears in more than one authority.
    """
    if not frames:
        msg = "no viewer CSVs to combine"
        raise ValueError(msg)
    columns = {name: list(frame.columns) for name, frame in frames.items()}
    if len({tuple(c) for c in columns.values()}) > 1:
        msg = f"the viewer CSVs carry different columns: {columns}"
        raise ValueError(msg)
    for column, read in ((VERSION_COLUMN, _commit), (METHOD_COLUMN, str)):
        if column not in next(iter(frames.values())).columns:
            continue
        seen = {
            name: sorted({read(value) for value in frame[column].dropna()})
            for name, frame in frames.items()
        }
        if len({value for values in seen.values() for value in values}) > 1:
            msg = (
                f"the viewer CSVs disagree on {column}, so they are not one run "
                f"of the code: {seen}. Rebuild them at one commit."
            )
            raise ValueError(msg)
    stacked = pd.concat(
        [frame.assign(**{TA_COLUMN: name}) for name, frame in frames.items()],
        ignore_index=True,
    )
    repeated = stacked.loc[stacked[CLAIM_COLUMN].duplicated(keep=False)]
    if not repeated.empty:
        example = repeated.groupby(CLAIM_COLUMN)[TA_COLUMN].agg(list).head(3)
        msg = (
            f"{repeated[CLAIM_COLUMN].nunique():,} claims appear in more than one "
            f"authority, for example {example.to_dict()}"
        )
        raise ValueError(msg)
    order = [CLAIM_COLUMN, TA_COLUMN] + [
        c for c in stacked.columns if c not in (CLAIM_COLUMN, TA_COLUMN)
    ]
    return stacked[order]


def main(*, extents, world_id, realisation_id):
    """Combine the authorities' viewer CSVs and write the region's.

    Args:
        extents: The authorities' extent names.
        world_id: The exposure world the CSVs were built for.
        realisation_id: The earthquake the CSVs were built for.

    Raises:
        FileNotFoundError: If an authority's CSV is not in the viewer folder.
    """
    frames = {}
    for extent in extents:
        path = viewer_csv_path(extent, world_id=world_id, realisation_id=realisation_id)
        if not path.exists():
            msg = (
                f"{path} is missing: run gen_viewer_data.py for {extent}, or copy "
                "its CSV into the viewer folder"
            )
            raise FileNotFoundError(msg)
        name = get_area_of_interest(extent).name
        frames[name] = pd.read_csv(path)
        print(f"  {name}: {len(frames[name]):,} claims from {path.name}")

    rows = combine_viewer_rows(frames)
    out = viewer_csv_path(REGION_NAME, world_id=world_id, realisation_id=realisation_id)
    rows.to_csv(out, index=False)
    page = write_viewer(OUT_DIR, viewer_version())
    print(f"Wrote {len(rows):,} claims over {len(frames)} authorities to {out}")
    print(f"Wrote {page}")
    print("Open the page and drag the CSV onto it; choose an authority under Area.")


if __name__ == "__main__":
    main(
        extents=REGION_EXTENTS,
        world_id=WORLD_ID,
        realisation_id=REALISATION_ID,
    )
