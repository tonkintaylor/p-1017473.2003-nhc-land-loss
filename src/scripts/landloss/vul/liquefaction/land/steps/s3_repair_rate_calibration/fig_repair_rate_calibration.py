"""Draw how the liquefied land repair rates were fitted, as an aid to explaining it.

Four figures, one per stage of the fit in step 3, read off the claims step 2
last wrote and the rates step 2 is configured with:

    uv run --frozen python src/scripts/landloss/vul/liquefaction/land/steps/s3_repair_rate_calibration/fig_repair_rate_calibration.py

- **Ground lost.** The mean inundated and evacuated area of a modelled claim
  per land damage state: what the rates per m² multiply. Inundated runs to
  hundreds of m² from Moderate up; evacuated stays in single figures until
  Severe.
- **Cost build-up.** The modelled mean cost of a claim per state, stacked as the
  per-claim cost, the evacuated cost and the inundated cost, against the
  Canterbury claimant-only mean the three rates were fitted to.
- **Quartiles.** The lower quartile, median and upper quartile of a claim's
  cost per state, modelled against Canterbury, with a fixed per-claim cost and
  with the fitted spread: why the spread is there, and how far it gets.
- **Spread fit.** The claim-weighted miss against the Canterbury quartiles as
  the spread varies, with the minimum the fit chose.

The Canterbury figures are a calibration target only, drawn to compare with.
The modelled quartiles integrate the per-claim draw, as step 3 does, rather
than reading step 2's single draw, so a small state is not drawn noisy.

It reads step 3's ``config.py`` for the extent and realisations, and step 2's
for the rates. Run step 3 first if the two might disagree; it says when they
do. The figures go under ``report/vul/liquefaction/repair-rates/fig/``, which
is gitignored -- the script is the record of how they were made, not the PNGs.
"""

