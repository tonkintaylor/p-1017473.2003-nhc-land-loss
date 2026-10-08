"""Ground step 3: find the pips, pifs, sizs and elements on the 1 m DEM, once.

    uv run --frozen python src/scripts/landloss/ground/steps/s3_instability_zones/gen_instability_zones.py

The grid work of the urban slope chain, split out of the old landslide step 12
(the lead, 2026-10-08) because it depends only on the 1 m DEM (ground step 1),
the ground map (ground step 2) and the LINZ building outlines and coastline,
and is by far the slowest part of the chain. It moved into the ground module
that day. It runs
:func:`landloss.hazard.landslide.instability_zones.find_instability_zones`
(pips, pifs cut into pieces, the siz test on each piece, the growth into
elements), tile by tile over a large extent, and the grid columns of the siz
table (:func:`grid_table`). It writes under temp/ground/:

- the found elements, ``urban-slope-found{suffix}.pkl`` (with its per-tile
  pickles on a tiled run), which landslide step 4 (``gen_wall_zones.py``) reads;
- the element polygons, ``urban-slope-elements{suffix}.parquet``;
- the siz table's grid columns, ``urban-slope-grid-sizs{suffix}.parquet``,
  which ground step 4 (``gen_slope_faces.py``) reads the wall evidence onto;
- a record of what it was built from,
  ``urban-slope-instability-zones{suffix}.json``.

On a rerun it reads the record and skips itself if nothing it depends on has
changed: the settings, the size and time of the 1 m DEM and the ground map,
and the source of the code that does the search. ``config.REBUILD`` forces a
search. Settings are in ``config.py`` beside this script, which also holds the pif and
wall line rules that ground step 4 and exposure rw step 6 read. ``gen_ground.py``
runs it.
"""

import hashlib
import inspect
import json
import pickle
import time

import geopandas as gpd
import numpy as np
import rioxarray
from rasterio import features

from landloss.common.utils import tiles
from landloss.hazard.landslide import bend_split, instability_zones, slope_elements
from landloss.hazard.landslide.instability_zones import (
    beyond_reach,
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
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_building_outlines, get_nz_coastline_polygons
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.ground.steps.s3_instability_zones import config, tiled
from scripts.landloss.paths import TEMP_DIR

CRS = 2193

WORK_DIR = TEMP_DIR / "ground"


def grid_sizs_path(*, extent):
    """Where ground step 3 writes the siz table's grid columns.

    Ground step 4 reads the wall evidence onto this table and writes the
    full siz table to :func:`siz_table_path`.
    """
    return WORK_DIR / f"urban-slope-grid-sizs{extent_suffix(extent)}.parquet"


def elements_path(*, extent):
    """Where the grown elements are written."""
    return WORK_DIR / f"urban-slope-elements{extent_suffix(extent)}.parquet"


def found_path(*, extent):
    """Where the grown elements, as found, are kept for the per-world zones."""
    return WORK_DIR / f"urban-slope-found{extent_suffix(extent)}.pkl"


def write_found(found, *, extent):
    """Keep the found elements so landslide step 4's per-world zones need not find them again."""
    with found_path(extent=extent).open("wb") as file:
        pickle.dump(found, file, protocol=pickle.HIGHEST_PROTOCOL)


def read_found(*, extent):
    """The found elements :func:`write_found` kept.

    Raises:
        FileNotFoundError: If ground step 3 has not written them.
    """
    path = found_path(extent=extent)
    if not path.exists():
        msg = f"{path} not found: run ground step 3 (gen_instability_zones.py)"
        raise FileNotFoundError(msg)
    with path.open("rb") as file:
        # Written by this step's own run under temp/, not an outside file.
        return pickle.load(file)  # noqa: S301


def dem_bbox(*, extent):
    """The bounds of the 1 m DEM, the bbox the step reads its layers on.

    The reader caches are keyed by bbox, so every script reading
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
    *,
    extent,
    use_cached_layers,
    core_m,
    margin_m,
    building_reach_m,
    find_settings,
    table_settings,
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
    n_skipped = 0
    for tile in grid:
        found = tiled.find_tile(
            dem_file,
            tile,
            inputs=inputs,
            find_settings=find_settings,
            building_reach_m=building_reach_m,
        )
        if found is None:
            n_skipped += 1
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
    print(
        f"{n_skipped} of {len(grid)} tiles skipped: no land within "
        f"{building_reach_m:,.0f} m of a building"
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
        columns=["geometry", "label"],
        crs=CRS,
    )
    frame = frame.dissolve(by="label")
    return frame.join(found.elements, how="left")


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


def describe(zones, elapsed, *, building_reach_m):
    """Print the counts and timings of the run."""
    sizs = zones.sizs
    print(
        f"{zones.n_pifs_excluded:,} pifs dropped with most of their pips in a "
        f"building outline or over {building_reach_m:,.0f} m from one, "
        f"{zones.n_pifs_short:,} with a spine under 3 m"
    )
    print(f"{int(zones.pips.mask.sum()):,} pips, {len(sizs):,} pifs, ", end="")
    print(f"{int(sizs['is_siz'].sum()):,} sizs, {len(zones.found.elements):,} elements")
    print(sizs.groupby("ground_group")["is_siz"].agg(["size", "sum"]).to_string())
    print(f"Pips to grown elements: {elapsed:.1f} s")
    print(f"Pif pieces the 50 m cap cut, by stage: {zones.cap_cuts}")


# The code the search runs: a change to any of it makes the last run stale.
SEARCH_CODE = (
    instability_zones,
    slope_elements,
    bend_split,
    tiled,
    tiles,
    get_dem,
    get_inputs,
    building_mask,
    grid_table,
    find_tiled,
    element_polygons,
)


def record_path(*, extent):
    """Where the record of what the last run was built from is written."""
    return WORK_DIR / f"urban-slope-instability-zones{extent_suffix(extent)}.json"


def outputs(*, extent):
    """The files a run writes, all of which have to exist for a skip."""
    return (
        found_path(extent=extent),
        elements_path(extent=extent),
        grid_sizs_path(extent=extent),
    )


def built_from(*, extent, settings):
    """What a run over the extent depends on, as a JSON-ready dict."""

    def stamp(path):
        stat = path.stat()
        return {
            "path": str(path),
            "bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }

    code = hashlib.sha256()
    for item in SEARCH_CODE:
        code.update(inspect.getsource(item).encode())
    return {
        "extent": extent,
        "settings": settings,
        "dem": stamp(dem_path(1, extent=extent)),
        "ground_map": stamp(ground_map_path(extent=extent)),
        "code_sha256": code.hexdigest(),
    }


def is_current(*, extent, record):
    """Whether the last run's record matches and its outputs are all there."""
    path = record_path(extent=extent)
    if not path.exists() or not all(p.exists() for p in outputs(extent=extent)):
        return False
    return json.loads(path.read_text(encoding="utf-8")) == record


def search_whole(
    *, extent, use_cached_layers, building_reach_m, find_settings, table_settings
):
    """Search the whole DEM at once; write the found elements; return the tables."""
    dem, transform, bbox, _, group, position = get_inputs(
        extent=extent, use_cached_layers=use_cached_layers
    )
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=CRS, use_cache=use_cached_layers
    )
    start = time.perf_counter()
    on_building = building_mask(buildings, transform, dem.shape)
    zones = find_instability_zones(
        dem,
        group,
        transform,
        categories={"ground_row": position},
        exclude=on_building
        | beyond_reach(on_building, abs(transform.a), building_reach_m),
        **find_settings,
    )
    write_found(zones.found, extent=extent)
    describe(zones, time.perf_counter() - start, building_reach_m=building_reach_m)
    table = grid_table(zones, dem, transform, **table_settings)
    return table, element_polygons(zones.found, transform)


