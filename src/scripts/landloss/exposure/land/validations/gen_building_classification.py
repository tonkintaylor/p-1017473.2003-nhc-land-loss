"""Show how the building outlines are classed as dwellings, for checking in QGIS.

    uv run --frozen python src/scripts/landloss/exposure/land/validations/gen_building_classification.py

The insured land extent is buffered off the buildings
:func:`~landloss.exposure.land.extent.drop_non_residential_buildings` keeps:
every outline LINZ has not named as a school, hospital or supermarket, and no
larger than the step's ``MAX_DWELLING_FOOTPRINT_M2``.
That is a footprint rule, and it errs both ways. An apartment block is
residential with a footprint like a warehouse, so it is dropped and its flats
carry no insured land; a shop, a workshop or a church under the threshold is
kept and buffered as though it were a house.

This writes every outline in the extent with the class the rule gives it and
the evidence beside it -- its footprint, the property it stands on, and how
many addresses and unit addresses that property carries, since a large outline
on a property with many unit addresses is likely to be flats -- and reports
what the size rule would drop at other thresholds.

**With the QV rating roll** (``config.USE_QV_ROLL``) it also classes each
property by its ``property_category`` on the roll, which says what the land is
used for rather than inferring it from a footprint, and records where that
disagrees with the footprint rule. The roll is read from T: and is sensitive,
so the layer carries only the class derived from it, never a field of the roll
itself. The classes are those the insured land step uses under its default
"qv" rule, from :mod:`landloss.exposure.land.residential_use`.

Writes ``building-classification[-qv]<suffix>.gpkg`` to ``config.OUT_DIR``.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.land.extent import (
    BUILDING_USE_COLUMN,
    CLAIM_ID_COLUMN,
    UNNAMED_BUILDING_USE,
    build_claim_properties,
)
from landloss.exposure.land.residential_use import (
    PROPERTY_CATEGORY_COLUMN,
    VALUATION_REFERENCE_COLUMN,
    drop_buildings_by_property_use,
    property_use,
)
from landloss.io.area_of_interest import (
    extent_suffix,
    get_area_of_interest,
    get_study_areas,
)
from landloss.io.readers import (
    get_nz_addresses,
    get_nz_building_outlines,
    get_nz_property_boundaries,
)
from scripts.landloss.exposure.land.steps.s5_insured_land_extent import (
    config as insured_config,
)
from scripts.landloss.exposure.land.validations import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RULE = "-" * 72

# What the footprint rule calls each outline.
KEPT = "kept"
NAMED = "named non-residential"
TOO_LARGE = "over the size limit"

# What the comparison calls a property the rating roll does not hold.
QV_UNMATCHED = "not on the roll"

# How the footprint rule and the roll compare, per outline.
AGREE_KEPT = "both keep"
AGREE_DROPPED = "both drop"
MISSED = "only the roll rule keeps"
FALSE_KEEP = "only the footprint rule keeps"


def footprint_class(outlines: gpd.GeoDataFrame) -> pd.Series:
    """Return the footprint rule's verdict on each outline.

    The same two tests as ``drop_non_residential_buildings``, named rather than
    collapsed to keep or drop, so the map can show which one an outline failed.
    """
    uses = outlines[BUILDING_USE_COLUMN].fillna(UNNAMED_BUILDING_USE)
    uses = uses.replace("", UNNAMED_BUILDING_USE)
    return pd.Series(
        np.select(
            [
                uses != UNNAMED_BUILDING_USE,
                outlines.geometry.area > insured_config.MAX_DWELLING_FOOTPRINT_M2,
            ],
            [NAMED, TOO_LARGE],
            default=KEPT,
        ),
        index=outlines.index,
    )


def qv_property_class(boundaries: gpd.GeoDataFrame) -> pd.Series:
    """Return each claim property's use on the QV rating roll, read from T:.

    The same classes and join the insured land step uses under its "qv" rule
    (landloss.exposure.land.residential_use), so the map shows what the model
    does.
    """
    from landloss.io.qv_rating_roll import (  # noqa: PLC0415 - needs T:, so only on request
        get_qv_rating_roll,
        linz_valuation_reference,
    )

    roll = get_qv_rating_roll()
    units = pd.DataFrame(
        {
            VALUATION_REFERENCE_COLUMN: linz_valuation_reference(roll),
            PROPERTY_CATEGORY_COLUMN: roll["property_category"],
        }
    )
    return property_use(boundaries, units)


def compare(footprint_kept: pd.Series, qv_kept: pd.Series) -> pd.Series:
    """Return how the footprint rule and the roll rule decide each outline.

    Both are the model's own rules, so this is what switching between them
    changes, not a reading of the roll alone.
    """
    return pd.Series(
        np.select(
            [footprint_kept & qv_kept, ~footprint_kept & ~qv_kept, qv_kept],
            [AGREE_KEPT, AGREE_DROPPED, MISSED],
            default=FALSE_KEEP,
        ),
        index=footprint_kept.index,
    )


def address_counts(
    claims: gpd.GeoDataFrame, addresses: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Return how many addresses, and unit addresses, stand on each claim."""
    joined = gpd.sjoin(
        addresses[["unit", "geometry"]],
        claims[[CLAIM_ID_COLUMN, "geometry"]],
        predicate="within",
    )
    unit = joined["unit"].fillna("").astype(str).str.strip() != ""
    return pd.DataFrame(
        {
            "addresses_on_property": joined.groupby(CLAIM_ID_COLUMN).size(),
            "unit_addresses_on_property": unit.groupby(joined[CLAIM_ID_COLUMN]).sum(),
        }
    )


