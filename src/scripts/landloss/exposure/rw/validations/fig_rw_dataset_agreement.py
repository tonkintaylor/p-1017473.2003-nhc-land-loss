"""Chart where the three retaining wall datasets agree, property by property.

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/fig_rw_dataset_agreement.py

Reads the tables ``table_rw_dataset_agreement.py`` builds, from the layer
``gen_rw_dataset_properties.py`` writes, so run that first. Every chart is of
aggregates. Writes to ``report/exposure/rw/rw-datasets/fig/``:

- ``rw-dataset-agreement-gns-nhc.png``: properties GNS and NHC both, or only
  one of them, record a wall on, and how the split moves with the tolerance a
  GNS line is given;
- ``rw-dataset-upset-claims.png``: every combination of the three on claimed
  properties GNS mapped, as an UpSet chart;
- ``rw-dataset-claims-recall.png``: how often GNS and NHC flag a claimed
  property, by whether its report lists a wall, against how often they flag any
  property;
- ``rw-dataset-by-slope.png``: the share each flags by NZMM slope class;
- ``rw-dataset-wall-counts.png``: walls a claim report lists against walls GNS
  mapped on the same property.

Each dataset keeps one colour on every chart and map: GNS blue, NHC orange,
claim reports aqua, the first three slots of the dataviz reference palette,
which hold apart under colour vision deficiency as a set.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts.landloss.exposure.rw.validations import config
from scripts.landloss.exposure.rw.validations.rw_datasets import (
    BOTH,
    CLAIMS,
    GNS,
    GNS_ONLY,
    NHC,
    NHC_ONLY,
    gns_nhc_population,
    load_properties,
)
from scripts.landloss.exposure.rw.validations.table_rw_dataset_agreement import (
    build_tables,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

COLOURS = {GNS: "#2a78d6", NHC: "#eb6834", CLAIMS: "#1baf7a"}
# Both is neither dataset's colour: a neutral ink, so it does not read as one.
CATEGORY_COLOURS = {BOTH: "#52514e", GNS_ONLY: COLOURS[GNS], NHC_ONLY: COLOURS[NHC]}
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e5e4e0"
EMPTY = "#d9d8d4"
HEAT = "Blues"

DPI = 250
RULE = "-" * 72


def style(ax: plt.Axes, *, axis: str = "y") -> None:
    """Give an axes a recessive grid and no box."""
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(TEXT_MUTED)
    ax.tick_params(colors=TEXT_MUTED, labelcolor=TEXT)


def percent(ax: plt.Axes, axis: str = "y") -> None:
    """Label an axis in percent."""
    formatter = mpl.ticker.PercentFormatter(xmax=1.0, decimals=0)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(formatter)


def fig_gns_nhc(table: pd.DataFrame) -> plt.Figure:
    """Chart properties flagged by both, GNS only or NHC only, and by tolerance."""
    fig, (ax_count, ax_split) = plt.subplots(
        1, 2, figsize=(10.0, 3.8), gridspec_kw={"width_ratios": [1.0, 1.3]}
    )
    categories = [BOTH, GNS_ONLY, NHC_ONLY]

    row = table.loc[config.TOLERANCE_M]
    counts = [row[name] for name in categories]
    positions = np.arange(len(categories))[::-1]
    ax_count.barh(
        positions,
        counts,
        color=[CATEGORY_COLOURS[name] for name in categories],
        height=0.6,
        edgecolor="white",
        linewidth=2,
    )
    for position, count in zip(positions, counts, strict=True):
        ax_count.text(
            count, position, f" {count:,.0f}", va="center", color=TEXT, fontsize=9
        )
    ax_count.set_yticks(positions, categories)
    ax_count.set_xlabel("Properties recorded with a wall")
    ax_count.set_xlim(0, max(counts) * 1.2)
    ax_count.set_title(
        f"Urban Wellington City, {row['properties']:,.0f} properties\n"
        f"GNS line within {config.TOLERANCE_M:g} m",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    style(ax_count, axis="x")

    tolerances = table.index.to_numpy()
    either = table[categories].sum(axis=1)
    left = np.zeros(len(tolerances))
    labels = [f"{tolerance:g} m" for tolerance in tolerances]
    for name in categories:
        shares = (table[name] / either).to_numpy()
        ax_split.barh(
            labels,
            shares,
            left=left,
            color=CATEGORY_COLOURS[name],
            height=0.6,
            edgecolor="white",
            linewidth=2,
            label=name,
        )
        for index, (start, value) in enumerate(zip(left, shares, strict=True)):
            if value > 0.06:
                ax_split.text(
                    start + value / 2,
                    index,
                    f"{value:.0%}",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=8,
                )
        left += shares
    ax_split.invert_yaxis()
    ax_split.set_xlim(0, 1)
    percent(ax_split, axis="x")
    ax_split.set_xlabel("Share of properties either dataset records a wall on")
    ax_split.set_ylabel("Tolerance on a GNS line")
    ax_split.set_title(
        "The split barely moves with the tolerance", loc="left", fontsize=10, color=TEXT
    )
    ax_split.legend(
        ncols=3, loc="upper center", bbox_to_anchor=(0.5, -0.22), frameon=False
    )
    style(ax_split, axis="x")
    fig.tight_layout()
    return fig


def fig_upset(combos: pd.DataFrame) -> plt.Figure:
    """Draw an UpSet chart of the three datasets on claimed GNS properties."""
    sets = [CLAIMS, GNS, NHC]
    combos = combos.sort_values("properties", ascending=False).reset_index(drop=True)
    total = combos["properties"].sum()

    fig = plt.figure(figsize=(8.5, 4.6))
    grid = fig.add_gridspec(
        2,
        2,
        width_ratios=[1.0, 3.2],
        height_ratios=[2.4, 1.0],
        wspace=0.45,
        hspace=0.05,
    )
    ax_bars = fig.add_subplot(grid[0, 1])
    ax_matrix = fig.add_subplot(grid[1, 1], sharex=ax_bars)
    ax_sizes = fig.add_subplot(grid[1, 0], sharey=ax_matrix)

    x = np.arange(len(combos))
    members = combos[sets].to_numpy(dtype=bool)
    agreeing = members.all(axis=1) | ~members.any(axis=1)
    colours = [TEXT_MUTED if agree else "#9a9893" for agree in agreeing]
    ax_bars.bar(x, combos["properties"], color=colours, width=0.6)
    for position, count in zip(x, combos["properties"], strict=True):
        ax_bars.text(
            position,
            count,
            f"{count:,}\n{count / total:.0%}",
            ha="center",
            va="bottom",
            fontsize=8,
            color=TEXT,
        )
    ax_bars.set_ylabel("Claimed properties")
    ax_bars.set_ylim(0, combos["properties"].max() * 1.25)
    ax_bars.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_bars.set_title(
        f"Claimed properties in urban Wellington City ({total:,}): which datasets "
        "record a wall\nDark bars: all three agree (all, or none)",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    style(ax_bars)

    rows = np.arange(len(sets))[::-1]
    for column, member in enumerate(members):
        dots = [rows[index] for index, flag in enumerate(member) if flag]
        ax_matrix.scatter(
            [column] * len(rows), rows, s=60, color=EMPTY, zorder=2, linewidth=0
        )
        ax_matrix.scatter(
            [column] * len(dots),
            dots,
            s=60,
            color=[COLOURS[sets[list(rows).index(dot)]] for dot in dots],
            zorder=3,
            edgecolor="white",
            linewidth=1.5,
        )
        if len(dots) > 1:
            ax_matrix.plot(
                [column, column],
                [min(dots), max(dots)],
                color=TEXT_MUTED,
                lw=2,
                zorder=2,
            )
    ax_matrix.set_yticks(rows, sets)
    ax_matrix.tick_params(axis="y", length=0, labelcolor=TEXT, pad=8)
    ax_matrix.set_xticks([])
    ax_matrix.set_ylim(-0.6, len(sets) - 0.4)
    for side in ("top", "right", "bottom", "left"):
        ax_matrix.spines[side].set_visible(False)

    sizes = [members[:, index] @ combos["properties"].to_numpy() for index in range(3)]
    ax_sizes.barh(rows, sizes, color=[COLOURS[name] for name in sets], height=0.5)
    for row, size in zip(rows, sizes, strict=True):
        ax_sizes.text(size, row, f"{size:,} ", ha="right", va="center", fontsize=8)
    ax_sizes.set_xlim(max(sizes) * 1.35, 0)
    ax_sizes.set_xlabel("Records a wall", color=TEXT)
    ax_sizes.tick_params(left=False, labelleft=False, colors=TEXT_MUTED)
    for side in ("top", "left", "right"):
        ax_sizes.spines[side].set_visible(False)
    return fig


def fig_claims_recall(recall: pd.DataFrame, background: dict[str, float]) -> plt.Figure:
    """Chart how often GNS and NHC flag a claim property, by what the claim lists."""
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    groups = recall.index.tolist()
    series = [(GNS, "gns_flagged"), (NHC, "nhc_flagged_where_gns_mapped")]
    width = 0.32
    x = np.arange(len(groups))
    for offset, (name, column) in zip((-0.5, 0.5), series, strict=True):
        values = recall[column].to_numpy()
        ax.bar(
            x + offset * width * 1.06,
            values,
            width,
            color=COLOURS[name],
            label=name,
            edgecolor="white",
            linewidth=2,
        )
        for position, value in zip(x + offset * width * 1.06, values, strict=True):
            ax.text(
                position, value, f"{value:.0%}", ha="center", va="bottom", fontsize=8
            )
    for name, value in background.items():
        ax.axhline(
            value,
            color=COLOURS[name],
            linestyle="--",
            linewidth=1.2,
            label=f"{name}, all properties GNS mapped: {value:.0%}",
            zorder=0,
        )
    ax.set_xticks(
        x,
        [
            f"Claim report {group}\n({recall.loc[group, 'properties_gns_mapped']:,.0f} properties)"
            for group in groups
        ],
    )
    ax.set_ylabel("Share flagged with a wall")
    percent(ax)
    ax.set_ylim(0, max(recall["gns_flagged"].max(), *background.values()) * 1.3)
    ax.set_title(
        "Claimed properties in urban Wellington City: GNS and NHC flag a wall about\n"
        "as often whether or not the claim report lists one",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    style(ax)
    fig.tight_layout()
    return fig


def fig_by_slope(by_slope: pd.DataFrame) -> plt.Figure:
    """Chart the share each dataset flags by NZMM slope class."""
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    series = [
        (GNS, "gns_flagged", "properties_gns_mapped", "of properties GNS mapped"),
        (NHC, "nhc_flagged", "properties_nzmm", "of properties NZMM covers"),
        (CLAIMS, "claim_lists_wall", "claimed_properties", "of claimed properties"),
    ]
    classes = by_slope.index.astype(int).tolist()
    x = np.arange(len(classes))
    width = 0.26
    for offset, (name, column, n_column, label) in zip((-1, 0, 1), series, strict=True):
        values = by_slope[column].to_numpy(dtype=float)
        positions = x + offset * width * 1.06
        ax.bar(
            positions,
            values,
            width,
            color=COLOURS[name],
            edgecolor="white",
            linewidth=2,
            label=f"{name}, {label}",
        )
        for position, value, n in zip(
            positions, values, by_slope[n_column], strict=True
        ):
            if np.isfinite(value):
                ax.text(
                    position,
                    value,
                    f"{value:.0%}\nn={n:,}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color=TEXT,
                )
    ax.set_xticks(x, [f"Slope class {value}" for value in classes])
    ax.set_ylabel("Share recorded with a wall")
    percent(ax)
    ax.set_ylim(0, np.nanmax(by_slope[[s[1] for s in series]].to_numpy(float)) * 1.35)
    ax.set_title(
        "Share of properties recorded with a wall, by NZMM mean slope class",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    ax.legend(frameon=False, loc="upper right", fontsize=8)
    style(ax)
    fig.tight_layout()
    return fig


def fig_wall_counts(counts: pd.DataFrame) -> plt.Figure:
    """Draw claim report wall counts against GNS wall counts as a heatmap."""
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    values = counts.to_numpy()
    image = ax.imshow(
        np.log1p(values), cmap=HEAT, aspect="auto", origin="lower", vmin=0
    )
    threshold = np.log1p(values.max()) * 0.6
    for (row, column), value in np.ndenumerate(values):
        ax.text(
            column,
            row,
            f"{value:,}",
            ha="center",
            va="center",
            fontsize=9,
            color="white" if np.log1p(value) > threshold else TEXT,
        )
    ax.set_xticks(range(counts.shape[1]), counts.columns)
    ax.set_yticks(range(counts.shape[0]), counts.index)
    ax.set_xlabel(f"Walls GNS mapped on the property (within {config.TOLERANCE_M:g} m)")
    ax.set_ylabel("Walls the claim report lists")
    ax.set_title(
        f"Claimed properties in urban Wellington City ({values.sum():,})",
        loc="left",
        fontsize=10,
        color=TEXT,
    )
    for side in ax.spines.values():
        side.set_visible(False)
    ax.tick_params(length=0)
    image.set_rasterized(True)
    fig.tight_layout()
    return fig


def main() -> int:
    """Write every chart."""
    config.FIG_DIR.mkdir(parents=True, exist_ok=True)
    properties = load_properties()
    tables = build_tables(properties)
    population = gns_nhc_population(properties)
    background = {
        GNS: float(population["gns_wall"].mean()),
        NHC: float(population["nhc_wall"].mean()),
    }

    figures = {
        "rw-dataset-agreement-gns-nhc.png": fig_gns_nhc(
            tables["rw-dataset-agreement-gns-nhc.csv"]
        ),
        "rw-dataset-upset-claims.png": fig_upset(
            tables["rw-dataset-agreement-claims.csv"]
        ),
        "rw-dataset-claims-recall.png": fig_claims_recall(
            tables["rw-dataset-claims-recall.csv"], background
        ),
        "rw-dataset-by-slope.png": fig_by_slope(tables["rw-dataset-by-slope.csv"]),
        "rw-dataset-wall-counts.png": fig_wall_counts(
            tables["rw-dataset-wall-counts.csv"]
        ),
    }
    for name, fig in figures.items():
        fig.savefig(config.FIG_DIR / name, dpi=DPI, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {config.FIG_DIR / name}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
