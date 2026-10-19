"""Snapshot the inputs the pipeline downloaded from the web, on T: SourceMaterial.

    uv run --frozen python src/scripts/landloss/archive/archive_web_inputs.py
    uv run --frozen python src/scripts/landloss/archive/archive_web_inputs.py --copy

Every web download lands in ``.koopcache`` (``landloss.io.koopcache_dir``). This
copies the ones a rerun would need to reproduce the run to
``SOURCE_MATERIAL_DIR/web-downloaded-inputs`` (``tdrive_sync_config.py``):

- **Koordinates layers and tables** (LINZ, and the WCC, GNS and NLM layers T+T
  hosts): the newest cached version of each, the one the runs read. A layer is
  copied whole, not the extents clipped from it. Older cached versions are only
  listed in the manifest.
- **The WCC ArcGIS and GNS WFS extracts**, as cached.
- **The LINZ elevation STAC JSON** cached while walking the catalogue.

**Not copied:** the DEM and DSM rasters, which are large and can be fetched
again, and anything read from T: or R: (``.tdrivecache``, ``gfdb/``), which is
there already. In place of the DEMs, ``dem_metadata.json`` records where they
came from: the STAC collections ``linz_stac_utils`` loads, the LiDAR surveys
under each authority with their capture dates and tile checksums, and the
SHA-256 of each authority's ``ground/dem-1m-<extent>.tif`` as the run used it.

``inputs_manifest.csv`` lists every file with its layer id, version, title and
publication date (looked up on Koordinates with the ``.env`` keys; the version
in the file name stands when a lookup fails), size and SHA-256.

Without ``--copy`` nothing is written to T: and T: is not read: the plan and the
two records are written to ``temp/archive/`` to read first. The DEM metadata
reads the public LINZ catalogue either way, caching what it reads.
"""

import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urljoin

import rasterio
import requests
from linz_stac_utils.elevation import (
    CONTOUR_8M_DEM_COLLECTION_ID,
    LIDAR_1M_DEM_COLLECTION_ID,
)
from pyproj import Transformer
from ttpy.gis.koop import KoordinatesConnection
from ttpy.gis.koop.backend.api.layers_and_tables.get_details import get_layer_details

import tdrive_sync as ts
from landloss.domain import constants
from landloss.io import koopcache_dir
from landloss.io.area_of_interest import get_area_of_interest
from landloss.io.elevation import (
    ELEVATION_CATALOG_URL,
    MAX_WORKERS,
    fetch_json,
    find_dem_collections,
)
from landloss.io.readers import resolve_api_key
from scripts.landloss.archive import config
from scripts.landloss.archive.copying import (
    PlannedCopy,
    damage,
    describe_plan,
    git_commit,
    run_copy,
    sha256,
    stamp,
    write_plan_csv,
)
from scripts.landloss.paths import TEMP_DIR

# A full Koordinates download: <layer>_<version>_<md5>.gpkg or .tif.
LAYER_FILE = re.compile(r"^(\d+)_(\d+)_[0-9a-f]{32}\.(gpkg|tif)$")
# A Koordinates table export: <table>_<version>.parquet.
TABLE_FILE = re.compile(r"^(\d+)_(\d+)\.parquet$")

# The layers T+T hosts on its own Koordinates site; every other layer id the
# cache holds is LINZ's.
TTGROUP_LAYERS = {
    constants.WCC_CUT_AREAS_LAYER_ID,
    constants.WCC_FILL_AREAS_LAYER_ID,
    constants.GNS_SLIDE_MORPHOLOGY_LAYER_ID,
    constants.GNS_SLIDE_GENESIS_LAYER_ID,
    constants.TT_MANUAL_WALLS_LAYER_ID,
    constants.NLM_GEOMORPHOLOGY_LAYER_ID,
    constants.NLM_FLATLAND_LAYER_ID,
    constants.GWD_MEDIAN_DEPTH_LAYER_ID,
}

