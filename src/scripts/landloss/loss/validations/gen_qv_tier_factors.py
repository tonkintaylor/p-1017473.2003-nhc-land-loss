"""Show how the three land tiers correct each property's average QV rate.

    uv run --frozen python src/scripts/landloss/loss/validations/gen_qv_tier_factors.py

The loss module values damaged land from each property's own QV land value,
spread over three tiers (:mod:`landloss.loss.qv_land_value`): the building
footprint at the full rate ``R``, the rest of the insured land at half of it,
and the uninsured remainder at 0.15 of it. The plain alternative would be the
property's average rate, its land value over its area. This draws how far the
tiers move the rate away from that average -- the **correction factor** -- per
claim property:

- **liquefaction factor**: the insured land's average rate over the property's
  average rate, what liquefied ground is valued at;
- **footprint factor**: ``R`` over the average, landslide ground under the house;
- **ring factor**: ``0.5 R`` over the average, landslide ground off the house.

A section the insured land covers wholly has no outer tier to take value, so its
liquefaction factor is about 1; a large section with a small insured area rises
well above it. The factors are rates before GST at the common valuation date;
GST and the land value sensitivity scale every tier alike, so they do not move
a factor.

Writes, for the extent in ``config.QV_TIER_EXTENT``:

- ``report/loss/qv-land-value/fig/qv-tier-factors<suffix>.png``: the tiers on a
  worked example, the liquefaction factor against how much of the property is
  insured, the factors by authority, and suburb medians. Summaries only, so it
  may go in the report.
- ``temp/loss/qv-tier-factors/``: ``qv-tier-factors-by-suburb<suffix>`` as CSV
  and geoparquet (medians), the per-property layer when
  ``config.QV_TIER_WRITE_PROPERTY_LAYER`` is set, and a QGIS project
  ``qv-tier-factors<suffix>.qgs`` styling both by the liquefaction factor;
  and, when ``config.QV_TIER_WRITE_TIER_LAYER`` is set, the tier layer: each
  property cut into its footprint, the rest of its insured land and its
  uninsured remainder, each with the QV rate per m² it is valued at, before
  GST. The pieces tile the property and their rates times their areas add back
  to its QV land value.

Sensitive:
    The per-property and tier layers carry rates derived from each property's QV land
    value, which is close to the roll re-tabulated. It stays under ``temp/``
    (gitignored), is not shared, and is destroyed with the roll at the end of the
    project (:mod:`landloss.io.qv_rating_roll`). The suburb layer, the CSV and
    the figure hold medians over at least
    ``config.QV_TIER_MIN_SUBURB_PROPERTIES`` properties, and the figure draws
    properties as a density, not as points; its worked example is invented.

Needs exposure step 5 run over the extent since 2026-10-11 (the insured land's
footprint area and the valuation links), and the QV roll from T:, or from the
local cache with ``TTDRIVE_SYNC_LOCAL_MODE=True``.
"""

import sys

import geopandas as gpd
import matplotlib as mpl

mpl.use("Agg")  # non-interactive: this script only writes PNGs

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import NullFormatter

from landloss.exposure.land.extent import (
    AREA_COLUMN,
    CLAIM_ID_COLUMN,
    FOOTPRINT_AREA_COLUMN,
    PROPERTY_AREA_COLUMN,
    SUBURB_COLUMN,
    build_claim_properties,
)
from landloss.exposure.land.land_value import COMMON_VALUATION_DATE, load_base_rates
from landloss.io.area_of_interest import extent_suffix, get_study_areas
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.io.readers import get_nz_property_boundaries
from landloss.loss.qv_land_value import (
    INSURED_RATIO,
    MAX_UNINSURED_M2,
    QV_LAND_VALUE_COLUMN,
    UNINSURED_RATIO,
    footprint_rate,
    qv_land_value_by_claim,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    fetch_extent,
    footprints_path,
    insured_land_path,
    land_value_path,
    valuation_links_path,
)
from scripts.landloss.hazard.landslide.validations.qgis import (
    gen_landslide_qgis_project as landslide,
)
from scripts.landloss.loss.validations import config
from scripts.landloss.paths import REPORT_DIR, TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = TEMP_DIR / "loss" / "qv-tier-factors"
FIG_DIR = REPORT_DIR / "loss" / "qv-land-value" / "fig"
STEM = "qv-tier-factors"
NZTM = 2193
DPI = 200
RULE = "-" * 72

