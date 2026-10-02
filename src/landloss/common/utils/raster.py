"""Re-expressing an extent between projections, so a clip can be made honestly.

Every reader in this study is handed an extent in the study's own projection and
a raster in whichever projection its supplier built it in. Clipping the raster
means expressing the extent in the raster's projection first, and that
conversion is where a study extent quietly loses a strip of ground. It is done
here, once, rather than in each reader and each step that goes to a grid nobody
else has clipped for it.
"""

from pyproj import CRS, Transformer

# How many intermediate points each edge of a bounding box is broken into before
# it is reprojected. See :func:`bbox_in_crs` for why a box needs any at all; 21
# is enough to hold the error under a metre across a New Zealand sized extent,
# and the cost is four transformed points against eighty.
BBOX_DENSIFY_POINTS = 21


def bbox_in_crs(
    bbox: tuple[float, float, float, float],
    from_crs: int | str | CRS,
    to_crs: int | str | CRS,
) -> tuple[float, float, float, float]:
    """Re-express a bounding box in another coordinate reference system.

    A rectangle in one projection is not a rectangle in another: its edges bow.
    Transforming only the four corners and taking their envelope therefore
    returns a box strictly *inside* the true extent, and the clip made with it
    silently drops a lens-shaped strip along whichever edges bowed outwards. On
    a Wellington-to-WGS84 transform that is nothing; on a South Island wide
    extent it is over a hundred metres, which is several cells of a 32 m grid.

    So the edges are broken into :data:`BBOX_DENSIFY_POINTS` points each before
    the envelope is taken, which is what ``Transformer.transform_bounds`` does.
    The error goes from "several cells" to well under a metre.

    Args:
        bbox: The extent (minx, miny, maxx, maxy), in ``from_crs``.
        from_crs: The coordinate reference system ``bbox`` is expressed in.
        to_crs: The coordinate reference system to express it in.

    Returns:
        The extent in ``to_crs``, never smaller than the true reprojected
        extent.
    """
    transformer = Transformer.from_crs(from_crs, to_crs, always_xy=True)
    west, south, east, north = transformer.transform_bounds(
        *bbox, densify_pts=BBOX_DENSIFY_POINTS
    )
    return (float(west), float(south), float(east), float(north))
