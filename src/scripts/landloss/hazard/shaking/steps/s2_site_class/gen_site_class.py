r"""Write the TS1170.5 site class per 100 m cell over the extent, from Foster Vs30.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s2_site_class/gen_site_class.py

Reads the Foster et al. (2019) Vs30 model over the extent and assigns each cell
its TS1170.5:2025 Table 3.3 site class from Vs30 alone
(``landloss.hazard.shaking.site_class``; see its docstring for what Vs30 alone
leaves out). The model's own grid -- 100 m NZTM cells on 100 m-aligned bounds --
is the grid written, and the grid the shaking steps that read the site class
(PGV, and PGA to follow) put their demand on.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import numpy as np

from landloss.common.utils.terrain import write_raster
from landloss.hazard.shaking.site_class import ts1170_site_class_from_vs30
from landloss.io.ts1170 import SITE_CLASS_NUMERALS
from landloss.io.vs30 import get_foster_2019_vs30
from scripts.landloss.hazard.shaking.steps.s1_pga_realisation.gen_pga_realisations import (
    resolve_extent,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"

RULE = "-" * 72


def site_class_path(*, pilot):
    """Return the file a run writes the site class grid to.

    Args:
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"site-class-100m{suffix}.tif"


def main(*, pilot):
    """Write the site class grid over the extent.

    Args:
        pilot: Whether to clip to the small Wellington pilot box.
    """
    bbox, extent_name = resolve_extent(pilot=pilot)

    print("Reading the Foster et al. (2019) Vs30 model ...", flush=True)
    vs30 = get_foster_2019_vs30(bbox)
    site_class = ts1170_site_class_from_vs30(vs30)

    values = vs30.values[np.isfinite(vs30.values)]
    classes = site_class.values[np.isfinite(site_class.values)]
    print(RULE)
    print(f"Extent: {extent_name}")
    print(f"Grid: {vs30.shape[0]} by {vs30.shape[1]} cells at 100 m")
    if values.size:
        print(
            f"Vs30 (m/s): min {values.min():.0f}   median {np.median(values):.0f}   "
            f"max {values.max():.0f}"
        )
    print("Site class share of cells:")
    for numeral, cls in SITE_CLASS_NUMERALS.items():
        share = np.mean(classes == cls) if classes.size else 0.0
        print(f"  {numeral:>3}: {share:6.1%}")

    path = site_class_path(pilot=pilot)
    write_raster(site_class.astype("float32"), path)
    print(RULE)
    print(f"Wrote {path}")
    print(
        "Site class is from Vs30 alone, without the profile criteria of TS1170.5 "
        "Table 3.3, and Class VII is taken as Class VI (L-38)."
    )


if __name__ == "__main__":
    main(pilot=config.PILOT)
