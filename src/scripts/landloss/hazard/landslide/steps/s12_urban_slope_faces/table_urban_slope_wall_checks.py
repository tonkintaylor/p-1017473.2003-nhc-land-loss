"""Step 12 checks on the wall units: GNS recall, held-out claims, strata, counts.

Four tables, written to ``report/hazard/landslide/urban-slope-faces/tab/``,
aggregates only:

* ``wall-gns-recall.csv``: the share of the GNS mapped wall length within the
  match distance of a wall unit member's footprint (the pips, or the GNS-only
  line), pifs only and pifs with the GNS-only pieces, against the recall of
  every pif (the ``share_near_any_pif`` of ``gns-agreement.csv`` in
  ``table_urban_slope_face_checks.py``, computed here the same way);
* ``wall-claims-holdout.csv``: on the held-out claimed properties, the
  expected walls and P(at least one wall) against what the reports list, for
  the floor and both updates;
* ``wall-strata.csv``: by council, NZMM slope class and age bin, the modelled
  share of properties with a wall against the share each dataset records, and
  ``below_recorded`` where the modelled share falls below the largest of them
  (the plan's one-sided test). The age bin is exposure rw step 8's per claim
  property (``rwt-age[-pilot].geoparquet``); where that step has not been run
  for the extent the age bin is one ``not available`` row saying so;
* ``wall-pilot-counts.csv``: units, expected walls, and per world the walled
  share of the sizs, the evacuated area against the two bounds and the share
  of drawn walls under 1.5 m against Anderson et al.'s 54%.

The checks are one-sided: a dataset with no wall is not evidence of no wall.
Any value over fewer than ``validations.config.MIN_HEX_CLAIMS`` claimed
properties (or properties) is suppressed, as the claim and NZMM data are
private.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/table_urban_slope_wall_checks.py

Run ``gen_urban_slope_wall_units.py`` and ``gen_urban_slope_wall_zones.py``
first. Settings are in ``config.py``.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from landloss.domain.loss_contract import CLAIM_ID_COLUMN
from landloss.exposure.rw.age import AGE_BIN_COLUMN
from landloss.hazard.landslide.instability_zones import read_siz_table
from landloss.hazard.landslide.slope_polygons import EVACUATED
from landloss.hazard.landslide.wall_units import CANDIDATE_CLASSES, unit_property_ids
from landloss.io.readers import get_gns_slide_morphology
from scripts.landloss.exposure.rw.steps.s8_infer_rwt_age.gen_rwt_age import (
    rwt_age_path,
)
from scripts.landloss.exposure.rw.validations.config import MIN_HEX_CLAIMS
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    MAPPED_WALL_TYPE,
    SCENARIOS,
    dem_bbox,
    gns_only_path,
    siz_table_path,
    zones_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_units import (
    wall_draws_path,
    wall_property_records_path,
    wall_units_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_wall_zones import (
    world_scenario,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.table_urban_slope_face_checks import (
    TAB_DIR,
    pip_tree,
    sample_points,
    share_within,
)

# Anderson et al. [anderson_2015]: 54% of 2,991 Canterbury walls retained
# under 1.5 m, the height the Building Act exempts from consent.
ANDERSON_UNDER_HEIGHT_M = 1.5
ANDERSON_UNDER_SHARE = 0.54

# The probability columns the hold-out scores.
ESTIMATES = ("p_floor", "p_claims", "p_claims_nzmm")

NOT_AVAILABLE = "not available"

# Why the age bin stratum is not built, where it is not.
NO_AGE_SOURCE = "exposure rw step 8 (gen_rwt_age.py) not run for this extent"

# The recorded shares a stratum's modelled share is held against.
RECORDED_SHARES = ("share_gns_wall", "share_nzmm_wall", "share_claim_wall")


def gns_recall(sizs, gns_only, walls, *, match_m):
    """The share of mapped wall length near the unit members' footprints."""
    points = sample_points(walls)
    pifs = sizs[sizs["candidate_class"].isin(CANDIDATE_CLASSES)]
    pips = shapely.get_coordinates(pifs.geometry.to_numpy())
    near_pif = np.zeros(len(points), dtype=bool)
    if len(pips) and len(points):
        near_pif = cKDTree(pips).query(points)[0] <= match_m
    near_line = np.zeros(len(points), dtype=bool)
    if len(gns_only) and len(points):
        hits = shapely.STRtree(gns_only.geometry.to_numpy()).query(
            shapely.points(points), predicate="dwithin", distance=match_m
        )
        near_line[np.unique(hits[0])] = True
    rows = [
        ("pifs", near_pif),
        ("pifs and gns_only", near_pif | near_line),
    ]
    pif_recall = share_within(points, pip_tree(sizs), match_m)
    return pd.DataFrame(
        [
            {
                "members": name,
                "match_m": match_m,
                "sample_points": len(points),
                "share_near": float(near.mean()) if len(near) else np.nan,
                "pif_recall_reference": pif_recall,
            }
            for name, near in rows
        ]
    )


