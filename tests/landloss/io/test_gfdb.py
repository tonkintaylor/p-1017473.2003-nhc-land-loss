"""Tests for reading the USGS Ground Failure Database (GFDB) geodatabase.

Every layer here is written to a synthetic GeoPackage in ``tmp_path`` --
GeoPackage rather than a file geodatabase because GDAL's FileGDB/OpenFileGDB
drivers are read-only, so there is no write driver available to build a
throwaway ``.gdb`` with. ``GFDB_V4_GDB_PATH`` -- the one place that would
reach R: -- is monkeypatched to it. Nothing touches the network or the R:
drive.
"""

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from landloss.io import KOOPCACHE_DIR_ENV_VAR, gfdb

SQUARE = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path, monkeypatch):
    """Keep the event-name cache this module writes out of the working tree."""
    monkeypatch.setenv(KOOPCACHE_DIR_ENV_VAR, str(tmp_path / "koopcache"))


@pytest.fixture
def delivered(monkeypatch, tmp_path):
    """Point GFDB_V4_GDB_PATH at a GeoPackage carrying the given layer name."""

    def use(layer_columns, geometry, *, real_layer_name):
        path = tmp_path / "gfdb.gpkg"
        gdf = gpd.GeoDataFrame({**layer_columns, "geometry": geometry}, crs="EPSG:3857")
        gdf.to_file(path, layer=real_layer_name, driver="GPKG")
        monkeypatch.setattr(gfdb, "GFDB_V4_GDB_PATH", path)
        return path

    return use


def test_ground_failure_polygons_columns_are_lower_cased(delivered) -> None:
    """SHAPE_Length/SHAPE_Area are the only non-lower-case fields on this layer."""
    delivered(
        {
            "area": [206, 68],
            "event_name": ["M 7.5 Guatemala", "M 7.5 Guatemala"],
            "type": ["Landslide", "Landslide"],
            "SHAPE_Length": [78.9, 39.2],
            "SHAPE_Area": [222.4, 73.8],
        },
        [SQUARE, SQUARE],
        real_layer_name="Ground_Failure_Polygons",
    )

    polygons = gfdb.get_gfdb_ground_failure_polygons()

    assert set(polygons.columns) == {
        "area",
        "event_name",
        "type",
        "shape_length",
        "shape_area",
        "geometry",
    }
    assert len(polygons) == 2
    assert polygons.crs.to_epsg() == 3857


def test_ground_failure_points_columns_are_already_lower_case(delivered) -> None:
    """This layer carries no SHAPE_* fields, so lower-casing is a no-op here."""
    delivered(
        {
            "inventory_name": ["Morton (1971)", "Morton (1971)"],
            "event_name": ["M 6.6 Agua Dulce", "M 6.6 Agua Dulce"],
            "type": ["Landslide", "Landslide"],
        },
        [Point(0, 0), Point(1, 1)],
        real_layer_name="Ground_Failure_Points",
    )

    points = gfdb.get_gfdb_ground_failure_points()

    assert set(points.columns) == {"inventory_name", "event_name", "type", "geometry"}
    assert len(points) == 2


def test_seismic_events_columns_are_lower_cased_from_title_case(delivered) -> None:
    """USGS_Name, Depth_km etc are all title-cased in the source layer."""
    delivered(
        {
            "USGS_Name": ["53 km NNE of Amberley, New Zealand", "Darfield"],
            "Country": [None, None],
            "Magnitude": [7.8, 7.1],
            "Depth_km": [15.1, 11.0],
            "Landslide_status": [
                "Inventory (not included)",
                "Inventory (not included)",
            ],
        },
        [Point(0, 0), Point(1, 1)],
        real_layer_name="seismic_event_locations",
    )

    events = gfdb.get_gfdb_seismic_events()

    assert set(events.columns) == {
        "usgs_name",
        "country",
        "magnitude",
        "depth_km",
        "landslide_status",
        "geometry",
    }
    assert events["landslide_status"].tolist() == [
        "Inventory (not included)",
        "Inventory (not included)",
    ]


def test_inventory_centroids_columns_are_lower_cased(delivered) -> None:
    """SB_Link lower-cases to sb_link, not to a spelled-out sciencebase_link."""
    delivered(
        {
            "Event_Name": ["M 7.5 Guatemala", "M 6.6 Agua Dulce"],
            "Inventory_Name": ["Harp and others (1981)", "Morton (1971)"],
            "SB_Link": ["https://sciencebase.gov/a", "https://sciencebase.gov/b"],
            "GF_Type": ["Landslide", "Landslide"],
            "Geo_type": ["Polygon", "Point"],
        },
        [Point(0, 0), Point(1, 1)],
        real_layer_name="event_inventory_centroids",
    )

    centroids = gfdb.get_gfdb_inventory_centroids()

    assert set(centroids.columns) == {
        "event_name",
        "inventory_name",
        "sb_link",
        "gf_type",
        "geo_type",
        "geometry",
    }
    assert len(centroids) == 2


