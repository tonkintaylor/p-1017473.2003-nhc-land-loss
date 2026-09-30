"""Map the site class step 2 wrote and the PGV step 3 wrote, side by side.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s3_pgv/fig_pgv.py

Reads ``config.py`` beside it, the same file ``gen_pgv.py`` reads, and asks
``gen_site_class.site_class_path`` and ``gen_pgv.output_path`` where those runs'
layers went, so the figure draws the extent and return period last run.

- **Site class.** The TS1170.5 class per 100 m cell, from Vs30 alone. It is the
  panel to check by eye against the ground: stiff hill country should read
  Class II, and the soft ground round the harbour and the valley floors should
  read IV to VI.
- **PGV.** The same cells after the class picks its Sa(1.0 s). Within one 0.1
  degree TS1170.5 grid cell PGV only changes where the site class does, so the
  pattern should follow the left panel, stepped where the coarse demand grid
  changes.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/shaking/pgv/fig/``, which is gitignored -- the script is the
record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rioxarray
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.ts1170 import SITE_CLASS_NUMERALS
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    resolve_extent,
    site_class_path,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv import config
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "shaking" / "pgv" / "fig"
DPI = 200

# Site class is ordered, stiff to soft, so it takes one hue light to dark rather
# than six unrelated colours: softer ground reads darker, as it shakes harder.
CLASS_NUMERALS = {number: numeral for numeral, number in SITE_CLASS_NUMERALS.items()}
CLASS_COLOURS = plt.get_cmap("Oranges")(np.linspace(0.2, 0.95, len(CLASS_NUMERALS)))
PGV_CMAP = "Purples"

# Enough of the basemap shows through to place the layers, not so much that it
# competes with them.
LAYER_ALPHA = 0.8


def read_layer(path):
    """Read one layer a shaking step wrote."""
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def image_extent(raster):
    """Return the raster's bounds in the order ``imshow`` takes them."""
    minx, miny, maxx, maxy = raster.rio.bounds()
    return (minx, maxx, miny, maxy)


def draw_site_class(ax, site_class, extent):
    """Draw the site class panel, with a legend naming the classes present."""
    classes = sorted(CLASS_NUMERALS)
    cmap = ListedColormap(CLASS_COLOURS)
    norm = BoundaryNorm(np.arange(classes[0] - 0.5, classes[-1] + 1.5), cmap.N)
    ax.imshow(
        site_class.values,
        extent=image_extent(site_class),
        cmap=cmap,
        norm=norm,
        alpha=LAYER_ALPHA,
        interpolation="nearest",
        zorder=2,
    )
    style_basemap_ax(ax, extent)

    present = {int(c) for c in np.unique(site_class.values) if np.isfinite(c)}
    handles = [
        Patch(color=CLASS_COLOURS[i], label=f"{CLASS_NUMERALS[cls]}")
        for i, cls in enumerate(classes)
        if cls in present
    ]
    ax.legend(handles=handles, title="Site class", loc="upper left", fontsize=7)
    ax.set_title("TS1170.5 site class from Vs30", fontsize=9)


def draw_pgv(ax, pgv, extent, *, return_period_yr):
    """Draw the PGV panel, with its colour bar."""
    image = ax.imshow(
        pgv.values,
        extent=image_extent(pgv),
        cmap=PGV_CMAP,
        alpha=LAYER_ALPHA,
        interpolation="nearest",
        zorder=2,
    )
    style_basemap_ax(ax, extent)
    bar = plt.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    bar.set_label("PGV (m/s)", fontsize=8)
    bar.ax.tick_params(labelsize=7)
    ax.set_title(f"PGV, {return_period_yr}-year TS1170.5 demand", fontsize=9)


def main(*, pilot, return_period_yr):
    """Draw the site class and PGV maps.

    Args:
        pilot: Whether the run being drawn was over the pilot box.
        return_period_yr: The return period of the run being drawn.
    """
    bbox, extent_name = resolve_extent(pilot=pilot)
    extent = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=constants.DEFAULT_CRS)
    site_class = read_layer(site_class_path(pilot=pilot))
    pgv = read_layer(output_path("pgv", return_period_yr=return_period_yr, pilot=pilot))

    fig, (ax_class, ax_pgv) = plt.subplots(1, 2, figsize=(11, 5.5))
    draw_site_class(ax_class, site_class, extent)
    draw_pgv(ax_pgv, pgv, extent, return_period_yr=return_period_yr)
    fig.suptitle(extent_name, fontsize=10)
    fig.tight_layout()

    suffix = "-pilot" if pilot else ""
    path = FIG_DIR / f"site-class-pgv-{return_period_yr}yr{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(pilot=config.PILOT, return_period_yr=config.RETURN_PERIOD_YR)
