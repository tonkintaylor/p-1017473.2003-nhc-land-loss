"""The value of a claim's damaged land, from the QV rating roll in three tiers.

The loss module values land itself; nothing upstream sends it a land value.
Each claim property's own land value on QV's rating roll, indexed to the
common valuation date, is spread over the property in three tiers that step
down from the house outwards, and the damaged land is valued by the tier it
lies in. ``src/scripts/landloss/loss/qv_land_value_method.md`` sets the
approach out for a reader; this is the arithmetic.

**Why tiers.** A property's land value over its area is an average over the
whole section, and on a large section most of that area is garden, bush or
paddock that adds little. Damaged land lies around the house, so the average
undervalues it. Valuers treat the house site as the valuable part and the rest
as worth a fraction of its rate; NHC's own rules mark out the same ground, as
the insured land within 8 m of the dwelling plus its accessway. So:

1. the building footprint is valued at the full rate ``R``;
2. the rest of the insured land -- the 8 m buffer and the accessway -- at
   :data:`INSURED_RATIO` times it;
3. the uninsured remainder of the property at :data:`UNINSURED_RATIO` times it,

with ``R`` set so the three add back to the property's land value:
``R = V / (A_footprint + INSURED_RATIO * A_ring + UNINSURED_RATIO * A_outer)``.

**Damaged land by tier.** Damaged land is insured land, so only the first two
tiers price it. Landslide ground is located, and vul measures how much of it
fell on the footprint, so it is valued exactly. Liquefaction damage is an area
with no location, so it takes the insured land's average, which is its expected
value if it is spread evenly. A polygon with both is valued by the larger, as
:func:`~landloss.loss.claims.damaged_area_m2` counts the larger area.

**Not on the roll.** A property whose land value cannot be read off the roll
takes the median land value per m² of the properties in its suburb that can,
times its own area, and is then tiered the same way; with no such property in
its suburb, the median over the whole run.

Sensitive:
    The roll is QV's, supplied as sensitive data
    (:mod:`landloss.io.qv_rating_roll`); a rate derived from one property's
    land value is close to its record.
"""

import numpy as np
import pandas as pd

from landloss.domain.gst import add_gst
from landloss.domain.loss_contract import (
    CLAIM_ID_COLUMN,
    LAND_FOOTPRINT_AREA_COLUMN,
    LAND_PROPERTY_AREA_COLUMN,
    LAND_SUBURB_COLUMN,
    LANDSLIDE_AREA_COLUMN,
    LANDSLIDE_FOOTPRINT_AREA_COLUMN,
    LIQ_LD_AREA_COLUMN,
    TOTAL_INSURED_LAND_AREA_COLUMN,
)
from landloss.exposure.land.residential_use import (
    USE_PRECEDENCE,
    VALUATION_REFERENCE_COLUMN,
    classify_property_category,
)
from landloss.io.qv_rating_roll import linz_valuation_reference

# The tiers' rates as shares of the footprint's: the rest of the insured land,
# and the uninsured remainder of the property.
#
# PLACEHOLDERS, TO BE SET BY A VALUER (T-153). Chosen in the spirit of the
# valuers' depth rules, which put the back of a section at a fraction of the
# front's rate, and of the primary site against surplus land, about a fifth.
INSURED_RATIO = 0.5
UNINSURED_RATIO = 0.15

# The roll's land value summed over a claim property, indexed to the common
# valuation date, and what else is known about the property from the roll.
QV_LAND_VALUE_COLUMN = "qv_land_value_indexed_nzd"
QV_UNITS_COLUMN = "qv_rating_units"
QV_USE_COLUMN = "property_use"

# Each claim's land value as the tiers spread it, and where it came from: its
# own roll record, its suburb's median rate, or the run's.
LAND_VALUE_COLUMN = "land_value_excl_gst_nzd"
VALUE_SOURCE_COLUMN = "land_value_source"
FROM_ROLL = "qv"
FROM_SUBURB = "suburb median"
FROM_RUN = "run median"

# What damaged_land_rates writes on each land row, all including GST: the
# footprint's full rate, the insured land's average, and the rate the row's
# damaged land is valued at.
FOOTPRINT_RATE_COLUMN = "footprint_rate_incl_gst_nzd_per_m2"
INSURED_RATE_COLUMN = "insured_land_rate_incl_gst_nzd_per_m2"
DAMAGED_LAND_RATE_COLUMN = "damaged_land_rate_incl_gst_nzd_per_m2"


