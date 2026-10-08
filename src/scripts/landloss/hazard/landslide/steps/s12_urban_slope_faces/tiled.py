"""Step 12's grid work tile by tile, for an extent whose 1 m DEM is too large.

The faces and the wall zones hold the whole 1 m DEM and a stack of layers grown
from it, which over a territorial authority is more memory than there is. Over
such an extent (``config.MAX_UNTILED_CELLS``) the two grid passes run on tiles
of the DEM (:mod:`landloss.common.utils.tiles`) and everything after them runs
once, on the stitched tables, as it does over a pilot.

Ownership. A tile reads its core and a margin of ``config.TILE_MARGIN_M``. A
pif belongs to the tile whose core holds the centre of its parent's pips, so a
parent (and every piece cut from it) is kept from the one tile that saw it
whole; the margin is wider than the longest parent on the pilots. An element
belongs to the tile that owns the pif it grew from; a line or forced element to
the tile whose core holds its wall unit's line; a polygon to the tile that owns
its element.

Ids. A tile numbers its pifs, elements and polygons from 1, so each is matched
to one global id by something no tile changes: a pif by its pips' cells, a
grown element by its pif, a line or forced element by its wall unit. A copy of
a pif or element in another tile's margin carries the same global id, so a
wall drawn on it reaches every tile it is seen in. A pif cut short by the edge
of a margin matches nothing and is dropped there.
"""

import pickle
from dataclasses import dataclass, field, replace
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from rasterio import features
from rasterio.transform import Affine

from landloss.common.utils import tiles
from landloss.hazard.landslide.forced_polygons import gen_forced_elements
from landloss.hazard.landslide.instability_zones import (
    add_line_elements,
    find_instability_zones,
    with_walls,
)
from landloss.hazard.landslide.slope_elements import rasterise_ground_map
from landloss.hazard.landslide.slope_polygons import build_slope_polygons
from landloss.hazard.landslide.wall_units import gen_element_walls

# How finely a pip's coordinates are compared between two tiles, in metres. A
# pip is a cell centre, so two tiles agree to far better than this.
_KEY_DECIMALS = 3

# The element kinds a key names: grown from a pif, on a wall unit's line, or
# forced from a wall unit's line.
GROWN, LINE, FORCED = "grown", "line", "forced"


@dataclass
class FoundTile:
    """One tile's elements as found, and how its ids map onto the extent's.

    Attributes:
        tile: The tile.
        path: The pickle of the tile's ``SlopeElements``.
        pif_ids: Each local pif id seen whole, to its global id.
        element_keys: Each local grown element label, to its key
            ``(GROWN, global pif id)``; an element of an unmatched pif is
            absent.
        owned_pifs: The global ids of the pifs this tile owns.
    """

    tile: tiles.Tile
    path: Path
    pif_ids: dict[int, int] = field(default_factory=dict)
    element_keys: dict[int, tuple] = field(default_factory=dict)
    owned_pifs: set[int] = field(default_factory=set)


@dataclass
class TiledFound:
    """What the tiled faces pass keeps for the tiled wall zones pass.

    Attributes:
        transform: The whole DEM's transform.
        tiles: Each tile's elements and id maps.
        labels: The global label of each grown element key.
    """

    transform: Affine
    tiles: list[FoundTile]
    labels: dict[tuple, int]


def tile_inputs(dem_file, tile, *, land, ground_map, buildings):
    """One tile's DEM (sea masked), ground groups, ground rows and building mask.

    Returns:
        ``(dem, transform, group, position, buildings_mask)``, on the tile's
        outer window. ``position`` is the row of the whole ground map.
    """
    window = tiles.read_window(dem_file, tile.outer)
    dem = window.to_numpy().astype("float64")
    transform = window.rio.transform()
    minx, miny, maxx, maxy = window.rio.bounds()
    on_land = _burn(land.cx[minx:maxx, miny:maxy], transform, dem.shape)
    dem = np.where(on_land, dem, np.nan)
    near = ground_map.cx[minx:maxx, miny:maxy]
    group, position = rasterise_ground_map(
        near, transform, dem.shape, fill_as_soil=True
    )
    rows = ground_map.index.get_indexer(near.index)
    position = np.where(position >= 0, rows[np.maximum(position, 0)], -1).astype(
        np.int32
    )
    on_building = _burn(buildings.cx[minx:maxx, miny:maxy], transform, dem.shape)
    return dem, transform, group, position, on_building


