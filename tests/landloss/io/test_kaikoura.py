"""Tests for reading the Kaikōura V3 landslide inventory shapefiles.

Every shapefile here is written to ``tmp_path`` by the test that reads it, and
``kaikoura_shapefile_path`` -- the one place that would reach T: -- is
replaced. Nothing touches the network or the network drive.
"""

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from landloss.io import kaikoura

SQUARE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


def write_source_areas(path):
    """Write a two-row source area shapefile using the DBF-truncated columns."""
    gdf = gpd.GeoDataFrame(
        {
            "Source_ID": [1, 2],
            "GeolCode": [3, 2],
            "Method": ["Method 4: Scaling Relationship", "Method 2: Mean Depth"],
            "Volume": [525.0, 567.0],
            "Vol_p1SD": [541.0, 3116.0],
            "Vol_m1SD": [511.0, 0.0],
            "Note": ["Volume used for the total event volume estimate.", None],
            "Reference": ["Jones et al. 2024", "Jones et al. 2024"],
            "Shape_Leng": [40.0, 40.0],
            "Shape_Area": [100.0, 100.0],
            "geometry": [SQUARE, SQUARE],
        },
        crs="EPSG:2193",
    )
    gdf.to_file(path)
    return path


def write_debris_trails(path):
    """Write a two-row debris trail shapefile using the DBF-truncated columns."""
    gdf = gpd.GeoDataFrame(
        {
            "Debris_ID": [1, 2],
            "Shape_Leng": [80.0, 12.0],
            "Shape_Area": [200.0, 5.0],
            "geometry": [SQUARE, SQUARE],
        },
        crs="EPSG:2193",
    )
    gdf.to_file(path)
    return path


@pytest.fixture
def delivered(monkeypatch):
    """Return a function that stands a written shapefile in for one on T:."""

    def use(path):
        monkeypatch.setattr(kaikoura, "kaikoura_shapefile_path", lambda *_, **__: path)
        return path

    return use


def test_source_areas_are_renamed_to_the_csvs_own_column_names(
    tmp_path, delivered
) -> None:
    """The DBF names are truncated; the CSV attribute table's names are not."""
    delivered(write_source_areas(tmp_path / "source_areas.shp"))

    source_areas = kaikoura.get_kaikoura_landslide_source_areas()

    assert set(source_areas.columns) == {
        "source_id",
        "geol_code",
        "ensemble_method",
        "source_area_volume_m3",
        "volume_p1sd_m3",
        "volume_m1sd_m3",
        "note",
        "reference",
        "shape_length_m",
        "source_area_m2",
        "geometry",
    }
    assert source_areas.crs.to_epsg() == 2193
    assert len(source_areas) == 2
    assert source_areas["source_area_volume_m3"].tolist() == [525.0, 567.0]


def test_debris_trails_are_renamed_to_the_csvs_own_column_names(
    tmp_path, delivered
) -> None:
    """The debris trail shapefile carries far fewer columns than the source one."""
    delivered(write_debris_trails(tmp_path / "debris_trails.shp"))

    debris_trails = kaikoura.get_kaikoura_landslide_debris_trails()

    assert set(debris_trails.columns) == {
        "shape_length_m",
        "debris_area_m2",
        "debris_id",
        "geometry",
    }
    assert debris_trails.crs.to_epsg() == 2193
    assert len(debris_trails) == 2
    assert debris_trails["debris_area_m2"].tolist() == [200.0, 5.0]


def testkaikoura_shapefile_path_builds_off_the_shapefiles_dir_and_defaults_uncached(
    tmp_path, monkeypatch
) -> None:
    """copy_to_local defaults False: the source tree is too deep to mirror locally."""
    calls = []

    def record(path, **kwargs):
        calls.append((path, kwargs))
        return tmp_path / "resolved.shp"

    monkeypatch.setattr("tdrive_sync.get_cached", record)

    result = kaikoura.kaikoura_shapefile_path("a_file.shp")

    assert calls == [
        (kaikoura.KAIKOURA_V3_SHAPEFILES_DIR / "a_file.shp", {"copy_to_local": False})
    ]
    assert result == tmp_path / "resolved.shp"
