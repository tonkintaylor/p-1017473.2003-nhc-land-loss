"""Slope units: the half-basins the large landslide model places failures in.

A slope unit is one hillslope facet from a drainage line at the bottom to the
ridge at the top, with one broad aspect, of the order of 1 to 100 ha. It is the
unit a large failure is placed in, not the unit the large models are fitted
on. The delineation is the ``r.slopeunits`` logic of [alvioli_2016] without
GRASS: route the flow, draw a channel network at an upstream-area threshold,
cut the sub-basin of each channel link, split each sub-basin along its channel
into a left and a right half-basin, merge neighbouring half-basins of similar
aspect, and split anything still too large by the variance of its aspect.

The routing comes from :mod:`landloss.common.utils.hydrology` -- priority
flood, D8 receivers and accumulation -- and the labelling from
``scipy.ndimage``; pysheds is not used, because it needs numba and numba
forces a numpy downgrade this project does not tolerate (contract section 12).
The layer is built by landslide step 5 (``s5_slope_units``), which mints the
``unit_id`` and reads the flatland share onto each unit.

Every stage is a public function taking and returning arrays or frames, so a
caller can run them singly; :func:`delineate_slope_units` runs them in order.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from rasterio import features, windows
from rasterio.transform import Affine
from scipy import ndimage
from scipy.cluster.vq import ClusterError, kmeans2
from scipy.spatial import cKDTree
from shapely.geometry import shape

from landloss.common.utils import hydrology, terrain
from landloss.common.utils.hydrology import OUTLET

#: The two banks of a channel, looking downstream.
SIDES = ("left", "right")
LEFT, RIGHT = SIDES

#: The attribute columns :func:`delineate_slope_units` writes, after the ids.
STATISTIC_COLUMNS = (
    "area_m2",
    "mean_slope_degrees",
    "mean_aspect_degrees",
    "aspect_sd_degrees",
    "min_elevation_m",
    "max_elevation_m",
    "relief_m",
)

M2_PER_HA = 10_000.0

# The most split-and-merge passes delineate_slope_units makes before it accepts
# that a unit stays over the maximum. Absorbing a fragment into its most
# similar neighbour (the small-unit rule) can push that neighbour just over
# the maximum again, so the two stages alternate a bounded number of times.
_MAX_PASSES = 3

# Seed of the k-means in split_by_aspect_variance, so a split reproduces.
_KMEANS_SEED = 1017473

# A k-means on aspect that puts fewer than this share of a unit's cells in its
# smaller cluster has found noise, not a second facet, and the unit is split
# by position instead.
_MIN_CLUSTER_SHARE = 0.05

# A unit whose aspect unit vectors have a mean resultant this long or longer
# faces one way; its cells are halved by position rather than by aspect.
_UNIFORM_ASPECT_RESULTANT = 0.999

# Column names carried on the frames between stages.
_LABEL = "label"
_BASIN = "basin_id"
_SIDE = "side"
_GEOMETRY = "geometry"
_AREA = "area_m2"
_ASPECT = "mean_aspect_degrees"


# --------------------------------------------------------------------------
# Raster stages
# --------------------------------------------------------------------------


def channel_cells(accumulation_m2: np.ndarray, *, threshold_m2: float) -> np.ndarray:
    """Mark the cells whose upstream area reaches the channel threshold.

    Args:
        accumulation_m2: Upstream contributing area per cell, in square
            metres, NaN off the DEM.
        threshold_m2: The upstream area at which a cell becomes a channel.

    Returns:
        A boolean grid, True on channel cells, False off the DEM.
    """
    with np.errstate(invalid="ignore"):
        return np.asarray(accumulation_m2 >= threshold_m2) & np.isfinite(
            accumulation_m2
        )


def _donor_counts(receiver: np.ndarray, member: np.ndarray) -> np.ndarray:
    """Count, per flat index, how many member cells drain straight into it."""
    flat = member.ravel()
    donors = np.flatnonzero(flat)
    targets = receiver[donors]
    targets = targets[targets != OUTLET]
    targets = targets[flat[targets]]
    return np.bincount(targets, minlength=flat.size)


def channel_links(channels: np.ndarray, receiver: np.ndarray) -> np.ndarray:
    """Label every channel reach between junctions, from 1.

    A link starts at a channel head (no channel cell drains into it) or at a
    junction (two or more do), and runs downstream until the cell before the
    next junction, or the last channel cell before the flow leaves the network
    or the grid. The junction cell itself belongs to the link that starts at
    it. Links are numbered in the raster order of their first cell, so the
    numbering is deterministic.

    Args:
        channels: The boolean channel grid from :func:`channel_cells`.
        receiver: Per flat index, the receiving cell from
            :func:`landloss.common.utils.hydrology.d8_receivers`.

    Returns:
        An integer grid of link labels, 0 off the channel network.
    """
    flat_channels = channels.ravel()
    donors = _donor_counts(receiver, channels)
    starts = np.flatnonzero(flat_channels & (donors != 1))
    links = np.zeros(flat_channels.size, dtype=np.int64)
    for label, start in enumerate(starts, start=1):
        idx = start
        while True:
            links[idx] = label
            downstream = receiver[idx]
            if (
                downstream == OUTLET
                or not flat_channels[downstream]
                or donors[downstream] != 1
            ):
                break
            idx = downstream
    return links.reshape(channels.shape)


def link_catchments(
    receiver: np.ndarray, order: np.ndarray, links: np.ndarray
) -> np.ndarray:
    """Assign every valid cell to the link it drains to.

    Walking the flood order downstream first, each off-channel cell takes the
    catchment of its receiver, so the label propagates up every hillslope. A
    cell whose flow leaves the grid before it reaches a channel -- an edge
    slope, or a coastal slope draining straight into the sea -- drains to no
    link, and takes the catchment of the nearest labelled cell instead, so that
    no part of the extent is left outside every unit. Where no cell reached the
    channel threshold at all, so there is no link, every valid cell is basin 1:
    the extent is then one hillslope at that threshold, not none.

    Args:
        receiver: Per flat index, the receiving cell.
        order: The flood order from
            :func:`landloss.common.utils.hydrology.priority_flood`.
        links: The link labels from :func:`channel_links`.

    Returns:
        An integer grid of link labels per cell, 0 off the DEM.
    """
    catchment = links.ravel().copy()
    valid = np.zeros(catchment.size, dtype=bool)
    valid[order] = True
    if not (catchment > 0).any():
        catchment[valid] = 1
        return catchment.reshape(links.shape)
    for idx in order:
        if catchment[idx] == 0:
            downstream = receiver[idx]
            if downstream != OUTLET:
                catchment[idx] = catchment[downstream]
    catchment = catchment.reshape(links.shape)
    valid = valid.reshape(links.shape)

    unreached = valid & (catchment == 0)
    if unreached.any():
        _, (nearest_rows, nearest_cols) = ndimage.distance_transform_edt(
            catchment == 0, return_indices=True
        )
        catchment[unreached] = catchment[
            nearest_rows[unreached], nearest_cols[unreached]
        ]
    return catchment


def _cells_by_label(labels: np.ndarray) -> dict[int, np.ndarray]:
    """Group the flat indices of a label grid by label, in one pass.

    One stable sort of the flattened grid replaces a scan of the whole grid
    per label, which on the full study area (some 32 million 10 m cells and
    thousands of links) is the difference between seconds and hours.

    Args:
        labels: An integer grid; 0 and below is outside every label.

    Returns:
        Per positive label, the flat indices of its cells in raster order.
    """
    flat = labels.ravel()
    order = np.argsort(flat, kind="stable")
    sorted_labels = flat[order]
    present = np.unique(sorted_labels[sorted_labels > 0])
    starts = np.searchsorted(sorted_labels, present, side="left")
    stops = np.searchsorted(sorted_labels, present, side="right")
    return {
        int(label): order[start:stop]
        for label, start, stop in zip(present, starts, stops, strict=True)
    }


def _unit_vectors(azimuth_degrees: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the east and north components of a compass azimuth."""
    radians = np.deg2rad(azimuth_degrees)
    return np.sin(radians), np.cos(radians)


