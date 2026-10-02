"""Raster segmentation of the urban domain into failure candidates.

What belongs here: the urban domain (building outlines buffered, less the NLM
flatland), the slope bands and aspect octants a cell is classed into, the
4-connected labelling of patches at each scale, the minimum patch and the
contour-length split, and the snap tolerance the wall lines share. The
candidates are built by landslide step 6 (``s6_urban_slope_candidates``), which
reads the terrain and ground attributes onto what this module returns.

The segmentation is the banded connected-components baseline of plan section
8.2 (``.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md``):
the slope at one scale is classed into bands, the downhill azimuth into eight
octants, and cells of one band and one octant that share an edge form a
patch. The patch edges therefore fall on the band boundaries, which are the
crest and toe lines the urban model wants. The bands are not a cut-off: the
gentlest band produces candidates like every other. Everything here is raster
arithmetic on numpy arrays; the only vector work is turning the final labels
into polygons and trimming them to the domain.

Parameters that are fixed by the method -- the bands, the octants, the snap
tolerance -- live here (contract section 10). The minimum patch and the
contour length are run settings and live in the step's ``config.py``, passed
in as arguments.
"""

import math
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import xarray as xr
from numpy.typing import NDArray
from rasterio import features
from rasterio.transform import Affine
from scipy import ndimage
from shapely.geometry import Polygon, shape

from landloss.common.utils.terrain import RASTER_DIMS, cell_size

# The slope band breaks in degrees. A value on a break falls in the band above,
# so 10 degrees is "10-20". The bands are those of plan section 8.2; the
# gentlest band is a candidate class like any other, not a cut-off.
SLOPE_BANDS_DEG = (10.0, 20.0, 30.0, 45.0, 60.0)
SLOPE_BAND_LABELS = ("0-10", "10-20", "20-30", "30-45", "45-60", "60+")

# The downhill azimuth is binned into this many octants, centred on north,
# north-east and so on clockwise: north is 337.5 to 22.5 degrees and is octant 0.
ASPECT_OCTANTS = 8

# Snap tolerance in metres, shared by the wall lines (mapped walls onto
# candidate edges) and step 7 (candidate edges onto wall lines).
SNAP_TOLERANCE_M = 3.0

# The band and octant of a cell that has none: slope NaN, or level ground with
# no downhill direction.
NO_CLASS = -1

# The label of a cell outside every patch.
OUTSIDE = 0

# Edges only, no corners: the 4-connectivity of plan section 8.2.
FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)

# The columns :func:`delineate_candidates` returns, in this order.
CANDIDATE_COLUMNS = (
    "scale_m",
    "slope_band",
    "aspect_octant",
    "slope_degrees",
    "aspect_degrees",
    "area_m2",
    "contour_length_m",
    "geometry",
)

# The dtype of each attribute column of :data:`CANDIDATE_COLUMNS` (contract
# section 3.4), which an empty frame carries as well as a populated one.
CANDIDATE_DTYPES: dict[str, Any] = {
    "scale_m": np.int64,
    "slope_band": object,
    "aspect_octant": np.int64,
    "slope_degrees": float,
    "aspect_degrees": float,
    "area_m2": float,
    "contour_length_m": float,
}

_FULL_TURN = 360.0
_OCTANT_WIDTH = _FULL_TURN / ASPECT_OCTANTS


def _check_projected(frame: gpd.GeoDataFrame, name: str) -> None:
    """Refuse a frame in a geographic system, where a buffer would be degrees."""
    if frame.crs is not None and frame.crs.is_geographic:
        msg = (
            f"the {name} are in {frame.crs}, a geographic system, so a distance "
            "would be in degrees. Work in a projected system such as NZGD2000 / NZTM."
        )
        raise ValueError(msg)


