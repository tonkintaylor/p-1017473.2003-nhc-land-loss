"""Histograms of the QV land rates the tiers apply, their factors, and examples.

    uv run --frozen python src/scripts/landloss/loss/validations/gen_qv_average_rate.py

A property's **average rate** is its QV land value, indexed to the common
valuation date, over its whole area: the rate the land would be valued at if
every square metre were worth the same. The loss module does not value damaged
land at it. It spreads the value over three tiers stepping down from the house
(:mod:`landloss.loss.qv_land_value`), so each property has, beside its average:

- the **rate under the house**, ``R``, what landslide ground under the dwelling
  is valued at;
- the **rate around the house**, ``INSURED_RATIO`` x ``R``, on the rest of the
  insured land, what landslide ground off the dwelling is valued at;
- the **insured land's average rate**, the two together weighted by area, what
  liquefied ground is valued at.

Each rate is one figure of three panels on the same $/m2 axis, the histogram
stacked by hill or flat land (elevated flat counted as flat), by territorial
authority, and by the property's total area (``config.QV_RATE_AREA_BANDS_M2``).
How far the tiers move a rate off the average is its **correction factor**,
drawn for the liquefaction rate and the rate under the house. Two worked
examples show the tiers themselves: a valuer's 3,000 m2 section, and a typical
section built from the medians, each at the module's ratios.

Writes, to ``report/loss/qv-land-value/fig/``, over every claim property on the
roll in ``config.QV_RATE_EXTENTS``:

- ``qv-rate-<average|footprint|ring|insured>.png``: the four rates;
- ``qv-tier-factor-by-<landform|ta|area>.png``: the two factors, at the loss
  module's tier ratios;
- ``qv-tier-examples.png``: the two examples.

Sensitive:
    The rates and factors are derived from each property's QV land value. The
    figures hold counts per band and medians only, so no property's value can
    be read off them, and anything beyond the drawn range is counted in the end
    bins rather than drawn where it lies.

Needs exposure steps 2, 3 and 5 over each extent, and the QV roll from T:, or
from the local cache with ``TTDRIVE_SYNC_LOCAL_MODE=True``.
"""

import itertools
import sys

import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, NullFormatter

from landloss.exposure.land.extent import (
    AREA_COLUMN,
    CLAIM_ID_COLUMN,
    FOOTPRINT_AREA_COLUMN,
    PROPERTY_AREA_COLUMN,
)
from landloss.exposure.land.land_value import COMMON_VALUATION_DATE, load_base_rates
from landloss.exposure.land.landform import ELEVATED_FLAT, FLAT, HILL, LANDFORM_COLUMN
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.loss.qv_land_value import (
    INSURED_RATIO,
    MAX_UNINSURED_M2,
    QV_LAND_VALUE_COLUMN,
    UNINSURED_RATIO,
    footprint_rate,
    qv_land_value_by_claim,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
    land_value_path,
    valuation_links_path,
)
from scripts.landloss.exposure.steps.s3_dwellings_per_property.gen_dwellings_per_property import (
    address_to_claim_path,
)
from scripts.landloss.loss.validations import config
from scripts.landloss.paths import REPORT_DIR

# Dollar signs are money here, not mathtext.
plt.rcParams["text.parse_math"] = False

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FIG_DIR = REPORT_DIR / "loss" / "qv-land-value" / "fig"
RATE_STEM = "qv-rate"
FACTOR_STEM = "qv-tier-factor-by"
DPI = 200
RULE = "-" * 72
BINS = 48

TA_COLUMN = "territorial_authority"
RATE_COLUMN = "average_rate_nzd_per_m2"
FOOTPRINT_RATE_COLUMN = "footprint_rate_nzd_per_m2"
RING_RATE_COLUMN = "ring_rate_nzd_per_m2"
INSURED_RATE_COLUMN = "insured_rate_nzd_per_m2"
LIQUEFACTION_FACTOR = "liquefaction_factor"
FOOTPRINT_FACTOR = "footprint_factor"
AREA_BAND_COLUMN = "area_band"
ADDRESS_ID_COLUMN = "address_id"
FOOTPRINT_COLUMN = "footprint_m2"
INSURED_COLUMN = "insured_m2"