def _resultant_azimuth_degrees(east: float, north: float) -> float:
    """Return the compass azimuth of a resultant vector, in [0, 360).

    The modulus hands back 360.0 for a resultant a rounding error west of
    north, which is outside the range a bearing lives in, so that is folded
    to 0.0 as :func:`landloss.common.utils.terrain.mean_azimuth_degrees` does.
    """
    azimuth = float(np.rad2deg(np.arctan2(east, north)) % terrain.FULL_TURN_DEGREES)
    return 0.0 if azimuth >= terrain.FULL_TURN_DEGREES else azimuth


def _link_direction(
    rows: np.ndarray, cols: np.ndarray, receiver: np.ndarray, shape: tuple[int, int]
) -> tuple[float, float]:
    """Return the downstream chord of one link as an (east, north) unit vector.

    The chord runs from the link's head, the cell no link cell drains into, to
    its tail, the cell whose receiver is off the link. A one-cell link takes
    the direction to its receiver, or has none when it drains off the grid.
    """
    flat = rows * shape[1] + cols
    member = np.zeros(shape[0] * shape[1], dtype=bool)
    member[flat] = True
    downstream = receiver[flat]
    on_link = (downstream != OUTLET) & member[
        np.where(downstream == OUTLET, 0, downstream)
    ]
    in_link_donors = np.bincount(downstream[on_link], minlength=member.size)[flat]
    head = flat[in_link_donors == 0][0]
    tail = flat[~on_link][0]
    if head == tail:
        tail = receiver[head]
        if tail == OUTLET:
            return 0.0, 0.0
    head_row, head_col = divmod(int(head), shape[1])
    tail_row, tail_col = divmod(int(tail), shape[1])
    east, north = float(tail_col - head_col), float(head_row - tail_row)
    length = np.hypot(east, north)
    return (east / length, north / length) if length > 0 else (0.0, 0.0)