def urban_domain(
    buildings: gpd.GeoDataFrame,
    flatland: gpd.GeoDataFrame,
    *,
    building_distance_m: float,
) -> shapely.Geometry:
    """Build the ground the urban model runs over.

    The union of the building outlines buffered by ``building_distance_m``,
    less the NLM flatland polygons: sloping ground near a building (plan
    section 8.1). No insured land mask is applied.

    Args:
        buildings: The LINZ building outlines, in a projected system.
        flatland: The NLM flatland polygons, in the same system. May be empty.
        building_distance_m: How far from an outline the domain reaches.

    Returns:
        One (multi)polygon, empty when there are no buildings.

    Raises:
        ValueError: If the two frames are in different systems or a geographic
            one, or the distance is not positive.
    """
    if building_distance_m <= 0:
        msg = f"building_distance_m must be positive, not {building_distance_m}"
        raise ValueError(msg)
    _check_projected(buildings, "buildings")
    if buildings.crs != flatland.crs:
        msg = (
            f"the buildings are in {buildings.crs} but the flatland is in "
            f"{flatland.crs}; reproject one onto the other first"
        )
        raise ValueError(msg)
    if buildings.empty:
        return Polygon()
    near = buildings.geometry.buffer(building_distance_m).union_all()
    if flatland.empty:
        return near
    return near.difference(flatland.geometry.union_all())


def slope_band(slope_degrees: NDArray[np.floating]) -> NDArray[np.integer]:
    """Class a slope into the bands of :data:`SLOPE_BANDS_DEG`.

    Args:
        slope_degrees: Slope in degrees, any shape.

    Returns:
        The band index, 0 for the gentlest to ``len(SLOPE_BANDS_DEG)`` for the
        steepest, with :data:`NO_CLASS` where the slope is NaN. A value on a
        break falls in the band above.
    """
    values = np.asarray(slope_degrees, dtype=float)
    band = np.digitize(np.nan_to_num(values, nan=0.0), SLOPE_BANDS_DEG)
    return np.where(np.isnan(values), NO_CLASS, band).astype(np.int64)


def aspect_octant(azimuth_degrees: NDArray[np.floating]) -> NDArray[np.integer]:
    """Bin a downhill azimuth into :data:`ASPECT_OCTANTS` octants.

    Args:
        azimuth_degrees: Degrees clockwise from grid north, any shape.

    Returns:
        The octant, 0 for north to 7 for north-west clockwise, each centred on
        its compass point, with :data:`NO_CLASS` where the azimuth is NaN.
    """
    values = np.asarray(azimuth_degrees, dtype=float)
    shifted = (np.nan_to_num(values, nan=0.0) + _OCTANT_WIDTH / 2) % _FULL_TURN
    octant = np.floor(shifted / _OCTANT_WIDTH).astype(np.int64)
    octant = np.clip(octant, 0, ASPECT_OCTANTS - 1)
    return np.where(np.isnan(values), NO_CLASS, octant).astype(np.int64)


def _shared_edges(
    labels: NDArray[np.integer],
) -> tuple[NDArray[np.integer], NDArray[np.integer], NDArray[np.integer]]:
    """Count the cell edges each pair of adjacent patches shares.

    Args:
        labels: The patch label of each cell, :data:`OUTSIDE` off every patch.

    Returns:
        Three arrays of one row per unordered pair of distinct labels, both
        inside a patch, that share at least one cell edge: the lower label, the
        higher label, and the number of edges they share.
    """
    horizontal = np.stack([labels[:, :-1].ravel(), labels[:, 1:].ravel()], axis=1)
    vertical = np.stack([labels[:-1, :].ravel(), labels[1:, :].ravel()], axis=1)
    pairs = np.concatenate([horizontal, vertical])
    pairs = pairs[(pairs[:, 0] != pairs[:, 1]) & (pairs > OUTSIDE).all(axis=1)]
    if pairs.size == 0:
        empty = np.zeros(0, dtype=np.int64)
        return empty, empty, empty
    pairs.sort(axis=1)
    unique, counts = np.unique(pairs, axis=0, return_counts=True)
    return unique[:, 0], unique[:, 1], counts


def _best_neighbours(
    labels: NDArray[np.integer],
    *,
    merging: NDArray[np.bool_],
    allowed: NDArray[np.bool_],
) -> dict[int, int]:
    """Pick, for each patch to merge, the allowed neighbour sharing the most edges.

    Args:
        labels: The patch label of each cell.
        merging: One flag per label, true for the patches to merge away.
        allowed: One flag per label, true for the patches that may receive one.

    Returns:
        A map from each merging label that has an allowed neighbour to that
        neighbour. Ties go to the lowest neighbouring label, so the choice is
        reproducible.
    """
    low, high, counts = _shared_edges(labels)
    source = np.concatenate([low, high])
    target = np.concatenate([high, low])
    shared = np.concatenate([counts, counts])
    keep = merging[source] & allowed[target]
    source, target, shared = source[keep], target[keep], shared[keep]
    if source.size == 0:
        return {}
    # Sorted by source, then most shared edges first, then lowest target: the
    # first row of each source is its choice.
    order = np.lexsort((target, -shared, source))
    source, target = source[order], target[order]
    first = np.ones(source.size, dtype=bool)
    first[1:] = source[1:] != source[:-1]
    return dict(zip(source[first].tolist(), target[first].tolist(), strict=True))


