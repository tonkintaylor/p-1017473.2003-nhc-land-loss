"""Path construction for tdrive_sync's storage tiers.

Resolves between T: (the shared drive), the DATA_VERSION local cache (a
mirror of T:), and the TTDRIVE_SYNC_LOCAL_VERSION local cache (a purely local
working area).
"""

from pathlib import Path

from tdrive_sync import _config, _copy


def _cache_root(settings: _config.LocalModeSettings) -> Path:
    """Anchor a relative TTDRIVE_SYNC_CACHE_DIR to the project root.

    A relative cache dir must not be resolved against the current working
    directory: scripts and IDE run configurations start from many different
    directories, and a bare ".tdrivecache" would then scatter a separate copy
    under each one instead of sharing the one cache. An absolute
    TTDRIVE_SYNC_CACHE_DIR is used exactly as given.

    Args:
        settings: The loaded TTDRIVE_SYNC_* environment settings.

    Returns:
        The cache directory, absolute.
    """
    if settings.cache_dir.is_absolute():
        return settings.cache_dir
    return _config.find_config_file(Path.cwd()).parent / settings.cache_dir


def _relative_base_dir(base_dir: Path) -> Path:
    """Strip the drive/UNC anchor so the local cache mirrors base_dir's layout."""
    parts = base_dir.parts
    return Path(*parts[1:]) if len(parts) > 1 else Path()


def get_base_path(*, fname: str, sub_dirs: list[str] | None = None) -> Path:
    """Return the T: path for a file, ignoring local-only working mode.

    Args:
        fname: The file's name.
        sub_dirs: Subdirectories under the configured DATA_VERSION.

    Returns:
        The path on T:.
    """
    config = _config.load_config()
    return config.base_dir / config.data_version / Path(*(sub_dirs or [])) / fname


def get_local_path(*, fname: str, sub_dirs: list[str] | None = None) -> Path:
    """Return the local cache mirror of get_base_path, ignoring local-only mode.

    Args:
        fname: The file's name.
        sub_dirs: Subdirectories under the configured DATA_VERSION.

    Returns:
        The path in the local cache, under the configured DATA_VERSION.
    """
    config = _config.load_config()
    settings = _config.load_local_mode_settings()
    return (
        _cache_root(settings)
        / _relative_base_dir(config.base_dir)
        / config.data_version
        / Path(*(sub_dirs or []))
        / fname
    )


def local_version_cache_path(
    config: _config.TdriveSyncConfig,
    settings: _config.LocalModeSettings,
    *,
    fname: str,
    sub_dirs: list[str],
) -> Path:
    """Return the purely-local path for a file, under TTDRIVE_SYNC_LOCAL_VERSION.

    Args:
        config: The loaded tdrive_sync_config.py settings.
        settings: The loaded TTDRIVE_SYNC_* environment settings.
        fname: The file's name.
        sub_dirs: Subdirectories under the local version.

    Returns:
        The path in the local cache, under TTDRIVE_SYNC_LOCAL_VERSION.

    Raises:
        ValueError: If TTDRIVE_SYNC_LOCAL_VERSION is not set.
    """
    if settings.local_version is None:
        msg = "TTDRIVE_SYNC_LOCAL_VERSION must be set to resolve a local-mode path."
        raise ValueError(msg)

    return (
        _cache_root(settings)
        / _relative_base_dir(config.base_dir)
        / settings.local_version
        / Path(*sub_dirs)
        / fname
    )


def _resolve_cached_path(
    *, base_path: Path, local_path: Path, copy_to_local: bool
) -> Path:
    """Resolve a path against a local cache mirror, refreshing it if needed.

    Shared by ``get_path`` (the DATA_VERSION store) and ``get_source_mat``
    (SourceMaterial) -- both cache a T: file locally the same way, just under
    a different base/local pair.

    Args:
        base_path: The T: path.
        local_path: Its local cache mirror.
        copy_to_local: Whether to refresh the local cache from T: when it is
            missing or stale.

    Returns:
        The resolved path: the local cache copy if it exists (and, if
        ``copy_to_local``, is now up to date), otherwise the T: path.

    Raises:
        ValueError: If the file exists at neither location.
    """
    if copy_to_local and base_path.exists() and not local_path.exists():
        _copy.copy_to(src_path=base_path, dst_path=local_path)

    if not base_path.exists():
        if local_path.exists():
            return local_path
        msg = f"Cannot find file: {base_path}"
        raise ValueError(msg)

    if not local_path.exists():
        return base_path

    stat_local = local_path.stat()
    stat_base = base_path.stat()
    matches = (
        stat_local.st_size == stat_base.st_size
        and stat_local.st_mtime == stat_base.st_mtime
        and stat_local.st_mode == stat_base.st_mode
    )
    if not matches and copy_to_local:
        _copy.copy_to(src_path=base_path, dst_path=local_path)

    return local_path


