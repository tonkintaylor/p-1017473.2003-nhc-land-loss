"""Stage D2 (deprecated): slope elements from free-face and bank seeds, on the pilot.

Deprecated 2026-10-04: superseded by ``fig_pilot_example_instability_zones.py``
(pips, pifs and sizs). Kept for the old-versus-new comparison; the new script
imports its input helpers from here.

Stage D1 (``fig_toy_slope_elements.py``) proved the library on terrain whose
answer is known. This runs it once over the whole pilot DEM and draws the sites
listed in ``config.PILOT_SITES`` for the lead to judge: the sort of ground it
was built for, and the sort it was not.

For each site it draws, on a hillshade of the real DEM,

- the elements the library found (crest and toe cells, free-face or bank) with
  the GNS mapped retaining walls, the GNS breaks in slope and the SLIDE cut and
  fill outlines over them, to see whether the elements land where the mapping
  says the ground changes;
- the failure polygons the elements make, zone by zone;
- a section down the fall line of the site's tallest element, with the
  polygon's evacuated, imminent and inundated reach.

It also checks, over the whole pilot, how far the elements and the GNS mapping
agree (the plan's detection check in miniature, phase 4 does it properly) and
writes an overview map of where the sites sit.

The GNS mapped wall has no height attribute, so a wall "of known height" here
is a wall under a free-face whose height the DEM gives. Phase 2 has not decided
which free-faces carry a wall, so the polygons are drawn with every free-face
taking a wall's wedge, as in D1. The ground map's fill share is still the one
from before the ground step 2 fill changes, so most elements here are treated as fill
(see ``pilot_example_slope_elements.md``).

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_slope_elements.py

Writes one PNG per site and an overview map to
``report/hazard/landslide/slope-elements/fig/``. Needs the 1 m pilot DEM
(ground step 1) and the pilot ground map (ground step 2) in the cache, and the GNS
layers through the Koordinates readers.
"""

import sys
import textwrap
import time
from contextlib import contextmanager
from dataclasses import dataclass

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray
from affine import Affine
from matplotlib.colors import LightSource, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.patheffects import withStroke
from rasterio import features
from scipy import ndimage

from landloss.exposure.rw.lines import CUT_FILL_LINE_TYPE, MAPPED_WALL_TYPE
import landloss.hazard.landslide.slope_elements as slope_elements
from landloss.hazard.landslide.slope_elements import (
    BANK,
    BETA_GROW_ANGLE_DEG,
    CREST,
    FREE_FACE,
    TOE,
    SlopeElements,
    _bank_pass,
    _free_face_pass,
    find_slope_elements,
    rasterise_ground_map,
)
from landloss.hazard.landslide.slope_polygons import (
    EVACUATED,
    IMMINENT,
    INUNDATED,
    SlopePolygons,
    build_slope_polygons,
    polygon_geometries,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_nz_coastline_polygons,
    get_slide_genesis,
)
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "slope-elements" / "fig"

# The colours are the toy script's, so a D1 and a D2 figure read alike.
INUNDATED_COLOUR = "#2a78d6"
FREE_FACE_COLOUR = "#eb6834"
BANK_COLOUR = "#1baf7a"
IMMINENT_COLOUR = "#eda100"
INK = "#0b0b0b"
MUTED = "#898781"
TYPE_COLOUR = {FREE_FACE: FREE_FACE_COLOUR, BANK: BANK_COLOUR}
ZONE_COLOUR = {
    EVACUATED: None,  # the polygon's element type
    IMMINENT: IMMINENT_COLOUR,
    INUNDATED: INUNDATED_COLOUR,
}
CUT_COLOUR = "#8c564b"
FILL_COLOUR = "#9467bd"
BREAK_COLOUR = "#7a7a7a"
SHARP_BREAK_COLOUR = "#d62ba3"

# Muted, so the element markers and the GNS lines stay legible over them.
MATERIAL_COLOUR = {
    "rock": "#b8b0a2",
    "weak_rock": "#b8b0a2",
    "stronger_rock": "#7f786a",
    "colluvium": "#dcc690",
    "fill_uncontrolled": "#d9a3a8",
    "alluvium": "#a3bfd1",
    "loess": "#ece29b",
    "unknown": "#e4e4e4",
}

FILL_MODIFICATION = "fill"
SHARP = "sharp"
BREAK_TYPES = ("Concave break in slope", "Convex break in slope")
CUT_SLOPE_TYPE = "Cut slope"
FILL_BODY_TYPE = "Fill body"
CRS = 2193

# The wall candidates of panel 3, by the evidence the GNS layers give.
WALL_EVIDENCE_COLOUR = {
    "gns": "#b3261e",
    "break": FREE_FACE_COLOUR,
    "none": "#f6c4ae",
}
SEED_DROPPED_COLOUR = "#4d4d4d"
BANK_GREY = "#9a9a9a"
SEED_DOT_SIZE = 2.5
# Heights under this are not labelled in panel 3, to keep the labels readable.
LABEL_MIN_HEIGHT_M = 1.5


@contextmanager
def bank_slope_override(bank_slope_deg):
    """Temporarily set the bank seed slope for a one-off pilot run."""
    if bank_slope_deg is None:
        yield
        return
    original = slope_elements.BANK_SEED_SLOPE_DEG
    slope_elements.BANK_SEED_SLOPE_DEG = {
        group: float(bank_slope_deg) for group in slope_elements.GROUND_GROUPS
    }
    try:
        yield
    finally:
        slope_elements.BANK_SEED_SLOPE_DEG = original


