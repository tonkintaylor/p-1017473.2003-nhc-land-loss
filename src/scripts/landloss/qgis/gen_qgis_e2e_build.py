"""Build the end-to-end QGIS project: one run's hazard, exposure, vul and cost.

    uv run --frozen python src/scripts/landloss/qgis/gen_qgis_e2e_build.py

Writes ``temp/qgis/e2e_build/e2e_build<suffix>.qgs`` for one extent, world and
realisation (``config.py``), and beside it the few layers that have to be
derived for QGIS to draw them:

- the cost layers: the loss module's settlement table per claim, joined to the
  claim's insured land, one file per cost and only the claims with that cost;
- every urban slope polygon's potential evacuated ground, coloured by its
  probability of triggering in this earthquake. Landslide step 6 keeps
  ``p_fail`` only for the polygons it draws as failed, so it is evaluated here
  for all of them with that step's own functions (``sample_pgv`` at the
  representative point and ``lognormal_failure_probability`` on the landslide
  step 5 ``theta`` and ``beta``);
- the landslide step 5 polygons with one geometry column (QGIS takes the first
  of the model file's five, which is points);
- the vul land table split to the properties with evacuated or inundated
  ground, so its bands spread over the damaged ones;
- 5 m contours of the 3 m DEM.

Every other layer points at the file its step wrote, through that step's own
path function. Set ``RESULTS_DIR`` in ``config.py`` to build over a copy of a
run's outputs instead: each layer is then the file of the same name in that
folder, and the project is written into it with its derived layers in
``qgis/``. The legend runs Cost, Vul, Hazard, Ground model, Exposure and
Context, top down, over Esri satellite imagery. Run the whole pipeline
(``gen_all.py``) and the loss module (``loss/gen_loss.py``) for the extent
first; a missing output is skipped with a warning, never built here.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd

from landloss.hazard.landslide.urban import realisation as urban
from landloss.hazard.landslide.urban.fragility import lognormal_failure_probability
from landloss.io.area_of_interest import extent_suffix, get_area_of_interest
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    driveway_path,
    insured_land_path,
    land_value_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_probability import (
    wall_probability_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
    slope_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997.gen_hancox_1997_coverage import (
    coverage_path as hancox_coverage_path,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility.gen_urban_slope_fragility import (
    urban_slope_model_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.hazard.landslide.validations.qgis import (
    gen_landslide_qgis_project as landslide,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    beta_probability_path,
    ls_zones_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.hazard.shaking.steps.s2_site_class.gen_site_class import (
    site_class_path,
)
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation.gen_pga_realisations import (
    pga_path,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation.gen_pgv_realisations import (
    pgv_path,
)
from scripts.landloss.loss.steps.s1_settlement.s1_gen_settlement import (
    settlement_path,
)
from scripts.landloss.paths import TEMP_DIR
from scripts.landloss.qgis import config
from scripts.landloss.vul.steps.s10_property_damage.gen_property_damage import (
    world_loss_input_path,
)

OUT_DIR = TEMP_DIR / "qgis" / "e2e_build"
NZTM = 2193

# The NZD a claim's cost layers are banded in, the same in every build so two
# extents or two runs read on one legend.
COST_BREAKS = [0, 5e3, 1e4, 2e4, 5e4, 1e5, 2e5, 5e5, 1e6, 5e6]
# The probability bands a polygon's chance of triggering is read on.
P_FAIL_BREAKS = [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0]

# What each cost layer shows, from the loss module's settlement table. The
# landslide cost is the land repair and the spoil removal, the two costs loss
# books against landslide ground; the wall cost is shown on its own because a
# wall can be replaced after shaking alone.
COST_LAYERS = [
    (
        "settlement_incl_gst_nzd",
        "Cost · total settlement incl GST (NZD per claim)",
        True,
    ),
    (
        "repair_cost_incl_gst_nzd",
        "Cost · total repair cost incl GST (NZD per claim)",
        False,
    ),
    (
        "landslide_cost_incl_gst_nzd",
        "Cost · landslide: land repair + spoil removal incl GST",
        False,
    ),
    ("wall_repair_cost_incl_gst_nzd", "Cost · retaining wall repair incl GST", False),
    (
        "liquefaction_repair_cost_incl_gst_nzd",
        "Cost · liquefaction land repair incl GST",
        False,
    ),
]
LANDSLIDE_COSTS = ["land_repair_cost_incl_gst_nzd", "spoil_removal_cost_incl_gst_nzd"]

WALL_TYPE_COLOUR = {
    "brick_rock": ["#6d4c41", "Brick or rock masonry"],
    "reinforced_concrete_pre_1992": [
        "#546e7a",
        "Reinforced concrete, before July 1992",
    ],
    "crib_gabion": ["#ef6c00", "Crib or gabion"],
    "timber_pole_pre_1992": ["#c62828", "Timber pole, before July 1992"],
    "concrete_block": ["#1565c0", "Concrete block"],
    "timber_pole_post_1992": ["#2e7d32", "Timber pole, July 1992 on"],
    "garden_timber": ["#f9a825", "Garden timber"],
    "reinforced_concrete_post_1992": ["#6a1b9a", "Reinforced concrete, July 1992 on"],
}
LD_STATE_CLASSES = {
    "1": ["#3AB04A", "1 None observed"],
    "2": ["#A6D96A", "2 Minor"],
    "3": ["#FEE900", "3 Moderate"],
    "4": ["#F8951D", "4 Major"],
    "5": ["#D7301F", "5 Severe"],
    "6": ["#9D1C1F", "6 Very severe"],
}
SITE_CLASSES = {
    "2": ["#1a9850", "Class 2"],
    "3": ["#91cf60", "Class 3"],
    "4": ["#fee08b", "Class 4"],
    "5": ["#fc8d59", "Class 5"],
    "6": ["#d73027", "Class 6"],
}
CONTOUR_COLOUR = {
    "index": ["#ffffff", "Index contour"],
    "contour": ["#e8e2d4", "Contour"],
}
PROPERTY_OUTLINE = {"outline": "#55555580", "width": 0.1}


class Layout:
    """Where the layers are read from and where the project is written.

    With no results folder, every layer is the file its step wrote and the
    project goes in ``OUT_DIR``. With one, a copy of a run's outputs such as
    ``U:/<user>/land-loss/results/porirua``, each layer is the file of the same
    name anywhere under it, and the project goes in the folder itself with its
    derived layers in ``qgis/`` beside it.
    """

    def __init__(self, results_dir):
        self.results_dir = None if results_dir is None else Path(results_dir)
        if self.results_dir is None:
            self.project_dir = self.derived_dir = OUT_DIR
            self._files = {}
        else:
            self.project_dir = self.results_dir
            self.derived_dir = self.results_dir / "qgis"
            self._files = {
                f.name: f for f in self.results_dir.rglob("*") if f.is_file()
            }

    def find(self, path):
        """The layer a step's path function names, in this layout."""
        if self.results_dir is None:
            return path
        return self._files.get(path.name, self.results_dir / path.name)

    def write(self, frame, name):
        """Write one derived layer beside the project and return its path."""
        path = self.derived_dir / name
        frame.to_parquet(path)
        print(f"wrote {path}: {len(frame):,} rows")
        return path


