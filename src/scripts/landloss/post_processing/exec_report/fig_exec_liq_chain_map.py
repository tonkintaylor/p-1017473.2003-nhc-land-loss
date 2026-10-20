"""Map the liquefaction chain on a window: groundwater to land damage.

    uv run --frozen python src/scripts/landloss/post_processing/exec_report/fig_exec_liq_chain_map.py

The liquefaction companion to ``fig_exec_chain_map.py``: four panels of one
window, one figure per entry in ``config.LIQ_WINDOWS`` (Porirua's is the chain
map's own 600 by 450 m window, the Hutt ones the valley floors), read left to
right and top to bottom:

1. **Groundwater**: the National Liquefaction Model's median depth to
   groundwater, the input the liquefaction probabilities lean on most.
2. **Minor to moderate**: the probability the land damage is moderate or
   worse, one minus P(None) minus P(Minor) of the hazard step 2 grids. The
   lateral spreading correction moves only the major exceedance, so this is
   the NLM's own P(at least Moderate).
3. **Moderate to major**: the probability the land damage is major or worse,
   the sum of the Major, Severe and Very Severe grids, so after the lateral
   spreading correction step 2 applies.
4. **Land damage**: the state hazard step 3 drew for each cell in one
   realisation.

Panels 2 and 3 carry the near and middle lateral spreading zones step 2 wrote
beside its grids, the ground within 100 m and 100 to 200 m of a free face.

Every hazard layer is read through its step's path function for the extent
the window is read out of, so run liquefaction steps 1 to 3 over that extent
first. The insured land is outlined on windows narrow enough for a parcel to
show. The
groundwater grid is read from the NLM's release tree on T: through
``landloss.io.nlm`` and kept in the local cache after the first run. The
basemap is fetched over the network.
"""

import contextlib

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.patheffects import withStroke
from pyproj import CRS
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.liquefaction.lateral_spreading import FAR_FIELD_M, NEAR_FIELD_M
from landloss.io.area_of_interest import get_area_of_interest
from landloss.io.nlm import nlm_gwd_median_path, nlm_release_path
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    beta_probability_path,
    ls_zones_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.post_processing.exec_report import config
from scripts.landloss.post_processing.exec_report.fig_exec_chain_map import (
    BASEMAP,
    DPI,
    FIG_DIR,
    FIGSIZE,
    FONT_SIZE,
    LD_LOWEST_STATE_SHOWN,
    LD_STATE_COLOURS,
    LD_STATE_LABELS,
    NZTM,
    RULE,
    draw_ld_cells,
)

FIG_NAME = "exec-liq-chain-map{suffix}.png"

# Every panel lays a white veil over the imagery so its grid reads first.
VEIL_ALPHA = 0.35

# The groundwater and probability scales are the National Liquefaction Model's
# own, so a panel here reads against its scenario figures: the colours are
# get_gw_seg_cmap and get_prob_seg_cmap of its common/utils/nlm_colors.py,
# sampled from the same matplotlib ramps, at the alphas its scenario grids
# draw them at (scripts/scenario/reporting/scenario_grid_utils.py).
#
# Depth to groundwater in metres, YlGnBu reversed so shallow water, which is
# what liquefies, is dark. Open at both ends: the first and last colours are
# shallower than 0.25 m and deeper than 10 m.
GWD_BREAKS_M = [0.25, 0.5, 1, 2, 3, 5, 10]
GWD_COLOURS = [
    "#1e2f87",
    "#2256a4",
    "#1d89bc",
    "#3db1c3",
    "#7acbbb",
    "#c4e7b4",
    "#ecf7b1",
    "#ffffd9",
]
GWD_ALPHA = 0.8

# One probability scale for panels 2 and 3, so they read against each other:
# plasma, closed at 0 and 100%, with fine bands at the low end where most
# ground sits.
PROBABILITY_BREAKS = [
    0,
    0.005,
    0.01,
    0.02,
    0.035,
    0.05,
    0.1,
    0.2,
    0.35,
    0.5,
    0.85,
    0.95,
    1,
]
PROBABILITY_COLOURS = [
    "#0c0786",
    "#3d039b",
    "#6200a6",
    "#8506a6",
    "#a51f97",
    "#bf3982",
    "#d5536d",
    "#e76e5a",
    "#f58d45",
    "#fcad31",
    "#fbd124",
    "#eff821",
]
PROBABILITY_ALPHA = 1.0

