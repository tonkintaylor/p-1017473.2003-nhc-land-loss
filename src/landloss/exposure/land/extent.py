"""The insured land extent: the ground around a dwelling that NHC cover pays for.

Every hazard in this study is read against a polygon rather than against a
point. A liquefaction land damage state is sampled at the property, but a
landslide is intersected with the ground a claim actually covers, and the area
that falls inside it is the damage measure the repair cost is built from. So the
whole chain needs one polygon per claim, and this module builds it.

**The claim is the property, not the address.** That is the decision this module
is built around, and it replaces an earlier model keyed on address points. An
address point is a label on a front door: 40% of them found no building near
enough to buffer, so 40% of the portfolio carried no insured land at all, while
a block of flats put several claims on ground that settles as one. A property
boundary is the piece of land a claim is made over, which is what the policy
actually attaches to.

So:

- **The property boundary sets the claim**, one row per distinct piece of ground
  in the LINZ property boundaries, from :func:`build_claim_properties`.
- **Every building outline inside the property sets the insured land extent**,
  each buffered by :data:`INSURED_LAND_BUFFER_M` and the buffers merged. A
  garage, a sleepout and a shed are appurtenant structures and are buffered like
  the dwelling, not excluded from it.
- **The address points inside the property count the dwellings**, from
  :func:`count_dwellings`. That count is what NHC's per-dwelling sub-caps and
  excess are multiplied by, so it is what decides the retaining wall cap --
  neither the land area nor the building count does.
- **The extent is clipped to the property.** An 8 metre line from a house near a
  boundary reaches onto the neighbour's section, and that ground is not covered
  by this claim. Clipping also makes the extents pairwise disjoint without any
  further rule, which matters because the vulnerability step sums area per
  claim.

Four decisions the module makes, each of which costs something:

- **Stacked titles are one claim.** A unit-titled block carries one boundary
  polygon per unit, all on the same footprint; over the Wellington pilot 2,251
  of 7,670 boundaries were exact duplicates of another, in 255 groups. Left
  alone, each would claim the whole block's insured land and the same ground
  would be paid for many times over. They are dissolved on identical geometry,
  so near-identical footprints are not caught.
- **Roads and water are not claims.** Boundaries sourced from the road and hydro
  parcel layers are dropped by :data:`NON_CLAIM_SOURCES`; they are land with no
  dwelling on it and no residential cover over it.
- **A building LINZ has named, or one too large to be a house, is not a
  dwelling.** :func:`drop_non_residential_buildings` applies both tests. The
  outlines layer carries a ``use`` column that names schools, hospitals,
  supermarkets, huts and shelters and says ``Unknown`` for everything else, so
  it cannot confirm that a building is residential but it can rule one out; and
  a footprint over :data:`MAX_DWELLING_FOOTPRINT_M2` is a warehouse, a mall or
  an office block rather than a house, the pilot's outlines running to a median
  of 120 m2 and a 95th percentile of 290. A property left with no building at
  all then carries no extent, which is how a school site or a retail park leaves
  the portfolio without a rule of its own. Neither test can say a building *is*
  residential, so this is a tidy-up rather than the residential filter the study
  still needs.
- **A property with no address point carries no insured land.** Cover follows a
  residential building, and a dwelling count of zero is the model saying it
  cannot see one. A bare section, a garage on its own title, and a property
  whose address point LINZ has placed just outside the boundary all land in that
  group, and only the last is an error.
- **A building straddling a boundary is split, but only if it properly straddles
  it.** A piece is kept when it is the building's largest, or when it is at
  least :data:`MIN_CROSSING_AREA_M2` and :data:`MIN_CROSSING_SHARE` of the
  building. Over the pilot, 241 of 6,927 outlines cross that far and 77% of
  those span two freehold titles -- semi detached and terraced houses captured
  as one polygon, which really are two buildings on two properties. The 3,227
  outlines that overhang by less are the outline and boundary layers disagreeing
  along a shared edge, at a median of 0.30 square metres, and their overhang is
  dropped rather than made into a second building.

**Driveways are part of the real definition** and are unioned in when supplied.
They matter out of proportion to their area, because they are where most
retaining walls sit. The part of a driveway beyond the property boundary is
clipped away with everything else: it runs onto the road reserve, which the
claimant does not own.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj

from landloss.domain.loss_contract import CLAIM_ID_COLUMN

# The insured land definition: metres from the building outline. Not a tuning
# parameter -- it is NHC's own line, so it belongs here rather than in a step's
# config.py. It applies to appurtenant structures as well as to the dwelling.
INSURED_LAND_BUFFER_M = 8.0

# What counts as a building properly straddling a property boundary, rather than
# the outline layer and the boundary layer disagreeing along a shared edge. Both
# have to be passed: a share, so a large building is not split by a small
# absolute overhang, and an area, so a small shed is not split by a large
# relative one. Anything smaller is treated as a boundary error and dropped.
MIN_CROSSING_AREA_M2 = 5.0
MIN_CROSSING_SHARE = 0.10

# Boundary rows that are land rather than property. The layer fills the gaps
# between rating units with primary parcels, which brings in the road reserve
# and the waterways; neither can carry a residential claim.
NON_CLAIM_SOURCES = (
    "NZ Primary Parcels - Road",
    "NZ Primary Parcels - Hydro",
)

# The building outlines layer's ``use`` column, and the value it carries when
# LINZ has not named the building. Nationally 3,209,472 of 3,236,141 outlines are
# "Unknown" and the remainder are School, Hospital, Supermarket, Hut and Shelter,
# so the column is a gazetteer of named institutions rather than a land use
# classification: it can say a building is *not* a dwelling and never that it is.
BUILDING_USE_COLUMN = "use"
UNNAMED_BUILDING_USE = "Unknown"

# The largest footprint a building is taken to be a dwelling at. Over the pilot
# the outlines run to a median of 120 m2 and a 95th percentile of 290, so this
# sits well clear of a large house and cuts in where the warehouses, the malls
# and the office blocks are. It is a threshold on this study's own model rather
# than a line NHC draws, and it is the crude half of the filter: an apartment
# block is residential and has a footprint like a warehouse, so it goes too.
MAX_DWELLING_FOOTPRINT_M2 = 500.0

ADDRESS_ID_COLUMN = "address_id"
AREA_COLUMN = "area_m2"
PROPERTY_AREA_COLUMN = "property_area_m2"
# The area of the property an address stands on, carried on the address. What
# the land value model sizes a section by and divides the rate by.
SECTION_AREA_COLUMN = "section_area_m2"
# How many addresses stand on that property. The land value model counts each
# property once, not once per address, when it holds a TA to its average.
PROPERTY_ADDRESS_COUNT_COLUMN = "addresses_on_property"
# How many rating units the property is: the boundary rows dissolved into its
# footprint, one per unit of a unit-titled block and one for a freehold title.
PROPERTY_RATING_UNIT_COUNT_COLUMN = "rating_units_on_property"
BUILDING_COUNT_COLUMN = "building_count"
DWELLING_COUNT_COLUMN = "dwelling_count"
# What the loss module values the land from, written beside the insured land:
# the area of the buildings it is buffered off, and the suburb the claim's
# addresses mostly stand in. No land value is carried; the loss module reads
# the QV roll itself (landloss.loss.qv_land_value).
FOOTPRINT_AREA_COLUMN = "footprint_area_m2"
SUBURB_COLUMN = "suburb_locality"
BOUNDARY_ROW_COLUMN = "boundary_rows"

# Which outline a building part came from, kept because one outline can be split
# across two properties. Named for the outline rather than the building because
# the LINZ outlines layer carries a ``building_id`` of its own, which this must
# not overwrite -- several outlines can belong to one building.
OUTLINE_ID_COLUMN = "outline_id"

# The boundaries layer's own columns this module reads.
SOURCE_COLUMN = "source"
SOURCE_ID_COLUMN = "source_id"
TITLE_TYPE_COLUMN = "title_type"


def _check_projected(crs: pyproj.CRS | None) -> None:
    """Refuse a geographic system, where a buffer of 8 would be 8 degrees.

    Args:
        crs: The coordinate reference system to check.

    Raises:
        ValueError: If the system is geographic.
    """
    if crs is not None and crs.is_geographic:
        msg = (
            f"{crs} is a geographic system, so a buffer of "
            f"{INSURED_LAND_BUFFER_M} would be that many degrees, and an area "
            "would be in square degrees. Work in a projected system such as "
            "NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def _check_frames(properties: gpd.GeoDataFrame, other: gpd.GeoDataFrame) -> None:
    """Refuse inputs the buffer arithmetic would silently get wrong.

    Args:
        properties: The claim properties.
        other: The frame being combined with them.

    Raises:
        ValueError: If the two frames are in different coordinate reference
            systems, or if that system is geographic, where a buffer of 8 would
            be 8 degrees.
    """
    if properties.crs != other.crs:
        msg = (
            f"The properties are in {properties.crs} and the other layer in "
            f"{other.crs}. Reproject one onto the other before building the "
            "extent, rather than letting the join compare coordinates in two "
            "different systems."
        )
        raise ValueError(msg)

    _check_projected(properties.crs)


def drop_non_residential_buildings(
    buildings: gpd.GeoDataFrame,
    *,
    use_column: str = BUILDING_USE_COLUMN,
    unnamed_use: str = UNNAMED_BUILDING_USE,
    max_area_m2: float = MAX_DWELLING_FOOTPRINT_M2,
) -> gpd.GeoDataFrame:
    """Drop the building outlines that cannot be a home.

    NHC land cover follows a residential building, and nothing in the address,
    property or building layers says which buildings those are. Two tests are
    applied, and both rule buildings out rather than ruling them in.

    **The name.** The outlines layer's ``use`` column is the one field that says
    anything about a building's purpose, and it only ever says the opposite: it
    names schools, hospitals, supermarkets, huts and shelters, and leaves every
    other building -- 99.2% of the country -- as ``unnamed_use``. Everything
    named is dropped, rather than a list of known values being excluded, so a
    use LINZ adds to the layer later is excluded without this having to be
    edited. The cost of that choice is that it would drop the whole layer if
    LINZ ever populated the column properly, which is why the caller reports
    what it removed instead of removing it silently.

    **The size.** A footprint over ``max_area_m2`` is a warehouse, a mall or an
    office block rather than a house. It is measured on the outline as served,
    before anything is cut to a property, so a terrace captured as one large
    polygon is judged whole -- the split into one building per property happens
    downstream, in :func:`assign_buildings_to_properties`, and this runs first
    because the same outline has to be ruled in or out consistently for every
    property it touches.

    The size test is the crude one. An apartment block is residential and has
    the footprint of a warehouse, so it goes with them, and the dwellings inside
    it lose their insured land. The population left behind is still houses,
    offices and small commercial units together.

    Args:
        buildings: The LINZ NZ Building Outlines layer, carrying ``use_column``.
        use_column: The column naming the building's use.
        unnamed_use: The value the column carries when LINZ has not named it.
            A missing or blank value is treated the same way.
        max_area_m2: The largest footprint a building is taken to be a dwelling
            at.

    Returns:
        A new GeoDataFrame holding only the outlines that pass both tests,
        re-indexed from zero. The caller's frame is left untouched.

    Raises:
        ValueError: If the outlines carry no ``use_column``, or are in a
            geographic coordinate reference system, where the footprints this
            measures would be in square degrees.
    """
    _check_projected(buildings.crs)
    if use_column not in buildings.columns:
        msg = (
            f"the building outlines carry no {use_column!r} column, so the "
            "named non-residential buildings cannot be identified"
        )
        raise ValueError(msg)

    uses = buildings[use_column].fillna(unnamed_use).replace("", unnamed_use)
    keep = (uses == unnamed_use) & (buildings.geometry.area <= max_area_m2)
    return buildings[keep].reset_index(drop=True)


def stack_representatives(boundaries: gpd.GeoDataFrame) -> pd.Series:
    """Return the row that stands for each boundary's stack of titles.

    A unit-titled block carries one boundary per unit on a single footprint.
    Boundaries with exactly the same geometry are one stack, and the one with
    the lowest :data:`SOURCE_ID_COLUMN` (compared in the column's own dtype)
    represents it, so which title stands for a block does not depend on the
    order the rows arrived in. Near duplicates are not caught. This is the one
    rule every reader of the stacks uses: the claim properties, the claim and
    NZMM records and the property a retaining wall candidate lies on.

    Args:
        boundaries: LINZ property boundaries carrying :data:`SOURCE_ID_COLUMN`,
            on a unique index.

    Returns:
        Indexed like ``boundaries``: the index label of the row representing
        each row's stack (its own label where it represents itself).

    Raises:
        ValueError: If the index is not unique.
    """
    if not boundaries.index.is_unique:
        msg = "stack_representatives needs the boundaries on a unique index"
        raise ValueError(msg)
    ordered = pd.DataFrame(
        {
            "footprint": boundaries.geometry.to_wkb().to_numpy(),
            "row": boundaries.index.to_numpy(),
        },
        index=boundaries.index,
    ).loc[boundaries[SOURCE_ID_COLUMN].sort_values(kind="stable").index]
    first = ordered.groupby("footprint", sort=False)["row"].transform("first")
    return first.reindex(boundaries.index).rename("stack_row")


def build_claim_properties(
    boundaries: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    non_claim_sources: tuple[str, ...] = NON_CLAIM_SOURCES,
) -> gpd.GeoDataFrame:
    """Reduce the LINZ property boundaries to one row per claimable property.

    Two things happen. Road and water parcels are dropped, because they are land
    with no residential cover over them. Boundaries with identical geometry are
    dissolved into one, because a unit-titled block carries one boundary per unit
    on a single footprint and each of them would otherwise claim the whole
    block's insured land.

    Args:
        boundaries: The LINZ NZ Property Boundaries layer, carrying
            :data:`SOURCE_COLUMN` and :data:`SOURCE_ID_COLUMN`.
        id_column: The claim identifier to mint.
        non_claim_sources: Values of :data:`SOURCE_COLUMN` that are not claims.

    Returns:
        One row per distinct piece of ground, carrying ``id_column``,
        :data:`PROPERTY_AREA_COLUMN`, :data:`BOUNDARY_ROW_COLUMN` -- how many
        boundary rows were dissolved into it -- and the layer's own columns.

    Raises:
        ValueError: If the boundaries carry no source columns, or are in a
            geographic coordinate reference system, where the areas this
            computes would be in square degrees.
    """
    _check_projected(boundaries.crs)
    missing = [
        column
        for column in (SOURCE_COLUMN, SOURCE_ID_COLUMN)
        if column not in boundaries.columns
    ]
    if missing:
        msg = f"the property boundaries carry no {missing} column"
        raise ValueError(msg)

    claimable = boundaries[~boundaries[SOURCE_COLUMN].isin(non_claim_sources)]
    claimable = claimable.reset_index(drop=True)
    if claimable.empty:
        return claimable.assign(
            **{id_column: [], PROPERTY_AREA_COLUMN: [], BOUNDARY_ROW_COLUMN: []}
        )

    # Exact geometric equality, which is what stacked unit titles are
    # (stack_representatives). Near duplicates are not caught, and the run
    # reports what is left overlapping.
    stack = stack_representatives(claimable)
    rows = stack.map(stack.value_counts())
    properties = claimable.assign(**{BOUNDARY_ROW_COLUMN: rows.to_numpy()})[
        stack.to_numpy() == claimable.index.to_numpy()
    ].copy()
    properties[id_column] = properties[SOURCE_ID_COLUMN].to_numpy()
    properties[PROPERTY_AREA_COLUMN] = properties.geometry.area
    return properties.reset_index(drop=True)


def count_dwellings(
    properties: gpd.GeoDataFrame,
    addresses: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    address_id_column: str = ADDRESS_ID_COLUMN,
) -> pd.DataFrame:
    """Attribute each address point to the property it stands inside.

    The number of rows per property is the number of dwellings on the claim,
    which is what NHC's per-dwelling sub-caps and excess are multiplied by -- so
    it is what sets the retaining wall cap, not the land area and not the count
    of buildings.

    An address point falling in two overlapping properties is counted once, in
    the lower claim identifier, so the dwellings across the portfolio add up.

    Args:
        properties: The claim properties, carrying ``id_column``.
        addresses: The address points, carrying ``address_id_column``.
        id_column: The claim identifier.
        address_id_column: The address identifier.

    Returns:
        One row per address that landed in a property, carrying both
        identifiers. Addresses outside every property are absent, which is what
        makes them countable.
    """
    if addresses.empty or properties.empty:
        return pd.DataFrame({address_id_column: [], id_column: []})

    located = gpd.sjoin(
        addresses[[address_id_column, addresses.geometry.name]].reset_index(drop=True),
        properties[[id_column, properties.geometry.name]],
        how="inner",
        predicate="within",
    )
    ordered = located.sort_values(id_column, kind="stable")
    ordered = ordered[~ordered.index.duplicated(keep="first")]
    return ordered[[address_id_column, id_column]].reset_index(drop=True)


def section_area_per_address(
    properties: gpd.GeoDataFrame,
    addresses: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    address_id_column: str = ADDRESS_ID_COLUMN,
) -> pd.DataFrame:
    """Give every address the area of the property it stands on.

    The whole property's area, not a share of it. A published land value is for
    the property, however many addresses LINZ has put on it: 13 Lawrence Street,
    Newtown, is one 170 m2 property valued at $540,000 with three address points,
    and splitting its area three ways doubled its modelled rate per square metre.
    Every address on a property therefore carries the same area, and so the same
    size factor and the same rate. The addresses are placed by
    :func:`count_dwellings`, so an address in two overlapping properties is
    placed once.

    Args:
        properties: The claim properties, carrying ``id_column`` and
            :data:`PROPERTY_AREA_COLUMN`, as :func:`build_claim_properties`
            returns them.
        addresses: The address points, carrying ``address_id_column``.
        id_column: The claim identifier.
        address_id_column: The address identifier.

    Returns:
        One row per address that landed in a property, carrying
        ``address_id_column``, ``id_column``, :data:`SECTION_AREA_COLUMN` in
        square metres, :data:`PROPERTY_ADDRESS_COUNT_COLUMN` and
        :data:`PROPERTY_RATING_UNIT_COUNT_COLUMN`. Addresses outside every
        property are absent.

    Raises:
        ValueError: If the properties are in a geographic coordinate reference
            system, where their areas would be in square degrees.
    """
    _check_projected(properties.crs)

    placed = count_dwellings(
        properties, addresses, id_column=id_column, address_id_column=address_id_column
    )
    if placed.empty:
        return placed.assign(
            **{
                SECTION_AREA_COLUMN: pd.Series(dtype=float),
                PROPERTY_ADDRESS_COUNT_COLUMN: pd.Series(dtype=int),
                PROPERTY_RATING_UNIT_COUNT_COLUMN: pd.Series(dtype=int),
            }
        )

    indexed = properties.set_index(id_column)
    area = placed[id_column].map(indexed[PROPERTY_AREA_COLUMN])
    sharing = placed.groupby(id_column)[address_id_column].transform("size")
    # A property built without the dissolve count is one rating unit.
    units = (
        placed[id_column].map(indexed[BOUNDARY_ROW_COLUMN])
        if BOUNDARY_ROW_COLUMN in indexed.columns
        else 1
    )
    return placed.assign(
        **{
            SECTION_AREA_COLUMN: area,
            PROPERTY_ADDRESS_COUNT_COLUMN: sharing,
            PROPERTY_RATING_UNIT_COUNT_COLUMN: units,
        }
    )


def assign_buildings_to_properties(
    buildings: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
    min_crossing_area_m2: float = MIN_CROSSING_AREA_M2,
    min_crossing_share: float = MIN_CROSSING_SHARE,
) -> gpd.GeoDataFrame:
    """Cut every building outline to the properties it stands on.

    A building wholly inside one property comes back whole. A building properly
    straddling a boundary -- a semi detached pair or a terrace captured as one
    polygon -- comes back as one part per property, because those really are two
    buildings on two pieces of land. A building overhanging a boundary by less
    than the thresholds comes back whole on the property that holds most of it,
    the overhang being the two layers disagreeing rather than a building on two
    titles.

    Args:
        buildings: The building outlines.
        properties: The claim properties, carrying ``id_column``.
        id_column: The claim identifier.
        min_crossing_area_m2: The smallest piece that counts as a real crossing.
        min_crossing_share: The smallest share of a building that does.

    Returns:
        One row per building part, carrying ``id_column``,
        :data:`OUTLINE_ID_COLUMN` and the part's own geometry. A building
        standing on no property at all is absent.
    """
    empty = buildings.iloc[:0].assign(**{id_column: [], OUTLINE_ID_COLUMN: []})
    if buildings.empty or properties.empty:
        return empty

    indexed = buildings.reset_index(drop=True)
    indexed[OUTLINE_ID_COLUMN] = np.arange(len(indexed))
    whole_area = indexed.set_index(OUTLINE_ID_COLUMN).geometry.area

    pieces = gpd.overlay(
        indexed[[OUTLINE_ID_COLUMN, indexed.geometry.name]],
        properties[[id_column, properties.geometry.name]],
        how="intersection",
        keep_geom_type=True,
    )
    pieces = pieces[~pieces.geometry.is_empty]
    if pieces.empty:
        return empty

    pieces = pieces.assign(_piece_area=pieces.geometry.area)
    pieces["_share"] = pieces["_piece_area"] / pieces[OUTLINE_ID_COLUMN].map(whole_area)

    # The largest piece is always kept, so a building smaller than the crossing
    # threshold is not dropped entirely for being small. Every other piece has
    # to clear both thresholds to be a building in its own right.
    largest = pieces.groupby(OUTLINE_ID_COLUMN)["_piece_area"].transform("max")
    keep = (pieces["_piece_area"] >= largest) | (
        (pieces["_piece_area"] >= min_crossing_area_m2)
        & (pieces["_share"] >= min_crossing_share)
    )
    kept = pieces[keep].drop(columns=["_piece_area", "_share"])
    return kept.sort_values([id_column, OUTLINE_ID_COLUMN]).reset_index(drop=True)


def buffer_buildings(
    parts: gpd.GeoDataFrame,
    *,
    buffer_m: float = INSURED_LAND_BUFFER_M,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Buffer the building parts and merge them into one polygon per claim.

    A property with a house, a garage and a sleepout has three overlapping
    buffers, and the insured land around it is one piece of ground rather than
    three, so they are dissolved before anything measures an area. The
    appurtenant structures are buffered exactly as the dwelling is.

    Args:
        parts: The building parts, carrying ``id_column``.
        buffer_m: How far the insured land reaches from an outline.
        id_column: The claim identifier to dissolve on.

    Returns:
        One row per claim, carrying ``id_column``,
        :data:`BUILDING_COUNT_COLUMN` and the buffered polygon.
    """
    buffered = gpd.GeoDataFrame(
        parts[[id_column]].copy(),
        geometry=parts.geometry.buffer(buffer_m),
        crs=parts.crs,
    )
    counts = buffered.groupby(id_column).size().rename(BUILDING_COUNT_COLUMN)
    dissolved = buffered.dissolve(by=id_column)
    return dissolved.join(counts).reset_index()


def add_driveways(
    parts: gpd.GeoDataFrame,
    driveways: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Union each claim's driveway corridors into its buffered extent.

    Args:
        parts: One buffered polygon per claim, as :func:`buffer_buildings`
            returns.
        driveways: The driveway corridors, keyed on ``id_column``.
        id_column: The claim identifier both are keyed on.

    Returns:
        ``parts`` with each claim's driveways unioned into its polygon. The part
        of a driveway outside the property is removed later, when the extent is
        clipped, because it runs onto the road reserve.
    """
    corridors = driveways.dissolve(by=id_column).geometry
    merged = parts.copy()
    additions = merged[id_column].map(corridors)
    has_driveway = additions.notna()
    merged.loc[has_driveway, merged.geometry.name] = [
        polygon.union(addition)
        for polygon, addition in zip(
            merged.loc[has_driveway, merged.geometry.name],
            additions[has_driveway],
            strict=True,
        )
    ]
    return merged


def clip_to_property(
    parts: gpd.GeoDataFrame,
    properties: gpd.GeoDataFrame,
    *,
    id_column: str = CLAIM_ID_COLUMN,
) -> gpd.GeoDataFrame:
    """Cut each claim's extent back to the property it is claimed over.

    This is what keeps the extents from overlapping one another, and it replaces
    the rule the address-keyed model needed -- partitioning contested ground
    between neighbours on which building was nearest. With a boundary to cut
    against there is nothing to arbitrate: land belongs to whoever owns it.

    Args:
        parts: One buffered polygon per claim, carrying ``id_column``.
        properties: The claim properties, carrying ``id_column``.
        id_column: The claim identifier.

    Returns:
        ``parts`` clipped to each claim's own property. A claim left with no
        ground at all is dropped.
    """
    boundary = properties.set_index(id_column).geometry
    own = parts[id_column].map(boundary)
    clipped = [
        polygon.intersection(limit) if limit is not None else None
        for polygon, limit in zip(parts.geometry, own, strict=True)
    ]
    out = parts.set_geometry(gpd.GeoSeries(clipped, index=parts.index, crs=parts.crs))
    return out[~(out.geometry.isna() | out.geometry.is_empty)]


def build_insured_land_extent(
    properties: gpd.GeoDataFrame,
    buildings: gpd.GeoDataFrame,
    dwellings: pd.DataFrame,
    *,
    driveways: gpd.GeoDataFrame | None = None,
    buffer_m: float = INSURED_LAND_BUFFER_M,
) -> gpd.GeoDataFrame:
    """Build one insured land polygon per claim from the buildings on it.

    Every building standing on a property is buffered by ``buffer_m``, the
    buffers are merged, the driveways are unioned in, and the result is clipped
    back to the property. Appurtenant structures are buffered like the dwelling.
    The module docstring sets out what each of those steps costs.

    Args:
        properties: The claim properties, from :func:`build_claim_properties`.
        buildings: The building outlines over the same extent.
        dwellings: The address-to-claim rows from :func:`count_dwellings`. A
            property with none of them carries no residential cover and is
            dropped.
        driveways: The driveway corridors, keyed on the claim identifier.
        buffer_m: How far the insured land reaches from a building outline.

    Returns:
        One row per claim with a building and at least one dwelling, carrying
        :data:`CLAIM_ID_COLUMN`, :data:`BUILDING_COUNT_COLUMN`,
        :data:`DWELLING_COUNT_COLUMN`, :data:`PROPERTY_AREA_COLUMN`,
        :data:`AREA_COLUMN` and the polygon, in claim order. The polygons do not
        overlap one another.

    Raises:
        ValueError: If the frames disagree on their coordinate reference system,
            or that system is geographic.
    """
    _check_frames(properties, buildings)

    id_column = CLAIM_ID_COLUMN
    columns = [
        id_column,
        BUILDING_COUNT_COLUMN,
        DWELLING_COUNT_COLUMN,
        PROPERTY_AREA_COLUMN,
        AREA_COLUMN,
    ]
    counts = dwellings.groupby(id_column).size().rename(DWELLING_COUNT_COLUMN)
    occupied = properties[properties[id_column].isin(counts.index)]
    parts = (
        assign_buildings_to_properties(buildings, occupied, id_column=id_column)
        if not occupied.empty
        else occupied.iloc[:0]
    )
    if parts.empty:
        return gpd.GeoDataFrame(
            {column: [] for column in columns}, geometry=[], crs=properties.crs
        )

    extent = buffer_buildings(parts, buffer_m=buffer_m, id_column=id_column)
    if driveways is not None and not driveways.empty:
        extent = add_driveways(extent, driveways, id_column=id_column)
    extent = clip_to_property(extent, occupied, id_column=id_column)

    extent[DWELLING_COUNT_COLUMN] = extent[id_column].map(counts).astype(int)
    extent[PROPERTY_AREA_COLUMN] = extent[id_column].map(
        occupied.set_index(id_column)[PROPERTY_AREA_COLUMN]
    )
    extent[AREA_COLUMN] = extent.geometry.area

    return (
        extent[[*columns, extent.geometry.name]]
        .sort_values(id_column, kind="stable")
        .reset_index(drop=True)
    )
