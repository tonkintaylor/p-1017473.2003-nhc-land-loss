"""Scatter of NHC's land claims cohort: repair cost against damaged land area.

Each point is one cohort claim, coloured by the free-text damaged land
description NHC recorded for it, so any relationship between land area and
repair cost can be checked against what kind of damage each claim involved.

    uv run --frozen python src/scripts/landloss/vul/research/fig_land_claims_cohort.py

Reads the CSV written by
``src/scripts/landloss/vul/static_data_gen/get_nhi_act_claims_data.py``.
"""

import argparse
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import pandas as pd

from scripts.landloss.paths import NHI_ACT_LAND_CLAIMS_COHORT_CSV, RESEARCH_DIR

FIG_DIR = RESEARCH_DIR / "vul" / "claims_cohort" / "fig"

X_COLUMN = "Damaged land area (m2)"
Y_COLUMN = "Indicative land repair cost ($)"
CATEGORY_COLUMN = "Damaged land description"

DPI = 200
FIGSIZE = (10, 7)


def plot_claims_cohort(claims: pd.DataFrame) -> plt.Figure:
    """Draw the scatter, one colour per damaged land description.

    Args:
        claims: The cohort claims, carrying X_COLUMN, Y_COLUMN and
            CATEGORY_COLUMN.

    Returns:
        The figure, ready to save.
    """
    categories = sorted(claims[CATEGORY_COLUMN].dropna().unique())
    # The descriptions are free text, so there can be dozens of them -- draw
    # from three qualitative colormaps back to back rather than one.
    palette = [
        colour
        for name in ("tab20", "tab20b", "tab20c")
        for colour in plt.get_cmap(name).colors
    ][: len(categories)]
    colours = dict(zip(categories, palette, strict=False))

    fig, ax = plt.subplots(figsize=FIGSIZE)
    for category, group in claims.groupby(CATEGORY_COLUMN):
        ax.scatter(
            group[X_COLUMN],
            group[Y_COLUMN],
            label=category,
            color=colours[category],
            s=40,
            alpha=0.8,
            edgecolor="black",
            linewidth=0.3,
        )
    ax.set_xlabel(X_COLUMN)
    ax.set_ylabel(Y_COLUMN)
    ax.set_title("NHI Act land claims cohort")
    ax.legend(
        title=CATEGORY_COLUMN,
        loc="upper left",
        bbox_to_anchor=(1.02, 1),
        fontsize="xx-small",
        title_fontsize="x-small",
    )
    fig.tight_layout()
    return fig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=NHI_ACT_LAND_CLAIMS_COHORT_CSV,
        help="The claims cohort CSV from get_nhi_act_claims_data.py.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=FIG_DIR,
        help="Where to write the figure.",
    )
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Cannot reach {args.csv}")
        print("\nRun get_nhi_act_claims_data.py first.")
        return 1

    claims = pd.read_csv(args.csv)
    print(f"Loaded {len(claims):,} cohort claims")

    fig = plot_claims_cohort(claims)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "land-claims-cohort-scatter.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