# The services the ArcGIS and WFS extracts were read from, by cache folder.
SERVICE_URLS = {
    "arcgis": f"{constants.GNS_SLIDE_SERVICE_URL}/"
    f"{constants.GNS_SLIDE_INTERPRETED_MATERIALS_SUBLAYER}",
    "wfs": f"{constants.GNS_GEOSERVER_WFS_URL}?typeName="
    f"{constants.GNS_URBAN_WELLINGTON_GEOLOGY_LAYER}",
}

# How often a catalogue read is tried, and the first wait between tries.
FETCH_ATTEMPTS = 5
FETCH_BACKOFF_S = 2.0

DEM_NOTE = (
    "The DEMs are not copied. Each authority's 1 m DEM was loaded by "
    "linz_stac_utils.elevation.load_elevation from the LINZ elevation STAC "
    "catalogue: the national 1 m LiDAR DEM mosaic, falling back to the 8 m "
    "contour DEM where the mosaic has no data. Which cells came from the "
    "fallback is not recorded. 'surveys' are the 1 m DEM collections in the "
    "catalogue over each authority, newest first, as read when this was "
    "written; the mosaic is built from them. 'dem_file' is the DEM the run used, "
    "as written by ground step 1."
)


def newest(paths, pattern) -> list[tuple[Path, int, int]]:
    """Return the newest version of each id among cached files, as (path, id, version)."""
    best: dict[int, tuple[Path, int, int]] = {}
    for path in paths:
        match = pattern.match(path.name)
        if match is None:
            continue
        item = (path, int(match.group(1)), int(match.group(2)))
        if item[1] not in best or item[2] > best[item[1]][2]:
            best[item[1]] = item
    return sorted(best.values(), key=lambda item: item[1])


def plan_inputs(cache: Path, *, target_of) -> tuple[list[PlannedCopy], list[dict]]:
    """Plan the copy of the web downloads, and describe each file copied.

    Returns:
        The files to copy, and one manifest row per file without its hash.
    """
    plan, rows = [], []

    def add(path, group, **row):
        relative = path.relative_to(cache)
        plan.append(PlannedCopy(path, target_of(relative), group))
        rows.append({"path": relative.as_posix(), "group": group, **row})

    layer_dirs = [
        d for d in cache.iterdir() if d.is_dir() and d.name.split("-")[0].isdigit()
    ]
    for folder in sorted(layer_dirs):
        cached = [p for p in folder.iterdir() if p.is_file()]
        for path, layer, version_id in newest(cached, LAYER_FILE):
            older = sorted(
                int(m.group(2))
                for p in cached
                if (m := LAYER_FILE.match(p.name)) and int(m.group(2)) != version_id
            )
            add(
                path,
                "koordinates layer",
                layer_id=layer,
                version_id=version_id,
                older_cached_versions=" ".join(map(str, older)),
            )
    for path, table, version_id in newest(
        (cache / "tables").glob("*.parquet"), TABLE_FILE
    ):
        add(path, "koordinates table", layer_id=table, version_id=version_id)
    for kind in ("arcgis", "wfs"):
        for path in sorted((cache / kind).rglob("*.gpkg")):
            add(path, kind, source_url=SERVICE_URLS[kind])
    for path in sorted((cache / "nz-elevation").glob("*.json")):
        add(path, "elevation catalogue", source_url=ELEVATION_CATALOG_URL)
    return plan, rows


def look_up_layers(rows) -> None:
    """Add each Koordinates file's title and publication date, in place."""
    connections = {}
    for row in rows:
        if "version_id" not in row:
            continue
        layer = row["layer_id"]
        domain = (
            constants.TTGROUP_DOMAIN
            if layer in TTGROUP_LAYERS
            else constants.LINZ_DOMAIN
        )
        row["domain"] = domain
        try:
            if domain not in connections:
                connections[domain] = KoordinatesConnection(
                    api_key=resolve_api_key(domain), domain=domain
                )
            conn = connections[domain]
            details = get_layer_details(
                session=conn.session,
                domain=conn.domain,
                api_version=conn.api_version,
                layer_id=layer,
                version_id=row["version_id"],
            )
            row["title"], row["published_at"] = details.title, str(details.published_at)
        except Exception as error:
            row["title"] = f"lookup failed: {type(error).__name__}: {error}"[:200]