def describe_thresholds(outlines: gpd.GeoDataFrame) -> None:
    """Print what the size rule drops at each threshold in the config."""
    unnamed = outlines[outlines["footprint_class"] != NAMED]
    area = unnamed["area_m2"]
    flats = unnamed["unit_addresses_on_property"] >= 2
    print(
        f"\n{RULE}\nThe size rule at other thresholds (unnamed outlines only)\n{RULE}"
    )
    print(
        f"{'over (m2)':>10} {'outlines':>9} {'share':>7} {'on a property with 2+ unit addresses':>38}"
    )
    for threshold in config.FOOTPRINT_THRESHOLDS_M2:
        over = area > threshold
        print(
            f"{threshold:>10,.0f} {int(over.sum()):>9,} {over.mean():>7.2%} "
            f"{int((over & flats).sum()):>38,}"
        )


def main(*, extent, use_qv_roll):
    """Classify the outlines over an extent and write them out."""
    area = get_area_of_interest(extent)
    if area is None:
        study = get_study_areas(constants.DEFAULT_CRS)
        bbox = tuple(float(v) for v in study.total_bounds)
        clip = study.union_all()
    else:
        bbox = area.bbox(constants.DEFAULT_CRS)
        clip = area.polygon(constants.DEFAULT_CRS)

    print("Reading the building outlines ...", flush=True)
    outlines = get_nz_building_outlines(bbox=bbox, crs=constants.DEFAULT_CRS)
    outlines = outlines[outlines.intersects(clip)].copy()
    outlines = outlines.set_geometry(outlines.geometry.make_valid())
    print("Reading the property boundaries and addresses ...", flush=True)
    boundaries = get_nz_property_boundaries(bbox=bbox, crs=constants.DEFAULT_CRS)
    boundaries = boundaries.set_geometry(boundaries.geometry.make_valid())
    addresses = get_nz_addresses(bbox=bbox, crs=constants.DEFAULT_CRS)
    addresses = addresses[addresses.within(clip)]

    claims = build_claim_properties(boundaries)
    claims["property_area_m2"] = claims.geometry.area
    counts = address_counts(claims, addresses)

    # Each outline stands on the property its representative point falls in.
    # The insured land step splits an outline across properties instead; for
    # classing it, one property is enough.
    points = outlines[["geometry"]].copy()
    points["geometry"] = outlines.geometry.representative_point()
    on = gpd.sjoin(points, claims[[CLAIM_ID_COLUMN, "geometry"]], predicate="within")
    on = on[~on.index.duplicated()]
    outlines[CLAIM_ID_COLUMN] = on[CLAIM_ID_COLUMN].reindex(outlines.index)

    outlines["area_m2"] = outlines.geometry.area.round(1)
    outlines["footprint_class"] = footprint_class(outlines)
    by_claim = claims.set_index(CLAIM_ID_COLUMN)
    outlines["property_area_m2"] = (
        outlines[CLAIM_ID_COLUMN].map(by_claim["property_area_m2"]).round(1)
    )
    for column in counts.columns:
        outlines[column] = (
            outlines[CLAIM_ID_COLUMN].map(counts[column]).fillna(0).astype(int)
        )

    if use_qv_roll:
        print("Reading the QV rating roll from T: ...", flush=True)
        qv = qv_property_class(boundaries)
        outlines["qv_class"] = outlines[CLAIM_ID_COLUMN].map(qv).fillna(QV_UNMATCHED)
        qv_kept = outlines.index.isin(
            drop_buildings_by_property_use(
                outlines,
                claims,
                qv,
                max_area_m2=insured_config.MAX_DWELLING_FOOTPRINT_M2,
            ).index
        )
        outlines["comparison"] = compare(
            outlines["footprint_class"] == KEPT,
            pd.Series(qv_kept, index=outlines.index),
        )

    keep = [
        "building_id",
        BUILDING_USE_COLUMN,
        "name",
        "territorial_authority",
        "suburb_locality",
        CLAIM_ID_COLUMN,
        "area_m2",
        "property_area_m2",
        "addresses_on_property",
        "unit_addresses_on_property",
        "footprint_class",
        *(["qv_class", "comparison"] if use_qv_roll else []),
        "geometry",
    ]
    out = outlines[keep]

    print(f"\n{RULE}\n{len(out):,} outlines over {extent}\n{RULE}")
    print(pd.crosstab(out["territorial_authority"], out["footprint_class"]).to_string())
    describe_thresholds(out)
    if use_qv_roll:
        print(f"\n{RULE}\nThe footprint rule against the QV rating roll\n{RULE}")
        print(out["comparison"].value_counts().to_string())

    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    name = "building-classification" + ("-qv" if use_qv_roll else "")
    path = config.OUT_DIR / f"{name}{extent_suffix(extent)}.gpkg"
    out.to_file(path, layer=name, driver="GPKG")
    print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    main(extent=config.EXTENT, use_qv_roll=config.USE_QV_ROLL)
