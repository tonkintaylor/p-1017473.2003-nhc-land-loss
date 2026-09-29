"""Generic helpers for a shared, versioned T: drive data store.

``tdrive_sync`` resolves reads and writes across up to three tiers:

1. T:, the shared network drive, under the project's configured
   ``DATA_VERSION`` (from ``tdrive_sync_config.py`` at the project root).
2. A local cache mirroring T:, under the same ``DATA_VERSION``.
3. A purely local, disposable working area, under
   ``TTDRIVE_SYNC_LOCAL_VERSION`` (from the environment), used only when
   ``TTDRIVE_SYNC_LOCAL_MODE=True``.

It also offers ``get_source_mat``, a read-only, unversioned counterpart for
fetching a file from the project's ``SOURCE_MATERIAL_DIR`` (data supplied by
someone else, e.g. NHC) and caching it locally -- there is no corresponding
save, and local-only working mode does not apply to it.

``get_cached`` is the same read-only, cache-locally behaviour for an arbitrary
absolute T: path -- for a caller with its own release tree elsewhere on T:
(e.g. another project's upstream data) that has no reason to go through
``tdrive_sync_config.py`` at all.

See the project's README for the full behaviour of each environment
variable, and ``tdrive_sync_config.py`` for the project-wide settings.
"""

from pathlib import Path
from typing import Any

from tdrive_sync import _config, _copy, _formats, _paths
from tdrive_sync._config import SCRATCH_VERSION, TdriveSyncConfigError
from tdrive_sync._paths import (
    get_base_path,
    get_cached,
    get_cached_local_path,
    get_local_path,
    get_path,
    get_source_mat,
    get_source_mat_base_path,
    get_source_mat_local_path,
)

__all__ = [
    "SCRATCH_VERSION",
    "TdriveSyncConfigError",
    "get_base_path",
    "get_cached",
    "get_cached_local_path",
    "get_local_path",
    "get_path",
    "get_source_mat",
    "get_source_mat_base_path",
    "get_source_mat_local_path",
    "local_read",
    "local_save",
]


def local_save(
    obj: Any, *, fname: str, sub_dirs: list[str] | None = None, **kwargs: Any
) -> None:
    """Save ``obj`` under the project's configured T: base directory.

    In local-only working mode (``TTDRIVE_SYNC_LOCAL_MODE=True``), this saves
    only to the local ``TTDRIVE_SYNC_LOCAL_VERSION`` cache and always
    overwrites -- T: is never touched.

    Otherwise, this saves under the configured ``DATA_VERSION``, on both T:
    and its local cache mirror. It refuses to overwrite a file that already
    exists there, unless ``DATA_VERSION`` is set to
    ``tdrive_sync.SCRATCH_VERSION``, in which case it always overwrites.

    Args:
        obj: The object to save (a GeoDataFrame, DataFrame, DataArray, dict,
            or any picklable object, depending on ``fname``'s suffix).
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to save under.
        **kwargs: Passed through to the underlying save function.

    Raises:
        FileExistsError: If the file already exists and ``DATA_VERSION`` is
            not ``tdrive_sync.SCRATCH_VERSION``.
    """
    sub_dirs = sub_dirs or []
    config = _config.load_config()
    settings = _config.load_local_mode_settings()

    if settings.enabled:
        path = _paths.local_version_cache_path(
            config, settings, fname=fname, sub_dirs=sub_dirs
        )
        _formats.save(obj, path, **kwargs)
        return

    local_path = _paths.get_local_path(fname=fname, sub_dirs=sub_dirs)
    base_path = _paths.get_base_path(fname=fname, sub_dirs=sub_dirs)

    if config.data_version != SCRATCH_VERSION and (
        local_path.exists() or base_path.exists()
    ):
        msg = (
            f"{base_path} already exists. Bump DATA_VERSION in "
            f'tdrive_sync_config.py, or set it to "{SCRATCH_VERSION}" to '
            f"overwrite freely."
        )
        raise FileExistsError(msg)

    _formats.save(obj, local_path, **kwargs)
    _copy.copy_to(src_path=local_path, dst_path=base_path)


def _resolve_local_mode_read_path(
    config: _config.TdriveSyncConfig,
    settings: _config.LocalModeSettings,
    *,
    fname: str,
    sub_dirs: list[str],
    copy_to_local: bool,
) -> Path:
    """Resolve a read path in local-only working mode.

    Checks the local ``TTDRIVE_SYNC_LOCAL_VERSION`` cache, then the local
    ``DATA_VERSION`` cache, then finally T: -- never checking T: for
    staleness, so local mode never touches the network unless nothing at all
    is cached yet.
    """
    local_version_path = _paths.local_version_cache_path(
        config, settings, fname=fname, sub_dirs=sub_dirs
    )
    if local_version_path.exists():
        return local_version_path

    data_version_path = _paths.get_local_path(fname=fname, sub_dirs=sub_dirs)
    if data_version_path.exists():
        return data_version_path

    base_path = _paths.get_base_path(fname=fname, sub_dirs=sub_dirs)
    if not base_path.exists():
        msg = f"Cannot find file: {base_path}"
        raise ValueError(msg)

    if copy_to_local:
        _copy.copy_to(src_path=base_path, dst_path=data_version_path)
        return data_version_path

    return base_path


def local_read(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file saved under the project's configured T: base directory.

    In local-only working mode (``TTDRIVE_SYNC_LOCAL_MODE=True``), this looks
    first in the local ``TTDRIVE_SYNC_LOCAL_VERSION`` cache, then in the local
    ``DATA_VERSION`` cache, then falls back to T: (populating the
    ``DATA_VERSION`` cache as it does).

    Otherwise, this resolves the same as the National Liquefaction Model's
    ``get_path``: the local ``DATA_VERSION`` cache if present and up to date
    with T:, refreshing it from T: first if it is missing or stale.

    Args:
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to read from.
        copy_to_local: Whether a fallback read from T: populates the local
            cache. In local-only working mode this only affects the final T:
            fallback tier; the two local tiers are always preferred as-is.
        return_path: If True, return the resolved path instead of reading it.
        **kwargs: Passed through to the underlying read function.

    Returns:
        The file's content, or its resolved path if ``return_path`` is True.

    Raises:
        ValueError: If the file cannot be found in any location it could be
            read from.
    """
    sub_dirs = sub_dirs or []
    config = _config.load_config()
    settings = _config.load_local_mode_settings()

    if settings.enabled:
        path = _resolve_local_mode_read_path(
            config,
            settings,
            fname=fname,
            sub_dirs=sub_dirs,
            copy_to_local=copy_to_local,
        )
    else:
        path = get_path(fname=fname, sub_dirs=sub_dirs, copy_to_local=copy_to_local)

    if return_path:
        return path

    try:
        return _formats.read(path, **kwargs)
    except FileNotFoundError as err:
        msg = f"Cannot find file: {path}"
        raise ValueError(msg) from err