def _resolve_targets(mapping: dict[int, int]) -> dict[int, int]:
    """Follow merge chains to their end, breaking a cycle at its lowest label.

    Two small patches that each choose the other would otherwise swap labels
    for ever; both go to the lower of the two instead.

    Args:
        mapping: Each merging label to the neighbour it chose.

    Returns:
        Each merging label to the label it finally takes.
    """
    resolved: dict[int, int] = {}
    for start in mapping:
        if start in resolved:
            continue
        chain = [start]
        seen = {start}
        current = start
        while current in mapping and current not in resolved:
            current = mapping[current]
            if current in seen:
                # A cycle: everything from its first member onward collapses
                # onto the cycle's lowest label.
                cycle = chain[chain.index(current) :]
                current = min(cycle)
                break
            chain.append(current)
            seen.add(current)
        end = resolved.get(current, current)
        for label in chain:
            resolved[label] = end
    return resolved


def _apply_mapping(
    labels: NDArray[np.integer], mapping: dict[int, int]
) -> NDArray[np.integer]:
    """Relabel the cells of each merging patch to their chosen neighbour."""
    lookup = np.arange(int(labels.max()) + 1, dtype=np.int64)
    for source, target in mapping.items():
        lookup[source] = target
    return lookup[labels]


def _renumber(labels: NDArray[np.integer]) -> NDArray[np.integer]:
    """Renumber the patches 1 to n in order of first appearance, keeping 0."""
    unique, inverse = np.unique(labels, return_inverse=True)
    inverse = inverse.reshape(labels.shape)
    if unique.size and unique[0] == OUTSIDE:
        return inverse.astype(np.int64)
    return (inverse + 1).astype(np.int64)


def label_patches(
    band: NDArray[np.integer], octant: NDArray[np.integer]
) -> NDArray[np.integer]:
    """Label the 4-connected runs of cells sharing one band and one octant.

    Each (band, octant) class is labelled on its own with
    :func:`scipy.ndimage.label` and the labels are stacked, so no two classes
    share a label. Level cells in the gentlest band, which have no octant,
    then join the neighbouring gentlest-band patch they share the most edges
    with (contract section 10); a level run with no such neighbour stays a
    patch of its own.

    Args:
        band: The slope band of each cell, from :func:`slope_band`.
        octant: The aspect octant of each cell, from :func:`aspect_octant`.

    Returns:
        An integer label per cell, from 1 upward, :data:`OUTSIDE` where the
        band is :data:`NO_CLASS`.

    Raises:
        ValueError: If the two arrays are not the same two-dimensional shape.
    """
    band = np.asarray(band)
    octant = np.asarray(octant)
    if band.ndim != 2 or band.shape != octant.shape:
        msg = (
            f"band {band.shape} and octant {octant.shape} must be the same "
            "two-dimensional grid"
        )
        raise ValueError(msg)

    # The octant is shifted up by one so that level cells (octant -1) are a
    # class of their own rather than colliding with the cells outside.
    classes = np.where(
        band == NO_CLASS, NO_CLASS, band * (ASPECT_OCTANTS + 1) + octant + 1
    )
    labels = np.zeros(band.shape, dtype=np.int64)
    offset = 0
    for value in np.unique(classes):
        if value == NO_CLASS:
            continue
        labelled, count = ndimage.label(classes == value, structure=FOUR_CONNECTED)
        inside = labelled > 0
        labels[inside] = labelled[inside] + offset
        offset += count

    # Level runs in the gentlest band join a sloping gentlest-band neighbour.
    level = (band == 0) & (octant == NO_CLASS)
    if level.any():
        count = int(labels.max()) + 1
        level_labels = np.zeros(count, dtype=bool)
        level_labels[np.unique(labels[level])] = True
        gentle = np.zeros(count, dtype=bool)
        gentle[np.unique(labels[(band == 0) & (octant != NO_CLASS)])] = True
        gentle[OUTSIDE] = False
        mapping = _best_neighbours(labels, merging=level_labels, allowed=gentle)
        if mapping:
            labels = _apply_mapping(labels, mapping)
    return _renumber(labels)