def property_estimates(units, column):
    """Per property: the expected walls and P(at least one) from one column.

    A unit counts on every property it enters by at least 1 m
    (``property_lengths_m``), as the claim update counts it.
    """
    on = pd.DataFrame(
        {"property_id": unit_property_ids(units), "p": units[column].to_numpy()}
    ).explode("property_id")
    on = on[on["property_id"].notna()]
    p = on["p"].to_numpy(dtype=float)
    frame = pd.DataFrame(
        {
            "property_id": on["property_id"].astype(str).to_numpy(),
            "p": p,
            "log_none": np.log1p(-np.minimum(p, 1.0 - 1e-12)),
        }
    )
    grouped = frame.groupby("property_id")
    return pd.DataFrame(
        {
            "expected": grouped["p"].sum(),
            "p_any": 1.0 - np.exp(grouped["log_none"].sum()),
        }
    )


def _suppress(row, n, columns, *, name):
    """Blank the columns of a row computed over fewer than MIN_HEX_CLAIMS.

    ``suppressed`` names, joined by ``;``, every group of values blanked.
    """
    if n < MIN_HEX_CLAIMS:
        for column in columns:
            row[column] = np.nan
        row["suppressed"] = ";".join(filter(None, [row.get("suppressed", ""), name]))
    return row


def claims_holdout(units, records):
    """The floor and both updates scored on the held-out claimed properties."""
    if records.empty:
        return pd.DataFrame([{"estimate": NOT_AVAILABLE, "n": 0}])
    held = records[records["held_out"] & records["claim_walls"].notna()]
    listed = held["claim_walls"].astype(float)
    rows = []
    for column in ESTIMATES:
        est = property_estimates(units, column).reindex(held.index)
        expected = est["expected"].fillna(0.0)
        p_any = est["p_any"].fillna(0.0)
        listing = listed >= 1
        row = {
            "estimate": column,
            "n": len(held),
            "mean_expected_walls": expected.mean(),
            "mean_listed_walls": listed.mean(),
            "share_reaching_count": (expected >= listed).mean(),
            "n_listing": int(listing.sum()),
            "mean_p_any_where_listed": p_any[listing].mean(),
            "suppressed": "",
        }
        row = _suppress(
            row,
            len(held),
            ("mean_expected_walls", "mean_listed_walls", "share_reaching_count"),
            name="held_out",
        )
        row = _suppress(
            row, int(listing.sum()), ("mean_p_any_where_listed",), name="listing"
        )
        rows.append(row)
    return pd.DataFrame(rows)


def read_age_bins(*, extent):
    """The age bin per claim property from exposure rw step 8, or None if not run.

    The claim id is the source id of the title that represents its stack, the
    ``property_id`` the records are indexed by.
    """
    path = rwt_age_path(extent=extent)
    if not path.exists():
        return None
    ages = pd.read_parquet(path, columns=[CLAIM_ID_COLUMN, AGE_BIN_COLUMN])
    return pd.Series(
        ages[AGE_BIN_COLUMN].to_numpy(),
        index=pd.Index(ages[CLAIM_ID_COLUMN].astype(str), name="property_id"),
    )


