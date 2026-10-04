r"""Inputs for reproducing Kritikos et al. (2015) on its own events.

The paper's training events are Northridge 1994 and Wenchuan 2008. Each needs a
landslide inventory, a ShakeMap intensity grid, a map of active faults and a DEM.

Sources:
    - Inventories: the USGS Ground Failure Database v4, read with
      :mod:`landloss.io.gfdb` from ``R:``. Northridge is Harp and Jibson (1995)
      polygons, the paper's 11,111 landslides; Wenchuan is Gorum et al. (2011)
      points, the paper's 60,109. Both are public USGS data release content.
    - Intensity: the USGS ShakeMap ``grid.xml`` of the event, downloaded once
      into ``temp/reference/kritikos_2015_validation/``. USGS products are in
      the public domain.
    - Faults: the GEM Global Active Faults Database (Styron and Pagani, 2020,
      doi:10.1177/8755293020944182), GitHub release of the harmonised GeoJSON.
      Licence CC BY-SA 4.0 as its README states it (verify); attribute GEM.
      The paper used each region's own mapped faults, so this is a stand-in.
    - DEM: Copernicus DEM GLO-30 (ESA, 2021), 1 arc-second, anonymous from the
      public ``copernicus-dem-30m`` bucket on AWS, aggregated here to the
      model's 60 m grid. Licence: free of charge with attribution, "Produced
      using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus
      Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
      European Union and ESA; all rights reserved". The paper used 60 m ASTER
      (Northridge) and Gorum et al.'s 60 m DEM (Wenchuan), so this is a
      stand-in.

These are working copies for a validation, kept under ``temp/`` with the
sources recorded in ``SOURCES.md`` there; nothing here is redistributed.
"""

import math
import shutil
import urllib.request
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import rasterio
import rioxarray  # noqa: F401 - registers the .rio accessor
import xarray as xr
from rasterio.enums import Resampling
from rasterio.merge import merge

from landloss.io import gfdb
from landloss.io.shakemap import get_shakemap_grid
from scripts.landloss.paths import TEMP_DIR

REFERENCE_DIR = TEMP_DIR / "reference" / "kritikos_2015_validation"

GEM_FAULTS_URL = (
    "https://raw.githubusercontent.com/GEMScienceTools/gem-global-active-faults/"
    "master/geojson/gem_active_faults_harmonized.geojson"
)
COPERNICUS_URL = (
    "https://copernicus-dem-30m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
    "Copernicus_DSM_COG_10_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif"
)

# The cell size of the model's grid.
RESOLUTION_M = 60.0


@dataclass(frozen=True)
class Event:
    """One of the paper's events and where its inputs come from."""

    name: str
    utm_crs: str
    gfdb_event_name: str
    gfdb_inventory: str
    gfdb_layer: str  # "polygons" or "points"
    shakemap_url: str
    published_auc: float
    published_auc_over_5deg: float


EVENTS = {
    "northridge": Event(
        name="northridge",
        utm_crs="EPSG:32611",
        gfdb_event_name="M 6.7 - 1km NNW of Reseda, CA",
        gfdb_inventory="Harp and Jibson (1995)",
        gfdb_layer="polygons",
        shakemap_url=(
            "https://earthquake.usgs.gov/product/shakemap/ci3144585/atlas/"
            "1594159786829/download/grid.xml"
        ),
        published_auc=0.904,
        published_auc_over_5deg=0.871,
    ),
    "wenchuan": Event(
        name="wenchuan",
        utm_crs="EPSG:32648",
        gfdb_event_name="M 7.9 - 58 km W of Tianpeng, China",
        gfdb_inventory="Gorum and others (2011)",
        gfdb_layer="points",
        shakemap_url=(
            "https://earthquake.usgs.gov/product/shakemap/usp000g650/atlas/"
            "1594174375811/download/grid.xml"
        ),
        published_auc=0.839,
        published_auc_over_5deg=0.845,
    ),
}


def _download(url, path, *, use_cache):
    """Fetch a URL to a file, unless a cached copy is wanted and present."""
    if use_cache and path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, path.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(response, out)
    return path


def get_landslide_points(event, *, use_cache):
    """Return the event's landslides as one point each, in the event's UTM CRS.

    The paper reduces landslide polygons to a point at the top of each. This
    takes the polygon's representative point instead, which lies inside it; a
    polygon is far smaller than the 60 m cell except for the largest ones.
    """
    read = (
        gfdb.get_gfdb_ground_failure_polygons
        if event.gfdb_layer == "polygons"
        else gfdb.get_gfdb_ground_failure_points
    )
    landslides = read(event_name=event.gfdb_event_name, use_cache=use_cache)
    landslides = landslides[
        (landslides["type"] == "Landslide")
        & (landslides["inventory_name"] == event.gfdb_inventory)
    ]
    landslides = landslides.to_crs(event.utm_crs)
    points = landslides.geometry.representative_point()
    return gpd.GeoSeries(points, crs=event.utm_crs)


