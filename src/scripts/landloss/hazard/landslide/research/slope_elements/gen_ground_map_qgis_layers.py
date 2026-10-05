"""Write the ground map's inputs and result as layers for a QGIS project.

Clips each polygon source step 4 reads, and the ground map it makes, to the pilot and
writes them under ``temp/qgis-ground-map/`` with a spec for
``.agents/skills/making-qgis-projects/scripts/build_qgis_project.py``. Hillshade and
contours are reused from ``temp/qgis-d2-pilot/``
(``gen_pilot_qgis_layers.py``).

Run from the repository root, then build the project::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/research/slope_elements/gen_ground_map_qgis_layers.py
    uv run --frozen python .agents/skills/making-qgis-projects/scripts/build_qgis_project.py \
        temp/qgis-ground-map/spec.json
"""

import json

import geopandas as gpd
import matplotlib as mpl
from shapely.geometry import box

from landloss.io.nlm import get_nlm_flatland
from landloss.io.readers import (
    get_gwd_median_depth,
    get_nlm_geomorphology,
    get_slide_genesis,
    get_slide_interpreted_materials,
    get_wellington_urban_geology,
)
from scripts.landloss.hazard.landslide.research.slope_elements import config
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    resolve_extent,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    MODIFICATION_RESIDUAL_M,
    ground_map_path,
    polygonise_groundwater,
    polygonise_residual,
    read_raster,
    residual_path,
)
from scripts.landloss.paths import REPO_ROOT, TEMP_DIR

OUT_DIR = TEMP_DIR / "qgis-ground-map"
D2_DIR = "temp/qgis-d2-pilot"
PROJECT_PATH = "C:/Users/mami/Downloads/landloss_ground_map.qgs"
RESIDUAL_THRESHOLD_M = 1.0
ALPHA = "d0"
OUTLINE = "#4a4640"

MATERIAL_COLOURS = {
    "rock": ("#8a8070", "rock (no weathering grade mapped)"),
    "rock_uw_mw": ("#5f584c", "rock, unweathered to moderately weathered"),
    "rock_hw_cw": ("#a89c88", "rock, highly to completely weathered"),
    "rock_crushed": ("#b59a7e", "rock, crushed"),
    "colluvium": ("#c9a24e", "colluvium"),
    "fill_uncontrolled": ("#c4707b", "fill (uncontrolled)"),
    "alluvium": ("#6f9bb8", "alluvium"),
    "loess": ("#d6c150", "loess"),
    "unknown": ("#bdbdbd", "unknown"),
}
MODIFICATION_COLOURS = {
    "fill": ("#c4707b", "fill"),
    "cut": ("#d98a3d", "cut"),
    "natural": ("#9bbf8a", "natural"),
}


def palette(values):
    """One distinct colour per value, as a spec ``categories`` map."""
    colours = mpl.colormaps["tab20"].colors
    return {
        str(v): [mpl.colors.to_hex(colours[i % 20]) + ALPHA, str(v)]
        for i, v in enumerate(sorted(values))
    }


def fixed(colours):
    return {k: [colour + ALPHA, label] for k, (colour, label) in colours.items()}


def write(frame, name, area):
    path = OUT_DIR / f"{name}.gpkg"
    clipped = gpd.clip(frame.to_crs(2193), area).reset_index(drop=True)
    clipped.to_file(path, driver="GPKG")
    print(f"{name}: {len(clipped):,} features")
    return clipped


def vector(name, title, *, checked=False, **style):
    return {"path": f"temp/qgis-ground-map/{name}.gpkg", "name": title, "checked": checked, **style}


def categorised(name, title, field, categories, *, checked=False):
    return vector(
        name,
        title,
        checked=checked,
        field=field,
        outline=OUTLINE,
        width=0.15,
        categories=categories,
    )


