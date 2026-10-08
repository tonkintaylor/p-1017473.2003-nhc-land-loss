"""Landslide step 4: the zones of each wall scenario side by side at the pilot sites.

Reads the zone files this step wrote and draws, for each site in
``config.FIG_SITES``, one map panel per scenario in
``config.FIG_ZONE_SCENARIOS``: the evacuated zones (orange where the element
is walled, a free-face; green where it is not, a bank), the imminent and the
inundated zones, at their true size and shape, over a hillshade, with the
wall units as lines.

Which scenarios are drawn is the figure's mode, set in ``config.py``:

- ``"walled"`` and ``"bare"``, every siz walled and none, are the two
  whole-scenario bounds ``gen_wall_zones.py`` writes. They show what
  the walls change and are never read by the pipeline.
- ``"w000"`` and so on are one exposure world's drawn walls
  (``gen_wall_zones.py``), the zones landslide steps 5 and 6 read;
  there the walled units of that world are drawn solid and the rest dashed.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s4_wall_zones/fig_wall_zones.py

Run ``gen_wall_zones.py`` first, which needs exposure rw step 6's
``gen_wall_units.py`` for a world scenario. The
figures go under ``report/hazard/landslide/wall-zones/fig/``.
"""

import matplotlib as mpl

mpl.use("Agg")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rioxarray
from matplotlib.colors import LightSource
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from landloss.hazard.landslide.slope_elements import BANK, FREE_FACE
from landloss.hazard.landslide.slope_polygons import EVACUATED, IMMINENT, INUNDATED
from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_draws_path,
    wall_units_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import config
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.gen_wall_zones import (
    zones_path,
)
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "wall-zones" / "fig"
DPI = 150

# The colours of the slope elements research figures, so the two read alike.
FREE_FACE_COLOUR = "#eb6834"
BANK_COLOUR = "#1baf7a"
IMMINENT_COLOUR = "#eda100"
INUNDATED_COLOUR = "#2a78d6"
INK = "#0b0b0b"
MUTED = "#898781"
TYPE_COLOUR = {FREE_FACE: FREE_FACE_COLOUR, BANK: BANK_COLOUR}
ZONE_COLOUR = {IMMINENT: IMMINENT_COLOUR, INUNDATED: INUNDATED_COLOUR}

# The bounds' titles; a world scenario is titled by its number.
BOUND_TITLES = {"walled": "every siz walled (bound)", "bare": "no siz walled (bound)"}


def scenario_title(scenario):
    """The panel title of a scenario."""
    if scenario in BOUND_TITLES:
        return BOUND_TITLES[scenario]
    return f"world {int(scenario.lstrip('w'))}, the walls it drew (pipeline)"


def walled_units(scenario, draws):
    """The wall units walled in a world scenario; None for a bound."""
    if scenario in BOUND_TITLES:
        return None
    rows = draws[(draws["world_id"] == int(scenario.lstrip("w"))) & draws["walled"]]
    return set(rows["wall_unit_id"])


def site_bounds(site):
    """``(xmin, ymin, xmax, ymax)`` of a site's window."""
    half = site["half_size_m"]
    return (site["x"] - half, site["y"] - half, site["x"] + half, site["y"] + half)


def hillshade(dem):
    """A hillshade of a 1 m DEM, lit from the north-west."""
    return LightSource(azdeg=315, altdeg=40).hillshade(dem, vert_exag=1.5, dx=1, dy=1)


def polygon_handles():
    """The legend entries of the zones."""
    return [
        Patch(facecolor=FREE_FACE_COLOUR, alpha=0.35, label="Evacuated, walled"),
        Patch(facecolor=BANK_COLOUR, alpha=0.35, label="Evacuated, not walled"),
        Patch(facecolor=IMMINENT_COLOUR, alpha=0.3, label="Imminent"),
        Patch(facecolor=INUNDATED_COLOUR, alpha=0.3, label="Inundated"),
        Line2D([], [], color=INK, lw=0.6, label="Edge of each evacuated polygon"),
    ]


def draw_hillshade(ax, dem, bounds):
    """The hillshade of the DEM under the window."""
    window = dem.rio.clip_box(*bounds)
    values = window.to_numpy().astype(float)
    shade = hillshade(np.where(np.isfinite(values), values, np.nanmin(values)))
    left, bottom, right, top = window.rio.bounds()
    ax.imshow(
        shade, cmap="gray", extent=(left, right, bottom, top), alpha=0.6, zorder=0
    )