TA_COLUMN = "territorial_authority"
AVERAGE_RATE_COLUMN = "average_rate_nzd_per_m2"
FULL_RATE_COLUMN = "footprint_rate_nzd_per_m2"
INSURED_RATE_COLUMN = "insured_rate_nzd_per_m2"
INSURED_SHARE_COLUMN = "insured_share"
LIQUEFACTION_FACTOR = "liquefaction_factor"
FOOTPRINT_FACTOR = "footprint_factor"
RING_FACTOR = "ring_factor"
# The tier layer's columns: which tier a piece is, and its rate per m2.
TIER_COLUMN = "tier"
TIER_RATE_COLUMN = "rate_nzd_per_m2"
FACTORS = {
    LIQUEFACTION_FACTOR: "Liquefaction: insured land's average",
    FOOTPRINT_FACTOR: "Landslide under the house: R",
    RING_FACTOR: f"Landslide off the house: {INSURED_RATIO:g}R",
}

# The worked example the tier panel draws: invented, so nothing of the roll is in
# it, and the one in the loss module's method note.
EXAMPLE = {"value": 600_000.0, "area": 3_000.0, "footprint": 150.0, "insured": 800.0}

# The factor bands the QGIS layers are drawn in: pale near 1, darker as the tiers
# move the rate further above the property's average.
FACTOR_BREAKS = [0.0, 0.95, 1.05, 1.15, 1.3, 1.5, 2.0, 3.0, 1000.0]
# How many suburbs the suburb panel names at each end.
LABELLED_SUBURBS = 8

TIER_COLOURS = {"footprint": "#b2182b", "ring": "#ef8a62", "outer": "#fddbc7"}
FACTOR_COLOURS = {
    LIQUEFACTION_FACTOR: "#2166ac",
    FOOTPRINT_FACTOR: "#b2182b",
    RING_FACTOR: "#ef8a62",
}


def tier_factors(insured, qv_value):
    """Return each claim property's tier rates and correction factors.

    Args:
        insured: Exposure step 5's insured land, one row per claim.
        qv_value: The indexed QV land value per claim.

    Returns:
        One row per claim on the roll, indexed by claim id.
    """
    claims = insured.drop_duplicates(CLAIM_ID_COLUMN).set_index(CLAIM_ID_COLUMN)
    value = claims.index.map(qv_value).astype(float)
    table = pd.DataFrame(
        {
            QV_LAND_VALUE_COLUMN: value,
            "property_m2": claims[PROPERTY_AREA_COLUMN].astype(float),
            "insured_m2": claims[AREA_COLUMN].astype(float),
            "footprint_m2": claims[FOOTPRINT_AREA_COLUMN].astype(float),
            SUBURB_COLUMN: claims[SUBURB_COLUMN],
        },
        index=claims.index,
    ).dropna(subset=[QV_LAND_VALUE_COLUMN])
    table = table[(table[QV_LAND_VALUE_COLUMN] > 0) & (table["property_m2"] > 0)]
    full = footprint_rate(
        table[QV_LAND_VALUE_COLUMN],
        table["footprint_m2"],
        table["insured_m2"],
        table["property_m2"],
    )
    footprint = table["footprint_m2"].clip(lower=0)
    insured_m2 = np.maximum(table["insured_m2"], footprint)
    insured_rate = (
        full
        * (footprint + INSURED_RATIO * (insured_m2 - footprint))
        / insured_m2.where(insured_m2 > 0)
    )
    average = table[QV_LAND_VALUE_COLUMN] / table["property_m2"]
    table[AVERAGE_RATE_COLUMN] = average
    table[FULL_RATE_COLUMN] = full
    table[INSURED_RATE_COLUMN] = insured_rate
    table[INSURED_SHARE_COLUMN] = (insured_m2 / table["property_m2"]).clip(upper=1)
    table[LIQUEFACTION_FACTOR] = insured_rate / average
    table[FOOTPRINT_FACTOR] = full / average
    table[RING_FACTOR] = INSURED_RATIO * full / average
    return table.dropna(subset=[LIQUEFACTION_FACTOR])


