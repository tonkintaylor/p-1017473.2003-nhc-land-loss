"""Tests for get_cached: a read-only cache mirror for an arbitrary T: path.

Unlike get_path and get_source_mat, this needs no tdrive_sync_config.py at
all -- the caller supplies the full absolute path itself, so nothing here
touches DATA_VERSION or SOURCE_MATERIAL_DIR. In local-only working mode a
cached copy is used without checking the source.
"""

import time
from pathlib import Path

import pytest

import tdrive_sync as ts


@pytest.fixture(autouse=True)
def _cache_dir_env(cache_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point TTDRIVE_SYNC_CACHE_DIR at an isolated tmp_path directory."""
    monkeypatch.setenv("TTDRIVE_SYNC_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_VERSION", raising=False)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_get_cached_copies_from_the_source_path_and_caches_locally(
    tmp_path: Path,
) -> None:
    """A file only at the given path is copied into the local cache and returned."""
    source = tmp_path / "t_drive" / "other_project" / "data.csv"
    _write(source, "a\n")

    resolved = ts.get_cached(source)

    assert resolved != source
    assert resolved.read_text() == "a\n"


def test_get_cached_reuses_an_up_to_date_cache(tmp_path: Path) -> None:
    """A second call, with nothing changed at the source, does not need to recopy."""
    source = tmp_path / "t_drive" / "data.csv"
    _write(source, "a\n")
    first = ts.get_cached(source)

    second = ts.get_cached(source)

    assert second == first
    assert second.read_text() == "a\n"


def test_get_cached_refreshes_a_stale_cache(tmp_path: Path) -> None:
    """A cache copy that no longer matches the source is refreshed, not trusted."""
    source = tmp_path / "t_drive" / "data.csv"
    _write(source, "a\n")
    ts.get_cached(source)

    time.sleep(0.01)
    source.write_text("b\n")
    resolved = ts.get_cached(source)

    assert resolved.read_text() == "b\n"


def test_get_cached_raises_when_the_file_exists_nowhere(tmp_path: Path) -> None:
    """Resolving a path for a file that exists nowhere fails loudly."""
    with pytest.raises(ValueError, match="Cannot find file"):
        ts.get_cached(tmp_path / "t_drive" / "missing.csv")


def test_get_cached_without_copy_to_local_reads_straight_from_the_source(
    tmp_path: Path,
) -> None:
    """copy_to_local=False resolves the source path without populating the cache."""
    source = tmp_path / "t_drive" / "data.csv"
    _write(source, "a\n")

    resolved = ts.get_cached(source, copy_to_local=False)

    assert resolved == source


def test_get_cached_in_local_mode_fetches_an_uncached_file_from_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In local-only working mode a file with no cached copy still comes from
    the source path."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_VERSION", "scratchpad")
    source = tmp_path / "t_drive" / "data.csv"
    _write(source, "a\n")

    resolved = ts.get_cached(source)

    assert resolved.read_text() == "a\n"


def test_get_cached_local_path_is_where_get_cached_reads_from(tmp_path: Path) -> None:
    """A file written to the named cache path is what get_cached returns."""
    source = tmp_path / "r_drive" / "library" / "data.csv"
    local = ts.get_cached_local_path(source)
    _write(local, "a\n")

    assert ts.get_cached(source, copy_to_local=False) == local


def test_get_cached_in_local_mode_uses_the_cache_without_checking_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In local-only working mode a cached copy is returned even when the
    source holds a newer file, so a fully cached run never touches T:."""
    source = tmp_path / "t_drive" / "data.csv"
    _write(source, "old\n")
    cached = ts.get_cached(source)
    time.sleep(0.05)
    _write(source, "new\n")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_VERSION", "scratchpad")

    resolved = ts.get_cached(source)

    assert resolved == cached
    assert resolved.read_text() == "old\n"
