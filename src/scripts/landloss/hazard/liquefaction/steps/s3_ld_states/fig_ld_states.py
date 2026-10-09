"""Map one realisation of land damage states, and check its shares against the input.

Reads the raster ``gen_liq_ld_states.py`` writes and produces the figure that
realisation gets checked by eye against:

    uv run --frozen python src/scripts/landloss/hazard/liquefaction/steps/s3_ld_states/fig_ld_states.py

It reads ``config.py`` beside it, the same file the draw reads, and asks
``gen_liq_ld_states.ld_state_path`` where that run's output went -- so the figure
cannot end up drawing a different extent, or a different realisation, from the
one last run.

Two panels, each answering a question the run output cannot.

- **Where.** The states over the extent. What this panel is for is the pattern:
  the worse states should follow the flat, low ground the National Liquefaction
  Model puts its probability on, and the salt-and-pepper texture across it is
  the independent per-cell draw, visible rather than described.
- **Shares.** The realised share of each state beside the mean probability it
  was drawn from, on a log axis because the six shares span an order of
  magnitude. The two bars of a pair should be close to level; a pair that is
  plainly not is the draw putting a band boundary in the wrong place, and it is
  easier to see here than in the columns the run prints.

Needs network access for the basemap tiles. The figure goes under
``report/hazard/liquefaction/ld-states/fig/``, which is gitignored -- the script
is the record of how it was made, not the PNG.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rioxarray
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from shapely.geometry import box

from landloss.common.utils.plot import style_basemap_ax
from landloss.hazard.liquefaction.land_damage import LD_STATES
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states import config
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
    read_probabilities,
)
from scripts.landloss.paths import REPORT_DIR

# Mirrors the step's own module path and then names the topic, so a figure says
# which step drew it without the file name having to.
FIG_DIR = REPORT_DIR / "hazard" / "liquefaction" / "ld-states" / "fig"
DPI = 200

# One sequence from pale to dark across the six states, because the scale is
# ordered: a reader should be able to see severity without reading the legend.
# Near-white for None, so the basemap shows through the ground that is fine.
COLOURS = {
    "None": "#f7f7f7",
    "Minor": "#fee391",
    "Moderate": "#fec44f",
    "Major": "#fe9929",
    "Severe": "#cc4c02",
    "Very Severe": "#7f2704",
}

# Enough to read the basemap's roads and coastline through the states, which is
# how the pattern gets judged against the ground it sits on.
FILL_ALPHA = 0.75

RULE = "-" * 72


def state_colourmap():
    """Return the colourmap and the norm that put state 1 to 6 on the six colours.

    Returns:
        ``(cmap, norm)``, ready to pass to ``imshow``. The boundaries sit at the
        half integers so each state gets exactly one colour rather than a slice
        of a continuous ramp.
    """
    cmap = ListedColormap([COLOURS[state] for state in LD_STATES])
    boundaries = np.arange(0.5, len(LD_STATES) + 1.5)
    return cmap, BoundaryNorm(boundaries, cmap.N)


def draw_map(ax, states, *, title):
    """Draw the state raster over a basemap.

    Args:
        ax: The map axes to draw on.
        states: The ``ld_state`` raster, carrying a projection.
        title: The panel title.
    """
    # Sorted north to south so that origin="upper" is true of the array,
    # whichever way round the file stored its rows.
    ordered = states.sortby("y", ascending=False)
    west, south, east, north = (float(value) for value in states.rio.bounds())
    cmap, norm = state_colourmap()

    ax.imshow(
        np.ma.masked_invalid(ordered.to_numpy()),
        extent=(west, east, south, north),
        origin="upper",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
        alpha=FILL_ALPHA,
        # The basemap goes on at zorder 0, and an image would otherwise sit
        # there with it.
        zorder=2,
    )

    extent = gpd.GeoDataFrame(
        geometry=[box(west, south, east, north)], crs=states.rio.crs
    )
    style_basemap_ax(
        ax,
        extent,
        arrow_kwargs={"scale": 0.2, "label_size": 7},
        scalebar_kwargs={"font_size": 7},
    )
    ax.set_title(title, fontsize=9)


def draw_shares(ax, probabilities, states):
    """Plot the realised share of each state beside the probability it came from."""
    values = states.to_numpy()
    total = int(np.isfinite(values).sum())

    realised = [
        int((values == index).sum()) / total for index in range(1, len(LD_STATES) + 1)
    ]
    expected = [
        float(np.nanmean(probabilities[state].to_numpy())) for state in LD_STATES
    ]

    positions = np.arange(len(LD_STATES))
    width = 0.38
    ax.bar(
        positions - width / 2,
        expected,
        width,
        color="#9e9e9e",
        label="mean probability",
    )
    ax.bar(
        positions + width / 2,
        realised,
        width,
        color=[COLOURS[state] for state in LD_STATES],
        edgecolor="#4d4d4d",
        linewidth=0.4,
        label="realised share",
    )

    ax.set_xticks(positions)
    ax.set_xticklabels(LD_STATES, fontsize=7, rotation=30, ha="right")
    ax.set_ylabel("Share of cells", fontsize=8)
    ax.set_yscale("log")
    ax.set_title("Shares — each pair should be level", fontsize=9)
    ax.tick_params(labelsize=7)
    ax.grid(visible=True, axis="y", linewidth=0.3, alpha=0.4)
    ax.legend(fontsize=7, frameon=False)


def build_figure(probabilities, states, *, realisation_id):
    """Assemble the two panels."""
    fig = plt.figure(figsize=(11, 5.5))
    grid = fig.add_gridspec(1, 2, width_ratios=[1.4, 1.0], wspace=0.26)

    ax_map = fig.add_subplot(grid[0, 0])
    draw_map(ax_map, states, title=f"Land damage state — realisation {realisation_id}")

    ax_shares = fig.add_subplot(grid[0, 1])
    draw_shares(ax_shares, probabilities, states)

    handles = [
        Patch(facecolor=COLOURS[state], edgecolor="none", label=state)
        for state in LD_STATES
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(LD_STATES),
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(bottom=0.18)
    return fig


def main(*, extent, realisation_ids):
    """Draw each realisation the state step wrote for this extent.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        realisation_ids: The modelled earthquakes to draw, one figure each.
    """
    probabilities = read_probabilities(extent=extent)

    for realisation_id in realisation_ids:
        raster_path = ld_state_path(realisation_id, extent=extent)
        print(f"Reading the states from {raster_path} ...")
        with rioxarray.open_rasterio(raster_path, masked=True) as opened:
            states = opened.squeeze(drop=True).load()

        fig = build_figure(probabilities, states, realisation_id=realisation_id)
        figure_path = FIG_DIR / f"{raster_path.stem}.png"
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(figure_path, dpi=DPI, bbox_inches="tight")
        plt.close(fig)

        print(RULE)
        print(f"Wrote {figure_path}")


if __name__ == "__main__":
    main(extent=config.EXTENT, realisation_ids=config.REALISATION_IDS)
