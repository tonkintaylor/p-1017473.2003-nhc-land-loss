r"""Write Sa(1.0 s) and PGV per 100 m cell over the extent, from the site class.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s3_pgv/gen_pgv.py

Run step 2 (``s2_site_class/gen_site_class.py``) first, over the same extent:
this reads the site class grid it writes.

1. Reads the site class grid step 2 wrote. Its grid, the Foster Vs30 model's
   100 m NZTM cells, is the grid every output is written on.
2. Reads the TS1170.5 Sa(1.0 s) grid of each site class at the return period
   (``landloss.io.ts1170.get_ts1170_sa_t1``), puts each on the site class grid
   by nearest neighbour, and takes per cell the one for that cell's class. The
   Sa(1.0 s) grids are about 9,930 m a cell, so within one of them the value
   changes only where the site class does.
3. Converts Sa(1.0 s) to PGV with ``landloss.hazard.shaking.pgv``, as
   PGV (mm/s) = 750 x Sa(1.0 s) (g), written in m/s.

What it runs over, and at which return period, comes from ``config.py`` beside
it.
"""

import sys

import numpy as np
import rioxarray
from rasterio.enums import Resampling

from landloss.common.utils.terrain import write_raster
from landloss.hazard.shaking.pgv import pgv_m_s_from_sa_1s
from landloss.hazard.shaking.site_class import select_by_site_class
from landloss.io.ts1170 import SITE_CLASS_NUMERALS, get_ts1170_sa_t1
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    site_class_path,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv import config
from scripts.landloss.paths import TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"

# The layers this step writes, and the name each raster carries.
LAYERS = {
    "sa-t1": "sa_t1_g",
    "pgv": "pgv_m_s",
}

RULE = "-" * 72


def output_path(layer, *, return_period_yr, pilot):
    """Return the file a run writes one layer to.

    Args:
        layer: One of :data:`LAYERS`.
        return_period_yr: The return period of the demand.
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.

    Raises:
        ValueError: If the layer is not one this step writes.
    """
    if layer not in LAYERS:
        msg = f"No layer {layer!r}; expected one of {sorted(LAYERS)}."
        raise ValueError(msg)
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{layer}-{return_period_yr}yr-100m{suffix}.tif"


def read_site_class(*, pilot):
    """Read the site class grid step 2 wrote.

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


def sa_t1_by_site_class(return_period_yr, template):
    """Read each site class's Sa(1.0 s) grid, put on the template grid."""
    return {
        site_class: get_ts1170_sa_t1(return_period_yr, site_class).rio.reproject_match(
            template, resampling=Resampling.nearest
        )
        for site_class in SITE_CLASS_NUMERALS.values()
    }


def describe(name, values, unit):
    """Print the range of one layer."""
    finite = values[np.isfinite(values)]
    if finite.size:
        print(
            f"{name} ({unit}): min {finite.min():.3f}   "
            f"median {np.median(finite):.3f}   max {finite.max():.3f}"
        )


def main(*, pilot, return_period_yr):
    """Write the Sa(1.0 s) and PGV grids over the extent.

    Args:
        pilot: Whether the run is over the small Wellington pilot box.
        return_period_yr: The return period of the TS1170.5 demand, in years.
    """
    site_class = read_site_class(pilot=pilot)

    print(f"Reading the TS1170.5 Sa(1.0 s) grids at {return_period_yr} years ...")
    sa_t1 = select_by_site_class(
        site_class, sa_t1_by_site_class(return_period_yr, site_class)
    )
    pgv = pgv_m_s_from_sa_1s(sa_t1)

    print(RULE)
    print(f"Grid: {site_class.shape[0]} by {site_class.shape[1]} cells at 100 m")
    describe("Sa(1.0 s)", sa_t1.values, "g")
    describe("PGV", pgv.values, "m/s")

    print(RULE)
    for layer, raster in (("sa-t1", sa_t1), ("pgv", pgv)):
        path = output_path(layer, return_period_yr=return_period_yr, pilot=pilot)
        write_raster(raster.astype("float32").rename(LAYERS[layer]), path)
        print(f"Wrote {path}")


if __name__ == "__main__":
    main(pilot=config.PILOT, return_period_yr=config.RETURN_PERIOD_YR)