def authority_of(insured, index):
    """Return the territorial authority each claim's insured land stands in."""
    claims = insured.drop_duplicates(CLAIM_ID_COLUMN).set_index(CLAIM_ID_COLUMN)
    points = gpd.GeoDataFrame(
        geometry=claims.geometry.representative_point(), crs=claims.crs
    )
    areas = get_study_areas(claims.crs)[["name", "geometry"]]
    joined = gpd.sjoin(points, areas, how="left", predicate="within")
    named = joined.loc[~joined.index.duplicated(), "name"]
    return named.reindex(index).fillna("Outside the study area")


def by_suburb(factors, min_properties):
    """Return the median factors per suburb with enough properties."""
    table = (
        factors.groupby([TA_COLUMN, SUBURB_COLUMN])
        .agg(
            properties=(LIQUEFACTION_FACTOR, "size"),
            median_liquefaction_factor=(LIQUEFACTION_FACTOR, "median"),
            median_footprint_factor=(FOOTPRINT_FACTOR, "median"),
            median_ring_factor=(RING_FACTOR, "median"),
            median_insured_share=(INSURED_SHARE_COLUMN, "median"),
        )
        .reset_index()
    )
    return table[table["properties"] >= min_properties].reset_index(drop=True)


def describe(factors):
    """Print the factors overall and by insured share."""
    print(RULE)
    print(f"Claim properties on the roll: {len(factors):,}")
    for column, label in FACTORS.items():
        q = factors[column].quantile([0.1, 0.5, 0.9])
        print(
            f"  {label:<38} median {q[0.5]:.2f}, "
            f"10th to 90th percentile {q[0.1]:.2f} to {q[0.9]:.2f}"
        )
    bands = pd.cut(
        factors[INSURED_SHARE_COLUMN],
        [0, 0.5, 0.7, 0.9, 0.99, 1.0],
        labels=["under 50%", "50-70%", "70-90%", "90-99%", "99% or more"],
        include_lowest=True,
    )
    print("Liquefaction factor by how much of the property is insured:")
    print(
        factors.groupby(bands, observed=True)[LIQUEFACTION_FACTOR]
        .agg(["size", "median"])
        .round(2)
        .to_string()
    )