import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from landloss.io.area_of_interest import extent_suffix
from landloss.vul.liquefaction.costs import (
    CLAIMS_COLUMN,
    MEAN_COST_COLUMN,
    QUARTILE_COLUMNS,
    load_claimant_costs,
)
from landloss.vul.liquefaction.damaged_area import (
    EVACUATED_AREA_COLUMN,
    INUNDATED_AREA_COLUMN,
)
from landloss.vul.liquefaction.repair_rates import (
    MAX_SIGMA,
    RepairRates,
    modelled_quartiles,
)
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage import (
    config as s2_config,
)
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage.gen_liq_land_damage import (
    CLAIMED_COLUMN,
    STATE_COLUMN,
    liq_land_damage_path,
)
from scripts.landloss.vul.liquefaction.land.steps.s3_repair_rate_calibration import (
    config,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "vul" / "liquefaction" / "repair-rates" / "fig"
DPI = 200

# Ink and chrome, and the categorical slots in fixed order: per claim, then
# evacuated, then inundated, in every figure that shows them.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
PER_CLAIM = "#2a78d6"
EVACUATED = "#eb6834"
INUNDATED = "#1baf7a"
# Canterbury is the reference, so it wears ink rather than a series hue.
CANTERBURY = INK_SECONDARY
MODELLED = PER_CLAIM

# A quartile range narrower than this share of its median is drawn as a line.
FLAT_SHARE = 0.02
# How many spreads the miss is drawn at in the spread-fit figure.
SIGMA_STEPS = 121

STATE_LABELS = {
    1: "None",
    2: "Minor",
    3: "Moderate",
    4: "Major",
    5: "Severe",
    6: "Very severe",
}

plt.rcParams.update(
    {
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "xtick.labelcolor": INK_SECONDARY,
        "ytick.labelcolor": INK_SECONDARY,
        "font.size": 9,
        "legend.frameon": False,
        "legend.labelcolor": INK_SECONDARY,
    }
)

DOLLARS = FuncFormatter(lambda value, _: f"${value:,.0f}")


def load_claims(extent, realisation_ids):
    """Return the modelled claims, pooled over the realisations."""
    damage = pd.concat(
        pd.read_parquet(liq_land_damage_path(realisation_id, extent=extent))
        for realisation_id in realisation_ids
    )
    claims = damage.loc[damage[CLAIMED_COLUMN]].copy()
    claims[STATE_COLUMN] = claims[STATE_COLUMN].astype(int)
    return claims


def area_cost_by_state(claims, rates):
    """Return each claim's cost of ground lost, before the per-claim cost."""
    cost = (
        claims[INUNDATED_AREA_COLUMN] * rates.inundated_nzd_per_m2
        + claims[EVACUATED_AREA_COLUMN] * rates.evacuated_nzd_per_m2
    )
    return {
        int(state): group.to_numpy()
        for state, group in cost.groupby(claims[STATE_COLUMN])
    }


def finish(fig, name, extent):
    """Write a figure and say where it went."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{name}{extent_suffix(extent)}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote {path}")


def label_bars(ax, bars, fmt):
    """Write each bar's value just above it, in text ink."""
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt(height),
            (bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            color=INK_SECONDARY,
            fontsize=8,
        )


def fig_ground_lost(claims, states, extent):
    """Mean inundated and evacuated area of a claim per state, two panels."""
    means = claims.groupby(STATE_COLUMN)[
        [INUNDATED_AREA_COLUMN, EVACUATED_AREA_COLUMN]
    ].mean()
    counts = claims.groupby(STATE_COLUMN).size()
    labels = [f"{STATE_LABELS[s]}\n{counts.get(s, 0)} claims" for s in states]
    x = np.arange(len(states))

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=False)
    panels = (
        (INUNDATED_AREA_COLUMN, INUNDATED, "Inundated (under ejecta)"),
        (EVACUATED_AREA_COLUMN, EVACUATED, "Evacuated (cracked or spread)"),
    )
    for ax, (column, colour, title) in zip(axes, panels, strict=True):
        values = means[column].reindex(states).fillna(0).to_numpy()
        bars = ax.bar(x, values, width=0.6, color=colour, edgecolor=SURFACE)
        label_bars(ax, bars, lambda v: f"{v:,.0f} m²")
        ax.set_xticks(x, labels)
        ax.set_ylabel("Mean area per claim (m²)")
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
        ax.margins(y=0.15)
    fig.suptitle(
        "Ground lost by a modelled claim, by land damage state",
        x=0.01,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.01,
        -0.04,
        "Drawn uniformly within each state's agreed ranges (L-39), over the claims "
        "step 2 wrote. The rates per m² multiply these.",
        color=INK_MUTED,
        fontsize=8,
    )
    fig.tight_layout()
    finish(fig, "liq-repair-ground-lost", extent)


