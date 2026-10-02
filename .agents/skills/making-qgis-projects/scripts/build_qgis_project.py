"""Build a QGIS project (.qgs) from a JSON layer spec, using this study's colour maps.

Run with the repo venv (it imports rasterio, geopandas, pyproj, tdrive_sync and
landloss.common.utils.colors):

    SKILL=.agents/skills/making-qgis-projects
    uv run --frozen python $SKILL/scripts/build_qgis_project.py spec.json

The .qgs is written as plain XML, so no QGIS install or PyQGIS is needed to build it.
See ../SKILL.md for the spec format and ../references/qgs-xml-notes.md for the XML
details that are easy to get wrong.

Ported from the National Liquefaction Model's ``nlm-qgis-project`` skill. Two things
differ, both because this project stores its data differently. Paths resolve through
``tdrive_sync`` rather than the NLM's release-tree constants, across the three tiers
this project keeps data in -- the versioned store, source material, and the
gitignored ``temp/`` working area. And vectors can be coloured by a field, because this
study's headline outputs are polygons with a class column rather than rasters.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.sax.saxutils import escape, quoteattr

QGIS_VERSION = "3.34.0-Prizren"

# The Wellington region in NZTM, used as the canvas whenever no layer extent could be
# read -- which is the normal case for a project built to point at T:.
WELLINGTON_EXTENT = (1_723_000.0, 5_403_000.0, 1_800_000.0, 5_470_000.0)
DEFAULT_CRS = "EPSG:2193"

RASTER_SUFFIXES = frozenset({".tif", ".tiff", ".vrt", ".asc", ".nc"})

# This project writes ``.geoparquet``, which geopandas reads only through
# ``read_parquet`` -- ``read_file`` hands it to OGR and fails obscurely.
PARQUET_SUFFIXES = frozenset({".parquet", ".geoparquet"})

# The stores this project keeps data in. A layer names one of these, or gives an
# explicit ``path``. See ../SKILL.md for which holds what.
STORES = ("versioned", "source_material", "temp")

# shapely's geometry type names against the ones the symbol builder uses. Only
# lines differ, and that one difference is silent: a line layer handed a fill
# symbol loads, reports valid, and draws nothing.
GEOMETRY_NAMES = {"linestring": "line", "linearring": "line"}

# The QGIS provider each kind of layer is read through. The legend entry and the
# map layer have to agree on this or the layer silently drops out of the tree.
PROVIDERS = {"raster": "gdal", "vector": "ogr", "basemap": "wms"}

# Tile basemaps, by the name a layer spec asks for them with. These are XYZ tile
# services read live over the network rather than files, so nothing about them
# resolves through a store and nothing is cached: a project carrying one needs an
# internet connection to draw it, which a project meant for offline work does not
# want.
#
# The braces in the URL are percent-encoded because the datasource is a query
# string and QGIS parses it before it substitutes the tile numbers.
BASEMAPS = {
    "osm": {
        "name": "OpenStreetMap",
        "url": "https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png",
        "zmin": 0,
        "zmax": 19,
        # https://www.openstreetmap.org/copyright -- ODbL. Anything published
        # over this basemap has to credit OpenStreetMap contributors.
        "attribution": "© OpenStreetMap contributors",
    },
}


# -------------------------------------------------------------------------------------
# Colour handling
# -------------------------------------------------------------------------------------


def _split_color(value: str) -> tuple[str, int]:
    """Split a colour into ``(#rrggbb, alpha 0-255)``.

    Args:
        value: ``#rrggbb``, ``#rrggbbaa``, or the literal ``"transparent"``.

    Returns:
        The six-digit colour and its alpha byte, which the .qgs format wants as
        two separate attributes.
    """
    if value == "transparent":
        return "#000000", 0
    if len(value) == 9:
        return value[:7], int(value[7:9], 16)
    return value, 255


def _ramp_dict(style: str, spec: dict[str, Any]) -> dict[tuple[float, float], str]:
    """Resolve a raster style name to a ``{(lower, upper): hex}`` band dict.

    The named maps come from :mod:`landloss.common.utils.colors`, so a QGIS layer and
    the report figure of the same quantity are coloured identically -- somebody
    comparing the two should not have to re-learn the legend.

    Args:
        style: The style name from the layer spec.
        spec: The layer spec, read for ``cmap``, ``min``, ``max`` and ``steps``
            when the style is ``cmap``.

    Returns:
        One entry per band, keyed by its bounds.

    Raises:
        ValueError: If the style is not one this builder knows.
    """
    from landloss.common.utils import colors

    named = {
        "eil_probability": colors.EIL_PROBABILITY_COLOURS,
        "slope": colors.SLOPE_DEGREE_COLOURS,
    }

    if style in named:
        return named[style]

    if style == "cmap":
        # The generic fallback, for a quantity with no house colour map yet.
        import numpy as np
        from matplotlib import colormaps
        from matplotlib.colors import to_hex

        low = float(spec.get("min", 0))
        high = float(spec.get("max", 1))
        steps = int(spec.get("steps", 10))
        edges = np.linspace(low, high, steps + 1)
        cmap = colormaps[spec.get("cmap", "viridis")]
        return {
            (round(float(edges[i]), 6), round(float(edges[i + 1]), 6)): to_hex(
                cmap(i / max(steps - 1, 1))
            )
            for i in range(steps)
        }

    known = sorted([*named, "cmap", "classes", "gray"])
    msg = (
        f"Unknown raster style {style!r}. Use one of {known}, or add the house colour "
        f"map to landloss.common.utils.colors and register it here."
    )
    raise ValueError(msg)


def _ramp_items(bands: dict[tuple[float, float], str]) -> str:
    """Build the colour-ramp items for a DISCRETE shader.

    In a DISCRETE ramp an item colours every value up to and including its own value, so
    the item value is the band's upper edge. An open-ended band is marked by setting
    upper equal to lower: leading means "everything below", trailing means "everything
    above" (an inf item).

    Args:
        bands: The bands, keyed by ``(lower, upper)``.

    Returns:
        The ``<item/>`` elements, ready to drop into a colour ramp shader.
    """
    # Sorted rather than trusted in insertion order, because position is what tells an
    # "everything below" band from an "everything above" one.
    entries = sorted(bands.items(), key=lambda kv: kv[0])
    items = []
    for idx, ((lower, upper), color) in enumerate(entries):
        hexcode, alpha = _split_color(color)
        open_ended = upper <= lower
        if open_ended and idx == len(entries) - 1:
            value, label = "inf", f"> {lower:g}"
        elif open_ended:
            value, label = f"{lower:g}", f"< {lower:g}"
        else:
            value, label = f"{upper:g}", f"{lower:g} - {upper:g}"
        items.append(
            f'<item value="{value}" color="{hexcode}" label={quoteattr(label)} '
            f'alpha="{alpha}"/>'
        )
    return "\n            ".join(items)


def _palette_entries(classes: dict[str, Any]) -> str:
    """Build paletted-renderer entries from ``{code: [hex, label]}`` or ``{code: hex}``.

    Args:
        classes: The class codes and their colours.

    Returns:
        The ``<paletteEntry/>`` elements.
    """
    entries = []
    for code, value in sorted(classes.items(), key=lambda kv: float(kv[0])):
        color, label = value if isinstance(value, list) else (value, str(code))
        hexcode, alpha = _split_color(color)
        entries.append(
            f'<paletteEntry value="{code}" color="{hexcode}" label={quoteattr(label)} '
            f'alpha="{alpha}"/>'
        )
    return "\n          ".join(entries)


def _categories(layer: dict[str, Any]) -> dict[str, Any]:
    """Resolve a vector layer's categories, by name or from the spec.

    Args:
        layer: The layer spec, carrying ``categories`` either as a name from
            :mod:`landloss.common.utils.colors` or as an explicit mapping.

    Returns:
        ``{value: [colour, label]}``.

    Raises:
        ValueError: If a named category set is not one this builder knows.
    """
    from landloss.common.utils import colors

    named = {
        "land_class": colors.LAND_CLASS_COLOURS,
        "gwrc_severity": colors.GWRC_SEVERITY_COLOURS,
        "land_damage_state": colors.LAND_DAMAGE_STATE_COLOURS,
    }

    categories = layer.get("categories")
    if isinstance(categories, str):
        if categories not in named:
            msg = (
                f"Unknown category set {categories!r}. Use one of {sorted(named)}, "
                f"give the categories explicitly, or add the map to "
                f"landloss.common.utils.colors and register it here."
            )
            raise ValueError(msg)
        return {str(k): list(v) for k, v in named[categories].items()}

    return {
        str(k): (v if isinstance(v, list) else [v, str(k)])
        for k, v in categories.items()
    }


# -------------------------------------------------------------------------------------
# XML fragments
# -------------------------------------------------------------------------------------


def _srs_block(authid: str) -> str:
    """Build the ``<spatialrefsys>`` block for a CRS.

    Args:
        authid: The CRS, as anything pyproj accepts (normally ``EPSG:2193``).

    Returns:
        The XML block, used for the project CRS, the canvas and every layer.
    """
    from pyproj import CRS

    crs = CRS.from_user_input(authid)
    operation = crs.coordinate_operation
    method = (operation.method_name if operation else "").lower()
    projection = "tmerc" if "transverse mercator" in method else "longlat"
    return f"""<spatialrefsys nativeFormat="Wkt">
      <wkt>{escape(crs.to_wkt())}</wkt>
      <srsid>0</srsid>
      <srid>{crs.to_epsg()}</srid>
      <authid>{authid}</authid>
      <description>{escape(crs.name)}</description>
      <projectionacronym>{projection}</projectionacronym>
      <ellipsoidacronym>EPSG:7019</ellipsoidacronym>
      <geographicflag>{"true" if crs.is_geographic else "false"}</geographicflag>
    </spatialrefsys>"""


def _raster_renderer(layer: dict[str, Any]) -> str:
    """Build the renderer for a raster layer.

    Args:
        layer: The layer spec.

    Returns:
        The ``<rasterrenderer>`` block.

    Raises:
        ValueError: If style ``classes`` is asked for with no classes given.
    """
    style = layer.get("style", "gray")

    if style == "classes":
        classes = layer.get("classes")
        if isinstance(classes, str):
            # A named class set, so a classified raster and a vector of the same
            # quantity cannot end up carrying different legends.
            classes = _categories({**layer, "categories": classes})
        if not classes:
            msg = (
                f"Layer {layer['name']!r} uses style 'classes' but gives no 'classes'."
            )
            raise ValueError(msg)
        return f"""<rasterrenderer type="paletted" band="1" opacity="1" alphaBand="-1"
                        nodataColor="">
        <rasterTransparency/>
        <colorPalette>
          {_palette_entries(classes)}
        </colorPalette>
      </rasterrenderer>"""

    if style == "gray":
        low, high = layer.get("min", 0), layer.get("max", 1)
        return f"""<rasterrenderer type="singlebandgray" band="1" opacity="1"
                        alphaBand="-1" gradient="BlackToWhite" nodataColor="">
        <rasterTransparency/>
        <contrastEnhancement>
          <minValue>{low}</minValue>
          <maxValue>{high}</maxValue>
          <algorithm>StretchToMinimumMaximum</algorithm>
        </contrastEnhancement>
      </rasterrenderer>"""

    bands = _ramp_dict(style, layer)
    edges = [edge for band in bands for edge in band]
    finite = [e for e in edges if abs(e) != float("inf")]
    return f"""<rasterrenderer type="singlebandpseudocolor" band="1" opacity="1"
                        alphaBand="-1" classificationMin="{min(finite)}"
                        classificationMax="{max(finite)}" nodataColor="">
        <rasterTransparency/>
        <rastershader>
          <colorrampshader colorRampType="DISCRETE" classificationMode="2" clip="0"
                           minimumValue="{min(finite)}" maximumValue="{max(finite)}"
                           labelPrecision="2">
            {_ramp_items(bands)}
          </colorrampshader>
        </rastershader>
      </rasterrenderer>"""


def _symbol_xml(
    name: str,
    geometry: str,
    *,
    color: str,
    outline: str,
    width: float,
    size: float,
    centroid_marker: float | None = None,
) -> str:
    """Build one ``<symbol>`` element.

    Args:
        name: The symbol's name, which a categorised renderer matches against the
            ``symbol`` attribute of its category.
        geometry: ``polygon``, ``line`` or ``point``.
        color: The fill or line colour, as ``#rrggbb`` or ``#rrggbbaa``.
        outline: The outline colour.
        width: Line or outline width, in millimetres.
        size: Marker size, for point geometry.
        centroid_marker: If set, the diameter in millimetres of a dot drawn at
            each polygon's centroid on top of the fill. Real ground units shrink
            with the map; this does not, so a feature smaller than a pixel stays
            visible instead of disappearing. See :func:`_vector_renderer`.

    Returns:
        The symbol element, without its enclosing renderer.
    """
    fill, alpha = _split_color(color)
    # "match" outlines a feature in its own fill colour. For a feature a pixel or
    # two across that is the difference between a smudge and a readable dot, and
    # unlike a marker it claims no more ground than the polygon covers -- it is
    # the polygon's own boundary.
    stroke, stroke_alpha = _split_color(color if outline == "match" else outline)
    rgba = f"{int(fill[1:3], 16)},{int(fill[3:5], 16)},{int(fill[5:7], 16)},{alpha}"
    # The outline's own alpha, not a hardcoded 255. A polygon smaller than a pixel is
    # drawn as its outline alone, so an outline forced opaque turns every small feature
    # black and hides the category colour the layer exists to show -- which looks like a
    # broken renderer rather than a styling choice.
    stroke_rgba = (
        f"{int(stroke[1:3], 16)},{int(stroke[3:5], 16)},{int(stroke[5:7], 16)},"
        f"{stroke_alpha}"
    )

    if geometry == "point":
        symbol_type, layer_class = "marker", "SimpleMarker"
        props = (
            f'<Option type="QString" name="color" value="{rgba}"/>'
            f'<Option type="QString" name="outline_color" value="{stroke_rgba}"/>'
            f'<Option type="QString" name="size" value="{size}"/>'
            f'<Option type="QString" name="name" value="circle"/>'
        )
    elif geometry == "line":
        symbol_type, layer_class = "line", "SimpleLine"
        props = (
            f'<Option type="QString" name="line_color" value="{rgba}"/>'
            f'<Option type="QString" name="line_width" value="{width}"/>'
        )
    else:
        symbol_type, layer_class = "fill", "SimpleFill"
        props = (
            f'<Option type="QString" name="color" value="{rgba}"/>'
            f'<Option type="QString" name="outline_color" value="{stroke_rgba}"/>'
            f'<Option type="QString" name="outline_width" value="{width}"/>'
            f'<Option type="QString" name="style" value="solid"/>'
        )

    # A dot at the centroid, sized in millimetres on the page rather than in metres
    # on the ground, so it does not vanish when the feature is smaller than a pixel.
    # The sub-symbol name has to be "@<parent name>@<layer index>" or QGIS drops it.
    centroid = ""
    if centroid_marker and symbol_type == "fill":
        centroid = (
            f'<layer class="CentroidFill" enabled="1" pass="0" locked="0">'
            f'<Option type="Map">'
            f'<Option type="QString" name="point_on_all_parts" value="1"/>'
            f'<Option type="QString" name="point_on_surface" value="0"/>'
            f"</Option>"
            f'<symbol type="marker" name="@{name}@1" alpha="1" frame_rate="10" '
            f'clip_to_extent="1">'
            f'<layer class="SimpleMarker" enabled="1" pass="0" locked="0">'
            f'<Option type="Map">'
            f'<Option type="QString" name="color" value="{rgba}"/>'
            f'<Option type="QString" name="name" value="circle"/>'
            f'<Option type="QString" name="outline_style" value="no"/>'
            f'<Option type="QString" name="size" value="{centroid_marker}"/>'
            f"</Option></layer></symbol></layer>"
        )

    return (
        f'<symbol type="{symbol_type}" name="{name}" alpha="1" frame_rate="10" '
        f'clip_to_extent="1">'
        f'<layer class="{layer_class}" enabled="1" pass="0" locked="0">'
        f'<Option type="Map">{props}</Option>'
        f"</layer>{centroid}</symbol>"
    )


def graduated_breaks(values: list[float], bins: int, mode: str) -> list[float]:
    """Choose the class edges for a graduated renderer.

    Args:
        values: The field's values, with nulls already removed.
        bins: How many classes to cut them into.
        mode: ``"quantile"`` for equal counts per class, ``"equal"`` for equal
            widths.

    Returns:
        ``bins + 1`` edges, ascending.

    Raises:
        ValueError: If the mode is not one of the two, or there is nothing to cut.
    """
    import numpy as np

    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if array.size == 0:
        msg = "The field has no finite values, so it cannot be graduated."
        raise ValueError(msg)

    if mode == "quantile":
        # Equal counts per class. Right for a skewed or clustered field, which is
        # most money and most terrain: equal widths would put nearly every
        # feature in one or two classes and waste the ramp on empty ground.
        edges = np.quantile(array, np.linspace(0, 1, bins + 1))
    elif mode == "equal":
        edges = np.linspace(array.min(), array.max(), bins + 1)
    else:
        msg = f"bin_mode must be 'quantile' or 'equal', got {mode!r}."
        raise ValueError(msg)

    # Duplicate edges come out of a field with a heavy repeated value, and an
    # empty class renders nothing while still taking a legend row.
    return sorted({float(e) for e in edges})


def _graduated_renderer(layer: dict[str, Any], geometry: str, **symbol: Any) -> str:
    """Build a graduated renderer, colouring features by a continuous field.

    Args:
        layer: The layer spec, carrying ``field``, ``cmap`` and ``breaks``.
        geometry: The geometry type the symbols are built for.
        **symbol: The remaining symbol arguments, passed through.

    Returns:
        The ``<renderer-v2>`` block.

    Raises:
        ValueError: If the breaks could not be worked out, which happens when the
            file was unreadable and the spec gave no ``min`` and ``max``.
    """
    from matplotlib import colormaps
    from matplotlib.colors import to_hex

    edges = layer.get("breaks")
    if not edges:
        msg = (
            f"Layer {layer['name']!r} asks for a graduated render of "
            f"{layer.get('field')!r} but the file could not be read to find its "
            f"range. Give 'min' and 'max' in the spec, or point the project at a "
            f"readable copy."
        )
        raise ValueError(msg)

    cmap = colormaps[layer.get("cmap", "viridis")]
    count = len(edges) - 1
    ranges, symbols = [], []
    for idx in range(count):
        low, high = edges[idx], edges[idx + 1]
        colour = to_hex(cmap(idx / max(count - 1, 1)))
        ranges.append(
            f'<range lower="{low:.6f}" upper="{high:.6f}" symbol="{idx}" '
            f'label={quoteattr(f"{low:,.0f} - {high:,.0f}")} render="true"/>'
        )
        symbols.append(_symbol_xml(str(idx), geometry, color=colour, **symbol))

    return f"""<renderer-v2 type="graduatedSymbol" forceraster="0" symbollevels="0"
                  attr={quoteattr(layer["field"])} graduatedMethod="GraduatedColor">
        <ranges>
          {"\n          ".join(ranges)}
        </ranges>
        <symbols>
          {"\n          ".join(symbols)}
        </symbols>
      </renderer-v2>"""


def _vector_renderer(layer: dict[str, Any]) -> str:
    """Build the renderer for a vector layer: single symbol, categorised or graduated.

    A categorised renderer is what this study's landslide and zonation outputs need:
    one polygon set carrying a class column, which has to arrive in QGIS already
    coloured by that column or the legend says nothing. A graduated one is the same
    argument for a continuous field -- a land value or a slope per feature.

    Args:
        layer: The layer spec.

    Returns:
        The ``<renderer-v2>`` block.

    Raises:
        ValueError: If ``categories`` or ``cmap`` is given with no ``field`` to
            read them from.
    """
    geometry = layer.get("geometry", "polygon")
    width = layer.get("width", 0.3)
    size = layer.get("size", 2)
    outline = layer.get("outline", "#232323")
    marker = layer.get("centroid_marker")
    symbol_args = {
        "outline": outline,
        "width": width,
        "size": size,
        "centroid_marker": marker,
    }

    if layer.get("cmap"):
        if not layer.get("field"):
            msg = (
                f"Layer {layer['name']!r} gives 'cmap' but no 'field' to grade by. "
                f"Name the numeric column the colours run over."
            )
            raise ValueError(msg)
        return _graduated_renderer(layer, geometry, **symbol_args)

    if not layer.get("categories"):
        symbol = _symbol_xml(
            "0",
            geometry,
            color=layer.get("color", "#5707b3"),
            outline=outline,
            width=width,
            size=size,
            centroid_marker=marker,
        )
        return f"""<renderer-v2 type="singleSymbol" forceraster="0" symbollevels="0">
        <symbols>
          {symbol}
        </symbols>
      </renderer-v2>"""

    field = layer.get("field")
    if not field:
        msg = (
            f"Layer {layer['name']!r} gives 'categories' but no 'field' to colour by. "
            f"Name the column the categories are values of."
        )
        raise ValueError(msg)

    categories = _categories(layer)
    rows = "\n          ".join(
        f'<category render="true" value={quoteattr(str(value))} '
        f'symbol="{idx}" label={quoteattr(str(label))}/>'
        for idx, (value, (_, label)) in enumerate(categories.items())
    )
    symbols = "\n          ".join(
        _symbol_xml(
            str(idx),
            geometry,
            color=color,
            outline=outline,
            width=width,
            size=size,
            centroid_marker=marker,
        )
        for idx, (color, _) in enumerate(categories.values())
    )
    return f"""<renderer-v2 type="categorizedSymbol" forceraster="0" symbollevels="0"
                  attr={quoteattr(field)}>
        <categories>
          {rows}
        </categories>
        <symbols>
          {symbols}
        </symbols>
      </renderer-v2>"""


def _extent_block(bounds: tuple[float, float, float, float] | None) -> str:
    """Build the cached ``<extent>`` for a layer, or nothing if it is unknown.

    Args:
        bounds: ``(left, bottom, right, top)``, or None when the file could not
            be read at build time.

    Returns:
        The extent block, or an empty string. QGIS recomputes it on load either
        way, so leaving it out is safe.
    """
    if bounds is None:
        return ""
    left, bottom, right, top = bounds
    return f"""<extent>
        <xmin>{left}</xmin><ymin>{bottom}</ymin><xmax>{right}</xmax><ymax>{top}</ymax>
      </extent>"""


def _maplayer(layer: dict[str, Any], authid: str) -> str:
    """Build one ``<maplayer>``.

    Args:
        layer: The resolved layer spec.
        authid: The project CRS.

    Returns:
        The map layer element.
    """
    kind = layer["kind"]
    is_raster = kind in {"raster", "basemap"}

    if kind == "basemap":
        # A tile service has no band of values to classify, so it takes the
        # pass-through renderer rather than one of the ones above; its own CRS is
        # web mercator and QGIS reprojects it to the project's on the fly.
        body = """<pipe>
        <rasterrenderer type="singlebandcolordata" band="1" opacity="1"
                        alphaBand="-1" nodataColor=""/>
        <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
        <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0"/>
        <rasterresampler maxOversampling="2"/>
      </pipe>
      <blendMode>0</blendMode>"""
        provider = "wms"
        srs_authid = "EPSG:3857"
    elif is_raster:
        body = f"""<noData><noDataList bandNo="1" useSrcNoData="1"/></noData>
      <pipe>
        {_raster_renderer(layer)}
        <brightnesscontrast brightness="0" contrast="0" gamma="1"/>
        <huesaturation saturation="0" grayscaleMode="0" colorizeOn="0"/>
        <rasterresampler maxOversampling="2"/>
      </pipe>
      <blendMode>0</blendMode>"""
        provider = "gdal"
        srs_authid = authid
    else:
        body = f"""{_vector_renderer(layer)}
      <blendMode>0</blendMode>"""
        provider = "ogr"
        srs_authid = authid

    return f"""<maplayer type="{"raster" if is_raster else "vector"}"
             geometry="{"" if is_raster else layer.get("geometry", "Polygon")}"
             hasScaleBasedVisibilityFlag="0" minScale="1e+08" maxScale="0"
             autoRefreshTime="0" refreshOnNotifyEnabled="0">
      <id>{layer["id"]}</id>
      <datasource>{escape(layer["source"])}</datasource>
      <layername>{escape(layer["name"])}</layername>
      {_extent_block(layer.get("bounds"))}
      <srs>
        {_srs_block(srs_authid)}
      </srs>
      <provider>{provider}</provider>
      <map-layer-style-manager current="default">
        <map-layer-style name="default"/>
      </map-layer-style-manager>
      {body}
      <customproperties><Option/></customproperties>
    </maplayer>"""


def build_xml(
    title: str,
    layers: list[dict[str, Any]],
    authid: str,
    extent: tuple[float, float, float, float],
) -> str:
    """Assemble the whole project file.

    Args:
        title: The project title, shown in the QGIS window.
        layers: The resolved layers, in legend order.
        authid: The project CRS.
        extent: The initial canvas view, in the project CRS.

    Returns:
        The .qgs file contents.
    """
    tree = "\n      ".join(
        f'<layer-tree-layer id="{lyr["id"]}" name={quoteattr(lyr["name"])} '
        f"source={quoteattr(lyr['source'])} "
        f'providerKey="{PROVIDERS[lyr["kind"]]}" '
        f'checked="{"Qt::Checked" if lyr.get("checked", True) else "Qt::Unchecked"}" '
        f'expanded="0"><customproperties><Option/></customproperties></layer-tree-layer>'
        for lyr in layers
    )
    order = "\n      ".join(f'<layer id="{lyr["id"]}"/>' for lyr in layers)
    maplayers = "\n    ".join(_maplayer(lyr, authid) for lyr in layers)
    xmin, ymin, xmax, ymax = extent

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<qgis projectname={quoteattr(title)} version="{QGIS_VERSION}">
  <homePath path=""/>
  <title>{escape(title)}</title>
  <transaction mode="Disabled"/>
  <projectFlags set=""/>
  <projectCrs>
    {_srs_block(authid)}
  </projectCrs>
  <layer-tree-group>
    <customproperties><Option/></customproperties>
      {tree}
    <custom-order enabled="0">
      {order}
    </custom-order>
  </layer-tree-group>
  <snapping-settings enabled="0" type="1" tolerance="12" unit="1" mode="2">
    <individual-layer-settings/>
  </snapping-settings>
  <relations/>
  <mapcanvas name="theMapCanvas" annotationsVisible="1">
    <units>meters</units>
    <extent>
      <xmin>{xmin}</xmin><ymin>{ymin}</ymin><xmax>{xmax}</xmax><ymax>{ymax}</ymax>
    </extent>
    <rotation>0</rotation>
    <destinationsrs>
      {_srs_block(authid)}
    </destinationsrs>
    <rendermaptile>0</rendermaptile>
  </mapcanvas>
  <legend updateDrawingOrder="true"/>
  <projectlayers>
    {maplayers}
  </projectlayers>
  <layerorder>
    {order}
  </layerorder>
  <properties>
    <Gui>
      <CanvasColorBluePart type="int">255</CanvasColorBluePart>
      <CanvasColorGreenPart type="int">255</CanvasColorGreenPart>
      <CanvasColorRedPart type="int">255</CanvasColorRedPart>
    </Gui>
    <Measure><Ellipsoid type="QString">EPSG:7019</Ellipsoid></Measure>
    <Paths><Absolute type="bool">true</Absolute></Paths>
    <SpatialRefSys>
      <!-- Without this QGIS ignores <projectCrs> and opens with no CRS at all. -->
      <ProjectionsEnabled type="int">1</ProjectionsEnabled>
    </SpatialRefSys>
  </properties>
</qgis>
"""


# -------------------------------------------------------------------------------------
# Path resolution
# -------------------------------------------------------------------------------------


def _resolve(layer: dict[str, Any], source: str) -> tuple[str, Path | None]:
    """Work out the path to write into the project, and one that can be read now.

    ``local`` points the project at the tdrive_sync cache under the repo;
    ``t_drive`` points it at the shared path on the network, which is what a project
    sent to a colleague needs. Even for a T: project the metadata is read from the
    cached copy when there is one, because it is the same file and this machine reaches
    T: only through the T+T Network Browse MCP.

    Nothing here touches T:. ``tdrive_sync``'s path builders construct paths without
    looking at the drive, which is exactly what writing a path into a document needs;
    the resolvers that *do* stat T: -- ``get_path``, ``get_source_mat``, ``get_cached``
    -- are deliberately not used.

    Args:
        layer: The layer spec.
        source: ``"local"`` or ``"t_drive"``.

    Returns:
        ``(path written into the project, a readable local path or None)``.

    Raises:
        ValueError: If the layer names no store and no path, or an unknown store.
    """
    import tdrive_sync
    from scripts.landloss.paths import TEMP_DIR

    if "basemap" in layer:
        key = layer["basemap"]
        if key not in BASEMAPS:
            msg = (
                f"Unknown basemap {key!r}. Use one of {sorted(BASEMAPS)}, or add "
                f"the tile service to BASEMAPS with its attribution."
            )
            raise ValueError(msg)
        tiles = BASEMAPS[key]
        source = (
            f"crs=EPSG:3857&format&type=xyz&url={tiles['url']}"
            f"&zmax={tiles['zmax']}&zmin={tiles['zmin']}"
        )
        return source, None

    if "path" in layer:
        path = Path(layer["path"])
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return str(path), path if path.exists() else None

    store = layer.get("store")
    if store not in STORES:
        msg = (
            f"Layer {layer.get('name', layer)!r} needs either 'path' or a 'store' from "
            f"{list(STORES)}, but has store={store!r}."
        )
        raise ValueError(msg)

    if store == "temp":
        # temp/ is local by definition -- a gitignored working area under the repo, not
        # something T: has a copy of -- so 'source' does not apply to it.
        path = TEMP_DIR.joinpath(*layer.get("sub_dirs", []), layer["fname"])
        return str(path), path if path.exists() else None

    if store == "source_material":
        relative = layer.get("relative_path") or "/".join(
            [*layer.get("sub_dirs", []), layer["fname"]]
        )
        local = tdrive_sync.get_source_mat_local_path(relative)
        base = tdrive_sync.get_source_mat_base_path(relative)
    else:
        kwargs = {"fname": layer["fname"], "sub_dirs": layer.get("sub_dirs", [])}
        local = tdrive_sync.get_local_path(**kwargs)
        base = tdrive_sync.get_base_path(**kwargs)

    target = base if source == "t_drive" else local
    return str(target), local if local.exists() else None


def _field_values(path: Path, field: str) -> list[float]:
    """Read one numeric column off a vector file, for choosing graduated breaks.

    Read separately from the rest of the metadata rather than threaded through it,
    because only a graduated layer needs it and only a vector can supply it.

    Args:
        path: A readable local path.
        field: The column to read.

    Returns:
        The column's non-null values.

    Raises:
        ValueError: If the file has no such column. Naming the columns it does
            have saves a round trip, since a wrong field name otherwise renders
            as a layer in one flat colour.
    """
    import geopandas as gpd

    read = (
        gpd.read_parquet if path.suffix.lower() in PARQUET_SUFFIXES else gpd.read_file
    )
    gdf = read(path)
    if field not in gdf.columns:
        columns = sorted(c for c in gdf.columns if c != gdf.geometry.name)
        msg = f"{path.name} has no column {field!r} to grade by. It has: {columns}."
        raise ValueError(msg)
    return gdf[field].dropna().to_numpy().tolist()


def _read_meta(path: Path, kind: str) -> dict[str, Any]:
    """Read a layer's extent, CRS and geometry type off the file.

    Args:
        path: A readable local path.
        kind: ``"raster"`` or ``"vector"``.

    Returns:
        ``bounds`` and ``authid``, plus ``geometry`` for a vector.
    """
    if kind == "raster":
        import rasterio

        with rasterio.open(path) as src:
            return {"bounds": tuple(src.bounds), "authid": str(src.crs)}

    import geopandas as gpd

    read = (
        gpd.read_parquet if path.suffix.lower() in PARQUET_SUFFIXES else gpd.read_file
    )
    gdf = read(path)

    # An empty layer is a real answer, not a broken file: a pilot box with no
    # culverts in it has nothing to draw and should still appear in the legend,
    # saying so. It has no extent and no geometry type to report, so both are
    # left to the spec and the provider.
    if gdf.empty:
        return {"bounds": None, "authid": str(gdf.crs), "geometry": None}

    # shapely says "LineString"; the symbol builder and the .qgs both want "line".
    # Left untranslated, a line layer is given a fill symbol and draws nothing at
    # all while still reporting valid, which is the hardest kind of wrong to spot.
    geometry = str(gdf.geom_type.iloc[0]).replace("Multi", "").lower()
    return {
        "bounds": tuple(gdf.total_bounds),
        "authid": str(gdf.crs),
        "geometry": GEOMETRY_NAMES.get(geometry, geometry),
    }


def _prepare_layer(
    layer: dict[str, Any], source: str
) -> tuple[dict[str, Any], str, Path | None]:
    """Resolve one layer's path, and fill in everything that is read off the file.

    Args:
        layer: The layer spec, which this mutates and returns.
        source: ``"local"`` or ``"t_drive"``.

    Returns:
        ``(layer, path written into the project, a readable local path or None)``.
    """
    written, readable = _resolve(layer, source)
    layer["source"] = written

    if "basemap" in layer:
        # A tile service, not a file: no suffix to infer a kind from, no extent
        # to read and nothing to report as missing, so it skips the whole
        # metadata step.
        layer["kind"] = "basemap"
        layer.setdefault("name", BASEMAPS[layer["basemap"]]["name"])
        layer["id"] = f"{layer['basemap']}_{uuid4().hex}"
        return layer, written, None

    layer["id"] = f"{Path(written).stem}_{uuid4().hex}"
    layer.setdefault(
        "kind",
        "raster" if Path(written).suffix.lower() in RASTER_SUFFIXES else "vector",
    )
    layer.setdefault("name", Path(written).stem)

    graded = layer.get("field") if layer.get("cmap") else None

    if readable is None:
        # A graduated layer pointing at a file this machine cannot open has no
        # range to work from, so the spec has to supply one. Equal intervals,
        # since there are no values to take quantiles of.
        if graded and layer.get("min") is not None:
            import numpy as np

            layer["breaks"] = np.linspace(
                float(layer["min"]),
                float(layer["max"]),
                int(layer.get("bins", 8)) + 1,
            ).tolist()
        return layer, written, None

    meta = _read_meta(readable, layer["kind"])
    if meta["bounds"] is not None:
        layer["bounds"] = meta["bounds"]
    layer.setdefault("crs", meta["authid"])
    if layer["kind"] == "vector" and meta.get("geometry"):
        layer.setdefault("geometry", meta["geometry"])
    if graded:
        layer["breaks"] = graduated_breaks(
            _field_values(readable, graded),
            int(layer.get("bins", 8)),
            layer.get("bin_mode", "quantile"),
        )
    return layer, written, readable


def run(spec: dict[str, Any]) -> Path:
    """Build the project described by a spec and write it out.

    Args:
        spec: The parsed spec JSON. See ../SKILL.md for the format.

    Returns:
        The path written.

    Raises:
        ValueError: If ``source`` is not ``local`` or ``t_drive``.
    """
    source = spec.get("source", "local")
    if source not in {"local", "t_drive"}:
        msg = f"source must be 'local' or 't_drive', got {source!r}"
        raise ValueError(msg)

    layers: list[dict[str, Any]] = []
    unreadable: list[str] = []

    for raw in spec["layers"]:
        layer, written, readable = _prepare_layer(dict(raw), source)
        if readable is None and layer["kind"] != "basemap":
            unreadable.append(written)
        layers.append(layer)

    authid = spec.get("crs") or next(
        (lyr["crs"] for lyr in layers if lyr.get("crs")), DEFAULT_CRS
    )
    # The view the project opens on. Taken from the spec when it says, because the
    # union of every layer is the wrong answer whenever one context layer is much
    # wider than the study extent: a pilot project holding one region-wide grid
    # opens twenty times too far out, and every pilot layer in it is then a
    # sub-pixel smudge that reads as an empty project rather than a zoomed-out one.
    # Always set `extent` on a project built for one area.
    bounds = [lyr["bounds"] for lyr in layers if lyr.get("bounds")]
    if spec.get("extent"):
        west, south, east, north = (float(v) for v in spec["extent"])
        extent = (west, south, east, north)
    elif bounds:
        extent = (
            min(b[0] for b in bounds),
            min(b[1] for b in bounds),
            max(b[2] for b in bounds),
            max(b[3] for b in bounds),
        )
    else:
        extent = WELLINGTON_EXTENT

    out = Path(spec["out"]).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_xml(spec.get("title", out.stem), layers, authid, extent), encoding="utf-8"
    )

    print(f"Wrote {out} with {len(layers)} layers ({source} paths)")
    if unreadable:
        # Worth saying out loud: the project references files this machine could not
        # open, so nothing about them has been checked -- not the CRS, not the extent,
        # not that they exist at all.
        print(
            "Could not read (extent and CRS not verified):\n  "
            + "\n  ".join(unreadable),
            file=sys.stderr,
        )
    return out


def main() -> None:
    """Build the project described by the spec file named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Path to the JSON layer spec.")
    args = parser.parse_args()
    run(json.loads(args.spec.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