def get_shakemap_mmi(event, *, use_cache):
    """Return the event's ShakeMap intensity on its own EPSG:4326 grid."""
    path = _download(
        event.shakemap_url,
        REFERENCE_DIR / f"{event.name}-grid.xml",
        use_cache=use_cache,
    )
    return get_shakemap_grid(path)["mmi"]


def get_gem_active_faults(*, use_cache):
    """Return the GEM Global Active Faults traces in EPSG:4326."""
    path = _download(
        GEM_FAULTS_URL,
        REFERENCE_DIR / "gem_active_faults_harmonized.geojson",
        use_cache=use_cache,
    )
    return gpd.read_file(path)


def get_dem_60m(event, bounds_utm, *, use_cache):
    """Return Copernicus GLO-30 aggregated to a 60 m grid over a UTM extent.

    Args:
        event: The event, for its UTM CRS.
        bounds_utm: (minx, miny, maxx, maxy) in the event's UTM CRS. The grid
            is snapped outward to whole 60 m cells from the origin.
        use_cache: Reuse downloaded tiles.

    Returns:
        Elevation in metres on a 60 m grid in the event's UTM CRS, NaN where
        there is no ground, by averaging the 30 m cells.
    """
    minx = math.floor(bounds_utm[0] / RESOLUTION_M) * RESOLUTION_M
    miny = math.floor(bounds_utm[1] / RESOLUTION_M) * RESOLUTION_M
    maxx = math.ceil(bounds_utm[2] / RESOLUTION_M) * RESOLUTION_M
    maxy = math.ceil(bounds_utm[3] / RESOLUTION_M) * RESOLUTION_M
    box = gpd.GeoSeries.from_xy([minx, maxx], [miny, maxy], crs=event.utm_crs)
    west, south, east, north = box.to_crs("EPSG:4326").total_bounds
    tiles = []
    for lat in range(math.floor(south), math.floor(north) + 1):
        for lon in range(math.floor(west), math.floor(east) + 1):
            ns, ew = ("N" if lat >= 0 else "S"), ("E" if lon >= 0 else "W")
            url = COPERNICUS_URL.format(ns=ns, lat=abs(lat), ew=ew, lon=abs(lon))
            name = f"copernicus-dsm-30m-{ns}{abs(lat):02d}-{ew}{abs(lon):03d}.tif"
            tiles.append(_download(url, REFERENCE_DIR / name, use_cache=use_cache))

    handles = [rasterio.open(tile) for tile in tiles]
    try:
        nodata = handles[0].nodata
        mosaic, transform = merge(
            handles,
            bounds=(west - 0.01, south - 0.01, east + 0.01, north + 0.01),
            nodata=nodata,
        )
    finally:
        for handle in handles:
            handle.close()
    dem = xr.DataArray(
        mosaic[0].astype("float32"),
        dims=("y", "x"),
        coords={
            "y": transform.f + transform.e * (np.arange(mosaic.shape[1]) + 0.5),
            "x": transform.c + transform.a * (np.arange(mosaic.shape[2]) + 0.5),
        },
    ).rio.write_crs("EPSG:4326")
    if nodata is not None:
        dem = dem.where(dem != nodata)
    dem = dem.rio.write_nodata(np.nan)

    width = round((maxx - minx) / RESOLUTION_M)
    height = round((maxy - miny) / RESOLUTION_M)
    template = xr.DataArray(
        np.zeros((height, width), dtype="float32"),
        dims=("y", "x"),
        coords={
            "y": maxy - RESOLUTION_M * (np.arange(height) + 0.5),
            "x": minx + RESOLUTION_M * (np.arange(width) + 0.5),
        },
    ).rio.write_crs(event.utm_crs)
    return dem.rio.reproject_match(template, resampling=Resampling.average)


def get_mmi_on(mmi, template):
    """Return ShakeMap intensity bilinearly resampled onto a template grid."""
    mmi = mmi.rio.write_crs("EPSG:4326")
    return mmi.rio.reproject_match(template, resampling=Resampling.bilinear)


def get_faults_utm(event, template, *, use_cache):
    """Return the GEM traces near a grid, reprojected to the event's UTM CRS."""
    faults = get_gem_active_faults(use_cache=use_cache)
    left, bottom, right, top = template.rio.transform_bounds("EPSG:4326")
    margin = 0.6  # a bit over the 55 km far-field reach, in degrees
    faults = faults.cx[left - margin : right + margin, bottom - margin : top + margin]
    return faults.to_crs(event.utm_crs)