# The reference palette's categorical slots in order, and its blue ramp for the
# ordered area bands (steps 250 to 700), both checked with the dataviz
# validator on the light surface.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
AREA_RAMP = ["#86b6ef", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SURFACE = "#fcfcfb"
INK = "#1c1c1a"
MUTED = "#6a6a66"
GRID = "#e4e4e0"
# The tiers in the examples, darker nearer the house, from the blue ramp; and
# the two averages drawn across them.
TIER_COLOURS = {"footprint": "#184f95", "ring": "#3987e5", "outer": "#b7d3f6"}
INSURED_LINE = "#eb6834"

# The example a valuer reviewed (2026-10-13): a 3,000 m2 section worth $600,000,
# a 150 m2 house and 500 m2 more of insured land around it.
VALUER_EXAMPLE = {
    "name": "A valuer's example",
    "value": 600_000.0,
    "area": 3_000.0,
    "footprint": 150.0,
    "insured": 650.0,
}


def load_properties(extents):
    """Return each claim property on the roll: rate, factors, area, landform, TA.

    An authority's extent is its bounding box, so it takes in the edges of its
    neighbours; a property met in two extents is counted once, under the
    authority its addresses are in. The footprint and insured land are read as
    loss reads them: the claim's footprint, and its insured land summed.

    Args:
        extents: The extents to read, names from
            landloss.io.area_of_interest.EXTENTS.

    Returns:
        One row per claim property with a QV land value and an area, indexed by
        claim id.
    """
    print("Reading the QV rating roll (sensitive) ...", flush=True)
    roll = get_qv_rating_roll()
    base_rates = load_base_rates()
    frames = []
    for extent in extents:
        value = qv_land_value_by_claim(
            roll, pd.read_parquet(valuation_links_path(extent=extent)), base_rates
        )[QV_LAND_VALUE_COLUMN]
        areas = (
            pd.read_parquet(
                insured_land_path(extent=extent),
                columns=[
                    CLAIM_ID_COLUMN,
                    PROPERTY_AREA_COLUMN,
                    FOOTPRINT_AREA_COLUMN,
                    AREA_COLUMN,
                ],
            )
            .groupby(CLAIM_ID_COLUMN)
            .agg(
                **{
                    PROPERTY_AREA_COLUMN: (PROPERTY_AREA_COLUMN, "first"),
                    FOOTPRINT_COLUMN: (FOOTPRINT_AREA_COLUMN, "first"),
                    INSURED_COLUMN: (AREA_COLUMN, "sum"),
                }
            )
        )
        addresses = pd.read_parquet(
            land_value_path(extent=extent),
            columns=[ADDRESS_ID_COLUMN, TA_COLUMN, LANDFORM_COLUMN],
        ).merge(pd.read_parquet(address_to_claim_path(extent=extent)))
        # A property's landform and authority are its addresses' most common.
        by_claim = addresses.groupby(CLAIM_ID_COLUMN)[[TA_COLUMN, LANDFORM_COLUMN]].agg(
            lambda s: s.mode().iloc[0] if s.notna().any() else None
        )
        table = by_claim.join(areas, how="inner")
        table[QV_LAND_VALUE_COLUMN] = value.reindex(table.index)
        frames.append(table)
        print(
            f"  {extent}: {len(table):,} claim properties, {value.size:,} on the roll"
        )
    table = pd.concat(frames)
    table = table[~table.index.duplicated()]
    table = table.dropna(subset=[QV_LAND_VALUE_COLUMN, TA_COLUMN])
    table = table[(table[QV_LAND_VALUE_COLUMN] > 0) & (table[PROPERTY_AREA_COLUMN] > 0)]
    average = table[QV_LAND_VALUE_COLUMN] / table[PROPERTY_AREA_COLUMN]
    full = footprint_rate(
        table[QV_LAND_VALUE_COLUMN],
        table[FOOTPRINT_COLUMN],
        table[INSURED_COLUMN],
        table[PROPERTY_AREA_COLUMN],
    )
    footprint = table[FOOTPRINT_COLUMN].clip(lower=0)
    insured = np.maximum(table[INSURED_COLUMN], footprint)
    insured_rate = (
        full * (footprint + INSURED_RATIO * (insured - footprint))
    ) / insured.where(insured > 0)
    table[RATE_COLUMN] = average
    table[FOOTPRINT_RATE_COLUMN] = full
    table[RING_RATE_COLUMN] = INSURED_RATIO * full
    table[INSURED_RATE_COLUMN] = insured_rate
    table[FOOTPRINT_FACTOR] = full / average
    table[LIQUEFACTION_FACTOR] = insured_rate / average
    # Elevated flat is flat land standing above the valley floor: flat for this.
    table[LANDFORM_COLUMN] = table[LANDFORM_COLUMN].replace({ELEVATED_FLAT: FLAT})
    edges = [0, *config.QV_RATE_AREA_BANDS_M2, np.inf]
    table[AREA_BAND_COLUMN] = pd.cut(
        table[PROPERTY_AREA_COLUMN], edges, right=False, labels=area_labels(edges)
    )
    return table


def area_labels(edges):
    """Name each area band, as "under 500 m²", "500-800 m²" and "4,000 m² or more"."""
    inner = edges[1:-1]
    labels = [f"under {inner[0]:,.0f} m²"]
    labels += [f"{lo:,.0f}-{hi:,.0f} m²" for lo, hi in itertools.pairwise(inner)]
    return [*labels, f"{inner[-1]:,.0f} m² or more"]


def describe(table):
    """Print the average rate and the factors, overall and by each grouping."""
    print(RULE)
    print(
        f"Claim properties on the roll: {len(table):,}; tier ratios "
        f"{INSURED_RATIO:g} and {UNINSURED_RATIO:g}, outer tier counted to "
        f"{MAX_UNINSURED_M2:,.0f} m2"
    )
    for value in (
        RATE_COLUMN,
        FOOTPRINT_RATE_COLUMN,
        RING_RATE_COLUMN,
        INSURED_RATE_COLUMN,
        LIQUEFACTION_FACTOR,
        FOOTPRINT_FACTOR,
    ):
        print(f"\n{value}:")
        for column in (LANDFORM_COLUMN, TA_COLUMN, AREA_BAND_COLUMN):
            print(
                table.groupby(column, observed=True)[value]
                .describe(percentiles=[0.1, 0.5, 0.9])[["count", "10%", "50%", "90%"]]
                .round(2)
                .to_string()
            )


def stacked(ax, values, labels, groups, colours, span, fmt):
    """Draw a log-binned histogram stacked by group; return the legend handles.

    Args:
        ax: The axes to draw on.
        values: The value per property.
        labels: The group per property.
        groups: The groups, in stacking order.
        colours: A colour per group.
        span: The (low, high) range drawn; values beyond it count in the end
            bins, so no lone property stands out.
        fmt: Formats a value for the legend's medians.

    Returns:
        A legend handle per group, naming its count and median.
    """
    lo, hi = span
    edges = np.geomspace(lo, hi, BINS + 1)
    clipped = values.clip(lo, hi * 0.999)
    bottom = np.zeros(BINS)
    handles = []
    for group, colour in zip(groups, colours, strict=True):
        inside = labels == group
        counts, _ = np.histogram(clipped[inside], bins=edges)
        ax.bar(
            edges[:-1],
            counts,
            width=np.diff(edges),
            bottom=bottom,
            align="edge",
            color=colour,
            edgecolor=SURFACE,
            linewidth=0.8,
        )
        bottom += counts
        handles.append(
            Patch(
                color=colour,
                label=f"{group}: {int(inside.sum()):,} properties, "
                f"median {fmt(values[inside].median())}",
            )
        )
    # Headroom above the tallest bar, so the median's label clears it.
    top = bottom.max() * 1.1
    ax.set_ylim(0, top)
    overall = values.median()
    ax.axvline(overall, color=INK, lw=1, ls="--")
    ax.annotate(
        f"All properties' median {fmt(overall)}",
        (overall, top),
        xytext=(5, -3),
        textcoords="offset points",
        va="top",
        fontsize=8.5,
        color=INK,
    )
    ax.set_xscale("log")
    ax.set_xlim(lo, hi)
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_ylabel("Claim properties", color=INK)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK)
    return handles


