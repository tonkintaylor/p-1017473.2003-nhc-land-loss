"""Move an existing download cache into one folder per dataset.

The readers now cache each Koordinates layer in a folder of its own,
``<layer id>-<common name>/``, with that layer's clipped extents in an
``extents/`` folder inside it (see :mod:`landloss.io.readers`). A cache filled
before that has every download loose in the root and every extent in one shared
``extents/`` folder, and the readers would no longer find them there: they would
download each layer again.

This moves them instead, without contacting Koordinates. A layer's common name
is read from the table name inside its GeoPackage, which Koordinates sets from
the layer title; a raster carries no such name, so it is taken from the
``*_LAYER_ID`` constant holding its ID. File names are left as they are.

ArcGIS and WFS reads cannot be moved: their file names are a hash of the
service, extent and CRS, so which layer a file came from cannot be recovered.
They are listed rather than touched, and are fetched again on first use (both
services are public, with no key). Delete the listed files once that is done.

Safe to run more than once; a second run finds nothing to move.

    uv run --frozen python src/landloss/io/one_offs/gen_koopcache_folders.py
"""

import re
from pathlib import Path

import geopandas as gpd

from landloss.domain import constants
from landloss.io import koopcache_dir
from landloss.io.readers import dataset_cache_dir

# A ttpy download, ``<layer id>_<version id>_<md5 of details>.<suffix>``, and a
# clipped extent of one, which appends a 16-character digest to that stem.
DOWNLOAD_PATTERN = re.compile(r"^(\d+)_\d+_[0-9a-f]{32}\.(gpkg|tif)$")
EXTENT_PATTERN = re.compile(r"^(\d+)_\d+_[0-9a-f]{32}_[0-9a-f]{16}\.gpkg$")


def layer_name(layer: int, path: Path) -> str:
    """Return a common name for a layer, from its file or the constants.

    Args:
        layer: The Koordinates ID of the layer.
        path: A GeoPackage or GeoTIFF of the layer.

    Returns:
        The table name inside a GeoPackage download, else the name of the
        constant holding ``layer`` without its ``_LAYER_ID`` suffix, else
        ``layer``.
    """
    if path.suffix == ".gpkg" and DOWNLOAD_PATTERN.match(path.name):
        return str(gpd.list_layers(path)["name"].iloc[0])

    for constant, value in vars(constants).items():
        if constant.endswith("_LAYER_ID") and value == layer:
            return constant.removesuffix("_LAYER_ID")

    return "layer"


def move(path: Path, folder: Path) -> None:
    """Move one file into a folder, printing what moved where."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / path.name
    path.rename(target)
    print(f"  {path.name}  ->  {target.parent.relative_to(koopcache_dir())}")


def main() -> None:
    """Move every download and extent in the cache into its layer's folder."""
    root = koopcache_dir()
    print(f"Cache directory: {root}")

    downloads = sorted(p for p in root.iterdir() if DOWNLOAD_PATTERN.match(p.name))
    print(f"\n{len(downloads)} downloads to move:")
    for path in downloads:
        layer = int(DOWNLOAD_PATTERN.match(path.name).group(1))
        name = layer_name(layer, path)
        move(path, dataset_cache_dir(str(layer), lambda name=name: name))

    extents_dir = root / "extents"
    extents = (
        sorted(p for p in extents_dir.iterdir() if EXTENT_PATTERN.match(p.name))
        if extents_dir.is_dir()
        else []
    )
    print(f"\n{len(extents)} extents to move:")
    for path in extents:
        layer = int(EXTENT_PATTERN.match(path.name).group(1))
        name = layer_name(layer, path)
        layer_dir = dataset_cache_dir(str(layer), lambda name=name: name)
        move(path, layer_dir / "extents")

    unplaced = sorted(
        p
        for kind in ("arcgis", "wfs")
        if (root / kind).is_dir()
        for p in (root / kind).iterdir()
        if p.is_file()
    )
    if unplaced:
        print(
            f"\n{len(unplaced)} ArcGIS and WFS reads cannot be placed. They will be"
            " fetched again into named folders on first use; delete these after:"
        )
        for path in unplaced:
            print(f"  {path.relative_to(root)}")


if __name__ == "__main__":
    main()
