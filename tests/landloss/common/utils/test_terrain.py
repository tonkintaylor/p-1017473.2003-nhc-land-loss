"""Tests for the terrain derivatives.

Every DEM here is built by hand out of numpy, on shapes whose slope and
topographic position can be worked out on paper: a plane, a ramp of known
gradient, a cone, a basin. Nothing is downloaded, and nothing is compared
against a stored expected array, because an expected array records only what the
code did the day it was written. A ramp rising exactly one cell height per cell
is 45 degrees whatever anybody implements, and that is the sort of claim these
tests make.
"""

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import Point, box

from landloss.common.utils.terrain import (
    CUT_FILL_RESIDUAL_NAME,
    DOWNHILL_AZIMUTH_NAME,
    PROFILE_CURVATURE_NAME,
    SLOPE_NAME,
    TOPOGRAPHIC_POSITION_NAME,
    VEGETATION_HEIGHT_NAME,
    azimuth_offsets,
    azimuth_sd_degrees,
    block_mean,
    cell_size,
    cut_fill_residual,
    downhill_azimuth_degrees,
    mean_azimuth_degrees,
    profile_curvature,
    sample_at_points,
    slope_degrees,
    topographic_position,
    vegetation_height,
    window_in_cells,
    write_raster,
    zonal_azimuth_mean,
    zonal_statistic,
)
from landloss.domain import constants

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about. It is a warning about how rioxarray
# calls affine, there is nothing to fix on this side, and the suite turns every
# warning into a failure -- so the tests that put a raster on disk ignore this
# one specifically rather than the whole category.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, so that a raster written to
# tmp_path sits where a Wellington raster would sit rather than at the origin.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0


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


def ramp(size: int, rise_per_cell: float, axis: int = 1, sign: int = 1):
    """Build a planar ramp rising by a fixed amount per cell along one axis."""
    steps = sign * rise_per_cell * np.arange(size, dtype=float)
    return np.tile(steps, (size, 1)) if axis == 1 else np.tile(steps, (size, 1)).T


def interior(values: xr.DataArray, border: int = 1):
    """Strip the NaN border off a derivative so the real answers can be compared."""
    return values.to_numpy()[border:-border, border:-border]


def cone(size: int, peak_height: float, resolution: float = 10.0):
    """Build a symmetric cone, highest in the middle and falling away evenly."""
    centre = (size - 1) / 2
    rows, columns = np.meshgrid(
        np.arange(size, dtype=float), np.arange(size, dtype=float), indexing="ij"
    )
    distance = np.hypot(rows - centre, columns - centre) * resolution
    return peak_height - distance


# --- slope --------------------------------------------------------------------


def test_a_flat_plane_has_no_slope() -> None:
    """Ground that does not change height cannot have a gradient."""
    dem = make_dem(np.full((7, 7), 42.0))

    slope = slope_degrees(dem, resolution=10.0)

    assert interior(slope) == pytest.approx(0.0)


def test_a_ramp_rising_one_cell_height_per_cell_is_forty_five_degrees() -> None:
    """The check that catches a wrong cell size or a transposed axis at once."""
    resolution = 10.0
    dem = make_dem(ramp(7, rise_per_cell=resolution), resolution=resolution)

    slope = slope_degrees(dem, resolution=resolution)

    assert interior(slope) == pytest.approx(45.0)


@pytest.mark.parametrize("axis", [0, 1])
@pytest.mark.parametrize("sign", [1, -1])
def test_slope_does_not_depend_on_which_way_the_ramp_faces(
    axis: int, sign: int
) -> None:
    """A north-facing hillside is as steep as the south-facing one opposite it."""
    resolution = 10.0
    dem = make_dem(
        ramp(7, rise_per_cell=resolution, axis=axis, sign=sign), resolution=resolution
    )

    slope = slope_degrees(dem, resolution=resolution)

    assert interior(slope) == pytest.approx(45.0)


def test_halving_the_cell_size_doubles_the_gradient() -> None:
    """The same rise over half the run is twice as steep, which is what 'run' means."""
    elevation = ramp(7, rise_per_cell=1.0)

    coarse = slope_degrees(make_dem(elevation, resolution=10.0), resolution=10.0)
    fine = slope_degrees(make_dem(elevation, resolution=5.0), resolution=5.0)

    coarse_gradient = np.tan(np.radians(interior(coarse)))
    fine_gradient = np.tan(np.radians(interior(fine)))
    assert fine_gradient == pytest.approx(2 * coarse_gradient)


def test_the_edge_cells_have_no_slope_at_all() -> None:
    """A one-sided gradient would read as a plausible small number and mislead."""
    dem = make_dem(ramp(7, rise_per_cell=10.0))

    slope = slope_degrees(dem, resolution=10.0).to_numpy()

    assert np.isnan(slope[0, :]).all()
    assert np.isnan(slope[-1, :]).all()
    assert np.isnan(slope[:, 0]).all()
    assert np.isnan(slope[:, -1]).all()


