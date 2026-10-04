"""Stage D2: pips, pifs, sizs and the evacuated zones on real pilot ground.

Runs :func:`landloss.hazard.landslide.instability_zones.find_instability_zones`
once over the whole pilot DEM, with fill taken as soil, and draws each site in
``config.PILOT_SITES`` as four map panels:

1. pips (dots, so the material shows) coloured by whether their pif is a siz;
2. the elements grown from the sizs, each outlined;
3. the evacuated zones if **every siz has a retaining wall**;
4. the evacuated zones if **no siz has one**.

It also writes the siz table (every pif) for the retaining-wall workflow and
prints the evacuated polygons over ``config.LARGE_POLYGON_M2`` for review.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/fig_pilot_example_instability_zones.py
"""

import time
from types import SimpleNamespace

import matplotlib as mpl

mpl.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from rasterio import features
from rasterio.transform import Affine

from landloss.hazard.landslide.instability_zones import (
    find_instability_zones,
    gen_siz_table,
    with_walls,
    write_siz_table,
)
from landloss.hazard.landslide.slope_polygons import EVACUATED, build_slope_polygons
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.research.slope_elements import (
    fig_pilot_example_slope_elements as base,
)
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.paths import TEMP_DIR

SIZ_COLOUR = "#eb6834"
NOT_SIZ_COLOUR = "#2a78d6"


def get_zone_run(*, extent):
    """Run the zones and both wall scenarios over the whole pilot."""
    dem, dem_run, water, transform, _, ground_map, group, position = (
        base.get_pilot_inputs(extent=extent, fill_as_soil=True)
    )
    start = time.perf_counter()
    zones = find_instability_zones(
        dem_run, group, transform, categories={"ground_row": position}
    )
    zones_seconds = time.perf_counter() - start
    elements = zones.found.elements
    rows = elements["majority_ground_row"].to_numpy()
    modification = np.where(
        rows >= 0, ground_map["modification"].to_numpy()[np.maximum(rows, 0)], ""
    )
    is_fill = pd.Series(modification == base.FILL_MODIFICATION, index=elements.index)
    thickness = pd.Series(
        np.where(
            is_fill,
            ground_map["fill_thickness_m"].to_numpy()[np.maximum(rows, 0)],
            np.nan,
        ),
        index=elements.index,
    )
    views = {}
    for name, walled in (("walled", True), ("bare", False)):
        start = time.perf_counter()
        found = with_walls(zones.found, walled)
        result = build_slope_polygons(
            found, dem_run, transform, is_fill=is_fill, fill_thickness_m=thickness
        )
        views[name] = SimpleNamespace(
            dem=dem,
            transform=transform,
            ground_map=ground_map,
            found=found,
            result=result,
            seconds=time.perf_counter() - start,
        )
    return zones, zones_seconds, views


def draw_pips(ax, zones, rows, cols, bounds):
    """Pips as dots: orange where the pif is a siz, blue where it is not."""
    labels = zones.pif_labels[rows, cols]
    is_siz = np.zeros(len(zones.sizs) + 1, dtype=bool)
    is_siz[zones.sizs.index.to_numpy()] = zones.sizs["is_siz"].to_numpy()
    pip = labels > 0
    siz = pip & is_siz[labels]
    counts = []
    for mask, colour in ((siz, SIZ_COLOUR), (pip & ~siz, NOT_SIZ_COLOUR)):
        r, c = np.nonzero(mask)
        ax.scatter(
            bounds[0] + c + 0.5,
            bounds[3] - r - 0.5,
            s=base.SEED_DOT_SIZE,
            color=colour,
            lw=0,
            zorder=3,
        )
        counts.append(len(r))
    return counts


def draw_elements(ax, found, rows, cols, transform):
    """Each element as a filled outline of its labelled cells."""
    window = found.labels[rows, cols].astype("int32")
    window_transform = Affine(
        transform.a,
        0,
        transform.c + cols.start * transform.a,
        0,
        transform.e,
        transform.f + rows.start * transform.e,
    )
    count = 0
    for geometry, _ in features.shapes(
        window, mask=window > 0, transform=window_transform
    ):
        for ring in geometry["coordinates"]:
            x, y = zip(*ring, strict=True)
            ax.fill(x, y, color=SIZ_COLOUR, alpha=0.25, lw=0, zorder=3)
            ax.plot(x, y, color=base.INK, lw=0.6, zorder=4)
        count += 1
    return count


