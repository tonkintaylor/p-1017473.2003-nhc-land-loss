"""Step 12: wall units on the pifs, their probability, and one draw per world.

Joins the candidate pifs and the GNS-only pieces into wall units across
property boundaries, draws each unit as one line of few straight sections,
records its length in every property it enters, reads each pif's wall height and cut and fill class from landslide step
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
    gen_property_wall_records,
    gen_unit_boundary_flags,
    gen_unit_properties,
    gen_wall_draws,
    gen_wall_members,
    gen_wall_points,
    gen_wall_unit_probability,
    gen_wall_units,
    load_wall_points,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_property_boundaries
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_age import (
    wall_age_path,
)
from scripts.landloss.exposure.rw.validations.config import PROPERTIES_PATH
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import config
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces.gen_urban_slope_faces import (
    CRS,
    WORK_DIR,
    dem_bbox,
    gns_only_path,
    siz_table_path,
)
from scripts.landloss.hazard.landslide.steps.s13_pif_cut_fill.gen_pif_cut_fill import (
    pif_cut_fill_path,
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


def read_cut_fill(*, extent):
    """Step 13's cut and fill class of every pif, refused if stale.

    The wall height is the siz table's ``near_drop_p80_m`` (2026-10-06), so
    only the class is read from step 13.

    Returns:
        One row per pif, indexed by ``pif_id``, with ``cut_fill_class``.

    Raises:
        FileNotFoundError: If step 13 has not written its pif table.
        ValueError: If it is older than the siz table.
    """
    sizs_written = siz_table_path(extent=extent).stat().st_mtime
    rerun = (
        "run landslide step 13 (steps/s13_pif_cut_fill/gen_pif_cut_fill.py) "
        "after gen_urban_slope_faces.py and before gen_urban_slope_wall_units.py"
    )
    path = pif_cut_fill_path(extent=extent)
    if not path.exists():
        msg = f"{path} not found: {rerun}"
        raise FileNotFoundError(msg)
    if path.stat().st_mtime < sizs_written:
        msg = f"{path} is older than the siz table: {rerun}"
        raise ValueError(msg)
    return pd.read_parquet(path, columns=["cut_fill_class"])


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
    points = units["wall_points"]
    print(
        "Wall points: "
        + ", ".join(
            f"{q:.0%} {points.quantile(q):+.0f}" for q in (0.05, 0.25, 0.5, 0.75, 0.95)
        )
    )
    for column in ("p_prior", "p_floor", "p_claims", "p_wall"):
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
        "  NZMM's flag is points now (+5 on its property's candidates), not an update."
    )


def read_age_shares(*, extent):
    """Exposure rw step 6's wall age shares per property, or None, loudly.

    The age points need them; without the file every candidate scores 0 for
    age. Run exposure rw step 6's gen_wall_age.py (which reads QV on T:);
    gen_hazard runs it before the wall units.
    """
    path = wall_age_path(extent=extent)
    if not path.exists():
        print(RULE)
        print(
            f"!!! wall age shares not found at {path}: every candidate scores 0 "
            "age points. Run exposure/rw/steps/s6_wall_population/gen_wall_age.py."
        )
        print(RULE)
        return None
    shares = pd.read_parquet(path)
    shares.index = shares.index.astype(str)
    return shares


def describe_lines(units):
    """Print how the units' lines were simplified and the properties they enter."""
    original = units["length_original_m"].sum()
    print(
        f"Unit lines: {units['length_m'].sum():,.0f} m simplified from "
        f"{original:,.0f} m of members; bends "
        f"{units['n_bends'].value_counts().sort_index().to_dict()}"
    )
    counts = units["n_properties"].value_counts().sort_index().to_dict()
    print(f"Units by the properties they enter by 1 m or more: {counts}")
    long = units["length_m"] > 50.0
    print(
        f"Units over 50 m: {int(long.sum()):,}, longest "
        f"{units['length_m'].max():,.0f} m; on a property boundary "
        f"{int(units['on_property_boundary'].sum()):,}, on a road frontage "
        f"{int(units['on_road_frontage'].sum()):,}"
    )


