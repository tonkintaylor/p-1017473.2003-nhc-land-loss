"""Draw whether the Act pays some owners in full more often than others.

    uv run --frozen python src/scripts/landloss/loss/equity/gen_equity_by_value.py

Equity here means who the land cover is generous to, and the question the
figures answer is whether the Act pays wealthier owners their full repair cost
more often than others. The Act's land cover cap is built from the value of the
damaged land, so the same damage can be settled differently on a dear section
and a cheap one; a fixed land cap pays every claim its repair cost up to one
figure, whatever the land is worth. Claims are grouped by the capital value of
their property, a stand-in for the owner's wealth, and drawn in this order:

1. **Paid in full**: the share of each band's claims whose whole repair cost is
   within the cap, before the excess, with the average shortfall per dwelling
   of the claims left short.
2. **Paid in full by damage type**: the same, one panel per kind of damage.
   Landslides fall on hill suburbs and liquefaction on the flats, so a trend
   by value can be a trend by ground; within one kind of damage it cannot.
3. **Unpaid cost as a share of capital value**: the shortfall against what the
   property is worth, so the burden reads against the owner's means.
4. **Damage mix**: the kinds of damage in each band, the context for 1 and 2.
5. **What limits the settlement**: whether a claim is paid its repair cost,
   capped, or taken wholly by the excess.
6. **The change** in each claim's settlement under a fixed cap
   (``config.FIXED_CAP_NZD``), the claims paid more and those paid less in a
   panel each.
7. **Every cap scenario** (``config.CAP_SCENARIOS_NZD``): the change in the
   total each band is paid against the Act.

The files are numbered in that order. Where the Act and a fixed cap are
compared, the Act is the top panel or the left bar and the cap below it or to
its right, on the same scale.

The fixed cap is NHC's "replace" scheme as the loss viewer runs it: it stands
in for the land cover cap -- land value and the sub-caps -- so a claim is paid
its repair cost up to the cap, less the excess. Per dwelling, as the viewer
applies it (2026-10-14) and as NHC's scenarios state it: a claim's cap is the
fixed cap times its dwellings.

Per dwelling, both in banding and in what is drawn, so a block of flats is
read as its households rather than as one dear property.

All in dollars excluding GST, as the viewer works: the module settles
GST-inclusive, so the repair cost and the Act's cap are taken back out of GST
and the excess is applied after, as on the page. Capital value is the QV
roll's, summed over the claim property's rating units and indexed to the
common valuation date, as land value is (:func:`qv_capital_value_by_claim`).

**The claims are the loss viewer's** (:func:`load_claims`): each authority's
claims are the rows of its viewer CSV, so a claim is a property with damage
inside its own authority -- not one in a neighbour's box, and not one whose
only cost is the Canterbury average for liquefaction state None -- and its
damage type is the viewer's (:func:`damage_type`), ground that came down with
the claim's own wall counting as wall damage. Insurance penetration is not
applied: every damaged property is drawn.

Sensitive:
    Capital value comes from the QV roll. The figures draw summaries over
    thousands of claims and nothing per property, and nothing per property is
    written.

Needs loss step 1 and the viewer CSV (``gen_viewer_data.py``) over each extent
in ``config.EXTENTS``, exposure step 5's valuation links for each, and the QV
roll from T:, or from the local cache with ``TTDRIVE_SYNC_LOCAL_MODE=True``.
"""

import sys
from itertools import pairwise

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullFormatter, PercentFormatter

from landloss.domain.gst import GST_RATE
from landloss.exposure.land.land_value import load_base_rates
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.loss.policy import PolicySettings
from landloss.loss.qv_land_value import (
    QV_CAPITAL_VALUE_COLUMN,
    qv_capital_value_by_claim,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    valuation_links_path,
)
from scripts.landloss.loss.equity import config
from scripts.landloss.loss.steps.s0_land_cover_cap.s0_gen_land_cover_cap import (
    CAP_COLUMN,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    REPAIR_COST_COLUMN,
    settlement_path,
)
from scripts.landloss.loss.ui.gen_viewer_region import viewer_csv_path
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "loss" / "equity" / "fig"
DPI = 200
RULE = "-" * 72

