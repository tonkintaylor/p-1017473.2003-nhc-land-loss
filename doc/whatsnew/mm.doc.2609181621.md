Every hazard submodule under `src/scripts/landloss/hazard/` now carries a brief
`status.md` holding the current approach for that hazard and what will be done
next, in the sections `Approach`, `Where it is now`, `Next`, `Validation` and
`Open decisions`. It is the module-level orientation page, distinct from the
per-step implementation plan and method files, which it points at rather than
restates.

`hazard/shaking/status.md` is the first one: the port of the NLM's
`gen_pga_layer`, the switch to the Foster V<sub>s</sub>30 model for site class,
PGA and Sa(T₁) across the study extent at the 2500-year return period, the
empirical Sa(T₁) → PGV conversion, and the mean-PGA-per-site-class check against
NSHM. The convention is recorded in `AGENTS.md` and
`.agents/context/code-structure.md`.
