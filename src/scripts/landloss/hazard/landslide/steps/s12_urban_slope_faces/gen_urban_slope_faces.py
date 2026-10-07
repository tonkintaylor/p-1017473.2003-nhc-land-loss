"""Step 12: urban slope faces, from pips to evacuated zones, over an extent.

Finds the potential instability points (pips), groups them into faces (pifs),
drops the faces most of whose pips lie in a LINZ building outline (a roof's
edge is not a slope), tests every face for a seed instability zone (siz),
grows the sizs into
elements and builds the evacuated, imminent and inundated zones twice: once
with every siz walled and once with none. It also reads the evidence for a
retaining wall onto each pif (:mod:`landloss.hazard.landslide.wall_candidates`).
The mapped walls are the GNS SLIDE walls and T+T's manually mapped walls, less
any manual wall within ``MANUAL_WALL_DUPLICATE_M`` of a GNS wall.
Reads the DEM from step 3 and the ground map from step 4.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s12_urban_slope_faces/gen_urban_slope_faces.py

Settings are in ``config.py``.
"""

import pickle
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray
from rasterio import features

from landloss.common.utils import tiles
from landloss.hazard.landslide.instability_zones import (
    find_instability_zones,
    gen_pif_near_drops,
    gen_pif_spines,
    gen_pif_verticality,
    gen_siz_table,
    write_siz_table,
)
from landloss.hazard.landslide.slope_elements import (
    COARSE_SLOPE_M,
    rasterise_ground_map,
)
from landloss.hazard.landslide.slope_polygons import (
    ZONES,
    polygon_geometries,
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
    get_nz_coastline_polygons,
    get_nz_property_boundaries,
    get_slide_genesis,
    get_tt_manual_walls,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    config,
    tiled,
)
from scripts.landloss.paths import TEMP_DIR

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
CRS = 2193
SCENARIOS = {"walled": True, "bare": False}

# GNS morphology types (landloss.exposure.rw.lines) and SLIDE genesis types.
MAPPED_WALL_TYPE = "Retaining wall (man-made feature)"
CUT_FILL_LINE_TYPE = "Cut/fill line"
CUT_SLOPE_TYPE = "Cut slope"
FILL_BODY_TYPE = "Fill body"
FILL_MODIFICATION = "fill"


def siz_table_path(*, extent):
    """Where the siz table, with its wall evidence, is written."""
    return WORK_DIR / f"urban-slope-sizs{extent_suffix(extent)}.parquet"


def elements_path(*, extent):
    """Where the grown elements are written."""
    return WORK_DIR / f"urban-slope-elements{extent_suffix(extent)}.parquet"


def gns_only_path(*, extent):
    """Where the GNS-only wall candidates (lines) are written."""
    return WORK_DIR / f"urban-slope-gns-wall-candidates{extent_suffix(extent)}.parquet"


def wall_elements_path(*, extent):
    """Where the elements with the GNS-only wall lines added are written.

    ``gen_urban_slope_wall_zones.py`` writes it; landslide step 8 reads it.
    """
    return WORK_DIR / f"urban-slope-wall-elements{extent_suffix(extent)}.parquet"


def zones_path(scenario, *, extent):
    """Where the evacuated, imminent and inundated zones of a scenario are written."""
    return WORK_DIR / f"urban-slope-zones-{scenario}{extent_suffix(extent)}.parquet"


def found_path(*, extent):
    """Where the grown elements, as found, are kept for the per-world zones."""
    return WORK_DIR / f"urban-slope-found{extent_suffix(extent)}.pkl"


def write_found(found, *, extent):
    """Keep the found elements so the per-world zones need not find them again."""
    with found_path(extent=extent).open("wb") as file:
        pickle.dump(found, file, protocol=pickle.HIGHEST_PROTOCOL)


def read_found(*, extent):
    """The found elements :func:`write_found` kept.

    Raises:
        FileNotFoundError: If this step's faces run has not written them.
    """
    path = found_path(extent=extent)
    if not path.exists():
        msg = f"{path} not found: rerun gen_urban_slope_faces.py"
        raise FileNotFoundError(msg)
    with path.open("rb") as file:
        # Written by this step's own run under temp/, not an outside file.
        return pickle.load(file)  # noqa: S301