def draw_example(ax):
    """Draw the three tiers of the worked example, rate against area."""
    value, area = EXAMPLE["value"], EXAMPLE["area"]
    footprint, insured = EXAMPLE["footprint"], EXAMPLE["insured"]
    ring, outer = insured - footprint, area - insured
    full = value / (footprint + INSURED_RATIO * ring + UNINSURED_RATIO * outer)
    average = value / area
    tiers = (
        ("footprint", "Footprint", footprint, full),
        ("ring", "Rest of the insured land", ring, INSURED_RATIO * full),
        ("outer", "Uninsured remainder", outer, UNINSURED_RATIO * full),
    )
    left = 0.0
    for key, label, width, rate in tiers:
        ax.bar(
            left,
            rate,
            width=width,
            align="edge",
            color=TIER_COLOURS[key],
            edgecolor="white",
        )
        ax.annotate(
            f"{label}\n{width:,.0f} m² at ${rate:,.0f}/m²",
            # The footprint is a narrow bar, so its label sits to its right.
            (left + (width if width < 0.1 * area else width / 2), rate),
            xytext=(4, -24) if width < 0.1 * area else (0, 4),
            textcoords="offset points",
            ha="left" if width < 0.1 * area else "center",
            va="bottom",
            fontsize=8,
        )
        left += width
    ax.axhline(average, color="k", lw=1, ls="--")
    ax.annotate(
        f"Property average ${average:,.0f}/m²",
        (area, average),
        xytext=(-4, 4),
        textcoords="offset points",
        ha="right",
        fontsize=8,
    )
    insured_rate = full * (footprint + INSURED_RATIO * ring) / insured
    ax.axhline(insured_rate, color=FACTOR_COLOURS[LIQUEFACTION_FACTOR], lw=1.2)
    ax.annotate(
        f"Insured land's average ${insured_rate:,.0f}/m² "
        f"= {insured_rate / average:.2f}x the property average",
        (area, insured_rate),
        xytext=(-4, 4),
        textcoords="offset points",
        ha="right",
        fontsize=8,
        color=FACTOR_COLOURS[LIQUEFACTION_FACTOR],
    )
    ax.set_xlim(0, area)
    ax.set_ylim(0, full * 1.3)
    ax.set_xlabel("Area of the property (m²)")
    ax.set_ylabel("Land value per m², before GST")
    ax.set_title(
        f"(a) The three tiers on an example: ${value:,.0f} of land, {area:,.0f} m²,\n"
        f"a {footprint:,.0f} m² house and {insured:,.0f} m² insured; "
        "the tiers add back to the value",
        fontsize=10,
    )


