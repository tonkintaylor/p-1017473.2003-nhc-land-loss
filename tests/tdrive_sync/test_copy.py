"""Tests for the atomic, parallel-safe copy helpers."""

import threading
from pathlib import Path

from tdrive_sync import _copy


def test_copy_one_creates_the_destination(tmp_path: Path) -> None:
    """A plain copy produces a destination file with the source's content."""
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"

    _copy.copy_one(src, dst)

    assert dst.read_text() == "hello"


def test_copy_one_does_not_leave_a_staging_file_behind(tmp_path: Path) -> None:
    """The temporary file used to stage the copy is cleaned up afterwards."""
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "dst.txt"

    _copy.copy_one(src, dst)

    assert set(tmp_path.iterdir()) == {src, dst}


def test_copy_to_creates_missing_parent_directories(tmp_path: Path) -> None:
    """copy_to makes the destination's parent directory if it does not exist."""
    src = tmp_path / "src.txt"
    src.write_text("hello")
    dst = tmp_path / "a" / "b" / "dst.txt"

    _copy.copy_to(src_path=src, dst_path=dst)

    assert dst.read_text() == "hello"


def test_copy_to_copies_shapefile_sidecars(tmp_path: Path) -> None:
    """A .shp destination copies every sidecar file alongside it, not just the .shp."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        (src_dir / f"data{suffix}").write_text(suffix)

    dst_dir = tmp_path / "dst"

    _copy.copy_to(src_path=src_dir / "data.shp", dst_path=dst_dir / "data.shp")

    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        assert (dst_dir / f"data{suffix}").read_text() == suffix


def test_concurrent_copies_of_the_same_file_both_succeed(tmp_path: Path) -> None:
    """Two "racing" copies to the same destination must not raise or corrupt it.

    Adapted from the reasoning in copy_one's docstring: parallel steps can
    decide the same cache file is missing and copy it at the same time.
    """
    src = tmp_path / "src.txt"
    src.write_text("race" * 1000)
    dst = tmp_path / "dst.txt"
    errors: list[Exception] = []

    def worker() -> None:
        try:
            _copy.copy_one(src, dst)
        except OSError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert dst.read_text() == src.read_text()
