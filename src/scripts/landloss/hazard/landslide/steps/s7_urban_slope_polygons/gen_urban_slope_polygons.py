"""Reconcile the urban failure candidates to the wall lines and fix each state's geometry.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s7_urban_slope_polygons/gen_urban_slope_polygons.py

The run settings -- the extent, whether to reuse the
cached LINZ layers, and the road half width -- come from ``config.py`` beside
this script rather than from the command line.

Step 6 delineates failure candidates from the terrain alone; step 6 of the
exposure retaining wall work draws the lines a wall could stand on. This step
joins the two into the failure polygons the urban model draws on
(``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``,
sections 1.2 and 7; the build contract, sections 3.6 and 7.6):

1. **Reconcile the edges.** A candidate edge within the snap tolerance of a
   wall line is moved onto it, and a candidate straddling a line is split along
   it, so a wall is a polygon's edge and never runs through its middle
   (``landloss.hazard.landslide.urban.geometry.reconcile_candidates``). Every
   line is snapped to and split along; only lines on sloping land are
   recorded on an edge, because a flat-land wall has no polygon.
2. **Mint the ids.** Each piece becomes a failure polygon with a ``slope_id``,
   numbered by scale (coarsest first) and then location, so the ids depend on
   the inputs and not on the order the rows arrived in.
3. **Read the walls on the edge.** Every sloping-land line running along the
   polygon's boundary, longest shared edge first (``wall_line_ids``): the
   lines are split at property boundaries and the polygons are not, so one
   wall along an edge is often several lines. The line sharing the longest
   edge is ``wall_line_id`` and gives the polygon its wall position (fill or
   cut) and face height.
4. **Nest the scales.** Each polygon's parent is the smallest coarser polygon
   covering nine tenths of it.
5. **Score the ground.** The Kingsbury susceptibility rating and zone from the
   polygon's own attributes, the continuous rating the fragility reads, and the
   topographic amplification factor.
6. **Fix the state geometries.** For the no-wall state and, where a wall is on
   the edge, the state matching its position: the evacuated, inundated and
   imminent polygons and the evacuated and inundated depths, computed once here
   so that a realisation only picks them up.

Writes one GeoParquet with a row per ``slope_id`` under ``temp/hazard/landslide/``,
with the extent's ``extent_suffix`` (``-pilot`` for the small Wellington pilot).
"""

