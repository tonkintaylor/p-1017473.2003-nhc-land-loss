`gen_observed_damage_db.py` and `fig_land_damage_v_lsn.py` now write and read
the observed damage database through `landloss.io.versioned_store`'s
`save_vul`/`read_vul` instead of a hardcoded `T:` path, so the database follows
`DATA_VERSION` and local-only working mode like the rest of the versioned data
store. `--out`/`--database` accordingly work differently: `gen_observed_damage_db.py`
no longer takes an `--out` argument, and `fig_land_damage_v_lsn.py`'s
`--database` is now an explicit override rather than a `T:`-path default.
