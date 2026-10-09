"""Map the slope and the aspect ground step 1 wrote at each cell size, side by side.

    uv run --frozen python src/scripts/landloss/ground/steps/s1_terrain/fig_multiscale_slope.py

Reads ``config.py`` beside it, the same file ``gen_multiscale_slope.py`` reads,
and asks ``slope_path()`` and ``aspect_path()`` where that run's layers went,
so the figure draws the extent and cell sizes last run. One column per cell
size: the slope on a shared scale across every column, so a hillside reads
steeper at 1 m than at 100 m by exactly what the cell size does to it, and the
aspect on a cyclic scale under it.

Needs network access for the basemap tiles. The figure goes under
``report/ground/multiscale-slope/fig/``, which is gitignored -- the
script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.io.area_of_interest import extent_suffix, is_full_extent
from scripts.landloss.ground.steps.s1_terrain import config
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    aspect_path,
    read_layer,
    slope_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "ground" / "multiscale-slope" / "fig"
DPI = 200
PANEL_WIDTH_IN = 4.5
SLOPE_CMAP = "YlOrRd"
ASPECT_CMAP = "twilight"
SLOPE_MAX_DEGREES = 60.0

# Enough of the basemap shows through to place the layers, not so much that it
# competes with them.
LAYER_ALPHA = 0.85


def image_extent(raster):
    """Return the raster's bounds in the order ``imshow`` takes them."""
    minx, miny, maxx, maxy = raster.rio.bounds()
    return (minx, maxx, miny, maxy)


def draw_panel(ax, layer, extent, *, title, cmap, vmin, vmax, label):
    """Draw one layer with its colour bar on a basemap."""
    image = ax.imshow(
        layer.values,
        extent=image_extent(layer),
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        alpha=LAYER_ALPHA,
        interpolation="nearest",
        zorder=2,
    )
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 6},
        scalebar_kwargs={"font_size": 6},
    )
    bar = plt.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
    bar.set_label(label, fontsize=7)
    bar.ax.tick_params(labelsize=6)
    ax.set_title(title, fontsize=9)


def main(*, extent, resolutions_m):
    """Draw the slope and the aspect at each cell size.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        resolutions_m: The cell sizes to draw.

    Raises:
        FileNotFoundError: If a slope or an aspect at one of the cell sizes was
            not built.
    """
    resolutions = sorted(resolutions_m)
    missing = [
        r
        for r in resolutions
        if not (
            slope_path(r, extent=extent).exists()
            and aspect_path(r, extent=extent).exists()
        )
    ]
    if missing:
        sizes = ", ".join(f"{r:g} m" for r in missing)
        msg = (
            f"No slope or aspect at {sizes} for {extent}: ground step 1 builds them "
            "only at SLOPE_RESOLUTIONS_M. Add those cell sizes to "
            "SLOPE_RESOLUTIONS_M in src/scripts/landloss/ground/steps/s1_terrain/"
            "config.py and rerun gen_multiscale_slope.py to build them."
        )
        raise FileNotFoundError(msg)
    slopes = {r: read_layer(slope_path(r, extent=extent)) for r in resolutions}
    aspects = {r: read_layer(aspect_path(r, extent=extent)) for r in resolutions}
    first = next(iter(slopes.values()))
    frame = gpd.GeoDataFrame(
        geometry=[box(*first.rio.bounds())], crs=constants.DEFAULT_CRS
    )

    fig, axes = plt.subplots(
        2,
        len(resolutions),
        figsize=(PANEL_WIDTH_IN * len(resolutions), PANEL_WIDTH_IN * 2),
    )
    axes = np.atleast_2d(axes)
    for column, resolution in enumerate(resolutions):
        draw_panel(
            axes[0, column],
            slopes[resolution],
            frame,
            title=f"Slope, {resolution:g} m",
            cmap=SLOPE_CMAP,
            vmin=0.0,
            vmax=SLOPE_MAX_DEGREES,
            label="degrees",
        )
        draw_panel(
            axes[1, column],
            aspects[resolution],
            frame,
            title=f"Aspect, {resolution:g} m",
            cmap=ASPECT_CMAP,
            vmin=0.0,
            vmax=360.0,
            label="degrees clockwise from north, downhill",
        )
    fig.suptitle(
        "Slope and aspect by cell size"
        + ("" if is_full_extent(extent) else f" ({extent})")
    )
    fig.tight_layout()

    suffix = extent_suffix(extent)
    path = FIG_DIR / f"multiscale-slope{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, resolutions_m=config.RESOLUTIONS_M)