DWELLINGS_COLUMN = "dwelling_count"
WALL_UDV_COLUMN = "retaining_wall_udv_incl_gst_nzd"
CV_PER_DWELLING = "cv_per_dwelling_nzd"
BAND = "cv_band"
# Per claim, excluding GST: the repair cost and the Act's land cover cap.
REPAIR = "repair_excl_gst_nzd"
ACT_CAP = "act_cap_excl_gst_nzd"
# Per dwelling, excluding GST.
ACT = "act_per_dwelling_nzd"
FIXED = "fixed_cap_per_dwelling_nzd"
CHANGE = "change_per_dwelling_nzd"
# What decided each claim's settlement, under the Act and the fixed cap.
ACT_LIMIT = "act_limit"
FIXED_LIMIT = "fixed_cap_limit"
# Whether the cap covers the whole repair cost, before the excess, and what it
# leaves unpaid per dwelling when it does not.
ACT_FULL = "act_paid_in_full"
FIXED_FULL = "fixed_cap_paid_in_full"
ACT_SHORT = "act_shortfall_per_dwelling_nzd"
FIXED_SHORT = "fixed_cap_shortfall_per_dwelling_nzd"
# The kind of damage, as the loss viewer types it.
DAMAGE_TYPE = "damage_type"
# A change smaller than this is a rounding difference, not a gain or a loss.
UNCHANGED_NZD = 1.0
# The whiskers run between these percentiles, not to 1.5 interquartile ranges:
# a settlement is right-skewed and a box plot's default calls a tenth of them
# outliers. Beyond them nothing is drawn; the note says so.
WHISKERS = (5, 95)

# Ink and chrome as the repair rate figures. The Act is the reference, so it
# wears ink, and the fixed cap the first series hue; gains and losses take the
# first two categorical slots, in the change figure and the scenarios alike.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SERIES = "#2a78d6"
ACT_COLOUR = INK_SECONDARY
FIXED_COLOUR = SERIES
GAIN = SERIES
LOSS = "#eb6834"
BOX_WIDTH = 0.42

# What limits a claim, in stacking order, and the colour each wears. Paid in
# full is the series hue; a cap binding takes the second slot, and the wall
# sub-cap, a cap of its own, the fourth; the excess taking everything is no
# payment at all, so it is muted.
PAID = "Repair cost paid"
CAPPED_VALUE = "Capped: land and wall value short of the repair"
CAPPED_SUB_CAP = "Capped: retaining wall sub-cap reached"
CAPPED_FIXED = "Capped at the fixed cap"
EXCESS = "Excess took it all"
LIMIT_COLOURS = {
    PAID: SERIES,
    CAPPED_VALUE: LOSS,
    CAPPED_SUB_CAP: "#eda100",
    CAPPED_FIXED: LOSS,
    EXCESS: BASELINE,
}
# A stacked segment narrower than this share is left unlabelled.
MIN_LABELLED_SHARE = 0.05

# The kinds of damage, as the loss viewer names them, in the order drawn, with
# the categorical slots the viewer gives them. A claim with more than one kind
# is a combination. Crossing-only claims are too few to read by band, so they
# are counted in the damage mix but given no panel of their own.
LIQUEFACTION = "Liquefaction only"
WALL = "Retaining wall only"
LANDSLIDE = "Landslide only"
CROSSING = "Culvert or bridge only"
COMBINATION = "Combination"
DAMAGE_COLOURS = {
    LIQUEFACTION: "#2a78d6",
    WALL: "#eb6834",
    LANDSLIDE: "#1baf7a",
    CROSSING: "#e87ba4",
    COMBINATION: "#eda100",
}
DAMAGE_PANELS = [LIQUEFACTION, LANDSLIDE, WALL, COMBINATION]
# A band with fewer claims than this in a damage panel is drawn, but marked as
# too few to read much into.
FEW_CLAIMS = 30
# The viewer CSV columns a claim's damage type is read from.
VIEWER_COLUMNS = [
    "claim_id",
    "has_liquefaction",
    "has_damaged_wall",
    "has_landslide",
    "crossing_repair_excl_gst",
]

# The councils' extents as a reader names them, for the figures' notes.
EXTENT_NAMES = {
    "wellington-city": "Wellington City",
    "lower-hutt": "Lower Hutt",
    "porirua": "Porirua",
    "upper-hutt": "Upper Hutt",
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
        # Labels carry dollar amounts, two of which would otherwise be read as
        # maths markup.
        "text.parse_math": False,
        "legend.frameon": False,
        "legend.labelcolor": INK_SECONDARY,
    }
)

DOLLARS = FuncFormatter(lambda value, _: f"${value:,.0f}")
SIGNED_DOLLARS = FuncFormatter(
    lambda value, _: (
        f"{'+' if value > 0 else '\N{MINUS SIGN}' if value < 0 else ''}"
        f"${abs(value):,.0f}"
    )
)


def signed_percent(value):
    """Return a share as a signed percentage, with a true minus sign.

    A share that rounds to nothing is 0%, not -0%.
    """
    if round(abs(value) * 100) == 0:
        return "0%"
    sign = "+" if value > 0 else "\N{MINUS SIGN}"
    return f"{sign}{abs(value):.0%}"


