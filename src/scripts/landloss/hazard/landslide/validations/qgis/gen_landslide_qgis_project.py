"""Build the landslide QGIS project: the whole chain, from pips to failed ground.

    uv run --frozen python src/scripts/landloss/hazard/landslide/validations/qgis/gen_landslide_qgis_project.py

Writes ``temp/qgis/landslide-models/landslide-models<suffix>.qgs`` and, beside
it, the layers QGIS cannot read straight from the step outputs:

- **every urban polygon's evacuated, imminent and inundated ground, failed or
  not**, from step 8's model (which holds all three geometries per
  ``slope_id``), each row marked by whether its ``slope_id`` failed in step 9;
- the **pips coloured by their pif's cut/fill class** (step 13), and the line
  from each pip to the foot of its face;
- the pif spines by class, the forced polygons and the flatland, each with one
  geometry column;
- a 1 m hillshade and 5 m contours.

Step 8's model file carries four geometry columns, and QGIS opens it on
``rep_point``, as points, so every model layer is a copy with the polygon
alone. The copies are rewritten on every run, so rerun this script after the
landslide steps rerun.

Nothing is recomputed: each layer is a step's output cut to the columns worth
inspecting, joined on the ids the steps write. The project is built by the
``making-qgis-projects`` skill's builder, which this script loads by path.
"""

import importlib.util

import contourpy
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from matplotlib.colors import LightSource

from landloss.io.area_of_interest import extent_suffix
from scripts.landloss.hazard.landslide.steps.s1_landslide_realisation.s1_simulate_landslides import (
    realisation_path as large_realisation_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
    slope_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s5_slope_units.gen_slope_units import (
    slope_units_path,
)
from scripts.landloss.hazard.landslide.steps.s8_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s9_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.hazard.landslide.steps.s10_hancox_1997.gen_hancox_1997_coverage import (
    coverage_path as hancox_coverage_path,
)
from scripts.landloss.hazard.landslide.steps.s11_kritikos_2015.gen_kritikos_2015_hazard import (
    coverage_path as kritikos_coverage_path,
)
from scripts.landloss.hazard.landslide.steps.s11_kritikos_2015.gen_kritikos_2015_hazard import (
    hazard_path as kritikos_hazard_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    elements_path,
    siz_table_path,
    wall_elements_path,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
    pif_cut_fill_pips_path,
)
from scripts.landloss.hazard.landslide.validations.qgis import config
from scripts.landloss.paths import REPO_ROOT, TEMP_DIR

OUT_DIR = TEMP_DIR / "qgis" / "landslide-models"
BUILDER_PATH = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "making-qgis-projects"
    / "scripts"
    / "build_qgis_project.py"
)

# The colours the reviewer pages use, so the project and the page read alike.
CLASS_COLOUR = {
    "cut": ["#2a78d6", "Cut"],
    "fill": ["#eb6834", "Fill"],
    "cut_and_fill": ["#8a5cc2", "Cut and fill"],
    "natural": ["#1baf7a", "Natural"],
    "uncertain": ["#b4b4b0", "Uncertain"],
    "unknown": ["#55554f", "Unknown"],
}
# Failed ground is drawn in the land class colours; ground that stood is a pale
# version of the same, so a reviewer sees both and tells them apart.
ZONE_OUTCOME_COLOUR = {
    "evacuated · failed": ["#a50026", "Evacuated land, failed"],
    "inundated · failed": ["#f46d43", "Inundated land, failed"],
    "imminent · failed": ["#fdae61", "Imminent land, failed"],
    "evacuated · stood": ["#f4c7c3", "Evacuated land, did not fail"],
    "inundated · stood": ["#fde0d0", "Inundated land, did not fail"],
    "imminent · stood": ["#fff2cc", "Imminent land, did not fail"],
}
# Drawn widest first and failed last, so the evacuated ground and the failures
# sit on top.
ZONE_DRAW_ORDER = ["imminent", "inundated", "evacuated"]
ZONE_COLOUR = {
    "evacuated": ["#a50026", "Evacuated"],
    "imminent": ["#fee08b", "Imminent"],
    "inundated": ["#f46d43", "Inundated"],
}
WALL_STATE_COLOUR = {
    "cut_wall": ["#2c7fb8", "Cut wall"],
    "fill_wall": ["#31a354", "Fill wall"],
    "no_wall": ["#969696", "No wall"],
}
MATERIAL_COLOUR = {
    "rock": ["#8d6e63", "Rock"],
    "colluvium": ["#c0a060", "Colluvium"],
    "fill_uncontrolled": ["#eb6834", "Fill, uncontrolled"],
    "fill_engineered": ["#f2a65a", "Fill, engineered"],
    "alluvium": ["#7fb3d5", "Alluvium"],
    "loess": ["#d9c27a", "Loess"],
    "unknown": ["#b4b4b0", "Unknown"],
}
LAND_CLASS_COLOUR = {
    "evacuated land": ["#a50026", "Evacuated land"],
    "inundated land": ["#f46d43", "Inundated land"],
    "imminent land": ["#fee08b", "Imminent land"],
}

