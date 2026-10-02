"""Tests for walking the LINZ elevation STAC catalogue."""

from pathlib import Path

import pytest

from landloss.io import elevation

# A box over Lower Hutt, in WGS84, matching the fake collections below.
HUTT_BBOX = (174.90, -41.25, 174.95, -41.20)


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the catalogue cache out of the working tree during tests."""
    monkeypatch.setenv("KOOPCACHE_DIR", str(tmp_path / "koopcache"))


# --- helpers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ((0, 0, 2, 2), (1, 1, 3, 3), True),
        ((0, 0, 1, 1), (2, 2, 3, 3), False),
        ((0, 0, 1, 1), (1, 1, 2, 2), True),
        ((0, 0, 1, 1), (0.2, 0.2, 0.3, 0.3), True),
    ],
)
def test_overlap_detection(a: tuple, b: tuple, expected: bool) -> None:
    """Boxes overlap when they share any area, including touching at a corner."""
    assert elevation._overlaps(a, b) is expected  # noqa: SLF001


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Wellington LiDAR 1m DEM (2013-2014)", 2014),
        ("Wellington - Hutt City LiDAR 1m DEM (2025)", 2025),
        ("Wellington - Kāpiti Coast LiDAR 1m DEM (2024-2025)", 2025),
    ],
)
def test_survey_year_takes_the_end_of_a_range(title: str, expected: int) -> None:
    """A survey flown over two summers is ordered by the later one."""
    assert elevation._survey_year(title, "") == expected  # noqa: SLF001


def test_survey_year_falls_back_to_the_href() -> None:
    """A collection with no year in its title still sorts, using its path."""
    href = "./wellington/hutt-city_2021/dem_1m/"

    assert elevation._survey_year("", href) == 2021  # noqa: SLF001


# --- caching ------------------------------------------------------------------


def test_a_document_is_cached_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The catalogue is walked once; a second read comes off disk."""
    calls = []

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"id": "x"}

    def fake_get(url: str, timeout: int) -> FakeResponse:
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(elevation.requests, "get", fake_get)

    url = "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/catalog.json"
    first = elevation.fetch_json(url)
    second = elevation.fetch_json(url)

    assert first == second == {"id": "x"}
    assert len(calls) == 1


def test_the_cache_can_be_bypassed(monkeypatch: pytest.MonkeyPatch) -> None:
    """use_cache=False re-reads, so a stale catalogue can be refreshed."""
    calls = []

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict:
            return {"id": "x"}

    monkeypatch.setattr(
        elevation.requests,
        "get",
        lambda url, timeout: (calls.append(url), FakeResponse())[1],
    )

    url = "https://nz-elevation.s3-ap-southeast-2.amazonaws.com/catalog.json"
    elevation.fetch_json(url, use_cache=False)
    elevation.fetch_json(url, use_cache=False)

    assert len(calls) == 2


# --- collection selection -----------------------------------------------------


@pytest.fixture
def fake_catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve a three-collection catalogue: two over Lower Hutt, one over Auckland."""
    root = {
        "links": [
            {
                "rel": "child",
                "href": "./wellington/hutt-city_2021/dem_1m/2193/collection.json",
            },
            {
                "rel": "child",
                "href": "./wellington/hutt-city_2025/dem_1m/2193/collection.json",
            },
            {
                "rel": "child",
                "href": "./wellington/hutt-city_2025/dsm_1m/2193/collection.json",
            },
            {
                "rel": "child",
                "href": (
                    "./auckland/auckland-north_2016-2018/dem_1m/2193/collection.json"
                ),
            },
        ]
    }
    hutt_extent = {"spatial": {"bbox": [[174.80, -41.35, 175.03, -41.09]]}}
    auckland_extent = {"spatial": {"bbox": [[174.40, -37.05, 175.30, -36.10]]}}

    documents = {
        "hutt-city_2021/dem_1m": {
            "id": "c2021",
            "title": "Wellington - Hutt City LiDAR 1m DEM (2021)",
            "extent": hutt_extent,
            "links": [],
        },
        "hutt-city_2025/dem_1m": {
            "id": "c2025",
            "title": "Wellington - Hutt City LiDAR 1m DEM (2025)",
            "extent": hutt_extent,
            "links": [],
        },
        "auckland-north_2016-2018/dem_1m": {
            "id": "cakl",
            "title": "Auckland North LiDAR 1m DEM (2016-2018)",
            "extent": auckland_extent,
            "links": [],
        },
    }

    def fake_fetch(url: str, *, use_cache: bool = True) -> dict:
        if url.endswith("catalog.json"):
            return root
        for key, document in documents.items():
            if key in url:
                return document
        msg = f"unexpected url {url}"
        raise AssertionError(msg)

    monkeypatch.setattr(elevation, "fetch_json", fake_fetch)


def test_only_covering_collections_are_returned(fake_catalogue: None) -> None:
    """A survey whose extent misses the area of interest is skipped."""
    found = elevation.find_dem_collections(HUTT_BBOX)

    assert {c["id"] for c in found} == {"c2021", "c2025"}


def test_collections_come_back_newest_first(fake_catalogue: None) -> None:
    """Later surveys are consulted first, so a point takes its newest elevation."""
    found = elevation.find_dem_collections(HUTT_BBOX)

    assert [c["id"] for c in found] == ["c2025", "c2021"]


def test_surface_models_are_ignored(fake_catalogue: None) -> None:
    """Only bare earth DEM collections are used; a DSM would include buildings."""
    found = elevation.find_dem_collections(HUTT_BBOX)

    assert all("dsm" not in c["url"] for c in found)


# --- sampling guards ----------------------------------------------------------


def test_mismatched_coordinate_arrays_are_rejected() -> None:
    """Sampling needs one northing per easting."""
    with pytest.raises(ValueError, match="same length"):
        elevation.sample_elevation([1.0, 2.0], [1.0])
