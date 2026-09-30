r"""Write the TS1170.5 site class per 100 m cell over the extent, from Foster Vs30.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s2_site_class/gen_site_class.py

Reads the Foster et al. (2019) Vs30 model over the extent and assigns each cell
its TS1170.5:2025 Table 3.3 site class from Vs30 alone
(``landloss.hazard.shaking.site_class``; see its docstring for what Vs30 alone
leaves out). Cells the model leaves without a Vs30 value, along the harbour
edge, take the class of the nearest classed cell within 200 m
(``fill_site_class_gaps``), and a mask of those cells is written beside the
grid. The model's own grid -- 100 m NZTM cells on 100 m-aligned bounds --
is the grid written, and the grid the shaking steps that read the site class
(PGV, and PGA to follow) put their demand on.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import numpy as np
import rioxarray

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.shaking.site_class import (
    GAP_FILL_MAX_DISTANCE_M,
    fill_site_class_gaps,
    ts1170_site_class_from_vs30,
)
from landloss.io.area_of_interest import SMALL_WLG_PILOT, get_study_areas
from landloss.io.ts1170 import SITE_CLASS_NUMERALS
from landloss.io.vs30 import get_foster_2019_vs30
from scripts.landloss.hazard.shaking.steps.s2_site_class import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"

RULE = "-" * 72


def resolve_extent(*, pilot):
    """Return the bounding box, in NZTM, and its name for this run.

    The shaking steps all run over this extent: this step sets the grid, and
    the steps after it read the grid this step wrote.
    """
    if pilot:
        return SMALL_WLG_PILOT.bbox(constants.DEFAULT_CRS), "Small Wellington pilot"
    areas = get_study_areas(constants.DEFAULT_CRS)
    return tuple(areas.total_bounds), "Four territorial authorities"


def site_class_path(*, pilot):
    """Return the file a run writes the site class grid to.

    Args:
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"site-class-100m{suffix}.tif"


def filled_mask_path(*, pilot):
    """Return the file a run writes the mask of gap-filled cells to.

    Args:
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"site-class-filled-100m{suffix}.tif"


def read_site_class(*, pilot):
    """Read the site class grid this step wrote, for the steps after it.

    Raises:
        FileNotFoundError: If step 2 has not been run over this extent.
    """
    path = site_class_path(pilot=pilot)
    if not path.exists():
        msg = f"No site class grid at {path}. Run s2_site_class/gen_site_class.py "
        msg += f"with PILOT = {pilot} first."
        raise FileNotFoundError(msg)
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def main(*, pilot):
    """Write the site class grid over the extent.

    Args:
        pilot: Whether to clip to the small Wellington pilot box.
    """
    bbox, extent_name = resolve_extent(pilot=pilot)

    print("Reading the Foster et al. (2019) Vs30 model ...", flush=True)
    vs30 = get_foster_2019_vs30(bbox)
    site_class, was_filled = fill_site_class_gaps(ts1170_site_class_from_vs30(vs30))

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
    gaps = int(np.isnan(vs30.values).sum())
    filled = int(was_filled.values.sum())
    print(
        f"Cells without a Vs30 value: {gaps:,}; {filled:,} took the class of a "
        f"classed cell within {GAP_FILL_MAX_DISTANCE_M:.0f} m"
    )
    print("Site class share of cells:")
    for numeral, cls in SITE_CLASS_NUMERALS.items():
        share = np.mean(classes == cls) if classes.size else 0.0
        print(f"  {numeral:>3}: {share:6.1%}")

    print(RULE)
    path = site_class_path(pilot=pilot)
    write_raster(site_class.astype("float32"), path)
    print(f"Wrote {path}")
    path = filled_mask_path(pilot=pilot)
    write_raster(was_filled.astype("uint8"), path)
    print(f"Wrote {path}")
    print(
        "Site class is from Vs30 alone, without the profile criteria of TS1170.5 "
        "Table 3.3, and Class VII is taken as Class VI (L-38)."
    )


if __name__ == "__main__":
    main(pilot=config.PILOT)
