"""Integration-style tests for tdrive_sync's public API.

Covers local_save, local_read, get_path, get_local_path and get_base_path,
across both local-only working mode and the normal (T:-backed) mode,
including the SCRATCH_VERSION override.
"""

import time
from pathlib import Path

import pandas as pd
import pytest

import tdrive_sync as ts
from tdrive_sync import _config


@pytest.fixture
def some_df() -> pd.DataFrame:
    """A minimal DataFrame, cheap to save/read/compare."""
    return pd.DataFrame({"a": [1, 2, 3]})


# --- normal mode, ordinary DATA_VERSION ----------------------------------------


def test_local_save_writes_to_both_the_cache_and_base_dir(
    configured: Path, base_dir: Path, some_df: pd.DataFrame
) -> None:
    """A save lands on both the local cache mirror and the T: stand-in."""
    ts.local_save(some_df, fname="data.csv", sub_dirs=["vul"], index=False)

    assert (base_dir / "v1" / "vul" / "data.csv").exists()
    assert ts.get_local_path(fname="data.csv", sub_dirs=["vul"]).exists()


def test_local_save_raises_if_the_file_already_exists(
    configured: Path, some_df: pd.DataFrame
) -> None:
    """Saving over an existing file at the normal DATA_VERSION is refused."""
    ts.local_save(some_df, fname="data.csv", index=False)

    with pytest.raises(FileExistsError):
        ts.local_save(some_df, fname="data.csv", index=False)


def test_local_read_returns_what_was_saved(
    configured: Path, some_df: pd.DataFrame
) -> None:
    """A file saved through local_save reads back with the same content."""
    ts.local_save(some_df, fname="data.csv", index=False)

    result = ts.local_read(fname="data.csv")

    pd.testing.assert_frame_equal(result, some_df)


def test_local_read_return_path_does_not_read_the_file(
    configured: Path, some_df: pd.DataFrame
) -> None:
    """return_path=True hands back the resolved path instead of its content."""
    ts.local_save(some_df, fname="data.csv", index=False)

    path = ts.local_read(fname="data.csv", return_path=True)

    assert isinstance(path, Path)
    assert path.exists()


def test_local_read_raises_when_nothing_is_saved(configured: Path) -> None:
    """Reading a file that exists nowhere fails loudly, not with a stack trace
    from deep inside a format reader."""
    with pytest.raises(ValueError, match="Cannot find file"):
        ts.local_read(fname="missing.csv")


def test_get_path_copies_from_base_dir_when_the_cache_is_missing(
    configured: Path, some_df: pd.DataFrame
) -> None:
    """A missing local cache is repopulated from T: rather than left absent."""
    ts.local_save(some_df, fname="data.csv", index=False)
    local_path = ts.get_local_path(fname="data.csv")
    local_path.unlink()

    resolved = ts.get_path(fname="data.csv")

    assert resolved == local_path
    assert local_path.exists()


def test_get_path_refreshes_a_stale_cache(
    configured: Path, some_df: pd.DataFrame
) -> None:
    """A cache copy that no longer matches T: is refreshed, not trusted as-is."""
    ts.local_save(some_df, fname="data.csv", index=False)
    local_path = ts.get_local_path(fname="data.csv")
    base_path = ts.get_base_path(fname="data.csv")
    time.sleep(0.01)
    base_path.write_text(base_path.read_text() + "\n")

    ts.get_path(fname="data.csv")

    assert local_path.read_text() == base_path.read_text()


def test_get_path_raises_when_the_file_exists_nowhere(configured: Path) -> None:
    """Resolving a path for a file that was never saved fails loudly."""
    with pytest.raises(ValueError, match="Cannot find file"):
        ts.get_path(fname="missing.csv")


# --- normal mode, DATA_VERSION == SCRATCH --------------------------------------


@pytest.fixture
def scratch_configured(
    project_dir: Path,
    base_dir: Path,
    source_material_dir: Path,
    cache_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """As configured, but with DATA_VERSION set to the SCRATCH sentinel."""
    (project_dir / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\n\n"
        f'BASE_DIR = Path(r"{base_dir}")\n'
        f'DATA_VERSION = "{_config.SCRATCH_VERSION}"\n'
        f'SOURCE_MATERIAL_DIR = Path(r"{source_material_dir}")\n'
    )
    monkeypatch.chdir(project_dir / "src" / "scripts")
    monkeypatch.setenv("TTDRIVE_SYNC_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)
    return project_dir


def test_scratch_version_overwrites_without_raising(
    scratch_configured: Path, some_df: pd.DataFrame
) -> None:
    """DATA_VERSION == SCRATCH lets a second save replace the first freely."""
    ts.local_save(some_df, fname="data.csv", index=False)
    other = pd.DataFrame({"a": [9]})

    ts.local_save(other, fname="data.csv", index=False)

    result = ts.local_read(fname="data.csv")
    pd.testing.assert_frame_equal(result, other)


# --- local-only working mode ---------------------------------------------------


@pytest.fixture
def local_mode_configured(configured: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """As configured, but with TTDRIVE_SYNC_LOCAL_MODE switched on."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_VERSION", "scratchpad")
    return configured


def test_local_mode_save_never_touches_base_dir(
    local_mode_configured: Path, base_dir: Path, some_df: pd.DataFrame
) -> None:
    """A save in local mode leaves the T: stand-in completely untouched."""
    ts.local_save(some_df, fname="data.csv", index=False)

    assert not any(base_dir.rglob("*"))


def test_local_mode_save_always_overwrites(
    local_mode_configured: Path, some_df: pd.DataFrame
) -> None:
    """Local mode never raises on an existing file -- it is disposable by design."""
    ts.local_save(some_df, fname="data.csv", index=False)
    other = pd.DataFrame({"a": [9]})

    ts.local_save(other, fname="data.csv", index=False)

    result = ts.local_read(fname="data.csv")
    pd.testing.assert_frame_equal(result, other)


def test_local_mode_read_prefers_the_local_version_tier(
    local_mode_configured: Path, some_df: pd.DataFrame
) -> None:
    """A file saved in local mode is read back from the local-version tier."""
    ts.local_save(some_df, fname="data.csv", index=False)

    result = ts.local_read(fname="data.csv")

    pd.testing.assert_frame_equal(result, some_df)


def test_local_mode_read_falls_back_to_the_data_version_cache(
    local_mode_configured: Path, some_df: pd.DataFrame
) -> None:
    """With nothing in the local-version tier, the DATA_VERSION cache is used."""
    data_version_path = ts.get_local_path(fname="data.csv")
    data_version_path.parent.mkdir(parents=True, exist_ok=True)
    some_df.to_csv(data_version_path, index=False)

    result = ts.local_read(fname="data.csv")

    pd.testing.assert_frame_equal(result, some_df)


def test_local_mode_read_falls_back_to_base_dir_and_populates_the_cache(
    local_mode_configured: Path, base_dir: Path, some_df: pd.DataFrame
) -> None:
    """With nothing cached locally at all, T: is read and the cache is filled."""
    base_path = base_dir / "v1" / "data.csv"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    some_df.to_csv(base_path, index=False)

    result = ts.local_read(fname="data.csv")

    pd.testing.assert_frame_equal(result, some_df)
    assert ts.get_local_path(fname="data.csv").exists()


def test_local_mode_read_raises_when_nothing_is_saved(
    local_mode_configured: Path,
) -> None:
    """Local mode still fails loudly rather than silently return nothing."""
    with pytest.raises(ValueError, match="Cannot find file"):
        ts.local_read(fname="missing.csv")