def dem_bbox(*, extent):
    """The bounds of the 1 m DEM, the bbox the step reads its layers on.

    The reader caches are keyed by bbox, so every script of the step reading
    the LINZ and GNS layers takes it from here and shares their cache.
    """
    with rioxarray.open_rasterio(dem_path(1, extent=extent)) as dem:
        return tuple(dem.rio.bounds())


def get_dem(*, extent, use_cached_layers):
    """The 1 m DEM with every cell off the LINZ land polygons set to no data.

    The pips are found on this DEM, so a later step that walks or fits the
    pifs reads it from here too.

    Returns:
        ``(dem, transform, bbox)``.
    """
    dem_da = rioxarray.open_rasterio(dem_path(1, extent=extent), masked=True).squeeze(
        "band", drop=True
    )
    dem = dem_da.to_numpy().astype("float64")
    transform = dem_da.rio.transform()
    bbox = dem_bbox(extent=extent)
    land = get_nz_coastline_polygons(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    on_land = features.rasterize(
        [(geometry, 1) for geometry in land.geometry],
        out_shape=dem.shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)
    return np.where(on_land, dem, np.nan), transform, bbox


def get_inputs(*, extent, use_cached_layers):
    """The DEM with the sea masked, the ground map and the ground groups.

    Returns:
        ``(dem, transform, bbox, ground_map, group, position)``. Fill is read
        as soil in ``group``, as the pip test has no fill class.
    """
    dem, transform, bbox = get_dem(extent=extent, use_cached_layers=use_cached_layers)
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    group, position = rasterise_ground_map(
        ground_map, transform, dem.shape, fill_as_soil=True
    )
    return dem, transform, bbox, ground_map, group, position


def fill_by_element(elements, ground_map):
    """Whether each element is on fill, and the fill's thickness where it is."""
    rows = elements["majority_ground_row"].to_numpy()
    on_map = rows >= 0
    safe = np.maximum(rows, 0)
    is_fill = on_map & (
        ground_map["modification"].to_numpy()[safe] == FILL_MODIFICATION
    )
    thickness = np.where(
        is_fill, ground_map["fill_thickness_m"].to_numpy()[safe], np.nan
    )
    return (
        pd.Series(is_fill, index=elements.index),
        pd.Series(thickness, index=elements.index),
    )


def grid_table(
    zones, dem, transform, *, end_window_m, wall_height_reach_m, wall_height_quantile
):
    """The siz table with the columns read off the grid: drops, verticality, spines."""
    table = gen_siz_table(zones, transform, crs=CRS)
    table["near_drop_p80_m"] = gen_pif_near_drops(
        dem,
        zones.pips,
        zones.pif_labels,
        abs(transform.a),
        reach_m=wall_height_reach_m,
        quantile=wall_height_quantile,
    ).reindex(table.index)
    table["verticality"] = gen_pif_verticality(
        dem, zones.pips, zones.pif_labels
    ).reindex(table.index)
    return table.join(
        gen_pif_spines(
            table,
            cell_size_m=abs(transform.a),
            end_window_m=end_window_m,
            lines=zones.pif_lines,
        )
    )


def tile_found_path(tile, *, extent):
    """Where one tile's elements, as found, are kept for the wall zones."""
    folder = WORK_DIR / f"urban-slope-found{extent_suffix(extent)}-tiles"
    return folder / f"tile-{tile.row:02d}-{tile.col:02d}.pkl"


def find_tiled(
    *, extent, use_cached_layers, core_m, margin_m, find_settings, table_settings
):
    """Find the pifs and elements tile by tile and stitch them (:mod:`tiled`).

    Returns:
        ``(table, elements, bbox, ground_map, buildings)``: the siz table with
        its grid columns and the element polygons, owned rows only with
        global ids, and the layers the rest of the step reads.
    """
    dem_file = dem_path(1, extent=extent)
    bbox = dem_bbox(extent=extent)
    ground_map = gpd.read_parquet(ground_map_path(extent=extent))
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    land = get_nz_coastline_polygons(bbox=bbox, crs=CRS, use_cache=use_cached_layers)
    inputs = {"land": land, "ground_map": ground_map, "buildings": buildings}
    # The catchments are read on blocks of cells from the window's corner, so
    # every tile starts on the whole grid's blocks.
    with rioxarray.open_rasterio(dem_file) as dem:
        transform = dem.rio.transform()
    block = max(round(COARSE_SLOPE_M / abs(transform.a)), 1)
    grid = tiles.tile_grid(
        dem_file, core_m=core_m, margin_m=margin_m, align_cells=block
    )
    print(f"{len(grid)} tiles of {core_m:,.0f} m with a {margin_m:,.0f} m margin")
    start = time.perf_counter()
    records = []
    for tile in grid:
        found = tiled.find_tile(
            dem_file, tile, inputs=inputs, find_settings=find_settings
        )
        if found is None:
            continue
        zones, dem, transform = found
        table = grid_table(zones, dem, transform, **table_settings)
        path = tile_found_path(tile, extent=extent)
        tiled.write_tile_found(zones.found, path)
        records.append(
            {
                "tile": tile,
                "path": path,
                "table": table,
                "elements": element_polygons(zones.found, transform),
                "owned": tiled.owned_parents(table, tile.core_bounds),
            }
        )
        print(
            f"  tile {tile.row},{tile.col}: {len(table):,} pifs, "
            f"{len(zones.found.elements):,} elements "
            f"({time.perf_counter() - start:,.0f} s)",
            flush=True,
        )
    found, table, elements = tiled.globalise_found(records, transform)
    with found_path(extent=extent).open("wb") as file:
        pickle.dump(found, file, protocol=pickle.HIGHEST_PROTOCOL)
    print(
        f"Stitched: {len(table):,} pifs, {int(table['is_siz'].sum()):,} sizs, "
        f"{len(elements):,} elements"
    )
    return table, elements, bbox, ground_map, buildings


def element_polygons(found, transform):
    """The grown elements as polygons, with their attributes."""
    shapes = features.shapes(
        found.labels.astype("int32"), mask=found.labels > 0, transform=transform
    )
    frame = gpd.GeoDataFrame.from_features(
        [
            {"type": "Feature", "geometry": g, "properties": {"label": int(v)}}
            for g, v in shapes
        ],
        crs=CRS,
    )
    frame = frame.dissolve(by="label")
    return frame.join(found.elements, how="left")


def zone_polygons(result, *, scenario):
    """Every zone of every polygon of a scenario, one row per polygon and zone."""
    parts = []
    for zone in ZONES:
        frame = polygon_geometries(result, zone=zone, crs=CRS)
        frame["zone"] = zone
        parts.append(frame)
    zones = pd.concat(parts, ignore_index=True)
    zones = zones.merge(result.polygons.reset_index(), on="polygon", how="left")
    zones["scenario"] = scenario
    return gpd.GeoDataFrame(zones, geometry="geometry", crs=CRS)


def building_mask(buildings, transform, shape):
    """True on the cells whose centre lies in a LINZ building outline."""
    if buildings.empty:
        return np.zeros(shape, dtype=bool)
    return features.rasterize(
        [(geometry, 1) for geometry in buildings.geometry],
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)


def describe(zones, elapsed):
    """Print the counts and timings of the run."""
    sizs = zones.sizs
    print(
        f"{zones.n_pifs_excluded:,} pifs dropped with most of their pips in a "
        f"building outline, {zones.n_pifs_short:,} with a spine under 3 m"
    )
    print(f"{int(zones.pips.mask.sum()):,} pips, {len(sizs):,} pifs, ", end="")
    print(f"{int(sizs['is_siz'].sum()):,} sizs, {len(zones.found.elements):,} elements")
    print(sizs.groupby("ground_group")["is_siz"].agg(["size", "sum"]).to_string())
    print(f"Pips to grown elements: {elapsed:.1f} s")
    print(f"Pif pieces the 50 m cap cut, by stage: {zones.cap_cuts}")


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
    end_window_m,
    max_bends,
    stray_tolerance_m,
    min_segment_m,
    max_turn_deg,
    wall_max_length_m,
    wall_height_reach_m,
    wall_height_quantile,
    max_untiled_cells,
    tile_core_m,
    tile_margin_m,
):
    """Run the pipeline over the extent and write the siz table, elements and zones.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ and GNS layers.
        gns_wall_match_m: A mapped wall within this many metres of a pif is on it.
        manual_wall_duplicate_m: A manually mapped wall this close to a GNS
            wall is dropped as a duplicate.
        search_m: Walls, lines and buildings further than this are not recorded.
        gns_only_min_length_m: Mapped wall with no pip near it becomes a candidate
            of its own if at least this long, in metres.
        end_window_m: The fall direction at each end of a pif's spine is the
            mean over its pips within this many metres of the end.
        max_bends: The bends rule the pifs are cut by, as the walls are.
        stray_tolerance_m: How far a piece may stray from its pif's spine.
        min_segment_m: The shortest pif piece.
        max_turn_deg: The most a pif piece's line may turn in all.
        wall_max_length_m: The longest a GNS-only candidate may be.
        wall_height_reach_m: A pip's near drop is read this far below it.
        wall_height_quantile: A pif's wall height is this quantile of its
            pips' near drops.
        max_untiled_cells: A 1 m DEM larger than this, in cells, is searched
            tile by tile (:mod:`tiled`).
        tile_core_m: The side of a tile's core, in metres.
        tile_margin_m: The width read around each core, in metres.
    """
    find_settings = {
        "max_bends": max_bends,
        "stray_tolerance_m": stray_tolerance_m,
        "min_segment_m": min_segment_m,
        "max_turn_deg": max_turn_deg,
    }
    table_settings = {
        "end_window_m": end_window_m,
        "wall_height_reach_m": wall_height_reach_m,
        "wall_height_quantile": wall_height_quantile,
    }
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if tiles.raster_cells(dem_path(1, extent=extent)) > max_untiled_cells:
        table, elements, bbox, ground_map, buildings = find_tiled(
            extent=extent,
            use_cached_layers=use_cached_layers,
            core_m=tile_core_m,
            margin_m=tile_margin_m,
            find_settings=find_settings,
            table_settings=table_settings,
        )
    else:
        dem, transform, bbox, ground_map, group, position = get_inputs(
            extent=extent, use_cached_layers=use_cached_layers
        )
        buildings = get_nz_building_outlines(
            bbox=bbox, crs=CRS, use_cache=use_cached_layers
        )
        start = time.perf_counter()
        zones = find_instability_zones(
            dem,
            group,
            transform,
            categories={"ground_row": position},
            exclude=building_mask(buildings, transform, dem.shape),
            **find_settings,
        )
        elapsed = time.perf_counter() - start
        write_found(zones.found, extent=extent)
        describe(zones, elapsed)
        table = grid_table(zones, dem, transform, **table_settings)
        elements = element_polygons(zones.found, transform)

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
    elements.to_parquet(elements_path(extent=extent))
    print(f"Written to {WORK_DIR}")


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        gns_wall_match_m=config.GNS_WALL_MATCH_M,
        manual_wall_duplicate_m=config.MANUAL_WALL_DUPLICATE_M,
        search_m=config.SEARCH_M,
        gns_only_min_length_m=config.GNS_ONLY_MIN_LENGTH_M,
        end_window_m=config.PIF_END_WINDOW_M,
        max_bends=config.WALL_MAX_BENDS,
        stray_tolerance_m=config.WALL_STRAY_TOLERANCE_M,
        min_segment_m=config.WALL_MIN_SEGMENT_M,
        max_turn_deg=config.MAX_TOTAL_TURN_DEG,
        wall_max_length_m=config.WALL_MAX_LENGTH_M,
        wall_height_reach_m=config.WALL_HEIGHT_REACH_M,
        wall_height_quantile=config.WALL_HEIGHT_QUANTILE,
        max_untiled_cells=config.MAX_UNTILED_CELLS,
        tile_core_m=config.TILE_CORE_M,
        tile_margin_m=config.TILE_MARGIN_M,
    )