def present(path):
    """Whether a step's output is there; a missing one is reported, not built."""
    if path.exists():
        return True
    print(f"WARNING: {path} is missing, so its layer is left out")
    return False


def gen_claim_costs(settlement, insured_land):
    """The settlement table on each claim's insured land, one row per claim."""
    land = insured_land[["claim_id", "geometry"]].dissolve(by="claim_id")
    costs = settlement.assign(
        landslide_cost_incl_gst_nzd=settlement[LANDSLIDE_COSTS].sum(axis=1)
    )
    return land.join(costs.set_index("claim_id"), how="inner").reset_index()


def gen_trigger_probability(model, pgv_file):
    """Each landslide step 5 polygon's evacuated ground with its trigger probability.

    The same evaluation landslide step 6 makes before it draws: PGV at the
    polygon's representative point, through the polygon's lognormal curve.
    """
    pgv = urban.sample_pgv(gpd.GeoSeries(model[urban.REP_POINT_COLUMN]), pgv_file)
    p_fail = lognormal_failure_probability(
        pgv.reindex(model.index).to_numpy(dtype=float),
        model["theta"].to_numpy(dtype=float),
        model["beta"].to_numpy(dtype=float),
    )
    frame = model[["slope_id", "wall_state", "wall_type", "theta", "beta"]].assign(
        pgv_m_s=pgv.reindex(model.index).to_numpy(dtype=float), p_fail=p_fail
    )
    return gpd.GeoDataFrame(
        frame, geometry=gpd.GeoSeries(model["evacuated"]).values, crs=model.crs
    )


