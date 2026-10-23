"""Write the numbers the retaining wall appendix quotes.

    uv run --frozen python src/scripts/landloss/exposure/rw/report/gen_report_numbers.py

Every number the appendix states comes from here, so each can be traced to the
code or the run it came from rather than typed in. The YAML has five parts:

- ``meta``: when and from which commit it was written, and the date each
  territorial authority's wall run was written.
- ``settings``: how candidates are found, how their lines and heights are set,
  how points become a probability, and how types are drawn, read from the
  constants and committed assets that set them.
- ``study_area``: over the four territorial authorities, the candidates by
  kind, the expected number of walls, and the walls drawn into world 0 by
  type and size class, with their length and height.
- ``by_authority``: the same counts for each territorial authority.
- ``validation``: the agreement between the wall datasets, read from the
  dataset comparison tables.

Each authority's run covers its bounding box, which takes in the edges of its
neighbours, so a candidate or wall is counted only in the authority its
representative point lies in, and only from that authority's own run. Reads the
outputs under ``temp/`` and the committed assets only, never the T: drive.
Written to ``report/exposure/rw/tab/report-numbers.yaml``.
"""

import datetime as dt
import sys

import geopandas as gpd
import pandas as pd
import yaml

from landloss.domain import constants
from landloss.exposure.rw import beta_population, wall_type
from landloss.exposure.rw.age import AGE_BINS, BIN_START_YEARS
from landloss.hazard.landslide import instability_zones
from landloss.io import ASSETS_DIR
from landloss.io.area_of_interest import get_area_of_interest, get_study_areas
from scripts.landloss.exposure.rw.steps.s6_wall_population import config as s6_config
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_population import (
    drawn_walls_path,
    wall_population_path,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_units_path,
)
from scripts.landloss.ground.steps.s3_instability_zones import config as s3_config
from scripts.landloss.hazard.liquefaction.report.gen_report_numbers import git_commit
from scripts.landloss.paths import REPORT_DIR

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUT_PATH = REPORT_DIR / "exposure" / "rw" / "tab" / "report-numbers.yaml"
DATASETS_DIR = REPORT_DIR / "exposure" / "rw" / "rw-datasets" / "tab"
# The four territorial authorities of the study, by extent name.
AUTHORITY_EXTENTS = ("wellington-city", "porirua", "lower-hutt", "upper-hutt")
WORLD_ID = 0
METRES_PER_KM = 1000.0


def records(path):
    """Return a CSV's rows as plain dicts."""
    return pd.read_csv(path).to_dict(orient="records")


def settings():
    """Return the values candidates, lines, probabilities and types are set with."""
    seed = pd.read_csv(ASSETS_DIR / "landslide-seed-thresholds.csv")
    slope = pd.read_csv(ASSETS_DIR / "landslide-slope-thresholds.csv")
    shares = pd.read_csv(ASSETS_DIR / "beta-retaining-wall-type-shares.csv")
    return {
        "pip_drop_m": instability_zones.PIP_DROP_M,
        "pip_offsets_m": list(instability_zones.PIP_OFFSETS_M),
        "pif_join_m": instability_zones.PIF_JOIN_M,
        "min_pif_pips": instability_zones.BETA_MIN_PIF_PIPS,
        "min_pif_length_m": instability_zones.BETA_MIN_PIF_LENGTH_M,
        "building_reach_m": s3_config.BUILDING_REACH_M,
        "near_pair_m": instability_zones.NEAR_PAIR_M,
        "max_pair_m": instability_zones.MAX_PAIR_M,
        "adjacent_step_m": dict(
            zip(seed["ground_group"], seed["adjacent_step_m"], strict=True)
        ),
        "slope_thresholds": records(ASSETS_DIR / "landslide-slope-thresholds.csv"),
        "slope_bands_m": slope["height_from_m"].tolist(),
        "wall_max_bends": s3_config.WALL_MAX_BENDS,
        "wall_min_segment_m": s3_config.WALL_MIN_SEGMENT_M,
        "wall_max_length_m": s3_config.WALL_MAX_LENGTH_M,
        "height_reach_m": s3_config.WALL_HEIGHT_REACH_M,
        "height_quantile": s3_config.WALL_HEIGHT_QUANTILE,
        "small_max_height_m": beta_population.SMALL_MAX_HEIGHT_M,
        "medium_max_height_m": beta_population.MEDIUM_MAX_HEIGHT_M,
        "base_p": constants.BETA_WALL_BASE_P,
        "points_per_doubling": constants.BETA_WALL_POINTS_PER_DOUBLING,
        "boundary_distance_m": constants.BETA_WALL_BOUNDARY_DISTANCE_M,
        "gns_floor": constants.BETA_GNS_WALL_UNIT_FLOOR,
        "gns_only_p": constants.BETA_GNS_ONLY_WALL_PROBABILITY,
        "claim_holdout_share": s6_config.CLAIM_HOLDOUT_SHARE,
        "points": records(ASSETS_DIR / "wall-probability-points.csv"),
        "age_bins": list(AGE_BINS),
        "age_bin_starts": list(BIN_START_YEARS),
        "type_height_bands": list(wall_type.HEIGHT_BANDS),
        "rebuilt_share": wall_type.BETA_WALL_REBUILT_SHARE,
        "type_shares": shares.to_dict(orient="records"),
        "frontage_multipliers": records(
            ASSETS_DIR / "beta-retaining-wall-frontage-multipliers.csv"
        ),
        "type_labels": records(ASSETS_DIR / "retaining-wall-types.csv"),
    }