def describe_dem(path: Path) -> dict:
    """Return a DEM file's hash, size, grid and modification time."""
    with rasterio.open(path) as dem:
        grid = {
            "crs": str(dem.crs),
            "resolution_m": list(dem.res),
            "bounds": list(dem.bounds),
            "width": dem.width,
            "height": dem.height,
        }
    modified = datetime.fromtimestamp(path.stat().st_mtime, UTC).astimezone()
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "modified": modified.isoformat(timespec="seconds"),
        "sha256": sha256(path),
        **grid,
    }


def fetch_with_retries(url: str) -> dict | None:
    """Fetch one catalogue document, retrying a dropped connection, or None.

    The public bucket resets the odd connection when many are open at once,
    so each read is tried :data:`FETCH_ATTEMPTS` times, waiting longer each
    time, before it is given up on.
    """
    for attempt in range(FETCH_ATTEMPTS):
        try:
            return fetch_json(url)
        except requests.RequestException:
            time.sleep(FETCH_BACKOFF_S * 2**attempt)
    return None


def collections_with_retries(bbox_wgs84) -> list[dict]:
    """Return the 1 m DEM surveys over an extent, retrying a dropped connection.

    Raises:
        requests.RequestException: If the catalogue still fails on the last try.
    """
    for attempt in range(FETCH_ATTEMPTS - 1):
        try:
            return find_dem_collections(bbox_wgs84)
        except requests.RequestException:
            time.sleep(FETCH_BACKOFF_S * 2**attempt)
    return find_dem_collections(bbox_wgs84)


def dem_file(path: Path) -> dict | None:
    """Describe a DEM the run used, or say why it cannot be: missing or cut short."""
    if not path.exists():
        return None
    reason = damage(path)
    if reason is not None:
        return {"path": str(path), "bytes": path.stat().st_size, "damaged": reason}
    return describe_dem(path)


def survey_record(collection: dict, bbox_wgs84) -> dict:
    """Return a survey's identity, dates and the checksums of its tiles over the extent."""
    document = collection["document"]

    def tile(link: dict) -> dict | None:
        url = urljoin(collection["url"], link["href"])
        item = fetch_with_retries(url)
        if item is None:
            return {"id": None, "unread": url}
        bbox = item.get("bbox") or []
        if len(bbox) != 4 or not _overlaps(bbox, bbox_wgs84):
            return None
        properties = item.get("properties", {})
        asset = next(iter((item.get("assets") or {}).values()), {})
        return {
            "id": item.get("id"),
            "start_datetime": properties.get("start_datetime"),
            "end_datetime": properties.get("end_datetime"),
            "processing_version": properties.get("processing:version"),
            "file_checksum": asset.get("file:checksum"),
        }

    links = [link for link in document.get("links", []) if link.get("rel") == "item"]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        found = [t for t in pool.map(tile, links) if t is not None]
    tiles = [t for t in found if "unread" not in t]
    unread = [t["unread"] for t in found if "unread" in t]
    return {
        "id": collection["id"],
        "title": collection["title"],
        "url": collection["url"],
        "temporal_interval": document.get("extent", {})
        .get("temporal", {})
        .get("interval"),
        "created": document.get("created"),
        "updated": document.get("updated"),
        "providers": [p.get("name") for p in document.get("providers", [])],
        "license": document.get("license"),
        "tiles_over_extent": tiles,
        # Items the catalogue would not serve after every retry; each may or
        # may not lie over the extent.
        "items_unread": unread,
    }


