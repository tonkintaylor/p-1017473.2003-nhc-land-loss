"""Save/read helpers for this project's own versioned data.

Each of hazard, exposure, vul and loss gets its own area under
``tdrive_sync``'s configured ``BASE_DIR``/``DATA_VERSION``, so the four
modules can share one shared T: version without colliding on file names. See
the project README for how ``DATA_VERSION`` and local-only working mode are
configured.
"""

from typing import Any

import tdrive_sync as ts


def _save(
    module: str,
    obj: Any,
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    **kwargs: Any,
) -> None:
    """Save obj under module's area of the versioned data store."""
    ts.local_save(obj, fname=fname, sub_dirs=[module, *(sub_dirs or [])], **kwargs)


def _read(
    module: str,
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file from module's area of the versioned data store."""
    return ts.local_read(
        fname=fname,
        sub_dirs=[module, *(sub_dirs or [])],
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )


def save_hazard(
    obj: Any, *, fname: str, sub_dirs: list[str] | None = None, **kwargs: Any
) -> None:
    """Save obj under the hazard module's area of the versioned data store.

    Args:
        obj: The object to save (a GeoDataFrame, DataFrame, DataArray, dict,
            or any picklable object, depending on ``fname``'s suffix).
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to save under, within the hazard area.
        **kwargs: Passed through to ``tdrive_sync.local_save``.
    """
    _save("hazard", obj, fname=fname, sub_dirs=sub_dirs, **kwargs)


def read_hazard(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file from the hazard module's area of the versioned data store.

    Args:
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to read from, within the hazard area.
        copy_to_local: Passed through to ``tdrive_sync.local_read``.
        return_path: If True, return the resolved path instead of reading it.
        **kwargs: Passed through to ``tdrive_sync.local_read``.

    Returns:
        The file's content, or its resolved path if ``return_path`` is True.
    """
    return _read(
        "hazard",
        fname=fname,
        sub_dirs=sub_dirs,
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )


def save_exposure(
    obj: Any, *, fname: str, sub_dirs: list[str] | None = None, **kwargs: Any
) -> None:
    """Save obj under the exposure module's area of the versioned data store.

    Args:
        obj: The object to save (a GeoDataFrame, DataFrame, DataArray, dict,
            or any picklable object, depending on ``fname``'s suffix).
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to save under, within the exposure area.
        **kwargs: Passed through to ``tdrive_sync.local_save``.
    """
    _save("exposure", obj, fname=fname, sub_dirs=sub_dirs, **kwargs)


def read_exposure(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file from the exposure module's area of the versioned data store.

    Args:
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to read from, within the exposure area.
        copy_to_local: Passed through to ``tdrive_sync.local_read``.
        return_path: If True, return the resolved path instead of reading it.
        **kwargs: Passed through to ``tdrive_sync.local_read``.

    Returns:
        The file's content, or its resolved path if ``return_path`` is True.
    """
    return _read(
        "exposure",
        fname=fname,
        sub_dirs=sub_dirs,
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )


def save_vul(
    obj: Any, *, fname: str, sub_dirs: list[str] | None = None, **kwargs: Any
) -> None:
    """Save obj under the vul module's area of the versioned data store.

    Args:
        obj: The object to save (a GeoDataFrame, DataFrame, DataArray, dict,
            or any picklable object, depending on ``fname``'s suffix).
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to save under, within the vul area.
        **kwargs: Passed through to ``tdrive_sync.local_save``.
    """
    _save("vul", obj, fname=fname, sub_dirs=sub_dirs, **kwargs)


def read_vul(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file from the vul module's area of the versioned data store.

    Args:
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to read from, within the vul area.
        copy_to_local: Passed through to ``tdrive_sync.local_read``.
        return_path: If True, return the resolved path instead of reading it.
        **kwargs: Passed through to ``tdrive_sync.local_read``.

    Returns:
        The file's content, or its resolved path if ``return_path`` is True.
    """
    return _read(
        "vul",
        fname=fname,
        sub_dirs=sub_dirs,
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )


def save_loss(
    obj: Any, *, fname: str, sub_dirs: list[str] | None = None, **kwargs: Any
) -> None:
    """Save obj under the loss module's area of the versioned data store.

    Args:
        obj: The object to save (a GeoDataFrame, DataFrame, DataArray, dict,
            or any picklable object, depending on ``fname``'s suffix).
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to save under, within the loss area.
        **kwargs: Passed through to ``tdrive_sync.local_save``.
    """
    _save("loss", obj, fname=fname, sub_dirs=sub_dirs, **kwargs)


def read_loss(
    *,
    fname: str,
    sub_dirs: list[str] | None = None,
    copy_to_local: bool = True,
    return_path: bool = False,
    **kwargs: Any,
) -> Any:
    """Read a file from the loss module's area of the versioned data store.

    Args:
        fname: The file's name, including its suffix.
        sub_dirs: Subdirectories to read from, within the loss area.
        copy_to_local: Passed through to ``tdrive_sync.local_read``.
        return_path: If True, return the resolved path instead of reading it.
        **kwargs: Passed through to ``tdrive_sync.local_read``.

    Returns:
        The file's content, or its resolved path if ``return_path`` is True.
    """
    return _read(
        "loss",
        fname=fname,
        sub_dirs=sub_dirs,
        copy_to_local=copy_to_local,
        return_path=return_path,
        **kwargs,
    )
