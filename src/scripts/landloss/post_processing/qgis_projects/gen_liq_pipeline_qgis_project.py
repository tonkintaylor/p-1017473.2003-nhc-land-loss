"""Write a QGIS project that steps through the liquefaction land damage pipeline.

    uv run --frozen python src/scripts/landloss/post_processing/qgis_projects/gen_liq_pipeline_qgis_project.py

Its layers run top to bottom in the order the pipeline builds them, read bottom
up:

1. The lateral spreading free faces and the 100 m and 200 m zones round them
   (hazard step 1 and step 2).
2. The probability of each of the six land damage states, after the lateral
   spreading correction (hazard step 2).
3. The land damage state drawn per grid cell for one realisation (hazard step 3).
4. The point each insured property samples that grid at (vul step 2). The state
   is sampled once per property, at its representative point, so every property
   whose point falls in one 100 m cell takes that cell's state (T-72).
5. Each insured property's state, evacuated area and inundated share (vul
   step 2). The pipeline holds evacuated and inundated land as areas per
   property, not as polygons, so they are shown by colouring the insured land
   rather than drawing where on it the ground was lost.

The project and every file it reads are written to the liquefaction module's
folder, ``<QGIS_DIR>/hazard/liquefaction/``, on the network drive set in
``config.py``, so the team can open it and there is one copy to keep up to date.
The rasters are copied there from where the hazard steps wrote them, and the
per-property layers are written there as GeoPackages, because the vul output is
a table with no geometry and has to be joined to the insured land to be drawn. A
re-run replaces them.

It writes to the network drive, so it is run by hand. Run the hazard and vul
liquefaction steps over the same extent first; settings come from ``config.py``
beside this.
"""

import importlib.util
import shutil

import geopandas as gpd
import pandas as pd
import rasterio

from landloss.common.utils.colors import LAND_DAMAGE_STATE_COLOURS
from landloss.domain.loss_contract import LAND_ID_COLUMN
from landloss.hazard.liquefaction.land_damage import LD_STATES
from landloss.io.area_of_interest import check_extent, extent_suffix
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.hazard.liquefaction.steps.s1_free_faces.gen_liq_free_faces import (
    free_faces_path,
)
from scripts.landloss.hazard.liquefaction.steps.s2_ld_probabilities.gen_liq_ld_probabilities import (
    beta_probability_path,
    ls_zones_path,
)
from scripts.landloss.hazard.liquefaction.steps.s3_ld_states.gen_liq_ld_states import (
    ld_state_path,
)
from scripts.landloss.paths import REPO_ROOT
from scripts.landloss.post_processing.qgis_projects import config
from scripts.landloss.vul.liquefaction.land.steps.s2_liq_land_damage.gen_liq_land_damage import (
    EVACUATED_AREA_COLUMN,
    HAZARD_STATE_COLUMN,
    INUNDATED_AREA_COLUMN,
    ON_GRID_COLUMN,
    liq_land_damage_path,
)

BUILDER = (
    REPO_ROOT / ".agents/skills/making-qgis-projects/scripts/build_qgis_project.py"
)

INUNDATED_SHARE_COLUMN = "inundated_share"
STATE_CATEGORIES = {
    str(state): [colour, label]
    for state, (colour, label) in LAND_DAMAGE_STATE_COLOURS.items()
}
ZONE_CATEGORIES = {
    "near": ["#d7301f60", "Lateral spreading, within 100 m"],
    "middle": ["#f8951d40", "Lateral spreading, 100 to 200 m"],
}
OFF_GRID_COLOUR = "#bdbdbd60"
OUTLINE = "#4a4640"


