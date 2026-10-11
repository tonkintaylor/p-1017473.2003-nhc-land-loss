"""Compare the modelled land value against the QV rating roll, property by property.

    uv run --frozen python src/scripts/landloss/exposure/land/validations/gen_land_value_vs_qv.py

The land value step (``s2_land_value/s4_estimate_land_value.py``) spreads each
territorial authority's published average across its addresses by landform,
terrain, accessibility, amenity and section size. Only the authority totals are
anchored; how value is spread *within* an authority rests on judgement and has
not been checked (L-20). The QV rating roll holds a land value for every rating
unit, so it is the check.

The two are compared per claim property -- the LINZ property boundaries reduced
by :func:`~landloss.exposure.land.extent.build_claim_properties`, the unit every
claim and every modelled value sits on:

- **Modelled**: the property's ``site_land_value_nzd``, the whole section's
  value, already at the common date (``COMMON_VALUATION_DATE``).
- **QV**: the land value of every rating unit on the property, joined on the
  valuation reference the same way as
  :func:`~landloss.exposure.land.residential_use.property_use`, summed, and
  indexed to the common date with the same per-authority factor the model uses
  (``index_to_2025_09`` in ``land-value-base-rates.csv``). Without the index,
  Wellington City's 2024 roll would read about 4% high against the model.

A rating unit linked to more than one claim property cannot be split between
them, so those properties are left out, and the run says how many.

Writes, for the extent in ``config.LAND_VALUE_QV_EXTENT``:

- ``report/exposure/land/land-value/fig/land-value-vs-qv<suffix>.png``: a
  density of modelled against QV value, the ratio by authority and by landform,
  and suburb medians. Summaries only, so it may go in the report.
- ``temp/exposure/land-value-vs-qv/``: ``land-value-vs-qv-by-suburb<suffix>``
  as CSV and geoparquet (summaries), the per-property layer when
  ``config.LAND_VALUE_QV_WRITE_PROPERTY_LAYER`` is set, and a QGIS project
  ``land-value-vs-qv<suffix>.qgs`` styling both by the ratio.

Sensitive:
    The per-property layer carries the roll's land value against each property,
    which is the roll re-tabulated. It stays under ``temp/`` (gitignored), is not
    shared, and is destroyed with the roll at the end of the project
    (:mod:`landloss.io.qv_rating_roll`). The suburb layer, the CSV and the figure
    hold medians over at least ``config.LAND_VALUE_QV_MIN_SUBURB_PROPERTIES``
    properties, and the figure draws the property comparison as a density
    rather than as points.

The roll is read through tdrive_sync from T:, or from the local cache with
``TTDRIVE_SYNC_LOCAL_MODE=True``. Run the land value step over the extent first.
"""

import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, NullFormatter

from landloss.domain import constants
from landloss.exposure.land.extent import (
    CLAIM_ID_COLUMN,
    build_claim_properties,
)
from landloss.exposure.land.land_value import (
    COMMON_VALUATION_DATE,
    SITE_LAND_VALUE_COLUMN,
    load_base_rates,
)
from landloss.exposure.land.landform import LANDFORM_COLUMN
from landloss.exposure.land.residential_use import (
    DWELLING_USES,
    claim_ids_by_valuation_reference,
)
from landloss.io.area_of_interest import extent_suffix, get_study_areas
from landloss.io.qv_rating_roll import get_qv_rating_roll
from landloss.io.readers import get_nz_property_boundaries
from landloss.loss.qv_land_value import (
    QV_LAND_VALUE_COLUMN,
    QV_UNITS_COLUMN,
    QV_USE_COLUMN,
    qv_land_value_by_claim,
)
from scripts.landloss.exposure.land.steps.s2_land_value.s4_estimate_land_value import (
    resolve_extent,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    land_value_path,
)
from scripts.landloss.exposure.land.validations import config
from scripts.landloss.hazard.landslide.validations.qgis import (
    gen_landslide_qgis_project as landslide,
)
from scripts.landloss.paths import REPORT_DIR, TEMP_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_DIR = TEMP_DIR / "exposure" / "land-value-vs-qv"
FIG_DIR = REPORT_DIR / "exposure" / "land" / "land-value" / "fig"
STEM = "land-value-vs-qv"
NZTM = 2193
DPI = 200
RULE = "-" * 72

