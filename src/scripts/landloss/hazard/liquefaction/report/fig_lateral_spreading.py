"""Plot how the lateral spreading correction works, and write it out for GIS.

Three figures, for explaining the correction rather than for checking a run:

- ``lateral-spreading-zones.png``: the free faces by type, and the near (within
  100 m) and middle (100 to 200 m) zones buffered from them. Everywhere else is
  the far zone.
- ``lateral-spreading-change.png``: the NLM's P(at least Major) before the
  correction, after it, and the change, cell by cell.
- ``lateral-spreading-correction.png``: the correction itself, the corrected
  probability against the NLM's, for each zone.

It also writes the same content as a GeoPackage for GIS,
``temp/hazard/liquefaction/lateral-spreading<suffix>.gpkg``, with three
layers: ``free_faces``, ``ls_zones`` (near and middle; the far zone is
everywhere else), and ``nlm_cells``, one polygon per NLM cell carrying its
probabilities before and after the correction, the change, the zone its centre
falls in and its weight between the near and far maps.

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/report/fig_lateral_spreading.py

What it runs over is :data:`EXTENT`, at the bottom of this file: ``"lower-hutt"``
for explaining the method, since the small Wellington pilot box holds no river,
only coast, or ``"full"`` for the four territorial authorities. Every output
carries the extent's suffix from :data:`SUFFIXES`, so one run does not overwrite
another. Over the full study area a cell is kept where its centre lies inside
the four authorities' boundary.

It reads the free faces step 1 wrote for the same extent, so run
``s1_free_faces`` with that EXTENT first, and the NLM grids from the local cache
step 2 keeps of them: this script never reads the T: drive, so run step 2 once on
a machine that can.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rioxarray
import shapely
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from rasterio.enums import Resampling
from shapely.geometry import box

import tdrive_sync
from landloss.common.utils.plot import style_basemap_ax
from landloss.domain import constants
from landloss.hazard.liquefaction.lateral_spreading import (
    FAR_FIELD_M,
    KNEE,
    MIDDLE_BAND_FAR_WEIGHT,
    NEAR_FIELD_M,
    ZONES,
    apply_lateral_spreading,
    correct_major_or_worse,
    far_weight_grid,
    lateral_spreading_zones,
    zone_grid,
)
from landloss.io.area_of_interest import (
    FULL_EXTENT,
    LOWER_HUTT_PILOT,
    get_study_areas,
)
from landloss.io.nlm import NLM_RELEASES_DIR
from scripts.landloss.hazard.liquefaction.steps.s1_free_faces.gen_liq_free_faces import (
    LOWER_HUTT,
    free_faces_path,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    clip_to_extent,
)
from scripts.landloss.paths import REPORT_DIR, TEMP_DIR

FIG_DIR = REPORT_DIR / "hazard" / "liquefaction" / "fig"
DPI = 200
GIS_DIR = TEMP_DIR / "hazard" / "liquefaction"

# The extents this script draws, the name each is titled with, and the suffix
# each output carries.
NAMES = {LOWER_HUTT: "lower Hutt Valley", FULL_EXTENT: "the study area"}
SUFFIXES = {LOWER_HUTT: "-lower-hutt", FULL_EXTENT: "-study-area"}

# The same two grids step 2 reads, by their path below the NLM's release tree.
NLM_GRIDS = {
    "moderate": "core/v2026p0rc6/scenario/return_period/"
    "rp2500y_lsn_pl50_gwd-med_p_ld_moderate_fu.tif",
    "major": "core/v2026p0rc6/scenario/return_period/"
    "rp2500y_lsn_pl50_gwd-med_p_ld_major_fu.tif",
}

NEAR_COLOUR = "#d7301f"
MIDDLE_COLOUR = "#fdae61"
FAR_COLOUR = "#4575b4"
FACE_STYLES = {
    "river": {"color": "#08519c", "linewidth": 1.6},
    "coast": {"color": "#252525", "linewidth": 1.2},
    "lake": {"color": "#6baed6", "linewidth": 1.0},
    "swamp": {"color": "#41ab5d", "linewidth": 1.0},
    "lagoon": {"color": "#807dba", "linewidth": 1.0},
}
FACE_LABELS = {
    "river": "River (named, or kept by ID)",
    "coast": "Coastline",
    "lake": "Lake of 5 ha or more",
    "swamp": "Swamp of 5 ha or more",
    "lagoon": "Lagoon of 5 ha or more",
}


def read_cached_nlm(name):
    """Read one NLM grid from the local cache step 2 keeps, never from T:.

    Raises:
        FileNotFoundError: If step 2 has not cached the grid on this machine.
    """
    path = tdrive_sync.get_cached_local_path(NLM_RELEASES_DIR / NLM_GRIDS[name])
    if not path.exists():
        msg = f"No cached NLM grid at {path}. Run s2_ld_probabilities once first."
        raise FileNotFoundError(msg)
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze(drop=True).load()


def extent_frame(extent):
    """Return the area drawn as a one-row frame in the study's projection.

    The lower Hutt box, or the four territorial authorities dissolved into one.

    Raises:
        KeyError: If ``extent`` is not one of :data:`NAMES`.
    """
    if extent not in NAMES:
        msg = f"EXTENT must be one of {sorted(NAMES)}, not {extent!r}"
        raise KeyError(msg)
    if extent == FULL_EXTENT:
        areas = get_study_areas(constants.DEFAULT_CRS)
        return gpd.GeoDataFrame(
            geometry=[areas.geometry.union_all()], crs=constants.DEFAULT_CRS
        )
    bbox = LOWER_HUTT_PILOT.bbox(constants.DEFAULT_CRS)
    return gpd.GeoDataFrame(geometry=[box(*bbox)], crs=constants.DEFAULT_CRS)


def mask_outside(grid, area):
    """Blank the cells whose centre lies outside the area drawn."""
    xs, ys = np.meshgrid(grid.x.to_numpy(), grid.y.to_numpy())
    inside = shapely.contains_xy(area.geometry.iloc[0], xs, ys)
    return grid.where(inside)


def read_free_faces(extent, area):
    """Read the free faces step 1 wrote, and those of them within the area drawn.

    Raises:
        FileNotFoundError: If step 1 has not been run for the extent.
    """
    path = free_faces_path(extent)
    if not path.exists():
        msg = f'No free faces at {path}. Run s1_free_faces with EXTENT = "{extent}".'
        raise FileNotFoundError(msg)
    faces = gpd.read_file(path).to_crs(constants.DEFAULT_CRS)
    return faces, gpd.clip(faces, area)


def raster_extent(grid):
    """Return a grid's bounds in the order ``imshow`` wants them."""
    west, south, east, north = grid.rio.bounds()
    return (west, east, south, north)


