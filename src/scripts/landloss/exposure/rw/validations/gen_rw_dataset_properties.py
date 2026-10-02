"""Put the three retaining wall datasets on one layer of properties.

    uv run --frozen python src/scripts/landloss/exposure/rw/validations/gen_rw_dataset_properties.py

The three datasets record walls in different ways, and the property is the one
unit all three can be compared on:

- **GNS SLIDE mapped walls** [townsend_2020]: lines, mapped from above, over
  urban Wellington City only. A property has one where at least
  ``MIN_WALL_LENGTH_M`` of wall lies within ``tolerance`` of it.
- **NHC NZMM land attributes**: a Y/N retaining wall flag per property over the
  four councils. It has no geometry, so it is put on the LINZ property
  boundaries through QV's rating roll: NZMM ``qpid`` to the roll, the roll's
  valuation number to the LINZ ``valuation_reference``.
- **Claim reports**: the walls T+T engineers listed on site for a land claim,
  read from the claim report extraction. A report lists the walls that matter to
  the claim, so none listed is not no wall.

One row per LINZ property polygon (roads and hydro parcels left out) in the
study area. Settings are in ``config.py``. Needs ``LINZ_API_KEY`` and access to
the T+T Koordinates instance in ``.env``, the sensitive NZMM and QV files on T:,
and the claim report extraction.

The output is derived from the NZMM extract and the claim reports, one row per
property, so it is as sensitive as they are: it stays under the gitignored
``temp/`` and is destroyed with them. Only aggregates are written out by the
``table_`` and ``fig_`` scripts.
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.domain import constants
from landloss.exposure.rw.lines import MAPPED_WALL_TYPE
from landloss.io.area_of_interest import get_study_areas
from landloss.io.nzmm_land_attributes import get_nzmm_land_attributes
from landloss.io.qv_rating_roll import get_qv_rating_roll, linz_valuation_reference
from landloss.io.readers import get_gns_slide_morphology, get_nz_property_boundaries
from scripts.landloss.exposure.rw.validations import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CRS = constants.DEFAULT_CRS
GNS_TA = "Wellington City"

# The LINZ property boundary sources that are a property, not a road or river.
PROPERTY_SOURCES = ("NZ Unit of Property", "NZ Property Titles", "NZ Primary Parcels")

RULE = "-" * 72


def gns_column(tolerance_m: float, what: str) -> str:
    """Return the column name for a GNS measure at a tolerance."""
    return f"gns_{what}_{tolerance_m:g}m"


def load_properties(study_areas: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the LINZ property polygons in the study area, each with its TA."""
    bbox = tuple(float(value) for value in study_areas.total_bounds)
    boundaries = get_nz_property_boundaries(
        bbox, crs=CRS, use_cache=config.USE_CACHED_LAYERS
    )
    boundaries = boundaries.loc[boundaries["source"].isin(PROPERTY_SOURCES)]
    boundaries = boundaries[["valuation_reference", "source", "area", "geometry"]]

    points = boundaries.geometry.representative_point()
    joined = gpd.sjoin(
        gpd.GeoDataFrame(geometry=points, crs=CRS),
        study_areas[["name", "geometry"]],
        predicate="within",
    )
    joined = joined.loc[~joined.index.duplicated()]
    properties = boundaries.loc[joined.index].copy()
    properties["ta"] = joined["name"]
    return properties.reset_index(drop=True)


