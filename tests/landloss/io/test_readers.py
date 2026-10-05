"""Tests for the vector dataset readers."""

import io
import os
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon

from landloss.domain import constants
from landloss.io import (
    DEFAULT_KOOPCACHE_DIR,
    REPO_ROOT,
    elevation,
    koopcache_dir,
    readers,
)
from landloss.io.area_of_interest import SMALL_WLG_PILOT
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_gwrc_slope_failure,
    get_koordinates_layer_extent,
    get_nz_addresses,
    get_nz_coastline_polygons,
    get_nz_land_cover,
    get_nz_rail_stations,
    get_nz_river_name_lines,
    get_nz_topo50_water,
    get_slide_genesis,
    get_slide_interpreted_materials,
    get_wcc_cut_areas,
    get_wcc_fill_areas,
    get_wellington_urban_geology,
    resolve_api_key,
)

# One square well inside the bbox used below, one entirely outside it, and one
# straddling its eastern edge.
INSIDE = Polygon([(1000, 1000), (1010, 1000), (1010, 1010), (1000, 1010)])
OUTSIDE = Polygon([(5000, 5000), (5010, 5000), (5010, 5010), (5000, 5010)])
STRADDLING = Polygon([(1990, 1000), (2010, 1000), (2010, 1010), (1990, 1010)])

BBOX = (0.0, 0.0, 2000.0, 2000.0)


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the extent cache out of the working tree during tests."""
    monkeypatch.setenv("KOOPCACHE_DIR", str(tmp_path / "koopcache"))


class FakeLayerDetails:
    """Stands in for ttpy's layer details, which name a layer's cache folder."""

    title = "Test Layer: v2"


@pytest.fixture(autouse=True)
def _fake_layer_details(monkeypatch: pytest.MonkeyPatch) -> None:
    """Name layer folders without asking Koordinates for the layer's title."""
    monkeypatch.setattr(
        readers, "get_latest_layer_details", lambda conn, layer_id: FakeLayerDetails
    )