def get_path(
    *, fname: str, sub_dirs: list[str] | None = None, copy_to_local: bool = True
) -> Path:
    """Resolve the path to read a file from, refreshing the local cache if needed.

    Ignores local-only working mode -- this is the "normal", DATA_VERSION-only
    resolution, ported from the National Liquefaction Model's ``get_path``.

    Args:
        fname: The file's name.
        sub_dirs: Subdirectories under the configured DATA_VERSION.
        copy_to_local: Whether to refresh the local cache from T: when it is
            missing or stale.

    Returns:
        The resolved path: the local cache copy if it exists (and, if
        ``copy_to_local``, is now up to date), otherwise the T: path.

    Raises:
        ValueError: If the file exists at neither location.
    """
    local_path = get_local_path(fname=fname, sub_dirs=sub_dirs)
    base_path = get_base_path(fname=fname, sub_dirs=sub_dirs)
    return _resolve_cached_path(
        base_path=base_path, local_path=local_path, copy_to_local=copy_to_local
    )


def get_source_mat_base_path(relative_path: str | Path) -> Path:
    """Return the T: path for a file under the configured SOURCE_MATERIAL_DIR.

    Path construction only: nothing here touches the drive, which is what makes
    it usable from a machine that cannot reach T: at all. A caller that wants
    the file itself wants :func:`get_source_mat`.

    Args:
        relative_path: The file's path, relative to SOURCE_MATERIAL_DIR.

    Returns:
        The path the file has on T:, whether or not it is there.
    """
    config = _config.load_config()
    return config.source_material_dir / relative_path


def get_source_mat_local_path(relative_path: str | Path) -> Path:
    """Return the local cache mirror of :func:`get_source_mat_base_path`.

    Path construction only, and the counterpart to it: between them a caller
    can name both sides of the cache without resolving either, which is what
    writing a file path into a document rather than reading the file needs.

    Args:
        relative_path: The file's path, relative to SOURCE_MATERIAL_DIR.

    Returns:
        The path the file has in the local cache, whether or not it is there.
    """
    config = _config.load_config()
    settings = _config.load_local_mode_settings()
    return (
        _cache_root(settings)
        / _relative_base_dir(config.source_material_dir)
        / relative_path
    )


def get_source_mat(relative_path: str | Path, *, copy_to_local: bool = True) -> Path:
    """Resolve the path to a file under the configured SOURCE_MATERIAL_DIR.

    SourceMaterial holds data supplied by someone else -- NHC, another team --
    rather than anything this project generates, so unlike ``get_path`` there
    is no DATA_VERSION and no save side: this only ever fetches from T: and
    caches locally, ignoring local-only working mode (there is no local,
    disposable stand-in for someone else's source data).

    Args:
        relative_path: The file's path, relative to SOURCE_MATERIAL_DIR (e.g.
            ``"CHC-loss-data-from-NHC/loss.csv"``).
        copy_to_local: Whether to refresh the local cache from T: when it is
            missing or stale.

    Returns:
        The resolved path: the local cache copy if it exists (and, if
        ``copy_to_local``, is now up to date), otherwise the T: path.

    Raises:
        ValueError: If the file exists at neither location.
    """
    base_path = get_source_mat_base_path(relative_path)
    local_path = get_source_mat_local_path(relative_path)
    return _resolve_cached_path(
        base_path=base_path, local_path=local_path, copy_to_local=copy_to_local
    )


def get_cached_local_path(path: Path) -> Path:
    """Return the local cache mirror of an arbitrary absolute path.

    Path construction only, the counterpart to :func:`get_cached` as
    :func:`get_source_mat_local_path` is to :func:`get_source_mat`: for a
    caller that writes a file into the cache itself, ahead of the file being
    placed at ``path``, so that ``get_cached`` then finds it.

    Args:
        path: The absolute path, anywhere on a network drive.

    Returns:
        The path the file has in the local cache, whether or not it is there.
    """
    settings = _config.load_local_mode_settings()
    return _cache_root(settings) / _relative_base_dir(path)


def get_cached(path: Path, *, copy_to_local: bool = True) -> Path:
    """Resolve an arbitrary T: path against its local cache mirror.

    For a caller with its own absolute T: path -- outside both the
    DATA_VERSION store and SOURCE_MATERIAL_DIR, e.g. another project's own
    versioned release tree -- that wants the same "local cache mirrors T:,
    refresh if stale" behaviour as ``get_path`` and ``get_source_mat``,
    without adding another concept to ``tdrive_sync_config.py``. Like
    ``get_source_mat``, there is no save side and no local-only working mode
    fallback: this only ever fetches from T: and caches locally.

    Args:
        path: The absolute path to read, anywhere on T:.
        copy_to_local: Whether to refresh the local cache from T: when it is
            missing or stale.

    Returns:
        The resolved path: the local cache copy if it exists (and, if
        ``copy_to_local``, is now up to date), otherwise ``path`` itself.

    Raises:
        ValueError: If the file exists at neither location.
    """
    return _resolve_cached_path(
        base_path=path,
        local_path=get_cached_local_path(path),
        copy_to_local=copy_to_local,
    )
