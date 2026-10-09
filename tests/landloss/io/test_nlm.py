"""Tests for reading the National Liquefaction Model's release tree.

Every raster or vector layer here is written to ``tmp_path`` by the test that
reads it, and the resolver that would go to the T: drive is replaced. Nothing
touches the network or the network drive.
"""

import geopandas as gpd
import numpy as np
import pytest
import rioxarray  # noqa: F401  # registers the .rio accessor
import xarray as xr
from shapely.geometry import Point

from landloss.io import nlm

pytestmark = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)


def write_raster(path, values, nodata=None):
    """Write an array to a GeoTIFF, and return its path."""
    values = np.asarray(values, dtype=float)
    rows, columns = values.shape
    raster = xr.DataArray(
        values,
        dims=("y", "x"),
        coords={
            "y": np.arange(rows)[::-1].astype(float),
            "x": np.arange(columns).astype(float),
        },
    ).rio.write_crs("EPSG:2193")

    if nodata is not None:
        raster = raster.rio.write_nodata(nodata)

    raster.rio.to_raster(path)
    return path


@pytest.fixture
def released(monkeypatch):
    """Return a function that stands a written raster in for one on the T: drive."""

    def use(path):
        monkeypatch.setattr(nlm, "nlm_release_path", lambda *_, **__: path)
        return path

    return use


def test_a_scenario_raster_comes_back_on_its_own_grid(tmp_path, released) -> None:
    """The plain case, so every failure below is about the handling, not the read."""
    values = np.arange(12, dtype=float).reshape(3, 4)
    released(write_raster(tmp_path / "grid.tif", values))

    raster = nlm.get_nlm_scenario_raster("whatever.tif")

    assert tuple(raster.dims) == ("y", "x")
    assert raster.to_numpy() == pytest.approx(values)


def test_the_nodata_marker_arrives_as_nan_rather_than_as_a_number(
    tmp_path, released
) -> None:
    """A -9999 left in place is the commonest way a raster quietly poisons a model."""
    values = np.full((3, 4), 0.25)
    values[1, 1] = -9999.0
    released(write_raster(tmp_path / "grid.tif", values, nodata=-9999.0))

    raster = nlm.get_nlm_scenario_raster("whatever.tif")

    assert np.isnan(raster.to_numpy()[1, 1])
    assert raster.to_numpy()[0, 0] == pytest.approx(0.25)


def test_the_rp2500y_moderate_helper_reads_its_hardcoded_path(
    tmp_path, monkeypatch
) -> None:
    """The path is a constant precisely so that nobody retypes it into a script."""
    path = write_raster(tmp_path / "rp2500y.tif", np.full((4, 4), 0.01))
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(nlm, "nlm_release_path", record)

    raster = nlm.get_nlm_scenario_rp2500y_gwd_med_p_ld_moderate_fu()

    assert asked_for == [
        (
            f"core/{nlm.CORE_NLM_VERSION}/scenario/return_period/"
            "rp2500y_lsn_pl50_gwd-med_p_ld_moderate_fu.tif"
        )
    ]
    assert raster.to_numpy() == pytest.approx(0.01)


def test_the_rp2500y_major_helper_reads_its_hardcoded_path(
    tmp_path, monkeypatch
) -> None:
    """The path is a constant precisely so that nobody retypes it into a script."""
    path = write_raster(tmp_path / "rp2500y.tif", np.full((4, 4), 0.02))
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(nlm, "nlm_release_path", record)

    raster = nlm.get_nlm_scenario_rp2500y_gwd_med_p_ld_major_fu()

    assert asked_for == [
        (
            f"core/{nlm.CORE_NLM_VERSION}/scenario/return_period/"
            "rp2500y_lsn_pl50_gwd-med_p_ld_major_fu.tif"
        )
    ]
    assert raster.to_numpy() == pytest.approx(0.02)


def test_the_pga_2500yr_site_class_5_helper_reads_its_hardcoded_path(
    tmp_path, monkeypatch
) -> None:
    """The path is a constant precisely so that nobody retypes it into a script."""
    path = write_raster(tmp_path / "pga.tif", np.full((4, 4), 0.35))
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(nlm, "nlm_release_path", record)

    raster = nlm.get_nlm_scenario_pga_2500yr_site_class_5()

    assert asked_for == [
        (
            f"core/{nlm.CORE_NLM_VERSION}/scenario/return_period/"
            "seismic_standard/pga_2500yr_site_class_5.tif"
        )
    ]
    assert raster.to_numpy() == pytest.approx(0.35)


def test_nlm_release_path_appends_the_relative_path_and_caches(
    tmp_path, monkeypatch
) -> None:
    """nlm_release_path builds NLM_RELEASES_DIR / relative_path and caches it."""
    asked_for = []

    def record(path, **_):
        asked_for.append(path)
        return tmp_path / "cached.tif"

    monkeypatch.setattr("tdrive_sync.get_cached", record)

    result = nlm.nlm_release_path("core/v1/scenario/grid.tif")

    assert asked_for == [nlm.NLM_RELEASES_DIR / "core/v1/scenario/grid.tif"]
    assert result == tmp_path / "cached.tif"


def test_the_flatland_helper_reads_its_hardcoded_path(tmp_path, monkeypatch) -> None:
    """The path is built off FLATLAND_NLM_VERSION rather than CORE_NLM_VERSION."""
    path = tmp_path / "flatland.gpkg"
    flatland = gpd.GeoDataFrame({"geometry": [Point(0, 0)]}, crs="EPSG:2193")
    flatland.to_file(path, driver="GPKG")
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(nlm, "nlm_release_path", record)

    result = nlm.get_nlm_flatland()

    assert asked_for == [
        f"flatland/{nlm.FLATLAND_NLM_VERSION}/_v0p5_slen200m_smoothed.gpkg"
    ]
    assert len(result) == 1
    assert result.crs.to_epsg() == 2193


@pytest.mark.parametrize("site_class", nlm.SITE_CLASSES)
@pytest.mark.parametrize(
    ("reader", "prefix"),
    [
        (nlm.get_nlm_scenario_pga_2500yr, "pga"),
        (nlm.get_nlm_scenario_sa_t1_2500yr, "sa_t1"),
    ],
)
def test_seismic_standard_readers_read_each_site_class(
    tmp_path, monkeypatch, site_class, reader, prefix
) -> None:
    """Each of the seven site classes resolves to its own file in the folder."""
    path = write_raster(tmp_path / "grid.tif", np.full((4, 4), 0.4))
    asked_for = []

    def record(relative_path, **_):
        asked_for.append(relative_path)
        return path

    monkeypatch.setattr(nlm, "nlm_release_path", record)

    reader(site_class)

    assert asked_for == [
        (
            f"core/{nlm.CORE_NLM_VERSION}/scenario/return_period/seismic_standard/"
            f"{prefix}_2500yr_site_class_{site_class}.tif"
        )
    ]


def test_a_site_class_the_nlm_does_not_publish_is_refused() -> None:
    with pytest.raises(ValueError, match="Site class 8"):
        nlm.nlm_seismic_standard_path("sa_t1", 8)


def test_an_unknown_measure_is_refused() -> None:
    with pytest.raises(ValueError, match="pgv"):
        nlm.nlm_seismic_standard_path("pgv", 2)
