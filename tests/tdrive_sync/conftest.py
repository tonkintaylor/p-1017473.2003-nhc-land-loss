"""Shared fixtures for tdrive_sync tests.

Builds a real ``tdrive_sync_config.py`` under ``tmp_path`` rather than mocking
``_config`` internals, and clears ``load_config``'s cache around every test so
the cached result of one test never leaks into the next.
"""

from pathlib import Path

import pytest

from tdrive_sync import _config


@pytest.fixture(autouse=True)
def _reset_config_cache() -> None:
    """Clear the cached config before and after every test."""
    _config.load_config.cache_clear()
    yield
    _config.load_config.cache_clear()


@pytest.fixture
def base_dir(tmp_path: Path) -> Path:
    """A stand-in for T:, as an ordinary directory under tmp_path."""
    path = tmp_path / "t_drive" / "versioned_data"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def source_material_dir(tmp_path: Path) -> Path:
    """A stand-in for T:'s SourceMaterial folder, under tmp_path."""
    path = tmp_path / "t_drive" / "source_material"
    path.mkdir(parents=True)
    return path


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """Where the local cache tiers are written during a test."""
    return tmp_path / "cache"


@pytest.fixture
def project_dir(tmp_path: Path, base_dir: Path, source_material_dir: Path) -> Path:
    """A fake project root with a real tdrive_sync_config.py at its top."""
    root = tmp_path / "project"
    (root / "src" / "scripts").mkdir(parents=True)
    (root / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\n\n"
        f'BASE_DIR = Path(r"{base_dir}")\n'
        'DATA_VERSION = "v1"\n'
        f'SOURCE_MATERIAL_DIR = Path(r"{source_material_dir}")\n'
    )
    return root


@pytest.fixture
def configured(
    project_dir: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Run as if from a script nested under project_dir.

    The config file is found by walking upward from the (changed) working
    directory, and the local cache is pointed at an isolated tmp_path
    directory. Local-only working mode is off unless a test turns it on.

    Returns:
        The fake project root (project_dir), for tests that want to inspect
        or replace its tdrive_sync_config.py.
    """
    monkeypatch.chdir(project_dir / "src" / "scripts")
    monkeypatch.setenv("TTDRIVE_SYNC_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_VERSION", raising=False)
    return project_dir
