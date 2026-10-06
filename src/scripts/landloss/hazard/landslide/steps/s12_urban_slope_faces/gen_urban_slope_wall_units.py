"""Step 12: wall units on the pifs, their probability, and one draw per world.

Joins the candidate pifs and the GNS-only pieces of each property into wall
units, reads each pif's wall height and cut and fill class from landslide step
13, puts a prior on each, lifts the units GNS maps to the floor, updates
every property's units on the walls its claim report lists (and, flagged
unreliable, on NZMM), and draws each unit walled or not per exposure world
(:mod:`landloss.hazard.landslide.wall_units`). The plan is
``.agents/plans/placing-retaining-walls-on-pifs.md``.

Writes, under ``temp/hazard/landslide/``:

* ``urban-slope-wall-units.geoparquet``: one row per unit, with its member pif
  and GNS-only ids, its property and its probability and the parts of it;
* ``urban-slope-wall-draws.parquet``: whether each unit is walled, per world;
* ``urban-slope-wall-candidates-missing.parquet``: the properties whose units
  cannot hold the walls their records list;
* ``urban-slope-wall-property-records.parquet``: the claim and NZMM records
  read onto the LINZ properties, with the hold-out.

The last two are per property and as sensitive as the claim reports; they stay
under ``temp/``.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/gen_urban_slope_wall_units.py

Run ``gen_urban_slope_faces.py`` and then step 13's ``gen_pif_cut_fill.py``
first; this stops if step 13's tables are missing or older than the siz
table. The claim and NZMM layer is
``validations/config.PROPERTIES_PATH`` in exposure rw, written by
``gen_rw_dataset_properties.py``; where it is absent no update is applied.
Settings are in ``config.py``.
"""

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.domain import constants
from landloss.exposure.rw.lines import FACE_SAMPLE_SPACING_M, step_height_m
from landloss.hazard.landslide.instability_zones import read_siz_table
from landloss.hazard.landslide.wall_units import (
    UNIT_SOURCES,
    gen_claim_holdout,
    gen_gns_floor,
    gen_gns_wall_features,
    gen_pif_wall_heights,
    gen_property_wall_records,
    gen_wall_draws,
    gen_wall_members,
    gen_wall_prior,
    gen_wall_unit_probability,
    gen_wall_units,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_gns_slide_morphology, get_nz_property_boundaries
from scripts.landloss.exposure.rw.validations.config import PROPERTIES_PATH
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    MAPPED_WALL_TYPE,
    WORK_DIR,
    dem_bbox,
    gns_only_path,
    siz_table_path,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
    pif_cut_fill_pips_path,
)

# The siz table columns that only a run of the faces script with the spines
# and the rateable property writes, and the GNS-only column that only a run
# with the GNS-only rateable property writes.
SIZ_COLUMNS_NEEDED = ("pip_direction", "spine", "rateable_property_id")
GNS_ONLY_COLUMNS_NEEDED = ("rateable_property_id",)

RULE = "-" * 72


def wall_units_path(*, extent):
    """Where the wall unit table is written."""
    return WORK_DIR / f"urban-slope-wall-units{extent_suffix(extent)}.geoparquet"


def wall_draws_path(*, extent):
    """Where the per-world wall unit draws are written."""
    return WORK_DIR / f"urban-slope-wall-draws{extent_suffix(extent)}.parquet"


