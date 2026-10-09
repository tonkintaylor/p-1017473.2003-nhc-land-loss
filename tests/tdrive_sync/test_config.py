"""Tests for config discovery/loading, and TTDRIVE_SYNC_* env var parsing."""

from pathlib import Path

import pytest

from tdrive_sync import _config

# --- find_config_file ---------------------------------------------------------


def test_find_config_file_walks_up_from_a_nested_directory(project_dir: Path) -> None:
    """A script run from deep inside the project still finds the root config."""
    nested = project_dir / "src" / "scripts"

    found = _config.find_config_file(nested)

    assert found == project_dir / _config.CONFIG_FILENAME


def test_find_config_file_raises_when_none_exists(tmp_path: Path) -> None:
    """A project with no config file fails loudly, not silently."""
    lonely = tmp_path / "nowhere"
    lonely.mkdir()

    with pytest.raises(_config.TdriveSyncConfigError, match="Could not find"):
        _config.find_config_file(lonely)


# --- load_config ---------------------------------------------------------------


def test_load_config_reads_base_dir_and_data_version(
    configured: Path, base_dir: Path, source_material_dir: Path
) -> None:
    """A valid config file loads with the expected values."""
    config = _config.load_config()

    assert config.base_dir == base_dir
    assert config.data_version == "v1"
    assert config.source_material_dir == source_material_dir


def test_load_config_raises_when_no_config_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Running outside any configured project fails loudly."""
    lonely = tmp_path / "nowhere"
    lonely.mkdir()
    monkeypatch.chdir(lonely)

    with pytest.raises(_config.TdriveSyncConfigError, match="Could not find"):
        _config.load_config()


def test_load_config_raises_for_a_non_path_base_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong-typed BASE_DIR is rejected rather than used as-is."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / _config.CONFIG_FILENAME).write_text(
        'BASE_DIR = "not-a-path"\nDATA_VERSION = "v1"\n'
    )

    with pytest.raises(_config.TdriveSyncConfigError, match="BASE_DIR"):
        _config.load_config()


def test_load_config_raises_for_a_missing_data_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config file missing DATA_VERSION is rejected rather than defaulted."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\nBASE_DIR = Path('base')\n"
    )

    with pytest.raises(_config.TdriveSyncConfigError, match="DATA_VERSION"):
        _config.load_config()


def test_load_config_raises_for_an_empty_data_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty DATA_VERSION string is rejected rather than treated as unset."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\nBASE_DIR = Path('base')\nDATA_VERSION = ''\n"
    )

    with pytest.raises(_config.TdriveSyncConfigError, match="DATA_VERSION"):
        _config.load_config()


def test_load_config_raises_for_a_missing_source_material_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A config file missing SOURCE_MATERIAL_DIR is rejected rather than defaulted."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\nBASE_DIR = Path('base')\nDATA_VERSION = \"v1\"\n"
    )

    with pytest.raises(_config.TdriveSyncConfigError, match="SOURCE_MATERIAL_DIR"):
        _config.load_config()


def test_load_config_raises_for_a_non_path_source_material_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong-typed SOURCE_MATERIAL_DIR is rejected rather than used as-is."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / _config.CONFIG_FILENAME).write_text(
        "from pathlib import Path\n"
        "BASE_DIR = Path('base')\n"
        'DATA_VERSION = "v1"\n'
        'SOURCE_MATERIAL_DIR = "not-a-path"\n'
    )

    with pytest.raises(_config.TdriveSyncConfigError, match="SOURCE_MATERIAL_DIR"):
        _config.load_config()


# --- load_local_mode_settings --------------------------------------------------


def test_local_mode_defaults_to_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no TTDRIVE_SYNC_LOCAL_MODE set, local-only working mode is off."""
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_MODE", raising=False)

    settings = _config.load_local_mode_settings()

    assert settings.enabled is False


def test_local_mode_on_requires_a_local_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turning local mode on without a version to use fails loudly."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.delenv("TTDRIVE_SYNC_LOCAL_VERSION", raising=False)

    with pytest.raises(ValueError, match="TTDRIVE_SYNC_LOCAL_VERSION"):
        _config.load_local_mode_settings()


def test_local_mode_on_with_a_version_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local mode with both variables set loads without error."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "True")
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_VERSION", "scratchpad")

    settings = _config.load_local_mode_settings()

    assert settings.enabled is True
    assert settings.local_version == "scratchpad"


def test_an_invalid_bool_value_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-"True"/"False" value for a boolean env var fails loudly."""
    monkeypatch.setenv("TTDRIVE_SYNC_LOCAL_MODE", "yes")

    with pytest.raises(ValueError, match="TTDRIVE_SYNC_LOCAL_MODE"):
        _config.load_local_mode_settings()


def test_cache_dir_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no TTDRIVE_SYNC_CACHE_DIR set, the default cache directory is used."""
    monkeypatch.delenv("TTDRIVE_SYNC_CACHE_DIR", raising=False)

    settings = _config.load_local_mode_settings()

    assert settings.cache_dir == _config.DEFAULT_CACHE_DIR
