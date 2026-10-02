Rasters are now read through a context manager and loaded into memory, in
`landloss.io.nlm`, `landloss.io.source_material` and the three steps that read a
GeoTIFF directly. A lazily-opened GDAL handle was being finalised during
interpreter shutdown, which surfaced as a bare `Error in sys.excepthook` after
every otherwise clean run — alarming, and it hid any real shutdown error behind
it.
