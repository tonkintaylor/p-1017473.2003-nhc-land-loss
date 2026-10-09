"""Tests for reading the Foster et al. (2019) Vs30 model.

Each GeoTIFF is written to ``tmp_path``, and ``foster_2019_path`` -- the one
place that would reach R: -- is replaced. Nothing touches the network drive.
"""

import numpy as np
import pytest
import rioxarray  # noqa: F401 -- registers the .rio accessor
import xarray as xr

from landloss.io import vs30

# rioxarray builds a raster's transform with affine's deprecated `*` operator
# when writing it; the warning is theirs, not this reader's.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

NODATA = -3.4e38


def write_layer(path, values):
    """Write a 100 m NZTM layer with Foster's nodata value, and return its path."""
    values = np.asarray(values, dtype="float32")
    rows, cols = values.shape
    raster = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": 5_000_050.0 + 100.0 * np.arange(rows)[::-1],
            "x": 1_700_050.0 + 100.0 * np.arange(cols),
        },
    ).rio.write_crs("EPSG:2193")
    raster.rio.write_nodata(NODATA).rio.to_raster(path)
    return path


@pytest.fixture
def delivered(tmp_path, monkeypatch):
    """Stand written layers in for the two on R:, keyed by file name."""
    paths = {
        vs30.FOSTER_2019_VS30_FNAME: write_layer(
            tmp_path / "vs30.tif", [[200.0, 400.0, 800.0], [NODATA, 300.0, 500.0]]
        ),
        vs30.FOSTER_2019_SIGMA_FNAME: write_layer(
            tmp_path / "sigma.tif", [[0.2, 0.3, 0.4], [NODATA, 0.5, 0.6]]
        ),
    }
    monkeypatch.setattr(vs30, "foster_2019_path", lambda fname, **_: paths[fname])
    return paths


def test_vs30_reads_in_m_s_with_nodata_as_nan(delivered) -> None:
    """Foster's -3.4e38 nodata reads as NaN, not as a velocity."""
    result = vs30.get_foster_2019_vs30()

    assert result.rio.crs.to_epsg() == 2193
    assert result.shape == (2, 3)
    assert float(result[0, 2]) == pytest.approx(800.0)
    assert np.isnan(float(result[1, 0]))


def test_bbox_cuts_the_window(delivered) -> None:
    """Only the cells inside the bbox come back."""
    result = vs30.get_foster_2019_vs30(
        (1_700_100.0, 5_000_000.0, 1_700_300.0, 5_000_100.0)
    )

    assert result.shape == (1, 2)
    np.testing.assert_allclose(result.values, [[300.0, 500.0]])


def test_sigma_reads_from_its_own_file(delivered) -> None:
    """The sigma reader reads the sigma layer, on the same grid."""
    result = vs30.get_foster_2019_vs30_sigma()

    assert float(result[0, 0]) == pytest.approx(0.2)
    assert result.shape == (2, 3)