def qv_land_value_by_claim(
    roll: pd.DataFrame, links: pd.DataFrame, base_rates: pd.DataFrame
) -> pd.DataFrame:
    """Return the roll's indexed land value summed over each claim property.

    A rating unit on two claim properties cannot be split between them, and a
    property with a unit missing its value or index would be under-counted, so
    both are left out, and the run says how many.

    Args:
        roll: The QV rating roll, from ``get_qv_rating_roll``.
        links: Valuation references and the claims they belong to, from
            :func:`~landloss.exposure.land.residential_use.claim_ids_by_valuation_reference`.
        base_rates: The land value base rates, carrying each authority's index.

    Returns:
        Indexed by claim id: :data:`QV_LAND_VALUE_COLUMN`,
        :data:`QV_UNITS_COLUMN` and :data:`QV_USE_COLUMN`.
    """
    index = base_rates.assign(
        district=base_rates["ta_code"].astype(str).str.zfill(3).str[-2:]
    ).set_index("district")["index_to_2025_09"]
    units = pd.DataFrame(
        {
            VALUATION_REFERENCE_COLUMN: linz_valuation_reference(roll),
            "land_value": roll["land_value"].astype("Float64"),
            "factor": roll["district_ta_code"].map(index).astype("Float64"),
            "use": classify_property_category(roll["property_category"]),
        }
    ).dropna(subset=[VALUATION_REFERENCE_COLUMN])
    units = units.drop_duplicates(VALUATION_REFERENCE_COLUMN)

    joined = links.merge(units, on=VALUATION_REFERENCE_COLUMN, how="inner")

    spread = joined.groupby(VALUATION_REFERENCE_COLUMN)[CLAIM_ID_COLUMN].nunique()
    split_refs = spread.index[spread > 1]
    split_claims = set(
        joined.loc[joined[VALUATION_REFERENCE_COLUMN].isin(split_refs), CLAIM_ID_COLUMN]
    )
    print(
        f"  {len(split_refs):,} rating units span more than one claim property; "
        f"the {len(split_claims):,} properties they touch are left out"
    )
    joined = joined[~joined[CLAIM_ID_COLUMN].isin(split_claims)]

    incomplete = set(
        joined.loc[
            joined["land_value"].isna() | joined["factor"].isna(), CLAIM_ID_COLUMN
        ]
    )
    if incomplete:
        print(
            f"  {len(incomplete):,} properties have a unit with no land value or "
            "no index factor and are left out"
        )
    joined = joined[~joined[CLAIM_ID_COLUMN].isin(incomplete)]

    rank = {use: order for order, use in enumerate(USE_PRECEDENCE)}
    joined = joined.assign(
        indexed=joined["land_value"] * joined["factor"],
        rank=joined["use"].map(rank).fillna(len(rank)),
    )
    grouped = joined.groupby(CLAIM_ID_COLUMN)
    first_use = (
        joined.sort_values([CLAIM_ID_COLUMN, "rank"], kind="stable")
        .drop_duplicates(CLAIM_ID_COLUMN)
        .set_index(CLAIM_ID_COLUMN)["use"]
    )
    return pd.DataFrame(
        {
            QV_LAND_VALUE_COLUMN: grouped["indexed"].sum().astype(float),
            QV_UNITS_COLUMN: grouped.size(),
            QV_USE_COLUMN: first_use,
        }
    )


def claim_land_values(land: pd.DataFrame, qv_value: pd.Series) -> pd.DataFrame:
    """Return each claim's land value: its own, or its suburb's median rate.

    Args:
        land: The contract's land table, carrying the claim, its property area
            and its suburb.
        qv_value: The indexed QV land value per claim, from
            :func:`qv_land_value_by_claim`.

    Returns:
        Indexed by claim id: :data:`LAND_VALUE_COLUMN`, in dollars excluding
        GST, and :data:`VALUE_SOURCE_COLUMN`.
    """
    claims = land.groupby(CLAIM_ID_COLUMN).agg(
        area=(LAND_PROPERTY_AREA_COLUMN, "first"),
        suburb=(LAND_SUBURB_COLUMN, "first"),
    )
    value = claims.index.map(qv_value).astype(float)
    value = pd.Series(value, index=claims.index)
    rate = value / claims["area"].where(claims["area"] > 0)
    by_suburb = rate.groupby(claims["suburb"]).median()
    suburb_rate = claims["suburb"].map(by_suburb)
    run_rate = rate.median()
    source = pd.Series(FROM_ROLL, index=claims.index).where(value.notna(), None)
    filled = value.copy()
    use_suburb = value.isna() & suburb_rate.notna()
    filled[use_suburb] = (suburb_rate * claims["area"])[use_suburb]
    source[use_suburb] = FROM_SUBURB
    use_run = filled.isna()
    filled[use_run] = run_rate * claims["area"][use_run]
    source[use_run] = FROM_RUN
    return pd.DataFrame({LAND_VALUE_COLUMN: filled, VALUE_SOURCE_COLUMN: source})


