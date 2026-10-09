The download cache now keeps each dataset in a folder named for it, so a layer
can be found by what it is rather than by a hash. A Koordinates layer caches in
`.koopcache/<layer id>-<slugified title>/` (e.g.
`125308-gns-slide-morphological-data/`), with its clipped extents in an
`extents/` folder inside; ArcGIS and WFS reads go in named folders under
`arcgis/` and `wfs/`. File names are unchanged. An existing cache is moved into
the new layout, without downloading anything again, by
`src/landloss/io/one_offs/gen_koopcache_folders.py`; without that, every layer is
downloaded afresh on first use.
