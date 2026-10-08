"""Landslide step 14: find the pips, pifs, sizs and elements on the 1 m DEM, once.

    uv run --frozen python src/scripts/landloss/hazard/landslide/steps/s14_instability_zones/gen_instability_zones.py

The grid work of the urban slope chain, split out of step 12 (the lead,
2026-10-08) because it depends only on the 1 m DEM (step 3), the ground map
(step 4) and the LINZ building outlines and coastline, and is by far the
slowest part of the chain. It runs
:func:`landloss.hazard.landslide.instability_zones.find_instability_zones`
(pips, pifs cut into pieces, the siz test on each piece, the growth into
elements), tile by tile over a large extent, and the grid columns of the siz
table (step 12's ``grid_table``). It writes:

- the found elements, ``urban-slope-found{suffix}.pkl`` (with its per-tile
  pickles on a tiled run), which step 12's wall zones read;
- the element polygons, ``urban-slope-elements{suffix}.parquet``;
- the siz table's grid columns, ``urban-slope-grid-sizs{suffix}.parquet``,
  which step 12's faces script reads the wall evidence onto;
- a record of what it was built from,
  ``urban-slope-instability-zones{suffix}.json``.

On a rerun it reads the record and skips itself if nothing it depends on has
changed: the settings, the size and time of the 1 m DEM and the ground map,
and the source of the code that does the search. ``config.REBUILD`` forces a
search. Settings are in ``config.py`` beside this script and step 12's.
"""

import hashlib
import inspect
import json
import time

from landloss.common.utils import tiles
from landloss.hazard.landslide import bend_split, instability_zones, slope_elements
from landloss.hazard.landslide.instability_zones import (
    find_instability_zones,
    write_siz_table,
)
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_building_outlines
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.hazard.landslide.steps.s4_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    config as faces_config,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import (
    gen_urban_slope_faces as faces,
)
from scripts.landloss.hazard.landslide.steps.s12_urban_slope_faces import tiled
from scripts.landloss.hazard.landslide.steps.s14_instability_zones import config

# The code the search runs: a change to any of it makes the last run stale.
SEARCH_CODE = (
    instability_zones,
    slope_elements,
    bend_split,
    tiled,
    tiles,
    faces.get_dem,
    faces.get_inputs,
    faces.building_mask,
    faces.grid_table,
    faces.find_tiled,
    faces.element_polygons,
)


def record_path(*, extent):
    """Where the record of what the last run was built from is written."""
    return faces.WORK_DIR / f"urban-slope-instability-zones{extent_suffix(extent)}.json"


def outputs(*, extent):
    """The files a run writes, all of which have to exist for a skip."""
    return (
        faces.found_path(extent=extent),
        faces.elements_path(extent=extent),
        faces.grid_sizs_path(extent=extent),
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


def search_whole(*, extent, use_cached_layers, find_settings, table_settings):
    """Search the whole DEM at once; write the found elements; return the tables."""
    dem, transform, bbox, _, group, position = faces.get_inputs(
        extent=extent, use_cached_layers=use_cached_layers
    )
    buildings = get_nz_building_outlines(
        bbox=bbox, crs=faces.CRS, use_cache=use_cached_layers
    )
    start = time.perf_counter()
    zones = find_instability_zones(
        dem,
        group,
        transform,
        categories={"ground_row": position},
        exclude=faces.building_mask(buildings, transform, dem.shape),
        **find_settings,
    )
    faces.write_found(zones.found, extent=extent)
    faces.describe(zones, time.perf_counter() - start)
    table = faces.grid_table(zones, dem, transform, **table_settings)
    return table, faces.element_polygons(zones.found, transform)


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

    faces.WORK_DIR.mkdir(parents=True, exist_ok=True)
    if tiles.raster_cells(dem_path(1, extent=extent)) > max_untiled_cells:
        table, elements, *_ = faces.find_tiled(
            extent=extent,
            use_cached_layers=use_cached_layers,
            core_m=tile_core_m,
            margin_m=tile_margin_m,
            find_settings=find_settings,
            table_settings=table_settings,
        )
    else:
        table, elements = search_whole(
            extent=extent,
            use_cached_layers=use_cached_layers,
            find_settings=find_settings,
            table_settings=table_settings,
        )
    write_siz_table(table, faces.grid_sizs_path(extent=extent))
    elements.to_parquet(faces.elements_path(extent=extent))
    record_path(extent=extent).write_text(
        json.dumps(record, indent=1), encoding="utf-8"
    )
    print(
        f"{len(table):,} pifs, {int(table['is_siz'].sum()):,} sizs, "
        f"{len(elements):,} elements written to {faces.WORK_DIR}"
    )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        rebuild=config.REBUILD,
        max_bends=faces_config.WALL_MAX_BENDS,
        stray_tolerance_m=faces_config.WALL_STRAY_TOLERANCE_M,
        min_segment_m=faces_config.WALL_MIN_SEGMENT_M,
        max_turn_deg=faces_config.MAX_TOTAL_TURN_DEG,
        end_window_m=faces_config.PIF_END_WINDOW_M,
        wall_height_reach_m=faces_config.WALL_HEIGHT_REACH_M,
        wall_height_quantile=faces_config.WALL_HEIGHT_QUANTILE,
        max_untiled_cells=config.MAX_UNTILED_CELLS,
        tile_core_m=config.TILE_CORE_M,
        tile_margin_m=config.TILE_MARGIN_M,
    )
