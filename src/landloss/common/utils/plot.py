"""Shared styling for the map panels that go into the report.

Ported from the National Liquefaction Model, so that a figure produced for this
study reads the same as one produced for that one. The two studies are shown
side by side often enough that a gratuitous difference in basemap or map
furniture would be a distraction.
"""

from typing import Any

import contextily as cx
import geopandas as gpd
from matplotlib.axes import Axes
from matplotlib_map_utils import NorthArrow
from matplotlib_scalebar.scalebar import ScaleBar

# Esri's grey canvas rather than CartoDB Positron, which now serves
# "API KEY REQUIRED" watermarked tiles at these zooms that show through the
# semi-transparent data overlays.
DEFAULT_BASEMAP = cx.providers.Esri.WorldGrayCanvas


def gen_north_arrow(scale: float = 0.3, label_size: float | None = None) -> NorthArrow:
    """Generate a north arrow for geospatial plots.

    Args:
        scale: Size of the arrow relative to the axes.
        label_size: Size of the "N" above it, in points. Drop this and ``scale``
            below their defaults for figures whose map panels are only a couple
            of inches across.

    Returns:
        The north arrow, ready to add to an axes as an artist.
    """
    label: dict[str, Any] = {"position": "top"}
    if label_size is not None:
        label["fontsize"] = label_size

    return NorthArrow(
        location="upper right",
        rotation={"degrees": 0},
        scale=scale,
        shadow=False,
        base={"facecolor": "black"},
        fancy={"facecolor": "white"},
        label=label,
        pack={"sep": 2},
    )


def gen_scalebar(font_size: float | None = None) -> ScaleBar:
    """Generate a scale bar for geospatial plots.

    Args:
        font_size: Label size in points. Leave it unset to follow the ambient
            rcParams.

    Returns:
        The scale bar, ready to add to an axes as an artist.
    """
    font_properties = None if font_size is None else {"size": font_size}
    return ScaleBar(
        dx=1.0, loc="lower right", units="m", font_properties=font_properties
    )


def style_basemap_ax(
    ax: Axes,
    extent: gpd.GeoDataFrame,
    *,
    basemap: Any = DEFAULT_BASEMAP,
    set_limits: bool = True,
    equal_aspect: bool = True,
    north_arrow: bool = True,
    scalebar: bool = True,
    reset_extent: bool = True,
    zoom_adjust: int = 1,
    arrow_kwargs: dict[str, Any] | None = None,
    scalebar_kwargs: dict[str, Any] | None = None,
) -> None:
    """Style a geospatial map panel: fix its extent, strip ticks, and add a basemap.

    Replaces easting/northing ticks and labels -- which cost room and carry little
    at report print sizes -- with an optional north arrow and scale bar. Holds the
    panel to the full ``extent`` rather than the extent of the data, which can
    stop short at the coast, so that panels stay comparable with one another.

    Note that ``equal_aspect`` is what keeps the scale bar honest: drawn on axes
    whose aspect ratio is not 1, the bar measures only the horizontal and warns.

    Args:
        ax: The map axes to style.
        extent: Region extent. Its ``total_bounds`` sets the view and its ``crs``
            the projection the basemap is fetched in.
        basemap: Contextily tile source; defaults to :data:`DEFAULT_BASEMAP`.
        set_limits: Fix the x and y limits to ``extent.total_bounds``.
        equal_aspect: Give the panel an equal aspect ratio.
        north_arrow: Add the north arrow (see :func:`gen_north_arrow`).
        scalebar: Add the scale bar (see :func:`gen_scalebar`).
        reset_extent: Passed to ``contextily.add_basemap``, keeping the axis
            limits set above.
        zoom_adjust: Passed to ``contextily.add_basemap``, controlling basemap
            tile detail.
        arrow_kwargs: Extra keyword arguments for :func:`gen_north_arrow`, such as
            ``scale`` or ``label_size`` for small panels.
        scalebar_kwargs: Extra keyword arguments for :func:`gen_scalebar`, such as
            ``font_size``.
    """
    if set_limits:
        minx, miny, maxx, maxy = extent.total_bounds
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)

    if equal_aspect:
        ax.set_aspect("equal")

    ax.set_xticks([])
    ax.set_yticks([])

    if north_arrow:
        ax.add_artist(gen_north_arrow(**(arrow_kwargs or {})))

    if scalebar:
        ax.add_artist(gen_scalebar(**(scalebar_kwargs or {})))

    cx.add_basemap(
        ax=ax,
        crs=extent.crs,
        source=basemap,
        reset_extent=reset_extent,
        zorder=0,
        zoom_adjust=zoom_adjust,
        attribution=False,
    )
