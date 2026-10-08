"""Ground step 5 checks: the cut and fill classes, against the GNS SLIDE mapping and ground.

Three tables, written to ``report/ground/pif-cut-fill/tab/``:

* ``class-counts.csv``: the pifs in each class, all of them and those of at
  least ``config.CHECK_MIN_PIPS`` pips;
* ``class-vs-slide.csv``: the share of each class among the pifs that touch a
  SLIDE cut slope, a SLIDE fill body, both or neither, for both sizes. The SLIDE
  polygons are a partial mapping of the larger earthworks, so "neither" is a
  baseline, not natural ground;
* ``class-by-ground-group.csv``: the share of each class in soil-like ground and
  weak rock (the siz table's ``ground_group``), which the wall prior reads
  together: a cut in rock is the least likely place for a wall.

Run from the repository root, after ``gen_pif_cut_fill.py``::

    uv run --frozen python \
        src/scripts/landloss/ground/steps/s5_pif_cut_fill/table_pif_cut_fill_checks.py

Settings are in ``config.py``.
"""

import numpy as np
import pandas as pd

from landloss.hazard.landslide.instability_zones import read_siz_table
from landloss.hazard.landslide.pif_cut_fill import CLASSES
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import siz_table_path
from scripts.landloss.ground.steps.s5_pif_cut_fill import config
from scripts.landloss.ground.steps.s5_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
)
from scripts.landloss.paths import REPORT_DIR

TAB_DIR = REPORT_DIR / "ground" / "pif-cut-fill" / "tab"
ALL_SIZES = "all"


def slide_reference(table):
    """What the GNS SLIDE genesis polygons say about each pif."""
    cut = table["in_slide_cut"].fillna(value=False).astype(bool)
    fill = table["in_slide_fill"].fillna(value=False).astype(bool)
    reference = np.select(
        [cut & fill, cut, fill], ["cut and fill", "cut", "fill"], "neither"
    )
    return pd.Series(reference, index=table.index, name="slide")


def shares(pifs, by, size_label):
    """The share of each class within each value of ``by``, with the counts."""
    table = pd.crosstab(pifs[by], pifs["cut_fill_class"], normalize="index")
    table = table.reindex(columns=list(CLASSES), fill_value=0.0)
    table.insert(0, "n", pifs[by].value_counts())
    table.insert(0, "pifs", size_label)
    return table.reset_index()


def main(*, extent, check_min_pips):
    """Write the three check tables.

    Args:
        extent: The extent the step was run over.
        check_min_pips: The pifs of at least this many pips are reported on
            their own as well.
    """
    pifs = pd.read_parquet(pif_cut_fill_path(extent=extent))
    table = read_siz_table(siz_table_path(extent=extent))
    pifs = pifs.join(slide_reference(table)).join(table["ground_group"])
    larger = pifs[pifs["n_pips"] >= check_min_pips]
    larger_label = f"{check_min_pips}+ pips"

    counts = pd.DataFrame(
        {
            ALL_SIZES: pifs["cut_fill_class"].value_counts(),
            larger_label: larger["cut_fill_class"].value_counts(),
        }
    ).reindex(list(CLASSES), fill_value=0)
    counts.loc["total"] = counts.sum()
    vs_slide = pd.concat(
        [shares(pifs, "slide", ALL_SIZES), shares(larger, "slide", larger_label)]
    )
    by_ground = pd.concat(
        [
            shares(pifs, "ground_group", ALL_SIZES),
            shares(larger, "ground_group", larger_label),
        ]
    )

    TAB_DIR.mkdir(parents=True, exist_ok=True)
    counts.to_csv(TAB_DIR / "class-counts.csv", index_label="class")
    vs_slide.to_csv(TAB_DIR / "class-vs-slide.csv", index=False, float_format="%.3f")
    by_ground.to_csv(
        TAB_DIR / "class-by-ground-group.csv", index=False, float_format="%.3f"
    )
    print(counts.to_string())
    print(vs_slide.round(2).to_string(index=False))
    print(by_ground.round(2).to_string(index=False))
    print(f"Written to {TAB_DIR}")


if __name__ == "__main__":
    main(extent=config.EXTENT, check_min_pips=config.CHECK_MIN_PIPS)
