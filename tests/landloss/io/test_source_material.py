"""Tests for reading rasters supplied to the project as source material.

Every raster here is written to ``tmp_path`` by the test that reads it, and the
resolver that would go to the T: drive is replaced. Nothing touches the network
or the network drive, which is what makes these runnable on a laptop with no
mapped drives -- the condition most of this suite is written under.

What is being tested is the handling, not the reading: rasterio can open a
GeoTIFF without help. It is the nodata marker, the projection and the clip that
go wrong quietly, and each of those is a separate claim below.
"""

import numpy as np
import pytest
import rioxarray  # noqa: F401  # registers the .rio accessor
import xarray as xr

from landloss.domain import constants
from landloss.io import source_material

# rioxarray recomputes the transform through affine's ``*`` operator, which
# affine 3.0.1 has begun warning about. It is a warning about how rioxarray
# calls affine, there is nothing to fix on this side, and the suite turns every
# warning into a failure.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)

# An arbitrary but realistic corner in NZTM, so the test rasters sit where a
# Wellington raster would sit rather than at the origin.
ORIGIN_EASTING = 1_748_000.0
ORIGIN_NORTHING = 5_425_000.0
RESOLUTION = 25.0


def write_raster(path, values, crs=constants.DEFAULT_CRS, nodata=None):
    """Write an array to a GeoTIFF on a 25 m north-up grid, and return its path."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    raster = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": ORIGIN_NORTHING + RESOLUTION * (np.arange(rows)[::-1] + 0.5),
            "x": ORIGIN_EASTING + RESOLUTION * (np.arange(columns) + 0.5),
        },
    ).rio.write_crs(crs)

    if nodata is not None:
        raster = raster.rio.write_nodata(nodata)

    raster.rio.to_raster(path)
    return path


@pytest.fixture
def supplied(monkeypatch):
    """Return a function that stands a written raster in for one on the T: drive."""

    def use(path):
        monkeypatch.setattr(
            source_material, "source_material_path", lambda *_, **__: path
        )
        return path

    return use


def test_a_supplied_raster_comes_back_on_its_own_grid(tmp_path, supplied) -> None:
    """The plain case, so every failure below is about handling, not reading."""
    values = np.arange(12, dtype=float).reshape(3, 4)
    supplied(write_raster(tmp_path / "grid.tif", values))

    raster = source_material.get_source_material_raster("whatever.tif")

    assert tuple(raster.dims) == source_material.RASTER_DIMS
    assert raster.to_numpy() == pytest.approx(values)


def test_the_nodata_marker_arrives_as_nan_rather_than_as_a_number(
    tmp_path, supplied
) -> None:
    """A -9999 left in place is the commonest way a raster quietly poisons a model."""
    values = np.full((3, 4), 0.25)
    values[1, 1] = -9999.0
    supplied(write_raster(tmp_path / "grid.tif", values, nodata=-9999.0))

    raster = source_material.get_source_material_raster("whatever.tif")

    assert np.isnan(raster.to_numpy()[1, 1])
    assert raster.to_numpy()[0, 0] == pytest.approx(0.25)


def test_an_extent_cuts_the_grid_down_to_it(tmp_path, supplied) -> None:
    """The study area is a fraction of a regional grid; reading it whole is waste."""
    supplied(write_raster(tmp_path / "grid.tif", np.zeros((10, 10))))

    whole = source_material.get_source_material_raster("whatever.tif")
    clipped = source_material.get_source_material_raster(
        "whatever.tif",
        bbox=(
            ORIGIN_EASTING + 10.0,
            ORIGIN_NORTHING + 10.0,
            ORIGIN_EASTING + 60.0,
            ORIGIN_NORTHING + 60.0,
        ),
    )

    assert whole.shape == (10, 10)
    assert clipped.size < whole.size
    assert float(clipped["x"].min()) >= ORIGIN_EASTING


def test_a_grid_in_another_projection_is_returned_in_the_one_asked_for(
    tmp_path, supplied
) -> None:
    """A model that silently mixes projections puts every landslide in the sea."""
    supplied(write_raster(tmp_path / "grid.tif", np.zeros((8, 8)), crs="EPSG:2193"))

    raster = source_material.get_source_material_raster("whatever.tif", crs="EPSG:3857")

    assert raster.rio.crs.to_epsg() == 3857


def test_a_grid_with_no_projection_is_refused(tmp_path, supplied) -> None:
    """Nothing can be located against it, and that failure surfaces far from here."""
    path = tmp_path / "grid.tif"
    xr.DataArray(
        np.zeros((4, 4)),
        dims=("y", "x"),
        coords={"y": np.arange(4.0)[::-1], "x": np.arange(4.0)},
    ).rio.to_raster(path)
    supplied(path)

    with pytest.raises(ValueError, match="coordinate reference system"):
        source_material.get_source_material_raster("whatever.tif")


def test_an_extent_that_misses_the_grid_says_so_in_so_many_words(
    tmp_path, supplied
) -> None:
    """Two datasets that were never meant to meet, which rioxarray reports obscurely."""
    supplied(write_raster(tmp_path / "grid.tif", np.zeros((4, 4))))

    with pytest.raises(ValueError, match="does not overlap"):
        source_material.get_source_material_raster(
            "whatever.tif", bbox=(1_500_000.0, 5_000_000.0, 1_500_100.0, 5_000_100.0)
        )


def test_the_landslide_probability_grid_is_read_from_its_configured_path(
    tmp_path, monkeypatch
) -> None:
    """The path is a constant precisely so that nobody retypes it into a script."""
    path = write_raster(tmp_path / "eil.tif", np.full((4, 4), 0.01))
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(source_material, "source_material_path", record)

    raster = source_material.get_eil_landslide_probability()

    assert asked_for == [constants.EIL_PROBABILITY_SOURCE_PATH]
    assert raster.to_numpy() == pytest.approx(0.01)