def draw_site(site, views, zones, *, intervals, max_contours):
    walled, bare = views["walled"], views["bare"]
    x, y, half = site["x"], site["y"], site["half_size_m"]
    rows, cols, bounds = base.window_slices(walled, x, y, half)
    fig = plt.figure(figsize=(13, 14.6))
    grid = fig.add_gridspec(
        2, 2, left=0.06, right=0.99, top=0.9, bottom=0.06, hspace=0.3, wspace=0.14
    )
    axes = [fig.add_subplot(grid[i, j]) for i in range(2) for j in range(2)]
    for number, ax in enumerate(axes):
        base.draw_base(
            ax,
            walled,
            rows,
            cols,
            bounds,
            intervals=intervals,
            max_contours=max_contours,
            by_material=number == 0,
        )
    n_siz, n_not = draw_pips(axes[0], zones, rows, cols, bounds)
    n_elements = draw_elements(axes[1], walled.found, rows, cols, walled.transform)
    base.draw_polygons(axes[2], walled, base.windowed_result(walled, rows, cols))
    base.draw_polygons(axes[3], bare, base.windowed_result(bare, rows, cols))
    titles = (
        f"1. Pips: {n_siz} in sizs (orange), {n_not} not (blue)",
        f"2. Elements grown from the sizs: {n_elements}",
        f"3. Evacuated zones, every siz walled "
        f"({len(np.unique(base.windowed_result(walled, rows, cols).cells['polygon']))})",
        f"4. Evacuated zones, no siz walled "
        f"({len(np.unique(base.windowed_result(bare, rows, cols).cells['polygon']))})",
    )
    for ax, title in zip(axes, titles, strict=True):
        ax.set_title(title, fontsize=9, loc="left")
    handles = [
        Line2D([], [], marker="o", ls="", color=SIZ_COLOUR, label="pip in a siz"),
        Line2D([], [], marker="o", ls="", color=NOT_SIZ_COLOUR, label="pip, not siz"),
    ]
    handles += base.material_handles(axes[0].materials)
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
        ncol=6,
        fontsize=7,
        frameon=False,
    )
    fig.suptitle(f"Site {site['name']}", fontsize=11, y=0.995)
    base.FIG_DIR.mkdir(parents=True, exist_ok=True)
    name = f"pilot_instability_{site['name']}{extent_suffix(config.PILOT_EXTENT)}.png"
    path = base.FIG_DIR / name
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def flag_large_polygons(view, *, threshold_m2, label, sites):
    """Print the evacuated polygons over the threshold, largest first."""
    transform = view.transform
    cells = view.result.cells
    cells = cells[cells["zone"] == EVACUATED]
    area = cells.groupby("polygon").size() * abs(transform.a * transform.e)
    big = area[area > threshold_m2].sort_values(ascending=False)
    print(f"\n=== {label}: {len(big)} evacuated polygons over {threshold_m2:,.0f} m2")
    if big.empty:
        return
    centre = cells[cells["polygon"].isin(big.index)].groupby("polygon")[["row", "col"]]
    centre = centre.mean().loc[big.index]
    x = transform.c + (centre["col"] + 0.5) * transform.a
    y = transform.f + (centre["row"] + 0.5) * transform.e
    table = pd.DataFrame({"area_m2": big.round(0), "x": x.round(0), "y": y.round(0)})
    table["site"] = [
        next(
            (
                s["name"][:2]
                for s in sites
                if abs(px - s["x"]) <= s["half_size_m"]
                and abs(py - s["y"]) <= s["half_size_m"]
            ),
            "-",
        )
        for px, py in zip(table["x"], table["y"], strict=True)
    ]
    print(table.head(25).to_string())
    print("by site:", table["site"].value_counts().to_dict())


def main(*, extent, sites, contour_intervals_m, max_contours, large_polygon_m2, siz_file):
    zones, zones_seconds, views = get_zone_run(extent=extent)
    sizs = zones.sizs
    transform = views["walled"].transform
    print(
        f"Pips, pifs, sizs and growth over the {extent} pilot in "
        f"{zones_seconds:.1f} s; scenario polygons in "
        f"{views['walled'].seconds:.1f} s (walled) and {views['bare'].seconds:.1f} s "
        f"(bare)"
    )
    print(
        f"{int(zones.pips.mask.sum()):,} pips, {len(sizs):,} pifs, "
        f"{int(sizs['is_siz'].sum()):,} sizs, "
        f"{len(zones.found.elements):,} elements"
    )
    print(sizs.groupby("ground_group")["is_siz"].agg(["size", "sum"]).to_string())
    siz_path = TEMP_DIR / f"{siz_file}{extent_suffix(extent)}.parquet"
    write_siz_table(gen_siz_table(zones, transform, crs=base.CRS), siz_path)
    print(f"Siz table: {siz_path}")
    for name, label in (("walled", "every siz walled"), ("bare", "no siz walled")):
        flag_large_polygons(
            views[name], threshold_m2=large_polygon_m2, label=label, sites=sites
        )
    for site in sites:
        print(
            draw_site(
                site,
                views,
                zones,
                intervals=contour_intervals_m,
                max_contours=max_contours,
            )
        )


if __name__ == "__main__":
    main(
        extent=config.PILOT_EXTENT,
        sites=config.PILOT_SITES,
        contour_intervals_m=config.PILOT_CONTOUR_INTERVALS_M,
        max_contours=config.PILOT_MAX_CONTOURS,
        large_polygon_m2=config.LARGE_POLYGON_M2,
        siz_file=config.PILOT_SIZ_FILE,
    )