def merge_small_patches(
    labels: NDArray[np.integer], *, min_cells: int
) -> NDArray[np.integer]:
    """Merge every patch under a minimum size into its best neighbour.

    A patch of fewer than ``min_cells`` cells joins the neighbouring patch it
    shares the most cell edges with, whatever that neighbour's band or
    octant, and the merge is repeated until no small patch has a neighbour. A
    small patch with no neighbour at all -- an island inside the cells outside
    -- is kept as it is.

    Args:
        labels: The patch label of each cell, from :func:`label_patches`.
        min_cells: The smallest patch kept as it is, in cells.

    Returns:
        The merged labels, renumbered 1 to n.

    Raises:
        ValueError: If ``min_cells`` is less than one.
    """
    if min_cells < 1:
        msg = f"min_cells must be at least 1, not {min_cells}"
        raise ValueError(msg)
    labels = _renumber(np.asarray(labels))
    while True:
        sizes = np.bincount(labels.ravel())
        small = (sizes > 0) & (sizes < min_cells)
        small[OUTSIDE] = False
        if not small.any():
            break
        allowed = sizes > 0
        allowed[OUTSIDE] = False
        chosen = _best_neighbours(labels, merging=small, allowed=allowed)
        if not chosen:
            break
        labels = _renumber(_apply_mapping(labels, _resolve_targets(chosen)))
    return labels


def patches_to_polygons(
    labels: NDArray[np.integer], transform: Affine, crs: str
) -> gpd.GeoDataFrame:
    """Turn a label raster into one polygon per patch.

    Args:
        labels: The patch label of each cell, :data:`OUTSIDE` off every patch.
        transform: The raster's affine transform, cell corner based.
        crs: The raster's coordinate reference system.

    Returns:
        A frame with ``label`` and ``geometry``, one row per patch in raster
        scan order, on a fresh index. A patch is 4-connected so it is one
        polygon, possibly with holes.
    """
    labels = np.asarray(labels)
    shapes = features.shapes(
        labels.astype(np.int32),
        mask=labels > OUTSIDE,
        connectivity=4,
        transform=transform,
    )
    rows = [(int(value), shape(geometry)) for geometry, value in shapes]
    frame = gpd.GeoDataFrame(
        {"label": pd.Series([label for label, _ in rows], dtype=np.int64)},
        geometry=[geometry for _, geometry in rows],
        crs=crs,
    )
    return frame.reset_index(drop=True)


