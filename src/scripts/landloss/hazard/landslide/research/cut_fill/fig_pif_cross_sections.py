"""Cross-sections down the hill, showing each pif's cut or fill class.

Draws the sections in ``config.SECTIONS``, each ``config.SECTION_LENGTH_M``
long, uphill on the left. Each section draws the 1 m DEM, the two natural
surfaces ``gen_pif_cut_fill.py`` compares each pif against (the rolling mean,
and each pif's own quadratic over the stretch of the section its points
cover), every pip within ``config.SECTION_PIP_BUFFER_M`` of the line coloured
by its pif's class, the foot of the face below each of those pips, and the
buildings, GNS mapped walls and cut/fill lines it crosses. Each pif is
labelled with its id and its class by both methods. A plan beside them shows
the sections over the hillshade, the pips coloured the same way.

The sections are drawn at true scale (no vertical exaggeration), so a terrace's
platform and batter read at the angles they are.

Run from the repository root, after ``gen_pif_cut_fill.py``::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/cut_fill/fig_pif_cross_sections.py

Settings are in ``config.py``. The figure goes under
``research/hazard/landslide/pif_cut_fill/fig/``.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import math

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy import ndimage

from landloss.io.readers import get_gns_slide_morphology, get_nz_building_outlines
from scripts.landloss.hazard.landslide.research.cut_fill import config
from scripts.landloss.hazard.landslide.research.cut_fill.gen_pif_cut_fill import (
    CUT,
    CUT_AND_FILL,
    FILL,
    NATURAL,
    eval_quadratic,
    pif_table_path,
    pip_table_path,
    rolling_mean_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    CUT_FILL_LINE_TYPE,
    MAPPED_WALL_TYPE,
)
from scripts.landloss.paths import RESEARCH_DIR

FIG_DIR = RESEARCH_DIR / "hazard" / "landslide" / "pif_cut_fill" / "fig"
DPI = 200

# The DEM profile is read every this many metres along a section.
STEP_M = 0.25

# The plan's margin around the sections, in metres.
PLAN_MARGIN_M = 10.0

# A pif's quadratic is drawn this far beyond its points along the section.
POLY_REACH_M = 5.0

CLASS_COLOURS = {
    CUT: "#2a78d6",
    FILL: "#eb6834",
    CUT_AND_FILL: "#1baf7a",
    NATURAL: "#9e9e9e",
}
CLASS_LABELS = {
    CUT: "cut",
    FILL: "fill",
    CUT_AND_FILL: "cut and fill",
    NATURAL: "natural",
}
CLASS_SHORT = {CUT: "C", FILL: "F", CUT_AND_FILL: "CF", NATURAL: "N"}
GROUND_COLOUR = "#1a1a1a"
ROLLING_COLOUR = "#7b2d8e"
POLY_COLOUR = "#5f5f5f"
GNS_WALL_COLOUR = "#7b2d8e"
CUT_FILL_COLOUR = "#eda100"
BUILDING_COLOUR = "#9e9e9e"


def read_raster(path):
    """A raster as ``(values, transform, bounds)``, no data as NaN."""
    with rasterio.open(path) as src:
        values = src.read(1, masked=True).filled(np.nan).astype("float64")
        return values, src.transform, tuple(src.bounds)


def sample(values, transform, x, y):
    """A raster at points, interpolated bilinearly between cell centres."""
    col, row = ~transform * (np.asarray(x), np.asarray(y))
    return ndimage.map_coordinates(
        values, [row - 0.5, col - 0.5], order=1, mode="nearest", cval=np.nan
    )


def build_sections(specs, *, length_m):
    """The section lines, each running downhill along its bearing through its centre."""
    sections = []
    for spec in specs:
        bearing = math.radians(spec["bearing_deg"])
        east, north = math.sin(bearing), math.cos(bearing)
        half = length_m / 2
        start = (spec["x"] - east * half, spec["y"] - north * half)
        end = (spec["x"] + east * half, spec["y"] + north * half)
        sections.append(
            {"line": shapely.LineString([start, end]), "bearing": spec["bearing_deg"]}
        )
    return sections


def chainage_of(line, geometries):
    """The distance along a line of each point where it meets some geometries."""
    out = []
    for geom in geometries:
        crossing = line.intersection(geom)
        if not crossing.is_empty:
            out.extend(line.project(point) for point in _points_of(crossing))
    return np.asarray(out)


def _points_of(geom):
    """The points of an intersection: the vertices of a point, line or collection."""
    if isinstance(geom, shapely.Point):
        return [geom]
    if hasattr(geom, "geoms"):
        return [p for part in geom.geoms for p in _points_of(part)]
    return [shapely.Point(c) for c in geom.coords]


def building_spans(line, buildings):
    """The (start, end) chainage of each building the line passes through."""
    spans = []
    for geom in buildings.geometry:
        crossing = line.intersection(geom)
        for part in getattr(crossing, "geoms", [crossing]):
            if isinstance(part, shapely.LineString) and not part.is_empty:
                a = line.project(shapely.Point(part.coords[0]))
                b = line.project(shapely.Point(part.coords[-1]))
                spans.append((min(a, b), max(a, b)))
    return spans


def draw_plan(ax, dem, sections, pips, walls, cut_fill, buildings):
    """The sections over the hillshade, with the pips by class, walls and buildings."""
    elevation, transform, _ = dem
    lines = shapely.MultiLineString([s["line"] for s in sections])
    minx, miny, maxx, maxy = lines.buffer(PLAN_MARGIN_M).bounds
    # Widen the view to the panel's own shape, so it shows more of the hill
    # rather than leaving the panel blank above and below.
    box = ax.get_position()
    fig_w, fig_h = ax.figure.get_size_inches()
    panel_ratio = (box.height * fig_h) / (box.width * fig_w)
    centre_x, centre_y = (minx + maxx) / 2, (miny + maxy) / 2
    half_w = max(maxx - minx, (maxy - miny) / panel_ratio) / 2
    half_h = half_w * panel_ratio
    minx, maxx = centre_x - half_w, centre_x + half_w
    miny, maxy = centre_y - half_h, centre_y + half_h
    c0, r1 = ~transform * (minx, miny)
    c1, r0 = ~transform * (maxx, maxy)
    r0, r1, c0, c1 = int(r0), math.ceil(r1), int(c0), math.ceil(c1)
    window = elevation[r0:r1, c0:c1]
    x0, y0 = transform * (c0, r0)
    x1, y1 = transform * (c1, r1)
    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(window, nan=np.nanmin(window)), vert_exag=1, dx=1, dy=1
    )
    ax.imshow(shade, cmap="gray", extent=(x0, x1, y1, y0), origin="upper")
    ax.contour(
        np.linspace(x0, x1, window.shape[1]),
        np.linspace(y0, y1, window.shape[0]),
        window,
        levels=np.arange(np.floor(np.nanmin(window)), np.nanmax(window), 2.0),
        colors="#ffffff",
        linewidths=0.3,
        alpha=0.6,
    )
    view = shapely.box(minx, miny, maxx, maxy)
    buildings[buildings.intersects(view)].plot(
        ax=ax, facecolor="none", edgecolor=BUILDING_COLOUR, linewidth=0.8
    )
    walls[walls.intersects(view)].plot(ax=ax, color=GNS_WALL_COLOUR, linewidth=1.5)
    cut_fill[cut_fill.intersects(view)].plot(
        ax=ax, color=CUT_FILL_COLOUR, linewidth=1.5
    )
    in_view = pips[
        pips.x.between(minx, maxx) & pips.y.between(miny, maxy)
    ]
    for cls, colour in CLASS_COLOURS.items():
        these = in_view[in_view["class"] == cls]
        ax.scatter(these.x, these.y, s=2, color=colour, linewidths=0)
    for number, section in enumerate(sections, start=1):
        xs, ys = section["line"].xy
        ax.plot(xs, ys, color="#ffffff", linewidth=2.5)
        ax.plot(xs, ys, color=GROUND_COLOUR, linewidth=1.0)
        ax.annotate(
            "",
            xy=(xs[1], ys[1]),
            xytext=(xs[0] + 0.9 * (xs[1] - xs[0]), ys[0] + 0.9 * (ys[1] - ys[0])),
            arrowprops={"arrowstyle": "-|>", "color": GROUND_COLOUR, "lw": 1.0},
        )
        ax.text(
            xs[1],
            ys[1],
            f" {number}",
            fontsize=9,
            fontweight="bold",
            color=GROUND_COLOUR,
            bbox={"facecolor": "#ffffff", "edgecolor": "none", "pad": 1},
        )
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(
        "Plan: sections numbered at their downhill end, 2 m contours", fontsize=10
    )


def draw_section(ax, number, section, dem, rolling, pips, classes, layers, *, buffer_m, length_m):
    """One section: the ground, both natural surfaces, the pips by class and their feet."""
    walls, cut_fill, buildings = layers
    line = section["line"]
    chain = np.arange(0.0, line.length + STEP_M / 2, STEP_M)
    points = [line.interpolate(d) for d in chain]
    xs, ys = np.array([p.x for p in points]), np.array([p.y for p in points])
    ground = sample(dem[0], dem[1], xs, ys)
    ax.plot(chain, ground, color=GROUND_COLOUR, linewidth=1.2, zorder=3)
    ax.plot(
        chain,
        sample(rolling[0], rolling[1], xs, ys),
        color=ROLLING_COLOUR,
        linewidth=1.0,
        linestyle="--",
        zorder=3,
    )

    for start, end in building_spans(line, buildings):
        on = (chain >= start) & (chain <= end)
        ax.plot(
            chain[on],
            ground[on],
            color=BUILDING_COLOUR,
            linewidth=5,
            alpha=0.6,
            zorder=2,
            solid_capstyle="butt",
        )
    for geoms, colour in ((walls.geometry, GNS_WALL_COLOUR), (cut_fill.geometry, CUT_FILL_COLOUR)):
        for d in chainage_of(line, geoms):
            z = np.interp(d, chain, ground)
            ax.plot([d, d], [z - 1.5, z + 1.5], color=colour, linewidth=2, zorder=4)

    near = pips[shapely.distance(shapely.points(pips.x, pips.y), line) <= buffer_m].copy()
    near["d"] = line.project(shapely.points(near.x, near.y))
    near["foot_d"] = line.project(shapely.points(near.foot_x, near.foot_y))

    for pif, group in near.groupby("pif_id"):
        fit = classes.loc[pif]
        if np.isnan(fit["poly_a"]):
            continue
        reach = (chain >= min(group.d.min(), group.foot_d.min()) - POLY_REACH_M) & (
            chain <= max(group.d.max(), group.foot_d.max()) + POLY_REACH_M
        )
        coefficients = fit[["poly_a", "poly_b", "poly_c", "poly_d", "poly_e", "poly_f"]]
        centre = (fit["poly_centre_x"], fit["poly_centre_y"])
        surface = eval_quadratic(
            coefficients.to_numpy(float), centre, config.FIT_RADIUS_M, xs[reach], ys[reach]
        )
        ax.plot(chain[reach], surface, color=POLY_COLOUR, linewidth=0.9, linestyle=":", zorder=3)

    for cls, colour in CLASS_COLOURS.items():
        these = near[near["class"] == cls]
        ax.scatter(these.d, these.z, s=18, color=colour, edgecolor="#ffffff", linewidth=0.5, zorder=5)
        ax.scatter(these.foot_d, these.foot_z, s=14, marker="v", facecolor="none", edgecolor=colour, linewidth=0.8, zorder=5)

    method = config.FIGURE_CLASS_METHOD
    other = "poly" if method == "rolling" else "rolling"
    for pif, group in near.groupby("pif_id"):
        row = classes.loc[pif]
        label = (
            f"{pif} {CLASS_SHORT[row[f'class_{method}']]}/{CLASS_SHORT[row[f'class_{other}']]}"
        )
        top = group.loc[group.z.idxmax()]
        ax.annotate(
            label,
            (top.d, top.z),
            xytext=(2, 5),
            textcoords="offset points",
            fontsize=6.5,
            fontweight="bold" if pif == config.SECTION_PIF_ID else "normal",
            color="#424242",
            zorder=6,
        )

    ax.set_aspect("equal")
    ax.set_xlim(0, length_m)
    ax.set_ylim(np.nanmin(ground) - 2, np.nanmax(ground) + 4)
    ax.grid(color="#e0e0e0", linewidth=0.5)
    ax.tick_params(labelsize=7)
    ax.set_ylabel("Elevation (m)", fontsize=8)
    ax.set_title(
        f"Section {number}: bearing {section['bearing']:.0f}\N{DEGREE SIGN}, uphill on the left",
        fontsize=9,
        loc="left",
    )


def main(*, extent, use_cached_layers, specs, length_m, buffer_m, method):
    """Draw the sections and write the figure.

    Args:
        extent: The extent ``gen_pif_cut_fill.py`` was run over.
        use_cached_layers: Whether to reuse the cached LINZ and GNS layers.
        specs: Each section's centre and bearing.
        length_m: The length of each section, in metres.
        buffer_m: A pip within this many metres of a section is drawn on it.
        method: The method whose class colours the pips.
    """
    classes = pd.read_parquet(pif_table_path(extent=extent))
    pips = pd.read_parquet(pip_table_path(extent=extent))
    pips["class"] = pips["pif_id"].map(classes[f"class_{method}"])
    dem = read_raster(dem_path(1, extent=extent))
    rolling = read_raster(rolling_mean_path(extent=extent))

    # The same bbox landslide step 12 read the layers with, so the cache is reused.
    bbox = dem[2]
    morphology = get_gns_slide_morphology(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    walls = morphology[morphology["Type"] == MAPPED_WALL_TYPE]
    cut_fill = morphology[morphology["Type"] == CUT_FILL_LINE_TYPE]
    buildings = get_nz_building_outlines(bbox=bbox, crs=CRS, use_cache=use_cached_layers)

    sections = build_sections(specs, length_m=length_m)
    fig = plt.figure(figsize=(16, 3.2 * len(sections) + 1))
    grid = fig.add_gridspec(len(sections), 2, width_ratios=(1, 1.9), wspace=0.08, hspace=0.35)
    draw_plan(fig.add_subplot(grid[:, 0]), dem, sections, pips, walls, cut_fill, buildings)
    axes = []
    for number, section in enumerate(sections, start=1):
        ax = fig.add_subplot(grid[number - 1, 1])
        draw_section(
            ax,
            number,
            section,
            dem,
            rolling,
            pips,
            classes,
            (walls, cut_fill, buildings),
            buffer_m=buffer_m,
            length_m=length_m,
        )
        axes.append(ax)
    axes[-1].set_xlabel("Distance along section (m)", fontsize=8)

    handles = [
        Line2D([], [], color=GROUND_COLOUR, linewidth=1.2, label="1 m DEM"),
        Line2D([], [], color=ROLLING_COLOUR, linewidth=1.0, linestyle="--", label=f"rolling mean, {config.ROLLING_WINDOW_M:g} m"),
        Line2D([], [], color=POLY_COLOUR, linewidth=0.9, linestyle=":", label="pif's quadratic"),
        *[
            Line2D([], [], marker="o", linestyle="", color=colour, label=f"pip: {CLASS_LABELS[cls]}")
            for cls, colour in CLASS_COLOURS.items()
        ],
        Line2D([], [], marker="v", linestyle="", markerfacecolor="none", color=GROUND_COLOUR, label="foot of face below the pip"),
        Line2D([], [], color=GNS_WALL_COLOUR, linewidth=2, label="GNS mapped wall"),
        Line2D([], [], color=CUT_FILL_COLOUR, linewidth=2, label="GNS cut/fill line"),
        Patch(color=BUILDING_COLOUR, alpha=0.6, label="LINZ building"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=6, fontsize=8, frameon=False)
    other = "poly" if method == "rolling" else "rolling"
    fig.suptitle(
        f"Cut and fill at the pifs around pif {config.SECTION_PIF_ID}: pips coloured by "
        f"the {method} class; labels are pif id, {method} / {other} class "
        "(C cut, F fill, CF cut and fill, N natural); true scale",
        fontsize=10,
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"pif-{config.SECTION_PIF_ID}-cross-sections.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    print(f"Written to {path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        specs=config.SECTIONS,
        length_m=config.SECTION_LENGTH_M,
        buffer_m=config.SECTION_PIP_BUFFER_M,
        method=config.FIGURE_CLASS_METHOD,
    )
