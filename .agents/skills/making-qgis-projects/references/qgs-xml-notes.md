# .qgs XML notes

Things about the QGIS project format that fail quietly — the file parses, the project
opens, and the mistake only shows up as a wrong-looking map. All of these were confirmed
against QGIS 3.42 by loading the project headlessly. Ported from the National
Liquefaction Model, where the same builder is used.

## The project CRS needs ProjectionsEnabled

`<projectCrs>` on its own is ignored. QGIS only applies it when the property is set:

```xml
<properties>
  <SpatialRefSys>
    <ProjectionsEnabled type="int">1</ProjectionsEnabled>
  </SpatialRefSys>
</properties>
```

Without it the project opens with an invalid CRS while every layer still reports its own
CRS correctly, so the layer list looks perfectly healthy. `QgsProject.crs().authid()`
coming back as `''` is the symptom.

## QgsCoordinateReferenceSystem.readXml takes the parent node

When debugging a CRS block, pass the element *containing* `<spatialrefsys>` (e.g. the
`<projectCrs>` node), not the `<spatialrefsys>` element itself — `readXml` looks for a
`spatialrefsys` child and returns `False` if handed the child directly. This looks exactly
like a malformed CRS block and sends you chasing the wrong problem.

## DISCRETE ramps are keyed by the band's upper edge

In `<colorrampshader colorRampType="DISCRETE">`, an `<item value="V">` colours every value
up to and including `V`. So a band `(5, 10) -> #3AB04A` becomes `<item value="10" .../>`,
not `value="5"`. Getting this wrong shifts the whole legend by one band, which is easy to
miss on a map you have not seen before.

The last item should be `value="inf"` when the top band is open-ended;
`landloss.common.utils.colors` marks an open-ended band by setting its upper bound equal
to its lower bound (e.g. `(0.4, 0.4)` at the top of `EIL_PROBABILITY_COLOURS`), at either
end of the dict.

## Colours and alpha are separate attributes

`color` takes `#rrggbb` only. Eight-digit hex (`#rrggbbaa`) must be split, with the alpha
byte going to the `alpha` attribute as 0–255. A literal `"transparent"` entry becomes any
colour with `alpha="0"`. `landloss.common.utils.colors` may use either form, so the
builder always splits rather than assuming six digits.

Vector symbol layers are different again: their `Option` values want comma-separated
`r,g,b,a`, not hex.

## Categorised vectors need one symbol per category, matched by name

A `<renderer-v2 type="categorizedSymbol" attr="land_class">` carries a `<categories>`
list and a `<symbols>` list, and they are joined by the `symbol` attribute on each
category matching the `name` attribute on each symbol. Those are indices as strings
("0", "1", ...), not the category values. Get them out of step and the layer draws in a
single default colour with a legend that looks right, which is the worst combination.

The `attr` is the column name and is matched case-sensitively against the field in the
file. A column that does not exist gives every feature the same symbol rather than an
error.

## A line layer given a fill symbol draws nothing

`SimpleFill` on a line geometry loads, reports `valid=True`, keeps its renderer and
paints no pixels. There is no warning anywhere. The trap is that shapely calls the
geometry `LineString` while the symbol needs `line`, so a geometry type auto-detected
from the file and passed straight through silently picks the wrong symbol class. The
builder normalises through `GEOMETRY_NAMES`; anything hand-writing symbol XML has to do
the same.

This is the case `--render` exists for: every other check passes.

## Nodata

`<noData><noDataList bandNo="1" useSrcNoData="1"/></noData>` makes QGIS honour the nodata
value GDAL reports, which covers both NaN float rasters and the `0` nodata on the class
raster. This needs no knowledge of the file, so it is safe to write for a layer that
cannot be read at build time.

## Extents are a cache, not a requirement

`<extent>` inside `<maplayer>` is a hint; QGIS recomputes from the provider on load. It
can be omitted for a layer whose file is not readable at build time. `<mapcanvas><extent>`
is what sets the initial view, and is worth filling in — an unhelpful default view is the
first thing the user sees.

## Absolute paths

Set `<properties><Paths><Absolute type="bool">true</Absolute></Paths></properties>` when
the project lives somewhere other than the data (a project in Downloads pointing at the
repo cache, for instance). Relative paths would be resolved against the project file's
directory.

## Layer ids must match

The `id` on each `<layer-tree-layer>`, the `<id>` inside its `<maplayer>`, and the entries
in `<layerorder>` and `<custom-order>` all have to agree, or the layer silently drops out
of the legend.
