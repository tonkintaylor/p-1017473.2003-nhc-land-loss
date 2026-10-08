"""Build the retaining wall placement QGIS project from the current outputs.

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/qgis/gen_rw_qgis_project.py

Writes ``temp/qgis/wall-placement/wall-placement<suffix>.qgs`` and, beside it,
flat copies of the layers it shows (one geometry column, no list columns, so
QGIS opens each the way it is meant to be drawn):

- **every potential wall (wall unit) coloured by its probability ``p_wall``**,
  in equal bins over its range, with its prior, GNS floor and claim stages as
  attributes, and the same units by the stage that set ``p_wall``;
- world 0's draw, the exposure walls by realisation outcome, and the urban
  ground by zone, failed or not;
- the pips, pif spines and elements behind the units, and the walled and bare
  scenario zones;
- the GNS mapped walls, LINZ property boundaries, contours, the ground map and
  a 1 m hillshade.

Replaces the hand-run ``prep_qgis.py`` and spec the project was first built
from. Rerun it after ground steps 3 to 5, exposure rw step 6 or landslide step 4
reruns. The project itself is built by the ``making-qgis-projects`` skill's builder.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_gns_slide_morphology, get_nz_property_boundaries
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_draws_path,
    wall_units_path,
)
from scripts.landloss.exposure.rw.validations.qgis import config
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import (
    gns_only_path,
    siz_table_path,
)
from scripts.landloss.ground.steps.s5_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
    pif_cut_fill_pips_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.gen_wall_zones import (
    wall_elements_path,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
    urban_wall_outcome_path,
)
from scripts.landloss.hazard.landslide.validations.qgis import (
    gen_landslide_qgis_project as landslide,
)
from scripts.landloss.paths import TEMP_DIR

OUT_DIR = TEMP_DIR / "qgis" / "wall-placement"
CRS = 2193

UNIT_COLUMNS = [
    "wall_unit_id",
    "unit_source",
    "cut_fill_class",
    "height_m",
    "length_m",
    "is_siz",
    "gns_wall",
    "wall_points",
    "p_prior",
    "p_prior_basis",
    "p_floor",
    "p_floor_basis",
    "p_claims",
    "p_wall",
    "p_wall_basis",
    "claim_walls",
    "nzmm_wall",
    "on_road_frontage",
    "on_property_boundary",
    "in_exposure",
    "property_id",
]
P_WALL_BASIS_COLOUR = {
    "points": ["#3b6e8f", "Points prior (no floor or claim raised it)"],
    "gns_floor": ["#1b7f4d", "Raised to the GNS floor"],
    "gns_only": ["#111111", "GNS-only flat value"],
    "claims": ["#c62828", "Raised by a claim report count"],
}
CANDIDATE_COLOUR = {
    "siz": ["#e31a1c", "SIZ"],
    "low_height": ["#ff7f00", "Low-height wall (GNS wall, no SIZ)"],
    "none": ["#bdbdbd", "Not a candidate"],
}
WALLED_COLOUR = {
    "walled": ["#0b3c8c", "Walled"],
    "not walled": ["#f4a6a6", "Not walled"],
}
OUTCOME_COLOUR = {
    "failed_with_polygon": ["#d7191c", "Failed with polygon"],
    "standing": ["#1a9641", "Standing"],
    "absorbed": ["#fdae61", "Absorbed"],
    "superseded": ["#7b3294", "Superseded"],
    "no outcome (uninsured)": ["#9e9e9e", "Uninsured (no loss row)"],
}


def write(frame, name):
    """Write one layer beside the project, flat, and return its path."""
    frame = frame.copy()
    for column in frame.columns:
        if column == frame.geometry.name:
            continue
        if (
            frame[column]
            .map(lambda v: isinstance(v, (list, tuple, np.ndarray, dict)))
            .any()
        ):
            frame = frame.drop(columns=column)
        elif str(frame[column].dtype) in ("string", "str"):
            frame[column] = frame[column].astype(object)
    path = OUT_DIR / f"{name}.geoparquet"
    frame.to_parquet(path)
    print(f"wrote {path.name}: {len(frame):,} rows")
    return path


def gen_units(units, draws, *, world_id):
    """The wall units with their probability stages and this world's draw."""
    walled = draws.loc[draws["world_id"] == world_id].set_index("wall_unit_id")[
        "walled"
    ]
    frame = units[[c for c in UNIT_COLUMNS if c in units.columns]].copy()
    frame["walled"] = (
        frame["wall_unit_id"]
        .map(walled)
        .fillna(value=False)
        .astype(bool)
        .map({True: "walled", False: "not walled"})
    )
    return gpd.GeoDataFrame(frame, geometry=units.geometry.values, crs=units.crs)


