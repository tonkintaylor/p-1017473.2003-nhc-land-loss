"""Landslide step 3 on synthetic terrain, with no network.

``gen_multiscale_slope.py`` normally fetches the 1 m DEM from LINZ and
``gen_terrain_derivatives.py`` the 1 m surface model. Here both fetches are
replaced by hand-built grids over a small extent, and the work directory is
pointed at ``tmp_path``, so the tests are of what the two scripts write -- the
files, their band names, their grids -- and not of LINZ.
"""

import geopandas as gpd
import numpy as np
import pytest
import rasterio
import rioxarray
import xarray as xr

from landloss.common.utils.terrain import block_mean, write_raster
from landloss.domain import constants
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_multiscale_slope as slope_step,
)
from scripts.landloss.hazard.landslide.steps.s3_multiscale_slope import (
    gen_terrain_derivatives as terrain_step,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# A 300 m square on a round NZTM coordinate, so it snaps to itself.
ORIGIN_EASTING = 1_748_100.0
ORIGIN_NORTHING = 5_425_200.0
SIDE_M = 300.0
RESOLUTIONS_M = (1, 3, 10, 30, 50, 100)


def make_dem(elevation, resolution: float, origin=(ORIGIN_EASTING, ORIGIN_NORTHING)):
    """Wrap an elevation array as a north-up DEM in NZTM with its top left at origin."""
    elevation = np.asarray(elevation, dtype=float)
    rows, columns = elevation.shape
    left, top = origin
    eastings = left + resolution * (np.arange(columns) + 0.5)
    northings = top - resolution * (np.arange(rows) + 0.5)
    dem = xr.DataArray(
        elevation, dims=("y", "x"), coords={"y": northings, "x": eastings}
    )
    return dem.rio.write_crs(constants.DEFAULT_CRS)


def hillside(rows: int, columns: int, resolution: float):
    """A slope rising to the east with a knoll in the middle of it."""
    x = (np.arange(columns) + 0.5) * resolution
    y = (np.arange(rows) + 0.5) * resolution
    xx, yy = np.meshgrid(x, y)
    knoll = 15.0 * np.exp(-(((xx - 150) ** 2 + (yy - 150) ** 2) / (2 * 40.0**2)))
    return 0.3 * xx + knoll


def read(path):
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


def band_name(path):
    with rasterio.open(path) as source:
        return source.descriptions[0]


@pytest.fixture
def work_dir(tmp_path, monkeypatch):
    """Point both scripts' outputs at tmp_path."""
    monkeypatch.setattr(slope_step, "WORK_DIR", tmp_path)
    monkeypatch.setattr(terrain_step, "TERRAIN_DIR", tmp_path / "terrain")
    return tmp_path


@pytest.fixture
def small_extent(monkeypatch):
    """Run over the 300 m square rather than the pilot box."""
    bbox = (
        ORIGIN_EASTING,
        ORIGIN_NORTHING - SIDE_M,
        ORIGIN_EASTING + SIDE_M,
        ORIGIN_NORTHING,
    )
    monkeypatch.setattr(slope_step, "resolve_extent", lambda *, pilot: (bbox, "square"))
    return bbox


@pytest.fixture
def fake_fetch(monkeypatch):
    """Serve a synthetic 1 m DEM over whatever padded extent the step asks for."""

    def fetch_dem(bbox, resolution_m, *, use_cache):
        minx, miny, maxx, maxy = bbox
        rows = int((maxy - miny) / resolution_m)
        columns = int((maxx - minx) / resolution_m)
        return make_dem(
            hillside(rows, columns, resolution_m), resolution_m, (minx, maxy)
        )

    monkeypatch.setattr(slope_step, "fetch_dem", fetch_dem)


# --- path functions ------------------------------------------------------------


def test_the_path_wrappers_name_the_layer_the_size_and_the_extent():
    assert slope_step.dem_path(1, pilot=True).name == "dem-1m-pilot.tif"
    assert slope_step.slope_path(30, pilot=False).name == "slope-30m.tif"
    assert slope_step.aspect_path(3, pilot=True).name == "aspect-3m-pilot.tif"
    assert slope_step.aspect_path(10, pilot=True).parent == slope_step.WORK_DIR


def test_the_terrain_paths_carry_the_contract_file_names():
    assert (
        terrain_step.terrain_path("face-height-5m", pilot=True).name
        == "face-height-5m-pilot.tif"
    )
    assert (
        terrain_step.terrain_path("cut-fill-residual-100m", pilot=False).name
        == "cut-fill-residual-100m.tif"
    )
    assert (
        terrain_step.terrain_path("profile-curvature", pilot=True).name
        == "profile-curvature-3m-pilot.tif"
    )
    assert (
        terrain_step.terrain_path("topographic-position-100m", pilot=True).name
        == "topographic-position-100m-pilot.tif"
    )
    assert (
        terrain_step.terrain_path("vegetation-height", pilot=True).name
        == "vegetation-height-pilot.tif"
    )
    assert (
        terrain_step.terrain_path("vegetation-height", pilot=True).parent
        == terrain_step.TERRAIN_DIR
    )


def test_an_unknown_terrain_layer_is_refused():
    with pytest.raises(KeyError, match="not a terrain layer"):
        terrain_step.terrain_path("slope-1m", pilot=True)


def test_every_contract_layer_has_a_band_name():
    assert set(terrain_step.TERRAIN_LAYERS) == {
        "face-height-5m",
        "face-height-10m",
        "cut-fill-residual-30m",
        "cut-fill-residual-100m",
        "profile-curvature",
        "topographic-position-20m",
        "topographic-position-100m",
        "vegetation-height",
    }


# --- gen_multiscale_slope ------------------------------------------------------


@ignore_affine_matmul
def test_the_slope_step_writes_a_dem_a_slope_and_an_aspect_per_cell_size(
    work_dir, small_extent, fake_fetch
):
    slope_step.main(pilot=True, resolutions_m=RESOLUTIONS_M, use_cached_dem=True)

    for resolution in RESOLUTIONS_M:
        dem = read(slope_step.dem_path(resolution, pilot=True))
        slope = read(slope_step.slope_path(resolution, pilot=True))
        aspect = read(slope_step.aspect_path(resolution, pilot=True))

        cells = int(SIDE_M / resolution)
        assert dem.shape == slope.shape == aspect.shape == (cells, cells)
        assert dem.rio.bounds() == pytest.approx(small_extent)
        assert (
            band_name(slope_step.slope_path(resolution, pilot=True)) == "slope_degrees"
        )
        assert (
            band_name(slope_step.aspect_path(resolution, pilot=True))
            == "downhill_azimuth_degrees"
        )
        # The margin held the kernel's border, so nothing inside the extent is NaN.
        assert np.isfinite(slope.values).all()
        assert np.isfinite(aspect.values).all()


@ignore_affine_matmul
def test_the_aspect_points_downhill_and_the_grids_nest(
    work_dir, small_extent, fake_fetch
):
    slope_step.main(pilot=True, resolutions_m=(1, 10), use_cached_dem=True)

    aspect_1m = read(slope_step.aspect_path(1, pilot=True)).values
    aspect_10m = read(slope_step.aspect_path(10, pilot=True)).values
    dem_1m = read(slope_step.dem_path(1, pilot=True))
    dem_10m = read(slope_step.dem_path(10, pilot=True))

    # Away from the knoll the ground rises east, so it runs downhill west.
    assert aspect_1m[10, 10] == pytest.approx(270.0, abs=1.0)
    assert aspect_10m[1, 1] == pytest.approx(270.0, abs=1.0)
    assert (aspect_1m >= 0).all()
    assert (aspect_1m < 360).all()
    # The 10 m DEM is the block mean of the 1 m one, written from the same corner.
    assert dem_10m.values == pytest.approx(block_mean(dem_1m, 10).values, abs=1e-4)


# --- gen_terrain_derivatives ---------------------------------------------------


@pytest.fixture
def step3_dems(work_dir):
    """The DEMs step 3 writes, built from one synthetic 1 m grid."""
    cells = int(SIDE_M)
    dem_1m = make_dem(hillside(cells, cells, 1.0), 1.0)
    for resolution in RESOLUTIONS_M:
        dem = dem_1m if resolution == 1 else block_mean(dem_1m, resolution)
        write_raster(dem, slope_step.dem_path(resolution, pilot=True))
    return dem_1m


@pytest.fixture
def fake_dsm(work_dir, monkeypatch, step3_dems):
    """A surface model two metres above the ground over the west half, NaN east."""
    surface = step3_dems.values + 2.0
    surface[:, 150:] = np.nan
    path = write_raster(make_dem(surface, 1.0), work_dir / "dsm.tif")
    calls = []

    def get_dsm(bbox, resolution=1, crs=constants.DEFAULT_CRS, *, use_cache=True):
        calls.append((bbox, resolution, use_cache))
        return path

    monkeypatch.setattr(terrain_step, "get_dsm", get_dsm)
    monkeypatch.setattr(
        terrain_step,
        "get_nz_building_outlines",
        lambda bbox, crs: gpd.GeoDataFrame(geometry=[], crs=crs),
    )
    return calls


def run_terrain_step():
    terrain_step.main(
        pilot=True,
        use_cached_dsm=True,
        face_height_windows_m=(5.0, 10.0),
        residual_base_resolutions_m=(30, 100),
        topographic_position_windows_m={20.0: 3, 100.0: 10},
        curvature_resolution_m=3,
    )


@ignore_affine_matmul
def test_the_terrain_step_writes_every_layer_with_its_band_name(fake_dsm):
    run_terrain_step()

    for key, band in terrain_step.TERRAIN_LAYERS.items():
        path = terrain_step.terrain_path(key, pilot=True)
        assert path.exists(), key
        assert band_name(path) == band, key


@ignore_affine_matmul
def test_the_layers_sit_on_the_grids_the_contract_gives_them(fake_dsm):
    run_terrain_step()

    def cell_size_of(key):
        with rasterio.open(terrain_step.terrain_path(key, pilot=True)) as source:
            return source.res[0]

    assert cell_size_of("face-height-5m") == pytest.approx(1.0)
    assert cell_size_of("cut-fill-residual-30m") == pytest.approx(1.0)
    assert cell_size_of("profile-curvature") == pytest.approx(3.0)
    assert cell_size_of("topographic-position-20m") == pytest.approx(3.0)
    assert cell_size_of("topographic-position-100m") == pytest.approx(10.0)
    assert cell_size_of("vegetation-height") == pytest.approx(1.0)


@ignore_affine_matmul
def test_the_vegetation_height_is_nan_where_no_surface_model_covers(fake_dsm):
    run_terrain_step()

    height = read(terrain_step.terrain_path("vegetation-height", pilot=True)).values

    assert height[:, :150] == pytest.approx(2.0, abs=1e-3)
    assert np.isnan(height[:, 150:]).all()


@ignore_affine_matmul
def test_the_surface_model_is_fetched_over_the_1m_dem_extent(fake_dsm, step3_dems):
    run_terrain_step()

    ((bbox, resolution, use_cache),) = fake_dsm
    assert bbox == pytest.approx(step3_dems.rio.bounds())
    assert resolution == 1
    assert use_cache is True


@ignore_affine_matmul
def test_the_face_height_reads_the_knoll_taller_in_the_wider_window(fake_dsm):
    run_terrain_step()

    narrow = read(terrain_step.terrain_path("face-height-5m", pilot=True)).values
    wide = read(terrain_step.terrain_path("face-height-10m", pilot=True)).values

    inside = np.isfinite(narrow) & np.isfinite(wide)
    assert (wide[inside] >= narrow[inside] - 1e-6).all()
    assert (narrow[inside] >= 0).all()
