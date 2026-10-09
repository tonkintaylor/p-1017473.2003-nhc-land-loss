"""Tests for the step a wall line makes in the 1 m DEM.

The rasters are written to tmp_path the way test_terrain.py writes its DEMs.
"""

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import LineString

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.exposure.rw import lines as wl

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; see test_terrain.py.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, so that a raster written to
# tmp_path sits where a Wellington raster would sit rather than at the origin.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0

# The rasters run this far beyond the block on every side, so a boundary on
# the block's edge is still read rather than falling off the raster.
RASTER_MARGIN_M = 50.0
SIZE_M = 300

CRS = constants.DEFAULT_CRS
TOLERANCE_M = 3.0
ROAD_DISTANCE_M = 10.0
MIN_SLOPE_DEG = 5.0
MIN_HEIGHT_M = constants.MIN_WALL_HEIGHT_M

# Everything below y = 48 m (local) has a 0.4 m face: the mapped walls and the
# cut/fill line sit there, the rest of the lines sit above it.
LOW_FACE_BELOW_Y = 48.0
LOW_FACE_M = 0.4
HIGH_FACE_M = 2.0

# The terrace step in the synthetic 1 m DEM, along the A/C boundary.
STEP_AT_Y = 100.0
STEP_M = 2.0
# The step along the top edge of the cut slope in D.
CUT_TOP_Y = 150.0
CUT_STEP_M = 1.5


def make_dem(elevation, resolution: float = 10.0):
    """Wrap an elevation array as a north-up DEM in NZTM."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape

    # y descending, which is how a GeoTIFF stores a north-up raster; x ascending.
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)

    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def local(x, y):
    """Move a local coordinate in metres into NZTM."""
    return (ORIGIN_EASTING + x, ORIGIN_NORTHING + y)


def line(*points):
    """Build a line from local coordinates."""
    return LineString([local(x, y) for x, y in points])


def write_grid(path, value_of, resolution: float = 1.0):
    """Write a raster whose value at each cell centre is value_of(x, y), local."""
    cells = int(SIZE_M / resolution)
    offsets = resolution * (np.arange(cells) + 0.5) - RASTER_MARGIN_M
    x, y = np.meshgrid(offsets, offsets[::-1])
    grid = make_dem(value_of(x, y), resolution).rename(path.stem)
    grid = grid.assign_coords(x=grid.x - RASTER_MARGIN_M, y=grid.y - RASTER_MARGIN_M)
    return write_raster(grid, path)


@pytest.fixture
def rasters(tmp_path):
    """The terrain rasters over the neighbourhood, written to tmp_path."""
    return {
        "face": write_grid(
            tmp_path / "face.tif",
            lambda x, y: np.where(y < LOW_FACE_BELOW_Y, LOW_FACE_M, HIGH_FACE_M),
        ),
        # Fill (positive) in the north half, cut (negative) in the south.
        "residual": write_grid(
            tmp_path / "residual.tif", lambda x, y: np.where(y >= 100.0, 1.0, -1.0)
        ),
        "slope_3m": write_grid(tmp_path / "slope-3m.tif", lambda x, y: 15.0 + 0 * x),
        # Sloping in the west half, flat in the east half.
        "slope_10m": write_grid(
            tmp_path / "slope-10m.tif", lambda x, y: np.where(x < 100.0, 15.0, 2.0)
        ),
        # Downhill to the south everywhere, so uphill is north.
        "aspect": write_grid(tmp_path / "aspect-3m.tif", lambda x, y: 180.0 + 0 * x),
        # Rising 0.2 m per metre to the north, with a 2 m step along y = 100:
        # the boundary between A and C is stepped, every other one is not. A
        # second, 1.5 m step along the top edge of the cut slope in D.
        "dem": write_grid(
            tmp_path / "dem-1m.tif",
            lambda x, y: (
                0.2 * y
                + np.where(y >= STEP_AT_Y, STEP_M, 0.0)
                + np.where(
                    (y >= CUT_TOP_Y) & (x > 110.0) & (x < 190.0), CUT_STEP_M, 0.0
                )
            ),
        ),
    }


# -- the sources ---------------------------------------------------------------


@ignore_affine_matmul
def test_the_step_is_read_across_a_stepped_line_and_not_an_even_slope(rasters):
    """A line along the terrace step reads 2 m; along or down the even slope, 0."""
    lines = gpd.GeoSeries(
        [
            line((10, 100), (90, 100)),  # along the 2 m step
            line((10, 60), (90, 60)),  # along the even slope
            line((50, 20), (50, 80)),  # straight down the even slope
        ],
        crs=CRS,
    )
    steps = wl.step_height_m(lines, rasters["dem"], spacing_m=1.0)
    assert steps.iloc[0] == pytest.approx(STEP_M, abs=0.05)
    assert steps.iloc[1] == pytest.approx(0.0, abs=0.05)
    assert steps.iloc[2] == pytest.approx(0.0, abs=0.05)


def test_the_step_spans_must_be_ordered():
    with pytest.raises(ValueError, match="must be more than"):
        wl.step_height_m(
            gpd.GeoSeries([], crs=CRS), "x.tif", spacing_m=1.0, near_m=2.0, far_m=1.0
        )


# -- the snap, the collapse and the split ------------------------------------


# -- the attributes -----------------------------------------------------------


# -- the whole chain -----------------------------------------------------------


# -- the script ----------------------------------------------------------------
