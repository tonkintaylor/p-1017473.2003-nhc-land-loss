Added `src/tdrive_sync` (imported as `ts`), a generic package for saving and
reading this project's own versioned intermediate/output data on the shared
`T:` drive, and `landloss.io.versioned_store`
(`save_hazard`/`read_hazard`, `save_exposure`/`read_exposure`,
`save_vul`/`read_vul`, `save_loss`/`read_loss`), a thin per-module layer on top
of it. `BASE_DIR`/`DATA_VERSION` are set in a new, committed
`tdrive_sync_config.py` at the repo root; normal saves refuse to overwrite an
existing file unless `DATA_VERSION = "SCRATCH"`. New `TTDRIVE_SYNC_LOCAL_MODE`/
`TTDRIVE_SYNC_LOCAL_VERSION`/`TTDRIVE_SYNC_CACHE_DIR` environment variables
switch reads and writes to a private, disposable local cache instead of `T:`.
See `README.md`'s "Environment variables" section for the full behaviour.