def band_labels(edges):
    """Return a label per capital value band, from its upper edges."""

    def short(value):
        return f"${value / 1e6:g}m" if value >= 1e6 else f"${value / 1e3:,.0f}k"

    labels = [f"Under {short(edges[0])}"]
    labels += [f"{short(lo)} to {short(hi)}" for lo, hi in pairwise(edges)]
    labels.append(f"Over {short(edges[-1])}")
    return labels


def cap_label(cap_nzd):
    """Return a cap as a short label, $100k."""
    return f"${cap_nzd / 1e3:,.0f}k"


def damage_type(viewer: pd.DataFrame) -> pd.Series:
    """Return each claim's kind of damage, as the loss viewer types it.

    Liquefaction is a land damage state worse than None, a wall a damaged
    existing wall (ground that came down with the claim's own wall counts as
    wall damage, not landslide), a landslide landslide ground, and a crossing a
    culvert or bridge with a repair cost. More than one kind is a combination.

    Args:
        viewer: Viewer CSV rows, carrying :data:`VIEWER_COLUMNS`.

    Returns:
        The kind per row, None where a row has no damage.
    """
    kinds = {
        LIQUEFACTION: viewer["has_liquefaction"].fillna(0) > 0,
        WALL: viewer["has_damaged_wall"].fillna(0) > 0,
        LANDSLIDE: viewer["has_landslide"].fillna(0) > 0,
        CROSSING: viewer["crossing_repair_excl_gst"].fillna(0) > 0,
    }
    count = sum(flag.astype(int) for flag in kinds.values())
    return pd.Series(
        np.select(
            [count > 1, *kinds.values()],
            [COMBINATION, *kinds.keys()],
            default=None,
        ),
        index=viewer.index,
    )


def load_claims(extents, world_id, realisation_id):
    """Return every claim over the extents with its capital value per dwelling.

    The claims are each authority's viewer CSV rows that carry damage, joined
    to their settlement: a claim in a neighbour's box, or one whose only cost
    is the liquefaction None average, is not one.

    Returns:
        One row per claim: the settlement columns, the extent it came from,
        its damage type and its capital value per dwelling.
    """
    print("Reading the QV rating roll (sensitive) ...", flush=True)
    roll = get_qv_rating_roll()
    base_rates = load_base_rates()
    frames = []
    for extent in extents:
        settled = pd.read_parquet(
            settlement_path(world_id, realisation_id, extent=extent)
        )
        capital = qv_capital_value_by_claim(
            roll, pd.read_parquet(valuation_links_path(extent=extent)), base_rates
        )[QV_CAPITAL_VALUE_COLUMN]
        viewer = pd.read_csv(
            viewer_csv_path(extent, world_id=world_id, realisation_id=realisation_id),
            usecols=VIEWER_COLUMNS,
        )
        viewer[DAMAGE_TYPE] = damage_type(viewer)
        viewer = viewer.dropna(subset=[DAMAGE_TYPE])
        settled = settled.merge(
            viewer[["claim_id", DAMAGE_TYPE]], on="claim_id", how="inner"
        )
        settled = settled.loc[settled[REPAIR_COST_COLUMN] > 0].copy()
        settled["extent"] = extent
        settled[CV_PER_DWELLING] = (
            settled["claim_id"].map(capital) / settled[DWELLINGS_COLUMN]
        )
        frames.append(settled)
    return pd.concat(frames, ignore_index=True)


def settled_per_dwelling(claims, cap_nzd, policy):
    """Return each claim's settlement per dwelling under a cap, excluding GST.

    Args:
        claims: The claims, carrying :data:`REPAIR` and :data:`ACT_CAP`.
        cap_nzd: A fixed cap in place of the Act's, or ``None`` for the Act.
        policy: The settings the excess is taken under.

    Returns:
        The settlement per dwelling, never below zero.
    """
    dwellings = claims[DWELLINGS_COLUMN].to_numpy(float)
    # A fixed cap is per dwelling; the Act's cap is the claim's own.
    cap = claims[ACT_CAP].to_numpy(float) if cap_nzd is None else cap_nzd * dwellings
    payable = np.minimum(claims[REPAIR].to_numpy(float), cap)
    excess = policy.excess_nzd(payable, dwellings)
    return np.maximum(payable - excess, 0.0) / dwellings


