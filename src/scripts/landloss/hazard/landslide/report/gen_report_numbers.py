"""Write the numbers the landslide damage appendix quotes.

    uv run --frozen python src/scripts/landloss/hazard/landslide/report/gen_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has four parts:

- ``meta``: when and from which commit it was written, and the date each
  territorial authority's combined realisation was written.
- ``settings``: the scenario, the Hancox and Marc et al. relationships, how
  large landslides are sized and placed, the Kingsbury rating, the runout rules
  and the fragility curves of urban slopes and walls, read from the constants
  and committed assets that set them.
- ``study_area``: over the four territorial authorities, the landslides of
  realisation 0 by population and land class, the walls they fail by type, and
  the insured land they damage.
- ``by_authority``: the same counts for each territorial authority.

Each authority's run covers its bounding box, which takes in the edges of its
neighbours, so a landslide, wall or property is counted only in the authority
its representative point lies in, and only from that authority's own run.
Reads the outputs under ``temp/`` and the committed assets only, never the T:
drive. Written to ``report/hazard/landslide/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from landloss.domain import constants
from landloss.domain.loss_contract import LAND_ID_COLUMN
from landloss.hazard.landslide import geometry, slope_polygons, susceptibility
from landloss.hazard.landslide.models.hancox_1997 import relationships as hancox
from landloss.hazard.landslide.urban import fragility, wall_type_fragility
from landloss.io import ASSETS_DIR
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from scripts.landloss.exposure.land.steps.s5_insured_land_extent.gen_insured_land import (
    insured_land_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    wall_population_path,
)
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997 import config as s2_config
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997.gen_hancox_1997_coverage import (
    marc_event_total_area_km2,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    config as s3_config,
)
from scripts.landloss.hazard.landslide.steps.s3_landslide_realisation import (
    s1_simulate_landslides as large,
)
from scripts.landloss.hazard.landslide.steps.s5_urban_slope_fragility import (
    config as s5_config,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_realisation.gen_urban_slope_realisation import (
    combined_realisation_path,
)
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPORT_DIR
from scripts.landloss.vul.landslide.land.steps.s3_landslide_land_damage.gen_landslide_land_damage import (
    landslide_land_damage_path,
)
from scripts.landloss.vul.landslide.rw.steps.s11_wall_landslide_damage.gen_wall_landslide_damage import (
    wall_landslide_damage_path,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "hazard" / "landslide" / "tab" / "report-numbers.yaml"
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
WORLD_ID = 0
REALISATION_ID = 0
M2_PER_KM2 = 1_000_000.0
HECTARE_M2 = 10_000.0


def records(path):
    """Return a CSV's rows as plain dicts."""
    return pd.read_csv(path).to_dict(orient="records")


