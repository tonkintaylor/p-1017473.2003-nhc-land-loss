"""Build KML files for Google Earth from the same layer spec the QGIS builder takes.

Run with the repo venv (it imports geopandas, shapely and the QGIS builder beside it):

    SKILL=.agents/skills/making-kml-files
    uv run --frozen python $SKILL/scripts/build_kml.py spec.json

See ../SKILL.md for the spec format. A layer is named exactly as in the
``making-qgis-projects`` skill (``store`` + ``fname``, or ``path``) and styled with the
same keys (``color``, ``outline``, ``field`` + ``categories``, ``field`` + ``cmap``), so
one spec can produce a QGIS project and the Google Earth files of the same layers.

The path resolution, the house category colours and the graduated breaks all come from
``build_qgis_project`` rather than being copied here, so a layer cannot be one colour in
QGIS and another in Google Earth.
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

# The QGIS builder sits in a sibling skill. It is imported, not copied: the XML writer
# in there is the thing the skill warns against duplicating, and the same goes for the
# colour handling.
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "making-qgis-projects" / "scripts")
)
import build_qgis_project as qgis

# Helpers the QGIS builder keeps private. Bound once here, on purpose, so the colours
# and paths cannot drift from the QGIS project's; a copy would be the duplication the
# skill exists to avoid.
split_color = qgis._split_color  # noqa: SLF001
resolve_categories = qgis._categories  # noqa: SLF001
resolve_layer_path = qgis._resolve  # noqa: SLF001

KML_CRS = "EPSG:4326"

# Where the files go unless the spec says otherwise. Resolved by default_out_dir() and
# nowhere else.
DEFAULT_DRIVE = "U:/"
DEFAULT_SUBDIR = "GoogleEarthFiles"

# A colour ramp only reads on the ground if the fill lets the imagery through.
FILL_ALPHA = 0.6

# KML colours are aabbggrr, and widths are pixels rather than millimetres.
LINE_WIDTH_PX = 2.0
OUTLINE_WIDTH_PX = 1.0
POINT_SCALE = 0.6

# Above this many features Google Earth becomes slow to pan. A warning, not a limit:
# dropping features silently would put a layer on the globe that does not match the
# model output it is named after.
SLOW_FEATURE_COUNT = 50_000

# Columns that name a feature, in the order they are tried.
NAME_FIELD_SUFFIXES = ("_id", "id")


def default_out_dir() -> Path:
    """Resolve the folder Google Earth files are written to by default.

    The folder is the user's own on the U: drive, named for their Windows login in
    capitals, so the same skill works for every colleague rather than carrying one
    person's name. Every caller asks this function; none repeats the lookup.

    Returns:
        ``U:/<LOGIN>/GoogleEarthFiles``.
    """
    login = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return Path(DEFAULT_DRIVE) / login.upper() / DEFAULT_SUBDIR


def kml_colour(value: str, opacity: float | None = None) -> str:
    """Convert ``#rrggbb`` or ``#rrggbbaa`` to KML's ``aabbggrr``.

    Args:
        value: The colour as the QGIS builder takes it, or ``"transparent"``.
        opacity: Overrides the colour's own alpha, from 0 to 1. Used to let imagery
            show through a polygon fill.

    Returns:
        Eight hex digits, alpha first and red last.
    """
    hexcode, alpha = split_color(value)
    if opacity is not None:
        alpha = round(255 * opacity)
    red, green, blue = hexcode[1:3], hexcode[3:5], hexcode[5:7]
    return f"{alpha:02x}{blue}{green}{red}"


# -------------------------------------------------------------------------------------
# Styles
# -------------------------------------------------------------------------------------


def _style_xml(style_id: str, geometry: str, colour: str, layer: dict[str, Any]) -> str:
    """Build one ``<Style>`` for a geometry type.

    Args:
        style_id: The id placemarks refer to.
        geometry: ``polygon``, ``line`` or ``point``.
        colour: The feature colour, ``#rrggbb``.
        layer: The layer spec, read for ``outline`` and ``kml_width``.

    Returns:
        The style element.
    """
    if geometry == "point":
        return (
            f'<Style id="{style_id}"><IconStyle><color>{kml_colour(colour)}</color>'
            f"<scale>{layer.get('kml_scale', POINT_SCALE)}</scale>"
            f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/shaded_dot.png"
            f"</href></Icon></IconStyle><LabelStyle><scale>0</scale></LabelStyle>"
            f"</Style>"
        )

    if geometry == "line":
        width = layer.get("kml_width", LINE_WIDTH_PX)
        return (
            f'<Style id="{style_id}"><LineStyle><color>{kml_colour(colour)}</color>'
            f"<width>{width}</width></LineStyle></Style>"
        )

    # "match" outlines a feature in its own colour, as it does in the QGIS builder.
    # It is the polygon's own boundary, so a feature a pixel or two across stays
    # visible without claiming ground it does not cover.
    outline = layer.get("outline", "#232323")
    outline_colour = colour if outline == "match" else outline
    width = layer.get("kml_width", OUTLINE_WIDTH_PX)
    return (
        f'<Style id="{style_id}"><LineStyle><color>{kml_colour(outline_colour)}'
        f"</color><width>{width}</width></LineStyle>"
        f"<PolyStyle><color>{kml_colour(colour, FILL_ALPHA)}</color>"
        f"<fill>{1 if layer.get('fill', True) else 0}</fill><outline>1</outline>"
        f"</PolyStyle></Style>"
    )


def _class_styles(
    layer: dict[str, Any], geometry: str, gdf: Any
) -> tuple[list[str], Any, list[tuple[str, str]]]:
    """Work out the styles and which one each feature takes.

    Args:
        layer: The resolved layer spec.
        geometry: ``polygon``, ``line`` or ``point``.
        gdf: The layer's GeoDataFrame, in the KML CRS.

    Returns:
        ``(style elements, a per-feature list of style ids, legend rows)``, where a
        legend row is ``(colour, label)``.
    """
    import numpy as np
    import pandas as pd

    field = layer.get("field")
    colour_default = layer.get("color", "#5707b3")

    if layer.get("cmap"):
        if not field:
            msg = f"Layer {layer['name']!r} gives 'cmap' but no 'field' to grade by."
            raise ValueError(msg)
        from matplotlib import colormaps
        from matplotlib.colors import to_hex

        values = gdf[field].to_numpy(dtype=float)
        edges = qgis.graduated_breaks(
            values[np.isfinite(values)].tolist(),
            int(layer.get("bins", 8)),
            layer.get("bin_mode", "quantile"),
        )
        count = len(edges) - 1
        cmap = colormaps[layer["cmap"]]
        colours = [to_hex(cmap(i / max(count - 1, 1))) for i in range(count)]
        # searchsorted on the inner edges puts a value on an edge into the upper
        # class, and the maximum into the last one.
        bins = np.clip(np.searchsorted(edges[1:-1], values, side="right"), 0, count - 1)
        ids = [
            f"c{b}" if np.isfinite(v) else "c_none"
            for b, v in zip(bins, values, strict=False)
        ]
        styles = [
            _style_xml(f"c{i}", geometry, c, layer) for i, c in enumerate(colours)
        ]
        if "c_none" in ids:
            styles.append(_style_xml("c_none", geometry, "#999999", layer))
        legend = [
            (colours[i], f"{edges[i]:,.0f} - {edges[i + 1]:,.0f}") for i in range(count)
        ]
        return styles, ids, legend

    if layer.get("categories"):
        if not field:
            msg = f"Layer {layer['name']!r} gives 'categories' but no 'field'."
            raise ValueError(msg)
        categories = resolve_categories(layer)
        keys = list(categories)
        styles, legend = [], []
        for idx, key in enumerate(keys):
            colour, label = categories[key]
            styles.append(_style_xml(f"k{idx}", geometry, colour, layer))
            legend.append((colour, label))
        styles.append(_style_xml("k_other", geometry, "#999999", layer))
        lookup = {key: f"k{idx}" for idx, key in enumerate(keys)}
        # A missing value is its own category, keyed "null", rather than the string
        # "nan" or "None" depending on how the file stored it.
        ids = [
            lookup.get("null" if pd.isna(v) else str(v), "k_other") for v in gdf[field]
        ]
        return styles, ids, legend

    return (
        [_style_xml("s0", geometry, colour_default, layer)],
        ["s0"] * len(gdf),
        [(colour_default, layer["name"])],
    )


# -------------------------------------------------------------------------------------
# Geometry and attributes
# -------------------------------------------------------------------------------------


def _coords(coords: Any) -> str:
    """Format a coordinate sequence as KML ``lon,lat`` text, to about a centimetre."""
    return " ".join(f"{x:.7f},{y:.7f}" for x, y, *_ in coords)


def _polygon_xml(polygon: Any) -> str:
    """Build a ``<Polygon>``, wound the way KML expects (outer ring anticlockwise)."""
    from shapely.geometry.polygon import orient

    polygon = orient(polygon)
    inner = "".join(
        f"<innerBoundaryIs><LinearRing><coordinates>{_coords(ring.coords)}"
        f"</coordinates></LinearRing></innerBoundaryIs>"
        for ring in polygon.interiors
    )
    return (
        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        f"{_coords(polygon.exterior.coords)}</coordinates></LinearRing>"
        f"</outerBoundaryIs>{inner}</Polygon>"
    )


def _geometry_xml(geom: Any) -> str:
    """Build the KML geometry for a shapely geometry, multi-part ones included."""
    kind = geom.geom_type
    if kind == "Point":
        return f"<Point><coordinates>{_coords(geom.coords)}</coordinates></Point>"
    if kind == "LineString":
        return (
            f"<LineString><tessellate>1</tessellate><coordinates>"
            f"{_coords(geom.coords)}</coordinates></LineString>"
        )
    if kind == "Polygon":
        return _polygon_xml(geom)
    if kind in {"MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"}:
        parts = "".join(_geometry_xml(part) for part in geom.geoms)
        return f"<MultiGeometry>{parts}</MultiGeometry>"
    msg = f"Cannot write a {kind} to KML."
    raise ValueError(msg)


def _name_field(columns: list[str], requested: str | None) -> str | None:
    """Choose the column a placemark is named from.

    Args:
        columns: The layer's attribute columns.
        requested: ``name_field`` from the spec, if the layer gave one.

    Returns:
        The column, or None to leave placemarks unnamed.

    Raises:
        ValueError: If the spec names a column the layer does not have.
    """
    if requested:
        if requested not in columns:
            msg = f"name_field {requested!r} is not a column. It has: {columns}."
            raise ValueError(msg)
        return requested
    return next((c for c in columns if c.endswith(NAME_FIELD_SUFFIXES)), None)


def _value_text(value: Any) -> str | None:
    """Render an attribute for ExtendedData, or None if it has nothing to say."""
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        # Ten significant figures, so an NZTM easting of 1749840.123 keeps its
        # decimals rather than collapsing to 1.74984e+06.
        return f"{value:.10g}"
    return str(value)


def _placemarks(
    gdf: Any, ids: list[str], columns: list[str], name_field: str | None
) -> str:
    """Build every ``<Placemark>`` of a layer."""
    rows = []
    geometry_name = gdf.geometry.name
    for style_id, record in zip(ids, gdf.to_dict("records"), strict=False):
        name = ""
        if name_field:
            text = _value_text(record[name_field])
            name = f"<name>{escape(text)}</name>" if text else ""
        data = "".join(
            f"<Data name={quoteattr(col)}><value>{escape(text)}</value></Data>"
            for col in columns
            if (text := _value_text(record[col])) is not None
        )
        rows.append(
            f"<Placemark>{name}<styleUrl>#{style_id}</styleUrl>"
            f"<ExtendedData>{data}</ExtendedData>"
            f"{_geometry_xml(record[geometry_name])}</Placemark>"
        )
    return "\n".join(rows)


def _legend_description(
    legend: list[tuple[str, str]], field: str | None, attribution: str | None
) -> str:
    """Build the layer's description, which Google Earth shows as its legend."""
    swatches = "".join(
        f'<tr><td style="background:{colour};width:1.5em">&nbsp;</td>'
        f"<td>{escape(label)}</td></tr>"
        for colour, label in legend
    )
    heading = f"<b>{escape(field)}</b>" if field else ""
    credit = f"<p><i>{escape(attribution)}</i></p>" if attribution else ""
    return f"<![CDATA[{heading}<table>{swatches}</table>{credit}]]>"