def settle_both_ways(claims, fixed_cap_nzd, policy):
    """Add each claim's settlement under the Act and the fixed cap, per dwelling.

    Excluding GST, as the loss viewer works: the repair cost and the Act's cap
    come out of GST and the excess is taken off after. Each claim also carries
    what decided its settlement under each.
    """
    claims = claims.assign(
        **{
            REPAIR: claims[REPAIR_COST_COLUMN] / (1 + GST_RATE),
            ACT_CAP: claims[CAP_COLUMN] / (1 + GST_RATE),
        }
    )
    act = settled_per_dwelling(claims, None, policy)
    fixed = settled_per_dwelling(claims, fixed_cap_nzd, policy)

    # Both GST-inclusive, as the module compares them.
    wall_limit = policy.retaining_wall_limit_nzd(claims[DWELLINGS_COLUMN].to_numpy())
    sub_capped = claims[WALL_UDV_COLUMN].to_numpy(float) > wall_limit
    act_capped = (claims[ACT_CAP] < claims[REPAIR]).to_numpy()
    act_limit = np.select(
        [act <= 0, ~act_capped, sub_capped],
        [EXCESS, PAID, CAPPED_SUB_CAP],
        default=CAPPED_VALUE,
    )
    fixed_limit = np.select(
        [
            fixed <= 0,
            (claims[REPAIR] <= fixed_cap_nzd * claims[DWELLINGS_COLUMN]).to_numpy(),
        ],
        [EXCESS, PAID],
        default=CAPPED_FIXED,
    )
    dwellings = claims[DWELLINGS_COLUMN].to_numpy(float)
    repair = claims[REPAIR].to_numpy(float)
    act_cap = claims[ACT_CAP].to_numpy(float)
    fixed_cap = fixed_cap_nzd * dwellings
    return claims.assign(
        **{
            ACT: act,
            FIXED: fixed,
            CHANGE: fixed - act,
            ACT_LIMIT: act_limit,
            FIXED_LIMIT: fixed_limit,
            ACT_FULL: ~act_capped,
            FIXED_FULL: repair <= fixed_cap,
            ACT_SHORT: np.maximum(repair - act_cap, 0.0) / dwellings,
            FIXED_SHORT: np.maximum(repair - fixed_cap, 0.0) / dwellings,
        }
    )


def describe(claims, labels):
    """Print each band's count, median settlement, and who gains and loses."""
    print(RULE)
    print("Per dwelling, excluding GST:")
    print(
        f"  {'band':<18}{'claims':>8}{'Act full':>10}{'cap full':>10}"
        f"{'Act median':>13}{'cap median':>13}{'gain':>7}{'lose':>7}"
    )
    for label, group in claims.groupby(BAND, observed=True):
        gain = (group[CHANGE] > UNCHANGED_NZD).mean()
        lose = (group[CHANGE] < -UNCHANGED_NZD).mean()
        print(
            f"  {label:<18}{len(group):>8,}{group[ACT_FULL].mean():>10.0%}"
            f"{group[FIXED_FULL].mean():>10.0%}{group[ACT].median():>13,.0f}"
            f"{group[FIXED].median():>13,.0f}{gain:>7.0%}{lose:>7.0%}"
        )
    print(f"  {len(claims):,} claims across {len(labels)} bands")


def draw_boxes(ax, groups, colour):
    """Draw one box per band, whiskers at the WHISKERS percentiles, no fliers.

    A band with nothing to draw is left empty rather than drawn as a line.
    """
    drawn = [(i, g) for i, g in enumerate(groups) if len(g)]
    if not drawn:
        return
    ax.boxplot(
        [g for _, g in drawn],
        positions=[i for i, _ in drawn],
        widths=BOX_WIDTH,
        whis=WHISKERS,
        showfliers=False,
        patch_artist=True,
        boxprops={"facecolor": colour, "edgecolor": colour, "alpha": 0.85},
        medianprops={"color": SURFACE, "linewidth": 2.2},
        whiskerprops={"color": colour, "linewidth": 1.2},
        capprops={"color": colour, "linewidth": 1.2},
    )


def label_boxes(ax, groups, fmt, *, stat=np.median):
    """Write each box's median, or another statistic, clear of its right edge."""
    for i, values in enumerate(groups):
        if not len(values):
            continue
        value = float(stat(values))
        ax.annotate(
            fmt(value),
            (i + BOX_WIDTH / 2, value),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            color=INK_SECONDARY,
            fontsize=7.5,
        )


def stacked_panels(rows, *, height=2.6, width=10.0, sharey=True):
    """Return a figure of panels one above another, the bands shared.

    Returns:
        The figure and its axes, top first.
    """
    fig, axes = plt.subplots(
        rows, 1, figsize=(width, height * rows + 0.4), sharex=True, sharey=sharey
    )
    return fig, np.atleast_1d(axes)


def band_axis(ax, labels, grouped):
    """Label the bands along the bottom panel, with no vertical grid."""
    ax.set_xticks(
        np.arange(len(labels)),
        [
            f"{label}\n{len(g):,} claims"
            for label, g in zip(labels, grouped, strict=True)
        ],
        fontsize=8,
    )
    ax.set_xlim(-0.5, len(labels) - 0.5)
    ax.set_xlabel("Capital value per dwelling, indexed to 2025-09")


