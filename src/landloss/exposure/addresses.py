"""The address points the whole study runs over: the spine of the exposure model.

NHC cover attaches at property level, so every number this study produces -- a
hazard sampled, a land value estimated, a loss accumulated -- has to hang off a
property. The LINZ NZ Addresses layer is what that spine is built from, and the
LINZ property ID carried on it is the identifier chosen to join everything else
back to.

The layer is used rather than a parcel layer because it already carries
``territorial_authority`` and ``suburb_locality`` on every point. Those two
columns are what let the results be reported per TA and per suburb without a
spatial join against boundaries that would have to be sourced, cleaned and kept
in step, and their values match :data:`landloss.domain.constants.STUDY_AREA_TA_CODES`
exactly.

What the layer does not carry should be stated plainly, because it bounds what
can be claimed downstream. There is no land area on an address point, so lot size
has to come from elsewhere, and there is no residential or commercial flag, so
the population cannot yet be narrowed to the dwellings NHC actually covers. Until
parcel data arrives, the exposure population is simply every current land
address in the study area, and any per-property figure built on it inherits that
approximation.
"""

import geopandas as gpd
from shapely import is_empty, is_missing
from shapely.geometry.base import BaseGeometry

from landloss.domain import constants
from landloss.io.readers import get_nz_addresses

# The columns carried forward out of the address layer. Everything else on the
# source layer -- road names, unit numbers, audit fields -- is dropped, so that
# the frames handed around the rest of the study stay small and the columns that
# results are grouped by are obvious.
ADDRESS_COLUMNS = (
    "address_id",
    "territorial_authority",
    "suburb_locality",
    "town_city",
    "geometry",
)

# An address is only part of the exposure population while it is current. The
# layer also carries retired and proposed addresses, which either no longer exist
# on the ground or do not exist yet, and neither can suffer a loss.
CURRENT_LIFECYCLE = "Current"

# ``is_land`` is "T" for an address on land and "F" for one on water -- a marina
# berth, a jetty. Water addresses have no land to lose, so they are excluded.
LAND_FLAG = "T"

# Checked before any filtering, because the two flag columns are consumed by the
# filter itself and so are gone from the result.
REQUIRED_COLUMNS = ("address_lifecycle", "is_land", *ADDRESS_COLUMNS)


def filter_addresses(addresses: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Cut an address layer back to the current land addresses, and trim columns.

    Kept separate from :func:`get_addresses` so that the filtering can be
    exercised without reaching for the network.

    Args:
        addresses: Address points carrying at least :data:`REQUIRED_COLUMNS`.

    Returns:
        A new GeoDataFrame holding only :data:`ADDRESS_COLUMNS`, restricted to
        current addresses on land with usable geometry, and re-indexed from zero.
        The caller's frame is left untouched.

    Raises:
        ValueError: If any of :data:`REQUIRED_COLUMNS` is absent, naming the
            columns that are missing.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in addresses.columns]
    if missing:
        msg = (
            f"The address layer is missing the column(s) {', '.join(missing)}. "
            f"Expected all of: {', '.join(REQUIRED_COLUMNS)}."
        )
        raise ValueError(msg)

    is_current = addresses["address_lifecycle"] == CURRENT_LIFECYCLE
    is_on_land = addresses["is_land"] == LAND_FLAG

    # Tested at the shapely level rather than with GeoSeries.notna, which warns
    # when the series holds empty geometry -- and empty geometry is exactly the
    # case being looked for here. Clipping to a boundary is what produces it.
    geometries = addresses.geometry.to_numpy()
    has_geometry = ~is_missing(geometries) & ~is_empty(geometries)

    keep = is_current & is_on_land & has_geometry

    # ``.loc`` with a boolean mask returns a copy, so selecting and re-indexing
    # here cannot write back through to the frame that was passed in.
    return addresses.loc[keep, list(ADDRESS_COLUMNS)].reset_index(drop=True)


def get_addresses(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    clip_to: gpd.GeoDataFrame | gpd.GeoSeries | BaseGeometry | None = None,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the exposure population of addresses for an extent.

    A bounding box is a rectangle, and the study area is not: reading the four
    Wellington territorial authorities by their bounds alone also picks up much
    of the Wairarapa, whose addresses are not part of this study. Pass ``clip_to``
    as well to cut the result back to the real boundary, while ``bbox`` keeps the
    read itself cheap.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``. Omitting it
            reads every address in New Zealand, which is rarely wanted.
        crs: The coordinate reference system to return the addresses in.
        clip_to: Optionally, a boundary to cut the addresses back to, in ``crs``.
            Anything ``geopandas.clip`` accepts.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of current land addresses holding :data:`ADDRESS_COLUMNS`.
    """
    addresses = get_nz_addresses(bbox=bbox, crs=crs, use_cache=use_cache)

    if clip_to is not None:
        # Clip before filtering, so that the empty geometry a clip leaves behind
        # is dropped by filter_addresses rather than reaching the exposure model.
        addresses = addresses.clip(clip_to)

    return filter_addresses(addresses)
