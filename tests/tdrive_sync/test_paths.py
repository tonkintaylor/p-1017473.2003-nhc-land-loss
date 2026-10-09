"""Tests for tdrive_sync's local cache directory anchoring."""

from pathlib import Path

import pytest

from tdrive_sync import _paths


def test_default_cache_dir_is_anchored_to_the_project_root(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unset TTDRIVE_SYNC_CACHE_DIR must not scatter under the working directory.

    Scripts and IDE run configurations start from many different working
    directories under the project. If the default cache dir were left
    relative to the current working directory, each one would get its own
    ".tdrivecache" instead of sharing the one at the project root.
    """
    monkeypatch.chdir(project_dir / "src" / "scripts")
    monkeypatch.delenv("TTDRIVE_SYNC_CACHE_DIR", raising=False)
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)

    local_path = _paths.get_local_path(fname="thing.csv")

    assert local_path.is_relative_to(project_dir / ".tdrivecache")


def test_an_absolute_cache_dir_is_used_as_given(
    project_dir: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit absolute TTDRIVE_SYNC_CACHE_DIR is not re-anchored."""
    monkeypatch.chdir(project_dir / "src" / "scripts")
    monkeypatch.setenv("TTDRIVE_SYNC_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)

    local_path = _paths.get_local_path(fname="thing.csv")

    assert local_path.is_relative_to(cache_dir)
