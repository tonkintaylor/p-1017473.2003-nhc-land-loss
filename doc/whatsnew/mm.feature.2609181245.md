Added the first `vul` step, `s1_ces_observed_damage`, which builds the Canterbury
observed land damage database: NHC's settled earthquake sequence losses joined
spatially to the National Liquefaction Model's mapped land damage observations
and its per-event LSN grid, one row per property per event. Added
`fig_land_damage_v_lsn.py` under `vul/report/`, which plots settled land damage
against LSN split by observed land damage category. The National Liquefaction
Model release is now pinned as `NLM_VERSION` and `NLM_OBS_VERSION` in
`landloss.domain.constants`.
