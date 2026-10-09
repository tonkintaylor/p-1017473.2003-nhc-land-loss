"""Draw a few neighbouring properties' insured land, close enough to judge by eye.

The extent is an 8 metre buffer of the building outlines, split between
neighbours on which building is nearer. Neither of those is visible in a summary
statistic: an area total cannot show a buffer that has swallowed the street, or
a boundary between two properties drawn down the wrong side of a garage. This
figure puts the buildings, the buffer and the split on the same picture:

    uv run --frozen python src/scripts/landloss/exposure/land/steps/s5_insured_land_extent/fig_insured_land.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_insured_land.insured_land_path`` where that run's output went -- so the
figure cannot end up drawing a different extent from the one last written.

Two panels.

- **Close up.** The busiest neighbourhood in the run, at
  ``config.CLOSE_UP_M`` across, with one colour per property and the building
  outlines drawn over the top. What to look for: every coloured patch wrapped
  around its own buildings, and no two colours overlapping anywhere.
- **How big.** Insured area per property across the whole run, as a histogram.
  A property is bounded below by its building footprint, so the left edge is the
  smallest sheds in the extent; a long right tail is properties with several
  buildings spread far enough apart not to merge.

Needs ``LINZ_API_KEY`` in ``.env``: the building outlines are fetched again over
the close-up window alone, rather than written out by the generation step, which
is a small extra read against carrying a second layer through ``temp/``. Needs
network access for the basemap tiles too. The figure goes under
``report/exposure/land/insured-land/fig/``, which is gitignored -- the script is
the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch
from shapely import STRtree
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.exposure.land.extent import (
    AREA_COLUMN,
    INSURED_LAND_BUFFER_M,
    drop_non_residential_buildings,
)
from landloss.io.readers import get_nz_building_outlines
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import config
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "exposure" / "land" / "insured-land" / "fig"
DPI = 200

# A qualitative ramp, so that two properties sharing a boundary are told apart
# by hue rather than by shade. Twenty colours is more than a window this size
# ever holds.
PALETTE = mpl.colormaps["tab20"]
FILL_ALPHA = 0.65

BUILDING_EDGE = "#1a1a1a"
HISTOGRAM_BINS = 40


def busiest_window(extent, width_m):
    """Choose the neighbourhood with the most properties in it.

    The close-up is there to show properties against their neighbours, so an
    isolated house on a hillside is the least useful window in the run. The
    busiest one is also where the shared ground rule is doing the most work.

    Args:
        extent: The insured land polygons.
        width_m: How wide the window is, in metres.

    Returns:
        The window as a one row GeoDataFrame, ready to pass to the map styling.
    """
    centroids = extent.geometry.centroid
    tree = STRtree(centroids.to_numpy())
    neighbourhoods = centroids.buffer(width_m / 2).to_numpy()

    left, _ = tree.query(neighbourhoods, predicate="intersects")
    counts = np.bincount(left, minlength=len(extent))
    centre = centroids.iloc[int(counts.argmax())]

    half = width_m / 2
    window = box(centre.x - half, centre.y - half, centre.x + half, centre.y + half)
    return gpd.GeoDataFrame(geometry=[window], crs=extent.crs)


def draw_close_up(ax, extent, buildings, window):
    """Draw the properties in the window, one colour each, with the buildings over."""
    in_window = extent[extent.intersects(window.geometry.iloc[0])]

    for position, (_, row) in enumerate(in_window.iterrows()):
        gpd.GeoSeries([row.geometry], crs=extent.crs).plot(
            ax=ax,
            color=PALETTE(position % PALETTE.N),
            edgecolor=PALETTE(position % PALETTE.N),
            linewidth=0.6,
            alpha=FILL_ALPHA,
        )

    if not buildings.empty:
        buildings.plot(ax=ax, facecolor="none", edgecolor=BUILDING_EDGE, linewidth=0.8)

    style_basemap_ax(
        ax,
        window,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(
        f"Close up — {config.CLOSE_UP_M:,.0f} m across, {len(in_window):,} properties",
        fontsize=9,
    )


def draw_area_distribution(ax, areas):
    """Plot the insured area per property across the whole run."""
    ax.hist(areas, bins=HISTOGRAM_BINS, color="#2166ac")
    ax.set_xlabel("Insured land per property (m²)", fontsize=8)
    ax.set_ylabel("Properties", fontsize=8)
    ax.set_title("How big", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(visible=True, linewidth=0.3, alpha=0.4)


def build_figure(extent, buildings, window):
    """Assemble the two panels."""
    fig = plt.figure(figsize=(11, 5.5))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.3, 1.0], wspace=0.18)

    draw_close_up(fig.add_subplot(grid[0, 0]), extent, buildings, window)
    draw_area_distribution(fig.add_subplot(grid[0, 1]), extent[AREA_COLUMN])

    handles = [
        Patch(
            facecolor=PALETTE(0), edgecolor="none", label="insured land, one property"
        ),
        Patch(facecolor="none", edgecolor=BUILDING_EDGE, label="building outline"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(bottom=0.12)
    return fig


def main(*, extent, close_up_m, use_cached_extent):
    """Draw the insured land extent this run wrote.

    Args:
        extent: The extent to draw, a name from
            landloss.io.area_of_interest.EXTENTS or "full". Must match the
            setting the generation was run with, which is why both read it from
            the same ``config.py``.
        close_up_m: How wide the close-up panel is, in metres.
        use_cached_extent: Whether to reuse the already-clipped building
            outlines for the close-up window.
    """
    in_path = insured_land_path(extent=extent)
    figure_path = FIG_DIR / f"{in_path.stem}.png"

    print(f"Reading the insured land extent from {in_path} ...", flush=True)
    insured = gpd.read_parquet(in_path)

    window = busiest_window(insured, close_up_m)
    print("Fetching the building outlines over the close-up window ...", flush=True)
    buildings = get_nz_building_outlines(
        bbox=tuple(float(value) for value in window.total_bounds),
        crs=constants.DEFAULT_CRS,
        use_cache=use_cached_extent,
    )
    # The same filter the extent was built with, so the outlines drawn on the
    # close-up are the ones that were actually buffered.
    # The footprint rule, at the step's limit. The figure reads nothing
    # from T:, so under the default "qv" rule its buildings can differ
    # from the extent's on mixed and commercial land.
    buildings = drop_non_residential_buildings(
        buildings, max_area_m2=config.MAX_DWELLING_FOOTPRINT_M2
    )

    print(f"Buffer: {INSURED_LAND_BUFFER_M:,.0f} m from every building outline")
    fig = build_figure(insured, buildings, window)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        close_up_m=config.CLOSE_UP_M,
        use_cached_extent=config.USE_CACHED_EXTENT,
    )