def _burn(frame, transform, shape):
    """True on the cells whose centre lies in one of the frame's polygons."""
    if frame.empty:
        return np.zeros(shape, dtype=bool)
    return features.rasterize(
        [(geometry, 1) for geometry in frame.geometry],
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype="uint8",
    ).astype(bool)


def pip_keys(table):
    """A key per pif that every tile seeing the pif whole computes alike."""
    rounded = shapely.set_precision(table.geometry.to_numpy(), 10.0**-_KEY_DECIMALS)
    return pd.Series(
        [shapely.to_wkb(shapely.normalize(g)) for g in rounded], index=table.index
    )


def owned_parents(table, core_bounds):
    """The local parent ids whose pips' centre lies in the tile's core."""
    bounds = table.geometry.bounds.assign(parent=table["parent_pif_id"].to_numpy())
    box = bounds.groupby("parent").agg(
        minx=("minx", "min"),
        miny=("miny", "min"),
        maxx=("maxx", "max"),
        maxy=("maxy", "max"),
    )
    centres = gpd.GeoDataFrame(
        geometry=gpd.points_from_xy(
            (box["minx"] + box["maxx"]) / 2, (box["miny"] + box["maxy"]) / 2
        ),
        index=box.index,
    )
    return set(box.index[tiles.owned_by(centres, core_bounds)])


def globalise_found(records, transform):
    """Number the owned pifs and elements across tiles and map every tile onto them.

    Args:
        records: Per tile, in tile order: ``tile``, ``path``, the ``table``
            (siz table with the grid columns), ``elements`` (element polygons,
            indexed by local label) and ``owned`` (local parent ids owned).
        transform: The whole DEM's transform.

    Returns:
        ``(found, table, elements)``: the :class:`TiledFound`, and the owned
        pifs and owned elements of every tile with global ids, grid indices
        moved onto the whole DEM.
    """
    key_to_pif: dict[bytes, int] = {}
    parent_ids: dict[tuple[int, int], int] = {}
    owned_tables = []
    for number, record in enumerate(records):
        table = record["table"]
        keys = pip_keys(table)
        # A parent longer than the margin is seen whole by no tile, and each
        # tile's cut of it has its own centre, so two tiles can both claim it.
        # A piece is kept by the first tile to claim it.
        mine = table["parent_pif_id"].isin(record["owned"]).to_numpy()
        mine = mine & ~keys.isin(key_to_pif.keys()).to_numpy()
        for local in table.index[mine]:
            key_to_pif[keys[local]] = len(key_to_pif) + 1
        for parent in sorted(record["owned"]):
            parent_ids[(number, parent)] = len(parent_ids) + 1
        record["keys"] = keys
        record["mine"] = mine
    found_tiles = []
    labels: dict[tuple, int] = {}
    owned_elements = []
    for number, record in enumerate(records):
        table, keys = record["table"], record["keys"]
        pif_ids = {
            local: key_to_pif[key] for local, key in keys.items() if key in key_to_pif
        }
        owned = table.loc[record["mine"]].copy()
        owned.index = pd.Index([pif_ids[i] for i in owned.index], name=table.index.name)
        owned["parent_pif_id"] = [
            parent_ids[(number, p)] for p in owned["parent_pif_id"]
        ]
        owned_tables.append(owned)
        elements = record["elements"]
        element_keys = {
            label: (GROWN, pif_ids[siz])
            for label, siz in elements["siz_id"].items()
            if siz in pif_ids
        }
        owned_pifs = set(owned.index)
        found_tiles.append(
            FoundTile(record["tile"], record["path"], pif_ids, element_keys, owned_pifs)
        )
        mine = [
            label
            for label, key in element_keys.items()
            if key[1] in owned_pifs and key not in labels
        ]
        for label in mine:
            labels[element_keys[label]] = len(labels) + 1
        kept = elements.loc[mine].copy()
        kept["siz_id"] = [element_keys[label][1] for label in mine]
        kept = _to_whole_grid(kept, record["tile"])
        kept.index = pd.Index(
            [labels[element_keys[label]] for label in mine], name="label"
        )
        owned_elements.append(kept)
    table = pd.concat(owned_tables).sort_index()
    elements = pd.concat(owned_elements).sort_index()
    return (
        TiledFound(transform, found_tiles, labels),
        gpd.GeoDataFrame(table, geometry="geometry", crs=records[0]["table"].crs),
        gpd.GeoDataFrame(elements, geometry="geometry", crs=records[0]["elements"].crs),
    )


def _to_whole_grid(frame, tile):
    """Move a tile's seed rows and columns onto the whole DEM's grid."""
    frame = frame.copy()
    seeded = frame["seed_row"] >= 0
    frame.loc[seeded, "seed_row"] += tile.outer.row_off
    frame.loc[seeded, "seed_col"] += tile.outer.col_off
    return frame