def settings():
    """Return the values the landslides are drawn and damage set with."""
    mw = s2_config.SCENARIO_MW
    marc_total = marc_event_total_area_km2(
        mw=mw,
        r0_km=s2_config.MARC_R0_KM,
        fault_type=s2_config.MARC_FAULT_TYPE,
        onshore_fraction=s2_config.MARC_ONSHORE_FRACTION,
        modal_slope_deg=s2_config.MARC_MODAL_SLOPE_DEG,
        a_topo=s2_config.MARC_A_TOPO,
    )
    wall_curves = pd.read_csv(wall_type_fragility.WALL_TYPE_FRAGILITY_PATH)
    labels = pd.read_csv(ASSETS_DIR / "retaining-wall-types.csv")
    wall_curves = wall_curves.merge(labels[["wall_type", "label"]], on="wall_type")
    return {
        "scenario_mw": mw,
        "site_distance_km": constants.BETA_SITE_DISTANCE_KM,
        "mm_threshold": hancox.MM_THRESHOLD_WELLINGTON,
        "hancox_area": {"slope": hancox.AREA_SLOPE, "intercept": hancox.AREA_INTERCEPT},
        "hancox_area_affected_km2": round(float(hancox.area_affected_km2(mw)), 0),
        "hancox_distance": {
            "slope": hancox.DISTANCE_SLOPE,
            "intercept": hancox.DISTANCE_INTERCEPT,
        },
        "hancox_distance_km": round(
            10.0 ** (hancox.DISTANCE_SLOPE * mw + hancox.DISTANCE_INTERCEPT), 0
        ),
        "slope_class_edges_deg": list(hancox.SLOPE_CLASS_EDGES_DEG),
        "slope_shares_printed": dict(hancox.SLOPE_SHARES_PRINTED),
        "slope_shares": dict(hancox.SLOPE_SHARES),
        "marc": {
            "r0_km": s2_config.MARC_R0_KM,
            "fault_type": s2_config.MARC_FAULT_TYPE,
            "modal_slope_deg": s2_config.MARC_MODAL_SLOPE_DEG,
            "share_factor": s2_config.BETA_MARC_SHARE_FACTOR,
            "event_total_km2": round(float(marc_total), 1),
        },
        "large": {
            "min_source_area_m2": s3_config.LARGE_MIN_SOURCE_AREA_M2,
            "max_source_area_m2": large.MAX_SOURCE_AREA_M2,
            "size_exponent": large.SIZE_EXPONENT,
            "aspect_ratio": s3_config.SOURCE_ASPECT_RATIO,
            "crest_weight": s3_config.CREST_WEIGHT,
            "min_displacement_m": large.MIN_DISPLACEMENT_M,
            "max_displacement_m": large.MAX_DISPLACEMENT_M,
            "min_displacement_slope_deg": large.MIN_DISPLACEMENT_SLOPE_DEG,
            "max_displacement_slope_deg": large.MAX_DISPLACEMENT_SLOPE_DEG,
            "volume_alpha": geometry.ALPHA,
            "volume_gamma": geometry.GAMMA,
        },
        "kingsbury": {
            "weights": {
                "slope": susceptibility.SLOPE_ANGLE_WEIGHT,
                "modification": susceptibility.SLOPE_MODIFICATION_WEIGHT,
                "height": susceptibility.SLOPE_HEIGHT_WEIGHT,
                "geology": susceptibility.GEOLOGY_WEIGHT,
                "landslides": susceptibility.LANDSLIDE_WEIGHT,
                "groundwater": susceptibility.GROUNDWATER_WEIGHT,
            },
            "max_rating": susceptibility.MAX_RATING,
            "zone_breaks": list(susceptibility.ZONE_BREAKS),
        },
        "runout": {
            "cut_coefficient": slope_polygons.CUT_REACH_COEFFICIENT,
            "cut_exponent": slope_polygons.CUT_REACH_EXPONENT,
            "downslope_slope": slope_polygons.DOWNSLOPE_REACH_SLOPE,
            "downslope_intercept": slope_polygons.DOWNSLOPE_REACH_INTERCEPT,
            "steep_downslope_deg": slope_polygons.BETA_STEEP_DOWNSLOPE_DEG,
            "max_runout_h": [
                slope_polygons.BETA_MAX_RUNOUT_H_FLAT,
                slope_polygons.BETA_MAX_RUNOUT_H_MODERATE,
                slope_polygons.BETA_MAX_RUNOUT_H_STEEP,
            ],
            "steep_runout_downslope_deg": slope_polygons.BETA_STEEP_RUNOUT_DOWNSLOPE_DEG,
            "min_deposit_depth_m": slope_polygons.BETA_MIN_DEPOSIT_DEPTH_M,
            "seismic_runout_m": {
                int(k): v for k, v in slope_polygons.BETA_SEISMIC_RUNOUT_M.items()
            },
            "repose_angle_deg": slope_polygons.BETA_REPOSE_ANGLE_DEG,
            "min_evacuated_width_h": slope_polygons.BETA_MIN_EVACUATED_WIDTH_H,
            "min_evacuated_width_m": slope_polygons.BETA_MIN_EVACUATED_WIDTH_M,
        },
        "fragility": {
            "topographic_amplification": constants.TOPOGRAPHIC_AMPLIFICATION,
            "urban_rate": s5_config.URBAN_RATE,
            "localised_points": records(fragility.LOCALISED_FRAGILITY_PATH),
            "tall_wall_m": wall_type_fragility.HEIGHT_CLASS_SPLIT_M,
            "tall_factor": wall_type_fragility.TALL_HEIGHT_FACTOR,
            "fill_factor": wall_type_fragility.FILL_CAPACITY_FACTOR,
            "cut_factor": wall_type_fragility.CUT_CAPACITY_FACTOR,
            "wall_curves": wall_curves[["label", "p15", "p50"]]
            .sort_values("p50")
            .to_dict(orient="records"),
        },
    }


def boundary_of(extent, authorities):
    """Return the boundary of the extent's territorial authority."""
    name = get_area_of_interest(extent).name
    return authorities.loc[authorities["name"] == name].union_all()


def written(path):
    """Return the date a file was written."""
    return (
        dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().date().isoformat()
    )


def union_area(geometries):
    """Return the area of the union of polygons, overlaps counted once.

    Only the clusters of polygons that touch are unioned, and the rest summed,
    which is many times faster than unioning tens of thousands of polygons at
    once and gives the same area.
    """
    geoms = shapely.make_valid(np.asarray(geometries))
    left, right = shapely.STRtree(geoms).query(geoms, predicate="intersects")
    n = len(geoms)
    graph = coo_matrix((np.ones(len(left)), (left, right)), shape=(n, n))
    _, cluster = connected_components(graph, directed=False)
    alone = np.bincount(cluster)[cluster] == 1
    total = float(shapely.area(geoms[alone]).sum())
    order = np.argsort(cluster[~alone], kind="stable")
    clusters, grouped = cluster[~alone][order], geoms[~alone][order]
    for part in np.split(grouped, np.flatnonzero(np.diff(clusters)) + 1):
        if len(part):
            total += shapely.union_all(part).area
    return total


