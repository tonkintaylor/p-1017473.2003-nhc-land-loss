"""Waterways for the study area, split into named rivers and everything else.

Distance to a waterway free-face drives lateral spreading, but not every
watercourse is a free-face: a major river has banks metres high, while a piped
or shallow urban stream has effectively none. The split kept here is the one the
National Liquefaction Model uses -- a feature counts as a river when its name
says so -- so that the two studies classify the same watercourse the same way.

The smaller watercourses are kept rather than discarded, because the report has
to show what was considered and rejected, not only what was used.
"""

import geopandas as gpd
from shapely import is_empty, is_missing
from shapely.geometry.base import BaseGeometry

from landloss.domain import constants
from landloss.io.readers import get_nz_river_name_lines

# A feature is treated as a river when this appears in its name, matched case
# insensitively. Crude, but it is what the source layer supports: ``feat_type``
# does not reliably separate a river from a stream across the country.
RIVER_NAME_PATTERN = "river"

# The values the ``wtype`` column takes.
WATERWAY_TYPES = ("river", "other")


def classify_waterways(waterways: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Tag each watercourse as a named river or as other, and drop empty geometry.

    Kept separate from :func:`get_waterways` so that the classification can be
    exercised without reaching for the network.

    Args:
        waterways: Watercourse centrelines carrying a ``name`` column.

    Returns:
        A copy with a ``wtype`` column added, holding one of
        :data:`WATERWAY_TYPES`, and with null or empty geometry removed.
    """
    classified = waterways.copy()

    # ``na=False`` sends unnamed features to "other" rather than to NaN; an
    # unnamed watercourse is not one of the major rivers by definition.
    is_river = classified["name"].str.contains(RIVER_NAME_PATTERN, case=False, na=False)
    classified["wtype"] = is_river.map({True: "river", False: "other"})

    # Tested at the shapely level rather than with GeoSeries.notna, which warns
    # when the series holds empty geometry -- and empty geometry is exactly the
    # case being looked for here.
    geometries = classified.geometry.to_numpy()
    keep = ~is_missing(geometries) & ~is_empty(geometries)
    return classified.loc[keep].reset_index(drop=True)


def get_waterways(
    bbox: tuple[float, float, float, float] | None = None,
    crs: int | str = constants.DEFAULT_CRS,
    clip_to: gpd.GeoDataFrame | gpd.GeoSeries | BaseGeometry | None = None,
    *,
    use_cache: bool = True,
) -> gpd.GeoDataFrame:
    """Load the watercourses for an extent, tagged as named rivers or other.

    A bounding box is a rectangle, and the study area is not: reading the four
    Wellington territorial authorities by their bounds alone also picks up much
    of the Wairarapa, whose rivers are not part of this study. Pass ``clip_to``
    as well to cut the result back to the real boundary, while ``bbox`` keeps the
    read itself cheap.

    Args:
        bbox: The extent to read (minx, miny, maxx, maxy) in ``crs``. Omitting it
            reads every watercourse in New Zealand, which is rarely wanted.
        crs: The coordinate reference system to return the watercourses in.
        clip_to: Optionally, a boundary to cut the watercourses back to, in
            ``crs``. Anything ``geopandas.clip`` accepts.
        use_cache: Whether to read and write the clipped extent cache.

    Returns:
        A GeoDataFrame of watercourse centrelines with a ``wtype`` column.
    """
    waterways = get_nz_river_name_lines(bbox=bbox, crs=crs, use_cache=use_cache)

    if clip_to is not None:
        # Clip before classifying, so that the empty geometry a clip leaves
        # behind is dropped by classify_waterways rather than reaching the plot.
        waterways = waterways.clip(clip_to)

    return classify_waterways(waterways)
