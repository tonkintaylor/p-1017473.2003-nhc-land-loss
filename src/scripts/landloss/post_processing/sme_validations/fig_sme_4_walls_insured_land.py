"""SME test 4: whether walls support insured land.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_4_walls_insured_land.py

Experience says sections are small, so a wall somewhere on a property quite
likely supports insured land. A wall counts as supporting it when its line
meets its own claim's insured land, within ``config.TOUCH_TOLERANCE_M``: the
ground it holds then lies on or against that land. Drawn as the share of walls,
and of walled properties, that do. Settings come from ``config.py`` beside this.
"""

import sys

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.post_processing.sme_validations import config, sme_data

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-4-walls-insured-land.png"


def wall_meets_insured(walls, insured, tolerance_m):
    """Return, per wall, whether it comes within tolerance of its claim's insured land."""
    land = insured.set_index("claim_id").geometry
    own_land = gpd.GeoSeries(walls["claim_id"].map(land), crs=insured.crs)
    distance = walls.geometry.distance(own_land, align=False)
    return distance.le(tolerance_m).to_numpy()


def draw(shares):
    """Draw one bar per measure, split into meeting and not meeting the land."""
    fig, ax = plt.subplots(figsize=(8, 2.2))
    y = np.arange(len(shares))[::-1]
    ax.barh(
        y,
        shares.values(),
        height=0.55,
        color=sme_data.MODEL,
        edgecolor="white",
        linewidth=1.5,
    )
    ax.barh(
        y,
        [1 - s for s in shares.values()],
        left=list(shares.values()),
        height=0.55,
        color=sme_data.EXPECTED_BAND,
        edgecolor="white",
        linewidth=1.5,
    )
    for row, share in zip(y, shares.values(), strict=False):
        ax.text(
            share / 2,
            row,
            f"{share:.0%}",
            ha="center",
            va="center",
            color="white",
            fontsize=9,
        )
    ax.set_yticks(y, list(shares))
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share meeting the claim's insured land", color=sme_data.INK)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    sme_data.style_axes(ax)
    fig.tight_layout()
    return fig


def main(*, extent, world_id, tolerance_m, fig_dir):
    """Draw the figure and print the shares it shows."""
    insured = sme_data.read_insured_land(extent=extent)
    walls = sme_data.read_walls(world_id, extent=extent)
    walls["meets"] = wall_meets_insured(walls, insured, tolerance_m)
    by_property = walls.groupby("claim_id")["meets"].any()
    shares = {
        f"Walls ({len(walls):,})": float(walls["meets"].mean()),
        f"Walled properties, any wall ({len(by_property):,})": float(
            by_property.mean()
        ),
    }
    for label, share in shares.items():
        print(f"{label}: {share:.1%} meet the insured land")
    fig = draw(shares)
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        tolerance_m=config.TOUCH_TOLERANCE_M,
        fig_dir=config.FIG_DIR,
    )
