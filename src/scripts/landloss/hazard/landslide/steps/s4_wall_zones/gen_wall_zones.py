"""Landslide step 4: the evacuated, imminent and inundated zones of the wall draws.

First every wall unit none of whose pifs grew an element (the GNS-only
units and the units of ``low_height`` pifs) gets an element along its line
(:func:`landloss.hazard.landslide.instability_zones.add_line_elements`), so
its wall has the minimum polygon too; the elements with these added are
written to ``urban-slope-wall-elements.parquet``, which landslide step 5
reads. A unit whose line found no free cell (all of them on other elements,
or off the DEM) gets its minimum polygon drawn as geometry from its line
instead, overlapping what it must
(:mod:`landloss.hazard.landslide.forced_polygons`, the lead, 2026-10-07): its
element is added to that file with the evacuated band as geometry, and its
zones are added to every zones file after the built ones. Then the zones are built twice as the bounds, every element walled
(``walled``) and none (``bare``), and once per exposure world from the wall
units exposure rw step 6 drew (``gen_wall_units.py``): an element is walled where its
pif is a member of a walled unit, or its line is a walled unit's
(:func:`landloss.hazard.landslide.wall_units.gen_element_walls`). The world
zones are what downstream reads.

Writes ``urban-slope-zones-walled.parquet``, ``urban-slope-zones-bare.parquet``
and ``urban-slope-zones-wNNN.parquet`` per world under
``temp/hazard/landslide/``. It reads the
elements ground step 3 found (``urban-slope-found.pkl``) rather than
finding them again, so the pip to element pipeline runs once per extent.

Run from the repository root::

    uv run --frozen python \
        src/scripts/landloss/hazard/landslide/steps/s4_wall_zones/gen_wall_zones.py

Run ground step 3 (``gen_instability_zones.py``) and exposure rw step 6
(``gen_wall_units.py``) first. Settings are in ``config.py``.

Over an extent ground step 3 searched in tiles the zones are built tile by tile
(:func:`build_tiled`), ``TILE_WORKERS`` tiles at once in worker processes
(:mod:`zone_tiles`). Each tile is kept on disk as it is built, so a run that
stops resumes from the tiles not yet built, and the tiles are stitched in tile
order, so the outputs do not depend on which worker finished first. A kept tile
is reused only by a run with the same record (:func:`built_from`).
"""