def cost_layers(claims, suffix, layout):
    """One layer per cost, each holding only the claims with that cost."""
    layers = []
    for column, name, checked in COST_LAYERS:
        some = claims[claims[column] > 0]
        file = layout.write(
            some, f"cost-{column.removesuffix('_incl_gst_nzd')}{suffix}.geoparquet"
        )
        layers.append(
            {
                "path": str(file),
                "name": f"{name} · {len(some):,} claims, total ${some[column].sum() / 1e6:,.1f}M",
                "field": column,
                "cmap": "YlOrRd",
                "breaks": COST_BREAKS,
                "label_decimals": 0,
                "checked": checked,
                **PROPERTY_OUTLINE,
            }
        )
    return layers


def vul_layers(land_file, rw_file, suffix, layout):
    """The vul contract tables: walls replaced, and the damage per property."""
    layers = []
    if present(rw_file):
        layers.append(
            {
                "path": str(rw_file),
                "name": "Vul · insured walls damaged by shaking",
                "geometry": "line",
                "field": "is_damaged_by_shaking",
                "categories": {
                    "true": ["#c62828", "Replaced (failed with its polygon)"],
                    "false": ["#1b7f4d", "Not damaged by shaking"],
                },
                "width": 1.2,
                "checked": False,
            }
        )
    if not present(land_file):
        return layers
    land = gpd.read_parquet(land_file)
    for column, label, cmap in [
        ("evacuated_area", "evacuated insured area (m²)", "OrRd"),
        ("inundated_insured_area", "inundated insured area (m²)", "PuBu"),
    ]:
        hit = land[land[column] > 0]
        file = layout.write(hit, f"vul-{column}{suffix}.geoparquet")
        layers.append(
            {
                "path": str(file),
                "name": f"Vul · landslide {label}, {len(hit):,} properties",
                "field": column,
                "cmap": cmap,
                "bins": 8,
                "bin_mode": "quantile",
                "checked": False,
                **PROPERTY_OUTLINE,
            }
        )
    layers.append(
        {
            "path": str(land_file),
            "name": "Vul · liquefaction land damage state per property",
            "field": "Liq_LD_state",
            "categories": "land_damage_state",
            "checked": False,
            **PROPERTY_OUTLINE,
        }
    )
    return layers


