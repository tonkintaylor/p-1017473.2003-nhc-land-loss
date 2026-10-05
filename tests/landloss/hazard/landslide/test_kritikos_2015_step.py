from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import xarray as xr
from shapely.geometry import LineString

from landloss.domain import constants
from landloss.hazard.landslide.models.kritikos_2015 import evaluation
from scripts.landloss.hazard.landslide.steps.s11_kritikos_2015 import (
    config,
)
from scripts.landloss.hazard.landslide.steps.s11_kritikos_2015 import (
    gen_kritikos_2015_hazard as step,
)

pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)


def grid(values, *, cell, name):
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    result = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": 5_425_000.0 - cell * (np.arange(rows) + 0.5),
            "x": 1_748_000.0 + cell * (np.arange(columns) + 0.5),
        },
        name=name,
    )
    return result.rio.write_crs(constants.DEFAULT_CRS).rio.write_nodata(np.nan)


def ramp_dem(size=240):
    # A 30 degree ramp rising to the east on a 10 m grid, with a ridge and a
    # valley so that the slope position has classes to find.
    x = np.arange(size) * 10.0
    profile = x * np.tan(np.radians(30)) + 40.0 * np.sin(x / 100.0)
    return grid(np.tile(profile, (size, 1)), cell=10.0, name="dem")


def test_hazard_path_names_the_model_realisation_and_extent():
    assert (
        step.hazard_path(3, extent="wlg-pilot").name
        == "kritikos-2015-hazard-r003-pilot.tif"
    )
    assert step.hazard_path(0, extent="full").name == "kritikos-2015-hazard-r000.tif"


def test_far_field_fault_term_never_reads_the_fault_database():
    def fail(_bbox):
        msg = "the faults were read"
        raise AssertionError(msg)

    slope, _, fault_km = step.build_inputs(
        ramp_dem(),
        tpi_window_m=600.0,
        tpi_sd_m=None,
        fault_term="far_field",
        get_faults=fail,
    )
    valid = np.isfinite(slope.to_numpy())
    assert np.isinf(fault_km.to_numpy()[valid]).all()


def test_mapped_fault_term_reads_faults_around_the_grid():
    seen = []
    dem = ramp_dem()
    left, bottom, right, top = dem.rio.bounds()
    trace = LineString([(left - 1000.0, bottom - 1000.0), (right, bottom - 1000.0)])

    def get_faults(bbox):
        seen.append(bbox)
        return gpd.GeoDataFrame(geometry=[trace], crs=constants.DEFAULT_CRS)

    _, _, fault_km = step.build_inputs(
        dem,
        tpi_window_m=600.0,
        tpi_sd_m=None,
        fault_term="mapped",
        get_faults=get_faults,
    )

    assert seen[0][0] == pytest.approx(left - 55_000.0)
    assert seen[0][3] == pytest.approx(top + 55_000.0)
    assert np.nanmin(fault_km.to_numpy()) > 0.9
    assert np.nanmax(fault_km.to_numpy()) < 3.6


def test_unknown_fault_term_is_rejected():
    with pytest.raises(ValueError, match="fault_term"):
        step.build_inputs(
            ramp_dem(),
            tpi_window_m=600.0,
            tpi_sd_m=None,
            fault_term="nearest",
            get_faults=lambda _bbox: None,
        )


