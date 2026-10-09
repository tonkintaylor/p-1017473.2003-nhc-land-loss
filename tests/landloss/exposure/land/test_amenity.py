"""Tests for the sea view attribute.

Every DEM here is a small synthetic grid built in memory: a straight north-south
coast with the sea to the west, at 10 m cells, so the expected answers can be
worked out by hand.
"""

import math

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from shapely.geometry import Point, box

from landloss.exposure.land.amenity import (
    WinterSun,
    measure_sea,
    sea_mask,
    sea_view_share,
    solar_position,
)

CRS = "EPSG:2193"
CELL_M = 10.0
SIZE_M = 2000.0
COAST_X = 1000.0


def make_dem(land_elevation=10.0, features=()):
    """Build a DEM: sea at 0 m west of the coast, land east of it.

    ``features`` are (minx, maxx, elevation) strips running the full height of
    the grid, laid over the land.
    """
    centres = np.arange(CELL_M / 2, SIZE_M, CELL_M)
    x = centres
    y = centres[::-1]  # north-up: rows run north to south
    xx = np.broadcast_to(x, (len(y), len(x)))
    values = np.where(xx < COAST_X, 0.0, land_elevation)
    for minx, maxx, elevation in features:
        values = np.where((xx >= minx) & (xx < maxx), elevation, values)
    dem = xr.DataArray(values.astype(float), coords={"y": y, "x": x}, dims=("y", "x"))
    return dem.rio.write_crs(CRS)


LAND = gpd.GeoDataFrame(geometry=[box(COAST_X, 0, SIZE_M, SIZE_M)], crs=CRS)


def share_at(dem, x, y, **overrides):
    """Return the sea view share of one point on the DEM."""
    settings = {
        "eye_height_m": 5.0,
        "max_distance_m": 800.0,
        "n_directions": 72,
        "step_m": CELL_M,
    } | overrides
    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)
    points = gpd.GeoSeries([Point(x, y)], crs=CRS)
    return sea_view_share(dem, sea, points, **settings).iloc[0]


# --- the sea mask -------------------------------------------------------------


def test_low_cells_outside_the_land_are_sea() -> None:
    sea = sea_mask(make_dem(), LAND, max_sea_elevation_m=1.0)

    assert sea[:, : int(COAST_X / CELL_M)].all()
    assert not sea[:, int(COAST_X / CELL_M) :].any()


def test_low_land_inside_the_land_polygons_is_not_sea() -> None:
    """The Petone flats stand a few metres above the harbour but are land."""
    sea = sea_mask(make_dem(land_elevation=0.5), LAND, max_sea_elevation_m=1.0)

    assert not sea[:, int(COAST_X / CELL_M) :].any()


def test_a_cell_the_dem_has_no_value_for_outside_the_land_is_sea() -> None:
    """Open sea can come back as nodata rather than as elevations near zero."""
    dem = make_dem()
    dem[:, :10] = np.nan

    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)

    assert sea[:, :10].all()


def test_high_ground_outside_the_land_is_not_sea() -> None:
    """The DEM reaches beyond the study area onto land in Kapiti and Wairarapa."""
    dem = make_dem(features=[(200.0, 400.0, 50.0)])

    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)

    assert not sea[:, 20:40].any()


# --- the view -----------------------------------------------------------------


def test_a_house_on_a_straight_coast_sees_the_sea_across_half_the_compass() -> None:
    """Bearings pointing west reach the sea; along the coast they do not.

    Of the 72 bearings, 35 point strictly west of north-south. The two nearest
    north and south cross a few hundred metres of 10 m land before the water,
    and from a 5 m eye that land hides the waterline, so 33 see the sea.
    """
    share = share_at(make_dem(), COAST_X + 25.0, SIZE_M / 2)

    assert share == pytest.approx(33 / 72)