def strata(units, records, age_bins):
    """By council, NZMM slope class, age bin and setting, the modelled and recorded shares.

    Args:
        units: The wall unit table.
        records: The claim and NZMM records on the LINZ properties.
        age_bins: From :func:`read_age_bins`; None for no age bin stratum.
    """
    if records.empty:
        return pd.DataFrame([{"stratum": NOT_AVAILABLE, "n": 0}])
    est = property_estimates(units, "p_wall").reindex(records.index)
    frame = records.assign(p_any=est["p_any"].fillna(0.0).to_numpy())
    if age_bins is not None:
        frame["age_bin"] = age_bins[~age_bins.index.duplicated()].reindex(frame.index)
    frame["has_gns_wall"] = (
        frame["gns_walls_2m"].fillna(0.0) > 0 if "gns_walls_2m" in frame else np.nan
    )
    frame["setting"] = wall_setting(units).reindex(frame.index).fillna("no_unit")
    claimed = frame["claim_walls"].notna()
    frame["claim_wall"] = frame["claim_walls"].fillna(0).astype(float) >= 1
    rows = []
    for stratum in ("ta", "nzmm_slope_class", "age_bin", "setting"):
        if stratum not in frame:
            continue
        for value, group in frame.groupby(frame[stratum].astype(str), dropna=False):
            in_claims = claimed.loc[group.index]
            row = {
                "stratum": stratum,
                "value": value,
                "n": len(group),
                "mean_p_any": group["p_any"].mean(),
                "share_p_any_over_half": (group["p_any"] > 0.5).mean(),
                "share_gns_wall": group["has_gns_wall"].astype(float).mean(),
                "share_nzmm_wall": group["nzmm_wall"].astype(float).mean(),
                "n_claimed": int(in_claims.sum()),
                "share_claim_wall": group.loc[in_claims, "claim_wall"].mean(),
                "suppressed": "",
            }
            row = _suppress(
                row,
                len(group),
                (
                    "mean_p_any",
                    "share_p_any_over_half",
                    "share_gns_wall",
                    "share_nzmm_wall",
                ),
                name="properties",
            )
            row = _suppress(
                row, int(in_claims.sum()), ("share_claim_wall",), name="claimed"
            )
            row["below_recorded"] = below_recorded(row)
            rows.append(row)
    if age_bins is None:
        rows.append(
            {
                "stratum": "age_bin",
                "value": NOT_AVAILABLE,
                "n": 0,
                "note": NO_AGE_SOURCE,
            }
        )
    return pd.DataFrame(rows)


def wall_setting(units):
    """Per property, the setting of its units, for the strata.

    ``road_frontage`` where any unit on the property takes the road frontage
    factor, else ``property_boundary`` where any takes the boundary factor,
    else ``interior``; a unit counts on every property it enters by 1 m.
    """
    if "is_road_frontage" not in units:
        return pd.Series(dtype=object)
    setting = np.where(
        units["is_road_frontage"].to_numpy(dtype=bool),
        2,
        np.where(units["is_property_boundary"].to_numpy(dtype=bool), 1, 0),
    )
    frame = pd.DataFrame(
        {"property_id": unit_property_ids(units), "setting": setting}
    ).explode("property_id")
    frame = frame[frame["property_id"].notna()]
    best = frame.groupby(frame["property_id"].astype(str))["setting"].max()
    return best.map({0: "interior", 1: "property_boundary", 2: "road_frontage"})


def below_recorded(row):
    """Whether the modelled share falls below the largest recorded share.

    The modelled share is ``share_p_any_over_half``, the share of properties
    more likely than not to have a wall, against the largest of
    :data:`RECORDED_SHARES` left after suppression; NA where either is blank.
    """
    recorded = [row.get(column, np.nan) for column in RECORDED_SHARES]
    recorded = [value for value in recorded if pd.notna(value)]
    modelled = row.get("share_p_any_over_half", np.nan)
    if not recorded or pd.isna(modelled):
        return pd.NA
    return bool(modelled < max(recorded))


def evacuated_m2(scenario, *, extent):
    """The evacuated area of one zones file, NaN if it is not written."""
    path = zones_path(scenario, extent=extent)
    if not path.exists():
        return np.nan
    zones = gpd.read_parquet(path)
    return float(zones.loc[zones["zone"] == EVACUATED].geometry.area.sum())