def test_build_hazard_rises_with_pgv_and_is_nan_where_pgv_is():
    slope, position, fault_km = step.build_inputs(
        ramp_dem(),
        tpi_window_m=600.0,
        tpi_sd_m=None,
        fault_term="far_field",
        get_faults=lambda _bbox: None,
    )
    # 100 m PGV on the same extent as the 60 m grid.
    weak = grid(np.full((24, 24), 0.02), cell=100.0, name="pgv_m_s")
    strong = grid(np.full((24, 24), 1.0), cell=100.0, name="pgv_m_s")

    hazard_weak, mm_weak, _ = step.build_hazard(
        slope, position, fault_km, weak, gamma=0.9
    )
    hazard_strong, mm_strong, gentle = step.build_hazard(
        slope, position, fault_km, strong, gamma=0.9
    )

    assert hazard_strong.name == "kritikos_2015_hazard"
    assert np.nanmax(mm_strong) > np.nanmax(mm_weak)
    assert np.nanmedian(hazard_strong.to_numpy()) > np.nanmedian(hazard_weak.to_numpy())
    assert np.nanmax(hazard_strong.to_numpy()) <= 1.0
    assert gentle.shape == hazard_strong.shape


def test_main_writes_a_hazard_and_a_coverage_grid_per_realisation(monkeypatch):
    dem = ramp_dem()
    pgv = grid(np.full((24, 24), 0.5), cell=100.0, name="pgv_m_s")
    written = []
    curve = evaluation.TransferFunction(
        hazard=np.array([0.0, 1.0]),
        coverage=np.array([0.0, 0.04]),
        settings={"gamma": 0.9, "tpi_window_m": 600.0, "fault_term": "far_field"},
    )

    monkeypatch.setattr(step.evaluation, "get_transfer_function", lambda: curve)
    monkeypatch.setattr(
        step.gen_multiscale_slope,
        "dem_path",
        lambda resolution_m, *, extent: Path("dem.tif"),
    )
    monkeypatch.setattr(
        step,
        "pgv_path",
        lambda realisation_id, *, extent: Path(f"pgv-{realisation_id}.tif"),
    )
    monkeypatch.setattr(
        step, "read_grid", lambda path: dem if path.name == "dem.tif" else pgv
    )
    monkeypatch.setattr(
        step, "write_raster", lambda raster, path: written.append((raster, path))
    )

    step.main(
        extent="wlg-pilot",
        realisation_ids=[0, 2],
        gamma=0.9,
        tpi_window_m=600.0,
        tpi_sd_m=None,
        fault_term="far_field",
    )

    assert [path.name for _, path in written] == [
        "kritikos-2015-hazard-r000-pilot.tif",
        "kritikos-2015-coverage-r000-pilot.tif",
        "kritikos-2015-hazard-r002-pilot.tif",
        "kritikos-2015-coverage-r002-pilot.tif",
    ]
    hazard, coverage = written[0][0], written[1][0]
    assert hazard.name == "kritikos_2015_hazard"
    assert coverage.name == "kritikos_2015_coverage"
    both = np.isfinite(hazard.to_numpy())
    assert np.array_equal(both, np.isfinite(coverage.to_numpy()))
    assert np.allclose(
        coverage.to_numpy()[both], 0.04 * hazard.to_numpy()[both], atol=1e-6
    )


def test_coverage_path_names_the_model_realisation_and_extent():
    assert (
        step.coverage_path(3, extent="wlg-pilot").name
        == "kritikos-2015-coverage-r003-pilot.tif"
    )


def test_a_curve_fitted_with_other_settings_is_refused():
    curve = evaluation.TransferFunction(
        hazard=np.array([0.0, 1.0]),
        coverage=np.array([0.0, 0.04]),
        settings={"gamma": 0.9, "tpi_window_m": 600.0, "fault_term": "mapped"},
    )
    step.check_transfer_function(
        curve, gamma=0.9, tpi_window_m=600.0, fault_term="mapped"
    )
    with pytest.raises(ValueError, match="gen_kritikos_2015_transfer_function"):
        step.check_transfer_function(
            curve, gamma=0.8, tpi_window_m=600.0, fault_term="mapped"
        )


def test_the_committed_curve_matches_the_committed_settings():
    step.check_transfer_function(
        evaluation.get_transfer_function(),
        gamma=config.GAMMA,
        tpi_window_m=config.TPI_WINDOW_M,
        fault_term=config.FAULT_TERM,
    )