MODEL_COLUMN = "model_land_value_nzd"
QV_COLUMN = QV_LAND_VALUE_COLUMN
RATIO_COLUMN = "model_over_qv"
USE_COLUMN = QV_USE_COLUMN
UNITS_COLUMN = QV_UNITS_COLUMN

# Within this factor of the roll either way counts as close, for the share the
# run reports. 1.25 is about the spread between neighbouring sections on the
# roll itself, so closer than that is more than the model could claim.
CLOSE_FACTOR = 1.25

# The ratio bands the QGIS layers are drawn in: blue where the model is under
# the roll, red where it is over, white within 10%.
RATIO_BREAKS = [0.0, 0.5, 0.67, 0.8, 0.9, 1.1, 1.25, 1.5, 2.0, 1000.0]

# How many suburbs the suburb panel names: the furthest from the 1:1 line.
LABELLED_SUBURBS = 6

TA_COLOURS = {
    "Wellington City": "#1565c0",
    "Lower Hutt City": "#2e7d32",
    "Upper Hutt City": "#ef6c00",
    "Porirua City": "#6a1b9a",
}


def model_by_property(valued, properties):
    """Return the modelled site land value of each claim property.

    Every address on a property carries the same site value, so the median is
    that value; the run reports any property whose addresses disagree.

    Args:
        valued: The valued addresses from the land value step.
        properties: The claim properties.

    Returns:
        Indexed by claim id: the site value, authority, suburb and landform.
    """
    on = gpd.sjoin(
        valued[
            [
                SITE_LAND_VALUE_COLUMN,
                "territorial_authority",
                "suburb_locality",
                LANDFORM_COLUMN,
                "geometry",
            ]
        ],
        properties[[CLAIM_ID_COLUMN, "geometry"]],
        predicate="within",
    )
    on = on[~on.index.duplicated()]
    print(
        f"  {len(on):,} of {len(valued):,} valued addresses stand in a claim property"
    )

    grouped = on.groupby(CLAIM_ID_COLUMN)
    values = grouped[SITE_LAND_VALUE_COLUMN]
    spread = values.max() / values.min()
    disagree = int((spread > 1.001).sum())
    if disagree:
        print(
            f"  {disagree:,} properties carry more than one site value across "
            "their addresses; their median is used"
        )
    return pd.DataFrame(
        {
            MODEL_COLUMN: values.median(),
            "territorial_authority": grouped["territorial_authority"].first(),
            "suburb_locality": grouped["suburb_locality"].agg(
                lambda s: s.mode().iloc[0] if not s.mode().empty else pd.NA
            ),
            LANDFORM_COLUMN: grouped[LANDFORM_COLUMN].agg(
                lambda s: s.mode().iloc[0] if not s.mode().empty else pd.NA
            ),
        }
    )