# -------------------------------------------------------------------------------------
# Layers and files
# -------------------------------------------------------------------------------------


def read_layer(layer: dict[str, Any]) -> Any:
    """Read one layer from the local copy and reproject it to WGS84.

    KML is always WGS84, so this is the one place the source CRS is left behind.

    Args:
        layer: The layer spec, with ``source`` already resolved.

    Returns:
        The GeoDataFrame in ``EPSG:4326``.

    Raises:
        FileNotFoundError: If the file is not on this machine. A KML embeds the data,
            so unlike a QGIS project it cannot point at a path it has not read.
        ValueError: If the layer has no CRS to reproject from.
    """
    import geopandas as gpd

    path = Path(layer["source"])
    if not path.exists():
        msg = (
            f"{path} is not on this machine. A KML holds the data itself, so the "
            f"layer has to be readable now. Run the step that writes it, or sync it "
            f"into the local cache."
        )
        raise FileNotFoundError(msg)

    read = (
        gpd.read_parquet
        if path.suffix.lower() in qgis.PARQUET_SUFFIXES
        else gpd.read_file
    )
    gdf = read(path)
    if gdf.crs is None:
        msg = f"{path.name} has no CRS, so it cannot be placed on the globe."
        raise ValueError(msg)
    return gdf.to_crs(KML_CRS)