def draw_zones(ax, zones):
    """Inundated, then imminent, then evacuated, each true to its cells."""
    for zone, zorder in ((INUNDATED, 1), (IMMINENT, 2), (EVACUATED, 3)):
        rows = zones[zones["zone"] == zone]
        if rows.empty:
            continue
        if zone == EVACUATED:
            colours = rows["element_type"].map(TYPE_COLOUR).fillna(MUTED)
            rows.plot(ax=ax, color=colours.to_list(), alpha=0.35, lw=0, zorder=zorder)
            rows.boundary.plot(ax=ax, color=INK, lw=0.4, alpha=0.8, zorder=zorder)
        else:
            rows.plot(ax=ax, color=ZONE_COLOUR[zone], alpha=0.3, lw=0, zorder=zorder)


def draw_units(ax, units, walled):
    """The wall units: solid where walled in the world, dashed otherwise."""
    if units.empty:
        return
    if walled is None:
        units.plot(ax=ax, color=INK, lw=0.8, zorder=4)
        return
    is_walled = units.index.isin(list(walled))
    if is_walled.any():
        units[is_walled].plot(ax=ax, color=INK, lw=1.2, zorder=4)
    if (~is_walled).any():
        units[~is_walled].plot(ax=ax, color=MUTED, lw=0.8, ls="--", zorder=4)


def draw_site(site, scenarios, zones_by_scenario, units, draws, dem, *, extent):
    """One figure per site, one panel per scenario."""
    bounds = site_bounds(site)
    fig, axes = plt.subplots(
        1, len(scenarios), figsize=(6.2 * len(scenarios), 6.6), squeeze=False
    )
    for ax, scenario in zip(axes[0], scenarios, strict=True):
        zones = zones_by_scenario[scenario].cx[
            bounds[0] : bounds[2], bounds[1] : bounds[3]
        ]
        draw_hillshade(ax, dem, bounds)
        draw_zones(ax, zones)
        draw_units(
            ax,
            units.cx[bounds[0] : bounds[2], bounds[1] : bounds[3]],
            walled_units(scenario, draws),
        )
        n_polygons = zones.loc[zones["zone"] == EVACUATED, "polygon"].nunique()
        area = zones.loc[zones["zone"] == EVACUATED].area.sum()
        ax.set_title(
            f"{scenario_title(scenario)}\n{n_polygons} polygons reach the window, "
            f"{area:,.0f} m2 evacuated",
            fontsize=9,
            loc="left",
        )
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
    handles = [
        *polygon_handles(),
        Line2D([], [], color=INK, lw=1.2, label="Wall unit (walled in the world)"),
        Line2D([], [], color=MUTED, lw=0.8, ls="--", label="Wall unit, not walled"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=4,
        fontsize=7,
        frameon=False,
    )
    fig.suptitle(f"Site {site['name']}", fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"urban_slope_wall_zones_{site['name']}{extent_suffix(extent)}.png"
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def main(*, extent, scenarios, sites):
    """Draw every site for the scenarios given.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        scenarios: The zone files to draw, ``"walled"``, ``"bare"`` or
            ``"wNNN"``.
        sites: The sites, each with ``name``, ``x``, ``y`` and
            ``half_size_m``.

    Raises:
        FileNotFoundError: If a scenario's zone file is not written.
    """
    zones_by_scenario = {}
    for scenario in scenarios:
        path = zones_path(scenario, extent=extent)
        if not path.exists():
            msg = f"{path} not found: run this step's generation scripts first"
            raise FileNotFoundError(msg)
        zones_by_scenario[scenario] = gpd.read_parquet(path)
        print(f"Read {path.name}")
    units = gpd.read_parquet(wall_units_path(extent=extent))
    draws_file = wall_draws_path(extent=extent)
    draws = (
        pd.read_parquet(draws_file)
        if draws_file.exists()
        else pd.DataFrame(columns=["world_id", "wall_unit_id", "walled"])
    )
    with rioxarray.open_rasterio(dem_path(1, extent=extent), masked=True) as raster:
        dem = raster.squeeze("band", drop=True).load()
    for site in sites:
        print(
            draw_site(
                site, scenarios, zones_by_scenario, units, draws, dem, extent=extent
            )
        )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        scenarios=config.FIG_ZONE_SCENARIOS,
        sites=config.FIG_SITES,
    )
