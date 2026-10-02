r"""Write a peak ground velocity field per realisation, on the site class grid.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s5_pgv_realisation/gen_pgv_realisations.py

Run step 3 (``s3_pgv/gen_pgv.py``) first, over the same extent and return
period: this reads the PGV grid it writes.

1. Reads the PGV grid step 3 wrote: the Foster Vs30 model's 100 m NZTM cells,
   each with the PGV of its TS1170.5 site class at the return period, in m/s.
2. Scales that field by **the same lognormal factor step 4 applied to PGA** for
   the same realisation id, so one modelled earthquake's two measures agree.
   Step 4 does not write its factor; this step recomputes it from the same
   seed. ``beta_scale_factor(realisation_seed(BASE_SEED, realisation_id,
   "shaking"))`` is the first and only draw step 4's ``beta_pga_realisation``
   makes on that generator, and ``landloss.hazard.shaking.pgv.beta_pgv_realisation``
   makes the same draw on a generator seeded the same way. A unit test in
   ``tests/landloss/hazard/shaking/test_pga.py`` holds the two together.

Within one realisation every cell moves by one factor, as step 4's PGA does: a
beta shortcut named in ``landloss.hazard.shaking.pga``.

What it runs over, for which realisations and at which return period, comes from
``config.py`` beside it.
"""

import sys

import numpy as np
import rioxarray

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.pga import BETA_PGA_COV
from landloss.hazard.shaking.pgv import beta_pgv_realisation
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    RNG_STREAM,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"
OUT_STEM = "pgv"

RULE = "-" * 72


def pgv_path(realisation_id, *, pilot):
    """Return the file a run writes one realisation's PGV field to.

    Args:
        realisation_id: Which modelled earthquake this is.
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.tif"


def read_pgv(*, return_period_yr, pilot):
    """Read the PGV grid step 3 wrote, at the return period and over the extent.

    Args:
        return_period_yr: The return period of the TS1170.5 demand, in years.
        pilot: Whether the run is over the pilot box.

    Returns:
        The grid, in m/s, with nodata masked to NaN.
    """
    path = output_path("pgv", return_period_yr=return_period_yr, pilot=pilot)
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def describe_field(pgv, return_period_yr):
    """Print the field the realisations are drawn from."""
    finite = pgv.values[np.isfinite(pgv.values)]
    print(RULE)
    print(f"Grid: {pgv.shape[0]} by {pgv.shape[1]} cells at 100 m")
    if finite.size:
        print(
            f"PGV at {return_period_yr} years (m/s): min {finite.min():.3f}   "
            f"median {np.median(finite):.3f}   max {finite.max():.3f}, "
            f"over {finite.size:,} cells"
        )
    print(f"Spread put on it: {BETA_PGA_COV:.0%} coefficient of variation")


def main(*, pilot, realisation_ids, return_period_yr):
    """Write a PGV field per realisation.

    Args:
        pilot: Whether the run is over the small Wellington pilot box.
        realisation_ids: Which modelled earthquakes to draw.
        return_period_yr: The return period of the TS1170.5 demand, in years.
    """
    print(f"Reading the PGV grid step 3 wrote at {return_period_yr} years ...")
    supplied = read_pgv(return_period_yr=return_period_yr, pilot=pilot)
    describe_field(supplied, return_period_yr)

    for realisation_id in realisation_ids:
        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        field, factor = beta_pgv_realisation(supplied, rng)
        values = field.values
        finite = values[np.isfinite(values)]

        print(RULE)
        print(f"Realisation {realisation_id}, stream {RNG_STREAM!r}")
        print(f"  scaled by {factor:.4f}, the factor step 4 put on PGA")
        if finite.size:
            print(
                f"  median PGV {np.median(finite):.3f} m/s, max {finite.max():.3f} m/s"
            )

        out_path = pgv_path(realisation_id, pilot=pilot)
        write_raster(field.astype("float32"), out_path)
        print(f"Wrote {out_path}")

    print(RULE)
    print(
        "The spread is one factor over the whole extent, the same factor as the "
        "realisation's PGA, so a realisation's two measures agree and every "
        "property moves together within it: a beta shortcut."
    )


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        realisation_ids=config.REALISATION_IDS,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