def _overlaps(a, b) -> bool:
    """Return whether two (minx, miny, maxx, maxy) boxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def dem_metadata(sources) -> dict:
    """Describe the DEM each authority's run used, and the surveys under it."""
    to_wgs84 = Transformer.from_crs(2193, 4326, always_xy=True)
    extents = {}
    for authority, root in sources.items():
        print(f"  {authority} ...", flush=True)
        area = get_area_of_interest(authority)
        west, south, east, north = area.to_geoseries().to_crs(2193).total_bounds
        lon0, lat0 = to_wgs84.transform(west, south)
        lon1, lat1 = to_wgs84.transform(east, north)
        bbox_wgs84 = (lon0, lat0, lon1, lat1)
        dem_path = root / "ground" / f"dem-1m-{authority}.tif"
        extents[authority] = {
            "bbox_nztm": [west, south, east, north],
            "bbox_wgs84": list(bbox_wgs84),
            "dem_file": dem_file(dem_path),
            "surveys": [
                survey_record(collection, bbox_wgs84)
                for collection in collections_with_retries(bbox_wgs84)
            ],
        }
    return {
        "written": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
        "commit": git_commit(),
        "note": DEM_NOTE,
        "catalog": ELEVATION_CATALOG_URL,
        "loader": f"linz-stac-utils {version('linz-stac-utils')}",
        "collections_loaded": {
            "lidar_1m_dem_mosaic": LIDAR_1M_DEM_COLLECTION_ID,
            "contour_8m_dem_fallback": CONTOUR_8M_DEM_COLLECTION_ID,
        },
        "extents": extents,
    }


def write_manifest(rows, plan, path: Path) -> None:
    """Write the inputs manifest, hashing each file."""
    columns = [
        "path",
        "group",
        "layer_id",
        "version_id",
        "title",
        "published_at",
        "domain",
        "source_url",
        "older_cached_versions",
        "bytes",
        "sha256",
    ]
    with path.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for row, item in zip(rows, plan, strict=True):
            writer.writerow(
                {
                    **row,
                    "bytes": item.source.stat().st_size,
                    "sha256": sha256(item.source),
                }
            )


def main(*, sources, subdir, copy):
    """Plan the snapshot, write its records locally, and copy it all when asked.

    Args:
        sources: ``{authority: temp folder}`` whose DEMs are described.
        subdir: The folder under SOURCE_MATERIAL_DIR to copy to.
        copy: Whether to copy to T:; otherwise only the plan and records are
            written, under temp/archive/.
    """
    cache = koopcache_dir()
    target_root = ts.get_source_mat_base_path(subdir)
    plan, rows = plan_inputs(cache, target_of=lambda relative: target_root / relative)
    print(f"Snapshotting {cache} to {target_root}")
    describe_plan(plan)
    print("Looking up the Koordinates layers ...", flush=True)
    look_up_layers(rows)
    print("Describing the DEMs ...", flush=True)
    metadata = dem_metadata(sources)

    when = stamp()
    local = TEMP_DIR / "archive" / f"web-inputs-{when}"
    local.mkdir(parents=True, exist_ok=True)
    write_plan_csv(plan, local / "plan.csv")
    write_manifest(rows, plan, local / "inputs_manifest.csv")
    (local / "dem_metadata.json").write_text(
        json.dumps(metadata, indent=1), encoding="utf-8"
    )
    print(f"Wrote the plan, inputs_manifest.csv and dem_metadata.json to {local}")
    if not copy:
        print("Dry run: nothing was copied. Run again with --copy to copy.")
        return
    records = [
        PlannedCopy(local / name, target_root / f"{when}-{name}", "records")
        for name in ("inputs_manifest.csv", "dem_metadata.json")
    ]
    run_copy(plan + records)
    print(f"Copied, with {when}-inputs_manifest.csv and {when}-dem_metadata.json")


if __name__ == "__main__":
    main(
        sources=config.DEM_SOURCES,
        subdir=config.WEB_INPUTS_SUBDIR,
        copy="--copy" in sys.argv[1:],
    )