def footprint_rate(
    land_value: pd.Series,
    footprint_m2: pd.Series,
    insured_m2: pd.Series,
    property_m2: pd.Series,
    *,
    insured_ratio: float = INSURED_RATIO,
    uninsured_ratio: float = UNINSURED_RATIO,
) -> pd.Series:
    """Return the footprint's full rate, so the three tiers add back to the value.

    The insured land includes the footprint, so the ring is the insured land
    less the footprint and the outer tier the property less the insured land;
    neither goes below zero where the layers disagree slightly.

    Args:
        land_value: Each property's land value, in dollars.
        footprint_m2: The area of the buildings on it.
        insured_m2: The area of its insured land, footprint included.
        property_m2: The area of the whole property.
        insured_ratio: The ring's rate as a share of the footprint's.
        uninsured_ratio: The outer tier's rate as a share of the footprint's.

    Returns:
        The full rate per m², indexed as ``land_value``; missing where there is
        no value or no area to spread it over.

    Raises:
        ValueError: If a ratio is outside 0 to 1, or the ring's is below the
            outer tier's.
    """
    if not 0 <= uninsured_ratio <= insured_ratio <= 1:
        msg = (
            "need 0 <= uninsured_ratio <= insured_ratio <= 1, got "
            f"{uninsured_ratio} and {insured_ratio}"
        )
        raise ValueError(msg)
    footprint = footprint_m2.astype(float).clip(lower=0)
    insured = np.maximum(insured_m2.astype(float), footprint)
    ring = insured - footprint
    outer = (property_m2.astype(float) - insured).clip(lower=0)
    weighted = footprint + insured_ratio * ring + uninsured_ratio * outer
    return land_value.astype(float) / weighted.where(weighted > 0)


def damaged_land_rates(
    land: pd.DataFrame,
    values: pd.DataFrame,
    *,
    insured_ratio: float = INSURED_RATIO,
    uninsured_ratio: float = UNINSURED_RATIO,
) -> pd.DataFrame:
    """Return the land table with the rate each row's damaged land is valued at.

    A claim's value is spread over its property once, on its footprint and
    its summed insured area, and every row of the claim takes the same
    tier rates; the damaged land on each row is then valued by tier.

    Args:
        land: The contract's land table.
        values: Each claim's land value, from :func:`claim_land_values`.
        insured_ratio: The ring's rate as a share of the footprint's.
        uninsured_ratio: The outer tier's rate as a share of the footprint's.

    Returns:
        ``land`` with :data:`FOOTPRINT_RATE_COLUMN`, :data:`INSURED_RATE_COLUMN`,
        :data:`DAMAGED_LAND_RATE_COLUMN` and :data:`VALUE_SOURCE_COLUMN` added,
        the rates including GST.
    """
    claims = land.groupby(CLAIM_ID_COLUMN).agg(
        # The footprint is the claim's, written on each of its rows; the
        # insured land is the row's own polygon.
        footprint=(LAND_FOOTPRINT_AREA_COLUMN, "first"),
        insured=(TOTAL_INSURED_LAND_AREA_COLUMN, "sum"),
        area=(LAND_PROPERTY_AREA_COLUMN, "first"),
    )
    value = values[LAND_VALUE_COLUMN].reindex(claims.index)
    full = add_gst(
        footprint_rate(
            value,
            claims["footprint"],
            claims["insured"],
            claims["area"],
            insured_ratio=insured_ratio,
            uninsured_ratio=uninsured_ratio,
        )
    )
    footprint = claims["footprint"].clip(lower=0)
    insured = np.maximum(claims["insured"], footprint)
    average = (
        full
        * (footprint + insured_ratio * (insured - footprint))
        / insured.where(insured > 0)
    )

    claim = land[CLAIM_ID_COLUMN]
    row_full = claim.map(full).to_numpy(dtype=float)
    row_average = claim.map(average).to_numpy(dtype=float)
    slipped = np.nan_to_num(land[LANDSLIDE_AREA_COLUMN].to_numpy(dtype=float))
    liquefied = np.nan_to_num(land[LIQ_LD_AREA_COLUMN].to_numpy(dtype=float))
    on_footprint = np.minimum(
        np.nan_to_num(land[LANDSLIDE_FOOTPRINT_AREA_COLUMN].to_numpy(dtype=float)),
        slipped,
    )
    landslide_rate = np.where(
        slipped > 0,
        (row_full * on_footprint + insured_ratio * row_full * (slipped - on_footprint))
        / np.where(slipped > 0, slipped, 1.0),
        row_average,
    )
    # The larger cause is the one loss counts, so it sets the rate.
    rate = np.where((slipped > 0) & (slipped >= liquefied), landslide_rate, row_average)
    return land.assign(
        **{
            FOOTPRINT_RATE_COLUMN: row_full,
            INSURED_RATE_COLUMN: row_average,
            DAMAGED_LAND_RATE_COLUMN: rate,
            VALUE_SOURCE_COLUMN: claim.map(values[VALUE_SOURCE_COLUMN]).to_numpy(),
        }
    )
