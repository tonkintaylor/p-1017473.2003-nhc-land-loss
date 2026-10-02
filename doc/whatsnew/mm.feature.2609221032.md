The National Liquefaction Model release is now pinned in one place for the whole
study. `CORE_NLM_VERSION` in `landloss.domain.constants` replaces `NLM_VERSION`
and `NLM_OBS_VERSION` there and the separate `CORE_NLM_VERSION` that lived in
`landloss.io.nlm`, so the scenario grids and the mapped land damage observations
resolve to the same release rather than to three constants that could drift
apart. The releases themselves are now the `NlmRelease` enum beside it — a
`StrEnum` that drops straight into a path join — which exists because the folder
names are punctuated inconsistently (`v2025p0_rc4` against `v2026p0rc4`) and are
easy to mistype. A reader that has to stay on an older release names the enum
member at the point of use instead of adding a second project-wide constant.

Note that the buffered land damage observations `gen_observed_damage_db.py`
reads were previously pinned to an older release than the rest of the study, on
the grounds that survey data does not change when the model is re-run and so was
not necessarily carried forward. They now read at `CORE_NLM_VERSION` like
everything else; the step's implementation plan carries an open check that the
`fragility/event_obs_buffered_no_map` folder exists under that release.

The Koordinates download cache location is now decided in exactly one place,
`landloss.io.koopcache_dir`, instead of each module reading `KOOPCACHE_DIR` for
itself. The four call sites had already drifted — `example_download_linz_data.py`
defaulted to a relative `.koopcache` resolved against the working directory while
the readers defaulted to the repo root — so the same script could fill two
caches depending on where it was run from. A relative `KOOPCACHE_DIR` is now
anchored to the repo root rather than the working directory, so an existing
`.env` carrying the `KOOPCACHE_DIR=.koopcache` that `.env.example` used to ship
stops scattering caches without anyone having to edit it; the template no longer
sets the variable at all. Clipped extents, DEM tiles and the
LINZ elevation catalogue all now hang off that one root, and
`readers.DEFAULT_CACHE_DIR` and `elevation.DEFAULT_CACHE_DIR` are gone in favour
of `landloss.io.DEFAULT_KOOPCACHE_DIR`.