def plot(factors, suburbs, out, *, title):
    """Draw the four panel figure."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    ax_example, ax_share, ax_ta, ax_sub = axes.ravel()

    draw_example(ax_example)

    # (b) A density rather than points: one point per property would draw the
    # roll's records.
    share = factors[INSURED_SHARE_COLUMN].to_numpy()
    factor = np.log10(factors[LIQUEFACTION_FACTOR].to_numpy())
    hexes = ax_share.hexbin(
        share,
        factor,
        gridsize=45,
        extent=(0, 1, np.log10(0.8), np.log10(4)),
        bins="log",
        mincnt=3,
        cmap="viridis",
    )
    fig.colorbar(hexes, ax=ax_share, label="Properties per cell")
    bins = np.linspace(0, 1, 21)
    centres = (bins[:-1] + bins[1:]) / 2
    medians = (
        factors.groupby(pd.cut(factors[INSURED_SHARE_COLUMN], bins), observed=False)[
            LIQUEFACTION_FACTOR
        ]
        .median()
        .to_numpy()
    )
    ax_share.plot(centres, np.log10(medians), "w-", lw=2.5)
    ax_share.plot(centres, np.log10(medians), "k-", lw=1.2, label="Median")
    ax_share.axhline(0, color="k", lw=0.6, ls=":")
    ticks = [0.8, 1, 1.25, 1.5, 2, 3, 4]
    ax_share.set_yticks(np.log10(ticks), [f"{t:g}x" for t in ticks])
    ax_share.set_xlabel("Share of the property that is insured land")
    ax_share.set_ylabel("Liquefaction factor (log)")
    ax_share.legend(loc="upper right", fontsize=8)
    ax_share.set_title(
        "(b) The less of the section is insured, the more the tiers\n"
        "raise the rate liquefied land is valued at",
        fontsize=10,
    )

    # (c) The three factors by authority.
    authorities = sorted(factors[TA_COLUMN].unique())
    width = 0.25
    for i, (column, label) in enumerate(FACTORS.items()):
        data = [
            factors.loc[factors[TA_COLUMN] == ta, column].to_numpy()
            for ta in authorities
        ]
        positions = np.arange(len(authorities)) + (i - 1) * width
        box = ax_ta.boxplot(
            data,
            positions=positions,
            widths=width * 0.85,
            whis=(10, 90),
            showfliers=False,
            patch_artist=True,
            medianprops={"color": "k"},
        )
        for patch in box["boxes"]:
            patch.set_facecolor(FACTOR_COLOURS[column])
            patch.set_alpha(0.8)
        ax_ta.plot([], [], "s", color=FACTOR_COLOURS[column], label=label)
    counts = factors[TA_COLUMN].value_counts()
    ax_ta.set_xticks(
        np.arange(len(authorities)),
        [f"{ta}\nn={counts[ta]:,}" for ta in authorities],
    )
    ax_ta.axhline(1, color="k", lw=0.8)
    ax_ta.set_yscale("log")
    ax_ta.set_yticks(
        [0.5, 0.75, 1, 1.5, 2, 3, 4], ["0.5", "0.75", "1", "1.5", "2", "3", "4"]
    )
    ax_ta.yaxis.set_minor_formatter(NullFormatter())
    ax_ta.set_ylabel("Factor on the property's average rate (log)")
    ax_ta.legend(loc="upper left", fontsize=8)
    ax_ta.set_title(
        "(c) The factors by authority: box the middle half, whiskers 10th to 90th",
        fontsize=10,
    )

    # (d) Suburb medians, the highest and lowest.
    ranked = suburbs.sort_values("median_liquefaction_factor")
    shown = pd.concat(
        [ranked.head(LABELLED_SUBURBS), ranked.tail(LABELLED_SUBURBS)]
    ).drop_duplicates()
    y = np.arange(len(shown))
    ax_sub.barh(
        y,
        shown["median_liquefaction_factor"] - 1,
        left=1,
        color=FACTOR_COLOURS[LIQUEFACTION_FACTOR],
    )
    ax_sub.set_yticks(
        y,
        [
            f"{row[SUBURB_COLUMN]} ({row['properties']:,})"
            for _, row in shown.iterrows()
        ],
        fontsize=8,
    )
    ax_sub.axvline(1, color="k", lw=0.8)
    ax_sub.set_xlabel("Median liquefaction factor")
    ax_sub.set_title(
        f"(d) Suburbs with the lowest and highest median factor\n"
        f"(at least {config.QV_TIER_MIN_SUBURB_PROPERTIES} properties; "
        "properties in brackets)",
        fontsize=10,
    )

    fig.suptitle(title, fontsize=12)
    fig.text(
        0.01,
        -0.01,
        f"Each property's QV land value, indexed to {COMMON_VALUATION_DATE}, spread "
        f"over three tiers: the footprint at R, the rest of the insured land at "
        f"{INSURED_RATIO:g}R and the uninsured remainder at {UNINSURED_RATIO:g}R "
        "(placeholders, T-153).\nFactor: the rate damaged land is valued at, over "
        "the property's land value divided by its area. Properties on the roll "
        "only; before GST.",
        fontsize=8,
        color="#52514e",
    )
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def tier_pieces(insured, footprints, properties, factors):
    """Return each claim property cut into its three tiers, each with its rate.

    The footprint is exposure's merged buildings; the ring is the insured land
    less the footprint; the outer tier is the property less the insured land.

    Args:
        insured: Exposure step 5's insured land, one polygon per claim.
        footprints: Exposure step 5's footprints, one per claim.
        properties: The claim properties, carrying the claim id.
        factors: :func:`tier_factors`, for each claim's full rate.

    Returns:
        One row per claim and tier: the claim, the tier, its rate per m² before
        GST, its area, and its polygon.
    """
    claims = factors.index
    full = factors[FULL_RATE_COLUMN]
    land = insured.drop_duplicates(CLAIM_ID_COLUMN).set_index(CLAIM_ID_COLUMN)
    land = land.geometry.reindex(claims)
    built = footprints.set_index(CLAIM_ID_COLUMN).geometry.reindex(claims)
    whole = properties.set_index(CLAIM_ID_COLUMN).geometry.reindex(claims)
    has_built = built.notna()
    ring = land.copy()
    ring[has_built] = land[has_built].difference(built[has_built])
    outer = whole.difference(land)
    pieces = []
    for tier, shapes, ratio in (
        ("footprint", built, 1.0),
        ("rest of the insured land", ring, INSURED_RATIO),
        ("uninsured remainder", outer, UNINSURED_RATIO),
    ):
        shapes = shapes.dropna()
        shapes = shapes[~shapes.is_empty]
        rate = full.reindex(shapes.index) * ratio
        if tier == "uninsured remainder":
            # Only the property's own remainder, to MAX_UNINSURED_M2, carries
            # value; the piece also holds any shared lot and the land beyond
            # the cap, so its rate is that value averaged over all of it.
            own = (factors["property_m2"] - factors["insured_m2"]).clip(
                lower=0, upper=MAX_UNINSURED_M2
            )
            rate = rate * own.reindex(shapes.index) / shapes.area
        pieces.append(
            gpd.GeoDataFrame(
                {
                    CLAIM_ID_COLUMN: shapes.index,
                    TIER_COLUMN: tier,
                    TIER_RATE_COLUMN: rate.round(2),
                    "area_m2": shapes.area.round(1).to_numpy(),
                },
                geometry=shapes.to_numpy(),
                crs=insured.crs,
            )
        )
    tiers = pd.concat(pieces, ignore_index=True)
    return tiers[tiers["area_m2"] > 0.5]


def write_qgis(insured, factors, suburbs, suffix, *, tiers=None):
    """Write the suburb (and optionally property) layers and a QGIS project."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shapes = insured.drop_duplicates(CLAIM_ID_COLUMN).set_index(CLAIM_ID_COLUMN)[
        ["geometry"]
    ]
    layers = []
    suburb_shapes = (
        gpd.GeoDataFrame(
            factors[[TA_COLUMN, SUBURB_COLUMN]].join(shapes, how="inner"),
            crs=insured.crs,
        )
        .dissolve(by=[TA_COLUMN, SUBURB_COLUMN])
        .reset_index()
    )
    suburb_layer = suburb_shapes.merge(
        suburbs, on=[TA_COLUMN, SUBURB_COLUMN], how="inner"
    )
    suburb_path = OUT_DIR / f"{STEM}-by-suburb{suffix}.geoparquet"
    suburb_layer.to_parquet(suburb_path)
    suburbs.to_csv(
        OUT_DIR / f"{STEM}-by-suburb{suffix}.csv", index=False, encoding="utf-8-sig"
    )
    print(f"Wrote {suburb_path} ({len(suburb_layer):,} suburbs)")
    layers.append(
        {
            "path": str(suburb_path),
            "name": "Suburb median liquefaction factor (insured land over property)",
            "field": "median_liquefaction_factor",
            "cmap": "YlOrRd",
            "breaks": FACTOR_BREAKS,
            "label_decimals": 2,
            "outline": "#ffffff",
            "width": 0.3,
            "checked": True,
        }
    )
    if config.QV_TIER_WRITE_PROPERTY_LAYER:
        columns = [
            TA_COLUMN,
            SUBURB_COLUMN,
            INSURED_SHARE_COLUMN,
            AVERAGE_RATE_COLUMN,
            FULL_RATE_COLUMN,
            INSURED_RATE_COLUMN,
            *FACTORS,
        ]
        per_property = gpd.GeoDataFrame(
            factors[columns].join(shapes, how="inner"), crs=insured.crs
        ).reset_index()
        property_path = OUT_DIR / f"{STEM}-by-property{suffix}.geoparquet"
        per_property.to_parquet(property_path)
        print(
            f"Wrote {property_path} ({len(per_property):,} properties). SENSITIVE: "
            "its rates are derived from each property's QV land value; do not "
            "share it, and destroy it with the roll."
        )
        for column, label in FACTORS.items():
            layers.append(
                {
                    "path": str(property_path),
                    "name": f"Property {label.lower()} factor (SENSITIVE)",
                    "field": column,
                    "cmap": "YlOrRd",
                    "breaks": FACTOR_BREAKS,
                    "label_decimals": 2,
                    "outline": "#55555580",
                    "width": 0.1,
                    "checked": column == LIQUEFACTION_FACTOR,
                }
            )
    if tiers is not None:
        tier_path = OUT_DIR / f"{STEM}-by-tier{suffix}.geoparquet"
        tiers.to_parquet(tier_path)
        print(
            f"Wrote {tier_path} ({len(tiers):,} pieces). SENSITIVE: its rates are "
            "derived from each property's QV land value; do not share it, and "
            "destroy it with the roll."
        )
        layers.append(
            {
                "path": str(tier_path),
                "name": "QV rate per m² by tier, before GST (SENSITIVE)",
                "field": TIER_RATE_COLUMN,
                "cmap": "YlOrRd",
                "bins": 8,
                "bin_mode": "quantile",
                "label_decimals": 0,
                "outline": "#55555580",
                "width": 0.1,
                "checked": True,
            }
        )
    project = OUT_DIR / f"{STEM}{suffix}.qgs"
    landslide.load_builder().run(
        {
            "title": f"QV land value tier correction factors{suffix}",
            "out": str(project),
            "source": "local",
            "crs": f"EPSG:{NZTM}",
            "layers": layers,
        }
    )
    print(f"Wrote {project}")


