"""Tests for the slope unit delineation on a synthetic valley.

The valley is a V: a floor descending east, flanks rising at a fixed grade
north and south of it. Every cell on the north flank drains south to the floor
and then east out of the grid, so the channel is one link and the catchment is
the whole grid, which is what makes the half-basin split, the merge and the
split checkable on paper. Nothing is downloaded.
"""

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from rasterio import features
from shapely.geometry import box

from landloss.common.utils.hydrology import OUTLET
from landloss.common.utils.terrain import (
    cell_size,
    downhill_azimuth_degrees,
    slope_degrees,
    write_raster,
)
from landloss.domain import constants
from landloss.hazard.landslide import slope_units
from scripts.landloss.hazard.landslide.steps.s1_slope_units import (
    gen_slope_units as step,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side, and the
# suite turns every warning into a failure.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0
RESOLUTION = 10.0
ROWS, COLUMNS = 41, 60
CENTRE_ROW = 20
HA = 10_000.0

CONTRACT_COLUMNS = [
    "basin_id",
    "side",
    "area_m2",
    "mean_slope_degrees",
    "mean_aspect_degrees",
    "aspect_sd_degrees",
    "min_elevation_m",
    "max_elevation_m",
    "relief_m",
    "channel_threshold_ha",
    "geometry",
]


def make_dem(elevation, resolution: float = RESOLUTION):
    """Wrap an elevation array as a north-up DEM in NZTM."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)
    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def valley_elevation():
    """A V-shaped valley: floor on the centre row falling east, flanks rising."""
    row, col = np.indices((ROWS, COLUMNS))
    return 100.0 - 0.5 * col + 2.0 * np.abs(row - CENTRE_ROW)


def grids(elevation):
    dem = make_dem(elevation)
    resolution = cell_size(dem)
    return (
        dem,
        slope_degrees(dem, resolution),
        downhill_azimuth_degrees(dem, resolution),
    )


def delineate(elevation, **overrides):
    settings = dict(
        channel_threshold_ha=1.0,
        aspect_tolerance_deg=45.0,
        min_area_ha=1.0,
        max_area_ha=50.0,
    )
    settings.update(overrides)
    dem, slope, aspect = grids(elevation)
    return slope_units.delineate_slope_units(dem, slope, aspect, **settings), dem


def angular_difference(a, b):
    difference = abs(a - b) % 360.0
    return min(difference, 360.0 - difference)


def covered(units, dem):
    return (
        features.rasterize(
            zip(units.geometry, range(1, len(units) + 1), strict=True),
            out_shape=dem.shape,
            transform=dem.rio.transform(),
            fill=0,
            dtype="int32",
        )
        > 0
    )


# -- stages ------------------------------------------------------------------


def test_channel_links_break_at_junctions():
    # Two heads at the top corners join at the middle cell and leave at the
    # bottom: three links, the junction cell starting the third.
    channels = np.zeros((3, 3), dtype=bool)
    channels[0, 0] = channels[0, 2] = channels[1, 1] = channels[2, 1] = True
    receiver = np.full(9, OUTLET, dtype=np.int64)
    receiver[0] = 4
    receiver[2] = 4
    receiver[4] = 7
    links = slope_units.channel_links(channels, receiver)
    assert links[0, 0] == 1
    assert links[0, 2] == 2
    assert links[1, 1] == 3
    assert links[2, 1] == 3
    assert (links[~channels] == 0).all()


def test_link_catchments_reach_every_cell():
    channels = np.zeros((3, 3), dtype=bool)
    channels[0, 0] = channels[0, 2] = channels[1, 1] = channels[2, 1] = True
    receiver = np.full(9, OUTLET, dtype=np.int64)
    receiver[0] = 4
    receiver[2] = 4
    receiver[4] = 7
    receiver[1] = 4  # an off-channel cell draining into the junction
    # Downstream first: a receiver always comes before the cell it receives.
    order = np.array([7, 4, 0, 2, 1, 3, 5, 6, 8])
    links = slope_units.channel_links(channels, receiver)
    catchments = slope_units.link_catchments(receiver, order, links)
    assert catchments[0, 0] == 1
    assert catchments[0, 2] == 2
    assert catchments[0, 1] == 3
    # (2, 2) drains straight off the grid and takes the nearest catchment.
    assert catchments[2, 2] == 3
    assert (catchments > 0).all()


def test_channel_cells_are_at_or_above_the_threshold_and_never_nan():
    accumulation = np.array([[100.0, 200.0], [np.nan, 300.0]])
    channels = slope_units.channel_cells(accumulation, threshold_m2=200.0)
    assert channels.tolist() == [[False, True], [False, True]]


def test_no_link_makes_every_valid_cell_one_basin_on_the_left():
    links = np.zeros((2, 3), dtype=np.int64)
    receiver = np.full(6, OUTLET, dtype=np.int64)
    order = np.array([0, 1, 2, 4, 5])  # cell 3 is off the DEM
    catchments = slope_units.link_catchments(receiver, order, links)
    assert catchments.tolist() == [[1, 1, 1], [0, 1, 1]]
    half = slope_units.split_half_basins(
        catchments, links, receiver, np.full((2, 3), 90.0)
    )
    assert half.tolist() == [[1, 1, 1], [0, 1, 1]]


def test_cells_are_grouped_by_label_in_raster_order():
    labels = np.array([[2, 0, 1], [1, 2, -1]])
    groups = slope_units._cells_by_label(labels)  # noqa: SLF001
    assert set(groups) == {1, 2}
    assert groups[1].tolist() == [2, 3]
    assert groups[2].tolist() == [0, 4]


def test_a_resultant_a_rounding_error_west_of_north_is_zero_not_360():
    azimuth = slope_units._resultant_azimuth_degrees  # noqa: SLF001
    assert azimuth(-1e-18, 1.0) == 0.0
    assert azimuth(0.0, 1.0) == 0.0
    assert azimuth(1.0, 0.0) == pytest.approx(90.0)
    assert azimuth(-1.0, 0.0) == pytest.approx(270.0)
    assert 0.0 <= azimuth(-1e-12, 1.0) < 360.0


# -- the valley --------------------------------------------------------------


def test_a_v_valley_gives_two_half_basins_of_opposite_aspect():
    units, dem = delineate(valley_elevation())

    assert list(units.columns) == CONTRACT_COLUMNS
    assert len(units) == 2
    assert set(units["side"]) == {"left", "right"}
    assert units["basin_id"].nunique() == 1
    assert units["basin_id"].dtype == np.int64

    north = units.set_index("side").loc["left"]
    south = units.set_index("side").loc["right"]
    # Looking downstream (east), the left bank is the north flank. Its
    # downhill direction is 0.2 south and 0.05 east per metre, an azimuth of
    # 166 degrees; the south flank faces north-east, 14 degrees.
    assert angular_difference(north["mean_aspect_degrees"], 166.0) < 5.0
    assert angular_difference(south["mean_aspect_degrees"], 14.0) < 5.0
    assert (
        angular_difference(north["mean_aspect_degrees"], south["mean_aspect_degrees"])
        > 140.0
    )
    assert north["geometry"].centroid.y > south["geometry"].centroid.y

    assert units["area_m2"].sum() == pytest.approx(ROWS * COLUMNS * RESOLUTION**2)
    assert (units["channel_threshold_ha"] == 1.0).all()
    assert (units["relief_m"] > 0).all()
    assert (units["mean_slope_degrees"] > 5.0).all()
    assert (units["min_elevation_m"] < units["max_elevation_m"]).all()
    assert covered(units, dem).all()


def test_a_grid_with_no_channel_at_the_threshold_is_one_unit():
    # A 4 ha plane sloping east: at a 5 ha threshold no cell is a channel,
    # and the extent is still one unit rather than none (contract 3.3).
    row, col = np.indices((20, 20))
    elevation = 100.0 - 0.5 * col + 0.0 * row
    units, dem = delineate(elevation, channel_threshold_ha=5.0)

    assert list(units.columns) == CONTRACT_COLUMNS
    assert len(units) == 1
    assert units["basin_id"].iloc[0] == 1
    assert units["side"].iloc[0] == "left"
    assert units["area_m2"].iloc[0] == pytest.approx(400 * RESOLUTION**2)
    assert angular_difference(units["mean_aspect_degrees"].iloc[0], 90.0) < 1.0
    assert (units["channel_threshold_ha"] == 5.0).all()
    assert covered(units, dem).all()


def test_the_written_aspect_stays_inside_a_full_turn():
    # Flanks facing a hair either side of north: every unit's circular mean
    # is in [0, 360), never the 360.0 the modulus hands back west of north.
    row, col = np.indices((ROWS, COLUMNS))
    elevation = 100.0 - 0.5 * col + 2.0 * np.abs(row - CENTRE_ROW)
    units, _ = delineate(elevation)
    assert (units["mean_aspect_degrees"] >= 0.0).all()
    assert (units["mean_aspect_degrees"] < 360.0).all()
    assert (units["aspect_sd_degrees"] >= 0.0).all()


def test_a_unit_over_the_maximum_is_split_and_no_cell_is_dropped():
    elevation = valley_elevation()
    # A patch of sea in a corner: the slopes beside it drain straight into it
    # without reaching the channel, and must still end in a unit.
    elevation[:5, :5] = np.nan
    units, dem = delineate(elevation, max_area_ha=5.0)

    assert len(units) > 2
    assert (units["area_m2"] <= 5.0 * HA).all()
    assert (units["area_m2"] >= 1.0 * HA).all()
    assert units.geometry.is_valid.all()
    assert (units.geometry.geom_type == "Polygon").all()

    valid = np.isfinite(dem.to_numpy())
    assert np.array_equal(covered(units, dem), valid)
    assert units["area_m2"].sum() == pytest.approx(valid.sum() * RESOLUTION**2)
    # Units do not overlap: the union's area is the sum of the areas.
    assert units.geometry.union_all().area == pytest.approx(units["area_m2"].sum())


def test_merge_joins_similar_neighbours_and_absorbs_small_ones():
    side = 100.0  # 1 ha squares
    squares = {
        "a": (box(0, 0, side, side), 10.0),
        "b": (box(side, 0, 2 * side, side), 40.0),
        "c": (box(2 * side, 0, 3 * side, side), 200.0),
        # A quarter-hectare sliver beside c, facing much as c does.
        "d": (box(2 * side, side, 2.5 * side, 1.5 * side), 190.0),
    }
    units = gpd.GeoDataFrame(
        {
            "basin_id": np.array([1, 1, 2, 2], dtype=np.int64),
            "side": ["left", "right", "left", "right"],
            "mean_aspect_degrees": [v[1] for v in squares.values()],
        },
        geometry=[v[0] for v in squares.values()],
        crs=constants.DEFAULT_CRS,
    )

    merged = slope_units.merge_similar_aspect(
        units, tolerance_deg=45.0, min_area_m2=0.5 * HA, max_area_m2=5 * HA
    )
    # a and b merge (30 degrees apart); d is absorbed into c, not b.
    assert len(merged) == 2
    assert sorted(merged["area_m2"]) == pytest.approx([1.25 * HA, 2 * HA])
    assert merged["area_m2"].sum() == pytest.approx(units.geometry.area.sum())
    big = merged.set_index("area_m2").loc[2 * HA]
    assert 10.0 < big["mean_aspect_degrees"] < 40.0

    # The same merge is refused when it would pass the maximum area.
    capped = slope_units.merge_similar_aspect(
        units, tolerance_deg=45.0, min_area_m2=0.5 * HA, max_area_m2=1.5 * HA
    )
    assert len(capped) == 3

    # And at a tight tolerance only the absorption happens.
    tight = slope_units.merge_similar_aspect(
        units, tolerance_deg=10.0, min_area_m2=0.5 * HA, max_area_m2=5 * HA
    )
    assert len(tight) == 3


def test_the_merge_on_the_valley_joins_the_flanks_at_a_wide_tolerance():
    units, _ = delineate(valley_elevation(), aspect_tolerance_deg=179.0)
    assert len(units) == 1
    assert units["area_m2"].iloc[0] == pytest.approx(ROWS * COLUMNS * RESOLUTION**2)


def test_the_threshold_changes_the_unit_count_on_a_branching_valley():
    # Two tributary gullies cut into the north flank: at a low threshold they
    # become channels of their own with half-basins each side; at a high one
    # the flank is one bank.
    elevation = valley_elevation()
    row, col = np.indices((ROWS, COLUMNS))
    for gully_col in (15, 40):
        elevation -= (
            1.5 * np.clip(3 - np.abs(col - gully_col), 0, None) * (row < CENTRE_ROW)
        )
    # The gully half-basins are well under a hectare and face about 25 degrees
    # off the main flank, so a small minimum and a tight tolerance keep them,
    # and the count then shows the threshold.
    settings = dict(aspect_tolerance_deg=10.0, min_area_ha=0.1)
    low, _ = delineate(elevation, channel_threshold_ha=0.5, **settings)
    high, _ = delineate(elevation, channel_threshold_ha=20.0, **settings)
    assert len(low) > len(high)
    assert low["area_m2"].sum() == pytest.approx(high["area_m2"].sum())


def test_grids_must_share_a_projected_layout():
    dem, slope, aspect = grids(valley_elevation())
    with pytest.raises(ValueError, match="shape"):
        slope_units.delineate_slope_units(
            dem,
            slope.isel(x=slice(0, 10)),
            aspect,
            channel_threshold_ha=1.0,
            aspect_tolerance_deg=45.0,
            min_area_ha=1.0,
            max_area_ha=50.0,
        )
    geographic = dem.rio.write_crs("EPSG:4326")
    with pytest.raises(ValueError, match="geographic"):
        slope_units.delineate_slope_units(
            geographic,
            slope,
            aspect,
            channel_threshold_ha=1.0,
            aspect_tolerance_deg=45.0,
            min_area_ha=1.0,
            max_area_ha=50.0,
        )


# -- the step ----------------------------------------------------------------


STEP_COLUMNS = [
    "unit_id",
    "basin_id",
    "side",
    "area_m2",
    "mean_slope_degrees",
    "mean_aspect_degrees",
    "aspect_sd_degrees",
    "min_elevation_m",
    "max_elevation_m",
    "relief_m",
    "flatland_share",
    "channel_threshold_ha",
    "geometry",
]


@pytest.fixture
def step_inputs(tmp_path, monkeypatch):
    """Ground steps 1 and 2's rasters and ground map, synthetic, for the step."""
    dem, slope, aspect = grids(valley_elevation())
    paths = {
        "dem": write_raster(dem.rename("dem"), tmp_path / "dem-10m-pilot.tif"),
        "slope": write_raster(slope, tmp_path / "slope-10m-pilot.tif"),
        "aspect": write_raster(aspect, tmp_path / "aspect-10m-pilot.tif"),
        "ground_map": tmp_path / "ground-map-pilot.geoparquet",
    }
    # Flatland over the south-east quarter of the grid, as the NLM would map
    # a valley floor; the rest of the ground map is hill.
    minx, miny, maxx, maxy = dem.rio.bounds()
    midx, midy = (minx + maxx) / 2, (miny + maxy) / 2
    ground_map = gpd.GeoDataFrame(
        {
            "ground_id": ["GM0000001", "GM0000002"],
            "is_flatland": [True, False],
        },
        geometry=[box(midx, miny, maxx, midy), box(minx, midy, maxx, maxy)],
        crs=constants.DEFAULT_CRS,
    )
    ground_map.to_parquet(paths["ground_map"])
    monkeypatch.setattr(step, "input_paths", lambda *, extent: paths)
    monkeypatch.setattr(step, "WORK_DIR", tmp_path)
    return dem


def test_the_path_names_the_extent():
    assert (
        step.slope_units_path(extent="wlg-pilot").name == "slope-units-pilot.geoparquet"
    )
    assert step.slope_units_path(extent="full").name == "slope-units.geoparquet"
    assert step.slope_units_path(extent="wlg-pilot").parent == step.WORK_DIR


def test_the_step_writes_the_contract_columns(step_inputs, capsys):
    step.main(
        extent="wlg-pilot",
        channel_threshold_ha=1.0,
        channel_thresholds_tried_ha=(0.5, 1.0, 20.0),
        aspect_merge_tolerance_deg=45.0,
        min_unit_area_ha=1.0,
        max_unit_area_ha=5.0,
    )
    written = gpd.read_parquet(step.slope_units_path(extent="wlg-pilot"))

    assert list(written.columns) == STEP_COLUMNS
    assert written.crs == constants.DEFAULT_CRS
    assert written["unit_id"].str.fullmatch(r"SU\d{7}").all()
    assert written["unit_id"].is_unique
    assert written["unit_id"].iloc[0] == "SU0000001"
    assert written["basin_id"].dtype == np.int64
    assert set(written["side"]) <= {"left", "right"}
    assert (written["channel_threshold_ha"] == 1.0).all()
    assert written["flatland_share"].between(0.0, 1.0).all()
    # The south-east quarter is flat: some unit lies on it and some do not.
    assert (written["flatland_share"] > 0.5).any()
    assert (written["flatland_share"] == 0.0).any()
    assert (written["area_m2"] <= 5.0 * HA).all()
    assert written["area_m2"].sum() == pytest.approx(ROWS * COLUMNS * RESOLUTION**2)
    # Ids follow location: the first unit is the westernmost, then southernmost.
    points = written.geometry.representative_point()
    assert points.x.iloc[0] == points.x.min()

    out = capsys.readouterr().out
    assert "Sensitivity to the channel threshold" in out
    for threshold in ("0.5", "1.0", "20.0"):
        assert threshold in out
    assert "Wrote" in out
