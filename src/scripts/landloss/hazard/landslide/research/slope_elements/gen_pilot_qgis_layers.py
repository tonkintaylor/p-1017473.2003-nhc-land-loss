"""Write the old and new D2 pilot layers for a QGIS project.

Runs both pipelines over the whole pilot (the old free-face seeding with banks off, and
the pip/pif/siz one) and writes, under ``temp/qgis-d2-pilot/``, the layers a QGIS
project of the comparison needs: hillshade, contours, evacuated / imminent / inundated
zones for the old run and the two new wall scenarios, the elements each grew, the old
seeds, the new pips and the pif table. The project itself is built from these by
``.agents/skills/making-qgis-projects/scripts/build_qgis_project.py``.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/gen_pilot_qgis_layers.py
"""

import contextlib

import contourpy
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib.colors import LightSource
from rasterio import features
from shapely.geometry import shape

from landloss.hazard.landslide.slope_polygons import (
    EVACUATED,
    IMMINENT,
    INUNDATED,
    polygon_geometries,
)
from scripts.landloss.hazard.landslide.research.slope_elements import (
    fig_pilot_example_instability_zones as new,
)
from scripts.landloss.hazard.landslide.research.slope_elements import (
    fig_pilot_example_slope_elements as old,
)
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.paths import TEMP_DIR

OUT_DIR = TEMP_DIR / "qgis-d2-pilot"
CRS = old.CRS
ZONE_ORDER = (INUNDATED, IMMINENT, EVACUATED)


def zones_frame(result, found):
    """Every zone of every polygon, widest zone first so QGIS draws the core last."""
    frames = []
    kinds = result.polygons["element_type"]
    for zone in ZONE_ORDER:
        frame = polygon_geometries(result, zone=zone, crs=CRS)
        frame["zone"] = zone
        frame["element_type"] = kinds.loc[frame["polygon"]].to_numpy()
        frames.append(frame)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=CRS)


def elements_frame(found, transform):
    """The elements' cells as one polygon each, with their measurements."""
    labels = found.labels.astype("int32")
    shapes = {}
    for geometry, value in features.shapes(labels, mask=labels > 0, transform=transform):
        shapes.setdefault(int(value), []).append(shape(geometry))
    elements = found.elements
    keep = [c for c in ("element_type", "height_m", "overall_angle_deg") if c in elements]
    frame = elements.loc[list(shapes), keep].copy()
    frame.index.name = "label"
    return gpd.GeoDataFrame(
        frame.reset_index(),
        geometry=[shapely.union_all(g) for g in shapes.values()],
        crs=CRS,
    )


def points_frame(mask, transform, **columns):
    rows, cols = np.nonzero(mask)
    frame = gpd.GeoDataFrame(
        {name: values[rows, cols] for name, values in columns.items()},
        geometry=gpd.points_from_xy(
            transform.c + (cols + 0.5) * transform.a,
            transform.f + (rows + 0.5) * transform.e,
        ),
        crs=CRS,
    )
    return frame


def write_hillshade(dem_run, transform, path):
    filled = np.where(np.isnan(dem_run), np.nanmin(dem_run), dem_run)
    shade = LightSource(azdeg=315, altdeg=40).hillshade(
        filled, vert_exag=1.5, dx=1, dy=1
    )
    shade = np.where(np.isnan(dem_run), np.nan, shade).astype("float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=shade.shape[0],
        width=shade.shape[1],
        count=1,
        dtype="float32",
        crs=CRS,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        dst.write(shade, 1)


def write_contours(dem_run, transform, minor_path, major_path, *, minor_m, major_m):
    """Contours from cell-centre coordinates, minor ones without the major levels."""
    n_rows, n_cols = dem_run.shape
    x = transform.c + (np.arange(n_cols) + 0.5) * transform.a
    y = transform.f + (np.arange(n_rows) + 0.5) * transform.e
    generator = contourpy.contour_generator(
        x, y, np.ma.masked_invalid(dem_run), line_type=contourpy.LineType.Separate
    )
    low, high = np.nanmin(dem_run), np.nanmax(dem_run)
    levels = np.arange(np.ceil(low / minor_m) * minor_m, high, minor_m)
    minor, major = [], []
    for level in levels:
        lines = [shapely.LineString(line) for line in generator.lines(level) if len(line) > 1]
        target = major if level % major_m == 0 else minor
        target.extend({"elev_m": float(level), "geometry": line} for line in lines)
    for rows, path in ((minor, minor_path), (major, major_path)):
        gpd.GeoDataFrame(rows, crs=CRS).to_file(path, driver="GPKG")


def main(*, extent, bank_slope_deg, minor_m, major_m):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zones, _, views = new.get_zone_run(extent=extent)
    pilot = old.get_pilot_run(extent=extent, bank_slope_deg=bank_slope_deg)
    transform = pilot.transform
    dem_run = np.where(pilot.water, np.nan, pilot.dem)

    write_hillshade(dem_run, transform, OUT_DIR / "hillshade.tif")
    write_contours(
        dem_run,
        transform,
        OUT_DIR / "contours-minor.gpkg",
        OUT_DIR / "contours-major.gpkg",
        minor_m=minor_m,
        major_m=major_m,
    )

    outputs = {
        "old-zones": zones_frame(pilot.result, pilot.found),
        "new-zones-all-walled": zones_frame(views["walled"].result, views["walled"].found),
        "new-zones-none-walled": zones_frame(views["bare"].result, views["bare"].found),
        "old-elements": elements_frame(pilot.found, transform),
        "new-elements": elements_frame(zones.found, transform),
        "old-seeds": points_frame(
            pilot.seed_free_face | pilot.seed_bank,
            transform,
            seed=np.where(pilot.seed_bank, "bank", "free_face"),
        ),
    }
    is_siz = np.zeros(len(zones.sizs) + 1, dtype=bool)
    is_siz[zones.sizs.index.to_numpy()] = zones.sizs["is_siz"].to_numpy()
    outputs["new-pips"] = points_frame(
        zones.pips.mask,
        transform,
        pif_id=zones.pif_labels,
        is_siz=np.where(is_siz[zones.pif_labels], "siz", "not_siz"),
    )
    sizs = zones.sizs.reset_index()
    outputs["new-pifs"] = gpd.GeoDataFrame(
        sizs.assign(is_siz=np.where(sizs["is_siz"], "siz", "not_siz")),
        geometry=gpd.points_from_xy(sizs["x"], sizs["y"]),
        crs=CRS,
    )
    outputs["gns-mapped-walls"] = pilot.walls[["geometry"]].copy()
    ground = gpd.read_parquet(ground_map_path(extent=extent))
    outputs["ground-map"] = ground[
        ["material", "modification", "fill_thickness_m", "geometry"]
    ]
    for name, frame in outputs.items():
        path = OUT_DIR / f"{name}.gpkg"
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        frame.to_file(path, driver="GPKG")
        print(f"{name}: {len(frame):,} features")
    print(OUT_DIR)


if __name__ == "__main__":
    main(
        extent=config.PILOT_EXTENT,
        bank_slope_deg=config.PILOT_BANK_SLOPE_DEG,
        minor_m=2.0,
        major_m=10.0,
    )