def within_authority(frame, extent, authorities):
    """Keep the rows whose representative point lies in the extent's authority."""
    name = get_area_of_interest(extent).name
    boundary = authorities.loc[authorities["name"] == name].union_all()
    return frame[frame.representative_point().within(boundary)]


def written(path):
    """Return the date a file was written."""
    return (
        dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone().date().isoformat()
    )


def counts(units, drawn, insured):
    """Return the candidate and wall counts for one area."""
    return {
        "candidates": len(units),
        "candidates_by_kind": {
            "steep": int(units["is_siz"].sum()),
            "mapped_only": int(
                (units["n_gns_only"] > 0).sum() if "n_gns_only" in units else 0
            ),
            "with_mapped_wall": int(units["gns_wall"].sum()),
        },
        "expected_walls": round(float(units["p_wall"].sum()), 0),
        "drawn_walls": len(drawn),
        "drawn_length_km": round(float(drawn["length_m"].sum()) / METRES_PER_KM, 1),
        "insured_walls": len(insured),
    }


def main(*, world_id):
    """Compute the numbers and write the YAML."""
    authorities = get_study_areas(constants.DEFAULT_CRS)
    units_all, drawn_all, insured_all, by_authority, runs = [], [], [], {}, {}
    for extent in AUTHORITY_EXTENTS:
        paths = {
            "units": wall_units_path(extent=extent),
            "drawn": drawn_walls_path(world_id, extent=extent),
            "insured": wall_population_path(world_id, extent=extent),
        }
        units = within_authority(
            gpd.read_parquet(paths["units"]).to_crs(constants.DEFAULT_CRS),
            extent,
            authorities,
        )
        drawn = within_authority(
            gpd.read_parquet(paths["drawn"]).to_crs(constants.DEFAULT_CRS),
            extent,
            authorities,
        )
        insured = within_authority(
            gpd.read_parquet(paths["insured"]).to_crs(constants.DEFAULT_CRS),
            extent,
            authorities,
        )
        name = get_area_of_interest(extent).name
        by_authority[name] = counts(units, drawn, insured)
        runs[extent] = written(paths["drawn"])
        units_all.append(units)
        drawn_all.append(drawn)
        insured_all.append(insured)
    units = pd.concat(units_all, ignore_index=True)
    drawn = pd.concat(drawn_all, ignore_index=True)
    insured = pd.concat(insured_all, ignore_index=True)
    labels = {
        row["wall_type"]: row["label"]
        for row in records(ASSETS_DIR / "retaining-wall-types.csv")
    }
    study = counts(units, drawn, insured)
    study["by_type"] = {
        labels.get(str(k), str(k)): int(v)
        for k, v in drawn["wall_type"].value_counts().items()
    }
    study["by_size"] = {
        str(k): int(v) for k, v in drawn["size_class"].value_counts().items()
    }
    study["height_m"] = {
        "median": round(float(drawn["height_m"].median()), 2),
        "p10": round(float(drawn["height_m"].quantile(0.1)), 2),
        "p90": round(float(drawn["height_m"].quantile(0.9)), 2),
    }
    study["share_under_1_5_m"] = round(float((drawn["height_m"] < 1.5).mean()), 3)
    numbers = {
        "meta": {
            "written": dt.datetime.now().astimezone().date().isoformat(),
            "commit": git_commit(),
            "world_id": world_id,
            "runs": runs,
        },
        "settings": settings(),
        "study_area": study,
        "by_authority": by_authority,
        "validation": {
            "coverage": records(DATASETS_DIR / "rw-dataset-coverage.csv"),
            "claims_recall": records(DATASETS_DIR / "rw-dataset-claims-recall.csv"),
        },
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
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main(world_id=WORLD_ID)