def split_half_basins(
    catchments: np.ndarray,
    links: np.ndarray,
    receiver: np.ndarray,
    aspect_degrees: np.ndarray,
) -> np.ndarray:
    """Put each cell on the left or the right bank of its link.

    The side is the sign of the cross product of the link's downstream
    direction -- the chord from its head to its tail -- and the vector from the
    nearest link cell to the cell. A cell on the link itself, where that
    vector is zero, takes the side its own downhill azimuth points to; where
    that is along the chord too, it goes left. A link with no direction (one
    cell draining off the grid) puts its whole catchment on the left, and so
    does a catchment with no link cells at all (no cell reached the channel
    threshold, so :func:`link_catchments` made the extent one basin).

    Args:
        catchments: The catchment label per cell from :func:`link_catchments`.
        links: The link labels from :func:`channel_links`.
        receiver: Per flat index, the receiving cell.
        aspect_degrees: The downhill azimuth per cell, degrees clockwise from
            north.

    Returns:
        An integer grid of half-basin labels, 0 off the DEM: ``2 * link - 1``
        on the left bank of a link and ``2 * link`` on the right.
    """
    half = np.zeros(catchments.shape, dtype=np.int64)
    width = catchments.shape[1]
    east, north = _unit_vectors(np.nan_to_num(aspect_degrees, nan=0.0))
    link_cells = _cells_by_label(links)
    for link, cells in _cells_by_label(catchments).items():
        cell_rows, cell_cols = np.divmod(cells, width)
        if link not in link_cells:
            half[cell_rows, cell_cols] = 2 * link - 1
            continue
        link_rows, link_cols = np.divmod(link_cells[link], width)
        d_east, d_north = _link_direction(
            link_rows, link_cols, receiver, catchments.shape
        )
        _, nearest = cKDTree(np.column_stack([link_rows, link_cols])).query(
            np.column_stack([cell_rows, cell_cols])
        )
        v_east = (cell_cols - link_cols[nearest]).astype(float)
        v_north = (link_rows[nearest] - cell_rows).astype(float)
        cross = d_east * v_north - d_north * v_east
        on_link = (v_east == 0) & (v_north == 0)
        cross[on_link] = (
            d_east * north[cell_rows, cell_cols] - d_north * east[cell_rows, cell_cols]
        )[on_link]
        half[cell_rows, cell_cols] = np.where(cross < 0, 2 * link, 2 * link - 1)
    return half