def hazard_layers(*, extent, world_id, realisation_id, suffix, layout):
    """The landslide, liquefaction and shaking layers of one earthquake."""
    w, r = world_id, realisation_id
    layers = []
    realisation = layout.find(combined_realisation_path(w, r, extent=extent))
    if present(realisation):
        layers.append(
            {
                "path": str(realisation),
                "name": "Hazard · landslide realisation (urban + large)",
                "field": "land_class",
                "categories": "land_class",
                "outline": "match",
                "width": 0.2,
                "checked": True,
            }
        )
    model_file = layout.find(urban_slope_model_path(w, extent=extent))
    if present(model_file) and present(layout.find(pgv_path(r, extent=extent))):
        model = gpd.read_parquet(model_file)
        trigger = layout.write(
            gen_trigger_probability(model, layout.find(pgv_path(r, extent=extent))),
            f"urban-trigger-probability-w{w:03d}-r{r:03d}{suffix}.geoparquet",
        )
        polygons = gpd.GeoDataFrame(
            model[landslide.MODEL_COLUMNS],
            geometry=model.geometry.values,
            crs=model.crs,
        )
        model_copy = layout.write(
            polygons, f"urban-slope-model-w{w:03d}-polygons{suffix}.geoparquet"
        )
        layers += [
            {
                "path": str(trigger),
                "name": "Hazard · urban potential evacuated ground by probability of triggering (this earthquake)",
                "field": "p_fail",
                "cmap": "YlOrRd",
                "breaks": P_FAIL_BREAKS,
                "outline": "#00000000",
                "checked": False,
            },
            {
                "path": str(model_copy),
                "name": "Hazard · urban slope fragility median θ (PGV m/s; red fails at less shaking)",
                "field": "theta",
                "cmap": "RdYlGn",
                "bins": 8,
                "bin_mode": "quantile",
                "outline": "#00000000",
                "checked": False,
            },
        ]
    rasters = [
        (
            layout.find(hancox_coverage_path(r, extent=extent)),
            "Hazard · large failures: probability a point fails (Hancox 1997 areal coverage)",
            {"style": "eil_probability"},
        ),
        (
            layout.find(beta_probability_path("Minor", extent=extent)),
            "Hazard · liquefaction P(land damage state 2, minor), 100 m cells",
            {"style": "cmap", "cmap": "YlGnBu", "min": 0, "max": 0.5, "steps": 10},
        ),
        (
            layout.find(beta_probability_path("Moderate", extent=extent)),
            "Hazard · liquefaction P(land damage state 3, moderate), 100 m cells",
            {"style": "cmap", "cmap": "YlOrBr", "min": 0, "max": 0.5, "steps": 10},
        ),
        (
            layout.find(ld_state_path(r, extent=extent)),
            "Hazard · liquefaction land damage state drawn (100 m)",
            {"style": "classes", "classes": LD_STATE_CLASSES},
        ),
    ]
    layers += [
        {"path": str(path), "name": name, "checked": False, **style}
        for path, name, style in rasters
        if present(path)
    ]
    zones = layout.find(ls_zones_path(extent=extent))
    if present(zones):
        layers.append(
            {
                "path": str(zones),
                "name": "Hazard · lateral spread zones",
                "color": "#7b1fa255",
                "outline": "#7b1fa2",
                "width": 0.6,
                "checked": False,
            }
        )
    shaking = [
        (
            layout.find(pgv_path(r, extent=extent)),
            "Hazard · PGV (m/s)",
            {"style": "cmap", "cmap": "viridis", "min": 0.5, "max": 2.5, "steps": 8},
        ),
        (
            layout.find(pga_path(r, extent=extent)),
            "Hazard · PGA (g)",
            {"style": "cmap", "cmap": "viridis", "min": 0.5, "max": 2.5, "steps": 8},
        ),
        (
            layout.find(site_class_path(extent=extent)),
            "Hazard · TS1170.5 site class (100 m)",
            {"style": "classes", "classes": SITE_CLASSES},
        ),
    ]
    layers += [
        {"path": str(path), "name": name, "checked": False, **style}
        for path, name, style in shaking
        if present(path)
    ]
    return layers


def ground_layers(extent, layout):
    """The ground model: material and groundwater depth."""
    ground = layout.find(ground_map_path(extent=extent))
    if not present(ground):
        return []
    return [
        {
            "path": str(ground),
            "name": "Ground model · material",
            "field": "material",
            "categories": landslide.MATERIAL_COLOUR,
            "outline": "#00000000",
            "checked": False,
        },
        {
            "path": str(ground),
            "name": "Ground model · groundwater depth (m)",
            "field": "gw_depth_m",
            "cmap": "Blues_r",
            "bins": 6,
            "bin_mode": "quantile",
            "outline": "#00000000",
            "checked": False,
        },
    ]


def exposure_layers(*, extent, world_id, layout):
    """The walls, the insured land and the values on it."""
    specs = [
        (
            layout.find(wall_population_path(world_id, extent=extent)),
            {
                "name": f"Exposure · insured retaining walls by type (w{world_id:03d})",
                "geometry": "line",
                "field": "wall_type",
                "categories": WALL_TYPE_COLOUR,
                "width": 1.2,
            },
        ),
        (
            layout.find(wall_probability_path(extent=extent)),
            {
                "name": "Exposure · wall candidates by p_wall",
                "geometry": "line",
                "field": "p_wall",
                "cmap": "plasma",
                "bins": 6,
                "bin_mode": "quantile",
                "width": 0.8,
            },
        ),
        (
            layout.find(insured_land_path(extent=extent)),
            {
                "name": "Exposure · insured land by building footprint (m²)",
                "field": "footprint_area_m2",
                "cmap": "turbo",
                "bins": 8,
                "bin_mode": "quantile",
                "outline": "#ffffff80",
                "width": 0.1,
            },
        ),
        (
            layout.find(land_value_path(extent=extent)),
            {
                "name": "Exposure · address land value (NZD)",
                "geometry": "point",
                "field": "land_value_nzd",
                "cmap": "viridis",
                "bins": 7,
                "bin_mode": "quantile",
                "size": 1.6,
            },
        ),
        (
            layout.find(driveway_path(extent=extent)),
            {
                "name": "Exposure · driveways",
                "color": "#9e9e9e",
                "outline": "#616161",
                "width": 0.6,
            },
        ),
    ]
    return [
        {"path": str(path), "checked": False, **style}
        for path, style in specs
        if present(path)
    ]