MODEL_COLUMNS = [
    "slope_id",
    "wall_state",
    "fragility_basis",
    "wall_type",
    "size_class",
    "kingsbury_zone",
    "continuous_rating",
    "amp_factor",
    "rate_factor",
    "theta",
    "beta",
    "material",
    "modification",
]


def load_builder():
    """The QGIS project builder of the making-qgis-projects skill, as a module."""
    spec = importlib.util.spec_from_file_location("build_qgis_project", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(frame, name):
    """Write one layer beside the project and return its path."""
    path = OUT_DIR / name
    frame.to_parquet(path)
    print(f"wrote {path.name}: {len(frame):,} rows")
    return path


def gen_zone_outcomes(model, realisation):
    """Every model polygon's three kinds of ground, each marked failed or stood.

    A polygon failed if step 9 wrote evacuated ground under its ``slope_id``.
    One that failed but was absorbed by a larger failure is not written under
    its own id, so it shows as stood here; its ground is inside the larger
    failure's.
    """
    urban = realisation[realisation["population"] == "urban"]
    failed = set(urban.loc[urban["land_class"] == "evacuated land", "slope_id"])
    frames = []
    for zone in ZONE_DRAW_ORDER:
        part = model[[*MODEL_COLUMNS, zone]].dropna(subset=[zone])
        values = part[zone]
        if not isinstance(values, gpd.GeoSeries):
            values = gpd.GeoSeries(shapely.from_wkb(values), crs=model.crs)
        geometry = gpd.GeoSeries(values.values, crs=model.crs)
        frame = gpd.GeoDataFrame(
            part[MODEL_COLUMNS], geometry=geometry.values, crs=model.crs
        )
        frame = frame[~frame.geometry.is_empty]
        frame.insert(1, "zone", zone)
        frame.insert(2, "failed", frame["slope_id"].isin(failed))
        frames.append(frame)
    zones = pd.concat(frames, ignore_index=True)
    zones["outcome"] = (
        zones["zone"] + " · " + np.where(zones["failed"], "failed", "stood")
    )
    order = zones["zone"].map({z: i for i, z in enumerate(ZONE_DRAW_ORDER)})
    zones = zones.assign(_order=order * 2 + zones["failed"]).sort_values("_order")
    return gpd.GeoDataFrame(zones.drop(columns="_order"), crs=model.crs)


def gen_pips(pif_table, pips):
    """The pips as points, with their pif's cut/fill class."""
    classes = pif_table.set_index("pif_id")["cut_fill_class"]
    points = gpd.GeoDataFrame(
        pips[["pif_id", "z"]].assign(cut_fill_class=pips["pif_id"].map(classes)),
        geometry=gpd.points_from_xy(pips["x"], pips["y"]),
        crs="EPSG:2193",
    )
    walked = pips[pips["foot_x"].notna()]
    ticks = shapely.linestrings(
        np.stack(
            [walked[["x", "foot_x"]].to_numpy(), walked[["y", "foot_y"]].to_numpy()],
            axis=-1,
        )
    )
    feet = gpd.GeoDataFrame(
        walked[["pif_id"]].assign(cut_fill_class=walked["pif_id"].map(classes)),
        geometry=ticks,
        crs="EPSG:2193",
    )
    return points, feet


def gen_spines(sizs, pif_table):
    """Each pif piece's spine as a line, with its class and siz flag."""
    spine = sizs["spine"]
    if not isinstance(spine, gpd.GeoSeries):
        spine = gpd.GeoSeries(shapely.from_wkb(spine), crs=sizs.crs)
    classes = pif_table.set_index("pif_id")["cut_fill_class"]
    columns = [
        "pif_id",
        "parent_pif_id",
        "candidate_class",
        "is_siz",
        "ground_group",
        "near_drop_p80_m",
        "gns_wall",
    ]
    frame = sizs[columns].assign(cut_fill_class=sizs["pif_id"].map(classes))
    return gpd.GeoDataFrame(frame, geometry=spine.values, crs=sizs.crs)


def gen_flatland(ground):
    """The NLM flatland pieces of the ground map, dissolved."""
    flat = ground[ground["is_flatland"].fillna(value=False).astype(bool)]
    return flat[["geometry"]].dissolve().explode(index_parts=False)


def gen_hillshade(dem, out):
    """A hillshade of the DEM, written as a GeoTIFF."""
    with rasterio.open(dem) as src:
        z = src.read(1, masked=True).astype(float).filled(np.nan)
        profile = src.profile
        cell = src.res[0]
    shade = LightSource(azdeg=315, altdeg=45).hillshade(
        np.nan_to_num(z, nan=np.nanmin(z)), dx=cell, dy=cell
    )
    profile.update(dtype="uint8", count=1, nodata=0, compress="deflate")
    with rasterio.open(out, "w", **profile) as dst:
        dst.write((1 + shade * 254).astype("uint8"), 1)
    print(f"wrote {out.name}")
    return out


def gen_contours(dem, *, step_m, index_m):
    """Contour lines of the DEM every ``step_m``, flagged every ``index_m``."""
    with rasterio.open(dem) as src:
        z = src.read(1, masked=True).astype(float).filled(np.nan)
        transform = src.transform
        crs = src.crs
    rows, cols = np.mgrid[0 : z.shape[0], 0 : z.shape[1]]
    xs, ys = rasterio.transform.xy(transform, rows, cols)
    generator = contourpy.contour_generator(
        np.asarray(xs).reshape(z.shape), np.asarray(ys).reshape(z.shape), z
    )
    records = []
    for level in np.arange(
        np.floor(np.nanmin(z) / step_m) * step_m, np.nanmax(z), step_m
    ):
        kind = "index" if np.isclose(level % index_m, 0) else "contour"
        records += [
            {
                "elevation_m": float(level),
                "kind": kind,
                "geometry": shapely.LineString(line),
            }
            for line in generator.lines(level)
            if len(line) > 1
        ]
    return gpd.GeoDataFrame(records, crs=crs)


def temp_layer(path, **style):
    """A layer spec for a file under the repository."""
    return {"path": str(path), **style}


def main(
    *, extent, world_id, realisation_id, open_extent, contour_step_m, contour_index_m
):
    """Write the derived layers and the project."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = extent_suffix(extent)
    w, r = world_id, realisation_id

    model = gpd.read_parquet(urban_slope_model_path(w, extent=extent))
    realisation_file = combined_realisation_path(w, r, extent=extent)
    realisation = gpd.read_parquet(realisation_file)
    zone_outcomes = write(
        gen_zone_outcomes(model, realisation),
        f"urban-zones-outcome-w{w:03d}-r{r:03d}{suffix}.geoparquet",
    )
    polygons = gpd.GeoDataFrame(
        model[MODEL_COLUMNS], geometry=model.geometry.values, crs=model.crs
    )
    model_copy = write(
        polygons, f"urban-slope-model-w{w:03d}-polygons{suffix}.geoparquet"
    )

    pif_table = pd.read_parquet(pif_cut_fill_path(extent=extent)).reset_index()
    pips, feet = gen_pips(
        pif_table, pd.read_parquet(pif_cut_fill_pips_path(extent=extent))
    )
    pips_file = write(pips, f"pips-by-cut-fill{suffix}.geoparquet")
    feet_file = write(feet, f"pip-to-foot{suffix}.geoparquet")
    sizs = gpd.read_parquet(siz_table_path(extent=extent)).reset_index()
    spines_file = write(gen_spines(sizs, pif_table), f"pif-spines{suffix}.geoparquet")

    wall_elements = gpd.read_parquet(wall_elements_path(extent=extent))
    forced = wall_elements[wall_elements["forced"].fillna(value=False).astype(bool)]
    forced_file = write(
        forced[["wall_unit_id", "height_m", "geometry"]],
        f"forced-polygons{suffix}.geoparquet",
    )
    ground_file = ground_map_path(extent=extent)
    flat_file = write(
        gen_flatland(gpd.read_parquet(ground_file)), f"nlm-flatland{suffix}.geoparquet"
    )

    hill_file = gen_hillshade(
        dem_path(1, extent=extent), OUT_DIR / f"hillshade-1m{suffix}.tif"
    )
    contours = gen_contours(
        dem_path(3, extent=extent), step_m=contour_step_m, index_m=contour_index_m
    )
    contour_file = write(contours, f"contours-{contour_step_m:g}m{suffix}.geoparquet")

    large_file = large_realisation_path(extent=extent, realisation_id=r)
    n_large = len(gpd.read_parquet(large_file))
    ids = f"W{w:03d} R{r:03d}"
    layers = [
        temp_layer(
            zone_outcomes,
            name=f"{ids} | urban ground by zone, failed or not",
            field="outcome",
            categories=ZONE_OUTCOME_COLOUR,
            outline="match",
            width=0.1,
            checked=True,
        ),
        temp_layer(
            realisation_file,
            name=f"{ids} | realisation as written (failed ground, after absorption)",
            field="land_class",
            categories=LAND_CLASS_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            model_copy,
            name=f"W{w:03d} | step 8 median theta (PGV m/s)",
            field="theta",
            cmap="RdYlGn",
            bins=8,
            bin_mode="quantile",
            outline="match",
            width=0.1,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            model_copy,
            name=f"W{w:03d} | step 8 wall state",
            field="wall_state",
            categories=WALL_STATE_COLOUR,
            outline="match",
            width=0.1,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            zones_path(f"w{w:03d}", extent=extent),
            name=f"W{w:03d} | step 12 zones (all, by zone)",
            field="zone",
            categories=ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            pips_file,
            name="Intermediate | pips by pif cut/fill class (step 13)",
            field="cut_fill_class",
            categories=CLASS_COLOUR,
            geometry="point",
            size=0.9,
            outline="match",
            checked=True,
        ),
        temp_layer(
            feet_file,
            name="Intermediate | pip to foot of face (step 13 walk)",
            field="cut_fill_class",
            categories=CLASS_COLOUR,
            geometry="line",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            spines_file,
            name="Intermediate | pif spines by cut/fill class",
            field="cut_fill_class",
            categories=CLASS_COLOUR,
            geometry="line",
            width=0.6,
            checked=False,
        ),
        temp_layer(
            elements_path(extent=extent),
            name="Intermediate | grown elements",
            color="#c9a36b55",
            outline="#7a5a32",
            width=0.2,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            forced_file,
            name="Intermediate | forced polygons",
            color="#ad1457",
            outline="#ad1457",
            width=0.3,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            zones_path("walled", extent=extent),
            name="Scenario | zones, every unit walled",
            field="zone",
            categories=ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            zones_path("bare", extent=extent),
            name="Scenario | zones, no walls",
            field="zone",
            categories=ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            slope_units_path(extent=extent),
            name="Large | slope units (step 5)",
            color="#00000000",
            outline="#111111",
            width=0.5,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            hancox_coverage_path(r, extent=extent),
            name=f"Large | Hancox 1997 coverage R{r:03d} (in run)",
            style="cmap",
            cmap="magma_r",
            min=0,
            max=0.05,
            steps=10,
            checked=False,
        ),
        temp_layer(
            kritikos_coverage_path(r, extent=extent),
            name=f"Large | Kritikos 2015 coverage R{r:03d} (not in run)",
            style="cmap",
            cmap="magma_r",
            min=0,
            max=0.05,
            steps=10,
            checked=False,
        ),
        temp_layer(
            kritikos_hazard_path(r, extent=extent),
            name=f"Large | Kritikos 2015 relative hazard H R{r:03d}",
            style="cmap",
            cmap="viridis",
            min=0.4,
            max=1.0,
            steps=10,
            checked=False,
        ),
        temp_layer(
            flat_file,
            name="Input | NLM flatland (no large failure starts)",
            color="#4a90c255",
            outline="#1f5f99",
            width=0.3,
            geometry="polygon",
            checked=False,
        ),
        temp_layer(
            ground_file,
            name="Input | ground map (material)",
            field="material",
            categories=MATERIAL_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        temp_layer(
            contour_file,
            name=f"Input | contours {contour_step_m:g} m ({contour_index_m:g} m index)",
            field="kind",
            categories={
                "index": ["#3a3a3a", "Index"],
                "contour": ["#8c8c8c", "Contour"],
            },
            geometry="line",
            width=0.2,
            checked=False,
        ),
        temp_layer(
            slope_path(10, extent=extent),
            name="Input | slope 10 m",
            style="slope",
            checked=False,
        ),
        temp_layer(
            hill_file,
            name="Input | hillshade of the 1 m DEM",
            style="gray",
            min=0,
            max=255,
            opacity=0.45,
            checked=True,
        ),
        {"basemap": "esri_imagery", "checked": True},
    ]
    if n_large:
        layers.insert(
            1,
            {
                "path": str(large_file),
                "name": f"R{r:03d} | large failures (step 1)",
                "field": "land_class",
                "categories": LAND_CLASS_COLOUR,
                "outline": "#4e342e",
                "width": 0.4,
                "checked": True,
            },
        )
    else:
        print(f"step 1 wrote no large failures for R{r:03d}; the layer is left out")

    builder = load_builder()
    builder.run(
        {
            "title": f"Landslide chain - {extent} ({ids})",
            "out": str(OUT_DIR / f"landslide-models{suffix}.qgs"),
            "source": "local",
            "extent": list(open_extent),
            "layers": layers,
        }
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        open_extent=config.OPEN_EXTENT,
        contour_step_m=config.CONTOUR_STEP_M,
        contour_index_m=config.CONTOUR_INDEX_M,
    )