def pilot_counts(units, draws, sizs, *, extent, world_ids):
    """The unit counts, and per world the walled sizs, area and height shape."""
    bounds = {scenario: evacuated_m2(scenario, extent=extent) for scenario in SCENARIOS}
    rows = [
        {"metric": "wall_units", "value": len(units)},
        {"metric": "wall_units_in_exposure", "value": int(units["in_exposure"].sum())},
        {"metric": "expected_walls", "value": float(units["p_wall"].sum())},
        {"metric": "expected_walls_floor", "value": float(units["p_floor"].sum())},
        *(
            {"metric": f"units_{flag}", "value": int(units[flag].sum())}
            for flag in ("is_property_boundary", "is_road_frontage")
            if flag in units
        ),
        {
            "metric": "units_tall_face",
            "value": int((units.get("tall_face_factor", pd.Series(1.0)) < 1).sum()),
        },
        *(
            {"metric": f"evacuated_m2_{scenario}", "value": area}
            for scenario, area in bounds.items()
        ),
    ]
    siz_ids = sizs.index[sizs["is_siz"].astype(bool)]
    members = units["member_pif_ids"].explode().dropna().astype(np.int64)
    for world_id in world_ids:
        walled = (
            draws[draws["world_id"] == world_id]
            .set_index("wall_unit_id")["walled"]
            .reindex(units.index, fill_value=False)
        )
        walled_pifs = set(members[walled.reindex(members.index).to_numpy()])
        height = units.loc[walled.to_numpy(), "height_m"].to_numpy(dtype=float)
        height = height[np.isfinite(height)]
        rows += [
            {
                "metric": "walled_share_of_units",
                "world_id": world_id,
                "value": float(walled.mean()),
            },
            {
                "metric": "walled_share_of_sizs",
                "world_id": world_id,
                "value": float(siz_ids.isin(walled_pifs).mean()),
            },
            {
                "metric": "evacuated_m2",
                "world_id": world_id,
                "value": evacuated_m2(world_scenario(world_id), extent=extent),
                "reference": bounds.get("walled"),
            },
            {
                "metric": f"share_walled_under_{ANDERSON_UNDER_HEIGHT_M:g}m",
                "world_id": world_id,
                "value": (
                    float((height < ANDERSON_UNDER_HEIGHT_M).mean())
                    if len(height)
                    else np.nan
                ),
                "reference": ANDERSON_UNDER_SHARE,
            },
        ]
    counts = pd.DataFrame(rows)
    counts["world_id"] = counts["world_id"].astype("Int64")
    return counts


def main(*, extent, use_cached_layers, gns_wall_match_m, world_ids):
    """Write the four wall check tables for the extent.

    Args:
        extent: The build extent.
        use_cached_layers: Whether to reuse the cached GNS layer.
        gns_wall_match_m: A mapped wall this close to a footprint is found.
        world_ids: The exposure worlds to report.
    """
    units = gpd.read_parquet(wall_units_path(extent=extent))
    draws = pd.read_parquet(wall_draws_path(extent=extent))
    records = pd.read_parquet(wall_property_records_path(extent=extent))
    sizs = read_siz_table(siz_table_path(extent=extent))
    gns_only = gpd.read_parquet(gns_only_path(extent=extent))
    morphology = get_gns_slide_morphology(
        bbox=dem_bbox(extent=extent), crs=CRS, use_cache=use_cached_layers
    )
    tables = {
        "wall-gns-recall": gns_recall(
            sizs,
            gns_only,
            morphology[morphology["Type"] == MAPPED_WALL_TYPE],
            match_m=gns_wall_match_m,
        ),
        "wall-claims-holdout": claims_holdout(units, records),
        "wall-strata": strata(units, records, read_age_bins(extent=extent)),
        "wall-pilot-counts": pilot_counts(
            units, draws, sizs, extent=extent, world_ids=world_ids
        ),
    }
    if records.empty:
        print(
            "!!! no claim/NZMM records: the hold-out and strata tables are "
            f"'{NOT_AVAILABLE}'"
        )
    TAB_DIR.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(TAB_DIR / f"{name}.csv", index=False, float_format="%.3f")
        print(f"\n{name}\n{table.to_string(index=False)}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        world_ids=config.WORLD_IDS,
    )
