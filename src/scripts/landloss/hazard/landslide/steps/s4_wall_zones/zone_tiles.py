"""Landslide step 4's zones, one tile at a time, for worker processes.

A worker process imports this module afresh (on Windows it does not inherit the
console's functions), so everything a tile is built with lives here, importable,
rather than in ``gen_wall_zones.py``, which is often run as a script. A worker
reads the layers every tile reads once (:func:`start_worker`), builds a tile
(:func:`build_zone_tile`), keeps its zones on disk and lets them go, so it holds
one tile's zones at a time.
"""

import os
import pickle
import time
from contextlib import contextmanager
from dataclasses import replace
from functools import partial

import geopandas as gpd
import numpy as np
import pandas as pd

from landloss.hazard.landslide.forced_polygons import gen_forced_zones
from landloss.hazard.landslide.slope_polygons import ZONES, polygon_geometries
from landloss.hazard.landslide.urban.face_polygons import ground_of_elements
from scripts.landloss.ground.steps.s3_instability_zones import tiled
from scripts.landloss.ground.steps.s3_instability_zones.grid import (
    CRS,
    element_polygons,
)
from scripts.landloss.ground.steps.s4_slope_faces.gen_slope_faces import (
    FILL_MODIFICATION,
)


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


def zone_polygons(result, *, scenario, skip=frozenset(), outlines=None):
    """Every zone of every polygon of a scenario, one row per polygon and zone.

    Args:
        result: The scenario's built polygons.
        scenario: The scenario name written on every row.
        skip: Elements whose polygons are not drawn: a tile keeps the zones of
            the elements it owns, so drawing the margin's would be thrown away.
            Each polygon is drawn from its own cells, so the others are drawn
            exactly as when none is skipped.
        outlines: A dict kept across the tile's scenarios, so a polygon whose
            cells are the same under two scenarios is drawn once
            (:func:`~landloss.hazard.landslide.slope_polygons.polygon_geometries`).
    """
    if skip:
        polygons = result.polygons[~result.polygons["element"].isin(skip)]
        cells = result.cells[result.cells["polygon"].isin(polygons.index)]
        result = replace(result, polygons=polygons, cells=cells)
    parts = []
    for zone in ZONES:
        frame = polygon_geometries(result, zone=zone, crs=CRS, cache=outlines)
        frame["zone"] = zone
        parts.append(frame)
    zones = pd.concat(parts, ignore_index=True)
    zones = zones.merge(result.polygons.reset_index(), on="polygon", how="left")
    zones = drawn_areas(gpd.GeoDataFrame(zones, geometry="geometry", crs=CRS))
    zones["scenario"] = scenario
    return zones


def drawn_areas(zones):
    """Set each polygon's areas to its drawn zones' and its depth to match.

    The zones are drawn smoothed (``polygon_geometries``), so their areas are
    not the cell counts the builder measured: ``area_m2``,
    ``imminent_area_m2`` and ``inundated_area_m2`` become the drawn areas
    (0 where a zone is not drawn), and ``depth_m`` the volume, which stays
    the cells' depths summed, over the drawn evacuated area.
    """
    drawn = zones.geometry.area
    for zone, column in (
        ("evacuated", "area_m2"),
        ("imminent", "imminent_area_m2"),
        ("inundated", "inundated_area_m2"),
    ):
        area = drawn[zones["zone"] == zone].groupby(zones["polygon"]).sum()
        zones[column] = zones["polygon"].map(area).fillna(0.0).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        zones["depth_m"] = zones["volume_m3"] / zones["area_m2"]
    return zones


def ground_rows(geometries, ground_map):
    """The ground map row (by position) under each geometry's representative point.

    -1 where no ground map polygon holds it, as an element off the map.
    """
    points = gpd.GeoDataFrame(
        geometry=geometries.representative_point().to_numpy(), crs=geometries.crs
    )
    frame = ground_map[["geometry"]].reset_index(drop=True)
    joined = gpd.sjoin(points, frame, predicate="within", how="left")
    first = joined[~joined.index.duplicated()]["index_right"]
    return first.fillna(-1).astype(np.int64).to_numpy()


