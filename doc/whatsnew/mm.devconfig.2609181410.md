`gen_observed_damage_db.py` and `fig_land_damage_v_lsn.py` no longer take
command-line arguments (`--losses`/`--obs-dir`/`--lsn-dir` and
`--database`/`--event`/`--out-dir` respectively). The loss GeoPackage is now
fetched from T:'s SourceMaterial through `tdrive_sync.get_source_mat` (caching
it locally), and the other paths are fixed, so there is nothing left to point
elsewhere at. `AGENTS.md` now documents this as a standing rule: scripts under
`src/scripts/` must not use `argparse` to make paths or other settings
configurable.
