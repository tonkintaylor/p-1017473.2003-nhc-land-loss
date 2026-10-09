from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from landloss.domain import constants
from scripts.landloss.hazard.landslide.steps.s2_hancox_1997 import (
    gen_hancox_1997_coverage as step,
)


def grid(values, *, name):
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    result = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": 5_425_000.0 - 10.0 * (np.arange(rows) + 0.5),
            "x": 1_748_000.0 + 10.0 * (np.arange(columns) + 0.5),
        },
        name=name,
    )
    return result.rio.write_crs(constants.DEFAULT_CRS).rio.write_nodata(np.nan)


def test_forward_scenario_constants_are_defined_once():
    assert constants.BETA_SCENARIO_MW == 8.1
    assert constants.BETA_SITE_DISTANCE_KM == 25.0


def test_coverage_path_names_the_model_realisation_and_extent():
    assert (
        step.coverage_path(3, extent="wlg-pilot").name
        == "hancox-1997-coverage-r003-pilot.tif"
    )
    assert step.coverage_path(0, extent="full").name == "hancox-1997-coverage-r000.tif"


def test_build_coverage_uses_pgv_for_the_mm_threshold():
    slope = grid([[30.0, 30.0], [30.0, 30.0]], name="slope_degrees")
    # 0.01 m/s = 1 cm/s = MM 3.78; 0.3 m/s = 30 cm/s = MM 7.56.
    pgv = grid([[0.01, 0.3], [0.01, 0.3]], name="pgv_m_s")

    coverage, result = step.build_coverage(
        slope,
        pgv,
        on_flatland=np.array([[False, False], [False, True]]),
        mw=8.1,
        site_distance_km=25.0,
        event_total_area_km2=10.0,
    )

    assert coverage.name == "hancox_1997_coverage"
    assert coverage.values[0, 0] == 0.0
    assert coverage.values[0, 1] > 0.0
    assert np.isnan(coverage.values[1, 1])
    assert float((coverage * 0.0001).sum()) == pytest.approx(
        result.study_target_area_km2
    )


def test_marc_total_uses_the_explicit_forward_settings():
    total = step.marc_event_total_area_km2(
        mw=8.1,
        r0_km=22.5,
        fault_type="R",
        onshore_fraction=1.0,
        modal_slope_deg=22.0,
        a_topo=1.0,
    )

    assert total == pytest.approx(18.0, rel=0.1)


def test_main_writes_one_coverage_grid_per_realisation(monkeypatch):
    slope = grid(
        [[10.0, 20.0, 30.0, 40.0, 50.0], [10.0, 20.0, 30.0, 40.0, 50.0]],
        name="slope_degrees",
    )
    pgv = grid(
        [[0.3, 0.3, 0.3, 0.3, 0.3], [0.3, 0.3, 0.3, 0.3, 0.3]],
        name="pgv_m_s",
    )
    written = []

    monkeypatch.setattr(
        step.gen_multiscale_slope,
        "slope_path",
        lambda resolution_m, *, extent: Path("slope.tif"),
    )
    monkeypatch.setattr(
        step,
        "pgv_path",
        lambda realisation_id, *, extent: Path(f"pgv-{realisation_id}.tif"),
    )
    monkeypatch.setattr(
        step,
        "read_grid",
        lambda path: slope if path.name == "slope.tif" else pgv,
    )
    monkeypatch.setattr(
        step,
        "read_flatland_mask",
        lambda *, extent, template: np.zeros(template.shape, dtype=bool),
        raising=False,
    )
    monkeypatch.setattr(
        step,
        "write_raster",
        lambda raster, path: written.append((raster, path)),
    )

    step.main(
        extent="wlg-pilot",
        realisation_ids=[0, 2],
        scenario_mw=8.1,
        site_distance_km=25.0,
        marc_r0_km=22.5,
        marc_fault_type="R",
        marc_onshore_fraction=1.0,
        marc_modal_slope_deg=22.0,
        marc_a_topo=1.0,
    )

    assert [path.name for _, path in written] == [
        "hancox-1997-coverage-r000-pilot.tif",
        "hancox-1997-coverage-r002-pilot.tif",
    ]
    assert all(raster.name == "hancox_1997_coverage" for raster, _ in written)