def test_slope_is_never_negative_or_past_vertical() -> None:
    """Slope is the magnitude of a gradient, so it lives in [0, 90] by definition."""
    rng = np.random.default_rng(seed=1017473)
    dem = make_dem(rng.normal(loc=150.0, scale=40.0, size=(15, 15)))

    slope = interior(slope_degrees(dem, resolution=10.0))

    assert (slope >= 0).all()
    assert (slope <= 90).all()


def test_nodata_left_as_nan_spreads_only_to_the_cells_that_touch_it() -> None:
    """A masked cell must not silently become a cliff, nor blank out the whole grid."""
    elevation = np.full((7, 7), 10.0)
    elevation[3, 3] = np.nan
    dem = make_dem(elevation)

    slope = slope_degrees(dem, resolution=10.0).to_numpy()

    assert np.isnan(slope[2:5, 2:5]).all()
    assert slope[1, 1] == pytest.approx(0.0)


def test_the_result_keeps_the_grid_and_the_projection() -> None:
    """A derivative that cannot be written back out beside its DEM is no use."""
    dem = make_dem(ramp(7, rise_per_cell=10.0))

    slope = slope_degrees(dem, resolution=10.0)

    assert slope.name == SLOPE_NAME
    assert slope.shape == dem.shape
    assert slope.rio.crs == dem.rio.crs
    assert slope["x"].to_numpy() == pytest.approx(dem["x"].to_numpy())


def test_a_dem_with_a_band_dimension_is_rejected() -> None:
    """A GeoTIFF read without a squeeze keeps its band, and would compute nonsense."""
    dem = make_dem(np.zeros((7, 7))).expand_dims("band")

    with pytest.raises(ValueError, match="band"):
        slope_degrees(dem, resolution=10.0)


def test_a_non_positive_cell_size_is_rejected() -> None:
    """Dividing the rise by zero run would report every hillside as vertical."""
    dem = make_dem(np.zeros((7, 7)))

    with pytest.raises(ValueError, match="positive"):
        slope_degrees(dem, resolution=0.0)


# --- block mean ---------------------------------------------------------------


@ignore_affine_matmul
def test_a_block_mean_is_the_mean_of_the_cells_it_covers() -> None:
    """Each coarse cell averages its whole block, not the cell at its centre."""
    dem = make_dem(np.arange(36, dtype=float).reshape(6, 6))

    coarse = block_mean(dem, 3).to_numpy()

    assert coarse.shape == (2, 2)
    assert coarse[0, 0] == pytest.approx(np.mean([0, 1, 2, 6, 7, 8, 12, 13, 14]))


@ignore_affine_matmul
def test_a_block_mean_sets_the_coarse_cell_size_and_keeps_the_corner() -> None:
    """The coarse grid has to line up with the fine one it was built from."""
    dem = make_dem(np.zeros((10, 10)), resolution=10.0)

    coarse = block_mean(dem, 5)

    assert cell_size(coarse) == pytest.approx(50.0)
    assert coarse.rio.bounds() == pytest.approx(dem.rio.bounds())
    assert coarse.rio.crs == dem.rio.crs


@ignore_affine_matmul
def test_a_block_mean_drops_a_part_block_rather_than_averaging_it() -> None:
    """Seven cells at a factor of three leave one over, which is not a block."""
    dem = make_dem(np.zeros((7, 7)))

    assert block_mean(dem, 3).shape == (2, 2)


@ignore_affine_matmul
def test_a_block_mostly_of_nodata_carries_no_mean() -> None:
    """One cell of land in a block of nodata is not the block's elevation."""
    elevation = np.full((4, 4), np.nan)
    elevation[0, 0] = 5.0
    elevation[2:, 2:] = 1.0
    elevation[3, 3] = np.nan

    coarse = block_mean(make_dem(elevation), 2).to_numpy()

    assert np.isnan(coarse[0, 0])
    assert coarse[1, 1] == pytest.approx(1.0)


@ignore_affine_matmul
def test_a_planar_ramp_keeps_its_slope_when_block_averaged() -> None:
    """Averaging a plane leaves a plane, so the slope survives coarsening."""
    dem = make_dem(ramp(30, rise_per_cell=10.0), resolution=10.0)

    coarse = block_mean(dem, 3)

    assert interior(slope_degrees(coarse, cell_size(coarse))) == pytest.approx(45.0)


def test_a_block_mean_factor_under_one_is_rejected() -> None:
    """A block has to cover at least the cell it stands for."""
    with pytest.raises(ValueError, match="at least one cell"):
        block_mean(make_dem(np.zeros((4, 4))), 0)