def draw_faces(ax, faces):
    """Draw the free faces by type, polygons as outlines over a light fill."""
    for wtype, style in FACE_STYLES.items():
        subset = faces.loc[faces["wtype"] == wtype]
        if subset.empty:
            continue
        is_area = subset.geom_type.str.contains("Polygon")
        if is_area.any():
            subset.loc[is_area].plot(
                ax=ax, facecolor=style["color"], alpha=0.25, edgecolor="none", zorder=4
            )
            subset.loc[is_area].boundary.plot(ax=ax, zorder=5, **style)
        if (~is_area).any():
            subset.loc[~is_area].plot(ax=ax, zorder=5, **style)


def face_handles(faces):
    """Return a legend entry for each free face type present."""
    present = [w for w in FACE_STYLES if (faces["wtype"] == w).any()]
    return [Line2D([], [], label=FACE_LABELS[w], **FACE_STYLES[w]) for w in present]


def plot_zones(faces, zones, extent, name):
    """Draw the free faces and the near and middle zones buffered from them."""
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    clipped = gpd.clip(zones, extent)
    colours = {"near": NEAR_COLOUR, "middle": MIDDLE_COLOUR}
    for _, row in clipped.iterrows():
        gpd.GeoSeries([row.geometry], crs=zones.crs).plot(
            ax=ax, color=colours[row["zone_name"]], alpha=0.35, zorder=3
        )
    draw_faces(ax, faces)
    style_basemap_ax(ax, extent)

    handles = [
        Patch(
            color=NEAR_COLOUR,
            alpha=0.35,
            label=f"Near zone, within {NEAR_FIELD_M:.0f} m",
        ),
        Patch(
            color=MIDDLE_COLOUR,
            alpha=0.35,
            label=f"Middle zone, {NEAR_FIELD_M:.0f} to {FAR_FIELD_M:.0f} m",
        ),
        Patch(
            facecolor="none",
            edgecolor="#999999",
            label=f"Far zone, beyond {FAR_FIELD_M:.0f} m",
        ),
        *face_handles(faces),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=7.5, framealpha=0.92)
    ax.set_title(f"Lateral spreading zones, {name}", fontsize=10)
    return fig


