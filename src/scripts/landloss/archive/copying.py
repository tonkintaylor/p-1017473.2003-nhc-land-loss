"""Copy files to T: without ever overwriting, and record what was copied.

Both archive scripts plan a list of (source, target) pairs, print it, and copy
only when asked. The rules are ``tdrive_sync.local_save``'s: a target that
already exists is never replaced. One with the same contents is skipped, so an
interrupted copy can be run again; one with different contents stops the whole
copy before anything is written.
"""

import csv
import hashlib
import os
import pickle
import shutil
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import rasterio
from rasterio.windows import Window

from scripts.landloss.paths import REPO_ROOT

# Read in blocks of 8 MiB, so hashing a 2 GB DEM never holds it in memory.
HASH_BLOCK_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class PlannedCopy:
    """One file to copy, with what the manifest says about it."""

    source: Path
    target: Path
    group: str
    note: str = ""


def sha256(path: Path) -> str:
    """Return a file's SHA-256 as hex, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(HASH_BLOCK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def damage(path: Path) -> str | None:
    """Return why a file is not whole, or None when it reads to its end.

    A copy cut short still opens by its header, so each kind is read where a
    short file fails: a Parquet file's footer and last row group, a GeoTIFF's
    last row, a GeoPackage's own integrity check, a pickle whole. Other files
    (CSV, JSON, HTML, images) are taken as they are.
    """
    try:
        if path.suffix in (".parquet", ".geoparquet"):
            meta = pq.read_metadata(path)
            if meta.num_row_groups:
                pq.ParquetFile(path).read_row_group(
                    meta.num_row_groups - 1, columns=[meta.schema.names[0]]
                )
        elif path.suffix == ".tif":
            with rasterio.open(path) as raster:
                raster.read(1, window=Window(0, raster.height - 1, raster.width, 1))
        elif path.suffix == ".gpkg":
            with closing(
                sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
            ) as db:
                result = db.execute("pragma quick_check").fetchone()[0]
            if result != "ok":
                return f"GeoPackage check: {result}"
        elif path.suffix == ".pkl":
            with path.open("rb") as file:
                pickle.load(file)  # noqa: S301 -- this project's own cache files
    except Exception as error:
        return f"{type(error).__name__}: {str(error)[:120]}"
    return None


def check_sources(plan: list[PlannedCopy]) -> None:
    """Refuse a plan holding any file that is not whole, naming each.

    Raises:
        OSError: If any source is damaged. Nothing has been copied.
    """
    damaged = [
        (item.source, reason) for item in plan if (reason := damage(item.source))
    ]
    if damaged:
        names = "\n  ".join(f"{path} ({reason})" for path, reason in damaged)
        msg = (
            f"{len(damaged)} source files are not whole, so nothing is copied:\n  "
            f"{names}\nCopy them again from the run that built them."
        )
        raise OSError(msg)


def git_commit() -> str:
    """Return the repo's commit, with ``-dirty`` when it has local changes."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    commit = git("rev-parse", "--short=7", "HEAD") or "unknown"
    return (
        f"{commit}-dirty"
        if git("status", "--porcelain", "--untracked-files=no")
        else commit
    )


def stamp() -> str:
    """Return the time now as yymmddhhmm, to name this archive's own records."""
    return datetime.now(UTC).astimezone().strftime("%y%m%d%H%M")


def describe_plan(plan: list[PlannedCopy]) -> None:
    """Print how many files and bytes each group holds, and the total."""
    groups: dict[str, list[PlannedCopy]] = {}
    for item in plan:
        groups.setdefault(item.group, []).append(item)
    total = 0
    for group, items in sorted(groups.items()):
        size = sum(item.source.stat().st_size for item in items)
        total += size
        print(f"  {group:<36} {len(items):>5} files {size / 1e9:>8.2f} GB")
    print(f"  {'total':<36} {len(plan):>5} files {total / 1e9:>8.2f} GB")


def write_plan_csv(plan: list[PlannedCopy], path: Path) -> None:
    """Write the plan as a CSV on local disk, for reading before a copy."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["group", "source", "target", "bytes", "note"])
        for item in plan:
            writer.writerow(
                [
                    item.group,
                    item.source,
                    item.target,
                    item.source.stat().st_size,
                    item.note,
                ]
            )


def check_targets(
    plan: list[PlannedCopy],
) -> tuple[list[PlannedCopy], list[PlannedCopy]]:
    """Split the plan into files still to copy and files already there unchanged.

    Raises:
        FileExistsError: If any target exists with different contents, naming
            up to ten of them. Nothing has been copied when it is raised.
    """
    todo, done, clashes = [], [], []
    for item in plan:
        if not item.target.exists():
            todo.append(item)
        elif item.target.stat().st_size == item.source.stat().st_size and sha256(
            item.target
        ) == sha256(item.source):
            done.append(item)
        else:
            clashes.append(item)
    if clashes:
        names = "\n  ".join(str(item.target) for item in clashes[:10])
        msg = (
            f"{len(clashes)} targets already exist with different contents, and are "
            f"never overwritten:\n  {names}\nMove them aside, or archive to "
            "another version, and run again. Nothing was copied."
        )
        raise FileExistsError(msg)
    return todo, done


def copy_file(item: PlannedCopy) -> None:
    """Copy one file to its target through a partial file, then check its size.

    Raises:
        OSError: If the copy's size differs from the source's.
    """
    item.target.parent.mkdir(parents=True, exist_ok=True)
    partial = item.target.with_name(f"{item.target.name}.partial")
    shutil.copy2(item.source, partial)
    if partial.stat().st_size != item.source.stat().st_size:
        partial.unlink()
        msg = f"{item.target} was copied short; nothing was kept"
        raise OSError(msg)
    os.replace(partial, item.target)


def write_manifest(plan: list[PlannedCopy], path: Path, *, root: Path) -> None:
    """Write what was copied: path under ``root``, source, size, time and hash.

    Raises:
        FileExistsError: If the manifest's own path is already taken.
    """
    if path.exists():
        msg = f"{path} already exists; it is never overwritten"
        raise FileExistsError(msg)
    with path.open("x", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            ["path", "group", "source", "bytes", "source_modified", "sha256", "note"]
        )
        for item in plan:
            info = item.source.stat()
            modified = datetime.fromtimestamp(info.st_mtime, UTC).astimezone()
            writer.writerow(
                [
                    item.target.relative_to(root).as_posix(),
                    item.group,
                    item.source,
                    info.st_size,
                    modified.isoformat(timespec="seconds"),
                    sha256(item.source),
                    item.note,
                ]
            )


def run_copy(plan: list[PlannedCopy]) -> None:
    """Copy every file not already there, after checking each is whole and none
    would be replaced."""
    print("Checking every source file is whole ...", flush=True)
    check_sources(plan)
    print("Checking the targets on T: ...", flush=True)
    todo, done = check_targets(plan)
    print(f"  {len(done):,} already there and identical; {len(todo):,} to copy")
    for number, item in enumerate(todo, start=1):
        size = item.source.stat().st_size / 1e6
        print(f"  [{number}/{len(todo)}] {item.target} ({size:,.1f} MB)", flush=True)
        copy_file(item)
