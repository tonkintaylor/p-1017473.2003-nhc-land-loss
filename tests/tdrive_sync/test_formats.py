"""Round-trip tests for each format tdrive_sync knows how to save and read."""

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401  (registers the .rio accessor)
import xarray as xr
from shapely.geometry import Point

from tdrive_sync import _formats


def test_csv_round_trips(tmp_path: Path) -> None:
    """A DataFrame saved as csv reads back with the same content."""
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "data.csv"

    _formats.save(df, path, index=False)
    result = _formats.read(path)

    pd.testing.assert_frame_equal(result, df)


def test_json_round_trips(tmp_path: Path) -> None:
    """A dict saved as json reads back unchanged."""
    obj = {"a": 1, "b": [1, 2, 3]}
    path = tmp_path / "data.json"

    _formats.save(obj, path)
    result = _formats.read(path)

    assert result == obj


def test_pickle_round_trips(tmp_path: Path) -> None:
    """An arbitrary picklable object round-trips through .pickle."""
    obj = {"nested": (1, 2, {"three": 3})}
    path = tmp_path / "data.pickle"

    _formats.save(obj, path)
    result = _formats.read(path)

    assert result == obj


def test_pkl_suffix_is_also_accepted(tmp_path: Path) -> None:
    """The shorter .pkl suffix is treated the same as .pickle."""
    obj = {"a": 1}
    path = tmp_path / "data.pkl"

    _formats.save(obj, path)
    result = _formats.read(path)

    assert result == obj


def test_parquet_round_trips_a_plain_dataframe(tmp_path: Path) -> None:
    """A DataFrame without a geometry column reads back as a DataFrame."""
    df = pd.DataFrame({"a": [1, 2]})
    path = tmp_path / "data.parquet"

    _formats.save(df, path)
    result = _formats.read(path)

    assert not isinstance(result, gpd.GeoDataFrame)
    pd.testing.assert_frame_equal(result, df)


def test_parquet_round_trips_a_geodataframe(tmp_path: Path) -> None:
    """A geometry column is detected, so the result comes back as a GeoDataFrame."""
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:2193")
    path = tmp_path / "data.parquet"

    _formats.save(gdf, path)
    result = _formats.read(path)

    assert isinstance(result, gpd.GeoDataFrame)
    assert list(result["name"]) == ["a"]


def test_gpkg_round_trips(tmp_path: Path) -> None:
    """A GeoDataFrame saved as gpkg reads back with the same features."""
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:2193")
    path = tmp_path / "data.gpkg"

    _formats.save(gdf, path)
    result = _formats.read(path)

    assert list(result["name"]) == ["a"]


def test_shp_round_trips(tmp_path: Path) -> None:
    """A GeoDataFrame saved as shp reads back with the same features."""
    gdf = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:2193")
    path = tmp_path / "data.shp"

    _formats.save(gdf, path)
    result = _formats.read(path)

    assert list(result["name"]) == ["a"]


def test_tif_round_trips(tmp_path: Path) -> None:
    """A DataArray saved as tif reads back with the same values."""
    data = np.arange(4, dtype="float32").reshape(1, 2, 2)
    da = xr.DataArray(
        data,
        dims=("band", "y", "x"),
        coords={"band": [1], "y": [1.0, 0.0], "x": [0.0, 1.0]},
    )
    da = da.rio.write_crs("EPSG:2193")
    path = tmp_path / "data.tif"

    with warnings.catch_warnings():
        # rioxarray's internal transform computation uses the deprecated
        # Affine `*` operator; unrelated to anything under our control here.
        warnings.simplefilter("ignore", PendingDeprecationWarning)
        _formats.save(da, path)
        result = _formats.read(path)

    np.testing.assert_array_equal(result.values, da.values)


def test_save_creates_missing_parent_directories(tmp_path: Path) -> None:
    """Saving into a directory tree that does not exist yet just creates it."""
    path = tmp_path / "a" / "b" / "c" / "data.json"

    _formats.save({"x": 1}, path)

    assert path.exists()


def test_an_unsupported_suffix_raises_on_save(tmp_path: Path) -> None:
    """A file type with no dispatch entry fails loudly, not silently."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        _formats.save({}, tmp_path / "data.xyz")


def test_an_unsupported_suffix_raises_on_read(tmp_path: Path) -> None:
    """Reading a file type with no dispatch entry fails loudly, not silently."""
    path = tmp_path / "data.xyz"
    path.write_text("nonsense")

    with pytest.raises(ValueError, match="Unsupported file type"):
        _formats.read(path)