def add_nhc(properties: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add the NZMM retaining wall flag and slope class to each property."""
    nzmm = get_nzmm_land_attributes().dropna(subset=["has_retaining_wall"])
    nzmm = nzmm.drop_duplicates("property_id")
    roll = get_qv_rating_roll()
    roll = roll.assign(valuation_reference=linz_valuation_reference(roll))
    nzmm = nzmm.merge(
        roll[["qpid", "valuation_reference"]].dropna(), on="qpid", how="left"
    )
    print(
        f"NZMM properties with a flag: {len(nzmm):,}; "
        f"found on the QV roll: {nzmm['valuation_reference'].notna().mean():.1%}"
    )

    by_reference = nzmm.groupby("valuation_reference").agg(
        nhc_wall=("has_retaining_wall", "max"),
        nzmm_slope_class=("mean_slope_class", "max"),
        nzmm_properties=("property_id", "size"),
    )
    properties = properties.merge(
        by_reference, left_on="valuation_reference", right_index=True, how="left"
    )
    properties["nhc_wall"] = properties["nhc_wall"].astype("boolean")
    properties["has_nzmm"] = properties["nhc_wall"].notna()

    placed = nzmm["valuation_reference"].isin(set(properties["valuation_reference"]))
    print(
        f"NZMM properties placed on a LINZ polygon: {placed.sum():,} "
        f"({placed.mean():.1%}); flagged: {nzmm.loc[placed, 'has_retaining_wall'].sum():,} "
        f"of {nzmm['has_retaining_wall'].sum():,}"
    )
    return properties


def load_gns(
    study_areas: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Return the GNS mapped walls as connected lines, and the area mapped.

    The walls are supplied as 11,288 short segments; joining the ones that meet
    end to end makes a wall one feature, so a property's wall count is of walls
    and not of segments. The area mapped is the hull of every morphology line,
    of every type, within Wellington City.
    """
    wcc = study_areas.loc[study_areas["name"] == GNS_TA]
    bbox = tuple(float(value) for value in wcc.total_bounds)
    morphology = get_gns_slide_morphology(
        bbox, crs=CRS, use_cache=config.USE_CACHED_LAYERS
    )
    hull = shapely.convex_hull(shapely.union_all(morphology.geometry.to_numpy()))
    coverage = gpd.GeoDataFrame(
        geometry=[shapely.intersection(hull, wcc.geometry.iloc[0])], crs=CRS
    )

    segments = morphology.loc[morphology["Type"] == MAPPED_WALL_TYPE].geometry
    merged = shapely.line_merge(shapely.union_all(segments.to_numpy()))
    walls = gpd.GeoDataFrame(
        geometry=list(shapely.get_parts(merged)), crs=CRS
    ).rename_axis("wall_id")
    walls = walls.reset_index()
    print(
        f"GNS mapped walls: {len(segments):,} segments, {len(walls):,} walls, "
        f"{walls.length.sum() / 1000:,.0f} km"
    )
    return walls, coverage


def add_gns(
    properties: gpd.GeoDataFrame,
    walls: gpd.GeoDataFrame,
    coverage: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Add, per tolerance, the length and count of GNS walls on each property.

    Missing outside the area GNS mapped, where a property can have no mapped
    wall whatever is there.
    """
    points = properties.geometry.representative_point()
    mapped = points.within(coverage.geometry.iloc[0])
    properties["in_gns_coverage"] = mapped.to_numpy()

    for tolerance in config.TOLERANCES_M:
        zones = gpd.GeoDataFrame(
            geometry=properties.geometry.buffer(tolerance), crs=CRS
        ).loc[mapped]
        pairs = gpd.sjoin(zones, walls, predicate="intersects")
        lengths = shapely.length(
            shapely.intersection(
                pairs.geometry.to_numpy(),
                walls.geometry.to_numpy()[pairs["index_right"].to_numpy()],
            )
        )
        pairs = pairs.assign(length_m=lengths)
        pairs = pairs.loc[pairs["length_m"] >= config.MIN_WALL_LENGTH_M]
        per_property = pairs.groupby(level=0).agg(
            length_m=("length_m", "sum"), walls=("wall_id", "nunique")
        )

        length_column = gns_column(tolerance, "wall_m")
        count_column = gns_column(tolerance, "walls")
        properties[length_column] = np.where(mapped, 0.0, np.nan)
        properties[count_column] = np.where(mapped, 0.0, np.nan)
        properties.loc[per_property.index, length_column] = per_property["length_m"]
        properties.loc[per_property.index, count_column] = per_property["walls"]

    return properties


def load_claims() -> gpd.GeoDataFrame:
    """Return every extracted claim report with a location, as points."""
    frames = []
    for name in config.CLAIMS_LISTS:
        path = config.CLAIM_REPORTS_EXTRACTED_DIR / name / "reports.csv"
        frame = pd.read_csv(path, dtype={"subproject": str})
        frames.append(frame.assign(claims_list=name))
    reports = pd.concat(frames, ignore_index=True)
    reports = reports.dropna(subset=["lon", "lat"])
    reports["n_walls"] = pd.to_numeric(reports["n_walls"], errors="coerce")
    return gpd.GeoDataFrame(
        reports[["subproject", "claims_list", "claim_accepted", "n_walls"]],
        geometry=gpd.points_from_xy(reports["lon"], reports["lat"], crs=4326),
    ).to_crs(CRS)


def add_claims(
    properties: gpd.GeoDataFrame, claims: gpd.GeoDataFrame
) -> gpd.GeoDataFrame:
    """Add each property's claim reports and the most walls any of them lists.

    A claim is placed on the property its point falls in, or the nearest one
    within ``CLAIM_SNAP_DISTANCE_M`` where it falls in a road. A property claimed
    more than once takes the largest wall count, since a later report on the
    same land usually lists the same walls again.
    """
    polygons = properties[["geometry"]]
    within = gpd.sjoin(claims, polygons, predicate="within")
    within = within.loc[~within.index.duplicated()]
    rest = claims.loc[~claims.index.isin(within.index)]
    near = gpd.sjoin_nearest(rest, polygons, max_distance=config.CLAIM_SNAP_DISTANCE_M)
    near = near.loc[~near.index.duplicated()]
    placed = pd.concat([within, near])
    print(
        f"Claim reports with a location: {len(claims):,}; placed on a property: "
        f"{len(placed):,} ({len(within):,} inside one, {len(near):,} snapped)"
    )

    per_property = placed.groupby("index_right").agg(
        claim_reports=("subproject", "size"),
        claim_walls=("n_walls", "max"),
    )
    properties["claim_reports"] = 0
    properties.loc[per_property.index, "claim_reports"] = per_property["claim_reports"]
    properties["claim_walls"] = np.nan
    properties.loc[per_property.index, "claim_walls"] = per_property["claim_walls"]
    properties["has_claim"] = properties["claim_reports"] > 0
    properties["claim_wall"] = (properties["claim_walls"] > 0).where(
        properties["claim_walls"].notna()
    )
    properties["claim_wall"] = properties["claim_wall"].astype("boolean")
    return properties


def main() -> int:
    """Build and write the per-property comparison layer."""
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    study_areas = get_study_areas(CRS)

    properties = load_properties(study_areas)
    print(f"LINZ properties in the study area: {len(properties):,}")
    properties = add_nhc(properties)

    walls, coverage = load_gns(study_areas)
    properties = add_gns(properties, walls, coverage)
    properties = add_claims(properties, load_claims())

    # The valuation reference identifies a property on the sensitive extract,
    # and nothing downstream needs it.
    properties = properties.drop(columns=["valuation_reference"])
    properties.to_parquet(config.PROPERTIES_PATH)
    walls.to_parquet(config.GNS_WALLS_PATH)
    coverage.to_parquet(config.GNS_COVERAGE_PATH)

    print(RULE)
    print(f"Wrote {config.PROPERTIES_PATH}")
    return 0


if __name__ == "__main__":
    status = main()
    if status:
        raise SystemExit(status)
