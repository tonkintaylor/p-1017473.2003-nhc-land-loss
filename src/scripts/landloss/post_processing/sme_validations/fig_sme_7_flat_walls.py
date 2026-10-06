"""SME test 7: whether walls on flat land are few and low.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_7_flat_walls.py

Experience says walls on flat land, such as the lower Hutt Valley, are few, and
those there are low. Drawn as the share of flat and of hill properties with a
wall, and the heights of the walls on each, with flat and hill as test 1 reads
them. The wall population's own ``is_flatland`` flag, from the NLM flatland, is
printed beside it. Settings come from ``config.py`` beside this.
"""

import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.post_processing.sme_validations import config, sme_data
from scripts.landloss.post_processing.sme_validations.fig_sme_1_hill_walls import (
    walled_properties,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-7-flat-walls.png"
LANDFORMS = ("flat", "hill")


def draw(shares, counts, heights):
    """Draw the walled share per landform beside the wall heights on each."""
    fig, (share_ax, height_ax) = plt.subplots(
        1, 2, figsize=(9, 3), width_ratios=(1, 1.4)
    )
    y = np.arange(len(LANDFORMS))[::-1]
    colours = [sme_data.MODEL_LIGHT, sme_data.MODEL]
    share_ax.barh(y, [shares[f] for f in LANDFORMS], height=0.55, color=colours)
    for row, landform in zip(y, LANDFORMS, strict=False):
        share_ax.text(
            shares[landform] + 0.02,
            row,
            f"{shares[landform]:.0%}",
            va="center",
            fontsize=8,
            color=sme_data.INK,
        )
    share_ax.set_yticks(y, [f"{f.capitalize()} ({counts[f]:,})" for f in LANDFORMS])
    share_ax.set_xlim(0, 1)
    share_ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    share_ax.set_xlabel("Properties with a wall", color=sme_data.INK)
    share_ax.tick_params(axis="y", length=0)
    share_ax.spines["left"].set_visible(False)
    sme_data.style_axes(share_ax)

    box = height_ax.boxplot(
        [heights[f] for f in LANDFORMS],
        orientation="horizontal",
        positions=y,
        widths=0.5,
        showfliers=False,
        patch_artist=True,
        medianprops={"color": sme_data.INK, "linewidth": 1.5},
    )
    for patch, colour in zip(box["boxes"], colours, strict=False):
        patch.set_facecolor(colour)
        patch.set_edgecolor(sme_data.INK)
    height_ax.set_yticks(
        y, [f"{f.capitalize()} ({len(heights[f]):,} walls)" for f in LANDFORMS]
    )
    height_ax.set_xlabel("Wall height (m), box p25 to p75", color=sme_data.INK)
    height_ax.tick_params(axis="y", length=0)
    height_ax.spines["left"].set_visible(False)
    sme_data.style_axes(height_ax)
    fig.tight_layout()
    return fig


def main(*, extent, world_id, fig_dir):
    """Draw the figure and print the shares it shows."""
    properties, walls = walled_properties(extent=extent, world_id=world_id)
    walls = walls.join(properties.set_index("claim_id")["landform"], on="claim_id")
    shares = properties.groupby("landform")["walled"].mean()
    counts = properties["landform"].value_counts()
    heights = {
        f: walls.loc[walls["landform"] == f, "height_m"].to_numpy() for f in LANDFORMS
    }
    for landform in LANDFORMS:
        print(
            f"{landform}: {shares[landform]:.1%} of {counts[landform]:,} properties walled, "
            f"{len(heights[landform]):,} walls, median height {np.median(heights[landform]):.2f} m"
        )
    print(
        f"Walls the population flags as on NLM flatland: {int(walls['is_flatland'].sum()):,} of {len(walls):,}"
    )
    fig = draw(shares, counts, heights)
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(extent=config.EXTENT, world_id=config.WORLD_ID, fig_dir=config.FIG_DIR)