@pytest.fixture
def layer_file(tmp_path: Path) -> Path:
    """Write a three-feature layer to disk and return its path."""
    gdf = gpd.GeoDataFrame(
        {"name": ["inside", "outside", "straddling"]},
        geometry=[INSIDE, OUTSIDE, STRADDLING],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "layer.gpkg"
    gdf.to_file(path)
    return path


class FakeConnection:
    """Stands in for KoordinatesConnection, recording how it was built."""

    def __init__(self, api_key: str, domain: str) -> None:
        self.api_key = api_key
        self.domain = domain
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_koordinates(
    layer_file: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """Serve layer_file in place of a Koordinates download, recording the call."""
    calls: dict[str, object] = {}

    def fake_connection(*, api_key: str, domain: str) -> FakeConnection:
        conn = FakeConnection(api_key=api_key, domain=domain)
        calls["conn"] = conn
        return conn

    def fake_get_latest_layer(*, conn: FakeConnection, layer_id: int) -> Path:
        calls["layer_id"] = layer_id
        return layer_file

    monkeypatch.setattr(readers, "KoordinatesConnection", fake_connection)
    monkeypatch.setattr(readers, "get_latest_layer", fake_get_latest_layer)
    monkeypatch.setenv("TNT_KOORDINATES_API_KEY", "tnt-key")
    monkeypatch.setenv("LINZ_API_KEY", "linz-key")
    return calls


# --- reading and clipping ----------------------------------------------------


def test_loads_every_feature_from_a_path(layer_file: Path) -> None:
    """Without a bbox, the whole layer comes back."""
    result = get_koordinates_layer_extent(layer=layer_file)

    assert sorted(result["name"]) == ["inside", "outside", "straddling"]


def test_defaults_to_nztm(layer_file: Path) -> None:
    """The default CRS is NZTM, which is what the rest of the model works in."""
    result = get_koordinates_layer_extent(layer=layer_file)

    assert result.crs.to_string() == constants.DEFAULT_CRS


def test_reprojects_to_the_requested_crs(layer_file: Path) -> None:
    """The layer is returned in the CRS the caller asked for, not its own."""
    result = get_koordinates_layer_extent(layer=layer_file, crs="EPSG:4326")

    assert result.crs.to_string() == "EPSG:4326"


def test_bbox_excludes_features_outside_it(layer_file: Path) -> None:
    """A feature wholly outside the bounding box is dropped."""
    result = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    assert "outside" not in set(result["name"])


def test_bbox_cuts_a_straddling_feature_at_the_edge(layer_file: Path) -> None:
    """A feature crossing the boundary is clipped rather than kept or dropped."""
    result = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    straddling = result.loc[result["name"] == "straddling"]
    assert len(straddling) == 1

    # The original spans x from 1990 to 2010; only the half inside should remain.
    minx, _, maxx, _ = straddling.total_bounds
    assert minx == pytest.approx(1990.0)
    assert maxx == pytest.approx(2000.0)


def test_bbox_leaves_an_interior_feature_intact(layer_file: Path) -> None:
    """A feature wholly inside the bounding box keeps its original area."""
    result = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    inside = result.loc[result["name"] == "inside"]
    assert inside.geometry.iloc[0].area == pytest.approx(INSIDE.area)


def test_an_empty_bbox_returns_an_empty_frame(layer_file: Path) -> None:
    """A bounding box matching nothing gives an empty frame, not an error."""
    result = get_koordinates_layer_extent(layer=layer_file, bbox=(-10, -10, -5, -5))

    assert result.empty


def test_point_geometry_is_selected_by_bbox(tmp_path: Path) -> None:
    """Clipping works for points as well as polygons."""
    gdf = gpd.GeoDataFrame(
        {"name": ["in", "out"]},
        geometry=[Point(100, 100), Point(9000, 9000)],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "points.gpkg"
    gdf.to_file(path)

    result = get_koordinates_layer_extent(layer=path, bbox=BBOX)

    assert list(result["name"]) == ["in"]


def test_a_bbox_in_another_crs_is_transformed(tmp_path: Path) -> None:
    """A WGS84 bbox selects the right NZTM features, not an empty or full set."""
    pilot = SMALL_WLG_PILOT.bbox()
    inside_pilot = Point((pilot[0] + pilot[2]) / 2, (pilot[1] + pilot[3]) / 2)
    outside_pilot = Point(pilot[2] + 5000, pilot[3] + 5000)

    gdf = gpd.GeoDataFrame(
        {"name": ["in", "out"]},
        geometry=[inside_pilot, outside_pilot],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "wellington.gpkg"
    gdf.to_file(path)

    result = get_koordinates_layer_extent(
        layer=path, crs="EPSG:4326", bbox=SMALL_WLG_PILOT.bbox("EPSG:4326")
    )

    assert list(result["name"]) == ["in"]
    assert result.crs.to_string() == "EPSG:4326"


# --- API keys ----------------------------------------------------------------


def test_resolve_api_key_reads_the_variable_for_the_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each domain has its own key, chosen by domain rather than a shared name."""
    monkeypatch.setenv("TNT_KOORDINATES_API_KEY", "tnt-key")
    monkeypatch.setenv("LINZ_API_KEY", "linz-key")

    assert resolve_api_key(constants.TTGROUP_DOMAIN) == "tnt-key"
    assert resolve_api_key(constants.LINZ_DOMAIN) == "linz-key"


def test_resolve_api_key_rejects_an_unknown_domain() -> None:
    """An unconfigured domain fails loudly rather than sending no key."""
    with pytest.raises(ValueError, match="No API key variable is configured"):
        resolve_api_key("example.koordinates.com")


def test_resolve_api_key_requires_the_variable_to_be_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing key names the variable to set, rather than failing at the API."""
    monkeypatch.delenv("LINZ_API_KEY", raising=False)

    with pytest.raises(ValueError, match="LINZ_API_KEY"):
        resolve_api_key(constants.LINZ_DOMAIN)


# --- Cache directory -----------------------------------------------------------


def test_the_domain_key_is_used_for_the_connection(
    fake_koordinates: dict[str, object],
) -> None:
    """Reading a LINZ layer uses the LINZ key, not the T+T one."""
    get_koordinates_layer_extent(layer=1, domain=constants.LINZ_DOMAIN)

    conn = fake_koordinates["conn"]
    assert conn.api_key == "linz-key"
    assert conn.domain == constants.LINZ_DOMAIN


def test_the_connection_is_closed(fake_koordinates: dict[str, object]) -> None:
    """The session is closed after use rather than left open."""
    get_koordinates_layer_extent(layer=1)

    assert fake_koordinates["conn"].closed


def test_an_integer_layer_is_downloaded_from_koordinates(
    fake_koordinates: dict[str, object],
) -> None:
    """An integer is treated as a layer ID and fetched, not opened as a path."""
    result = get_koordinates_layer_extent(layer=121398)

    assert fake_koordinates["layer_id"] == 121398
    assert len(result) == 3


def test_a_path_never_touches_koordinates(
    layer_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading from a path must not open a connection, which would need a key."""

    def fail(*args: object, **kwargs: object) -> None:
        msg = "Koordinates should not be contacted when given a path"
        raise AssertionError(msg)

    monkeypatch.setattr(readers, "KoordinatesConnection", fail)
    monkeypatch.setattr(readers, "get_latest_layer", fail)

    result = get_koordinates_layer_extent(layer=layer_file)

    assert len(result) == 3


# --- caching -----------------------------------------------------------------


def test_the_same_extent_is_not_reread(
    layer_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second request for the same extent is served from the cache."""
    first = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    def fail(*args: object, **kwargs: object) -> None:
        msg = "the source should not be read again for a cached extent"
        raise AssertionError(msg)

    monkeypatch.setattr(readers, "_read_extent", fail)
    second = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    assert sorted(second["name"]) == sorted(first["name"])
    assert len(second) == len(first)


def test_use_cache_false_recomputes(
    layer_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passing use_cache=False reads the source even when a cache entry exists."""
    get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    calls: list[int] = []
    original = readers._read_extent  # noqa: SLF001

    def counting(*args: object, **kwargs: object) -> gpd.GeoDataFrame:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(readers, "_read_extent", counting)
    get_koordinates_layer_extent(layer=layer_file, bbox=BBOX, use_cache=False)

    assert len(calls) == 1


def test_a_different_bbox_is_cached_separately(layer_file: Path) -> None:
    """The cache key includes the bbox, so a new extent is not served stale."""
    whole = get_koordinates_layer_extent(layer=layer_file)
    clipped = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)

    assert len(whole) == 3
    assert len(clipped) == 2


def test_a_different_crs_is_cached_separately(layer_file: Path) -> None:
    """The cache key includes the CRS, so a reprojection is not served stale."""
    nztm = get_koordinates_layer_extent(layer=layer_file)
    wgs84 = get_koordinates_layer_extent(layer=layer_file, crs="EPSG:4326")

    assert nztm.crs.to_string() == constants.DEFAULT_CRS
    assert wgs84.crs.to_string() == "EPSG:4326"


def test_the_cache_key_includes_the_layer_version(
    layer_file: Path, tmp_path: Path
) -> None:
    """Two source files cache separately, so a new layer version is not masked."""
    other = tmp_path / "layer_v2.gpkg"
    gpd.GeoDataFrame(
        {"name": ["only"]}, geometry=[INSIDE], crs=constants.DEFAULT_CRS
    ).to_file(other)

    first = get_koordinates_layer_extent(layer=layer_file, bbox=BBOX)
    second = get_koordinates_layer_extent(layer=other, bbox=BBOX)

    assert len(first) == 2
    assert list(second["name"]) == ["only"]


def test_an_unclipped_read_is_not_cached(layer_file: Path) -> None:
    """Without a bbox there is no clip to skip, so no duplicate is written."""
    result = get_koordinates_layer_extent(layer=layer_file)

    assert len(result) == 3
    assert not readers.extent_cache_path(
        layer_file, constants.DEFAULT_CRS, None
    ).exists()
    assert not any(readers.extent_cache_dir().iterdir())


def test_an_empty_result_is_not_cached(layer_file: Path) -> None:
    """An empty extent is returned without a cache file being written."""
    empty_bbox = (-10.0, -10.0, -5.0, -5.0)
    result = get_koordinates_layer_extent(layer=layer_file, bbox=empty_bbox)

    assert result.empty
    assert not readers.extent_cache_path(
        layer_file, constants.DEFAULT_CRS, empty_bbox
    ).exists()


# --- the ttpy download cache -------------------------------------------------


@pytest.fixture
def ttpy_sees(monkeypatch: pytest.MonkeyPatch, layer_file: Path) -> dict[str, str]:
    """Record the KOOPCACHE_DIR ttpy would read at the moment it is called."""
    seen: dict[str, str] = {}

    def fake_get_latest_layer(*, conn: FakeConnection, layer_id: int) -> Path:
        seen["KOOPCACHE_DIR"] = os.environ.get("KOOPCACHE_DIR", "")
        return layer_file

    monkeypatch.setattr(readers, "KoordinatesConnection", FakeConnection)
    monkeypatch.setattr(readers, "get_latest_layer", fake_get_latest_layer)
    monkeypatch.setenv("TNT_KOORDINATES_API_KEY", "tnt-key")
    return seen


LAYER_FOLDER = "1-test-layer-v2"


def test_ttpy_gets_the_default_cache_when_the_variable_is_unset(
    ttpy_sees: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """.env.example says leave it unset; ttpy raises on an unset one by itself."""
    monkeypatch.delenv("KOOPCACHE_DIR")
    monkeypatch.setattr(readers, "koopcache_dir", _koopcache_dir_without_creating)

    get_koordinates_layer_extent(layer=1)

    assert Path(ttpy_sees["KOOPCACHE_DIR"]) == DEFAULT_KOOPCACHE_DIR / LAYER_FOLDER


def test_ttpy_gets_a_relative_cache_anchored_at_the_repo_root(
    ttpy_sees: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise ttpy downloads to wherever the script happened to be run from."""
    monkeypatch.setenv("KOOPCACHE_DIR", ".koopcache")
    monkeypatch.setattr(readers, "koopcache_dir", _koopcache_dir_without_creating)

    get_koordinates_layer_extent(layer=1)

    assert Path(ttpy_sees["KOOPCACHE_DIR"]) == REPO_ROOT / ".koopcache" / LAYER_FOLDER


def test_ttpy_gets_an_absolute_cache_unchanged(
    ttpy_sees: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cache deliberately put on another disk stays there."""
    monkeypatch.setenv("KOOPCACHE_DIR", str(tmp_path / "elsewhere"))

    get_koordinates_layer_extent(layer=1)

    assert Path(ttpy_sees["KOOPCACHE_DIR"]) == tmp_path / "elsewhere" / LAYER_FOLDER


def _koopcache_dir_without_creating(*subdirs: str, create: bool = True) -> Path:
    """Resolve cache folders under the real repo without making them there."""
    return koopcache_dir(*subdirs, create=False)


def test_the_cache_root_is_restored_after_a_download(
    ttpy_sees: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every other cache reads the same variable, so ttpy's value must not stick."""
    monkeypatch.setenv("KOOPCACHE_DIR", str(tmp_path / "elsewhere"))

    get_koordinates_layer_extent(layer=1)

    assert os.environ["KOOPCACHE_DIR"] == str(tmp_path / "elsewhere")


def test_an_unset_cache_root_is_left_unset_after_a_download(
    ttpy_sees: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Putting the variable back means removing it when it was never there."""
    monkeypatch.delenv("KOOPCACHE_DIR")
    monkeypatch.setattr(readers, "koopcache_dir", _koopcache_dir_without_creating)

    get_koordinates_layer_extent(layer=1)

    assert "KOOPCACHE_DIR" not in os.environ


# --- one folder per dataset --------------------------------------------------


def test_slugify_keeps_only_lowercase_words_and_hyphens() -> None:
    """Punctuation in a Koordinates title must not reach a Windows path."""
    assert (
        readers.slugify("GNS SLIDE Morphological Data - Genesis")
        == "gns-slide-morphological-data-genesis"
    )
    assert readers.slugify("  Cut/fill: (2013)  ") == "cut-fill-2013"


def test_a_dataset_folder_is_named_from_its_key_and_name() -> None:
    """The point of the folders: a person can find a layer by what it is."""
    folder = readers.dataset_cache_dir("125308", lambda: "GNS SLIDE Data")

    assert folder.name == "125308-gns-slide-data"
    assert folder.is_dir()


def test_an_existing_dataset_folder_is_reused_without_asking_its_name() -> None:
    """A renamed layer keeps its folder, and finding it costs no request."""
    first = readers.dataset_cache_dir("7", lambda: "Old name")

    def fail() -> str:
        msg = "the name should not be asked for when the folder exists"
        raise AssertionError(msg)

    assert readers.dataset_cache_dir("7", fail) == first


def test_a_key_is_not_mistaken_for_a_longer_one() -> None:
    """Layer 12 must not reuse layer 125's folder."""
    readers.dataset_cache_dir("125", lambda: "Other")

    assert readers.dataset_cache_dir("12", lambda: "Mine").name == "12-mine"


def test_a_downloaded_layer_is_fetched_into_its_own_folder(
    ttpy_sees: dict[str, str], tmp_path: Path
) -> None:
    """ttpy is pointed at the layer's folder, not the cache root."""
    get_koordinates_layer_extent(layer=1)

    assert Path(ttpy_sees["KOOPCACHE_DIR"]).name == LAYER_FOLDER


def test_a_downloaded_layer_caches_its_extents_beside_it(
    fake_koordinates: dict[str, object], layer_file: Path
) -> None:
    """A layer's clips sit in an extents folder next to the download."""
    get_koordinates_layer_extent(layer=1, bbox=BBOX)

    assert len(list((layer_file.parent / "extents").glob("*.gpkg"))) == 1
    assert not any(readers.extent_cache_dir().iterdir())


def test_an_arcgis_layer_is_cached_in_a_named_folder(monkeypatch) -> None:
    """The sub-layer's name is asked of the service, once, to name its folder."""
    requests_made = []

    def fake_get(url, params, timeout):
        requests_made.append(url)
        return FakeResponse({"name": "Interpreted Materials"})

    monkeypatch.setattr(readers.requests, "get", fake_get)
    url = "https://example.test/rest/services/Env/GNSSlideData/MapServer"

    first = readers.arcgis_cache_path(url, 3, "EPSG:2193", None)
    second = readers.arcgis_cache_path(url, 3, "EPSG:2193", (1, 2, 3, 4))

    assert first.parent.name == "gnsslidedata-3-interpreted-materials"
    assert first.parent.parent.name == "arcgis"
    assert second.parent == first.parent
    assert requests_made == [f"{url}/3"]


def test_a_wfs_layer_is_cached_in_a_folder_named_for_it() -> None:
    """A WFS type name already reads as a name, so it names the folder."""
    path = readers.wfs_cache_path(
        "https://example.test/ows", "gns:NZL-Urban_Wellington", "EPSG:2193", None
    )

    assert path.parent.name == "gns-nzl-urban-wellington"
    assert path.parent.parent.name == "wfs"


# --- NZ Rail Station Points ---------------------------------------------------


def test_get_nz_rail_stations_requests_the_linz_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The helper points at the LINZ Topo50 station layer with the LINZ key."""
    get_nz_rail_stations(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.NZ_RAIL_STATION_POINTS_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.LINZ_DOMAIN
    assert fake_koordinates["conn"].api_key == "linz-key"


# --- NZ Addresses ------------------------------------------------------------


def test_get_nz_addresses_requests_the_linz_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The helper points at the LINZ addresses layer with the LINZ key."""
    get_nz_addresses(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.NZ_ADDRESSES_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.LINZ_DOMAIN
    assert fake_koordinates["conn"].api_key == "linz-key"


def test_get_nz_addresses_applies_the_bbox(
    fake_koordinates: dict[str, object],
) -> None:
    """The extent is passed through, rather than the whole country returned."""
    result = get_nz_addresses(bbox=BBOX)

    assert "outside" not in set(result["name"])


def test_get_nz_addresses_applies_the_crs(
    fake_koordinates: dict[str, object],
) -> None:
    """The requested CRS is passed through to the reader."""
    result = get_nz_addresses(crs="EPSG:4326")

    assert result.crs.to_string() == "EPSG:4326"


def test_nz_addresses_layer_id_matches_linz() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.NZ_ADDRESSES_LAYER_ID == 123113


def test_get_nz_river_name_lines_requests_the_linz_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The helper points at the LINZ river name lines layer with the LINZ key."""
    get_nz_river_name_lines(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.NZ_RIVER_NAME_LINES_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.LINZ_DOMAIN
    assert fake_koordinates["conn"].api_key == "linz-key"


def test_get_nz_coastline_polygons_requests_the_linz_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The water mask reads the LINZ Topo50 land polygons with the LINZ key."""
    get_nz_coastline_polygons(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.NZ_COASTLINE_POLYGONS_LAYER_ID
    assert fake_koordinates["layer_id"] == 51153
    assert fake_koordinates["conn"].domain == constants.LINZ_DOMAIN
    assert fake_koordinates["conn"].api_key == "linz-key"


@pytest.mark.parametrize(
    ("kind", "layer_id"),
    [
        ("river", constants.NZ_RIVER_POLYGONS_TOPO50_LAYER_ID),
        ("lake", constants.NZ_LAKE_POLYGONS_TOPO50_LAYER_ID),
        ("lagoon", constants.NZ_LAGOON_POLYGONS_TOPO50_LAYER_ID),
        ("swamp", constants.NZ_SWAMP_POLYGONS_TOPO50_LAYER_ID),
        ("coast", constants.NZ_COASTLINES_TOPO50_LAYER_ID),
    ],
)
def test_get_nz_topo50_water_requests_the_linz_layer(
    fake_koordinates: dict[str, object], kind: str, layer_id: int
) -> None:
    """Each topo50 water helper points at the layer for its kind."""
    get_nz_topo50_water(kind, bbox=BBOX)

    assert fake_koordinates["layer_id"] == layer_id
    assert fake_koordinates["conn"].domain == constants.LINZ_DOMAIN
    assert fake_koordinates["conn"].api_key == "linz-key"


def test_get_nz_river_name_lines_applies_the_bbox(
    fake_koordinates: dict[str, object],
) -> None:
    """The extent is passed through, rather than the whole country returned."""
    result = get_nz_river_name_lines(bbox=BBOX)

    assert "outside" not in set(result["name"])


def test_nz_river_name_lines_layer_id_matches_linz() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.NZ_RIVER_NAME_LINES_LAYER_ID == 103632


# --- GWRC slope failure ------------------------------------------------------

# A self-intersecting bow tie: invalid as written, and repairable.
BOW_TIE = Polygon([(0, 0), (10, 10), (10, 0), (0, 10)])


@pytest.fixture
def fake_gwrc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Serve a severity-classed layer in place of a Koordinates download."""
    gdf = gpd.GeoDataFrame(
        {
            "SEVERITY": ["1 Low", "3 Moderate", "5 High"],
            "LSKEY": [1, 2, 3],
        },
        geometry=[INSIDE, STRADDLING, OUTSIDE],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "gwrc.gpkg"
    gdf.to_file(path)

    calls: dict[str, object] = {}

    def fake_connection(*, api_key: str, domain: str) -> FakeConnection:
        conn = FakeConnection(api_key=api_key, domain=domain)
        calls["conn"] = conn
        return conn

    def fake_get_latest_layer(*, conn: FakeConnection, layer_id: int) -> Path:
        calls["layer_id"] = layer_id
        return path

    monkeypatch.setattr(readers, "KoordinatesConnection", fake_connection)
    monkeypatch.setattr(readers, "get_latest_layer", fake_get_latest_layer)
    monkeypatch.setenv("KOORDINATES_PUBLIC_API_KEY", "public-key")
    calls["path"] = path
    return calls


def test_gwrc_uses_the_public_catalogue_and_its_own_key(
    fake_gwrc: dict[str, object],
) -> None:
    """The layer is on koordinates.com, whose key is neither the T+T nor LINZ one."""
    get_gwrc_slope_failure()

    assert fake_gwrc["layer_id"] == constants.GWRC_SLOPE_FAILURE_LAYER_ID
    assert fake_gwrc["conn"].domain == constants.KOORDINATES_PUBLIC_DOMAIN
    assert fake_gwrc["conn"].api_key == "public-key"


def test_gwrc_layer_id_matches_koordinates() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.GWRC_SLOPE_FAILURE_LAYER_ID == 4069


def test_gwrc_severity_is_ranked(fake_gwrc: dict[str, object]) -> None:
    """SEVERITY is an inconsistently labelled string, so a sortable rank is added."""
    zones = get_gwrc_slope_failure()

    ranks = dict(zip(zones["SEVERITY"], zones["severity_rank"], strict=False))
    assert ranks == {"1 Low": 1, "3 Moderate": 3, "5 High": 5}


def test_gwrc_keeps_the_original_severity(fake_gwrc: dict[str, object]) -> None:
    """The source labels survive, so a figure can show what the source says."""
    zones = get_gwrc_slope_failure()

    assert set(zones["SEVERITY"]) == {"1 Low", "3 Moderate", "5 High"}


def test_gwrc_every_known_class_has_a_rank() -> None:
    """All five classes are present in the real layer, so all five must map."""
    assert sorted(constants.GWRC_SEVERITY_RANKS.values()) == [1, 2, 3, 4, 5]


def test_gwrc_rejects_an_unknown_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new class upstream must fail loudly rather than become a silent gap."""
    gdf = gpd.GeoDataFrame(
        {"SEVERITY": ["6 Extreme"], "LSKEY": [1]},
        geometry=[INSIDE],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "unknown.gpkg"
    gdf.to_file(path)

    monkeypatch.setattr(
        readers,
        "KoordinatesConnection",
        lambda *, api_key, domain: FakeConnection(api_key=api_key, domain=domain),
    )
    monkeypatch.setattr(readers, "get_latest_layer", lambda *, conn, layer_id: path)
    monkeypatch.setenv("KOORDINATES_PUBLIC_API_KEY", "public-key")

    with pytest.raises(ValueError, match="Unrecognised SEVERITY"):
        get_gwrc_slope_failure()


def test_gwrc_repairs_invalid_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid source polygons would otherwise break every later clip or overlay."""
    gdf = gpd.GeoDataFrame(
        {"SEVERITY": ["1 Low"], "LSKEY": [1]},
        geometry=[BOW_TIE],
        crs=constants.DEFAULT_CRS,
    )
    path = tmp_path / "invalid.gpkg"
    gdf.to_file(path)
    assert not gpd.read_file(path).geometry.is_valid.all()

    monkeypatch.setattr(
        readers,
        "KoordinatesConnection",
        lambda *, api_key, domain: FakeConnection(api_key=api_key, domain=domain),
    )
    monkeypatch.setattr(readers, "get_latest_layer", lambda *, conn, layer_id: path)
    monkeypatch.setenv("KOORDINATES_PUBLIC_API_KEY", "public-key")

    zones = get_gwrc_slope_failure()

    assert zones.geometry.is_valid.all()


def test_gwrc_applies_the_bbox(fake_gwrc: dict[str, object]) -> None:
    """The extent is passed through, rather than the whole region returned."""
    zones = get_gwrc_slope_failure(bbox=BBOX)

    assert "5 High" not in set(zones["SEVERITY"])


def test_get_nz_land_cover_requests_the_lris_layer(
    fake_koordinates: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The helper points at the LCDB layer on LRIS, with the LRIS key."""
    monkeypatch.setenv("LRIS_API_KEY", "lris-key")

    get_nz_land_cover(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.NZ_LCDB_V60_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.LRIS_DOMAIN
    assert fake_koordinates["conn"].api_key == "lris-key"


def test_nz_land_cover_layer_id_matches_lris() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.NZ_LCDB_V60_LAYER_ID == 123148


def test_lris_has_its_own_api_key_variable() -> None:
    """LRIS is a separate Koordinates account, so it needs its own key."""
    assert constants.API_KEY_ENV_VARS[constants.LRIS_DOMAIN] == "LRIS_API_KEY"


# --- GNS SLIDE morphology --------------------------------------------------


def test_get_gns_slide_morphology_requests_the_ttgroup_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The mirror lives on the T+T instance, so the T+T key is the one used."""
    get_gns_slide_morphology(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.GNS_SLIDE_MORPHOLOGY_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.TTGROUP_DOMAIN
    assert fake_koordinates["conn"].api_key == "tnt-key"


def test_gns_slide_morphology_layer_id_matches_koordinates() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.GNS_SLIDE_MORPHOLOGY_LAYER_ID == 125308


def test_get_gns_slide_morphology_applies_the_bbox(
    fake_koordinates: dict[str, object],
) -> None:
    """The extent is passed through, rather than all of Wellington returned."""
    result = get_gns_slide_morphology(bbox=BBOX)

    assert "outside" not in set(result["name"])


# --- GNS SLIDE genesis -----------------------------------------------------


def test_get_slide_genesis_requests_the_ttgroup_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The mirror lives on the T+T instance, so the T+T key is the one used."""
    get_slide_genesis(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.GNS_SLIDE_GENESIS_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.TTGROUP_DOMAIN
    assert fake_koordinates["conn"].api_key == "tnt-key"


def test_gns_slide_genesis_layer_id_matches_koordinates() -> None:
    """Guards the layer ID against an accidental edit."""
    assert constants.GNS_SLIDE_GENESIS_LAYER_ID == 125309


def test_the_slide_genesis_layer_is_not_the_morphology_layer() -> None:
    """Morphology is the lines and genesis the polygons; mixing them up is quiet."""
    assert (
        constants.GNS_SLIDE_GENESIS_LAYER_ID != constants.GNS_SLIDE_MORPHOLOGY_LAYER_ID
    )


def test_get_slide_genesis_applies_the_bbox(
    fake_koordinates: dict[str, object],
) -> None:
    """The extent is passed through, rather than all of Wellington returned."""
    result = get_slide_genesis(bbox=BBOX)

    assert "outside" not in set(result["name"])


# --- WCC earthmoving ---------------------------------------------------------


def test_get_wcc_cut_areas_requests_the_ttgroup_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The mirror lives on the T+T instance, so the T+T key is the one used."""
    get_wcc_cut_areas(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.WCC_CUT_AREAS_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.TTGROUP_DOMAIN
    assert fake_koordinates["conn"].api_key == "tnt-key"


def test_get_wcc_fill_areas_requests_the_ttgroup_layer(
    fake_koordinates: dict[str, object],
) -> None:
    """The fill mirror is on the same instance and read the same way."""
    get_wcc_fill_areas(bbox=BBOX)

    assert fake_koordinates["layer_id"] == constants.WCC_FILL_AREAS_LAYER_ID
    assert fake_koordinates["conn"].domain == constants.TTGROUP_DOMAIN
    assert fake_koordinates["conn"].api_key == "tnt-key"


def test_wcc_cut_and_fill_are_separate_layers() -> None:
    """Cut and fill fail differently under shaking and must not be merged."""
    assert constants.WCC_CUT_AREAS_LAYER_ID != constants.WCC_FILL_AREAS_LAYER_ID


def test_wcc_layer_ids_match_koordinates() -> None:
    """Guards the layer IDs against an accidental edit."""
    assert constants.WCC_CUT_AREAS_LAYER_ID == 125307
    assert constants.WCC_FILL_AREAS_LAYER_ID == 125311


def test_get_wcc_cut_areas_applies_the_bbox(
    fake_koordinates: dict[str, object],
) -> None:
    """The extent is passed through, rather than all of Wellington returned."""
    result = get_wcc_cut_areas(bbox=BBOX)

    assert "outside" not in set(result["name"])


# --- ArcGIS REST ---------------------------------------------------------------


class FakeResponse:
    """Stands in for a requests Response carrying one page of GeoJSON."""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def geojson_page(names):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"Type": name},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                    ],
                },
            }
            for name in names
        ],
    }


@pytest.fixture
def fake_arcgis(monkeypatch):
    """Serve two pages then an empty one, recording every request made."""
    calls = []
    pages = [geojson_page(["a", "b"]), geojson_page(["c"])]

    def fake_get(url, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        index = len(calls) - 1
        payload = pages[index] if index < len(pages) else geojson_page([])
        return FakeResponse(payload)

    monkeypatch.setattr(readers.requests, "get", fake_get)
    return calls


def test_arcgis_pages_until_a_short_page(fake_arcgis, tmp_path):
    """The service caps a page, so one request is never the whole layer."""
    result = readers.get_arcgis_feature_layer(
        "https://example.test/MapServer", 3, page_size=2, use_cache=False
    )

    assert list(result["Type"]) == ["a", "b", "c"]
    assert len(fake_arcgis) == 2


def test_arcgis_advances_the_offset_between_pages(fake_arcgis):
    """Without the offset moving, the same page comes back for ever."""
    readers.get_arcgis_feature_layer(
        "https://example.test/MapServer", 3, page_size=2, use_cache=False
    )

    offsets = [call["params"]["resultOffset"] for call in fake_arcgis]
    assert offsets == [0, 2]


def test_arcgis_asks_the_service_for_the_crs(fake_arcgis):
    """outSR avoids reprojecting geometry that the service can project itself."""
    result = readers.get_arcgis_feature_layer(
        "https://example.test/MapServer", 3, page_size=2, use_cache=False
    )

    assert fake_arcgis[0]["params"]["outSR"] == "2193"
    assert result.crs.to_string() == constants.DEFAULT_CRS


def test_arcgis_sends_the_bbox_in_the_same_crs(fake_arcgis):
    """A box in one system and geometry in another would silently select nothing."""
    readers.get_arcgis_feature_layer(
        "https://example.test/MapServer",
        3,
        bbox=(1.0, 2.0, 3.0, 4.0),
        page_size=2,
        use_cache=False,
    )

    params = fake_arcgis[0]["params"]
    assert params["geometry"] == "1.0,2.0,3.0,4.0"
    assert params["inSR"] == params["outSR"]


def test_arcgis_raises_on_a_service_error(monkeypatch):
    """ArcGIS answers an error with HTTP 200, so it has to be checked for."""
    payload = {"error": {"code": 400, "message": "Invalid or missing input"}}
    monkeypatch.setattr(
        readers.requests, "get", lambda url, params, timeout: FakeResponse(payload)
    )

    with pytest.raises(ValueError, match="Invalid or missing input"):
        readers.get_arcgis_feature_layer(
            "https://example.test/MapServer", 3, use_cache=False
        )


def test_slide_materials_points_at_the_wcc_service(fake_arcgis):
    """The materials layer is sub-layer 3, and is not on Koordinates at all."""
    get_slide_interpreted_materials(use_cache=False)

    assert fake_arcgis[0]["url"].startswith(constants.GNS_SLIDE_SERVICE_URL)
    assert fake_arcgis[0]["url"].endswith(
        f"/{constants.GNS_SLIDE_INTERPRETED_MATERIALS_SUBLAYER}/query"
    )


def test_the_slide_sublayers_are_distinct():
    """Genesis says what formed the ground, materials what it is made of."""
    sublayers = {
        constants.GNS_SLIDE_MORPHOLOGY_SUBLAYER,
        constants.GNS_SLIDE_STUDY_AREA_SUBLAYER,
        constants.GNS_SLIDE_GENESIS_SUBLAYER,
        constants.GNS_SLIDE_INTERPRETED_MATERIALS_SUBLAYER,
    }

    assert len(sublayers) == 4


class WfsCalls(list):
    """The requests made to the fake WFS, and the answer it serves next."""

    def __init__(self):
        super().__init__()
        self.payload: dict = {}


@pytest.fixture
def fake_wfs(monkeypatch):
    """Serve one GeoJSON answer, recording every request made."""
    calls = WfsCalls()
    calls.payload = {**geojson_page(["a", "b"]), "numberMatched": 2}

    def fake_get(url, params, timeout):
        calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(calls.payload)

    monkeypatch.setattr(readers.requests, "get", fake_get)
    return calls


def test_wfs_returns_the_features_in_the_requested_crs(fake_wfs):
    """The layer comes back as a frame in the CRS asked for."""
    result = readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)

    assert list(result["Type"]) == ["a", "b"]
    assert result.crs.to_string() == constants.DEFAULT_CRS


def test_wfs_asks_the_service_for_the_crs(fake_wfs):
    """srsName avoids reprojecting geometry the server can project itself."""
    readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)

    params = fake_wfs[0]["params"]
    assert params["srsName"] == "EPSG:2193"
    assert params["typeNames"] == "ns:x"
    assert params["outputFormat"] == "application/json"


def test_wfs_sends_the_bbox_in_the_same_crs(fake_wfs):
    """A box in one system and geometry in another would silently select nothing."""
    readers.get_wfs_layer(
        "https://example.test/ows",
        "ns:x",
        bbox=(1.0, 2.0, 3.0, 4.0),
        use_cache=False,
    )

    assert fake_wfs[0]["params"]["bbox"] == "1.0,2.0,3.0,4.0,EPSG:2193"


def test_wfs_omits_the_bbox_when_none_is_given(fake_wfs):
    """No box means the whole layer, so nothing is sent to restrict it."""
    readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)

    assert "bbox" not in fake_wfs[0]["params"]


def test_wfs_raises_when_the_server_truncates(fake_wfs):
    """A server-side cap must not pass for the whole layer."""
    fake_wfs.payload = {**geojson_page(["a"]), "numberMatched": 5}

    with pytest.raises(ValueError, match="1 of the 5 features"):
        readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)


def test_wfs_raises_on_an_exception_report(monkeypatch):
    """WFS reports a fault as XML, which is not GeoJSON."""

    class XmlResponse(FakeResponse):
        text = "<ows:ExceptionReport>Could not find layer ns:x</ows:ExceptionReport>"

        def json(self):
            msg = "not json"
            raise ValueError(msg)

    monkeypatch.setattr(
        readers.requests, "get", lambda url, params, timeout: XmlResponse(None)
    )

    with pytest.raises(ValueError, match="Could not find layer"):
        readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)


def test_wfs_returns_an_empty_frame_for_an_empty_extent(fake_wfs):
    """An extent with nothing in it is an empty layer, not an error."""
    fake_wfs.payload = {**geojson_page([]), "numberMatched": 0}

    result = readers.get_wfs_layer("https://example.test/ows", "ns:x", use_cache=False)

    assert result.empty
    assert result.crs.to_string() == constants.DEFAULT_CRS


def test_wfs_cache_key_includes_the_layer_and_extent():
    """Two layers or two extents must never share a cache file."""
    url = "https://example.test/ows"
    keys = {
        readers.wfs_cache_path(url, "ns:x", "EPSG:2193", None),
        readers.wfs_cache_path(url, "ns:y", "EPSG:2193", None),
        readers.wfs_cache_path(url, "ns:x", "EPSG:2193", (1, 2, 3, 4)),
        readers.wfs_cache_path(url, "ns:x", "EPSG:4326", None),
    }

    assert len(keys) == 4


def test_wellington_urban_geology_points_at_the_gns_geoserver(fake_wfs):
    """The 1:50,000 geology is a GNS GeoServer layer, not a Koordinates one."""
    get_wellington_urban_geology(use_cache=False)

    assert fake_wfs[0]["url"] == constants.GNS_GEOSERVER_WFS_URL
    assert (
        fake_wfs[0]["params"]["typeNames"]
        == constants.GNS_URBAN_WELLINGTON_GEOLOGY_LAYER
    )


def test_wellington_urban_geology_applies_the_bbox(fake_wfs):
    """The extent is passed through to the service."""
    get_wellington_urban_geology(bbox=BBOX, use_cache=False)

    assert fake_wfs[0]["params"]["bbox"].startswith(
        ",".join(str(value) for value in BBOX)
    )


# --- the surface model --------------------------------------------------------
#
# The surface model is mosaicked from tiles found by walking the LINZ STAC
# catalogue. Here the walk is faked with local tiles written to tmp_path, so
# the test is of the mosaic -- newest survey first, gaps left NaN, the cache --
# and not of the catalogue.

DSM_BBOX = (1_748_000.0, 5_425_000.0, 1_748_020.0, 5_425_010.0)

# rasterio builds a transform through affine's ``*`` operator, which affine
# 3.0.1 has begun warning about; nothing to fix on this side, and the suite
# turns every warning into a failure.
ignore_affine_matmul = pytest.mark.filterwarnings(
    "ignore:Use `@` matmul:PendingDeprecationWarning"
)


def write_tile(
    path: Path, bounds: tuple[float, float, float, float], value: float
) -> Path:
    """Write a 1 m NZTM tile of one value over some bounds."""
    minx, miny, maxx, maxy = bounds
    width, height = int(maxx - minx), int(maxy - miny)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=constants.DEFAULT_CRS,
        transform=from_origin(minx, maxy, 1.0, 1.0),
        nodata=-9999.0,
    ) as destination:
        destination.write(np.full((height, width), value, dtype="float32"), 1)
    return path


@pytest.fixture
def fake_dsm_tiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Two overlapping surveys over the west of DSM_BBOX, nothing over its east."""
    newer = write_tile(
        tmp_path / "newer.tif",
        (1_748_000.0, 5_425_000.0, 1_748_010.0, 5_425_010.0),
        10.0,
    )
    older = write_tile(
        tmp_path / "older.tif",
        (1_748_005.0, 5_425_000.0, 1_748_015.0, 5_425_010.0),
        20.0,
    )
    calls: dict = {"bboxes": []}

    def fake_find_dsm_tiles(bbox_wgs84, *, use_cache):
        calls["bboxes"].append(bbox_wgs84)
        return [
            {
                "id": "newer",
                "bbox": (0, 0, 0, 0),
                "asset": str(newer),
                "survey": "2025",
            },
            {
                "id": "older",
                "bbox": (0, 0, 0, 0),
                "asset": str(older),
                "survey": "2014",
            },
        ]

    monkeypatch.setattr(readers, "find_dsm_tiles", fake_find_dsm_tiles)
    return calls


def read_grid(path: Path) -> np.ndarray:
    with rasterio.open(path) as source:
        return source.read(1)


@ignore_affine_matmul
def test_get_dsm_mosaics_newest_survey_first_and_leaves_gaps_nan(
    fake_dsm_tiles: dict,
) -> None:
    path = readers.get_dsm(DSM_BBOX, resolution=1)

    grid = read_grid(path)
    assert grid.shape == (10, 20)
    assert grid[:, :10] == pytest.approx(10.0)  # the newer survey wins its overlap
    assert grid[:, 10:15] == pytest.approx(20.0)  # the older fills what it alone has
    assert np.isnan(grid[:, 15:]).all()  # no survey reaches the east


@ignore_affine_matmul
def test_get_dsm_asks_the_catalogue_for_the_extent_in_wgs84(
    fake_dsm_tiles: dict,
) -> None:
    readers.get_dsm(DSM_BBOX, resolution=1)

    (bbox_wgs84,) = fake_dsm_tiles["bboxes"]
    assert 174.0 < bbox_wgs84[0] < bbox_wgs84[2] < 176.0
    assert -42.0 < bbox_wgs84[1] < bbox_wgs84[3] < -41.0


@ignore_affine_matmul
def test_get_dsm_writes_the_grid_the_extent_asked_for(fake_dsm_tiles: dict) -> None:
    path = readers.get_dsm(DSM_BBOX, resolution=1)

    with rasterio.open(path) as source:
        assert source.bounds == pytest.approx(DSM_BBOX)
        assert source.crs.to_epsg() == 2193
        assert np.isnan(source.nodata)


@ignore_affine_matmul
def test_get_dsm_reuses_the_cached_file(fake_dsm_tiles: dict) -> None:
    first = readers.get_dsm(DSM_BBOX, resolution=1)
    second = readers.get_dsm(DSM_BBOX, resolution=1)

    assert first == second
    assert len(fake_dsm_tiles["bboxes"]) == 1


@ignore_affine_matmul
def test_get_dsm_can_be_told_to_fetch_again(fake_dsm_tiles: dict) -> None:
    readers.get_dsm(DSM_BBOX, resolution=1)
    readers.get_dsm(DSM_BBOX, resolution=1, use_cache=False)

    assert len(fake_dsm_tiles["bboxes"]) == 2


def test_the_dsm_cache_is_keyed_apart_from_the_dem_cache() -> None:
    dem = readers.dem_cache_path(DSM_BBOX, 1, constants.DEFAULT_CRS)
    dsm = readers.dsm_cache_path(DSM_BBOX, 1, constants.DEFAULT_CRS)

    assert dem != dsm
    assert dsm.parent.name == "dsm"
    assert dsm.name.startswith("dsm_1m_")


@pytest.fixture
def fake_dsm_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two DSM surveys over Lower Hutt, a DEM one there, and a DSM over Auckland."""
    root_url = elevation.ELEVATION_CATALOG_URL
    base = root_url.rsplit("/", maxsplit=1)[0]
    hutt = {"spatial": {"bbox": [[174.80, -41.35, 175.03, -41.09]]}}
    auckland = {"spatial": {"bbox": [[174.40, -37.05, 175.30, -36.10]]}}

    def collection(title, extent, end, items):
        return {
            "id": title,
            "title": title,
            "extent": {**extent, "temporal": {"interval": [["2000-01-01", end]]}},
            "links": [{"rel": "item", "href": f"./{item}.json"} for item in items],
        }

    def item(bbox):
        return {"bbox": list(bbox), "assets": {"visual": {"href": "./tile.tif"}}}

    documents = {
        root_url: {
            "links": [
                {
                    "rel": "child",
                    "href": "./wellington/hutt_2021/dsm_1m/2193/collection.json",
                },
                {
                    "rel": "child",
                    "href": "./wellington/hutt_2025/dsm_1m/2193/collection.json",
                },
                {
                    "rel": "child",
                    "href": "./wellington/hutt_2025/dem_1m/2193/collection.json",
                },
                {
                    "rel": "child",
                    "href": "./auckland/north_2016/dsm_1m/2193/collection.json",
                },
            ]
        },
        f"{base}/wellington/hutt_2021/dsm_1m/2193/collection.json": collection(
            "Hutt DSM 2021", hutt, "2021-03-01", ["a"]
        ),
        f"{base}/wellington/hutt_2025/dsm_1m/2193/collection.json": collection(
            "Hutt DSM 2025", hutt, "2025-03-01", ["b", "far"]
        ),
        f"{base}/wellington/hutt_2025/dem_1m/2193/collection.json": collection(
            "Hutt DEM 2025", hutt, "2025-03-01", ["c"]
        ),
        f"{base}/auckland/north_2016/dsm_1m/2193/collection.json": collection(
            "Auckland DSM", auckland, "2016-03-01", ["d"]
        ),
        f"{base}/wellington/hutt_2021/dsm_1m/2193/a.json": item(
            (174.90, -41.25, 174.95, -41.20)
        ),
        f"{base}/wellington/hutt_2025/dsm_1m/2193/b.json": item(
            (174.90, -41.25, 174.95, -41.20)
        ),
        f"{base}/wellington/hutt_2025/dsm_1m/2193/far.json": item(
            (175.00, -41.12, 175.02, -41.10)
        ),
    }

    def fake_fetch_json(url, *, use_cache=True):
        return documents[url]

    monkeypatch.setattr(elevation, "fetch_json", fake_fetch_json)


def test_find_dsm_tiles_keeps_only_covering_dsm_surveys_newest_first(
    fake_dsm_catalogue: None,
) -> None:
    tiles = readers.find_dsm_tiles((174.90, -41.25, 174.95, -41.20))

    assert [tile["survey"] for tile in tiles] == ["Hutt DSM 2025", "Hutt DSM 2021"]
    assert tiles[0]["asset"].endswith("/wellington/hutt_2025/dsm_1m/2193/tile.tif")


# --- Koordinates tables ------------------------------------------------------


def zipped_csv(text):
    """Return a Koordinates export zip holding one CSV and its sidecars."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("table.csv", "\ufeff" + text)
        archive.writestr("table.txt", "licence")
    return buffer.getvalue()


class FakeTableResponse:
    """Stands in for a requests Response from the Koordinates exports API."""

    def __init__(self, payload=None, content=b""):
        self.payload = payload
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeTableSession:
    """Serves one table's details, an export that finishes on the second poll,
    and the zip it produces, recording every request."""

    def __init__(self, *, final_state="complete", version=7):
        self.headers = {}
        self.requests = []
        self.final_state = final_state
        self.version = version
        self.polls = 0

    def get(self, url, **kwargs):
        self.requests.append(("GET", url))
        if url.endswith("/tables/51567/"):
            return FakeTableResponse({"version": {"id": self.version}})
        if url.endswith("/exports/1/"):
            self.polls += 1
            state = "processing" if self.polls < 2 else self.final_state
            return FakeTableResponse(
                {"id": 1, "state": state, "download_url": "https://x.test/dl"}
            )
        return FakeTableResponse(
            content=zipped_csv("title_no,code\nWN1/1,060\n123456,007\n")
        )

    def post(self, url, json, **kwargs):
        self.requests.append(("POST", url))
        self.posted = json
        return FakeTableResponse({"id": 1, "state": "processing"})


@pytest.fixture
def fake_table_session(monkeypatch):
    """Replace requests.Session in the readers with a FakeTableSession."""
    sessions = []

    def make(**kwargs):
        session = FakeTableSession(**kwargs)
        sessions.append(session)
        return session

    monkeypatch.setattr(readers.requests, "Session", make)
    monkeypatch.setattr(readers.time, "sleep", lambda seconds: None)
    monkeypatch.setenv("LINZ_API_KEY", "linz-key")
    return sessions


def test_a_table_is_read_with_every_column_as_text(fake_table_session):
    """A district code of 060 keeps its leading zero."""
    table = readers.get_koordinates_table(51567)

    assert list(table.columns) == ["title_no", "code"]
    assert table["code"].tolist() == ["060", "007"]


def test_a_table_is_exported_as_csv_with_the_domain_key(fake_table_session):
    readers.get_koordinates_table(51567)

    session = fake_table_session[0]
    assert session.headers["Authorization"] == "key linz-key"
    assert session.posted["formats"] == {"table": "text/csv"}
    assert session.posted["items"][0]["item"].endswith("/tables/51567/")


def test_a_cached_table_is_not_exported_again(fake_table_session):
    readers.get_koordinates_table(51567)
    readers.get_koordinates_table(51567)

    second = fake_table_session[1]
    assert not any(method == "POST" for method, _ in second.requests)


def test_the_table_cache_is_keyed_by_version(fake_table_session, tmp_path):
    readers.get_koordinates_table(51567)

    assert readers.koordinates_table_cache_path(51567, 7).exists()
    assert not readers.koordinates_table_cache_path(51567, 8).exists()


def test_a_failed_table_export_raises(monkeypatch, fake_table_session):
    monkeypatch.setattr(
        readers.requests,
        "Session",
        lambda: FakeTableSession(final_state="cancelled"),
    )

    with pytest.raises(ValueError, match="cancelled"):
        readers.get_koordinates_table(51567, use_cache=False)