import hashlib
import inspect
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from landloss.common.utils import tiles
from landloss.domain import constants
from landloss.hazard.landslide import (
    bend_split,
    forced_polygons,
    instability_zones,
    pif_cut_fill,
    slope_elements,
    slope_polygons,
    susceptibility,
    wall_candidates,
    wall_units,
)
from landloss.hazard.landslide import geometry as landslide_geometry
from landloss.hazard.landslide import ground_map as landslide_ground_map
from landloss.hazard.landslide.forced_polygons import gen_forced_elements
from landloss.hazard.landslide.instability_zones import add_line_elements, with_walls
from landloss.hazard.landslide.slope_elements import restore_elements
from landloss.hazard.landslide.slope_polygons import build_slope_polygons
from landloss.hazard.landslide.urban import face_polygons, fragility
from landloss.hazard.landslide.urban import geometry as urban_geometry
from landloss.hazard.landslide.urban.face_polygons import ground_of_elements
from landloss.hazard.landslide.wall_units import gen_element_walls
from landloss.io.area_of_interest import extent_suffix
from landloss.io.readers import get_nz_building_outlines, get_nz_coastline_polygons
from scripts.landloss.exposure.rw.steps.s6_wall_population.gen_wall_units import (
    wall_draws_path,
    wall_units_path,
)
from scripts.landloss.ground.steps.s1_terrain.gen_multiscale_slope import (
    dem_path,
)
from scripts.landloss.ground.steps.s2_ground_map.gen_ground_map import (
    ground_map_path,
)
from scripts.landloss.ground.steps.s3_instability_zones import grid, tiled
from scripts.landloss.ground.steps.s3_instability_zones.gen_instability_zones import (
    CRS,
    dem_bbox,
    element_polygons,
    elements_path,
    found_path,
    get_inputs,
    read_found,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import (
    FILL_MODIFICATION,
    siz_table_path,
)
from scripts.landloss.hazard.landslide.steps.s4_wall_zones import config, zone_tiles
from scripts.landloss.hazard.landslide.steps.s4_wall_zones.zone_tiles import (
    fill_by_element,
    ground_rows,
    with_forced,
)
from scripts.landloss.paths import TEMP_DIR

WORK_DIR = TEMP_DIR / "hazard" / "landslide"
SCENARIOS = {"walled": True, "bare": False}


def wall_elements_path(*, extent):
    """Where the elements with the GNS-only wall lines added are written.

    ``gen_wall_zones.py`` writes it; landslide step 5 reads it.
    """
    return WORK_DIR / f"urban-slope-wall-elements{extent_suffix(extent)}.parquet"


def zones_path(scenario, *, extent):
    """Where the evacuated, imminent and inundated zones of a scenario are written."""
    return WORK_DIR / f"urban-slope-zones-{scenario}{extent_suffix(extent)}.parquet"


def units_without_element(units, elements):
    """The wall units none of whose pifs grew an element.

    Every wall gets a polygon (the lead, 2026-10-06): these units, the
    GNS-only units and the units of ``low_height`` pifs (a GNS mapped wall on a
    pif that is not a siz, which seeds no growth), get an element along their
    line (:func:`landloss.hazard.landslide.instability_zones.add_line_elements`).
    A low-height pif's unit takes a line element rather than growth from its pips:
    its pif failed the siz test, so growth at the siz threshold would keep
    only its own pips and measure a face the test called not steep enough,
    while the line takes the unit's own wall height and the same width floor
    as every other wall.
    """
    grown = set(elements["siz_id"].astype(np.int64))
    has_element = units["member_pif_ids"].map(
        lambda ids: any(int(i) in grown for i in ids)
    )
    return units[~has_element.to_numpy(dtype=bool)]


def describe_forced(forced, zones):
    """Print the forced polygons, those on unknown sides and those overlapping."""
    evacuated = zones[zones["zone"] == "evacuated"]
    built = evacuated[~evacuated["forced"].astype(bool)]
    own = evacuated[evacuated["forced"].astype(bool)]
    tree = shapely.STRtree(built.geometry.to_numpy())
    overlap = 0
    for geometry in own.geometry:
        near = tree.query(geometry, predicate="intersects")
        if (
            len(near)
            and shapely.area(
                shapely.intersection(geometry, built.geometry.to_numpy()[near])
            ).sum()
            > 0.01
        ):
            overlap += 1
    print(
        f"{len(forced):,} forced polygons (no free cell for a line element), "
        f"{int(forced['side_unknown'].sum()):,} with the uphill side unknown, "
        f"{overlap:,} overlapping a built polygon"
    )


def world_scenario(world_id):
    """The scenario name, and zones file tag, of one world's wall draw."""
    return f"w{world_id:03d}"


def world_walls(draws, world_id):
    """One world's walled flag per wall unit.

    Raises:
        ValueError: If the world is not in the draws.
    """
    rows = draws[draws["world_id"] == world_id]
    if rows.empty:
        msg = (
            f"world {world_id} not drawn; add it to config WORLD_IDS and rerun "
            "gen_wall_units.py"
        )
        raise ValueError(msg)
    return rows.set_index("wall_unit_id")["walled"]


# The code that builds a tile: a change to any of it makes the kept tiles stale.
# Whole modules are hashed for the values a tile reads from them (the depth and
# volume constants of ``geometry``, the ground map's materials, the minimum wall
# height of ``constants``, the grid's CRS), as ground step 3's SEARCH_CODE does.
TILE_CODE = (
    zone_tiles,
    tiled,
    tiles,
    instability_zones,
    slope_elements,
    slope_polygons,
    forced_polygons,
    wall_units,
    face_polygons,
    urban_geometry,
    bend_split,
    landslide_geometry,
    susceptibility,
    landslide_ground_map,
    pif_cut_fill,
    wall_candidates,
    fragility,
    constants,
    grid,
    units_without_element,
    world_scenario,
    world_walls,
)


def tiles_dir(*, extent):
    """The folder a tiled run keeps each tile's zones in, for a resume and the stitch."""
    return WORK_DIR / f"urban-slope-zones-tiles{extent_suffix(extent)}"


def tile_zones_path(tile, *, extent):
    """Where one tile's zones are kept."""
    return tiles_dir(extent=extent) / f"tile-{tile.row:02d}-{tile.col:02d}.pkl"


def keep_or_clear_tiles(*, extent, record, rebuild):
    """Keep the tiles an earlier run of the same record built; clear any others.

    The folder holds the run's record (:func:`built_from`), so a tile is reused
    only by a run built from the same elements, wall units and draws,
    scenarios, settings and code.

    Returns:
        How many tile files were cleared.
    """
    folder = tiles_dir(extent=extent)
    stamp = folder / "built-from.json"
    same = stamp.exists() and read_record(stamp) == record
    stale = [] if same and not rebuild else sorted(folder.glob("tile-*"))
    for path in stale:
        path.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    partial = stamp.with_name(f"{stamp.name}.partial")
    try:
        partial.write_text(json.dumps(record, indent=1), encoding="utf-8")
        os.replace(partial, stamp)
    finally:
        partial.unlink(missing_ok=True)
    return len(stale)


def read_record(path):
    """The record a run kept, or None where the file is not a whole record.

    A run killed while writing it leaves a file that is empty or cut short;
    that is not the same record as any run's, so the tiles are built again.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def rebuild_wanted(*, rebuild, use_cached_layers):
    """Whether every tile is built again whatever the record says.

    The record holds the code and the files the tiles are built from, not the
    LINZ coastline and building layers every tile reads. Fetching them again
    (``use_cached_layers`` False) may change them, so it rebuilds.
    """
    return rebuild or not use_cached_layers


def tile_settings(*, extent, scenarios, world_ids):
    """The settings a tile is built with, for the record.

    Besides the extent, scenarios and worlds, the name of the fill modification the
    tiles read from ground step 4's slope faces module, which is too broad to hash.
    """
    return {
        "extent": extent,
        "scenarios": list(scenarios),
        "world_ids": [int(world_id) for world_id in world_ids],
        "fill_modification": FILL_MODIFICATION,
    }


def built_from(*, hashed, stamped, settings, code):
    """What a tiled run depends on, as a JSON-ready dict.

    Args:
        hashed: Name to path of the small inputs, recorded by the hash of their
            content: the found elements, the wall units and the draws.
        stamped: Name to path of the large inputs, recorded by size and time
            modified: the 1 m DEM, the ground map and the tiles' found
            elements.
        settings: The scenarios and worlds, and any setting the tiles are built
            with.
        code: The modules and functions that build a tile; the record holds
            the hash of their source.
    """

    def digest(path):
        sha = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1 << 20), b""):
                sha.update(block)
        return sha.hexdigest()

    def stamp(path):
        stat = path.stat()
        return {"bytes": stat.st_size, "modified_ns": stat.st_mtime_ns}

    source = hashlib.sha256()
    for item in code:
        source.update(inspect.getsource(item).encode())
    return {
        "hashed": {name: digest(path) for name, path in hashed.items()},
        "stamped": {name: stamp(path) for name, path in stamped.items()},
        "settings": settings,
        "code_sha256": source.hexdigest(),
    }


def tiles_to_build(found, *, extent):
    """The tiles of the found elements whose zones are not yet kept."""
    return [
        found_tile
        for found_tile in found.tiles
        if not tile_zones_path(found_tile.tile, extent=extent).exists()
    ]


def read_kept_tiles(found, *, extent):
    """Every tile's kept zones, in tile order, whichever order they were built."""
    return [
        zone_tiles.read_tile_zones(tile_zones_path(found_tile.tile, extent=extent))
        for found_tile in found.tiles
    ]


def describe_tile(summary, *, number, total, elapsed):
    """The progress line of a tile that is done."""
    tile = summary["tile"]
    return (
        f"  [{number}/{total}] tile {tile.row},{tile.col}: "
        f"{summary['n_elements']:,} elements ({summary['seconds']:,.0f} s; "
        f"{elapsed:,.0f} s in all)"
    )


def run_tiles(todo, *, workers, start_args, tile_kwargs):
    """Build the tiles not yet kept, in worker processes, printing each as it lands.

    Each tile is written to disk by :func:`zone_tiles.build_zone_tile` and
    dropped from memory, so a worker holds one tile at a time. With one worker
    the tiles run here, in order, without a pool. A tile that fails stops the
    run; the tiles already kept stay for the next one.
    """
    start = time.perf_counter()

    def report(number, summary):
        print(
            describe_tile(
                summary,
                number=number,
                total=len(todo),
                elapsed=time.perf_counter() - start,
            ),
            flush=True,
        )

    if workers == 1:
        zone_tiles.start_worker(*start_args)
        try:
            for number, (found_tile, kwargs) in enumerate(
                zip(todo, tile_kwargs, strict=True), 1
            ):
                report(number, zone_tiles.build_zone_tile(found_tile, **kwargs))
        finally:
            zone_tiles.end_worker()
        return
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=zone_tiles.start_worker,
        initargs=start_args,
    ) as pool:
        futures = [
            pool.submit(zone_tiles.build_zone_tile, found_tile, **kwargs)
            for found_tile, kwargs in zip(todo, tile_kwargs, strict=True)
        ]
        try:
            for number, future in enumerate(as_completed(futures), 1):
                report(number, future.result())
        except BaseException:
            # The tiles already written stay on disk for the next run.
            pool.shutdown(wait=False, cancel_futures=True)
            raise