def with_forced(
    result,
    scenario,
    forced,
    walled,
    is_fill,
    thickness,
    ground,
    *,
    skip=frozenset(),
    outlines=None,
):
    """A scenario's built zones with the forced polygons' zones after them.

    ``skip`` is the elements whose built polygons are not drawn and ``outlines``
    the outlines already drawn (:func:`zone_polygons`); the forced polygons are
    numbered as if all were drawn.
    """
    first = int(result.polygons.index.max()) + 1 if len(result.polygons) else 1
    zones = zone_polygons(result, scenario=scenario, skip=skip, outlines=outlines)
    zones["forced"] = False
    zones["side_unknown"] = False
    extra = gen_forced_zones(
        forced,
        walled,
        is_fill=is_fill,
        fill_thickness_m=thickness,
        ground=ground,
        first_polygon=first,
        scenario=scenario,
    )
    if extra.empty:
        return zones
    return gpd.GeoDataFrame(
        pd.concat([zones, extra], ignore_index=True), geometry="geometry", crs=zones.crs
    )


# What a worker's tiles read, set once per process by start_worker.
_worker = {}


def start_worker(
    ground_map_file, dem_file, land, buildings, units, lineless, flags, found
):
    """Read the layers every tile reads, once per worker process.

    Args:
        ground_map_file: The ground map, read here rather than sent.
        dem_file: The 1 m DEM.
        land: The coastline polygons.
        buildings: The building outlines.
        units: Every wall unit.
        lineless: The wall units no pif grew an element for, extent-wide.
        flags: Per scenario, all True, all False, or a world's walled flag per
            wall unit.
        found: The :class:`tiled.TiledFound`.
    """
    _worker.update(
        dem_file=dem_file,
        inputs={
            "land": land,
            "buildings": buildings,
            "ground_map": gpd.read_parquet(ground_map_file),
        },
        units=units,
        lineless=lineless,
        flags=flags,
        found=found,
    )


def end_worker():
    """Let go of the layers :func:`start_worker` read."""
    _worker.clear()


def write_tile_zones(zones, path):
    """Keep one tile's zones, through a temporary file so a killed run leaves no half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.partial")
    try:
        with partial.open("wb") as file:
            pickle.dump(zones, file, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def read_tile_zones(path):
    """The :class:`tiled.TileZones` :func:`write_tile_zones` kept."""
    with path.open("rb") as file:
        # Written by this step's own run under temp/, not an outside file.
        return pickle.load(file)  # noqa: S301


@contextmanager
def sharing_between_scenarios():
    """Have a tile's scenarios share what the walls do not change in the builder.

    ``tiled.zones_tile`` builds each scenario with ``build_slope_polygons``, which
    takes a ``shared`` dict for the work the scenarios' walls leave the same
    (the rays from the crest cells and each cell's distance below its crest).
    ``zones_tile`` is ground step 3's code, whose source is in that step's
    record, so it is left as it is and its builder is swapped here for one that
    passes the dict, for the length of one tile.
    """
    shared = {}
    build = tiled.build_slope_polygons

    def build_sharing(*args, **kwargs):
        return build(*args, shared=shared, **kwargs)

    tiled.build_slope_polygons = build_sharing
    try:
        yield
    finally:
        tiled.build_slope_polygons = build


def build_zone_tile(found_tile, *, path):
    """Build one tile's zones for every scenario and keep them at ``path``.

    Runs in a worker process after :func:`start_worker`, or in the main
    process for one worker. The tile's zones are dropped from memory once
    written.

    Returns:
        A summary for the progress line: ``tile``, ``n_elements`` (the tile's
        own elements) and ``seconds``.
    """
    start = time.perf_counter()
    # A grown element of a pif another tile owns is built (its ground can
    # change a neighbour's polygon) but its zones are another tile's to keep.
    margin = {
        label
        for label, key in found_tile.element_keys.items()
        if key[0] == tiled.GROWN and key[1] not in found_tile.owned_pifs
    }
    with sharing_between_scenarios():
        zones = tiled.zones_tile(
            found_tile,
            _worker["dem_file"],
            tiled=_worker["found"],
            inputs=_worker["inputs"],
            units=_worker["units"],
            lineless=_worker["lineless"],
            flags_by_scenario=_worker["flags"],
            fill_by_element=fill_by_element,
            ground_of_elements=ground_of_elements,
            ground_rows=ground_rows,
            zone_frames=partial(with_forced, skip=margin, outlines={}),
            element_polygons=element_polygons,
        )
    write_tile_zones(zones, path)
    return {
        "tile": found_tile.tile,
        "n_elements": len(zones.elements),
        "seconds": time.perf_counter() - start,
    }
