"""Tests for cutting a raster into tiles with margins.

Everything is synthetic and written to a temporary directory.
"""

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401  # registers the .rio accessor
import xarray as xr
from shapely.geometry import box

from landloss.common.utils import tiles
from landloss.common.utils.terrain import write_raster
from landloss.domain import constants

ROWS, COLUMNS = 230, 170
CELL = 2.0
WEST, NORTH = 1_750_000.0, 5_430_000.0

# rioxarray multiplies an affine transform with `*`, which affine 3 warns
# about; the suite turns warnings into failures, so the tests that write a
# raster ignore that one warning, as test_terrain.py does.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)


def grid(tmp_path):
    """Write a raster whose every cell holds its own flat index."""
    values = np.arange(ROWS * COLUMNS, dtype="float64").reshape(ROWS, COLUMNS)
    values[5, 7] = np.nan
    raster = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": NORTH - CELL * (np.arange(ROWS) + 0.5),
            "x": WEST + CELL * (np.arange(COLUMNS) + 0.5),
        },
    ).rio.write_crs(constants.DEFAULT_CRS)
    return write_raster(raster.rio.write_nodata(np.nan), tmp_path / "grid.tif")


def test_the_cores_cover_every_cell_once(tmp_path):
    path = grid(tmp_path)
    covered = np.zeros((ROWS, COLUMNS), dtype=int)
    for tile in tiles.tile_grid(path, core_m=100.0, margin_m=15.0):
        core = tile.core
        covered[
            core.row_off : core.row_off + core.height,
            core.col_off : core.col_off + core.width,
        ] += 1
    assert (covered == 1).all()


def test_the_margin_reaches_round_the_core_and_stops_at_the_edge(tmp_path):
    path = grid(tmp_path)
    for tile in tiles.tile_grid(path, core_m=100.0, margin_m=15.0):
        core, outer = tile.core, tile.outer
        # 15 m at 2 m cells rounds up to 8 cells.
        assert outer.col_off == max(0, core.col_off - 8)
        assert outer.row_off == max(0, core.row_off - 8)
        assert outer.col_off + outer.width == min(
            COLUMNS, core.col_off + core.width + 8
        )
        assert outer.row_off + outer.height == min(ROWS, core.row_off + core.height + 8)


def test_a_window_reads_the_cells_a_whole_read_holds_there(tmp_path):
    path = grid(tmp_path)
    whole = tiles.read_window(
        path, tiles.tile_grid(path, core_m=1e6, margin_m=0)[0].outer
    )
    for tile in tiles.tile_grid(path, core_m=100.0, margin_m=15.0):
        outer = tile.outer
        part = tiles.read_window(path, outer)
        expected = whole.isel(
            y=slice(outer.row_off, outer.row_off + outer.height),
            x=slice(outer.col_off, outer.col_off + outer.width),
        )
        np.testing.assert_array_equal(part.to_numpy(), expected.to_numpy())
        assert part.rio.transform() == expected.rio.transform()
        assert part.rio.crs == expected.rio.crs


def test_a_feature_on_a_seam_belongs_to_exactly_one_tile(tmp_path):
    path = grid(tmp_path)
    grid_tiles = tiles.tile_grid(path, core_m=100.0, margin_m=15.0)
    # Small squares centred on every core corner and edge midpoint, so many
    # representative points fall exactly on a seam.
    centres = {
        (x, y)
        for tile in grid_tiles
        for x in (tile.core_bounds[0], tile.core_bounds[2])
        for y in (tile.core_bounds[1], tile.core_bounds[3])
    }
    features = gpd.GeoDataFrame(
        geometry=[box(x - 1, y - 1, x + 1, y + 1) for x, y in sorted(centres)],
        crs=constants.DEFAULT_CRS,
    )
    # Only those inside the raster can be owned; the rest lie off its edge.
    owners = sum(
        tiles.owned_by(features, tile.core_bounds).astype(int) for tile in grid_tiles
    )
    minx, miny = WEST, NORTH - ROWS * CELL
    maxx, maxy = WEST + COLUMNS * CELL, NORTH
    points = features.geometry.representative_point()
    inside = (
        (points.x >= minx) & (points.x < maxx) & (points.y >= miny) & (points.y < maxy)
    ).to_numpy()
    assert (owners[inside] == 1).all()
    assert (owners[~inside] == 0).all()


def test_aligned_tiles_start_on_whole_blocks(tmp_path):
    path = grid(tmp_path)
    # 100 m and 15 m at 2 m cells are 50 and 8 cells; aligned to 3 they are 51
    # and 9, so every outer window starts on a multiple of 3.
    for tile in tiles.tile_grid(path, core_m=100.0, margin_m=15.0, align_cells=3):
        assert tile.outer.col_off % 3 == 0
        assert tile.outer.row_off % 3 == 0
        assert tile.core.col_off % 51 == 0
        assert tile.core.row_off % 51 == 0