def build_tiled(
    found,
    units,
    draws,
    *,
    extent,
    use_cached_layers,
    world_ids,
    rebuild,
    workers,
):
    """Build every scenario's zones tile by tile and write them stitched.

    The tiled counterpart of :func:`main`'s own pass, for an extent ground
    step 3 searched in tiles (:mod:`tiled`): each tile adds the line and
    forced elements of the wall units that reach it and builds every
    scenario, keeping what it owns, and the tiles are numbered into one set
    of elements and one zones file per scenario. ``workers`` tiles are built
    at once (:func:`run_tiles`); each is kept on disk as it is built, so a
    stopped run resumes from the tiles not yet built, and the stitch reads
    them in tile order.
    """
    elements_file = elements_path(extent=extent)
    lineless = units_without_element(units, gpd.read_parquet(elements_file))
    missed = tiled.units_on_no_tile(found, lineless)
    if len(missed):
        print(
            f"{len(missed):,} wall units with no element are on no searched tile "
            f"(beyond the ground searched near the buildings) and get no forced "
            f"element: {missed['unit_source'].value_counts().to_dict()}"
        )
    flags = dict(SCENARIOS.items())
    for world_id in world_ids:
        flags[world_scenario(world_id)] = world_walls(draws, world_id)
    dem_file = dem_path(1, extent=extent)
    ground_map_file = ground_map_path(extent=extent)
    found_tile_files = {
        f"found-tile-{t.tile.row:02d}-{t.tile.col:02d}": t.path for t in found.tiles
    }
    record = built_from(
        hashed={
            "found": found_path(extent=extent),
            "units": wall_units_path(extent=extent),
            "draws": wall_draws_path(extent=extent),
        },
        stamped={
            "dem": dem_file,
            "ground_map": ground_map_file,
            "elements": elements_file,
            **found_tile_files,
        },
        settings=tile_settings(extent=extent, scenarios=flags, world_ids=world_ids),
        code=TILE_CODE,
    )
    n_cleared = keep_or_clear_tiles(
        extent=extent,
        record=record,
        rebuild=rebuild_wanted(rebuild=rebuild, use_cached_layers=use_cached_layers),
    )
    if n_cleared:
        print(f"Cleared {n_cleared} tile files from an earlier, different run")
    todo = tiles_to_build(found, extent=extent)
    workers = min(workers, max(len(todo), 1))
    print(
        f"{len(found.tiles)} tiles: {len(found.tiles) - len(todo)} kept by an "
        f"earlier run, {len(todo)} to build on {workers} worker(s)"
    )
    if todo:
        bbox = dem_bbox(extent=extent)
        land = get_nz_coastline_polygons(
            bbox=bbox, crs=CRS, use_cache=use_cached_layers
        )
        buildings = get_nz_building_outlines(
            bbox=bbox, crs=CRS, use_cache=use_cached_layers
        )
        run_tiles(
            todo,
            workers=workers,
            start_args=(
                ground_map_file,
                dem_file,
                land,
                buildings,
                units,
                lineless,
                flags,
                found,
            ),
            tile_kwargs=[
                {"path": tile_zones_path(found_tile.tile, extent=extent)}
                for found_tile in todo
            ],
        )
    tile_zones = read_kept_tiles(found, extent=extent)
    labels = tiled.label_keys(found, tile_zones)
    tiled.stitch_elements(tile_zones, labels).to_parquet(
        wall_elements_path(extent=extent)
    )
    for scenario in flags:
        zones = tiled.stitch_zones(tile_zones, labels, scenario)
        zones.to_parquet(zones_path(scenario, extent=extent))
        evacuated = zones[zones["zone"] == "evacuated"]
        print(
            f"{scenario}: {evacuated['polygon'].nunique():,} polygons, "
            f"{evacuated['area_m2'].sum():,.0f} m2 evacuated"
        )