def test_a_ridge_between_the_house_and_the_sea_blocks_the_view() -> None:
    dem = make_dem(features=[(1100.0, 1150.0, 80.0)])

    assert share_at(dem, 1300.0, SIZE_M / 2) == 0.0


def test_a_house_high_enough_sees_over_the_ridge() -> None:
    dem = make_dem(features=[(1100.0, 1150.0, 30.0), (1280.0, 1320.0, 120.0)])

    assert share_at(dem, 1300.0, SIZE_M / 2) > 0.3


def test_the_sea_beyond_the_casting_distance_is_not_seen() -> None:
    """A distant glimpse is not a sea view; the casting distance says how far."""
    assert share_at(make_dem(), 1900.0, SIZE_M / 2, max_distance_m=500.0) == 0.0


def test_the_drop_of_the_earth_is_allowed_for() -> None:
    """At 5 km the sea surface sits 1.7 m below the horizontal of a 5 m eye."""
    drop = (5000.0**2 / (2 * 6_371_000.0)) * (1 - 0.13)

    assert drop == pytest.approx(1.71, abs=0.01)


def test_a_point_off_the_dem_has_no_share() -> None:
    points = gpd.GeoSeries([Point(-500.0, -500.0), None], crs=CRS)
    dem = make_dem()
    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)

    shares = sea_view_share(
        dem,
        sea,
        points,
        eye_height_m=5.0,
        max_distance_m=500.0,
        n_directions=8,
        step_m=CELL_M,
    )

    assert shares.isna().all()


def test_the_answer_does_not_depend_on_the_chunk_size() -> None:
    dem = make_dem(features=[(1100.0, 1150.0, 30.0)])
    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)
    points = gpd.GeoSeries(
        [Point(1000.0 + 37.0 * k, 200.0 + 113.0 * k) for k in range(15)], crs=CRS
    )
    settings = {
        "eye_height_m": 5.0,
        "max_distance_m": 600.0,
        "n_directions": 36,
        "step_m": CELL_M,
    }

    whole = sea_view_share(dem, sea, points, chunk=100, **settings)
    split = sea_view_share(dem, sea, points, chunk=4, **settings)

    assert whole.tolist() == pytest.approx(split.tolist())
    assert not math.isnan(whole.iloc[0])


def test_a_crs_mismatch_is_rejected() -> None:
    dem = make_dem()
    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)

    with pytest.raises(ValueError, match="EPSG"):
        sea_view_share(
            dem,
            sea,
            gpd.GeoSeries([Point(174.7, -41.3)], crs="EPSG:4326"),
            eye_height_m=5.0,
            max_distance_m=500.0,
            n_directions=8,
            step_m=CELL_M,
        )


# --- the distance to the coast ------------------------------------------------


def coast_distance_at(dem, x, y, max_distance_m=800.0):
    sea = sea_mask(dem, LAND, max_sea_elevation_m=1.0)
    points = gpd.GeoSeries([Point(x, y)], crs=CRS)
    return measure_sea(
        dem,
        sea,
        points,
        eye_height_m=5.0,
        max_distance_m=max_distance_m,
        n_directions=72,
        step_m=CELL_M,
    )["coast_distance_m"].iloc[0]


def test_the_coast_distance_is_the_straight_line_to_the_sea() -> None:
    """225 m inland from a straight coast, to within one 10 m step."""
    distance = coast_distance_at(make_dem(), COAST_X + 225.0, SIZE_M / 2)

    assert distance == pytest.approx(225.0, abs=CELL_M)


def test_the_coast_distance_ignores_what_stands_in_the_way() -> None:
    """A ridge hides the water, but the beach is still that far away."""
    dem = make_dem(features=[(1100.0, 1150.0, 80.0)])

    distance = coast_distance_at(dem, 1300.0, SIZE_M / 2)

    assert distance == pytest.approx(300.0, abs=CELL_M)


def test_beyond_the_casting_distance_there_is_no_coast_distance() -> None:
    assert math.isnan(coast_distance_at(make_dem(), 1900.0, SIZE_M / 2, 500.0))