# The lateral spreading zones as outlines, so the probability beneath shows
# through: the near zone solid, the middle zone dashed, both cased in white.
ZONE_COLOUR = "#1a1a19"
NEAR_WIDTH = 0.9
MIDDLE_WIDTH = 0.7
MIDDLE_STYLE = (0, (3, 1.5))
ZONE_CASING = [withStroke(linewidth=1.8, foreground="white")]
NEAR_HATCH = "////"
NEAR_HATCH_ALPHA = 0.3

INSURED_LAND_COLOUR = "#fcfcfb"
INSURED_LAND_WIDTH = 0.3
# Wider than this, a parcel is a few pixels across and the outlines merge into
# a white smear, so they are left off.
INSURED_LAND_MAX_WINDOW_M = 2000.0

# The map rows take their height from the window's shape at the chain map's
# panel width; the key strips beneath them keep theirs.
KEY_HEIGHT_IN = 0.9
TITLE_HEIGHT_IN = 0.5

# The places' names for the figure title, by the figure's name in
# config.LIQ_WINDOWS.
PLACE_NAMES = {
    "porirua": "Porirua",
    "lower-hutt-main-valley": "Lower Hutt main valley",
    "upper-hutt-main-valley": "Upper Hutt main valley",
    "lower-hutt-alicetown": "Alicetown, Lower Hutt",
    "upper-hutt-trentham": "Trentham, Upper Hutt",
}


# ----------------------------------------------------------------------------
# Reading
# ----------------------------------------------------------------------------


def resolve_window(window):
    """A window as an NZTM box, from a box or the name of an extent."""
    if isinstance(window, str):
        return get_area_of_interest(window).bbox(NZTM)
    return window


def shows_parcels(window):
    """Whether the window is narrow enough to outline the insured land."""
    minx, _, maxx, _ = window
    return maxx - minx <= INSURED_LAND_MAX_WINDOW_M


def clip(frame, window):
    """The rows of a frame that touch the window, cut to it, in NZTM."""
    return gpd.clip(frame.to_crs(NZTM), box(*window))


def read_raster(path, window):
    """One band of a raster over the window, in NZTM, with its plotting extent.

    Read a cell beyond the window on every side, so the cells snapped to the
    grid still reach the frame; the axes clip them to it. A grid in another
    projection, as the NLM's national grids may be, is warped to NZTM by
    nearest neighbour on the way in, so no cell takes a value it did not hold.
    """
    margin = 100.0
    minx, miny, maxx, maxy = window
    minx, miny, maxx, maxy = minx - margin, miny - margin, maxx + margin, maxy + margin
    with contextlib.ExitStack() as stack:
        source = stack.enter_context(rasterio.open(path))
        if CRS(source.crs) != CRS(NZTM):
            source = stack.enter_context(
                WarpedVRT(source, crs=NZTM, resampling=Resampling.nearest)
            )
        raster_window = from_bounds(minx, miny, maxx, maxy, source.transform)
        raster_window = raster_window.round_offsets().round_lengths()
        values = source.read(1, window=raster_window, boundless=True, masked=True)
        bounds = rasterio.windows.bounds(raster_window, source.transform)
        transform = source.window_transform(raster_window)
    left, bottom, right, top = bounds
    return values.astype(float).filled(np.nan), (left, right, bottom, top), transform


def read_probability(states, *, window, extent):
    """The sum of some of step 2's state probability grids, over the window."""
    grids = [
        read_raster(beta_probability_path(state, extent=extent), window)
        for state in states
    ]
    _, plot_extent, transform = grids[0]
    return sum(values for values, _, _ in grids), plot_extent, transform


