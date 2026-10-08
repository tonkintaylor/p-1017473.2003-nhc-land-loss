"""Tiles for running a fine-grid step over an extent too large to hold whole.

A 1 m grid over a territorial authority is several hundred million cells, and
a step that holds a few of them, with their working arrays, runs out of memory.
Such a step runs tile by tile instead: each tile is a core, which the tile
owns, and a margin around it, which is read so that anything reaching the core
is seen whole. A vector feature belongs to the tile whose core holds its
representative point, so a feature is kept once, from the one tile that saw it
whole, and features at a seam are neither lost nor doubled.

The margin has to be wider than the largest feature the step makes. A feature
larger than the margin can be cut at the edge of the tile that owns it; the
step that tiles says what margin it uses and why.

See ``.agents/plans/running-per-territorial-authority.md``, phase 1.
"""

import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import rioxarray
import shapely
import xarray as xr
from rasterio import windows
from rasterio.transform import Affine

# The bounds of a box, as (minx, miny, maxx, maxy).
Bounds = tuple[float, float, float, float]


@dataclass(frozen=True)
class Tile:
    """One tile of a raster: the cells it owns and the cells it reads.

    Attributes:
        row: The tile's row in the tile grid, from the north.
        col: The tile's column in the tile grid, from the west.
        core: The window of cells the tile owns.
        outer: The window of cells the tile reads, the core plus the margin,
            clipped to the raster.
        core_bounds: The core as (minx, miny, maxx, maxy) in the raster's
            system.
    """

    row: int
    col: int
    core: windows.Window
    outer: windows.Window
    core_bounds: Bounds


def raster_cells(path: Path | str) -> int:
    """Return how many cells a raster on disk holds, without reading it."""
    with rasterio.open(path) as source:
        return source.width * source.height


def tile_grid(
    path: Path | str, *, core_m: float, margin_m: float, align_cells: int = 1
) -> list[Tile]:
    """Cut a raster's grid into tiles of whole cells, row by row from the north.

    Args:
        path: The raster on disk whose grid is cut.
        core_m: The side of a tile's core, in metres. Rounded to whole cells;
            the last row and column of tiles are cut short at the raster edge.
        margin_m: The width read around each core, in metres, rounded up to
            whole cells.
        align_cells: The core and the margin are rounded up to a multiple of
            this many cells, so every tile's outer window starts on the same
            blocks of cells as the whole grid does. A step that averages
            blocks of cells from the window's corner (step 12's 3 m
            catchment grid) needs its block size here.

    Returns:
        The tiles. Their cores cover every cell exactly once.
    """
    with rasterio.open(path) as source:
        transform = source.transform
        width, height = source.width, source.height
    cell = abs(transform.a)
    core_cells = _round_up(max(1, round(core_m / cell)), align_cells)
    margin_cells = _round_up(math.ceil(margin_m / cell), align_cells)

    tiles = []
    for row, row_off in enumerate(range(0, height, core_cells)):
        for col, col_off in enumerate(range(0, width, core_cells)):
            core = windows.Window(
                col_off,
                row_off,
                min(core_cells, width - col_off),
                min(core_cells, height - row_off),
            )
            outer_col = max(0, col_off - margin_cells)
            outer_row = max(0, row_off - margin_cells)
            outer = windows.Window(
                outer_col,
                outer_row,
                min(width, col_off + core.width + margin_cells) - outer_col,
                min(height, row_off + core.height + margin_cells) - outer_row,
            )
            tiles.append(Tile(row, col, core, outer, window_bounds(core, transform)))
    return tiles


def _round_up(cells: int, multiple: int) -> int:
    """Round a count of cells up to a whole multiple."""
    return math.ceil(cells / multiple) * multiple


def window_bounds(window: windows.Window, transform: Affine) -> Bounds:
    """Return a window's (minx, miny, maxx, maxy) on a north-up grid."""
    west = transform.c + window.col_off * transform.a
    east = west + window.width * transform.a
    north = transform.f + window.row_off * transform.e
    south = north + window.height * transform.e
    return (float(west), float(south), float(east), float(north))


def read_window(path: Path | str, window: windows.Window) -> xr.DataArray:
    """Read one window of a single-band raster, nodata as NaN.

    The cells are exactly those a whole read would hold at the same rows and
    columns, on a grid that keeps the raster's CRS and transform, so a step
    reads a tile as it would read the whole raster.
    """
    with rioxarray.open_rasterio(path, masked=True) as opened:
        grid = (
            opened.squeeze("band", drop=True)
            .isel(
                y=slice(window.row_off, window.row_off + window.height),
                x=slice(window.col_off, window.col_off + window.width),
            )
            .load()
        )
    grid.encoding.pop("_FillValue", None)
    return grid.rio.write_nodata(np.nan)


def owned_by(frame: gpd.GeoDataFrame, core_bounds: Bounds) -> np.ndarray:
    """Return which features a tile owns, by where their representative points fall.

    The core is closed on the west and south and open on the east and north,
    so a point on a seam belongs to exactly one tile. The representative point
    is always inside the feature, unlike the centroid of a crescent.

    Args:
        frame: The features one tile made.
        core_bounds: The tile's core, as :attr:`Tile.core_bounds`.

    Returns:
        A boolean array, one per row of ``frame``.
    """
    if frame.empty:
        return np.zeros(0, dtype=bool)
    minx, miny, maxx, maxy = core_bounds
    points = shapely.point_on_surface(frame.geometry.to_numpy())
    x = shapely.get_x(points)
    y = shapely.get_y(points)
    return (x >= minx) & (x < maxx) & (y >= miny) & (y < maxy)