# --- the winter sun -----------------------------------------------------------

# Wellington's latitude, near enough: the synthetic grid is placed at NZTM
# 1,750,000 E / 5,425,000 N, a few hundred metres from the Basin Reserve.
GRID_ORIGIN = (1_750_000.0, 5_425_000.0)
WINTER = WinterSun(eye_height_m=1.5, days_of_year=(172,), minutes_step=20.0)


def make_wellington_dem(walls=()):
    """A flat 10 m land surface near Wellington, with east-west walls laid over it.

    ``walls`` are (min_y, max_y, height) bands, in metres from the grid's south
    edge, running the full width.
    """
    centres = np.arange(CELL_M / 2, SIZE_M, CELL_M)
    x = GRID_ORIGIN[0] + centres
    y = GRID_ORIGIN[1] + centres[::-1]
    yy = np.broadcast_to(centres[::-1][:, None], (len(y), len(x)))
    values = np.full((len(y), len(x)), 10.0)
    for min_y, max_y, height in walls:
        values = np.where((yy >= min_y) & (yy < max_y), height, values)
    dem = xr.DataArray(values, coords={"y": y, "x": x}, dims=("y", "x"))
    return dem.rio.write_crs(CRS)


def sun_at(dem, north_of_south_edge_m=1000.0):
    point = gpd.GeoSeries(
        [Point(GRID_ORIGIN[0] + 1000.0, GRID_ORIGIN[1] + north_of_south_edge_m)],
        crs=CRS,
    )
    no_sea = np.zeros(dem.shape, dtype=bool)
    return measure_sea(
        dem,
        no_sea,
        point,
        eye_height_m=5.0,
        max_distance_m=900.0,
        n_directions=72,
        step_m=CELL_M,
        winter_sun=WINTER,
    )["winter_sun_share"].iloc[0]


def test_the_winter_solstice_sun_stands_25_degrees_over_wellington_at_noon() -> None:
    """90 - (41.3 + 23.44) = 25.3 degrees, due north."""
    elevation, azimuth = solar_position(np.array([-41.3]), 172, np.array([12.0]))

    assert math.degrees(elevation[0, 0]) == pytest.approx(25.3, abs=0.2)
    assert math.degrees(azimuth[0, 0]) == pytest.approx(0.0, abs=0.5)


def test_the_morning_sun_is_east_of_north_and_the_afternoon_west() -> None:
    _, azimuth = solar_position(np.array([-41.3]), 172, np.array([9.0, 15.0]))

    assert 0 < math.degrees(azimuth[0, 0]) < 90
    assert 270 < math.degrees(azimuth[0, 1]) < 360


def test_open_ground_gets_all_the_winter_sun() -> None:
    assert sun_at(make_wellington_dem()) == pytest.approx(1.0)


def test_a_ridge_to_the_north_takes_the_winter_sun() -> None:
    """The southern hemisphere's winter sun is low in the north."""
    ridge = make_wellington_dem(walls=[(1100.0, 1200.0, 150.0)])

    assert sun_at(ridge) < 0.2


def test_a_ridge_to_the_south_leaves_the_winter_sun() -> None:
    """In June the sun never stands in the south at Wellington."""
    ridge = make_wellington_dem(walls=[(800.0, 900.0, 150.0)])

    assert sun_at(ridge) == pytest.approx(1.0)


def test_the_winter_sun_is_left_out_unless_asked_for() -> None:
    dem = make_wellington_dem()
    point = gpd.GeoSeries(
        [Point(GRID_ORIGIN[0] + 1000, GRID_ORIGIN[1] + 1000)], crs=CRS
    )

    measured = measure_sea(
        dem,
        np.zeros(dem.shape, dtype=bool),
        point,
        eye_height_m=5.0,
        max_distance_m=500.0,
        n_directions=8,
        step_m=CELL_M,
    )

    assert "winter_sun_share" not in measured.columns
