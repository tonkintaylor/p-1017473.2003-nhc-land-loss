"""Which buildings are dwellings, read off what the land is used for.

NHC land cover follows a residential building, so the insured land extent is
buffered only off the buildings that are dwellings. The building outlines
cannot say which those are: LINZ names a school or a hospital but leaves 99% of
outlines as "Unknown". The footprint rule,
:func:`~landloss.exposure.land.extent.drop_non_residential_buildings`, falls
back on the size, and a footprint errs both ways -- an apartment
block is dropped with the warehouses, and a shop or a workshop under the size
limit is kept as a house.

This module reads the use off the QV rating roll instead. Every rating unit
carries a ``property_category`` under the Rating Valuations Rules 2008, whose
first letter is the broad use: R residential (RV vacant residential land), L
lifestyle, A, D, F, H, P and S rural, and C, I, O, U and M commercial,
industrial, other, utilities and mining. A building is a dwelling where the
property it stands on is used residentially, whatever its size.

The roll is sensitive (:mod:`landloss.io.qv_rating_roll`). Nothing here keeps a
field of it: what leaves this module is the broad use of a claim property.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.exposure.land.extent import (
    BUILDING_USE_COLUMN,
    CLAIM_ID_COLUMN,
    MAX_DWELLING_FOOTPRINT_M2,
    NON_CLAIM_SOURCES,
    SOURCE_COLUMN,
    SOURCE_ID_COLUMN,
    UNNAMED_BUILDING_USE,
    stack_representatives,
)

# The columns the roll's units arrive in, as the step builds them from
# landloss.io.qv_rating_roll: the valuation reference the LINZ property
# boundaries carry, and the unit's property category.
VALUATION_REFERENCE_COLUMN = "valuation_reference"
PROPERTY_CATEGORY_COLUMN = "property_category"

# The broad use of a rating unit, and of a claim property.
RESIDENTIAL = "residential"
LIFESTYLE = "lifestyle"
RURAL = "rural"
NON_RESIDENTIAL = "non-residential"
VACANT = "residential vacant"

# Which use a property takes where its rating units differ -- a block of unit
# titles, or shops under flats -- in order: the first any unit has. So a
# mixed-use building with a dwelling in it counts as residential, which is how
# NHC treats a building with a residential part.
USE_PRECEDENCE = (RESIDENTIAL, LIFESTYLE, RURAL, NON_RESIDENTIAL, VACANT)

# The uses that carry a dwelling. A lifestyle block or a farm has a house on it
# as much as a suburban section does.
DWELLING_USES = (RESIDENTIAL, LIFESTYLE, RURAL)

# The uses that rule a building out. Vacant residential land is deliberately
# not one: the roll is a valuation snapshot, and a house built since the
# revaluation stands on land the roll still calls vacant, so a building there
# falls back on the footprint rule rather than being dropped.
NOT_DWELLING_USES = (NON_RESIDENTIAL,)

RURAL_LETTERS = tuple("ADFHPS")
VACANT_CATEGORY = "RV"


def classify_property_category(category: pd.Series) -> pd.Series:
    """Return the broad use of each rating unit from its property category.

    Args:
        category: The roll's ``property_category`` per unit.

    Returns:
        One of :data:`USE_PRECEDENCE` per unit, or missing where the category
        is blank.
    """
    code = category.fillna("").astype(str).str.strip().str.upper()
    first = code.str[:1]
    use = pd.Series(
        np.select(
            [
                code.str.startswith(VACANT_CATEGORY),
                first == "R",
                first == "L",
                first.isin(RURAL_LETTERS),
            ],
            [VACANT, RESIDENTIAL, LIFESTYLE, RURAL],
            default=NON_RESIDENTIAL,
        ),
        index=category.index,
        dtype=object,
    )
    return use.where(code != "")


def property_use(
    boundaries: gpd.GeoDataFrame,
    units: pd.DataFrame,
    *,
    non_claim_sources: tuple[str, ...] = NON_CLAIM_SOURCES,
) -> pd.Series:
    """Return the broad use of each claim property on the rating roll.

    A unit joins to the LINZ property boundaries on the valuation reference.
    Each boundary belongs to the claim property
    :func:`~landloss.exposure.land.extent.build_claim_properties` makes of its
    stack -- the same representative row, so the same claim id -- and a
    property whose units differ takes the first use in
    :data:`USE_PRECEDENCE`.

    Args:
        boundaries: The LINZ property boundaries, carrying ``source``,
            ``source_id`` and ``valuation_reference``.
        units: The roll's units, carrying :data:`VALUATION_REFERENCE_COLUMN`
            and :data:`PROPERTY_CATEGORY_COLUMN`.
        non_claim_sources: Boundary sources that are not claims, as
            ``build_claim_properties`` takes them.

    Returns:
        The use per claim id, for the claims with a unit on the roll only. A
        claim missing from it is not on the roll.

    Raises:
        ValueError: If a frame lacks a column the join needs.
    """
    for frame, name, columns in (
        (
            boundaries,
            "boundaries",
            (SOURCE_COLUMN, SOURCE_ID_COLUMN, VALUATION_REFERENCE_COLUMN),
        ),
        (units, "units", (VALUATION_REFERENCE_COLUMN, PROPERTY_CATEGORY_COLUMN)),
    ):
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            msg = f"the {name} carry no {missing} column"
            raise ValueError(msg)

    claimable = boundaries[~boundaries[SOURCE_COLUMN].isin(non_claim_sources)]
    claimable = claimable.reset_index(drop=True)
    if claimable.empty:
        return pd.Series(dtype=object, name="property_use")
    stack = stack_representatives(claimable)
    linked = pd.DataFrame(
        {
            VALUATION_REFERENCE_COLUMN: claimable[
                VALUATION_REFERENCE_COLUMN
            ].to_numpy(),
            CLAIM_ID_COLUMN: claimable.loc[
                stack.to_numpy(), SOURCE_ID_COLUMN
            ].to_numpy(),
        }
    )
    # pandas joins a missing key to every other missing key, so both sides drop
    # theirs first.
    linked = linked[linked[VALUATION_REFERENCE_COLUMN].notna()]
    roll = pd.DataFrame(
        {
            VALUATION_REFERENCE_COLUMN: units[VALUATION_REFERENCE_COLUMN].to_numpy(),
            "use": classify_property_category(
                units[PROPERTY_CATEGORY_COLUMN]
            ).to_numpy(),
        }
    ).dropna()
    joined = linked.merge(roll, on=VALUATION_REFERENCE_COLUMN, how="inner")
    rank = {use: order for order, use in enumerate(USE_PRECEDENCE)}
    first = (
        joined.assign(rank=joined["use"].map(rank))
        .sort_values([CLAIM_ID_COLUMN, "rank"], kind="stable")
        .drop_duplicates(CLAIM_ID_COLUMN)
    )
    return first.set_index(CLAIM_ID_COLUMN)["use"].rename("property_use")


def drop_buildings_by_property_use(
    buildings: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    uses: pd.Series,
    *,
    use_column: str = BUILDING_USE_COLUMN,
    unnamed_use: str = UNNAMED_BUILDING_USE,
    max_area_m2: float = MAX_DWELLING_FOOTPRINT_M2,
) -> gpd.GeoDataFrame:
    """Keep the buildings that stand on residentially used land.

    A building stands on the claim property its representative point falls in,
    and is kept or dropped by that property's use, whatever its size:

    - **A building LINZ has named is dropped** -- a school, a hospital, a
      supermarket -- as the footprint rule does, whatever the land is used for.
    - **On land the roll uses for a dwelling** (:data:`DWELLING_USES`) it is
      kept, so an apartment block is a dwelling.
    - **On land the roll uses otherwise** (:data:`NOT_DWELLING_USES`) it is
      dropped, so a corner shop or a workshop is not.
    - **Anywhere else** -- a property not on the roll, vacant land a house may
      have been built on since, or a building outside every property -- the
      footprint rule decides: kept up to ``max_area_m2``.

    Args:
        buildings: The building outlines, carrying ``use_column``.
        properties: The claim properties, carrying ``claim_id``.
        uses: :func:`property_use`'s use per claim id.
        use_column: The outline column naming the building's use.
        unnamed_use: The value it carries when LINZ has not named the building.
        max_area_m2: The footprint rule's limit, for buildings the roll does
            not decide.

    Returns:
        A copy of the kept buildings with their original columns.

    Raises:
        ValueError: If the outlines carry no ``use_column``, or the two frames
            are in different systems.
    """
    if use_column not in buildings.columns:
        msg = (
            f"the building outlines carry no {use_column!r} column, so the "
            "named non-residential buildings cannot be identified"
        )
        raise ValueError(msg)
    if buildings.crs != properties.crs:
        msg = (
            f"the buildings are in {buildings.crs} but the properties in "
            f"{properties.crs}"
        )
        raise ValueError(msg)
    if buildings.empty:
        return buildings.copy()

    named = (
        buildings[use_column].fillna(unnamed_use).replace("", unnamed_use)
        != unnamed_use
    )
    points = gpd.GeoDataFrame(
        geometry=buildings.geometry.representative_point(), crs=buildings.crs
    )
    on = gpd.sjoin(
        points, properties[[CLAIM_ID_COLUMN, "geometry"]], predicate="within"
    )
    on = on[~on.index.duplicated()]
    use = on[CLAIM_ID_COLUMN].map(uses).reindex(buildings.index)

    dwelling = use.isin(DWELLING_USES)
    not_dwelling = use.isin(NOT_DWELLING_USES)
    small = buildings.geometry.area <= max_area_m2
    keep = ~named & (dwelling | (~not_dwelling & small))
    return buildings[keep.to_numpy()].copy()
