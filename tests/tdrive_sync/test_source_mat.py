"""Tests for get_source_mat: a read-only, unversioned SourceMaterial fetch.

Unlike the DATA_VERSION store, there is no save side and no local-only working
mode to consider -- these tests only cover fetching from the SOURCE_MATERIAL_DIR
stand-in and caching locally.
"""

import time
from pathlib import Path

import pytest

import tdrive_sync as ts


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_get_source_mat_copies_from_t_and_caches_locally(
    configured: Path, source_material_dir: Path
) -> None:
    """A file only on the T: stand-in is copied into the local cache and returned."""
    _write(source_material_dir / "nhc" / "loss.csv", "qpid\n1\n")

    resolved = ts.get_source_mat("nhc/loss.csv")

    assert resolved.read_text() == "qpid\n1\n"
    assert resolved != source_material_dir / "nhc" / "loss.csv"
    assert resolved.exists()


def test_get_source_mat_reuses_an_up_to_date_cache(
    configured: Path, source_material_dir: Path
) -> None:
    """A second call, with nothing changed on T:, does not need to recopy."""
    _write(source_material_dir / "loss.csv", "a\n")
    first = ts.get_source_mat("loss.csv")

    second = ts.get_source_mat("loss.csv")

    assert second == first
    assert second.read_text() == "a\n"


def test_get_source_mat_refreshes_a_stale_cache(
    configured: Path, source_material_dir: Path
) -> None:
    """A cache copy that no longer matches T: is refreshed, not trusted as-is."""
    base_path = source_material_dir / "loss.csv"
    _write(base_path, "a\n")
    ts.get_source_mat("loss.csv")

    time.sleep(0.01)
    base_path.write_text("b\n")
    resolved = ts.get_source_mat("loss.csv")

    assert resolved.read_text() == "b\n"


def test_get_source_mat_raises_when_the_file_exists_nowhere(configured: Path) -> None:
    """Resolving a path for a file that was never supplied fails loudly."""
    with pytest.raises(ValueError, match="Cannot find file"):
        ts.get_source_mat("missing.csv")


def test_get_source_mat_without_copy_to_local_reads_straight_from_t(
    configured: Path, source_material_dir: Path
) -> None:
    """copy_to_local=False resolves T:'s path without populating the cache."""
    base_path = source_material_dir / "loss.csv"
    _write(base_path, "a\n")

    resolved = ts.get_source_mat("loss.csv", copy_to_local=False)

    assert resolved == base_path


def test_get_source_mat_ignores_local_only_working_mode(
    configured: Path, source_material_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local-only working mode has no bearing on SourceMaterial -- it still
    fetches from and caches against the T: stand-in."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_VERSION", "scratchpad")
    _write(source_material_dir / "loss.csv", "a\n")

    resolved = ts.get_source_mat("loss.csv")

    assert resolved.read_text() == "a\n"
