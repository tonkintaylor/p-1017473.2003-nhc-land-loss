"""Flow routing on a DEM: depression filling, D8 directions and accumulation.

Enough hydrology to compute upstream contributing area, which is what a
topographic wetness index needs. No hydrology package is in the environment, and
the grids this is used on -- a coarse ~1 km DEM over one region -- are small
enough that a straightforward pure-Python priority flood is quick.

The method is the priority-flood of Barnes, Lehman & Mulla (2014): every cell on
the grid edge or next to nodata is an outlet, cells are visited in order of
rising (filled) elevation from the outlets inwards, and a cell lower than the
one it was reached from is raised to it. That visiting order is a valid
upstream-to-downstream ordering in reverse, which is what makes accumulation a
single pass. Flow directions are D8 steepest descent on the filled surface; a
cell with no strictly lower neighbour -- a flat, or a filled depression -- drains
to the neighbour the flood reached it from, so flats drain towards their outlet
rather than stalling.

Cell spacing may differ between the two axes and from row to row, as it does on
a geographic grid, so distances are passed in metres per row.
"""

import heapq
from typing import NamedTuple

import numpy as np

# The eight neighbours as (row offset, column offset).
_NEIGHBOURS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)

# Receiver value for a cell that drains off the grid or into nodata.
OUTLET = -1


def priority_flood(dem: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fill depressions and record the order and parent of the flood.

    Args:
        dem: Elevation, 2D. NaN is nodata, and a cell next to it is an outlet,
            which is how the sea is handled.

    Returns:
        ``(filled, order, parent)``. ``filled`` is the DEM with every depression
        raised to its spill level, NaN where the input was. ``order`` is the
        flat index of every valid cell in the order the flood visited it, which
        is non-decreasing in filled elevation. ``parent`` holds, per flat index,
        the flat index of the cell the flood reached it from, or :data:`OUTLET`
        for a seed cell.
    """
    rows, cols = dem.shape
    filled = dem.astype(float).copy()
    valid = ~np.isnan(filled)
    visited = ~valid
    parent = np.full(rows * cols, OUTLET, dtype=np.int64)
    order = []
    heap = []

    # Seed with every valid cell on the edge of the grid or beside nodata.
    padded = np.pad(valid, 1, constant_values=False)
    interior = np.ones_like(valid)
    for dr, dc in _NEIGHBOURS:
        interior &= padded[1 + dr : 1 + dr + rows, 1 + dc : 1 + dc + cols]
    for r, col in zip(*np.nonzero(valid & ~interior), strict=True):
        heapq.heappush(heap, (filled[r, col], r * cols + col))
        visited[r, col] = True

    while heap:
        z, idx = heapq.heappop(heap)
        order.append(idx)
        r, col = divmod(idx, cols)
        for dr, dc in _NEIGHBOURS:
            nr, nc = r + dr, col + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc]:
                visited[nr, nc] = True
                filled[nr, nc] = max(filled[nr, nc], z)
                parent[nr * cols + nc] = idx
                heapq.heappush(heap, (filled[nr, nc], nr * cols + nc))

    return filled, np.asarray(order, dtype=np.int64), parent


def d8_receivers(
    filled: np.ndarray, parent: np.ndarray, dx_m: np.ndarray, dy_m: float
) -> np.ndarray:
    """Give each cell the neighbour it drains to, by D8 steepest descent.

    Args:
        filled: The depression-filled DEM from :func:`priority_flood`.
        parent: The flood parents from :func:`priority_flood`, used where a
            cell has no strictly lower neighbour.
        dx_m: The east-west cell spacing in metres, one value per row.
        dy_m: The north-south cell spacing in metres.

    Returns:
        Per flat index, the flat index of the receiving cell, or
        :data:`OUTLET` where the cell drains off the grid.
    """
    rows, cols = filled.shape
    best_drop = np.zeros((rows, cols))
    receiver = np.full((rows, cols), OUTLET, dtype=np.int64)
    padded = np.pad(filled, 1, constant_values=np.nan)
    row_index, col_index = np.indices((rows, cols))
    flat_index = row_index * cols + col_index
    for dr, dc in _NEIGHBOURS:
        neighbour = padded[1 + dr : 1 + dr + rows, 1 + dc : 1 + dc + cols]
        distance = np.hypot(dx_m[:, None] * dc, dy_m * dr)
        drop = (filled - neighbour) / distance
        steeper = np.nan_to_num(drop, nan=-np.inf) > best_drop
        best_drop = np.where(steeper, drop, best_drop)
        receiver = np.where(steeper, flat_index + dr * cols + dc, receiver)

    receiver = receiver.ravel()
    no_descent = (receiver == OUTLET) & ~np.isnan(filled.ravel())
    receiver[no_descent] = parent[no_descent]
    return receiver


def flow_accumulation(
    receiver: np.ndarray, order: np.ndarray, weight: np.ndarray
) -> np.ndarray:
    """Sum each cell's weight and everything upstream of it.

    Args:
        receiver: Per flat index, the receiving cell from :func:`d8_receivers`.
        order: The flood order from :func:`priority_flood`; downstream cells
            come earlier, so walking it backwards visits upstream cells first.
        weight: What each cell contributes, 2D -- its area, for upstream area.

    Returns:
        The accumulated weight, including each cell's own, NaN where the
        weight is.
    """
    shape = weight.shape
    total = weight.astype(float).ravel().copy()
    for idx in order[::-1]:
        downstream = receiver[idx]
        if downstream != OUTLET:
            total[downstream] += total[idx]
    return total.reshape(shape)


class FlowRouting(NamedTuple):
    """The routing of one grid, as :func:`route_grid` returns it."""

    #: The depression-filled DEM, NaN where the input was.
    filled: np.ndarray
    #: The flat index of every valid cell in flood order, downstream first.
    order: np.ndarray
    #: Per flat index, the receiving cell's flat index, or :data:`OUTLET`.
    receiver: np.ndarray
    #: Upstream contributing area per cell in square metres, the cell's own
    #: included, NaN where the DEM is.
    upstream_area_m2: np.ndarray


def route_grid(dem: np.ndarray, *, dx_m: float, dy_m: float) -> FlowRouting:
    """Fill, route and accumulate a grid of equal cells in one call.

    The three stages are :func:`priority_flood`, :func:`d8_receivers` and
    :func:`flow_accumulation` weighted by the cell area, which is what a
    projected grid such as NZTM wants; a geographic grid, whose cell width
    changes with latitude, calls the three stages itself with a spacing per row.

    Args:
        dem: Elevation, 2D. NaN is nodata.
        dx_m: The east-west cell spacing in metres.
        dy_m: The north-south cell spacing in metres.

    Returns:
        The filled DEM, the flood order, the receivers and the upstream area.
    """
    filled, order, parent = priority_flood(dem)
    receiver = d8_receivers(filled, parent, np.full(dem.shape[0], dx_m), dy_m)
    cell_area = np.where(np.isnan(filled), np.nan, dx_m * dy_m)
    upstream_area_m2 = flow_accumulation(receiver, order, cell_area)
    return FlowRouting(filled, order, receiver, upstream_area_m2)
