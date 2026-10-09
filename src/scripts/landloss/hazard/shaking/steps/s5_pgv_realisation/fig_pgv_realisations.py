"""Map the PGV step 3 wrote beside each realisation of it step 5 wrote.

    uv run --frozen python src/scripts/landloss/hazard/shaking/steps/s5_pgv_realisation/fig_pgv_realisations.py

Reads ``config.py`` beside it, the same file ``gen_pgv_realisations.py`` reads,
and asks ``gen_pgv.output_path`` and ``gen_pgv_realisations.pgv_path``
where those runs' layers went, so the figure draws the extent, return period and
realisations last run.

- **Supplied PGV.** Step 3's field, the TS1170.5 PGV of each cell's site class
  at the return period, before any spread is put on it.
- **One panel per realisation.** The same cells scaled by that realisation's
  factor. Every panel shares one colour scale, so a realisation reads darker or
  lighter than the supplied field by exactly its factor, and the pattern within
  a panel is the supplied pattern: the factor is one number over the whole
  extent.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/shaking/pgv-realisation/fig/``, which is gitignored -- the
script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rioxarray
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    resolve_extent,
)
from scripts.landloss.hazard.shaking.steps.s3_pgv.gen_pgv import output_path
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import config
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "hazard" / "shaking" / "pgv-realisation" / "fig"
DPI = 200
PGV_CMAP = "Purples"
PANEL_WIDTH_IN = 5.5

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


def realised_factor(field, supplied):
    """Return the one factor a realisation scaled the supplied field by."""
    ratio = field.values / supplied.values
    return float(np.nanmedian(ratio))


def draw_pgv(ax, pgv, extent, *, title, vmin, vmax):
    """Draw one PGV panel on the shared colour scale, with its colour bar."""
    image = ax.imshow(
        pgv.values,
        extent=image_extent(pgv),
        cmap=PGV_CMAP,
        vmin=vmin,
        vmax=vmax,
        alpha=LAYER_ALPHA,
        interpolation="nearest",
        zorder=2,
    )
    style_basemap_ax(ax, extent)
    bar = plt.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    bar.set_label("PGV (m/s)", fontsize=8)
    bar.ax.tick_params(labelsize=7)
    ax.set_title(title, fontsize=9)


def main(*, extent, realisation_ids, return_period_yr):
    """Draw the supplied PGV and each realisation of it.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: Which realisations to draw.
        return_period_yr: The return period of the run being drawn.
    """
    bbox, extent_name = resolve_extent(extent=extent)
    extent_frame = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=constants.DEFAULT_CRS)
    supplied = read_layer(
        output_path("pgv", return_period_yr=return_period_yr, extent=extent)
    )
    fields = {
        realisation_id: read_layer(pgv_path(realisation_id, extent=extent))
        for realisation_id in realisation_ids
    }

    # One scale across every panel, so a realisation's factor shows as a shade.
    stacked = np.concatenate(
        [supplied.values.ravel()] + [f.values.ravel() for f in fields.values()]
    )
    vmin, vmax = np.nanmin(stacked), np.nanmax(stacked)

    panels = 1 + len(fields)
    fig, axes = plt.subplots(1, panels, figsize=(PANEL_WIDTH_IN * panels, 5.5))
    axes = np.atleast_1d(axes)
    draw_pgv(
        axes[0],
        supplied,
        extent_frame,
        title=f"Supplied PGV, {return_period_yr}-year TS1170.5 demand",
        vmin=vmin,
        vmax=vmax,
    )
    for ax, (realisation_id, field) in zip(axes[1:], fields.items(), strict=True):
        factor = realised_factor(field, supplied)
        draw_pgv(
            ax,
            field,
            extent_frame,
            title=f"Realisation {realisation_id}, factor {factor:.3f}",
            vmin=vmin,
            vmax=vmax,
        )
    fig.suptitle(extent_name, fontsize=10)
    fig.tight_layout()

    suffix = extent_suffix(extent)
    path = FIG_DIR / f"pgv-realisations-{return_period_yr}yr{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        return_period_yr=config.RETURN_PERIOD_YR,
    )
