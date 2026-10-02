"""Config discovery and loading for tdrive_sync.

Locates this project's ``tdrive_sync_config.py``, and reads the
``TTDRIVE_SYNC_*`` environment variables that control local-only working mode.
"""

import functools
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import dotenv

dotenv.load_dotenv()

CONFIG_FILENAME = "tdrive_sync_config.py"
DEFAULT_CACHE_DIR = Path(".tdrivecache")

# A DATA_VERSION of this value lets local_save overwrite an existing file on
# T: instead of raising -- see tdrive_sync_config.py.
SCRATCH_VERSION = "SCRATCH"

_BOOL_VALUES = {"True": True, "False": False}


class TdriveSyncConfigError(RuntimeError):
    """Raised when tdrive_sync_config.py cannot be found or is invalid."""


@dataclass(frozen=True)
class TdriveSyncConfig:
    """The project-wide settings read from tdrive_sync_config.py."""

    base_dir: Path
    data_version: str
    source_material_dir: Path


@dataclass(frozen=True)
class LocalModeSettings:
    """The TTDRIVE_SYNC_* environment settings for local-only working mode."""

    enabled: bool
    local_version: str | None
    cache_dir: Path


def find_config_file(start_dir: Path) -> Path:
    """Walk upward from ``start_dir`` looking for ``tdrive_sync_config.py``.

    Args:
        start_dir: Where to start the search, typically the current working
            directory.

    Returns:
        The path to the config file.

    Raises:
        TdriveSyncConfigError: If no config file is found by the filesystem
            root.
    """
    resolved = start_dir.resolve()
    for directory in (resolved, *resolved.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate

    msg = (
        f"Could not find {CONFIG_FILENAME} in {start_dir} or any parent "
        f"directory. Create one at the project root defining BASE_DIR (a "
        f"pathlib.Path), DATA_VERSION (a str) and SOURCE_MATERIAL_DIR (a "
        f"pathlib.Path)."
    )
    raise TdriveSyncConfigError(msg)


def _load_config_module(path: Path) -> ModuleType:
    """Load ``path`` as a Python module, without needing it on sys.path."""
    spec = importlib.util.spec_from_file_location("tdrive_sync_config", path)
    if spec is None or spec.loader is None:
        msg = f"Could not load {path} as a Python module."
        raise TdriveSyncConfigError(msg)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@functools.lru_cache
def load_config() -> TdriveSyncConfig:
    """Find, load and validate this project's tdrive_sync_config.py.

    The search starts from the current working directory, so scripts and
    tests must be run from inside the project (the existing convention for
    this repo). The result is cached; tests that change the working directory
    must call ``load_config.cache_clear()`` first.

    Returns:
        The loaded config.

    Raises:
        TdriveSyncConfigError: If the file cannot be found, or does not
            define valid BASE_DIR/DATA_VERSION/SOURCE_MATERIAL_DIR attributes.
    """
    path = find_config_file(Path.cwd())
    module = _load_config_module(path)

    base_dir = getattr(module, "BASE_DIR", None)
    data_version = getattr(module, "DATA_VERSION", None)
    source_material_dir = getattr(module, "SOURCE_MATERIAL_DIR", None)

    if not isinstance(base_dir, Path):
        msg = f"BASE_DIR in {path} must be a pathlib.Path, got {base_dir!r}."
        raise TdriveSyncConfigError(msg)
    if not isinstance(data_version, str) or not data_version:
        msg = f"DATA_VERSION in {path} must be a non-empty str, got {data_version!r}."
        raise TdriveSyncConfigError(msg)
    if not isinstance(source_material_dir, Path):
        msg = (
            f"SOURCE_MATERIAL_DIR in {path} must be a pathlib.Path, got "
            f"{source_material_dir!r}."
        )
        raise TdriveSyncConfigError(msg)

    return TdriveSyncConfig(
        base_dir=base_dir,
        data_version=data_version,
        source_material_dir=source_material_dir,
    )


def _parse_bool(value: str, *, var_name: str) -> bool:
    """Parse a strict "True"/"False" environment variable value."""
    try:
        return _BOOL_VALUES[value]
    except KeyError:
        msg = f'{var_name} must be "True" or "False", got {value!r}.'
        raise ValueError(msg) from None


def load_local_mode_settings() -> LocalModeSettings:
    """Read the TTDRIVE_SYNC_* environment variables.

    Returns:
        The local-mode settings for this process.

    Raises:
        ValueError: If TTDRIVE_SYNC_LOCAL_MODE is True but
            TTDRIVE_SYNC_LOCAL_VERSION is not set, or either boolean variable
            is set to something other than "True"/"False".
    """
    enabled = _parse_bool(
        os.environ.get("TTDRIVE_SYNC_LOCAL_MODE", "False"),
        var_name="TTDRIVE_SYNC_LOCAL_MODE",
    )
    local_version = os.environ.get("TTDRIVE_SYNC_LOCAL_VERSION") or None
    cache_dir = Path(os.environ.get("TTDRIVE_SYNC_CACHE_DIR", str(DEFAULT_CACHE_DIR)))

    if enabled and local_version is None:
        msg = (
            "TTDRIVE_SYNC_LOCAL_VERSION must be set when "
            "TTDRIVE_SYNC_LOCAL_MODE is True."
        )
        raise ValueError(msg)

    return LocalModeSettings(
        enabled=enabled, local_version=local_version, cache_dir=cache_dir
    )
