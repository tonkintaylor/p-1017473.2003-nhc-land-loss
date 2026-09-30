r"""Write a peak ground acceleration field per realisation, on the site class grid.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s4_pga_realisation/gen_pga_realisations.py

Run step 2 (``s2_site_class/gen_site_class.py``) first, over the same extent:
this reads the site class grid it writes.

1. Reads the site class grid step 2 wrote: the Foster Vs30 model's 100 m NZTM
   cells, each with a TS1170.5 site class.
2. Gives each cell the TS1170.5 PGA of its site class at the return period
   (``landloss.io.ts1170.get_ts1170_pga``, through
   ``landloss.hazard.shaking.site_class.demand_on_site_class_grid``). The PGA
   grids are about 9,930 m a cell, so within one of them PGA changes only where
   the site class does.
3. Scales that field by one lognormal draw per realisation
   (``landloss.hazard.shaking.pga.beta_pga_realisation``), so the chain carries a
   spread in its shaking rather than one fixed field. The spread is a flat 10%
   coefficient of variation over the whole field, a beta shortcut named in that
   module.

At 2500 years TS1170.5 gives *lower* PGA on softer ground (Class II 1.77 g
against Class V 1.00 g at the Wellington grid point): the table carries
non-linear site response. Sa(1.0 s), and so PGV, runs the other way.

What it runs over, for which realisations and at which return period, comes from
``config.py`` beside it.
"""

import sys

import numpy as np

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.pga import BETA_PGA_COV, beta_pga_realisation
from landloss.hazard.shaking.site_class import demand_on_site_class_grid
from landloss.io.ts1170 import SITE_CLASS_NUMERALS, get_ts1170_pga
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    read_site_class,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "hazard" / "shaking"
OUT_STEM = "beta-pga"

# The stream this step draws from. One name per hazard, so realisation 3's
# shaking belongs to the same modelled earthquake as its liquefaction.
RNG_STREAM = "shaking"

RULE = "-" * 72


def pga_path(realisation_id, *, pilot):
    """Return the file a run writes one realisation's PGA field to.

    Args:
        realisation_id: Which modelled earthquake this is.
        pilot: Whether the run is over the pilot box.

    Returns:
        The output path, under ``temp/hazard/shaking/``.
    """
    suffix = "-pilot" if pilot else ""
    return WORK_DIR / f"{OUT_STEM}-r{realisation_id:03d}{suffix}.tif"


def describe_field(site_class, pga, return_period_yr):
    """Print the field the realisations are drawn from, by site class."""
    print(RULE)
    print(f"Grid: {pga.shape[0]} by {pga.shape[1]} cells at 100 m")
    print(f"PGA at {return_period_yr} years, by site class:")
    for numeral, cls in SITE_CLASS_NUMERALS.items():
        in_class = pga.values[site_class.values == cls]
        in_class = in_class[np.isfinite(in_class)]
        if in_class.size:
            print(
                f"  {numeral:>3}: {in_class.size:>7,} cells   PGA (g) "
                f"{in_class.min():.2f} to {in_class.max():.2f}"
            )
    print(f"Spread put on it: {BETA_PGA_COV:.0%} coefficient of variation")


def main(*, pilot, realisation_ids, return_period_yr):
    """Write a PGA field per realisation.

    Args:
        pilot: Whether the run is over the small Wellington pilot box.
        realisation_ids: Which modelled earthquakes to draw.
        return_period_yr: The return period of the TS1170.5 demand, in years.
    """
    site_class = read_site_class(pilot=pilot)
    print(f"Reading the TS1170.5 PGA grids at {return_period_yr} years ...")
    supplied = demand_on_site_class_grid(
        get_ts1170_pga, site_class, return_period_yr=return_period_yr
    )
    describe_field(site_class, supplied, return_period_yr)

    for realisation_id in realisation_ids:
        rng = realisation_seed(constants.BASE_SEED, realisation_id, RNG_STREAM)
        field, factor = beta_pga_realisation(supplied, rng)
        values = field.values
        finite = values[np.isfinite(values)]

        print(RULE)
        print(f"Realisation {realisation_id}, stream {RNG_STREAM!r}")
        print(f"  scaled by {factor:.4f}")
        if finite.size:
            print(f"  median PGA {np.median(finite):.3f} g, max {finite.max():.3f} g")

        out_path = pga_path(realisation_id, pilot=pilot)
        write_raster(field.astype("float32"), out_path)
        print(f"Wrote {out_path}")

    print(RULE)
    print(
        "The spread is one factor over the whole extent, so every property moves "
        "together within a realisation: a beta shortcut. Site class is from Vs30 "
        "alone (L-38)."
    )


if __name__ == "__main__":
    main(
        pilot=config.PILOT,
        realisation_ids=config.REALISATION_IDS,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
