"""SME test 1: the share of hill properties with a retaining wall.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_1_hill_walls.py

Experience expects a third to a half of hill properties to have a wall of some
kind. A property counts as walled when the exposure world's wall population
puts at least one wall on its claim, and as hill when most of its addresses
were classed hill by the land value step. Drawn per suburb, with the expected
band shaded. Settings come from ``config.py`` beside this.
"""

import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.post_processing.sme_validations import config, sme_data

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-1-hill-walls.png"
ALL_LABEL = "All hill properties"


def walled_properties(*, extent, world_id):
    """Return every claim with insured land, its landform and whether it is walled."""
    insured = sme_data.read_insured_land(extent=extent)
    walls = sme_data.read_walls(world_id, extent=extent)
    properties = insured[["claim_id"]].join(
        sme_data.property_landform(extent=extent), on="claim_id"
    )
    properties["walled"] = properties["claim_id"].isin(walls["claim_id"])
    return properties, walls


def shares_by_suburb(hill):
    """Return the walled share and count of hill properties per suburb, then all."""
    by_suburb = hill.groupby("suburb")["walled"].agg(share="mean", properties="size")
    by_suburb = by_suburb.sort_values("share")
    by_suburb.loc[ALL_LABEL] = [hill["walled"].mean(), len(hill)]
    return by_suburb


def draw(shares, expected):
    """Draw one bar per suburb, the whole pilot last, over the expected band."""
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(shares) + 1.4))
    y = np.arange(len(shares))[::-1]
    colours = [
        sme_data.MODEL if name == ALL_LABEL else sme_data.MODEL_LIGHT
        for name in shares.index
    ]
    ax.axvspan(*expected, color=sme_data.EXPECTED_BAND, zorder=0)
    ax.barh(y, shares["share"], height=0.6, color=colours)
    for row, share in zip(y, shares["share"]):
        ax.text(share + 0.01, row, f"{share:.0%}", va="center", fontsize=8, color=sme_data.INK)
    labels = [f"{name} ({int(n):,})" for name, n in shares["properties"].items()]
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share of hill properties with at least one wall", color=sme_data.INK)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    sme_data.style_axes(ax)
    ax.text(
        np.mean(expected),
        len(shares) - 0.35,
        "Experience expects\na third to a half",
        ha="center",
        fontsize=8,
        color=sme_data.INK,
    )
    fig.tight_layout()
    return fig


def main(*, extent, world_id, expected, fig_dir):
    """Draw the figure and print the shares it shows."""
    properties, _ = walled_properties(extent=extent, world_id=world_id)
    hill = properties[properties["landform"] == "hill"]
    shares = shares_by_suburb(hill)
    print(shares.round(3).to_string())
    fig = draw(shares, expected)
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        expected=config.EXPECTED_HILL_WALLED,
        fig_dir=config.FIG_DIR,
    )
