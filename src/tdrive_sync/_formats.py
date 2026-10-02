"""Format-specific save/read dispatch, keyed by a file's suffix.

Ported from the National Liquefaction Model's ``common.io.public.local``.
"""

import json
import pickle
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
from rioxarray import open_rasterio


def save(obj: Any, path: Path, **kwargs: Any) -> None:
    """Save ``obj`` to ``path``, dispatching on its suffix.

    Args:
        obj: The object to save -- a GeoDataFrame/DataFrame for ``.gpkg``,
            ``.parquet``, ``.csv`` or ``.shp``; a DataArray for ``.tif``; a
            dict for ``.json``; or any picklable object for ``.pickle``/
            ``.pkl``.
        path: Where to save it. Its parent directory is created if needed.
        **kwargs: Passed through to the underlying save function.

    Raises:
        ValueError: If ``path``'s suffix is not one of the supported formats.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.suffix == ".gpkg":
        obj.to_file(path, use_arrow=True, **kwargs)
    elif path.suffix == ".parquet":
        obj.to_parquet(path, **kwargs)
    elif path.suffix == ".tif":
        obj.rio.to_raster(path, **kwargs)
    elif path.suffix == ".csv":
        obj.to_csv(path, **kwargs)
    elif path.suffix == ".json":
        with path.open("w") as f:
            json.dump(obj, f, indent=2, **kwargs)
    elif path.suffix in (".pickle", ".pkl"):
        with path.open("wb") as f:
            pickle.dump(obj, f, **kwargs)
    elif path.suffix == ".shp":
        obj.to_file(path, **kwargs)
    else:
        msg = f"Unsupported file type: {path.suffix}"
        raise ValueError(msg)


def read(path: Path, **kwargs: Any) -> Any:  # noqa: PLR0911
    """Read the file at ``path``, dispatching on its suffix.

    Args:
        path: The file to read.
        **kwargs: Passed through to the underlying read function.

    Returns:
        The file's content: a GeoDataFrame for ``.gpkg``/``.shp``, or for a
        ``.parquet`` with a geometry column; otherwise a DataFrame for
        ``.parquet``/``.csv``; a DataArray for ``.tif``; a dict for
        ``.json``; or whatever a ``.pickle``/``.pkl`` file contains.

    Raises:
        ValueError: If ``path``'s suffix is not one of the supported formats.
    """
    if path.suffix == ".gpkg":
        return gpd.read_file(path, use_arrow=True, **kwargs)
    if path.suffix == ".parquet":
        parquet_file = pq.ParquetFile(path)
        if "geometry" in parquet_file.schema.names:
            return gpd.read_parquet(path, **kwargs)
        return pd.read_parquet(path, **kwargs)
    if path.suffix == ".tif":
        return open_rasterio(path, **kwargs)
    if path.suffix == ".csv":
        return pd.read_csv(path, **kwargs)
    if path.suffix == ".json":
        with path.open("r") as f:
            return json.load(f)
    if path.suffix in (".pickle", ".pkl"):
        with path.open("rb") as f:
            return pickle.load(f)  # noqa: S301
    if path.suffix == ".shp":
        return gpd.read_file(path, **kwargs)

    msg = f"Unsupported file type: {path.suffix}"
    raise ValueError(msg)
