"""Tests for the vector dataset readers."""

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point, Polygon

from landloss.domain import constants
from landloss.io import readers
from landloss.io.area_of_interest import SMALL_WLG_PILOT
from landloss.io.readers import (
    get_gns_slide_morphology,
    get_gwrc_slope_failure,
    get_koordinates_layer_extent,
    get_nz_addresses,
    get_nz_land_cover,
    get_nz_river_name_lines,
    get_slide_interpreted_materials,
    get_wcc_cut_areas,
    get_wcc_fill_areas,
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
