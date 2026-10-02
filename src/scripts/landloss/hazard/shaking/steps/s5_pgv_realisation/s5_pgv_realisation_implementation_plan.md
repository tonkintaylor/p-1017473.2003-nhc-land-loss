# Step 5 — PGV realisation: implementation plan

**Status:** Phase 1 complete: built and tested on synthetic grids; not yet run
over the pilot (no `pgv-rNNN` file exists). Phase 0 of
`.agents/plans/building-urban-slope-failure-and-retaining-wall-models.md`; the
contract is section 3.0 of `.agents/plans/urban-slope-build-contract.md`.

## Phase 1 — PGV per realisation (complete)

- [x] Read the PGV grid step 3 wrote at the configured return period and over
      the configured extent.
- [x] Scale it by the lognormal factor step 4 drew for the same realisation id,
      recomputed from the same seed rather than read from a file step 4 does
      not write, so the two fields of one modelled earthquake agree.
- [x] Hold the two steps together with a unit test: `beta_pga_realisation`'s
      factor equals `beta_scale_factor` on a generator seeded the same way, and
      `beta_pgv_realisation` takes that same factor.
- [x] Write `temp/hazard/shaking/pgv-rNNN[-pilot].tif` through
      `pgv_path()`, and draw the supplied field beside each
      realisation.
- [x] Run this step from `hazard/gen_hazard.py` after step 4
      (`gen_hazard.main`).
- [x] Take `RETURN_PERIOD_YR` from step 3's `config.py`, so the return period
      of the PGV grid is set in one place.
- [ ] Run over the pilot once step 3 has written the PGV grid, and review the
      printed factor and the figure.

## Phase 2 — A defensible spread

- [ ] When step 4 replaces the flat 10% coefficient of variation with the
      ground motion model's own sigma, take the PGV sigma from the same model
      rather than reusing the PGA one: the two measures have different
      dispersions.
- [ ] When step 4 moves to a spatially correlated random field, scale PGV by
      the same field, which then has to be written by step 4 and read here
      rather than recomputed from the seed.

## Potential future improvements

- Carry the realisation factor in the raster's metadata, so a downstream reader
  can see which draw a field is without recomputing it.