def plot_change(before, after, faces, zones, extent):
    """Draw P(at least Major) before and after the correction, and the change."""
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.6), constrained_layout=True)
    vmax = float(np.nanmax([np.nanmax(before), np.nanmax(after)]))
    limits = raster_extent(before)
    outline = gpd.clip(zones, extent).boundary

    for ax, grid, title in (
        (axes[0], before, "NLM P(at least Major)"),
        (axes[1], after, "After the lateral spreading correction"),
    ):
        image = ax.imshow(
            grid.to_numpy(),
            extent=limits,
            cmap="YlOrRd",
            vmin=0,
            vmax=vmax,
            alpha=0.85,
            zorder=2,
            interpolation="nearest",
        )
        outline.plot(ax=ax, color="#333333", linewidth=0.5, linestyle=":", zorder=4)
        draw_faces(ax, faces)
        style_basemap_ax(ax, extent, scalebar_kwargs={"font_size": 7})
        ax.set_title(title, fontsize=10)
    fig.colorbar(
        image, ax=axes[:2], shrink=0.75, label="Probability", location="bottom"
    )

    change = (after - before) * 100
    span = float(np.nanmax(np.abs(change))) or 1.0
    shift = axes[2].imshow(
        change.to_numpy(),
        extent=limits,
        cmap="RdBu_r",
        norm=TwoSlopeNorm(vmin=-span, vcenter=0, vmax=span),
        alpha=0.9,
        zorder=2,
        interpolation="nearest",
    )
    outline.plot(ax=axes[2], color="#333333", linewidth=0.5, linestyle=":", zorder=4)
    draw_faces(axes[2], faces)
    style_basemap_ax(axes[2], extent, scalebar_kwargs={"font_size": 7})
    axes[2].set_title("Change (percentage points)", fontsize=10)
    fig.colorbar(
        shift, ax=axes[2], shrink=0.75, label="Percentage points", location="bottom"
    )
    return fig


def plot_correction():
    """Draw the corrected P(at least Major) against the NLM's, for each zone."""
    p = np.linspace(0, 0.5, 501)
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    ax.plot(p, p, color="#999999", linestyle="--", linewidth=1, label="No correction")
    for weight, colour, label in (
        (0.0, NEAR_COLOUR, f"Near zone (within {NEAR_FIELD_M:.0f} m)"),
        (
            MIDDLE_BAND_FAR_WEIGHT,
            MIDDLE_COLOUR,
            f"Middle zone ({NEAR_FIELD_M:.0f} to {FAR_FIELD_M:.0f} m)",
        ),
        (1.0, FAR_COLOUR, f"Far zone (beyond {FAR_FIELD_M:.0f} m)"),
    ):
        ax.plot(
            p,
            correct_major_or_worse(p, np.full_like(p, weight)),
            color=colour,
            linewidth=2,
            label=label,
        )
    ax.axvline(KNEE, color="#666666", linewidth=0.8, linestyle=":")
    ax.text(KNEE + 0.005, 0.47, f"knee, {KNEE:.1%}", fontsize=8, color="#444444")

    for weight, colour in (
        (0.0, NEAR_COLOUR),
        (MIDDLE_BAND_FAR_WEIGHT, MIDDLE_COLOUR),
        (1.0, FAR_COLOUR),
    ):
        value = float(correct_major_or_worse(np.array([0.2]), np.array([weight]))[0])
        ax.plot([0.2], [value], "o", color=colour, markersize=5)
        ax.annotate(
            f"{value:.0%}",
            (0.2, value),
            xytext=(6, -3),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xlim(0, 0.5)
    ax.set_ylim(0, 0.5)
    ax.set_xlabel("NLM P(at least Major)")
    ax.set_ylabel("Corrected P(at least Major)")
    ax.set_title("The correction, by zone", fontsize=10)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0, decimals=0))
    ax.grid(color="#eeeeee")
    ax.legend(fontsize=8, loc="lower right")
    return fig


