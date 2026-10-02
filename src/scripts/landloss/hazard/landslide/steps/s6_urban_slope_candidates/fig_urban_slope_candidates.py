"""Map the candidate urban failure polygons at each scale.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s6_urban_slope_candidates/fig_urban_slope_candidates.py

Reads ``config.py`` beside it, the same file ``gen_urban_slope_candidates.py``
reads, and asks ``gen_urban_slope_candidates.urban_slope_candidates_path``
where that run's output went, so the figure draws the extent last run.

One panel per scale in ``config.SCALES_M``, the candidates coloured by slope
band on one sequential scale from the gentlest band to the steepest. What the
panels are for is the nesting: a 1 m face should sit inside the 3 m and 10 m
bank around it, the patch edges should follow the crests and toes of the
terrain, and the gentlest band should be there too, because it is a candidate
class and not a cut-off. A panel of rectangles would give away a grid artefact.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/urban-slope-candidates/fig/``, which is gitignored --
the script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide.urban.delineation import SLOPE_BAND_LABELS
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates import config
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates.gen_urban_slope_candidates import (
    urban_slope_candidates_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic.
FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-candidates" / "fig"
DPI = 200
PANEL_WIDTH_IN = 6.0

# One hue, light for the gentlest band to dark for the steepest: the band is a
# magnitude, so it takes a sequential scale rather than a categorical one.
BAND_CMAP = "Oranges"
FILL_ALPHA = 0.75
EDGE_WIDTH = 0.2

RULE = "-" * 72


def band_colours():
    """One colour per slope band, gentlest lightest."""
    cmap = plt.get_cmap(BAND_CMAP)
    steps = len(SLOPE_BAND_LABELS)
    # Start part way up the ramp so the gentlest band shows against the basemap.
    return {
        band: cmap(0.25 + 0.75 * position / (steps - 1))
        for position, band in enumerate(SLOPE_BAND_LABELS)
    }


def figure_path(*, pilot):
    """Return the file the figure is written to."""
    suffix = "-pilot" if pilot else ""
    return FIG_DIR / f"urban-slope-candidates{suffix}.png"


def draw_panel(ax, candidates, extent, colours, *, scale_m):
    """Draw one scale's candidates over the basemap."""
    for band, colour in colours.items():
        subset = candidates[candidates["slope_band"] == band]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            color=colour,
            alpha=FILL_ALPHA,
            edgecolor="black",
            linewidth=EDGE_WIDTH,
        )
    style_basemap_ax(
        ax, extent, arrow_kwargs={"scale": 0.25}, scalebar_kwargs={"font_size": 7}
    )
    ax.set_title(
        f"{scale_m} m: {len(candidates):,} candidates, "
        f"{candidates['area_m2'].sum() / 10_000:,.1f} ha",
        fontsize=10,
    )


def main(*, pilot, scales_m):
    """Draw the candidates of every scale, one panel each.

    Args:
        pilot: Whether the run to draw was over the pilot box.
        scales_m: The scales to draw, one panel each.
    """
    path = urban_slope_candidates_path(pilot=pilot)
    print(f"Reading {path} ...")
    candidates = gpd.read_parquet(path)
    extent = gpd.GeoDataFrame(
        geometry=[box(*candidates.total_bounds)], crs=candidates.crs
    )
    colours = band_colours()

    columns = 2
    rows = -(-len(scales_m) // columns)
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(PANEL_WIDTH_IN * columns, PANEL_WIDTH_IN * rows),
        squeeze=False,
    )
    for ax, scale_m in zip(axes.flat, scales_m, strict=False):
        subset = candidates[candidates["scale_m"] == scale_m]
        draw_panel(ax, subset, extent, colours, scale_m=scale_m)
    for ax in axes.flat[len(scales_m) :]:
        ax.set_axis_off()

    handles = [
        Patch(
            facecolor=colour,
            edgecolor="black",
            linewidth=EDGE_WIDTH,
            label=f"{band} degrees",
        )
        for band, colour in colours.items()
    ]
    fig.legend(
        handles=handles,
        title="Slope band",
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=8,
        title_fontsize=9,
    )
    fig.suptitle(
        "Urban slope failure candidates by delineation scale", fontsize=12, y=0.995
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))

    out_path = figure_path(pilot=pilot)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
    print(RULE)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(pilot=config.PILOT, scales_m=config.SCALES_M)
