"""Scatter of settled NHC land claims: settlement amount against repair cost.

    uv run --frozen python src/scripts/landloss/vul/research/fig_settled_land_claims.py

Reads the CSV written by
``src/scripts/landloss/vul/static_data_gen/get_nhi_act_claims_data.py``.
"""

import argparse
from pathlib import Path

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import pandas as pd

from scripts.landloss.paths import NHI_ACT_SETTLED_LAND_CLAIMS_CSV, RESEARCH_DIR

FIG_DIR = RESEARCH_DIR / "vul" / "settled_claims" / "fig"

X_COLUMN = "TotalCosttoRepair"
Y_COLUMN = "Total Settlement Amount"

DPI = 200
FIGSIZE = (8, 6)


def plot_settled_claims(claims: pd.DataFrame) -> plt.Figure:
    """Draw the scatter of settlement amount against cost to repair.

    Args:
        claims: The settled claims, carrying X_COLUMN and Y_COLUMN.

    Returns:
        The figure, ready to save.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.scatter(claims[X_COLUMN], claims[Y_COLUMN], s=10, alpha=0.5)
    ax.set_xlabel(X_COLUMN)
    ax.set_ylabel(Y_COLUMN)
    ax.set_title("NHI Act settled land claims")
    fig.tight_layout()
    return fig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=NHI_ACT_SETTLED_LAND_CLAIMS_CSV,
        help="The settled land claims CSV from get_nhi_act_claims_data.py.",
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
    print(f"Loaded {len(claims):,} settled claims")

    fig = plot_settled_claims(claims)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "settled-land-claims-scatter.png"
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
