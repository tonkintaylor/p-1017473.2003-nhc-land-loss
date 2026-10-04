---
name: making-qgis-projects
description: >-
  Build a QGIS project (.qgs) that loads this study's layers — the landslide
  realisation polygons, the supplied hazard grids, the address spine, DEM
  derivatives and the Koordinates context layers — with the house colours
  already applied. Use whenever the user wants to look at, inspect, check, QA or
  share model outputs in QGIS, or asks for a .qgs/.qgz, a 'QGIS project' or a
  'map project', or says things like 'load these in QGIS', 'set me up a project
  with the landslide output', 'I want to eyeball the realisation', or 'make
  something I can send to the team to open'. Also use when extending or
  debugging the builder. Always ask whether the project should point at the
  local cache or at T: unless the user has already said.
compatibility:
  platform: universal
metadata:
  author: mmillen
  version: "1.0"
---

# QGIS projects for landloss layers

A QGIS project here is a thin thing: a `.qgs` file (plain XML) holding absolute paths to
rasters and vectors plus the styling to render them. The data is never copied. That makes
the one consequential decision *which* paths go in the file, which is why this skill asks
about it up front.

Ported from the National Liquefaction Model's `nlm-qgis-project` skill. Two things differ
because this project stores its data differently: paths resolve through `tdrive_sync`
across three stores rather than the NLM's release tree, and vectors can be coloured by a
field, because this study's headline outputs are polygons with a class column rather than
rasters.

## 1. Ask where the layers should point

Unless the user has already said, ask before building — the answer changes who can open
the project, and a project full of paths the recipient cannot reach is worse than useless
because it looks fine until they try.

Use `AskUserQuestion` with these two options:

- **Local cache** (`source: "local"`) — paths under `.tdrivecache/` in the repo. Fast,
  works offline, and reflects exactly what this machine's own runs produced. Only opens
  on this machine. The right default for the user's own QA and for anything
  mid-development.
- **T: drive** (`source: "t_drive"`) — paths under the shared store, which is
  `BASE_DIR/<DATA_VERSION>` or `SOURCE_MATERIAL_DIR` from `tdrive_sync_config.py` at the
  repo root. Anyone on the T+T network can open it, so this is what to pick for sharing,
  for a record of a release, or when the local cache does not hold everything.

Offer local first when the user is clearly inspecting their own work, T: first when they
mention sharing, a colleague or a release.

