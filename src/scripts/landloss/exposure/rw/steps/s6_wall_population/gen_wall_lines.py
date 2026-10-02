"""Build the candidate retaining wall lines: every line a wall could stand on.

Reads the terrain rasters landslide step 3 wrote, the ground map of step 4 and
the urban failure candidates of step 6, the GNS SLIDE mapped walls, cut and
fill lines and genesis edges, the LINZ property boundaries, buildings and
roads, and writes one row per candidate line carrying its source, its face
height and size class, whether it holds fill or a cut face, the ground under
it, and the claim it belongs to. No probability: ``gen_wall_probability.py``
puts one on each line and ``gen_wall_population.py`` draws from it.

    uv run --frozen python src/scripts/landloss/exposure/rw/steps/s6_wall_population/gen_wall_lines.py

Needs the Koordinates key in ``.env`` the first time a layer is fetched, and
landslide steps 3, 4 and 6 run over the same extent first.

The rules are in `landloss.exposure.rw.lines`: the sources in precedence order,
the snap of the mapped walls onto the candidate edges, the collapse of
coincident lines, the split at property boundaries, the face height, the wall
position and the claim rule. The vector layers are read over a margin beyond
the extent so a property or wall across its edge is split at its real
boundary, and the lines are then cut back to the extent the landslide steps
ran over, by their midpoint. The ids are minted here, by location, so a rerun
over the same extent reproduces them and a changed extent renumbers.

What it runs over comes from ``config.py`` beside it.
"""

import sys

import geopandas as gpd
import numpy as np