def read_tile_found(found_tile):
    """The ``SlopeElements`` one tile found."""
    with found_tile.path.open("rb") as file:
        # Written by this step's own run under temp/, not an outside file.
        return pickle.load(file)  # noqa: S301


def write_tile_found(found, path):
    """Keep one tile's ``SlopeElements`` for the wall zones pass."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as file:
        pickle.dump(found, file, protocol=pickle.HIGHEST_PROTOCOL)


def find_tile(dem_file, tile, *, inputs, find_settings):
    """Find one tile's pips, pifs, sizs and elements."""
    dem, transform, group, position, on_building = tile_inputs(dem_file, tile, **inputs)
    if not np.isfinite(dem).any():
        return None
    zones = find_instability_zones(
        dem,
        group,
        transform,
        categories={"ground_row": position},
        exclude=on_building,
        **find_settings,
    )
    return zones, dem, transform


@dataclass
class TileZones:
    """One tile's share of a scenario's zones and the elements behind them."""

    zones: dict[str, gpd.GeoDataFrame]
    elements: gpd.GeoDataFrame


def line_keys(found, first_new_label):
    """The key of each line element ``add_line_elements`` appended."""
    elements = found.elements
    added = elements.loc[elements.index >= first_new_label]
    return {
        label: (LINE, int(unit))
        for label, unit in added["wall_unit_id"].items()
        if pd.notna(unit)
    }


def zones_tile(
    found_tile,
    dem_file,
    *,
    tiled,
    inputs,
    units,
    lineless,
    flags_by_scenario,
    fill_by_element,
    ground_of_elements,
    ground_rows,
    zone_frames,
    element_polygons,
):
    """Build one tile's zones for every scenario, keeping what the tile owns.

    Args:
        found_tile: The tile's :class:`FoundTile`.
        dem_file: The 1 m DEM.
        tiled: The :class:`TiledFound`.
        inputs: The layers `tile_inputs` reads.
        units: Every wall unit, with ``member_pif_ids`` in global pif ids.
        lineless: The wall units no pif grew an element for, extent-wide.
        flags_by_scenario: Per scenario, all True, all False, or a world's
            walled flag per wall unit.
        fill_by_element: The step's ``fill_by_element``.
        ground_of_elements: The ground each element's Kingsbury zone is
            scored on
            (:func:`landloss.hazard.landslide.urban.face_polygons.ground_of_elements`).
        ground_rows: The wall zones script's ``ground_rows``.
        zone_frames: Builds a scenario's zone rows from the built polygons and
            the forced elements: ``(result, scenario, forced, walled, is_fill,
            thickness, ground) -> GeoDataFrame``.
        element_polygons: The step's ``element_polygons``.

    Returns:
        A :class:`TileZones` with element and polygon ids still local, and
        per element its key in ``element_key``.
    """
    tile = found_tile.tile
    dem, transform, group, position, _ = tile_inputs(dem_file, tile, **inputs)
    found = read_tile_found(found_tile)
    elements = found.elements.copy()
    keys = dict(found_tile.element_keys)
    elements["siz_id"] = [keys.get(label, (None, 0))[1] for label in elements.index]
    found = replace(found, elements=elements)

    outer = shapely.box(*tiles.window_bounds(tile.outer, tiled.transform))
    here = lineless[lineless.geometry.intersects(outer)]
    first_new = int(found.elements.index.max()) + 1 if len(found.elements) else 1
    found = add_line_elements(
        found,
        here.geometry,
        here["height_m"],
        dem=dem,
        ground_group=group,
        transform=transform,
        categories={"ground_row": position},
    )
    keys.update(line_keys(found, first_new))
    on_line = set(found.elements["wall_unit_id"].dropna().astype(np.int64))
    still = here[~here.index.isin(on_line)]
    first_forced = int(found.elements.index.max()) + 1 if len(found.elements) else 1
    forced = gen_forced_elements(
        still.geometry,
        still["height_m"],
        dem=dem,
        transform=transform,
        first_label=first_forced,
    )
    forced["majority_ground_row"] = ground_rows(forced.geometry, inputs["ground_map"])
    for label, unit in forced["wall_unit_id"].items():
        keys[label] = (FORCED, int(unit))
    forced_fill, forced_thickness = fill_by_element(forced, inputs["ground_map"])
    forced_ground = ground_of_elements(forced, inputs["ground_map"])

    owned_units = set(here.index[tiles.owned_by(here, tile.core_bounds)])
    owned = {
        label
        for label, key in keys.items()
        if (key[0] == GROWN and key[1] in found_tile.owned_pifs)
        or (key[0] in (LINE, FORCED) and key[1] in owned_units)
    }

    is_fill, thickness = fill_by_element(found.elements, inputs["ground_map"])
    element_ground = ground_of_elements(found.elements, inputs["ground_map"])
    zones = {}
    for scenario, walled in flags_by_scenario.items():
        if isinstance(walled, bool):
            flags = walled
            forced_walled = pd.Series(walled, index=forced.index)
        else:
            flags = gen_element_walls(units, walled, found.elements)
            forced_walled = pd.Series(
                forced["wall_unit_id"]
                .map(walled)
                .fillna(value=False)
                .to_numpy(dtype=bool),
                index=forced.index,
            )
        result = build_slope_polygons(
            with_walls(found, flags),
            dem,
            transform,
            is_fill=is_fill,
            fill_thickness_m=thickness,
            element_ground=element_ground,
        )
        frame = zone_frames(
            result,
            scenario,
            forced,
            forced_walled,
            forced_fill,
            forced_thickness,
            forced_ground,
        )
        frame = frame[frame["element"].isin(owned)].copy()
        zones[scenario] = _key_elements(frame, keys)

    element_frame = _element_frame(
        element_polygons(found, transform), forced, owned, keys, tile
    )
    return TileZones(zones, element_frame)


