"""Map every terrain derivative ground step 1 wrote over the extent last run.

    uv run --frozen python src/scripts/landloss/ground/steps/s1_terrain/fig_terrain_derivatives.py

Reads ``config.py`` beside it, the same file ``gen_terrain_derivatives.py``
reads, and asks ``terrain_path()`` where that run's layers went, so the figure
draws the extent last run. One panel per layer in ``TERRAIN_LAYERS``, each on
its own colour scale: the signed layers (the residuals and the
topographic position) on a diverging scale centred on zero, any other on a
sequential one. The scales are clipped at the 1st and 99th percentiles so a
single cliff does not wash out the rest of the extent.

Needs network access for the basemap tiles. The figure goes under
``report/ground/terrain-derivatives/fig/``, which is gitignored --
the script is the record of how it was made, not the PNG.
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
    read_layer,
)
from scripts.landloss.ground.steps.s1_terrain.gen_terrain_derivatives import (
    TERRAIN_LAYERS,
    terrain_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "ground" / "terrain-derivatives" / "fig"
DPI = 200
PANEL_WIDTH_IN = 5.0
COLUMNS = 4

# Enough of the basemap shows through to place the layers, not so much that it
# competes with them.
LAYER_ALPHA = 0.85

# The layers that run both ways round zero, drawn on a diverging scale.
SIGNED_LAYERS = {
    "cut-fill-residual-30m",
    "cut-fill-residual-100m",
    "topographic-position-100m",
}
SIGNED_CMAP = "RdBu_r"
HEIGHT_CMAP = "viridis"

# The percentile clip on each colour scale.
CLIP = (1, 99)

UNITS = {
    "cut_fill_residual_m": "m (cut < 0 < fill)",
    "topographic_position_m": "m",
}


def image_extent(raster):
    """Return the raster's bounds in the order ``imshow`` takes them."""
    minx, miny, maxx, maxy = raster.rio.bounds()
    return (minx, maxx, miny, maxy)


def colour_limits(values, *, signed):
    """Return the colour scale limits, clipped to the percentiles, centred if signed."""
    present = values[np.isfinite(values)]
    if present.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(present, CLIP)
    if signed:
        reach = max(abs(low), abs(high))
        return -reach, reach
    return low, high


def draw_layer(ax, key, layer, extent):
    """Draw one layer on its own colour scale, with its colour bar."""
    signed = key in SIGNED_LAYERS
    vmin, vmax = colour_limits(layer.values, signed=signed)
    image = ax.imshow(
        layer.values,
        extent=image_extent(layer),
        cmap=SIGNED_CMAP if signed else HEIGHT_CMAP,
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
    bar.set_label(UNITS[TERRAIN_LAYERS[key]], fontsize=7)
    bar.ax.tick_params(labelsize=6)
    nan_share = float(np.isnan(layer.values).mean())
    ax.set_title(f"{key} ({nan_share:.0%} NaN)", fontsize=9)


def main(*, extent):
    """Draw every terrain derivative over the extent it was built on.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
    """
    layers = {
        key: read_layer(terrain_path(key, extent=extent)) for key in TERRAIN_LAYERS
    }
    first = next(iter(layers.values()))
    frame = gpd.GeoDataFrame(
        geometry=[box(*first.rio.bounds())], crs=constants.DEFAULT_CRS
    )

    rows = -(-len(layers) // COLUMNS)
    fig, axes = plt.subplots(
        rows, COLUMNS, figsize=(PANEL_WIDTH_IN * COLUMNS, PANEL_WIDTH_IN * rows)
    )
    axes = np.atleast_1d(axes).ravel()
    for ax, (key, layer) in zip(axes, layers.items(), strict=False):
        draw_layer(ax, key, layer, frame)
    for ax in axes[len(layers) :]:
        ax.set_axis_off()
    fig.suptitle(
        "Terrain derivatives" + ("" if is_full_extent(extent) else f" ({extent})"),
        fontsize=11,
    )
    fig.tight_layout()

    suffix = extent_suffix(extent)
    path = FIG_DIR / f"terrain-derivatives{suffix}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main(extent=config.EXTENT)
