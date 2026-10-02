"""Draw one realisation of large landslides: where they are, how big, and how far they ran.

Reads the GeoParquet ``s1_simulate_landslides.py`` writes and produces the figure
that realisation gets checked by eye against:

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s1_landslide_realisation/fig_landslide_realisation.py

It reads ``config.py`` beside it, the same file the simulation reads, and asks
``s1_simulate_landslides.realisation_path`` where that run's output went -- so
the figure cannot end up drawing a different extent from the one last run. The
slope units the failures were placed in come from ``input_paths`` the same way.

Four panels, each answering a question the numbers in the run output cannot.

- **Where.** The whole extent, with every landslide on it over the slope unit
  outlines. What this panel is for is the pattern: landslides should sit on
  the hill country and leave the flat land alone, several should share a
  unit where the grid is high, and none should form the neat rectangles or
  edges that give away a grid artefact.
- **Close up.** One neighbourhood at full size, showing the source ellipse, the
  polygon the material ends up in, the seed cell at the ellipse's crest, and an
  arrow between the two centres. This is the panel that catches a downhill
  direction pointing uphill, or an ellipse elongated across the slope rather
  than down it, which no summary statistic would show.
- **How big.** The source areas, as the complementary cumulative distribution on
  log axes -- the standard way a landslide inventory is plotted, so the sampled
  sizes can be put beside a published one. A bounded power law is a straight
  line on these axes until it turns down at the upper bound; the lower bound
  is the top of the urban range, drawn as a line.
- **How far.** Displacement against slope, which is a plot of the assumption
  rather than of the result: it should show the straight ramp the model applies
  and nothing else. It is here so that the assumption is visible in the same
  figure as the landslides it produced.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/landslide-realisation/fig/``, which is gitignored --
the script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.colors import LAND_CLASS_COLOURS
from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide.land_class import (
    EVACUATED,
    INUNDATED,
    LAND_CLASS_COLUMN,
)
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation import config
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation.s1_simulate_landslides import (
    input_paths,
    realisation_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "landslide-realisation" / "fig"
DPI = 200

# Red for the ground that leaves, orange for the ground it lands on. The two
# have to be told apart at a glance, because the whole point of keeping them
# separate is that they are settled differently. Taken from
# landloss.common.utils.colors rather than set here, so that this figure and a
# QGIS project of the same realisation carry the same legend.
COLOURS = {land_class: colour for land_class, (colour, _) in LAND_CLASS_COLOURS.items()}

# The slope unit outlines, drawn under the landslides: grey and thin, so they
# place a failure without competing with it.
UNIT_EDGE = "#555555"
UNIT_LINEWIDTH = 0.3

# Inundated land first, so the source is drawn over the top of it. Where the
# displacement is short next to the landslide the two very nearly coincide, and
# drawn the other way round the source disappears under its own runout -- which
# would read as a model that had lost half its output.
DRAW_ORDER = (INUNDATED, EVACUATED)
FILL_ALPHA = {INUNDATED: 0.55, EVACUATED: 0.95}

# How wide the close-up window is, in metres. Wide enough to hold several
# large failures and the ground between them.
CLOSE_UP_M = 600.0

RULE = "-" * 72


def close_up_window(sources):
    """Choose the neighbourhood to show at full size.

    Centred on the largest landslide in the realisation, because that is the one
    whose source and runout polygons are big enough to read, and because if the
    direction is wrong anywhere it is wrong there too.

    Args:
        sources: The evacuated polygons, carrying ``source_area_m2``.

    Returns:
        The window as a one row GeoDataFrame, ready to pass to the map styling.
    """
    largest = sources.loc[sources["source_area_m2"].idxmax()]
    easting = float(largest["easting"])
    northing = float(largest["northing"])
    half = CLOSE_UP_M / 2

    window = box(easting - half, northing - half, easting + half, northing + half)
    return gpd.GeoDataFrame(geometry=[window], crs=sources.crs)


def draw_map(ax, polygons, units, extent, *, title):
    """Draw the slope unit outlines and the two polygon sets over a basemap."""
    if not units.empty:
        units.boundary.plot(ax=ax, color=UNIT_EDGE, linewidth=UNIT_LINEWIDTH)
    for land_class in DRAW_ORDER:
        subset = polygons[polygons[LAND_CLASS_COLUMN] == land_class]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            color=COLOURS[land_class],
            edgecolor=COLOURS[land_class],
            linewidth=0.4,
            alpha=FILL_ALPHA[land_class],
        )

    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(title, fontsize=9)


def draw_runout_arrows(ax, sources):
    """Draw each landslide's seed, and an arrow from its source centre to its runout."""
    ax.scatter(
        sources["seed_easting"],
        sources["seed_northing"],
        s=6,
        color="#1a1a1a",
        marker="^",
        linewidths=0,
        zorder=5,
    )
    for _, row in sources.iterrows():
        ax.annotate(
            "",
            xy=(row["runout_easting"], row["runout_northing"]),
            xytext=(row["easting"], row["northing"]),
            arrowprops={
                "arrowstyle": "->",
                "color": "#1a1a1a",
                "linewidth": 0.7,
                "shrinkA": 0,
                "shrinkB": 0,
            },
        )


