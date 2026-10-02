# Step 5 — PGV realisation: method

- The step writes one peak ground velocity field per realisation, per 100 m
  cell, in m/s. It is run by `gen_pgv_realisations.py`, with the extent and
  realisations set in `config.py`; its `RETURN_PERIOD_YR` is step 3's own
  (`s3_pgv/config.py`, 2500 years), imported rather than repeated, so the step
  always reads the grid step 3 wrote.
- **The grid and the PGV come from step 3**: `read_pgv()` reads the grid
  `s3_pgv/gen_pgv.py` wrote at the configured return period, found through
  `gen_pgv.output_path("pgv", ...)`, so the cells, the site class each carries
  and the gaps are step 3's. A cell step 3 left without a value carries none.
- **A realisation is the field scaled by one lognormal draw**, from
  `landloss.hazard.shaking.pgv.beta_pgv_realisation`, against the same 10%
  coefficient of variation as step 4 (`landloss.hazard.shaking.pga.BETA_PGA_COV`).
  One multiplier covers the whole field, so every property moves together
  within a realisation. The run prints the factor.
- **The factor is step 4's.** The draw is seeded by
  `realisation_seed(BASE_SEED, realisation_id, "shaking")`, the stream name
  imported from `s4_pga_realisation/gen_pga_realisations.py`, and
  `beta_pgv_realisation` makes the one draw `beta_scale_factor` makes, which is
  the first and only draw step 4's `beta_pga_realisation` makes on that
  generator. Step 4 writes no factor; this step recomputes it. The tests in
  `tests/landloss/hazard/shaking/test_pga.py` and `test_pgv.py` assert the
  three agree, so the two steps cannot drift.
- The output is `temp/hazard/shaking/pgv-rNNN[-pilot].tif` from
  `pgv_path()`, a float32 raster of PGV in m/s named `pgv_m_s`, on
  the step 2 site class grid, NaN where step 3 had none.
- The supplied field and each realisation are mapped side by side on one colour
  scale in the figure produced by `fig_pgv_realisations.py`, written to
  `report/hazard/shaking/pgv-realisation/fig/`.
- Nothing downstream reads this step yet; the urban slope realisation and the
  flat-land wall damage state step (contract sections 3.10 and 3.11) are the
  readers it is written for.

Potential future improvements: see `s5_pgv_realisation_implementation_plan.md`.
