"""Check our rebuilt Nowicki Jessee input layers against the USGS's, at Loma Prieta.

Rebuilds slope, lithology, land cover and CTI from GMTED2010, GLiM and
GlobCover 2009 over the Loma Prieta extent, and compares each with the layer
the USGS ``groundfailure`` package ships for the same ground. Then a swap
test: the model is run on the USGS inputs with one layer at a time replaced by
ours, and finally on all of ours, and each run's coverage is compared with the
USGS's expected output. A layer can differ a good deal and barely move the
answer -- CTI carries a coefficient of 0.03 -- so the swap test, not the layer
comparison, is what says whether a rebuilt layer is good enough.

Prints both comparisons and draws, per layer, our value against the USGS's.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/nowicki_2018/fig_nowicki_2018_loma_prieta_layers.py

Requires the static data on T: -- run every ``get_`` script in
``static_data_gen/`` first. Results are written up in
``nowicki_2018_loma_prieta_findings.md`` beside this script.
"""

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes a PNG

import matplotlib.pyplot as plt
import numpy as np

from scripts.landloss.hazard.landslide.validations.nowicki_2018 import loma_prieta
from scripts.landloss.paths import REPORT_DIR

FIG_DIR = REPORT_DIR / "hazard" / "landslide" / "nowicki-2018-validation" / "fig"
FIG_NAME = "loma-prieta-layers-against-usgs.png"
DPI = 200

LABELS = {
    "slope_deg": "Slope (degrees)",
    "rock_coefficient": "Lithology coefficient",
    "landcover_coefficient": "Land cover coefficient",
    "cti": "CTI",
}

# The class coefficients are compared for exact agreement; anything closer than
# this is the same coefficient.
SAME_COEFFICIENT = 1.0e-6


def compare_layer(name, ours, usgs, mask):
    """Print one layer's agreement and return the cells compared."""
    both = mask & np.isfinite(ours) & np.isfinite(usgs)
    a, u = ours[both], usgs[both]
    line = f"  {LABELS[name]:<24} n={both.sum():>7,}"
    if name.endswith("_coefficient"):
        line += (
            f"  same class coefficient {np.mean(np.abs(a - u) < SAME_COEFFICIENT):.2%}"
        )
    else:
        line += (
            f"  r={np.corrcoef(a, u)[0, 1]:.3f}  mean diff {np.mean(a - u):+.3f}"
            f"  mean |diff| {np.mean(np.abs(a - u)):.3f}"
        )
    print(line)
    return both


def compare_coverage(label, coverage, target, grid, mask):
    """Print one swap-test run's agreement with the USGS coverage."""
    both = mask & np.isfinite(coverage) & np.isfinite(target)
    area = loma_prieta.landslide_area_km2(coverage, grid, both)
    usgs_area = loma_prieta.landslide_area_km2(target, grid, both)
    r = np.corrcoef(coverage[both], target[both])[0, 1]
    mad = np.mean(np.abs(coverage[both] - target[both]))
    print(
        f"  {label:<34} r={r:.3f}  mean |diff| {mad:.5f}  "
        f"area {area:7.2f} km2 vs {usgs_area:7.2f} ({area / usgs_area - 1:+.1%})"
    )


def main():
    """Run the layer comparison and the swap test, and draw the figure."""
    target = loma_prieta.get_target()
    mask = loma_prieta.interior(target)
    shaking = loma_prieta.get_shaking(target)
    usgs = loma_prieta.get_usgs_inputs(target)
    ours = loma_prieta.gen_rebuilt_inputs(target)

    print("Rebuilt layers against the USGS's, on the target grid:")
    compared = {
        name: compare_layer(name, ours[name].to_numpy(), usgs[name].to_numpy(), mask)
        for name in loma_prieta.LAYERS
    }

    print("Swap test, coverage against the USGS's expected output:")
    t = target.to_numpy()
    compare_coverage(
        "USGS inputs",
        loma_prieta.run_operational(usgs, shaking).coverage,
        t,
        target,
        mask,
    )
    for name in loma_prieta.LAYERS:
        swapped = usgs.copy()
        swapped[name] = ours[name]
        result = loma_prieta.run_operational(swapped, shaking)
        compare_coverage(
            f"USGS inputs, our {LABELS[name]}", result.coverage, t, target, mask
        )
    rebuilt = ours.assign(logit_std=usgs["logit_std"])
    compare_coverage(
        "All rebuilt inputs",
        loma_prieta.run_operational(rebuilt, shaking).coverage,
        t,
        target,
        mask,
    )

    fig, axes = plt.subplots(1, 4, figsize=(18, 4.6), constrained_layout=True)
    for ax, name in zip(axes, loma_prieta.LAYERS, strict=True):
        both = compared[name]
        u, a = usgs[name].to_numpy()[both], ours[name].to_numpy()[both]
        ax.hexbin(u, a, gridsize=60, bins="log", mincnt=1, cmap="viridis")
        lo, hi = float(min(u.min(), a.min())), float(max(u.max(), a.max()))
        ax.plot([lo, hi], [lo, hi], color="black", lw=0.8)
        ax.set_title(LABELS[name])
        ax.set_xlabel("USGS groundfailure 1.3.2")
    axes[0].set_ylabel("Rebuilt from raw sources")
    fig.suptitle("Nowicki Jessee (2018) inputs, 1989 Loma Prieta: rebuilt against USGS")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / FIG_NAME, dpi=DPI)
    plt.close(fig)
    print(f"Wrote {FIG_DIR / FIG_NAME}")


if __name__ == "__main__":
    main()