# --- downhill direction -------------------------------------------------------
#
# Every claim below is about a hillside whose downhill direction anybody can
# point at. That is the whole risk in this function: an azimuth of 253 degrees
# looks equally plausible whether or not the y axis was read the right way up,
# and only a slope whose answer is known in advance catches the mistake.


def test_ground_that_rises_to_the_east_runs_downhill_to_the_west() -> None:
    """A bearing is clockwise from north, so due west is 270 and nothing else."""
    dem = make_dem(ramp(7, rise_per_cell=5.0, axis=1, sign=1))

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert interior(azimuth) == pytest.approx(270.0)


def test_ground_that_rises_to_the_south_runs_downhill_to_the_north() -> None:
    """The one that fails if the array's rows are mistaken for map north."""
    # Row index increases southwards on a north-up raster, so a ramp rising with
    # the row index rises to the south.
    dem = make_dem(ramp(7, rise_per_cell=5.0, axis=0, sign=1))

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert interior(azimuth) == pytest.approx(0.0)


def test_ground_that_falls_to_the_south_runs_downhill_to_the_south() -> None:
    """The mirror of the last one: the two together pin the sign of the y axis."""
    dem = make_dem(ramp(7, rise_per_cell=5.0, axis=0, sign=-1))

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert interior(azimuth) == pytest.approx(180.0)


def test_a_hillside_rising_to_the_north_east_runs_downhill_to_the_south_west() -> None:
    """A diagonal catches a bearing measured anticlockwise, which the axes do not."""
    dem = make_dem(
        ramp(7, rise_per_cell=5.0, axis=1, sign=1)
        + ramp(7, rise_per_cell=5.0, axis=0, sign=-1)
    )

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert interior(azimuth) == pytest.approx(225.0)


def test_a_raster_stored_the_other_way_up_describes_the_same_hillside() -> None:
    """The direction is read off the coordinates, so the storage order cannot matter."""
    elevation = ramp(7, rise_per_cell=5.0, axis=0, sign=1)
    north_up = make_dem(elevation)

    # The same ground, written south-up: rows reversed, and y ascending to match.
    south_up = xr.DataArray(
        elevation[::-1],
        dims=("y", "x"),
        coords={
            "y": north_up["y"].to_numpy()[::-1],
            "x": north_up["x"].to_numpy(),
        },
    ).rio.write_crs(constants.DEFAULT_CRS)

    assert interior(
        downhill_azimuth_degrees(south_up, resolution=10.0)
    ) == pytest.approx(interior(downhill_azimuth_degrees(north_up, resolution=10.0)))


def test_level_ground_has_no_downhill_direction_at_all() -> None:
    """Reporting one would send debris off in whatever direction rounding chose."""
    dem = make_dem(np.full((7, 7), 42.0))

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert np.isnan(interior(azimuth)).all()


def test_every_bearing_is_a_bearing() -> None:
    """Anything outside [0, 360) is not a compass direction, whatever it means."""
    rng = np.random.default_rng(seed=1017473)
    dem = make_dem(rng.normal(loc=150.0, scale=40.0, size=(15, 15)))

    azimuth = interior(downhill_azimuth_degrees(dem, resolution=10.0))

    assert (azimuth >= 0).all()
    assert (azimuth < 360).all()


def test_a_cone_sheds_material_away_from_its_peak_in_every_direction() -> None:
    """The check a single ramp cannot make: the bearing turns with the hillside."""
    size = 15
    dem = make_dem(cone(size, peak_height=100.0))
    peak = size // 2

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0).to_numpy()

    # Four cells around the peak, each of which can only fall away from it.
    assert azimuth[peak, peak + 3] == pytest.approx(90.0)
    assert azimuth[peak, peak - 3] == pytest.approx(270.0)
    assert azimuth[peak - 3, peak] == pytest.approx(0.0)
    assert azimuth[peak + 3, peak] == pytest.approx(180.0)


def test_the_downhill_raster_keeps_the_grid_and_the_projection() -> None:
    """It is written out and sampled beside the slope, so it stays georeferenced."""
    dem = make_dem(ramp(7, rise_per_cell=10.0))

    azimuth = downhill_azimuth_degrees(dem, resolution=10.0)

    assert azimuth.name == DOWNHILL_AZIMUTH_NAME
    assert azimuth.shape == dem.shape
    assert azimuth.rio.crs == dem.rio.crs


def test_a_dem_whose_coordinates_double_back_is_rejected() -> None:
    """Coordinates that do not run one way are not a grid, and have no direction."""
    dem = make_dem(np.zeros((7, 7)))
    scrambled = dem.assign_coords(x=np.array([0.0, 2.0, 1.0, 3.0, 4.0, 5.0, 6.0]))

    with pytest.raises(ValueError, match="do not run in one direction"):
        downhill_azimuth_degrees(scrambled, resolution=10.0)