def main(*, extent):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bbox, _ = resolve_extent(extent=extent)
    area = box(*bbox)

    materials = write(get_slide_interpreted_materials(bbox=bbox), "in-slide-materials", area)
    genesis = write(get_slide_genesis(bbox=bbox), "in-slide-genesis", area)
    geology = write(get_wellington_urban_geology(bbox=bbox), "in-geology-1-50k", area)
    landforms = write(get_nlm_geomorphology(bbox=bbox), "in-nlm-geomorphology", area)
    flatland = write(get_nlm_flatland(), "in-nlm-flatland", area)
    write(
        polygonise_groundwater(get_gwd_median_depth(), area, flatland),
        "in-nlm-groundwater-depth",
        area,
    )
    residual_file = residual_path(MODIFICATION_RESIDUAL_M, extent=extent)
    write(
        polygonise_residual(read_raster(residual_file), threshold_m=RESIDUAL_THRESHOLD_M),
        "in-residual-30m-cut-fill",
        area,
    )
    ground = write(gpd.read_parquet(ground_map_path(extent=extent)), "ground-map", area)

    geology["label"] = geology["unit_code"] + " " + geology["descriptio"].fillna("")
    geology.to_file(OUT_DIR / "in-geology-1-50k.gpkg", driver="GPKG")

    spec = {
        "title": "Ground map: inputs and result",
        "out": PROJECT_PATH,
        "source": "local",
        "extent": [1748323, 5423605, 1751191, 5425337],
        "layers": [
            {"path": f"{D2_DIR}/contours-major.gpkg", "name": "Contours 10 m", "checked": True, "color": "#3a2c1e", "width": 0.4},
            {"path": f"{D2_DIR}/contours-minor.gpkg", "name": "Contours 2 m", "checked": False, "color": "#5a4a3a99", "width": 0.15},
            categorised("ground-map", "FINAL ground map: material", "material", fixed(MATERIAL_COLOURS), checked=True),
            categorised("ground-map", "FINAL ground map: modification", "modification", fixed(MODIFICATION_COLOURS)),
            categorised("ground-map", "FINAL ground map: strength set", "strength_source", palette(ground["strength_source"].dropna().unique())),
            categorised("ground-map", "FINAL ground map: groundwater class", "gw_depth_class", palette(ground["gw_depth_class"].unique())),
            categorised("ground-map", "FINAL ground map: material source", "material_source", palette(ground["material_source"].unique())),
            categorised("ground-map", "FINAL ground map: modification source", "modification_source", palette(ground["modification_source"].unique())),
            categorised("in-slide-materials", "INPUT SLIDE interpreted materials (Type)", "Type", palette(materials["Type"].unique())),
            categorised("in-slide-genesis", "INPUT SLIDE genesis (Type)", "Type", palette(genesis["Type"].unique())),
            categorised("in-geology-1-50k", "INPUT 1:50k geology (unit and description)", "label", palette(geology["label"].unique())),
            categorised("in-nlm-geomorphology", "INPUT NLM geomorphology (l3_yp)", "l3_yp", palette(landforms["l3_yp"].unique())),
            vector("in-nlm-flatland", "INPUT NLM flatland", color="#2a78d640", outline="#2a78d6", width=0.4),
            vector("in-nlm-groundwater-depth", "INPUT NLM groundwater depth (m)", field="gw_depth_m", cmap="viridis_r", bins=6, bin_mode="equal", outline="#00000000"),
            categorised("in-residual-30m-cut-fill", "INPUT 30 m residual cut / fill (>1 m)", "modification", fixed(MODIFICATION_COLOURS)),
            {"path": str(residual_file.relative_to(REPO_ROOT)).replace("\\", "/"), "name": "INPUT 30 m cut-fill residual (m)", "checked": False, "style": "cmap", "cmap": "RdBu", "min": -5, "max": 5, "steps": 10, "opacity": 0.6},
            {"path": f"{D2_DIR}/hillshade.tif", "name": "Hillshade", "checked": True, "style": "gray", "min": 0, "max": 1, "opacity": 0.45},
            {"basemap": "esri_imagery", "checked": True},
        ],
    }
    (OUT_DIR / "spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(extent=config.PILOT_EXTENT)