def describe(zone, before, after, capped):
    """Print the cells, mean P(at least Major) and cap count per zone."""
    zones = zone.to_numpy()
    b, a = before.to_numpy(), after.to_numpy()
    print(f"  {'zone':<8} {'cells':>7} {'NLM mean':>9} {'corrected':>10}")
    for code, name in ZONES.items():
        mask = (zones == code) & np.isfinite(b)
        if mask.any():
            print(
                f"  {name:<8} {int(mask.sum()):>7,} {b[mask].mean():>9.1%} {a[mask].mean():>10.1%}"
            )
    print(f"  Capped at P(at least Moderate) in {int(capped.to_numpy().sum()):,} cells")


def cell_polygons(grid):
    """Return one square polygon per cell of a north-up grid, row by row."""
    xs, ys = grid.x.to_numpy(), grid.y.to_numpy()
    half_x, half_y = abs(xs[1] - xs[0]) / 2, abs(ys[1] - ys[0]) / 2
    cx, cy = np.meshgrid(xs, ys)
    return [
        box(x - half_x, y - half_y, x + half_x, y + half_y)
        for x, y in zip(cx.ravel(), cy.ravel(), strict=True)
    ]


def write_gis(path, faces, zones, extent, cells):
    """Write the free faces, the zones and the corrected cells to one GeoPackage.

    Args:
        path: The GeoPackage to write, replaced if it is there.
        faces: The free faces within the box.
        zones: The near and middle zones.
        extent: The box, to clip the zones to.
        cells: The grids, by column name, on one grid; cells with no NLM value
            are left out.
    """
    first = next(iter(cells.values()))
    frame = gpd.GeoDataFrame(
        {name: grid.to_numpy().ravel() for name, grid in cells.items()},
        geometry=cell_polygons(first),
        crs=first.rio.crs,
    ).to_crs(constants.DEFAULT_CRS)
    frame = frame.loc[np.isfinite(frame["p_major_nlm"])].reset_index(drop=True)
    frame["zone_name"] = frame["ls_zone"].map(ZONES)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    faces.to_file(path, layer="free_faces", driver="GPKG")
    gpd.clip(zones, extent).to_file(path, layer="ls_zones", driver="GPKG")
    frame.to_file(path, layer="nlm_cells", driver="GPKG")
    print(f"Wrote {path} ({len(frame):,} cells)")


def main(*, extent):
    """Build the three figures and the GeoPackage, and write them out.

    Args:
        extent: One of :data:`NAMES`, from :data:`EXTENT`.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    area = extent_frame(extent)
    name = NAMES[extent]
    suffix = SUFFIXES[extent]
    all_faces, faces = read_free_faces(extent, area)
    zones = lateral_spreading_zones(all_faces)

    bbox = tuple(float(v) for v in area.total_bounds)
    moderate = clip_to_extent(read_cached_nlm("moderate"), bbox, "moderate")
    major = clip_to_extent(read_cached_nlm("major"), bbox, "major")
    major = major.rio.reproject_match(moderate, resampling=Resampling.nearest)
    moderate = mask_outside(moderate, area)
    major = mask_outside(major, area)
    weight = far_weight_grid(zones, major)
    corrected, capped = apply_lateral_spreading(moderate, major, weight)
    zone = zone_grid(zones, major)

    print(f"{name[0].upper()}{name[1:]}, {len(faces):,} free faces:")
    describe(zone, major, corrected, capped)

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for file_name, fig in (
        (f"lateral-spreading-zones{suffix}.png", plot_zones(faces, zones, area, name)),
        (
            f"lateral-spreading-change{suffix}.png",
            plot_change(major, corrected, faces, zones, area),
        ),
        ("lateral-spreading-correction.png", plot_correction()),
    ):
        path = FIG_DIR / file_name
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {path}")

    write_gis(
        GIS_DIR / f"lateral-spreading{suffix}.gpkg",
        faces,
        zones,
        area,
        {
            "p_moderate_nlm": moderate,
            "p_major_nlm": major,
            "p_major_corrected": corrected,
            "change_pp": (corrected - major) * 100,
            "ls_zone": zone,
            "far_weight": weight,
            "capped": capped,
        },
    )


# The extent to draw: "lower-hutt" or "full".
EXTENT = FULL_EXTENT

if __name__ == "__main__":
    main(extent=EXTENT)