# --- bearings and cell sizes --------------------------------------------------


@pytest.mark.parametrize(
    ("azimuth", "east", "north"),
    [(0.0, 0.0, 10.0), (90.0, 10.0, 0.0), (180.0, 0.0, -10.0), (270.0, -10.0, 0.0)],
)
def test_the_four_cardinal_bearings_move_the_way_a_compass_says(
    azimuth: float, east: float, north: float
) -> None:
    """If these four are right the sines and cosines cannot have been swapped."""
    eastward, northward = azimuth_offsets(azimuth, 10.0)

    assert float(eastward) == pytest.approx(east, abs=1e-9)
    assert float(northward) == pytest.approx(north, abs=1e-9)


def test_moving_along_a_bearing_covers_the_distance_asked_for() -> None:
    """The offsets are a decomposition, so their length is the distance itself."""
    eastward, northward = azimuth_offsets(np.array([37.0, 214.0, 301.0]), 25.0)

    assert np.hypot(eastward, northward) == pytest.approx(25.0)


def test_an_unknown_bearing_cannot_move_anything() -> None:
    """A cell with no downhill direction must not quietly end up displaced due north."""
    eastward, northward = azimuth_offsets(np.nan, 10.0)

    assert np.isnan(eastward)
    assert np.isnan(northward)


def test_the_cell_size_is_read_off_the_grid_as_a_positive_number() -> None:
    """The negative y resolution says which way the rows run, not how big a cell is."""
    assert cell_size(make_dem(np.zeros((5, 5)), resolution=25.0)) == pytest.approx(25.0)


def test_a_grid_with_rectangular_cells_is_refused() -> None:
    """Every derivative here uses one run length, and would mis-measure one axis."""
    dem = make_dem(np.zeros((5, 5)), resolution=10.0)
    stretched = dem.assign_coords(x=dem["x"].to_numpy() * 2.0)

    with pytest.raises(ValueError, match="square"):
        cell_size(stretched)


# --- topographic position -----------------------------------------------------


def test_a_plane_stands_neither_above_nor_below_itself() -> None:
    """Level ground has no position: it is exactly as high as everything near it."""
    dem = make_dem(np.full((15, 15), 8.0))

    position = topographic_position(dem, resolution=10.0, window_m=50.0)

    assert interior(position, border=2) == pytest.approx(0.0)


def test_an_even_hillside_stands_neither_above_nor_below_itself() -> None:
    """A uniform slope has as much ground above it as below, so it is not a terrace."""
    dem = make_dem(ramp(15, rise_per_cell=3.0))

    position = topographic_position(dem, resolution=10.0, window_m=50.0)

    assert interior(position, border=2) == pytest.approx(0.0)


