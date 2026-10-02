"""Tests for the one place the download cache location is decided."""

from pathlib import Path

import pytest

from landloss.io import (
    DEFAULT_KOOPCACHE_DIR,
    KOOPCACHE_DIR_ENV_VAR,
    REPO_ROOT,
    elevation,
    koopcache_dir,
    readers,
)


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every cache directory these tests create out of the working tree."""
    monkeypatch.setenv(KOOPCACHE_DIR_ENV_VAR, str(tmp_path / "koopcache"))


def test_the_default_is_anchored_to_the_repo_root() -> None:
    """The default must not be a bare relative path.

    A relative ".koopcache" resolves against whatever the current working
    directory happens to be, so it scatters a separate cache under every
    directory a script is ever run from instead of sharing one.
    """
    assert DEFAULT_KOOPCACHE_DIR.is_absolute()
    assert DEFAULT_KOOPCACHE_DIR.name == ".koopcache"
    assert DEFAULT_KOOPCACHE_DIR.parent == REPO_ROOT


def test_the_environment_variable_overrides_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A developer can move the cache off the repo's disk without editing code."""
    monkeypatch.setenv(KOOPCACHE_DIR_ENV_VAR, str(tmp_path / "elsewhere"))

    assert koopcache_dir() == tmp_path / "elsewhere"


def test_a_relative_override_is_anchored_to_the_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative value must not resolve against the working directory.

    The shipped ``.env.example`` set this to a bare ".koopcache" for a long time,
    so many ``.env`` files carry one. Left to resolve against the cwd it fills a
    separate cache under every directory a script is ever launched from, which is
    the whole failure this resolver exists to prevent.
    """
    monkeypatch.setenv(KOOPCACHE_DIR_ENV_VAR, ".koopcache")

    assert koopcache_dir(create=False) == REPO_ROOT / ".koopcache"


def test_an_empty_environment_variable_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unset variable and one set to nothing mean the same thing.

    A blank value in a ``.env`` file would otherwise resolve to the working
    directory, which is the failure this resolver exists to prevent.
    """
    monkeypatch.setenv(KOOPCACHE_DIR_ENV_VAR, "")

    assert koopcache_dir(create=False) == DEFAULT_KOOPCACHE_DIR


def test_subdirectories_hang_off_the_one_root() -> None:
    """Each kind of download gets its own drawer, not its own cache."""
    root = koopcache_dir()

    assert koopcache_dir("extents").parent == root
    assert koopcache_dir("dem").parent == root


def test_the_directory_is_created() -> None:
    """A caller can write into what it is handed without checking first."""
    assert koopcache_dir("extents").is_dir()


def test_create_false_does_not_bring_the_directory_into_existence() -> None:
    """Asking where the cache is should not make one; some callers only report it."""
    path = koopcache_dir("nothing-here", create=False)

    assert not path.exists()


def test_every_reader_caches_under_the_same_root() -> None:
    """The point of the resolver: one cache, not one per module that downloads.

    These three resolved independently before, and the defaults had already
    drifted -- the example script's was relative while the readers' were not.
    """
    root = koopcache_dir()
    paths = [
        readers.extent_cache_dir(),
        readers.dem_cache_path(bbox=(0, 0, 1, 1), resolution=10, crs="EPSG:2193"),
        elevation.cache_dir(),
    ]

    for path in paths:
        assert root in path.parents