def wall_candidates_missing_path(*, extent):
    """Where the properties whose units cannot hold their listed walls go."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"urban-slope-wall-candidates-missing{suffix}.parquet"


def wall_property_records_path(*, extent):
    """Where the claim and NZMM records on the LINZ properties are written."""
    suffix = extent_suffix(extent)
    return WORK_DIR / f"urban-slope-wall-property-records{suffix}.parquet"


def read_sizs(*, extent):
    """The siz table, refused if the faces run that wrote it predates the spines.

    Raises:
        ValueError: If a column the wall units need is missing.
    """
    sizs = read_siz_table(siz_table_path(extent=extent))
    missing = [column for column in SIZ_COLUMNS_NEEDED if column not in sizs.columns]
    if missing:
        msg = (
            f"the siz table carries no {missing}: rerun gen_urban_slope_faces.py "
            "before gen_urban_slope_wall_units.py"
        )
        raise ValueError(msg)
    return sizs


def read_gns_only(*, extent):
    """The GNS-only candidates, refused if written before their rateable property.

    Raises:
        ValueError: If a column the wall units need is missing.
    """
    gns_only = gpd.read_parquet(gns_only_path(extent=extent))
    missing = [c for c in GNS_ONLY_COLUMNS_NEEDED if c not in gns_only.columns]
    if missing:
        msg = (
            f"the GNS-only candidates carry no {missing}: rerun "
            "gen_urban_slope_faces.py before gen_urban_slope_wall_units.py"
        )
        raise ValueError(msg)
    return gns_only


def read_cut_fill(*, extent, wall_height_quantile):
    """Step 13's class and the wall height of every pif, refused if stale.

    Args:
        extent: The build extent.
        wall_height_quantile: The quantile of the pips' face drops a pif's
            wall height is.

    Returns:
        One row per pif, indexed by ``pif_id``, with ``cut_fill_class``,
        ``face_drop_m`` and ``wall_height_m``.

    Raises:
        FileNotFoundError: If step 13 has not written its tables.
        ValueError: If either table is older than the siz table.
    """
    sizs_written = siz_table_path(extent=extent).stat().st_mtime
    rerun = (
        "run landslide step 13 (steps/s13_pif_cut_fill/gen_pif_cut_fill.py) "
        "after gen_urban_slope_faces.py and before gen_urban_slope_wall_units.py"
    )
    for path in (
        pif_cut_fill_path(extent=extent),
        pif_cut_fill_pips_path(extent=extent),
    ):
        if not path.exists():
            msg = f"{path} not found: {rerun}"
            raise FileNotFoundError(msg)
        if path.stat().st_mtime < sizs_written:
            msg = f"{path} is older than the siz table: {rerun}"
            raise ValueError(msg)
    pifs = pd.read_parquet(
        pif_cut_fill_path(extent=extent), columns=["cut_fill_class", "face_drop_m"]
    )
    pips = pd.read_parquet(
        pif_cut_fill_pips_path(extent=extent), columns=["pif_id", "z", "foot_z"]
    )
    heights = gen_pif_wall_heights(pips, quantile=wall_height_quantile)
    return pifs.join(heights)


def read_records(*, properties, bbox):
    """The claim and NZMM records on the LINZ properties, or None if not held."""
    if not PROPERTIES_PATH.exists():
        print(RULE)
        print(
            f"!!! claim/NZMM layer not found at {PROPERTIES_PATH}; no database "
            "update applied, hold-out empty. Run "
            "exposure/rw/validations/gen_rw_dataset_properties.py to write it."
        )
        print(RULE)
        return None
    records = gpd.read_parquet(PROPERTIES_PATH).to_crs(CRS)
    minx, miny, maxx, maxy = bbox
    return gen_property_wall_records(properties, records.cx[minx:maxx, miny:maxy])


def no_records():
    """An empty records frame, for a run with no claim and NZMM layer."""
    return pd.DataFrame(
        {
            "claim_walls": pd.array([], dtype="Int64"),
            "nzmm_wall": pd.Series(dtype=bool),
            "ta": pd.Series(dtype=object),
        },
        index=pd.Index([], name="property_id", dtype=object),
    )


def describe_units(units):
    """Print the units by source and exposure, and the bases of their parts."""
    print(RULE)
    print(f"Wall units: {len(units):,}")
    print(
        pd.crosstab(units["unit_source"], units["in_exposure"])
        .reindex(UNIT_SOURCES, fill_value=0)
        .to_string()
    )
    pif_units = units["unit_source"] == "pif"
    print("Pif units by cut and fill class:")
    print(units.loc[pif_units, "cut_fill_class"].value_counts().to_string())
    for column in ("p_prior_basis", "p_floor_basis", "p_wall_basis"):
        print(f"By {column}:")
        print(units[column].value_counts().to_string())
    for column in ("p_prior", "p_floor", "p_claims", "p_claims_nzmm", "p_wall"):
        total = float(np.nansum(units[column].to_numpy(dtype=float)))
        print(f"  sum of {column}: {total:,.1f}")


def describe_records(records, held_out, missing):
    """Print what the claim and NZMM records hold, as aggregates only."""
    claimed = records["claim_walls"].notna()
    listing = records["claim_walls"].fillna(0) >= 1
    print(
        f"Records on {len(records):,} LINZ properties: {int(claimed.sum()):,} "
        f"claimed, {int(listing.sum()):,} listing a wall, "
        f"{int(held_out.sum()):,} claimed held out; NZMM true on "
        f"{int(records['nzmm_wall'].sum()):,}"
    )
    for update, rows in missing.groupby("update"):
        print(
            f"  candidates missing ({update}): {int(rows['missing'].sum()):,} walls "
            f"on {len(rows):,} properties"
        )
    print(
        "  NZMM update flagged unreliable (kappa 0.03 against GNS); applied at "
        f"weight {constants.BETA_NZMM_UPDATE_WEIGHT:g} of the full update."
    )


def main(
    *,
    extent,
    use_cached_layers,
    gns_wall_match_m,
    gns_feature_snap_m,
    join_gap_m,
    max_offset_m,
    bearing_tol_deg,
    corner_gap_m,
    corner_max_deg,
    gns_only_merge_m,
    wall_height_quantile,
    holdout_share,
    holdout_seed,
    use_nzmm,
    world_ids,
):
    """Build the wall units, their probability and the draws, and write them.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ and GNS layers.
        gns_wall_match_m: A member within this many metres of a GNS mapped
            wall feature is on it.
        gns_feature_snap_m: Mapped wall segments this close are one feature.
        join_gap_m: The largest gap between two pifs' facing ends, in metres.
        max_offset_m: The largest offset of the ends along their fall.
        bearing_tol_deg: The largest difference in the facing ends' falls.
        corner_gap_m: The largest gap at a corner, in metres.
        corner_max_deg: The largest turn at a corner, in degrees.
        gns_only_merge_m: A GNS-only piece this close to a pif joins it.
        wall_height_quantile: A pif's wall height is this quantile of its
            pips' face drops (step 13's pip table).
        holdout_share: The share of claimed properties held out of the update.
        holdout_seed: The seed that picks them.
        use_nzmm: Whether ``p_wall`` takes the NZMM update.
        world_ids: The exposure worlds to draw.
    """
    sizs = read_sizs(extent=extent)
    cut_fill = read_cut_fill(extent=extent, wall_height_quantile=wall_height_quantile)
    gns_only = read_gns_only(extent=extent)
    bbox = dem_bbox(extent=extent)
    gns_only["step_height_m"] = step_height_m(
        gns_only.geometry, dem_path(1, extent=extent), spacing_m=FACE_SAMPLE_SPACING_M
    )
    no_step = int(gns_only["step_height_m"].isna().sum())
    print(f"GNS-only pieces with no step height read off the DEM: {no_step:,}")

    morphology = get_gns_slide_morphology(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    features = gen_gns_wall_features(
        morphology[morphology["Type"] == MAPPED_WALL_TYPE], snap_m=gns_feature_snap_m
    )
    members = gen_wall_members(sizs, gns_only, cut_fill)
    units = gen_wall_units(
        members,
        features,
        gns_match_m=gns_wall_match_m,
        join_gap_m=join_gap_m,
        max_offset_m=max_offset_m,
        bearing_tol_deg=bearing_tol_deg,
        corner_gap_m=corner_gap_m,
        corner_max_deg=corner_max_deg,
        gns_only_merge_m=gns_only_merge_m,
    )
    print(
        f"{len(features):,} GNS mapped wall features; {len(members):,} members "
        f"joined into {len(units):,} wall units"
    )
    prior = gen_wall_prior(units)
    floor = gen_gns_floor(units, prior)

    properties = get_nz_property_boundaries(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    records = read_records(properties=properties, bbox=bbox)
    if records is None:
        records = no_records()
        held_out_ids = pd.Series(dtype=bool, index=pd.Index([], name="property_id"))
    else:
        claimed = records.index[records["claim_walls"].notna()]
        held_out_ids = gen_claim_holdout(
            claimed, share=holdout_share, seed=holdout_seed
        )
    probability, missing = gen_wall_unit_probability(
        units,
        floor,
        records=records,
        held_out=held_out_ids,
        nzmm_min_walls=constants.BETA_NZMM_MIN_WALLS,
        nzmm_weight=constants.BETA_NZMM_UPDATE_WEIGHT,
        use_nzmm=use_nzmm,
    )
    units = units.join(prior).join(floor).join(probability)
    describe_units(units)
    if len(records):
        describe_records(records, held_out_ids, missing)

    draws = gen_wall_draws(
        units, world_ids=world_ids, base_seed=constants.EXPOSURE_BASE_SEED
    )
    for world_id, rows in draws.groupby("world_id"):
        print(f"World {world_id}: {rows['walled'].mean():.1%} of wall units walled")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    units.to_parquet(wall_units_path(extent=extent))
    draws.to_parquet(wall_draws_path(extent=extent), index=False)
    missing.to_parquet(wall_candidates_missing_path(extent=extent), index=False)
    out_records = records.assign(
        held_out=held_out_ids.reindex(records.index, fill_value=False).astype(bool)
    )
    out_records.to_parquet(wall_property_records_path(extent=extent))
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        gns_feature_snap_m=config.GNS_FEATURE_SNAP_M,
        join_gap_m=config.WALL_JOIN_GAP_M,
        max_offset_m=config.WALL_JOIN_MAX_OFFSET_M,
        bearing_tol_deg=config.WALL_JOIN_BEARING_TOL_DEG,
        corner_gap_m=config.WALL_CORNER_GAP_M,
        corner_max_deg=config.WALL_CORNER_MAX_ANGLE_DEG,
        gns_only_merge_m=config.GNS_ONLY_MERGE_M,
        wall_height_quantile=config.WALL_HEIGHT_QUANTILE,
        holdout_share=config.CLAIM_HOLDOUT_SHARE,
        holdout_seed=config.CLAIM_HOLDOUT_SEED,
        use_nzmm=config.USE_NZMM_UPDATE,
        world_ids=config.WORLD_IDS,
    )
