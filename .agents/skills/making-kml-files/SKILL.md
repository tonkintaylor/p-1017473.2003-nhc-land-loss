---
name: making-kml-files
description: >-
  Turn this study's vector layers into styled KML files for Google Earth and save them
  to the user's GoogleEarthFiles folder on the U: drive. Use whenever the user wants to
  look at model outputs in Google Earth, asks for a .kml, 'Google Earth files' or 'KML
  for the pilot study', or wants something a colleague without QGIS can open by
  double-clicking. Also use when extending or debugging the builder. Takes the same
  layer spec as the making-qgis-projects skill, so one spec can produce both.
compatibility:
  platform: universal
metadata:
  author: mmillen
  version: "1.0"
---

# KML files for Google Earth

A KML here is a **copy** of the layer, not a pointer to it. That is the opposite of a QGIS
project, and it drives everything below: the file has to be built from data this machine
can read, it goes stale the moment a step re-runs, and there is no `local` versus `t_drive`
question to ask.

The builder is `scripts/build_kml.py`. It imports path resolution, the house category
colours and the graduated breaks from the QGIS builder in `making-qgis-projects` rather
than copying them, so a layer is the same colour in both programs. Read that skill's
sections 2 and 3 for how a layer is named and styled — this one only covers what differs.

## 1. Where the files go

Default: `U:\<LOGIN>\GoogleEarthFiles`, where `<LOGIN>` is the Windows login in capitals
(`U:\MAMI\GoogleEarthFiles` for `mami`). `default_out_dir()` in the builder is the only
place that is worked out, so change the default there and nowhere else. Set `out_dir` in
the spec to write elsewhere.

`U:` is the user's own drive, so writing to it is fine. It is not one of the drives the
org rule limits to the T+T Network Browse MCP (`T:`, `P:`, `I:`) and it is not one of the
forbidden ones. Do not read from `T:`, `P:` or `I:` to build a KML: the builder resolves
every layer to its **local** copy and never touches them.

**Look in the folder before you clear or overwrite anything in it.** It is the user's
working folder and may hold KMLs this skill did not write. The builder overwrites a file of
the same name and touches nothing else; do not `rm *.kml` to tidy up.

## 2. Build

Write a spec to the scratchpad (or reuse one) and run:

```bash
uv run --frozen python .agents/skills/making-kml-files/scripts/build_kml.py spec.json
```

The spec is the QGIS one, with these differences:

- `out_dir` — folder to write to. Optional; see section 1.
- `combined` — a filename stem. Put every layer in **one** KML as separate folders, rather
  than one file per layer. Use it when the user wants one thing to send.
- `source` and `extent` are ignored. `basemap` layers are skipped: Google Earth has its own
  imagery.
- Per layer, `kml_width` (pixels, lines and outlines) and `kml_scale` (points) replace the
  millimetre `width` and `size`, which mean nothing on a globe. `name_field` picks the
  column a placemark is named from (default: the first column ending `_id`) and `fields`
  limits which columns go into each placemark's ExtendedData (default: all of them).
- `checked: false` leaves the layer switched off when it opens, but **only in a `combined`
  file**. A file of one layer is always on: it was made to look at that layer.
- `fill: false` draws polygons as outlines only, which is right for property boundaries
  laid over imagery. Pair it with `"outline": "match"` so the outline carries the
  category colour.
- `attribution` is text added under the layer's legend. **Set it on any layer taken from
  LINZ**, whose data is CC BY 4.0 and must credit LINZ, note the licence and say it was
  changed. A `null` key in `categories` colours features with a missing value.

Layers are **vectors only**. A raster is skipped with a message, because KML would need a
rendered image overlay and that is a picture of the data rather than the data. Say so if
the user asks for one.

Empty layers are skipped and reported, since an empty KML shows nothing and looks broken.

Polygon fills are drawn 60% opaque so imagery shows through. `"outline": "match"` works as
in QGIS.

As with QGIS, **draw the true geometry**. Do not swap a polygon whose size is a model
output for a pin. Google Earth draws a 3 m landslide circle at 3 m, which is small from
altitude and correct when zoomed in; each file opens on a `LookAt` over its layer's extent.

## 3. Verify before reporting back

There is no way to open Google Earth from here, so check the file instead. Do all of:

1. Parse each KML as XML and confirm the placemark count equals the source row count.
2. Confirm every `styleUrl` resolves to a `Style` in the file, and that no feature fell
   into the grey `*_other` fallback (a category value the colour map does not know).
3. Read each file back with `pyogrio.list_layers` / `read_info` — GDAL's KML driver is a
   second, independent parser.

If Google Earth is available to the user, ask them to open one and confirm, and say plainly
that this is the only check that has not been done.

Layers over about 50,000 features make Google Earth slow to pan. The builder warns and
writes them anyway rather than dropping features; offer a filtered copy in `temp/`.

## 4. The pilot study

`references/pilot-study-layers.json` is the spec for the current pilot study. It names the
layers with a map-worthy field, styled to match the QGIS pilot project. Rebuild them with
the command in section 2 after any step re-runs — the KMLs are copies and will not update.

The two LINZ layers, building outlines and property boundaries, name their clipped
extents by `path` under each layer's `.koopcache/<layer id>-<name>/extents/`. Those file
names carry a hash of the layer version and the pilot box, so they **go stale** when either changes: LINZ rebuilds
the property layer weekly, so the reader's own lookup can miss the cache and start a
multi-gigabyte download, which is why the spec points at the files directly. If a file
is missing, re-run `gen_insured_land.py` (which fetches both over the pilot box) and
update the two paths from `.koopcache/101290-nz-building-outlines/extents/` and
`.koopcache/122657-nz-property-boundaries/extents/`.

Of the other layers, the address spine, the land rate per address and the insured land
extent are also derived from LINZ data and are not yet credited in their KMLs.

The bridge, culvert, crossing and structure-damage pilot layers are left out of the spec
because they hold no features in the pilot box. If a run changes that, add them.

The files it names carry the `-pilot` suffix, so this spec is for `PILOT = True` runs. For
a full-region run, copy the spec and drop the suffix — and expect the 132,000-polygon
landslide layer to trip the slow-layer warning.