def read_layers(*, window, extent, realisation_id):
    """Read every layer the four panels draw, over the window."""
    none_or_minor, plot_extent, transform = read_probability(
        ["None", "Minor"], window=window, extent=extent
    )
    return {
        "gwd": read_raster(nlm_release_path(nlm_gwd_median_path()), window),
        "moderate_or_worse": (1.0 - none_or_minor, plot_extent, transform),
        "major_or_worse": read_probability(
            ["Major", "Severe", "Very Severe"], window=window, extent=extent
        ),
        "ld_state": read_raster(ld_state_path(realisation_id, extent=extent), window),
        "zones": clip(gpd.read_file(ls_zones_path(extent=extent)), window),
        "land": clip(
            gpd.read_parquet(insured_land_path(extent=extent), columns=["geometry"]),
            window,
        )
        if shows_parcels(window)
        else None,
    }


# ----------------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------------


def start_panel(ax, window):
    """Hold a panel to the window over the veiled imagery."""
    style_basemap_ax(
        ax,
        gpd.GeoDataFrame(geometry=[box(*window)], crs=NZTM),
        basemap=BASEMAP,
        arrow_kwargs={"scale": 0.16, "label_size": 5},
        scalebar_kwargs={"font_size": 5},
    )
    minx, miny, maxx, maxy = window
    ax.add_patch(
        Rectangle(
            (minx, miny),
            maxx - minx,
            maxy - miny,
            facecolor="white",
            alpha=VEIL_ALPHA,
            linewidth=0,
            zorder=0.5,
        )
    )


def draw_land(ax, land):
    """The insured land's outlines, thin, for the reader to find their street."""
    if land is not None and not land.empty:
        land.boundary.plot(
            ax=ax, color=INSURED_LAND_COLOUR, linewidth=INSURED_LAND_WIDTH, zorder=3
        )


def gwd_scale():
    """The groundwater depth scale, open at both ends."""
    cmap = ListedColormap(GWD_COLOURS)
    return cmap, BoundaryNorm(GWD_BREAKS_M, cmap.N, extend="both")


def probability_scale():
    """The probability scale, closed at 0 and 100%."""
    cmap = ListedColormap(PROBABILITY_COLOURS)
    return cmap, BoundaryNorm(PROBABILITY_BREAKS, cmap.N, clip=True)


def percent(value):
    """A probability as a percentage, with no trailing ``.0``."""
    return f"{value:.1%}".replace(".0%", "%")


def draw_grid(ax, grid, scale, alpha):
    """A grid drawn on its cells in the scale's banded colours."""
    values, extent, _ = grid
    cmap, norm = scale
    ax.imshow(
        np.ma.masked_invalid(values),
        extent=extent,
        cmap=cmap,
        norm=norm,
        alpha=alpha,
        interpolation="nearest",
        zorder=1,
    )


def draw_zones(ax, zones):
    """The near and middle lateral spreading zones as outlines."""
    styles = {
        "middle": {"linewidth": MIDDLE_WIDTH, "linestyle": MIDDLE_STYLE},
        "near": {"linewidth": NEAR_WIDTH, "linestyle": "-"},
    }
    # The near zone also takes a faint hatch, so it reads which side of its
    # line it lies.
    near = zones[(zones["zone_name"] == "near") & ~zones.is_empty]
    if not near.empty:
        near.plot(
            ax=ax,
            facecolor="none",
            edgecolor=ZONE_COLOUR,
            hatch=NEAR_HATCH,
            linewidth=0,
            alpha=NEAR_HATCH_ALPHA,
            zorder=4,
        )
    # Middle first: its inner edge is the near zone's outer one, drawn solid
    # over it.
    for name, style in styles.items():
        rows = zones[(zones["zone_name"] == name) & ~zones.is_empty]
        for line in rows.boundary:
            for part in getattr(line, "geoms", [line]):
                ax.plot(
                    *part.xy,
                    color=ZONE_COLOUR,
                    path_effects=ZONE_CASING,
                    zorder=5,
                    **style,
                )


def zone_handles():
    """The key entries for the lateral spreading zones."""
    return [
        Patch(
            facecolor="none",
            edgecolor=ZONE_COLOUR,
            hatch=NEAR_HATCH,
            linewidth=NEAR_WIDTH,
            label=f"Lateral spreading near zone, within {NEAR_FIELD_M:.0f} m of a free face",
        ),
        Line2D(
            [],
            [],
            color=ZONE_COLOUR,
            linewidth=MIDDLE_WIDTH,
            linestyle=MIDDLE_STYLE,
            label=f"Middle zone, {NEAR_FIELD_M:.0f} to {FAR_FIELD_M:.0f} m",
        ),
    ]