def landslide_counts(polygons):
    """Return the landslide counts and areas by population and land class."""
    out = {}
    for population, group in polygons.groupby("population"):
        out[str(population)] = {
            "count": int(group["landslide_id"].nunique()),
            "area_km2": {
                str(land_class): round(
                    union_area(rows.geometry.to_numpy()) / M2_PER_KM2, 2
                )
                for land_class, rows in group.groupby("land_class")
            },
        }
    return out


def wall_counts(walls):
    """Return the walls that fail and stand, by type."""
    failed = walls[walls["outcome"] != "standing"]
    return {
        "on_failed_or_standing": len(walls),
        "failed": len(failed),
        "failed_share": round(len(failed) / len(walls), 3) if len(walls) else 0.0,
        "failed_length_km": round(float(failed["damaged_length_m"].sum()) / 1000.0, 1),
    }


def land_counts(land):
    """Return the properties damaged and the ground they lose."""
    damaged = land[(land["evacuated_area_m2"] + land["inundated_area_m2"]) > 0]
    return {
        "properties_damaged": len(damaged),
        "evacuated_ha": round(
            float(damaged["evacuated_area_m2"].sum()) / HECTARE_M2, 1
        ),
        "inundated_ha": round(
            float(damaged["inundated_area_m2"].sum()) / HECTARE_M2, 1
        ),
        "imminent_ha": round(
            float(land["imminent_evacuated_area_m2"].sum()) / HECTARE_M2, 1
        ),
        "median_evacuated_m2": round(
            float(
                damaged.loc[
                    damaged["evacuated_area_m2"] > 0, "evacuated_area_m2"
                ].median()
            ),
            0,
        ),
    }


def read_authority(extent, authorities):
    """Return one authority's landslides, walls and land, trimmed to it."""
    boundary = boundary_of(extent, authorities)
    crs = constants.DEFAULT_CRS
    path = combined_realisation_path(WORLD_ID, REALISATION_ID, extent=extent)
    polygons = gpd.read_parquet(path).to_crs(crs)
    polygons = polygons[polygons.representative_point().within(boundary)]

    population = gpd.read_parquet(wall_population_path(WORLD_ID, extent=extent)).to_crs(
        crs
    )
    population = population[population.representative_point().within(boundary)]
    walls = pd.read_parquet(
        wall_landslide_damage_path(WORLD_ID, REALISATION_ID, extent=extent)
    ).drop(columns=["damaged_line"], errors="ignore")
    walls = walls.merge(
        population[["rw_id", "wall_type", "size_class"]], on="rw_id", how="inner"
    )

    insured = gpd.read_parquet(
        insured_land_path(extent=extent), columns=[LAND_ID_COLUMN, "geometry"]
    ).to_crs(crs)
    inside = insured.loc[
        insured.representative_point().within(boundary), LAND_ID_COLUMN
    ]
    land = pd.read_parquet(
        landslide_land_damage_path(WORLD_ID, REALISATION_ID, extent=extent)
    )
    land = land[land[LAND_ID_COLUMN].isin(inside)]
    return polygons, walls, land, written(path)


def main():
    """Compute the numbers and write the YAML."""
    authorities = get_study_areas(constants.DEFAULT_CRS)
    parts, by_authority, runs = [], {}, {}
    for extent in AUTHORITY_EXTENTS:
        polygons, walls, land, date = read_authority(extent, authorities)
        name = get_area_of_interest(extent).name
        by_authority[name] = {
            "landslides": landslide_counts(polygons),
            "walls": wall_counts(walls),
            "land": land_counts(land),
        }
        runs[extent] = date
        parts.append((polygons, walls, land))
    polygons = pd.concat([p for p, _, _ in parts], ignore_index=True)
    walls = pd.concat([w for _, w, _ in parts], ignore_index=True)
    land = pd.concat([la for _, _, la in parts], ignore_index=True)
    labels = {
        row["wall_type"]: row["label"]
        for row in records(ASSETS_DIR / "retaining-wall-types.csv")
    }
    study = {
        "landslides": landslide_counts(polygons),
        "walls": wall_counts(walls),
        "land": land_counts(land),
    }
    study["walls"]["failed_share_by_type"] = {
        labels.get(str(k), str(k)): round(float(v), 3)
        for k, v in (walls["outcome"] != "standing")
        .groupby(walls["wall_type"])
        .mean()
        .sort_values()
        .items()
    }
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "world_id": WORLD_ID,
            "realisation_id": REALISATION_ID,
            "runs": runs,
        },
        "settings": settings(),
        "study_area": study,
        "by_authority": by_authority,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        yaml.safe_dump(numbers, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(
        yaml.safe_dump(
            {k: numbers[k] for k in ("study_area", "by_authority")}, sort_keys=False
        )
    )
    print(yaml.safe_dump(numbers["settings"]["marc"], sort_keys=False))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