def rank_correlation(a, b):
    """Spearman's rank correlation, without scipy."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def describe(compared, group, heading):
    """Print the comparison per group: totals, median ratio, spread and rank."""
    print(RULE)
    print(heading)
    print(
        f"{'':<22}{'Properties':>11}{'Total ratio':>12}{'Median':>8}"
        f"{'p10':>7}{'p90':>7}{f'±{CLOSE_FACTOR:g}x':>8}{'Spearman':>10}"
    )
    rows = [("All", compared)]
    if group is not None:
        rows += list(compared.groupby(group, sort=True))
    for name, rows_ in rows:
        ratio = rows_[RATIO_COLUMN]
        close = ((ratio >= 1 / CLOSE_FACTOR) & (ratio <= CLOSE_FACTOR)).mean()
        print(
            f"{name!s:<22}{len(rows_):>11,}"
            f"{rows_[MODEL_COLUMN].sum() / rows_[QV_COLUMN].sum():>12.2f}"
            f"{ratio.median():>8.2f}{ratio.quantile(0.1):>7.2f}"
            f"{ratio.quantile(0.9):>7.2f}{100 * close:>7.0f}%"
            f"{rank_correlation(rows_[MODEL_COLUMN], rows_[QV_COLUMN]):>10.2f}"
        )
    if group is not None:
        print(
            "\nTotal ratio is the modelled total over the roll's; Median, p10 and "
            f"p90 are of the\nper-property ratio; ±{CLOSE_FACTOR:g}x is the share "
            "within that factor of the roll."
        )


def by_suburb(compared, min_properties):
    """Return the suburb medians, for suburbs with enough properties."""
    grouped = compared.groupby(["territorial_authority", "suburb_locality"])
    table = grouped.agg(
        properties=(RATIO_COLUMN, "size"),
        median_model_nzd=(MODEL_COLUMN, "median"),
        median_qv_indexed_nzd=(QV_COLUMN, "median"),
        median_ratio=(RATIO_COLUMN, "median"),
        p25_ratio=(RATIO_COLUMN, lambda s: s.quantile(0.25)),
        p75_ratio=(RATIO_COLUMN, lambda s: s.quantile(0.75)),
    ).reset_index()
    return table[table["properties"] >= min_properties].reset_index(drop=True)


def plot(compared, suburbs, out, *, title):
    """Draw the four panel comparison figure."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 11))
    ax_hex, ax_ta, ax_form, ax_sub = axes.ravel()

    # (a) Density rather than points: one point per property would draw the
    # roll's values.
    x = np.log10(compared[QV_COLUMN].to_numpy())
    y = np.log10(compared[MODEL_COLUMN].to_numpy())
    lo, hi = np.percentile(np.concatenate([x, y]), [0.5, 99.5])
    hexes = ax_hex.hexbin(
        x, y, gridsize=70, extent=(lo, hi, lo, hi), bins="log", mincnt=3, cmap="viridis"
    )
    fig.colorbar(hexes, ax=ax_hex, label="Properties per cell")
    for factor, style in ((1, "-"), (2, ":"), (0.5, ":")):
        ax_hex.plot(
            [lo, hi],
            [lo + np.log10(factor), hi + np.log10(factor)],
            "k",
            ls=style,
            lw=0.8,
        )
    ticks = [v for v in (1e5, 2e5, 5e5, 1e6, 2e6, 5e6) if lo <= np.log10(v) <= hi]
    for setter in (ax_hex.set_xticks, ax_hex.set_yticks):
        setter([np.log10(v) for v in ticks], [f"${v / 1e3:,.0f}k" for v in ticks])
    ax_hex.set_xlim(lo, hi)
    ax_hex.set_ylim(lo, hi)
    ax_hex.set_xlabel(f"QV land value, indexed to {COMMON_VALUATION_DATE}")
    ax_hex.set_ylabel("Modelled land value")
    rho = rank_correlation(compared[MODEL_COLUMN], compared[QV_COLUMN])
    ax_hex.set_title(
        f"(a) Per property, n = {len(compared):,}; Spearman {rho:.2f}\n"
        "solid 1:1, dotted x2 and x0.5",
        fontsize=10,
    )

    # (b) and (c) The ratio by authority and by landform.
    for ax, column, label in (
        (ax_ta, "territorial_authority", "(b) By territorial authority"),
        (ax_form, LANDFORM_COLUMN, "(c) By landform class"),
    ):
        groups = [
            (name, rows[RATIO_COLUMN].to_numpy())
            for name, rows in compared.groupby(column, sort=True)
        ]
        ax.boxplot(
            [values for _, values in groups],
            tick_labels=[f"{name}\nn={len(values):,}" for name, values in groups],
            whis=(10, 90),
            showfliers=False,
            medianprops={"color": "k"},
        )
        ax.axhline(1, color="k", lw=0.8)
        ax.set_yscale("log")
        ax.set_yticks([0.5, 0.67, 1, 1.5, 2], ["0.5", "0.67", "1", "1.5", "2"])
        ax.yaxis.set_minor_formatter(NullFormatter())
        ax.set_ylabel("Modelled / QV (box p25–p75, whiskers p10–p90)")
        ax.set_title(label, fontsize=10)
        ax.tick_params(axis="x", labelsize=8)

    # (d) Suburb medians.
    for ta, rows in suburbs.groupby("territorial_authority"):
        ax_sub.scatter(
            rows["median_qv_indexed_nzd"],
            rows["median_model_nzd"],
            s=np.sqrt(rows["properties"]) * 2,
            color=TA_COLOURS.get(ta, "#757575"),
            alpha=0.7,
            label=ta,
            edgecolor="white",
            linewidth=0.4,
        )
    if not suburbs.empty:
        lo_s = suburbs[["median_qv_indexed_nzd", "median_model_nzd"]].min().min() * 0.9
        hi_s = suburbs[["median_qv_indexed_nzd", "median_model_nzd"]].max().max() * 1.1
        ax_sub.plot([lo_s, hi_s], [lo_s, hi_s], "k", lw=0.8)
        ax_sub.set_xlim(lo_s, hi_s)
        ax_sub.set_ylim(lo_s, hi_s)
        far = suburbs.assign(
            off=np.abs(
                np.log(suburbs["median_model_nzd"] / suburbs["median_qv_indexed_nzd"])
            )
        ).nlargest(LABELLED_SUBURBS, "off")
        for _, row in far.iterrows():
            ax_sub.annotate(
                row["suburb_locality"],
                (row["median_qv_indexed_nzd"], row["median_model_nzd"]),
                fontsize=7,
                xytext=(3, 3),
                textcoords="offset points",
            )
        ax_sub.legend(fontsize=8, loc="upper left")
    ax_sub.set_xscale("log")
    ax_sub.set_yscale("log")
    dollars = FuncFormatter(lambda value, _: f"${value / 1e3:,.0f}k")
    for axis in (ax_sub.xaxis, ax_sub.yaxis):
        axis.set_major_formatter(dollars)
        axis.set_minor_formatter(dollars)
    ax_sub.tick_params(which="minor", labelsize=7)
    ax_sub.set_xlabel("Suburb median QV land value, indexed")
    ax_sub.set_ylabel("Suburb median modelled land value")
    ax_sub.set_title(
        f"(d) Suburb medians, {len(suburbs):,} suburbs "
        f"(≥ {config.LAND_VALUE_QV_MIN_SUBURB_PROPERTIES} properties), size by count",
        fontsize=10,
    )

    fig.suptitle(title, fontsize=12)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {out}")