def draw_scale_key(fig, ax, scale, *, alpha, title, ticklabels, handles=(), note=None):
    """A grid's banded scale as a bar, with the panel's other key entries."""
    cmap, norm = scale
    ax.axis("off")
    bar = ax.inset_axes((0.02, 0.72, 0.94, 0.1))
    colourbar = fig.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap),
        cax=bar,
        orientation="horizontal",
        spacing="uniform",
    )
    colourbar.set_ticks(norm.boundaries)
    colourbar.set_ticklabels(ticklabels)
    colourbar.ax.tick_params(labelsize=FONT_SIZE - 2, length=2, pad=1)
    colourbar.outline.set_linewidth(0.4)
    colourbar.solids.set_alpha(alpha)
    ax.text(0.02, 1.0, title, fontsize=FONT_SIZE, va="top", transform=ax.transAxes)
    if handles:
        ax.legend(
            handles=list(handles),
            loc="upper left",
            bbox_to_anchor=(0.0, 0.5),
            frameon=False,
            fontsize=FONT_SIZE - 1,
            handlelength=2.2,
            borderaxespad=0.2,
        )
    if note:
        ax.text(
            0.02,
            0.5,
            note,
            fontsize=FONT_SIZE - 1,
            va="top",
            transform=ax.transAxes,
            linespacing=1.3,
        )


def draw_state_key(ax, states):
    """The land damage states drawn, as a key."""
    ax.axis("off")
    ax.legend(
        handles=[
            Patch(
                facecolor=LD_STATE_COLOURS[state],
                alpha=0.7,
                label=f"{state}  {LD_STATE_LABELS[state]}",
            )
            for state in states
        ],
        loc="upper left",
        ncol=2,
        frameon=False,
        fontsize=FONT_SIZE - 1,
        handlelength=2.2,
        borderaxespad=0.2,
        title=f"Land damage state ({LD_STATE_LABELS[1].lower()} is left unshaded)",
        title_fontsize=FONT_SIZE,
        alignment="left",
    )


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------


def describe(layers, *, window, extent):
    """Print the window's numbers for the caption."""
    print(RULE)
    print(f"Window {window}, extent {extent}, r{config.REALISATION_ID:03d}")
    gwd = layers["gwd"][0]
    print(
        f"  Median depth to groundwater {np.nanmin(gwd):.1f} to {np.nanmax(gwd):.1f} m, "
        f"median {np.nanmedian(gwd):.1f} m"
    )
    for key, label in (
        ("moderate_or_worse", "P(moderate or worse)"),
        ("major_or_worse", "P(major or worse)"),
    ):
        values = layers[key][0]
        print(
            f"  {label:<21} mean {np.nanmean(values):.2f}, "
            f"range {np.nanmin(values):.2f} to {np.nanmax(values):.2f}"
        )
    states = layers["ld_state"][0]
    states = states[np.isfinite(states)].astype(int)
    counts = {int(state): int((states == state).sum()) for state in np.unique(states)}
    print(f"  Land damage state cells: {counts}")
    area = box(*window).area
    for name in ("near", "middle"):
        share = layers["zones"].loc[layers["zones"]["zone_name"] == name].area.sum()
        print(
            f"  Lateral spreading {name} zone covers {share / area:.0%} of the window"
        )