def panel_title(ax, text):
    """Title a panel, smaller than the figure's."""
    ax.set_title(text, fontsize=10)
    ax.grid(axis="x", visible=False)


def finish(fig, title, note, out):
    """Title, note and write a figure, and say where it went."""
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.text(0.01, -0.01, note, color=INK_MUTED, fontsize=8, va="top")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote {out}")


def basis_note(claims, fixed_cap_nzd):
    """Return the lines every figure's note ends with: what was run, on what."""
    places = ", ".join(EXTENT_NAMES.get(e, e) for e in claims["extent"].unique())
    return (
        f"Every damaged property in {places}, one modelled event.\n"
        "A fixed cap replaces the land cover cap (land value and sub-caps): a claim "
        f"is paid its repair cost up to the cap ({cap_label(fixed_cap_nzd)} here), "
        "less the excess,\nthe cap per dwelling. Capital "
        "value from the QV roll, per dwelling; dollars excluding GST."
    )


BOX_NOTE = (
    f"Boxes run between the quartiles, the white line at the median; whiskers at "
    f"the {WHISKERS[0]}th and {WHISKERS[1]}th percentiles, nothing drawn beyond.\n"
)


def scenarios(fixed_cap_nzd):
    """Return the Act and the fixed cap: column, panel title and colour."""
    return (
        (ACT, "Under the Act", ACT_COLOUR),
        (FIXED, f"Under a fixed {cap_label(fixed_cap_nzd)} land cap", FIXED_COLOUR),
    )