@dataclass(frozen=True)
class Pilot:
    """One library run over the whole pilot, with the layers it is judged on."""

    dem: np.ndarray
    water: np.ndarray
    transform: object
    seed_free_face: np.ndarray
    seed_bank: np.ndarray
    found: SlopeElements
    result: SlopePolygons
    ground_map: gpd.GeoDataFrame
    walls: gpd.GeoDataFrame
    breaks: gpd.GeoDataFrame
    cut_fill_lines: gpd.GeoDataFrame
    genesis: gpd.GeoDataFrame
    is_fill: pd.Series
    seconds: float


def get_pilot_inputs(*, extent, fill_as_soil=False):
    """The DEM, water mask, ground groups and ground map of the pilot.

    Returns ``(dem, dem_run, water, transform, bbox, ground_map, group,
    position)``; ``dem_run`` is the DEM with the sea set to NaN.
    """
    dem_da = rioxarray.open_rasterio(dem_path(1, extent=extent), masked=True).squeeze(
        "band", drop=True
    )
    dem = dem_da.to_numpy().astype("float64")
    transform = dem_da.rio.transform()
    bbox = dem_da.rio.bounds()
    land = get_nz_coastline_polygons(bbox=bbox, crs=CRS, use_cache=True)
    on_land = features.rasterize(
        [(geometry, 1) for geometry in land.geometry],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    water = ~on_land
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    group, position = rasterise_ground_map(
        ground_map, transform, dem.shape, fill_as_soil=fill_as_soil
    )
    return (
        dem,
        np.where(water, np.nan, dem),
        water,
        transform,
        bbox,
        ground_map,
        group,
        position,
    )


def get_pilot_run(*, extent, bank_slope_deg=None):
    """Run the elements and the polygons once over the whole pilot DEM."""
    dem, dem_run, water, transform, bbox, ground_map, group, position = (
        get_pilot_inputs(extent=extent)
    )
    with bank_slope_override(bank_slope_deg):
        start = time.perf_counter()
        found = find_slope_elements(
            dem_run, group, transform, categories={"ground_row": position}
        )
        # The library does not keep the seeds, so the two passes are rerun for them.
        free_face_grown, free_face_seeds, _ = _free_face_pass(
            dem_run, group, found.layers, 1.0
        )
        _, bank_seeds = _bank_pass(free_face_grown > 0, dem_run, found.layers, group)
        rows = found.elements["majority_ground_row"].to_numpy()
        on_map = rows >= 0
        modification = np.where(
            on_map, ground_map["modification"].to_numpy()[np.maximum(rows, 0)], ""
        )
        is_fill = pd.Series(
            modification == FILL_MODIFICATION, index=found.elements.index
        )
        thickness = pd.Series(
            np.where(
                is_fill,
                ground_map["fill_thickness_m"].to_numpy()[np.maximum(rows, 0)],
                np.nan,
            ),
            index=found.elements.index,
        )
        result = build_slope_polygons(
            found, dem_run, transform, is_fill=is_fill, fill_thickness_m=thickness
        )
        seconds = time.perf_counter() - start
    morphology = get_gns_slide_morphology(bbox=bbox, crs=CRS, use_cache=True)
    genesis = get_slide_genesis(bbox=bbox, crs=CRS, use_cache=True)
    return Pilot(
        dem=dem,
        water=water,
        transform=transform,
        seed_free_face=free_face_seeds > 0,
        seed_bank=bank_seeds > 0,
        found=found,
        result=result,
        ground_map=ground_map,
        walls=morphology[morphology["Type"] == MAPPED_WALL_TYPE],
        breaks=morphology[morphology["Type"].isin(BREAK_TYPES)],
        cut_fill_lines=morphology[morphology["Type"] == CUT_FILL_LINE_TYPE],
        genesis=genesis,
        is_fill=is_fill,
        seconds=seconds,
    )


def burn(geometries, pilot, *, all_touched=True):
    """The cells the geometries cross, as a boolean grid on the pilot's grid."""
    shapes = [(geometry, 1) for geometry in geometries if not geometry.is_empty]
    if not shapes:
        return np.zeros(pilot.dem.shape, dtype=bool)
    return features.rasterize(
        shapes,
        out_shape=pilot.dem.shape,
        transform=pilot.transform,
        fill=0,
        dtype="uint8",
        all_touched=all_touched,
    ).astype(bool)


def distance_to(mask):
    """Each cell's distance, in metres on a 1 m grid, to the nearest True cell."""
    return ndimage.distance_transform_edt(~mask)


def window_slices(pilot, x, y, half_size_m):
    """The (rows, columns) slices of the DEM a site's window covers, and its bounds."""
    n_rows, n_cols = pilot.dem.shape
    col0 = max(int(np.floor(x - half_size_m - pilot.transform.c)), 0)
    col1 = min(int(np.ceil(x + half_size_m - pilot.transform.c)), n_cols)
    row0 = max(int(np.floor(pilot.transform.f - (y + half_size_m))), 0)
    row1 = min(int(np.ceil(pilot.transform.f - (y - half_size_m))), n_rows)
    bounds = (
        pilot.transform.c + col0,
        pilot.transform.c + col1,
        pilot.transform.f - row1,
        pilot.transform.f - row0,
    )
    return slice(row0, row1), slice(col0, col1), bounds


def hillshade(dem):
    return LightSource(azdeg=315, altdeg=40).hillshade(dem, vert_exag=1.5, dx=1, dy=1)


def contour_interval(window, intervals, max_contours):
    relief = float(np.nanmax(window) - np.nanmin(window))
    for interval in intervals:
        if relief / interval <= max_contours:
            return interval
    return intervals[-1]


def material_image(pilot, rows, cols, bounds):
    """The ground map's material over the window, shaded by the hillshade.

    Returns the RGB image and the materials that appear in the window.
    """
    height, width = pilot.dem[rows, cols].shape
    names = list(MATERIAL_COLOUR)
    near = clipped(pilot.ground_map, bounds)
    codes = near["material"].map(names.index).to_numpy()
    window_transform = Affine(1.0, 0.0, bounds[0], 0.0, -1.0, bounds[3])
    burned = features.rasterize(
        zip(near.geometry, codes.tolist(), strict=True),
        out_shape=(height, width),
        transform=window_transform,
        fill=-1,
        dtype="int16",
    )
    palette = np.array(
        [mpl.colors.to_rgb(MATERIAL_COLOUR[n]) for n in names] + [(1.0, 1.0, 1.0)]
    )
    rgb = palette[np.where(burned >= 0, burned, len(names))]
    shade = hillshade(pilot.dem[rows, cols])[..., None]
    present = [names[c] for c in np.unique(burned[burned >= 0])]
    return np.clip(rgb * (0.45 + 0.7 * shade), 0, 1), present


def draw_base(
    ax, pilot, rows, cols, bounds, *, intervals, max_contours, by_material=False
):
    """Hillshade (or material) and contours of the window, in map coordinates."""
    window = pilot.dem[rows, cols]
    extent = (bounds[0], bounds[1], bounds[2], bounds[3])
    materials = []
    if by_material:
        image, materials = material_image(pilot, rows, cols, bounds)
        ax.imshow(image, extent=extent, interpolation="nearest", zorder=0)
    else:
        ax.imshow(
            hillshade(window),
            cmap="gray",
            vmin=0.0,
            vmax=1.0,
            extent=extent,
            interpolation="nearest",
            zorder=0,
        )
    ax.materials = materials
    interval = contour_interval(window, intervals, max_contours)
    x = bounds[0] + np.arange(window.shape[1]) + 0.5
    y = bounds[3] - np.arange(window.shape[0]) - 0.5
    levels = np.arange(
        np.floor(np.nanmin(window) / interval) * interval,
        np.nanmax(window) + interval,
        interval,
    )
    ax.contour(
        x,
        y,
        window,
        levels=levels,
        colors="#5a4a3a",
        linewidths=0.4,
        alpha=0.7,
        zorder=1,
    )
    ax.set_xlim(bounds[0], bounds[1])
    ax.set_ylim(bounds[2], bounds[3])
    ax.set_aspect("equal")
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.tick_params(labelsize=6)
    ax.tick_params(axis="x", labelrotation=30)
    return interval


def draw_lines(ax, frame, *, colour, width, style="-", zorder=3):
    for geometry in frame.geometry:
        for line in getattr(geometry, "geoms", [geometry]):
            x, y = line.xy
            ax.plot(x, y, color=colour, lw=width, ls=style, zorder=zorder)


def draw_outlines(ax, frame, *, colour, zorder=2):
    for geometry in frame.geometry:
        for part in getattr(geometry, "geoms", [geometry]):
            x, y = part.exterior.xy
            ax.plot(x, y, color=colour, lw=0.9, ls="--", zorder=zorder)


def clipped(frame, bounds):
    """The rows of a layer that touch the window, with a little margin."""
    box = gpd.GeoSeries.from_xy(
        [bounds[0], bounds[1]], [bounds[2], bounds[3]], crs=CRS
    ).union_all()
    return frame[frame.intersects(box.envelope.buffer(2.0))]


def cell_xy(rows, cols, transform):
    return transform.c + cols + 0.5, transform.f - rows - 0.5


def window_burn(frame, bounds, shape):
    """The cells of a window that a layer's geometries cover, as a boolean grid."""
    shapes = [(g, 1) for g in frame.geometry if not g.is_empty]
    if not shapes:
        return np.zeros(shape, dtype=bool)
    return features.rasterize(
        shapes,
        out_shape=shape,
        transform=Affine(1.0, 0.0, bounds[0], 0.0, -1.0, bounds[3]),
        fill=0,
        dtype="uint8",
    ).astype(bool)


def paint(ax, cells, bounds, *, zorder):
    """Draw cells exactly, from an RGBA grid the shape of the window."""
    ax.imshow(
        cells,
        extent=(bounds[0], bounds[1], bounds[2], bounds[3]),
        interpolation="nearest",
        zorder=zorder,
    )


def rgba_grid(shape, groups):
    """An RGBA grid with each (mask, colour, alpha) painted over the last."""
    grid = np.zeros((*shape, 4))
    for mask, colour, alpha in groups:
        grid[mask] = (*mpl.colors.to_rgb(colour), alpha)
    return grid


def draw_seeds(ax, pilot, rows, cols, bounds):
    """Panel 1: only the seeds, the cells steep enough to start an element."""
    labels = pilot.found.labels[rows, cols]
    free = pilot.seed_free_face[rows, cols]
    bank = pilot.seed_bank[rows, cols]
    kept = labels > 0
    # One dot per seed cell, so the material colour underneath still shows.
    for mask, colour in (
        (bank & ~kept, SEED_DROPPED_COLOUR),
        (free & ~kept, SEED_DROPPED_COLOUR),
        (bank & kept, BANK_COLOUR),
        (free & kept, FREE_FACE_COLOUR),
    ):
        at = np.argwhere(mask)
        x, y = cell_xy(at[:, 0] + rows.start, at[:, 1] + cols.start, pilot.transform)
        ax.scatter(x, y, s=SEED_DOT_SIZE, c=colour, linewidths=0, zorder=4)
    return {
        "free": int((free & kept).sum()),
        "bank": int((bank & kept).sum()),
        "dropped": int(((free | bank) & ~kept).sum()),
    }


def draw_grown(ax, pilot, rows, cols, bounds):
    """Panel 2: the elements grown from the seeds, each outlined."""
    found = pilot.found
    labels = found.labels[rows, cols]
    kinds = found.elements["element_type"].to_numpy()
    inside = labels > 0
    is_free = np.zeros(labels.shape, dtype=bool)
    is_free[inside] = kinds[labels[inside] - 1] == FREE_FACE
    padded = np.pad(labels, 1)
    edge = np.zeros(labels.shape, dtype=bool)
    for shift in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        edge |= np.roll(padded, shift, axis=(0, 1))[1:-1, 1:-1] != labels
    paint(
        ax,
        rgba_grid(
            labels.shape,
            [
                (inside & ~is_free, BANK_COLOUR, 0.4),
                (inside & is_free, FREE_FACE_COLOUR, 0.55),
                (inside & edge, INK, 0.9),
            ],
        ),
        bounds,
        zorder=3,
    )
    ids = np.unique(labels[inside])
    areas = found.elements["area_m2"].to_numpy()[ids - 1]
    return {
        "elements": len(ids),
        "largest_m2": float(areas.max()) if len(ids) else 0.0,
    }


def wall_evidence(pilot, rows, cols, bounds, site_gns):
    """Each free-face's evidence for a wall in the window: GNS wall, break or none."""
    found = pilot.found
    labels = found.labels[rows, cols]
    shape = labels.shape
    index = np.unique(labels[labels > 0])
    free = index[found.elements["element_type"].to_numpy()[index - 1] == FREE_FACE]
    if not len(free):
        return pd.Series(dtype=object)
    walls = window_burn(site_gns["walls"], bounds, shape)
    wall_distance = (
        distance_to(walls) if walls.any() else np.full(shape, np.inf, dtype=float)
    )
    breaks = site_gns["breaks"]
    sharp = window_burn(breaks[breaks["Subtype"] == SHARP], bounds, shape)
    break_distance = (
        distance_to(sharp) if sharp.any() else np.full(shape, np.inf, dtype=float)
    )
    nearest_wall = ndimage.minimum(wall_distance, labels, free)
    nearest_break = ndimage.minimum(break_distance, labels, free)
    evidence = np.where(
        np.asarray(nearest_wall) <= config.GNS_WALL_MATCH_M,
        "gns",
        np.where(
            np.asarray(nearest_break) <= config.GNS_BREAK_MATCH_M, "break", "none"
        ),
    )
    return pd.Series(evidence, index=free)


def draw_wall_candidates(ax, pilot, rows, cols, bounds, site_gns):
    """Panel 3: every free-face is a wall candidate, shaded by its evidence."""
    found = pilot.found
    labels = found.labels[rows, cols]
    kinds = found.elements["element_type"].to_numpy()
    inside = labels > 0
    is_free = np.zeros(labels.shape, dtype=bool)
    is_free[inside] = kinds[labels[inside] - 1] == FREE_FACE
    evidence = wall_evidence(pilot, rows, cols, bounds, site_gns)
    groups = [(inside & ~is_free, BANK_GREY, 0.45)]
    for name, colour in WALL_EVIDENCE_COLOUR.items():
        mine = evidence.index[evidence == name]
        groups.append((np.isin(labels, mine), colour, 0.95))
    paint(ax, rgba_grid(labels.shape, groups), bounds, zorder=3)
    draw_gns(ax, site_gns, breaks=True)
    elements = found.elements
    for label in evidence.index:
        element = elements.loc[label]
        if not bounds[0] < element["centroid_x"] < bounds[1]:
            continue
        if not bounds[2] < element["centroid_y"] < bounds[3]:
            continue
        if element["height_m"] < LABEL_MIN_HEIGHT_M:
            continue
        text = ax.text(
            element["centroid_x"],
            element["centroid_y"],
            f"{element['height_m']:.1f}" + ("f" if pilot.is_fill.loc[label] else ""),
            fontsize=5.5,
            color=INK,
            ha="center",
            va="center",
            zorder=8,
        )
        text.set_path_effects([withStroke(linewidth=1.8, foreground="white")])
    return {name: int((evidence == name).sum()) for name in WALL_EVIDENCE_COLOUR}


def draw_gns(ax, site_gns, *, breaks=False):
    """The GNS mapped walls, with the sharp breaks in slope when asked."""
    if breaks:
        sharp = site_gns["breaks"][site_gns["breaks"]["Subtype"] == SHARP]
        draw_lines(ax, sharp, colour=SHARP_BREAK_COLOUR, width=0.9, zorder=6)
    draw_lines(ax, site_gns["walls"], colour=INK, width=1.8, zorder=7)


def draw_polygons(ax, pilot, windowed):
    """The zones of the polygons that reach the window, widest zone first.

    Each evacuated polygon's own edge is drawn, so a large element split into
    segments reads as separate polygons. Imminent and inundated zones are filled
    only, with their combined outer edge.
    """
    kinds = pilot.result.polygons["element_type"]
    evacuated = polygon_geometries(windowed, zone=EVACUATED, crs=CRS)
    for zone in (INUNDATED, IMMINENT, EVACUATED):
        shapes = (
            evacuated
            if zone == EVACUATED
            else polygon_geometries(windowed, zone=zone, crs=CRS)
        )
        for polygon, geometry in zip(shapes["polygon"], shapes.geometry, strict=True):
            colour = ZONE_COLOUR[zone] or TYPE_COLOUR[kinds.loc[polygon]]
            for part in getattr(geometry, "geoms", [geometry]):
                x, y = part.exterior.xy
                ax.fill(
                    x,
                    y,
                    facecolor=colour,
                    alpha=0.3,
                    lw=0,
                    zorder=2 if zone != EVACUATED else 3,
                )
                if zone == EVACUATED:
                    ax.plot(x, y, color=INK, lw=0.5, alpha=0.8, zorder=4)
        if zone != EVACUATED:
            for part in getattr(shapes.union_all(), "geoms", [shapes.union_all()]):
                x, y = part.exterior.xy
                ax.plot(x, y, color=colour, lw=1.0, zorder=3)


def windowed_result(pilot, rows, cols):
    """The result cut to the polygons with a cell in the window."""
    cells = pilot.result.cells
    inside = (
        cells["row"].between(rows.start, rows.stop - 1)
        & cells["col"].between(cols.start, cols.stop - 1)
        & (cells["zone"] == EVACUATED)
    )
    polygons = np.unique(cells.loc[inside, "polygon"])
    keep = cells[cells["polygon"].isin(polygons)]
    return SlopePolygons(
        polygons=pilot.result.polygons.loc[polygons],
        cells=keep,
        element_links=pilot.result.element_links,
        retrogression_links=pilot.result.retrogression_links,
        overlaps=pilot.result.overlaps,
        shape=pilot.result.shape,
        transform=pilot.result.transform,
    )


def site_layers(pilot, bounds):
    return {
        "walls": clipped(pilot.walls, bounds),
        "breaks": clipped(pilot.breaks, bounds),
        "cut_fill_lines": clipped(pilot.cut_fill_lines, bounds),
        "cut": clipped(pilot.genesis[pilot.genesis["Type"] == CUT_SLOPE_TYPE], bounds),
        "fill": clipped(pilot.genesis[pilot.genesis["Type"] == FILL_BODY_TYPE], bounds),
    }


def material_handles(materials):
    return [
        Patch(facecolor=MATERIAL_COLOUR[m], edgecolor="none", label=m.replace("_", " "))
        for m in materials
    ]


def gns_wall_handle():
    return Line2D([], [], color=INK, lw=1.8, label="GNS mapped retaining wall")


def seed_handles(counts):
    def dot(colour, label):
        return Line2D(
            [], [], ls="", marker="o", ms=3, mfc=colour, mec="none", label=label
        )

    return [
        dot(
            FREE_FACE_COLOUR,
            f"Step or slope test passed, seeds a free-face ({counts['free']:,} cells)",
        ),
        dot(
            BANK_COLOUR,
            f"Bank slope test passed, seeds a bank ({counts['bank']:,} cells)",
        ),
        dot(
            SEED_DROPPED_COLOUR,
            f"Seed whose region failed the tests ({counts['dropped']:,})",
        ),
    ]


def grown_handles():
    return [
        Patch(facecolor=FREE_FACE_COLOUR, alpha=0.55, label="Free-face element"),
        Patch(facecolor=BANK_COLOUR, alpha=0.4, label="Bank element"),
        Line2D([], [], color=INK, lw=1.2, label="Edge of each element"),
    ]


def wall_handles(counts):
    return [
        Patch(
            facecolor=WALL_EVIDENCE_COLOUR["gns"],
            label=f"Wall candidate, GNS wall within {config.GNS_WALL_MATCH_M:g} m ({counts['gns']})",
        ),
        Patch(
            facecolor=WALL_EVIDENCE_COLOUR["break"],
            label=f"Wall candidate, GNS sharp break within {config.GNS_BREAK_MATCH_M:g} m ({counts['break']})",
        ),
        Patch(
            facecolor=WALL_EVIDENCE_COLOUR["none"],
            label=f"Wall candidate, neither ({counts['none']})",
        ),
        Patch(facecolor=BANK_GREY, alpha=0.45, label="Bank (not a wall candidate)"),
        gns_wall_handle(),
        Line2D([], [], color=SHARP_BREAK_COLOUR, lw=0.9, label="GNS sharp break"),
        Patch(
            facecolor="none",
            edgecolor="none",
            label="Number: height in m; f = ground map says fill",
        ),
    ]


def polygon_handles():
    return [
        Patch(facecolor=FREE_FACE_COLOUR, alpha=0.3, label="Evacuated, free-face"),
        Patch(facecolor=BANK_COLOUR, alpha=0.3, label="Evacuated, bank"),
        Patch(facecolor=IMMINENT_COLOUR, alpha=0.3, label="Imminent"),
        Patch(facecolor=INUNDATED_COLOUR, alpha=0.3, label="Inundated"),
        Line2D([], [], color=INK, lw=0.6, label="Edge of each evacuated polygon"),
    ]


def site_table(pilot, windowed, site, rows, cols, bounds, layers):
    """What the library found in a site's window, for the findings document."""
    elements = pilot.found.elements
    inside = elements[
        elements["centroid_x"].between(bounds[0], bounds[1])
        & elements["centroid_y"].between(bounds[2], bounds[3])
    ]
    polygons = windowed.polygons
    mine = polygons[polygons["element"].isin(inside.index)]
    wall_length = float(
        layers["walls"]
        .intersection(
            gpd.GeoSeries.from_xy(
                [bounds[0], bounds[1]], [bounds[2], bounds[3]], crs=CRS
            )
            .union_all()
            .envelope
        )
        .length.sum()
    )
    reaching = polygons.groupby("element")
    return {
        "site": site["name"],
        "free_faces": int((inside["element_type"] == FREE_FACE).sum()),
        "banks": int((inside["element_type"] == BANK).sum()),
        "tallest_m": round(float(inside["height_m"].max()), 1) if len(inside) else 0.0,
        "polygons": len(mine),
        "wall_rule": int((mine["width_rule"] == "wall_wedge").sum()),
        "band_rule": int((mine["width_rule"] == "headscarp_band").sum()),
        "stacks": int(mine["is_stack"].sum()),
        "evacuated_m2": float(mine["area_m2"].sum()),
        "volume_m3": float(mine["volume_m3"].sum()),
        "fill_elements": int(pilot.is_fill.loc[inside.index].sum()),
        "gns_wall_m": round(wall_length),
        # Over every polygon that reaches the window, including elements whose
        # centroid is outside it, because a large bank's polygons run in from outside.
        "reaching_polygons": len(polygons),
        "largest_polygon_m2": float(polygons["area_m2"].max())
        if len(polygons)
        else 0.0,
        "most_segments": int(reaching.size().max()) if len(polygons) else 0,
        "largest_element_m2": (
            float(elements.loc[polygons["element"], "area_m2"].max())
            if len(polygons)
            else 0.0
        ),
    }


def draw_site(pilot, site, *, intervals, max_contours):
    x, y, half = site["x"], site["y"], site["half_size_m"]
    rows, cols, bounds = window_slices(pilot, x, y, half)
    layers = site_layers(pilot, bounds)
    windowed = windowed_result(pilot, rows, cols)

    fig = plt.figure(figsize=(13, 14.6))
    grid = fig.add_gridspec(
        2, 2, left=0.06, right=0.99, top=0.9, bottom=0.1, hspace=0.46, wspace=0.14
    )
    axes = [fig.add_subplot(grid[i, j]) for i in range(2) for j in range(2)]
    ax_seed, ax_grown, ax_wall, ax_poly = axes
    interval = None
    for ax in axes:
        interval = draw_base(
            ax,
            pilot,
            rows,
            cols,
            bounds,
            intervals=intervals,
            max_contours=max_contours,
            by_material=ax is ax_seed,
        )
    seed_counts = draw_seeds(ax_seed, pilot, rows, cols, bounds)
    grown = draw_grown(ax_grown, pilot, rows, cols, bounds)
    wall_counts = draw_wall_candidates(ax_wall, pilot, rows, cols, bounds, layers)
    draw_polygons(ax_poly, pilot, windowed)
    table = site_table(pilot, windowed, site, rows, cols, bounds, layers)

    legend_materials = site.get("legend_materials", ax_seed.materials)
    bank_slope_deg = site.get("bank_slope_deg", BETA_GROW_ANGLE_DEG)
    steps = (
        (
            ax_seed,
            "1. Seeds: only the steepest ground",
            (
                "Dots: cells that pass a threshold. Orange: step test (step over the "
                "minimum) or slope test (3 m slope over the angle for the ground and "
                "step height). Green: bank slope test (over "
                f"{bank_slope_deg:g}\u00b0), any material. See "
                "landslide-slope/seed-thresholds.csv."
            ),
            seed_handles(seed_counts) + material_handles(legend_materials),
        ),
        (
            ax_grown,
            "2. Elements: each seed grown into the steep ground around it",
            (
                "The grown regions are the elements, each outlined. "
                f"{grown['elements']} reach this window; the largest covers "
                f"{grown['largest_m2']:,.0f} m\u00b2 (it may run outside the window). "
                "Bank seeds already cover all ground over the bank angle, so a bank "
                "is one region however large."
            ),
            grown_handles(),
        ),
        (
            ax_wall,
            "3. Wall candidates: every free-face, with the evidence there is",
            (
                "Not built yet (phase 2): every free-face is taken as a wall. Shaded "
                "by whether a GNS wall or sharp break lies close, which is evidence a "
                "wall probability could weigh."
            ),
            wall_handles(wall_counts),
        ),
        (
            ax_poly,
            "4. Failure polygons: what each element takes with it",
            (
                "Each element takes the ground behind its crest (a wall's wedge, a "
                "headscarp band or a share of its height), and a long or tall element "
                f"is cut into segments, one polygon each. {table['reaching_polygons']} "
                f"polygons reach this window; one element has {table['most_segments']} "
                f"of them, and the largest polygon is {table['largest_polygon_m2']:,.0f}"
                " m\u00b2."
            ),
            polygon_handles(),
        ),
    )
    for ax, title, caption, handles in steps:
        ax.set_title(title, fontsize=9.5, fontweight="bold", loc="left", pad=46)
        ax.text(
            0,
            1.012,
            textwrap.fill(caption, 98),
            transform=ax.transAxes,
            fontsize=6.8,
            va="bottom",
            ha="left",
            linespacing=1.25,
        )
        ax.legend(
            handles=handles,
            loc="upper left",
            bbox_to_anchor=(0.0, -0.1),
            ncol=2,
            fontsize=6.5,
            frameon=False,
        )
    fig.suptitle(
        textwrap.fill(f"{site['name']}: {site['category']}. {site['reason']}", 170)
        + "\n"
        + textwrap.fill(f"Should show: {site['expect']}", 170),
        fontsize=9,
        x=0.02,
        ha="left",
        y=0.995,
    )
    ax_seed.text(
        0.01,
        0.01,
        f"Contours every {interval:g} m; NZTM, window {2 * half:g} m",
        transform=ax_seed.transAxes,
        fontsize=6,
        color="white",
        bbox={"facecolor": "black", "alpha": 0.5, "pad": 1.5, "lw": 0},
    )
    path = (
        FIG_DIR / f"pilot_site_{site['name']}{extent_suffix(config.PILOT_EXTENT)}.png"
    )
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path, table


def draw_overview(pilot, sites):
    """The pilot's hillshade with the evacuated ground and the sites boxed."""
    step = 2
    dem = pilot.dem
    n_rows, n_cols = dem.shape
    bounds = (
        pilot.transform.c,
        pilot.transform.c + n_cols,
        pilot.transform.f - n_rows,
        pilot.transform.f,
    )
    fig, ax = plt.subplots(figsize=(13, 8.5))
    ax.imshow(
        hillshade(dem)[::step, ::step],
        cmap="gray",
        vmin=0,
        vmax=1,
        extent=(bounds[0], bounds[1], bounds[2], bounds[3]),
        zorder=0,
    )
    ax.imshow(
        np.ma.masked_equal(pilot.water.astype(float), 0)[::step, ::step],
        cmap=ListedColormap(["#9cc4e4"]),
        alpha=0.6,
        extent=(bounds[0], bounds[1], bounds[2], bounds[3]),
        zorder=1,
    )
    evacuated = pilot.result.cells[pilot.result.cells["zone"] == EVACUATED]
    mask = np.zeros(dem.shape, dtype=float)
    mask[evacuated["row"], evacuated["col"]] = 1.0
    overlay = np.ma.masked_equal(mask, 0)[::step, ::step]
    ax.imshow(
        overlay,
        cmap=ListedColormap([FREE_FACE_COLOUR]),
        alpha=0.5,
        vmin=0,
        vmax=1,
        extent=(bounds[0], bounds[1], bounds[2], bounds[3]),
        zorder=1,
    )
    draw_lines(ax, pilot.walls, colour=INK, width=0.7, zorder=3)
    for site in sites:
        half = site["half_size_m"]
        ax.add_patch(
            Rectangle(
                (site["x"] - half, site["y"] - half),
                2 * half,
                2 * half,
                fill=False,
                ec="#1f4ea8",
                lw=1.2,
                zorder=4,
            )
        )
        ax.text(
            site["x"] + half,
            site["y"] + half,
            site["name"][:2],
            color="#1f4ea8",
            fontsize=9,
            fontweight="bold",
            zorder=5,
        )
    ax.set_xlim(bounds[0], bounds[1])
    ax.set_ylim(bounds[2], bounds[3])
    ax.set_aspect("equal")
    ax.set_title(
        "Stage D2 sites over the pilot: evacuated ground of every polygon (orange), "
        "GNS mapped retaining walls (black) and the LINZ water mask (blue)",
        fontsize=10,
    )
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")
    path = FIG_DIR / f"pilot_sites_overview{extent_suffix(config.PILOT_EXTENT)}.png"
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return path


def agreement(pilot, *, wall_match_m, break_match_m):
    """How far the elements and the GNS mapping agree over the whole pilot."""
    found = pilot.found
    elements = found.elements
    is_free = np.isin(
        found.labels, elements.index[elements["element_type"] == FREE_FACE]
    )
    is_any = found.labels > 0
    crest = (found.edge_roles & CREST) > 0
    face_crest = is_free & crest
    any_edge = is_any & ((found.edge_roles & (CREST | TOE)) > 0)

    wall = burn(pilot.walls.geometry, pilot)
    breaks = burn(pilot.breaks.geometry, pilot)
    sharp = burn(
        pilot.breaks[pilot.breaks["Subtype"] == SHARP].geometry,
        pilot,
    )
    cut_fill = burn(pilot.cut_fill_lines.geometry, pilot)
    in_cut = burn(
        pilot.genesis[pilot.genesis["Type"] == CUT_SLOPE_TYPE].geometry,
        pilot,
        all_touched=False,
    )
    in_fill = burn(
        pilot.genesis[pilot.genesis["Type"] == FILL_BODY_TYPE].geometry,
        pilot,
        all_touched=False,
    )

    d_face = distance_to(is_free)
    d_any = distance_to(is_any)
    d_edge = distance_to(any_edge)
    d_wall = distance_to(wall)
    d_break = distance_to(breaks)
    d_mapped = distance_to(wall | breaks | cut_fill)
    rows = [
        {
            "check": "GNS wall cells with a free-face within the wall match",
            "n": int(wall.sum()),
            "share": float((d_face[wall] <= wall_match_m).mean()),
        },
        {
            "check": "GNS wall cells with any element within the wall match",
            "n": int(wall.sum()),
            "share": float((d_any[wall] <= wall_match_m).mean()),
        },
        {
            "check": "GNS sharp-break cells with an element crest or toe within the break match",
            "n": int(sharp.sum()),
            "share": float((d_edge[sharp] <= break_match_m).mean()),
        },
        {
            "check": "GNS rounded-break cells with an element crest or toe within the break match",
            "n": int((breaks & ~sharp).sum()),
            "share": float((d_edge[breaks & ~sharp] <= break_match_m).mean()),
        },
        {
            "check": "Free-face crest cells within the wall match of a GNS wall",
            "n": int(face_crest.sum()),
            "share": float((d_wall[face_crest] <= wall_match_m).mean()),
        },
        {
            "check": "Free-face crest cells within the break match of a GNS break",
            "n": int(face_crest.sum()),
            "share": float((d_break[face_crest] <= break_match_m).mean()),
        },
        {
            "check": "Free-face crest cells within the break match of any GNS wall, break or cut/fill line",
            "n": int(face_crest.sum()),
            "share": float((d_mapped[face_crest] <= break_match_m).mean()),
        },
        {
            "check": "Free-face crest cells inside a SLIDE cut slope or fill body",
            "n": int(face_crest.sum()),
            "share": float((in_cut | in_fill)[face_crest].mean()),
        },
    ]
    return pd.DataFrame(rows)


def whole_pilot_summary(pilot):
    found = pilot.found
    result = pilot.result
    polygons = result.polygons
    evacuated = result.cells[result.cells["zone"] == EVACUATED]
    n_cells = pilot.dem.size
    return {
        "elements": len(found.elements),
        "free_faces": int((found.elements["element_type"] == FREE_FACE).sum()),
        "banks": int((found.elements["element_type"] == BANK).sum()),
        "polygons": len(polygons),
        "styles": polygons["style"].value_counts().to_dict(),
        "width_rules": polygons["width_rule"].value_counts().to_dict(),
        "stack_polygons": int(polygons["is_stack"].sum()),
        "overlaps": result.overlaps["reason"].value_counts().to_dict(),
        "retrogression_links": len(result.retrogression_links),
        "evacuated_cells": len(evacuated),
        "evacuated_distinct_cells": int(
            evacuated[["row", "col"]].drop_duplicates().shape[0]
        ),
        "share_of_grid_evacuated": float(
            evacuated[["row", "col"]].drop_duplicates().shape[0] / n_cells
        ),
        "water_share_of_grid": float(pilot.water.mean()),
        "share_of_land_evacuated": float(
            evacuated[["row", "col"]].drop_duplicates().shape[0] / (~pilot.water).sum()
        ),
        "evacuated_cells_on_water": int(
            pilot.water[evacuated["row"], evacuated["col"]].sum()
        ),
        "fill_elements": int(pilot.is_fill.sum()),
        "seconds": pilot.seconds,
    }


def main(
    *, extent, sites, contour_intervals_m, max_contours, wall_match_m, break_match_m
):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_colwidth", 90)
    paths = []
    tables = []
    pilots = {}
    for site in sites:
        bank_slope_deg = site.get("bank_slope_deg", config.PILOT_BANK_SLOPE_DEG)
        pilot = pilots.get(bank_slope_deg)
        if pilot is None:
            pilot = get_pilot_run(extent=extent, bank_slope_deg=bank_slope_deg)
            pilots[bank_slope_deg] = pilot
            label = (
                f"bank slope {bank_slope_deg:g}°"
                if bank_slope_deg is not None
                else "default bank slope"
            )
            print(f"Elements and polygons over the {extent} pilot ({label}) in {pilot.seconds:.1f} s")
            print("\n=== Whole pilot")
            for key, value in whole_pilot_summary(pilot).items():
                print(f"{key}: {value}")
            print("\n=== Agreement with the GNS mapping, whole pilot")
            print(
                agreement(pilot, wall_match_m=wall_match_m, break_match_m=break_match_m)
                .round(3)
                .to_string(index=False)
            )
        path, table = draw_site(
            pilot, site, intervals=contour_intervals_m, max_contours=max_contours
        )
        paths.append(path)
        tables.append(table)
    print("\n=== Sites")
    print(pd.DataFrame(tables).round(1).to_string(index=False))
    paths.append(draw_overview(pilot, sites))
    print("\nFigures:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main(
        extent=config.PILOT_EXTENT,
        sites=config.PILOT_SITES,
        contour_intervals_m=config.PILOT_CONTOUR_INTERVALS_M,
        max_contours=config.PILOT_MAX_CONTOURS,
        wall_match_m=config.GNS_WALL_MATCH_M,
        break_match_m=config.GNS_BREAK_MATCH_M,
    )