def layer_folder_xml(layer: dict[str, Any], gdf: Any) -> str:
    """Build a ``<Folder>`` holding one layer's styles and placemarks.

    Args:
        layer: The resolved layer spec.
        gdf: The layer in ``EPSG:4326``, not empty.

    Returns:
        The folder element.
    """
    geometry = "polygon"
    first = gdf.geom_type.iloc[0].replace("Multi", "").lower()
    if first in {"linestring", "linearring"}:
        geometry = "line"
    elif first == "point":
        geometry = "point"

    styles, ids, legend = _class_styles(layer, geometry, gdf)
    columns = [c for c in gdf.columns if c != gdf.geometry.name]
    if layer.get("fields"):
        columns = [c for c in layer["fields"] if c in columns]
    name_field = _name_field(columns, layer.get("name_field"))

    visibility = "1" if layer.get("checked", True) else "0"
    description = _legend_description(
        legend, layer.get("field"), layer.get("attribution")
    )
    return (
        f"<Folder><name>{escape(layer['name'])}</name>"
        f"<visibility>{visibility}</visibility>"
        f"<description>{description}</description>\n"
        + "\n".join(styles)
        + "\n"
        + _placemarks(gdf, ids, columns, name_field)
        + "</Folder>"
    )


def _look_at(bounds: tuple[float, float, float, float]) -> str:
    """Build the ``<LookAt>`` that opens Google Earth on the study area.

    Args:
        bounds: ``(west, south, east, north)`` in degrees.

    Returns:
        The element. Range is a rough height, from the longer side of the box.
    """
    west, south, east, north = bounds
    lat = (south + north) / 2
    lon = (west + east) / 2
    metres_per_degree = 111_320
    width = (east - west) * metres_per_degree * math.cos(math.radians(lat))
    height = (north - south) * metres_per_degree
    return (
        f"<LookAt><longitude>{lon:.6f}</longitude><latitude>{lat:.6f}</latitude>"
        f"<range>{max(width, height) * 1.8:.0f}</range><tilt>0</tilt>"
        f"<heading>0</heading></LookAt>"
    )


