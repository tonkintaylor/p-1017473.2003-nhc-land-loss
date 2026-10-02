"""Draw the urban failure polygons, their wall edges and one state's fixed geometry.

Reads the GeoParquet ``gen_urban_slope_polygons.py`` writes and produces the
figure the polygons get checked by eye against:

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s7_urban_slope_polygons/fig_urban_slope_polygons.py

It reads ``config.py`` beside it, the same file the generation reads, and asks
``gen_urban_slope_polygons.urban_slope_polygons_path`` where that run's output
went, so the figure cannot draw a different extent from the one last run.

Two panels.

- **Where.** The whole extent, with the polygons at the finest scale coloured
  by the wall on their edge (none, fill or cut) and every wall line over them.
  What this panel is for is the pattern: wall edges should follow the lines and
  the polygons should sit on the hill suburbs and leave the flat land alone.
- **Close up.** One neighbourhood at full size around the polygon with the
  longest wall edge, with the no-wall state's evacuated, inundated and imminent
  geometry drawn for every polygon in view. This is the panel that catches a
  headscarp band on the wrong side of the face or a runout pointing uphill,
  which no count would show.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/landslide/urban-slope-polygons/fig/``, which is gitignored --
the script is the record of how it was made, not the PNG.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.landslide.urban import geometry
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons import config
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons.gen_urban_slope_polygons import (
    urban_slope_polygons_path,
)
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "urban-slope-polygons" / "fig"
DPI = 200

# The state whose fixed geometry the close-up draws: every polygon carries it.
STATE = geometry.NO_WALL

# Polygons by the wall on their edge, and the three fixed geometries.
WALL_COLOURS = {None: "#bdbdbd", geometry.FILL: "#1b7837", geometry.CUT: "#762a83"}
WALL_LABELS = {
    None: "no wall line",
    geometry.FILL: "fill wall",
    geometry.CUT: "cut wall",
}
KIND_COLOURS = {
    geometry.EVACUATED: "#a50026",
    geometry.INUNDATED: "#f46d43",
    geometry.IMMINENT: "#fdae61",
}
KIND_ALPHA = {geometry.EVACUATED: 0.7, geometry.INUNDATED: 0.5, geometry.IMMINENT: 0.5}
LINE_COLOUR = "#1a1a1a"

# How wide the close-up window is, in metres: a few sections across.
CLOSE_UP_M = 120.0

RULE = "-" * 72


def close_up_window(polygons):
    """Centre the close-up on the polygon with the longest wall edge."""
    longest = polygons.loc[polygons[geometry.WALL_EDGE_LENGTH_COLUMN].idxmax()]
    point = longest.geometry.representative_point()
    half = CLOSE_UP_M / 2
    window = box(point.x - half, point.y - half, point.x + half, point.y + half)
    return gpd.GeoDataFrame(geometry=[window], crs=polygons.crs)


def draw_polygons(ax, polygons, lines, extent, *, title):
    """Draw the finest-scale polygons by wall state with the wall lines over them."""
    finest = polygons[
        polygons[geometry.SCALE_COLUMN] == polygons[geometry.SCALE_COLUMN].min()
    ]
    for position, colour in WALL_COLOURS.items():
        subset = (
            finest[finest[geometry.WALL_POSITION_COLUMN].isna()]
            if position is None
            else finest[finest[geometry.WALL_POSITION_COLUMN] == position]
        )
        if subset.empty:
            continue
        subset.plot(ax=ax, color=colour, edgecolor=colour, linewidth=0.3, alpha=0.6)
    if not lines.empty:
        lines.plot(ax=ax, color=LINE_COLOUR, linewidth=0.5)
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(title, fontsize=9)


def draw_state(ax, polygons, extent, *, title):
    """Draw one state's fixed geometries for the polygons in view."""
    for kind in (geometry.IMMINENT, geometry.INUNDATED, geometry.EVACUATED):
        column = f"{kind}_{STATE}"
        shapes = gpd.GeoSeries(polygons[column].dropna(), crs=polygons.crs)
        if shapes.empty:
            continue
        shapes.plot(
            ax=ax,
            color=KIND_COLOURS[kind],
            edgecolor=KIND_COLOURS[kind],
            linewidth=0.3,
            alpha=KIND_ALPHA[kind],
        )
    polygons.boundary.plot(ax=ax, color=LINE_COLOUR, linewidth=0.4)
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(title, fontsize=9)


def wall_lines(polygons):
    """Rebuild the wall edges to draw from the polygons' own geometry.

    The wall lines file is not read: the shared edge is what the model uses,
    and drawing the boundary of every polygon with a wall line shows it.
    """
    with_wall = polygons[polygons[geometry.WALL_LINE_ID_COLUMN].notna()]
    return gpd.GeoDataFrame(geometry=with_wall.boundary, crs=polygons.crs)


def build_figure(polygons):
    """Assemble the two panels."""
    fig, (ax_all, ax_close) = plt.subplots(1, 2, figsize=(11, 5.5))

    extent = gpd.GeoDataFrame(geometry=[box(*polygons.total_bounds)], crs=polygons.crs)
    finest_scale = int(polygons[geometry.SCALE_COLUMN].min())
    draw_polygons(
        ax_all,
        polygons,
        wall_lines(polygons),
        extent,
        title=f"Where — {len(polygons):,} polygons, {finest_scale} m scale by wall edge",
    )

    window = close_up_window(polygons)
    in_window = polygons[polygons.intersects(window.geometry.iloc[0])]
    draw_state(
        ax_close,
        in_window,
        window,
        title=f"Close up — {CLOSE_UP_M:,.0f} m across, the {STATE.replace('_', ' ')} state",
    )

    handles = [
        Patch(facecolor=colour, edgecolor="none", label=WALL_LABELS[position])
        for position, colour in WALL_COLOURS.items()
    ]
    handles.append(
        Line2D([0], [0], color=LINE_COLOUR, linewidth=0.8, label="wall edge")
    )
    handles.extend(
        Patch(facecolor=KIND_COLOURS[kind], edgecolor="none", label=kind)
        for kind in geometry.GEOMETRY_KINDS
    )
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(bottom=0.1)
    return fig


def main(*, pilot):
    """Draw the polygons the generation wrote for this extent.

    Args:
        pilot: Whether to draw the pilot box run rather than the full study
            area one. Must match the setting the generation was run with,
            which is why both read it from the same ``config.py``.
    """
    polygons_path = urban_slope_polygons_path(pilot=pilot)
    figure_path = FIG_DIR / f"{polygons_path.stem}.png"

    print(f"Reading the polygons from {polygons_path} ...")
    polygons = gpd.read_parquet(polygons_path)
    print(RULE)
    print(f"{len(polygons):,} polygons")

    fig = build_figure(polygons)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)

    print(RULE)
    print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(pilot=config.PILOT)
