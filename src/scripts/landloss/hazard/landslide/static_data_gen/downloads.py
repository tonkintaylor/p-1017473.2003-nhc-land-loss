"""Download a file into the project's SourceMaterial folder on T:.

Shared by the ``get_`` scripts beside it. Each script names its files by their
path below ``SourceMaterial`` -- the constants in
:mod:`landloss.domain.constants` that the readers in
:mod:`landloss.io.global_datasets` read back -- so the writing side and the
reading side cannot disagree about where a file lives.
"""

import shutil
import zipfile
from pathlib import Path

import requests

import tdrive_sync

# Large enough that a gigabyte file prints a few dozen progress lines, not
# thousands.
_CHUNK_BYTES = 8 * 1024 * 1024
_PROGRESS_EVERY_BYTES = 64 * 1024 * 1024
_TIMEOUT_S = 120


def get_file_to_source_material(url: str, relative_path: str) -> Path:
    """Download ``url`` to ``relative_path`` below SourceMaterial on T:.

    The download goes to a ``.part`` file first and is renamed only once
    complete, so an interrupted run never leaves a truncated file under the
    final name for a reader to pick up. A file already present is left alone
    and not downloaded again: delete it to force a fresh copy.

    Args:
        url: Where to download from.
        relative_path: The destination below ``SOURCE_MATERIAL_DIR``.

    Returns:
        The destination path on T:.
    """
    destination = tdrive_sync.get_source_mat_base_path(relative_path)
    if destination.exists():
        print(f"Already present, skipped: {destination}")
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    print(f"Downloading {url}\n  to {destination}")
    with requests.get(url, stream=True, timeout=_TIMEOUT_S) as response:
        response.raise_for_status()
        written = 0
        next_report = _PROGRESS_EVERY_BYTES
        with partial.open("wb") as out:
            for chunk in response.iter_content(chunk_size=_CHUNK_BYTES):
                out.write(chunk)
                written += len(chunk)
                if written >= next_report:
                    print(f"  {written / 1e6:,.0f} MB")
                    next_report += _PROGRESS_EVERY_BYTES
    partial.replace(destination)
    print(f"  done, {destination.stat().st_size / 1e6:,.1f} MB")
    return destination


def extract_member_to_source_material(
    archive: Path, member: str, relative_path: str
) -> Path:
    """Extract one file of a zip into SourceMaterial on T:.

    Args:
        archive: The zip, already downloaded.
        member: The file's name inside the zip.
        relative_path: The destination below ``SOURCE_MATERIAL_DIR``.

    Returns:
        The destination path on T:. A file already present is left alone.
    """
    destination = tdrive_sync.get_source_mat_base_path(relative_path)
    if destination.exists():
        print(f"Already present, skipped: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    with (
        zipfile.ZipFile(archive) as zf,
        zf.open(member) as src,
        partial.open("wb") as out,
    ):
        shutil.copyfileobj(src, out, length=_CHUNK_BYTES)
    partial.replace(destination)
    print(f"Extracted {member}\n  to {destination}")
    return destination
