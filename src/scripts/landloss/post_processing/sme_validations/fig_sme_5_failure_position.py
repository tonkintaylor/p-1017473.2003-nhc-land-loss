"""SME test 5: whether slope failures come from cuts behind the house.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_5_failure_position.py

Experience says most land claims come from cuts at the back of a house rather
than fills at the front. Each failure's evacuated land that reaches a claim's
insured land is placed against that claim's dwelling: behind when its ground is
higher than the dwelling's, in front when lower, by more than
``config.LEVEL_TOLERANCE_M``, and level otherwise. The failures' own wall state,
cut wall or fill wall, is printed as a cross-check. Settings come from
``config.py`` beside this.
"""

import sys

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from landloss.common.utils.terrain import sample_at_points
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.post_processing.sme_validations import config, sme_data

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-5-failure-position.png"
POSITIONS = ("Behind (above)", "Level", "In front (below)")


def failure_positions(failures, insured, dwelling_z, *, extent, tolerance_m):
    """Return each failure-and-claim pair with its position against the dwelling."""
    pairs = gpd.sjoin(
        failures[["landslide_id", "wall_state", "geometry"]],
        insured[["claim_id", "geometry"]],
        predicate="intersects",
    )
    pairs = pairs[pairs["claim_id"].isin(dwelling_z.index)].copy()
    ground = sample_at_points(
        dem_path(1, extent=extent), pairs.geometry.representative_point()
    )
    rise = ground.to_numpy() - pairs["claim_id"].map(dwelling_z).to_numpy()
    pairs["position"] = np.select(
        [rise > tolerance_m, rise < -tolerance_m],
        [POSITIONS[0], POSITIONS[2]],
        POSITIONS[1],
    )
    return pairs


def draw(shares, count):
    """Draw one bar split into behind, level and in front."""
    fig, ax = plt.subplots(figsize=(8, 1.9))
    colours = [sme_data.MODEL, sme_data.EXPECTED_BAND, sme_data.MODEL_LIGHT]
    left = 0.0
    for position, colour in zip(POSITIONS, colours, strict=False):
        share = shares[position]
        ax.barh(
            0,
            share,
            left=left,
            height=0.5,
            color=colour,
            edgecolor="white",
            linewidth=1.5,
        )
        ink = "white" if position != "Level" else sme_data.INK
        ax.text(
            left + share / 2,
            0,
            f"{position}\n{share:.0%}",
            ha="center",
            va="center",
            fontsize=8,
            color=ink,
        )
        left += share
    ax.set_title(
        "Experience expects most failures behind the house",
        fontsize=9,
        color=sme_data.INK,
        loc="left",
    )
    ax.set_yticks([0], [f"Failures reaching\ninsured land ({count:,})"])
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.4, 0.4)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    sme_data.style_axes(ax)
    fig.tight_layout()
    return fig


def main(*, extent, world_id, realisation_id, tolerance_m, fig_dir):
    """Draw the figure and print the shares it shows."""
    insured = sme_data.read_insured_land(extent=extent)
    failures = sme_data.read_failures(world_id, realisation_id, extent=extent)
    dwelling_z = sme_data.dwelling_elevations(insured, extent=extent)
    pairs = failure_positions(
        failures, insured, dwelling_z, extent=extent, tolerance_m=tolerance_m
    )
    shares = (
        pairs["position"].value_counts(normalize=True).reindex(POSITIONS, fill_value=0)
    )
    print(f"Failures reaching insured land: {len(pairs):,} failure-claim pairs")
    print(shares.round(3).to_string())
    print("Cross-check, all evacuated failures by wall state:")
    print(failures["wall_state"].value_counts().to_string())
    fig = draw(shares, len(pairs))
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        tolerance_m=config.LEVEL_TOLERANCE_M,
        fig_dir=config.FIG_DIR,
    )
