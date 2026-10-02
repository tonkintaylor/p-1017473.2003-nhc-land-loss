"""Tabulate the class-word-to-fraction reading behind the urban fragility anchors.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/urban/table_urban_fragility_anchors.py

Reads the packaged ``urban-fragility-anchors.csv`` and writes the table the
report carries: one row per failure class word, the fraction of polygons
failing it is read as, who set that number and why. The reading is judgement
(plan section 6 of
``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``),
and the table exists so that it is printed beside the curves rather than
buried in the asset. The project lead changes a number by editing the CSV,
not this script.

Reads only a packaged asset, so it needs no network and no run of any step.
The table goes under ``report/hazard/landslide/urban-fragility/tab/``.
"""

import sys

import pandas as pd

from landloss.hazard.landslide.urban import fragility
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TAB_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-fragility" / "tab"
TAB_NAME = "urban-fragility-anchors.csv"

TABLE_COLUMNS = ("class_word", "fail_fraction", "set_by", "basis")

RULE = "-" * 72


def class_word_table(anchors):
    """Reduce the anchors to one row per class word.

    Args:
        anchors: The table ``load_urban_fragility_anchors`` returns.

    Returns:
        One row per ``class_word`` with its ``fail_fraction``, ``set_by`` and
        a ``basis`` naming the anchors that use the word and the reading the
        first of them records, ordered by fraction.

    Raises:
        ValueError: If one word is read as two different fractions, which the
            anchor table must not do.
    """
    rows = []
    for word, group in anchors.groupby("class_word", sort=False):
        fractions = sorted(group["fail_fraction"].unique())
        if len(fractions) != 1:
            msg = f"The class word {word!r} is read as {fractions}; one fraction per word."
            raise ValueError(msg)
        rows.append(
            {
                "class_word": word,
                "fail_fraction": fractions[0],
                "set_by": "; ".join(sorted(group["set_by"].unique())),
                "basis": (
                    f"Anchors {', '.join(group['anchor_id'])}: {group['basis'].iloc[0]}"
                ),
            }
        )
    table = pd.DataFrame(rows, columns=list(TABLE_COLUMNS))
    return table.sort_values("fail_fraction", kind="mergesort").reset_index(drop=True)


def main():
    """Write the class-word table from the packaged anchors."""
    anchors = fragility.load_urban_fragility_anchors()
    table = class_word_table(anchors)
    out_path = TAB_DIR / TAB_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)
    print(RULE)
    with pd.option_context("display.max_colwidth", 60, "display.width", 160):
        print(table.to_string(index=False))
    print(RULE)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
