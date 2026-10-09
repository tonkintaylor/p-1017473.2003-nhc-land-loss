"""SME test 2: whether wall heights cluster at the no-consent height.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_2_wall_heights.py

Experience says many walls are built to about 1 to 1.5 m, the height owners
believe needs no consent. Drawn as the distribution of the wall population's
heights, with that band shaded and the median retained height of the walls in
the claim reports marked. Settings come from ``config.py`` beside this.
"""

import sys

import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.post_processing.sme_validations import config, sme_data

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-2-wall-heights.png"
BIN_WIDTH_M = 0.25
MAX_HEIGHT_M = 6.0


def draw(heights, consent_band, claims_median):
    """Draw the height histogram over the consent band, medians marked."""
    fig, ax = plt.subplots(figsize=(8, 4))
    bins = np.arange(0, MAX_HEIGHT_M + BIN_WIDTH_M, BIN_WIDTH_M)
    shown = np.clip(heights, 0, MAX_HEIGHT_M - 1e-9)
    low, high = consent_band
    ax.axvspan(
        low,
        high,
        color=sme_data.EXPECTED_BAND,
        zorder=0,
        label=f"{low:g} to {high:g} m, built without consent",
    )
    ax.hist(
        shown,
        bins=bins,
        color=sme_data.MODEL,
        edgecolor="white",
        linewidth=1.5,
        label="Model walls",
    )
    ax.axvline(
        float(np.median(heights)),
        color=sme_data.INK,
        linewidth=1.5,
        label=f"Model median {np.median(heights):.2f} m",
    )
    ax.axvline(
        claims_median,
        color=sme_data.INK,
        linewidth=1.5,
        linestyle="--",
        label=f"Claim reports median {claims_median:.1f} m",
    )
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.set_xlim(0, MAX_HEIGHT_M)
    ax.set_xlabel(
        f"Wall height (m), last bin {MAX_HEIGHT_M:g} m and over", color=sme_data.INK
    )
    ax.set_ylabel("Walls", color=sme_data.INK)
    sme_data.style_axes(ax, grid_axis="y")
    fig.tight_layout()
    return fig


def main(*, extent, world_id, consent_band, claims_median, fig_dir):
    """Draw the figure and print the shares it shows."""
    heights = sme_data.read_walls(world_id, extent=extent)["height_m"].to_numpy()
    low, high = consent_band
    print(f"Walls: {len(heights):,}")
    print(f"  median {np.median(heights):.2f} m")
    print(f"  under {low:g} m: {np.mean(heights < low):.1%}")
    print(
        f"  {low:g} to {high:g} m: {np.mean((heights >= low) & (heights <= high)):.1%}"
    )
    print(f"  over {high:g} m: {np.mean(heights > high):.1%}")
    fig = draw(heights, consent_band, claims_median)
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        consent_band=config.CONSENT_BAND_M,
        claims_median=config.CLAIMS_WALL_HEIGHT_MEDIAN_M,
        fig_dir=config.FIG_DIR,
    )