def main(*, extent, use_cached_layers, world_ids, rebuild, tile_workers):
    """Build and write the zones of each world's wall draw.

    Args:
        extent: The build extent (``landloss.io.area_of_interest.EXTENTS``).
        use_cached_layers: Whether to reuse the cached LINZ layers.
        world_ids: The exposure worlds to build; each must be in the draws.
        rebuild: Whether to build every tile again even when the kept tiles'
            record matches (a tiled extent only).
        tile_workers: How many tiles are built at once, each in its own
            process (a tiled extent only). Not part of the record: it does not
            change the result.

    Raises:
        ValueError: If ground step 3 or 4 was run again after the wall units
            were built, so the units may name other pifs, or a world is not
            in the draws.
    """
    units_path = wall_units_path(extent=extent)
    for upstream in (found_path(extent=extent), siz_table_path(extent=extent)):
        if upstream.exists() and upstream.stat().st_mtime > units_path.stat().st_mtime:
            msg = (
                f"{upstream.name} is newer than the wall units; rerun gen_wall_units.py"
            )
            raise ValueError(msg)
    units = gpd.read_parquet(units_path)
    draws = pd.read_parquet(wall_draws_path(extent=extent))
    found = read_found(extent=extent)
    if isinstance(found, tiled.TiledFound):
        build_tiled(
            found,
            units,
            draws,
            extent=extent,
            use_cached_layers=use_cached_layers,
            world_ids=world_ids,
            rebuild=rebuild,
            workers=tile_workers,
        )
        return
    dem, transform, _, ground_map, group, position = get_inputs(
        extent=extent, use_cached_layers=use_cached_layers
    )
    found = restore_elements(found, dem, abs(transform.a))
    lineless = units_without_element(units, found.elements)
    found = add_line_elements(
        found,
        lineless.geometry,
        lineless["height_m"],
        dem=dem,
        ground_group=group,
        transform=transform,
        categories={"ground_row": position},
    )
    elements = found.elements
    on_line = elements["wall_unit_id"].notna()
    print(
        f"{len(lineless):,} wall units with no element "
        f"({lineless['unit_source'].value_counts().to_dict()}, "
        f"{int((~lineless['is_siz']).sum()):,} with no siz); "
        f"{int(on_line.sum()):,} given an element along their line (the rest "
        "lie on another element or off the DEM)"
    )
    still = lineless[~lineless.index.isin(elements["wall_unit_id"].dropna())]
    forced = gen_forced_elements(
        still.geometry,
        still["height_m"],
        dem=dem,
        transform=transform,
        first_label=int(elements.index.max()) + 1 if len(elements) else 1,
    )
    forced["majority_ground_row"] = ground_rows(forced.geometry, ground_map)
    forced_fill, forced_thickness = fill_by_element(forced, ground_map)
    forced_ground = ground_of_elements(forced, ground_map)
    element_frame = element_polygons(found, transform)
    element_frame["forced"] = False
    element_frame = gpd.GeoDataFrame(
        pd.concat([element_frame, forced.drop(columns=["line"]).assign(forced=True)]),
        geometry="geometry",
        crs=element_frame.crs,
    )
    element_frame.to_parquet(wall_elements_path(extent=extent))
    is_fill, thickness = fill_by_element(elements, ground_map)
    # The ground each element's Kingsbury zone, and so its seismic runout, is
    # scored on (as landslide step 5 scores it).
    element_ground = ground_of_elements(elements, ground_map)
    in_unit = elements["siz_id"].isin(units["member_pif_ids"].explode().dropna())
    print(
        "Elements of a siz whose pif is in no wall unit: "
        f"{int((~in_unit & ~on_line).sum()):,}"
    )

    for scenario, walled in SCENARIOS.items():
        result = build_slope_polygons(
            with_walls(found, walled),
            dem,
            transform,
            is_fill=is_fill,
            fill_thickness_m=thickness,
            element_ground=element_ground,
        )
        zones = with_forced(
            result,
            scenario,
            forced,
            pd.Series(walled, index=forced.index),
            forced_fill,
            forced_thickness,
            forced_ground,
        )
        zones.to_parquet(zones_path(scenario, extent=extent))
        if scenario == "walled":
            describe_forced(forced, zones)
        print(
            f"{scenario}: {len(result.polygons):,} polygons, "
            f"{result.polygons['area_m2'].sum():,.0f} m2 evacuated"
        )

    for world_id in world_ids:
        rows = draws[draws["world_id"] == world_id]
        if rows.empty:
            msg = (
                f"world {world_id} not drawn; add it to config WORLD_IDS and rerun "
                "gen_wall_units.py"
            )
            raise ValueError(msg)
        walled = rows.set_index("wall_unit_id")["walled"]
        flags = gen_element_walls(units, walled, elements)
        result = build_slope_polygons(
            with_walls(found, flags),
            dem,
            transform,
            is_fill=is_fill,
            fill_thickness_m=thickness,
            element_ground=element_ground,
        )
        scenario = world_scenario(world_id)
        forced_walled = pd.Series(
            forced["wall_unit_id"].map(walled).fillna(value=False).to_numpy(dtype=bool),
            index=forced.index,
        )
        with_forced(
            result,
            scenario,
            forced,
            forced_walled,
            forced_fill,
            forced_thickness,
            forced_ground,
        ).to_parquet(zones_path(scenario, extent=extent))
        print(
            f"World {world_id}: {flags.mean():.1%} of elements walled, "
            f"{len(result.polygons):,} polygons, "
            f"{result.polygons['area_m2'].sum():,.0f} m2 evacuated"
        )


if __name__ == "__main__":
    main(
        extent=config.EXTENT,
        use_cached_layers=config.USE_CACHED_LAYERS,
        world_ids=config.WORLD_IDS,
        rebuild=config.REBUILD,
        tile_workers=config.TILE_WORKERS,
    )