def load_builder():
    """Import the QGIS project builder from the making-qgis-projects skill.

    It is a script rather than a package, so it is loaded from its file instead
    of being copied into the repository.
    """
    spec = importlib.util.spec_from_file_location("build_qgis_project", BUILDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project_dir(qgis_dir):
    """Return the liquefaction module's folder, which the project is written to.

    Every file name carries the extent, so a pilot and a full build sit side by
    side in it.
    """
    return qgis_dir / "hazard" / "liquefaction"


def gather(source, *, folder):
    """Copy a file the hazard steps wrote into the project's folder.

    Returns:
        The path of the copy, which the project reads.
    """
    target = folder / source.name
    shutil.copy2(source, target)
    return target


def write_property_layers(*, extent, realisation_id, folder):
    """Join the vul output to the insured land and write it for QGIS.

    Returns:
        The paths of the properties on the liquefaction grid, those off it, and
        the points the on-grid properties sampled the state raster at.
    """
    suffix = extent_suffix(extent)
    insured = gpd.read_parquet(insured_land_path(extent=extent))
    damage = pd.read_parquet(liq_land_damage_path(realisation_id, extent=extent))
    columns = [
        LAND_ID_COLUMN,
        HAZARD_STATE_COLUMN,
        "state_name",
        ON_GRID_COLUMN,
        EVACUATED_AREA_COLUMN,
        INUNDATED_AREA_COLUMN,
        "damaged_area_m2",
        "cost_nzd",
        "area_cost_nzd",
    ]
    properties = insured[[LAND_ID_COLUMN, "area_m2", "geometry"]].merge(
        damage[columns], on=LAND_ID_COLUMN, how="left", validate="one_to_one"
    )
    properties[INUNDATED_SHARE_COLUMN] = (
        properties[INUNDATED_AREA_COLUMN] / properties["area_m2"]
    )
    on_grid = properties[ON_GRID_COLUMN].fillna(False).astype(bool)

    names = {
        "on_grid": f"properties-on-liq-grid-r{realisation_id:03d}{suffix}.gpkg",
        "off_grid": f"properties-off-liq-grid{suffix}.gpkg",
        "points": f"sample-points-r{realisation_id:03d}{suffix}.gpkg",
    }
    paths = {key: folder / name for key, name in names.items()}
    properties.loc[on_grid].to_file(paths["on_grid"], driver="GPKG")
    properties.loc[~on_grid, [LAND_ID_COLUMN, "geometry"]].to_file(
        paths["off_grid"], driver="GPKG"
    )
    points = properties.loc[on_grid, [LAND_ID_COLUMN, HAZARD_STATE_COLUMN]].copy()
    points = gpd.GeoDataFrame(
        points,
        geometry=properties.loc[on_grid].geometry.representative_point(),
        crs=properties.crs,
    )
    points.to_file(paths["points"], driver="GPKG")
    print(
        f"{int(on_grid.sum()):,} properties on the liquefaction grid and "
        f"{int((~on_grid).sum()):,} off it"
    )
    return paths


def build_spec(*, extent, realisation_id, files, folder):
    """Compose the builder spec, top of the legend first.

    Building it copies the hazard rasters and layers into the project's folder.
    """
    state_raster = ld_state_path(realisation_id, extent=extent)
    with rasterio.open(state_raster) as raster:
        bounds = list(raster.bounds)

    def stored(path):
        return {"path": str(path)}

    def shared(source):
        return stored(gather(source, folder=folder))

    def property_layer(name, **style):
        return {
            **stored(files["on_grid"]),
            "name": name,
            "checked": False,
            "outline": OUTLINE,
            "width": 0.1,
            **style,
        }

    probabilities = [
        {
            **shared(beta_probability_path(state, extent=extent)),
            "name": f"2. P({number} {state})",
            "checked": False,
            "style": "cmap",
            "cmap": "magma_r",
            "min": 0,
            "max": 0.5,
            "steps": 10,
            "opacity": 0.8,
        }
        for number, state in enumerate(LD_STATES, start=1)
    ]
    layers = [
        property_layer(
            "5c. Inundated land, share of insured land",
            field=INUNDATED_SHARE_COLUMN,
            cmap="Blues",
            bins=5,
            bin_mode="equal",
        ),
        property_layer(
            "5b. Evacuated land (m²)",
            field=EVACUATED_AREA_COLUMN,
            cmap="Reds",
            bins=5,
            bin_mode="equal",
        ),
        property_layer(
            "5a. Property land damage state (sampled)",
            field=HAZARD_STATE_COLUMN,
            categories=STATE_CATEGORIES,
            checked=True,
        ),
        {
            **stored(files["off_grid"]),
            "name": "5. Properties off the liquefaction grid",
            "checked": True,
            "color": OFF_GRID_COLOUR,
            "outline": OUTLINE,
            "width": 0.1,
        },
        {
            **stored(files["points"]),
            "name": "4. Point each property samples the state at",
            "checked": False,
            "field": HAZARD_STATE_COLUMN,
            "categories": STATE_CATEGORIES,
            "outline": OUTLINE,
            "size": 1.6,
        },
        {
            **shared(state_raster),
            "name": f"3. Land damage state drawn per cell (r{realisation_id:03d})",
            "checked": True,
            "style": "classes",
            "classes": STATE_CATEGORIES,
            "opacity": 0.6,
        },
        *reversed(probabilities),
        {
            **shared(ls_zones_path(extent=extent)),
            "name": "1b. Lateral spreading zones",
            "checked": False,
            "field": "zone_name",
            "categories": ZONE_CATEGORIES,
            "outline": "#00000000",
        },
        {
            **shared(free_faces_path(extent)),
            "name": "1a. Lateral spreading free faces",
            "checked": True,
            "color": "#1f5fa8",
            "width": 0.8,
        },
        {"basemap": "esri_imagery", "checked": True},
    ]
    project = folder / f"liq-pipeline{extent_suffix(extent)}.qgs"
    return {
        "title": "Liquefaction land damage pipeline",
        "out": str(project),
        "source": "local",
        "extent": bounds,
        "layers": layers,
    }


def main(*, extent, realisation_id, qgis_dir):
    """Write the per-property layers and build the project over them."""
    check_extent(extent)
    folder = project_dir(qgis_dir)
    folder.mkdir(parents=True, exist_ok=True)
    files = write_property_layers(
        extent=extent, realisation_id=realisation_id, folder=folder
    )
    spec = build_spec(
        extent=extent, realisation_id=realisation_id, files=files, folder=folder
    )
    load_builder().run(spec)


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        realisation_id=config.REALISATION_ID,
        qgis_dir=config.QGIS_DIR,
    )