from landloss.common.utils.ids import mint_ids, sort_by_point
from landloss.domain import constants
from landloss.exposure.land.extent import build_claim_properties
from landloss.exposure.rw.beta_population import SIZE_CLASSES
from landloss.exposure.rw.lines import (
    CLAIM_ID_COLUMN,
    MIN_SLOPING_GROUND_DEG,
    SOURCES,
    WALL_POSITIONS,
    build_wall_lines,
    mapped_wall_lines,
    snap_to_candidate_edges,
)
from landloss.hazard.landslide.urban.delineation import SNAP_TOLERANCE_M
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_nz_address_roads,
    get_nz_building_outlines,
    get_nz_property_boundaries,
    get_slide_genesis,
)
from scripts.landloss.exposure.rw.steps.s6_wall_population import config
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    aspect_path,
    dem_path,
    resolve_extent,
    slope_path,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_terrain_derivatives import (
    terrain_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s6_urban_slope_candidates.gen_urban_slope_candidates import (
    urban_slope_candidates_path,
)
from scripts.landloss.paths import TEMP_DIR

# Wellington suburb names are macronised, which the default cp1252 Windows
# console cannot encode, so printing one raises without this.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WORK_DIR = TEMP_DIR / "exposure"
OUT_STEM = "wall-lines"

WALL_LINE_ID_COLUMN = "wall_line_id"

# The vector layers are read over the extent grown by this, so a wall mapped or
# a property lying across the edge of the extent is not clipped away at the
# box before the split; drop_off_extent() then removes the lines left in the
# margin, where steps 3, 4 and 6 wrote nothing.
LAYER_MARGIN_M = 50.0

# The slope rasters the midpoint attributes and the boundary filter read.
MIDPOINT_RESOLUTION_M = 3
BOUNDARY_RESOLUTION_M = 10
# The DEM a boundary's step is measured on: the finest, so a wall a metre high
# is a step rather than a slope.
STEP_RESOLUTION_M = 1

RULE = "-" * 72


def wall_lines_path(*, extent):
    """Return the file a run writes the candidate wall lines to.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".

    Returns:
        The output path, under ``temp/exposure/``.
    """
    suffix = extent_suffix(extent)
    return WORK_DIR / f"{OUT_STEM}{suffix}.geoparquet"


def read_layers(bbox, *, use_cached_layers):
    """Return the vector layers the lines are built from, over the extent.

    Args:
        bbox: The extent as (minx, miny, maxx, maxy) in the default CRS.
        use_cached_layers: Whether to reuse already-fetched clipped layers.

    Returns:
        A dict of ``morphology``, ``genesis``, ``properties`` (the claim
        properties, one polygon per claim), ``buildings`` and ``roads``.
    """
    minx, miny, maxx, maxy = bbox
    grown = (
        minx - LAYER_MARGIN_M,
        miny - LAYER_MARGIN_M,
        maxx + LAYER_MARGIN_M,
        maxy + LAYER_MARGIN_M,
    )
    print("Reading the GNS SLIDE and LINZ layers over the extent ...", flush=True)
    morphology = get_gns_slide_morphology(bbox=grown, use_cache=use_cached_layers)
    genesis = get_slide_genesis(bbox=grown, use_cache=use_cached_layers)
    boundaries = get_nz_property_boundaries(bbox=grown, use_cache=use_cached_layers)
    properties = build_claim_properties(boundaries)
    buildings = get_nz_building_outlines(bbox=grown, use_cache=use_cached_layers)
    roads = get_nz_address_roads(bbox=grown, use_cache=use_cached_layers)
    print(
        f"  {len(morphology):,} morphology lines, {len(genesis):,} genesis "
        f"polygons, {len(properties):,} claim properties from "
        f"{len(boundaries):,} boundaries, {len(buildings):,} buildings, "
        f"{len(roads):,} roads"
    )
    return {
        "morphology": morphology,
        "genesis": genesis,
        "properties": properties,
        "buildings": buildings,
        "roads": roads,
    }


def drop_off_extent(lines, bbox):
    """Return the lines whose midpoint lies inside the extent.

    The layers are read over the extent grown by ``LAYER_MARGIN_M``, so a
    line in the margin has been split at its real property boundary rather
    than at the box, but the rasters and the ground map stop at the extent
    and a line left out there would carry no face height, slope or ground. A
    line across the edge goes with the side its midpoint is on. The run
    prints how many lines are dropped.

    Args:
        lines: The lines ``build_wall_lines`` returned.
        bbox: The extent as (minx, miny, maxx, maxy) in the default CRS, the
            one ``resolve_extent`` gave and the landslide steps ran over.

    Returns:
        The rows whose midpoint lies inside ``bbox``, on a fresh index.
    """
    minx, miny, maxx, maxy = bbox
    middle = lines.geometry.interpolate(0.5, normalized=True)
    inside = (
        (middle.x >= minx)
        & (middle.x <= maxx)
        & (middle.y >= miny)
        & (middle.y <= maxy)
    )
    kept = lines.loc[inside.to_numpy(dtype=bool)].reset_index(drop=True)
    print(
        f"Dropped {len(lines) - len(kept):,} lines whose midpoint lies in the "
        f"{LAYER_MARGIN_M:g} m margin outside the extent; {len(kept):,} kept"
    )
    return kept


def mint_wall_line_ids(lines):
    """Return the lines sorted by location with ``wall_line_id`` in front.

    Args:
        lines: The lines ``build_wall_lines`` returned.

    Returns:
        The same rows ordered by representative point, fresh index, with the
        id as the first column.
    """
    ordered = sort_by_point(lines)
    ids = mint_ids(constants.WALL_LINE_ID_PREFIX, len(ordered))
    ordered.insert(0, WALL_LINE_ID_COLUMN, ids.to_numpy())
    return ordered


def describe_snap(morphology, candidates):
    """Print how many mapped walls the snap onto the candidate edges moved."""
    mapped = mapped_wall_lines(morphology)
    snapped = snap_to_candidate_edges(mapped, candidates, tolerance_m=SNAP_TOLERANCE_M)
    moved = int((~snapped.geometry.geom_equals(mapped.geometry)).sum())
    print(
        f"Mapped walls: {len(mapped):,} lines, {moved:,} moved onto a candidate "
        f"edge within {SNAP_TOLERANCE_M:g} m"
    )


def _count_and_length(lines, column, order):
    """Return a table of line count and length in km by one column's values."""
    grouped = lines.groupby(column, observed=True)
    table = grouped.size().to_frame("lines")
    table["km"] = grouped["length_m"].sum() / 1000.0
    return table.reindex(order, fill_value=0).fillna(0.0)


def describe_lines(lines):
    """Print the counts the plan's verification section asks for."""
    print(RULE)
    total_km = lines["length_m"].sum() / 1000.0
    print(f"Candidate wall lines: {len(lines):,} ({total_km:,.1f} km)")
    if lines.empty:
        return
    print("By source:")
    print(_count_and_length(lines, "source", SOURCES).to_string())
    print("By size class:")
    print(_count_and_length(lines, "size_class", SIZE_CLASSES).to_string())
    print("By wall position:")
    print(_count_and_length(lines, "wall_position", WALL_POSITIONS).to_string())
    with_claim = lines[CLAIM_ID_COLUMN].notna()
    print(
        f"With a claim: {int(with_claim.sum()):,} ({with_claim.mean():.1%}); "
        f"{int((~with_claim).sum()):,} on road reserve or outside every claim"
    )
    flat = lines["is_flatland"].to_numpy(dtype=bool)
    print(f"On flat land: {int(flat.sum()):,} ({flat.mean():.1%})")
    mapped = lines["is_mapped_wall"].to_numpy(dtype=bool)
    print(f"With a GNS mapped wall along them: {int(mapped.sum()):,}")
    face = lines["face_height_m"].to_numpy(dtype=float)
    known = np.isfinite(face)
    if known.any():
        deciles = np.percentile(face[known], [10, 50, 90])
        print(
            f"Face height: 10% {deciles[0]:.2f} m, median {deciles[1]:.2f} m, "
            f"90% {deciles[2]:.2f} m; {int((~known).sum()):,} unreadable"
        )


def main(*, extent, use_cached_layers, road_distance_m):
    """Build the candidate wall lines and write them out.

    Args:
        extent: The extent to run over, a name from
            landloss.io.area_of_interest.EXTENTS or "full".
        use_cached_layers: Whether to reuse already-fetched clipped GNS and
            LINZ layers.
        road_distance_m: How near a road centreline a property boundary piece
            has to be to count as a road frontage.
    """
    bbox, name = resolve_extent(extent=extent)
    print(f"Extent: {name}")

    candidates_file = urban_slope_candidates_path(extent=extent)
    ground_file = ground_map_path(extent=extent)
    print(f"Reading the candidates from {candidates_file} ...")
    candidates = gpd.read_parquet(candidates_file)
    print(f"Reading the ground map from {ground_file} ...")
    ground_map = gpd.read_parquet(ground_file)
    print(f"  {len(candidates):,} candidates, {len(ground_map):,} ground polygons")

    layers = read_layers(bbox, use_cached_layers=use_cached_layers)
    describe_snap(layers["morphology"], candidates)

    print("Building the candidate wall lines ...", flush=True)
    lines = build_wall_lines(
        **layers,
        candidates=candidates,
        ground_map=ground_map,
        face_height_path=terrain_path("face-height-5m", extent=extent),
        dem_path=dem_path(STEP_RESOLUTION_M, extent=extent),
        residual_path=terrain_path("cut-fill-residual-30m", extent=extent),
        slope_3m_path=slope_path(MIDPOINT_RESOLUTION_M, extent=extent),
        slope_10m_path=slope_path(BOUNDARY_RESOLUTION_M, extent=extent),
        aspect_path=aspect_path(MIDPOINT_RESOLUTION_M, extent=extent),
        snap_tolerance_m=SNAP_TOLERANCE_M,
        road_distance_m=road_distance_m,
        min_slope_deg=MIN_SLOPING_GROUND_DEG,
        min_wall_height_m=constants.MIN_WALL_HEIGHT_M,
    )
    lines = drop_off_extent(lines, bbox)
    lines = mint_wall_line_ids(lines)
    describe_lines(lines)

    out_path = wall_lines_path(extent=extent)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines.to_parquet(out_path)
    print(RULE)
    print(f"Wrote {len(lines):,} candidate wall lines to {out_path}")
    print(
        "These are places a wall could stand, not walls: gen_wall_probability.py "
        "puts a probability on each line."
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        road_distance_m=config.ROAD_FRONTAGE_DISTANCE_M,
    )