def main(
    *,
    extent,
    use_cached_layers,
    max_bends,
    min_segment_m,
    max_length_m,
    max_turn_deg,
    holdout_share,
    holdout_seed,
    world_ids,
):
    """Build the wall units, their probability and the draws, and write them.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ layers.
        max_bends: The most bends a unit's line may have.
        min_segment_m: The shortest a unit's line may be.
        max_length_m: The longest a unit's line may be.
        max_turn_deg: The most a unit's line may turn in all.
        holdout_share: The share of claimed properties held out of the update.
        holdout_seed: The seed that picks them.
        world_ids: The exposure worlds to draw.
    """
    sizs = read_sizs(extent=extent)
    cut_fill = read_cut_fill(extent=extent)
    gns_only = read_gns_only(extent=extent)
    bbox = dem_bbox(extent=extent)
    gns_only["step_height_m"] = step_height_m(
        gns_only.geometry, dem_path(1, extent=extent), spacing_m=FACE_SAMPLE_SPACING_M
    )
    no_step = int(gns_only["step_height_m"].isna().sum())
    print(f"GNS-only pieces with no step height read off the DEM: {no_step:,}")

    members = gen_wall_members(sizs, gns_only, cut_fill)
    properties = get_nz_property_boundaries(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    units = gen_wall_units(
        members,
        max_bends=max_bends,
        min_segment_m=min_segment_m,
        max_length_m=max_length_m,
        max_turn_deg=max_turn_deg,
    )
    by_class = units.groupby(
        np.where(
            units["unit_source"] == "gns_only",
            "gns_only",
            np.where(units["is_siz"], "siz", "low_height"),
        )
    )["length_m"].agg(["size", "sum"])
    print(f"{len(units):,} wall candidates, each its own unit:")
    print(by_class.round(0).to_string())
    units = (
        units.drop(columns=["property_id", "in_exposure"])
        .join(gen_unit_properties(units, properties))
        .join(gen_unit_boundary_flags(units, properties))
    )
    describe_lines(units)

    records = read_records(properties=properties, bbox=bbox)
    if records is None:
        records = no_records()
        held_out_ids = pd.Series(dtype=bool, index=pd.Index([], name="property_id"))
    else:
        claimed = records.index[records["claim_walls"].notna()]
        held_out_ids = gen_claim_holdout(
            claimed, share=holdout_share, seed=holdout_seed
        )
    shares = read_age_shares(extent=extent)
    prior = gen_wall_points(
        units,
        load_wall_points(),
        base_p=constants.BETA_WALL_BASE_P,
        low_height_base_p=constants.BETA_LOW_HEIGHT_WALL_PRIOR,
        per_doubling=constants.BETA_WALL_POINTS_PER_DOUBLING,
        age_shares=shares,
        nhc_flags=records["nzmm_wall"],
    )
    on_property = units["property_id"].notna().to_numpy()
    no_age = on_property & ~prior["has_age"].to_numpy(dtype=bool)
    if shares is not None and no_age.any():
        print(
            f"!!! {int(no_age.sum()):,} candidates on a property with no wall age "
            "shares score 0 age points."
        )
    floor = gen_gns_floor(units, prior)
    probability, missing = gen_wall_unit_probability(
        units, floor, records=records, held_out=held_out_ids
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
        max_bends=config.WALL_MAX_BENDS,
        min_segment_m=config.WALL_MIN_SEGMENT_M,
        max_length_m=config.WALL_MAX_LENGTH_M,
        max_turn_deg=config.MAX_TOTAL_TURN_DEG,
        holdout_share=config.CLAIM_HOLDOUT_SHARE,
        holdout_seed=config.CLAIM_HOLDOUT_SEED,
        world_ids=config.WORLD_IDS,
    )