def test_the_peak_of_a_cone_stands_above_the_land_around_it() -> None:
    """This is the signal the index exists for: a spur or terrace reads positive."""
    size = 21
    dem = make_dem(cone(size, peak_height=100.0))

    position = topographic_position(dem, resolution=10.0, window_m=70.0)

    assert float(position.to_numpy()[size // 2, size // 2]) > 0


def test_the_floor_of_a_basin_stands_below_the_land_around_it() -> None:
    """A gully has to read negative, or the index cannot separate one from a spur."""
    size = 21
    dem = make_dem(-cone(size, peak_height=100.0))

    position = topographic_position(dem, resolution=10.0, window_m=70.0)

    assert float(position.to_numpy()[size // 2, size // 2]) < 0


def test_the_index_is_in_metres_of_elevation() -> None:
    """Quoting it in metres is what lets a reviewer argue with a threshold."""
    elevation = np.zeros((15, 15))
    elevation[7, 7] = 6.0
    dem = make_dem(elevation)

    position = topographic_position(dem, resolution=10.0, window_m=30.0)

    # The knob is one cell of a 3x3 window, so its neighbourhood mean is 6/9 and
    # it stands 6 - 6/9 metres above it.
    assert float(position.to_numpy()[7, 7]) == pytest.approx(6.0 - 6.0 / 9.0)


def test_the_border_the_window_cannot_reach_over_is_nan() -> None:
    """Half a window of edge has no neighbourhood, and must not pretend to have one."""
    dem = make_dem(cone(15, peak_height=100.0))

    position = topographic_position(dem, resolution=10.0, window_m=50.0).to_numpy()

    assert np.isnan(position[:2, :]).all()
    assert np.isnan(position[:, :2]).all()
    assert np.isfinite(position[2, 2])


def test_an_even_window_is_widened_rather_than_rejected() -> None:
    """A width in metres is a length scale, not a cell count the caller must round."""
    assert window_in_cells(window_m=40.0, resolution=10.0) == 5


def test_an_odd_window_is_left_alone() -> None:
    """Widening a window that already has a centre cell would quietly blur it."""
    assert window_in_cells(window_m=30.0, resolution=10.0) == 3


def test_an_even_window_widens_the_nan_border_to_match() -> None:
    """The widening has to reach the rolling window, not just the reported count."""
    dem = make_dem(cone(15, peak_height=100.0))

    position = topographic_position(dem, resolution=10.0, window_m=40.0).to_numpy()

    # Four cells widened to five leaves two cells of border, not one.
    assert np.isnan(position[1, 1])
    assert np.isfinite(position[2, 2])


def test_a_window_narrower_than_three_cells_is_rejected() -> None:
    """With no ring of neighbours the index is zero everywhere, which reads as flat."""
    dem = make_dem(cone(15, peak_height=100.0))

    with pytest.raises(ValueError, match="at least 3 cells"):
        topographic_position(dem, resolution=10.0, window_m=20.0)


def test_the_position_keeps_the_grid_and_the_projection() -> None:
    """Like slope, this is written out and sampled, so it stays georeferenced."""
    dem = make_dem(cone(15, peak_height=100.0))

    position = topographic_position(dem, resolution=10.0, window_m=50.0)

    assert position.name == TOPOGRAPHIC_POSITION_NAME
    assert position.shape == dem.shape
    assert position.rio.crs == dem.rio.crs


def test_a_dem_with_a_band_dimension_is_rejected_here_too() -> None:
    """The rolling aggregation needs (y, x), and says so long after the real mistake."""
    dem = make_dem(np.zeros((15, 15))).expand_dims("band")

    with pytest.raises(ValueError, match="band"):
        topographic_position(dem, resolution=10.0, window_m=50.0)


# --- writing and sampling -----------------------------------------------------


@ignore_affine_matmul
def test_a_raster_round_trips_through_a_file_and_back_to_its_points(tmp_path) -> None:
    """Write then sample is the whole point of this pair, so it is tested as a pair."""
    resolution = 10.0
    elevation = np.arange(49, dtype=float).reshape(7, 7)
    dem = make_dem(elevation, resolution=resolution)

    path = write_raster(dem, tmp_path / "dem.tif")
    points = gpd.GeoSeries(
        [
            Point(dem["x"].to_numpy()[0], dem["y"].to_numpy()[0]),
            Point(dem["x"].to_numpy()[6], dem["y"].to_numpy()[6]),
        ],
        crs=constants.DEFAULT_CRS,
    )

    sampled = sample_at_points(path, points)

    assert sampled.tolist() == pytest.approx([elevation[0, 0], elevation[6, 6]])


@ignore_affine_matmul
def test_the_sampled_values_carry_the_caller_s_own_index(tmp_path) -> None:
    """A bare list aligns by position, which is wrong the moment a frame is filtered."""
    dem = make_dem(np.arange(49, dtype=float).reshape(7, 7))
    path = write_raster(dem, tmp_path / "dem.tif")
    points = gpd.GeoSeries(
        [Point(dem["x"].to_numpy()[3], dem["y"].to_numpy()[3])],
        index=["address-99"],
        crs=constants.DEFAULT_CRS,
    )

    sampled = sample_at_points(path, points)

    assert sampled.index.tolist() == ["address-99"]


@ignore_affine_matmul
def test_a_point_outside_the_raster_samples_as_nan(tmp_path) -> None:
    """The study area is a rectangle and the addresses are not, so this happens."""
    dem = make_dem(np.arange(49, dtype=float).reshape(7, 7))
    path = write_raster(dem, tmp_path / "dem.tif")
    points = gpd.GeoSeries(
        [
            Point(dem["x"].to_numpy()[0], dem["y"].to_numpy()[0]),
            Point(ORIGIN_EASTING - 50_000.0, ORIGIN_NORTHING - 50_000.0),
        ],
        index=["inside", "outside"],
        crs=constants.DEFAULT_CRS,
    )

    sampled = sample_at_points(path, points)

    assert np.isfinite(sampled["inside"])
    assert np.isnan(sampled["outside"])


@ignore_affine_matmul
def test_a_slope_raster_can_be_written_and_sampled_without_further_handling(
    tmp_path,
) -> None:
    """Slope is derived, written and sampled in one model step; prove the chain."""
    resolution = 10.0
    dem = make_dem(ramp(7, rise_per_cell=resolution), resolution=resolution)
    slope = slope_degrees(dem, resolution=resolution)

    path = write_raster(slope, tmp_path / "derived" / "slope.tif")
    points = gpd.GeoSeries(
        [Point(dem["x"].to_numpy()[3], dem["y"].to_numpy()[3])],
        crs=constants.DEFAULT_CRS,
    )

    assert sample_at_points(path, points).iloc[0] == pytest.approx(45.0)


@ignore_affine_matmul
def test_writing_creates_the_directory_it_was_pointed_at(tmp_path) -> None:
    """The caller writes then samples, and should not have to make the folder first."""
    dem = make_dem(np.zeros((7, 7)))

    path = write_raster(dem, tmp_path / "terrain" / "nested" / "dem.tif")

    assert path.exists()


def test_a_raster_without_a_projection_is_refused(tmp_path) -> None:
    """It would write, and then nothing could ever be sampled against it."""
    dem = xr.DataArray(
        np.zeros((7, 7)),
        dims=("y", "x"),
        coords={"y": np.arange(7.0)[::-1], "x": np.arange(7.0)},
    )

    with pytest.raises(ValueError, match="coordinate reference system"):
        write_raster(dem, tmp_path / "dem.tif")


# --- cut and fill residual ----------------------------------------------------


@ignore_affine_matmul
def test_a_plane_has_no_residual_against_its_own_block_mean() -> None:
    """Averaging a plane leaves the same plane, so nothing was cut or filled."""
    dem = make_dem(ramp(30, rise_per_cell=2.0), resolution=10.0)
    base = block_mean(dem, 3)

    residual = cut_fill_residual(dem, base)

    assert residual.name == CUT_FILL_RESIDUAL_NAME
    assert residual.shape == dem.shape
    assert interior(residual, border=3) == pytest.approx(0.0, abs=1e-6)


@ignore_affine_matmul
def test_a_platform_cut_into_a_hillside_reads_negative_and_fill_positive() -> None:
    """The sign is the whole point: cut below the smooth surface, fill above it."""
    elevation = ramp(30, rise_per_cell=2.0)
    elevation[12:15, 12:15] -= 5.0  # a cutting
    elevation[12:15, 18:21] += 5.0  # a platform
    dem = make_dem(elevation, resolution=10.0)

    residual = cut_fill_residual(dem, block_mean(dem, 3)).to_numpy()

    # Each feature fills one block exactly, so its own centre sits on the base
    # surface; the feature as a whole still sits below or above it.
    assert residual[12:15, 12:15].mean() < -1.0
    assert residual[12:15, 18:21].mean() > 1.0


def test_a_residual_needs_both_grids_to_be_placed() -> None:
    """A base surface with no projection cannot be laid over the DEM."""
    dem = make_dem(np.zeros((9, 9)))
    base = xr.DataArray(
        np.zeros((3, 3)),
        dims=("y", "x"),
        coords={"y": dem["y"].to_numpy()[::3], "x": dem["x"].to_numpy()[::3]},
    )

    with pytest.raises(ValueError, match="coordinate reference system"):
        cut_fill_residual(dem, base)


# --- profile curvature --------------------------------------------------------


def parabolic_ridge(size: int, curvature: float, resolution: float):
    """Build a ridge whose crest runs north-south: z = -curvature/2 * x**2."""
    offsets = (np.arange(size) - (size - 1) / 2) * resolution
    return np.tile(-curvature / 2 * offsets**2, (size, 1))


def test_a_ridge_is_convex_along_the_fall_line_and_reads_negative() -> None:
    """ArcGIS's sign: negative on a crest, which is what the amplification wants."""
    resolution = 10.0
    dem = make_dem(parabolic_ridge(9, 0.02, resolution), resolution=resolution)

    curvature = profile_curvature(dem, resolution).to_numpy()

    # Off the crest the fall line runs straight down the parabola, whose second
    # derivative is -0.02 everywhere.
    assert curvature[4, 2] == pytest.approx(-0.02)
    assert curvature[4, 6] == pytest.approx(-0.02)


def test_a_gully_is_concave_along_the_fall_line_and_reads_positive() -> None:
    """The mirror of the ridge, which pins the sign rather than the magnitude."""
    resolution = 10.0
    dem = make_dem(-parabolic_ridge(9, 0.02, resolution), resolution=resolution)

    curvature = profile_curvature(dem, resolution).to_numpy()

    assert curvature[4, 2] == pytest.approx(0.02)


def test_a_plane_has_no_profile_curvature() -> None:
    """An even hillside does not bend, and level ground has no fall line at all."""
    hillside = profile_curvature(make_dem(ramp(9, rise_per_cell=3.0)), 10.0)
    level = profile_curvature(make_dem(np.full((9, 9), 5.0)), 10.0)

    assert interior(hillside) == pytest.approx(0.0, abs=1e-12)
    assert interior(level) == pytest.approx(0.0)


def test_the_curvature_does_not_depend_on_which_way_the_rows_run() -> None:
    """Flipping the raster negates two terms together and changes nothing."""
    resolution = 10.0
    elevation = parabolic_ridge(9, 0.02, resolution) + ramp(9, 1.0, axis=0)
    north_up = make_dem(elevation, resolution=resolution)
    south_up = xr.DataArray(
        elevation[::-1],
        dims=("y", "x"),
        coords={
            "y": north_up["y"].to_numpy()[::-1],
            "x": north_up["x"].to_numpy(),
        },
    ).rio.write_crs(constants.DEFAULT_CRS)

    assert interior(profile_curvature(south_up, resolution))[::-1] == pytest.approx(
        interior(profile_curvature(north_up, resolution))
    )


def test_the_curvature_border_and_holes_are_nan() -> None:
    """No complete window, no curvature; a hole must not read as a bend."""
    elevation = ramp(9, rise_per_cell=3.0)
    elevation[4, 4] = np.nan
    curvature = profile_curvature(make_dem(elevation), 10.0).to_numpy()

    assert np.isnan(curvature[0, :]).all()
    assert np.isnan(curvature[:, -1]).all()
    assert np.isnan(curvature[3:6, 3:6]).all()
    assert np.isfinite(curvature[1, 1])


def test_the_curvature_keeps_the_grid_and_the_projection() -> None:
    """Written beside the slope and sampled, so it stays georeferenced."""
    dem = make_dem(parabolic_ridge(9, 0.02, 10.0))

    curvature = profile_curvature(dem, 10.0)

    assert curvature.name == PROFILE_CURVATURE_NAME
    assert curvature.rio.crs == dem.rio.crs
    assert curvature.shape == dem.shape


# --- vegetation height --------------------------------------------------------


@ignore_affine_matmul
def test_a_surface_one_metre_above_the_ground_is_one_metre_of_vegetation() -> None:
    """DSM minus DEM, on the DEM's grid."""
    dem = make_dem(ramp(9, rise_per_cell=2.0))
    dsm = (dem + 1.0).rio.write_crs(constants.DEFAULT_CRS)

    height = vegetation_height(dsm, dem)

    assert height.name == VEGETATION_HEIGHT_NAME
    assert height.to_numpy() == pytest.approx(1.0)


@ignore_affine_matmul
def test_a_surface_below_the_ground_is_noise_and_reads_zero() -> None:
    """Nothing stands at negative height; a DSM under the DEM is survey error."""
    dem = make_dem(np.full((9, 9), 10.0))
    dsm = (dem - 0.3).rio.write_crs(constants.DEFAULT_CRS)

    height = vegetation_height(dsm, dem).to_numpy()

    assert height == pytest.approx(0.0)


@ignore_affine_matmul
def test_where_no_surface_model_was_flown_the_height_is_nan() -> None:
    """Outside the surveys there is no answer, and zero would read as bare ground."""
    dem = make_dem(np.full((9, 9), 10.0))
    surface = np.full((9, 9), 12.0)
    surface[:, 5:] = np.nan
    dsm = make_dem(surface)

    height = vegetation_height(dsm, dem).to_numpy()

    assert height[:, :4] == pytest.approx(2.0)
    assert np.isnan(height[:, 6:]).all()


# --- circular statistics ------------------------------------------------------


def test_the_circular_mean_of_either_side_of_north_is_north() -> None:
    """350 and 10 average to 0, not to 180."""
    assert mean_azimuth_degrees(np.array([350.0, 10.0])) == pytest.approx(0.0)


def test_the_circular_mean_skips_nan_and_is_nan_with_nothing_finite() -> None:
    """A cell with no direction must not drag the mean, nor stand in for one."""
    assert mean_azimuth_degrees(np.array([90.0, np.nan, 90.0])) == pytest.approx(90.0)
    assert np.isnan(mean_azimuth_degrees(np.array([np.nan, np.nan])))


def test_bearings_that_cancel_have_no_mean_direction() -> None:
    """North and south together point nowhere, and must not pretend to."""
    assert np.isnan(mean_azimuth_degrees(np.array([0.0, 180.0])))


def test_agreeing_bearings_have_no_spread_and_opposed_ones_an_unbounded_one() -> None:
    """The circular standard deviation runs from 0 to infinity, not to 180."""
    assert azimuth_sd_degrees(np.array([45.0, 45.0, 45.0])) == pytest.approx(0.0)
    assert azimuth_sd_degrees(np.array([350.0, 10.0])) == pytest.approx(10.03, abs=0.01)
    assert np.isinf(azimuth_sd_degrees(np.array([0.0, 180.0])))
    assert np.isnan(azimuth_sd_degrees(np.array([np.nan])))


# --- zonal statistics ---------------------------------------------------------


@pytest.fixture
def written_grid(tmp_path):
    """A 7x7 raster of its own row index, on disk, with one NaN cell."""
    elevation = np.tile(np.arange(7, dtype=float), (7, 1)).T
    elevation[0, 0] = np.nan
    dem = make_dem(elevation)
    return dem, write_raster(dem, tmp_path / "grid.tif")


def cell_box(dem, rows, columns):
    """A polygon covering whole cells, by row and column slices."""
    resolution = cell_size(dem)
    x = dem["x"].to_numpy()
    y = dem["y"].to_numpy()
    return box(
        x[columns.start] - resolution / 2,
        y[rows.stop - 1] - resolution / 2,
        x[columns.stop - 1] + resolution / 2,
        y[rows.start] + resolution / 2,
    )


@ignore_affine_matmul
def test_a_zonal_mean_averages_the_cells_whose_centres_fall_inside(
    written_grid,
) -> None:
    """Rows 2 to 4 inclusive average 3; the polygon's index comes back with it."""
    dem, path = written_grid
    polygons = gpd.GeoSeries(
        [cell_box(dem, slice(2, 5), slice(1, 4))],
        index=["patch-7"],
        crs=constants.DEFAULT_CRS,
    )

    mean = zonal_statistic(path, polygons)

    assert mean.index.tolist() == ["patch-7"]
    assert mean["patch-7"] == pytest.approx(3.0)


@ignore_affine_matmul
@pytest.mark.parametrize(
    ("statistic", "expected"),
    [("mean", 3.0), ("max", 4.0), ("min", 2.0), ("median", 3.0)],
)
def test_every_statistic_offered_reduces_the_same_cells(
    written_grid, statistic: str, expected: float
) -> None:
    """One selection of cells, four reductions of it."""
    dem, path = written_grid
    polygons = gpd.GeoSeries(
        [cell_box(dem, slice(2, 5), slice(1, 4))], crs=constants.DEFAULT_CRS
    )

    assert zonal_statistic(path, polygons, statistic=statistic).iloc[
        0
    ] == pytest.approx(expected)


@ignore_affine_matmul
def test_a_sliver_holding_no_cell_centre_is_nan(written_grid) -> None:
    """Touching a cell is not being in it: a sliver reads as nothing at all."""
    dem, path = written_grid
    resolution = cell_size(dem)
    x = dem["x"].to_numpy()[3]
    y = dem["y"].to_numpy()[3]
    # A box in the corner of one cell, well clear of its centre.
    sliver = box(
        x + 0.3 * resolution,
        y + 0.3 * resolution,
        x + 0.45 * resolution,
        y + 0.45 * resolution,
    )
    polygons = gpd.GeoSeries([sliver, None], crs=constants.DEFAULT_CRS)

    result = zonal_statistic(path, polygons)

    assert np.isnan(result).all()


@ignore_affine_matmul
def test_nan_cells_are_skipped_not_averaged(written_grid) -> None:
    """A nodata cell inside the polygon does not blank the whole patch."""
    dem, path = written_grid
    polygons = gpd.GeoSeries(
        [cell_box(dem, slice(0, 2), slice(0, 2))], crs=constants.DEFAULT_CRS
    )

    # Rows 0 and 1 hold 0 and 1; the NaN at [0, 0] is left out of the three.
    assert zonal_statistic(path, polygons).iloc[0] == pytest.approx(2.0 / 3.0)


@ignore_affine_matmul
def test_polygons_in_another_projection_are_brought_to_the_raster(
    written_grid,
) -> None:
    """A WGS84 polygon over the same cells reads the same cells."""
    dem, path = written_grid
    polygons = gpd.GeoSeries(
        [cell_box(dem, slice(2, 5), slice(1, 4))], crs=constants.DEFAULT_CRS
    ).to_crs("EPSG:4326")

    assert zonal_statistic(path, polygons).iloc[0] == pytest.approx(3.0, abs=0.01)


@ignore_affine_matmul
def test_an_unknown_statistic_is_refused(written_grid) -> None:
    """A typo must not quietly fall back to the mean."""
    dem, path = written_grid
    polygons = gpd.GeoSeries([cell_box(dem, slice(2, 5), slice(1, 4))], crs=dem.rio.crs)

    with pytest.raises(ValueError, match="Unknown statistic"):
        zonal_statistic(path, polygons, statistic="mode")  # type: ignore[arg-type]


@ignore_affine_matmul
def test_the_zonal_azimuth_mean_is_circular(tmp_path) -> None:
    """A patch half facing 350 and half facing 10 faces north, not south."""
    bearings = np.full((7, 7), 350.0)
    bearings[:, 4:] = 10.0
    aspect = make_dem(bearings)
    path = write_raster(aspect, tmp_path / "aspect.tif")
    polygons = gpd.GeoSeries(
        [cell_box(aspect, slice(1, 6), slice(1, 6))], crs=constants.DEFAULT_CRS
    )

    circular = zonal_azimuth_mean(path, polygons).iloc[0]
    arithmetic = zonal_statistic(path, polygons).iloc[0]

    assert min(circular, 360.0 - circular) < 10.0
    assert arithmetic > 100.0
