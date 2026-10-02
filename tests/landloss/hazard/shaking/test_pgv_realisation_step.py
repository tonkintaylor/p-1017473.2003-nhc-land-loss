"""The PGV realisation step on a synthetic step 3 grid, with no network.

The step reads the PGV raster step 3 wrote and writes one scaled raster per
realisation. Here step 3's output is a small hand-built grid written where the
step looks for it (its work directory pointed at ``tmp_path``), so the test is
of the scaling and the file it lands in, not of the TS1170.5 demand.
"""

import numpy as np
import pytest
import rioxarray
import xarray as xr

from landloss.common.utils.terrain import write_raster
from landloss.domain import constants
from landloss.hazard.realisation import realisation_seed
from landloss.hazard.shaking.pga import beta_scale_factor
from scripts.landloss.hazard.shaking.steps.s3_pgv import gen_pgv
from scripts.landloss.hazard.shaking.steps.s4_pga_realisation import (
    gen_pga_realisations,
)
from scripts.landloss.hazard.shaking.steps.s5_pgv_realisation import (
    gen_pgv_realisations as step,
)

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about; nothing to fix on this side.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, so the raster sits where a
# Wellington raster would sit rather than at the origin.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0
RETURN_PERIOD_YR = 2500


def make_grid(values, resolution: float = 100.0):
    """Wrap an array as a north-up raster in NZTM, as step 3 writes one."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    eastings = ORIGIN_EASTING + resolution * (np.arange(columns) + 0.5)
    northings = ORIGIN_NORTHING + resolution * (np.arange(rows)[::-1] + 0.5)
    grid = xr.DataArray(values, dims=("y", "x"), coords={"y": northings, "x": eastings})
    return grid.rio.write_crs(constants.DEFAULT_CRS)


def read(path):
    with rioxarray.open_rasterio(path, masked=True) as raster:
        return raster.squeeze("band", drop=True).load()


@pytest.fixture
def step3_pgv(tmp_path, monkeypatch):
    """A step 3 PGV grid in a work directory the step reads from and writes to."""
    monkeypatch.setattr(gen_pgv, "WORK_DIR", tmp_path)
    monkeypatch.setattr(step, "WORK_DIR", tmp_path)
    pgv = make_grid([[0.9, 1.2, np.nan], [1.4, 2.1, 1.0]]).rename("pgv_m_s")
    write_raster(
        pgv.astype("float32"),
        gen_pgv.output_path("pgv", return_period_yr=RETURN_PERIOD_YR, pilot=True),
    )
    return pgv


def test_the_path_names_the_realisation_and_the_extent():
    assert step.pgv_path(3, pilot=True).name == "pgv-r003-pilot.tif"
    assert step.pgv_path(12, pilot=False).name == "pgv-r012.tif"
    assert step.pgv_path(0, pilot=True).parent == step.WORK_DIR


@ignore_affine_matmul
def test_a_realisation_is_step_3s_grid_scaled_by_step_4s_factor(step3_pgv):
    step.main(pilot=True, realisation_ids=[0, 4], return_period_yr=RETURN_PERIOD_YR)

    for realisation_id in (0, 4):
        written = read(step.pgv_path(realisation_id, pilot=True))
        expected_factor = beta_scale_factor(
            realisation_seed(constants.BASE_SEED, realisation_id, step.RNG_STREAM)
        )
        ratio = written.values / step3_pgv.values
        finite = np.isfinite(step3_pgv.values)
        # float32 on disk, so the ratio reproduces the factor to that precision.
        assert np.allclose(ratio[finite], expected_factor, rtol=1e-6)
        assert np.isnan(written.values[~finite]).all()
        assert written.shape == step3_pgv.shape
        assert written.rio.crs == step3_pgv.rio.crs
        assert np.array_equal(written.x.values, step3_pgv.x.values)
        assert np.array_equal(written.y.values, step3_pgv.y.values)


@ignore_affine_matmul
def test_two_realisations_take_different_factors(step3_pgv):
    step.main(pilot=True, realisation_ids=[0, 1], return_period_yr=RETURN_PERIOD_YR)
    first = read(step.pgv_path(0, pilot=True)).values
    second = read(step.pgv_path(1, pilot=True)).values
    assert not np.allclose(first[np.isfinite(first)], second[np.isfinite(second)])


def test_the_stream_is_step_4s():
    # The factor is step 4's only if the seed is: same base seed, same
    # realisation id, same stream name, which this step imports from step 4.
    assert step.RNG_STREAM is gen_pga_realisations.RNG_STREAM
