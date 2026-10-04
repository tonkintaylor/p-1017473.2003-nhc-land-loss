"""Draw the candidate wall lines by source over the run's extent.

Reads the GeoParquet ``gen_wall_lines.py`` writes and produces the figure that
run gets checked by eye against:

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/fig_wall_lines.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_wall_lines.wall_lines_path`` where that run's output went -- so the
figure cannot end up drawing a different extent from the one last written.

Two panels.

- **Where.** Every candidate line over the extent, one colour per source in
  precedence order, mapped walls drawn last so they sit on top. What to look
  for: the property boundaries and road frontages should stop at the flat
  land, the terrain breaks should follow the faces, and the mapped walls
  should lie on candidate edges rather than beside them.
- **How much.** Length by source, in kilometres, split by size class, so the
  share of the candidate stock that comes from a mapped feature rather than
  from a boundary is visible beside the map.

Needs network access for the basemap tiles. The figure goes under
``report/exposure/rw/wall-lines/fig/``, which is gitignored -- the script is
the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.exposure.rw.beta_population import SIZE_CLASSES
from landloss.exposure.rw.lines import SOURCES
from landloss.io.area_of_interest import extent_suffix, is_full_extent
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_lines import (
    wall_lines_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "exposure" / "rw" / "wall-lines" / "fig"
DPI = 200

# One fixed colour per source, in precedence order, from the Okabe-Ito set so
# the seven read apart under the common colour vision deficiencies. Assigned by
# name rather than cycled, so a run with no lines of one source does not
# repaint the others.
SOURCE_COLOURS = dict(
    zip(
        SOURCES,
        ("#D55E00", "#0072B2", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#7F7F7F"),
        strict=True,
    )
)
SOURCE_LABELS = {
    "gns_mapped_wall": "GNS mapped wall",
    "slide_cut_fill_line": "SLIDE cut/fill line",
    "slide_cut_edge": "SLIDE cut slope edge",
    "slide_fill_edge": "SLIDE fill body edge",
    "terrain_break": "Terrain break",
    "road_frontage": "Road frontage",
    "property_boundary": "Property boundary",
}

# Lowest precedence drawn first, so the mapped walls end up on top.
DRAW_ORDER = tuple(reversed(SOURCES))
LINE_WIDTH = 0.7

# Size classes shaded light to dark within one hue, so the bars read as one
# magnitude split three ways rather than as three series.
SIZE_ALPHAS = dict(zip(SIZE_CLASSES, (0.35, 0.65, 1.0), strict=True))
BAR_COLOUR = "#0072B2"


def draw_lines(ax, lines, extent):
    """Draw every line over the extent, coloured by source."""
    for source in DRAW_ORDER:
        subset = lines[lines["source"] == source]
        if subset.empty:
            continue
        subset.plot(ax=ax, color=SOURCE_COLOURS[source], linewidth=LINE_WIDTH)

    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    handles = [
        Line2D([0], [0], color=SOURCE_COLOURS[source], linewidth=2)
        for source in SOURCES
    ]
    ax.legend(
        handles,
        [SOURCE_LABELS[source] for source in SOURCES],
        loc="lower left",
        fontsize=6,
        frameon=True,
    )
    ax.set_title(f"Where — {len(lines):,} candidate lines", fontsize=9)


def draw_length_by_source(ax, lines):
    """Draw the length per source in km as stacked bars by size class."""
    km = (
        lines.groupby(["source", "size_class"], observed=True)["length_m"].sum()
        / 1000.0
    )
    positions = np.arange(len(SOURCES))
    left = np.zeros(len(SOURCES))
    for size in SIZE_CLASSES:
        values = np.array([km.get((source, size), 0.0) for source in SOURCES])
        ax.barh(
            positions,
            values,
            left=left,
            color=BAR_COLOUR,
            alpha=SIZE_ALPHAS[size],
            label=size,
            height=0.6,
        )
        left += values
    ax.set_yticks(positions)
    ax.set_yticklabels([SOURCE_LABELS[source] for source in SOURCES], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("Length (km)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(title="Size class", fontsize=6, title_fontsize=7, loc="lower right")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title("How much", fontsize=9)


def main(*, extent):
    """Draw the figure for the last run and write it out.

    Args:
        extent: The extent the run was over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
    """
    in_path = wall_lines_path(extent=extent)
    print(f"Reading {in_path} ...")
    lines = gpd.read_parquet(in_path)
    frame = gpd.GeoDataFrame(geometry=[box(*lines.total_bounds)], crs=lines.crs)

    fig, (ax_map, ax_bars) = plt.subplots(
        1, 2, figsize=(11, 6), gridspec_kw={"width_ratios": (1.6, 1.0)}
    )
    draw_lines(ax_map, lines, frame)
    draw_length_by_source(ax_bars, lines)
    label = "" if is_full_extent(extent) else f" ({extent})"
    fig.suptitle(f"Candidate retaining wall lines by source{label}", fontsize=11)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIG_DIR / f"wall-lines{extent_suffix(extent)}.png"
    fig.savefig(out_path, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT)