def fig_cost_build_up(claims, canterbury, rates, states, extent):
    """Modelled mean cost per state, stacked, against the Canterbury mean."""
    means = claims.groupby(STATE_COLUMN)[
        [INUNDATED_AREA_COLUMN, EVACUATED_AREA_COLUMN]
    ].mean()
    per_claim = np.full(len(states), rates.per_claim_nzd)
    evacuated = (
        means[EVACUATED_AREA_COLUMN].reindex(states).fillna(0).to_numpy()
        * rates.evacuated_nzd_per_m2
    )
    inundated = (
        means[INUNDATED_AREA_COLUMN].reindex(states).fillna(0).to_numpy()
        * rates.inundated_nzd_per_m2
    )
    target = canterbury.loc[states, MEAN_COST_COLUMN].to_numpy(float)
    modelled = per_claim + evacuated + inundated
    x = np.arange(len(states))
    width = 0.55

    fig, ax = plt.subplots(figsize=(9, 4.6))
    bottom = np.zeros(len(states))
    segments = (
        (per_claim, PER_CLAIM, f"Per claim, ${rates.per_claim_nzd:,.0f} on average"),
        (
            evacuated,
            EVACUATED,
            f"Evacuated, ${rates.evacuated_nzd_per_m2:,.2f} per m²",
        ),
        (
            inundated,
            INUNDATED,
            f"Inundated, ${rates.inundated_nzd_per_m2:,.2f} per m²",
        ),
    )
    handles = []
    for values, colour, label in segments:
        ax.bar(
            x,
            values,
            width,
            bottom=bottom,
            color=colour,
            edgecolor=SURFACE,
            linewidth=1.5,
        )
        bottom += values
        handles.append(Patch(facecolor=colour, label=label))
    ax.scatter(
        x,
        target,
        marker="D",
        s=46,
        color=CANTERBURY,
        edgecolor=SURFACE,
        linewidth=1.5,
        zorder=4,
    )
    handles.append(
        Line2D(
            [],
            [],
            marker="D",
            linestyle="none",
            color=CANTERBURY,
            markersize=7,
            label="Canterbury claimant-only mean (target)",
        )
    )
    for i, (m, t) in enumerate(zip(modelled, target, strict=True)):
        ax.annotate(
            f"{m / t:.2f}\N{MULTIPLICATION SIGN}",
            (x[i], max(m, t)),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            color=INK,
            fontsize=8,
            fontweight="bold",
        )
    claims_n = canterbury.loc[states, CLAIMS_COLUMN]
    ax.set_xticks(
        x,
        [
            f"{STATE_LABELS[s]}\n{n:,} claims"
            for s, n in zip(states, claims_n, strict=True)
        ],
    )
    ax.yaxis.set_major_formatter(DOLLARS)
    ax.set_ylabel("Mean cost of a claim, 2010/2011 NZD excl. GST")
    ax.grid(axis="x", visible=False)
    ax.margins(y=0.12)
    ax.set_title("How the three rates add up to the mean cost of a claim")
    ax.legend(handles=handles, loc="upper left", fontsize=8)
    fig.text(
        0.01,
        -0.04,
        "Rates fitted by least squares to the Canterbury means, each state "
        "weighted by its Canterbury claim count (under each state), all three "
        "non-negative. Labels: modelled over Canterbury.",
        color=INK_MUTED,
        fontsize=8,
    )
    fig.tight_layout()
    finish(fig, "liq-repair-cost-build-up", extent)


def draw_quartiles(ax, x, quartiles, colour, offset, width):
    """Draw lower to upper quartile as a bar, with the median as a tick.

    A state with no spread at all has no bar to draw, so it is drawn as a line
    in the series colour at its one value instead.
    """
    lower, median, upper = quartiles
    flat = (upper - lower) < FLAT_SHARE * median
    ax.hlines(
        median[flat],
        (x + offset - width / 2)[flat],
        (x + offset + width / 2)[flat],
        color=colour,
        linewidth=3,
    )
    lower, median, upper, x = lower[~flat], median[~flat], upper[~flat], x[~flat]
    ax.bar(
        x + offset,
        upper - lower,
        width,
        bottom=lower,
        color=colour,
        alpha=0.85,
        edgecolor=SURFACE,
        linewidth=1.5,
    )
    ax.hlines(
        median,
        x + offset - width / 2,
        x + offset + width / 2,
        color=SURFACE,
        linewidth=2.5,
    )


