The default on-disk caches (`.koopcache` for Koordinates/DEM downloads,
`.tdrivecache` for `tdrive_sync`'s local mirror) are no longer resolved
against the current working directory. A bare relative path scattered a
separate copy under every directory a script happened to be run from (e.g.
an IDE run configuration's working directory) instead of sharing one cache
at the project root. `.koopcache` is now anchored to the repo root via
`landloss.io.REPO_ROOT`, and `tdrive_sync`'s cache dir is anchored to the
directory holding `tdrive_sync_config.py` unless `TTDRIVE_SYNC_CACHE_DIR` (or
`KOOPCACHE_DIR`) is set to an absolute path.