def _decode_half_basin(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return the link and the side encoded in half-basin labels."""
    basin = (labels + 1) // 2
    side = np.where(labels % 2 == 1, LEFT, RIGHT)
    return basin, side


def units_to_polygons(
    labels: np.ndarray, transform: Affine, crs: str
) -> gpd.GeoDataFrame:
    """Polygonise a half-basin label grid, one row per connected piece.

    Pieces are 4-connected, so a label whose cells touch only at a corner
    becomes two rows carrying the same label; every unit is a plain polygon.
    Rows come in raster scan order, so the frame is deterministic.

    Args:
        labels: The half-basin labels from :func:`split_half_basins`, 0 outside.
        transform: The grid's affine transform.
        crs: The grid's coordinate reference system.

    Returns:
        ``label``, ``basin_id``, ``side`` and ``geometry``, on a fresh index.
    """
    shapes = features.shapes(
        labels.astype(np.int32),
        mask=labels > 0,
        transform=transform,
        connectivity=4,
    )
    geometries = []
    values = []
    for geometry, value in shapes:
        geometries.append(shape(geometry))
        values.append(int(value))
    label = np.asarray(values, dtype=np.int64)
    basin, side = _decode_half_basin(label)
    return gpd.GeoDataFrame(
        {_LABEL: label, _BASIN: basin, _SIDE: side},
        geometry=gpd.GeoSeries(geometries, crs=crs),
        crs=crs,
    )


# --------------------------------------------------------------------------
# Unit statistics
# --------------------------------------------------------------------------


def _rasterize_units(
    units: gpd.GeoDataFrame, shape: tuple[int, int], transform: Affine
) -> np.ndarray:
    """Burn each unit's positional index plus one into the grid, 0 outside."""
    if units.empty:
        return np.zeros(shape, dtype=np.int32)
    return features.rasterize(
        zip(units.geometry, range(1, len(units) + 1), strict=True),
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype=np.int32,
    )


def _unit_statistics(
    units: gpd.GeoDataFrame,
    dem: xr.DataArray,
    slope: xr.DataArray,
    aspect: xr.DataArray,
) -> pd.DataFrame:
    """Read the attribute columns of each unit off the three rasters.

    Returns the :data:`STATISTIC_COLUMNS` on ``units.index``. Area is the
    polygon's; the rest are over the cells whose centre the polygon covers,
    NaN cells skipped. The circular mean and standard deviation of the aspect
    are :func:`landloss.common.utils.terrain.mean_azimuth_degrees` and
    :func:`landloss.common.utils.terrain.azimuth_sd_degrees`, so one
    definition serves every caller; a unit whose azimuths cancel exactly has a
    NaN mean aspect and an infinite spread, and one with no finite cell has
    NaN for both.
    """
    labels = _rasterize_units(units, dem.shape, dem.rio.transform())
    elevation = dem.to_numpy().ravel()
    slope_values = slope.to_numpy().ravel()
    azimuth = aspect.to_numpy().ravel()
    cells_by_unit = _cells_by_label(labels)
    empty = np.empty(0, dtype=np.int64)
    count = len(units)
    mean_slope = np.full(count, np.nan)
    mean_aspect = np.full(count, np.nan)
    aspect_sd = np.full(count, np.nan)
    min_elevation = np.full(count, np.nan)
    max_elevation = np.full(count, np.nan)
    for i in range(count):
        cells = cells_by_unit.get(i + 1, empty)
        z = elevation[cells]
        z = z[np.isfinite(z)]
        s = slope_values[cells]
        s = s[np.isfinite(s)]
        if s.size:
            mean_slope[i] = s.mean()
        if z.size:
            min_elevation[i] = z.min()
            max_elevation[i] = z.max()
        mean_aspect[i] = terrain.mean_azimuth_degrees(azimuth[cells])
        aspect_sd[i] = terrain.azimuth_sd_degrees(azimuth[cells])
    return pd.DataFrame(
        {
            _AREA: units.geometry.area.to_numpy(),
            "mean_slope_degrees": mean_slope,
            _ASPECT: mean_aspect,
            "aspect_sd_degrees": aspect_sd,
            "min_elevation_m": min_elevation,
            "max_elevation_m": max_elevation,
            "relief_m": max_elevation - min_elevation,
        },
        index=units.index,
    )


# --------------------------------------------------------------------------
# Merge and split
# --------------------------------------------------------------------------


def _angular_difference(a: float, b: float) -> float:
    """Return the smaller angle between two azimuths, 0 to 180 degrees."""
    difference = abs(a - b) % 360.0
    return min(difference, 360.0 - difference)


def _edge_neighbours(units: gpd.GeoDataFrame) -> dict[int, set[int]]:
    """Return, per positional index, the units sharing an edge with it."""
    neighbours: dict[int, set[int]] = {i: set() for i in range(len(units))}
    geometries = units.geometry.to_numpy()
    left, right = units.sindex.query(units.geometry, predicate="touches")
    for a, b in zip(left, right, strict=True):
        if a < b and geometries[a].intersection(geometries[b]).length > 0:
            neighbours[a].add(b)
            neighbours[b].add(a)
    return neighbours


class _MergeState:
    """The units of :func:`merge_similar_aspect` while pairs are being merged.

    Each unit keeps its geometry, its area, its mean aspect as an
    area-weighted resultant vector, its basin and side, and its edge
    neighbours. Merging two sums the resultants, so the merged mean aspect is
    the area-weighted circular mean of the two, and keeps the basin and side
    of the larger.
    """

    def __init__(self, units: gpd.GeoDataFrame) -> None:
        east, north = _unit_vectors(units[_ASPECT].to_numpy(dtype=float))
        area = units.geometry.area.to_numpy()
        self.geometry = dict(enumerate(units.geometry.to_numpy()))
        self.area = dict(enumerate(area))
        self.east = dict(enumerate(np.nan_to_num(east) * area))
        self.north = dict(enumerate(np.nan_to_num(north) * area))
        self.basin = dict(enumerate(units[_BASIN].to_numpy()))
        self.side = dict(enumerate(units[_SIDE].to_numpy()))
        self.neighbours = _edge_neighbours(units)
        self.crs = units.crs

    def aspect(self, i: int) -> float:
        """Return the mean aspect of unit ``i`` in degrees, in [0, 360)."""
        return _resultant_azimuth_degrees(self.east[i], self.north[i])

    def difference(self, i: int, j: int) -> float:
        """Return the angular difference between two units' mean aspects."""
        return _angular_difference(self.aspect(i), self.aspect(j))

    def merge(self, keep: int, drop: int) -> None:
        """Merge unit ``drop`` into unit ``keep``."""
        if self.area[drop] > self.area[keep]:
            self.basin[keep], self.side[keep] = self.basin[drop], self.side[drop]
        self.geometry[keep] = self.geometry[keep].union(self.geometry[drop])
        self.area[keep] += self.area[drop]
        self.east[keep] += self.east[drop]
        self.north[keep] += self.north[drop]
        for other in self.neighbours.pop(drop):
            self.neighbours[other].discard(drop)
            if other != keep:
                self.neighbours[other].add(keep)
                self.neighbours[keep].add(other)
        self.neighbours[keep].discard(drop)
        for mapping in (
            self.geometry,
            self.area,
            self.east,
            self.north,
            self.basin,
            self.side,
        ):
            del mapping[drop]

    def frame(self) -> gpd.GeoDataFrame:
        """Return the units as a frame, in the order they were given."""
        keys = sorted(self.geometry)
        return gpd.GeoDataFrame(
            {
                _BASIN: np.asarray([self.basin[k] for k in keys], dtype=np.int64),
                _SIDE: [self.side[k] for k in keys],
                _AREA: [self.area[k] for k in keys],
                _ASPECT: [self.aspect(k) for k in keys],
            },
            geometry=[self.geometry[k] for k in keys],
            crs=self.crs,
        )


def merge_similar_aspect(
    units: gpd.GeoDataFrame,
    *,
    tolerance_deg: float,
    min_area_m2: float,
    max_area_m2: float,
) -> gpd.GeoDataFrame:
    """Absorb small units and merge neighbours of similar aspect.

    First every unit under ``min_area_m2`` that has an edge neighbour is
    absorbed into the neighbour whose mean aspect is closest to its own,
    smallest first, whatever the merged area. Then, repeatedly, the adjacent
    pair whose mean aspects differ least is merged while that difference is
    under ``tolerance_deg`` and the merged area stays under ``max_area_m2``.
    A merged unit takes the basin and side of the larger of the two. The mean
    aspect of a merged unit is the area-weighted circular mean of the two.

    Args:
        units: Units with ``basin_id``, ``side``, ``mean_aspect_degrees`` and
            ``geometry``, as :func:`units_to_polygons` plus the statistics
            give them.
        tolerance_deg: Neighbours whose mean aspects differ by less than this
            are merged.
        min_area_m2: Units under this area are absorbed.
        max_area_m2: A merge of similar neighbours is not made past this area.

    Returns:
        The merged units with ``basin_id``, ``side``, ``area_m2``,
        ``mean_aspect_degrees`` and ``geometry`` on a fresh index. The caller
        re-reads the other statistics off the rasters.
    """
    state = _MergeState(units)

    while True:
        small = [
            i
            for i in sorted(state.area, key=lambda k: state.area[k])
            if state.area[i] < min_area_m2 and state.neighbours[i]
        ]
        if not small:
            break
        i = small[0]
        keep = min(state.neighbours[i], key=lambda j: (state.difference(i, j), j))
        state.merge(keep, i)

    while True:
        best: tuple[float, int, int] | None = None
        for i, others in state.neighbours.items():
            for j in others:
                if j <= i:
                    continue
                if state.area[i] + state.area[j] >= max_area_m2:
                    continue
                difference = state.difference(i, j)
                if difference < tolerance_deg and (
                    best is None or (difference, i, j) < best
                ):
                    best = (difference, i, j)
        if best is None:
            break
        _, i, j = best
        state.merge(i, j)

    return state.frame()


def _cluster_cells(
    east: np.ndarray, north: np.ndarray, rows: np.ndarray, cols: np.ndarray
) -> np.ndarray:
    """Split one unit's cells in two: by aspect, or by position where aspect cannot.

    A unit whose aspect vectors all point one way -- their resultant length
    is near one -- has no second facet for a k-means to find, and k-means++
    cannot even seed on identical points, so such a unit is halved by
    position instead; so is one whose aspect clusters leave fewer than
    :data:`_MIN_CLUSTER_SHARE` of the cells on one side.

    Returns 0 or 1 per cell.
    """
    vectors = np.column_stack([east, north])
    finite = np.isfinite(vectors).all(axis=1)
    membership = np.zeros(rows.size, dtype=int)
    resultant = np.hypot(*vectors[finite].mean(axis=0)) if finite.any() else 1.0
    if finite.sum() >= 2 and resultant < _UNIFORM_ASPECT_RESULTANT:
        try:
            _, assigned = kmeans2(
                vectors[finite], 2, minit="++", missing="raise", seed=_KMEANS_SEED
            )
        except ClusterError:
            assigned = None
        if assigned is not None:
            membership[finite] = assigned
            smaller = min(
                np.count_nonzero(membership == 0), np.count_nonzero(membership == 1)
            )
            if smaller >= _MIN_CLUSTER_SHARE * rows.size:
                return membership
    positions = np.column_stack([cols, rows]).astype(float)
    _, membership = kmeans2(positions, 2, minit="++", seed=_KMEANS_SEED)
    return membership


def _keep_largest_components(membership: np.ndarray, inside: np.ndarray) -> np.ndarray:
    """Flip every connected component but the largest of each cluster.

    The flipped components join the cluster that surrounds them, so a split
    normally yields two pieces rather than a scatter of noise cells.
    """
    cleaned = membership.copy()
    for cluster in (0, 1):
        components, count = ndimage.label(inside & (membership == cluster))
        if count > 1:
            sizes = np.bincount(components.ravel())[1:]
            largest = int(np.argmax(sizes)) + 1
            cleaned[(components > 0) & (components != largest)] = 1 - cluster
    return cleaned


def split_by_aspect_variance(
    units: gpd.GeoDataFrame,
    aspect: xr.DataArray,
    *,
    max_area_m2: float,
) -> gpd.GeoDataFrame:
    """Split every unit over the maximum area in two by its aspect.

    A unit over ``max_area_m2`` has its cells clustered by k-means (k = 2) on
    their aspect unit vectors, seeded so the split reproduces. Where that
    leaves one cluster with under five percent of the cells -- a facet of one
    aspect, where the k-means has only found noise -- the cells are clustered
    by position instead, so the unit still halves. Every connected component
    of a cluster but the largest is handed to the other cluster, and each
    remaining component becomes a unit. The pass repeats until no unit is
    over the maximum.

    Args:
        units: Units with ``basin_id``, ``side`` and ``geometry``.
        aspect: The downhill azimuth grid the units were cut on.
        max_area_m2: The largest area a unit may keep.

    Returns:
        The units with ``basin_id``, ``side``, ``area_m2`` and ``geometry`` on
        a fresh index; units under the maximum are returned as they came.
    """
    transform = aspect.rio.transform()
    width = aspect.shape[1]
    east, north = _unit_vectors(aspect.to_numpy())
    current = units[[_BASIN, _SIDE, _GEOMETRY]].reset_index(drop=True)
    while True:
        over = current.geometry.area > max_area_m2
        if not over.any():
            break
        labels = _rasterize_units(current, aspect.shape, transform)
        cells_by_unit = _cells_by_label(labels)
        pieces = []
        for position, row in enumerate(current.itertuples(index=False), start=1):
            if not over.iloc[position - 1] or position not in cells_by_unit:
                pieces.append((row.basin_id, row.side, row.geometry))
                continue
            rows, cols = np.divmod(cells_by_unit[position], width)
            # Work in the unit's bounding window, not the whole grid, so the
            # component labelling and polygonising cost the unit's size.
            row_off, col_off = int(rows.min()), int(cols.min())
            height = int(rows.max()) - row_off + 1
            window = windows.Window(
                col_off, row_off, int(cols.max()) - col_off + 1, height
            )
            local_rows, local_cols = rows - row_off, cols - col_off
            inside = np.zeros((window.height, window.width), dtype=bool)
            inside[local_rows, local_cols] = True
            membership = np.zeros(inside.shape, dtype=int)
            membership[local_rows, local_cols] = _cluster_cells(
                east[rows, cols], north[rows, cols], rows, cols
            )
            membership = _keep_largest_components(membership, inside)
            window_transform = windows.transform(window, transform)
            for cluster in (0, 1):
                component_labels, _ = ndimage.label(inside & (membership == cluster))
                for geometry, _value in features.shapes(
                    component_labels.astype(np.int32),
                    mask=component_labels > 0,
                    transform=window_transform,
                    connectivity=4,
                ):
                    pieces.append((row.basin_id, row.side, shape(geometry)))
        if len(pieces) == len(current):
            msg = "a unit over the maximum area could not be split"
            raise RuntimeError(msg)
        current = gpd.GeoDataFrame(
            {
                _BASIN: np.asarray([p[0] for p in pieces], dtype=np.int64),
                _SIDE: [p[1] for p in pieces],
            },
            geometry=[p[2] for p in pieces],
            crs=units.crs,
        )
    current[_AREA] = current.geometry.area
    return current[[_BASIN, _SIDE, _AREA, _GEOMETRY]]


# --------------------------------------------------------------------------
# The whole delineation
# --------------------------------------------------------------------------


def _check_grids(dem: xr.DataArray, slope: xr.DataArray, aspect: xr.DataArray) -> None:
    """Refuse grids that do not share one projected cell layout."""
    for name, grid in (("dem", dem), ("slope", slope), ("aspect", aspect)):
        if grid.rio.crs is None:
            msg = f"the {name} grid carries no coordinate reference system"
            raise ValueError(msg)
        if grid.rio.crs.is_geographic:
            msg = (
                f"the {name} grid is in {grid.rio.crs}, a geographic system; "
                "slope units are cut on a projected grid such as NZGD2000 / NZTM"
            )
            raise ValueError(msg)
        if grid.shape != dem.shape:
            msg = f"the {name} grid has shape {grid.shape} and the dem {dem.shape}"
            raise ValueError(msg)


def delineate_slope_units(
    dem: xr.DataArray,
    slope: xr.DataArray,
    aspect: xr.DataArray,
    *,
    channel_threshold_ha: float,
    aspect_tolerance_deg: float,
    min_area_ha: float,
    max_area_ha: float,
) -> gpd.GeoDataFrame:
    """Cut the slope units of a DEM, the ``r.slopeunits`` way [alvioli_2016].

    The stages run in this order: :func:`landloss.common.utils.hydrology.route_grid`
    (priority flood, D8 receivers, accumulation of cell area),
    :func:`channel_cells`, :func:`channel_links`, :func:`link_catchments`,
    :func:`split_half_basins`, :func:`units_to_polygons`,
    :func:`merge_similar_aspect`, then :func:`split_by_aspect_variance` and
    :func:`merge_similar_aspect` again, alternating up to three times while a
    unit is still over the maximum. Every cell of the DEM ends in exactly one
    unit; none is dropped. Where no cell reaches ``channel_threshold_ha`` (a
    small extent, or a high threshold) the extent is one basin on the left
    bank, so the result is one unit rather than none.

    Args:
        dem: Elevation on a projected grid, NaN off the ground.
        slope: Slope in degrees on the same grid; its mean is read per unit.
        aspect: Downhill azimuth in degrees clockwise from north on the same
            grid.
        channel_threshold_ha: Upstream area at which a cell is a channel.
        aspect_tolerance_deg: Neighbours whose mean aspects differ by less
            than this are merged.
        min_area_ha: Units under this are absorbed into a neighbour.
        max_area_ha: Units over this are split.

    Returns:
        One row per unit with ``basin_id``, ``side``, the
        :data:`STATISTIC_COLUMNS`, ``channel_threshold_ha`` and ``geometry``,
        on a fresh index in raster order. The caller mints ``unit_id`` and
        reads ``flatland_share``.

    Raises:
        ValueError: If a grid has no CRS, a geographic one, or another shape.
    """
    _check_grids(dem, slope, aspect)
    transform = dem.rio.transform()
    dx_m, dy_m = abs(transform.a), abs(transform.e)
    crs = str(dem.rio.crs)

    routing = hydrology.route_grid(dem.to_numpy().astype(float), dx_m=dx_m, dy_m=dy_m)
    channels = channel_cells(
        routing.upstream_area_m2, threshold_m2=channel_threshold_ha * M2_PER_HA
    )
    links = channel_links(channels, routing.receiver)
    catchments = link_catchments(routing.receiver, routing.order, links)
    half = split_half_basins(catchments, links, routing.receiver, aspect.to_numpy())
    units = units_to_polygons(half, transform, crs)
    units = units.join(_unit_statistics(units, dem, slope, aspect))

    min_area_m2 = min_area_ha * M2_PER_HA
    max_area_m2 = max_area_ha * M2_PER_HA
    units = merge_similar_aspect(
        units,
        tolerance_deg=aspect_tolerance_deg,
        min_area_m2=min_area_m2,
        max_area_m2=max_area_m2,
    )
    for _ in range(_MAX_PASSES):
        if not (units.geometry.area > max_area_m2).any():
            break
        units = split_by_aspect_variance(units, aspect, max_area_m2=max_area_m2)
        units = units.join(_unit_statistics(units, dem, slope, aspect)[[_ASPECT]])
        units = merge_similar_aspect(
            units,
            tolerance_deg=aspect_tolerance_deg,
            min_area_m2=min_area_m2,
            max_area_m2=max_area_m2,
        )

    units = units[[_BASIN, _SIDE, _GEOMETRY]].reset_index(drop=True)
    statistics = _unit_statistics(units, dem, slope, aspect)
    result = units.join(statistics)
    result["channel_threshold_ha"] = float(channel_threshold_ha)
    columns = [_BASIN, _SIDE, *STATISTIC_COLUMNS, "channel_threshold_ha", _GEOMETRY]
    return result[columns]