def plot_change(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw how much each claim's settlement changes under the fixed cap.

    Most claims do not change at all -- the repair cost is under both caps -- so
    a box over every claim sits flat on zero. The claims paid more are drawn in
    the top panel and those paid less in the one below, each box labelled with
    its share of the band and its median.
    """
    cap = cap_label(fixed_cap_nzd)
    panels = (
        (CHANGE, 1, f"Claims paid more under a fixed {cap} land cap", GAIN),
        (CHANGE, -1, "Claims paid less", LOSS),
    )
    # Wider than the others: each box carries two lines of label beside it.
    fig, axes = stacked_panels(2, width=12.0, sharey=False)
    for ax, (column, sign, title, colour) in zip(axes, panels, strict=True):
        moved = [
            g.loc[sign * g[column] > UNCHANGED_NZD, column].to_numpy() for g in grouped
        ]
        draw_boxes(ax, moved, colour)
        for i, (v, g) in enumerate(zip(moved, grouped, strict=True)):
            if not len(v):
                continue
            median = float(np.median(v))
            ax.annotate(
                f"{len(v) / len(g):.0%} of claims\nmedian "
                f"{SIGNED_DOLLARS(median, None)}",
                (i + BOX_WIDTH / 2, median),
                xytext=(4, 0),
                textcoords="offset points",
                va="center",
                color=INK_SECONDARY,
                fontsize=7.5,
                linespacing=1.15,
            )
        ax.axhline(0, color=INK_MUTED, linewidth=1.0, zorder=1)
        ax.yaxis.set_major_formatter(SIGNED_DOLLARS)
        ax.set_ylabel("Change per dwelling")
        panel_title(ax, title)
    axes[0].set_ylim(bottom=0)
    axes[1].set_ylim(top=0)
    ax = axes[-1]
    band_axis(ax, labels, grouped)
    ax.set_xticks(
        ax.get_xticks(),
        [
            f"{label}\n{len(g):,} claims\n"
            f"{(g[CHANGE].abs() <= UNCHANGED_NZD).mean():.0%} unchanged"
            for label, g in zip(labels, grouped, strict=True)
        ],
        fontsize=8,
    )
    finish(
        fig,
        "Who gains and who loses under a fixed land cap, by property value",
        BOX_NOTE + basis_note(claims, fixed_cap_nzd),
        out,
    )


def paid_in_full(grouped, column):
    """Return each band's share of claims the cap pays in full."""
    return np.array([g[column].mean() if len(g) else np.nan for g in grouped])


def label_bars(ax, x, values, *, below=None):
    """Write each bar's share above it, and a note beneath that if given."""
    for i, (position, value) in enumerate(zip(x, values, strict=True)):
        if np.isnan(value):
            continue
        note = below[i] if below else ""
        ax.annotate(
            f"{value:.0%}" + (f"\n{note}" if note else ""),
            (position, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            color=INK_SECONDARY,
            fontsize=7.5,
            linespacing=1.1,
        )


def shortfall_note(group, full, short):
    """Return the average shortfall per dwelling of a band's claims left short."""
    left_short = group.loc[~group[full], short]
    return f"average short ${left_short.mean() / 1e3:,.0f}k" if len(left_short) else ""


def plot_paid_in_full(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw the share of each band's claims paid in full, the Act above."""
    fig, axes = stacked_panels(2)
    x = np.arange(len(labels))
    panels = (
        (ACT_FULL, ACT_SHORT, "Under the Act", ACT_COLOUR),
        (
            FIXED_FULL,
            FIXED_SHORT,
            f"Under a fixed {cap_label(fixed_cap_nzd)} land cap",
            FIXED_COLOUR,
        ),
    )
    for ax, (full, short, title, colour) in zip(axes, panels, strict=True):
        shares = paid_in_full(grouped, full)
        ax.bar(x, shares, 0.55, color=colour, edgecolor=SURFACE, linewidth=1.0)
        label_bars(
            ax, x, shares, below=[shortfall_note(g, full, short) for g in grouped]
        )
        ax.set_ylim(0, 1.2)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_ylabel("Claims paid in full")
        panel_title(ax, title)
    band_axis(axes[-1], labels, grouped)
    finish(
        fig,
        "Claims paid their full repair cost, by property value",
        "Paid in full: the cap covers the whole repair cost; every claim still pays "
        "the excess, which is left out here. Beneath each share: the average repair "
        "cost\nper dwelling the cap leaves unpaid on the band's claims it does not "
        "pay in full.\n" + basis_note(claims, fixed_cap_nzd),
        out,
    )


def plot_paid_in_full_by_type(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw the share paid in full, one panel per kind of damage, Act beside cap."""
    fig, axes = stacked_panels(len(DAMAGE_PANELS), height=2.2)
    x = np.arange(len(labels))
    width = 0.36
    for ax, kind in zip(axes, DAMAGE_PANELS, strict=True):
        within = [g[g[DAMAGE_TYPE] == kind] for g in grouped]
        for offset, full, colour in (
            (-width / 2, ACT_FULL, ACT_COLOUR),
            (width / 2, FIXED_FULL, FIXED_COLOUR),
        ):
            shares = paid_in_full(within, full)
            ax.bar(
                x + offset,
                np.nan_to_num(shares),
                width,
                color=colour,
                edgecolor=SURFACE,
                linewidth=1.0,
            )
            label_bars(ax, x + offset, shares)
        for i, w in enumerate(within):
            ax.annotate(
                f"{len(w):,} claims" + (" (few)" if 0 < len(w) < FEW_CLAIMS else ""),
                (i, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(0, -2),
                textcoords="offset points",
                ha="center",
                va="top",
                color=INK_MUTED,
                fontsize=7,
            )
        ax.set_ylim(0, 1.35)
        ax.set_yticks([0, 0.5, 1.0])
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax.set_ylabel("Paid in full")
        panel_title(ax, kind)
    axes[0].legend(
        handles=[
            Patch(facecolor=ACT_COLOUR, label="Under the Act"),
            Patch(
                facecolor=FIXED_COLOUR,
                label=f"Under a fixed {cap_label(fixed_cap_nzd)} land cap",
            ),
        ],
        loc="lower right",
        bbox_to_anchor=(1.0, 1.0),
        ncol=2,
        fontsize=8,
    )
    band_axis(axes[-1], labels, grouped)
    finish(
        fig,
        "Claims paid their full repair cost, by property value and kind of damage",
        "Within one kind of damage, a difference between bands is the cap's doing, "
        "not the ground's. Paid in full: the cap covers the whole repair cost, the "
        "excess left out.\nKinds of damage as the loss viewer types them: ground that "
        "came down with the claim's own wall counts as wall damage. A band with "
        f"fewer than {FEW_CLAIMS} claims is marked few.\n"
        + basis_note(claims, fixed_cap_nzd),
        out,
    )


def plot_damage_mix(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw the kinds of damage in each band, as 100% bars."""
    fig, axes = stacked_panels(1, height=3.2, width=12.0)
    ax = axes[0]
    x = np.arange(len(labels))
    bottom = np.zeros(len(labels))
    for kind, colour in DAMAGE_COLOURS.items():
        share = np.array(
            [(g[DAMAGE_TYPE] == kind).mean() if len(g) else 0.0 for g in grouped]
        )
        ax.bar(
            x,
            share,
            0.62,
            bottom=bottom,
            color=colour,
            edgecolor=SURFACE,
            linewidth=1.5,
            label=kind,
        )
        for i, s in enumerate(share):
            if s >= MIN_LABELLED_SHARE:
                ax.annotate(
                    f"{s:.0%}",
                    (i, bottom[i] + s / 2),
                    ha="center",
                    va="center",
                    color=SURFACE,
                    fontsize=7.5,
                )
        bottom += share
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.set_ylabel("Share of claims")
    panel_title(ax, "Kind of damage")
    handles, names = ax.get_legend_handles_labels()
    ax.legend(
        handles[::-1],
        names[::-1],
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        fontsize=8,
    )
    band_axis(ax, labels, grouped)
    finish(
        fig,
        "What kind of damage each band's claims have, by property value",
        "The context for the paid-in-full figures: landslides fall on hill suburbs "
        "and liquefaction on the flats, and the mix differs between bands.\n"
        "Kinds of damage as the loss viewer types them.\n"
        + basis_note(claims, fixed_cap_nzd),
        out,
    )


def plot_burden(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw the repair cost left unpaid against capital value, Act above."""
    fig, axes = stacked_panels(2)
    for ax, (column, title, colour) in zip(axes, scenarios(fixed_cap_nzd), strict=True):
        left_over = [
            (
                (g[REPAIR] / g[DWELLINGS_COLUMN] - g[column]) / g[CV_PER_DWELLING]
            ).to_numpy()
            for g in grouped
        ]
        # A log scale, since the shortfall runs from the excess on a dear house
        # to a sizeable share of a cheap one; nothing is left unpaid on a claim
        # whose excess is waived, so those are not drawn.
        left_over = [v[v > 0] for v in left_over]
        draw_boxes(ax, left_over, colour)
        label_boxes(ax, left_over, lambda v: f"{v:.2%}")
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v * 100:g}%"))
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_yticks([0.0001, 0.001, 0.01, 0.1])
        ax.set_ylabel("Unpaid, share of CV")
        panel_title(ax, title)
    band_axis(axes[-1], labels, grouped)
    finish(
        fig,
        "Repair cost left unpaid, against property value",
        BOX_NOTE
        + "Unpaid: the repair cost less the settlement, the excess included, over "
        "the capital value, per dwelling. Where a claim is paid its repair cost,\n"
        "the unpaid part is the excess alone, which is why the medians fall with "
        "value; the upper quartile and whisker are the claims a cap leaves short.\n"
        + basis_note(claims, fixed_cap_nzd),
        out,
    )


def draw_shares(ax, grouped, column, order):
    """Draw each band's claims as a 100% bar, split by what limited them."""
    x = np.arange(len(grouped))
    bottom = np.zeros(len(grouped))
    for limit in order:
        share = np.array(
            [(g[column] == limit).mean() if len(g) else 0.0 for g in grouped]
        )
        ax.bar(
            x,
            share,
            0.62,
            bottom=bottom,
            color=LIMIT_COLOURS[limit],
            edgecolor=SURFACE,
            linewidth=1.5,
        )
        for i, s in enumerate(share):
            if s >= MIN_LABELLED_SHARE:
                ax.annotate(
                    f"{s:.0%}",
                    (i, bottom[i] + s / 2),
                    ha="center",
                    va="center",
                    color=INK if limit == EXCESS else SURFACE,
                    fontsize=7.5,
                )
        bottom += share
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0))


def plot_limits(claims, grouped, labels, fixed_cap_nzd, out):
    """Draw what decided each band's settlements, the Act above, cap below."""
    panels = (
        (ACT_LIMIT, "Under the Act", [PAID, CAPPED_VALUE, CAPPED_SUB_CAP, EXCESS]),
        (
            FIXED_LIMIT,
            f"Under a fixed {cap_label(fixed_cap_nzd)} land cap",
            [PAID, CAPPED_FIXED, EXCESS],
        ),
    )
    fig, axes = stacked_panels(2, height=2.8, width=12.0)
    for ax, (column, title, order) in zip(axes, panels, strict=True):
        draw_shares(ax, grouped, column, order)
        ax.set_ylabel("Share of claims")
        panel_title(ax, title)
        # Each panel's own legend beside it, top category first as stacked.
        ax.legend(
            handles=[
                Patch(
                    facecolor=LIMIT_COLOURS[limit],
                    label=(
                        f"Capped at {cap_label(fixed_cap_nzd)}"
                        if limit == CAPPED_FIXED
                        else limit
                    ),
                )
                for limit in reversed(order)
            ],
            loc="center left",
            bbox_to_anchor=(1.01, 0.5),
            fontsize=8,
        )
    band_axis(axes[-1], labels, grouped)
    finish(
        fig,
        "What decides a claim's settlement, by property value",
        "Repair cost paid: the repair cost was under the cap and is paid less the "
        "excess. Capped: the cap was under the repair cost, so the owner bears the "
        "difference.\nUnder the Act a claim with no damaged land is capped at its "
        "wall's undepreciated value, below its repair cost by construction, so "
        "most wall-only claims read as capped.\n" + basis_note(claims, fixed_cap_nzd),
        out,
    )


def plot_scenarios(claims, grouped, labels, caps_nzd, policy, out):
    """Draw the change in each band's total settlement, one panel per fixed cap."""
    groups = [*grouped, claims]
    act_total = np.array([float((g[ACT] * g[DWELLINGS_COLUMN]).sum()) for g in groups])
    x = np.arange(len(groups))

    fig, axes = stacked_panels(len(caps_nzd), height=2.0)
    for ax, cap in zip(axes, caps_nzd, strict=True):
        totals = np.array(
            [
                float(
                    (settled_per_dwelling(g, cap, policy) * g[DWELLINGS_COLUMN]).sum()
                )
                for g in groups
            ]
        )
        change = totals / act_total - 1
        ax.bar(
            x,
            change,
            0.55,
            color=[GAIN if c >= 0 else LOSS for c in change],
            edgecolor=SURFACE,
            linewidth=1.0,
        )
        for position, value in zip(x, change, strict=True):
            ax.annotate(
                signed_percent(value),
                (position, value),
                xytext=(0, 3 if value >= 0 else -3),
                textcoords="offset points",
                ha="center",
                va="bottom" if value >= 0 else "top",
                color=INK_SECONDARY,
                fontsize=7.5,
            )
        ax.axhline(0, color=INK_MUTED, linewidth=1.0, zorder=1)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: signed_percent(v)))
        ax.set_ylabel("Change in total")
        panel_title(ax, f"Fixed {cap_label(cap)} land cap")
    axes[0].margins(y=0.22)
    # The last group is every claim together, set apart from the bands by a rule.
    for ax in axes:
        ax.axvline(len(groups) - 1.5, color=GRID, linewidth=1.0)
    axes[-1].set_xticks(
        x,
        [
            f"{label}\n{len(g):,} claims\n${total / 1e6:,.0f}m under the Act"
            for label, g, total in zip(
                [*labels, "All claims"], groups, act_total, strict=True
            )
        ],
        fontsize=8,
    )
    axes[-1].set_xlim(-0.5, len(groups) - 0.5)
    axes[-1].set_xlabel("Capital value per dwelling, indexed to 2025-09")
    places = ", ".join(EXTENT_NAMES.get(e, e) for e in claims["extent"].unique())
    finish(
        fig,
        "Change in the total settled under each fixed land cap, by property value",
        "Each bar: the total a band's claims are settled under the cap, against the "
        "total under the Act. Each cap replaces the land cover cap (land value and "
        "sub-caps),\nper dwelling, less the excess. Every damaged property in "
        f"{places}, one modelled event. Capital value from the QV roll, per "
        "dwelling; dollars excluding GST.",
        out,
    )


def main(*, extents, world_id, realisation_id, band_edges, fixed_cap_nzd, caps_nzd):
    """Band the claims by capital value and draw the seven figures."""
    claims = load_claims(extents, world_id, realisation_id)
    missing = claims[CV_PER_DWELLING].isna()
    print(f"  {missing.sum():,} of {len(claims):,} claims have no capital value")
    claims = claims.loc[~missing]
    policy = PolicySettings()
    claims = settle_both_ways(claims, fixed_cap_nzd, policy)
    labels = band_labels(band_edges)
    claims[BAND] = pd.cut(
        claims[CV_PER_DWELLING],
        [-np.inf, *band_edges, np.inf],
        labels=labels,
        right=False,
    )
    describe(claims, labels)
    grouped = [g for _, g in claims.groupby(BAND, observed=False)]
    cap = cap_label(fixed_cap_nzd).strip("$")
    # The damage mix is the same under any cap, so its name carries none.
    for name, draw in (
        (f"1-paid-in-full-by-capital-value-fixed-cap-{cap}", plot_paid_in_full),
        (
            f"2-paid-in-full-by-damage-type-by-capital-value-fixed-cap-{cap}",
            plot_paid_in_full_by_type,
        ),
        (
            f"3-unpaid-share-of-capital-value-by-capital-value-fixed-cap-{cap}",
            plot_burden,
        ),
        ("4-damage-mix-by-capital-value", plot_damage_mix),
        (f"5-settlement-limits-by-capital-value-fixed-cap-{cap}", plot_limits),
        (f"6-settlement-change-by-capital-value-fixed-cap-{cap}", plot_change),
    ):
        draw(claims, grouped, labels, fixed_cap_nzd, FIG_DIR / f"{name}.png")
    plot_scenarios(
        claims,
        grouped,
        labels,
        caps_nzd,
        policy,
        FIG_DIR / "7-cap-scenarios-by-capital-value.png",
    )


if __name__ == "__main__":
    main(
        extents=config.EXTENTS,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        band_edges=config.CV_BAND_EDGES_NZD,
        fixed_cap_nzd=config.FIXED_CAP_NZD,
        caps_nzd=config.CAP_SCENARIOS_NZD,
    )