import sys

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.common.utils.terrain import zonal_statistic
from landloss.domain import constants
from landloss.hazard.landslide import susceptibility
from landloss.hazard.landslide.urban import geometry
from landloss.hazard.landslide.urban.delineation import SNAP_TOLERANCE_M
from landloss.hazard.landslide.urban.fragility import continuous_rating
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_address_roads, get_nz_building_outlines
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_lines import (
    wall_lines_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
    resolve_extent,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates.gen_urban_slope_candidates import (
    urban_slope_candidates_path,
)
from scripts.landloss.hazard.landslide.steps.s7_urban_slope_polygons import config
from scripts.landloss.paths import TEMP_DIR

# Wellington place names are macronised, which the default cp1252 Windows
# console cannot encode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# temp/ is gitignored. This is a working layer, rebuildable from the candidates
# and the wall lines, so it has no business in a diff.
WORK_DIR = TEMP_DIR / "hazard" / "landslide"
OUT_STEM = "urban-slope-polygons"

# The DEM the relief is recomputed from on the reconciled geometry.
RELIEF_RESOLUTION_M = 1

# The columns this step adds to the candidate columns, in the order they are
# written after the candidate columns (contract section 3.6).
ADDED_COLUMNS = (
    geometry.WALL_LINE_ID_COLUMN,
    geometry.WALL_EDGE_LENGTH_COLUMN,
    geometry.WALL_LINE_IDS_COLUMN,
    geometry.WALL_POSITION_COLUMN,
    geometry.WALL_FACE_HEIGHT_COLUMN,
    geometry.PARENT_SLOPE_ID_COLUMN,
    "kingsbury_rating",
    "kingsbury_zone",
    "continuous_rating",
    "amp_factor",
    geometry.REP_POINT_COLUMN,
    *geometry.STATE_DEPTH_COLUMNS,
    *geometry.STATE_GEOMETRY_COLUMNS,
)

DECILES = (0.1, 0.5, 0.9)

RULE = "-" * 72


def urban_slope_polygons_path(*, extent):
    """Return the file a run writes the failure polygons to.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.

    Returns:
        The output path, under ``temp/hazard/landslide/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def runout_barriers(buildings, roads, *, road_half_width_m):
    """Return the geometries a failure's debris stops at.

    Building outlines as they are, and road centrelines buffered to the road's
    width, in one series (contract section 3.6).
    """
    road_polygons = roads.geometry.buffer(road_half_width_m)
    barriers = pd.concat([buildings.geometry, road_polygons], ignore_index=True)
    return gpd.GeoSeries(barriers, crs=buildings.crs)


def recompute_relief(polygons, dem):
    """Read the relief of each reconciled polygon off the DEM.

    Max minus min elevation under the polygon. A piece too thin to hold a
    cell centre keeps the relief its candidate carried from step 6.
    """
    highest = zonal_statistic(dem, polygons.geometry, statistic="max")
    lowest = zonal_statistic(dem, polygons.geometry, statistic="min")
    return (highest - lowest).fillna(polygons[geometry.RELIEF_COLUMN])


def mint_slope_ids(polygons):
    """Sort the polygons by scale (coarsest first) and location and number them."""
    ordered = sort_by_point(polygons, by=(geometry.SCALE_COLUMN,), ascending=(False,))
    ordered[geometry.SLOPE_ID_COLUMN] = mint_ids(
        constants.SLOPE_ID_PREFIX, len(ordered)
    ).to_numpy()
    return ordered


def score_ground(polygons):
    """Add the Kingsbury rating and zone, the continuous rating and the amplification."""
    factors = geometry.kingsbury_factors(polygons)
    rating = susceptibility.susceptibility_rating(**factors)
    polygons["kingsbury_rating"] = rating
    polygons["kingsbury_zone"] = pd.Series(
        susceptibility.susceptibility_zone(rating), index=polygons.index
    ).astype("Int64")
    polygons["continuous_rating"] = continuous_rating(
        slope_degrees=polygons[geometry.SLOPE_COLUMN].to_numpy(dtype=float),
        modification=factors["modification"],
        height=factors["height"],
        geology=factors["geology"],
        landslides=factors["landslides"],
        groundwater=factors["groundwater"],
    )
    polygons["amp_factor"] = geometry.amplification_factor(
        polygons["topographic_position_100m"].to_numpy(dtype=float),
        polygons[geometry.SLOPE_COLUMN].to_numpy(dtype=float),
    )
    return polygons


def order_columns(polygons, candidate_columns):
    """Put the id first, then the candidate columns, then what this step added."""
    carried = [
        column
        for column in candidate_columns
        if column not in {geometry.CANDIDATE_ID_COLUMN, "geometry"}
    ]
    ordered = [
        geometry.SLOPE_ID_COLUMN,
        geometry.CANDIDATE_ID_COLUMN,
        geometry.PIECE_COLUMN,
        *carried,
        *ADDED_COLUMNS,
        "geometry",
    ]
    return polygons[ordered]


def describe_result(polygons):
    """Print the counts the contract's verification asks for."""
    print(RULE)
    print(f"Polygons: {len(polygons):,}")
    by_scale = polygons.groupby(geometry.SCALE_COLUMN).size()
    for scale, count in by_scale.items():
        print(f"  {scale:>3} m : {count:,}")
    with_wall = polygons[geometry.WALL_LINE_ID_COLUMN].notna()
    print(f"Share with a wall edge: {with_wall.mean():.1%}")
    line_counts = polygons[geometry.WALL_LINE_IDS_COLUMN].map(
        lambda cell: len(geometry.edge_line_ids(cell))
    )
    print(
        f"  with more than one wall line on the edge: {int((line_counts > 1).sum()):,}"
    )
    for position, count in (
        polygons[geometry.WALL_POSITION_COLUMN].value_counts().items()
    ):
        print(f"  {position:<5}: {count:,}")
    print("Kingsbury zone:")
    for zone, count in (
        polygons["kingsbury_zone"].value_counts(dropna=False).sort_index().items()
    ):
        label = susceptibility.ZONE_LABELS.get(zone, "no rating")
        print(f"  {zone!s:>5} {label:<10}: {count:,}")
    for column in (geometry.AREA_COLUMN, "amp_factor"):
        values = polygons[column].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            print(f"{column}: nothing finite")
            continue
        quantiles = np.quantile(finite, DECILES)
        print(
            f"{column}: "
            + ", ".join(
                f"p{100 * q:g} {v:,.2f}"
                for q, v in zip(DECILES, quantiles, strict=True)
            )
        )
    print("State geometries that are empty or invalid (must be zero):")
    for column in geometry.STATE_GEOMETRY_COLUMNS:
        filled = polygons[column].dropna()
        empty = int(filled.is_empty.sum())
        invalid = int((~filled.is_valid).sum())
        print(
            f"  {column:<22}: {len(filled):,} filled, {empty:,} empty, {invalid:,} invalid"
        )
    no_direction = polygons[geometry.ASPECT_COLUMN].isna()
    print(
        f"Polygons with no downhill direction (NaN aspect; their states are a "
        f"band around the edge): {int(no_direction.sum()):,}"
    )


def main(*, extent, use_cached_layers, road_half_width_m):
    """Build the failure polygons from the candidates and the wall lines and write them.

    Args:
        extent: The extent to run over, a name from
            ``landloss.io.area_of_interest.EXTENTS`` or ``"full"``.
        use_cached_layers: Whether to reuse the cached LINZ building outlines
            and road centrelines.
        road_half_width_m: Half the width a road centreline is buffered to as
            a runout barrier.
    """
    bbox, extent_name = resolve_extent(extent=extent)
    print(RULE)
    print(f"Extent: {extent_name}")
    print(
        f"Snap tolerance: {SNAP_TOLERANCE_M:g} m; road half width: {road_half_width_m:g} m"
    )

    candidates_path = urban_slope_candidates_path(extent=extent)
    lines_path = wall_lines_path(extent=extent)
    print(f"Reading the candidates from {candidates_path} ...")
    candidates = gpd.read_parquet(candidates_path)
    print(f"Reading the wall lines from {lines_path} ...")
    lines = gpd.read_parquet(lines_path)
    print(f"  {len(candidates):,} candidates, {len(lines):,} wall lines")

    print("Reading the runout barriers ...", flush=True)
    buildings = get_nz_building_outlines(bbox, use_cache=use_cached_layers)
    roads = get_nz_address_roads(bbox, use_cache=use_cached_layers)
    barriers = runout_barriers(buildings, roads, road_half_width_m=road_half_width_m)
    print(f"  {len(buildings):,} building outlines, {len(roads):,} road centrelines")

    print("Reconciling the candidates to the wall lines ...", flush=True)
    polygons = geometry.reconcile_candidates(
        candidates, lines, tolerance_m=SNAP_TOLERANCE_M
    )
    split = int((polygons[geometry.PIECE_COLUMN] > 0).sum())
    print(f"  {len(polygons):,} polygons, {split:,} pieces of split candidates")

    polygons[geometry.RELIEF_COLUMN] = recompute_relief(
        polygons, dem_path(RELIEF_RESOLUTION_M, extent=extent)
    )
    polygons = mint_slope_ids(polygons)
    polygons[geometry.PARENT_SLOPE_ID_COLUMN] = geometry.nest_parents(polygons)
    polygons = score_ground(polygons)

    print("Fixing the state geometries ...", flush=True)
    polygons = geometry.attach_state_geometries(
        polygons, lines, barriers=barriers, tolerance_m=SNAP_TOLERANCE_M
    )
    polygons = order_columns(polygons, candidates.columns)
    describe_result(polygons)

    out_path = urban_slope_polygons_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    polygons.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(polygons):,} polygons to {out_path}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        road_half_width_m=config.ROAD_HALF_WIDTH_M,
    )