def _document(title: str, folders: list[str], bounds: Any) -> str:
    """Wrap folders in a KML document."""
    look = _look_at(tuple(bounds)) if bounds is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(title)}</name>{look}\n"
        + "\n".join(folders)
        + "</Document></kml>"
    )


def _safe_name(name: str) -> str:
    """Make a layer name safe as a filename."""
    # Punctuation is dropped rather than replaced: "state, realisation" reads better
    # as "state realisation" than as "state_ realisation".
    keep = "".join(c for c in name if c.isalnum() or c in " ._-()")
    return " ".join(keep.split())


def run(spec: dict[str, Any]) -> list[Path]:
    """Write the KML files a spec describes.

    Args:
        spec: The parsed spec. Beyond the layer keys the QGIS builder reads, it takes
            ``title``, ``out_dir`` (default :func:`default_out_dir`) and ``combined``
            (a filename stem: put every layer in one file rather than one each).

    Returns:
        The files written.
    """
    import pandas as pd

    out_dir = Path(spec["out_dir"]).expanduser() if spec.get("out_dir") else None
    out_dir = out_dir or default_out_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    title = spec.get("title", "Layers")
    written: list[Path] = []
    combined: list[tuple[dict[str, Any], Any]] = []
    skipped: list[str] = []

    for raw in spec["layers"]:
        if "basemap" in raw:
            # Google Earth has its own imagery under everything.
            continue
        layer = dict(raw)
        # Always the local copy: a KML embeds the data, so there is nothing for a
        # T: path to point at, and T: is never read from here.
        layer["source"], _ = resolve_layer_path(layer, "local")
        layer.setdefault("name", Path(layer["source"]).stem)

        if Path(layer["source"]).suffix.lower() in qgis.RASTER_SUFFIXES:
            skipped.append(f"{layer['name']} (raster: KML carries vectors only)")
            continue

        gdf = read_layer(layer)
        if gdf.empty:
            skipped.append(f"{layer['name']} (no features)")
            continue
        if len(gdf) > SLOW_FEATURE_COUNT:
            print(
                f"Warning: {layer['name']} has {len(gdf):,} features; Google Earth "
                f"will be slow. Filter it into temp/ first if that matters.",
                file=sys.stderr,
            )

        if spec.get("combined"):
            combined.append((layer, gdf))
            continue

        # A file of one layer is opened to look at that layer, so it is always on.
        # ``checked`` only means something where layers share a file.
        layer["checked"] = True
        path = out_dir / f"{_safe_name(layer['name'])}.kml"
        bounds = gdf.total_bounds
        path.write_text(
            _document(layer["name"], [layer_folder_xml(layer, gdf)], bounds),
            encoding="utf-8",
        )
        written.append(path)

    if combined:
        folders = [layer_folder_xml(layer, gdf) for layer, gdf in combined]
        bounds = pd.concat([g.geometry for _, g in combined]).total_bounds
        path = out_dir / f"{_safe_name(spec['combined'])}.kml"
        path.write_text(_document(title, folders, bounds), encoding="utf-8")
        written.append(path)

    for path in written:
        print(f"Wrote {path}")
    if skipped:
        print("Not written:\n  " + "\n  ".join(skipped), file=sys.stderr)
    return written


def main() -> None:
    """Build the files for the spec named on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="Path to the JSON layer spec.")
    args = parser.parse_args()
    run(json.loads(args.spec.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
