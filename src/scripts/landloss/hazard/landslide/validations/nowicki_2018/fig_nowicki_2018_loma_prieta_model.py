"""Check our Nowicki Jessee equations against the USGS's run, on the USGS inputs.

Runs :func:`landloss.hazard.landslide.models.nowicki_2018.run` (operational
variant) on the USGS ``groundfailure`` package's own prepared Loma Prieta
inputs and ShakeMap, and compares the coverage and its standard deviation with
the package's expected output. Because the inputs are the USGS's, any
difference is in the implementation: the equations, the masks, the
resampling. Prints the agreement and draws the target, our coverage and their
difference side by side.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/nowicki_2018/fig_nowicki_2018_loma_prieta_model.py

Requires the Loma Prieta test data on T: -- run
``static_data_gen/get_usgs_groundfailure_loma_prieta.py`` first. Results are
written up in ``nowicki_2018_loma_prieta_findings.md`` beside this script.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.hazard.landslide.validations.nowicki_2018 import loma_prieta
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "nowicki-2018-validation" / "fig"
FIG_NAME = "loma-prieta-model-against-usgs.png"
DPI = 200

# Coverage agreement counted as a match: the USGS output is rounded to four
# decimal places, so anything within one unit of the last place is the same.
MATCH_TOLERANCE = 1.0e-4


def describe(label, ours, target, mask):
    """Print how closely one of our grids reproduces the USGS's."""
    both = mask & np.isfinite(ours) & np.isfinite(target)
    diff = np.abs(ours - target)[both]
    print(f"{label}")
    print(f"  cells compared            {both.sum():,}")
    print(
        f"  within {MATCH_TOLERANCE:g}              {np.mean(diff <= MATCH_TOLERANCE):.4%}"
    )
    print(f"  largest difference        {diff.max():.6f}")
    print(
        f"  NaN in ours only          {np.sum(mask & np.isnan(ours) & np.isfinite(target)):,}"
    )
    print(
        f"  NaN in the target only    {np.sum(mask & np.isfinite(ours) & np.isnan(target)):,}"
    )


def main():
    """Run the check and draw the figure."""
    target = loma_prieta.get_target()
    target_std = loma_prieta.get_target_std()
    shaking = loma_prieta.get_shaking(target)
    result = loma_prieta.run_operational(loma_prieta.get_usgs_inputs(target), shaking)
    mask = loma_prieta.interior(target)

    describe("Coverage", result.coverage, target.to_numpy(), mask)
    describe(
        "Coverage standard deviation", result.coverage_std, target_std.to_numpy(), mask
    )
    ours_km2 = loma_prieta.landslide_area_km2(result.coverage, target, mask)
    usgs_km2 = loma_prieta.landslide_area_km2(target.to_numpy(), target, mask)
    print(f"Total landslide area: ours {ours_km2:.2f} km2, USGS {usgs_km2:.2f} km2")

    extent = [
        float(target.x.min()),
        float(target.x.max()),
        float(target.y.min()),
        float(target.y.max()),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
    vmax = float(np.nanpercentile(target.to_numpy(), 99.5))
    for ax, data, title in (
        (axes[0], target.to_numpy(), "USGS groundfailure 1.3.2"),
        (axes[1], result.coverage, "Rebuilt equations, USGS inputs"),
    ):
        image = ax.imshow(data, extent=extent, vmin=0, vmax=vmax, cmap="magma_r")
        ax.set_title(title)
    fig.colorbar(image, ax=axes[:2], label="Areal coverage", shrink=0.8)
    diff = np.where(mask, result.coverage - target.to_numpy(), np.nan)
    image = axes[2].imshow(diff, extent=extent, vmin=-3e-4, vmax=3e-4, cmap="RdBu_r")
    axes[2].set_title("Rebuilt minus USGS")
    fig.colorbar(image, ax=axes[2], label="Coverage difference", shrink=0.8)
    for ax in axes:
        ax.set_xlabel("Longitude")
    axes[0].set_ylabel("Latitude")
    fig.suptitle("Nowicki Jessee (2018), 1989 Loma Prieta: implementation check")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / FIG_NAME, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {FIG_DIR / FIG_NAME}")


if __name__ == "__main__":
    main()
