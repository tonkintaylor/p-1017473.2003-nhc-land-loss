"""Atomic, parallel-safe file copying.

Ported from the National Liquefaction Model's ``common.io.public.local``.
"""

import os
import shutil
import tempfile
from pathlib import Path


def copy_one(src_fp: Path, dst_fp: Path) -> None:
    """Copy a single file into place, tolerating a concurrent copy of it.

    Steps run in parallel groups over a shared cache, so two of them can
    decide the same file is missing and copy it at the same time. Writing
    straight to the destination would mean one holds it open while the other
    opens it for writing, which on Windows raises ``PermissionError`` rather
    than harmlessly duplicating identical bytes.

    Every racer copies the same source, so the destination ends up the same
    either way. Each stages its copy under a unique name and swaps it in; if
    the swap loses (Windows refuses to replace a file another process has
    open) the winner has already put those exact bytes there, so the loser
    concedes rather than failing. Staging also means a reader never sees a
    half-written file.

    Args:
        src_fp: The file to copy.
        dst_fp: Where to copy it to. Its parent directory must already exist.
    """
    handle, tmp_name = tempfile.mkstemp(
        dir=dst_fp.parent, prefix=f"{dst_fp.name}.", suffix=".tmp"
    )
    os.close(handle)
    tmp_fp = Path(tmp_name)
    try:
        shutil.copy2(src_fp, tmp_fp)
        try:
            tmp_fp.replace(dst_fp)
        except OSError:
            if not dst_fp.exists():
                raise
    finally:
        tmp_fp.unlink(missing_ok=True)


def copy_to(*, src_path: Path, dst_path: Path) -> None:
    """Copy a file -- or, for a shapefile, all of its sidecar files -- into place.

    Args:
        src_path: The file to copy from.
        dst_path: Where to copy it to. Its parent directory is created if
            needed.
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if dst_path.suffix == ".shp":
        for src_fp in src_path.parent.glob(f"{src_path.stem}.*"):
            copy_one(src_fp, dst_path.parent / src_fp.name)
    else:
        copy_one(src_path, dst_path)