A note on reading versus referencing: writing a T: path into a project file is just text
and needs no network access. Do **not** read from `T:\`, `P:\` or `I:\` to gather
metadata — on this setup those are reached only through the T+T Network Browse MCP, and
the org-level rule is absolute. The builder is written to respect this: it resolves paths
with `tdrive_sync.get_base_path`, `get_local_path`, `get_source_mat_base_path` and
`get_source_mat_local_path`, all of which only *construct* paths. It deliberately does not
use `get_path`, `get_source_mat` or `get_cached`, which stat T: to check the cache is
fresh. Metadata comes from the local cache copy when there is one — it is the same file —
and otherwise the extent is left out, which QGIS recomputes on open. If nothing is
readable, say so rather than implying the project has been checked.

## 2. Work out which layers to include

Take the user's wording to name the layers where you can, but go and look rather than
guess. A layer names a **store** plus a file, or an explicit `path`:

| `store` | Resolves to | Holds |
|---|---|---|
| `versioned` | `BASE_DIR/<DATA_VERSION>/<sub_dirs>/<fname>`, cached under `.tdrivecache/` | this project's own shared outputs, written by `tdrive_sync.local_save` |
| `source_material` | `SOURCE_MATERIAL_DIR/<relative_path>`, cached the same way | data supplied by others: the ESNZ landslide grid, NHC's claims extracts |
| `temp` | `temp/<sub_dirs>/<fname>` in the repo | gitignored working layers, e.g. the landslide realisation |
| *(none — give `path`)* | as written | anything else, including `.koopcache/dem/*.tif` and Koordinates extents |

A **basemap** is not a store at all. `{"basemap": "osm", "checked": true}` adds the
OpenStreetMap XYZ tile service, read live over the network and reprojected to the project
CRS by QGIS. Put it **last in the `layers` list** so it sits at the bottom of the legend
and draws under everything, and tick it — a basemap you have to switch on is not doing its
job. Two consequences worth saying out loud when you build one: the project then needs an
internet connection to draw, which an offline or field project does not want; and
OpenStreetMap is ODbL, so anything published over it credits OpenStreetMap contributors.
Other services go in `BASEMAPS` in the builder, with their attribution beside them.

`temp` has no T: side, so `source` does not apply to it — a `temp` layer always gets the
local path, and a project mixing `temp` layers with `t_drive` ones cannot be opened by
anybody else. Say so if you build one.

When the user names a script rather than files ("the landslide output"), read the script
and take the filename from what it writes — `realisation_path()` in
`s1_simulate_landslides.py`, or the `local_save(...)` call for a versioned layer. That is
authoritative, whereas a cache directory can also hold leftovers from an earlier version
of the pipeline. If you find extra files that no current script writes, leave them out and
mention them; adding them silently puts a layer in the project nobody can trace back to
code.

List the directory to confirm each file is actually there before building.

## 3. Choose styling

House colour maps live in `src/landloss/common/utils/colors.py` and the builder reads them
from there, so a QGIS layer and the equivalent report figure look the same. Someone
comparing the two should not have to re-learn the legend.

**Rasters** take `style`:

| `style` | Use for |
|---|---|
| `eil_probability` | the supplied landslide probability grid (banded, yellow → dark red) |
| `slope` | slope in degrees, on this study's 5/10/20/30/45° bands |
| `classes` | an integer-coded raster; give `classes` as `{"1": ["#3b0f70", "Label"], ...}` |
| `cmap` | anything with no house colour map: give `cmap` (matplotlib name), `min`, `max`, `steps` |
| `gray` | a quick look at an unstyled raster; give `min` and `max`, and optionally `opacity` (0–1) so a hillshade can sit over imagery |

**Vectors** take either a single symbol — `color`, `outline`, `width`, `size` and
`geometry` (`polygon`/`line`/`point`, auto-detected when the file is readable) — or a
categorised renderer, which is what the outputs with a class column need:

```json
{"store": "temp", "sub_dirs": ["hazard", "landslide"],
 "fname": "landslide-realisation.geoparquet",
 "field": "land_class", "categories": "land_class"}
```

For a **continuous** field — a value, a rate, a slope per feature — give `cmap` and
`field` instead of `categories`, which builds a graduated renderer:

```json
{"field": "land_rate_nzd_per_m2", "cmap": "turbo", "bins": 8, "bin_mode": "quantile"}
```

`bin_mode` is `quantile` (equal counts, the default) or `equal` (equal widths). Prefer
quantile for anything skewed or clustered, which is most money and most terrain: equal
widths put nearly every feature in one or two classes and waste the ramp on empty range.
The breaks are read off the file at build time, so a graduated layer pointing at a file
this machine cannot open needs `min` and `max` in the spec instead, and then gets equal
intervals.

`categories` is either a name from `colors.py` (`land_class`, `gwrc_severity`) or an
explicit `{value: [colour, label]}` map, and `field` is the column it reads. Both are
required together — categories without a field colours nothing and says nothing, which is
the failure this exists to prevent.

If a quantity has no house colour map, `cmap` is fine for a one-off; if it is going to
recur, add the map to `colors.py` and register it in the builder's `_ramp_dict` or
`_categories`.

**Leave the heavy layers unticked.** Tick the one layer the user actually asked about and
leave the rest for them to switch on. The landslide realisation is 132,000 polygons at
full extent and is slow to draw.

**Render the true geometry. Do not substitute a fixed-size marker for a polygon whose
size is a model output.** A landslide polygon carries its sampled area; a dot drawn at
its centroid is a different size from the thing it stands for, and someone reading the
map cannot tell which they are looking at. The project lead ruled this out directly. The
builder has a `centroid_marker` option and it should stay unused for any layer whose
extent is a result — it exists for a point-like feature that has no meaningful footprint.

When a real polygon is hard to see, fix the view rather than the geometry: set `extent`
so the project opens on the study area, and give the layer `"outline": "match"` with a
thin `width`, which outlines each feature in its own fill colour. That is the polygon's
own boundary, so it claims no ground the feature does not cover, and it is enough to make
a one-pixel circle read. The landslide sources are a median 2.8 m across, which is about
1.6 px on a 1600 px canvas over the pilot box — small, but present and correctly scaled,
and the big ones are visibly bigger, which is the whole point.

## 4. Build

Write a spec JSON to the scratchpad and run the builder with the repo venv:

```bash
uv run --frozen python .agents/skills/making-qgis-projects/scripts/build_qgis_project.py spec.json
```

```json
{
  "title": "Landslide realisation",
  "out": "C:/Users/mami/Downloads/landslide_realisation.qgs",
  "source": "local",
  "layers": [
    {
      "store": "temp",
      "sub_dirs": ["hazard", "landslide"],
      "fname": "landslide-realisation.geoparquet",
      "name": "Landslide realisation (evacuated / inundated)",
      "field": "land_class",
      "categories": "land_class",
      "outline": "#00000000",
      "checked": true
    },
    {
      "store": "source_material",
      "relative_path": "EILProb_Wellington/EILProb_PGA2g.tif",
      "name": "ESNZ landslide probability (PGA2g)",
      "style": "eil_probability",
      "checked": false
    }
  ]
}
```

Top-level keys: `title`, `out`, `source`, `crs` (overrides the CRS taken from the first
readable layer), `extent`, `layers`.

**Always set `extent` on a project built for one area.** Without it the canvas opens on
the union of every layer, and one region-wide context layer then drags the view twenty
times too far out — a pilot project holding the ESNZ grid opened at 61 x 50 km instead of
2.9 x 1.7 km, which made every pilot layer in it a sub-pixel smudge and read as an empty
project. The pilot box is `[1748323, 5423605, 1751191, 5425337]`. Per-layer: `store` + `fname` (+ `sub_dirs`), or
`relative_path` for source material, or `path` for anything else; then `name`, `checked`,
and the styling keys above.

## 5. Verify before reporting back

Always open the project in QGIS before telling the user it is ready. A `.qgs` that parses
as XML can still load with an invalid CRS, a dropped renderer or broken paths, and none of
that shows up in the file itself. Find QGIS's Python (it is not the repo venv):

```bash
ls -d "/c/Program Files/QGIS"*/bin/python-qgis.bat
```

```bash
"C:/Program Files/QGIS 3.42.2/bin/python-qgis.bat" \
  .agents/skills/making-qgis-projects/scripts/verify_qgis_project.py <project.qgs>