def _key_elements(frame, keys):
    """Replace a zones frame's element labels with their keys."""
    frame["element_key"] = frame["element"].map(keys)
    if "top_element" in frame:
        frame["top_element_key"] = frame["top_element"].map(keys)
    return frame


def _element_frame(frame, forced, owned, keys, tile):
    """The tile's owned elements, grown, line and forced, as polygons."""
    frame["forced"] = False
    frame = gpd.GeoDataFrame(
        pd.concat([frame, forced.drop(columns=["line"]).assign(forced=True)]),
        geometry="geometry",
        crs=frame.crs,
    )
    frame = frame.loc[[label for label in frame.index if label in owned]]
    frame = _to_whole_grid(frame, tile)
    frame["element_key"] = [keys[label] for label in frame.index]
    return frame


def label_keys(tiled, tile_zones):
    """Give every element key a global label: grown first, then line, then forced.

    Grown elements keep the labels the faces pass gave them; line and forced
    elements follow, ordered by wall unit, as the untiled pass numbers them
    after the grown ones.
    """
    labels = dict(tiled.labels)
    extra = sorted(
        {
            key
            for zones in tile_zones
            for key in zones.elements["element_key"]
            if key[0] != GROWN
        },
        key=lambda key: (key[0] != LINE, key[1]),
    )
    for key in extra:
        labels[key] = len(labels) + 1
    return labels


def stitch_zones(tile_zones, labels, scenario):
    """One scenario's zones over every tile, with global element and polygon ids.

    The built polygons come first and the forced ones after, as in the
    untiled pass, each numbered from where the last left off.
    """
    frames = [zones.zones[scenario] for zones in tile_zones]
    frames = [frame for frame in frames if len(frame)]
    if not frames:
        return gpd.GeoDataFrame()
    parts = []
    for number, frame in enumerate(frames):
        frame = frame.copy()
        frame["_tile"] = number
        parts.append(frame)
    zones = pd.concat(parts, ignore_index=True)
    zones["element"] = zones["element_key"].map(labels).astype("int64")
    if "top_element_key" in zones:
        zones["top_element"] = zones["top_element_key"].map(labels)
    order = zones[["forced", "_tile", "polygon"]].drop_duplicates()
    order = order.sort_values(["forced", "_tile", "polygon"]).reset_index(drop=True)
    order["global_polygon"] = np.arange(1, len(order) + 1)
    zones = zones.merge(order, on=["forced", "_tile", "polygon"], how="left")
    zones["polygon"] = zones.pop("global_polygon")
    zones = zones.drop(
        columns=["_tile", "element_key", "top_element_key"], errors="ignore"
    )
    return gpd.GeoDataFrame(zones, geometry="geometry", crs=frames[0].crs)


def stitch_elements(tile_zones, labels):
    """The wall elements of every tile, indexed by global label."""
    frame = pd.concat([zones.elements for zones in tile_zones])
    frame.index = pd.Index([labels[key] for key in frame["element_key"]], name="label")
    frame = frame.drop(columns=["element_key"]).sort_index()
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=tile_zones[0].elements.crs)
