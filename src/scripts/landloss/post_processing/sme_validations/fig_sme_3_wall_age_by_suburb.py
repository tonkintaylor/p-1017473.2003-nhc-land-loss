"""SME test 3: the age of each named suburb's properties against experience.

    uv run --frozen python src/scripts/landloss/post_processing/sme_validations/fig_sme_3_wall_age_by_suburb.py

Reads the property age shares by suburb that exposure step 8 tabulates
(``table_rwt_age_by_suburb.py``) and draws, for each suburb the statement names,
the share of its properties in each age bin, with the share experience expects
before 1970 marked where the statement gives one. The dwelling's age stands in
for its walls', as it does in the model.

Settings come from ``config.py`` beside this; the figure goes to
``config.FIG_DIR``.
"""

import sys

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from landloss.exposure.rw.age import AGE_BINS
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.table_rwt_age_by_suburb import (
    table_path,
)
from scripts.landloss.post_processing.sme_validations import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_NAME = "fig-sme-3-wall-age-by-suburb.png"
DPI = 200
BIN_LABELS = {
    "pre_1970": "Before 1970",
    "1970_1991": "1970 to 1991",
    "1992_2004": "1992 to 2004",
    "2005_on": "2005 on",
}
# One hue, oldest darkest, because the bins are ordered.
BIN_COLOURS = dict(
    zip(
        AGE_BINS,
        mpl.colormaps["Blues"](np.linspace(0.9, 0.3, len(AGE_BINS))),
        strict=False,
    )
)
INK = "#333333"
MUTED = "#6b6b6b"


def read_shares(suburbs, *, extent):
    """Return each named suburb's share of properties per age bin, in order."""
    table = pd.read_csv(table_path("suburb", extent=extent))
    rows = []
    for suburb, (ta, _, _) in suburbs.items():
        match = table[
            (table["suburb_locality"] == suburb)
            & (table["territorial_authority"] == ta)
        ]
        if match.empty:
            msg = f"{suburb}, {ta} is not in {table_path('suburb', extent=extent)}"
            raise KeyError(msg)
        rows.append(match.iloc[0])
    shares = pd.DataFrame(rows).set_index("suburb_locality")
    return shares[["properties", *(f"p_{name}" for name in AGE_BINS)]]


def draw(shares, suburbs):
    """Draw one stacked bar per suburb, with experience marked on it."""
    fig, ax = plt.subplots(figsize=(9, 0.55 * len(shares) + 1.6))
    y = np.arange(len(shares))[::-1]
    left = np.zeros(len(shares))
    for name in AGE_BINS:
        values = shares[f"p_{name}"].to_numpy()
        ax.barh(
            y,
            values,
            left=left,
            height=0.6,
            color=BIN_COLOURS[name],
            edgecolor="white",
            linewidth=1.5,
            label=BIN_LABELS[name],
        )
        left += values

    for row, (suburb, (_, expected, wording)) in zip(y, suburbs.items(), strict=False):
        pre_1970 = shares.loc[suburb, "p_pre_1970"]
        if pre_1970 >= 0.08:
            ax.text(
                pre_1970 / 2,
                row,
                f"{pre_1970:.0%}",
                ha="center",
                va="center",
                color="white",
                fontsize=8,
            )
        if expected is not None:
            ax.plot(
                [expected, expected],
                [row - 0.38, row + 0.38],
                color=INK,
                linewidth=2,
                solid_capstyle="butt",
            )
        ax.text(1.02, row, wording, va="center", color=MUTED, fontsize=8)

    labels = [
        f"{suburb} ({int(shares.loc[suburb, 'properties']):,})"
        for suburb in shares.index
    ]
    ax.set_yticks(y, labels)
    ax.set_xlim(0, 1)
    ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1.0))
    ax.set_xlabel("Share of claim properties, by age of the dwelling", color=INK)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)

    handles, names = ax.get_legend_handles_labels()
    handles.append(mpl.lines.Line2D([], [], color=INK, linewidth=2))
    names.append("Expected before 1970")
    ax.legend(
        handles,
        names,
        ncol=len(names),
        loc="lower left",
        bbox_to_anchor=(0, 1.02),
        frameon=False,
        fontsize=8,
        handlelength=1.2,
    )
    ax.text(1.02, len(shares) - 0.4, "Experience expects", color=INK, fontsize=8)
    fig.tight_layout()
    return fig


def main(*, extent, suburbs, fig_dir):
    """Draw the figure and print the shares it shows."""
    shares = read_shares(suburbs, extent=extent)
    print(shares.round(3).to_string())
    fig = draw(shares, suburbs)
    fig_dir.mkdir(parents=True, exist_ok=True)
    out_path = fig_dir / FIG_NAME
    fig.savefig(out_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main(extent=config.AGE_TABLE_EXTENT, suburbs=config.AGE_SUBURBS, fig_dir=config.FIG_DIR)
