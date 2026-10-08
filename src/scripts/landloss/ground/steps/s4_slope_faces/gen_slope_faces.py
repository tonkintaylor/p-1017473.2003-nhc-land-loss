"""Ground step 4: the wall evidence read onto each pif, and the siz table.

Reads the pifs ground step 3 found (the grid columns of its siz table) and
writes onto each the evidence for a retaining wall
(:mod:`landloss.hazard.landslide.wall_candidates`): the GNS SLIDE walls and
T+T's manually mapped walls (less any manual wall within
``MANUAL_WALL_DUPLICATE_M`` of a GNS wall), the cut and fill lines, the
property it sits on and the building nearest it. A mapped wall with no pip near
it becomes a GNS-only candidate line of its own. It writes the siz table and the
GNS-only candidate table, which exposure rw step 6 builds its wall units from.
Reads the DEM from ground step 1 and the ground map from ground step 2.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/ground/steps/s4_slope_faces/gen_slope_faces.py

Settings are in ``config.py``.
"""

import geopandas as gpd

from landloss.hazard.landslide.instability_zones import (
    read_siz_table,
    write_siz_table,
)
from landloss.hazard.landslide.wall_candidates import (
    TT_MANUAL_WALL_SOURCE,
    gen_gns_only_candidates,
    gen_mapped_walls,
    property_of_pifs,
    wall_candidate_evidence,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_nz_building_outlines,
    get_nz_property_boundaries,
    get_slide_genesis,
    get_tt_manual_walls,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    WORK_DIR,
    dem_bbox,
    grid_sizs_path,
)
from scripts.landloss.ground.steps.s4_slope_faces import config

# GNS morphology types (landloss.exposure.rw.lines) and SLIDE genesis types.
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"
CUT_FILL_LINE_TYPE = "Cut/fill line"
CUT_SLOPE_TYPE = "Cut slope"
FILL_BODY_TYPE = "Fill body"
FILL_MODIFICATION = "fill"


def siz_table_path(*, extent):
    """Where the siz table, with its wall evidence, is written."""
    return WORK_DIR / f"urban-slope-sizs{extent_suffix(extent)}.parquet"


def gns_only_path(*, extent):
    """Where the GNS-only wall candidates (lines) are written."""
    return WORK_DIR / f"urban-slope-gns-wall-candidates{extent_suffix(extent)}.parquet"


def describe_properties(table):
    """Print how cleanly the pifs sit on properties."""
    has_property = table["n_properties"] > 0
    on_road = table["property_is_road"].fillna(value=False).astype(bool)
    print(
        f"{has_property.mean():.1%} of pifs in a property, "
        f"{on_road.sum():,} on road parcels, "
        f"{(table['n_properties'] > 1).sum():,} straddling two or more properties"
    )


def describe_manual_walls(manual_walls, mapped_walls):
    """Print how many manually mapped walls were kept and dropped as duplicates."""
    kept = mapped_walls[mapped_walls["wall_source"] == TT_MANUAL_WALL_SOURCE]
    print(
        f"T+T manual walls: {len(manual_walls):,} ({manual_walls.length.sum():,.0f} m), "
        f"{len(kept):,} kept ({kept.length.sum():,.0f} m), "
        f"{len(manual_walls) - len(kept):,} dropped within the duplicate distance "
        "of a GNS wall"
    )


def main(
    *,
    extent,
    use_cached_layers,
    gns_wall_match_m,
    manual_wall_duplicate_m,
    search_m,
    gns_only_min_length_m,
    max_bends,
    stray_tolerance_m,
    max_turn_deg,
    wall_max_length_m,
):
    """Read the wall evidence onto ground step 3's pifs and write the siz table.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ and GNS layers.
        gns_wall_match_m: A mapped wall within this many metres of a pif is on it.
        manual_wall_duplicate_m: A manually mapped wall this close to a GNS
            wall is dropped as a duplicate.
        search_m: Walls, lines and buildings further than this are not recorded.
        gns_only_min_length_m: Mapped wall with no pip near it becomes a candidate
            of its own if at least this long, in metres.
        max_bends: The bends rule the GNS-only candidates are cut by.
        stray_tolerance_m: How far a piece may stray from its line.
        max_turn_deg: The most a piece's line may turn in all.
        wall_max_length_m: The longest a GNS-only candidate may be.
    """
    grid = grid_sizs_path(extent=extent)
    if not grid.exists():
        msg = f"{grid} not found: run ground step 3 (gen_instability_zones.py)"
        raise FileNotFoundError(msg)
    table = read_siz_table(grid)
    bbox = dem_bbox(extent=extent)
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )

    morphology = get_gns_slide_morphology(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    genesis = get_slide_genesis(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    properties = get_nz_property_boundaries(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    manual_walls = get_tt_manual_walls(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    mapped_walls = gen_mapped_walls(
        morphology[morphology["Type"] == MAPPED_WALL_TYPE],
        manual_walls,
        duplicate_m=manual_wall_duplicate_m,
    )
    describe_manual_walls(manual_walls, mapped_walls)
    evidence = wall_candidate_evidence(
        table,
        walls=mapped_walls,
        cut_fill_lines=morphology[morphology["Type"] == CUT_FILL_LINE_TYPE],
        cut_slopes=genesis[genesis["Type"] == CUT_SLOPE_TYPE],
        fill_bodies=genesis[genesis["Type"] == FILL_BODY_TYPE],
        ground_map=ground_map,
        buildings=buildings,
        wall_match_m=gns_wall_match_m,
        search_m=search_m,
    )
    table = table.join(evidence).join(property_of_pifs(table, properties))
    write_siz_table(table, siz_table_path(extent=extent))
    print(table["candidate_class"].value_counts().to_string())
    describe_properties(table)

    gns_only = gen_gns_only_candidates(
        table,
        walls=mapped_walls,
        properties=properties,
        ground_map=ground_map,
        buildings=buildings,
        wall_match_m=gns_wall_match_m,
        min_length_m=gns_only_min_length_m,
        max_length_m=wall_max_length_m,
        search_m=search_m,
        max_bends=max_bends,
        stray_tolerance_m=stray_tolerance_m,
        max_turn_deg=max_turn_deg,
    )
    gns_only.to_parquet(gns_only_path(extent=extent))
    on_property = int(gns_only["property_id"].notna().sum())
    print(
        f"{len(gns_only):,} GNS-only candidates, {gns_only['length_m'].sum():,.0f} m "
        f"of {mapped_walls.length.sum():,.0f} m mapped; {on_property:,} on a property"
    )
    print(
        gns_only.groupby("wall_source")["length_m"]
        .agg(["size", "sum"])
        .round(0)
        .to_string()
    )
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        manual_wall_duplicate_m=config.MANUAL_WALL_DUPLICATE_M,
        search_m=config.SEARCH_M,
        gns_only_min_length_m=config.GNS_ONLY_MIN_LENGTH_M,
        max_bends=config.WALL_MAX_BENDS,
        stray_tolerance_m=config.WALL_STRAY_TOLERANCE_M,
        max_turn_deg=config.MAX_TOTAL_TURN_DEG,
        wall_max_length_m=config.WALL_MAX_LENGTH_M,
    )
