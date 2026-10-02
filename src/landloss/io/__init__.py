"""Readers and writers for the datasets the landloss models are built from.

:data:`ASSETS_DIR` is the one place the packaged data files are located from, so
a module elsewhere in the package reads them by importing it rather than by
counting ``parents[N]`` levels back to here -- a count that silently breaks the
moment that module moves into a submodule.

:data:`REPO_ROOT` anchors the default on-disk cache so it always lands in one
place regardless of the current working directory a script happens to be run
from.

:func:`koopcache_dir` is the single place the download cache location is decided.
Every reader that caches to disk asks it rather than reading ``KOOPCACHE_DIR``
for itself: when the lookup was repeated at each call site the defaults drifted
apart, and one of them resolved against the working directory, so the same
script cached to two different places depending on where it was run from.
"""

import os
from pathlib import Path

__all__ = [
    "ASSETS_DIR",
    "DEFAULT_KOOPCACHE_DIR",
    "KOOPCACHE_DIR_ENV_VAR",
    "REPO_ROOT",
    "koopcache_dir",
]


ASSETS_DIR = Path(__file__).resolve().parent / "assets"
REPO_ROOT = Path(__file__).resolve().parents[3]

# The environment variable overriding where downloads are cached, and where they
# go when it is unset. Absolute, because a bare ".koopcache" would land wherever
# a script happened to be run from -- an IDE run configuration and a terminal
# would then fill two separate caches with the same gigabyte of layers.
KOOPCACHE_DIR_ENV_VAR = "KOOPCACHE_DIR"
DEFAULT_KOOPCACHE_DIR = REPO_ROOT / ".koopcache"


def koopcache_dir(*subdirs: str, create: bool = True) -> Path:
    """Return the on-disk cache root, or a directory inside it.

    Args:
        subdirs: Path components below the cache root, e.g. ``"extents"``.
            Omit them for the root itself.
        create: Whether to create the directory. Pass False to ask where the
            cache would be without bringing it into existence -- reporting on
            it, say.

    Returns:
        The cache directory: :data:`DEFAULT_KOOPCACHE_DIR`, or
        :data:`KOOPCACHE_DIR_ENV_VAR` where that is set. A relative value in the
        variable is anchored to :data:`REPO_ROOT`, not to the working directory,
        so it names one cache rather than one per directory a script is run
        from. Point the variable at an absolute path to put the cache on another
        disk.
    """
    root = Path(os.environ.get(KOOPCACHE_DIR_ENV_VAR) or DEFAULT_KOOPCACHE_DIR)

    # The shipped .env.example set this to a bare ".koopcache" for a long time,
    # so plenty of .env files carry a relative value. Anchoring it here means
    # those keep working and stop depending on where the script was launched.
    if not root.is_absolute():
        root = REPO_ROOT / root

    path = root.joinpath(*subdirs)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