def finish(fig, note, out):
    """Add the note under the figure and save it."""
    fig.patch.set_facecolor(SURFACE)
    fig.text(0.01, 0.01, note, fontsize=7.5, color=MUTED, va="bottom")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, facecolor=SURFACE)
    plt.close(fig)
    print(f"Wrote {out}")


def valued_on():
    """Return the common valuation date as "1 September 2025"."""
    date = pd.Timestamp(COMMON_VALUATION_DATE)
    return f"{date.day} {date:%B %Y}"


# The four rates, each one figure: its key, column, title, and what it values.
RATES = (
    (
        "average",
        RATE_COLUMN,
        "The property's average QV land rate: land value ÷ property area",
        "Before the tiers: damaged land is not valued at it.",
    ),
    (
        "footprint",
        FOOTPRINT_RATE_COLUMN,
        "The rate under the house, R",
        "What landslide ground under the dwelling is valued at.",
    ),
    (
        "ring",
        RING_RATE_COLUMN,
        f"The rate on the rest of the insured land, {INSURED_RATIO:g}R",
        "What landslide ground around the dwelling is valued at.",
    ),
    (
        "insured",
        INSURED_RATE_COLUMN,
        "The insured land's average rate: the house and the land around it",
        "What liquefied ground is valued at.",
    ),
)


