"""Point sampling of the LINZ 1 m LiDAR DEM, straight from the open STAC catalogue.

LINZ publishes its elevation data as a *static* STAC catalogue on S3: a root
catalogue listing one collection per LiDAR survey, each collection listing tile
items, each item carrying a single cloud optimised GeoTIFF. There is no search
API, so finding the tiles under a point means walking that tree.

This module does the walk, caches the JSON it reads, and samples the tiles
through GDAL's HTTP range requests, so only the few kilobytes of each COG that
sit under the sample points are ever transferred. No DEM is downloaded whole.

Surveys overlap -- Hutt City was flown in 2021 and again in 2025, over ground
already covered by the 2013-2014 Wellington survey -- so tiles are consulted
newest first and a point takes its elevation from the most recent survey that
covers it.

``linz_stac_utils.elevation.ElevationClient`` is the obvious alternative and is
already installed, but its ``load_lidar_dem`` searches for a hardcoded collection
ID (``01JE4ZZWAG19KPKRHYJJP02HC9``) that is not present in the catalogue. A
search for it walks all 224 collections, matches nothing, and does not return in
any workable time.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import rasterio
import requests
from pyproj import Transformer

from landloss.domain import constants
from landloss.io import koopcache_dir

ELEVATION_CATALOG_URL = (
    "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/catalog.json"
)

# Only the bare earth DEM; the catalogue carries matching DSM collections whose
# hrefs differ only in this segment, and a surface model would put tree canopy
# and rooftops into a terrain section.
DEM_PATH_MARKER = "/dem_1m/"

CACHE_SUBDIR = "nz-elevation"

# Enough threads to hide the latency of many small S3 reads without being
# impolite to a public bucket.
MAX_WORKERS = 16

_YEAR = re.compile(r"(\d{4})(?:-(\d{4}))?")


def cache_dir() -> Path:
    """Return the directory catalogue JSON is cached in, creating it if needed."""
    return koopcache_dir(CACHE_SUBDIR)


def _cache_path(url: str) -> Path:
    """Return the local file a catalogue URL is cached at."""
    # The catalogue's own path is unique and readable, so it makes a better key
    # than a hash would when looking at what has been cached.
    tail = url.rsplit("nz-elevation.s3-ap-southeast-2.amazonaws.com/", maxsplit=1)[-1]
    return cache_dir() / tail.replace("/", "_")


def fetch_json(url: str, *, use_cache: bool = True) -> dict:
    """Fetch one catalogue document, reading from and writing to the disk cache.

    Args:
        url: The document to fetch.
        use_cache: Whether to read and write the cache.

    Returns:
        The parsed document.
    """
    path = _cache_path(url)
    if use_cache and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    document = response.json()

    if use_cache:
        path.write_text(json.dumps(document), encoding="utf-8")

    return document


def _survey_year(title: str, href: str) -> int:
    """Return the last year a survey covers, for ordering surveys by recency."""
    match = _YEAR.search(title) or _YEAR.search(href)
    if match is None:
        return 0
    return int(match.group(2) or match.group(1))


def _overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """Return whether two (minx, miny, maxx, maxy) boxes overlap."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def find_dem_collections(
    bbox_wgs84: tuple[float, float, float, float], *, use_cache: bool = True
) -> list[dict]:
    """Find the 1 m DEM survey collections covering an extent, newest first.

    Args:
        bbox_wgs84: The extent of interest (minx, miny, maxx, maxy) in WGS84.
        use_cache: Whether to read and write the catalogue cache.

    Returns:
        One dict per covering survey, with ``id``, ``title``, ``url`` and
        ``year``, ordered most recent first.
    """
    root = fetch_json(ELEVATION_CATALOG_URL, use_cache=use_cache)
    candidates = [
        link
        for link in root.get("links", [])
        if link.get("rel") == "child" and DEM_PATH_MARKER in (link.get("href") or "")
    ]

    def load(link: dict) -> dict | None:
        url = urljoin(ELEVATION_CATALOG_URL, link["href"])
        collection = fetch_json(url, use_cache=use_cache)
        boxes = (collection.get("extent", {}).get("spatial", {}) or {}).get("bbox", [])
        if not boxes or not _overlaps(tuple(boxes[0]), bbox_wgs84):
            return None
        title = collection.get("title", "")
        return {
            "id": collection.get("id"),
            "title": title,
            "url": url,
            "year": _survey_year(title, link["href"]),
            "document": collection,
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        found = [c for c in pool.map(load, candidates) if c is not None]

    return sorted(found, key=lambda c: c["year"], reverse=True)


def find_tiles(
    collection: dict,
    bbox_wgs84: tuple[float, float, float, float],
    *,
    use_cache: bool = True,
) -> list[dict]:
    """Find the tiles of one survey that intersect an extent.

    Args:
        collection: A collection as returned by :func:`find_dem_collections`.
        bbox_wgs84: The extent of interest (minx, miny, maxx, maxy) in WGS84.
        use_cache: Whether to read and write the catalogue cache.

    Returns:
        One dict per intersecting tile, with ``id``, ``bbox`` and ``asset`` (the
        URL of its cloud optimised GeoTIFF).
    """
    base = collection["url"]
    links = [
        link
        for link in collection["document"].get("links", [])
        if link.get("rel") == "item"
    ]

    def load(link: dict) -> dict | None:
        item = fetch_json(urljoin(base, link["href"]), use_cache=use_cache)
        bbox = tuple(item.get("bbox", ()))
        if len(bbox) != 4 or not _overlaps(bbox, bbox_wgs84):
            return None
        assets = item.get("assets") or {}
        asset = next(iter(assets.values()), None)
        if asset is None:
            return None
        return {
            "id": item.get("id"),
            "bbox": bbox,
            "asset": urljoin(base, asset["href"]),
        }

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return [t for t in pool.map(load, links) if t is not None]


def sample_elevation(
    eastings: np.ndarray,
    northings: np.ndarray,
    *,
    use_cache: bool = True,
) -> np.ndarray:
    """Sample ground elevation at points, from the most recent LiDAR covering each.

    Licence:
        The LINZ elevation catalogue is licensed Creative Commons Attribution 4.0
        International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/,
        as declared by each survey collection. Anything derived from it and
        published -- a cross-section figure included -- must credit Land
        Information New Zealand and the relevant LiDAR survey, link the licence,
        and say if the data was changed.

    Source:
        Land Information New Zealand, https://data.linz.govt.nz/, served as a
        static STAC catalogue from the open ``nz-elevation`` S3 bucket. No API
        key is needed.

    Args:
        eastings: Sample point eastings, in NZTM (EPSG:2193).
        northings: Sample point northings, in NZTM (EPSG:2193).
        use_cache: Whether to read and write the catalogue cache.

    Returns:
        Ground elevation in metres at each point, NaN where no survey covers it
        or the survey itself has no data there.

    Raises:
        ValueError: If the two coordinate arrays differ in length.
    """
    eastings = np.asarray(eastings, dtype="float64")
    northings = np.asarray(northings, dtype="float64")
    if eastings.shape != northings.shape:
        msg = "eastings and northings must be the same length."
        raise ValueError(msg)

    to_wgs84 = Transformer.from_crs(constants.DEFAULT_CRS, "EPSG:4326", always_xy=True)
    lons, lats = to_wgs84.transform(eastings, northings)
    bbox = (float(lons.min()), float(lats.min()), float(lons.max()), float(lats.max()))

    elevation = np.full(eastings.shape, np.nan, dtype="float64")
    coordinates = list(zip(eastings, northings, strict=True))

    # Range requests over HTTPS; without these GDAL lists the whole bucket
    # prefix on every open, which dominates the run time.
    gdal_options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    }

    with rasterio.Env(**gdal_options):
        for collection in find_dem_collections(bbox, use_cache=use_cache):
            outstanding = np.isnan(elevation)
            if not outstanding.any():
                break

            for tile in find_tiles(collection, bbox, use_cache=use_cache):
                minx, miny, maxx, maxy = tile["bbox"]

                # Only points still missing an elevation *and* inside this tile
                # are worth a read; the rest would come back as nodata anyway.
                wanted = np.flatnonzero(
                    np.isnan(elevation)
                    & (lons >= minx)
                    & (lons <= maxx)
                    & (lats >= miny)
                    & (lats <= maxy)
                )
                if wanted.size == 0:
                    continue

                with rasterio.open(tile["asset"]) as src:
                    values = np.array(
                        [v[0] for v in src.sample([coordinates[i] for i in wanted])],
                        dtype="float64",
                    )
                    if src.nodata is not None:
                        values[values == src.nodata] = np.nan
                    elevation[wanted] = values

    return elevation