```

It prints the project CRS and, per layer, validity, CRS, tick state and the renderer with
its ramp or class entries. Add `--render <dir> --extent <xmin> <ymin> <xmax> <ymax>` to
write a PNG per layer and look at them. This catches the case where everything reports
valid but the map draws blank.

**Render at the extent the project actually opens at**, not at a convenient one. The two
faults this has caught so far — a line layer given a fill symbol, and features too small
to be worth a pixel — were both invisible to every other check, and the second only shows
at the opening view. Measuring the share of non-white pixels per render is a quick way to
find a blank layer among twenty:

```python
a = np.asarray(Image.open(png).convert("RGB"))
(a < 250).any(axis=2).mean()
```

Anything under about 0.1% is effectively blank on screen. Decide whether that is right
(an empty layer) or wrong (a styling fault, or features needing a `centroid_marker`)
before handing the project over — do not hand over a layer you have measured as blank and
explain it away in the covering note.

If QGIS is not installed on the machine, say plainly that the project is unverified beyond
its XML rather than implying it has been opened.

A T:-drive project cannot be verified from here beyond the XML either, since loading it
would read the drive. Build it, say so, and offer to build the local equivalent to confirm
the styling if that would help.

## 6. Performance

There are no overviews on the model rasters, so panning at regional zoom is slow. If the
user will spend real time in the project, offer to build external `.ovr` pyramids
(`rasterio` `build_overviews([2, 4, 8, 16, 32, 64])`, `average` for float bands and
`nearest` for class codes). It writes beside the raster and takes a while, so offer rather
than assume — and never against T:.

For a large vector, a GeoParquet with 132,000 polygons redraws on every pan. Offer to
write a filtered or dissolved copy into `temp/` for interactive work rather than styling
around the problem.

## Committing a generator

For a one-off look, the spec JSON in the scratchpad is enough; only the `.qgs` is the
deliverable. When the project is one the team will rebuild every time a step re-runs,
write a small `gen_qgis_project.py` into the step folder that composes the same spec dict
and calls `run()` from the builder — with its settings in that step's `config.py`, like
every other script under `src/scripts/` (see the `adding-steps-scripts` skill, section
2a). Do not copy the XML writer into the repo; the NLM has a committed generator that
predates its builder and duplicates it, and that duplication is the thing worth not
repeating.

## Google Earth

For the same layers as KML files for Google Earth, use the `making-kml-files` skill. It
takes this spec, so a project built here can be turned into KMLs without restating the
layers.

## When the XML needs hand-editing

`references/qgs-xml-notes.md` records the parts of the `.qgs` format that fail silently —
read it before hand-writing or patching project XML rather than rediscovering them.