def main(
    *,
    extent,
    use_cached_layers,
    rebuild,
    max_bends,
    stray_tolerance_m,
    min_segment_m,
    max_turn_deg,
    end_window_m,
    wall_height_reach_m,
    wall_height_quantile,
    building_reach_m,
    max_untiled_cells,
    tile_core_m,
    tile_margin_m,
):
    """Find the instability zones over the extent, unless the last run still holds.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ layers.
        rebuild: Whether to search again even when the last run's record matches.
        max_bends: The bends rule the pifs are cut by, as the walls are.
        stray_tolerance_m: How far a piece may stray from its pif's spine.
        min_segment_m: The shortest pif piece.
        max_turn_deg: The most a pif piece's line may turn in all.
        end_window_m: The fall direction at each end of a pif's spine is the
            mean over its pips within this many metres of the end.
        wall_height_reach_m: A pip's near drop is read this far below it.
        wall_height_quantile: A pif's wall height is this quantile of its
            pips' near drops.
        building_reach_m: A pif most of whose pips are further than this
            from every building outline is dropped.
        max_untiled_cells: A 1 m DEM larger than this, in cells, is searched
            tile by tile.
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
    tile_settings = {
        "building_reach_m": building_reach_m,
        "max_untiled_cells": max_untiled_cells,
        "tile_core_m": tile_core_m,
        "tile_margin_m": tile_margin_m,
    }
    record = built_from(
        extent=extent, settings=find_settings | table_settings | tile_settings
    )
    if not rebuild and is_current(extent=extent, record=record):
        print(
            f"Instability zones for {extent} are current "
            f"({record_path(extent=extent).name}); skipped. "
            "Set REBUILD to search again."
        )
        return

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if tiles.raster_cells(dem_path(1, extent=extent)) > max_untiled_cells:
        table, elements, *_ = find_tiled(
            extent=extent,
            use_cached_layers=use_cached_layers,
            core_m=tile_core_m,
            margin_m=tile_margin_m,
            building_reach_m=building_reach_m,
            find_settings=find_settings,
            table_settings=table_settings,
        )
    else:
        table, elements = search_whole(
            extent=extent,
            use_cached_layers=use_cached_layers,
            building_reach_m=building_reach_m,
            find_settings=find_settings,
            table_settings=table_settings,
        )
    write_siz_table(table, grid_sizs_path(extent=extent))
    elements.to_parquet(elements_path(extent=extent))
    record_path(extent=extent).write_text(
        json.dumps(record, indent=1), encoding="utf-8"
    )
    print(
        f"{len(table):,} pifs, {int(table['is_siz'].sum()):,} sizs, "
        f"{len(elements):,} elements written to {WORK_DIR}"
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        rebuild=config.REBUILD,
        max_bends=config.WALL_MAX_BENDS,
        stray_tolerance_m=config.WALL_STRAY_TOLERANCE_M,
        min_segment_m=config.WALL_MIN_SEGMENT_M,
        max_turn_deg=config.MAX_TOTAL_TURN_DEG,
        end_window_m=config.PIF_END_WINDOW_M,
        wall_height_reach_m=config.WALL_HEIGHT_REACH_M,
        wall_height_quantile=config.WALL_HEIGHT_QUANTILE,
        building_reach_m=config.BUILDING_REACH_M,
        max_untiled_cells=config.MAX_UNTILED_CELLS,
        tile_core_m=config.TILE_CORE_M,
        tile_margin_m=config.TILE_MARGIN_M,
    )