def context_layers(*, extent, suffix, contour_step_m, contour_index_m, layout):
    """Contours, slope and the DEM, over satellite imagery."""
    dem3 = layout.find(dem_path(3, extent=extent))
    layers = []
    if present(dem3):
        contours = layout.write(
            landslide.gen_contours(
                dem3, step_m=contour_step_m, index_m=contour_index_m
            ),
            f"contours-{contour_step_m:g}m{suffix}.geoparquet",
        )
        layers += [
            {
                "path": str(contours),
                "name": f"Context · contours {contour_step_m:g} m, index {contour_index_m:g} m",
                "geometry": "line",
                "field": "kind",
                "categories": CONTOUR_COLOUR,
                "width": 0.25,
                "checked": True,
            },
            {
                "path": str(dem3),
                "name": "Context · DEM 3 m (m)",
                "style": "gray",
                "min": 0,
                "max": 350,
                "opacity": 0.5,
                "checked": False,
            },
        ]
    slope = layout.find(slope_path(3, extent=extent))
    if present(slope):
        layers.insert(
            1,
            {
                "path": str(slope),
                "name": "Context · slope 3 m (degrees)",
                "style": "slope",
                "checked": False,
            },
        )
    return [*layers, {"basemap": "esri_imagery", "checked": True}]


def main(
    *, extent, world_id, realisation_id, contour_step_m, contour_index_m, results_dir
):
    """Write the derived layers and the project."""
    layout = Layout(results_dir)
    layout.derived_dir.mkdir(parents=True, exist_ok=True)
    suffix = extent_suffix(extent)
    w, r = world_id, realisation_id

    layers = []
    settlement_file = layout.find(settlement_path(w, r, extent=extent))
    land_file = layout.find(insured_land_path(extent=extent))
    if present(settlement_file) and present(land_file):
        claims = gen_claim_costs(
            pd.read_parquet(settlement_file), gpd.read_parquet(land_file)
        )
        layers += cost_layers(claims, suffix, layout)
    else:
        print("WARNING: run loss/gen_loss.py for this extent to get the cost layers")
    layers += vul_layers(
        layout.find(world_loss_input_path("land", w, r, extent=extent)),
        layout.find(world_loss_input_path("rw", w, r, extent=extent)),
        suffix,
        layout,
    )
    layers += hazard_layers(
        extent=extent, world_id=w, realisation_id=r, suffix=suffix, layout=layout
    )
    layers += ground_layers(extent, layout)
    layers += exposure_layers(extent=extent, world_id=w, layout=layout)
    layers += context_layers(
        extent=extent,
        suffix=suffix,
        contour_step_m=contour_step_m,
        contour_index_m=contour_index_m,
        layout=layout,
    )

    area = get_area_of_interest(extent)
    spec = {
        "title": f"End-to-end build - {extent} (w{w:03d} r{r:03d})",
        "out": str(layout.project_dir / f"e2e_build{suffix}.qgs"),
        "source": "local",
        "crs": f"EPSG:{NZTM}",
        "layers": layers,
    }
    if area is not None:
        spec["extent"] = list(area.bbox(NZTM))
    landslide.load_builder().run(spec)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        world_id=config.WORLD_ID,
        realisation_id=config.REALISATION_ID,
        contour_step_m=config.CONTOUR_STEP_M,
        contour_index_m=config.CONTOUR_INDEX_M,
        results_dir=config.RESULTS_DIR,
    )