def test_read_layer_pushes_bbox_and_where_down_to_the_read(
    delivered, monkeypatch
) -> None:
    """bbox/where are handed straight to gpd.read_file rather than filtered after."""
    path = delivered(
        {"type": ["Landslide", "Liquefaction"]},
        [SQUARE, SQUARE],
        real_layer_name="Ground_Failure_Polygons",
    )
    calls = []
    real_read_file = gpd.read_file

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(gfdb.gpd, "read_file", record)

    gfdb.get_gfdb_ground_failure_polygons(bbox=(0, 0, 5, 5), where="type = 'Landslide'")

    assert calls == [
        (
            (path,),
            {
                "layer": "Ground_Failure_Polygons",
                "bbox": (0, 0, 5, 5),
                "where": "type = 'Landslide'",
            },
        )
    ]


# --- event_name caching --------------------------------------------------


@pytest.fixture
def two_event_polygons(delivered):
    """A polygon layer carrying rows for two different events."""
    delivered(
        {
            "event_name": ["M 7.5 Guatemala", "M 7.5 Guatemala", "M 6.6 Agua Dulce"],
            "type": ["Landslide", "Landslide", "Landslide"],
        },
        [SQUARE, SQUARE, SQUARE],
        real_layer_name="Ground_Failure_Polygons",
    )


def test_event_name_reads_only_that_events_rows(two_event_polygons) -> None:
    """Only the matching event's rows come back, not the whole layer."""
    polygons = gfdb.get_gfdb_ground_failure_polygons(event_name="M 6.6 Agua Dulce")

    assert len(polygons) == 1
    assert polygons["event_name"].tolist() == ["M 6.6 Agua Dulce"]


def test_event_name_is_cached_after_the_first_read(two_event_polygons) -> None:
    """A second call for the same event never touches the source file again."""
    gfdb.get_gfdb_ground_failure_polygons(event_name="M 7.5 Guatemala")

    cache_path = gfdb._event_cache_path(  # noqa: SLF001
        "Ground_Failure_Polygons", "M 7.5 Guatemala"
    )
    assert cache_path.exists()


def test_gdb_path_prefers_the_local_cache_mirror(tmp_path, monkeypatch) -> None:
    """A copy under .tdrivecache is read in place of the one on R:."""
    source = tmp_path / "R" / "Ground_Failure_Database_v4.gdb"
    mirror = tmp_path / "mirror" / "Ground_Failure_Database_v4.gdb"
    monkeypatch.setattr(gfdb, "GFDB_V4_GDB_PATH", source)
    monkeypatch.setattr("tdrive_sync.get_cached_local_path", lambda _path: mirror)

    assert gfdb.gfdb_gdb_path() == source

    mirror.mkdir(parents=True)
    assert gfdb.gfdb_gdb_path() == mirror


def test_event_name_second_call_does_not_read_the_source_again(
    two_event_polygons, monkeypatch
) -> None:
    """A second call for the same event is served from the local cache file."""
    gfdb.get_gfdb_ground_failure_polygons(event_name="M 7.5 Guatemala")

    # A read of GFDB_V4_GDB_PATH itself would now error, since it no longer
    # points at a real file -- proving a cache hit never gets there.
    monkeypatch.setattr(gfdb, "GFDB_V4_GDB_PATH", Path("does-not-exist.gdb"))

    polygons = gfdb.get_gfdb_ground_failure_polygons(event_name="M 7.5 Guatemala")

    assert len(polygons) == 2


def test_use_cache_false_reads_the_source_again(
    two_event_polygons, monkeypatch
) -> None:
    """Passing use_cache=False re-reads the source even once a cache exists."""
    gfdb.get_gfdb_ground_failure_polygons(event_name="M 7.5 Guatemala")

    calls = []
    real_read_file = gpd.read_file

    def record(*args, **kwargs):
        calls.append((args, kwargs))
        return real_read_file(*args, **kwargs)

    monkeypatch.setattr(gfdb.gpd, "read_file", record)

    gfdb.get_gfdb_ground_failure_polygons(event_name="M 7.5 Guatemala", use_cache=False)

    assert len(calls) == 1
    assert calls[0][1]["where"] == "event_name LIKE 'M 7.5 Guatemala'"


def test_use_cache_false_does_not_write_a_cache_file(two_event_polygons) -> None:
    """A one-off event_name read leaves no cache file behind."""
    gfdb.get_gfdb_ground_failure_polygons(
        event_name="M 6.6 Agua Dulce", use_cache=False
    )

    cache_path = gfdb._event_cache_path(  # noqa: SLF001
        "Ground_Failure_Polygons", "M 6.6 Agua Dulce"
    )
    assert not cache_path.exists()


def test_event_name_and_where_are_mutually_exclusive(two_event_polygons) -> None:
    """Combining event_name with a free-form where would make an ambiguous cache key."""
    with pytest.raises(ValueError, match="Pass only one of"):
        gfdb.get_gfdb_ground_failure_polygons(
            event_name="M 7.5 Guatemala", where="type = 'Landslide'"
        )


def test_event_name_bbox_filters_the_cached_extract(delivered) -> None:
    """bbox still applies to an event_name read, just after the cache lookup."""
    delivered(
        {
            "event_name": ["M 7.5 Guatemala", "M 7.5 Guatemala"],
            "type": ["Landslide", "Landslide"],
        },
        [SQUARE, Polygon([(20, 20), (30, 20), (30, 30), (20, 30)])],
        real_layer_name="Ground_Failure_Polygons",
    )

    polygons = gfdb.get_gfdb_ground_failure_polygons(
        event_name="M 7.5 Guatemala", bbox=(0, 0, 15, 15)
    )

    assert len(polygons) == 1