def gen_exposure_walls(drawn, outcome):
    """This world's drawn walls with their insured status and realisation outcome."""
    walls = drawn.copy()
    walls["insured"] = np.where(walls["rw_id"].notna(), "insured", "uninsured")
    outcomes = outcome[["rw_id", "outcome"]].drop_duplicates("rw_id")
    walls = walls.merge(outcomes, on="rw_id", how="left")
    walls["outcome"] = walls["outcome"].fillna("no outcome (uninsured)")
    return walls


def layer(path, **style):
    """A layer spec for a file this script wrote or a step output."""
    return {"path": str(path), **style}


def main(
    *,
    extent,
    world_id,
    realisation_id,
    open_extent,
    contour_step_m,
    contour_index_m,
    p_wall_bins,
):
    """Write the flat layers and the project."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = extent_suffix(extent)
    w, r = world_id, realisation_id
    ids = f"W{w:03d}"

    with rasterio.open(dem_path(1, extent=extent)) as src:
        bbox = tuple(src.bounds)

    units = gpd.read_parquet(wall_units_path(extent=extent)).reset_index()
    draws = pd.read_parquet(wall_draws_path(extent=extent))
    units_file = write(
        gen_units(units, draws, world_id=w), f"wall-units-{ids.lower()}{suffix}"
    )

    model = gpd.read_parquet(urban_slope_model_path(w, extent=extent))
    realisation_file = combined_realisation_path(w, r, extent=extent)
    realisation = gpd.read_parquet(realisation_file)
    zones_file = write(
        landslide.gen_zone_outcomes(model, realisation),
        f"urban-zones-outcome-{ids.lower()}-r{r:03d}{suffix}",
    )
    model_file = write(
        gpd.GeoDataFrame(
            model[landslide.MODEL_COLUMNS],
            geometry=model.geometry.values,
            crs=model.crs,
        ),
        f"slope-model-{ids.lower()}{suffix}",
    )
    drawn = gpd.read_parquet(drawn_walls_path(w, extent=extent))
    outcome = pd.read_parquet(urban_wall_outcome_path(w, r, extent=extent))
    walls_file = write(
        gen_exposure_walls(drawn, outcome),
        f"exposure-walls-{ids.lower()}-r{r:03d}{suffix}",
    )

    pif_table = pd.read_parquet(pif_cut_fill_path(extent=extent)).reset_index()
    pips, _ = landslide.gen_pips(
        pif_table, pd.read_parquet(pif_cut_fill_pips_path(extent=extent))
    )
    sizs = gpd.read_parquet(siz_table_path(extent=extent)).reset_index()
    pips = pips.merge(sizs[["pif_id", "candidate_class"]], on="pif_id", how="left")
    pips["candidate_class"] = pips["candidate_class"].fillna("none")
    pips_file = write(pips, f"pips{suffix}")
    spines_file = write(landslide.gen_spines(sizs, pif_table), f"pif-spines{suffix}")
    elements = gpd.read_parquet(wall_elements_path(extent=extent))
    keep = ["wall_unit_id", "element_type", "height_m", "area_m2", "forced", "geometry"]
    elements_file = write(elements[keep], f"elements{suffix}")
    lines_file = write(
        elements.loc[elements["wall_unit_id"].notna(), keep], f"line-elements{suffix}"
    )

    morphology = get_gns_slide_morphology(bbox=bbox, crs=CRS, use_cache=True)
    gns = morphology[morphology["Type"] == "Retaining wall (man-made feature)"][
        ["Type", "geometry"]
    ]
    gns_file = write(gns, f"gns-walls{suffix}")
    properties = get_nz_property_boundaries(bbox=bbox, crs=CRS, use_cache=True)
    property_columns = [
        c for c in ["source_id", "title_type", "geometry"] if c in properties
    ]
    properties_file = write(properties[property_columns], f"properties{suffix}")
    contours_file = write(
        landslide.gen_contours(
            dem_path(3, extent=extent), step_m=contour_step_m, index_m=contour_index_m
        ),
        f"contours-{contour_step_m:g}m{suffix}",
    )
    hill_file = landslide.gen_hillshade(
        dem_path(1, extent=extent), OUT_DIR / f"hillshade-1m{suffix}.tif"
    )

    layers = [
        layer(
            units_file,
            name=f"{ids} | potential walls by probability (p_wall)",
            geometry="line",
            width=0.9,
            field="p_wall",
            cmap="YlOrRd",
            bins=p_wall_bins,
            bin_mode="equal",
            checked=True,
        ),
        layer(
            units_file,
            name=f"{ids} | potential walls by the stage that set p_wall",
            geometry="line",
            width=0.9,
            field="p_wall_basis",
            categories=P_WALL_BASIS_COLOUR,
            checked=False,
        ),
        layer(
            units_file,
            name=f"{ids} | potential walls drawn (walled / not walled)",
            geometry="line",
            width=0.9,
            field="walled",
            categories=WALLED_COLOUR,
            checked=False,
        ),
        layer(
            walls_file,
            name=f"{ids} R{r:03d} | exposure walls by outcome",
            geometry="line",
            width=0.8,
            field="outcome",
            categories=OUTCOME_COLOUR,
            checked=False,
        ),
        layer(
            zones_file,
            name=f"{ids} R{r:03d} | urban ground by zone, failed or not",
            field="outcome",
            categories=landslide.ZONE_OUTCOME_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            model_file,
            name=f"{ids} | slope model polygons by wall state",
            geometry="polygon",
            field="wall_state",
            categories=landslide.WALL_STATE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            zones_path(f"w{w:03d}", extent=extent),
            name=f"{ids} | zones from the drawn walls",
            field="zone",
            categories=landslide.ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            gns_only_path(extent=extent),
            name="Intermediate | GNS-only wall candidates",
            geometry="line",
            color="#ff00ff",
            width=0.6,
            checked=False,
        ),
        layer(
            spines_file,
            name="Intermediate | pif spines by cut/fill class (ground step 5)",
            geometry="line",
            width=0.6,
            field="cut_fill_class",
            categories=landslide.CLASS_COLOUR,
            checked=False,
        ),
        layer(
            pips_file,
            name="Intermediate | pips by pif cut/fill class (ground step 5)",
            geometry="point",
            size=0.6,
            field="cut_fill_class",
            categories=landslide.CLASS_COLOUR,
            outline="match",
            checked=False,
        ),
        layer(
            pips_file,
            name="Intermediate | pips by candidate class",
            geometry="point",
            size=0.6,
            field="candidate_class",
            categories=CANDIDATE_COLOUR,
            outline="match",
            checked=False,
        ),
        layer(
            elements_file,
            name="Intermediate | grown elements",
            geometry="polygon",
            color="#00000000",
            outline="#6a3d9a",
            width=0.2,
            checked=False,
        ),
        layer(
            lines_file,
            name="Intermediate | line and forced elements (GNS-only, low-height walls)",
            geometry="polygon",
            color="#ff00ff55",
            outline="#c000c0",
            width=0.4,
            checked=False,
        ),
        layer(
            zones_path("walled", extent=extent),
            name="Scenario | zones, every candidate walled",
            field="zone",
            categories=landslide.ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            zones_path("bare", extent=extent),
            name="Scenario | zones, no walls",
            field="zone",
            categories=landslide.ZONE_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            gns_file,
            name="Input | GNS mapped retaining walls",
            geometry="line",
            color="#000000",
            width=0.4,
            checked=True,
        ),
        layer(
            properties_file,
            name="Input | LINZ property boundaries",
            geometry="polygon",
            color="#00000000",
            outline="#8c8c8c",
            width=0.15,
            checked=True,
        ),
        layer(
            contours_file,
            name=f"Input | contours {contour_step_m:g} m ({contour_index_m:g} m index)",
            geometry="line",
            width=0.2,
            field="kind",
            categories={
                "index": ["#4d3319", "Index"],
                "contour": ["#a08060", "Contour"],
            },
            checked=False,
        ),
        layer(
            ground_map_path(extent=extent),
            name="Input | ground map (material)",
            field="material",
            categories=landslide.MATERIAL_COLOUR,
            outline="match",
            width=0.1,
            checked=False,
        ),
        layer(
            hill_file,
            name="Input | hillshade of the 1 m DEM",
            style="gray",
            min=0,
            max=255,
            opacity=0.35,
            checked=True,
        ),
        {"basemap": "esri_imagery", "checked": True},
    ]
    landslide.load_builder().run(
        {
            "title": f"Retaining wall placement - {extent} ({ids})",
            "out": str(OUT_DIR / f"wall-placement{suffix}.qgs"),
            "source": "local",
            "crs": "EPSG:2193",
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
        p_wall_bins=config.P_WALL_BINS,
    )