def draw_size_distribution(ax, areas, *, min_area_m2):
    """Plot the source areas as a complementary cumulative distribution."""
    ordered = np.sort(np.asarray(areas, dtype=float))
    exceedance = 1.0 - np.arange(ordered.size) / ordered.size

    ax.step(ordered, exceedance, where="post", color="#2166ac", linewidth=1.2)
    ax.axvline(min_area_m2, color="#888888", linewidth=0.8, linestyle="--")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Source area (m²)", fontsize=8)
    ax.set_ylabel("Proportion at least this large", fontsize=8)
    ax.set_title(f"How big — above the urban range ({min_area_m2:,.0f} m²)", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(visible=True, which="both", linewidth=0.3, alpha=0.4)


def draw_displacement(ax, slope, displacement):
    """Plot how far material travelled against the slope it travelled down."""
    ax.scatter(slope, displacement, s=4, color="#2166ac", alpha=0.35, linewidths=0)
    ax.set_xlabel("Slope (degrees)", fontsize=8)
    ax.set_ylabel("Displacement (m)", fontsize=8)
    ax.set_title("How far", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(visible=True, linewidth=0.3, alpha=0.4)


def build_figure(polygons, units, *, min_area_m2):
    """Assemble the four panels."""
    sources = polygons[polygons[LAND_CLASS_COLUMN] == EVACUATED]

    fig = plt.figure(figsize=(11, 7.5))
    grid = fig.add_gridspec(2, 2, height_ratios=[1.6, 1.0], hspace=0.22, wspace=0.16)

    extent = gpd.GeoDataFrame(geometry=[box(*units.total_bounds)], crs=units.crs)
    ax_all = fig.add_subplot(grid[0, 0])
    draw_map(
        ax_all, polygons, units, extent, title=f"Where — {len(sources):,} landslides"
    )

    window = close_up_window(sources)
    ax_close = fig.add_subplot(grid[0, 1])
    frame = window.geometry.iloc[0]
    draw_map(
        ax_close,
        polygons[polygons.intersects(frame)],
        units[units.intersects(frame)],
        window,
        title=f"Close up — {CLOSE_UP_M:,.0f} m across, around the largest failure",
    )
    draw_runout_arrows(ax_close, sources[sources.intersects(frame)])

    ax_size = fig.add_subplot(grid[1, 0])
    draw_size_distribution(ax_size, sources["source_area_m2"], min_area_m2=min_area_m2)

    ax_far = fig.add_subplot(grid[1, 1])
    draw_displacement(ax_far, sources["slope_degrees"], sources["displacement_m"])

    handles = [
        Patch(facecolor=COLOURS[EVACUATED], edgecolor="none", label=EVACUATED),
        Patch(facecolor=COLOURS[INUNDATED], edgecolor="none", label=INUNDATED),
        Line2D([0], [0], color=UNIT_EDGE, linewidth=0.8, label="slope unit"),
        Line2D(
            [0],
            [0],
            color="#1a1a1a",
            marker="^",
            linestyle="none",
            markersize=4,
            label="seed cell",
        ),
        Line2D([0], [0], color="#1a1a1a", linewidth=0.8, label="downhill runout"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=5,
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(bottom=0.08)
    return fig


def main(*, extent, realisation_id, large_min_source_area_m2):
    """Draw the realisation the simulation wrote for this extent.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full". Must match the
            setting the simulation was run with, which is why both read it
            from the same ``config.py``.
        realisation_id: Which modelled earthquake to draw.
        large_min_source_area_m2: The lower bound of the size law the run
            used, drawn on the size panel.
    """
    realisation = realisation_path(extent=extent, realisation_id=realisation_id)
    figure_path = FIG_DIR / f"{realisation.stem}.png"

    print(f"Reading the realisation from {realisation} ...")
    polygons = gpd.read_parquet(realisation)
    units = gpd.read_parquet(input_paths(extent=extent)["units"])

    print(RULE)
    for land_class in (EVACUATED, INUNDATED):
        count = int((polygons[LAND_CLASS_COLUMN] == land_class).sum())
        print(f"{land_class}: {count:,} polygons")

    fig = build_figure(polygons, units, min_area_m2=large_min_source_area_m2)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_id=config.REALISATION_IDS[0],
        large_min_source_area_m2=config.LARGE_MIN_SOURCE_AREA_M2,
    )