def plot_liq_chain_map(layers, *, window, place):
    """Draw the four panel figure for one window and return it."""
    plt.rcParams.update({"font.size": FONT_SIZE})
    minx, miny, maxx, maxy = window
    map_height = FIGSIZE[0] * 0.98 / 2 * (maxy - miny) / (maxx - minx)
    fig_height = 2 * (map_height + KEY_HEIGHT_IN) / 0.86
    fig = plt.figure(figsize=(FIGSIZE[0], fig_height))
    grid = fig.add_gridspec(
        4,
        2,
        height_ratios=[map_height, KEY_HEIGHT_IN, map_height, KEY_HEIGHT_IN],
        hspace=0.06,
        wspace=0.06,
        left=0.01,
        right=0.99,
        # Room for the title above the panel titles, the same on every figure
        # whatever its height.
        top=1 - TITLE_HEIGHT_IN / fig_height,
        bottom=0.04,
    )
    panels = [
        ("1  Groundwater", "Median depth to groundwater", grid[0, 0], grid[1, 0]),
        (
            "2  Minor to moderate",
            "Probability of moderate or worse",
            grid[0, 1],
            grid[1, 1],
        ),
        (
            "3  Moderate to major",
            "Probability of major or worse",
            grid[2, 0],
            grid[3, 0],
        ),
        ("4  Land damage", "State drawn for one earthquake", grid[2, 1], grid[3, 1]),
    ]
    axes = [
        (fig.add_subplot(map_cell), fig.add_subplot(key_cell))
        for *_, map_cell, key_cell in panels
    ]
    for (title, subtitle, *_), (ax, _) in zip(panels, axes, strict=True):
        start_panel(ax, window)
        ax.set_title(
            f"$\\bf{{{title.replace(' ', '~')}}}$   {subtitle}",
            loc="left",
            fontsize=FONT_SIZE + 1,
            pad=3,
        )
        draw_land(ax, layers["land"])
    fig.suptitle(
        f"Liquefaction, {place}", x=0.01, ha="left", fontsize=FONT_SIZE + 3, y=0.99
    )

    draw_grid(axes[0][0], layers["gwd"], gwd_scale(), GWD_ALPHA)
    draw_scale_key(
        fig,
        axes[0][1],
        gwd_scale(),
        alpha=GWD_ALPHA,
        title="Median depth to groundwater, m (National Liquefaction Model)",
        ticklabels=[f"{value:g}" for value in GWD_BREAKS_M],
        note="Shallow groundwater is what liquefies."
        + ("\nThin white lines are the insured land." if shows_parcels(window) else ""),
    )

    for (ax, key_ax), key, title in (
        (axes[1], "moderate_or_worse", "Probability of moderate land damage or worse"),
        (axes[2], "major_or_worse", "Probability of major land damage or worse"),
    ):
        draw_grid(ax, layers[key], probability_scale(), PROBABILITY_ALPHA)
        draw_zones(ax, layers["zones"])
        draw_scale_key(
            fig,
            key_ax,
            probability_scale(),
            alpha=PROBABILITY_ALPHA,
            title=title,
            ticklabels=[percent(value) for value in PROBABILITY_BREAKS],
            handles=zone_handles() if not layers["zones"].empty else (),
            note=None
            if not layers["zones"].empty
            else "No lateral spreading zone reaches this window.",
        )

    states = draw_ld_cells(axes[3][0], layers["ld_state"])
    draw_state_key(
        axes[3][1], [state for state in states if state >= LD_LOWEST_STATE_SHOWN]
    )

    fig.text(
        axes[2][0].get_position().x0,
        0.01,
        f"The {config.RETURN_PERIOD_YR:,}-year liquefaction scenario; panel 4 is one "
        f"modelled earthquake (realisation {config.REALISATION_ID}). Panel 3 includes "
        "the lateral spreading correction, which raises the major probability near\n"
        "free faces and lowers it beyond them. Groundwater and land damage "
        "probabilities are from the National Liquefaction Model at 100 m grid. "
        "Imagery: Esri World Imagery.",
        fontsize=FONT_SIZE - 1.5,
        color="#52514e",
        va="bottom",
    )
    return fig


def main(*, windows, realisation_id):
    """Read the layers, draw the figure and write it, for each window.

    Args:
        windows: By figure name, (the extent whose outputs are read, the
            window drawn as an NZTM box or an extent's name).
        realisation_id: The realisation whose land damage states are drawn.
    """
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for name, (extent, window_spec) in windows.items():
        window = resolve_window(window_spec)
        layers = read_layers(
            window=window, extent=extent, realisation_id=realisation_id
        )
        describe(layers, window=window, extent=extent)
        fig = plot_liq_chain_map(layers, window=window, place=PLACE_NAMES[name])
        out = FIG_DIR / FIG_NAME.format(suffix=f"-{name}")
        fig.savefig(out, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {out}")


if __name__ == "__main__":
    main(windows=config.LIQ_WINDOWS, realisation_id=config.REALISATION_ID)