def write_qgis(properties, compared, suburbs, suffix):
    """Write the suburb (and optionally property) layers and a QGIS project."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    shapes = properties.set_index(CLAIM_ID_COLUMN)[["geometry"]]
    layers = []

    suburb_shapes = (
        gpd.GeoDataFrame(
            compared[["territorial_authority", "suburb_locality"]].join(
                shapes, how="inner"
            ),
            crs=properties.crs,
        )
        .dissolve(by=["territorial_authority", "suburb_locality"])
        .reset_index()
    )
    suburb_layer = suburb_shapes.merge(
        suburbs, on=["territorial_authority", "suburb_locality"], how="inner"
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
            "name": "Suburb median modelled / QV land value",
            "field": "median_ratio",
            "cmap": "RdBu_r",
            "breaks": RATIO_BREAKS,
            "label_decimals": 2,
            "outline": "#ffffff",
            "width": 0.3,
            "checked": True,
        }
    )

    if config.LAND_VALUE_QV_WRITE_PROPERTY_LAYER:
        per_property = gpd.GeoDataFrame(
            compared.join(shapes, how="inner"), crs=properties.crs
        ).reset_index()
        property_path = OUT_DIR / f"{STEM}-by-property{suffix}.geoparquet"
        per_property.to_parquet(property_path)
        print(
            f"Wrote {property_path} ({len(per_property):,} properties). SENSITIVE: it "
            "carries the roll's land value; do not share it, and destroy it with "
            "the roll."
        )
        layers.append(
            {
                "path": str(property_path),
                "name": "Property modelled / QV land value (SENSITIVE)",
                "field": RATIO_COLUMN,
                "cmap": "RdBu_r",
                "breaks": RATIO_BREAKS,
                "label_decimals": 2,
                "outline": "#55555580",
                "width": 0.1,
                "checked": False,
            }
        )

    project = OUT_DIR / f"{STEM}{suffix}.qgs"
    landslide.load_builder().run(
        {
            "title": f"Modelled land value against the QV rating roll{suffix}",
            "out": str(project),
            "source": "local",
            "crs": f"EPSG:{NZTM}",
            "layers": layers,
        }
    )
    print(f"Wrote {project}")


def main(*, extent, dwelling_uses_only, min_suburb_properties):
    """Compare the modelled land value with the QV rating roll and write outputs.

    Args:
        extent: The extent to compare over, "full" or a name from
            landloss.io.area_of_interest.EXTENTS.
        dwelling_uses_only: Whether to keep only properties the roll uses for
            dwellings.
        min_suburb_properties: The fewest properties a suburb needs to be shown.

    Returns:
        1 if the land value step has not been run over the extent, else None.
    """
    suffix = extent_suffix(extent)
    valued_path = land_value_path(extent=extent)
    if not valued_path.exists():
        print(
            f"No modelled land values at {valued_path}; run s4_estimate_land_value.py"
        )
        return 1

    print(f"Reading the modelled land values from {valued_path} ...")
    valued = gpd.read_parquet(valued_path)
    bbox, _, extent_name = resolve_extent(
        get_study_areas(constants.DEFAULT_CRS), extent=extent
    )
    print(f"Extent: {extent_name}")

    print("Reading the LINZ property boundaries ...", flush=True)
    boundaries = get_nz_property_boundaries(
        bbox=bbox, crs=constants.DEFAULT_CRS, use_cache=True
    )
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
    properties = build_claim_properties(boundaries)
    valued = valued.to_crs(properties.crs)

    print("Modelled values per claim property ...")
    model = model_by_property(valued, properties)

    print("Reading the QV rating roll (sensitive) ...", flush=True)
    links = claim_ids_by_valuation_reference(boundaries)
    qv = qv_land_value_by_claim(get_qv_rating_roll(), links, load_base_rates())

    compared = model.join(qv, how="inner")
    print(f"  {len(compared):,} of {len(model):,} valued properties found on the roll")
    if dwelling_uses_only:
        before = len(compared)
        compared = compared[compared[USE_COLUMN].isin(DWELLING_USES)]
        print(
            f"  {before - len(compared):,} on land the roll does not use for "
            "dwellings are left out"
        )
    positive = (compared[MODEL_COLUMN] > 0) & (compared[QV_COLUMN] > 0)
    if (~positive).any():
        print(
            f"  {int((~positive).sum()):,} with a zero value on either side are left out"
        )
    compared = compared[positive].copy()
    compared[RATIO_COLUMN] = compared[MODEL_COLUMN] / compared[QV_COLUMN]

    describe(compared, "territorial_authority", "Modelled against QV, by authority")
    describe(compared, LANDFORM_COLUMN, "Modelled against QV, by landform class")

    suburbs = by_suburb(compared, min_suburb_properties)
    print(RULE)
    print(f"Suburbs furthest from the roll (≥ {min_suburb_properties} properties)")
    ranked = suburbs.assign(off=np.abs(np.log(suburbs["median_ratio"])))
    for _, row in ranked.nlargest(10, "off").iterrows():
        print(
            f"  {row['suburb_locality']!s:<26}{row['territorial_authority']!s:<18}"
            f"median ratio {row['median_ratio']:.2f} over {row['properties']:,}"
        )

    print(RULE)
    plot(
        compared,
        suburbs,
        FIG_DIR / f"{STEM}{suffix}.png",
        title=(
            f"Modelled land value against the QV rating roll — {extent_name}"
            + (" (dwelling land only)" if dwelling_uses_only else "")
        ),
    )
    write_qgis(properties, compared, suburbs, suffix)
    return None


if __name__ == "__main__":
    sys.exit(
        main(
            extent=config.LAND_VALUE_QV_EXTENT,
            dwelling_uses_only=config.LAND_VALUE_QV_DWELLING_USES_ONLY,
            min_suburb_properties=config.LAND_VALUE_QV_MIN_SUBURB_PROPERTIES,
        )
    )