def rate_figure(groupings, value, title, values_what, out):
    """Draw one rate as three histograms, stacked by each grouping in turn."""
    lo, hi = config.QV_RATE_RANGE_NZD_PER_M2
    fig, axes = plt.subplots(len(groupings), 1, figsize=(10, 13), sharex=True)
    for ax, letter, (by, rows, column, groups, colours) in zip(
        axes, "abc", groupings, strict=True
    ):
        handles = stacked(
            ax,
            rows[value],
            rows[column],
            groups,
            colours,
            (lo, hi),
            lambda v: f"${v:,.0f}/m²",
        )
        ax.legend(handles=handles, frameon=False, fontsize=8.5, loc="upper left")
        ax.set_title(f"({letter}) By {by}", loc="left", fontsize=10, color=INK)
    ticks = [
        t
        for t in (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000)
        if lo <= t <= hi
    ]
    axes[-1].set_xticks(ticks)
    axes[-1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    axes[-1].set_xlabel("$/m², excluding GST", color=INK)
    fig.suptitle(
        f"{title}, per claim property", x=0.01, ha="left", fontsize=12, color=INK
    )
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    finish(
        fig,
        f"{values_what} Each claim property's QV land value, indexed to "
        f"{valued_on()}, is spread over three tiers:\nthe house at R, the rest of "
        f"the insured land at {INSURED_RATIO:g}R and the rest of the section, up to "
        f"{MAX_UNINSURED_M2:,.0f} m², at {UNINSURED_RATIO:g}R, with R set so the "
        "tiers add back to the value.\n"
        f"Rates below ${lo:,.0f} or above ${hi:,.0f} are counted in the end bins. "
        "The same $/m² axis on every rate's figure. "
        f"Over {', '.join(config.QV_RATE_EXTENT_NAMES)}.",
        out,
    )


def typical_section(table):
    """Return a typical section: the median of each area, at the median rate.

    Rounded, so it is an invented section of typical size and value rather than
    any one property.
    """
    area = round(table[PROPERTY_AREA_COLUMN].median(), -1)
    footprint = round(table[FOOTPRINT_COLUMN].median(), -1)
    insured = round(
        np.maximum(table[INSURED_COLUMN], table[FOOTPRINT_COLUMN]).median(), -1
    )
    value = round(table[RATE_COLUMN].median() * area, -4)
    print(
        f"Typical section: {area:,.0f} m2, {footprint:,.0f} m2 house, "
        f"{insured:,.0f} m2 insured, worth ${value:,.0f}"
    )
    return {
        "name": "A typical section",
        "value": value,
        "area": area,
        "footprint": footprint,
        "insured": min(insured, area),
    }


def draw_example(
    ax, example, *, insured_ratio=INSURED_RATIO, uninsured_ratio=UNINSURED_RATIO
):
    """Draw the three tiers of an example as bars, rate against area."""
    value, area = example["value"], example["area"]
    footprint, insured = example["footprint"], example["insured"]
    ring, outer = insured - footprint, area - insured
    counted = min(outer, MAX_UNINSURED_M2)
    full = value / (footprint + insured_ratio * ring + uninsured_ratio * counted)
    average = value / area
    insured_rate = full * (footprint + insured_ratio * ring) / insured
    tiers = (
        ("footprint", "Under the house", footprint, full),
        ("ring", "Rest of the insured land", ring, insured_ratio * full),
        ("outer", "Rest of the section", outer, uninsured_ratio * full),
    )
    left = 0.0
    for key, label, width, rate in tiers:
        ax.bar(
            left,
            rate,
            width=width,
            align="edge",
            color=TIER_COLOURS[key],
            edgecolor=SURFACE,
            linewidth=1.2,
        )
        narrow = width < 0.15 * area
        ax.annotate(
            f"{label}\n{width:,.0f} m² at ${rate:,.0f}/m²\n= ${width * rate:,.0f}",
            (left + (width if narrow else width / 2), rate),
            xytext=(5, -36) if narrow else (0, 4),
            textcoords="offset points",
            ha="left" if narrow else "center",
            va="bottom",
            fontsize=8,
            color=INK,
            # The average lines pass behind a label rather than through it.
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1.5},
            zorder=5,
        )
        left += width
    ax.axhline(average, color=INK, lw=1, ls="--")
    ax.annotate(
        f"Section average ${average:,.0f}/m²",
        (area, average),
        xytext=(-4, 4),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=INK,
    )
    ax.axhline(insured_rate, color=INSURED_LINE, lw=1.4)
    ax.annotate(
        f"Insured land's average ${insured_rate:,.0f}/m² "
        f"({insured_rate / average:.1f}x the section average), for liquefaction",
        (area, insured_rate),
        xytext=(-4, 4),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=INK,
    )
    ax.set_xlim(0, area)
    ax.set_ylim(0, full * 1.25)
    ax.set_xlabel("Area of the section (m²)", color=INK)
    ax.set_ylabel("Land value per m², excluding GST", color=INK)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelcolor=INK)
    ax.set_title(
        f"{example['name']}: ${value:,.0f} of land on {area:,.0f} m², a "
        f"{footprint:,.0f} m² house and {ring:,.0f} m² more of insured land;\n"
        f"${full * footprint:,.0f} ({full * footprint / value:.0%}) of its value "
        "under the house",
        loc="left",
        fontsize=10,
        color=INK,
    )