def fig_quartiles(area_cost, canterbury, rates, states, extent):
    """Modelled against Canterbury quartiles, without and with the spread."""
    columns = list(QUARTILE_COLUMNS.values())
    target = canterbury.loc[states, columns].to_numpy(float).T
    x = np.arange(len(states))
    width = 0.34

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True)
    panels = (
        (0.0, "One per-claim cost for every claim"),
        (
            rates.per_claim_sigma,
            f"Per-claim cost spread, sigma {rates.per_claim_sigma:.2f}",
        ),
    )
    for ax, (sigma, title) in zip(axes, panels, strict=True):
        modelled = np.array(
            [
                modelled_quartiles(area_cost[s], rates.per_claim_nzd, sigma)
                for s in states
            ]
        ).T
        draw_quartiles(ax, x, target, CANTERBURY, -width / 2 - 0.02, width)
        draw_quartiles(ax, x, modelled, MODELLED, width / 2 + 0.02, width)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(DOLLARS)
        ax.yaxis.set_minor_formatter(FuncFormatter(lambda *_: ""))
        ax.set_yticks([250, 500, 1000, 2000, 4000, 8000])
        ax.set_xticks(x, [STATE_LABELS[s] for s in states])
        ax.grid(axis="x", visible=False)
        ax.set_title(title)
    axes[0].set_ylabel("Cost of a claim, 2010/2011 NZD excl. GST (log)")
    axes[0].legend(
        handles=[
            Patch(facecolor=CANTERBURY, label="Canterbury claimants (target)"),
            Patch(facecolor=MODELLED, label="Modelled"),
            Line2D([], [], color=INK_MUTED, linewidth=2.5, label="Median (white tick)"),
        ],
        loc="upper left",
        fontsize=8,
    )
    fig.suptitle(
        "Lower quartile to upper quartile of a claim's cost, by land damage state",
        x=0.01,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    fig.text(
        0.01,
        -0.04,
        "Left: a single per-claim cost puts a floor under every claim. Right: the "
        "per-claim cost drawn lognormally with a mean of one, so the means are "
        "unchanged; sigma fitted to the Canterbury quartiles.",
        color=INK_MUTED,
        fontsize=8,
    )
    fig.tight_layout()
    finish(fig, "liq-repair-quartiles", extent)


def fig_spread_fit(area_cost, canterbury, rates, states, weights, extent):
    """The miss against the Canterbury quartiles as the spread varies."""
    columns = list(QUARTILE_COLUMNS.values())
    targets = {s: canterbury.loc[s, columns].to_numpy(float) for s in states}
    sigmas = np.linspace(0.0, min(MAX_SIGMA, 2.0), SIGMA_STEPS)
    total = weights.sum()

    def miss(sigma, state):
        modelled = modelled_quartiles(area_cost[state], rates.per_claim_nzd, sigma)
        return float(np.sum(np.log(modelled / targets[state]) ** 2))

    curve = np.array(
        [sum(weights[s] * miss(sigma, s) for s in states) / total for sigma in sigmas]
    )
    fitted = sum(weights[s] * miss(rates.per_claim_sigma, s) for s in states) / total

    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.plot(sigmas, curve, color=MODELLED, linewidth=2)
    ax.scatter(
        [rates.per_claim_sigma],
        [fitted],
        s=60,
        color=MODELLED,
        edgecolor=SURFACE,
        linewidth=2,
        zorder=4,
    )
    ax.annotate(
        f"fitted sigma {rates.per_claim_sigma:.2f}",
        (rates.per_claim_sigma, fitted),
        xytext=(0, 36),
        textcoords="offset points",
        ha="center",
        color=INK,
        fontsize=9,
    )
    ax.set_xlabel("Spread of the per-claim cost (lognormal sigma)")
    ax.set_ylabel("Weighted squared log miss")
    ax.set_ylim(bottom=0)
    ax.set_title("Choosing the spread: miss against the Canterbury quartiles")
    fig.text(
        0.01,
        -0.06,
        "Sum over the lower quartile, median and upper quartile of "
        "ln(modelled / Canterbury)², averaged over states weighted by Canterbury "
        "claim count.",
        color=INK_MUTED,
        fontsize=8,
    )
    fig.tight_layout()
    finish(fig, "liq-repair-spread-fit", extent)


def main(*, extent, realisation_ids, fit_states, weight_by_claims, repair_rates):
    """Draw the four figures."""
    rates = RepairRates(**repair_rates)
    claims = load_claims(extent, realisation_ids)
    canterbury = load_claimant_costs()
    states = sorted(fit_states)
    area_cost = area_cost_by_state(claims, rates)
    weights = (
        canterbury.loc[states, CLAIMS_COLUMN].astype(float)
        if weight_by_claims
        else pd.Series(1.0, index=states)
    )
    fig_ground_lost(claims, states, extent)
    fig_cost_build_up(claims, canterbury, rates, states, extent)
    fig_quartiles(area_cost, canterbury, rates, states, extent)
    fig_spread_fit(area_cost, canterbury, rates, states, weights, extent)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_ids=config.REALISATION_IDS,
        fit_states=config.FIT_STATES,
        weight_by_claims=config.WEIGHT_BY_CLAIMS,
        repair_rates=s2_config.REPAIR_RATES,
    )
