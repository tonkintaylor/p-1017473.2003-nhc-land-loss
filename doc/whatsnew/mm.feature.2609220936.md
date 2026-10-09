Ported the National Liquefaction Model's QGIS-project skill across as
`making-qgis-projects`. It builds a `.qgs` from a JSON layer spec, as plain XML, so no
QGIS install is needed to make one — `.agents/skills/making-qgis-projects/scripts/build_qgis_project.py`
writes it and `verify_qgis_project.py` opens it under QGIS's own Python to report what
actually loaded, optionally rendering a PNG per layer to catch the project that reports
every layer valid and draws nothing.

Two things differ from the NLM original, both because this project stores its data
differently. Paths resolve through `tdrive_sync` across the three stores this project
uses — `versioned` for the shared `DATA_VERSION` store, `source_material` for data
supplied by others, and `temp` for gitignored working layers — with `source` choosing
whether the local cache path or the T: path is written into the project. Only
`tdrive_sync`'s path builders are used, never the resolvers that stat T: to check the
cache, so a project pointing at the network can be built on a machine that cannot reach
it. And vectors can be coloured by a field, which the original could not: this study's
headline outputs are polygons carrying a class column, and a single-symbol renderer
would say nothing about them.

`tdrive_sync` gains `get_source_mat_base_path` and `get_source_mat_local_path`, the two
sides of the source-material cache as pure path construction, which is what naming a
file in a document rather than reading it needs.

`landloss.common.utils.colors` is new, holding the colour maps shared between a figure
and the QGIS layer of the same quantity — the evacuated/inundated land classes, the GWRC
severity zonation, the supplied landslide probability bands and slope in degrees.
`fig_landslide_realisation.py` now takes its colours from there, so the report figure and
a QGIS project of the same realisation carry one legend rather than two that agree until
somebody edits one.

Three faults in the ported builder surfaced the first time it was pointed at a full set
of this project's layers, all of which produced a project that reported every layer valid
while drawing the wrong thing or nothing. A vector outline's alpha was discarded and
forced opaque, so any polygon smaller than a pixel — every landslide source — drew as a
black dot instead of its category colour. A line layer was given a fill symbol, because
shapely names the geometry `LineString` and the symbol builder wanted `line`, so the
retaining walls drew nothing at all. And an empty layer crashed the build outright, which
a pilot box containing no culverts is entitled to be. `references/qgs-xml-notes.md`
records the first two, since neither is visible without rendering the project.

A project built for one study area now takes an explicit `extent`, and a vector layer
takes a `centroid_marker`. Both come from the same failure: a pilot project holding one
region-wide context grid opened at 61 by 50 km rather than the 2.9 by 1.7 km pilot box,
because the canvas was the union of every layer, and at that zoom the landslide sources —
a median 1.4 m across — covered four hundredths of one per cent of the canvas. The layer
was valid, correctly styled and completely invisible. `centroid_marker` draws a dot of a
fixed size in millimetres at each polygon's centroid over the true footprint, so a feature
smaller than a pixel still reads on the map.

A vector layer can take `"outline": "match"`, outlining each feature in its own fill
colour. It is what makes a metre-scale polygon readable on a suburb-wide map without
misstating its size, and it replaces an earlier attempt to draw fixed-size dots at
polygon centroids — a landslide's extent is a model output, so a marker of some other
size is the wrong thing to put on the map. `verify_qgis_project.py` also takes `--size`
and now renders at 1600x1100 by default rather than 500x400: at the smaller size a
metre-scale feature is half a pixel and reads as a blank layer when on screen it is a
visible speck, which is a fault in the check rather than in the project.

A layer can now be a tile basemap rather than a file: `{"basemap": "osm"}` adds the
OpenStreetMap XYZ service, which QGIS reads live and reprojects to the project CRS.
Registered services live in `BASEMAPS` in the builder with their attribution beside them,
because OpenStreetMap is ODbL and anything published over it has to credit OpenStreetMap
contributors. A basemap resolves through no store, has no extent to read and is not
reported as unreadable, and it belongs last in the layer list so it draws under everything
else.

A vector layer can also be graduated over a continuous field: `cmap` plus `field` builds a
graduated renderer, with `bins` classes cut by `bin_mode` of `quantile` or `equal`. The
breaks are read off the file at build time, so the classes fit the data rather than a
guessed range, and a layer whose file cannot be opened falls back to equal intervals over
a `min` and `max` given in the spec. The modelled land value per address is now drawn this
way, on turbo over eight quantile classes of dollars per square metre.