def example_figure(examples, out):
    """Draw each example's tiers, a panel each."""
    fig, axes = plt.subplots(len(examples), 1, figsize=(11, 5.2 * len(examples)))
    for ax, example in zip(np.atleast_1d(axes), examples, strict=True):
        draw_example(ax, example)
    fig.suptitle(
        "The three land tiers on two sections",
        x=0.01,
        ha="left",
        fontsize=12,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1), h_pad=3)
    finish(
        fig,
        "Each bar is a tier: its width the tier's area, its height the rate per m² "
        "it is valued at. The house at R, the rest of the insured land at "
        f"{INSURED_RATIO:g}R and\nthe rest of the section, up to "
        f"{MAX_UNINSURED_M2:,.0f} m², at {UNINSURED_RATIO:g}R, with R set so the "
        "three add back to the land value. The typical section is the median "
        "area,\nhouse and insured land of the claim properties, at the median "
        f"average rate, over {', '.join(config.QV_RATE_EXTENT_NAMES)}. "
        "Excluding GST.",
        out,
    )


def factor_figure(table, column, groups, colours, out, *, by):
    """Draw the two correction factors' histograms stacked by ``column``."""
    span = config.QV_FACTOR_RANGE
    fig, axes = plt.subplots(2, 1, figsize=(10, 9.4), sharex=True)
    panels = (
        (
            LIQUEFACTION_FACTOR,
            (
                "(a) Liquefaction damage: the insured land's average rate ÷ the "
                "property's average"
            ),
        ),
        (
            FOOTPRINT_FACTOR,
            (
                "(b) Landslide damage under the house: the rate under the house, R, ÷ "
                "the property's average"
            ),
        ),
    )
    for ax, (value, title) in zip(axes, panels, strict=True):
        handles = stacked(
            ax,
            table[value],
            table[column],
            groups,
            colours,
            span,
            lambda v: f"{v:,.2f}x",
        )
        ax.legend(handles=handles, frameon=False, fontsize=8.5, loc="upper right")
        ax.set_title(title, loc="left", fontsize=10, color=INK)
    ticks = [t for t in (1, 1.5, 2, 3, 5, 10, 20, 50, 100) if span[0] <= t <= span[1]]
    axes[-1].set_xticks(ticks)
    axes[-1].xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    axes[-1].set_xlabel(
        "Correction factor: the rate damaged land is valued at, as a multiple of "
        "the property's average rate",
        color=INK,
    )
    fig.suptitle(
        f"How far the land tiers lift each claim property's rate, by {by}",
        x=0.01,
        ha="left",
        fontsize=11.5,
        color=INK,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    finish(
        fig,
        f"Tier ratios {INSURED_RATIO:g} and {UNINSURED_RATIO:g}: the insured land "
        f"around the house at {INSURED_RATIO:g}R and the rest of the section, up to "
        f"{MAX_UNINSURED_M2:,.0f} m², at {UNINSURED_RATIO:g}R, with R set so the "
        "tiers add back to the QV land value.\nLandslide damage around the house "
        f"takes {INSURED_RATIO:g} x factor (b). Factors below {span[0]:g}x or above "
        f"{span[1]:g}x are counted in the end bins. "
        f"Over {', '.join(config.QV_RATE_EXTENT_NAMES)}.",
        out,
    )


def main(*, extents):
    """Draw the four rates, the correction factors, and the examples."""
    table = load_properties(extents)
    describe(table)
    print(RULE)
    landforms = {HILL: "Hill", FLAT: "Flat"}
    authorities = table[TA_COLUMN].value_counts().index[: len(CATEGORICAL)].tolist()
    bands = table[AREA_BAND_COLUMN].cat.categories.tolist()
    groupings = (
        (
            "landform",
            "hill or flat land",
            table.assign(**{LANDFORM_COLUMN: table[LANDFORM_COLUMN].map(landforms)}),
            LANDFORM_COLUMN,
            list(landforms.values()),
            CATEGORICAL[:2],
        ),
        (
            "ta",
            "territorial authority",
            table[table[TA_COLUMN].isin(authorities)],
            TA_COLUMN,
            authorities,
            CATEGORICAL[: len(authorities)],
        ),
        (
            "area",
            "the property's total area",
            table,
            AREA_BAND_COLUMN,
            bands,
            AREA_RAMP[: len(bands)],
        ),
    )
    for key, value, title, values_what in RATES:
        rate_figure(
            [grouping[1:] for grouping in groupings],
            value,
            title,
            values_what,
            FIG_DIR / f"{RATE_STEM}-{key}.png",
        )
    for key, by, rows, column, groups, colours in groupings:
        factor_figure(
            rows, column, groups, colours, FIG_DIR / f"{FACTOR_STEM}-{key}.png", by=by
        )
    example_figure(
        [VALUER_EXAMPLE, typical_section(table)], FIG_DIR / "qv-tier-examples.png"
    )


if __name__ == "__main__":
    main(extents=config.QV_RATE_EXTENTS)
