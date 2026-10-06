"""SME test 6: whether slope failures are mostly small.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_6_failure_size.py

Experience says most rock-cut failures are small: slumps or rockfall onto the
land between house and slope. Drawn as the distribution of evacuated area per
damaged claim, from the landslide land damage step, against the medians of the
claim reports for earthquake and rain claims. Settings come from ``config.py``
beside this.
"""

import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.landloss.post_processing.sme_validations import config, sme_data
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage.gen_landslide_land_damage import (
    landslide_land_damage_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-6-failure-size.png"
BINS = np.logspace(0, 3, 31)


def draw(areas, claims_medians):
    """Draw the evacuated area histogram on a log scale, medians marked."""
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(
        np.clip(areas, BINS[0], BINS[-1]),
        bins=BINS,
        color=sme_data.MODEL,
        edgecolor="white",
        linewidth=1,
        label="Model claims",
    )
    ax.set_xscale("log")
    ax.axvline(
        float(np.median(areas)),
        color=sme_data.INK,
        linewidth=1.5,
        label=f"Model median {np.median(areas):.0f} m²",
    )
    for (cause, value), style in zip(claims_medians.items(), ("--", ":")):
        ax.axvline(
            value,
            color=sme_data.INK,
            linewidth=1.5,
            linestyle=style,
            label=f"Claim reports median, {cause}: {value:g} m²",
        )
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="lower left", bbox_to_anchor=(0, 1.0))
    ax.xaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("Evacuated area per damaged claim (m², log scale)", color=sme_data.INK)
    ax.set_ylabel("Claims", color=sme_data.INK)
    sme_data.style_axes(ax, grid_axis="y")
    fig.tight_layout()
    return fig


def main(*, extent, world_id, realisation_id, claims_medians, fig_dir):
    """Draw the figure and print the quantiles it shows."""
    damage = pd.read_parquet(
        landslide_land_damage_path(world_id, realisation_id, extent=extent)
    )
    areas = damage.loc[damage["evacuated_area_m2"] > 0, "evacuated_area_m2"].to_numpy()
    print(f"Claims with evacuated land: {len(areas):,}")
    for q in (0.25, 0.5, 0.75, 0.9):
        print(f"  p{int(q * 100)}: {np.quantile(areas, q):.1f} m2")
    print(f"  mean: {areas.mean():.1f} m2")
    fig = draw(areas, claims_medians)
    sme_data.save(fig, fig_dir, FIG_NAME)
    plt.close(fig)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        claims_medians=config.CLAIMS_EVACUATED_MEDIAN_M2,
        fig_dir=config.FIG_DIR,
    )