def _across_and_down(
    aspect_degrees: NDArray[np.floating],
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Return the unit vectors across the slope and down it, per aspect.

    The downhill vector of a bearing ``a`` clockwise from north is
    ``(sin a, cos a)``; across the slope is that turned a quarter turn.
    """
    radians = np.radians(np.asarray(aspect_degrees, dtype=float))
    down = np.stack([np.sin(radians), np.cos(radians)], axis=-1)
    across = np.stack([np.cos(radians), -np.sin(radians)], axis=-1)
    return across, down


def contour_length_m(
    geometry: gpd.GeoSeries, aspect_degrees: NDArray[np.floating]
) -> NDArray[np.floating]:
    """Measure each polygon across the slope.

    The length is the extent of the polygon's vertices along the direction
    perpendicular to its aspect: the width of a bank along the contour rather
    than down it. Step 7 recomputes it on the reconciled geometry, which is
    why it is public.

    Args:
        geometry: The polygons, one per aspect.
        aspect_degrees: The downhill azimuth of each polygon, clockwise from
            north.

    Returns:
        One length in the geometry's units per polygon, NaN where the aspect
        is NaN (level ground has no across-slope direction) or the geometry is
        empty.

    Raises:
        ValueError: If there is not one aspect per geometry.
    """
    aspects = np.asarray(aspect_degrees, dtype=float)
    if aspects.shape != (len(geometry),):
        msg = f"{aspects.shape} aspects for {len(geometry)} geometries"
        raise ValueError(msg)
    lengths = np.full(len(geometry), np.nan)
    if len(geometry) == 0:
        return lengths
    coordinates, index = shapely.get_coordinates(
        np.asarray(geometry.to_numpy()), return_index=True
    )
    if coordinates.size == 0:
        return lengths
    across, _ = _across_and_down(aspects)
    projection = (coordinates * across[index]).sum(axis=1)
    # A NaN aspect projects every vertex to NaN; those rows keep NaN lengths.
    finite = np.isfinite(projection)
    low = np.full(len(geometry), np.inf)
    high = np.full(len(geometry), -np.inf)
    np.minimum.at(low, index[finite], projection[finite])
    np.maximum.at(high, index[finite], projection[finite])
    measured = np.isfinite(low) & np.isfinite(high)
    lengths[measured] = high[measured] - low[measured]
    return lengths


def _slabs(
    polygon: shapely.Geometry, aspect: float, pieces: int
) -> list[shapely.Geometry]:
    """Cut a polygon into equal slabs across the slope, each a (multi)polygon."""
    across, down = _across_and_down(np.asarray([aspect]))
    across, down = across[0], down[0]
    coordinates = shapely.get_coordinates(polygon)
    along = coordinates @ across
    deep = coordinates @ down
    low, high = along.min(), along.max()
    # Pad the slab well past the polygon down the slope, so the cut is a line
    # parallel to the aspect and nothing else.
    pad = 1.0 + (deep.max() - deep.min())
    deep_low, deep_high = deep.min() - pad, deep.max() + pad
    width = (high - low) / pieces
    slabs = []
    for piece in range(pieces):
        start = low + piece * width
        # The last slab reaches past the far edge so floating point rounding
        # cannot leave a sliver of the polygon outside every slab.
        end = high + 1.0 if piece == pieces - 1 else start + width
        begin = start - 1.0 if piece == 0 else start
        corners = [
            begin * across + deep_low * down,
            end * across + deep_low * down,
            end * across + deep_high * down,
            begin * across + deep_high * down,
        ]
        slabs.append(polygon.intersection(Polygon(corners)))
    return slabs


def _polygon_parts(geometry: shapely.Geometry) -> list[shapely.Geometry]:
    """Return the polygons inside a geometry, dropping points, lines and empties."""
    parts = (
        shapely.get_parts(geometry) if geometry.geom_type != "Polygon" else [geometry]
    )
    return [
        part
        for part in parts
        if part.geom_type == "Polygon" and not part.is_empty and part.area > 0
    ]


def split_long_patches(
    patches: gpd.GeoDataFrame,
    aspect_degrees: NDArray[np.floating],
    *,
    max_length_m: float,
) -> gpd.GeoDataFrame:
    """Cut each patch longer than a limit across the slope into equal pieces.

    A patch whose :func:`contour_length_m` exceeds ``max_length_m`` is cut by
    lines parallel to its aspect into the fewest equal pieces that each fit
    the limit. The pieces keep the patch's other columns. A patch with a NaN
    aspect is level ground with no across-slope direction, and is not cut.

    Args:
        patches: One row per patch, with any columns, in a projected system.
        aspect_degrees: The downhill azimuth of each row, clockwise from north.
        max_length_m: The longest contour length kept uncut.

    Returns:
        The patches with the long ones replaced by their pieces, in the
        incoming order with pieces in order across the slope, on a fresh
        index.

    Raises:
        ValueError: If ``max_length_m`` is not positive, or the frame is in a
            geographic system.
    """
    if max_length_m <= 0:
        msg = f"max_length_m must be positive, not {max_length_m}"
        raise ValueError(msg)
    _check_projected(patches, "patches")
    aspects = np.asarray(aspect_degrees, dtype=float)
    lengths = contour_length_m(patches.geometry, aspects)
    long = np.isfinite(lengths) & (lengths > max_length_m)
    if not long.any():
        return patches.reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(patches.iterrows()):
        attributes = {key: value for key, value in row.items() if key != "geometry"}
        if not long[position]:
            rows.append({**attributes, "geometry": row.geometry})
            continue
        pieces = math.ceil(lengths[position] / max_length_m)
        for slab in _slabs(row.geometry, aspects[position], pieces):
            for part in _polygon_parts(slab):
                rows.append({**attributes, "geometry": part})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=patches.crs).reset_index(
        drop=True
    )


def _check_grid(raster: xr.DataArray, name: str) -> None:
    """Refuse a raster that is not an oriented 2-D grid with a CRS."""
    if tuple(raster.dims) != RASTER_DIMS:
        msg = f"{name} has dims {tuple(raster.dims)}, not {RASTER_DIMS}"
        raise ValueError(msg)
    if raster.rio.crs is None:
        msg = f"{name} carries no coordinate reference system"
        raise ValueError(msg)


def _majority(
    labels: NDArray[np.integer], values: NDArray[np.integer], width: int
) -> NDArray[np.integer]:
    """Return the most common value per label, for values in 0 to width - 1."""
    count = int(labels.max()) + 1
    key = labels.ravel() * width + values.ravel()
    table = np.bincount(key, minlength=count * width).reshape(count, width)
    return table.argmax(axis=1)


def _patch_statistics(
    labels: NDArray[np.integer],
    slope: NDArray[np.floating],
    aspect: NDArray[np.floating],
    band: NDArray[np.integer],
    octant: NDArray[np.integer],
) -> pd.DataFrame:
    """Compute the band, octant, mean slope and circular mean aspect per patch.

    The band and octant are the most common ones among the patch's cells,
    which after merging may hold more than one class.
    """
    count = int(labels.max()) + 1
    flat = labels.ravel()
    cells = np.bincount(flat, minlength=count)

    slope_values = np.nan_to_num(slope.ravel(), nan=0.0)
    slope_cells = np.bincount(flat, weights=np.isfinite(slope.ravel()), minlength=count)
    slope_sum = np.bincount(flat, weights=slope_values, minlength=count)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean_slope = np.where(slope_cells > 0, slope_sum / slope_cells, np.nan)

    radians = np.radians(aspect.ravel())
    finite = np.isfinite(radians)
    sine = np.bincount(
        flat, weights=np.where(finite, np.sin(radians), 0.0), minlength=count
    )
    cosine = np.bincount(
        flat, weights=np.where(finite, np.cos(radians), 0.0), minlength=count
    )
    aspect_cells = np.bincount(flat, weights=finite, minlength=count)
    mean_aspect = np.degrees(np.arctan2(sine, cosine)) % _FULL_TURN
    # A resultant a rounding error west of north comes out of the modulus as
    # 360.0 rather than 0.0, outside the [0, 360) a bearing lives in (the same
    # guard terrain._unit_vector_mean carries).
    mean_aspect = np.where(mean_aspect >= _FULL_TURN, 0.0, mean_aspect)
    mean_aspect = np.where(aspect_cells > 0, mean_aspect, np.nan)

    band_index = _majority(labels, np.where(band < 0, 0, band), len(SLOPE_BAND_LABELS))
    octant_index = _majority(labels, octant + 1, ASPECT_OCTANTS + 1) - 1

    statistics = pd.DataFrame(
        {
            "cells": cells,
            "slope_band": np.asarray(SLOPE_BAND_LABELS)[band_index],
            "aspect_octant": octant_index.astype(np.int64),
            "slope_degrees": mean_slope,
            "aspect_degrees": mean_aspect,
        }
    )
    return statistics.iloc[1:]  # drop OUTSIDE


def _clip_to_domain(
    patches: gpd.GeoDataFrame, domain: shapely.Geometry
) -> gpd.GeoDataFrame:
    """Trim the patches to the domain, keeping every polygon part that results."""
    geometries = np.asarray(patches.geometry.to_numpy())
    shapely.prepare(domain)
    inside = shapely.contains_properly(domain, geometries)
    trimmed = geometries.copy()
    trimmed[~inside] = shapely.intersection(geometries[~inside], domain)
    rows: list[dict[str, Any]] = []
    for position, (_, row) in enumerate(patches.iterrows()):
        attributes = {key: value for key, value in row.items() if key != "geometry"}
        for part in _polygon_parts(trimmed[position]):
            rows.append({**attributes, "geometry": part})
    if not rows:
        return patches.iloc[:0].reset_index(drop=True)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=patches.crs).reset_index(
        drop=True
    )


def delineate_candidates(
    slope: xr.DataArray,
    aspect: xr.DataArray,
    domain: shapely.Geometry,
    *,
    scale_m: int,
    min_patch_cells: int,
    max_length_m: float,
) -> gpd.GeoDataFrame:
    """Segment the slope at one scale into failure candidates over the domain.

    In order: the cells whose centres fall outside ``domain`` are set aside;
    the rest are classed by :func:`slope_band` and :func:`aspect_octant` and
    labelled by :func:`label_patches`; patches under ``min_patch_cells`` are
    merged by :func:`merge_small_patches`; the patches become polygons by
    :func:`patches_to_polygons`; patches longer than ``max_length_m`` across
    the slope are cut by :func:`split_long_patches`; and the polygons are
    trimmed to ``domain``. Every band produces candidates, the gentlest
    included.

    Args:
        slope: The slope in degrees at this scale, dims ``("y", "x")``, with
            a CRS. NaN cells are outside every patch.
        aspect: The downhill azimuth in degrees on the same grid.
        domain: The ground to segment, from :func:`urban_domain`, in the
            rasters' system.
        scale_m: The cell size of the two rasters in metres, written onto the
            rows.
        min_patch_cells: The smallest patch kept unmerged, in cells.
        max_length_m: The longest contour length kept uncut, in metres.

    Returns:
        One row per candidate with the columns of :data:`CANDIDATE_COLUMNS`:
        ``scale_m``, ``slope_band`` (a label of :data:`SLOPE_BAND_LABELS`),
        ``aspect_octant``, the mean ``slope_degrees`` and circular mean
        ``aspect_degrees`` of the patch's cells, ``area_m2``,
        ``contour_length_m`` and the polygon ``geometry``, on a fresh index,
        with the dtypes of :data:`CANDIDATE_DTYPES` whether or not any row is
        found. ``aspect_degrees`` is in [0, 360). A level patch, whose cells
        have no downhill direction, carries ``aspect_octant`` of
        :data:`NO_CLASS` (-1) and NaN ``aspect_degrees`` and
        ``contour_length_m``. The pieces of a split patch carry the whole
        patch's slope and aspect.

    Raises:
        ValueError: If a raster is not an oriented grid with a CRS, the two
            grids differ, or the cell size is not ``scale_m``.
    """
    _check_grid(slope, "slope")
    _check_grid(aspect, "aspect")
    if slope.shape != aspect.shape:
        msg = f"slope {slope.shape} and aspect {aspect.shape} are not on one grid"
        raise ValueError(msg)
    resolution = cell_size(slope)
    if not math.isclose(resolution, scale_m, rel_tol=1e-6):
        msg = f"the slope raster's cells are {resolution} m, not scale_m = {scale_m}"
        raise ValueError(msg)

    crs = slope.rio.crs.to_string()
    transform = slope.rio.transform()
    slope_values = slope.to_numpy().astype(float)
    aspect_values = aspect.to_numpy().astype(float)

    # The empty frame carries the dtypes a populated one does, because the
    # step concatenates the scales and an empty float column would otherwise
    # turn the integer columns of the other scales into float.
    empty = gpd.GeoDataFrame(
        {
            column: pd.Series(dtype=CANDIDATE_DTYPES[column])
            for column in CANDIDATE_COLUMNS[:-1]
        },
        geometry=gpd.GeoSeries([], crs=crs),
    )
    if domain.is_empty:
        return empty

    inside = features.geometry_mask(
        [domain], out_shape=slope_values.shape, transform=transform, invert=True
    )
    band = slope_band(slope_values)
    band[~inside] = NO_CLASS
    octant = aspect_octant(aspect_values)
    labels = merge_small_patches(label_patches(band, octant), min_cells=min_patch_cells)
    if labels.max() == OUTSIDE:
        return empty

    statistics = _patch_statistics(labels, slope_values, aspect_values, band, octant)
    polygons = patches_to_polygons(labels, transform, crs)
    polygons = polygons.join(statistics, on="label").drop(columns=["label", "cells"])
    polygons = split_long_patches(
        polygons, polygons["aspect_degrees"].to_numpy(), max_length_m=max_length_m
    )
    polygons = _clip_to_domain(polygons, domain)

    polygons["scale_m"] = np.int64(scale_m)
    polygons["area_m2"] = polygons.geometry.area
    polygons["contour_length_m"] = contour_length_m(
        polygons.geometry, polygons["aspect_degrees"].to_numpy()
    )
    polygons["aspect_octant"] = polygons["aspect_octant"].astype(np.int64)
    return polygons[list(CANDIDATE_COLUMNS)].reset_index(drop=True)