def main(*, extent, min_suburb_properties):
    """Work out the tier factors per claim property and write the outputs.

    Returns:
        1 if exposure step 5 has not written what is needed, else None.
    """
    suffix = extent_suffix(extent)
    insured_path = insured_land_path(extent=extent)
    links_path = valuation_links_path(extent=extent)
    if not insured_path.exists() or not links_path.exists():
        print(f"Run exposure step 5 over {extent} first: {insured_path}, {links_path}")
        return 1
    insured = gpd.read_parquet(insured_path)
    if FOOTPRINT_AREA_COLUMN not in insured.columns:
        print(
            f"{insured_path} has no {FOOTPRINT_AREA_COLUMN}; rerun exposure step 5 "
            "with the 2026-10-11 code"
        )
        return 1

    print("Reading the QV rating roll (sensitive) ...", flush=True)
    qv = qv_land_value_by_claim(
        get_qv_rating_roll(), pd.read_parquet(links_path), load_base_rates()
    )[QV_LAND_VALUE_COLUMN]

    factors = tier_factors(insured, qv)
    factors[TA_COLUMN] = authority_of(insured, factors.index)
    describe(factors)
    suburbs = by_suburb(factors, min_suburb_properties)
    print(RULE)
    plot(
        factors,
        suburbs,
        FIG_DIR / f"{STEM}{suffix}.png",
        title="How the three land tiers correct the property's average QV rate"
        f" -- {extent}",
    )
    tiers = None
    if config.QV_TIER_WRITE_TIER_LAYER:
        print("Cutting each property into its tiers ...", flush=True)
        # The boundaries over the same box exposure step 5 fetched, so they come
        # from its cache.
        addresses = gpd.read_parquet(land_value_path(extent=extent))
        boundaries = get_nz_property_boundaries(
            bbox=fetch_extent(addresses), crs=insured.crs, use_cache=True
        )
        boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
        tiers = tier_pieces(
            insured,
            gpd.read_parquet(footprints_path(extent=extent)),
            build_claim_properties(boundaries),
            factors,
        )
    write_qgis(insured, factors, suburbs, suffix, tiers=tiers)
    return None


if __name__ == "__main__":
    sys.exit(
        main(
            extent=config.QV_TIER_EXTENT,
            min_suburb_properties=config.QV_TIER_MIN_SUBURB_PROPERTIES,
        )
    )
